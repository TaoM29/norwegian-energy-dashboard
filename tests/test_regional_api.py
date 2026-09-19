from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pandas as pd
import pytest

import backend.regional as regional


@pytest.fixture
def client(monkeypatch):
    def fake_energy_frame(area, start, end, kind="production", groups=None):
        area_number = int(area[-1])
        frame = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"]
                ),
                "value": [float(area_number), float(area_number * 3)],
                "quality": ["ok", "ok"],
            }
        )
        frame.attrs["provenance"] = {
            "source": "Elhub Energy Data API",
            "version": "fixture-v1",
            "unit": "kWh",
        }
        return frame

    monkeypatch.setattr(regional, "energy_frame", fake_energy_frame)
    app = FastAPI()
    app.include_router(regional.router)
    return TestClient(app)


def test_summary_returns_record_weighted_means_for_all_areas(client):
    response = client.get(
        "/api/regional/summary",
        params={
            "start": "2026-01-01",
            "end": "2026-01-02",
            "kind": "production",
            "groups": "solar,wind",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"]["groups"] == ["solar", "wind"]
    assert [row["area"] for row in body["areas"]] == ["NO1", "NO2", "NO3", "NO4", "NO5"]
    assert [row["meanKwh"] for row in body["areas"]] == [2, 4, 6, 8, 10]
    assert all(row["partial"] for row in body["areas"])
    assert body["aggregation"].startswith("Arithmetic mean weighted")
    assert body["provenance"]["version"] == "fixture-v1"


def test_summary_preserves_the_original_nuclear_production_choice(client):
    response = client.get(
        "/api/regional/summary",
        params={"start": "2026-01-01", "end": "2026-01-02", "groups": "nuclear"},
    )
    assert response.status_code == 200
    assert response.json()["query"]["groups"] == ["nuclear"]


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-01-02", "end": "2026-01-01"},
        {"start": "2025-01-01", "end": "2026-01-03"},
        {"start": "2026-01-01", "end": "2026-01-02", "kind": "production", "groups": "coal"},
        {"start": "2026-01-01", "end": "2026-01-02", "kind": "production", "groups": ","},
    ],
)
def test_summary_rejects_invalid_ranges_and_groups(client, params):
    assert client.get("/api/regional/summary", params=params).status_code == 422


def test_geography_serves_five_real_price_area_polygons(client):
    body = client.get("/api/regional/geography").json()
    assert body["type"] == "FeatureCollection"
    assert {feature["properties"]["ElSpotOmr"].replace(" ", "") for feature in body["features"]} == {
        "NO1", "NO2", "NO3", "NO4", "NO5"
    }
    assert all(feature["geometry"]["type"] in {"Polygon", "MultiPolygon"} for feature in body["features"])


def test_snow_drift_uses_exact_request_coordinate_and_reports_method(client, monkeypatch):
    calls = []

    def fake_point(latitude, longitude, start, end, *, location_key=None):
        calls.append((latitude, longitude, start, end, location_key))
        frame = pd.DataFrame(
            {
                "time": pd.date_range("2023-07-01", periods=24, freq="h", tz="UTC"),
                "temperature_2m (°C)": [-2.0] * 24,
                "precipitation (mm)": [0.5] * 24,
                "wind_speed_10m (m/s)": [5.0] * 24,
                "wind_direction_10m (°)": [90.0] * 24,
                "wind_gusts_10m (m/s)": [7.0] * 24,
            }
        )
        frame.attrs["provenance"] = {
            "source": "Open-Meteo Historical Weather API",
            "model": "era5_seamless",
            "units": {"wind_speed_10m (m/s)": "m/s"},
            "coverage_complete": False,
        }
        return frame

    monkeypatch.setattr(regional, "load_openmeteo_point", fake_point)
    payload = {
        "latitude": 61.234567,
        "longitude": 8.765432,
        "seasonStart": 2023,
        "seasonEnd": 2023,
        "transportDistanceM": 3000,
        "fetchDistanceM": 30000,
        "relocationCoefficient": 0.5,
        "fenceType": "Wyoming",
    }
    response = client.post("/api/regional/snow-drift", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert calls[0][:2] == (61.234567, 8.765432)
    assert calls[0][4] == "snow-drift:61.234567,8.765432"
    assert body["seasonal"][0]["partial"] is True
    assert body["units"]["windSpeed"] == "m/s"
    assert len(body["directional"]) == 16
    assert len(body["sourcePreview"]) == 24
    assert "not a site-specific engineering design" in body["method"]["fenceMeaning"]


def test_snow_drift_rejects_unbounded_or_reversed_seasons(client):
    base = {
        "latitude": 60,
        "longitude": 10,
        "transportDistanceM": 3000,
        "fetchDistanceM": 30000,
        "relocationCoefficient": 0.5,
        "fenceType": "Wyoming",
    }
    assert client.post(
        "/api/regional/snow-drift", json={**base, "seasonStart": 2024, "seasonEnd": 2023}
    ).status_code == 422
    assert client.post(
        "/api/regional/snow-drift", json={**base, "seasonStart": 1980, "seasonEnd": 2020}
    ).status_code == 422
