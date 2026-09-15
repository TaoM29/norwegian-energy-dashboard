from __future__ import annotations

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_core.analysis.exploration import (
    circular_mean,
    energy_exploration,
    weather_exploration,
)
from backend import explore


@pytest.fixture
def client(monkeypatch) -> TestClient:
    timestamps = pd.date_range("2025-01-01", periods=3, freq="h", tz="UTC")
    energy = pd.DataFrame(
        [
            {"timestamp": timestamps[0], "group": "hydro", "value": 0.1},
            {"timestamp": timestamps[0], "group": "hydro", "value": 0.2},
            {"timestamp": timestamps[1], "group": "hydro", "value": 0.3},
            {"timestamp": timestamps[0], "group": "wind", "value": 1.0},
            {"timestamp": timestamps[1], "group": "wind", "value": 2.0},
            {"timestamp": timestamps[2], "group": "wind", "value": None},
        ]
    )
    energy.attrs["provenance"] = {"source": "fixture", "version": "energy-v1"}

    weather = pd.DataFrame(
        {
            "time": timestamps[:2],
            "temperature_2m (°C)": [1.0, 3.0],
            "precipitation (mm)": [0.5, 1.5],
            "wind_speed_10m (m/s)": [4.0, 6.0],
            "wind_gusts_10m (m/s)": [8.0, 10.0],
            "wind_direction_10m (°)": [359.0, 1.0],
        }
    )
    weather.attrs["provenance"] = {
        "source": "fixture",
        "model": "era5_seamless",
        "version": "weather-v1",
        "observedHours": 2,
        "coverage_complete": False,
    }

    def energy_frame(*args, **kwargs):
        result = energy.copy()
        result.attrs = energy.attrs.copy()
        groups = kwargs.get("groups")
        return result[result["group"].isin(groups)].copy() if groups else result

    def weather_frame(*args, **kwargs):
        result = weather.copy()
        result.attrs = weather.attrs.copy()
        return result

    def energy_daily_frame(*args, **kwargs):
        selected = kwargs.get("groups")
        values = energy[energy["group"].isin(selected)].copy() if selected else energy.copy()
        values["timestamp"] = values["timestamp"].dt.floor("D")
        result = values.groupby(["timestamp", "group"], as_index=False).agg(
            value=("value", lambda column: column.sum(min_count=1)),
            observed_hours=("value", "count"),
        )
        result.attrs["precomputed"] = True
        return result

    monkeypatch.setattr(explore.data, "energy_frame", energy_frame)
    monkeypatch.setattr(explore.data, "energy_daily_frame", energy_daily_frame)
    monkeypatch.setattr(explore.data, "weather_frame", weather_frame)
    monkeypatch.setattr(
        explore.data,
        "provenance",
        lambda area, start, end: {
            "area": area,
            "start": str(start),
            "end": str(end),
            "interval": "[start, end)",
            "timezone": "UTC",
        },
    )
    app = FastAPI()
    app.include_router(explore.router)
    return TestClient(app)


