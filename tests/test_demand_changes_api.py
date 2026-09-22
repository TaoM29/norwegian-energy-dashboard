from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_core.analysis.demand_changes import scan, summarize_daily
from backend.demand_changes import artifact_path, router


@pytest.fixture
def study():
    periods, coverage = {}, {}
    for name, year in (("calibration", 2024), ("test", 2025)):
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        rows = []
        for i in range(60 * 24):
            residual = (i // 24 % 7 - 3) + (8 if year == 2025 and i >= 30 * 24 else 0)
            rows.append({"time": (start + timedelta(hours=i)).isoformat(), "status": "ok",
                         "actual": 100 + residual, "expected": 100, "residual": residual})
        periods[name], coverage[name] = summarize_daily(rows, start.date().isoformat(),
            (start + timedelta(days=60)).date().isoformat(), name)
    return {"schemaVersion": 1, "id": "api-test", "createdAt": "2026-09-22T00:00:00Z",
            "dataMode": "fixture", "area": "NO1", "status": "ok",
            "protocol": {"config": {"alpha": .05}}, "metadata": {}, "coverage": coverage,
            "dailyRows": periods["calibration"] + periods["test"],
            "primary": scan(periods["calibration"], periods["test"], bootstrap_draws=39),
            "sensitivities": [], "controlledValidation": {"summary": []}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMAND_CHANGES_ARTIFACT", str(tmp_path / "study.json"))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_saved_read_and_download_never_compute(client, study, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Page reads must not recompute the study")
    monkeypatch.setattr("app_core.analysis.demand_changes.scan", forbidden)
    artifact_path().write_text(json.dumps(study))
    assert client.get("/api/diagnostics/demand-changes").json() == study
    response = client.get("/api/diagnostics/demand-changes/artifact")
    assert response.content == artifact_path().read_bytes()
    assert "attachment" in response.headers["content-disposition"]


def test_missing_malformed_and_inconsistent_studies(client, study):
    endpoint = "/api/diagnostics/demand-changes"
    assert client.get(endpoint).status_code == 404
    for content in ("[]", "{", '{"number":NaN}', '{"number":1e999}'):
        artifact_path().write_text(content)
        assert client.get(endpoint).status_code == 503
    for mutate in (
        lambda item: item["dailyRows"][0].update(actual=42),
        lambda item: item["dailyRows"][1].update(date=item["dailyRows"][0]["date"]),
        lambda item: item["coverage"]["test"].update(completeDays=0),
        lambda item: item["primary"].update(detected=not item["primary"]["detected"]),
    ):
        bad = deepcopy(study)
        mutate(bad)
        artifact_path().write_text(json.dumps(bad))
        assert client.get(endpoint).status_code == 503
        assert client.get(endpoint + "/artifact").status_code == 503


def test_saved_unavailable_is_a_distinct_state(client, study):
    study.update(status="unavailable", reason="No complete calibration block")
    for key in ("primary", "dailyRows", "coverage"):
        del study[key]
    artifact_path().write_text(json.dumps(study))
    response = client.get("/api/diagnostics/demand-changes")
    assert response.status_code == 200
    assert response.json()["reason"] == "No complete calibration block"
