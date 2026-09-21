from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from app_core.analysis.forecast_reliability import build_reliability_report


def _payload(*, dates=8, missing=(), areas=("NO1", "NO2"), hours=3):
    schedule = pd.date_range("2025-01-01", periods=dates, freq="8D", tz="UTC")
    rows = []
    for index, origin in enumerate(schedule):
        if index in missing:
            continue
        for area_index, area in enumerate(areas):
            for hour in range(hours):
                actual = float(100 + area_index * 10 + index + hour)
                baseline = actual - 2.0
                for model, offset in (("seasonal_naive", 2.0), ("ridge", 1.0)):
                    prediction = actual - offset
                    rows.append({
                        "area": area, "origin": origin.isoformat(),
                        "targetTime": (origin + pd.Timedelta(hours=hour)).isoformat(),
                        "horizon": hour + 1, "model": model, "actual": actual,
                        "prediction": prediction, "baseline": baseline,
                        "lower": prediction - 1.0, "median": prediction,
                        "upper": prediction + 1.0,
                        "lowerQuantile": 0.1, "upperQuantile": 0.9,
                    })
    return {"config": {"areas": list(areas), "models": ["seasonal_naive", "ridge"],
                       "horizon_hours": hours,
                       "holdout_origins": [origin.isoformat() for origin in schedule]},
            "predictions": rows}


def _model(report, name):
    return next(row for row in report["models"] if row["model"] == name)


def test_recomputes_hand_checked_paired_scores_and_residual_support():
    report = build_reliability_report(_payload(dates=8), block_lengths=(2,), resamples=100, seed=7)
    ridge = _model(report, "ridge")
    baseline = _model(report, "seasonal_naive")
    assert {key: ridge["overall"][key] for key in (
        "maeDeltaVsBaseline", "rmseDeltaVsBaseline", "bias", "intervalCoverage", "meanIntervalWidth"
    )} == pytest.approx({
        "maeDeltaVsBaseline": -1.0, "rmseDeltaVsBaseline": -1.0,
        "bias": 1.0, "intervalCoverage": 1.0, "meanIntervalWidth": 2.0,
    })
    assert baseline["overall"]["maeDeltaVsBaseline"] == 0
    assert report["support"]["matchedAreaOrigins"] == 16
    assert report["support"]["hourlyRowsPerModel"]["ridge"] == 48
    assert len(ridge["byOrigin"]) == 16
    assert ridge["residualDependence"]["withinWindowLag1Hour"]["pairs"] == 32
    assert ridge["residualDependence"]["exactTargetLag24Hours"]["pairs"] == 0
    assert ridge["residualDependence"]["originMeanLag8Days"]["pairs"] == 14
    assert len(ridge["residualDependence"]["byArea"]) == 2
    assert ridge["overall"]["pinballMedian"] == pytest.approx(0.5)
    assert "pinballMedian" in ridge["uncertainty"]["byBlockLength"][0]["intervals"]
    assert ridge["uncertainty"]["byBlockLength"][0]["intervals"]["maeDeltaVsBaseline"] == pytest.approx(
        {"lower": -1.0, "upper": -1.0}
    )


def test_missing_scheduled_dates_stay_in_grid_and_bootstrap_is_deterministic():
    payload = _payload(dates=8, missing=(3,))
    first = build_reliability_report(payload, block_lengths=(2,), resamples=120, seed=11)
    second = build_reliability_report(payload, block_lengths=(2,), resamples=120, seed=11)
    assert first == second
    assert first["support"]["scheduledDates"] == 8
    assert first["support"]["observedDates"] == 7
    assert first["support"]["excludedAreaOrigins"] == 2
    assert first["support"]["missingDates"] == ["2025-01-25T00:00:00+00:00"]
    assert _model(first, "ridge")["residualDependence"]["originMeanLag8Days"]["pairs"] == 10


def test_bootstrap_keeps_model_and_area_dates_paired():
    payload = _payload(dates=8)
    for row in payload["predictions"]:
        if row["model"] == "ridge":
            day = (pd.Timestamp(row["origin"]) - pd.Timestamp("2025-01-01T00:00:00Z")).days // 8
            row["prediction"] += day % 3
            row["lower"] = row["prediction"] - 1
            row["upper"] = row["prediction"] + 1
    original = build_reliability_report(payload, block_lengths=(2,), resamples=200, seed=1)
    reordered = copy.deepcopy(payload)
    reordered["predictions"].reverse()
    assert build_reliability_report(reordered, block_lengths=(2,), resamples=200, seed=1) == original
    assert _model(original, "ridge")["uncertainty"]["byBlockLength"][0]["intervals"] is not None


