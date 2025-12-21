from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd
from scipy.fftpack import dct, idct
from sklearn.neighbors import LocalOutlierFactor


@dataclass(frozen=True)
class SPCSummary:
    sigma_robust: float
    keep_k: int
    n_points: int
    n_outliers: int
    max_abs_satv: float


def regularize_hourly(series: pd.Series, *, interp_limit: int = 6) -> pd.Series:
    """
    Make a series hourly on a regular grid and interpolate small gaps.
    Expects a tz-aware DatetimeIndex (UTC recommended).
    """
    s = pd.to_numeric(series, errors="coerce").asfreq("h")
    if interp_limit is None or int(interp_limit) <= 0:
       return s
    return s.interpolate(method="time", limit=int(interp_limit))


def dct_lowpass_trend(y: np.ndarray, keep_frac: float) -> Tuple[np.ndarray, int]:
    """DCT low-pass trend by keeping the first k coefficients."""
    y = np.asarray(y, dtype=float)
    coeff = dct(y, norm="ortho")
    k = max(1, int(len(y) * float(keep_frac)))
    coeff_lp = np.zeros_like(coeff)
    coeff_lp[:k] = coeff[:k]
    trend = idct(coeff_lp, norm="ortho")
    return trend, k


def robust_sigma_mad(resid: np.ndarray) -> float:
    """Robust sigma via MAD; fallback to std; never returns 0."""
    r = np.asarray(resid, dtype=float)
    med = np.median(r)
    mad = np.median(np.abs(r - med))
    if mad > 0:
        sig = 1.4826 * mad
    else:
        sig = float(np.std(r)) if float(np.std(r)) > 0 else 1.0
    return float(sig) if sig > 0 else 1.0


def spc_outliers_dct(
    series: pd.Series,
    *,
    keep_frac: float = 0.01,
    k_sigma: float = 3.0,
    interp_limit: int = 6,
) -> Tuple[pd.DataFrame, SPCSummary]:
    """
    SPC-style outlier detection:
      - hourly regularization + interpolation
      - DCT low-pass trend
      - control bands = trend ± k_sigma * sigma_robust(MAD)
      - SATV = (value - trend) / sigma_robust
    Returns:
      - out_df with columns: time,value,trend,lo,hi,satv,is_outlier
      - SPCSummary for UI
    """
    if series is None or series.empty:
        empty = pd.DataFrame(columns=["time", "value", "trend", "lo", "hi", "satv", "is_outlier"])
        summary = SPCSummary(1.0, 1, 0, 0, 0.0)
        return empty, summary

    s = regularize_hourly(series, interp_limit=interp_limit)
    n = int(s.notna().sum())
    if n < 24:
        empty = pd.DataFrame(columns=["time", "value", "trend", "lo", "hi", "satv", "is_outlier"])
        summary = SPCSummary(1.0, 1, n, 0, 0.0)
        return empty, summary

    y = s.ffill().bfill().to_numpy(dtype=float)
    trend, k = dct_lowpass_trend(y, keep_frac=keep_frac)

    resid = y - trend
    sigma = robust_sigma_mad(resid)

    hi = trend + float(k_sigma) * sigma
    lo = trend - float(k_sigma) * sigma
    is_out = (y > hi) | (y < lo)

    satv = resid / sigma if sigma else np.zeros_like(resid)
    max_abs_satv = float(np.max(np.abs(satv))) if len(satv) else 0.0

    out_df = pd.DataFrame(
        {
            "time": s.index.to_pydatetime(),
            "value": y,
            "trend": trend,
            "lo": lo,
            "hi": hi,
            "satv": satv,
            "is_outlier": is_out,
        }
    )

    summary = SPCSummary(
        sigma_robust=float(sigma),
        keep_k=int(k),
        n_points=len(out_df),
        n_outliers=int(np.sum(is_out)),
        max_abs_satv=max_abs_satv,
    )
    return out_df, summary


def lof_precip_anomalies(
    df: pd.DataFrame,
    *,
    time_col: str = "time",
    precip_col: str = "precipitation (mm)",
    contamination: float = 0.01,
    n_neighbors: int = 60,
    roll_hours: int = 24,
) -> Tuple[pd.DataFrame, int]:
    """
    LOF anomaly detection on precipitation using 2D features:
      X = [precip, rolling_mean(roll_hours)]
    Returns:
      - a_df with: time, precip, roll24, lof_score, is_anom
      - n_eff used for n_neighbors
    """
    if df is None or df.empty or time_col not in df.columns or precip_col not in df.columns:
        return pd.DataFrame(columns=["time", "precip", "roll24", "lof_score", "is_anom"]), 0

    s = pd.to_numeric(df[precip_col], errors="coerce").fillna(0.0)
    roll = s.rolling(int(roll_hours), min_periods=1).mean()

    X = np.column_stack([s.to_numpy(dtype=float), roll.to_numpy(dtype=float)])

    n_eff = min(int(n_neighbors), max(10, len(s) - 1))
    lof = LocalOutlierFactor(n_neighbors=n_eff, contamination=float(contamination))
    labels = lof.fit_predict(X)  # -1 = outlier
    scores = -lof.negative_outlier_factor_

    a_df = pd.DataFrame(
        {
            "time": df[time_col],
            "precip": s,
            "roll24": roll,
            "lof_score": scores,
            "is_anom": labels == -1,
        }
    )
    return a_df, int(n_eff)
