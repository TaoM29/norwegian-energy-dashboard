"""HTTP routes for stored forecast results and bounded custom jobs."""
from __future__ import annotations

import atexit
import threading
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from backend.forecast_jobs import (
    ForecastArtifactError,
    ForecastJobManager,
    JobConflict,
    JobQueueFull,
)


router = APIRouter(prefix="/api/forecasts", tags=["forecasts"])


class ForecastJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["evaluation", "sarimax"]
    config: dict[str, Any] = Field(default_factory=dict)


_manager: ForecastJobManager | None = None
_manager_lock = threading.Lock()


def get_job_manager() -> ForecastJobManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = ForecastJobManager()
    return _manager


def _close_manager() -> None:
    if _manager is not None:
        _manager.close()


atexit.register(_close_manager)


def _not_found(record: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Forecast {record} was not found.")


@router.get("/results")
def list_results(manager: ForecastJobManager = Depends(get_job_manager)) -> dict[str, Any]:
    try:
        items = manager.store.list_result_summaries()
    except ForecastArtifactError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"items": items, "total": len(items)}


@router.get("/results/{result_id}")
def get_result(
    result_id: str, manager: ForecastJobManager = Depends(get_job_manager)
) -> dict[str, Any]:
    try:
        return manager.store.get_result(result_id)
    except KeyError as exc:
        raise _not_found("result") from exc
    except ForecastArtifactError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/jobs")
def list_jobs(manager: ForecastJobManager = Depends(get_job_manager)) -> dict[str, Any]:
    try:
        items = manager.list_jobs()
    except ForecastArtifactError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"items": items, "total": len(items)}


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str, manager: ForecastJobManager = Depends(get_job_manager)
) -> dict[str, Any]:
    try:
        return manager.get_job(job_id)
    except KeyError as exc:
        raise _not_found("job") from exc
    except ForecastArtifactError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
def create_job(
    request: ForecastJobRequest,
    manager: ForecastJobManager = Depends(get_job_manager),
) -> dict[str, Any]:
    try:
        return manager.create_job(request.kind, request.config)
    except JobQueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str, manager: ForecastJobManager = Depends(get_job_manager)
) -> dict[str, Any]:
    try:
        return manager.cancel_job(job_id)
    except KeyError as exc:
        raise _not_found("job") from exc
    except JobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ForecastArtifactError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
