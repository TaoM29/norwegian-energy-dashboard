"""Exact descriptive statistics for observed hourly household demand.

The input is one published kWh observation per UTC hour and price area. Missing
or unusable observations never become zeros or interpolated values. All
statistics are computed on the full selected interval before a caller chooses
any chart sampling. These are observed demand descriptions, not instantaneous
power, capacity, weather-adjusted effects, or evidence of energy transfers.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Mapping

import numpy as np
import pandas as pd

from app_core.ingestion.models import AREAS


def _iso(time: pd.Timestamp) -> str:
    return time.isoformat().replace("+00:00", "Z")


def _interval(start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
    left, right = pd.Timestamp(start), pd.Timestamp(end)
    if pd.isna(left) or pd.isna(right):
        raise ValueError("start and end must be valid UTC hours")
    left = left.tz_localize("UTC") if left.tz is None else left.tz_convert("UTC")
    right = right.tz_localize("UTC") if right.tz is None else right.tz_convert("UTC")
    if left != left.floor("h") or right != right.floor("h") or right <= left:
        raise ValueError("start and end must define a positive interval on the UTC hourly grid")
    return pd.date_range(left, right, freq="h", inclusive="left", tz="UTC")


def _observations(frame: pd.DataFrame, index: pd.DatetimeIndex) -> tuple[np.ndarray, dict[str, int]]:
    required = {"timestamp", "value", "quality"}
    if not required.issubset(frame.columns):
        raise ValueError("household frame needs timestamp, value, and quality columns")
    rows = frame.copy()
    try:
        rows["timestamp"] = pd.to_datetime(rows["timestamp"], utc=True, errors="raise")
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("household timestamps must be valid UTC hours") from exc
    if rows["timestamp"].isna().any():
        raise ValueError("household timestamps must be valid UTC hours")
    right = index[-1] + pd.Timedelta(hours=1)
    rows = rows.loc[(rows["timestamp"] >= index[0]) & (rows["timestamp"] < right)].copy()
    if rows["timestamp"].duplicated().any():
        raise ValueError("household timestamps must be unique UTC hours")
    if (rows["timestamp"] != rows["timestamp"].dt.floor("h")).any():
        raise ValueError("household timestamps must lie on the exact UTC hourly grid")
    if "unit" in rows and rows["unit"].ne("kWh").fillna(True).any():
        raise ValueError("household observations must use kWh")
    numeric = pd.to_numeric(rows["value"], errors="coerce")
    numeric_values = numeric.to_numpy(dtype=float, na_value=np.nan)
    finite = np.isfinite(numeric_values)
    good_quality = rows["quality"].eq("ok").fillna(False).to_numpy(dtype=bool)
    nonnegative = numeric_values >= 0
    usable = good_quality & finite & nonnegative
    values = pd.Series(np.nan, index=index, dtype=float)
    if len(rows):
        values.loc[rows.loc[usable, "timestamp"]] = numeric_values[usable]
    count = int(np.isfinite(values.to_numpy()).sum())
    details = {
        "expectedHours": len(index),
        "observedHours": count,
        "excludedHours": len(index) - count,
        "missingHours": len(index) - len(rows),
        "badQualityHours": int((~good_quality).sum()),
        "nonfiniteOrNegativeHours": int((good_quality & ~(finite & nonnegative)).sum()),
    }
    return values.to_numpy(), details


def _peak(index: pd.DatetimeIndex, values: np.ndarray) -> dict[str, Any] | None:
    present = np.isfinite(values)
    if not present.any():
        return None
    maximum = float(np.max(values[present]))
    positions = np.flatnonzero(present & (values == maximum))
    return {"time": _iso(index[positions[0]]), "valueKwh": maximum,
            "tieCount": len(positions)}


def _ramp(index: pd.DatetimeIndex, values: np.ndarray, *, rise: bool) -> dict[str, Any] | None:
    valid_pairs = np.isfinite(values[1:]) & np.isfinite(values[:-1])
    if not valid_pairs.any():
        return None
    changes = values[1:] - values[:-1]
    eligible = valid_pairs & (changes > 0 if rise else changes < 0)
    if not eligible.any():
        return None
    extreme = float(np.max(changes[eligible]) if rise else np.min(changes[eligible]))
    positions = np.flatnonzero(eligible & (changes == extreme))
    current = positions[0] + 1
    return {"time": _iso(index[current]), "previousTime": _iso(index[current - 1]),
            "changeKwh": extreme, "tieCount": len(positions)}


def _duration(values: np.ndarray) -> list[dict[str, float | int]]:
    observed = values[np.isfinite(values)]
    if len(observed) == 0:
        return []
    levels, counts = np.unique(observed, return_counts=True)
    thresholds = levels[::-1]
    cumulative = np.cumsum(counts[::-1])
    return [
        {"valueKwh": float(level), "hoursAtOrAbove": int(hours),
         "percentAtOrAbove": float(100 * hours / len(observed))}
        for level, hours in zip(thresholds, cumulative)
    ]


def analyze_area(
    frame: pd.DataFrame, area: str, start: str | pd.Timestamp, end: str | pd.Timestamp,
) -> dict[str, Any]:
    """Summarize one area's exact observed household kWh on a UTC [start, end) grid."""
    if area not in AREAS:
        raise ValueError("unknown Norwegian price area")
    index = _interval(start, end)
    values, coverage = _observations(frame, index)
    pairs = np.isfinite(values[1:]) & np.isfinite(values[:-1])
    coverage.update(validRampPairs=int(pairs.sum()), expectedRampPairs=max(len(index) - 1, 0))
    changes = np.full(len(index), np.nan)
    changes[1:][pairs] = np.diff(values)[pairs]
    present = np.isfinite(values)
    return {
        "area": area,
        "coverage": coverage,
        "summary": {
            "meanKwh": float(np.mean(values[present])) if present.any() else None,
            "peak": _peak(index, values),
            "largestRise": _ramp(index, values, rise=True),
            "largestFall": _ramp(index, values, rise=False),
        },
        "duration": _duration(values),
        "hourly": [
            {"time": _iso(time), "valueKwh": float(value) if np.isfinite(value) else None,
             "changeKwh": float(change) if np.isfinite(change) else None}
            for time, value, change in zip(index, values, changes)
        ],
        "calculation": {
            "interval": "UTC [start, end); hourly kWh observations",
            "duration": "Each unique observed value is a threshold; hoursAtOrAbove includes ties; percentAtOrAbove = 100 × hoursAtOrAbove / observedHours.",
            "peak": "Maximum observed hourly kWh; earliest UTC hour selected on an exact tie; tieCount counts all equal maxima.",
            "ramp": "Current minus previous kWh only for two consecutive valid UTC hours; earliest UTC endpoint selected on an exact tie. Positive rises and negative falls are separate.",
            "exclusions": "Absent, quality != ok, nonfinite, or negative kWh hours are excluded without filling; no gap-spanning ramps.",
        },
    }


