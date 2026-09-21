#!/usr/bin/env python3
"""Fit the fixed retrospective study offline and retain its exact input tables."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import pandas as pd
from fastapi import HTTPException
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.analysis.demand_sensitivity import DemandSensitivityConfig, analyze_area  # noqa: E402
from app_core.ingestion.models import AREAS  # noqa: E402
from backend import data  # noqa: E402
from backend.forecast_jobs import capture_execution_context  # noqa: E402
from backend.sensitivity import artifact_path  # noqa: E402


def _sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def load_area(area: str, config: DemandSensitivityConfig) -> tuple[pd.DataFrame, dict]:
    """Use bounded published-snapshot reads; no upstream fetch or imputation."""
    start = pd.Timestamp(config.start, tz="UTC")
    end = pd.Timestamp(config.end, tz="UTC")
    cursor = start
    chunks = []
    sources = []
    while cursor < end:
        stop = min(cursor + pd.Timedelta(days=365), end)
        energy = data.energy_frame(area, cursor, stop, kind="consumption", groups=["household"])
        weather = data.weather_frame(area, cursor, stop)
        if energy["timestamp"].duplicated().any() or weather["time"].duplicated().any():
            raise ValueError(f"{area}: duplicate hourly inputs")
        if not energy["unit"].eq("kWh").all():
            raise ValueError(f"{area}: household demand units must be kWh")
        e = energy.set_index("timestamp")["value"].where(energy.set_index("timestamp")["quality"].eq("ok"))
        w = weather.set_index("time")["temperature_2m (°C)"]
        grid = pd.date_range(cursor, stop, freq="h", inclusive="left")
        chunks.append(pd.DataFrame({"demand": e.reindex(grid), "temperature": w.reindex(grid)}))
        sources.append({"energy": energy.attrs.get("provenance", {}), "weather": weather.attrs.get("provenance", {})})
        cursor = stop
    versions = {source["energy"].get("version") for source in sources}
    if len(versions) != 1:
        raise ValueError(f"{area}: energy snapshot changed during loading; retry with a stable snapshot")
    return pd.concat(chunks).rename_axis("time"), {"chunks": sources, "spatialMeaning": "Fixed city proxy, not an area-average weather field."}


def publish_new(path: Path, study: dict) -> None:
    """Publish a complete immutable file without overwriting any older study."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".sensitivity-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(study, handle, allow_nan=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def run_study(output: Path, *, input_dir: Path | None = None, areas: list[str] | None = None) -> dict:
    output = output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"{output} already exists; select a new --output to preserve prior evidence")
    chosen = areas or list(AREAS)
    if len(set(chosen)) != len(chosen) or any(area not in AREAS for area in chosen):
        raise ValueError("Choose unique areas from NO1–NO5")
    config = DemandSensitivityConfig()
    protocol = asdict(config)
    execution = capture_execution_context()
    execution["runnerSha256"] = _sha(Path(__file__))
    input_manifest = None
    if input_dir is not None:
        input_dir = input_dir.expanduser().resolve()
        input_manifest = json.loads((input_dir / "manifest.json").read_text())
        if input_manifest["protocol"] != protocol:
            raise ValueError("Retained inputs use a different protocol")
    data_mode = input_manifest["dataMode"] if input_manifest else ("fixture" if os.environ.get("ENERGY_DATA_MODE") == "fixture" else "observed")
    inputs = output.parent / f"{output.stem}-inputs"
    inputs.mkdir(parents=True, exist_ok=False)
    manifest = {"protocol": protocol, "dataMode": data_mode, "areas": {}}
    # This record exists before any scores are inspected.
    (inputs / "protocol.json").write_text(json.dumps({"protocol": protocol, "execution": execution}, indent=2) + "\n")
    results = []
    started = time.monotonic()
    with threadpool_limits(limits=1):
        for area in chosen:
            print(f"Preparing {area}…", flush=True)
            try:
                if input_dir is None:
                    frame, sources = load_area(area, config)
                    retained = inputs / f"{area}.csv"
                    frame.to_csv(retained, index_label="time")
                else:
                    entry = input_manifest["areas"].get(area)
                    if entry is None:
                        raise ValueError(f"{area}: no retained inputs")
                    source_path = input_dir / f"{area}.csv"
                    if _sha(source_path) != entry["sha256"]:
                        raise ValueError(f"{area}: retained input checksum mismatch")
                    retained = inputs / f"{area}.csv"
                    retained.write_bytes(source_path.read_bytes())
                    sources = entry["sources"]
                # Initial fitting and replays both read the same serialized table.
                frame = pd.read_csv(retained, float_precision="round_trip")
                frame["time"] = pd.to_datetime(frame["time"], utc=True)
                frame = frame.set_index("time")
                entry = {"file": retained.name, "sha256": _sha(retained), "sources": sources}
                manifest["areas"][area] = entry
                result = analyze_area(frame, area, config)
                result["metadata"]["input"] = entry
                results.append(result)
                print(f"{area}: selected {result['selectedModel']}; {result['splits']['test']['observedHours']} evaluation pairs", flush=True)
            except (ValueError, HTTPException, OSError) as exc:
                reason = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
                results.append({"area": area, "status": "unavailable", "reason": reason})
                print(f"{area}: unavailable — {reason}", flush=True)
    (inputs / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if not any(area["status"] == "ok" for area in results):
        raise ValueError("No area passed the study's data requirements; no result was published")
    study = {
        "schemaVersion": 1, "id": output.stem,
        "createdAt": datetime.now(timezone.utc).isoformat(), "dataMode": data_mode,
        "protocol": protocol, "areas": results,
        "metadata": {
            "execution": execution, "durationSeconds": time.monotonic() - started,
            "inputDirectory": inputs.name, "inputManifestSha256": _sha(inputs / "manifest.json"),
            "purpose": "Retrospective exploratory adjusted association; not a causal effect or operational forecast.",
            "sourceLabel": "Synthetic fixture — not observations" if data_mode == "fixture" else "Elhub household demand and Open-Meteo ERA5 city-proxy weather",
        },
    }
    publish_new(output, study)
    print(f"Saved {output} ({output.stat().st_size / 1024**2:.2f} MiB)", flush=True)
    return study


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=artifact_path())
    parser.add_argument("--input-dir", type=Path, help="Replay checksummed input CSVs from an earlier study")
    parser.add_argument("--areas", nargs="+", choices=list(AREAS), default=list(AREAS))
    args = parser.parse_args()
    run_study(args.output, input_dir=args.input_dir, areas=args.areas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
