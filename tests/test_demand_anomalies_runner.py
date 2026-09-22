import json

import pytest

from scripts import run_demand_anomalies as runner
from scripts.run_forecast_reliability import checksum


def test_input_manifest_and_area_bytes_are_pinned(tmp_path):
    protocol = json.loads(runner.DEFAULT_PROTOCOL.read_text())
    manifest = {"areas": {}}
    for area in protocol["areas"]:
        path = tmp_path / f"{area}.csv"
        path.write_text("time,demand,temperature\n")
        manifest["areas"][area] = {"file": path.name, "sha256": checksum(path)}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    protocol["inputManifestSha256"] = checksum(manifest_path)
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol))
    assert runner.read_protocol(path, tmp_path)[1] == manifest
    (tmp_path / "NO3.csv").write_text("changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        runner.read_protocol(path, tmp_path)
    manifest_path.write_text("changed")
    with pytest.raises(ValueError, match="manifest differs"):
        runner.read_protocol(path, tmp_path)


def test_existing_result_refused_before_reading_or_fitting(tmp_path, monkeypatch):
    output = tmp_path / "study.json"
    output.write_text("retained evidence")
    monkeypatch.setattr(runner, "read_protocol", lambda *args: pytest.fail("must not read inputs"))
    with pytest.raises(FileExistsError):
        runner.run_study(output)
    assert output.read_text() == "retained evidence"
