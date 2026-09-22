from __future__ import annotations

from copy import deepcopy

import pandas as pd
import numpy as np
import pytest

from app_core.analysis.forecast_ablation import combine_ablation_runs


FEATURE_SETS = ("calendar", "calendar_demand", "calendar_demand_weather")


def _fixture(*, dates=8, hours=2, missing=None, offsets=(3.0, 2.0, 1.0)):
    missing = missing or {}
    origins = list(pd.date_range("2025-01-01", periods=dates, freq="8D", tz="UTC"))
    config = {
        "areas": ["NO1", "NO2"], "models": ["seasonal_naive", "ridge"],
        "horizon_hours": hours, "holdout_origins": [date.isoformat() for date in origins],
    }
    runs = {}
    variants = []
    for index, feature_set in enumerate(FEATURE_SETS):
        model = f"ridge_{feature_set}"
        features = {"featureSet": feature_set, "columns": [f"column_{index}"]}
        variants.append({"featureSet": feature_set, "model": model,
                         "label": f"Variant {index}", "features": features})
        rows = []
        for date_index, origin in enumerate(origins):
            for area_index, area in enumerate(config["areas"]):
                if (date_index, area) in missing.get(feature_set, set()):
                    continue
                for hour in range(hours):
                    target = origin + pd.Timedelta(hours=hour)
                    actual = float(100 + date_index + area_index * 10 + hour)
                    for name, error in (("seasonal_naive", 4.0), ("ridge", offsets[index])):
                        prediction = actual - error
                        rows.append({
                            "area": area, "cohort": "matched_holdout", "origin": origin.isoformat(),
                            "targetTime": target.isoformat(), "horizon": hour + 1, "model": name,
                            "actual": actual, "prediction": prediction,
                            "lower": prediction - 2.0, "median": prediction, "upper": prediction + 2.0,
                            "lowerQuantile": 0.1, "upperQuantile": 0.9, "baseline": actual - 4,
                            "maseScale": 2.0, "season": "winter", "isPeakPeriod": False,
                        })
        runs[feature_set] = {
            "schemaVersion": "1.0", "config": {**config, "feature_set": feature_set},
            "metadata": {"unit": "kWh", "features": features,
                         "assumptions": {"shared": "same", "weatherAvailability": feature_set}},
            "origins": {"holdout": config["holdout_origins"]},
            "selectedParameters": {area: {"ridge": {"alpha": index}, "seasonal_naive": {}}
                                   for area in config["areas"]},
            "calibration": {area: {"ridge": {"lower_residual": -2},
                                   "seasonal_naive": {"lower_residual": -2}}
                            for area in config["areas"]},
            "predictions": rows,
            "failures": [], "coverage": {"requestedModels": config["models"]},
        }
    protocol = {
        "variants": variants,
        "contrasts": [
            {"id": "demand", "label": "Add demand", "fromModel": "ridge_calendar",
             "toModel": "ridge_calendar_demand"},
            {"id": "weather", "label": "Add weather", "fromModel": "ridge_calendar_demand",
             "toModel": "ridge_calendar_demand_weather"},
        ],
        "uncertainty": {"blockLengths": [2, 4, 8], "resamples": 100, "seed": 7},
        "evidenceStatus": "exploratory",
    }
    return runs, protocol


def test_hand_scored_contrasts_and_zero_width_paired_intervals():
    runs, protocol = _fixture()
    report = combine_ablation_runs(runs, protocol)
    ablation = report["ablation"]
    assert [row["model"] for row in ablation["variants"]] == [
        "ridge_calendar", "ridge_calendar_demand", "ridge_calendar_demand_weather"]
    assert [row["id"] for row in ablation["contrasts"]] == ["demand", "weather"]
    assert len(report["predictions"]) == 8 * 2 * 2 * 4
    assert ablation["support"]["hourlyRowsPerModel"] == {
        model: 8 * 2 * 2 for model in report["config"]["models"]}
    for contrast in ablation["contrasts"]:
        assert contrast["overall"]["mae"] == pytest.approx(-1)
        assert contrast["overall"]["rmse"] == pytest.approx(-1)
        assert contrast["overall"]["pinballMedian"] == pytest.approx(-0.5)
        assert contrast["overall"]["intervalCoverage"] == pytest.approx(1 if contrast["id"] == "demand" else 0)
        ci = contrast["uncertainty"]["byBlockLength"][0]["intervals"]
        assert ci["mae"] == pytest.approx({"lower": -1, "upper": -1})
        assert ci["rmse"] == pytest.approx({"lower": -1, "upper": -1})
    assert report["config"]["feature_set"] == "mixed"
    assert report["metadata"]["features"]["perVariant"]["calendar"]["columns"] == ["column_0"]
    assert report["selectedParameters"]["NO1"]["ridge_calendar_demand"]["alpha"] == 1


