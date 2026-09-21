"""Controlled checks for temporal separation and adjusted temperature response."""

import numpy as np
import pandas as pd
import pytest

from app_core.analysis.demand_sensitivity import DemandSensitivityConfig, _hac_variances, analyze_area


@pytest.fixture(scope="module")
def sample():
    index = pd.date_range("2023-01-01", "2023-09-01", freq="h", inclusive="left", tz="UTC")
    generator = np.random.default_rng(731)
    temperature = np.clip(8 + generator.normal(0, 4, len(index)), -6, 22)
    hour = np.asarray(index.tz_convert("Europe/Oslo").hour)
    calendar = 180 + 12 * np.sin(2 * np.pi * hour / 24) + 3 * np.asarray(index.dayofweek)
    config = DemandSensitivityConfig(start="2023-01-01", train_end="2023-06-01",
                                     validation_end="2023-08-01", end="2023-09-01",
                                     minimum_train=50, minimum_validation=50, minimum_test=50,
                                     minimum_coverage=0.9, grid_points=31)
    return index, temperature, calendar, config


def test_recovers_nonlinear_contrast_and_recomputes_all_test_scores(sample):
    index, temperature, calendar, config = sample
    noise = np.random.default_rng(901).normal(0, 0.7, len(index))
    frame = pd.DataFrame({"demand": calendar + .9 * (temperature - 8)**2 + noise,
                          "temperature": temperature}, index=index)
    result = analyze_area(frame, "NO1", config)
    assert result["selectedModel"] == "spline"
    assert result["models"][2]["test"]["mae"] < result["models"][1]["test"]["mae"]
    supported = [point for point in result["curve"] if point["supported"]]
    assert len(supported) > 10
    for point in supported:
        if abs(point["temperature"] - result["referenceTemperature"]) > 1:
            truth = .9 * ((point["temperature"] - 8)**2 - (result["referenceTemperature"] - 8)**2)
            assert point["effect"] == pytest.approx(truth, abs=5)
        assert point["lower"] <= point["effect"] <= point["upper"]
        assert point["lower336"] <= point["effect"] <= point["upper336"]
    assert all(point["effect"] is None and point["lower"] is None for point in result["curve"] if not point["supported"])
    for model in result["models"]:
        actual = np.array([row["actual"] for row in result["predictions"]])
        predicted = np.array([row[model["model"]] for row in result["predictions"]])
        assert np.mean(np.abs(actual - predicted)) == pytest.approx(model["test"]["mae"])
        assert np.sqrt(np.mean((actual - predicted)**2)) == pytest.approx(model["test"]["rmse"])
        assert np.mean(actual - predicted) == pytest.approx(model["test"]["bias"])


def test_calendar_only_selects_simple_model_and_test_never_selects(sample):
    index, temperature, calendar, config = sample
    # A constant is exactly represented by the calendar intercept alone.
    frame = pd.DataFrame({"demand": np.full(len(index), 180.), "temperature": temperature}, index=index)
    first = analyze_area(frame, "NO2", config)
    assert first["selectedModel"] == "calendar"
    changed = frame.copy()
    changed.loc[changed.index >= "2023-08-01", "demand"] += 300 * (temperature[index >= "2023-08-01"] - 8)**2
    second = analyze_area(changed, "NO2", config)
    assert second["selectedModel"] == first["selectedModel"]
    assert second["curve"] == first["curve"]
    assert [x["validation"] for x in first["models"]] == [x["validation"] for x in second["models"]]


def test_preprocessing_fits_train_only_and_support_does_not_use_test(sample):
    index, temperature, calendar, config = sample
    frame = pd.DataFrame({"demand": calendar + temperature**2,
                          "temperature": temperature}, index=index)
    first = analyze_area(frame, "NO3", config)
    changed = frame.copy()
    changed.loc[changed.index >= "2023-06-01", "temperature"] += 35
    # Validation changes, but the training fit of scaling/knots stays fixed.
    second = analyze_area(changed, "NO3", config)
    for key in ("temperatureMeanTrain", "temperatureScaleTrain", "splineKnotVectorsTrainOnly"):
        assert second["metadata"]["preprocessing"][key] == first["metadata"]["preprocessing"][key]
    test_only = frame.copy()
    test_only.loc[test_only.index >= "2023-08-01", "temperature"] += 50
    third = analyze_area(test_only, "NO3", config)
    assert third["support"] == first["support"]
    assert third["referenceTemperature"] == first["referenceTemperature"]


