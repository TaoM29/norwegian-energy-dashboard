"""Framework-independent Tabler snow-transport calculations.

The implementation preserves the equations used by the original Streamlit page.
All transport values are calculated in kg/m; tonnes/m is a presentation
conversion. Weather observations must be hourly UTC values with wind in m/s.
"""

from __future__ import annotations

from datetime import date
import math
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


SECONDS_PER_HOUR = 3600
TABLER_WIND_DIVISOR = 233_847.0
SNOW_TEMPERATURE_THRESHOLD_C = 1.0
DIRECTION_LABELS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)
FENCE_FACTORS = {"Wyoming": 8.5, "Slat-and-wire": 7.7, "Solid": 2.9}

TIME_COLUMN = "time"
TEMPERATURE_COLUMN = "temperature_2m (°C)"
PRECIPITATION_COLUMN = "precipitation (mm)"
WIND_SPEED_COLUMN = "wind_speed_10m (m/s)"
WIND_DIRECTION_COLUMN = "wind_direction_10m (°)"


def _finite_nonnegative(values: Iterable[float], name: str) -> np.ndarray:
    result = np.asarray(list(values), dtype=float)
    if not np.isfinite(result).all():
        raise ValueError(f"{name} contains missing or non-finite values")
    if (result < 0).any():
        raise ValueError(f"{name} contains negative values")
    return result


def compute_Qupot(hourly_wind_speeds: Iterable[float], dt: int = SECONDS_PER_HOUR) -> float:
    """Return potential wind transport in kg/m for equally spaced observations."""
    if dt <= 0:
        raise ValueError("dt must be positive")
    speeds = _finite_nonnegative(hourly_wind_speeds, "wind speed")
    return float(np.sum(np.power(speeds, 3.8) * dt) / TABLER_WIND_DIVISOR)


