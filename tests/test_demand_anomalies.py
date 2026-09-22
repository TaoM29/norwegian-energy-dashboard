"""Controlled anomaly checks without treating unreviewed real hours as labels."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from app_core.analysis.demand_anomalies import DemandAnomalyConfig, analyze_area


@pytest.fixture(scope="module")
def sample():
    index = pd.date_range("2023-01-01", "2023-07-01", freq="h", inclusive="left", tz="UTC")
    rng = np.random.default_rng(146)
    local = index.tz_convert("Europe/Oslo")
    hour = np.asarray(local.hour)
    weekday = np.asarray(local.dayofweek)
    temperature = 9 + 2 * np.sin(np.arange(len(index)) * 2 * np.pi / (24 * 30)) + rng.normal(0, .4, len(index))
    demand = 180 + 8 * np.sin(2 * np.pi * hour / 24) + 2 * (weekday >= 5) + rng.normal(0, 1, len(index))
    frame = pd.DataFrame({"demand": demand, "temperature": temperature}, index=index)
    config = DemandAnomalyConfig(
        start="2023-01-01", train_end="2023-03-01", validation_end="2023-04-01",
        calibration_end="2023-05-01", end="2023-07-01", minimum_coverage=.9,
        minimum_train=100, minimum_validation=100, minimum_calibration=100,
        minimum_calibration_dates=20, minimum_test=100,
    )
    return frame, config


def _at(result, time):
    return next(row for row in result["rows"] if row["time"] == pd.Timestamp(time).isoformat())


def test_injected_spikes_shift_outage_and_missing_hours(sample):
    frame, config = sample
    modified = frame.copy()
    high = pd.Timestamp("2023-05-10T12:00:00Z")
    low = pd.Timestamp("2023-05-12T13:00:00Z")
    modified.loc[high, "demand"] += 40
    modified.loc[low, "demand"] -= 40
    modified.loc["2023-05-20T00:00:00Z":"2023-05-20T05:00:00Z", "demand"] += 25
    modified.loc["2023-05-20T03:00:00Z", "demand"] = np.nan
    modified.loc["2023-06-02T00:00:00Z":"2023-06-02T03:00:00Z", "demand"] -= 35
    modified.loc["2023-06-03T00:00:00Z", "temperature"] = np.nan
    result = analyze_area(modified, "NO1", config)
    assert _at(result, high)["flagged"]
    assert _at(result, low)["flagged"]
    assert _at(result, high)["residual"] > 0
    assert _at(result, low)["residual"] < 0
    assert _at(result, "2023-05-20T03:00:00Z")["status"] == "missing_demand"
    assert not _at(result, "2023-05-20T03:00:00Z")["flagged"]
    assert _at(result, "2023-06-03T00:00:00Z")["status"] == "missing_temperature"
    assert any(item["direction"] == "low" and item["hours"] >= 4 for item in result["candidates"])
    shift_episodes = [item for item in result["candidates"] if item["start"].startswith("2023-05-20")]
    assert len(shift_episodes) >= 2  # Missing hour breaks continuity.
    assert all(item["hours"] <= 3 for item in shift_episodes)
    assert result["summary"]["episodes"] == len(result["candidates"])
    assert result["summary"]["flaggedHours"] == sum(row["flagged"] for row in result["rows"])


def test_frozen_selection_and_refit_ignore_calibration_and_test_mutations(sample):
    frame, config = sample
    first = analyze_area(frame, "NO2", config)
    changed = frame.copy()
    changed.loc[changed.index >= "2023-04-01", "demand"] += 25
    second = analyze_area(changed, "NO2", config)
    assert second["selectedModel"] == first["selectedModel"]
    assert second["selection"] == first["selection"]
    assert second["metadata"]["coefficients"] == first["metadata"]["coefficients"]
    assert second["metadata"]["preprocessing"] == first["metadata"]["preprocessing"]
    assert second["calibration"]["medianCorrection"] == pytest.approx(first["calibration"]["medianCorrection"] + 25)
    assert second["calibration"]["lowerResidual"] == pytest.approx(first["calibration"]["lowerResidual"] + 25)
    test_only = frame.copy()
    test_only.loc[test_only.index >= "2023-05-01", "demand"] += 100
    third = analyze_area(test_only, "NO2", config)
    assert third["selectedModel"] == first["selectedModel"]
    assert third["selection"] == first["selection"]
    assert third["metadata"]["coefficients"] == first["metadata"]["coefficients"]
    assert third["calibration"] == first["calibration"]
    assert third["calibrationRows"] == first["calibrationRows"]


def test_empirical_signed_quantiles_scores_and_calibration_rows_reconcile(sample):
    frame, config = sample
    result = analyze_area(frame, "NO3", config)
    calibration = result["calibration"]
    residuals = np.array([row["actual"] - row["rawExpected"]
                          for row in result["calibrationRows"] if row["status"] == "ok"])
    assert calibration["observations"] == len(residuals)
    assert calibration["lowerResidual"] == pytest.approx(np.quantile(residuals, .005))
    assert calibration["medianCorrection"] == pytest.approx(np.quantile(residuals, .5))
    assert calibration["upperResidual"] == pytest.approx(np.quantile(residuals, .995))
    assert calibration["flagFraction"] == pytest.approx(
        sum(row["flagged"] for row in result["calibrationRows"]) / len(residuals))
    row = next(row for row in result["rows"] if row["status"] == "ok" and row["residual"] > 0)
    assert row["expected"] == pytest.approx(row["rawExpected"] + calibration["medianCorrection"])
    assert row["lower"] == pytest.approx(row["rawExpected"] + calibration["lowerResidual"])
    assert row["upper"] == pytest.approx(row["rawExpected"] + calibration["upperResidual"])
    assert row["score"] == pytest.approx(row["residual"] / calibration["upperWidth"])
    assert row["flagged"] == (row["score"] > 1)


def test_calendar_only_selection_and_unsupported_temperature(sample):
    frame, config = sample
    constant = frame.copy()
    constant["demand"] = 180 + np.random.default_rng(5).normal(0, 1, len(frame))
    result = analyze_area(constant, "NO4", config)
    assert result["selectedModel"] == "calendar"
    changed = constant.copy()
    changed.loc["2023-05-10T12:00:00Z", "temperature"] = 100
    altered = analyze_area(changed, "NO4", config)
    row = _at(altered, "2023-05-10T12:00:00Z")
    assert row["status"] == "unsupported_temperature"
    assert row["score"] is None and not row["flagged"]
    assert altered["coverage"]["test"]["unsupportedHours"] == result["coverage"]["test"]["unsupportedHours"] + 1


def test_peers_use_complete_prior_local_days_and_explicit_dst_exclusion(sample):
    frame, config = sample
    injected = frame.copy()
    injected.loc["2023-05-10T12:00:00Z", "demand"] += 50
    result = analyze_area(injected, "NO5", config)
    candidate = next(item for item in result["candidates"] if item["peakTime"].startswith("2023-05-10T12"))
    peers = candidate["peers"]
    assert peers["targetDate"] == "2023-05-10"
    assert len(peers["targetRows"]) == 24
    assert peers["excludedDstDays"] >= 1  # Spring-forward Oslo day is 23 hours.
    assert len(peers["days"]) <= 3
    assert all(len(day["rows"]) == 24 and day["date"] < "2023-05-01" for day in peers["days"])
    assert all(day["temperatureDifference"] <= 3 and day["seasonDistance"] <= 45 for day in peers["days"])


def test_input_and_support_failures_are_explicit(sample):
    frame, config = sample
    duplicate = pd.concat([frame, frame.iloc[[0]]])
    with pytest.raises(ValueError, match="unique and UTC"):
        analyze_area(duplicate, "NO1", config)
    offhour = frame.copy()
    shifted = offhour.index.to_list()
    shifted[0] += pd.Timedelta(minutes=30)
    offhour.index = pd.DatetimeIndex(shifted)
    with pytest.raises(ValueError, match="exact UTC hourly"):
        analyze_area(offhour, "NO1", config)
    sparse = frame.copy()
    sparse.loc["2023-04-05":"2023-04-25", "temperature"] = np.nan
    with pytest.raises(ValueError, match="calibration complete-case coverage"):
        analyze_area(sparse, "NO1", config)
    with pytest.raises(ValueError, match="calibration.*dates"):
        analyze_area(frame, "NO1", replace(config, minimum_calibration_dates=40))
