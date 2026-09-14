from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
import sqlite3
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pandas as pd
from pymongo import MongoClient
import streamlit as st


COLL_PROD_2021 = "prod_hour"
COLL_PROD_2224 = "elhub_production_mba_hour"
COLL_CONS_2124 = "elhub_consumption_mba_hour"
COLL_PROD_TOTALS_2021 = "prod_year_totals"

ENERGY_COLUMNS = [
    "timestamp", "area", "kind", "group", "value", "unit", "source",
    "retrieved_at", "revision", "quality",
]
DEFAULT_ENERGY_SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "energy.sqlite"
BASE_GROUPS = {
    "production": ("hydro", "other", "solar", "thermal", "wind"),
    "consumption": ("cabin", "household", "primary", "secondary", "tertiary"),
}
PRICE_AREAS = ("NO1", "NO2", "NO3", "NO4", "NO5")
ENERGY_FIRST_SELECTABLE_YEAR = 2021


def _ensure_auth_source(uri: str) -> str:
    p = urlparse(uri)
    q = dict(parse_qsl(p.query))
    q.setdefault("authSource", "admin")
    q.setdefault("retryWrites", "true")
    q.setdefault("w", "majority")
    q.setdefault("appName", "Cluster007")
    return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(q), p.fragment))


@st.cache_resource
def get_db():
    uri = _ensure_auth_source(st.secrets["MONGO_URI"].strip())
    dbname = st.secrets.get("MONGO_DB", "ind320")
    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    return client[dbname]


def get_prod_coll_for_year(year: int):
    db = get_db()
    return db[COLL_PROD_2021] if year == 2021 else db[COLL_PROD_2224]


def get_cons_coll():
    return get_db()[COLL_CONS_2124]


def _utc_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _mongo_datetime(value: Any) -> datetime:
    """Convert a boundary to the naive UTC representation used by legacy Mongo data."""
    return _utc_timestamp(value).tz_localize(None).to_pydatetime()


def _kind_name(kind: str) -> str:
    value = str(kind).strip().lower()
    if value not in {"production", "consumption"}:
        raise ValueError("kind must be 'Production' or 'Consumption'")
    return value


def _empty_energy_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=ENERGY_COLUMNS)


def _energy_store(path: Path = DEFAULT_ENERGY_SNAPSHOT):
    """Build the optional published-snapshot reader without making it an import requirement."""
    try:
        from app_core.ingestion import EnergyStore
    except ImportError:
        return None
    try:
        return EnergyStore(path)
    except (OSError, ValueError, sqlite3.Error):
        return None


@lru_cache(maxsize=4)
def _snapshot_metadata(path: str, version: tuple[int, int, int]) -> tuple[list[dict], dict | None]:
    """Scan coverage once per atomically published file, not once per chart."""
    from app_core.ingestion import EnergyStore
    store = EnergyStore(path)
    return list(store.coverage()), store.common_complete_window()


def _snapshot_version(path: Path) -> tuple[int, int, int]:
    info = path.stat()
    return info.st_ino, info.st_mtime_ns, info.st_size


def _snapshot_state(path: Path = DEFAULT_ENERGY_SNAPSHOT) -> tuple[Any | None, list[dict]]:
    store = _energy_store(path)
    if store is None:
        return None, []
    try:
        coverage, _ = _snapshot_metadata(str(path), _snapshot_version(path))
    except (OSError, ValueError):
        return None, []
    return (store, coverage) if coverage else (None, [])


def _mongo_specs(kinds: Iterable[str]) -> list[tuple[str, str, str]]:
    requested = {_kind_name(kind) for kind in kinds}
    specs: list[tuple[str, str, str]] = []
    if "production" in requested:
        specs.extend([
            (COLL_PROD_2021, "production", "production_group"),
            (COLL_PROD_2224, "production", "production_group"),
        ])
    if "consumption" in requested:
        specs.append((COLL_CONS_2124, "consumption", "consumption_group"))
    return specs


