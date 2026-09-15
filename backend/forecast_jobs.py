"""Small, persistent local job runner for forecast experiments.

The public dashboard reads immutable result JSON. Custom experiments run one at a
time in a child process so they can be cancelled and bounded without bringing a
queue service into the local deployment.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Literal, Mapping
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "data" / "forecasts"
ARTIFACT_ROOT_ENV = "FORECAST_ARTIFACT_ROOT"
DEFAULT_TIMEOUT_SECONDS = 30 * 60
DEFAULT_MAX_QUEUED = 4
JOB_KINDS = ("evaluation", "sarimax")
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

Runner = Callable[..., dict[str, Any]]
Validator = Callable[[dict[str, Any]], dict[str, Any]]


class ForecastArtifactError(RuntimeError):
    """Raised when a persisted forecast record cannot be read safely."""


class JobQueueFull(RuntimeError):
    """Raised before creating a job when the bounded queue is full."""


class JobConflict(RuntimeError):
    """Raised when an operation is invalid for the current job state."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def artifact_root() -> Path:
    configured = os.environ.get(ARTIFACT_ROOT_ENV)
    return Path(configured).expanduser().resolve() if configured else DEFAULT_ARTIFACT_ROOT


def _jsonable(value: Any) -> Any:
    """Convert common numerical and timestamp values without accepting NaN JSON."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, Path)):
        return value.isoformat().replace("+00:00", "Z") if isinstance(value, datetime) else str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        return _jsonable(value.item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    raise TypeError(f"Forecast result contains unsupported value {type(value).__name__}.")


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(_jsonable(value), indent=2, sort_keys=True, allow_nan=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ForecastArtifactError(f"Forecast artifact {path.name} is unreadable.") from exc
    if not isinstance(value, dict):
        raise ForecastArtifactError(f"Forecast artifact {path.name} is not a JSON object.")
    return value


def _validate_id(record_id: str) -> str:
    if not _SAFE_ID.fullmatch(record_id) or record_id in {".", ".."}:
        raise KeyError(record_id)
    return record_id


class ForecastStore:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root).resolve() if root is not None else artifact_root()
        self.jobs_dir = self.root / "jobs"
        self.results_dir = self.root / "results"
        self.manifest_path = self.root / "manifest.json"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def save_job(self, job: dict[str, Any]) -> None:
        _atomic_json(self.jobs_dir / f"{_validate_id(str(job['id']))}.json", job)

    def get_job(self, job_id: str) -> dict[str, Any]:
        path = self.jobs_dir / f"{_validate_id(job_id)}.json"
        if not path.is_file():
            raise KeyError(job_id)
        return _read_json(path)

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs = [_read_json(path) for path in self.jobs_dir.glob("*.json")]
        return sorted(jobs, key=lambda item: str(item.get("createdAt", "")), reverse=True)

    def save_result(self, result: dict[str, Any]) -> None:
        path = self.results_dir / f"{_validate_id(str(result['id']))}.json"
        if path.exists():
            raise FileExistsError(f"Forecast result {result['id']} already exists and is immutable.")
        _atomic_json(path, result)
        self._rebuild_manifest()

    def get_result(self, result_id: str) -> dict[str, Any]:
        path = self.results_dir / f"{_validate_id(result_id)}.json"
        if not path.is_file():
            raise KeyError(result_id)
        return _read_json(path)

    def list_results(self) -> list[dict[str, Any]]:
        results = [_read_json(path) for path in self.results_dir.glob("*.json")]
        return sorted(results, key=lambda item: str(item.get("createdAt", "")), reverse=True)

    def list_result_summaries(self) -> list[dict[str, Any]]:
        """Read the compact index, rebuilding it if result files changed."""
        paths = list(self.results_dir.glob("*.json"))
        expected_ids = {path.stem for path in paths}
        try:
            manifest = _read_json(self.manifest_path)
            items = manifest.get("items")
            if not isinstance(items, list) or {item.get("id") for item in items if isinstance(item, dict)} != expected_ids:
                raise ForecastArtifactError("Forecast manifest is stale.")
            return items
        except (ForecastArtifactError, KeyError):
            return self._rebuild_manifest()["items"]

    def _rebuild_manifest(self) -> dict[str, Any]:
        items = [summarize_result(result) for result in self.list_results()]
        manifest = {
            "schemaVersion": 1,
            "updatedAt": utc_now(),
            "latestResultId": items[0]["id"] if items else None,
            "items": items,
        }
        _atomic_json(self.manifest_path, manifest)
        return manifest

    def recover_interrupted_jobs(self) -> None:
        """Make work abandoned by a prior service instance visible and terminal."""
        for job in self.list_jobs():
            if job.get("status") not in {"queued", "running"}:
                continue
            now = utc_now()
            job.update(
                status="failed",
                error="Job was interrupted by a service restart and was not resumed.",
                message="Interrupted by service restart",
                updatedAt=now,
                completedAt=now,
            )
            self.save_job(job)


def _git_revision() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=3,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=3,
        ).stdout)
    except (OSError, subprocess.SubprocessError):
        commit, dirty = os.environ.get("ENERGY_CODE_COMMIT") or None, None

    digest = hashlib.sha256()
    for folder in (ROOT / "app_core", ROOT / "backend"):
        for path in sorted(folder.rglob("*.py")):
            digest.update(str(path.relative_to(ROOT)).encode())
            try:
                digest.update(path.read_bytes())
            except OSError:
                continue
    return {"commit": commit, "dirty": dirty, "sourceFingerprint": digest.hexdigest()}


def _environment() -> dict[str, Any]:
    packages = ("fastapi", "numpy", "pandas", "scikit-learn", "scipy", "statsmodels")
    dependencies: dict[str, str] = {}
    for package in packages:
        try:
            dependencies[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": dependencies,
    }


def capture_execution_context() -> dict[str, Any]:
    """Capture revision and dependency versions before a potentially long run."""
    return {"revision": _git_revision(), "environment": _environment()}


def _load_engine(kind: str) -> tuple[Runner, type[BaseException] | None]:
    if kind == "evaluation":
        from app_core.analysis import forecast_evaluation as engine

        return engine.run_evaluation, getattr(engine, "EvaluationCancelled", None)
    if kind == "sarimax":
        from app_core.analysis import forecast_sarimax as engine

        return engine.run_sarimax, getattr(engine, "SarimaxCancelled", None)
    raise ValueError(f"Unknown forecast job kind: {kind}")


def validate_job_config(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    """Run the engine-owned limits synchronously, before a worker is spawned."""
    if kind == "evaluation":
        from app_core.analysis.forecast_evaluation import validate_evaluation_config

        return validate_evaluation_config(dict(config))
    if kind == "sarimax":
        from app_core.analysis.forecast_sarimax import validate_sarimax_config

        return validate_sarimax_config(dict(config))
    raise ValueError(f"Unknown forecast job kind: {kind}")


def _result_summary(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    experiment = result.get("experiment") if isinstance(result.get("experiment"), dict) else {}
    config = experiment.get("config") if isinstance(experiment.get("config"), dict) else {}
    if not config and any(key in experiment for key in ("areas", "models", "horizon_hours", "area", "horizon")):
        config = experiment
    if not config:
        config = result.get("config") if isinstance(result.get("config"), dict) else {}
    predictions = result.get("predictions") if isinstance(result.get("predictions"), list) else []
    areas = config.get("areas") or ([config["area"]] if config.get("area") else None)
    if not areas:
        areas = sorted({str(row["area"]) for row in predictions if isinstance(row, dict) and row.get("area")})
    models = config.get("models")
    if not models:
        models = sorted({str(row["model"]) for row in predictions if isinstance(row, dict) and row.get("model")})
    if not models and result.get("kind") == "sarimax":
        models = ["SARIMAX", "Seasonal naive"]
        if config.get("weatherVariables") and config.get("evalNoExog"):
            models.insert(1, "SARIMAX (no exog)")
    training = metadata.get("trainingWindow") if isinstance(metadata.get("trainingWindow"), dict) else {}
    horizon = config.get("horizon_hours", config.get("horizon"))
    start = config.get("start") or training.get("start")
    end = config.get("end") or training.get("end")
    evaluation_origins = [
        value
        for key in ("validation_origins", "calibration_origins", "holdout_origins")
        for value in (config.get(key) or [])
        if isinstance(value, str)
    ]
    if evaluation_origins and start is None:
        first = datetime.fromisoformat(min(evaluation_origins).replace("Z", "+00:00"))
        start = (first - timedelta(days=int(config.get("train_window_days", 0)))).isoformat().replace("+00:00", "Z")
    if evaluation_origins and end is None:
        last = datetime.fromisoformat(max(evaluation_origins).replace("Z", "+00:00"))
        end = (last + timedelta(hours=int(horizon or 0))).isoformat().replace("+00:00", "Z")
    return {
        "id": result["id"],
        "kind": result.get("kind"),
        "title": result.get("title"),
        "createdAt": result.get("createdAt"),
        "issueTime": metadata.get("forecastIssueTime") or metadata.get("issueTime") or experiment.get("issueTime") or result.get("issueTime"),
        "areas": list(areas or []),
        "start": start,
        "end": end,
        "horizon": horizon,
        "models": list(models or []),
        "weatherMode": metadata.get("weatherMode") or config.get("weather_mode") or config.get("futureWeather"),
        "sourceLabel": metadata.get("sourceLabel") or "Published energy and weather snapshots",
        "metadata": metadata,
    }


def summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    return _result_summary(result)


def _prepare_result(
    job: dict[str, Any],
    payload: dict[str, Any],
    duration: float,
    execution_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = utc_now()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    result = {
        **payload,
        "id": job["id"],
        "kind": job["kind"],
        "title": payload.get("title") or (
            "Forecast model evaluation" if job["kind"] == "evaluation" else "Custom SARIMAX forecast"
        ),
        "createdAt": created_at,
        "metadata": {
            **metadata,
            "jobId": job["id"],
            "generatedAt": created_at,
            "runtime": {"durationSeconds": round(duration, 3)},
            **(execution_context or {"revision": _git_revision(), "environment": _environment()}),
        },
    }
    return _jsonable(result)


def publish_result_artifact(
    store: ForecastStore,
    *,
    kind: Literal["evaluation", "sarimax"],
    config: dict[str, Any],
    payload: dict[str, Any],
    duration_seconds: float,
    result_id: str | None = None,
    execution_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish a result produced by a scheduled/CLI run without creating a job."""
    if kind not in JOB_KINDS:
        raise ValueError("kind must be 'evaluation' or 'sarimax'.")
    if not isinstance(payload, dict):
        raise TypeError("Forecast engine must return a JSON object.")
    identifier = result_id or f"{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}"
    result = _prepare_result(
        {"id": identifier, "kind": kind, "config": _jsonable(config)},
        payload,
        duration_seconds,
        execution_context,
    )
    store.save_result(result)
    return result


