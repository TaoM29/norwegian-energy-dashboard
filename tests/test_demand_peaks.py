"""Known-hour checks for exact household peak and regional comparisons."""

import numpy as np
import pandas as pd
import pytest

from app_core.analysis.demand_peaks import analyze_area, analyze_regions
from app_core.ingestion.models import AREAS


def _frame(start: str, values: list[float | None]) -> pd.DataFrame:
    index = pd.date_range(start, periods=len(values), freq="h", tz="UTC")
    return pd.DataFrame({
        "timestamp": index, "value": values, "quality": ["ok"] * len(values),
        "unit": ["kWh"] * len(values),
    })


def test_area_exact_thresholds_peak_ties_and_only_adjacent_ramps():
    frame = _frame("2025-01-01", [3, 5, 5, np.nan, 2, 4, 2, 4])
    result = analyze_area(frame, "NO1", "2025-01-01", "2025-01-01T08:00:00Z")
    assert result["coverage"] == {
        "expectedHours": 8, "observedHours": 7, "excludedHours": 1,
        "missingHours": 0, "badQualityHours": 0, "nonfiniteOrNegativeHours": 1,
        "validRampPairs": 5, "expectedRampPairs": 7,
    }
    assert result["summary"]["meanKwh"] == pytest.approx(25 / 7)
    assert result["summary"]["peak"] == {
        "time": "2025-01-01T01:00:00Z", "valueKwh": 5, "tieCount": 2,
    }
    assert result["summary"]["largestRise"] == {
        "time": "2025-01-01T01:00:00Z", "previousTime": "2025-01-01T00:00:00Z",
        "changeKwh": 2, "tieCount": 3,
    }
    assert result["summary"]["largestFall"] == {
        "time": "2025-01-01T06:00:00Z", "previousTime": "2025-01-01T05:00:00Z",
        "changeKwh": -2, "tieCount": 1,
    }
    assert result["duration"] == [
        {"valueKwh": 5, "hoursAtOrAbove": 2, "percentAtOrAbove": 200 / 7},
        {"valueKwh": 4, "hoursAtOrAbove": 4, "percentAtOrAbove": 400 / 7},
        {"valueKwh": 3, "hoursAtOrAbove": 5, "percentAtOrAbove": 500 / 7},
        {"valueKwh": 2, "hoursAtOrAbove": 7, "percentAtOrAbove": 100},
    ]
    assert result["hourly"][3]["valueKwh"] is None
    assert result["hourly"][4]["changeKwh"] is None
    assert result["hourly"][5]["changeKwh"] == 2


def test_missing_row_bad_quality_and_zero_or_one_observation():
    frame = _frame("2025-01-01", [0, 8, 4, 0])
    frame = frame.drop(index=1)
    frame.loc[2, "quality"] = "missing"
    result = analyze_area(frame, "NO2", "2025-01-01", "2025-01-01T04:00Z")
    assert result["coverage"]["observedHours"] == 2
    assert result["coverage"]["missingHours"] == 1
    assert result["coverage"]["badQualityHours"] == 1
    assert result["coverage"]["validRampPairs"] == 0
    assert result["summary"]["largestRise"] is None
    assert result["summary"]["largestFall"] is None
    assert result["summary"]["peak"]["tieCount"] == 2
    assert result["duration"] == [
        {"valueKwh": 0, "hoursAtOrAbove": 2, "percentAtOrAbove": 100},
    ]
    empty = analyze_area(frame.iloc[0:0], "NO2", "2025-01-01", "2025-01-01T04:00Z")
    assert empty["summary"] == {"meanKwh": None, "peak": None,
                                "largestRise": None, "largestFall": None}
    assert empty["duration"] == []


def test_utc_adjacency_through_oslo_daylight_saving_change():
    frame = _frame("2025-03-30T00:00:00Z", [1, 3, 6])
    result = analyze_area(frame, "NO3", "2025-03-30", "2025-03-30T03:00:00Z")
    assert result["coverage"]["validRampPairs"] == 2
    assert [row["changeKwh"] for row in result["hourly"]] == [None, 2, 3]


def test_fall_back_repeated_oslo_hour_is_two_distinct_adjacent_utc_hours():
    frame = _frame("2025-10-26T00:00:00Z", [8, 5, 2])
    result = analyze_area(frame, "NO3", "2025-10-26", "2025-10-26T03:00:00Z")
    assert result["coverage"]["validRampPairs"] == 2
    assert result["summary"]["largestFall"] == {
        "time": "2025-10-26T01:00:00Z", "previousTime": "2025-10-26T00:00:00Z",
        "changeKwh": -3, "tieCount": 2,
    }


