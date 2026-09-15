from __future__ import annotations

import threading
import time

import pytest

from backend.forecast_jobs import (
    ForecastJobManager,
    ForecastStore,
    JobConflict,
    JobQueueFull,
    summarize_result,
    utc_now,
)


def _wait_for(manager: ForecastJobManager, job_id: str, statuses: set[str], timeout: float = 3) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get_job(job_id)
        if job["status"] in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(f"Job did not reach {statuses}: {manager.get_job(job_id)}")


def test_successful_job_persists_progress_result_and_reproducibility_metadata(tmp_path) -> None:
    observed = {}

    def validate(config):
        observed["validated"] = dict(config)
        return {"areas": ["NO1"], "models": ["ridge"], "horizon_hours": 24, **config}

    def run(config, progress, cancelled):
        assert not cancelled()
        progress(0.4, "Evaluating NO1")
        return {
            "schemaVersion": 1,
            "experiment": {"config": config},
            "predictions": [
                {"area": "NO1", "model": "ridge", "targetTime": "2026-08-01T00:00:00Z"}
            ],
            "metrics": [],
            "metadata": {
                "forecastIssueTime": "2026-08-01T00:00:00Z",
                "datasetVersions": {"energy": "fixture-v1"},
                "trainingWindow": {"start": "2026-04-01", "end": "2026-08-01"},
            },
        }

    manager = ForecastJobManager(
        tmp_path, use_process=False, runners={"evaluation": run}, validators={"evaluation": validate}
    )
    try:
        created = manager.create_job("evaluation", {"random_seed": 7})
        finished = _wait_for(manager, created["id"], {"succeeded"})
        assert observed["validated"] == {"random_seed": 7}
        assert finished["progress"] == 1
        assert finished["resultId"] == created["id"]

        result = manager.store.get_result(created["id"])
        assert result["metadata"]["datasetVersions"] == {"energy": "fixture-v1"}
        assert result["metadata"]["revision"]["sourceFingerprint"]
        assert result["metadata"]["environment"]["python"]
        assert result["metadata"]["runtime"]["durationSeconds"] >= 0
        summary = summarize_result(result)
        assert summary["areas"] == ["NO1"]
        assert summary["models"] == ["ridge"]
        assert summary["issueTime"] == "2026-08-01T00:00:00Z"
        assert summary["horizon"] == 24
    finally:
        manager.close()


def test_validation_happens_before_worker_and_queue_is_bounded(tmp_path) -> None:
    called = threading.Event()
    release = threading.Event()

    def validate(config):
        if config.get("invalid"):
            raise ValueError("invalid before spawn")
        return dict(config)

    def run(config, progress, cancelled):
        called.set()
        while not release.wait(0.01):
            if cancelled():
                raise InterruptedError("cancelled")
        return {"config": config, "metadata": {}}

    manager = ForecastJobManager(
        tmp_path,
        max_queued=1,
        use_process=False,
        runners={"sarimax": run},
        validators={"sarimax": validate},
    )
    try:
        with pytest.raises(ValueError, match="before spawn"):
            manager.create_job("sarimax", {"invalid": True})
        assert not called.is_set()

        first = manager.create_job("sarimax", {"number": 1})
        assert called.wait(1)
        second = manager.create_job("sarimax", {"number": 2})
        assert manager.get_job(second["id"])["status"] == "queued"
        with pytest.raises(JobQueueFull):
            manager.create_job("sarimax", {"number": 3})

        cancelled = manager.cancel_job(second["id"])
        assert cancelled["status"] == "cancelled"
        with pytest.raises(JobConflict):
            manager.cancel_job(second["id"])
        release.set()
        assert _wait_for(manager, first["id"], {"succeeded"})["status"] == "succeeded"
    finally:
        release.set()
        manager.close()


def test_running_job_can_be_cancelled_without_publishing_a_result(tmp_path) -> None:
    running = threading.Event()

    def run(config, progress, cancelled):
        running.set()
        while not cancelled():
            time.sleep(0.005)
        raise InterruptedError("cancelled")

    manager = ForecastJobManager(
        tmp_path,
        use_process=False,
        runners={"evaluation": run},
        validators={"evaluation": dict},
    )
    try:
        job = manager.create_job("evaluation", {})
        assert running.wait(1)
        cancelled = manager.cancel_job(job["id"])
        assert cancelled["status"] == "cancelled"
        with pytest.raises(KeyError):
            manager.store.get_result(job["id"])
    finally:
        manager.close()


def test_restart_marks_abandoned_jobs_failed_but_preserves_completed_jobs(tmp_path) -> None:
    store = ForecastStore(tmp_path)
    base = {
        "kind": "evaluation",
        "config": {},
        "progress": 0,
        "message": None,
        "error": None,
        "resultId": None,
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
        "startedAt": None,
        "completedAt": None,
        "limits": {},
    }
    store.save_job({**base, "id": "queued-one", "status": "queued"})
    store.save_job({**base, "id": "running-one", "status": "running"})
    store.save_job({**base, "id": "done-one", "status": "succeeded", "resultId": "done-one"})

    manager = ForecastJobManager(tmp_path, use_process=False)
    try:
        assert manager.get_job("queued-one")["status"] == "failed"
        interrupted = manager.get_job("running-one")
        assert interrupted["status"] == "failed"
        assert "restart" in interrupted["error"]
        assert manager.get_job("done-one")["status"] == "succeeded"
    finally:
        manager.close()


def test_runtime_limit_fails_a_cooperative_fake_worker(tmp_path) -> None:
    def run(config, progress, cancelled):
        while not cancelled():
            time.sleep(0.005)
        raise InterruptedError("stopped at limit")

    manager = ForecastJobManager(
        tmp_path,
        timeout_seconds=0.03,
        use_process=False,
        runners={"evaluation": run},
        validators={"evaluation": dict},
    )
    try:
        created = manager.create_job("evaluation", {})
        failed = _wait_for(manager, created["id"], {"failed"})
        assert "runtime limit" in failed["error"].lower()
        assert failed["resultId"] is None
    finally:
        manager.close()


def test_results_are_immutable(tmp_path) -> None:
    store = ForecastStore(tmp_path)
    result = {"id": "prepared-v1", "kind": "evaluation", "createdAt": utc_now()}
    store.save_result(result)
    with pytest.raises(FileExistsError, match="immutable"):
        store.save_result({**result, "title": "replacement"})
    assert store.get_result("prepared-v1") == result
