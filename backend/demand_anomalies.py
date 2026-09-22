"""Read-only inspection of a prepared retrospective household-demand study."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app_core.ingestion.models import AREAS
from backend.data import database_path

router = APIRouter(prefix="/api/diagnostics/demand-anomalies", tags=["diagnostics"])
CANDIDATE_LIMIT = 20


def artifact_path() -> Path:
    configured = os.environ.get("DEMAND_ANOMALIES_ARTIFACT")
    return Path(configured).expanduser().resolve() if configured else database_path().parent / "analyses/demand-anomalies.json"


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"Nonfinite JSON number: {value}")


def read_study(path: Path) -> dict:
    try:
        study = json.loads(path.read_text(), parse_constant=_reject_nonfinite)
        if (not isinstance(study, dict) or study.get("schemaVersion") != 1
                or study.get("dataMode") not in {"observed", "fixture"}
                or not isinstance(study.get("id"), str) or not isinstance(study.get("createdAt"), str)
                or not isinstance(study.get("protocol"), dict) or not isinstance(study.get("metadata"), dict)
                or not isinstance(study.get("areas"), list) or not study["areas"]):
            raise ValueError("Invalid study header")
        seen = set()
        for area in study["areas"]:
            if not isinstance(area, dict) or area.get("area") not in AREAS or area["area"] in seen:
                raise ValueError("Invalid or duplicate area")
            seen.add(area["area"])
            if area.get("status") == "unavailable":
                if not isinstance(area.get("reason"), str):
                    raise ValueError("Unavailable area needs a reason")
            elif area.get("status") == "ok":
                for key in ("summary", "calibration", "coverage", "splits", "metadata"):
                    if not isinstance(area.get(key), dict):
                        raise ValueError(f"Missing {key}")
                if not isinstance(area.get("rows"), list) or not area["rows"] or not isinstance(area.get("candidates"), list):
                    raise ValueError("Missing saved observations or candidate ranking")
                for row in area["rows"]:
                    if not isinstance(row, dict) or not isinstance(row.get("time"), str):
                        raise ValueError("Invalid hourly row")
                    if datetime.fromisoformat(row["time"].replace("Z", "+00:00")).tzinfo is None:
                        raise ValueError("Hourly row requires an explicit timezone")
                ids = [item["id"] for item in area["candidates"]]
                if len(ids) != len(set(ids)):
                    raise ValueError("Duplicate candidate identity")
                for item in area["candidates"]:
                    if (not isinstance(item.get("id"), str) or not isinstance(item.get("peakTime"), str)
                            or datetime.fromisoformat(item["peakTime"].replace("Z", "+00:00")).tzinfo is None):
                        raise ValueError("Candidate requires an identity and timezone-aware peak time")
            else:
                raise ValueError("Unknown area status")
        return study
    except FileNotFoundError as exc:
        raise HTTPException(404, "No saved demand anomaly study is available yet.") from exc
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(503, "The saved demand anomaly study is unreadable or incompatible.") from exc


@router.get("")
def get_anomalies(area: Literal["NO1", "NO2", "NO3", "NO4", "NO5"] = "NO1",
                  candidate: str | None = Query(default=None, max_length=200)) -> dict:
    study = read_study(artifact_path())
    selected = next((item for item in study["areas"] if item["area"] == area), None)
    if selected is None:
        selected = {"area": area, "status": "unavailable", "reason": "No saved result for this area."}
    ranking = selected.get("candidates", [])[:CANDIDATE_LIMIT]
    chosen = next((item for item in ranking if item["id"] == candidate), None) if candidate else next(iter(ranking), None)
    if candidate and chosen is None and selected["status"] == "ok":
        raise HTTPException(404, "The requested candidate is not in the saved review list.")
    rows = selected.get("rows", [])
    if chosen:
        center = datetime.fromisoformat(chosen["peakTime"].replace("Z", "+00:00"))
        left, right = center - timedelta(hours=48), center + timedelta(hours=49)
        context = [row for row in rows if left <= datetime.fromisoformat(row["time"].replace("Z", "+00:00")) < right]
    else:
        context = rows[:168]
    omit = {"rows", "calibrationRows", "candidates"}
    compact = {key: value for key, value in selected.items() if key not in omit}
    compact.update(candidates=[{key: value for key, value in item.items() if key != "peers"} for item in ranking],
                   candidateLimit=CANDIDATE_LIMIT, totalCandidates=len(selected.get("candidates", [])))
    return {
        **{key: value for key, value in study.items() if key != "areas"},
        "areas": [{key: value for key, value in item.items() if key in {"area", "status", "reason", "summary"}}
                  for item in study["areas"]],
        "selectedArea": compact,
        "selection": {"candidate": {key: value for key, value in chosen.items() if key != "peers"} if chosen else None,
                      "rows": context, "peers": chosen.get("peers", {}) if chosen else {}},
    }


@router.get("/artifact")
def download_anomalies() -> FileResponse:
    path = artifact_path()
    read_study(path)
    return FileResponse(path, media_type="application/json", filename=path.name)
