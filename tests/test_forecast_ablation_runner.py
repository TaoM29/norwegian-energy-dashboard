"""Ablation protocol integrity before any expensive fitting."""
import json
import pytest

from scripts import run_forecast_ablation as runner


def _bundle(tmp_path):
    protocol = json.loads(runner.DEFAULT_PROTOCOL.read_text())
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    parent = runner.ROOT / "docs/protocols" / protocol["parentProtocol"]
    (inputs / "protocol.json").write_bytes(parent.read_bytes())
    (inputs / "manifest.json").write_text('{"fixture": true}\n')
    protocol["inputManifestSha256"] = runner.checksum(inputs / "manifest.json")
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol))
    return path, inputs, protocol


def test_frozen_protocol_reuses_parent_policy_and_exact_nested_features(tmp_path):
    path, inputs, expected = _bundle(tmp_path)
    protocol, parent = runner.read_protocol(path, inputs)
    assert protocol == expected
    assert [len(v["features"]["columns"]) for v in protocol["variants"]] == [9, 17, 29]
    for key in ("holdout_origins", "calibration_origins", "validation_origins", "ridge_alphas"):
        assert protocol["config"][key] == parent["config"][key]


@pytest.mark.parametrize("change,match", [
    ("manifest", "manifest differs"), ("feature", "Feature definitions differ"),
    ("lag", "Feature definitions differ"), ("alpha", "preserve the Step 2"),
    ("contrast", "sequential contrasts"),
])
def test_rejects_protocol_drift_before_fitting(tmp_path, change, match):
    path, inputs, protocol = _bundle(tmp_path)
    if change == "manifest":
        (inputs / "manifest.json").write_text("changed")
    elif change == "feature":
        protocol["variants"][0]["features"]["columns"].append("weather_temperature_2m_available")
    elif change == "lag":
        protocol["config"]["weather_publication_lag_hours"] = 119
    elif change == "alpha":
        protocol["config"]["ridge_alphas"] = [0.1, 1.0, 20.0]
    else:
        protocol["contrasts"][1]["fromModel"] = "ridge_calendar"
    path.write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match=match):
        runner.read_protocol(path, inputs)


def test_existing_result_cannot_be_replaced_or_trigger_fits(tmp_path, monkeypatch):
    path, inputs, protocol = _bundle(tmp_path)
    store = runner.ForecastStore(tmp_path / "artifacts")
    target = store.results_dir / f"{protocol['id']}.json"
    target.write_text("original evidence")
    monkeypatch.setattr(runner, "load_inputs", lambda *_: pytest.fail("must stop before inputs/fits"))
    with pytest.raises(FileExistsError):
        runner.run_study(path, inputs, tmp_path / "runs", tmp_path / "artifacts")
    assert target.read_text() == "original evidence"


def test_replay_identity_is_path_safe(tmp_path):
    path, inputs, _ = _bundle(tmp_path)
    with pytest.raises(ValueError, match="identity"):
        runner.run_study(path, inputs, tmp_path / "runs", tmp_path / "artifacts", "../overwrite")
