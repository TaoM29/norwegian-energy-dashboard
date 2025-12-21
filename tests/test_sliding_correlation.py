import pandas as pd
import numpy as np

from app_core.analysis.sliding_correlation import apply_lag_hours, align_two_series, rolling_pearson_corr


def test_apply_lag_hours_shifts_index_forward():
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    s = pd.Series([1, 2, 3], index=idx, dtype=float)

    out = apply_lag_hours(s, 2)
    assert (out.index == (idx + pd.Timedelta(hours=2))).all()
    assert np.allclose(out.to_numpy(), s.to_numpy())


def test_align_two_series_intersection_and_dropna():
    idx_a = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    idx_b = pd.date_range("2024-01-01 01:00:00", periods=4, freq="h", tz="UTC")

    a = pd.Series([1.0, np.nan, 3.0, 4.0], index=idx_a)
    b = pd.Series([10.0, 11.0, np.nan, 13.0], index=idx_b)

    a2, b2 = align_two_series(a, b)
    # overlapping indices: 01:00,02:00,03:00
    # 01:00 -> a is nan (drop)
    # 02:00 -> b is nan (drop)
    # 03:00 -> both ok
    assert len(a2) == 1
    assert len(b2) == 1
    assert a2.index[0] == pd.Timestamp("2024-01-01 02:00:00", tz="UTC")
    assert float(a2.iloc[0]) == 3.0
    assert float(b2.iloc[0]) == 11.0


def test_rolling_corr_perfect_positive():
    idx = pd.date_range("2024-01-01", periods=50, freq="h", tz="UTC")
    a = pd.Series(np.arange(50, dtype=float), index=idx)
    b = 2.0 * a

    rho = rolling_pearson_corr(a, b, window=10, center=False, min_periods=10)
    # after min_periods, corr should be ~1
    valid = rho.dropna()
    assert len(valid) > 0
    assert np.allclose(valid.to_numpy(), 1.0, atol=1e-12)


def test_rolling_corr_perfect_negative():
    idx = pd.date_range("2024-01-01", periods=50, freq="h", tz="UTC")
    a = pd.Series(np.arange(50, dtype=float), index=idx)
    b = -1.0 * a

    rho = rolling_pearson_corr(a, b, window=10, center=False, min_periods=10)
    valid = rho.dropna()
    assert len(valid) > 0
    assert np.allclose(valid.to_numpy(), -1.0, atol=1e-12)