def _execute_job(
    root: str,
    job_id: str,
    cancel_event: Any,
    runner_override: Runner | None = None,
) -> None:
    store = ForecastStore(root)
    job = store.get_job(job_id)
    if job.get("status") != "queued" or cancel_event.is_set():
        return
    started_at = utc_now()
    job.update(
        status="running", startedAt=started_at, updatedAt=started_at,
        progress=0.0, message="Starting forecast experiment", error=None,
    )
    store.save_job(job)
    started = time.monotonic()
    # Capture the exact source/runtime at execution start; the working tree may
    # change while a longer benchmark is running.
    execution_context = capture_execution_context()

    def cancelled() -> bool:
        return bool(cancel_event.is_set())

    def progress(fraction: float, message: str) -> None:
        if cancelled():
            return
        current = store.get_job(job_id)
        if current.get("status") != "running":
            return
        current.update(
            progress=min(1.0, max(0.0, float(fraction))),
            message=str(message), updatedAt=utc_now(),
        )
        store.save_job(current)

    cancellation_type: type[BaseException] | None = None
    try:
        if runner_override is None:
            runner, cancellation_type = _load_engine(str(job["kind"]))
        else:
            runner = runner_override
        payload = runner(dict(job["config"]), progress=progress, cancelled=cancelled)
        if not isinstance(payload, dict):
            raise TypeError("Forecast engine must return a JSON object.")
        if cancelled():
            raise InterruptedError("Forecast job cancelled.")
        result = _prepare_result(job, payload, time.monotonic() - started, execution_context)
        store.save_result(result)
        now = utc_now()
        current = store.get_job(job_id)
        if current.get("status") != "cancelled":
            current.update(
                status="succeeded", progress=1.0, message="Forecast result is ready",
                resultId=result["id"], error=None, updatedAt=now, completedAt=now,
            )
            store.save_job(current)
    except BaseException as exc:
        now = utc_now()
        current = store.get_job(job_id)
        is_cancel = cancelled() or isinstance(exc, InterruptedError)
        if cancellation_type is not None and isinstance(exc, cancellation_type):
            is_cancel = True
        if is_cancel:
            current.update(
                status="cancelled", message="Forecast job cancelled", error=None,
                updatedAt=now, completedAt=now,
            )
        else:
            current.update(
                status="failed", message="Forecast experiment failed",
                error=f"{type(exc).__name__}: {exc}", updatedAt=now, completedAt=now,
            )
        store.save_job(current)