def test_energy_endpoint_preserves_exact_totals_before_daily_aggregation(client):
    response = client.get(
        "/api/explore/energy",
        params={
            "area": "NO1",
            "start": "2025-01-01",
            "end": "2025-01-02",
            "kind": "production",
            "groups": "hydro,wind",
            "aggregation": "daily",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"]["groups"] == ["hydro", "wind"]
    assert body["grandTotalKwh"] == pytest.approx(3.6)
    assert body["totals"] == [
        {
            "group": "hydro",
            "totalKwh": pytest.approx(0.6),
            "observations": 3,
            "observedHours": 2,
            "expectedHours": 24,
            "partial": True,
        },
        {
            "group": "wind",
            "totalKwh": 3.0,
            "observations": 2,
            "observedHours": 2,
            "expectedHours": 24,
            "partial": True,
        },
    ]
    assert body["series"] == [
        {"time": "2025-01-01T00:00:00.000Z", "group": "hydro", "valueKwh": pytest.approx(0.6)},
        {"time": "2025-01-01T00:00:00.000Z", "group": "wind", "valueKwh": 3.0},
    ]
    assert body["metadata"]["calculation"]["totals"].startswith("Exact sum")


@pytest.mark.parametrize("aggregation", ["daily", "weekly"])
def test_precomputed_daily_energy_is_identical_to_raw_hourly_analysis(aggregation):
    timestamps = pd.date_range("2025-01-01", periods=48, freq="h", tz="UTC")
    raw = pd.DataFrame(
        [
            {"timestamp": timestamp, "group": group, "value": float(hour + offset)}
            for hour, timestamp in enumerate(timestamps)
            for group, offset in (("hydro", 0), ("wind", 100))
        ]
    )
    daily = raw.assign(timestamp=raw["timestamp"].dt.floor("D")).groupby(
        ["timestamp", "group"], as_index=False
    ).agg(
        value=("value", lambda column: column.sum(min_count=1)),
        observed_hours=("value", "count"),
    )

    expected = energy_exploration(
        raw, aggregation=aggregation, groups=["hydro", "wind"]
    )
    actual = energy_exploration(
        daily, aggregation=aggregation, groups=["hydro", "wind"]
    )

    assert actual == expected


def test_weather_endpoint_matches_legacy_scalar_rules_and_uses_circular_direction(client):
    response = client.get(
        "/api/explore/weather",
        params={
            "area": "NO1",
            "start": "2025-01-01",
            "end": "2025-01-02",
            "variables": "temperature,precipitation,wind_direction",
            "aggregation": "daily",
            "rolling_hours": 0,
            "normalize": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    summary = {row["variable"]: row for row in body["summary"]}
    assert summary["temperature"]["min"] == 1.0
    assert summary["temperature"]["mean"] == 2.0
    assert summary["temperature"]["max"] == 3.0
    assert body["monthly"][0]["precipitation"] == 2.0
    assert body["monthly"][0]["temperature"] == 2.0
    assert len(body["monthly"]) == 12
    assert body["monthly"][1]["temperature"] is None
    rose = {row["sector"]: row for row in body["windRose"]}
    assert len(rose) == 16
    assert rose["N"]["count"] == 1
    assert rose["NNW"]["count"] == 1
    direction = next(row for row in body["series"] if row["variable"] == "wind_direction")
    assert min(abs(direction["value"]), abs(direction["value"] - 360.0)) < 1e-9
    assert body["metadata"]["calculation"]["windDirection"].startswith("circular")
    assert body["coverage"]["complete"] is False


def test_normalization_follows_aggregation_and_turns_constant_series_to_zero():
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2025-01-01", periods=48, freq="h", tz="UTC"),
            "temperature_2m (°C)": [5.0] * 48,
            "precipitation (mm)": [1.0] * 48,
            "wind_speed_10m (m/s)": [3.0] * 48,
            "wind_gusts_10m (m/s)": [6.0] * 48,
            "wind_direction_10m (°)": [0.0] * 48,
        }
    )
    result = weather_exploration(
        frame,
        variables=["temperature", "precipitation"],
        aggregation="daily",
        rolling_hours=0,
        normalize=True,
    )

    assert {row["value"] for row in result["series"]} == {0.0}
    # Summary/monthly values stay in physical units and are not changed by chart normalization.
    assert result["monthly"][0]["precipitation"] == 48.0


def test_circular_mean_fixes_the_north_boundary_case():
    assert circular_mean([359.0, 1.0]) == pytest.approx(0.0, abs=1e-9)
    assert sum([359.0, 1.0]) / 2 == 180.0  # retained page's linear behavior


def test_rolling_wind_direction_uses_the_same_circular_rule():
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2025-01-01", periods=2, freq="h", tz="UTC"),
            "temperature_2m (°C)": [0.0, 0.0],
            "precipitation (mm)": [0.0, 0.0],
            "wind_speed_10m (m/s)": [1.0, 1.0],
            "wind_gusts_10m (m/s)": [2.0, 2.0],
            "wind_direction_10m (°)": [359.0, 1.0],
        }
    )
    result = weather_exploration(
        frame,
        variables=["wind_direction"],
        aggregation="hourly",
        rolling_hours=2,
        normalize=False,
    )

    rolled = result["series"][-1]["value"]
    assert min(abs(rolled), abs(rolled - 360.0)) < 1e-9


@pytest.mark.parametrize(
    ("path", "params"),
    [
        (
            "/api/explore/energy",
            {"area": "NO1", "start": "2025-01-01", "end": "2025-01-02", "groups": ""},
        ),
        (
            "/api/explore/energy",
            {"area": "NO1", "start": "2025-01-01", "end": "2025-01-02", "groups": "nuclear"},
        ),
        (
            "/api/explore/weather",
            {"area": "NO1", "start": "2025-01-01", "end": "2025-01-02", "variables": "humidity"},
        ),
        (
            "/api/explore/weather",
            {"area": "NO1", "start": "2025-01-01", "end": "2026-01-03"},
        ),
    ],
)
def test_endpoints_reject_empty_unknown_or_unbounded_selections(client, path, params):
    assert client.get(path, params=params).status_code == 422
