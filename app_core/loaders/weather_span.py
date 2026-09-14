from __future__ import annotations

from datetime import datetime
from typing import Callable

import pandas as pd


def _as_utc(value: datetime | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _unavailable(columns: list[str], metadata: dict) -> pd.DataFrame:
    frame = pd.DataFrame(columns=columns)
    frame["time"] = pd.Series([], dtype="datetime64[ns, UTC]")
    frame.attrs["provenance"] = metadata
    return frame


def load_weather_span_df(
    load_openmeteo_era5: Callable[..., pd.DataFrame],
    area: str,
    start: datetime,
    end: datetime,
    *,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Stitch annual weather into the half-open UTC interval ``[start, end)``."""
    start_ts = _as_utc(start)
    end_ts = _as_utc(end)
    if start_ts >= end_ts:
        raise ValueError("start must be before end")

    frames: list[pd.DataFrame] = []
    annual_provenance: list[dict] = []
    final_year = (end_ts - pd.Timedelta(nanoseconds=1)).year
    for year in range(start_ts.year, final_year + 1):
        if force_refresh:
            weather = load_openmeteo_era5(area, year, force_refresh=True).copy()
        else:
            weather = load_openmeteo_era5(area, year).copy()
        annual_provenance.append(dict(weather.attrs.get("provenance", {})))
        if not weather.empty:
            weather["time"] = pd.to_datetime(weather["time"], utc=True, errors="coerce")
            frames.append(weather)

    request_metadata = {
        "location": area,
        "requested_start": start_ts.isoformat(),
        "requested_end": end_ts.isoformat(),
        "annual_provenance": annual_provenance,
    }
    if not frames or any(item.get("cache_status") == "unavailable" for item in annual_provenance):
        columns = list(frames[0].columns) if frames else ["time"]
        errors = [item["error"] for item in annual_provenance if item.get("error")]
        metadata = {**request_metadata, "cache_status": "unavailable", "coverage_complete": False}
        if errors:
            metadata["error"] = "; ".join(errors)
        return _unavailable(columns, metadata)

    result = pd.concat(frames, ignore_index=True)
    columns = list(result.columns)
    result = result[(result["time"] >= start_ts) & (result["time"] < end_ts)]
    result = result.sort_values("time").reset_index(drop=True)
    if result.empty:
        return _unavailable(columns, {**request_metadata, "cache_status": "unavailable"})
    if result["time"].isna().any() or result["time"].duplicated().any():
        return _unavailable(
            columns,
            {**request_metadata, "cache_status": "unavailable", "error": "invalid or duplicate timestamps"},
        )
    deltas = result["time"].diff().dropna()
    if not deltas.empty and not deltas.eq(pd.Timedelta(hours=1)).all():
        return _unavailable(
            columns,
            {**request_metadata, "cache_status": "unavailable", "error": "gap in hourly weather data"},
        )

    source_metadata = next((item for item in annual_provenance if item), {})
    cache_states = {item.get("cache_status") for item in annual_provenance}
    metadata = {
        **{key: source_metadata[key] for key in ("source", "model", "variables", "units") if key in source_metadata},
        **request_metadata,
        "available_start": result["time"].iloc[0].isoformat(),
        "available_end": (result["time"].iloc[-1] + pd.Timedelta(hours=1)).isoformat(),
        "cache_status": "stale_snapshot" if "stale_snapshot" in cache_states else (
            "network" if "network" in cache_states else "snapshot"
        ),
        "coverage_complete": result["time"].iloc[0] <= start_ts and (
            result["time"].iloc[-1] + pd.Timedelta(hours=1) >= end_ts
        ),
    }
    result.attrs["provenance"] = metadata
    for key, value in metadata.items():
        if key != "annual_provenance":
            result.attrs[key] = value
    return result
