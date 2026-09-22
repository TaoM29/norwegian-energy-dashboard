#!/usr/bin/env python3
"""Independently audit saved Step 8 evidence without importing its implementation.

Daily aggregation uses Python's compensated summation. Every observed and
bootstrap split is scored from direct segment means, without cumulative sums.
This verifies arithmetic and reproducibility, not statistical calibration.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def equal(actual, expected, label: str) -> None:
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys(), (label, "dictionary keys")
        for key in expected:
            equal(actual[key], expected[key], f"{label}.{key}")
    elif isinstance(expected, list):
        assert len(actual) == len(expected), (label, "length")
        for index, (left, right) in enumerate(zip(actual, expected)):
            equal(left, right, f"{label}[{index}]")
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        assert math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-8), (label, actual, expected)
    else:
        assert actual == expected, (label, actual, expected)


def aggregate(rows: list[dict], year: int, period: str) -> tuple[list[dict], dict]:
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    stop = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    hours = {}
    for row in rows:
        stamp = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
        assert stamp.utcoffset() == timedelta(0) and not (stamp.minute or stamp.second or stamp.microsecond)
        assert start <= stamp < stop and stamp not in hours
        hours[stamp] = row
    days, all_status = [], Counter()
    for offset in range((stop - start).days):
        date = start + timedelta(days=offset)
        entries, status = [], Counter()
        for hour in range(24):
            row = hours.get(date + timedelta(hours=hour))
            state = "missing_row" if row is None else row["status"]
            if state == "ok":
                triple = [row[key] for key in ("actual", "expected", "residual")]
                assert all(isinstance(v, (int, float)) and math.isfinite(v) for v in triple)
                equal(triple[0] - triple[1], triple[2], "hourly residual")
                entries.append(triple)
            status[state] += 1
        all_status.update(status)
        complete = len(entries) == 24
        means = [math.fsum(row[i] for row in entries) / 24 for i in range(3)] if complete else [None] * 3
        days.append(dict(date=date.date().isoformat(), period=period, actual=means[0], expected=means[1],
                         residual=means[2], okHours=status["ok"], expectedHours=24,
                         statusCounts=dict(status), complete=complete))
    complete = sum(row["complete"] for row in days)
    return days, dict(expectedDays=len(days), completeDays=complete, incompleteDays=len(days) - complete,
                      expectedHours=len(days) * 24, okHours=all_status["ok"], statusCounts=dict(all_status))


def distribution(rows: list[dict]) -> dict:
    values = [row["residual"] for row in rows]
    return dict(start=rows[0]["date"],
                endExclusive=(datetime.fromisoformat(rows[-1]["date"]) + timedelta(days=1)).date().isoformat(),
                days=len(rows), meanActual=math.fsum(row["actual"] for row in rows) / len(rows),
                meanExpected=math.fsum(row["expected"] for row in rows) / len(rows),
                meanResidual=math.fsum(values) / len(values), medianResidual=float(np.median(values)),
                q1Residual=float(np.quantile(values, .25)), q3Residual=float(np.quantile(values, .75)),
                residualDistribution=sorted(values))


def recompute(cal: list[dict], review: list[dict], block: int = 14, minimum: int = 28,
              seed: int = 20260922, draws: int = 999) -> dict:
    values = np.array([r["residual"] if r["complete"] else np.nan for r in cal], dtype=float)
    finite = values[np.isfinite(values)]
    scale = math.sqrt(math.fsum((x - finite.mean()) ** 2 for x in finite) / (len(finite) - 1))
    centered = values - finite.mean()
    starts = [i for i in range(len(values) - block + 1) if np.isfinite(values[i:i + block]).all()]
    runs = []
    begin = None
    for i in range(len(review) + 1):
        complete = i < len(review) and review[i]["complete"]
        if complete and begin is None:
            begin = i
        if not complete and begin is not None:
            runs.append((begin, i))
            begin = None
    splits = [(a, k, b) for a, b in runs for k in range(a + minimum, b - minimum + 1)]
    assert splits, "No eligible splits in audited scenario"
    observed = np.array([r["residual"] if r["complete"] else np.nan for r in review])
    choices = np.random.default_rng(seed).choice(starts, size=(draws, math.ceil(len(review) / block)))
    simulated = np.stack([np.concatenate([centered[i:i + block] for i in sequence])[:len(review)]
                          for sequence in choices])
    maxima = np.full(draws, -np.inf)
    best_score, best = -np.inf, None
    for a, k, b in splits:
        weight = math.sqrt((k - a) * (b - k) / (b - a)) / scale
        score = weight * abs(observed[k:b].mean() - observed[a:k].mean())
        if score > best_score:
            best_score, best = float(score), (a, k, b)
        # Direct segment means independently check the production prefix-sum formula.
        maxima = np.maximum(maxima, weight * np.abs(simulated[:, k:b].mean(axis=1) - simulated[:, a:k].mean(axis=1)))
    a, k, b = best
    before, after = distribution(review[a:k]), distribution(review[k:b])
    delta = after["meanResidual"] - before["meanResidual"]
    p = (1 + sum(value >= best_score for value in maxima)) / (draws + 1)
    return dict(status="ok", detected=bool(p <= .05), score=best_score, pValue=float(p),
                thresholdApprox95=float(sorted(maxima)[949]),
                candidate=dict(date=review[k]["date"], before=before, after=after,
                               deltaResidualKwh=delta, standardizedDelta=delta / scale),
                calibrationScaleKwh=scale, eligibleSplits=len(splits),
                testRuns=[dict(startIndex=a, endExclusiveIndex=b, days=b-a) for a, b in runs],
                calibrationBlockStarts=starts, bootstrapMaxima=maxima.tolist())


def variants(cal: list[dict], review: list[dict], spec: dict):
    for block in spec["blockDays"]:
        yield f"block-{block}", cal, review, dict(block=block)
    for minimum in spec["minSegmentDays"]:
        yield f"segment-{minimum}", cal, review, dict(minimum=minimum)
    for window in spec["windows"]:
        yield window["id"], cal, [r for r in review if window["start"] <= r["date"] < window["endExclusive"]], {}
    for window in spec["removedWindows"]:
        altered = deepcopy(review)
        for row in altered:
            if window["start"] <= row["date"] < window["endExclusive"]:
                row["complete"] = False
        yield f"gap-{window['start']}", cal, altered, {}
    correction = {}
    for month in range(1, 13):
        selected = [r["residual"] for r in cal if r["complete"] and int(r["date"][5:7]) == month]
        correction[month] = math.fsum(selected) / len(selected)
    adjusted = deepcopy([cal, review])
    for group in adjusted:
        for row in group:
            if row["complete"]:
                row["expected"] += correction[int(row["date"][5:7])]
                row["residual"] = row["actual"] - row["expected"]
    yield "month-correction", *adjusted, {}
    revision = spec["revisionPerturbation"]
    for fraction in revision["fractions"]:
        altered = deepcopy(review)
        for row in altered:
            if row["complete"] and revision["start"] <= row["date"] < revision["endExclusive"]:
                row["actual"] *= 1 + fraction
                row["residual"] = row["actual"] - row["expected"]
        yield f"synthetic-actual-{fraction:+g}", cal, altered, {}


def audit(study_path: Path, output: Path) -> dict:
    study = json.loads(study_path.read_text())
    evidence = study_path.parent / study["metadata"]["evidenceDirectory"]
    source_path = evidence / "source-step5.json"
    controls_path = evidence / "controlled-validation.json"
    protocol = study["protocol"]
    assert digest(source_path) == protocol["sourceSha256"] == study["metadata"]["inputSha256"]
    equal(json.loads((evidence / "protocol.json").read_text()), protocol, "saved protocol")
    assert digest(evidence / "execution-sources.tar.gz") == study["metadata"]["execution"]["sourceArchiveSha256"]
    source = json.loads(source_path.read_text())
    area = next(row for row in source["areas"] if row["area"] == "NO1")
    cal, cal_coverage = aggregate(area["calibrationRows"], 2024, "calibration")
    review, review_coverage = aggregate(area["rows"], 2025, "test")
    equal(cal + review, study["dailyRows"], "dailyRows")
    equal(dict(calibration=cal_coverage, test=review_coverage), study["coverage"], "coverage")
    primary = recompute(cal, review)
    equal(primary, study["primary"], "primary")
    print("Primary daily aggregation, direct-mean scan, 999 maxima and effects verified", flush=True)
    sensitivity_results = []
    for identifier, adjusted_cal, adjusted_review, options in variants(cal, review, protocol["sensitivities"]):
        actual = recompute(adjusted_cal, adjusted_review, **options)
        saved = next(item for item in study["sensitivities"] if item["id"] == identifier)
        for key in ("status", "detected", "score", "pValue", "thresholdApprox95", "eligibleSplits", "testRuns"):
            equal(actual[key], saved[key], f"{identifier}.{key}")
        equal(actual["candidate"]["date"], saved["candidateDate"], f"{identifier}.date")
        equal(actual["candidate"]["deltaResidualKwh"], saved["deltaResidualKwh"], f"{identifier}.effect")
        sensitivity_results.append(dict(id=identifier, candidateDate=actual["candidate"]["date"],
                                        pValue=actual["pValue"], verified=True))
    assert len(sensitivity_results) == len(study["sensitivities"]) == 11
    controls = json.loads(controls_path.read_text())
    equal(controls["summary"], study["controlledValidation"]["summary"], "embedded controls")
    equal(controls["specification"], protocol["controls"], "control specification")
    assert len(controls["cases"]) == 3600
    for item in controls["cases"]:
        assert item["pairSeed"] != item["bootstrapSeed"]
        assert item["detected"] == (item["pValue"] <= .05)
        assert item["detected"] == (item["score"] > item["thresholdApprox95"])
        equal((datetime(2025, 1, 1) + timedelta(days=item["candidateIndex"])).date().isoformat(),
              item["candidateDate"], "control date")
    for summary in controls["summary"]:
        records = [r for r in controls["cases"] if r["rho"] == summary["rho"] and r["scenario"] == summary["scenario"]]
        assert len(records) == 200 and sorted(r["replication"] for r in records) == list(range(200))
        hits = [r for r in records if r["detected"]]
        n, count = len(records), len(hits)
        equal(count, summary["detections"], "control detections")
        equal(count / n, summary["detectionRate"], "control rate")
        if summary["scenario"] == "no-change":
            equal(count / n, summary["falseAlarmRate"], "false alarm rate")
        z, p = 1.959963984540054, count / n
        center = (p + z*z/(2*n)) / (1 + z*z/n)
        half = z / (1 + z*z/n) * math.sqrt(p*(1-p)/n + z*z/(4*n*n))
        equal([max(0., center-half), min(1., center+half)], summary["detectionWilson95"], "Wilson interval")
        errors = [abs(r["candidateIndex"] - protocol["controls"]["shiftIndex"]) for r in hits] if summary["scenario"].startswith("step-") else []
        close = sum(error <= 14 for error in errors)
        equal(float(np.median(errors)) if errors else None, summary["medianAbsoluteCandidateIndexErrorAmongDetections"], "localization median")
        equal(close, summary["within14DaysAmongDetections"], "conditional localization count")
        equal(close, summary["within14DaysOfAllReplications"], "unconditional localization count")
        equal(close/len(hits) if errors else None, summary["within14DaysRateAmongDetections"], "conditional localization rate")
        equal(close/n, summary["within14DaysRateAllReplications"], "unconditional localization rate")
    report = dict(status="passed", createdAt=datetime.now(timezone.utc).isoformat(),
                  checks=["source, protocol and source-archive identities", "731 daily rows and coverage",
                          "310 primary split scores through direct segment means", "999 seeded bootstrap maxima",
                          "primary date, threshold, exceedance, effect and distributions", "all 11 sensitivity cases",
                          "3600 control decision/date/seed records", "18 control count/rate/Wilson/localization summaries"],
                  tolerance=dict(relative=1e-10, absolute=1e-8),
                  hashes=dict(auditScriptSha256=digest(Path(__file__)), studySha256=digest(study_path),
                              sourceSha256=digest(source_path), controlsSha256=digest(controls_path)),
                  primary=dict(candidateDate=primary["candidate"]["date"], score=primary["score"],
                               pValue=primary["pValue"], threshold=primary["thresholdApprox95"],
                               deltaResidualKwh=primary["candidate"]["deltaResidualKwh"]),
                  sensitivities=sensitivity_results,
                  noChangeControls=[s for s in controls["summary"] if s["scenario"] == "no-change"],
                  limitation="Independent arithmetic audit; does not establish valid false-alarm calibration. Control simulations are aggregated, not regenerated.")
    with output.open("x") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, default=ROOT / "data/analyses/demand-changes.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/analyses/demand-changes-evidence/independent-audit.json")
    args = parser.parse_args()
    result = audit(args.study, args.output)
    print(json.dumps(dict(status=result["status"], checks=len(result["checks"]), output=str(args.output))))


if __name__ == "__main__":
    main()
