from datetime import datetime, timedelta, timezone
import json

import numpy as np
import pytest

from app_core.analysis.demand_changes import scan, summarize_daily
from scripts import run_demand_changes as runner
from scripts.validate_demand_changes import run_controls, wilson95


def _hourly(days=3, start="2025-01-01"):
    first = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    return [{"time": (first + timedelta(hours=i)).isoformat(), "status": "ok",
             "actual": 110., "expected": 100., "residual": 10.} for i in range(days * 24)]


def _daily(values, year=2025):
    first = datetime(year, 1, 1)
    return [{"date": (first + timedelta(days=i)).date().isoformat(), "complete": np.isfinite(value),
             "actual": float(value + 100) if np.isfinite(value) else None,
             "expected": 100. if np.isfinite(value) else None,
             "residual": float(value) if np.isfinite(value) else None} for i, value in enumerate(values)]


def test_utc_daily_grid_and_missing_coverage():
    rows = _hourly()
    rows.pop(24)
    rows[30 - 1]["status"] = "unsupported_temperature"
    daily, coverage = summarize_daily(rows, "2025-01-01", "2025-01-04", "test")
    assert [day["complete"] for day in daily] == [True, False, True]
    assert daily[1]["residual"] is None and daily[1]["statusCounts"]["missing_row"] == 1
    assert coverage["okHours"] == 70 and coverage["expectedHours"] == 72
    assert daily[0]["actual"] == 110 and daily[2]["residual"] == 10


def test_duplicate_bad_numeric_and_non_utc_rejected():
    rows = _hourly(1)
    with pytest.raises(ValueError, match="duplicate"):
        summarize_daily(rows + [rows[0]], "2025-01-01", "2025-01-02", "test")
    rows[1]["actual"] = float("nan")
    daily, coverage = summarize_daily(rows, "2025-01-01", "2025-01-02", "test")
    assert daily[0]["residual"] is None and coverage["statusCounts"]["invalid_numeric"] == 1
    rows = _hourly(1)
    rows[0]["time"] = "2025-01-01T01:00:00+01:00"
    with pytest.raises(ValueError, match="UTC"):
        summarize_daily(rows, "2025-01-01", "2025-01-02", "test")


def test_hand_calculated_cusum_and_global_run_missing_mask():
    cal = _daily([-.5, .5] * 15, 2024)
    review = _daily([0.] * 3 + [2.] * 3 + [np.nan] + [0.] * 3 + [4.] * 3)
    outcome = scan(cal, review, block_days=2, min_segment_days=2, bootstrap_draws=19, seed=9)
    assert outcome["eligibleSplits"] == 3 + 3
    assert outcome["candidate"]["date"] == "2025-01-11"
    # Last run has 3 vs 3 days and delta=4; calibration sample SD is exact.
    assert outcome["score"] == pytest.approx(np.sqrt(3*3/6)*4 / np.std([-.5, .5]*15, ddof=1))
    assert outcome["candidate"]["deltaResidualKwh"] == pytest.approx(4)
    assert outcome["candidate"]["after"]["residualDistribution"] == [4., 4., 4.]
    assert outcome["pValue"] == (1 + sum(x >= outcome["score"] for x in outcome["bootstrapMaxima"])) / 20


def test_seed_replay_ties_and_cached_null():
    cal = _daily([-1., 0., 1.] * 10, 2024)
    review = _daily([0.] * 5 + [2.] * 5)
    config = dict(block_days=3, min_segment_days=2, bootstrap_draws=21, seed=13)
    a = scan(cal, review, **config)
    b = scan(cal, review, **config, null_maxima=np.asarray(a["bootstrapMaxima"]))
    assert a == b
    assert a["candidate"]["date"] == "2025-01-06"
    flat = scan(cal, _daily([0.] * 10), **config)
    assert flat["candidate"]["date"] == "2025-01-03"  # earliest exact tie
    assert not flat["detected"]


def test_missing_grid_consumes_bootstrap_date_before_masking():
    cal = _daily([-3., -2., -1., 0., 1., 2., 3.], 2024)
    review = _daily([0., 0., 0., 1., 1., 1., np.nan, 0., 0., 0., 2., 2., 2.])
    outcome = scan(cal, review, block_days=2, min_segment_days=2, bootstrap_draws=1, seed=4)
    # Reconstruct one draw on the full 13-day grid: the missing seventh day
    # consumes a sampled value, then its position is masked and splits are local.
    starts = np.arange(6)
    draws = np.random.default_rng(4).choice(starts, size=(1, 7))
    sampled = np.array(cal[0]["residual"] + np.arange(7))[draws[..., None] + np.arange(2)].reshape(-1)[:13]
    sampled[6] = np.nan
    scale = np.std([-3., -2., -1., 0., 1., 2., 3.], ddof=1)
    expected = max(np.sqrt(i*(6-i)/6) * abs(np.mean(sampled[begin+i:begin+6]) - np.mean(sampled[begin:begin+i]))/scale
                   for begin in (0, 7) for i in (2, 3, 4))
    assert outcome["bootstrapMaxima"] == pytest.approx([expected])


def test_insufficient_review_retains_coverage_and_wilson_bounds():
    cal = _daily([-1., 1.] * 8, 2024)
    result = scan(cal, _daily([0., 0., np.nan, 0., 0.]), block_days=2,
                  min_segment_days=2, bootstrap_draws=9)
    assert result["status"] == "insufficient_data" and result["candidate"] is None
    assert result["testRuns"] == [{"startIndex": 0, "endExclusiveIndex": 2, "days": 2},
                                   {"startIndex": 3, "endExclusiveIndex": 5, "days": 2}]
    assert wilson95(0, 200)[0] == 0 and wilson95(200, 200)[1] == 1


def test_existing_output_refused_before_source_read(tmp_path, monkeypatch):
    output = tmp_path / "study.json"
    output.write_text("saved")
    monkeypatch.setattr(runner, "read_protocol", lambda *args: pytest.fail("source must not be read"))
    with pytest.raises(FileExistsError):
        runner.run_study(output)
    assert output.read_text() == "saved"


def test_protocol_pins_saved_source_identity(tmp_path):
    protocol = json.loads(runner.DEFAULT_PROTOCOL.read_text())
    protocol["sourceSha256"] = "bad"
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol))
    source = tmp_path / "source.json"
    source.write_text("{}")
    with pytest.raises(ValueError, match="SHA-256"):
        runner.read_protocol(path, source)


def test_control_streams_independent_and_replayable():
    protocol = json.loads(runner.DEFAULT_PROTOCOL.read_text())
    spec = {**protocol["controls"], "rhos": [0.5], "replications": 2}
    config = {**protocol["config"], "bootstrapDraws": 17}
    first = run_controls(spec, config)
    assert first == run_controls(spec, config)
    no_change = [case for case in first["cases"] if case["scenario"] == "no-change"]
    assert len(no_change) == 2
    assert all(case["pairSeed"] != case["bootstrapSeed"] for case in no_change)
    assert len({case["pairSeed"] for case in no_change}) == 2
