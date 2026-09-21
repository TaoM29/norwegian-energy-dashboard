"""Read-only delivery of an explicitly prepared demand-sensitivity study."""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app_core.ingestion.models import AREAS
from backend.data import database_path


router = APIRouter(prefix="/api/diagnostics/sensitivity", tags=["diagnostics"])


def artifact_path() -> Path:
    configured = os.environ.get("DEMAND_SENSITIVITY_ARTIFACT")
    return Path(configured).expanduser().resolve() if configured else database_path().parent / "analyses" / "demand-sensitivity.json"


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"Nonfinite JSON number: {value}")


def read_study(path: Path) -> dict:
    try:
        study = json.loads(path.read_text(), parse_constant=_reject_nonfinite)
        if (
            not isinstance(study, dict)
            or study.get("schemaVersion") != 1
            or study.get("dataMode") not in {"observed", "fixture"}
            or not isinstance(study.get("id"), str)
            or not isinstance(study.get("createdAt"), str)
            or not isinstance(study.get("protocol"), dict)
            or not isinstance(study.get("metadata"), dict)
            or not isinstance(study.get("areas"), list)
            or not study["areas"]
        ):
            raise ValueError("Invalid study header")
        seen = set()
        for area in study["areas"]:
            if not isinstance(area, dict) or area.get("area") not in AREAS or area["area"] in seen:
                raise ValueError("Invalid area")
            seen.add(area["area"])
            if area.get("status") == "unavailable":
                if not isinstance(area.get("reason"), str):
                    raise ValueError("Missing unavailability reason")
            elif area.get("status") == "ok":
                for key in ("curve", "models"):
                    if not isinstance(area.get(key), list) or not area[key]:
                        raise ValueError(f"Missing {key}")
                for key in ("support", "splits", "residuals", "sensitivity", "metadata"):
                    if not isinstance(area.get(key), dict):
                        raise ValueError(f"Missing {key}")
                if area.get("selectedModel") not in {"calendar", "linear", "spline"}:
                    raise ValueError("Unknown selected model")
            else:
                raise ValueError("Unknown status")
        return study
    except FileNotFoundError as exc:
        raise HTTPException(404, "No saved demand sensitivity study is available yet.") from exc
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(503, "The saved demand sensitivity study is unreadable or incompatible.") from exc


@router.get("")
def get_sensitivity() -> dict:
    study = read_study(artifact_path())
    # Keep complete prediction rows in the downloadable artifact, not every page read.
    return {**study, "areas": [{key: value for key, value in area.items() if key != "predictions"} for area in study["areas"]]}


@router.get("/artifact")
def download_sensitivity() -> FileResponse:
    path = artifact_path()
    read_study(path)
    return FileResponse(path, media_type="application/json", filename=path.name)
