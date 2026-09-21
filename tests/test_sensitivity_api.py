from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.sensitivity import artifact_path, router
from scripts.run_demand_sensitivity import publish_new


@pytest.fixture
def study():
    return {
        "schemaVersion": 1, "id": "test-study", "createdAt": "2026-09-21T00:00:00Z",
        "dataMode": "fixture", "protocol": {"end": "2026-01-01"}, "metadata": {},
        "areas": [{
            "area": "NO1", "status": "ok", "selectedModel": "linear", "referenceTemperature": 5,
            "curve": [{"temperature": 5, "effect": 0, "lower": 0, "upper": 0}],
            "models": [{"model": "linear", "test": {"mae": 2}}],
            "support": {}, "splits": {}, "residuals": {}, "sensitivity": {}, "metadata": {},
            "predictions": [{"time": "2025-01-01T00:00:00Z", "actual": 10, "linear": 12}],
        }, {"area": "NO2", "status": "unavailable", "reason": "Insufficient observed pairs"}],
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMAND_SENSITIVITY_ARTIFACT", str(tmp_path / "study.json"))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_reads_compact_study_and_downloads_full_evidence(client, study, monkeypatch):
    # Page requests must never invoke fitting or read upstream observations.
    def forbidden(*args, **kwargs):
        raise AssertionError("Request-time fitting/data loading is forbidden")
    monkeypatch.setattr("app_core.analysis.demand_sensitivity.analyze_area", forbidden)
    monkeypatch.setattr("backend.data.energy_frame", forbidden)
    publish_new(artifact_path(), study)
    response = client.get("/api/diagnostics/sensitivity")
    assert response.status_code == 200
    result = response.json()
    assert result["dataMode"] == "fixture"
    assert "predictions" not in result["areas"][0]
    assert result["areas"][1]["reason"] == "Insufficient observed pairs"
    download = client.get("/api/diagnostics/sensitivity/artifact")
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    assert download.json() == study


def test_no_saved_study_has_clear_unavailability(client):
    for route in ("", "/artifact"):
        result = client.get(f"/api/diagnostics/sensitivity{route}")
        assert result.status_code == 404
        assert "No saved demand sensitivity study" in result.json()["detail"]


@pytest.mark.parametrize("contents", ["not json", "[]", '{"schemaVersion":99}', '{"schemaVersion":NaN}'])
def test_corrupt_or_unknown_artifact_is_not_a_server_crash(client, contents):
    artifact_path().write_text(contents)
    assert client.get("/api/diagnostics/sensitivity").status_code == 503


def test_immutable_publication_preserves_previous_file(tmp_path, study):
    path = tmp_path / "study.json"
    publish_new(path, study)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        publish_new(path, {**study, "id": "replacement"})
    assert path.read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_default_artifact_follows_selected_database(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMAND_SENSITIVITY_ARTIFACT", raising=False)
    monkeypatch.setenv("ENERGY_DATABASE", str(tmp_path / "fixture" / "energy.sqlite"))
    assert artifact_path() == tmp_path / "fixture" / "analyses" / "demand-sensitivity.json"


def test_nonfinite_publication_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    with pytest.raises(ValueError):
        publish_new(path, {"value": float("nan")})
    assert not path.exists()
