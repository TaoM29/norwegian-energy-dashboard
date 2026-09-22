"""Demand summaries read one bounded household snapshot and preserve coverage."""
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import demand_peaks as api


@pytest.fixture
def client(monkeypatch):
    calls = []
    def load(area, start, end, *, kind, groups):
        calls.append((area, start, end, kind, groups))
        offset = int(area[-1])
        frame = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC"),
            "value": [offset, 3 * offset, 2 * offset, 4 * offset],
            "quality": ["ok", "missing" if area == "NO5" else "ok", "ok", "ok"],
            "unit": "kWh",
        })
        frame.attrs["provenance"] = {"source": "Synthetic fixture", "version": "same-snapshot"}
        return frame
    monkeypatch.setattr(api.data, "energy_frame", load)
    monkeypatch.setenv("ENERGY_DATA_MODE", "fixture")
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app), calls


def test_area_hourly_detail_excludes_invalid_pairs_and_uses_household_only(client):
    http, calls = client
    response = http.get("/api/explore/demand-peaks?area=NO5&start=2025-01-01&end=2025-01-02")
    assert response.status_code == 200
    result = response.json()
    assert result["dataMode"] == "fixture"
    assert result["query"]["interval"] == "[start,end)"
    assert result["summary"]["peak"]["valueKwh"] == 20
    assert result["coverage"]["observedHours"] == 3
    assert result["coverage"]["validRampPairs"] == 1
    assert result["hourly"][1]["valueKwh"] is None
    assert result["hourly"][2]["changeKwh"] is None
    assert result["unit"] == "kWh"
    assert calls[0][3:] == ("consumption", ["household"])


def test_regions_share_one_cohort_and_snapshot_provenance(client):
    http, calls = client
    response = http.get("/api/regional/demand-peaks?start=2025-01-01&end=2025-01-02")
    assert response.status_code == 200
    result = response.json()
    assert result["coverage"]["matchedHours"] == 3
    assert result["coverage"]["expectedHours"] == 24
    assert all(result["hourly"][1][area] is None for area in ("NO1", "NO2", "NO3", "NO4", "NO5"))
    assert result["coincidentPeak"]["valueKwh"] == 60
    assert result["coincidenceFactor"] == 1
    assert len(result["metadata"]["provenance"]) == 5
    assert all(call[3:] == ("consumption", ["household"]) for call in calls)


@pytest.mark.parametrize("route", ["/api/explore/demand-peaks?area=NO1&", "/api/regional/demand-peaks?"])
def test_invalid_or_unbounded_ranges_do_not_read_data(client, route):
    http, calls = client
    for query in ("start=2025-01-01&end=2025-01-01", "start=2021-01-01&end=2026-01-01"):
        assert http.get(route + query).status_code == 422
    assert calls == []


def test_inconsistent_snapshot_is_reported_instead_of_combined(client, monkeypatch):
    http, _ = client
    load = api.data.energy_frame
    def changing(area, *args, **kwargs):
        frame = load(area, *args, **kwargs)
        frame.attrs["provenance"]["version"] = area
        return frame
    monkeypatch.setattr(api.data, "energy_frame", changing)
    response = http.get("/api/regional/demand-peaks?start=2025-01-01&end=2025-01-02")
    assert response.status_code == 503
    assert "snapshot changed" in response.json()["detail"]


def test_malformed_source_fails_clearly(client, monkeypatch):
    http, _ = client
    load = api.data.energy_frame
    def duplicated(*args, **kwargs):
        frame = load(*args, **kwargs)
        return pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    monkeypatch.setattr(api.data, "energy_frame", duplicated)
    response = http.get("/api/explore/demand-peaks?area=NO1&start=2025-01-01&end=2025-01-02")
    assert response.status_code == 503
