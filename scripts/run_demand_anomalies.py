#!/usr/bin/env python3
"""Fit and validate the frozen retrospective anomaly study from retained inputs."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tarfile
import time

import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.analysis.demand_anomalies import DemandAnomalyConfig, analyze_area
from backend.demand_anomalies import artifact_path
from backend.forecast_jobs import capture_execution_context
from scripts.run_demand_sensitivity import publish_new
from scripts.run_forecast_reliability import checksum, write_new_json
from scripts.validate_demand_anomalies import run_controls

DEFAULT_PROTOCOL = ROOT / "docs/protocols/demand-anomalies-20260922.json"
DEFAULT_INPUTS = ROOT / "data/analyses/demand-sensitivity-inputs"


def read_protocol(path: Path, input_dir: Path) -> tuple[dict, dict]:
    protocol = json.loads(path.read_text())
    if protocol.get("schemaVersion") != 1 or protocol.get("evidenceStatus") != "exploratory":
        raise ValueError("A version-1 exploratory protocol is required")
    config = DemandAnomalyConfig(**protocol["config"])
    if asdict(config) != protocol["config"]:
        raise ValueError("Every model setting must be explicit in the frozen protocol")
    if protocol["areas"] != ["NO1", "NO2", "NO3", "NO4", "NO5"]:
        raise ValueError("The frozen observed study covers all five areas")
    if checksum(input_dir / "manifest.json") != protocol["inputManifestSha256"]:
        raise ValueError("Retained input manifest differs from the frozen Step 1 inputs")
    manifest = json.loads((input_dir / "manifest.json").read_text())
    for area in protocol["areas"]:
        entry = manifest["areas"][area]
        if entry["file"] != f"{area}.csv" or checksum(input_dir / entry["file"]) != entry["sha256"]:
            raise ValueError(f"{area}: retained input checksum mismatch")
    return protocol, manifest


def run_study(output: Path, input_dir: Path = DEFAULT_INPUTS, protocol_path: Path = DEFAULT_PROTOCOL) -> dict:
    output = output.expanduser().resolve()
    input_dir = input_dir.expanduser().resolve()
    protocol_path = protocol_path.expanduser().resolve()
    if output.exists():
        raise FileExistsError("Study exists; choose a new --output to preserve evidence")
    protocol, manifest = read_protocol(protocol_path, input_dir)
    config = DemandAnomalyConfig(**protocol["config"])
    evidence = output.parent / f"{output.stem}-evidence"
    evidence.mkdir(parents=True, exist_ok=False)
    write_new_json(evidence / "protocol.json", protocol)
    write_new_json(evidence / "input-manifest.json", manifest)
    execution = capture_execution_context()
    sources = sorted({*ROOT.glob("app_core/**/*.py"), *ROOT.glob("backend/*.py"),
                      ROOT / "scripts/run_demand_sensitivity.py", ROOT / "scripts/run_forecast_reliability.py",
                      ROOT / "scripts/validate_demand_anomalies.py", Path(__file__), protocol_path,
                      ROOT / "requirements.txt"})
    archive = evidence / "execution-sources.tar.gz"
    with tarfile.open(archive, "x:gz") as handle:
        for source in sources:
            handle.add(source, arcname=str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else "external-protocol.json")
    execution["sourceArchiveSha256"] = checksum(archive)
    execution["runnerSha256"] = checksum(Path(__file__))
    write_new_json(evidence / "execution.json", execution)
    started = time.monotonic()
    results = []
    with threadpool_limits(limits=1):
        controls = run_controls(evidence / "controls", config, protocol["syntheticValidation"])
        write_new_json(evidence / "controlled-validation.json", controls)
        for area in protocol["areas"]:
            print(f"Fitting retrospective study for {area}", flush=True)
            frame = pd.read_csv(input_dir / f"{area}.csv", float_precision="round_trip")
            frame["time"] = pd.to_datetime(frame["time"], utc=True)
            try:
                result = analyze_area(frame.set_index("time"), area, config)
                print(f"{area}: {result['summary']}", flush=True)
                results.append(result)
            except ValueError as error:
                results.append({"area": area, "status": "unavailable", "reason": str(error)})
    if not any(area["status"] == "ok" for area in results):
        raise ValueError("No area has adequate support; evidence retained, no study published")
    study = {"schemaVersion": 1, "id": protocol["id"], "createdAt": datetime.now(timezone.utc).isoformat(),
             "dataMode": manifest["dataMode"], "protocol": protocol, "areas": results,
             "controlledValidation": controls,
             "metadata": {"execution": execution, "durationSeconds": time.monotonic() - started,
                          "inputManifestSha256": checksum(input_dir / "manifest.json"),
                          "inputDirectory": str(input_dir.relative_to(ROOT)) if input_dir.is_relative_to(ROOT) else str(input_dir),
                          "evidenceDirectory": evidence.name, "sourceLabel": "Elhub household demand and ERA5 city-proxy temperature",
                          "purpose": protocol["purpose"]}}
    publish_new(output, study)
    print(f"Saved {output}", flush=True)
    return study


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=artifact_path())
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args()
    run_study(args.output, args.input_dir, args.protocol)


if __name__ == "__main__":
    main()
