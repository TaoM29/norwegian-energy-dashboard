"""Bounded daily household-demand profiles from published hourly observations."""
from __future__ import annotations

from datetime import date
import os
from typing import Literal

from fastapi import APIRouter, HTTPException

from app_core.analysis.demand_profiles import analyze_profiles
from backend import data

router = APIRouter(tags=["demand profiles"])


@router.get("/api/explore/demand-profiles")
def demand_profiles(area: Literal["NO1", "NO2", "NO3", "NO4", "NO5"],
                    start: date, end: date) -> dict:
    left, right = data.validate_range(start, end, max_days=366)
    frame = data.energy_frame(area, left, right, kind="consumption", groups=["household"])
    try:
        result = analyze_profiles(frame, area, left, right)
    except ValueError as error:
        raise HTTPException(503, f"The published household-demand data cannot be analyzed: {error}") from error
    digest = result.pop("inputSha256")
    return {
        **result,
        "query": {"area": area, "start": start.isoformat(), "end": end.isoformat(),
                  "kind": "consumption", "group": "household", "interval": "[start,end)"},
        "dataMode": "fixture" if os.environ.get("ENERGY_DATA_MODE") == "fixture" else "observed",
        "unit": "kWh",
        "metadata": {
            "provenance": dict(frame.attrs.get("provenance", {})),
            "inputSha256": digest,
            "scope": "Observed area-level household energy; profiles do not identify household types or individual behavior.",
        },
    }
