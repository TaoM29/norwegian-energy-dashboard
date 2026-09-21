from __future__ import annotations

import json

import pandas as pd

from app_core.ingestion.models import AREAS, BASE_GROUPS
from app_core.ingestion.store import EnergyStore
from app_core.loaders import weather
from backend.forecast_jobs import ForecastStore
from scripts.create_fixture import (
    POINT_COORDINATE,
    _energy_rows,
    _weather_frame,
    create_fixture,
)


def test_fixture_series_are_deterministic_and_cover_all_base_groups() -> None:
    index = pd.date_range("2025-01-01T00:00:00Z", periods=24, freq="h")
    first = list(_energy_rows(index))
    second = list(_energy_rows(index))
    assert first == second
    assert len(first) == 24 * len(AREAS) * sum(len(groups) for groups in BASE_GROUPS.values())
    assert {row["source"] for row in first} == {"Synthetic offline fixture — not observations"}
    assert {row["quality"] for row in first} == {"ok"}

    first_weather = _weather_frame(index, 2.5)
    second_weather = _weather_frame(index, 2.5)
    pd.testing.assert_frame_equal(first_weather, second_weather)
    weather._validate_frame(first_weather)


def test_create_fixture_writes_api_readable_snapshots_and_prepared_result(tmp_path, monkeypatch) -> None:
    output = tmp_path / "fixture"
    forecast_config = {
        "areas": list(AREAS),
        "models": ["seasonal_naive"],
        "horizon_hours": 24,
        "train_window_days": 30,
        "validation_origins": ["2025-03-01T00:00:00Z"],
        "calibration_origins": ["2025-03-08T00:00:00Z"],
        "holdout_origins": ["2025-03-15T00:00:00Z"],
        "weather_mode": "historical_only",
        "energy_publication_lag_hours": 48,
        "weather_publication_lag_hours": 120,
        "interval_coverage": 0.8,
        "random_seed": 320,
    }
    manifest = create_fixture(
        output,
        energy_start="2025-01-01T00:00:00Z",
        energy_end="2025-04-01T00:00:00Z",
        point_years=[2024, 2025],
        forecast_config=forecast_config,
    )

    assert manifest["synthetic"] is True
    assert manifest["energy"]["rows"] == 90 * 24 * 5 * 10
    store = EnergyStore(output / "energy.sqlite")
    assert len(store.coverage()) == 5 * 10
    assert store.common_complete_window()["series_count"] == 50

    monkeypatch.setenv("WEATHER_SNAPSHOT_DIR", str(output / "weather"))
    monkeypatch.setenv("ENERGY_DATA_MODE", "fixture")
    monkeypatch.setattr(weather.requests, "get", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("fixture contacted upstream")))
    area = weather.load_openmeteo_era5("NO1", 2025)
    assert len(area) == 365 * 24
    assert area.attrs["provenance"]["annual_provenance"][0]["source"] == "Synthetic offline fixture — not observations"
    latitude, longitude = POINT_COORDINATE
    point = weather.load_openmeteo_point(
        latitude,
        longitude,
        pd.Timestamp("2025-01-01T00:00:00Z"),
        pd.Timestamp("2025-02-01T00:00:00Z"),
        location_key=f"snow-drift:{latitude:.6f},{longitude:.6f}",
    )
    assert len(point) == 31 * 24
    assert point.attrs["coverage_complete"] is True
    assert point.attrs["provenance"]["annual_provenance"][0]["synthetic"] is True

    from fastapi.testclient import TestClient
    from backend.main import app
    response = TestClient(app).post("/api/regional/snow-drift", json={
        "latitude": latitude, "longitude": longitude, "seasonStart": 2024, "seasonEnd": 2024,
    })
    assert response.status_code == 200
    assert response.json()["seasonal"][0]["observedHours"] == 365 * 24
    assert (output / "file.geojson").is_file()

    forecasts = ForecastStore(output / "forecasts").list_results()
    assert len(forecasts) == 1
    assert forecasts[0]["metadata"]["synthetic"] is True
    assert forecasts[0]["coverage"]["matchedOrigins"] == 5
    assert len(forecasts[0]["predictions"]) == 5 * 24
    sensitivity = json.loads((output / "analyses/demand-sensitivity.json").read_text())
    assert sensitivity["dataMode"] == "fixture"
    assert len(sensitivity["areas"]) == 5
    assert all(area["status"] == "ok" for area in sensitivity["areas"])
    assert sensitivity["protocol"]["end"].startswith("2025-04-01")
    fixture_manifest = json.loads((output / "fixture-manifest.json").read_text())
    assert fixture_manifest == manifest


def test_fixture_mode_never_fetches_an_uncached_point(tmp_path, monkeypatch):
    from app_core.loaders import weather
    import pytest
    monkeypatch.setenv("ENERGY_DATA_MODE", "fixture")
    monkeypatch.setenv("WEATHER_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setattr(weather.requests, "get", lambda *a, **kw: pytest.fail("fixture contacted upstream"))
    with pytest.raises(ValueError, match="No synthetic weather fixture"):
        weather._load_location_year(latitude=1.0, longitude=1.0, location="point:1.000000,1.000000", year=2025, force_refresh=False)
