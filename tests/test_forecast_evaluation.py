import numpy as np
import pandas as pd
import pytest

import app_core.analysis.forecast_evaluation as fe


def _config(**updates):
    config = {
        "areas": ["NO1"],
        "models": ["seasonal_naive", "ridge"],
        "horizon_hours": 4,
        "train_window_days": 30,
        "training_origin_stride_hours": 12,
        "validation_origins": ["2025-02-05T00:00:00Z"],
        "calibration_origins": ["2025-02-08T00:00:00Z"],
        "holdout_origins": ["2025-02-11T00:00:00Z", "2025-02-12T00:00:00Z"],
        "weather_mode": "historical_only",
        "energy_publication_lag_hours": 48,
        "weather_publication_lag_hours": 120,
        "interval_coverage": 0.8,
        "random_seed": 7,
        "ridge_alphas": [0.1, 10.0],
        "gradient_boosting_candidates": [
            {"n_estimators": 20, "learning_rate": 0.1, "max_depth": 2}
        ],
        "sarimax_candidates": [{"order": [1, 0, 0], "seasonal_order": [0, 0, 0, 0]}],
        "sarimax_maxiter": 5,
    }
    config.update(updates)
    return config


def _frames():
    timestamps = pd.date_range("2024-12-15", "2025-02-15", freq="h", tz="UTC")
    hour = np.arange(len(timestamps), dtype=float)
    energy = pd.DataFrame({
        "timestamp": timestamps,
        "area": "NO1",
        "kind": "consumption",
        "group": "household",
        "value": 200 + 15 * np.sin(2 * np.pi * hour / 24) + 6 * np.cos(2 * np.pi * hour / 168),
    })
    weather = pd.DataFrame({
        "time": timestamps,
        "area": "NO1",
        "temperature_2m (°C)": 2 + 4 * np.sin(2 * np.pi * hour / (24 * 14)),
        "precipitation (mm)": np.maximum(0, np.sin(hour / 13)),
        "wind_speed_10m (m/s)": 5 + np.cos(hour / 17),
    })
    return energy, weather


def test_regular_grid_preserves_missing_targets_without_future_fill():
    timestamps = pd.date_range("2025-01-01", periods=5, freq="h", tz="UTC")
    energy = pd.DataFrame({"time": timestamps.delete(2), "quantity_kwh": [1.0, 2.0, 4.0, 5.0]})
    weather = pd.DataFrame({"time": timestamps.delete(3), "temperature_2m": [0.0, 1.0, 2.0, 4.0]})

    y, w = fe.regularize_hourly_frames(energy, weather)

    assert y.index.equals(timestamps)
    assert pd.isna(y.loc[timestamps[2]])
    assert pd.isna(w.loc[timestamps[3], "temperature_2m"])
    assert y.loc[timestamps[1]] == 2.0 and y.loc[timestamps[3]] == 4.0


def test_historical_features_ignore_all_post_issue_target_and_weather_values():
    energy_frame, weather_frame = _frames()
    y, w = fe.regularize_hourly_frames(energy_frame, weather_frame)
    origin = pd.Timestamp("2025-02-05T00:00:00Z")
    config = _config()
    expected = fe.build_origin_features(y, w, origin, config)

    perturbed_y = y.copy()
    perturbed_w = w.copy()
    perturbed_y.loc[perturbed_y.index >= origin] += 1_000_000
    perturbed_w.loc[perturbed_w.index >= origin, :] += 1_000_000
    actual = fe.build_origin_features(perturbed_y, perturbed_w, origin, config)

    pd.testing.assert_frame_equal(actual, expected)
    cutoff = origin - pd.Timedelta(hours=config["energy_publication_lag_hours"] + 1)
    assert expected.iloc[0]["energy_available"] == y.loc[cutoff]

    upper_bound = fe.build_origin_features(
        perturbed_y, perturbed_w, origin, _config(weather_mode="realized_future_upper_bound")
    )
    assert upper_bound.filter(like="realized_target").ne(
        fe.build_origin_features(y, w, origin, _config(weather_mode="realized_future_upper_bound"))
        .filter(like="realized_target")
    ).all().all()


