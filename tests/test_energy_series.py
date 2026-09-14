import pandas as pd
import pytest

import app_core.loaders.energy_series as es


def patch_span(monkeypatch, rows):
    frame = pd.DataFrame(rows, columns=["time", "quantity_kwh"])
    monkeypatch.setattr(es, "load_energy_span_df", lambda **kwargs: frame.copy())


def test_load_energy_series_invalid_kind_raises():
    start = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    end = pd.Timestamp("2024-01-01 03:00:00", tz="UTC")
    with pytest.raises(ValueError):
        es.load_energy_series_hourly("NO1", "BadKind", "solar", 2024, start, end)


def test_load_energy_series_localizes_naive_start_end(monkeypatch):
    # production path with one row
    rows = [{"time": pd.Timestamp("2024-01-01 00:00:00"), "quantity_kwh": 1.0}]
    patch_span(monkeypatch, rows)

    start = pd.Timestamp("2024-01-01 00:00:00")  # naive
    end = pd.Timestamp("2024-01-01 01:00:00")    # naive

    s = es.load_energy_series_hourly("NO1", "Production", "solar", 2024, start, end)
    assert isinstance(s.index, pd.DatetimeIndex)
    assert s.index.tz is not None  # localized / converted to UTC


def test_load_energy_series_production_resample_sum(monkeypatch):
    rows = [
        {"time": pd.Timestamp("2024-01-01 00:00:00", tz="UTC"), "quantity_kwh": 1.0},
        {"time": pd.Timestamp("2024-01-01 00:30:00", tz="UTC"), "quantity_kwh": 2.0},
        {"time": pd.Timestamp("2024-01-01 01:10:00", tz="UTC"), "quantity_kwh": 3.0},
    ]
    patch_span(monkeypatch, rows)

    start = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    end = pd.Timestamp("2024-01-01 02:00:00", tz="UTC")

    s = es.load_energy_series_hourly("NO1", "Production", "solar", 2024, start, end)

    # resample("H").sum(): 00:00 hour has 1+2, 01:00 hour has 3
    assert float(s.loc[pd.Timestamp("2024-01-01 00:00:00", tz="UTC")]) == 3.0
    assert float(s.loc[pd.Timestamp("2024-01-01 01:00:00", tz="UTC")]) == 3.0


def test_load_energy_series_consumption_resample_sum(monkeypatch):
    rows = [
        {"time": pd.Timestamp("2024-01-01 00:05:00", tz="UTC"), "quantity_kwh": 1.5},
        {"time": pd.Timestamp("2024-01-01 00:50:00", tz="UTC"), "quantity_kwh": 2.5},
        {"time": pd.Timestamp("2024-01-01 01:00:00", tz="UTC"), "quantity_kwh": 10.0},
    ]
    patch_span(monkeypatch, rows)

    start = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    end = pd.Timestamp("2024-01-01 02:00:00", tz="UTC")

    s = es.load_energy_series_hourly("NO1", "Consumption", "household", 2024, start, end)
    assert float(s.loc[pd.Timestamp("2024-01-01 00:00:00", tz="UTC")]) == 4.0
    assert float(s.loc[pd.Timestamp("2024-01-01 01:00:00", tz="UTC")]) == 10.0


def test_load_energy_series_empty_rows_returns_empty(monkeypatch):
    patch_span(monkeypatch, [])

    start = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    end = pd.Timestamp("2024-01-01 01:00:00", tz="UTC")

    s = es.load_energy_series_hourly("NO1", "Production", "solar", 2024, start, end)
    assert isinstance(s, pd.Series)
    assert s.empty


def test_load_energy_series_keeps_empty_hour_missing(monkeypatch):
    patch_span(monkeypatch, [
        {"time": pd.Timestamp("2024-01-01 00:00:00", tz="UTC"), "quantity_kwh": 2.0},
        {"time": pd.Timestamp("2024-01-01 02:00:00", tz="UTC"), "quantity_kwh": 4.0},
    ])

    series = es.load_energy_series_hourly(
        "NO1", "Production", "solar", 2024,
        pd.Timestamp("2024-01-01", tz="UTC"),
        pd.Timestamp("2024-01-01 03:00:00", tz="UTC"),
    )

    assert pd.isna(series.loc[pd.Timestamp("2024-01-01 01:00:00", tz="UTC")])


def test_matched_ytd_windows_preserve_partial_utc_hour():
    windows = es.matched_ytd_windows(2026, pd.Timestamp("2026-09-14 13:00:00", tz="UTC"))

    assert windows["current_end"] == pd.Timestamp("2026-09-14 13:00:00", tz="UTC")
    assert windows["prior_end"] == pd.Timestamp("2025-09-14 13:00:00", tz="UTC")
    assert es.matched_ytd_expected_hours(windows["current_start"], windows["current_end"]) == \
        es.matched_ytd_expected_hours(windows["prior_start"], windows["prior_end"])


def test_matched_ytd_summary_excludes_leap_day_and_requires_complete_hours():
    windows = es.matched_ytd_windows(2024, pd.Timestamp("2024-03-02 12:00:00", tz="UTC"))
    current_times = pd.date_range(windows["current_start"], windows["current_end"], freq="h", inclusive="left")
    prior_times = pd.date_range(windows["prior_start"], windows["prior_end"], freq="h", inclusive="left")
    current = pd.DataFrame({"timestamp": current_times, "group": "hydro", "value": 2.0})
    prior = pd.DataFrame({"timestamp": prior_times, "group": "hydro", "value": 1.0})

    summary = es.matched_ytd_summary(current, prior, windows=windows, groups=["hydro"])

    assert summary.loc[0, "current_hours"] == summary.loc[0, "prior_hours"]
    assert bool(summary.loc[0, "is_comparable"])
    assert summary.loc[0, "change_pct"] == 100.0

    incomplete = es.matched_ytd_summary(current.iloc[:-1], prior, windows=windows, groups=["hydro"])
    assert not bool(incomplete.loc[0, "is_comparable"])


def test_matched_ytd_full_year_boundary_maps_to_next_prior_january():
    from app_core.loaders.energy_series import matched_ytd_windows
    windows = matched_ytd_windows(2026, pd.Timestamp("2027-01-01", tz="UTC"))
    assert windows["prior_end"] == pd.Timestamp("2026-01-01", tz="UTC")
