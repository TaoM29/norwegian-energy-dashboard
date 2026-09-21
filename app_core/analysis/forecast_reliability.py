"""Descriptive reliability analysis of immutable matched forecast predictions.

The resampling unit is a scheduled UTC issue date. Each moving block retains
every area, model and hourly target on its dates; absent scheduled dates remain
empty slots rather than being compressed into adjacent observed dates.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd


_MEASURES = (
    "maeDeltaVsBaseline", "rmseDeltaVsBaseline", "intervalCoverage", "meanIntervalWidth",
    "pinballLower", "pinballMedian", "pinballUpper",
)


def _finite(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def _pearson_pairs(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    count = len(left)
    if count < 3:
        return {"pairs": count, "correlation": None, "reason": "fewer than three exact-lag pairs"}
    if np.std(left) == 0 or np.std(right) == 0:
        return {"pairs": count, "correlation": None, "reason": "constant residuals"}
    return {"pairs": count, "correlation": _finite(np.corrcoef(left, right)[0, 1]), "reason": None}


def _residual_dependence(part: pd.DataFrame) -> dict[str, Any]:
    work = part[["area", "origin", "targetTime", "residual"]].copy()
    work["targetTime"] = pd.to_datetime(work["targetTime"], utc=True)
    work["origin"] = pd.to_datetime(work["origin"], utc=True)
    work = work.sort_values(["area", "origin", "targetTime"])
    within_left: list[float] = []
    within_right: list[float] = []
    for _, window in work.groupby(["area", "origin"], sort=False):
        preceding = window.shift(1)
        consecutive = (window["targetTime"] - preceding["targetTime"]) == pd.Timedelta(hours=1)
        within_left.extend(preceding.loc[consecutive, "residual"].astype(float))
        within_right.extend(window.loc[consecutive, "residual"].astype(float))
    result = {"withinWindowLag1Hour": _pearson_pairs(np.asarray(within_left), np.asarray(within_right))}

    # Exact target timestamps, not adjacency in a compressed row sequence.
    indexed = work.set_index(["area", "targetTime"])["residual"]
    if indexed.index.has_duplicates:
        raise ValueError("duplicate area/targetTime rows prevent exact-lag residual diagnostics")
    for hours in (24, 168):
        shifted = work[["area", "targetTime", "residual"]].copy()
        shifted["targetTime"] += pd.Timedelta(hours=hours)
        paired = work.merge(shifted, on=["area", "targetTime"], suffixes=("", "Prior"))
        result[f"exactTargetLag{hours}Hours"] = _pearson_pairs(
            paired["residualPrior"].to_numpy(dtype=float), paired["residual"].to_numpy(dtype=float)
        )

    means = work.groupby(["area", "origin"], as_index=False)["residual"].mean()
    for days in (8, 16):
        shifted = means.copy()
        shifted["origin"] += pd.Timedelta(days=days)
        paired = means.merge(shifted, on=["area", "origin"], suffixes=("", "Prior"))
        result[f"originMeanLag{days}Days"] = _pearson_pairs(
            paired["residualPrior"].to_numpy(dtype=float), paired["residual"].to_numpy(dtype=float)
        )
    return result


def _stats(part: pd.DataFrame) -> dict[str, float]:
    error = part["residual"].to_numpy(dtype=float)
    baseline_error = part["actual"].to_numpy(dtype=float) - part["baseline"].to_numpy(dtype=float)
    alpha = float(part["lowerQuantile"].iloc[0])
    lower_error = part["actual"].to_numpy(dtype=float) - part["lower"].to_numpy(dtype=float)
    median_error = part["actual"].to_numpy(dtype=float) - part["median"].to_numpy(dtype=float)
    upper_error = part["actual"].to_numpy(dtype=float) - part["upper"].to_numpy(dtype=float)
    pinball = lambda error, quantile: float(np.mean(np.maximum(quantile * error, (quantile - 1) * error)))
    return {
        "maeDeltaVsBaseline": float(np.mean(np.abs(error)) - np.mean(np.abs(baseline_error))),
        "rmseDeltaVsBaseline": float(np.sqrt(np.mean(error**2)) - np.sqrt(np.mean(baseline_error**2))),
        "bias": float(np.mean(error)),
        "intervalCoverage": float(np.mean(part["covered"].to_numpy(dtype=float))),
        "meanIntervalWidth": float(np.mean(part["width"].to_numpy(dtype=float))),
        "pinballLower": pinball(lower_error, alpha),
        "pinballMedian": pinball(median_error, 0.5),
        "pinballUpper": pinball(upper_error, 1 - alpha),
    }


def _date_sums(part: pd.DataFrame, schedule: list[pd.Timestamp]) -> np.ndarray:
    """One row per scheduled date, including zero rows for wholly missing dates."""
    work = part.copy()
    work["date"] = pd.to_datetime(work["origin"], utc=True).dt.normalize()
    work["absoluteError"] = work["residual"].abs()
    work["squaredError"] = work["residual"] ** 2
    base_error = work["actual"] - work["baseline"]
    work["baselineAbsoluteError"] = base_error.abs()
    work["baselineSquaredError"] = base_error**2
    alpha = float(work["lowerQuantile"].iloc[0])
    for name, forecast, quantile in (
        ("pinballLower", "lower", alpha), ("pinballMedian", "median", 0.5),
        ("pinballUpper", "upper", 1 - alpha),
    ):
        error = work["actual"] - work[forecast]
        work[name] = np.maximum(quantile * error, (quantile - 1) * error)
    grouped = work.groupby("date").agg(
        n=("residual", "size"), abs=("absoluteError", "sum"), sq=("squaredError", "sum"),
        base_abs=("baselineAbsoluteError", "sum"), base_sq=("baselineSquaredError", "sum"),
        covered=("covered", "sum"), width=("width", "sum"),
        pinball_lower=("pinballLower", "sum"), pinball_median=("pinballMedian", "sum"),
        pinball_upper=("pinballUpper", "sum"),
    ).reindex(schedule, fill_value=0)
    return grouped[["n", "abs", "sq", "base_abs", "base_sq", "covered", "width",
                    "pinball_lower", "pinball_median", "pinball_upper"]].to_numpy(dtype=float)


def _bootstrap_stats(sums: np.ndarray) -> np.ndarray:
    n = sums[:, 0]
    return np.column_stack((
        sums[:, 1] / n - sums[:, 3] / n,
        np.sqrt(sums[:, 2] / n) - np.sqrt(sums[:, 4] / n),
        sums[:, 5] / n,
        sums[:, 6] / n,
        sums[:, 7] / n,
        sums[:, 8] / n,
        sums[:, 9] / n,
    ))


def _moving_block_indices(rng: np.random.Generator, length: int, block: int, resamples: int) -> np.ndarray:
    blocks_per_sample = int(np.ceil(length / block))
    starts = rng.integers(0, length - block + 1, size=(resamples, blocks_per_sample))
    return (starts[:, :, None] + np.arange(block)).reshape(resamples, -1)[:, :length]


def build_reliability_report(
    payload: Mapping[str, Any], *, block_lengths: Sequence[int] = (2, 4, 8),
    resamples: int = 2000, seed: int = 20260921,
) -> dict[str, Any]:
    """Recompute paired reliability from saved rows; no fitting or artifact writes.

    Intervals describe variability under a stationary moving-block approximation,
    not operational prediction coverage or a proof of independent observations.
    """
    if not 100 <= resamples <= 100_000:
        raise ValueError("resamples must be from 100 to 100000")
    lengths = tuple(int(value) for value in block_lengths)
    if not lengths or any(value < 1 for value in lengths) or len(set(lengths)) != len(lengths):
        raise ValueError("block_lengths must be distinct positive integers")
    config = payload.get("config")
    if not isinstance(config, Mapping) or not config.get("holdout_origins"):
        raise ValueError("saved configuration with holdout origins is required")
    schedule = sorted({pd.Timestamp(value).tz_convert("UTC").normalize() for value in config["holdout_origins"]})
    if len(schedule) != len(config["holdout_origins"]):
        raise ValueError("holdout origins must have distinct UTC dates")
    cadence = [int((right - left) / pd.Timedelta(days=1)) for left, right in zip(schedule, schedule[1:])]
    regular_cadence = bool(cadence) and len(set(cadence)) == 1 and cadence[0] > 0
    requested_models = list(config.get("models") or [])
    rows = payload.get("predictions") or []
    if not rows:
        raise ValueError("saved matched prediction rows are required")
    frame = pd.DataFrame(rows).copy()
    needed = {"area", "origin", "targetTime", "horizon", "model", "actual", "prediction", "baseline",
              "lower", "median", "upper", "lowerQuantile", "upperQuantile"}
    if not needed.issubset(frame):
        raise ValueError(f"saved predictions lack columns: {sorted(needed - set(frame))}")
    if frame[list(needed - {"area", "origin", "targetTime", "model"})].isna().any().any():
        raise ValueError("saved predictions contain null required numeric values")
    if not np.isfinite(frame[list(needed - {"area", "origin", "targetTime", "model"})].to_numpy(dtype=float)).all():
        raise ValueError("saved predictions contain non-finite required numeric values")
    frame["origin"] = pd.to_datetime(frame["origin"], utc=True)
    frame["targetTime"] = pd.to_datetime(frame["targetTime"], utc=True)
    frame["date"] = frame["origin"].dt.normalize()
    areas = list(config.get("areas") or sorted(frame["area"].unique()))
    if not set(frame["area"]).issubset(set(areas)):
        raise ValueError("prediction rows contain an area outside the requested cohort")
    if not set(frame["date"]).issubset(set(schedule)):
        raise ValueError("prediction origins include dates outside scheduled holdout")
    key = ["area", "origin", "horizon"]
    if frame.duplicated([*key, "model"]).any():
        raise ValueError("saved predictions contain duplicate model/target rows")
    if requested_models and set(frame["model"]) != set(requested_models):
        raise ValueError("saved models differ from requested matched cohort")
    if frame.groupby(key, sort=False)["model"].nunique().ne(frame["model"].nunique()).any():
        raise ValueError("saved model rows are not paired on every target")
    if frame.groupby(key, sort=False)["targetTime"].nunique().gt(1).any():
        raise ValueError("saved model rows disagree on targetTime")
    for column in ("actual", "baseline"):
        if frame.groupby(key, sort=False)[column].nunique().gt(1).any():
            raise ValueError(f"saved paired rows disagree on {column}")
    horizon_hours = int(config.get("horizon_hours", 0))
    if horizon_hours < 1:
        raise ValueError("saved configuration requires horizon_hours")
    if not frame["horizon"].between(1, horizon_hours).all() or not (frame["horizon"] % 1 == 0).all():
        raise ValueError("saved rows contain an out-of-range or noninteger horizon")
    expected_time = frame["origin"] + pd.to_timedelta(frame["horizon"].astype(int) - 1, unit="h")
    if not frame["targetTime"].equals(expected_time.rename("targetTime")):
        raise ValueError("saved targetTime must equal origin plus horizon minus one hours")
    per_origin = frame.groupby(["area", "origin", "model"], sort=False)["horizon"].nunique()
    if per_origin.ne(horizon_hours).any():
        raise ValueError("saved area-origin rows do not contain the full requested horizon")
    baseline_rows = frame.loc[frame["model"] == "seasonal_naive", [*key, "prediction"]]
    if baseline_rows.empty:
        raise ValueError("seasonal_naive rows are required for paired baseline verification")
    paired = frame.merge(baseline_rows.rename(columns={"prediction": "seasonalPrediction"}), on=key, how="left")
    if paired["seasonalPrediction"].isna().any() or not np.allclose(
        paired["baseline"], paired["seasonalPrediction"], rtol=0, atol=1e-9
    ):
        raise ValueError("saved baseline values differ from seasonal_naive predictions")
    if frame.groupby("model", sort=False)["lowerQuantile"].nunique().gt(1).any() or frame.groupby(
        "model", sort=False
    )["upperQuantile"].nunique().gt(1).any():
        raise ValueError("saved interval quantiles vary within a model")
    frame["residual"] = frame["actual"] - frame["prediction"]
    frame["covered"] = (frame["actual"] >= frame["lower"]) & (frame["actual"] <= frame["upper"])
    frame["width"] = frame["upper"] - frame["lower"]
    if (frame["width"] < 0).any():
        raise ValueError("saved prediction intervals have negative width")
    observed_dates = sorted(frame["date"].unique())
    missing_dates = [date for date in schedule if date not in set(observed_dates)]
    area_origins = frame[["area", "origin"]].drop_duplicates()
    support = {
        "scheduledDates": len(schedule), "observedDates": len(observed_dates),
        "missingDates": [date.isoformat() for date in missing_dates],
        "scheduledAreaOrigins": len(schedule) * len(areas), "matchedAreaOrigins": len(area_origins),
        "excludedAreaOrigins": len(schedule) * len(areas) - len(area_origins),
        "hourlyRowsPerModel": {str(model): int(len(part)) for model, part in frame.groupby("model")},
    }
    methods = {
        "pairedDifferenceSign": "model minus seasonal baseline; negative error difference favors model",
        "biasSign": "actual minus prediction; positive bias means underprediction",
        "intervalCoverage": "observed fraction of saved actuals inside inclusive lower/upper bounds",
        "uncertainty": "95% percentile intervals from noncircular moving blocks of scheduled UTC issue dates; all areas, horizons and models share the same sampled dates; missing scheduled dates remain empty slots; hourly rows weight aggregate scores",
        "cadenceDays": cadence[0] if regular_cadence else None,
        "resamples": int(resamples), "seed": int(seed), "blockLengths": list(lengths),
        "supportRule": "intervals withheld when fewer than three effective observed blocks or fewer than 95% resamples contain observations; this is a reporting threshold, not a validity guarantee",
    }
    rng = np.random.default_rng(seed)
    indices = {length: _moving_block_indices(rng, len(schedule), length, resamples)
               for length in lengths if length <= len(schedule)}
    models = []
    for model, part in frame.groupby("model", sort=True):
        by_origin = []
        for (area, origin), origin_part in part.groupby(["area", "origin"], sort=True):
            by_origin.append({"area": str(area), "origin": origin.isoformat(),
                              "observations": int(len(origin_part)), **_stats(origin_part)})
        sums = _date_sums(part, schedule)
        uncertainty = []
        for length in lengths:
            effective = float(len(observed_dates) / length)
            entry: dict[str, Any] = {"blockLengthDates": length, "effectiveObservedBlocks": effective,
                                     "intervals": None, "reason": None, "validResamples": 0}
            if not regular_cadence:
                entry["reason"] = "scheduled origins are not on a regular date cadence"
            elif length > len(schedule):
                entry["reason"] = "block exceeds scheduled date grid"
            elif effective < 3:
                entry["reason"] = "fewer than three effective observed blocks"
            else:
                draws = sums[indices[length]].sum(axis=1)
                valid = draws[:, 0] > 0
                entry["validResamples"] = int(valid.sum())
                if valid.mean() < 0.95:
                    entry["reason"] = "fewer than 95% of resamples contain observations"
                else:
                    sampled = _bootstrap_stats(draws[valid])
                    entry["intervals"] = {
                        name: {"lower": float(np.quantile(sampled[:, col], 0.025)),
                               "upper": float(np.quantile(sampled[:, col], 0.975))}
                        for col, name in enumerate(_MEASURES)
                    }
            uncertainty.append(entry)
        dependence = _residual_dependence(part)
        dependence["byArea"] = [
            {"area": str(area), **_residual_dependence(area_part)}
            for area, area_part in part.groupby("area", sort=True)
        ]
        models.append({"model": str(model), "overall": _stats(part), "byOrigin": by_origin,
                       "residualDependence": dependence,
                       "uncertainty": {"byBlockLength": uncertainty}})
    return {"schemaVersion": 1, "method": methods, "support": support, "models": models}


__all__ = ["build_reliability_report"]