def _load_mongo_energy_records(
    db,
    *,
    start: Any | None,
    end: Any | None,
    areas: Iterable[str] | None,
    kinds: Iterable[str],
    groups: Iterable[str] | None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    area_values = list(areas or [])
    group_values = list(groups or [])
    for coll_name, kind, group_field in _mongo_specs(kinds):
        match: dict[str, Any] = {}
        if area_values:
            match["price_area"] = {"$in": area_values}
        if group_values:
            match[group_field] = {"$in": group_values}
        time_match: dict[str, datetime] = {}
        if start is not None:
            time_match["$gte"] = _mongo_datetime(start)
        if end is not None:
            time_match["$lt"] = _mongo_datetime(end)
        if time_match:
            match["start_time"] = time_match

        projection = {
            "_id": 0, "price_area": 1, group_field: 1, "start_time": 1,
            "quantity_kwh": 1, "source": 1, "retrieved_at": 1,
            "last_updated_time": 1, "revision": 1, "quality": 1,
        }
        try:
            rows = list(db[coll_name].find(match, projection))
        except (KeyError, TypeError):
            rows = []
        if not rows:
            continue
        frame = pd.DataFrame(rows).rename(columns={
            "start_time": "timestamp", "price_area": "area", group_field: "group",
            "quantity_kwh": "value",
        })
        frame["kind"] = kind
        frame["unit"] = "kWh"
        if "source" not in frame:
            frame["source"] = "Elhub (MongoDB legacy store)"
        if "retrieved_at" not in frame:
            frame["retrieved_at"] = pd.NaT
        if "revision" not in frame:
            frame["revision"] = frame.pop("last_updated_time") if "last_updated_time" in frame else pd.NaT
        elif "last_updated_time" in frame:
            frame["revision"] = frame["revision"].combine_first(frame.pop("last_updated_time"))
        if "quality" not in frame:
            frame["quality"] = None
        frames.append(frame[ENERGY_COLUMNS])

    if not frames:
        return _empty_energy_frame()
    result = pd.concat(frames, ignore_index=True)
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True, errors="coerce")
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result = result.dropna(subset=["timestamp", "area", "group", "value"])
    if start is not None:
        result = result[result["timestamp"] >= _utc_timestamp(start)]
    if end is not None:
        result = result[result["timestamp"] < _utc_timestamp(end)]
    return (result.sort_values(["timestamp", "area", "kind", "group"])
            .drop_duplicates(["timestamp", "area", "kind", "group"], keep="last")
            .reset_index(drop=True))


def load_energy_records(
    *,
    start: Any | None = None,
    end: Any | None = None,
    areas: Iterable[str] | None = None,
    kinds: Iterable[str] = ("production", "consumption"),
    groups: Iterable[str] | None = None,
    db=None,
    snapshot_path: Path = DEFAULT_ENERGY_SNAPSHOT,
) -> pd.DataFrame:
    """Load normalized energy records for the UTC half-open interval ``[start, end)``.

    The atomically published SQLite snapshot is preferred when it has validated
    coverage. MongoDB remains a compatibility fallback while Streamlit is kept
    runnable during migration. Supplying ``db`` explicitly selects that fallback.
    """
    normalized_kinds = tuple(_kind_name(kind) for kind in kinds)
    if start is not None and end is not None and _utc_timestamp(start) >= _utc_timestamp(end):
        return _empty_energy_frame()

    if db is None:
        store, _coverage = _snapshot_state(snapshot_path)
        if store is not None:
            rows = store.query(
                start=_utc_timestamp(start).to_pydatetime() if start is not None else None,
                end=_utc_timestamp(end).to_pydatetime() if end is not None else None,
                areas=list(areas) if areas else None,
                kinds=list(normalized_kinds),
                groups=list(groups) if groups else None,
            )
            if not rows:
                return _empty_energy_frame()
            frame = pd.DataFrame(rows).reindex(columns=ENERGY_COLUMNS)
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
            frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
            return frame.dropna(subset=["timestamp", "area", "group", "value"]).reset_index(drop=True)
        db = get_db()

    return _load_mongo_energy_records(
        db, start=start, end=end, areas=areas, kinds=normalized_kinds, groups=groups,
    )


