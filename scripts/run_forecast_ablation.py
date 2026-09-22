#!/usr/bin/env python3
"""Run the frozen ridge ablation using the exact retained Step 2 input bytes."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tarfile
import time

from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.analysis import forecast_evaluation as engine
from backend.forecast_jobs import ForecastStore, capture_execution_context, publish_result_artifact
from scripts.run_forecast_reliability import checksum, load_inputs, write_new_json

DEFAULT_PROTOCOL = ROOT / "docs/protocols/forecast-ablation-20260922.json"
DEFAULT_INPUTS = ROOT / "data/analyses/step2-household-reliability-20260921-inputs"
FEATURE_SETS = ("calendar", "calendar_demand", "calendar_demand_weather")


def read_protocol(path: Path, input_dir: Path) -> tuple[dict, dict]:
    protocol = json.loads(path.read_text())
    if protocol.get("schemaVersion") != 1 or protocol.get("evidenceStatus") != "exploratory":
        raise ValueError("A version-1 exploratory ablation protocol is required")
    identifier = protocol.get("id", "")
    if not identifier or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in identifier):
        raise ValueError("Invalid protocol result identity")
    config = engine.validate_evaluation_config(protocol["config"])
    if config != protocol["config"] or config["models"] != ["seasonal_naive", "ridge"]:
        raise ValueError("Freeze every setting for the ridge and seasonal-reference evaluation")
    if config["feature_set"] != FEATURE_SETS[-1] or config["weather_mode"] != "historical_only":
        raise ValueError("The parent configuration must use all eligible historical features")
    if [item["featureSet"] for item in protocol["variants"]] != list(FEATURE_SETS):
        raise ValueError("The three nested feature sets must be in the frozen order")
    for variant in protocol["variants"]:
        expected = engine._feature_metadata({**config, "feature_set": variant["featureSet"]})
        if variant["features"] != expected or variant["model"] != "ridge_" + variant["featureSet"]:
            raise ValueError("Feature definitions differ from the frozen protocol")
    expected_contrasts = [("ridge_calendar", "ridge_calendar_demand"),
                          ("ridge_calendar_demand", "ridge_calendar_demand_weather")]
    if [(v["fromModel"], v["toModel"]) for v in protocol["contrasts"]] != expected_contrasts:
        raise ValueError("The two sequential contrasts must be frozen before fitting")
    if checksum(input_dir / "manifest.json") != protocol["inputManifestSha256"]:
        raise ValueError("Input manifest differs from the frozen Step 2 snapshot")
    parent = json.loads((input_dir / "protocol.json").read_text())
    parent_config = engine.validate_evaluation_config(parent["config"])
    parent_config["models"] = ["seasonal_naive", "ridge"]
    if config != parent_config or protocol["uncertainty"] != parent["uncertainty"]:
        raise ValueError("Step 4 must preserve the Step 2 dates, fitting, availability and uncertainty policy")
    return protocol, parent


def run_study(protocol_path: Path, input_dir: Path, run_dir: Path,
              artifact_root: Path | None = None, result_id: str | None = None) -> dict:
    protocol, parent = read_protocol(protocol_path, input_dir)
    identifier = result_id or protocol["id"]
    if not identifier or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in identifier):
        raise ValueError("Invalid result identity")
    store = ForecastStore(artifact_root)
    if (store.results_dir / f"{identifier}.json").exists():
        raise FileExistsError(f"Result {identifier} exists; choose a new --result-id")
    energy, weather, manifest = load_inputs(input_dir, parent)
    run_dir.mkdir(parents=True, exist_ok=False)
    write_new_json(run_dir / "protocol.json", protocol)
    execution = capture_execution_context()
    # Preserve source bytes before the first fit, even while UI work continues.
    source_paths = sorted({*ROOT.glob("app_core/**/*.py"), *ROOT.glob("backend/*.py"),
                           ROOT / "scripts/run_forecast_reliability.py", Path(__file__), protocol_path,
                           ROOT / "requirements.txt"})
    archive = run_dir / "execution-sources.tar.gz"
    with tarfile.open(archive, "x:gz") as handle:
        for source in source_paths:
            handle.add(source, arcname=str(source.relative_to(ROOT)))
    execution["ablationSourcesSha256"] = checksum(archive)
    execution["runnerSha256"] = checksum(Path(__file__))
    write_new_json(run_dir / "execution.json", {**execution, "startedAt": datetime.now(timezone.utc).isoformat()})
    started = time.monotonic()
    runs = {}
    with threadpool_limits(limits=1):
        for feature_set in FEATURE_SETS:
            config = {**deepcopy(protocol["config"]), "feature_set": feature_set}
            print(f"Starting {feature_set}", flush=True)
            def progress(fraction: float, message: str) -> None:
                print(f"[{feature_set} {fraction:6.1%}] {message}", flush=True)
            payload = engine.evaluate_frames(energy, weather, config, progress=progress)
            write_new_json(run_dir / f"{feature_set}.json", payload)
            runs[feature_set] = payload
    from app_core.analysis.forecast_ablation import combine_ablation_runs
    payload = combine_ablation_runs(runs, protocol)
    payload["title"] = protocol["label"]
    payload["metadata"].update({
        "studyProtocol": protocol, "datasetVersion": manifest["sources"],
        "retainedInputs": {"manifestSha256": checksum(input_dir / "manifest.json"), "manifest": manifest},
        "retainedVariantRuns": {"directory": str(run_dir.relative_to(ROOT)) if run_dir.is_relative_to(ROOT) else str(run_dir),
                                "sha256": {name: checksum(run_dir / f"{name}.json") for name in FEATURE_SETS}},
        "dataMode": manifest["dataMode"],
        "sourceLabel": "Synthetic fixture — not observations" if manifest["dataMode"] == "fixture"
                       else "Elhub household demand and ERA5 city-proxy weather · exploratory ridge ablation",
    })
    payload["metadata"].setdefault("assumptions", {})["evaluationStatus"] = protocol["interpretation"]
    result = publish_result_artifact(store, kind="evaluation", config=payload["config"], payload=payload,
                                    duration_seconds=time.monotonic() - started, result_id=identifier,
                                    execution_context=execution)
    print(f"Saved {store.results_dir / (identifier + '.json')}", flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--result-id")
    args = parser.parse_args()
    protocol, _ = read_protocol(args.protocol, args.input_dir)
    run_dir = args.run_dir or ROOT / "data/analyses" / f"{args.result_id or protocol['id']}-runs"
    run_study(args.protocol, args.input_dir, run_dir, args.artifact_root, args.result_id)


if __name__ == "__main__":
    main()