class ForecastJobManager:
    """Bounded FIFO scheduler with exactly one active worker."""

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        max_queued: int = DEFAULT_MAX_QUEUED,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        use_process: bool = True,
        runners: Mapping[str, Runner] | None = None,
        validators: Mapping[str, Validator] | None = None,
    ) -> None:
        self.store = ForecastStore(root)
        self.max_queued = int(max_queued)
        self.timeout_seconds = float(timeout_seconds)
        self.use_process = use_process
        self.runners = dict(runners or {})
        self.validators = dict(validators or {})
        self._lock = threading.RLock()
        self._pending: list[str] = []
        self._active: tuple[str, Any, Any, float] | None = None
        self._closed = threading.Event()
        self.store.recover_interrupted_jobs()
        self._monitor = threading.Thread(target=self._monitor_jobs, daemon=True, name="forecast-job-monitor")
        self._monitor.start()

    @property
    def limits(self) -> dict[str, Any]:
        return {
            "maxConcurrent": 1,
            "maxQueued": self.max_queued,
            "timeoutSeconds": self.timeout_seconds,
        }

    def create_job(self, kind: Literal["evaluation", "sarimax"] | str, config: dict[str, Any]) -> dict[str, Any]:
        if kind not in JOB_KINDS:
            raise ValueError("kind must be 'evaluation' or 'sarimax'.")
        validator = self.validators.get(kind)
        normalized = validator(dict(config)) if validator is not None else validate_job_config(kind, config)
        if not isinstance(normalized, dict):
            raise TypeError("Forecast config validator must return a JSON object.")
        with self._lock:
            outstanding = len(self._pending) + (1 if self._active is not None else 0)
            if outstanding >= self.max_queued + 1:
                raise JobQueueFull("The forecast queue is full. Try again after another job finishes.")
            now = utc_now()
            job_id = f"{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}"
            job = {
                "id": job_id,
                "kind": kind,
                "status": "queued",
                "config": _jsonable(normalized),
                "progress": 0.0,
                "message": "Waiting for the forecast worker",
                "error": None,
                "resultId": None,
                "createdAt": now,
                "updatedAt": now,
                "startedAt": None,
                "completedAt": None,
                "limits": self.limits,
            }
            self.store.save_job(job)
            self._pending.append(job_id)
            self._launch_next_locked()
            return self.store.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self.store.get_job(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        return self.store.list_jobs()

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self.store.get_job(job_id)
            if job.get("status") in TERMINAL_STATUSES:
                raise JobConflict(f"Job is already {job['status']}.")
            if job_id in self._pending:
                self._pending.remove(job_id)
            if self._active is not None and self._active[0] == job_id:
                _, worker, cancel_event, _ = self._active
                cancel_event.set()
                if self.use_process and worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=1)
                self._active = None
            now = utc_now()
            job.update(
                status="cancelled", message="Forecast job cancelled", error=None,
                updatedAt=now, completedAt=now,
            )
            self.store.save_job(job)
            self._launch_next_locked()
            return job

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            if self._active is not None:
                _, worker, cancel_event, _ = self._active
                cancel_event.set()
                if self.use_process and worker.is_alive():
                    worker.terminate()
                worker.join(timeout=1)
                self._active = None
        self._monitor.join(timeout=1)

    def _launch_next_locked(self) -> None:
        if self._closed.is_set() or self._active is not None or not self._pending:
            return
        job_id = self._pending.pop(0)
        runner = self.runners.get(self.store.get_job(job_id)["kind"])
        if self.use_process:
            context = multiprocessing.get_context("spawn")
            cancel_event = context.Event()
            worker = context.Process(
                target=_execute_job,
                args=(str(self.store.root), job_id, cancel_event, runner),
                daemon=True,
                name=f"forecast-{job_id}",
            )
        else:
            cancel_event = threading.Event()
            worker = threading.Thread(
                target=_execute_job,
                args=(str(self.store.root), job_id, cancel_event, runner),
                daemon=True,
                name=f"forecast-{job_id}",
            )
        worker.start()
        self._active = (job_id, worker, cancel_event, time.monotonic())

    def _monitor_jobs(self) -> None:
        while not self._closed.wait(0.05):
            with self._lock:
                if self._active is None:
                    self._launch_next_locked()
                    continue
                job_id, worker, cancel_event, started = self._active
                if worker.is_alive() and time.monotonic() - started <= self.timeout_seconds:
                    continue
                if worker.is_alive():
                    cancel_event.set()
                    if self.use_process:
                        worker.terminate()
                    worker.join(timeout=1)
                    job = self.store.get_job(job_id)
                    now = utc_now()
                    job.update(
                        status="failed", message="Forecast job exceeded its runtime limit",
                        error=f"Runtime limit of {self.timeout_seconds:g} seconds exceeded.",
                        updatedAt=now, completedAt=now,
                    )
                    self.store.save_job(job)
                else:
                    worker.join(timeout=0)
                    job = self.store.get_job(job_id)
                    if job.get("status") not in TERMINAL_STATUSES:
                        now = utc_now()
                        exit_code = getattr(worker, "exitcode", None)
                        job.update(
                            status="failed", message="Forecast worker exited unexpectedly",
                            error=f"Forecast worker exited without a result (exit code {exit_code}).",
                            updatedAt=now, completedAt=now,
                        )
                        self.store.save_job(job)
                self._active = None
                self._launch_next_locked()