def test_gaps_keep_exact_utc_lags_and_fail_coverage(sample):
    index, temperature, calendar, config = sample
    frame = pd.DataFrame({"demand": calendar + temperature,
                          "temperature": temperature}, index=index)
    frame.loc["2023-08-10 03:00+00:00":"2023-08-10 09:00+00:00", "temperature"] = np.nan
    frame.loc["2023-08-20 00:00+00:00", "demand"] = np.nan
    result = analyze_area(frame, "NO4", config)
    test = frame.loc["2023-08-01":]
    complete = np.isfinite(test[["demand", "temperature"]].to_numpy()).all(axis=1)
    assert result["splits"]["test"]["observedHours"] == int(complete.sum())
    for item in result["residuals"]["acf"]:
        lag = item["lagHours"]
        assert item["pairs"] == int(np.sum(complete[lag:] & complete[:-lag]))
    sparse = frame.copy()
    sparse.loc["2023-08-03":"2023-08-31", "temperature"] = np.nan
    with pytest.raises(ValueError, match="test complete-case coverage"):
        analyze_area(sparse, "NO4", config)


def test_sparse_temperature_regions_are_suppressed(sample):
    index, temperature, calendar, config = sample
    clustered = np.where(temperature < 8, -5.0, 15.0)
    frame = pd.DataFrame({"demand": calendar + clustered, "temperature": clustered}, index=index)
    result = analyze_area(frame, "NO5", config)
    interior = [point for point in result["curve"] if 0 < point["temperature"] < 10]
    assert interior
    assert all(point["effect"] is None and not point["supported"] for point in interior)
    assert any(point["supported"] for point in result["curve"])
    assert result["referenceTemperature"] in (-5.0, 15.0)
    reference_point = next(point for point in result["curve"] if point["temperature"] == result["referenceTemperature"])
    assert reference_point["supported"] and reference_point["count"] >= 30
    assert reference_point["effect"] == pytest.approx(0, abs=1e-10)
    assert reference_point["lower"] == pytest.approx(0, abs=1e-10)
    assert reference_point["upper"] == pytest.approx(0, abs=1e-10)
    assert np.isfinite(result["sensitivity"]["maxCurveDifference"])
    if result["selectedModel"] == "calendar":
        assert result["sensitivity"]["maxCurveDifference"] == pytest.approx(0, abs=1e-10)


def test_hac_keeps_empty_hours_between_observed_scores():
    scores = np.array([[1.], [0.], [1.], [0.], [0.]])
    # Sum of squares=2; the only paired nonzero scores are exactly two hours
    # apart, with Bartlett weight 1/3 at bandwidth two.
    assert _hac_variances(scores, 1)[0] == pytest.approx(2.)
    assert _hac_variances(scores, 2)[0] == pytest.approx(2. + 2. / 3.)


def test_multiyear_seasonal_confounding_and_ar_noise_recover_response():
    # Generated independently of the module's calendar helper. Temperature
    # shares a strong annual cycle with demand, but hourly weather variation
    # identifies the nonlinear contrast after calendar adjustment.
    index = pd.date_range("2021-01-01", "2026-01-01", freq="h", inclusive="left", tz="UTC")
    generator = np.random.default_rng(114)
    tick = np.arange(len(index))
    annual = 2 * np.pi * tick / (365.2425 * 24)
    temperature = 7 + 9 * np.sin(annual) + generator.normal(0, 5, len(index))
    local = index.tz_convert("Europe/Oslo")
    hour = np.asarray(local.hour)
    day = np.asarray(local.dayofweek)
    innovation = generator.normal(0, 1.3, len(index))
    correlated_noise = np.empty(len(index))
    correlated_noise[0] = innovation[0]
    for i in range(1, len(index)):
        correlated_noise[i] = .65 * correlated_noise[i - 1] + innovation[i]
    def true_temperature_effect(t):
        return .6 * (t - 9)**2
    demand = (300 + 30 * np.sin(annual) + 18 * np.cos(annual) +
              12 * np.sin(2 * np.pi * hour / 24) + 5 * (day >= 5) +
              true_temperature_effect(temperature) + correlated_noise)
    result = analyze_area(pd.DataFrame({"demand": demand, "temperature": temperature}, index=index), "NO1")
    assert result["selectedModel"] == "spline"
    reference = result["referenceTemperature"]
    for point in result["curve"]:
        if point["supported"] and abs(point["temperature"] - reference) <= 12:
            expected = true_temperature_effect(point["temperature"]) - true_temperature_effect(reference)
            assert point["effect"] == pytest.approx(expected, abs=4)
    lag1 = next(item for item in result["residuals"]["acf"] if item["lagHours"] == 1)
    assert lag1["pairs"] == 8759
    assert lag1["correlation"] > .1
