# app_core/analysis/sarimax_utils.py
from __future__ import annotations

import math
from typing import Optional, Tuple, Dict, Any

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX


def _pandas_freq(freq: str) -> str:
    """Normalize freq strings so pandas doesn't emit FutureWarning for 'H'."""
    f = str(freq)
    return "h" if f.upper() == "H" else f


def aggregate_freq(df_energy: pd.DataFrame, df_weather: pd.DataFrame, freq: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Align energy and weather at requested frequency.
    freq: "h" or "D"
      - Energy (kWh): hourly as-is; daily = sum
      - Weather: daily temp/wind mean; precipitation sum
    """
    if df_energy.empty:
        return pd.DataFrame(columns=["quantity_kwh"]), pd.DataFrame()

    freq = _pandas_freq(freq)

    if freq == "h":
        e = df_energy.set_index("time").asfreq("h")
        e["quantity_kwh"] = pd.to_numeric(e["quantity_kwh"], errors="coerce").fillna(0.0)

        w = df_weather.set_index("time").asfreq("h") if not df_weather.empty else pd.DataFrame(index=e.index)
        for col in w.columns:
            if col == "precipitation (mm)":
                w[col] = pd.to_numeric(w[col], errors="coerce").fillna(0.0)
            else:
                w[col] = pd.to_numeric(w[col], errors="coerce").interpolate(limit=6)
        return e, w

    # Daily
    e = (
        df_energy.set_index("time")
        .resample("D")["quantity_kwh"]
        .sum()
        .to_frame()
    )

    if df_weather.empty:
        return e, pd.DataFrame(index=e.index)

    agg: dict[str, str] = {}
    for c in df_weather.columns:
        if c == "time":
            continue
        agg[c] = "sum" if "precipitation" in c else "mean"

    w = df_weather.set_index("time").resample("D").agg(agg)
    return e, w


def build_exog_future(exog_train: Optional[pd.DataFrame], horizon: int, freq: str, strategy: str) -> Optional[pd.DataFrame]:
    """
    Create future exogenous values for forecasting.
      - 'last': repeat last observed row
      - 'hod-mean': hour-of-day mean (hourly) / day-of-week mean (daily)
    """
    if exog_train is None or exog_train.empty:
        return exog_train

    freq = _pandas_freq(freq)

    last_index = exog_train.index[-1]
    if freq == "h":
        fut_index = pd.date_range(last_index + pd.Timedelta(hours=1), periods=horizon, freq="h", tz="UTC")
    else:
        fut_index = pd.date_range(last_index + pd.Timedelta(days=1), periods=horizon, freq="D", tz="UTC")

    if strategy == "last":
        fut_vals = pd.DataFrame(
            np.repeat(exog_train.iloc[[-1]].to_numpy(), horizon, axis=0),
            index=fut_index,
            columns=exog_train.columns,
        )
    elif strategy == "hod-mean":
        fut_vals = pd.DataFrame(index=fut_index, columns=exog_train.columns, dtype=float)
        if freq == "h":
            means = exog_train.groupby(exog_train.index.hour).mean(numeric_only=True)
            fut_vals.loc[:] = [means.loc[h].values for h in fut_index.hour]
        else:
            means = exog_train.groupby(exog_train.index.dayofweek).mean(numeric_only=True)
            fut_vals.loc[:] = [means.loc[d].values for d in fut_index.dayofweek]
    else:
        fut_vals = pd.DataFrame(
            np.repeat(exog_train.iloc[[-1]].to_numpy(), horizon, axis=0),
            index=fut_index,
            columns=exog_train.columns,
        )

    fut_vals = fut_vals.astype(float).interpolate(limit=6).bfill().ffill()
    return fut_vals


def mae(y_true: pd.Series, y_pred: pd.Series) -> float:
    a = (y_true - y_pred).abs().dropna()
    return float(a.mean()) if len(a) else float("nan")


def rmse(y_true: pd.Series, y_pred: pd.Series) -> float:
    a = (y_true - y_pred).dropna()
    if not len(a):
        return float("nan")
    return float(np.sqrt(np.mean(a.to_numpy() ** 2)))


def mase(y_true: pd.Series, y_pred: pd.Series, y_train: pd.Series, m: int) -> float:
    y_train = y_train.dropna()
    if len(y_train) < 3:
        return float("nan")

    if len(y_train) <= m:
        scale = float(y_train.diff().abs().dropna().mean())  # fallback
    else:
        scale = float(np.mean(np.abs(y_train.iloc[m:].to_numpy() - y_train.iloc[:-m].to_numpy())))

    if not np.isfinite(scale) or scale == 0:
        return float("nan")

    return mae(y_true, y_pred) / scale


def seasonal_naive_forecast(y_train: pd.Series, horizon: int, m: int, freq: str) -> pd.Series:
    y_train = y_train.dropna()
    if len(y_train) == 0:
        return pd.Series(dtype=float)

    m_eff = max(1, min(int(m), len(y_train)))
    last_season = y_train.iloc[-m_eff:].to_numpy()
    reps = int(math.ceil(horizon / m_eff))
    vals = np.tile(last_season, reps)[:horizon]

    pfreq = _pandas_freq(freq)

    idx = pd.date_range(
        y_train.index[-1] + pd.tseries.frequencies.to_offset(pfreq),
        periods=horizon,
        freq=pfreq,
        tz="UTC",
    )
    return pd.Series(vals, index=idx)


def _flatten_summary_cols(df: pd.DataFrame) -> pd.DataFrame:
    cols = []
    for c in df.columns:
        if isinstance(c, tuple):
            cols.append(c[0] if c[1] == "" else f"{c[0]}_{c[1]}")
        else:
            cols.append(str(c))
    df = df.copy()
    df.columns = cols
    return df


def rolling_origin_backtest_sarimax(
    y_values: pd.Series,
    X_values: Optional[pd.DataFrame],
    freq: str,
    horizon: int,
    step_size: int,
    folds: int,
    m_seasonal: int,
    order: Tuple[int, int, int],
    seasonal_order: Tuple[int, int, int, int],
    eval_no_exog: bool,
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Rolling-origin backtest inside the provided y_values span.
    Returns:
      - summary table: mean/std by model for MAE/RMSE/MASE
      - artifacts for plotting last fold: y_test, baseline, sarimax_best, sarimax_no_exog, sarimax_exog
    """
    freq = _pandas_freq(freq)

    y = y_values.dropna().copy()
    if len(y) < (horizon + max(60, 2 * max(1, m_seasonal))):
        return pd.DataFrame(), {}

    X = None
    if X_values is not None and not X_values.empty:
        X = X_values.reindex(y.index).copy().astype(float)
        X = X.interpolate(limit=6).bfill().ffill()

    min_train = max(
        60,
        2 * max(1, m_seasonal),
        5 * (order[0] + order[2] + seasonal_order[0] + seasonal_order[2] + 1),
    )
    last_cutoff_pos = len(y) - horizon - 1
    cut_positions = [last_cutoff_pos - step_size * k for k in range(int(folds))][::-1]
    cut_positions = [p for p in cut_positions if p >= min_train]
    if not cut_positions:
        return pd.DataFrame(), {}

    def fit_forecast(
        y_train: pd.Series,
        X_train: Optional[pd.DataFrame],
        X_test: Optional[pd.DataFrame],
    ) -> Optional[pd.Series]:
        try:
            model = SARIMAX(
                endog=y_train,
                exog=X_train,
                order=order,
                seasonal_order=seasonal_order,
                enforce_stationarity=False,
                enforce_invertibility=False,
                freq=freq,
            )
            res = model.fit(disp=False)
            fc = res.get_forecast(steps=int(horizon), exog=X_test)
            return fc.predicted_mean
        except Exception:
            return None

    rows: list[dict] = []
    artifacts: dict = {}

    for pos in cut_positions:
        y_train = y.iloc[: pos + 1]
        y_test = y.iloc[pos + 1 : pos + 1 + horizon]

        y_base = seasonal_naive_forecast(y_train, horizon=int(horizon), m=int(m_seasonal), freq=freq)
        rows.append(
            {
                "model": "Seasonal naive",
                "fold": int(pos),
                "MAE": mae(y_test, y_base),
                "RMSE": rmse(y_test, y_base),
                "MASE": mase(y_test, y_base, y_train, m=int(m_seasonal)),
            }
        )

        # SARIMAX no exog
        y_hat_no = None
        if eval_no_exog or X is None:
            y_hat_no = fit_forecast(y_train, None, None)
            if y_hat_no is not None:
                rows.append(
                    {
                        "model": "SARIMAX (no exog)",
                        "fold": int(pos),
                        "MAE": mae(y_test, y_hat_no),
                        "RMSE": rmse(y_test, y_hat_no),
                        "MASE": mase(y_test, y_hat_no, y_train, m=int(m_seasonal)),
                    }
                )

        # SARIMAX with exog
        y_hat_ex = None
        if X is not None:
            X_train = X.iloc[: pos + 1]
            X_test = X.iloc[pos + 1 : pos + 1 + horizon]
            y_hat_ex = fit_forecast(y_train, X_train, X_test)
            if y_hat_ex is not None:
                rows.append(
                    {
                        "model": "SARIMAX (+exog)",
                        "fold": int(pos),
                        "MAE": mae(y_test, y_hat_ex),
                        "RMSE": rmse(y_test, y_hat_ex),
                        "MASE": mase(y_test, y_hat_ex, y_train, m=int(m_seasonal)),
                    }
                )

        if pos == cut_positions[-1]:
            artifacts = {
                "y_test": y_test,
                "baseline": y_base,
                "sarimax_no_exog": y_hat_no,
                "sarimax_exog": y_hat_ex,
            }
            artifacts["sarimax_best"] = y_hat_ex if y_hat_ex is not None else y_hat_no

    df_folds = pd.DataFrame(rows)
    summary = df_folds.groupby("model")[["MAE", "RMSE", "MASE"]].agg(["mean", "std"]).reset_index()
    summary = _flatten_summary_cols(summary)

    order_models = ["Seasonal naive", "SARIMAX (no exog)", "SARIMAX (+exog)"]
    summary["__ord"] = summary["model"].apply(lambda x: order_models.index(x) if x in order_models else 999)
    summary = summary.sort_values("__ord").drop(columns="__ord").reset_index(drop=True)

    return summary, artifacts
