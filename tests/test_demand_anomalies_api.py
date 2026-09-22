from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.demand_anomalies import artifact_path, router
from scripts.run_demand_sensitivity import publish_new


@pytest.fixture
def study():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = [{"time": (start + timedelta(hours=i)).isoformat(), "actual": i} for i in range(300)]
    return {"schemaVersion": 1, "id": "test", "createdAt": start.isoformat(),
            "dataMode": "fixture", "protocol": {}, "metadata": {},
            "areas": [{"area": "NO1", "status": "ok", "summary": {}, "calibration": {},
                       "coverage": {}, "splits": {}, "metadata": {}, "rows": rows,
                       "calibrationRows": rows,
                       "candidates": [{"id": str(i), "peakTime": rows[100 + i]["time"],
                                       "peers": {"days": []}} for i in range(25)]},
                      {"area": "NO2", "status": "unavailable", "reason": "Insufficient support"}]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMAND_ANOMALIES_ARTIFACT", str(tmp_path / "study.json"))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_saved_only_compact_selection_and_exact_download(client, study, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Page requests must not fit models or load upstream data")
    monkeypatch.setattr("app_core.analysis.demand_anomalies.analyze_area", forbidden)
    monkeypatch.setattr("backend.data.energy_frame", forbidden)
    publish_new(artifact_path(), study)
    response = client.get("/api/diagnostics/demand-anomalies?candidate=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["selectedArea"]["candidates"]) == 20
    assert data["selectedArea"]["totalCandidates"] == 25
    assert "rows" not in data["selectedArea"]
    assert "calibrationRows" not in data["selectedArea"]
    assert data["selection"]["candidate"]["id"] == "2"
    assert len(data["selection"]["rows"]) == 97
    assert "peers" not in data["selectedArea"]["candidates"][0]
    download = client.get("/api/diagnostics/demand-anomalies/artifact")
    assert download.content == artifact_path().read_bytes()
    assert "attachment" in download.headers["content-disposition"]
    assert client.get("/api/diagnostics/demand-anomalies?candidate=24").status_code == 404
    assert client.get("/api/diagnostics/demand-anomalies?area=invalid").status_code == 422
    unavailable = client.get("/api/diagnostics/demand-anomalies?area=NO2").json()
    assert unavailable["selectedArea"]["status"] == "unavailable"
    assert unavailable["selection"]["rows"] == []


def test_missing_and_malformed_artifacts_fail_clearly(client, study):
    assert client.get("/api/diagnostics/demand-anomalies").status_code == 404
    for contents in ("[]", "not json", '{"schemaVersion":NaN}'):
        artifact_path().write_text(contents)
        assert client.get("/api/diagnostics/demand-anomalies").status_code == 503
    bad = deepcopy(study)
    bad["areas"][0]["candidates"][0]["peakTime"] = "2025-01-01"
    artifact_path().unlink()
    publish_new(artifact_path(), bad)
    assert client.get("/api/diagnostics/demand-anomalies").status_code == 503


def test_no_candidates_returns_bounded_first_week(client, study):
    study["areas"][0]["candidates"] = []
    publish_new(artifact_path(), study)
    data = client.get("/api/diagnostics/demand-anomalies").json()
    assert data["selection"]["candidate"] is None
    assert len(data["selection"]["rows"]) == 168