def test_operational_weather_is_rejected_until_archived_issue_time_data_exists():
    with pytest.raises(ValueError, match="archived issue-time forecasts are not ingested"):
        fe.validate_evaluation_config(_config(weather_mode="operational_forecast"))


def test_stage_boundaries_wait_until_prior_target_labels_are_published():
    with pytest.raises(ValueError, match="validation target labels must be available"):
        fe.validate_evaluation_config(_config(calibration_origins=["2025-02-06T00:00:00Z"]))

    with pytest.raises(ValueError, match="calibration target labels must be available"):
        fe.validate_evaluation_config(_config(holdout_origins=["2025-02-09T00:00:00Z"]))


def test_offline_origin_limit_is_96_but_interactive_limit_remains_24():
    from backend.forecast_jobs import validate_job_config

    holdout = pd.date_range("2025-02-11", periods=25, freq="D", tz="UTC")
    requested = _config(holdout_origins=[day.isoformat() for day in holdout])
    assert len(fe.validate_evaluation_config(requested)["holdout_origins"]) == 25
    with pytest.raises(ValueError, match="interactive holdout_origins"):
        validate_job_config("evaluation", requested)
    too_many = pd.date_range("2025-02-11", periods=97, freq="D", tz="UTC")
    with pytest.raises(ValueError, match="1 to 96"):
        fe.validate_evaluation_config(_config(holdout_origins=[day.isoformat() for day in too_many]))


def test_seasonal_naive_repeats_weekly_lag_until_reference_is_available():
    timestamps = pd.date_range("2024-12-01", "2025-02-10", freq="h", tz="UTC")
    energy = pd.Series(np.arange(len(timestamps), dtype=float), index=timestamps)
    origin = pd.Timestamp("2025-02-05T00:00:00Z")
    targets = pd.date_range(origin, periods=4, freq="h")
    cutoff = fe._availability_cutoff(origin, 168)

    prediction = fe._seasonal_naive(energy, targets, cutoff)

    references = [target - pd.Timedelta(hours=336) for target in targets]
    assert prediction.tolist() == [energy.loc[reference] for reference in references]
    assert all(reference <= cutoff for reference in references)


def test_mase_scale_keeps_hourly_spacing_across_missing_target():
    timestamps = pd.date_range("2025-01-01", periods=400, freq="h", tz="UTC")
    energy = pd.Series(np.arange(400, dtype=float), index=timestamps)
    energy.iloc[200] = np.nan

    assert fe._mase_scale(energy) == 168.0


def test_calendar_features_use_norwegian_local_time_across_dst_jump():
    timestamps = pd.date_range("2025-02-01", "2025-04-02", freq="h", tz="UTC")
    energy = pd.Series(1.0, index=timestamps)
    weather = pd.DataFrame(index=timestamps)
    origin = pd.Timestamp("2025-03-30T00:00:00Z")

    features = fe.build_origin_features(energy, weather, origin, _config())

    # UTC 00:00 and 01:00 map to local 01:00 and 03:00 when DST starts.
    assert features.iloc[0]["hour_sin"] == pytest.approx(np.sin(2 * np.pi * 1 / 24))
    assert features.iloc[1]["hour_sin"] == pytest.approx(np.sin(2 * np.pi * 3 / 24))


def test_holdout_values_cannot_change_validation_selection(monkeypatch):
    energy, weather = _frames()

    def simple_predict(model, parameters, prepared, origin, cfg):
        if model == "seasonal_naive":
            level = 0.0
        else:
            level = float(parameters["alpha"])
        return np.repeat(level, cfg["horizon_hours"])

    monkeypatch.setattr(fe, "_predict", simple_predict)
    # Make validation actuals close to alpha=10 and holdout actuals close to alpha=.1.
    validation_targets = pd.date_range("2025-02-05T00:00:00Z", periods=4, freq="h")
    holdout_targets = pd.date_range("2025-02-11T00:00:00Z", periods=28, freq="h")
    energy.loc[energy["timestamp"].isin(validation_targets), "value"] = 10.0
    energy.loc[energy["timestamp"].isin(holdout_targets), "value"] = 0.1
    first = fe.evaluate_frames(energy, weather, _config())

    changed = energy.copy()
    changed.loc[changed["timestamp"] >= pd.Timestamp("2025-02-11T00:00:00Z"), "value"] = 99999
    second = fe.evaluate_frames(changed, weather, _config())

    assert first["selectedParameters"] == second["selectedParameters"]
    assert first["selectedParameters"]["NO1"]["ridge"] == {"alpha": 10.0}
    assert first["origins"]["selectionFrozenBeforeHoldout"] is True