def _sector_index(degrees: float) -> int:
    """Return the nearest of 16 clockwise sectors, with north at index zero."""
    if not math.isfinite(float(degrees)):
        raise ValueError("wind direction contains a missing or non-finite value")
    return int(((float(degrees) + 11.25) % 360.0) // 22.5)


def sector_transport(
    wind_speeds: Iterable[float],
    wind_directions: Iterable[float],
    dt: int = SECONDS_PER_HOUR,
) -> list[float]:
    """Return potential wind transport in kg/m assigned to 16 direction sectors."""
    speeds = _finite_nonnegative(wind_speeds, "wind speed")
    directions = np.asarray(list(wind_directions), dtype=float)
    if len(speeds) != len(directions):
        raise ValueError("wind speed and direction must have the same length")
    if not np.isfinite(directions).all():
        raise ValueError("wind direction contains missing or non-finite values")
    sectors = [0.0] * 16
    for speed, direction in zip(speeds, directions):
        sectors[_sector_index(float(direction))] += (
            float(speed) ** 3.8 * dt / TABLER_WIND_DIVISOR
        )
    return sectors


def tabler_transport(
    T: float,
    F: float,
    theta: float,
    Swe_mm: float,
    ws: Iterable[float],
    dt: int = SECONDS_PER_HOUR,
) -> dict[str, float | str]:
    """Calculate the original page's Tabler components for one time slice."""
    if not (math.isfinite(T) and 100 <= T <= 10_000):
        raise ValueError("T must be between 100 and 10000 m")
    if not (math.isfinite(F) and 1_000 <= F <= 200_000):
        raise ValueError("F must be between 1000 and 200000 m")
    if not (math.isfinite(theta) and 0 <= theta <= 1):
        raise ValueError("theta must be between 0 and 1")
    if not (math.isfinite(Swe_mm) and Swe_mm >= 0):
        raise ValueError("Swe_mm must be finite and non-negative")

    qupot = compute_Qupot(ws, dt)
    qspot = 0.5 * T * Swe_mm
    srwe = theta * Swe_mm
    if qupot > qspot:
        qinf = 0.5 * T * srwe
        control = "Snowfall controlled"
    else:
        qinf = qupot
        control = "Wind controlled"
    qt = qinf * (1 - 0.14 ** (F / T))
    return {
        "Qupot (kg/m)": float(qupot),
        "Qspot (kg/m)": float(qspot),
        "Srwe (mm)": float(srwe),
        "Qinf (kg/m)": float(qinf),
        "Qt (kg/m)": float(qt),
        "Control": control,
    }


def fence_factor(name: str) -> float:
    try:
        return FENCE_FACTORS[name]
    except KeyError as error:
        raise ValueError(f"unknown fence type: {name}") from error


def fence_height(qt_kg_per_m: float, fence_type: str) -> float:
    """Return indicative fence height in metres from transport storage capacity."""
    if not math.isfinite(qt_kg_per_m) or qt_kg_per_m < 0:
        raise ValueError("Qt must be finite and non-negative")
    return float((qt_kg_per_m / 1_000.0 / fence_factor(fence_type)) ** (1 / 2.2))


def season_span(start_season: int, end_season: int) -> tuple[date, date]:
    """Return the half-open UTC date bounds for inclusive July–June seasons."""
    if start_season > end_season:
        raise ValueError("start season must not be after end season")
    return date(start_season, 7, 1), date(end_season + 1, 7, 1)


def _prepared_weather(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        TIME_COLUMN,
        TEMPERATURE_COLUMN,
        PRECIPITATION_COLUMN,
        WIND_SPEED_COLUMN,
        WIND_DIRECTION_COLUMN,
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"weather data is missing columns: {', '.join(missing)}")
    result = frame[list(required)].copy()
    result[TIME_COLUMN] = pd.to_datetime(result[TIME_COLUMN], utc=True, errors="coerce")
    for column in required - {TIME_COLUMN}:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if result[list(required)].isna().any().any():
        raise ValueError("weather data contains missing or invalid values")
    if result[TIME_COLUMN].duplicated().any():
        raise ValueError("weather data contains duplicate UTC timestamps")
    result = result.sort_values(TIME_COLUMN).reset_index(drop=True)
    if (result[PRECIPITATION_COLUMN] < 0).any() or (result[WIND_SPEED_COLUMN] < 0).any():
        raise ValueError("weather data contains negative precipitation or wind speed")
    return result


def _slice_result(frame: pd.DataFrame, T: float, F: float, theta: float) -> dict[str, float | str]:
    swe = float(
        np.where(
            frame[TEMPERATURE_COLUMN].to_numpy() < SNOW_TEMPERATURE_THRESHOLD_C,
            frame[PRECIPITATION_COLUMN].to_numpy(),
            0.0,
        ).sum()
    )
    return tabler_transport(T, F, theta, swe, frame[WIND_SPEED_COLUMN].to_numpy())


def _coverage(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, object]:
    observed = int(frame[TIME_COLUMN].nunique())
    expected = int((end - start) / pd.Timedelta(hours=1))
    return {
        "observedHours": observed,
        "expectedHours": expected,
        "missingHours": max(expected - observed, 0),
        "coveragePercent": round(100 * observed / expected, 2) if expected else 0.0,
        "partial": observed != expected,
    }


def compute_yearly(
    df_seasoned: pd.DataFrame,
    T: float,
    F: float,
    theta: float,
    *,
    seasons: Sequence[int] | None = None,
    fence_type: str = "Wyoming",
) -> pd.DataFrame:
    """Compute transport and coverage for each requested July–June season."""
    frame = _prepared_weather(df_seasoned)
    inferred = frame[TIME_COLUMN].dt.year.where(
        frame[TIME_COLUMN].dt.month >= 7, frame[TIME_COLUMN].dt.year - 1
    )
    frame["season"] = inferred.astype(int)
    selected = list(seasons) if seasons is not None else sorted(frame["season"].unique())
    rows: list[dict[str, object]] = []
    for season in selected:
        start = pd.Timestamp(year=int(season), month=7, day=1, tz="UTC")
        end = pd.Timestamp(year=int(season) + 1, month=7, day=1, tz="UTC")
        block = frame[(frame[TIME_COLUMN] >= start) & (frame[TIME_COLUMN] < end)]
        if block.empty:
            continue
        result = _slice_result(block, T, F, theta)
        coverage = _coverage(block, start, end)
        label = f"{season}–{season + 1}"
        if coverage["partial"]:
            label += f" (partial, {coverage['coveragePercent']:.1f}%)"
        rows.append(
            {
                "season": f"{season}-{season + 1}",
                "seasonLabel": label,
                "QupotKgPerM": result["Qupot (kg/m)"],
                "QspotKgPerM": result["Qspot (kg/m)"],
                "srweMm": result["Srwe (mm)"],
                "QinfKgPerM": result["Qinf (kg/m)"],
                "qtKgPerM": result["Qt (kg/m)"],
                "qtTonnesPerM": float(result["Qt (kg/m)"]) / 1_000.0,
                "control": result["Control"],
                "fenceHeightM": fence_height(float(result["Qt (kg/m)"]), fence_type),
                **coverage,
            }
        )
    return pd.DataFrame(rows)


def compute_monthly_results(
    df_all: pd.DataFrame,
    seasons_to_use: Sequence[int],
    T: float,
    F: float,
    theta: float,
) -> pd.DataFrame:
    """Compute Tabler transport for each available July–June calendar month."""
    frame = _prepared_weather(df_all)
    frame["season"] = frame[TIME_COLUMN].dt.year.where(
        frame[TIME_COLUMN].dt.month >= 7, frame[TIME_COLUMN].dt.year - 1
    ).astype(int)
    rows: list[dict[str, object]] = []
    for season in seasons_to_use:
        for month_index in range(1, 13):
            calendar_month = ((month_index + 5) % 12) + 1
            calendar_year = int(season) if calendar_month >= 7 else int(season) + 1
            start = pd.Timestamp(year=calendar_year, month=calendar_month, day=1, tz="UTC")
            end = start + pd.offsets.MonthBegin(1)
            block = frame[(frame[TIME_COLUMN] >= start) & (frame[TIME_COLUMN] < end)]
            if block.empty:
                continue
            result = _slice_result(block, T, F, theta)
            coverage = _coverage(block, start, end)
            rows.append(
                {
                    "season": int(season),
                    "seasonLabel": f"{season}–{season + 1}",
                    "seasonMonth": month_index,
                    "month": start.strftime("%b"),
                    "monthStart": start.date().isoformat(),
                    "qtKgPerM": result["Qt (kg/m)"],
                    "qtTonnesPerM": float(result["Qt (kg/m)"]) / 1_000.0,
                    "control": result["Control"],
                    **coverage,
                }
            )
    return pd.DataFrame(rows)


def average_sectors(df_seasoned: pd.DataFrame, seasons: Sequence[int] | None = None) -> list[float]:
    """Average each directional potential-transport sector across available seasons."""
    frame = _prepared_weather(df_seasoned)
    frame["season"] = frame[TIME_COLUMN].dt.year.where(
        frame[TIME_COLUMN].dt.month >= 7, frame[TIME_COLUMN].dt.year - 1
    ).astype(int)
    selected = list(seasons) if seasons is not None else sorted(frame["season"].unique())
    values = []
    for season in selected:
        block = frame[frame["season"] == season]
        if not block.empty:
            values.append(
                sector_transport(block[WIND_SPEED_COLUMN], block[WIND_DIRECTION_COLUMN])
            )
    return list(np.mean(np.asarray(values), axis=0)) if values else [0.0] * 16


def analyze_snow_drift(
    weather: pd.DataFrame,
    start_season: int,
    end_season: int,
    T: float,
    F: float,
    theta: float,
    fence_type: str,
) -> dict[str, object]:
    """Return complete seasonal, monthly, directional, and coverage results."""
    if end_season - start_season + 1 > 25:
        raise ValueError("at most 25 seasons can be analysed at once")
    fence_factor(fence_type)
    prepared = _prepared_weather(weather)
    start_date, end_date = season_span(start_season, end_season)
    start = pd.Timestamp(start_date, tz="UTC")
    end = pd.Timestamp(end_date, tz="UTC")
    prepared = prepared[(prepared[TIME_COLUMN] >= start) & (prepared[TIME_COLUMN] < end)]
    if prepared.empty:
        raise ValueError("weather data has no observations in the requested seasons")
    seasons = list(range(start_season, end_season + 1))
    yearly = compute_yearly(
        prepared, T, F, theta, seasons=seasons, fence_type=fence_type
    )
    monthly = compute_monthly_results(prepared, seasons, T, F, theta)
    sectors = average_sectors(prepared, seasons)
    overall = _coverage(prepared, start, end)
    return {
        "seasonal": yearly.to_dict(orient="records"),
        "monthly": monthly.to_dict(orient="records"),
        "directional": [
            {
                "sector": label,
                "degrees": index * 22.5,
                "transportKgPerM": float(sectors[index]),
                "transportTonnesPerM": float(sectors[index]) / 1_000.0,
            }
            for index, label in enumerate(DIRECTION_LABELS)
        ],
        "averageSeasonalQtKgPerM": float(yearly["qtKgPerM"].mean()),
        "averageSeasonalQtTonnesPerM": float(yearly["qtTonnesPerM"].mean()),
        "averageFenceHeightM": float(yearly["fenceHeightM"].mean()),
        "coverage": {
            **overall,
            "start": prepared[TIME_COLUMN].iloc[0].isoformat(),
            "end": (prepared[TIME_COLUMN].iloc[-1] + pd.Timedelta(hours=1)).isoformat(),
            "requestedStart": start.isoformat(),
            "requestedEnd": end.isoformat(),
        },
    }
