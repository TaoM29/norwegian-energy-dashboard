from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.main import app
from scripts.scheduled_refresh import next_run


def test_health_does_not_hide_unavailable_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ENERGY_DATABASE", str(tmp_path / "missing.sqlite"))
    monkeypatch.setenv("ENERGY_DATA_MODE", "fixture")
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok", "dataMode": "fixture"}
    assert client.get("/api/ready").status_code == 503


def test_daily_refresh_time_rolls_over_after_scheduled_minute():
    before = datetime(2026, 9, 15, 19, 36, tzinfo=timezone.utc)
    at = datetime(2026, 9, 15, 19, 37, tzinfo=timezone.utc)
    assert next_run(before) == at
    assert next_run(at) == datetime(2026, 9, 16, 19, 37, tzinfo=timezone.utc)


def test_container_forecast_provenance_uses_build_revision(monkeypatch):
    from backend import forecast_jobs
    from app_core.analysis import forecast_evaluation
    monkeypatch.setenv("ENERGY_CODE_COMMIT", "test-image-revision")
    def missing_git(*args, **kwargs):
        raise FileNotFoundError("git is absent from runtime image")
    monkeypatch.setattr(forecast_jobs.subprocess, "run", missing_git)
    revision = forecast_jobs._git_revision()
    assert revision["commit"] == "test-image-revision"
    assert revision["dirty"] is None
    assert len(revision["sourceFingerprint"]) == 64
    assert forecast_evaluation._code_commit() == "test-image-revision"


def test_failed_refresh_is_unhealthy_and_preserves_last_success(tmp_path, monkeypatch):
    from scripts import scheduled_refresh as worker
    from types import SimpleNamespace
    path = tmp_path / "status.json"
    worker.write_status({"lastSuccess": "2026-01-01T00:00:00+00:00"}, path)
    monkeypatch.setattr(worker.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1))
    result = worker.run_once(path)
    assert result["state"] == "failed"
    assert result["lastSuccess"] == "2026-01-01T00:00:00+00:00"
    assert not worker.healthy(path)
    monkeypatch.setattr(worker.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    assert worker.run_once(path)["state"] == "succeeded"
    assert worker.healthy(path)


def test_refresh_timeout_and_overdue_schedule_are_unhealthy(tmp_path, monkeypatch):
    from scripts import scheduled_refresh as worker
    path = tmp_path / "status.json"
    def timeout(*args, **kwargs):
        raise worker.subprocess.TimeoutExpired("refresh", 3600)
    monkeypatch.setattr(worker.subprocess, "run", timeout)
    assert worker.run_once(path)["state"] == "failed"
    assert not worker.healthy(path)
    worker.write_status({"state": "running", "nextRun": "2026-01-01T19:37:00+00:00"}, path)
    assert worker.healthy(path, datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc))
    assert not worker.healthy(path, datetime(2026, 1, 1, 21, 0, tzinfo=timezone.utc))
