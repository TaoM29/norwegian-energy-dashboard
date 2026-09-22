"""Retrospective, single-change scan on frozen Step 5 daily residual means.

There is no online fitting, recursive segmentation, or causal interpretation here.
The full test-grid missing mask is retained during calibration block resampling.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import math

import numpy as np


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def summarize_daily(rows: list[dict], start: str, end: str, period: str) -> tuple[list[dict], dict]:
    """Group an exact hourly UTC grid into complete 24-hour UTC days [start,end)."""
    first = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    stop = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    if first.hour or first.minute or first.second or stop.hour or stop.minute or stop.second or stop <= first:
        raise ValueError("UTC day boundaries are required")
    count = (stop - first).days
    if first + timedelta(days=count) != stop:
        raise ValueError("UTC day boundaries are required")
    by_hour: dict[datetime, dict] = {}
    for row in rows:
        try:
            stamp = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid hourly timestamp") from exc
        if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0) or stamp.minute or stamp.second or stamp.microsecond:
            raise ValueError("Hourly timestamps must be exact UTC hours")
        if not first <= stamp < stop or stamp in by_hour:
            raise ValueError("Hourly timestamp outside period or duplicate")
        by_hour[stamp] = row
    daily = []
    global_status: Counter[str] = Counter()
    for offset in range(count):
        day = first + timedelta(days=offset)
        hours = [by_hour.get(day + timedelta(hours=h)) for h in range(24)]
        statuses: Counter[str] = Counter()
        triples = []
        for hour in hours:
            if hour is None:
                statuses["missing_row"] += 1
                continue
            if hour.get("status") != "ok":
                statuses[hour.get("status", "unknown")] += 1
                continue
            try:
                actual = _number(hour.get("actual"), "actual")
                expected = _number(hour.get("expected"), "expected")
                residual = _number(hour.get("residual"), "residual")
            except ValueError:
                statuses["invalid_numeric"] += 1
                continue
            if not math.isclose(actual - expected, residual, rel_tol=1e-9, abs_tol=1e-6):
                raise ValueError("Hourly residual must equal actual minus expected")
            statuses["ok"] += 1
            triples.append((actual, expected, residual))
        global_status.update(statuses)
        ok = statuses["ok"]
        complete = ok == 24
        # Incomplete days have no analytic value, even when some hours were valid.
        means = np.mean(triples, axis=0).tolist() if complete else [None] * 3
        daily.append({"date": day.date().isoformat(), "period": period, "actual": means[0],
                      "expected": means[1], "residual": means[2], "okHours": ok,
                      "expectedHours": 24, "statusCounts": dict(sorted(statuses.items())), "complete": complete})
    return daily, {"expectedDays": count, "completeDays": sum(day["complete"] for day in daily),
                   "incompleteDays": sum(not day["complete"] for day in daily),
                   "expectedHours": count * 24, "okHours": global_status["ok"],
                   "statusCounts": dict(sorted(global_status.items()))}


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    edges = np.diff(np.r_[False, mask, False].astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def _split_indices(mask: np.ndarray, minimum: int) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    indices, starts, runs = [], [], []
    for start, stop in _runs(mask):
        runs.append({"startIndex": start, "endExclusiveIndex": stop, "days": stop - start})
        if stop - start >= 2 * minimum:
            choices = np.arange(start + minimum, stop - minimum + 1)
            indices.extend(choices.tolist())
            starts.extend([start] * len(choices))
    return np.asarray(indices, dtype=int), np.asarray(starts, dtype=int), runs


def _scores(series: np.ndarray, indices: np.ndarray, starts: np.ndarray, mask: np.ndarray, scale: float) -> np.ndarray:
    """Vectorized scores for one or many rows of equally masked test grids."""
    if not len(indices):
        return np.empty((series.shape[0], 0))
    # End of each run is found once from mask, avoiding per-bootstrap searches.
    run_end = np.empty(len(mask), dtype=int)
    for start, stop in _runs(mask):
        run_end[start:stop] = stop
    ends = run_end[starts]
    prefix = np.cumsum(np.pad(np.nan_to_num(series, nan=0), ((0, 0), (1, 0))), axis=1)
    n_left = indices - starts
    n_right = ends - indices
    left = (prefix[:, indices] - prefix[:, starts]) / n_left
    right = (prefix[:, ends] - prefix[:, indices]) / n_right
    return np.sqrt(n_left * n_right / (n_left + n_right)) * np.abs(right - left) / scale


def _distribution(rows: list[dict], start: int, stop: int) -> dict:
    selection = rows[start:stop]
    residuals = np.array([r["residual"] for r in selection], dtype=float)
    return {"start": selection[0]["date"],
            "endExclusive": (datetime.fromisoformat(selection[-1]["date"]) + timedelta(days=1)).date().isoformat(),
            "days": len(selection),
            "meanActual": float(np.mean([r["actual"] for r in selection])),
            "meanExpected": float(np.mean([r["expected"] for r in selection])),
            "meanResidual": float(residuals.mean()), "medianResidual": float(np.median(residuals)),
            "q1Residual": float(np.quantile(residuals, .25)), "q3Residual": float(np.quantile(residuals, .75)),
            "residualDistribution": sorted(residuals.tolist())}


def scan(calibration: list[dict], test: list[dict], *, block_days: int = 14,
         min_segment_days: int = 28, bootstrap_draws: int = 999, alpha: float = .05,
         seed: int = 20260922, include_maxima: bool = True,
         null_maxima: np.ndarray | None = None) -> dict:
    """Find strongest global split; calibrate familywise maximum with moving blocks.

    Draws sample globally centered calibration residuals from all contiguous
    wholly valid blocks. A draw first fills the entire test calendar grid,
    then applies its missing mask; every draw scans all eligible runs/splits.
    """
    if block_days < 1 or min_segment_days < 1 or bootstrap_draws < 1 or not 0 < alpha < 1:
        raise ValueError("Invalid scan configuration")
    cal = np.array([float(r["residual"]) if r["complete"] else np.nan for r in calibration])
    residual = np.array([float(r["residual"]) if r["complete"] else np.nan for r in test])
    valid_cal = cal[np.isfinite(cal)]
    if len(valid_cal) < 2:
        raise ValueError("At least two complete calibration days are required")
    scale = float(np.std(valid_cal, ddof=1))
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Calibration residual standard deviation must be positive")
    centered = cal - valid_cal.mean()
    block_starts = np.array([i for i in range(len(cal) - block_days + 1)
                             if np.isfinite(centered[i:i + block_days]).all()], dtype=int)
    if not len(block_starts):
        raise ValueError("No wholly complete calibration block")
    mask = np.isfinite(residual)
    indices, starts, runs = _split_indices(mask, min_segment_days)
    result = {"status": "insufficient_data" if not len(indices) else "ok", "detected": False,
              "score": None, "pValue": None, "thresholdApprox95": None, "candidate": None,
              "calibrationScaleKwh": scale, "eligibleSplits": len(indices), "testRuns": runs,
              "calibrationBlockStarts": block_starts.tolist(), "bootstrapMaxima": []}
    if not len(indices):
        return result
    scores = _scores(residual[None, :], indices, starts, mask, scale)[0]
    best = int(np.argmax(scores))  # Chronological order resolves exact ties.
    observed = float(scores[best])
    if null_maxima is not None:
        maxima = np.asarray(null_maxima, dtype=float)
        if maxima.shape != (bootstrap_draws,) or not np.isfinite(maxima).all():
            raise ValueError("Cached null maxima must have one finite value per draw")
    else:
        rng = np.random.default_rng(seed)
        num_blocks = math.ceil(len(test) / block_days)
        maxima = np.empty(bootstrap_draws)
        for begin in range(0, bootstrap_draws, 256):
            size = min(256, bootstrap_draws - begin)
            draws = rng.choice(block_starts, size=(size, num_blocks))
            values = centered[(draws[..., None] + np.arange(block_days)).reshape(size, -1)][:, :len(test)]
            grid = np.full((size, len(test)), np.nan)
            grid[:, mask] = values[:, mask]
            maxima[begin:begin + size] = np.max(_scores(grid, indices, starts, mask, scale), axis=1)
    p = (1 + int(np.count_nonzero(maxima >= observed))) / (bootstrap_draws + 1)
    split = int(indices[best]); start = int(starts[best]); end = next(e for s, e in _runs(mask) if s == start)
    before = _distribution(test, start, split)
    after = _distribution(test, split, end)
    delta = after["meanResidual"] - before["meanResidual"]
    result.update(status="ok", detected=bool(p <= alpha), score=observed, pValue=p,
                  thresholdApprox95=float(np.quantile(maxima, .95, method="higher")),
                  candidate={"date": test[split]["date"], "before": before, "after": after,
                             "deltaResidualKwh": delta, "standardizedDelta": delta / scale},
                  bootstrapMaxima=maxima.tolist() if include_maxima else [])
    return result
