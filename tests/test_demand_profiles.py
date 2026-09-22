"""Calendar and distribution checks for observed daily household profiles."""
import numpy as np
import pandas as pd
import pytest

from app_core.analysis.demand_profiles import analyze_profiles


def _frame(start, end, value=10.0):
    index = pd.date_range(start, end, freq="h", inclusive="left", tz="UTC")
    return pd.DataFrame({"timestamp": index, "value": value,
                         "quality": "ok", "unit": "kWh"})


def _day(result, date):
    return next(day for day in result["days"] if day["date"] == date)


def _group(result, group_type, group):
    return next(item for item in result["groups"]
                if item["groupType"] == group_type and item["group"] == group)


@pytest.mark.parametrize("start,end,date,expected,reason", [
    ("2025-03-29", "2025-04-01", "2025-03-30", 23, "dst23HourDay"),
    ("2025-10-25", "2025-10-28", "2025-10-26", 25, "dst25HourDay"),
])
def test_dst_days_remain_raw_and_never_enter_24_hour_profiles(start, end, date, expected, reason):
    result = analyze_profiles(_frame(start, end), "NO1", start, end)
    day = _day(result, date)
    assert day["expectedHours"] == expected
    assert day["selectedHours"] == expected
    assert day["validHours"] == expected
    assert day["exclusionReasons"] == [reason]
    assert not day["profileEligible"]
    assert len(day["hours"]) == expected
    assert len({hour["timeUtc"] for hour in day["hours"]}) == expected
    assert all("+0" in hour["timeOslo"] for hour in day["hours"])
    assert result["coverage"]["dstExcludedDays"] == 1
    if expected == 25:
        repeated = [hour for hour in day["hours"] if hour["localHour"] == 2]
        assert len(repeated) == 2
        assert repeated[0]["timeOslo"].endswith("+02:00")
        assert repeated[1]["timeOslo"].endswith("+01:00")
    else:
        assert not any(hour["localHour"] == 2 for hour in day["hours"])


def test_boundary_missing_quality_and_zero_mean_have_distinct_eligibility():
    frame = _frame("2025-01-01", "2025-01-06")
    local = frame["timestamp"].dt.tz_convert("Europe/Oslo")
    frame.loc[local.dt.date.astype(str) == "2025-01-02", "value"] = 0
    frame.loc[(local.dt.date.astype(str) == "2025-01-03") & (local.dt.hour == 8), "quality"] = "missing"
    frame = frame.loc[~((local.dt.date.astype(str) == "2025-01-04") & (local.dt.hour == 9))].copy()
    result = analyze_profiles(frame, "NO2", "2025-01-01", "2025-01-06")
    first = _day(result, "2025-01-01")
    assert first["selectedHours"] == 23
    assert first["exclusionReasons"] == ["partialBoundaryDay"]
    zero = _day(result, "2025-01-02")
    assert zero["profileEligible"] and not zero["normalizedEligible"]
    assert zero["meanKwh"] == 0 and zero["totalKwh"] == 0
    assert zero["exclusionReasons"] == ["zeroMeanDay"]
    assert _day(result, "2025-01-03")["exclusionReasons"] == ["incompleteDay"]
    assert _day(result, "2025-01-04")["exclusionReasons"] == ["incompleteDay"]
    assert result["coverage"]["badQualityHours"] == 1
    assert result["coverage"]["missingHours"] == 1
    assert result["coverage"]["incompleteExcludedDays"] == 2
    assert result["coverage"]["zeroMeanDays"] == 1
    assert result["coverage"]["profileEligibleDays"] == 2
    assert result["coverage"]["normalizedEligibleDays"] == 1
    assert _group(result, "dayType", "weekday")["actualDayCount"] == 1
    assert _group(result, "dayType", "weekday")["normalizedDayCount"] == 0
    assert _day(result, "2025-01-04")["hours"][9]["valueKwh"] is None


def test_empirical_bands_and_representative_use_normalized_observed_shape():
    frame = _frame("2025-01-05", "2025-01-11")
    local = frame["timestamp"].dt.tz_convert("Europe/Oslo")
    for day, first_hour in zip(range(6, 11), [10, 20, 30, 40, 50]):
        frame.loc[(local.dt.day == day) & (local.dt.hour == 0), "value"] = first_hour
    result = analyze_profiles(frame, "NO3", "2025-01-05", "2025-01-11")
    weekdays = _group(result, "dayType", "weekday")
    assert weekdays["actualDayCount"] == weekdays["normalizedDayCount"] == 5
    assert weekdays["actual"][0] == {"hour": 0, "medianKwh": 30,
                                      "p10Kwh": 14, "p90Kwh": 46}
    assert weekdays["actual"][1]["medianKwh"] == 10
    assert weekdays["representative"]["date"] == "2025-01-08"
    assert weekdays["normalized"][0]["p10PercentDailyMean"] is not None
    assert _group(result, "dayType", "weekend")["actual"][0]["p10Kwh"] is None
    assert "confidence interval" in result["calculation"]["actual"]


def test_utc_half_open_selection_keeps_only_touched_hours_and_stable_hash():
    frame = _frame("2025-01-01", "2025-01-03")
    outside = _frame("2025-01-03", "2025-01-04", 900)
    a = analyze_profiles(pd.concat([frame, outside], ignore_index=True), "NO4",
                         "2025-01-01", "2025-01-03")
    b = analyze_profiles(frame.sample(frac=1, random_state=1), "NO4",
                         "2025-01-01", "2025-01-03")
    assert a["inputSha256"] == b["inputSha256"]
    assert a["coverage"]["expectedHours"] == 48
    assert a["coverage"]["touchedDays"] == 3
    assert a["coverage"]["expectedDays"] == 1
    assert a["coverage"]["boundaryExcludedDays"] == 2
    assert a["coverage"]["profileEligibleDays"] == 1
    assert len(_day(a, "2025-01-03")["hours"]) == 1
    assert _day(a, "2025-01-03")["hours"][0]["valueKwh"] == 10


@pytest.mark.parametrize("kind", ["duplicate", "offgrid", "unit"])
def test_malformed_source_is_rejected_even_for_bad_quality(kind):
    frame = _frame("2025-01-01", "2025-01-02")
    if kind == "duplicate":
        frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        frame.loc[24, "quality"] = "missing"
    elif kind == "offgrid":
        frame.loc[0, "timestamp"] += pd.Timedelta(minutes=1)
        frame.loc[0, "quality"] = "missing"
    else:
        frame.loc[0, "unit"] = "MWh"
        frame.loc[0, "quality"] = "missing"
    with pytest.raises(ValueError):
        analyze_profiles(frame, "NO5", "2025-01-01", "2025-01-02")


def test_nonfinite_negative_and_absent_hours_are_not_interpolated():
    frame = _frame("2025-01-01", "2025-01-03")
    local = frame["timestamp"].dt.tz_convert("Europe/Oslo")
    for hour, value in [(1, np.inf), (2, -1)]:
        frame.loc[(local.dt.day == 2) & (local.dt.hour == hour), "value"] = value
    result = analyze_profiles(frame, "NO1", "2025-01-01", "2025-01-03")
    day = _day(result, "2025-01-02")
    assert day["validHours"] == 22
    assert day["exclusionReasons"] == ["incompleteDay"]
    assert [day["hours"][hour]["valueKwh"] for hour in (1, 2)] == [None, None]
    assert result["coverage"]["nonfiniteOrNegativeHours"] == 2
