"""Shared readers for published observations; ordinary views never fetch upstream."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
import json
import os
from pathlib import Path
import sqlite3

from fastapi import HTTPException
import pandas as pd

from app_core.ingestion.models import AREAS, BASE_GROUPS, KNOWN_GROUPS
from app_core.ingestion.store import EnergyStore
from app_core.loaders import weather

ROOT = Path(__file__).resolve().parents[1]
ENERGY_COLUMNS = ["timestamp", "area", "kind", "group", "value", "unit", "source", "retrieved_at", "revision", "quality"]


def database_path() -> Path:
    return Path(os.environ.get("ENERGY_DATABASE", ROOT / "data" / "energy.sqlite")).expanduser().resolve()


def file_version(path: Path) -> str:
    info = path.stat()
    return f"{info.st_ino:x}-{info.st_mtime_ns:x}-{info.st_size:x}"


def validate_range(start: date | str, end: date | str, max_days: int = 366) -> tuple[pd.Timestamp, pd.Timestamp]:
    try:
        a, b = pd.Timestamp(start), pd.Timestamp(end)
        a = a.tz_localize("UTC") if a.tzinfo is None else a.tz_convert("UTC")
        b = b.tz_localize("UTC") if b.tzinfo is None else b.tz_convert("UTC")
        if pd.isna(a) or pd.isna(b) or b <= a or b - a > pd.Timedelta(days=max_days):
            raise ValueError()
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(422, f"Choose a positive UTC interval of at most {max_days} days.") from exc
    return a, b


def energy_frame(area: str, start: date | str, end: date | str, kind: str = "production", groups: list[str] | None = None) -> pd.DataFrame:
    a, b = validate_range(start, end)
    if area not in AREAS or kind not in BASE_GROUPS:
        raise HTTPException(422, "Choose a valid price area and energy kind.")
    selected = list(BASE_GROUPS[kind]) if groups is None else list(groups)
    if any(group not in KNOWN_GROUPS[kind] or group == "*" for group in selected):
        raise HTTPException(422, "Unknown or overlapping aggregate energy group.")
    path = database_path()
    try:
        version = file_version(path)
        rows = EnergyStore(path).query(start=a.to_pydatetime(), end=b.to_pydatetime(), areas=[area], kinds=[kind], groups=selected) if selected else []
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, "The published energy snapshot is unavailable.") from exc
    result = pd.DataFrame(rows, columns=ENERGY_COLUMNS)
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result.attrs["provenance"] = {"source": "Synthetic fixture — not observations" if os.environ.get("ENERGY_DATA_MODE") == "fixture" else "Elhub Energy Data API", "version": version, "unit": "kWh", "timezone": "UTC", "start": a.isoformat(), "end": b.isoformat()}
    return result


@lru_cache(maxsize=12)
def _weather_year(path: str, version: str, area: str, year: int) -> pd.DataFrame:
    lat, lon = weather.AREA_COORDS[area]
    identity = weather._identity(area, lat, lon, year)
    found = weather._read_snapshot(Path(path), identity)
    if found is None:
        raise HTTPException(503, f"No validated weather snapshot for {area}, {year}. Run the data refresh first.")
    frame, metadata = found
    weather._attach_metadata(frame, {**metadata, "version": version, "cache_status": "snapshot"})
    return frame


def weather_frame(area: str, start: date | str, end: date | str) -> pd.DataFrame:
    a, b = validate_range(start, end)
    if area not in AREAS:
        raise HTTPException(422, "Choose a valid price area.")
    annual = []
    sources = []
    lat, lon = weather.AREA_COORDS[area]
    for year in range(a.year, (b - pd.Timedelta(nanoseconds=1)).year + 1):
        identity = weather._identity(area, lat, lon, year)
        path = weather._snapshot_path(identity)
        try:
            version = file_version(path)
        except OSError as exc:
            raise HTTPException(503, f"No weather snapshot for {area}, {year}. Run the data refresh first.") from exc
        frame = _weather_year(str(path), version, area, year)
        annual.append(frame)
        sources.append(dict(frame.attrs.get("provenance", {})))
    result = pd.concat(annual, ignore_index=True)
    result = result[(result["time"] >= a) & (result["time"] < b)].copy().reset_index(drop=True)
    expected = int((b-a).total_seconds() / 3600)
    metadata = {
        "source": "Synthetic fixture — not observations" if os.environ.get("ENERGY_DATA_MODE") == "fixture" else weather.SOURCE, "model": weather.MODEL, "units": weather.EXPECTED_UNITS,
        "location": area, "latitude": lat, "longitude": lon,
        "spatialMeaning": "Fixed city proxy for the price area, not an area-average weather field.",
        "requested_start": a.isoformat(), "requested_end": b.isoformat(), "timezone": "UTC",
        "expectedHours": expected, "observedHours": len(result),
        "coverage_complete": bool(len(result) == expected and result[list(weather.OUTPUT_COLUMNS.values())].notna().all().all()),
        "annual_provenance": sources, "cache_status": "snapshot",
    }
    weather._attach_metadata(result, metadata)
    return result


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso", double_precision=15))


def provenance(area: str, start: date | str, end: date | str) -> dict:
    path = database_path()
    try:
        version = file_version(path)
    except OSError:
        version = None
    return {"area": area, "start": str(start), "end": str(end), "timezone": "UTC", "interval": "[start, end)", "energy": {"source": "Synthetic fixture — not observations" if os.environ.get("ENERGY_DATA_MODE") == "fixture" else "Elhub Energy Data API", "version": version}, "weather": {"source": "Synthetic fixture — not observations" if os.environ.get("ENERGY_DATA_MODE") == "fixture" else weather.SOURCE, "model": weather.MODEL, "location": area, "cityProxy": weather.AREA_COORDS.get(area)}}


def energy_daily_frame(area: str, start: date | str, end: date | str, kind: str = "production", groups: list[str] | None = None) -> pd.DataFrame:
    """Read precomputed group sums/counts, falling back for older snapshots."""
    a, b = validate_range(start, end)
    selected = list(BASE_GROUPS.get(kind, ())) if groups is None else list(groups)
    if area not in AREAS or kind not in BASE_GROUPS or any(g not in KNOWN_GROUPS[kind] or g == "*" for g in selected):
        raise HTTPException(422, "Choose valid price area, kind and base groups.")
    path = database_path()
    try:
        with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as connection:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='energy_daily'").fetchone()
            if exists and a == a.normalize() and b == b.normalize() and selected:
                marks = ','.join('?' for _ in selected)
                result = pd.read_sql_query(
                    f"SELECT day AS timestamp, area, kind, energy_group AS 'group', value, observed_hours, minimum, maximum FROM energy_daily WHERE area=? AND kind=? AND day>=? AND day<? AND energy_group IN ({marks}) ORDER BY day, energy_group",
                    connection, params=[area, kind, a.date().isoformat(), b.date().isoformat(), *selected],
                )
                result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
                result.attrs["precomputed"] = True
                return result
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, "The published energy snapshot is unavailable.") from exc
    frame = energy_frame(area, start, end, kind, selected)
    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "area", "kind", "group", "value", "observed_hours", "minimum", "maximum"])
    frame["timestamp"] = frame["timestamp"].dt.floor("D")
    result = frame.groupby(["timestamp", "area", "kind", "group"], as_index=False).agg(value=("value", lambda x: x.sum(min_count=1)), observed_hours=("value", "count"), minimum=("value", "min"), maximum=("value", "max"))
    result.attrs["precomputed"] = False
    return result
