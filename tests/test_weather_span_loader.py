from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from app_core.loaders.weather_span import load_weather_span_df


def _frame(times) -> pd.DataFrame:
    frame = pd.DataFrame({"time": times, "temperature_2m (°C)": range(len(times))})
    frame.attrs["provenance"] = {
        "source": "Open-Meteo Historical Weather API",
        "model": "era5_seamless",
        "variables": ["temperature_2m"],
        "units": {"temperature_2m (°C)": "°C"},
        "cache_status": "snapshot",
    }
    return frame


def test_weather_span_is_half_open_and_utc_aware():
    def fake_loader(area: str, year: int) -> pd.DataFrame:
        return _frame(pd.date_range(f"{year}-01-01", periods=5, freq="h", tz="UTC"))

    result = load_weather_span_df(
        load_openmeteo_era5=fake_loader,
        area="NO1",
        start=datetime(2024, 1, 1, 1),
        end=datetime(2024, 1, 1, 3),
    )

    assert result["time"].tolist() == [
        pd.Timestamp("2024-01-01T01:00:00Z"),
        pd.Timestamp("2024-01-01T02:00:00Z"),
    ]
    assert result.attrs["requested_end"] == "2024-01-01T03:00:00+00:00"
    assert result.attrs["available_end"] == "2024-01-01T03:00:00+00:00"


def test_dst_offsets_convert_to_utc_without_duplicate_local_hour():
    times = pd.date_range("2024-10-26T22:00:00Z", periods=8, freq="h")

    def fake_loader(area: str, year: int) -> pd.DataFrame:
        return _frame(times)

    result = load_weather_span_df(
        fake_loader,
        "NO1",
        start=pd.Timestamp("2024-10-27 00:00", tz="Europe/Oslo"),
        end=pd.Timestamp("2024-10-27 05:00", tz="Europe/Oslo"),
    )

    assert len(result) == 6
    assert result["time"].is_unique
    assert result["time"].iloc[0] == pd.Timestamp("2024-10-26T22:00:00Z")
    assert result["time"].iloc[-1] == pd.Timestamp("2024-10-27T03:00:00Z")


@pytest.mark.parametrize(
    "times,error",
    [
        ([pd.Timestamp("2024-01-01T00:00:00Z"), pd.Timestamp("2024-01-01T00:00:00Z")], "duplicate"),
        ([pd.Timestamp("2024-01-01T00:00:00Z"), pd.Timestamp("2024-01-01T02:00:00Z")], "gap"),
    ],
)
def test_duplicate_or_gap_returns_unavailable(times, error):
    result = load_weather_span_df(
        lambda area, year: _frame(times),
        "NO1",
        datetime(2024, 1, 1),
        datetime(2024, 1, 1, 3),
    )
    assert result.empty
    assert result.attrs["provenance"]["cache_status"] == "unavailable"
    assert error in result.attrs["provenance"]["error"]


def test_force_refresh_is_forwarded_to_annual_loader():
    calls = []

    def fake_loader(area: str, year: int, *, force_refresh: bool = False) -> pd.DataFrame:
        calls.append((year, force_refresh))
        return _frame(pd.date_range(f"{year}-01-01", periods=2, freq="h", tz="UTC"))

    load_weather_span_df(
        fake_loader,
        "NO1",
        datetime(2024, 1, 1),
        datetime(2024, 1, 1, 2),
        force_refresh=True,
    )
    assert calls == [(2024, True)]


def test_missing_year_cannot_look_like_complete_multiyear_coverage():
    def fake_loader(area: str, year: int) -> pd.DataFrame:
        if year == 2023:
            return _frame(pd.date_range("2023-12-31", periods=24, freq="h", tz="UTC"))
        frame = _frame(pd.date_range("2024-01-01", periods=1, freq="h", tz="UTC"))
        frame = frame.iloc[0:0]
        frame.attrs["provenance"] = {"cache_status": "unavailable"}
        return frame

    result = load_weather_span_df(
        fake_loader,
        "NO1",
        datetime(2023, 12, 31),
        datetime(2024, 1, 2),
    )
    assert result.empty
    assert result.attrs["provenance"]["cache_status"] == "unavailable"


def test_invalid_interval_is_rejected():
    with pytest.raises(ValueError, match="start must be before end"):
        load_weather_span_df(lambda area, year: pd.DataFrame(), "NO1", datetime(2024, 1, 2), datetime(2024, 1, 1))