def test_nonfinite_negative_and_bad_quality_are_coverage_exclusions():
    frame = _frame("2025-01-01", [1, np.inf, -2, 4, 7, 10])
    frame.loc[4, "quality"] = "aggregate"
    result = analyze_area(frame, "NO4", "2025-01-01", "2025-01-01T06:00Z")
    assert result["coverage"]["observedHours"] == 3
    assert result["coverage"]["nonfiniteOrNegativeHours"] == 2
    assert result["coverage"]["badQualityHours"] == 1
    assert result["coverage"]["validRampPairs"] == 0
    assert result["summary"]["peak"]["valueKwh"] == 10
    assert all(row["changeKwh"] is None for row in result["hourly"])


def test_one_direction_one_hour_and_outside_interval_boundaries():
    one = _frame("2025-01-01", [2])
    one_result = analyze_area(one, "NO1", "2025-01-01", "2025-01-01T01:00Z")
    assert one_result["coverage"]["expectedRampPairs"] == 0
    assert one_result["summary"]["peak"]["valueKwh"] == 2
    assert one_result["summary"]["largestRise"] is None
    assert one_result["summary"]["largestFall"] is None
    increasing = _frame("2025-01-01", [1, 2, 2, 5])
    increasing_result = analyze_area(increasing, "NO1", "2025-01-01", "2025-01-01T03:00Z")
    assert increasing_result["summary"]["largestRise"]["changeKwh"] == 1
    assert increasing_result["summary"]["largestFall"] is None
    assert increasing_result["coverage"]["observedHours"] == 3
    assert increasing_result["summary"]["peak"]["valueKwh"] == 2


def test_rejects_duplicate_offgrid_and_incompatible_unit_even_if_quality_bad():
    frame = _frame("2025-01-01", [1, 2])
    duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    duplicate.loc[2, "quality"] = "missing"
    with pytest.raises(ValueError, match="unique UTC hours"):
        analyze_area(duplicate, "NO1", "2025-01-01", "2025-01-01T02:00Z")
    offgrid = frame.copy()
    offgrid.loc[1, "timestamp"] += pd.Timedelta(minutes=30)
    offgrid.loc[1, "quality"] = "missing"
    with pytest.raises(ValueError, match="exact UTC hourly grid"):
        analyze_area(offgrid, "NO1", "2025-01-01", "2025-01-01T02:00Z")
    wrong_unit = frame.copy()
    wrong_unit.loc[1, "unit"] = "MWh"
    with pytest.raises(ValueError, match="kWh"):
        analyze_area(wrong_unit, "NO1", "2025-01-01", "2025-01-01T02:00Z")


def test_regional_matched_cohort_reconciles_peak_factor_and_correlations():
    inputs = dict(zip(AREAS, [
        _frame("2025-01-01", values) for values in
        ([3, 8, 4], [6, 2, 4], [1, 2, 3], [2, 2, 2], [2, 4, 2])
    ]))
    inputs["NO5"].loc[1, "quality"] = "missing"
    result = analyze_regions(inputs, "2025-01-01", "2025-01-01T03:00Z")
    assert result["coverage"]["expectedHours"] == 3
    assert result["coverage"]["matchedHours"] == 2
    assert result["coverage"]["excludedHours"] == 1
    assert [row["observedHours"] for row in result["coverage"]["byArea"]] == [3, 3, 3, 3, 2]
    assert result["hourly"][1] == {
        "time": "2025-01-01T01:00:00Z", **{area: None for area in AREAS},
    }
    assert result["coincidentPeak"] == {
        "time": "2025-01-01T02:00:00Z", "valueKwh": 15, "tieCount": 1,
    }
    assert result["sumIndividualPeaksKwh"] == 17
    assert result["coincidenceFactor"] == pytest.approx(15 / 17)
    assert result["areas"][0]["meanKwh"] == 3.5
    assert result["areas"][0]["peak"]["valueKwh"] == 4
    assert result["areas"][0]["atCoincidentPeakKwh"] == 4
    correlations = {(row["areaA"], row["areaB"]): row for row in result["correlations"]}
    assert correlations[("NO1", "NO2")]["r"] == pytest.approx(-1)
    assert correlations[("NO1", "NO4")]["r"] is None
    assert all(row["hours"] == 2 for row in result["correlations"])


def test_regional_empty_and_zero_mean_do_not_divide_by_zero():
    inputs = {area: _frame("2025-01-01", [0, 0]) for area in AREAS}
    result = analyze_regions(inputs, "2025-01-01", "2025-01-01T02:00Z")
    assert result["coincidentPeak"]["valueKwh"] == 0
    assert result["coincidentPeak"]["tieCount"] == 2
    assert result["sumIndividualPeaksKwh"] == 0
    assert result["coincidenceFactor"] is None
    assert all(row["r"] is None for row in result["correlations"])
    inputs["NO5"]["quality"] = "missing"
    missing = analyze_regions(inputs, "2025-01-01", "2025-01-01T02:00Z")
    assert missing["coverage"]["matchedHours"] == 0
    assert missing["coincidentPeak"] is None
    assert missing["sumIndividualPeaksKwh"] is None
    assert all(row["meanKwh"] is None for row in missing["areas"])
