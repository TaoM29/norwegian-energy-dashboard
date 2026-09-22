"""Bounded, read-only household-demand summaries from published hourly data."""
from __future__ import annotations

from datetime import date
import os
from typing import Literal

from fastapi import APIRouter, HTTPException

from app_core.analysis.demand_peaks import analyze_area, analyze_regions
from app_core.ingestion.models import AREAS
from backend import data

router = APIRouter(tags=["demand peaks"])


def _query(start: date, end: date) -> dict:
    return {"start": start.isoformat(), "end": end.isoformat(),
            "kind": "consumption", "group": "household", "interval": "[start,end)"}


def _mode() -> str:
    return "fixture" if os.environ.get("ENERGY_DATA_MODE") == "fixture" else "observed"


def _frame(area, start, end):
    return data.energy_frame(area, start, end, kind="consumption", groups=["household"])


@router.get("/api/explore/demand-peaks")
def demand_peaks(area: Literal["NO1", "NO2", "NO3", "NO4", "NO5"], start: date, end: date) -> dict:
    left, right = data.validate_range(start, end, max_days=366)
    frame = _frame(area, left, right)
    try:
        result = analyze_area(frame, area, left, right)
    except ValueError as error:
        raise HTTPException(503, f"The published household-demand data cannot be analyzed: {error}") from error
    return {**result, "query": {**_query(start, end), "area": area}, "dataMode": _mode(), "unit": "kWh",
            "metadata": {"provenance": dict(frame.attrs.get("provenance", {})),
                         "scope": "Observed hourly household energy; no instantaneous peak or grid-capacity inference."}}


@router.get("/api/regional/demand-peaks")
def regional_demand_peaks(start: date, end: date) -> dict:
    left, right = data.validate_range(start, end, max_days=366)
    frames = {area: _frame(area, left, right) for area in AREAS}
    versions = {frame.attrs.get("provenance", {}).get("version") for frame in frames.values()}
    if len(versions) > 1:
        raise HTTPException(503, "The energy snapshot changed during comparison. Retry to use one consistent snapshot.")
    try:
        result = analyze_regions(frames, left, right)
    except ValueError as error:
        raise HTTPException(503, f"The published household-demand data cannot be compared: {error}") from error
    return {**result, "query": _query(start, end), "dataMode": _mode(), "unit": "kWh",
            "metadata": {"provenance": {area: dict(frame.attrs.get("provenance", {})) for area, frame in frames.items()},
                         "scope": "All regional metrics use shared valid timestamps. Co-movement does not establish transfers or causation."}}
