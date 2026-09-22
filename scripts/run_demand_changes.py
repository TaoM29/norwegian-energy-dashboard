#!/usr/bin/env python3
"""Publish a frozen retrospective NO1 change study from saved Step 5 output."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tarfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.analysis.demand_changes import scan, summarize_daily  # noqa: E402
from backend.forecast_jobs import capture_execution_context  # noqa: E402
from scripts.run_demand_sensitivity import publish_new  # noqa: E402
from scripts.run_forecast_reliability import checksum, write_new_json  # noqa: E402
from scripts.validate_demand_changes import run_controls  # noqa: E402

DEFAULT_PROTOCOL = ROOT / "docs/protocols/demand-changes-20260922.json"
DEFAULT_SOURCE = ROOT / "data/analyses/demand-anomalies.json"
DEFAULT_OUTPUT = ROOT / "data/analyses/demand-changes.json"


def read_protocol(path: Path, source_path: Path) -> tuple[dict, dict]:
    protocol = json.loads(path.read_text())
    if protocol.get("schemaVersion") != 1 or protocol.get("evidenceStatus") != "exploratory" or protocol.get("area") != "NO1":
        raise ValueError("Frozen NO1 exploratory version-1 protocol required")
    if protocol.get("dataMode") != "observed" or checksum(source_path) != protocol.get("sourceSha256"):
        raise ValueError("Saved Step 5 source SHA-256 or data mode differs from frozen protocol")
    if protocol.get("config") != {"blockDays": 14, "minSegmentDays": 28, "bootstrapDraws": 999,
                                   "alpha": .05, "seed": 20260922}:
        raise ValueError("Primary detector settings differ from frozen protocol")
    if protocol.get("periods") != {"calibration": {"start": "2024-01-01", "endExclusive": "2025-01-01"},
                                    "test": {"start": "2025-01-01", "endExclusive": "2026-01-01"}}:
        raise ValueError("Frozen UTC periods required")
    source = json.loads(source_path.read_text())
    if source.get("schemaVersion") != 1 or source.get("id") != protocol.get("sourceId") or source.get("dataMode") != "observed":
        raise ValueError("Saved observed Step 5 artifact identity differs from protocol")
    areas = [area for area in source.get("areas", []) if area.get("area") == protocol["area"]]
    if len(areas) != 1 or areas[0].get("status") != "ok":
        raise ValueError("Exactly one successful saved NO1 area required")
    area = areas[0]
    if not isinstance(area.get("calibrationRows"), list) or not isinstance(area.get("rows"), list):
        raise ValueError("Saved NO1 calibration and test hourly rows required")
    return protocol, area


def _scan(calibration: list[dict], test: list[dict], config: dict, **changes) -> dict:
    settings = {"block_days": config["blockDays"], "min_segment_days": config["minSegmentDays"],
                "bootstrap_draws": config["bootstrapDraws"], "alpha": config["alpha"], "seed": config["seed"],
                "include_maxima": False}
    settings.update(changes)
    return scan(calibration, test, **settings)


def sensitivities(calibration: list[dict], test: list[dict], protocol: dict) -> list[dict]:
    spec = protocol["sensitivities"]
    config = protocol["config"]
    cases: list[tuple[str, str, list[dict], list[dict], dict]] = []
    for block in spec["blockDays"]:
        cases.append((f"block-{block}", f"{block}-day calibration blocks", calibration, test, {"block_days": block}))
    for minimum in spec["minSegmentDays"]:
        cases.append((f"segment-{minimum}", f"{minimum}-day minimum segments", calibration, test,
                      {"min_segment_days": minimum}))
    for window in spec["windows"]:
        subset = [row for row in test if window["start"] <= row["date"] < window["endExclusive"]]
        cases.append((window["id"], f"{window['start']} to {window['endExclusive']} UTC review", calibration, subset, {}))
    for window in spec["removedWindows"]:
        gap = deepcopy(test)
        for row in gap:
            if window["start"] <= row["date"] < window["endExclusive"]:
                row.update(complete=False, actual=None, expected=None, residual=None, okHours=0,
                           statusCounts={"sensitivity_removed": 24})
        cases.append((f"gap-{window['start']}", f"Remove {window['start']} to {window['endExclusive']}",
                      calibration, gap, {}))
    months = {month: np.mean([row["residual"] for row in calibration if row["complete"] and int(row["date"][5:7]) == month])
              for month in range(1, 13)}
    if any(not np.isfinite(mean) for mean in months.values()):
        raise ValueError("2024 month correction requires complete support in all months")
    adjusted_cal, adjusted_test = deepcopy(calibration), deepcopy(test)
    for rows in (adjusted_cal, adjusted_test):
        for row in rows:
            if row["complete"]:
                correction = months[int(row["date"][5:7])]
                row["expected"] += correction
                row["residual"] = row["actual"] - row["expected"]
    cases.append(("month-correction", "Fixed 2024 monthly residual correction", adjusted_cal, adjusted_test, {}))
    revision = spec["revisionPerturbation"]
    for fraction in revision["fractions"]:
        shifted = deepcopy(test)
        for row in shifted:
            if row["complete"] and revision["start"] <= row["date"] < revision["endExclusive"]:
                row["actual"] *= 1 + fraction
                row["residual"] = row["actual"] - row["expected"]
        cases.append((f"synthetic-actual-{fraction:+g}", f"Synthetic actual {fraction:+.0%} from {revision['start']}",
                      calibration, shifted, {}))
    results = []
    for identifier, label, cal, review, changes in cases:
        result = _scan(cal, review, config, **changes)
        candidate = result["candidate"]
        results.append({"id": identifier, "label": label, "status": result["status"],
                        "detected": result["detected"], "score": result["score"],
                        "pValue": result["pValue"], "thresholdApprox95": result["thresholdApprox95"],
                        "candidateDate": candidate["date"] if candidate else None,
                        "deltaResidualKwh": candidate["deltaResidualKwh"] if candidate else None,
                        "eligibleSplits": result["eligibleSplits"], "testRuns": result["testRuns"]})
    return results


def run_study(output: Path = DEFAULT_OUTPUT, source_path: Path = DEFAULT_SOURCE,
              protocol_path: Path = DEFAULT_PROTOCOL, *, controls_only: bool = False) -> dict:
    output = output.expanduser().resolve()
    source_path = source_path.expanduser().resolve()
    protocol_path = protocol_path.expanduser().resolve()
    if output.exists():
        raise FileExistsError("Study exists; choose a new --output to preserve evidence")
    protocol, area = read_protocol(protocol_path, source_path)
    cal_range, test_range = protocol["periods"]["calibration"], protocol["periods"]["test"]
    cal, cal_coverage = summarize_daily(area["calibrationRows"], **{"start": cal_range["start"],
                                  "end": cal_range["endExclusive"], "period": "calibration"})
    review, test_coverage = summarize_daily(area["rows"], **{"start": test_range["start"],
                                  "end": test_range["endExclusive"], "period": "test"})
    if cal_coverage["completeDays"] < 300 or len(review) != 365:
        raise ValueError("Observed study requires at least 300 complete calibration dates and a full 365-day review grid")
    began = time.monotonic()
    controls = run_controls(protocol["controls"], protocol["config"])
    if controls_only:
        return controls
    primary = _scan(cal, review, protocol["config"], include_maxima=True)
    variants = sensitivities(cal, review, protocol)
    evidence = output.parent / f"{output.stem}-evidence"
    evidence.mkdir(parents=True, exist_ok=False)
    write_new_json(evidence / "protocol.json", protocol)
    with (evidence / "source-step5.json").open("xb") as saved, source_path.open("rb") as source:
        import shutil
        shutil.copyfileobj(source, saved)
    write_new_json(evidence / "controlled-validation.json", controls)
    write_new_json(evidence / "sensitivities.json", {"cases": variants})
    execution = capture_execution_context()
    archive = evidence / "execution-sources.tar.gz"
    sources = sorted({*ROOT.glob("app_core/**/*.py"), *ROOT.glob("backend/*.py"),
                      ROOT / "scripts/validate_demand_changes.py", Path(__file__),
                      ROOT / "scripts/run_demand_sensitivity.py", ROOT / "scripts/run_forecast_reliability.py",
                      protocol_path, ROOT / "requirements.txt"})
    with tarfile.open(archive, "x:gz") as handle:
        for path in sources:
            handle.add(path, arcname=str(path.relative_to(ROOT)))
    execution.update(sourceArchiveSha256=checksum(archive), runnerSha256=checksum(Path(__file__)))
    write_new_json(evidence / "execution.json", execution)
    result = {"schemaVersion": 1, "id": protocol["id"], "createdAt": datetime.now(timezone.utc).isoformat(),
              "dataMode": "observed", "protocol": protocol, "area": "NO1", "status": "ok",
              "coverage": {"calibration": cal_coverage, "test": test_coverage},
              "dailyRows": cal + review, "primary": primary, "sensitivities": variants,
              "controlledValidation": {"specification": controls["specification"], "summary": controls["summary"],
                                       "casesFile": "controlled-validation.json"},
              "metadata": {"inputSha256": checksum(source_path), "sourceId": protocol["sourceId"],
                           "evidenceDirectory": evidence.name, "execution": execution,
                           "durationSeconds": time.monotonic() - began,
                           "interpretation": "Retrospective exploratory change candidate; not a live alert, causal claim, or confirmed abrupt break."}}
    publish_new(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--controls-only", action="store_true", help="Run frozen synthetic controls without publishing observed outputs")
    args = parser.parse_args()
    result = run_study(args.output, args.source, args.protocol, controls_only=args.controls_only)
    print(json.dumps({"controls": len(result["cases"])} if args.controls_only else
                     {"output": str(args.output), "candidate": result["primary"]["candidate"]["date"] if result["primary"]["candidate"] else None}))


if __name__ == "__main__":
    main()
