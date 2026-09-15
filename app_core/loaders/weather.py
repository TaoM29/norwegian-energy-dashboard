from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests


AREA_COORDS = {
    "NO1": (59.9139, 10.7522),
    "NO2": (58.1467, 7.9956),
    "NO3": (63.4305, 10.3951),
    "NO4": (69.6492, 18.9553),
    "NO5": (60.3913, 5.3221),
}

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
SOURCE = "Open-Meteo Historical Weather API"
MODEL = "era5_seamless"
ERA5_FIRST_DAY = date(1940, 1, 1)
ERA5_DELAY_DAYS = 5
WEATHER_MAX_ATTEMPTS = 3
WEATHER_RETRY_BACKOFF_SECONDS = 0.5
CURRENT_SNAPSHOT_TTL = timedelta(hours=6)
WEATHER_SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "data" / "weather"
WEATHER_SNAPSHOT_DIR_ENV = "WEATHER_SNAPSHOT_DIR"

HOURLY_VARIABLES = (
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
)
OUTPUT_COLUMNS = {
    "temperature_2m": "temperature_2m (°C)",
    "precipitation": "precipitation (mm)",
    "wind_speed_10m": "wind_speed_10m (m/s)",
    "wind_gusts_10m": "wind_gusts_10m (m/s)",
    "wind_direction_10m": "wind_direction_10m (°)",
}
EXPECTED_UNITS = {
    "time": "iso8601",
    "temperature_2m": "°C",
    "precipitation": "mm",
    "wind_speed_10m": "m/s",
    "wind_gusts_10m": "m/s",
    "wind_direction_10m": "°",
}


def era5_available_end(now: datetime | None = None) -> pd.Timestamp:
    """Exclusive UTC boundary after the latest ERA5 day expected to be available."""
    current = now or datetime.now(timezone.utc)
    latest_day = current.astimezone(timezone.utc).date() - timedelta(days=ERA5_DELAY_DAYS)
    return pd.Timestamp(latest_day + timedelta(days=1), tz="UTC")


