from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

import numpy as np
import pandas as pd


Aggregation = Literal["hourly", "daily", "weekly"]

WEATHER_VARIABLES: dict[str, dict[str, str]] = {
    "temperature": {
        "column": "temperature_2m (°C)",
        "label": "Temperature",
        "unit": "°C",
        "aggregation": "mean",
    },
    "precipitation": {
        "column": "precipitation (mm)",
        "label": "Precipitation",
        "unit": "mm",
        "aggregation": "sum",
    },
    "wind_speed": {
        "column": "wind_speed_10m (m/s)",
        "label": "Wind speed",
        "unit": "m/s",
        "aggregation": "mean",
    },
    "wind_gusts": {
        "column": "wind_gusts_10m (m/s)",
        "label": "Wind gusts",
        "unit": "m/s",
        "aggregation": "mean",
    },
    "wind_direction": {
        "column": "wind_direction_10m (°)",
        "label": "Wind direction",
        "unit": "°",
        "aggregation": "circular mean",
    },
}

WIND_SECTORS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)

_RESAMPLE_RULES: dict[Aggregation, str] = {
    "hourly": "h",
    "daily": "D",
    # This preserves the Streamlit explorer's pandas `W` convention: bins end
    # on Sunday and are labeled with the Sunday timestamp in UTC.
    "weekly": "W",
}


def _utc(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="coerce")


