from __future__ import annotations

import math

import pandas as pd
import pytest

from app_core.analysis.snow_drift import (
    TABLER_WIND_DIVISOR,
    analyze_snow_drift,
    compute_Qupot,
    fence_height,
    sector_transport,
    tabler_transport,
)


def weather_fixture(times, *, temperatures=None, precipitation=None, speeds=None, directions=None):
    count = len(times)
    return pd.DataFrame(
        {
            "time": times,
            "temperature_2m (°C)": temperatures or [-2.0] * count,
            "precipitation (mm)": precipitation or [1.0] * count,
            "wind_speed_10m (m/s)": speeds or [4.0] * count,
            "wind_direction_10m (°)": directions or [0.0] * count,
        }
    )


def test_potential_transport_keeps_original_units_and_exponent():
    speeds = [2.0, 4.0, 7.0]
    expected = sum(speed**3.8 * 3600 for speed in speeds) / TABLER_WIND_DIVISOR
    assert compute_Qupot(speeds) == pytest.approx(expected)


def test_tabler_transport_exercises_wind_and_snowfall_limits():
    wind_limited = tabler_transport(3000, 30000, 0.5, 1000, [1.0])
    assert wind_limited["Control"] == "Wind controlled"
    assert wind_limited["Qinf (kg/m)"] == wind_limited["Qupot (kg/m)"]

    snowfall_limited = tabler_transport(3000, 30000, 0.5, 0.001, [30.0])
    assert snowfall_limited["Control"] == "Snowfall controlled"
    assert snowfall_limited["Qinf (kg/m)"] == pytest.approx(0.75)
    assert snowfall_limited["Qt (kg/m)"] == pytest.approx(
        0.75 * (1 - 0.14 ** 10)
    )


def test_directional_transport_uses_nearest_clockwise_16_sector():
    speed = 5.0
    contribution = speed**3.8 * 3600 / TABLER_WIND_DIVISOR
    result = sector_transport(
        [speed, speed, speed, speed],
        [0.0, 11.249, 11.25, 348.75],
    )
    assert result[0] == pytest.approx(contribution * 3)
    assert result[1] == pytest.approx(contribution)
    assert sum(result) == pytest.approx(contribution * 4)


def test_snowfall_threshold_is_strictly_below_one_degree():
    frame = weather_fixture(
        pd.date_range("2023-07-01", periods=2, freq="h", tz="UTC"),
        temperatures=[0.999, 1.0],
        precipitation=[2.0, 100.0],
        speeds=[0.0, 0.0],
    )
    result = analyze_snow_drift(frame, 2023, 2023, 3000, 30000, 0.5, "Wyoming")
    assert result["seasonal"][0]["srweMm"] == pytest.approx(1.0)


def test_analysis_labels_partial_leap_season_and_converts_tonnes():
    frame = weather_fixture(
        pd.date_range("2023-07-01", periods=48, freq="h", tz="UTC"),
        speeds=[6.0] * 48,
    )
    result = analyze_snow_drift(frame, 2023, 2023, 3000, 30000, 0.5, "Solid")
    season = result["seasonal"][0]
    assert season["expectedHours"] == 366 * 24
    assert season["observedHours"] == 48
    assert season["partial"] is True
    assert "partial" in season["seasonLabel"]
    assert season["qtTonnesPerM"] == pytest.approx(season["qtKgPerM"] / 1000)
    assert season["fenceHeightM"] == pytest.approx(
        fence_height(season["qtKgPerM"], "Solid")
    )
    assert len(result["directional"]) == 16
    assert result["directional"][0]["transportKgPerM"] == pytest.approx(
        compute_Qupot([6.0] * 48)
    )


@pytest.mark.parametrize(
    "mutator,error",
    [
        (lambda frame: frame.assign(**{"wind_speed_10m (m/s)": [math.nan]}), "missing"),
        (lambda frame: pd.concat([frame, frame]), "duplicate"),
    ],
)
def test_analysis_rejects_weather_that_would_corrupt_transport(mutator, error):
    frame = weather_fixture(pd.date_range("2023-07-01", periods=1, freq="h", tz="UTC"))
    with pytest.raises(ValueError, match=error):
        analyze_snow_drift(mutator(frame), 2023, 2023, 3000, 30000, 0.5, "Wyoming")