def era5_available_range(now: datetime | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return Open-Meteo ERA5-Seamless source coverage as UTC half-open bounds."""
    return pd.Timestamp(ERA5_FIRST_DAY, tz="UTC"), era5_available_end(now)


def _utc_timestamp(value: date | datetime | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _attach_metadata(frame: pd.DataFrame, provenance: dict[str, Any]) -> None:
    metadata = dict(provenance)
    frame.attrs["provenance"] = metadata
    for key in (
        "source", "model", "location", "variables", "units", "requested_start",
        "requested_end", "available_start", "available_end", "retrieved_at", "cache_status",
        "coverage_complete", "publication_lag_days", "source_expected_available_end",
        "source_coverage_complete", "variable_last_timestamp",
    ):
        if key in metadata:
            frame.attrs[key] = metadata[key]


def _empty_weather(provenance: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame({"time": pd.Series([], dtype="datetime64[ns, UTC]")})
    for output_name in OUTPUT_COLUMNS.values():
        frame[output_name] = pd.Series([], dtype="float64")
    _attach_metadata(frame, provenance)
    return frame


def _identity(location: str, latitude: float, longitude: float, year: int) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "model": MODEL,
        "location": location,
        "latitude": round(float(latitude), 6),
        "longitude": round(float(longitude), 6),
        "variables": list(HOURLY_VARIABLES),
        "year": int(year),
    }


def _snapshot_path(identity: dict[str, Any]) -> Path:
    raw_key = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw_key).hexdigest()[:20]
    configured = os.environ.get(WEATHER_SNAPSHOT_DIR_ENV)
    snapshot_dir = Path(configured).expanduser() if configured else WEATHER_SNAPSHOT_DIR
    return snapshot_dir / f"{identity['year']}-{digest}.json"


def _read_snapshot(path: Path, identity: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("identity") != identity:
            return None
        metadata = document["metadata"]
        frame = pd.DataFrame.from_records(document["records"])
        if not frame.empty:
            frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="raise")
        frame = _validate_frame(frame)
        metadata.setdefault(
            "variable_last_timestamp",
            {name: frame["time"].iloc[-1].isoformat() for name in HOURLY_VARIABLES},
        )
        return frame, metadata
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _write_snapshot(
    path: Path, identity: dict[str, Any], metadata: dict[str, Any], frame: pd.DataFrame
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = frame.assign(time=frame["time"].map(lambda value: value.isoformat())).to_dict("records")
    document = {"identity": identity, "metadata": metadata, "records": records}
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            json.dump(document, temporary, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _validate_frame(frame: pd.DataFrame) -> pd.DataFrame:
    expected = ["time", *OUTPUT_COLUMNS.values()]
    if list(frame.columns) != expected:
        raise ValueError("Open-Meteo returned an unexpected hourly schema")
    if frame.empty:
        raise ValueError("Open-Meteo returned no hourly weather data")
    if frame["time"].isna().any() or frame["time"].duplicated().any():
        raise ValueError("Open-Meteo returned invalid or duplicate timestamps")

    frame = frame.sort_values("time").reset_index(drop=True)
    deltas = frame["time"].diff().dropna()
    if not deltas.empty and not deltas.eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Open-Meteo returned a gap in hourly weather data")
    for column in OUTPUT_COLUMNS.values():
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    values = frame[list(OUTPUT_COLUMNS.values())]
    if values.isna().any().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("Open-Meteo returned missing, non-numeric, or non-finite weather values")
    if not frame["temperature_2m (°C)"].between(-100, 70).all():
        raise ValueError("Open-Meteo returned an impossible temperature")
    if (frame["precipitation (mm)"] < 0).any():
        raise ValueError("Open-Meteo returned negative precipitation")
    if (frame[["wind_speed_10m (m/s)", "wind_gusts_10m (m/s)"]] < 0).any().any():
        raise ValueError("Open-Meteo returned a negative wind speed")
    if not frame["wind_direction_10m (°)"].between(0, 360).all():
        raise ValueError("Open-Meteo returned an invalid wind direction")
    return frame


def _frame_from_response(
    payload: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, str], pd.Timestamp]:
    hourly = payload.get("hourly")
    units = payload.get("hourly_units")
    if not isinstance(hourly, dict) or not isinstance(units, dict):
        raise ValueError("Open-Meteo returned no hourly data or units")
    for variable, expected_unit in EXPECTED_UNITS.items():
        if units.get(variable) != expected_unit:
            raise ValueError(f"Open-Meteo returned unexpected units for {variable}")
    lengths = {len(hourly.get(name, [])) for name in ("time", *HOURLY_VARIABLES)}
    if len(lengths) != 1:
        raise ValueError("Open-Meteo returned hourly arrays of different lengths")
    frame = pd.DataFrame({
        "time": pd.to_datetime(hourly.get("time", []), utc=True, errors="coerce"),
        **{OUTPUT_COLUMNS[name]: hourly.get(name, []) for name in HOURLY_VARIABLES},
    })
    if frame.empty or frame["time"].isna().any() or frame["time"].duplicated().any():
        raise ValueError("Open-Meteo returned invalid or duplicate timestamps")
    frame = frame.sort_values("time").reset_index(drop=True)
    deltas = frame["time"].diff().dropna()
    if not deltas.empty and not deltas.eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Open-Meteo returned a gap in hourly timestamps")

    variable_last_timestamp: dict[str, str] = {}
    variable_ends: list[pd.Timestamp] = []
    for source_name, output_name in OUTPUT_COLUMNS.items():
        values = pd.to_numeric(frame[output_name], errors="coerce")
        finite = pd.Series(np.isfinite(values.to_numpy(dtype=float)), index=frame.index)
        valid_positions = frame.index[finite]
        if valid_positions.empty:
            raise ValueError(f"Open-Meteo returned no available values for {source_name}")
        last_position = int(valid_positions[-1])
        if not finite.iloc[: last_position + 1].all():
            raise ValueError(f"Open-Meteo returned an internal missing or non-finite value for {source_name}")
        last_timestamp = frame.loc[last_position, "time"]
        variable_last_timestamp[source_name] = last_timestamp.isoformat()
        variable_ends.append(last_timestamp + pd.Timedelta(hours=1))
        frame[output_name] = values

    common_end = min(variable_ends).floor("D")
    frame = frame[frame["time"] < common_end].reset_index(drop=True)
    if frame.empty:
        raise ValueError("Open-Meteo returned no complete UTC day across all variables")
    return _validate_frame(frame), variable_last_timestamp, common_end


def _is_transient_request_error(error: requests.RequestException) -> bool:
    if isinstance(error, (requests.ConnectionError, requests.Timeout)):
        return True
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code == 429 or (isinstance(status_code, int) and status_code >= 500)


def _request_payload(params: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(1, WEATHER_MAX_ATTEMPTS + 1):
        try:
            response = requests.get(ARCHIVE_URL, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            if attempt >= WEATHER_MAX_ATTEMPTS or not _is_transient_request_error(error):
                raise
            time.sleep(WEATHER_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
    raise RuntimeError("weather request retry loop ended unexpectedly")


def _load_location_year(
    *, latitude: float, longitude: float, location: str, year: int, force_refresh: bool
) -> pd.DataFrame:
    identity = _identity(location, latitude, longitude, year)
    snapshot_path = _snapshot_path(identity)
    snapshot = _read_snapshot(snapshot_path, identity)
    if os.environ.get("ENERGY_DATA_MODE") == "fixture":
        if snapshot is None or not snapshot[1].get("synthetic"):
            raise ValueError("No synthetic weather fixture for this point/year. Use 61.5, 9.0 and seasons 2021–2025, or switch to published data.")
        frame, metadata = snapshot
        _attach_metadata(frame, {**metadata, "cache_status": "fixture"})
        return frame
    requested_start = pd.Timestamp(year=year, month=1, day=1, tz="UTC")
    requested_end = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
    source_end = era5_available_end()
    effective_start = max(requested_start, pd.Timestamp(ERA5_FIRST_DAY, tz="UTC"))
    effective_end = min(requested_end, source_end)
    base_metadata: dict[str, Any] = {
        **identity,
        "units": {OUTPUT_COLUMNS[name]: EXPECTED_UNITS[name] for name in HOURLY_VARIABLES},
        "requested_start": requested_start.isoformat(),
        "requested_end": requested_end.isoformat(),
        "publication_lag_days": ERA5_DELAY_DAYS,
        "source_available_start": pd.Timestamp(ERA5_FIRST_DAY, tz="UTC").isoformat(),
        "source_expected_available_end": source_end.isoformat(),
    }
    if effective_start >= effective_end:
        return _empty_weather({**base_metadata, "cache_status": "unavailable", "error": "outside source coverage"})

    if snapshot and not force_refresh:
        cached_frame, cached_metadata = snapshot
        cached_end = _utc_timestamp(cached_metadata["available_end"])
        retrieved_at = cached_metadata.get("retrieved_at")
        recently_checked = False
        if retrieved_at:
            retrieved_ts = _utc_timestamp(retrieved_at)
            recently_checked = datetime.now(timezone.utc) - retrieved_ts.to_pydatetime() <= CURRENT_SNAPSHOT_TTL
        current_partial_year = requested_end > source_end
        if cached_end >= effective_end or (current_partial_year and recently_checked):
            cached_metadata = {**cached_metadata, "cache_status": "snapshot"}
            _attach_metadata(cached_frame, cached_metadata)
            return cached_frame

    params = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "start_date": effective_start.date().isoformat(),
        "end_date": (effective_end - pd.Timedelta(days=1)).date().isoformat(),
        "hourly": ",".join(HOURLY_VARIABLES),
        "models": MODEL,
        "temperature_unit": "celsius",
        "wind_speed_unit": "ms",
        "precipitation_unit": "mm",
        "timezone": "UTC",
    }
    try:
        frame, variable_last_timestamp, response_common_end = _frame_from_response(_request_payload(params))
        actual_end = min(effective_end, response_common_end)
        if requested_end <= source_end and actual_end < effective_end:
            raise ValueError("Open-Meteo returned incomplete coverage for a fully published year")
        frame = frame[(frame["time"] >= effective_start) & (frame["time"] < actual_end)].reset_index(drop=True)
        frame = _validate_frame(frame)
        if frame["time"].iloc[0] != effective_start or frame["time"].iloc[-1] + pd.Timedelta(hours=1) != actual_end:
            raise ValueError("Open-Meteo returned incomplete requested coverage")
        if snapshot:
            cached_frame, cached_metadata = snapshot
            cached_end = _utc_timestamp(cached_metadata["available_end"])
            if cached_end > actual_end:
                cached_metadata = {
                    **cached_metadata,
                    "cache_status": "stale_snapshot",
                    "refresh_error": "source response ended before the existing validated snapshot",
                }
                _attach_metadata(cached_frame, cached_metadata)
                return cached_frame
        metadata = {
            **base_metadata,
            "available_start": frame["time"].iloc[0].isoformat(),
            "available_end": (frame["time"].iloc[-1] + pd.Timedelta(hours=1)).isoformat(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "cache_status": "network",
            "coverage_complete": actual_end >= requested_end,
            "source_coverage_complete": actual_end >= effective_end,
            "variable_last_timestamp": variable_last_timestamp,
        }
        _write_snapshot(snapshot_path, identity, metadata, frame)
        _attach_metadata(frame, metadata)
        return frame
    except (requests.RequestException, RuntimeError, ValueError, TypeError, KeyError) as error:
        if snapshot:
            cached_frame, cached_metadata = snapshot
            cached_metadata = {**cached_metadata, "cache_status": "stale_snapshot", "refresh_error": str(error)}
            _attach_metadata(cached_frame, cached_metadata)
            return cached_frame
        return _empty_weather({**base_metadata, "cache_status": "unavailable", "error": str(error)})


def load_openmeteo_point(
    latitude: float,
    longitude: float,
    start: date | datetime | pd.Timestamp,
    end: date | datetime | pd.Timestamp,
    *,
    location_key: str | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Load hourly ERA5-Seamless weather for the half-open UTC interval ``[start, end)``."""
    start_ts = _utc_timestamp(start)
    end_ts = _utc_timestamp(end)
    if start_ts >= end_ts:
        raise ValueError("start must be before end")
    if not (-90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180):
        raise ValueError("invalid latitude or longitude")

    effective_end = min(end_ts, era5_available_end())
    location = location_key or f"point:{float(latitude):.6f},{float(longitude):.6f}"
    frames: list[pd.DataFrame] = []
    provenance: list[dict[str, Any]] = []
    if start_ts < effective_end:
        final_year = (effective_end - pd.Timedelta(nanoseconds=1)).year
        for year in range(start_ts.year, final_year + 1):
            annual = _load_location_year(
                latitude=float(latitude), longitude=float(longitude), location=location,
                year=year, force_refresh=force_refresh,
            )
            provenance.append(dict(annual.attrs.get("provenance", {})))
            if not annual.empty:
                frames.append(annual)

    base = {
        "source": SOURCE,
        "model": MODEL,
        "location": location,
        "latitude": float(latitude),
        "longitude": float(longitude),
        "variables": list(HOURLY_VARIABLES),
        "units": {OUTPUT_COLUMNS[name]: EXPECTED_UNITS[name] for name in HOURLY_VARIABLES},
        "requested_start": start_ts.isoformat(),
        "requested_end": end_ts.isoformat(),
        "publication_lag_days": ERA5_DELAY_DAYS,
        "source_available_start": pd.Timestamp(ERA5_FIRST_DAY, tz="UTC").isoformat(),
        "source_expected_available_end": era5_available_end().isoformat(),
        "annual_provenance": provenance,
    }
    if not frames or any(item.get("cache_status") == "unavailable" for item in provenance):
        errors = [item["error"] for item in provenance if item.get("error")]
        metadata = {**base, "cache_status": "unavailable", "coverage_complete": False}
        if errors:
            metadata["error"] = "; ".join(errors)
        return _empty_weather(metadata)

    frame = pd.concat(frames, ignore_index=True)
    frame = frame[(frame["time"] >= start_ts) & (frame["time"] < effective_end)].reset_index(drop=True)
    try:
        frame = _validate_frame(frame)
    except ValueError as error:
        return _empty_weather({**base, "cache_status": "unavailable", "error": str(error)})
    cache_states = {item.get("cache_status") for item in provenance}
    status = "stale_snapshot" if "stale_snapshot" in cache_states else (
        "network" if "network" in cache_states else "snapshot"
    )
    metadata = {
        **base,
        "available_start": frame["time"].iloc[0].isoformat(),
        "available_end": (frame["time"].iloc[-1] + pd.Timedelta(hours=1)).isoformat(),
        "retrieved_at": max((item.get("retrieved_at", "") for item in provenance), default=""),
        "cache_status": status,
        "coverage_complete": frame["time"].iloc[0] <= max(
            start_ts, pd.Timestamp(ERA5_FIRST_DAY, tz="UTC")
        ) and frame["time"].iloc[-1] + pd.Timedelta(hours=1) >= end_ts,
        "source_coverage_complete": frame["time"].iloc[0] <= max(
            start_ts, pd.Timestamp(ERA5_FIRST_DAY, tz="UTC")
        ) and frame["time"].iloc[-1] + pd.Timedelta(hours=1) >= effective_end,
        "variable_last_timestamp": {
            variable: max(
                (item.get("variable_last_timestamp", {}).get(variable, "") for item in provenance),
                default="",
            )
            for variable in HOURLY_VARIABLES
        },
    }
    refresh_errors = [item["refresh_error"] for item in provenance if item.get("refresh_error")]
    if refresh_errors:
        metadata["refresh_error"] = "; ".join(refresh_errors)
    _attach_metadata(frame, metadata)
    return frame


def load_openmeteo_era5(
    area: str, year: int, timezone: str = "UTC", *, force_refresh: bool = False
) -> pd.DataFrame:
    """Load one calendar year's available weather in UTC, preserving legacy column names."""
    if area not in AREA_COORDS:
        raise KeyError(area)
    if timezone != "UTC":
        raise ValueError("weather is loaded in UTC; convert only when displaying it")
    year = int(year)
    latitude, longitude = AREA_COORDS[area]
    return load_openmeteo_point(
        latitude,
        longitude,
        pd.Timestamp(year=year, month=1, day=1, tz="UTC"),
        pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC"),
        location_key=area,
        force_refresh=force_refresh,
    )
