"""Observed household-demand profiles on complete Europe/Oslo calendar days.

The selected interval is a UTC hourly grid. Local days with 23 or 25 hours,
partial boundary days, and days with invalid or absent observations remain in
the drilldown but never enter a 24-hour profile. Bands describe variation
between observed days, not uncertainty in a mean.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

from app_core.analysis.demand_peaks import _interval, _observations, _iso
from app_core.ingestion.models import AREAS


OSLO = "Europe/Oslo"
SEASONS = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
           6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}


def _input_sha(frame: pd.DataFrame, area: str, index: pd.DatetimeIndex) -> str:
    """Hash the selected, ordered source rows and query, including invalid values."""
    rows = frame.copy()
    rows["timestamp"] = pd.to_datetime(rows["timestamp"], utc=True)
    rows = rows.loc[(rows["timestamp"] >= index[0]) &
                    (rows["timestamp"] < index[-1] + pd.Timedelta(hours=1))]
    records = []
    for _, row in rows.sort_values("timestamp").iterrows():
        value = row["value"]
        records.append({
            "time": _iso(row["timestamp"]),
            "value": str(value),
            "quality": str(row["quality"]),
            "unit": str(row["unit"]) if "unit" in rows else None,
        })
    payload = {"area": area, "start": _iso(index[0]),
               "end": _iso(index[-1] + pd.Timedelta(hours=1)), "rows": records}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _profile(days: list[dict[str, Any]], field: str, unit: str) -> list[dict[str, Any]]:
    if days:
        matrix = np.array([day[field] for day in days], dtype=float)
        median = np.median(matrix, axis=0)
        low = np.quantile(matrix, .1, axis=0) if len(days) >= 5 else None
        high = np.quantile(matrix, .9, axis=0) if len(days) >= 5 else None
    else:
        median = low = high = None
    return [
        {"hour": hour, f"median{unit}": float(median[hour]) if median is not None else None,
         f"p10{unit}": float(low[hour]) if low is not None else None,
         f"p90{unit}": float(high[hour]) if high is not None else None}
        for hour in range(24)
    ]


def _group(days: list[dict[str, Any]], group_type: str, name: str) -> dict[str, Any]:
    selected = [day for day in days if day[group_type] == name and day["profileEligible"]]
    normalized = [day for day in selected if day["normalizedEligible"]]
    actual = _profile(selected, "_actual", "Kwh")
    shape = _profile(normalized, "_normalized", "PercentDailyMean")
    representative = None
    if normalized:
        median = np.array([point["medianPercentDailyMean"] for point in shape])
        closest = min(normalized, key=lambda day: (
            float(np.sum((np.array(day["_normalized"]) - median) ** 2)), day["date"]))
        representative = {
            "date": closest["date"],
            "squaredDistance": float(np.sum((np.array(closest["_normalized"]) - median) ** 2)),
        }
    return {"groupType": group_type, "group": name,
            "actualDayCount": len(selected), "normalizedDayCount": len(normalized),
            "actual": actual, "normalized": shape, "representative": representative}


def analyze_profiles(frame: pd.DataFrame, area: str,
                     start: str | pd.Timestamp, end: str | pd.Timestamp) -> dict[str, Any]:
    """Compare complete 24-hour local days within a UTC [start, end) selection."""
    if area not in AREAS:
        raise ValueError("unknown Norwegian price area")
    index = _interval(start, end)
    if len(index) > 366 * 24:
        raise ValueError("profile interval must be at most 366 UTC days")
    values, hourly_coverage = _observations(frame, index)
    local = index.tz_convert(OSLO)
    dates = local.date
    days: list[dict[str, Any]] = []
    for day_date in sorted(set(dates)):
        positions = np.flatnonzero(dates == day_date)
        midnight = pd.Timestamp(day_date).tz_localize(OSLO)
        next_midnight = (pd.Timestamp(day_date) + pd.Timedelta(days=1)).tz_localize(OSLO)
        expected = int((next_midnight.tz_convert("UTC") - midnight.tz_convert("UTC")) /
                       pd.Timedelta(hours=1))
        selected = len(positions)
        valid = int(np.isfinite(values[positions]).sum())
        reasons = []
        if selected != expected:
            reasons.append("partialBoundaryDay")
        if expected != 24:
            reasons.append(f"dst{expected}HourDay")
        if selected == expected and valid != expected:
            reasons.append("incompleteDay")
        eligible = not reasons
        observed = values[positions]
        mean = float(np.mean(observed)) if eligible else None
        normalized_eligible = bool(eligible and mean > 0)
        if eligible and not normalized_eligible:
            reasons.append("zeroMeanDay")
        hours = [
            {"timeUtc": _iso(index[position]), "timeOslo": local[position].isoformat(),
             "localHour": int(local[position].hour),
             "valueKwh": float(values[position]) if np.isfinite(values[position]) else None}
            for position in positions
        ]
        day: dict[str, Any] = {
            "date": day_date.isoformat(),
            "dayType": "weekend" if day_date.weekday() >= 5 else "weekday",
            "season": SEASONS[day_date.month], "expectedHours": expected,
            "selectedHours": selected, "validHours": valid,
            "profileEligible": eligible, "normalizedEligible": normalized_eligible,
            "exclusionReasons": reasons, "meanKwh": mean,
            "totalKwh": float(np.sum(observed)) if eligible else None,
            "hours": hours,
        }
        if eligible:
            by_hour = np.empty(24)
            for position in positions:
                by_hour[local[position].hour] = values[position]
            day["_actual"] = by_hour.tolist()
            if normalized_eligible:
                day["_normalized"] = (100 * by_hour / mean).tolist()
        days.append(day)
    groups = ([_group(days, "dayType", name) for name in ("weekday", "weekend")] +
              [_group(days, "season", name) for name in ("DJF", "MAM", "JJA", "SON")])
    coverage = {**hourly_coverage,
                "touchedDays": len(days),
                "expectedDays": sum(day["selectedHours"] == day["expectedHours"] for day in days),
                "profileEligibleDays": sum(day["profileEligible"] for day in days),
                "boundaryExcludedDays": sum("partialBoundaryDay" in day["exclusionReasons"] for day in days),
                "dstExcludedDays": sum(any(reason.startswith("dst") for reason in day["exclusionReasons"])
                                       for day in days),
                "incompleteExcludedDays": sum("incompleteDay" in day["exclusionReasons"] for day in days),
                "zeroMeanDays": sum("zeroMeanDay" in day["exclusionReasons"] for day in days),
                "normalizedEligibleDays": sum(day["normalizedEligible"] for day in days)}
    for day in days:
        day.pop("_actual", None)
        day.pop("_normalized", None)
    return {
        "area": area, "timezone": OSLO, "coverage": coverage, "groups": groups,
        "days": days, "inputSha256": _input_sha(frame, area, index),
        "calculation": {
            "interval": "UTC [start, end); hourly household kWh on the exact UTC grid.",
            "localDay": "Europe/Oslo midnight to midnight. Partial boundary, 23/25-hour DST, and incomplete or invalid days do not enter 24-hour profiles; all touched days remain in drilldown.",
            "groups": "Weekday means Monday–Friday, including public holidays; weekend means Saturday–Sunday. Seasons are DJF (December–February), MAM (March–May), JJA (June–August), and SON (September–November), pooled across years in the selection.",
            "coverage": "expectedDays counts whole local calendar days fully selected; touchedDays also includes partial edge days. Boundary, DST, and incomplete exclusion counts describe separate conditions and may overlap.",
            "actual": "Each local-hour median and empirical 10th/90th percentile across complete 24-hour days; bands shown with at least five days and describe between-day variability, not a confidence interval.",
            "normalized": "100 × each hourly kWh / that day's mean hourly kWh. Complete zero-mean days count in actual profiles but cannot be normalized.",
            "representative": "Observed positive-mean day with minimum sum of squared differences from the group's 24 normalized hourly medians; earliest local date breaks an exact tie. No clustering is inferred.",
            "exclusions": "Absent, quality != ok, nonfinite, or negative kWh hours are null; no interpolation.",
        },
    }