def test_missing_date_and_unequal_area_support_are_intersected_and_audited():
    runs, protocol = _fixture(missing={
        "calendar": {(2, "NO1")},
        "calendar_demand": {(4, "NO1")},
        "calendar_demand_weather": {(4, "NO2")},
    })
    report = combine_ablation_runs(runs, protocol)
    support = report["ablation"]["support"]
    assert support["scheduledDates"] == 8
    assert support["observedDates"] == 7
    assert support["scheduledAreaOrigins"] == 16
    assert support["matchedAreaOrigins"] == 13
    assert support["excludedAreaOrigins"] == 3
    assert support["missingDates"] == [pd.Timestamp("2025-02-02", tz="UTC").isoformat()]
    assert report["coverage"]["matchedOrigins"] == 13
    assert report["coverage"]["failedOrigins"] == 3
    no1 = next(row for row in report["coverage"]["areas"] if row["area"] == "NO1")
    assert no1["matchedOrigins"] == 6
    assert no1["successfulOriginsByModel"] == {
        "seasonal_naive": 7, "ridge_calendar": 7,
        "ridge_calendar_demand": 7, "ridge_calendar_demand_weather": 8,
    }
    calendar_no1 = next(row for row in report["ablation"]["variants"][0]["byArea"]
                        if row["area"] == "NO1")
    assert calendar_no1["observations"] == 12
    assert calendar_no1["origins"] == 6
    assert support["hourlyRowsPerModel"] == {model: 26 for model in report["config"]["models"]}
    audit = report["modelEvaluation"]["ridge_calendar"]["excludedSuccessfulPredictions"]
    assert len(audit) == 8  # Two successful origins lost from this variant, both models and hours.
    assert all(row["model"] in ("ridge_calendar", "seasonal_naive") for row in audit)


def test_identical_variant_predictions_have_zero_contrast_interval():
    runs, protocol = _fixture(offsets=(1.0, 1.0, 1.0))
    report = combine_ablation_runs(runs, protocol)
    for contrast in report["ablation"]["contrasts"]:
        assert all(value == pytest.approx(0) for value in contrast["overall"].values())
        for measure, bounds in contrast["uncertainty"]["byBlockLength"][0]["intervals"].items():
            assert bounds == pytest.approx({"lower": 0, "upper": 0}), measure


def test_rejects_target_and_full_horizon_corruption():
    runs, protocol = _fixture()
    changed = deepcopy(runs)
    row = next(row for row in changed["calendar_demand"]["predictions"] if row["model"] == "ridge")
    row["targetTime"] = (pd.Timestamp(row["targetTime"]) + pd.Timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError, match="targetTime"):
        combine_ablation_runs(changed, protocol)
    changed = deepcopy(runs)
    changed["calendar_demand"]["predictions"] = [row for row in changed["calendar_demand"]["predictions"]
        if not (row["area"] == "NO1" and row["origin"].startswith("2025-01-01") and row["horizon"] == 2)]
    with pytest.raises(ValueError, match="full requested horizon"):
        combine_ablation_runs(changed, protocol)


def test_rejects_cross_variant_actual_and_seasonal_disagreement():
    runs, protocol = _fixture()
    changed = deepcopy(runs)
    for row in changed["calendar_demand"]["predictions"]:
        if row["origin"].startswith("2025-01-01") and row["area"] == "NO1" and row["horizon"] == 1:
            row["actual"] += 1
    with pytest.raises(ValueError, match="disagree"):
        combine_ablation_runs(changed, protocol)

    changed = deepcopy(runs)
    for row in changed["calendar_demand"]["predictions"]:
        if row["model"] == "seasonal_naive" and row["origin"].startswith("2025-01-01"):
            row["prediction"] += 1
            row["baseline"] += 1
        elif row["origin"].startswith("2025-01-01"):
            row["baseline"] += 1
    with pytest.raises(ValueError, match="disagree"):
        combine_ablation_runs(changed, protocol)


def test_paired_blocks_replay_with_gaps_unequal_support_and_nonlinear_rmse():
    runs, protocol = _fixture(dates=16, missing={
        "calendar": {(3, "NO1"), (3, "NO2")},
        "calendar_demand": {(8, "NO1")},
    })
    for variant_index, run in enumerate(runs.values()):
        for row in run["predictions"]:
            if row["model"] == "ridge":
                day = (pd.Timestamp(row["origin"]) - pd.Timestamp("2025-01-01", tz="UTC")).days // 8
                error = 1 + ((day + row["horizon"] + (row["area"] == "NO2") * 3) % (7 - variant_index))
                row.update(prediction=row["actual"] - error, lower=row["actual"] - error - 2,
                           median=row["actual"] - error, upper=row["actual"] - error + 2)
    result = combine_ablation_runs(runs, protocol)
    assert combine_ablation_runs(runs, protocol) == result
    reordered = deepcopy(runs)
    for run in reordered.values():
        run["predictions"].reverse()
    assert combine_ablation_runs(reordered, protocol)["ablation"] == result["ablation"]
    # Independent explicit date draws and row gathering, without report helpers.
    frame = pd.DataFrame(result["predictions"])
    dates = runs["calendar"]["config"]["holdout_origins"]
    rng = np.random.default_rng(7)
    starts = rng.integers(0, 15, size=(100, 8))
    differences = []
    for sample in starts:
        selected = [index for start in sample for index in (start, start + 1)]
        rows = pd.concat([frame.loc[frame.origin.eq(dates[index])] for index in selected])
        scores = []
        for model in ("ridge_calendar", "ridge_calendar_demand"):
            part = rows.loc[rows.model.eq(model)]
            errors = part.actual.to_numpy() - part.prediction.to_numpy()
            scores.append([np.abs(errors).mean(), np.sqrt(np.square(errors).mean())])
        differences.append(np.subtract(scores[1], scores[0]))
    ci = result["ablation"]["contrasts"][0]["uncertainty"]["byBlockLength"][0]["intervals"]
    for column, name in enumerate(("mae", "rmse")):
        lower, upper = np.quantile(np.array(differences)[:, column], [.025, .975])
        assert ci[name] == pytest.approx({"lower": lower, "upper": upper})
