"""Retrospective, calendar- and weather-adjusted demand anomaly candidates.

Selection, refitting, and residual calibration finish before the 2025 review
period. The saved rows are investigation candidates, not fault labels or live
alerts. Every timestamp remains on the original regular UTC grid.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import SplineTransformer

from app_core.analysis.demand_sensitivity import _calendar, _fit, _metrics, _timestamp
from app_core.analysis.forecast_evaluation import _norwegian_holidays


@dataclass(frozen=True)
class DemandAnomalyConfig:
    start: str = "2021-01-01"
    train_end: str = "2023-01-01"
    validation_end: str = "2024-01-01"
    calibration_end: str = "2025-01-01"
    end: str = "2026-01-01"
    minimum_coverage: float = 0.95
    minimum_train: int = 10_000
    minimum_validation: int = 4_000
    minimum_calibration: int = 8_000
    minimum_calibration_dates: int = 300
    minimum_test: int = 4_000
    ridge_alpha: float = 1.0
    minimum_improvement: float = 0.01
    minimum_absolute_improvement: float = 0.01
    tail_fraction: float = 0.01
    peer_limit: int = 20


def _nullable(value: Any) -> float | None:
    return float(value) if np.isfinite(value) else None


def _split(
    index: pd.DatetimeIndex, present: np.ndarray, area: str,
    name: str, left: pd.Timestamp, right: pd.Timestamp,
    minimum: int, minimum_coverage: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    period = (index >= left) & (index < right)
    mask = period & present
    expected, observed = int(period.sum()), int(mask.sum())
    if expected == 0 or observed < minimum or observed / expected < minimum_coverage:
        raise ValueError(f"{area}: insufficient {name} complete-case coverage ({observed}/{expected})")
    return mask, {
        "start": left.isoformat(), "endExclusive": right.isoformat(),
        "expectedHours": expected, "completeHours": observed,
        "missingHours": expected - observed, "completeFraction": observed / expected,
    }


def _selection(validation: dict[str, dict[str, Any]], config: DemandAnomalyConfig) -> tuple[str, int]:
    def improves(candidate: float, baseline: float) -> bool:
        return baseline - candidate >= max(config.minimum_improvement * baseline,
                                           config.minimum_absolute_improvement)

    knots = 6 if improves(validation["spline6"]["mae"], validation["spline4"]["mae"]) else 4
    spline = f"spline{knots}"
    selected = "calendar"
    if improves(validation["linear"]["mae"], validation["calendar"]["mae"]):
        selected = "linear"
    if (improves(validation[spline]["mae"], validation["calendar"]["mae"])
            and improves(validation[spline]["mae"], validation["linear"]["mae"])):
        selected = spline
    return selected, knots


def _score_rows(
    index: pd.DatetimeIndex, values: np.ndarray, raw_expected: np.ndarray,
    supported: np.ndarray, median: float, low: float, high: float,
) -> list[dict[str, Any]]:
    local = index.tz_convert("Europe/Oslo")
    rows: list[dict[str, Any]] = []
    for position, time in enumerate(index):
        demand, temperature = values[position]
        demand_ok, temperature_ok = bool(np.isfinite(demand)), bool(np.isfinite(temperature))
        if not demand_ok and not temperature_ok:
            status = "missing_both"
        elif not demand_ok:
            status = "missing_demand"
        elif not temperature_ok:
            status = "missing_temperature"
        elif not supported[position]:
            status = "unsupported_temperature"
        else:
            status = "ok"
        result: dict[str, Any] = {
            "time": time.isoformat(), "actual": _nullable(demand),
            "temperature": _nullable(temperature), "rawExpected": None,
            "expected": None, "lower": None, "upper": None,
            "residual": None, "score": None, "flagged": False, "status": status,
            "localDate": local[position].date().isoformat(),
            "localHour": int(local[position].hour),
        }
        if status == "ok":
            raw = float(raw_expected[position])
            expected = raw + median
            residual = float(demand - expected)
            width = high - median if residual >= 0 else median - low
            if width <= 0:
                raise ValueError("calibration tail width must be positive")
            score = float(abs(residual) / width)
            result.update({
                "rawExpected": raw, "expected": expected,
                "lower": raw + low, "upper": raw + high,
                "residual": residual, "score": score,
                "flagged": bool(score > 1),
            })
        rows.append(result)
    return rows


def _episodes(rows: list[dict[str, Any]], area: str) -> list[dict[str, Any]]:
    episodes = []
    active: list[dict[str, Any]] = []

    def emit() -> None:
        if not active:
            return
        peak = max(active, key=lambda row: (row["score"], -pd.Timestamp(row["time"]).value))
        direction = "high" if active[0]["residual"] > 0 else "low"
        end = pd.Timestamp(active[-1]["time"]) + pd.Timedelta(hours=1)
        episodes.append({
            "id": f"{area}-{active[0]['time']}-{direction}",
            "start": active[0]["time"], "endExclusive": end.isoformat(),
            "peakTime": peak["time"], "direction": direction,
            "hours": len(active), "peakScore": peak["score"],
            "peakActual": peak["actual"], "peakExpected": peak["expected"],
            "peakTemperature": peak["temperature"],
            "peakResidual": peak["residual"], "peakLocalDate": peak["localDate"],
        })
        active.clear()

    for row in rows:
        if not row["flagged"]:
            emit()
            continue
        if active:
            contiguous = pd.Timestamp(row["time"]) - pd.Timestamp(active[-1]["time"]) == pd.Timedelta(hours=1)
            same_sign = (row["residual"] > 0) == (active[-1]["residual"] > 0)
            if not contiguous or not same_sign:
                emit()
        active.append(row)
    emit()
    episodes.sort(key=lambda item: (-item["peakScore"], item["peakTime"]))
    return episodes


def _season_distance(left: pd.Timestamp, right: pd.Timestamp) -> int:
    # Day-of-year circular distance, using a common leap-year calendar.
    def ordinal(value: pd.Timestamp) -> int:
        day = value.date()
        anchor = pd.Timestamp(year=2000, month=day.month, day=day.day)
        return int(anchor.dayofyear)
    distance = abs(ordinal(left) - ordinal(right))
    return min(distance, 366 - distance)


def _local_day_hours(date: str) -> int:
    begin = pd.Timestamp(date).tz_localize("Europe/Oslo")
    return len(pd.date_range(begin, begin + pd.DateOffset(days=1), freq="h", inclusive="left"))


def _peer_contexts(
    candidates: list[dict[str, Any]], index: pd.DatetimeIndex, values: np.ndarray,
    calibration_end: pd.Timestamp, limit: int,
) -> None:
    local = index.tz_convert("Europe/Oslo")
    holidays = set().union(*(_norwegian_holidays(year) for year in range(local.year.min(), local.year.max() + 1)))
    days: dict[str, list[int]] = {}
    for position, time in enumerate(local):
        days.setdefault(time.date().isoformat(), []).append(position)
    development = []
    excluded_dst_days = 0
    last_peer_date = calibration_end.tz_convert("Europe/Oslo").date()
    for date, positions in days.items():
        if pd.Timestamp(date).date() >= last_peer_date:
            continue
        if len(positions) != 24:
            if _local_day_hours(date) != 24:
                excluded_dst_days += 1
            continue
        if not np.isfinite(values[positions]).all():
            continue
        day = pd.Timestamp(date)
        development.append((date, day, float(np.mean(values[positions, 1])), positions))
    for candidate in candidates[:limit]:
        date = candidate["peakLocalDate"]
        positions = days.get(date, [])
        context: dict[str, Any] = {"targetDate": date, "targetHours": len(positions),
                                   "targetRows": [], "status": "available", "reason": None,
                                   "excludedDstDays": excluded_dst_days, "days": []}
        for position in positions:
            context["targetRows"].append({
                "time": index[position].isoformat(), "localHour": int(local[position].hour),
                "actual": _nullable(values[position, 0]),
                "temperature": _nullable(values[position, 1]),
            })
        if len(positions) != 24:
            context["status"] = "unavailable"
            context["reason"] = (
                "target Oslo date has 23 or 25 hours due to daylight saving time"
                if _local_day_hours(date) != 24 else
                "target Oslo date is incomplete at an evaluation boundary"
            )
        elif not np.isfinite(values[positions, 1]).all():
            context["status"] = "unavailable"
            context["reason"] = "target date has missing temperature"
        else:
            target = pd.Timestamp(date)
            mean_temperature = float(np.mean(values[positions, 1]))
            target_holiday = target.date() in holidays
            matches = []
            for peer_date, peer_day, peer_temp, peer_positions in development:
                if peer_day.dayofweek != target.dayofweek or (peer_day.date() in holidays) != target_holiday:
                    continue
                seasonal_distance = _season_distance(peer_day, target)
                temperature_difference = abs(peer_temp - mean_temperature)
                if seasonal_distance <= 45 and temperature_difference <= 3:
                    matches.append((temperature_difference, seasonal_distance,
                                    -peer_day.value, peer_date, peer_positions))
            matches.sort()
            for difference, seasonal_distance, _, peer_date, peer_positions in matches[:3]:
                context["days"].append({
                    "date": peer_date, "temperatureDifference": float(difference),
                    "seasonDistance": seasonal_distance,
                    "rows": [{"time": index[position].isoformat(),
                              "localHour": int(local[position].hour),
                              "actual": float(values[position, 0]),
                              "temperature": float(values[position, 1])}
                             for position in peer_positions],
                })
            if not context["days"]:
                context["status"] = "unavailable"
                context["reason"] = "no complete pre-evaluation peer day meets weekday, holiday, season and temperature rules"
        candidate["peers"] = context


def _diagnostics(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    seasons = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
               6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
    groups = {"season": {}, "dayType": {}}
    years = {pd.Timestamp(row["localDate"]).year for row in rows}
    holidays = set().union(*(_norwegian_holidays(year) for year in years))
    for row in rows:
        local_date = pd.Timestamp(row["localDate"])
        labels = {"season": seasons[local_date.month],
                  "dayType": "holiday" if local_date.date() in holidays else
                  "weekend" if local_date.dayofweek >= 5 else "weekday"}
        for dimension, label in labels.items():
            entry = groups[dimension].setdefault(label, {"hours": 0, "scoredHours": 0, "flaggedHours": 0})
            entry["hours"] += 1
            entry["scoredHours"] += int(row["status"] == "ok")
            entry["flaggedHours"] += int(row["flagged"])
    return {dimension: [{dimension: key, **value,
                         "flagRate": value["flaggedHours"] / value["scoredHours"]
                         if value["scoredHours"] else None}
                        for key, value in sorted(entries.items())]
            for dimension, entries in groups.items()}


def analyze_area(
    frame: pd.DataFrame, area: str, config: DemandAnomalyConfig | None = None,
) -> dict[str, Any]:
    """Fit a frozen pre-2025 baseline and score retrospective 2025 candidates."""
    config = config or DemandAnomalyConfig()
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("frame must have a timezone-aware UTC DatetimeIndex")
    if str(frame.index.tz) != "UTC" or frame.index.has_duplicates:
        raise ValueError("frame index must be unique and UTC")
    if any(frame.index != frame.index.floor("h")):
        raise ValueError("frame index must contain exact UTC hourly timestamps")
    if not {"demand", "temperature"}.issubset(frame.columns):
        raise ValueError("frame needs demand and temperature columns")
    start, train_end, validation_end, calibration_end, end = map(_timestamp, (
        config.start, config.train_end, config.validation_end, config.calibration_end, config.end,
    ))
    if not start < train_end < validation_end < calibration_end < end:
        raise ValueError("invalid temporal boundaries")
    if not 0 < config.minimum_coverage <= 1 or not 0 < config.tail_fraction < 0.5:
        raise ValueError("invalid coverage or tail fraction")
    if config.ridge_alpha <= 0 or config.peer_limit < 0:
        raise ValueError("ridge_alpha must be positive and peer_limit nonnegative")
    index = pd.date_range(start, end, freq="h", inclusive="left", tz="UTC")
    data = frame[["demand", "temperature"]].reindex(index).astype(float)
    values = data.to_numpy()
    demand, temperature = values[:, 0], values[:, 1]
    present = np.isfinite(values).all(axis=1)
    stages = (
        ("train", start, train_end, config.minimum_train),
        ("validation", train_end, validation_end, config.minimum_validation),
        ("calibration", validation_end, calibration_end, config.minimum_calibration),
        ("test", calibration_end, end, config.minimum_test),
    )
    masks: dict[str, np.ndarray] = {}
    splits: dict[str, dict[str, Any]] = {}
    for name, left, right, minimum in stages:
        masks[name], splits[name] = _split(index, present, area, name, left, right,
                                           minimum, config.minimum_coverage)

    calendar = _calendar(index, start, harmonics=2)
    train = masks["train"]
    development = masks["train"] | masks["validation"]
    fit_low, fit_high = float(np.min(temperature[development])), float(np.max(temperature[development]))
    if fit_high <= fit_low:
        raise ValueError(f"{area}: temperature has no usable development support")
    temperature_mean = float(np.mean(temperature[train]))
    temperature_scale = max(float(np.std(temperature[train])), 1e-8)
    finite_temp = np.isfinite(temperature)
    linear = np.zeros(len(index))
    linear[finite_temp] = (temperature[finite_temp] - temperature_mean) / temperature_scale
    designs = {"calendar": calendar, "linear": np.column_stack([calendar, linear])}
    transformers: dict[int, SplineTransformer] = {}
    for knot_count in (4, 6):
        transformer = SplineTransformer(n_knots=knot_count, knots="quantile", degree=3,
                                        include_bias=False, extrapolation="constant")
        transformer.fit(temperature[train, None])
        basis = np.zeros((len(index), transformer.n_features_out_))
        basis[finite_temp] = transformer.transform(temperature[finite_temp, None])
        designs[f"spline{knot_count}"] = np.column_stack([calendar, basis])
        transformers[knot_count] = transformer
    validation: dict[str, dict[str, Any]] = {}
    for model, design in designs.items():
        coefficient, _ = _fit(design[train], demand[train], config.ridge_alpha)
        validation[model] = _metrics(demand[masks["validation"]],
                                      design[masks["validation"]] @ coefficient)
    selected, selected_knots = _selection(validation, config)
    coefficient, _ = _fit(designs[selected][development], demand[development], config.ridge_alpha)
    raw = np.full(len(index), np.nan)
    supported = finite_temp & (temperature >= fit_low) & (temperature <= fit_high)
    predictable = supported & present
    raw[predictable] = designs[selected][predictable] @ coefficient
    calibration_mask = masks["calibration"] & supported
    calibration_dates = int(index[calibration_mask].normalize().nunique())
    if int(calibration_mask.sum()) < config.minimum_calibration or calibration_dates < config.minimum_calibration_dates:
        raise ValueError(f"{area}: insufficient supported calibration hours or UTC dates")
    calibration_residual = demand[calibration_mask] - raw[calibration_mask]
    lower, median, upper = (float(value) for value in np.quantile(
        calibration_residual, [config.tail_fraction / 2, 0.5, 1 - config.tail_fraction / 2]
    ))
    if median - lower <= 0 or upper - median <= 0:
        raise ValueError(f"{area}: degenerate calibration tail width; anomaly scoring unavailable")
    cal_rows = _score_rows(index[(index >= validation_end) & (index < calibration_end)],
                           values[(index >= validation_end) & (index < calibration_end)],
                           raw[(index >= validation_end) & (index < calibration_end)],
                           supported[(index >= validation_end) & (index < calibration_end)],
                           median, lower, upper)
    test_period = (index >= calibration_end) & (index < end)
    rows = _score_rows(index[test_period], values[test_period], raw[test_period],
                       supported[test_period], median, lower, upper)
    candidates = _episodes(rows, area)
    _peer_contexts(candidates, index, values, calibration_end, config.peer_limit)
    calibration_scored = sum(row["status"] == "ok" for row in cal_rows)
    calibration_flagged = sum(row["flagged"] for row in cal_rows)
    coverage = {}
    for name, stage_rows in (("calibration", cal_rows), ("test", rows)):
        status_count = {status: sum(row["status"] == status for row in stage_rows)
                        for status in ("ok", "missing_demand", "missing_temperature",
                                       "missing_both", "unsupported_temperature")}
        coverage[name] = {"expectedHours": len(stage_rows), "statusCounts": status_count,
                          "scoredHours": status_count["ok"],
                          "missingHours": sum(status_count[key] for key in (
                              "missing_demand", "missing_temperature", "missing_both")),
                          "unsupportedHours": status_count["unsupported_temperature"]}
    # Fit stages are complete-case only; test/calibration preserve explicit row status.
    for name in ("train", "validation"):
        coverage[name] = {"expectedHours": splits[name]["expectedHours"],
                          "completeHours": splits[name]["completeHours"],
                          "scoredHours": splits[name]["completeHours"],
                          "missingHours": splits[name]["missingHours"],
                          "unsupportedHours": 0}
    scored = coverage["test"]["scoredHours"]
    flagged = sum(row["flagged"] for row in rows)
    calendar_columns = (["intercept"] + [f"oslo_hour_{hour}" for hour in range(1, 24)]
                        + [f"oslo_weekday_{day}" for day in range(1, 7)]
                        + ["norwegian_public_holiday", "annual_sin_1", "annual_cos_1",
                           "annual_sin_2", "annual_cos_2", "years_since_start"])
    selected_columns = calendar_columns.copy()
    if selected == "linear":
        selected_columns.append("temperature_standardized_train")
    elif selected.startswith("spline"):
        selected_columns.extend(f"temperature_spline_basis_{number}"
                                for number in range(transformers[selected_knots].n_features_out_))
    if len(selected_columns) != len(coefficient):
        raise AssertionError("feature names do not match frozen design columns")
    return {
        "schemaVersion": 1, "area": area, "status": "ok", "selectedModel": selected,
        "selection": {"models": [{"model": name, "validation": validation[name]}
                                 for name in ("calendar", "linear", "spline4", "spline6")],
                      "selectedSplineKnots": selected_knots,
                      "rule": "Validation MAE; complexity needs at least 1% and 0.01 kWh improvement."},
        "splits": splits,
        "calibration": {
            "medianCorrection": median, "lowerResidual": lower, "upperResidual": upper,
            "lowerWidth": median - lower, "upperWidth": upper - median,
            "observations": int(calibration_mask.sum()), "distinctDates": calibration_dates,
            "tailFraction": config.tail_fraction,
            "coverage": calibration_scored / len(cal_rows),
            "flagFraction": calibration_flagged / calibration_scored,
            "groupSupport": _diagnostics(cal_rows),
        },
        "coverage": coverage,
        "summary": {"expectedHours": len(rows), "scoredHours": scored,
                    "flaggedHours": flagged, "flagRate": flagged / scored if scored else None,
                    "episodes": len(candidates)},
        "diagnostics": _diagnostics(rows),
        "rows": rows, "calibrationRows": cal_rows, "candidates": candidates,
        "metadata": {
            "config": asdict(config), "unit": "kWh", "temperatureUnit": "°C",
            "interpretation": "Retrospective candidate deviations, not confirmed faults or live alerts; temperature adjustment is associational, not causal.",
            "calendarDesign": "Intercept, Oslo hour 1–23 and weekday 1–6 dummies, public holiday, annual Fourier harmonics 1–2, years-since-start trend.",
            "preprocessing": {
                "temperatureMeanTrain": temperature_mean,
                "temperatureScaleTrain": temperature_scale,
                "temperatureMinDevelopment": fit_low,
                "temperatureMaxDevelopment": fit_high,
                "splineKnotVectorsTrainOnly": {
                    str(knots): [float(value) for value in transformer.bsplines_[0].t]
                    for knots, transformer in transformers.items()
                },
                "completeCasesOnly": True,
            },
            "coefficients": [float(value) for value in coefficient],
            "featureColumns": selected_columns,
            "ridgeAlpha": config.ridge_alpha,
            "calibration": "Fixed empirical signed residual quantiles on 2024; no test labels or refits used in threshold selection.",
            "peerRule": "Complete 24-hour pre-evaluation Oslo dates; same weekday/holiday, circular season distance at most 45 days, daily mean temperature within 3°C; closest three by temperature, season and recency.",
        },
    }


__all__ = ["DemandAnomalyConfig", "analyze_area"]
