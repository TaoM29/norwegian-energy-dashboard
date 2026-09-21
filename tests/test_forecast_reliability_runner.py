"""Retained-input integrity and immutable offline study execution."""
from copy import deepcopy
import json

import numpy as np
import pandas as pd
import pytest

from scripts import run_forecast_reliability as runner


def _inputs():
    times = pd.date_range("2022-09-01", "2025-12-29", freq="h", tz="UTC")
    energy = pd.DataFrame({"timestamp": times, "area": "NO1", "value": np.arange(len(times)) + 0.1234567890123456,
                           "unit": "kWh", "quality": "ok"})
    weather = pd.DataFrame({"time": times, "area": "NO1", "temperature_2m": 5.123456789012345,
                            "precipitation": 0.0, "wind_speed_10m": 2.0})
    energy.loc[10, "quality"] = "missing"
    sources = {"areas": {"NO1": {"energy": [{"version": "fixed"}], "weather": []}}}
    return energy, weather, sources


def _protocol():
    protocol = runner.read_protocol(runner.DEFAULT_PROTOCOL)
    protocol["config"]["areas"] = ["NO1"]
    return protocol


def test_frozen_protocol_has_explicit_settings_rotating_weekdays_and_embargoes():
    protocol = runner.read_protocol(runner.DEFAULT_PROTOCOL)
    config = protocol["config"]
    assert [len(config[k]) for k in ("validation_origins", "calibration_origins", "holdout_origins")] == [12, 23, 46]
    assert set(pd.to_datetime(config["holdout_origins"]).dayofweek) == set(range(7))
    assert set(pd.to_datetime(config["holdout_origins"]).month) == set(range(1, 13))
    assert protocol["evidenceStatus"] == "exploratory"
    assert config == runner.engine.validate_evaluation_config(config)


def test_retained_inputs_round_trip_mask_flags_and_reject_tampering(tmp_path, monkeypatch):
    original = _inputs()
    monkeypatch.setattr(runner.engine, "_load_frames", lambda config: original)
    protocol = _protocol()
    folder = tmp_path / "inputs"
    runner.prepare_inputs(folder, protocol)
    e, w, manifest = runner.load_inputs(folder, protocol)
    assert np.isnan(e.loc[10, "value"])
    assert e.loc[11, "value"] == original[0].loc[11, "value"]
    assert w.loc[11, "temperature_2m"] == original[1].loc[11, "temperature_2m"]
    assert manifest["areas"]["NO1"]["rows"] == len(original[0])
    coverage = json.loads((folder / "coverage.json").read_text())
    assert coverage["areas"][0]["energyHours"] == len(e) - 1
    with pytest.raises(FileExistsError):
        runner.prepare_inputs(folder, protocol)
    changed = deepcopy(protocol)
    changed["config"]["random_seed"] += 1
    with pytest.raises(ValueError, match="protocol differs"):
        runner.load_inputs(folder, changed)
    with (folder / "NO1.csv").open("a") as stream:
        stream.write("tampered\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        runner.load_inputs(folder, protocol)


def test_existing_result_refused_before_any_loading_or_fitting(tmp_path, monkeypatch):
    store = runner.ForecastStore(tmp_path / "artifacts")
    protocol = runner.read_protocol(runner.DEFAULT_PROTOCOL)
    path = store.results_dir / f"{protocol['id']}.json"
    path.write_text('"historical evidence"')
    monkeypatch.setattr(runner, "load_inputs", lambda *_args: pytest.fail("must not read inputs"))
    with pytest.raises(FileExistsError, match="already exists"):
        runner.run_study(runner.DEFAULT_PROTOCOL, tmp_path / "missing-inputs", tmp_path / "artifacts")
    assert path.read_text() == '"historical evidence"'