def _mongo_coverage(db) -> list[dict]:
    coverage: list[dict] = []
    for coll_name, kind, group_field in _mongo_specs(("production", "consumption")):
        pipeline = [
            {"$match": {group_field: {"$nin": ["*", "industry", "private", "business"]}}},
            {"$group": {
                "_id": {"area": "$price_area", "group": f"${group_field}"},
                "start": {"$min": "$start_time"},
                "last_observation": {"$max": "$start_time"},
                "count": {"$sum": 1},
            }},
        ]
        for row in db[coll_name].aggregate(pipeline, allowDiskUse=True):
            start = _utc_timestamp(row["start"])
            last = _utc_timestamp(row["last_observation"])
            end = last + pd.Timedelta(hours=1)
            expected = int((end - start) / pd.Timedelta(hours=1))
            count = int(row["count"])
            coverage.append({
                "area": row["_id"]["area"], "kind": kind, "group": row["_id"]["group"],
                "start": start.isoformat(), "end": end.isoformat(),
                "last_observation": last.isoformat(), "count": count,
                "expected_count": expected, "missing_count": max(expected - count, 0),
                "is_complete": count == expected,
            })
    merged: dict[tuple[str, str, str], dict] = {}
    for row in coverage:
        key = (row["area"], row["kind"], row["group"])
        if key not in merged:
            merged[key] = dict(row)
            continue
        current = merged[key]
        current["start"] = min(current["start"], row["start"])
        current["end"] = max(current["end"], row["end"])
        current["last_observation"] = max(current["last_observation"], row["last_observation"])
        current["count"] += row["count"]
        start = _utc_timestamp(current["start"])
        end = _utc_timestamp(current["end"])
        current["expected_count"] = int((end - start) / pd.Timedelta(hours=1))
        current["missing_count"] = max(current["expected_count"] - current["count"], 0)
        current["is_complete"] = current["count"] == current["expected_count"]
    return sorted(merged.values(), key=lambda row: (row["area"], row["kind"], row["group"]))


def _common_window(coverage: list[dict]) -> dict | None:
    expected = {
        (area, kind, group)
        for area in PRICE_AREAS
        for kind, groups in BASE_GROUPS.items()
        for group in groups
    }
    by_key = {
        (row["area"], row["kind"], row["group"]): row
        for row in coverage
        if int(row.get("count", 0)) > 0 and row.get("is_complete", False)
    }
    if not expected.issubset(by_key):
        return None
    usable = [by_key[key] for key in sorted(expected)]
    start = max(_utc_timestamp(row["start"]) for row in usable)
    end = min(_utc_timestamp(row["end"]) for row in usable)
    if start >= end:
        return None
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "last_observation": min(_utc_timestamp(row["last_observation"]) for row in usable).isoformat(),
        "series_count": len(usable),
    }


def available_years_from_window(window: dict | None) -> list[int]:
    if not window:
        return []
    start = _utc_timestamp(window["start"])
    end = _utc_timestamp(window["end"])
    if end <= start:
        return []
    return list(range(start.year, (end - pd.Timedelta(nanoseconds=1)).year + 1))


def available_years_from_coverage(
    coverage: Iterable[dict],
    *,
    area: str | None = None,
    kinds: Iterable[str] | None = None,
    groups: Iterable[str] | None = None,
) -> list[int]:
    """Derive selectable years from actual validated observations.

    This intentionally does not require the all-series common window. A category
    that begins later must not hide otherwise valid historical data for an area.
    """
    kind_values = {_kind_name(kind) for kind in kinds} if kinds else None
    group_values = set(groups) if groups else None
    years: set[int] = set()
    for row in coverage:
        if int(row.get("count", 0)) <= 0:
            continue
        if area is not None and row.get("area") != area:
            continue
        if kind_values is not None and row.get("kind") not in kind_values:
            continue
        if group_values is not None and row.get("group") not in group_values:
            continue
        start = _utc_timestamp(row["start"])
        end = _utc_timestamp(row["end"])
        if end > start:
            first_year = max(start.year, ENERGY_FIRST_SELECTABLE_YEAR)
            final_year = (end - pd.Timedelta(nanoseconds=1)).year
            if final_year >= first_year:
                years.update(range(first_year, final_year + 1))
    return sorted(years)


def get_energy_status(*, db=None, snapshot_path: Path = DEFAULT_ENERGY_SNAPSHOT) -> dict:
    """Return source and validated coverage metadata for date controls and labels."""
    store = None
    coverage: list[dict] = []
    common = None
    backend = "mongodb"
    source = "Elhub · MongoDB fallback"
    if db is None:
        store, coverage = _snapshot_state(snapshot_path)
        if store is not None:
            backend = "sqlite"
            source = "Elhub · local validated snapshot"
            _, common = _snapshot_metadata(str(snapshot_path), _snapshot_version(snapshot_path))
    if store is None:
        if db is None:
            db = get_db()
        coverage = _mongo_coverage(db)
        common = _common_window(coverage)

    observed = [_utc_timestamp(row["last_observation"]) for row in coverage
                if row.get("last_observation") is not None]
    return {
        "backend": backend, "source": source, "coverage": coverage,
        "common_complete_window": common,
        "available_years": available_years_from_coverage(coverage),
        "common_complete_years": available_years_from_window(common),
        "source_latest_observation": max(observed).isoformat() if observed else None,
    }