def test_shared_regional_shocks_are_never_resampled_as_independent_areas():
    payload = _payload(dates=16, areas=("NO1", "NO2"))
    for row in payload["predictions"]:
        if row["model"] == "ridge":
            index = (pd.Timestamp(row["origin"]) - pd.Timestamp("2025-01-01T00:00:00Z")).days // 8
            # Opposing regional errors cancel in each date's pooled absolute loss.
            # Independent area resampling would incorrectly introduce variability.
            error = 1 if (index % 2 == 0) == (row["area"] == "NO1") else 9
            row["prediction"] = row["actual"] - error
    report = build_reliability_report(payload, block_lengths=(2, 4), resamples=200)
    for block in _model(report, "ridge")["uncertainty"]["byBlockLength"]:
        assert block["intervals"]["maeDeltaVsBaseline"] == pytest.approx({"lower": 3.0, "upper": 3.0})


def test_exact_hour_lags_count_only_available_timestamp_pairs():
    report = build_reliability_report(_payload(dates=8, areas=("NO1",), hours=25),
                                      block_lengths=(2,), resamples=100)
    dependence = _model(report, "ridge")["residualDependence"]
    assert dependence["withinWindowLag1Hour"]["pairs"] == 8 * 24
    assert dependence["exactTargetLag24Hours"]["pairs"] == 8
    assert dependence["exactTargetLag168Hours"]["pairs"] == 7


def test_rmse_delta_uses_squared_row_errors_before_square_root():
    payload = _payload(dates=8, areas=("NO1",), hours=2)
    for row in payload["predictions"]:
        if row["model"] == "ridge" and row["horizon"] == 2:
            row["prediction"] = row["actual"] - 3
            row["lower"] = row["prediction"] - 1
            row["upper"] = row["prediction"] + 1
    report = build_reliability_report(payload, block_lengths=(2,), resamples=100)
    ridge = _model(report, "ridge")
    assert ridge["overall"]["rmseDeltaVsBaseline"] == pytest.approx(np.sqrt(5) - 2)
    assert ridge["overall"]["maeDeltaVsBaseline"] == pytest.approx(0)
    ci = ridge["uncertainty"]["byBlockLength"][0]["intervals"]["rmseDeltaVsBaseline"]
    assert ci["lower"] == pytest.approx(np.sqrt(5) - 2)
    assert ci["upper"] == pytest.approx(np.sqrt(5) - 2)


def test_sparse_dates_and_irregular_schedule_withhold_intervals():
    sparse = build_reliability_report(_payload(dates=8, missing=tuple(range(2, 8))),
                                      block_lengths=(2, 4, 8), resamples=100)
    for row in _model(sparse, "ridge")["uncertainty"]["byBlockLength"]:
        assert row["intervals"] is None
        assert "effective" in row["reason"]
    irregular = _payload(dates=8)
    irregular["config"]["holdout_origins"][3] = "2025-01-26T00:00:00+00:00"
    for row in irregular["predictions"]:
        if row["origin"].startswith("2025-01-25"):
            row["origin"] = "2025-01-26T00:00:00+00:00"
            row["targetTime"] = (pd.Timestamp(row["targetTime"]) + pd.Timedelta(days=1)).isoformat()
    report = build_reliability_report(irregular, block_lengths=(2,), resamples=100)
    assert "regular date cadence" in _model(report, "ridge")["uncertainty"]["byBlockLength"][0]["reason"]


def test_rejects_unpaired_saved_rows():
    payload = _payload()
    payload["predictions"].pop()
    with pytest.raises(ValueError, match="not paired"):
        build_reliability_report(payload, resamples=100)


@pytest.mark.parametrize("mutation,match", [
    (lambda rows: rows.__setitem__(0, {**rows[0], "targetTime": "2025-01-01T03:00:00+00:00"}), "targetTime"),
    (lambda rows: rows.__setitem__(0, {**rows[0], "baseline": 12345.0}), "baseline"),
    (lambda rows: rows.__setitem__(0, {**rows[0], "area": "NO5"}), "outside the requested cohort"),
    (lambda rows: rows.__setitem__(0, {**rows[0], "horizon": 99}), "not paired"),
])
def test_rejects_corrupted_saved_cohort_rows(mutation, match):
    payload = _payload()
    mutation(payload["predictions"])
    with pytest.raises(ValueError, match=match):
        build_reliability_report(payload, resamples=100)


def test_rejects_partial_horizon_even_when_models_are_paired():
    payload = _payload()
    payload["predictions"] = [row for row in payload["predictions"] if not (
        row["origin"].startswith("2025-01-01") and row["area"] == "NO1" and row["horizon"] == 3
    )]
    with pytest.raises(ValueError, match="full requested horizon"):
        build_reliability_report(payload, resamples=100)
