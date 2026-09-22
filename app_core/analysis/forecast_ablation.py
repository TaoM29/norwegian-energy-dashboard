"""Pure combination and paired analysis of the frozen ridge feature ablation.

The input runs are immutable evaluation payloads. A shared area-origin cohort is
formed before any scores are computed; excluded successful predictions remain in
the output audit record. Uncertainty resamples scheduled issue dates together
for every area, horizon and variant, including dates with no matched rows.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

from app_core.analysis.forecast_evaluation import _metrics
from app_core.analysis.forecast_reliability import (
    _date_sums, _moving_block_indices, build_reliability_report,
)


FEATURE_SETS = ("calendar", "calendar_demand", "calendar_demand_weather")
SCORE_NAMES = (
    "mae", "rmse", "intervalCoverage", "meanIntervalWidth",
    "pinballLower", "pinballMedian", "pinballUpper",
)


def _origin_key(row: Mapping[str, Any]) -> tuple[str, pd.Timestamp]:
    return str(row["area"]), pd.Timestamp(row["origin"]).tz_convert("UTC")


def _target_key(row: Mapping[str, Any]) -> tuple[str, pd.Timestamp, int]:
    area, origin = _origin_key(row)
    return area, origin, int(row["horizon"])


def _scores(row: Mapping[str, Any]) -> dict[str, float]:
    return {name: float(row[name]) for name in ("mae", "rmse", "bias", *SCORE_NAMES[2:])}


def _source_successes(
    run: Mapping[str, Any], source_keys: set[tuple[str, pd.Timestamp]],
    area: str, model: str,
) -> int:
    for area_row in (run.get("coverage") or {}).get("areas") or []:
        if area_row.get("area") == area:
            count = (area_row.get("successfulOriginsByModel") or {}).get(model)
            if count is not None:
                return int(count)
    return sum(row_area == area for row_area, _ in source_keys)


def _sample_scores(sums: np.ndarray) -> np.ndarray:
    n = sums[:, 0]
    return np.column_stack((
        sums[:, 1] / n, np.sqrt(sums[:, 2] / n), sums[:, 5] / n,
        sums[:, 6] / n, sums[:, 7] / n, sums[:, 8] / n, sums[:, 9] / n,
    ))


def _shared_metadata(runs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    sources = [run.get("metadata") or {} for run in runs.values()]
    first = sources[0]
    common = {key: deepcopy(value) for key, value in first.items()
              if key != "features" and all(source.get(key) == value for source in sources[1:])}
    assumptions = [source.get("assumptions") or {} for source in sources]
    if assumptions and all(isinstance(value, Mapping) for value in assumptions):
        common["assumptions"] = {key: deepcopy(value) for key, value in assumptions[0].items()
                                 if all(other.get(key) == value for other in assumptions[1:])}
    common["features"] = {"perVariant": {
        feature_set: deepcopy(runs[feature_set]["metadata"]["features"])
        for feature_set in FEATURE_SETS
    }}
    common["modelEvaluation"] = (
        "All ridge variants and the seasonal reference use the same complete area-origin cohort. "
        "Variant-specific configuration, calibration and exclusions are saved in modelEvaluation."
    )
    return common


def _uncertainty(
    frames: Mapping[str, pd.DataFrame], schedule: list[pd.Timestamp],
    contrasts: list[Mapping[str, Any]], uncertainty: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    lengths = tuple(int(value) for value in uncertainty.get("blockLengths", (2, 4, 8)))
    resamples = int(uncertainty.get("resamples", 2000))
    seed = int(uncertainty.get("seed", 20260921))
    if not lengths or any(value < 1 for value in lengths) or len(set(lengths)) != len(lengths):
        raise ValueError("blockLengths must be distinct positive integers")
    if not 100 <= resamples <= 100_000:
        raise ValueError("resamples must be from 100 to 100000")
    cadence = [int((right - left) / pd.Timedelta(days=1)) for left, right in zip(schedule, schedule[1:])]
    regular = bool(cadence) and len(set(cadence)) == 1 and cadence[0] > 0
    observed = len(set(pd.to_datetime(next(iter(frames.values()))["origin"], utc=True).dt.normalize()))
    date_sums = {model: _date_sums(frame, schedule) for model, frame in frames.items()}
    rng = np.random.default_rng(seed)
    indices = {length: _moving_block_indices(rng, len(schedule), length, resamples)
               for length in lengths if length <= len(schedule)}
    result: dict[str, list[dict[str, Any]]] = {}
    for contrast in contrasts:
        entries = []
        for length in lengths:
            effective = float(observed / length)
            entry: dict[str, Any] = {
                "blockLengthDates": length, "effectiveObservedBlocks": effective,
                "intervals": None, "reason": None, "validResamples": 0,
            }
            if not regular:
                entry["reason"] = "scheduled origins are not on a regular date cadence"
            elif length > len(schedule):
                entry["reason"] = "block exceeds scheduled date grid"
            elif effective < 3:
                entry["reason"] = "fewer than three effective observed blocks"
            else:
                sampled = indices[length]
                before = date_sums[contrast["fromModel"]][sampled].sum(axis=1)
                after = date_sums[contrast["toModel"]][sampled].sum(axis=1)
                valid = (before[:, 0] > 0) & (after[:, 0] > 0)
                entry["validResamples"] = int(valid.sum())
                if valid.mean() < 0.95:
                    entry["reason"] = "fewer than 95% of resamples contain observations"
                else:
                    # Differences are computed within each paired draw, not from
                    # independently estimated confidence interval endpoints.
                    differences = _sample_scores(after[valid]) - _sample_scores(before[valid])
                    entry["intervals"] = {
                        name: {"lower": float(np.quantile(differences[:, index], 0.025)),
                               "upper": float(np.quantile(differences[:, index], 0.975))}
                        for index, name in enumerate(SCORE_NAMES)
                    }
            entries.append(entry)
        result[str(contrast["id"])] = entries
    return result


def combine_ablation_runs(
    runs: Mapping[str, Mapping[str, Any]], protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Combine three saved evaluation runs without refitting or modifying them."""
    if set(runs) != set(FEATURE_SETS):
        raise ValueError(f"runs must contain exactly {', '.join(FEATURE_SETS)}")
    protocol_variants = protocol.get("variants") or []
    if [item.get("featureSet") for item in protocol_variants] != list(FEATURE_SETS):
        raise ValueError("protocol variants must follow the three feature sets in order")
    model_for = {item["featureSet"]: item["model"] for item in protocol_variants}
    if any(model_for[name] != f"ridge_{name}" for name in FEATURE_SETS):
        raise ValueError("protocol ridge variant model names differ from the frozen ablation")
    contrasts = list(protocol.get("contrasts") or [])
    expected = [(model_for["calendar"], model_for["calendar_demand"]),
                (model_for["calendar_demand"], model_for["calendar_demand_weather"])]
    if [(item.get("fromModel"), item.get("toModel")) for item in contrasts] != expected:
        raise ValueError("protocol contrasts must compare consecutive ridge variants")
    if len({item.get("id") for item in contrasts}) != 2:
        raise ValueError("protocol contrast IDs must be distinct")
    if protocol.get("evidenceStatus", "exploratory") != "exploratory":
        raise ValueError("the retrospective ablation must be labelled exploratory")

    base_config = dict(runs[FEATURE_SETS[0]]["config"])
    frozen_config = protocol.get("config")
    if isinstance(frozen_config, Mapping):
        for key, value in frozen_config.items():
            if key != "feature_set" and base_config.get(key) != value:
                raise ValueError(f"run configuration differs from frozen protocol on {key}")
    scheduled = [pd.Timestamp(value).tz_convert("UTC").normalize()
                 for value in base_config["holdout_origins"]]
    if len(scheduled) != len(set(scheduled)):
        raise ValueError("holdout origins must have distinct UTC dates")
    scheduled = sorted(scheduled)
    source_rows: dict[str, list[dict[str, Any]]] = {}
    source_keys: dict[str, set[tuple[str, pd.Timestamp]]] = {}
    source_support: dict[str, dict[str, Any]] = {}
    for feature_set in FEATURE_SETS:
        run = runs[feature_set]
        config = run.get("config") or {}
        if config.get("feature_set") != feature_set:
            raise ValueError(f"run feature_set does not match {feature_set}")
        if config.get("models") != ["seasonal_naive", "ridge"]:
            raise ValueError("each run must request seasonal_naive and ridge only")
        shared_config = {key: value for key, value in config.items() if key != "feature_set"}
        expected_config = {key: value for key, value in base_config.items() if key != "feature_set"}
        if shared_config != expected_config:
            raise ValueError("run configurations disagree outside feature_set")
        if run.get("origins") and runs[FEATURE_SETS[0]].get("origins") and (
            run["origins"] != runs[FEATURE_SETS[0]]["origins"]
        ):
            raise ValueError("run origin metadata differs between variants")
        if (run.get("metadata") or {}).get("features") != protocol_variants[FEATURE_SETS.index(feature_set)].get("features"):
            raise ValueError(f"{feature_set} feature metadata differs from frozen protocol")
        # This validates complete horizons, target timestamps, paired baseline
        # rows, finite values and the saved cohort before cross-run matching.
        source_support[feature_set] = build_reliability_report(
            run, block_lengths=(2,), resamples=100
        )["support"]
        rows = list(run["predictions"])
        source_rows[feature_set] = rows
        source_keys[feature_set] = {_origin_key(row) for row in rows}
    matched = set.intersection(*(source_keys[name] for name in FEATURE_SETS))
    if not matched:
        raise ValueError("the three runs have no shared complete area-origin cohort")

    # Validate exact target and reference agreement on the retained cohort.
    reference: dict[tuple[str, pd.Timestamp, int], tuple[Any, ...]] = {}
    for feature_set in FEATURE_SETS:
        naive = { _target_key(row): row for row in source_rows[feature_set]
                  if row["model"] == "seasonal_naive" and _origin_key(row) in matched }
        for row in source_rows[feature_set]:
            if row["model"] != "ridge" or _origin_key(row) not in matched:
                continue
            key = _target_key(row)
            baseline_row = naive[key]
            signature = (
                pd.Timestamp(row["targetTime"]).tz_convert("UTC"), row["actual"], row["baseline"],
                tuple((name, baseline_row.get(name)) for name in sorted(baseline_row)
                      if name not in ("model", "cohort", "origin", "targetTime", "area")),
            )
            if key in reference and reference[key] != signature:
                raise ValueError("matched runs disagree on target, actual, baseline or seasonal_naive rows")
            reference[key] = signature

    predictions: list[dict[str, Any]] = []
    selected: dict[str, dict[str, Any]] = {}
    calibration: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    model_evaluation: dict[str, dict[str, Any]] = {}
    for feature_set in FEATURE_SETS:
        run = runs[feature_set]
        model = model_for[feature_set]
        excluded = [deepcopy(row) for row in source_rows[feature_set] if _origin_key(row) not in matched]
        for row in excluded:
            if row["model"] == "ridge":
                row["model"] = model
        model_evaluation[model] = {
            "featureSet": feature_set, "config": deepcopy(run["config"]),
            "features": deepcopy(run["metadata"]["features"]),
            "metadata": deepcopy(run.get("metadata") or {}),
            "selectedParameters": deepcopy(run.get("selectedParameters") or {}),
            "calibration": deepcopy(run.get("calibration") or {}),
            "coverage": deepcopy(run.get("coverage") or {}),
            "support": source_support[feature_set],
            "failures": deepcopy(run.get("failures") or []),
            "excludedSuccessfulPredictions": excluded,
        }
        for area, parameters in (run.get("selectedParameters") or {}).items():
            selected.setdefault(area, {})[model] = deepcopy(parameters.get("ridge"))
            if feature_set == FEATURE_SETS[0]:
                selected[area]["seasonal_naive"] = deepcopy(parameters.get("seasonal_naive"))
        for area, values in (run.get("calibration") or {}).items():
            calibration.setdefault(area, {})[model] = deepcopy(values.get("ridge"))
            if feature_set == FEATURE_SETS[0]:
                calibration[area]["seasonal_naive"] = deepcopy(values.get("seasonal_naive"))
        for failure in run.get("failures") or []:
            saved = deepcopy(failure)
            saved["featureSet"] = feature_set
            if saved.get("model") == "ridge":
                saved["model"] = model
            failures.append(saved)
        for row in source_rows[feature_set]:
            if _origin_key(row) not in matched or (feature_set != FEATURE_SETS[0] and row["model"] == "seasonal_naive"):
                continue
            saved = deepcopy(row)
            if saved["model"] == "ridge":
                saved["model"] = model
            predictions.append(saved)
    predictions.sort(key=lambda row: (row["area"], row["origin"], row["horizon"], row["model"]))
    models = ["seasonal_naive", *(model_for[name] for name in FEATURE_SETS)]
    config = {**deepcopy(base_config), "models": models, "feature_set": "mixed"}
    area_coverage = []
    for area in base_config["areas"]:
        matched_origins = {origin for row_area, origin in matched if row_area == area}
        excluded_origins = [value for value in base_config["holdout_origins"]
                            if pd.Timestamp(value).tz_convert("UTC") not in matched_origins]
        successful = {
            "seasonal_naive": _source_successes(
                runs[FEATURE_SETS[0]], source_keys[FEATURE_SETS[0]], area, "seasonal_naive"
            ),
            **{model_for[feature_set]: _source_successes(
                runs[feature_set], source_keys[feature_set], area, "ridge"
            ) for feature_set in FEATURE_SETS},
        }
        area_coverage.append({
            "area": area, "attemptedOrigins": len(scheduled), "matchedOrigins": len(matched_origins),
            "excludedOrigins": excluded_origins,
            "successfulOriginsByModel": successful,
        })
    coverage = {
        "requestedModels": models, "areas": area_coverage,
        "attemptedOrigins": len(scheduled) * len(base_config["areas"]),
        "matchedOrigins": len(matched),
        "failedOrigins": len(scheduled) * len(base_config["areas"]) - len(matched),
    }
    result: dict[str, Any] = {
        "schemaVersion": runs[FEATURE_SETS[0]].get("schemaVersion", "1.0"),
        "experiment": "household_demand_24h_feature_ablation",
        "config": config, "metadata": _shared_metadata(runs),
        "selectedParameters": selected, "calibration": calibration,
        "origins": deepcopy(runs[FEATURE_SETS[0]].get("origins") or {}),
        "predictions": predictions, "failures": failures,
        "metrics": _metrics(predictions), "coverage": coverage,
        "modelEvaluation": model_evaluation,
    }
    # Validate the new four-model artifact before reporting paired contrasts.
    support = build_reliability_report(result, block_lengths=(2,), resamples=100)["support"]
    metric_index = {(row["model"], row["scope"], row.get("area")): row for row in result["metrics"]}
    variant_rows = []
    for item in protocol_variants:
        model = item["model"]
        variant_rows.append({
            "model": model, "featureSet": item["featureSet"], "label": item["label"],
            "features": deepcopy(item["features"]),
            "overall": _scores(metric_index[(model, "overall", None)]),
            "byArea": [{"area": area,
                        "observations": int(metric_index[(model, "area", area)]["observations"]),
                        "origins": int(metric_index[(model, "area", area)]["origins"]),
                        **_scores(metric_index[(model, "area", area)])}
                       for area in base_config["areas"] if (model, "area", area) in metric_index],
        })
    frames = {model: pd.DataFrame([row for row in predictions if row["model"] == model]).assign(
        residual=lambda frame: frame["actual"] - frame["prediction"],
        covered=lambda frame: (frame["actual"] >= frame["lower"]) & (frame["actual"] <= frame["upper"]),
        width=lambda frame: frame["upper"] - frame["lower"],
    ) for model in models}
    uncertainty = _uncertainty(frames, scheduled, contrasts, protocol.get("uncertainty") or {})
    contrast_rows = []
    for item in contrasts:
        from_scores = _scores(metric_index[(item["fromModel"], "overall", None)])
        to_scores = _scores(metric_index[(item["toModel"], "overall", None)])
        contrast_rows.append({
            "id": item["id"], "label": item["label"],
            "fromModel": item["fromModel"], "toModel": item["toModel"],
            "overall": {name: to_scores[name] - from_scores[name] for name in SCORE_NAMES},
            "uncertainty": {"byBlockLength": uncertainty[item["id"]]},
        })
    result["ablation"] = {
        "schemaVersion": 1, "evidenceStatus": protocol.get("evidenceStatus", "exploratory"),
        "interpretation": protocol.get("interpretation"),
        "method": {
            "contrastSign": "toModel minus fromModel; negative MAE and RMSE differences favor the added features",
            "intervalCoverage": "observed fraction inside inclusive saved bounds; width alone does not establish improvement",
            "uncertainty": "95% paired percentile intervals from noncircular moving blocks of scheduled UTC issue dates; missing dates stay empty; all areas, horizons and models share draws",
            "supportRule": "intervals withheld below three effective observed blocks or 95% nonempty resamples",
            "resamples": int((protocol.get("uncertainty") or {}).get("resamples", 2000)),
            "seed": int((protocol.get("uncertainty") or {}).get("seed", 20260921)),
            "blockLengths": list((protocol.get("uncertainty") or {}).get("blockLengths", (2, 4, 8))),
        },
        "variants": variant_rows, "support": support, "contrasts": contrast_rows,
    }
    return result


__all__ = ["combine_ablation_runs"]
