"""Independent seeded AR(1) no-change and known-shift detector controls."""
from __future__ import annotations

import math

import numpy as np

from app_core.analysis.demand_changes import scan


def _ar1(rng: np.random.Generator, count: int, rho: float, sd: float) -> np.ndarray:
    values = np.empty(count)
    values[0] = rng.normal(0, sd)
    innovations = rng.normal(0, sd * math.sqrt(1 - rho * rho), count - 1)
    for i, innovation in enumerate(innovations, 1):
        values[i] = rho * values[i - 1] + innovation
    return values


def _days(values: np.ndarray, year: int) -> list[dict]:
    from datetime import date, timedelta
    first = date(year, 1, 1)
    return [{"date": (first + timedelta(days=i)).isoformat(), "period": "control",
             "actual": float(v), "expected": 0., "residual": float(v),
             "complete": True, "okHours": 24, "expectedHours": 24, "statusCounts": {"ok": 24}}
            for i, v in enumerate(values)]


def wilson95(successes: int, n: int) -> list[float]:
    if n <= 0:
        raise ValueError("Wilson interval requires positive denominator")
    z = 1.959963984540054
    p = successes / n
    denominator = 1 + z*z/n
    mid = (p + z*z/(2*n)) / denominator
    radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return [0. if successes == 0 else max(0., mid-radius),
            1. if successes == n else min(1., mid+radius)]


def run_controls(specification: dict, config: dict) -> dict:
    """200 independent calibration/review pairs per rho; scenarios share test noise."""
    rng = np.random.default_rng(specification["seed"])
    cases = []
    summaries = []
    n = specification["replications"]
    shift_index = specification["shiftIndex"]
    review_count = specification["testDays"]
    if not (0 < shift_index < review_count):
        raise ValueError("Shift index must be inside test window")
    scenarios = [("no-change", 0.)] + [(f"step-{size:+g}", size) for size in specification["shiftSizes"]] + [("linear-drift", None)]
    for rho in specification["rhos"]:
        by_scenario: dict[str, list[dict]] = {name: [] for name, _ in scenarios}
        for replication in range(n):
            pair_seed = int(rng.integers(0, 2**63, dtype=np.int64))
            bootstrap_seed = int(rng.integers(0, 2**63, dtype=np.int64))
            pair_rng = np.random.default_rng(pair_seed)
            cal_noise = _ar1(pair_rng, specification["calibrationDays"], rho, specification["marginalSd"])
            review_noise = _ar1(pair_rng, review_count, rho, specification["marginalSd"])
            cal_days = _days(cal_noise, 2024)
            null_days = _days(review_noise, 2025)
            options = {"block_days": config["blockDays"], "min_segment_days": config["minSegmentDays"],
                       "bootstrap_draws": config["bootstrapDraws"], "alpha": config["alpha"],
                       "seed": bootstrap_seed, "include_maxima": True}
            baseline = scan(cal_days, null_days, **options)
            maxima = np.asarray(baseline["bootstrapMaxima"])
            for name, size in scenarios:
                if name == "no-change":
                    result = baseline
                else:
                    shifted = review_noise.copy()
                    if name == "linear-drift":
                        shifted += np.linspace(0, specification["linearDriftEnd"] * specification["marginalSd"], review_count)
                    else:
                        shifted[shift_index:] += size * specification["marginalSd"]
                    result = scan(cal_days, _days(shifted, 2025), **{**options, "include_maxima": False,
                                                                    "null_maxima": maxima})
                index = None if result["candidate"] is None else (np.datetime64(result["candidate"]["date"]) - np.datetime64("2025-01-01")).astype(int).item()
                record = {"rho": rho, "replication": replication, "pairSeed": pair_seed,
                          "bootstrapSeed": bootstrap_seed, "scenario": name,
                          "detected": result["detected"], "score": result["score"],
                          "thresholdApprox95": result["thresholdApprox95"], "pValue": result["pValue"],
                          "candidateIndex": index, "candidateDate": result["candidate"]["date"] if index is not None else None}
                cases.append(record)
                by_scenario[name].append(record)
        for name, _ in scenarios:
            records = by_scenario[name]
            detected = [record for record in records if record["detected"]]
            errors = [abs(record["candidateIndex"] - shift_index) for record in detected] if name.startswith("step-") else []
            close = sum(error <= 14 for error in errors)
            summaries.append({"rho": rho, "scenario": name, "replications": n,
                              "detections": len(detected), "detectionRate": len(detected)/n,
                              "falseAlarmRate": len(detected)/n if name == "no-change" else None,
                              "detectionWilson95": wilson95(len(detected), n),
                              "medianAbsoluteCandidateIndexErrorAmongDetections": float(np.median(errors)) if errors else None,
                              "within14DaysAmongDetections": close,
                              "within14DaysRateAmongDetections": close/len(detected) if errors else None,
                              "within14DaysOfAllReplications": close,
                              "within14DaysRateAllReplications": close/n,
                              "localizationIsConditionalOnDetection": True if name.startswith("step-") else None})
    return {"specification": specification, "summary": summaries, "cases": cases,
            "interpretation": "No-change detection rate estimates false alarms; shifted controls test detector behavior, not observed ground truth. Candidate localization is conditional on detection."}
