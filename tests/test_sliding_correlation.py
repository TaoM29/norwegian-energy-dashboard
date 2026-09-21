import pandas as pd
import numpy as np
import pytest

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
    # 02:00 -> both ok
    # 03:00 -> b is nan (drop)
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


@pytest.mark.parametrize("center", [False, True])
@pytest.mark.parametrize("missing", ["a_absent", "b_absent", "both_absent", "a_nan", "b_nan"])
def test_rolling_corr_requires_consecutive_hours(center, missing):
    idx = pd.date_range("2024-01-01", periods=12, freq="h", tz="UTC")
    a = pd.Series(np.arange(12, dtype=float), index=idx)
    b = a ** 2
    if missing in ("a_absent", "both_absent"):
        a = a.drop(idx[5])
    elif missing == "a_nan":
        a.loc[idx[5]] = np.nan
    if missing in ("b_absent", "both_absent"):
        b = b.drop(idx[5])
    elif missing == "b_nan":
        b.loc[idx[5]] = np.nan

    rho = rolling_pearson_corr(a, b, window=4, center=center)

    pd.testing.assert_index_equal(rho.index, idx)
    # The missing hour invalidates every four-hour window containing it.
    valid_positions = [2, 3, 8, 9, 10] if center else [3, 4, 9, 10, 11]
    assert list(rho.dropna().index) == list(idx[valid_positions])
    label = idx[8] if center else idx[9]
    assert rho.loc[label] == pytest.approx(np.corrcoef([6, 7, 8, 9], [36, 49, 64, 81])[0, 1])


@pytest.mark.parametrize("window", [5, 24, 168])
@pytest.mark.parametrize("center", [False, True])
def test_complete_hourly_windows_match_independent_pearson_values(window, center):
    idx = pd.date_range("2024-01-01", periods=400, freq="h", tz="UTC")
    x = np.arange(len(idx), dtype=float)
    a = pd.Series(np.sin(x / 7) + x / 100, index=idx)
    b = pd.Series(np.cos(x / 9), index=idx)
    rho = rolling_pearson_corr(a, b, window=window, center=center)
    label = 200
    start = label - window // 2 if center else label - window + 1
    expected = np.corrcoef(a.iloc[start:start + window], b.iloc[start:start + window])[0, 1]
    assert rho.iloc[label] == pytest.approx(expected)
    assert rho.notna().sum() == len(idx) - window + 1


def test_min_periods_does_not_expand_elapsed_window():
    idx = pd.date_range("2024-01-01", periods=10, freq="h", tz="UTC")
    a = pd.Series(np.arange(10, dtype=float), index=idx).drop(idx[5])
    b = a ** 2
    rho = rolling_pearson_corr(a, b, window=4, center=False, min_periods=3)
    assert rho.loc[idx[8]] == pytest.approx(np.corrcoef([6, 7, 8], [36, 49, 64])[0, 1])


@pytest.mark.parametrize("date", ["2025-03-29 22:00", "2025-10-25 22:00"])
def test_windows_count_elapsed_hours_across_oslo_dst(date):
    idx = pd.date_range(date, periods=12, freq="h", tz="UTC").tz_convert("Europe/Oslo")
    a = pd.Series(np.arange(12, dtype=float), index=idx)
    rho = rolling_pearson_corr(a.drop(idx[5]), -a, window=4, center=False)
    pd.testing.assert_index_equal(rho.index, idx)
    assert list(rho.dropna().index) == list(idx[[3, 4, 9, 10, 11]])
    assert np.allclose(rho.dropna(), -1)


def test_rolling_corr_retains_missing_edges_and_handles_no_overlap():
    idx = pd.date_range("2024-01-01", periods=8, freq="h", tz="UTC")
    a = pd.Series(np.arange(8, dtype=float), index=idx)
    a.iloc[[0, -1]] = np.nan
    b = pd.Series(np.arange(8, dtype=float), index=idx)
    rho = rolling_pearson_corr(a, b, window=4, center=False)
    pd.testing.assert_index_equal(rho.index, idx)
    assert list(rho.dropna().index) == list(idx[[4, 5, 6]])
    assert rolling_pearson_corr(a, apply_lag_hours(b, 24), window=4).empty
    assert rolling_pearson_corr(a * np.nan, b, window=4).isna().all()


@pytest.mark.parametrize("lag", [-2, 2])
def test_lag_aligns_weather_at_t_with_energy_at_t_plus_lag(lag):
    idx = pd.date_range("2024-01-01", periods=10, freq="h", tz="UTC")
    weather = pd.Series([1, 3, -1, 2, 9, 0, 4, 1, 8, 3], index=idx, dtype=float)
    energy = pd.Series(weather.to_numpy(), index=idx + pd.Timedelta(hours=lag))
    shifted = apply_lag_hours(weather.drop(idx[5]), lag)
    rho = rolling_pearson_corr(shifted, energy, window=4, center=False)
    assert list(rho.dropna().index) == list(energy.index[[3, 4, 9]])
    assert np.allclose(rho.dropna(), 1)
