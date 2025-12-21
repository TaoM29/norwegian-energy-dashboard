import numpy as np
import pandas as pd

from app_core.analysis.data_quality import (
    robust_sigma_mad,
    dct_lowpass_trend,
    spc_outliers_dct,
    lof_precip_anomalies,
)


def test_robust_sigma_mad_positive():
    r = np.array([0, 0, 0, 0, 10], dtype=float)
    sig = robust_sigma_mad(r)
    assert np.isfinite(sig)
    assert sig > 0


def test_dct_lowpass_trend_shapes():
    rng = np.random.default_rng(0)
    y = rng.normal(0, 1, 500)
    trend, k = dct_lowpass_trend(y, keep_frac=0.01)
    assert len(trend) == len(y)
    assert k >= 1
    # low-pass trend usually reduces variance vs white noise
    assert np.var(trend) < np.var(y)


def test_spc_outliers_detects_single_spike():
    idx = pd.date_range("2024-01-01", periods=240, freq="h", tz="UTC")
    y = np.zeros(len(idx), dtype=float)
    y[120] = 50.0  # spike
    s = pd.Series(y, index=idx)

    out_df, summ = spc_outliers_dct(s, keep_frac=0.01, k_sigma=3.0, interp_limit=0)
    assert not out_df.empty
    assert summ.n_points == len(out_df)
    assert summ.n_outliers >= 1

    spike_time = idx[120].to_pydatetime()
    flagged = out_df.loc[out_df["time"] == spike_time, "is_outlier"].iloc[0]
    assert bool(flagged) is True


def test_spc_outliers_empty_or_too_short_returns_empty():
    idx = pd.date_range("2024-01-01", periods=10, freq="h", tz="UTC")
    s = pd.Series(np.arange(10, dtype=float), index=idx)

    out_df, summ = spc_outliers_dct(s)
    assert out_df.empty
    assert summ.n_points in (0, 10)  # depending on internal handling
    assert summ.n_outliers == 0


def test_lof_precip_anomalies_flags_big_event():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=400, freq="h", tz="UTC")
    y = rng.uniform(0.0, 0.02, size=len(idx))  # tiny noise instead of many identical zeros
    y[200] = 100.0
    df = pd.DataFrame({"time": idx, "precipitation (mm)": y})

    a_df, n_eff = lof_precip_anomalies(
        df,
        time_col="time",
        precip_col="precipitation (mm)",
        contamination=0.01,
        n_neighbors=50,
        roll_hours=24,
    )
    assert not a_df.empty
    assert n_eff >= 10
    assert "is_anom" in a_df.columns

    flagged = a_df.loc[a_df["time"] == idx[200], "is_anom"].iloc[0]
    assert bool(flagged) is True


def test_lof_precip_anomalies_handles_missing_cols():
    df = pd.DataFrame({"x": [1, 2, 3]})
    a_df, n_eff = lof_precip_anomalies(df, time_col="time", precip_col="precipitation (mm)")
    assert a_df.empty
    assert n_eff == 0