def analyze_regions(
    frames_by_area: Mapping[str, pd.DataFrame], start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> dict[str, Any]:
    """Compare NO1–NO5 on the same exact complete-case UTC hours."""
    if set(frames_by_area) != set(AREAS):
        raise ValueError("regional comparison needs exactly NO1–NO5 household frames")
    index = _interval(start, end)
    raw = {}
    by_area = []
    for area in AREAS:
        values, coverage = _observations(frames_by_area[area], index)
        raw[area] = values
        by_area.append({"area": area, "observedHours": coverage["observedHours"],
                        "excludedHours": coverage["excludedHours"]})
    matched = np.logical_and.reduce([np.isfinite(raw[area]) for area in AREAS])
    aligned = np.column_stack([raw[area][matched] for area in AREAS])
    matched_index = index[matched]
    sums = aligned.sum(axis=1) if len(aligned) else np.empty(0)
    coincident = _peak(matched_index, sums)
    area_results = []
    for column, area in enumerate(AREAS):
        selected = aligned[:, column]
        selected_peak = _peak(matched_index, selected)
        coincident_position = int(np.argmax(sums)) if len(sums) else None
        area_results.append({
            "area": area,
            "meanKwh": float(np.mean(selected)) if len(selected) else None,
            "peak": selected_peak,
            "atCoincidentPeakKwh": float(selected[coincident_position]) if coincident_position is not None else None,
        })
    peak_sum = (sum(item["peak"]["valueKwh"] for item in area_results)
                if len(sums) else None)
    factor = (float(coincident["valueKwh"] / peak_sum)
              if coincident is not None and peak_sum is not None and peak_sum > 0 else None)
    correlations = []
    for first, second in combinations(range(len(AREAS)), 2):
        left, right = aligned[:, first], aligned[:, second]
        correlation = None
        if len(left) >= 2 and np.ptp(left) > 0 and np.ptp(right) > 0:
            correlation = float(np.clip(np.corrcoef(left, right)[0, 1], -1.0, 1.0))
        correlations.append({"areaA": AREAS[first], "areaB": AREAS[second],
                             "r": correlation, "hours": len(aligned)})
    return {
        "coverage": {"expectedHours": len(index), "matchedHours": int(matched.sum()),
                     "excludedHours": int((~matched).sum()), "byArea": by_area},
        "areas": area_results,
        "coincidentPeak": coincident,
        "sumIndividualPeaksKwh": peak_sum,
        "coincidenceFactor": factor,
        "correlations": correlations,
        "hourly": [
            {"time": _iso(time), **{area: float(raw[area][position]) if matched[position] else None
                                    for area in AREAS}}
            for position, time in enumerate(index)
        ],
        "calculation": {
            "cohort": "Only UTC hours with valid household kWh in all five areas enter every regional statistic; other hours are null in all five hourly columns.",
            "normalization": "For display, normalized demand = 100 × matched hourly kWh / that area's positive matched-hour mean kWh; undefined for zero mean.",
            "peak": "Each area's maximum and the maximum five-area sum use the same matched hours; earliest UTC hour wins an exact tie.",
            "coincidenceFactor": "Maximum simultaneous five-area sum / sum of five individual matched-hour maxima; undefined when the denominator is zero.",
            "correlation": "Raw Pearson correlation on the matched cohort; undefined with fewer than two hours or either constant series. Descriptive co-movement does not imply direct transfers.",
        },
    }
