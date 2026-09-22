"""Read-only access to a prepared retrospective demand-change study."""
from __future__ import annotations

from datetime import date, timedelta
import json
import math
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.data import database_path

router = APIRouter(prefix="/api/diagnostics/demand-changes", tags=["diagnostics"])


def artifact_path() -> Path:
    configured = os.environ.get("DEMAND_CHANGES_ARTIFACT")
    return Path(configured).expanduser().resolve() if configured else database_path().parent / "analyses/demand-changes.json"


def _reject(value: str):
    raise ValueError(f"Nonfinite JSON number: {value}")


def _float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("Nonfinite JSON number")
    return parsed


def _number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _validate(study: dict) -> None:
    if (not isinstance(study, dict) or study.get("schemaVersion") != 1
            or study.get("area") != "NO1" or study.get("dataMode") not in {"observed", "fixture"}
            or not isinstance(study.get("id"), str) or not isinstance(study.get("createdAt"), str)
            or not isinstance(study.get("protocol"), dict) or not isinstance(study.get("metadata"), dict)):
        raise ValueError("Invalid study header")
    if study.get("status") == "unavailable":
        if not isinstance(study.get("reason"), str):
            raise ValueError("Missing availability reason")
        return
    if study.get("status") != "ok":
        raise ValueError("Unknown study status")
    if not isinstance(study.get("sensitivities"), list) or not isinstance(study.get("controlledValidation"), dict):
        raise ValueError("Missing study checks")
    rows = study["dailyRows"]
    if not isinstance(rows, list) or not rows or len(rows) > 732:
        raise ValueError("Invalid daily observations")
    for period in ("calibration", "test"):
        selected = [row for row in rows if row["period"] == period]
        if not selected:
            raise ValueError("Missing study period")
        previous = None
        complete = 0
        for row in selected:
            day = date.fromisoformat(row["date"])
            if previous is not None and day != previous + timedelta(days=1):
                raise ValueError("Daily observations must preserve the calendar grid")
            previous = day
            if type(row["complete"]) is not bool or row["expectedHours"] != 24 or type(row["okHours"]) is not int or not 0 <= row["okHours"] <= 24:
                raise ValueError("Invalid daily coverage")
            if row["complete"]:
                if row["okHours"] != 24 or not all(_number(row[key]) for key in ("actual", "expected", "residual")):
                    raise ValueError("Complete day lacks finite values")
                if not math.isclose(row["actual"] - row["expected"], row["residual"], rel_tol=1e-9, abs_tol=1e-6):
                    raise ValueError("Inconsistent saved residual")
                complete += 1
            elif any(row[key] is not None for key in ("actual", "expected", "residual")):
                raise ValueError("Incomplete day must remain missing")
        coverage = study["coverage"][period]
        if (coverage["expectedDays"] != len(selected) or coverage["completeDays"] != complete
                or coverage["incompleteDays"] != len(selected) - complete):
            raise ValueError("Inconsistent coverage summary")
    if any(row["period"] not in {"calibration", "test"} for row in rows):
        raise ValueError("Unknown daily period")
    primary = study["primary"]
    if type(primary.get("detected")) is not bool:
        raise ValueError("Missing decision")
    if primary.get("status") == "insufficient_data":
        if primary["detected"] or primary.get("candidate") is not None:
            raise ValueError("Unsupported change decision")
        return
    if (primary.get("status") != "ok" or not all(_number(primary.get(key)) for key in ("score", "pValue", "thresholdApprox95", "calibrationScaleKwh"))
            or not 0 < primary["pValue"] <= 1 or primary["calibrationScaleKwh"] <= 0):
        raise ValueError("Invalid scan result")
    alpha = study["protocol"]["config"]["alpha"]
    if not _number(alpha) or not 0 < alpha < 1 or primary["detected"] != (primary["pValue"] <= alpha):
        raise ValueError("Inconsistent threshold decision")
    candidate = primary["candidate"]
    split = date.fromisoformat(candidate["date"])
    if candidate["before"]["endExclusive"] != split.isoformat() or candidate["after"]["start"] != split.isoformat():
        raise ValueError("Inconsistent candidate boundary")
    for segment in (candidate["before"], candidate["after"]):
        if (type(segment["days"]) is not int or segment["days"] < 1
                or len(segment["residualDistribution"]) != segment["days"]
                or not all(_number(value) for value in segment["residualDistribution"])
                or not all(_number(segment.get(key)) for key in ("meanActual", "meanExpected", "meanResidual", "medianResidual", "q1Residual", "q3Residual"))):
            raise ValueError("Invalid descriptive segment")
    if not all(_number(candidate.get(key)) for key in ("deltaResidualKwh", "standardizedDelta")):
        raise ValueError("Invalid effect description")


def read_study(path: Path) -> dict:
    try:
        study = json.loads(path.read_text(), parse_constant=_reject, parse_float=_float)
        _validate(study)
        return study
    except FileNotFoundError as exc:
        raise HTTPException(404, "No saved demand-change study is available yet.") from exc
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise HTTPException(503, "The saved demand-change study is unreadable or incompatible.") from exc


@router.get("")
def get_changes() -> dict:
    return read_study(artifact_path())


@router.get("/artifact")
def download_changes() -> FileResponse:
    path = artifact_path()
    read_study(path)
    return FileResponse(path, media_type="application/json", filename=path.name)
