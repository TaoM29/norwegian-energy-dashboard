from __future__ import annotations

from datetime import date
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app_core.analysis.exploration import (
    WEATHER_VARIABLES,
    Aggregation,
    energy_exploration,
    weather_exploration,
)
from app_core.ingestion.models import BASE_GROUPS
from backend import data


router = APIRouter(prefix="/api/explore", tags=["explore"])


def _selection(value: str | None, *, defaults: list[str], label: str) -> list[str]:
    if value is None:
        return defaults
    result = list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
    if not result:
        raise HTTPException(status_code=422, detail=f"Select at least one {label}.")
    return result


def _iso(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat().replace("+00:00", "Z")


@router.get("/energy")
def explore_energy(
    area: Literal["NO1", "NO2", "NO3", "NO4", "NO5"],
    start: date,
    end: date,
    kind: Literal["production", "consumption"] = "production",
    groups: str | None = Query(default=None),
    aggregation: Aggregation = "hourly",
) -> dict:
    start_utc, end_utc = data.validate_range(start, end, max_days=366)
    defaults = list(BASE_GROUPS[kind])
    selected_groups = _selection(groups, defaults=defaults, label="energy group")
    unknown = set(selected_groups) - set(defaults)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown {kind} group: {', '.join(sorted(unknown))}.",
        )

    frame = None
    if aggregation != "hourly":
        daily = data.energy_daily_frame(
            area, start_utc, end_utc, kind=kind, groups=selected_groups
        )
        expected_days = int((end_utc - start_utc) / pd.Timedelta(days=1))
        complete_daily = (
            len(daily) == expected_days * len(selected_groups)
            and not daily.empty
            and daily["value"].notna().all()
            and daily["observed_hours"].eq(24).all()
        )
        if complete_daily:
            frame = daily
    if frame is None:
        frame = data.energy_frame(
            area, start_utc, end_utc, kind=kind, groups=selected_groups
        )
    analysis = energy_exploration(
        frame, aggregation=aggregation, groups=selected_groups
    )
    expected_hours = int((end_utc - start_utc) / pd.Timedelta(hours=1))
    for total in analysis["totals"]:
        total["expectedHours"] = expected_hours
        total["partial"] = total["observedHours"] < expected_hours

    coverage = analysis["coverage"]
    coverage.update(
        {
            "firstObservation": _iso(coverage["firstObservation"]),
            "lastObservation": _iso(coverage["lastObservation"]),
            "expectedHoursPerGroup": expected_hours,
            "complete": bool(analysis["totals"])
            and all(not item["partial"] for item in analysis["totals"]),
        }
    )
    series = data.records(pd.DataFrame(analysis["series"])) if analysis["series"] else []
    shared_provenance = data.provenance(area, start, end)
    dataset_provenance = dict(frame.attrs.get("provenance", {}))
    if not dataset_provenance:
        dataset_provenance = {
            **shared_provenance.get("energy", {}),
            "unit": "kWh",
            "timezone": "UTC",
            "start": start_utc.isoformat(),
            "end": end_utc.isoformat(),
        }
    dataset_provenance["precomputedDaily"] = bool(frame.attrs.get("precomputed", False))
    return {
        "query": {
            "area": area,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "kind": kind,
            "groups": selected_groups,
            "aggregation": aggregation,
        },
        "unit": "kWh",
        "aggregationLabel": {
            "hourly": "Hourly sum (UTC)",
            "daily": "Daily sum (UTC)",
            "weekly": "Weekly sum, weeks ending Sunday (UTC)",
        }[aggregation],
        "availableGroups": defaults,
        "grandTotalKwh": analysis["grandTotalKwh"],
        "totals": analysis["totals"],
        "series": series,
        "coverage": coverage,
        "metadata": {
            **shared_provenance,
            "dataset": dataset_provenance,
            "calculation": {
                "totals": "Exact sum of all finite selected source observations before chart rendering.",
                "series": "Duplicate source observations are summed hourly; daily and weekly views sum those hourly values.",
            },
        },
    }


@router.get("/weather")
def explore_weather(
    area: Literal["NO1", "NO2", "NO3", "NO4", "NO5"],
    start: date,
    end: date,
    variables: str | None = Query(default=None),
    aggregation: Aggregation = "hourly",
    rolling_hours: int = Query(default=24, ge=0, le=240),
    normalize: bool = True,
) -> dict:
    start_utc, end_utc = data.validate_range(start, end, max_days=366)
    defaults = list(WEATHER_VARIABLES)
    selected_variables = _selection(
        variables, defaults=defaults, label="weather variable"
    )
    unknown = set(selected_variables) - WEATHER_VARIABLES.keys()
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown weather variable: {', '.join(sorted(unknown))}.",
        )

    frame = data.weather_frame(area, start_utc, end_utc)
    analysis = weather_exploration(
        frame,
        variables=selected_variables,
        aggregation=aggregation,
        rolling_hours=rolling_hours,
        normalize=normalize,
    )
    frame_provenance = dict(frame.attrs.get("provenance", {}))
    expected_hours = int((end_utc - start_utc) / pd.Timedelta(hours=1))
    observed_hours = int(frame_provenance.get("observedHours", len(frame)))
    analysis["coverage"].update(
        {
            "firstObservation": _iso(analysis["coverage"]["firstObservation"]),
            "lastObservation": _iso(analysis["coverage"]["lastObservation"]),
            "expectedHours": expected_hours,
            "observedHours": observed_hours,
            "complete": bool(frame_provenance.get("coverage_complete", observed_hours == expected_hours)),
        }
    )
    series = data.records(pd.DataFrame(analysis["series"])) if analysis["series"] else []
    return {
        "query": {
            "area": area,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "variables": selected_variables,
            "aggregation": aggregation,
            "rollingHours": rolling_hours,
            "normalize": normalize,
        },
        "valueLabel": "Normalized (0–1)" if normalize else "Value in each variable's stated unit",
        "aggregationLabel": {
            "hourly": "Hourly observations (UTC)",
            "daily": "Daily precipitation sum and variable means (UTC)",
            "weekly": "Weekly precipitation sum and variable means, weeks ending Sunday (UTC)",
        }[aggregation],
        "summary": analysis["summary"],
        "monthly": analysis["monthly"],
        "windRose": analysis["windRose"],
        "series": series,
        "coverage": analysis["coverage"],
        "variableDefinitions": analysis["variableDefinitions"],
        "metadata": {
            **data.provenance(area, start, end),
            "dataset": frame_provenance,
            "calculation": analysis["method"],
        },
    }