def test_holdout_values_cannot_change_calibration_residuals(monkeypatch):
    energy, weather = _frames()

    def simple_predict(model, parameters, prepared, origin, cfg):
        return np.repeat(190.0 if model == "ridge" else 200.0, cfg["horizon_hours"])

    monkeypatch.setattr(fe, "_predict", simple_predict)
    first = fe.evaluate_frames(energy, weather, _config(ridge_alphas=[1.0]))
    changed = energy.copy()
    changed.loc[changed["timestamp"] >= pd.Timestamp("2025-02-11T00:00:00Z"), "value"] += 1000
    second = fe.evaluate_frames(changed, weather, _config(ridge_alphas=[1.0]))
    assert first["calibration"] == second["calibration"]
    rows = first["calibration"]["NO1"]["ridge"]["residualRows"]
    assert len(rows) == first["calibration"]["NO1"]["ridge"]["observations"]
    assert all(row["actual"] - row["prediction"] == pytest.approx(row["residual"]) for row in rows)


def test_failed_model_excludes_origin_from_every_models_metrics(monkeypatch):
    energy, weather = _frames()
    failed_origin = pd.Timestamp("2025-02-12T00:00:00Z")

    def sometimes_fails(model, parameters, prepared, origin, cfg):
        if model == "ridge" and origin == failed_origin:
            raise RuntimeError("synthetic fold failure")
        return np.repeat(200.0, cfg["horizon_hours"])

    monkeypatch.setattr(fe, "_predict", sometimes_fails)
    result = fe.evaluate_frames(energy, weather, _config(ridge_alphas=[1.0]))

    assert result["coverage"]["attemptedOrigins"] == 2
    assert result["coverage"]["matchedOrigins"] == 1
    assert result["coverage"]["failedOrigins"] == 1
    assert {row["origin"] for row in result["predictions"]} == {"2025-02-11T00:00:00+00:00"}
    overall = [row for row in result["metrics"] if row["scope"] == "overall"]
    assert {row["model"] for row in overall} == {"seasonal_naive", "ridge"}
    assert {row["origins"] for row in overall} == {1}
    assert any(row["stage"] == "holdout" and row["model"] == "ridge" for row in result["failures"])


def test_small_real_ridge_evaluation_is_json_serializable():
    energy, weather = _frames()
    result = fe.evaluate_frames(energy, weather, _config(ridge_alphas=[1.0]))

    assert result["experiment"] == "household_demand_24h_flagship"
    assert result["coverage"]["matchedOrigins"] == 2
    assert len(result["predictions"]) == 2 * 4 * 2
    assert any(row["scope"] == "horizon" and row["horizon"] == 4 for row in result["metrics"])
    assert all("maeDeltaVsBaseline" in row for row in result["metrics"])
    assert all("bias" in row and "baselineBias" in row and "areaOrigins" in row for row in result["metrics"])
    assert all("baselineMase" in row and "maseDeltaVsBaseline" in row for row in result["metrics"])
    assert "snapshotCaveat" in result["metadata"]["assumptions"]
    # Artifact storage uses strict JSON; NaN and numpy scalar leakage must fail here.
    import json
    json.dumps(result, allow_nan=False)


def test_cancellation_stops_before_work(monkeypatch):
    energy, weather = _frames()
    with pytest.raises(fe.EvaluationCancelled):
        fe.evaluate_frames(energy, weather, _config(), cancelled=lambda: True)
