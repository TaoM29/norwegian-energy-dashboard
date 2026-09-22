#!/usr/bin/env python3
"""Execute a frozen forecast protocol from checksummed, retained hourly inputs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.analysis import forecast_evaluation as engine  # noqa: E402
from backend.forecast_jobs import (  # noqa: E402
    ForecastStore, capture_execution_context, publish_result_artifact,
)

DEFAULT_PROTOCOL = ROOT / "docs/protocols/forecast-reliability-20260921.json"


def checksum(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_new_json(path: Path, value: dict) -> None:
    with path.open("x") as handle:
        json.dump(engine._jsonable(value), handle, indent=2, allow_nan=False)
        handle.write("\n")


def read_protocol(path: Path) -> dict:
    protocol = json.loads(path.read_text())
    if protocol.get("schemaVersion") != 1 or protocol.get("evidenceStatus") != "exploratory":
        raise ValueError("This runner requires a version-1 exploratory study protocol")
    identifier = protocol.get("id", "")
    if not identifier or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in identifier):
        raise ValueError("Protocol id must contain lowercase letters, digits, hyphens or underscores")
    config = engine.validate_evaluation_config(protocol["config"])
    # Version-1 protocols predate feature ablation and froze the full feature set.
    # Preserve those original bytes and interpretation when replaying them.
    frozen_config = dict(protocol["config"])
    frozen_config.setdefault("feature_set", "calendar_demand_weather")
    if config != frozen_config:
        raise ValueError("Protocol must explicitly freeze every normalized model setting")
    origins = pd.to_datetime(config["holdout_origins"], utc=True)
    if len(origins) < 2 or len(set(np.diff(origins.asi8))) != 1:
        raise ValueError("Reliability study requires a regular evaluation-origin schedule")
    uncertainty = protocol["uncertainty"]
    if uncertainty != {"blockLengths": [2, 4, 8], "resamples": 2000, "seed": 20260921}:
        raise ValueError("Unsupported uncertainty protocol; version the method before changing it")
    return protocol


def coverage_report(energy: pd.DataFrame, weather: pd.DataFrame, config: dict) -> list[dict]:
    """Inspect availability only; no fitting or forecast-error calculations."""
    config = engine.validate_evaluation_config(config)
    rows = []
    for area in config["areas"]:
        prepared = engine._prepare_area(energy, weather, area)
        y, w = prepared.energy, prepared.weather
        stages = {}
        for stage in ("validation_origins", "calibration_origins", "holdout_origins"):
            origins = []
            for value in config[stage]:
                issue = pd.Timestamp(value)
                target = y.reindex(pd.date_range(issue, periods=config["horizon_hours"], freq="h"))
                cutoff = engine._availability_cutoff(issue, config["energy_publication_lag_hours"])
                history = y.reindex(pd.date_range(issue - pd.Timedelta(days=config["train_window_days"]), cutoff, freq="h"))
                features = engine._build_origin_features(y, w, issue, config)
                origins.append({
                    "origin": value, "targetHours": int(np.isfinite(target).sum()),
                    "expectedTargetHours": len(target), "eligibleTrainingHours": int(np.isfinite(history).sum()),
                    "expectedTrainingHours": len(history), "trainingCutoff": cutoff.isoformat(),
                    "missingFeatureCells": int((~np.isfinite(features)).sum().sum()),
                })
            stages[stage] = origins
        rows.append({
            "area": area, "start": y.index.min().isoformat(), "endInclusive": y.index.max().isoformat(),
            "gridHours": len(y), "energyHours": int(np.isfinite(y).sum()),
            "weatherCompleteHours": int(np.isfinite(w).all(axis=1).sum()), "stages": stages,
        })
    return rows


def prepare_inputs(directory: Path, protocol: dict) -> dict:
    """Freeze task inputs once; an existing bundle is never overwritten."""
    directory.mkdir(parents=True, exist_ok=False)
    write_new_json(directory / "protocol.json", protocol)
    energy, weather, provenance = engine._load_frames(protocol["config"])
    versions = {chunk["version"] for source in provenance["areas"].values() for chunk in source["energy"]}
    if len(versions) != 1:
        raise ValueError("Energy snapshot changed during loading; prepare a new stable input bundle")
    manifest = {
        "schemaVersion": 1, "createdAt": datetime.now(timezone.utc).isoformat(),
        "protocolSha256": checksum(directory / "protocol.json"),
        "dataMode": "fixture" if os.environ.get("ENERGY_DATA_MODE") == "fixture" else "observed",
        "sources": provenance, "areas": {},
    }
    for area in protocol["config"]["areas"]:
        e = energy.loc[energy["area"].eq(area)].copy()
        w = weather.loc[weather["area"].eq(area)].copy()
        if e["timestamp"].duplicated().any() or w["time"].duplicated().any():
            raise ValueError(f"{area}: duplicate task input timestamps")
        if not e["unit"].eq("kWh").all():
            raise ValueError(f"{area}: household energy units must be kWh")
        # Preserve flagged observations as missing, never zero or interpolated.
        e.loc[~e["quality"].eq("ok"), "value"] = np.nan
        y, weather_grid = engine.regularize_hourly_frames(e, w)
        frame = weather_grid.assign(value=y).rename_axis("timestamp")
        path = directory / f"{area}.csv"
        frame.to_csv(path)
        manifest["areas"][area] = {"file": path.name, "sha256": checksum(path), "rows": len(frame)}
    write_new_json(directory / "manifest.json", manifest)
    # Fit and replay both parse these identical bytes, including float precision.
    retained_energy, retained_weather, _ = load_inputs(directory, protocol)
    write_new_json(directory / "coverage.json", {"areas": coverage_report(retained_energy, retained_weather, protocol["config"])})
    return manifest


def load_inputs(directory: Path, protocol: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    manifest = json.loads((directory / "manifest.json").read_text())
    retained_protocol = directory / "protocol.json"
    if json.loads(retained_protocol.read_text()) != protocol or checksum(retained_protocol) != manifest["protocolSha256"]:
        raise ValueError("Retained protocol differs from the requested frozen protocol")
    energy_parts, weather_parts = [], []
    for area in protocol["config"]["areas"]:
        entry = manifest["areas"][area]
        path = directory / f"{area}.csv"
        if entry["file"] != path.name or checksum(path) != entry["sha256"]:
            raise ValueError(f"{area}: retained input checksum mismatch")
        frame = pd.read_csv(path, float_precision="round_trip")
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        if frame["timestamp"].duplicated().any() or len(frame) != entry["rows"]:
            raise ValueError(f"{area}: invalid retained input grid")
        frame["area"] = area
        energy_parts.append(frame[["timestamp", "area", "value"]])
        weather_parts.append(frame[["timestamp", "area", *engine.WEATHER_COLUMNS]])
    return pd.concat(energy_parts, ignore_index=True), pd.concat(weather_parts, ignore_index=True), manifest


def run_study(protocol_path: Path, input_dir: Path, artifact_root: Path | None = None, result_id: str | None = None) -> dict:
    from app_core.analysis.forecast_reliability import build_reliability_report

    protocol = read_protocol(protocol_path)
    identifier = result_id or protocol["id"]
    store = ForecastStore(artifact_root)
    if (store.results_dir / f"{identifier}.json").exists():
        raise FileExistsError(f"Result {identifier} already exists; choose a new --result-id for a replay")
    energy, weather, manifest = load_inputs(input_dir, protocol)
    execution = capture_execution_context()
    execution["runnerSha256"] = checksum(Path(__file__))
    started = time.monotonic()

    def progress(fraction: float, message: str) -> None:
        print(f"[{fraction:6.1%}] {message}", flush=True)

    with threadpool_limits(limits=1):
        payload = engine.evaluate_frames(energy, weather, protocol["config"], progress=progress)
    settings = protocol["uncertainty"]
    payload["reliability"] = build_reliability_report(
        payload, block_lengths=tuple(settings["blockLengths"]), resamples=settings["resamples"], seed=settings["seed"],
    )
    payload["title"] = protocol["label"]
    payload["metadata"].update({
        "studyProtocol": protocol, "datasetVersion": manifest["sources"],
        "retainedInputs": {"directory": str(input_dir.relative_to(ROOT)) if input_dir.is_relative_to(ROOT) else str(input_dir),
                           "manifestSha256": checksum(input_dir / "manifest.json"), "manifest": manifest},
        "inputCoverage": coverage_report(energy, weather, protocol["config"]),
        "dataMode": manifest["dataMode"],
        "sourceLabel": "Synthetic fixture — not observations" if manifest["dataMode"] == "fixture" else "Elhub household demand and ERA5 city-proxy weather · exploratory study",
    })
    payload["metadata"]["assumptions"]["evaluationStatus"] = protocol["interpretation"]
    result = publish_result_artifact(store, kind="evaluation", config=protocol["config"], payload=payload,
                                    duration_seconds=time.monotonic() - started, result_id=identifier, execution_context=execution)
    print(f"Saved {store.results_dir / (identifier + '.json')}", flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--input-dir", type=Path, help="Existing checksummed input bundle for fitting or replay")
    parser.add_argument("--prepare-only", action="store_true", help="Retain inputs and report coverage without fitting")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--result-id", help="New immutable result identity; required when replaying an existing result")
    args = parser.parse_args()
    protocol = read_protocol(args.protocol)
    inputs = (args.input_dir or ROOT / "data/analyses" / f"{protocol['id']}-inputs").expanduser().resolve()
    if args.input_dir is None:
        prepare_inputs(inputs, protocol)
        print(f"Retained inputs: {inputs}\nManifest SHA-256: {checksum(inputs / 'manifest.json')}", flush=True)
    elif args.prepare_only:
        parser.error("--prepare-only creates a new default input bundle; --input-dir selects an existing bundle")
    if not args.prepare_only:
        run_study(args.protocol, inputs, args.artifact_root, args.result_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
