from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend import forecast
from backend.forecast_jobs import ForecastJobManager


def _client(tmp_path, *, runner=None, validator=None, max_queued=4):
    runner = runner or (lambda config, progress, cancelled: {"config": config, "metadata": {}})
    validator = validator or (lambda config: {"area": "NO1", "horizon": 24, **config})
    manager = ForecastJobManager(
        tmp_path,
        max_queued=max_queued,
        use_process=False,
        runners={"sarimax": runner, "evaluation": runner},
        validators={"sarimax": validator, "evaluation": validator},
    )
    app = FastAPI()
    app.include_router(forecast.router)
    app.dependency_overrides[forecast.get_job_manager] = lambda: manager
    return TestClient(app), manager


def _wait(client: TestClient, job_id: str, status: str) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get(f"/api/forecasts/jobs/{job_id}")
        assert response.status_code == 200
        if response.json()["status"] == status:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(response.json())


def test_create_poll_and_read_stored_result_contract(tmp_path) -> None:
    def run(config, progress, cancelled):
        progress(0.5, "Halfway")
        return {
            "schemaVersion": 1,
            "experiment": {"config": {"areas": ["NO1"], "models": ["ridge"], "horizon_hours": 24}},
            "predictions": [
                {
                    "area": "NO1",
                    "model": "ridge",
                    "targetTime": "2026-08-01T00:00:00Z",
                    "actual": 10,
                    "prediction": 11,
                }
            ],
            "metrics": [{"area": "NO1", "model": "ridge", "mae": 1}],
            "metadata": {"forecastIssueTime": "2026-08-01T00:00:00Z"},
        }

    client, manager = _client(tmp_path, runner=run)
    try:
        response = client.post(
            "/api/forecasts/jobs", json={"kind": "evaluation", "config": {"random_seed": 7}}
        )
        assert response.status_code == 202
        created = response.json()
        assert set(created) == {
            "id", "kind", "status", "config", "progress", "message", "error", "resultId",
            "createdAt", "updatedAt", "startedAt", "completedAt", "limits",
        }
        assert created["kind"] == "evaluation"

        finished = _wait(client, created["id"], "succeeded")
        assert finished["resultId"] == created["id"]
        detail = client.get(f"/api/forecasts/results/{finished['resultId']}")
        assert detail.status_code == 200
        assert detail.json()["predictions"][0]["targetTime"] == "2026-08-01T00:00:00Z"
        listing = client.get("/api/forecasts/results").json()
        assert listing["total"] == 1
        assert listing["items"][0]["id"] == created["id"]
        assert listing["items"][0]["areas"] == ["NO1"]
        jobs = client.get("/api/forecasts/jobs").json()
        assert jobs["total"] == 1
    finally:
        manager.close()


def test_invalid_requests_are_rejected_before_worker_creation(tmp_path) -> None:
    calls = []

    def validate(config):
        calls.append(config)
        raise ValueError("horizon exceeds the public experiment limit")

    client, manager = _client(tmp_path, validator=validate)
    try:
        response = client.post(
            "/api/forecasts/jobs", json={"kind": "sarimax", "config": {"horizon": 999}}
        )
        assert response.status_code == 422
        assert "horizon" in response.json()["detail"]
        assert calls == [{"horizon": 999}]
        assert client.get("/api/forecasts/jobs").json()["total"] == 0

        assert client.post("/api/forecasts/jobs", json={"kind": "other", "config": {}}).status_code == 422
        assert client.post("/api/forecasts/jobs", json={"kind": "sarimax", "config": {}, "extra": 1}).status_code == 422
    finally:
        manager.close()


def test_cancel_and_missing_or_terminal_job_responses(tmp_path) -> None:
    started = False

    def run(config, progress, cancelled):
        nonlocal started
        started = True
        while not cancelled():
            time.sleep(0.005)
        raise InterruptedError("cancelled")

    client, manager = _client(tmp_path, runner=run)
    try:
        job = client.post("/api/forecasts/jobs", json={"kind": "evaluation", "config": {}}).json()
        deadline = time.monotonic() + 1
        while not started and time.monotonic() < deadline:
            time.sleep(0.005)
        cancelled = client.post(f"/api/forecasts/jobs/{job['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        again = client.post(f"/api/forecasts/jobs/{job['id']}/cancel")
        assert again.status_code == 409
        assert client.get("/api/forecasts/jobs/missing").status_code == 404
        assert client.get("/api/forecasts/results/missing").status_code == 404
    finally:
        manager.close()



def test_public_deployment_disables_mutations_but_keeps_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECAST_JOBS_ENABLED", "false")
    client, manager = _client(tmp_path)
    try:
        assert client.get("/api/forecasts/capabilities").json() == {"customJobsEnabled": False}
        assert client.get("/api/forecasts/results").status_code == 200
        assert client.post("/api/forecasts/jobs", json={"kind": "sarimax"}).status_code == 403
        assert client.post("/api/forecasts/jobs/anything/cancel").status_code == 403
        assert manager.list_jobs() == []
    finally:
        manager.close()
