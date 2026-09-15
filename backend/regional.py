"""Regional energy comparison, geography, and point snow-drift API."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import pandas as pd
import requests
from pydantic import BaseModel, Field, model_validator

from app_core.analysis.snow_drift import (
    FENCE_FACTORS,
    analyze_snow_drift,
    season_span,
)
from app_core.ingestion.models import AREAS, BASE_GROUPS
from app_core.loaders.weather import load_openmeteo_point
from backend.data import energy_frame, records, validate_range


router = APIRouter(prefix="/api/regional", tags=["regional"])
ROOT = Path(__file__).resolve().parents[1]
GEOGRAPHY_PATH = ROOT / "data" / "file.geojson"
REGIONAL_GROUPS = {
    "production": (*BASE_GROUPS["production"], "nuclear"),
    "consumption": BASE_GROUPS["consumption"],
}


class SnowDriftRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    seasonStart: int = Field(ge=1940, le=2100)
    seasonEnd: int = Field(ge=1940, le=2100)
    transportDistanceM: float = Field(default=3000, ge=100, le=10_000)
    fetchDistanceM: float = Field(default=30_000, ge=1_000, le=200_000)
    relocationCoefficient: float = Field(default=0.5, ge=0, le=1)
    fenceType: Literal["Wyoming", "Slat-and-wire", "Solid"] = "Wyoming"

    @model_validator(mode="after")
    def validate_seasons(self) -> "SnowDriftRequest":
        if self.seasonEnd < self.seasonStart:
            raise ValueError("seasonEnd must not be before seasonStart")
        if self.seasonEnd - self.seasonStart + 1 > 25:
            raise ValueError("at most 25 seasons can be analysed at once")
        return self


def _selected_groups(kind: str, groups: str | None) -> list[str]:
    if groups is None:
        return list(BASE_GROUPS[kind])
    selected = list(dict.fromkeys(item.strip().lower() for item in groups.split(",") if item.strip()))
    if not selected:
        raise HTTPException(422, "Choose at least one energy group.")
    unknown = sorted(set(selected).difference(REGIONAL_GROUPS[kind]))
    if unknown:
        raise HTTPException(422, f"Unknown {kind} group: {', '.join(unknown)}")
    return selected


@router.get("/summary")
def regional_summary(
    start: date,
    end: date,
    kind: Literal["production", "consumption"] = "production",
    groups: str | None = Query(default=None),
) -> dict:
    """Return raw-record-weighted hourly means for all five price areas."""
    start_ts, end_ts = validate_range(start, end, max_days=366)
    selected = _selected_groups(kind, groups)
    expected_hours = int((end_ts - start_ts) / pd.Timedelta(hours=1))
    expected_records = expected_hours * len(selected)
    areas = []
    metadata: dict | None = None
    for area in AREAS:
        frame = energy_frame(area, start_ts, end_ts, kind=kind, groups=selected)
        if metadata is None:
            metadata = dict(frame.attrs.get("provenance", {}))
        usable = frame[
            frame["value"].map(lambda value: value is not None and math.isfinite(float(value)))
            & frame["quality"].eq("ok")
        ]
        observed_records = len(usable)
        observed_hours = int(usable["timestamp"].nunique()) if observed_records else 0
        areas.append(
            {
                "area": area,
                "meanKwh": float(usable["value"].mean()) if observed_records else None,
                "observedRecords": observed_records,
                "expectedRecords": expected_records,
                "observedHours": observed_hours,
                "expectedHours": expected_hours,
                "partial": observed_records != expected_records,
            }
        )
    return {
        "query": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "kind": kind,
            "groups": selected,
            "interval": "[start, end)",
        },
        "unit": "kWh per hourly group observation",
        "aggregation": "Arithmetic mean weighted by valid hourly source records",
        "areas": areas,
        "provenance": metadata or {},
    }


@lru_cache(maxsize=1)
def _geography() -> dict:
    try:
        value = json.loads(GEOGRAPHY_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(503, "Norwegian price-area geography is unavailable.") from error
    if value.get("type") != "FeatureCollection" or len(value.get("features", [])) != 5:
        raise HTTPException(503, "Norwegian price-area geography is invalid.")
    return value


@router.get("/geography")
def regional_geography() -> JSONResponse:
    """Serve the repository's real NO1–NO5 polygon geography."""
    return JSONResponse(_geography())


@router.post("/snow-drift")
def snow_drift(request: SnowDriftRequest) -> dict:
    """Calculate Tabler transport from ERA5-Seamless weather at an exact point."""
    start, end = season_span(request.seasonStart, request.seasonEnd)
    location_key = f"snow-drift:{request.latitude:.6f},{request.longitude:.6f}"
    try:
        weather = load_openmeteo_point(
            request.latitude,
            request.longitude,
            start,
            end,
            location_key=location_key,
        )
    except (ValueError, requests.RequestException) as error:
        raise HTTPException(503, str(error)) from error
    provenance = dict(weather.attrs.get("provenance", {}))
    if weather.empty:
        detail = provenance.get("error", "Point weather is unavailable for the requested seasons.")
        raise HTTPException(503, str(detail))
    try:
        result = analyze_snow_drift(
            weather,
            request.seasonStart,
            request.seasonEnd,
            request.transportDistanceM,
            request.fetchDistanceM,
            request.relocationCoefficient,
            request.fenceType,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {
        "query": request.model_dump(),
        "units": {
            "transportInternal": "kg/m",
            "transportDisplay": "tonnes/m",
            "snowWaterEquivalent": "mm",
            "windSpeed": "m/s",
            "fenceHeight": "m",
            "time": "UTC",
        },
        **result,
        "sourcePreview": records(weather.head(24)),
        "provenance": provenance,
        "method": {
            "name": "Tabler snow-drift transport",
            "snowRule": "Hourly precipitation contributes to SWE when air temperature is below +1 °C.",
            "potentialTransport": "sum(u^3.8 × 3600) / 233847 kg/m",
            "transport": "Qinf × (1 − 0.14^(F/T)); Qinf is limited by wind or relocated SWE.",
            "directionalMeaning": "Potential wind-driven transport assigned to the nearest of 16 sectors and averaged across available seasons.",
            "fenceMeaning": (
                f"Indicative storage-height estimate using the {request.fenceType} capacity "
                f"factor {FENCE_FACTORS[request.fenceType]}; it is not a site-specific engineering design."
            ),
        },
    }