def _finite(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.where(np.isfinite(numeric))


def circular_mean(values: Iterable[float]) -> float:
    """Return a degree mean on the unit circle, or NaN for no usable values."""
    numeric = pd.to_numeric(pd.Series(values, dtype="float64"), errors="coerce")
    numeric = numeric[np.isfinite(numeric)]
    if numeric.empty:
        return float("nan")
    radians = np.deg2rad(numeric.to_numpy(dtype=float) % 360.0)
    sine = float(np.sin(radians).mean())
    cosine = float(np.cos(radians).mean())
    if np.isclose(sine, 0.0) and np.isclose(cosine, 0.0):
        return float("nan")
    result = float(np.rad2deg(np.arctan2(sine, cosine)) % 360.0)
    return 0.0 if np.isclose(result, 360.0) else result


def _resample_direction(series: pd.Series, rule: str) -> pd.Series:
    numeric = _finite(series)
    radians = np.deg2rad(numeric % 360.0)
    sine = np.sin(radians).resample(rule).mean()
    cosine = np.cos(radians).resample(rule).mean()
    magnitude = np.hypot(sine, cosine)
    degrees = np.rad2deg(np.arctan2(sine, cosine)) % 360.0
    return degrees.where(magnitude > 1e-12)


def _rolling_direction(series: pd.Series, hours: int) -> pd.Series:
    numeric = _finite(series)
    radians = np.deg2rad(numeric % 360.0)
    sine = np.sin(radians).rolling(f"{hours}h").mean()
    cosine = np.cos(radians).rolling(f"{hours}h").mean()
    magnitude = np.hypot(sine, cosine)
    degrees = np.rad2deg(np.arctan2(sine, cosine)) % 360.0
    return degrees.where(magnitude > 1e-12)


def energy_exploration(
    frame: pd.DataFrame,
    *,
    aggregation: Aggregation,
    groups: list[str],
) -> dict[str, Any]:
    """Calculate exact group totals and an aggregated energy series.

    Totals are calculated from the filtered source observations before any
    chart-oriented aggregation or rendering cap is applied by a client.
    """
    if aggregation not in _RESAMPLE_RULES:
        raise ValueError("unsupported energy aggregation")
    expected = {"timestamp", "group", "value"}
    if not expected.issubset(frame.columns):
        raise ValueError("energy frame is missing required columns")

    values = frame.loc[frame["group"].isin(groups), ["timestamp", "group", "value"]].copy()
    values["timestamp"] = _utc(values["timestamp"])
    values["value"] = _finite(values["value"])
    values = values.dropna(subset=["timestamp"]).sort_values(["timestamp", "group"])
    daily_source = "observed_hours" in frame.columns
    if daily_source:
        values["observed_hours"] = pd.to_numeric(
            frame.loc[values.index, "observed_hours"], errors="coerce"
        ).fillna(0).astype(int)

    totals: list[dict[str, Any]] = []
    for group in groups:
        group_values = values.loc[values["group"] == group]
        finite_values = group_values["value"].dropna()
        observed_hours = (
            int(group_values.loc[group_values["value"].notna(), "observed_hours"].sum())
            if daily_source
            else int(group_values.loc[group_values["value"].notna(), "timestamp"].nunique())
        )
        totals.append(
            {
                "group": group,
                "totalKwh": (
                    float(finite_values.sum(min_count=1)) if not finite_values.empty else None
                ),
                "observations": observed_hours if daily_source else int(finite_values.size),
                "observedHours": observed_hours,
            }
        )

    rule = _RESAMPLE_RULES[aggregation]
    rows: list[dict[str, Any]] = []
    for group in groups:
        subset = values.loc[values["group"] == group].set_index("timestamp")["value"]
        if subset.empty:
            continue
        # Sum duplicates into their source interval first. Published daily rows
        # already contain exact sums, so they can feed daily and weekly views
        # without expanding them into artificial hourly values.
        source_rule = "D" if daily_source else "h"
        source = subset.resample(source_rule).sum(min_count=1)
        aggregated = source if rule == source_rule else source.resample(rule).sum(min_count=1)
        rows.extend(
            {
                "time": timestamp,
                "group": group,
                "valueKwh": None if pd.isna(value) else float(value),
            }
            for timestamp, value in aggregated.items()
        )
    rows.sort(key=lambda row: (row["time"], groups.index(row["group"])))

    valid_timestamps = values.loc[values["value"].notna(), "timestamp"]
    last_observation = valid_timestamps.max() if not valid_timestamps.empty else None
    if daily_source and last_observation is not None:
        last_observation += pd.Timedelta(hours=23)
    grand_values = [row["totalKwh"] for row in totals if row["totalKwh"] is not None]
    return {
        "grandTotalKwh": float(sum(grand_values)) if grand_values else None,
        "totals": totals,
        "series": rows,
        "coverage": {
            "firstObservation": valid_timestamps.min() if not valid_timestamps.empty else None,
            "lastObservation": last_observation,
            "observations": (
                int(values.loc[values["value"].notna(), "observed_hours"].sum())
                if daily_source
                else int(values["value"].notna().sum())
            ),
        },
    }


def _weather_summary(frame: pd.DataFrame) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for key, metadata in WEATHER_VARIABLES.items():
        values = _finite(frame[metadata["column"]]).dropna()
        if values.empty:
            minimum = mean = maximum = None
        else:
            minimum = float(values.min())
            maximum = float(values.max())
            calculated_mean = circular_mean(values) if key == "wind_direction" else float(values.mean())
            mean = None if pd.isna(calculated_mean) else calculated_mean
        result.append(
            {
                "variable": key,
                "label": metadata["label"],
                "unit": metadata["unit"],
                "min": minimum,
                "mean": mean,
                "max": maximum,
                "observations": int(values.size),
            }
        )
    return result


def _monthly_weather(frame: pd.DataFrame) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    months = frame["time"].dt.month
    for month in range(1, 13):
        row: dict[str, Any] = {"month": month}
        mask = months == month
        for key in ("temperature", "precipitation", "wind_speed", "wind_gusts"):
            metadata = WEATHER_VARIABLES[key]
            values = _finite(frame.loc[mask, metadata["column"]]).dropna()
            value = values.sum(min_count=1) if key == "precipitation" else values.mean()
            row[key] = None if pd.isna(value) else float(value)
        result.append(row)
    return result


def _wind_rose(frame: pd.DataFrame) -> list[dict[str, Any]]:
    column = WEATHER_VARIABLES["wind_direction"]["column"]
    values = _finite(frame[column]).dropna().to_numpy(dtype=float)
    # Keep the existing valid-direction range and share denominator. Each
    # compass label denotes the center of a 22.5° sector; the first sector
    # spans both sides of north and 360° is equivalent to 0°.
    values = values[(values >= 0.0) & (values <= 360.0)]
    indices = np.floor(((values % 360.0) + 11.25) / 22.5).astype(int) % len(WIND_SECTORS)
    counts = np.bincount(indices, minlength=len(WIND_SECTORS))
    total = int(counts.sum())
    return [
        {
            "sector": sector,
            "count": int(count),
            "share": float(count / total) if total else None,
        }
        for sector, count in zip(WIND_SECTORS, counts, strict=True)
    ]


def _weather_series(
    frame: pd.DataFrame,
    *,
    variables: list[str],
    aggregation: Aggregation,
    rolling_hours: int,
    normalize: bool,
) -> list[dict[str, Any]]:
    rule = _RESAMPLE_RULES[aggregation]
    rows: list[dict[str, Any]] = []
    for key in variables:
        metadata = WEATHER_VARIABLES[key]
        series = frame.set_index("time")[metadata["column"]]
        if key == "wind_direction":
            aggregated = _resample_direction(series, rule)
        elif key == "precipitation" and aggregation != "hourly":
            aggregated = _finite(series).resample(rule).sum(min_count=1)
        else:
            aggregated = _finite(series).resample(rule).mean()

        if rolling_hours > 0:
            aggregated = (
                _rolling_direction(aggregated, rolling_hours)
                if key == "wind_direction"
                else aggregated.rolling(f"{rolling_hours}h").mean()
            )

        if normalize:
            minimum = aggregated.min()
            maximum = aggregated.max()
            span = maximum - minimum
            if pd.notna(minimum) and pd.notna(maximum):
                aggregated = (
                    (aggregated - minimum) / span
                    if not np.isclose(float(span), 0.0)
                    else aggregated.where(aggregated.isna(), 0.0)
                )

        rows.extend(
            {
                "time": timestamp,
                "variable": key,
                "value": None if pd.isna(value) else float(value),
            }
            for timestamp, value in aggregated.items()
        )
    rows.sort(key=lambda row: (row["time"], variables.index(row["variable"])))
    return rows


def weather_exploration(
    frame: pd.DataFrame,
    *,
    variables: list[str],
    aggregation: Aggregation,
    rolling_hours: int,
    normalize: bool,
) -> dict[str, Any]:
    """Build weather summaries and explorer values from validated hourly data."""
    if aggregation not in _RESAMPLE_RULES:
        raise ValueError("unsupported weather aggregation")
    if not 0 <= rolling_hours <= 240:
        raise ValueError("rolling_hours must be between 0 and 240")
    unknown = set(variables) - WEATHER_VARIABLES.keys()
    if unknown:
        raise ValueError(f"unknown weather variables: {', '.join(sorted(unknown))}")
    expected = {"time", *(item["column"] for item in WEATHER_VARIABLES.values())}
    if not expected.issubset(frame.columns):
        raise ValueError("weather frame is missing required columns")

    values = frame.loc[:, list(expected)].copy()
    values["time"] = _utc(values["time"])
    values = values.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    for metadata in WEATHER_VARIABLES.values():
        values[metadata["column"]] = _finite(values[metadata["column"]])

    valid_times = values["time"] if not values.empty else pd.Series(dtype="datetime64[ns, UTC]")
    return {
        "summary": _weather_summary(values),
        "monthly": _monthly_weather(values),
        "windRose": _wind_rose(values),
        "series": _weather_series(
            values,
            variables=variables,
            aggregation=aggregation,
            rolling_hours=rolling_hours,
            normalize=normalize,
        ),
        "coverage": {
            "firstObservation": valid_times.min() if not valid_times.empty else None,
            "lastObservation": valid_times.max() if not valid_times.empty else None,
            "observations": int(len(values)),
        },
        "variableDefinitions": [
            {"variable": key, **metadata} for key, metadata in WEATHER_VARIABLES.items()
        ],
        "method": {
            "processingOrder": ["date filter", "aggregation", "rolling mean", "normalization"],
            "precipitation": "sum when aggregated daily or weekly; mean only for a rolling window",
            "otherVariables": "arithmetic mean",
            "windDirection": "circular vector mean for aggregation and rolling windows",
            "weeklyBins": "UTC weeks ending Sunday",
        },
    }
