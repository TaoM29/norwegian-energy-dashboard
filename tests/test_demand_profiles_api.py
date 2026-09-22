"""Bounded profile endpoint contract and data failure behavior."""
import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import demand_profiles as api


def test_endpoint_reads_household_only_and_exposes_provenance(monkeypatch):
    calls = []
    def load(area, start, end, *, kind, groups):
        calls.append((area, kind, groups))
        frame = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", "2025-01-03", freq="h",
                                        inclusive="left", tz="UTC"),
            "value": 4.0, "quality": "ok", "unit": "kWh",
        })
        frame.attrs["provenance"] = {"source": "Synthetic fixture", "version": "test"}
        return frame
    monkeypatch.setattr(api.data, "energy_frame", load)
    monkeypatch.setenv("ENERGY_DATA_MODE", "fixture")
    app = FastAPI()
    app.include_router(api.router)
    http = TestClient(app)
    result = http.get("/api/explore/demand-profiles?area=NO1&start=2025-01-01&end=2025-01-03")
    assert result.status_code == 200
    body = result.json()
    assert calls == [("NO1", "consumption", ["household"])]
    assert body["query"]["interval"] == "[start,end)"
    assert body["dataMode"] == "fixture"
    assert body["coverage"]["profileEligibleDays"] == 1
    assert body["groups"][0]["actual"][0]["medianKwh"] == 4
    assert body["metadata"]["provenance"]["version"] == "test"
    assert len(body["metadata"]["inputSha256"]) == 64


def test_invalid_range_is_422_before_read_and_bad_source_is_503(monkeypatch):
    calls = []
    def load(*args, **kwargs):
        calls.append(1)
        frame = pd.DataFrame({"timestamp": ["2025-01-01T00:00Z", "2025-01-01T00:00Z"],
                              "value": [1, 2], "quality": ["ok", "ok"], "unit": ["kWh", "kWh"]})
        return frame
    monkeypatch.setattr(api.data, "energy_frame", load)
    app = FastAPI()
    app.include_router(api.router)
    http = TestClient(app)
    route = "/api/explore/demand-profiles?area=NO1&"
    assert http.get(route + "start=2025-01-01&end=2025-01-01").status_code == 422
    assert http.get(route + "start=2025-01-01&end=2026-01-03").status_code == 422
    assert calls == []
    result = http.get(route + "start=2025-01-01&end=2025-01-02")
    assert result.status_code == 503
    assert "unique UTC hours" in result.json()["detail"]
