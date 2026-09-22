from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
from typing import Iterator, Literal

from fastapi import FastAPI, HTTPException

from app_core.ingestion.models import AREAS, BASE_GROUPS
from backend.explore import router as explore_router
from backend.diagnostics import router as diagnostics_router
from backend.regional import router as regional_router
from backend.forecast import router as forecast_router
from backend.sensitivity import router as sensitivity_router
from backend.demand_anomalies import router as demand_anomalies_router


DEFAULT_DATABASE = Path(__file__).resolve().parents[1] / "data" / "energy.sqlite"
DATABASE_ENV = "ENERGY_DATABASE"

app = FastAPI(title="Norwegian Energy Dashboard API", version="0.1.0")
app.include_router(sensitivity_router)
app.include_router(demand_anomalies_router)


class DatabaseUnavailable(RuntimeError):
    pass


def _database_path() -> Path:
    configured = os.environ.get(DATABASE_ENV)
    return Path(configured).expanduser().resolve() if configured else DEFAULT_DATABASE


@contextmanager
def _snapshot() -> Iterator[tuple[sqlite3.Connection, dict]]:
    path = _database_path()
    connection = None
    try:
        for _ in range(2):
            before = path.stat()
            connection = sqlite3.connect(
                f"{path.as_uri()}?mode=ro", uri=True, check_same_thread=False
            )
            file_info = path.stat()
            if (before.st_ino, before.st_mtime_ns, before.st_size) == (
                file_info.st_ino,
                file_info.st_mtime_ns,
                file_info.st_size,
            ):
                break
            connection.close()
        else:
            raise OSError("snapshot changed while opening")
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        connection.execute("SELECT 1 FROM energy_observations LIMIT 1").fetchone()
    except (OSError, sqlite3.Error) as error:
        if connection is not None:
            connection.close()
        raise DatabaseUnavailable("The published energy snapshot is unavailable.") from error

    try:
        yield connection, {
            "version": (
                f"{file_info.st_ino:x}-{file_info.st_mtime_ns:x}-{file_info.st_size:x}"
            )
        }
    finally:
        connection.close()


def _unavailable(error: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=str(error))


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _ceil_day(value: datetime) -> datetime:
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight if value == midnight else midnight + timedelta(days=1)


def _snapshot_metadata(connection: sqlite3.Connection, version: dict) -> dict:
    rows = [
        connection.execute(
            """
            SELECT source, retrieved_at FROM energy_observations
            WHERE kind = ? AND area = ? AND energy_group = ?
            ORDER BY timestamp DESC LIMIT 1
            """,
            (kind, AREAS[0], groups[0]),
        ).fetchone()
        for kind, groups in BASE_GROUPS.items()
    ]
    rows = [row for row in rows if row]
    if not rows:
        raise DatabaseUnavailable("The published energy snapshot contains no base-series data.")
    sources = {row["source"] for row in rows}
    return {
        **version,
        "source": next(iter(sources)) if len(sources) == 1 else "Multiple public sources",
        "retrievedAt": max(row["retrieved_at"] for row in rows),
    }


@app.get("/api/coverage")
def coverage() -> dict:
    try:
        with _snapshot() as (connection, version):
            rows = []
            for area in AREAS:
                for kind, groups in BASE_GROUPS.items():
                    for group in groups:
                        first = connection.execute(
                            """
                            SELECT timestamp FROM energy_observations
                            WHERE kind = ? AND area = ? AND energy_group = ?
                              AND value IS NOT NULL AND quality = 'ok'
                            ORDER BY timestamp LIMIT 1
                            """,
                            (kind, area, group),
                        ).fetchone()
                        last = connection.execute(
                            """
                            SELECT timestamp FROM energy_observations
                            WHERE kind = ? AND area = ? AND energy_group = ?
                              AND value IS NOT NULL AND quality = 'ok'
                            ORDER BY timestamp DESC LIMIT 1
                            """,
                            (kind, area, group),
                        ).fetchone()
                        if not first or not last:
                            raise DatabaseUnavailable(
                                "The published energy snapshot is missing required base series."
                            )
                        rows.append(
                            {"start": first["timestamp"], "last_observation": last["timestamp"]}
                        )

            common_start = _ceil_day(max(_parse_utc(row["start"]) for row in rows))
            raw_end = min(
                _parse_utc(row["last_observation"]) + timedelta(hours=1) for row in rows
            )
            common_end = raw_end.replace(hour=0, minute=0, second=0, microsecond=0)
            if common_end <= common_start:
                raise DatabaseUnavailable(
                    "The published energy snapshot has no common complete UTC days."
                )
            suggested_start = max(common_start, common_end - timedelta(days=28))
            metadata = _snapshot_metadata(connection, version)
    except DatabaseUnavailable as error:
        raise _unavailable(error) from error
    except sqlite3.Error as error:
        raise _unavailable(DatabaseUnavailable("The published energy snapshot is unreadable.")) from error

    return {
        "areas": list(AREAS),
        "coverage": {"start": common_start.date().isoformat(), "end": common_end.date().isoformat()},
        "suggestedRange": {
            "start": suggested_start.date().isoformat(),
            "end": common_end.date().isoformat(),
        },
        "snapshot": metadata,
    }


def _metric(mwh: float | None, observed_hours: int, expected_hours: int) -> dict:
    return {
        "mwh": round(float(mwh), 3) if mwh is not None else None,
        "observedHours": observed_hours,
        "expectedHours": expected_hours,
        "partial": observed_hours < expected_hours,
    }


def _daily_rows(
    connection: sqlite3.Connection, area: str, start: str, end: str
) -> dict[tuple[str, str], dict]:
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='energy_daily_totals'").fetchone():
        rows = connection.execute(
            "SELECT day, kind, value / 1000.0 AS mwh, observed_hours FROM energy_daily_totals "
            "WHERE area = ? AND day >= ? AND day < ? ORDER BY day, kind",
            (area, start[:10], end[:10]),
        ).fetchall()
        return {(row["day"], row["kind"]): {"mwh": row["mwh"], "observedHours": int(row["observed_hours"])} for row in rows}
    # Older snapshots remain readable until the next scheduled publication.
    rows = connection.execute(
        """
        WITH hourly AS (
            SELECT SUBSTR(timestamp, 1, 10) AS day, timestamp, kind,
                   SUM(value) / 1000.0 AS mwh, COUNT(value) AS observed_groups
            FROM energy_observations
            WHERE area = ? AND timestamp >= ? AND timestamp < ?
              AND ((kind = 'production' AND energy_group IN ('hydro','other','solar','thermal','wind'))
                OR (kind = 'consumption' AND energy_group IN ('cabin','household','primary','secondary','tertiary')))
            GROUP BY day, timestamp, kind
        )
        SELECT day, kind, SUM(mwh) AS mwh,
               SUM(CASE WHEN observed_groups = 5 THEN 1 ELSE 0 END) AS observed_hours
        FROM hourly GROUP BY day, kind ORDER BY day, kind
        """,
        (area, start, end),
    ).fetchall()
    return {
        (row["day"], row["kind"]): {
            "mwh": row["mwh"],
            "observedHours": int(row["observed_hours"] or 0),
        }
        for row in rows
    }


def _production_mix(
    connection: sqlite3.Connection, area: str, start: str, end: str, expected_hours: int
) -> list[dict]:
    rows = {
        row["energy_group"]: row
        for row in connection.execute(
            """
            SELECT energy_group, SUM(value) / 1000.0 AS mwh,
                   COUNT(value) AS observed_hours
            FROM energy_observations
            WHERE area = ? AND kind = 'production' AND timestamp >= ? AND timestamp < ?
              AND energy_group IN ('hydro','other','solar','thermal','wind')
            GROUP BY energy_group
            """,
            (area, start, end),
        )
    }
    total = sum(float(row["mwh"]) for row in rows.values() if row["mwh"] is not None)
    result = []
    for group in BASE_GROUPS["production"]:
        row = rows.get(group)
        mwh = float(row["mwh"]) if row and row["mwh"] is not None else None
        item = {
            "group": group,
            **_metric(mwh, int(row["observed_hours"]) if row else 0, expected_hours),
            "share": round(mwh / total, 6) if mwh is not None and total else None,
        }
        result.append(item)
    return result


def _regional_ranking(
    connection: sqlite3.Connection, start: str, end: str, expected_hours: int
) -> list[dict]:
    rows = {}
    for area in AREAS:
        total = 0.0
        has_value = False
        hourly_counts: dict[str, int] = {}
        for group in BASE_GROUPS["consumption"]:
            observations = connection.execute(
                """
                SELECT timestamp, value FROM energy_observations
                WHERE kind = 'consumption' AND area = ? AND energy_group = ?
                  AND timestamp >= ? AND timestamp < ?
                """,
                (area, group, start, end),
            )
            for observation in observations:
                if observation["value"] is not None:
                    total += float(observation["value"]) / 1000.0
                    has_value = True
                    timestamp = observation["timestamp"]
                    hourly_counts[timestamp] = hourly_counts.get(timestamp, 0) + 1
        rows[area] = {
            "mwh": total if has_value else None,
            "observed_hours": sum(
                count == len(BASE_GROUPS["consumption"])
                for count in hourly_counts.values()
            ),
        }
    ordered = sorted(
        AREAS,
        key=lambda area: (
            rows[area]["mwh"] is None,
            -(float(rows[area]["mwh"]) if rows[area]["mwh"] is not None else 0),
            area,
        ),
    )
    return [
        {
            "rank": rank,
            "area": area,
            **_metric(
                float(rows[area]["mwh"])
                if rows[area]["mwh"] is not None
                else None,
                int(rows[area]["observed_hours"]),
                expected_hours,
            ),
        }
        for rank, area in enumerate(ordered, start=1)
    ]


@app.get("/api/overview")
def overview(
    area: Literal["NO1", "NO2", "NO3", "NO4", "NO5"],
    start: date,
    end: date,
) -> dict:
    days = (end - start).days
    if days <= 0:
        raise HTTPException(status_code=422, detail="end must be after start")
    if days > 366:
        raise HTTPException(status_code=422, detail="date range must be 366 days or fewer")

    start_iso = f"{start.isoformat()}T00:00:00Z"
    end_iso = f"{end.isoformat()}T00:00:00Z"
    expected_hours = days * 24
    try:
        with _snapshot() as (connection, version):
            daily_lookup = _daily_rows(connection, area, start_iso, end_iso)
            production_mix = _production_mix(
                connection, area, start_iso, end_iso, expected_hours
            )
            ranking = _regional_ranking(connection, start_iso, end_iso, expected_hours)
            metadata = _snapshot_metadata(connection, version)
    except DatabaseUnavailable as error:
        raise _unavailable(error) from error
    except sqlite3.Error as error:
        raise _unavailable(DatabaseUnavailable("The published energy snapshot is unreadable.")) from error

    daily = []
    cursor = start
    while cursor < end:
        day = cursor.isoformat()
        item = {"date": day}
        for kind in ("consumption", "production"):
            found = daily_lookup.get((day, kind))
            item[kind] = _metric(
                found["mwh"] if found else None,
                found["observedHours"] if found else 0,
                24,
            )
        daily.append(item)
        cursor += timedelta(days=1)

    headline = {}
    for kind in ("consumption", "production"):
        # Round the final period total, not each daily subtotal before summing.
        values = [
            row["mwh"] for (_, row_kind), row in daily_lookup.items()
            if row_kind == kind and row["mwh"] is not None
        ]
        headline[kind] = _metric(
            sum(values) if values else None,
            sum(row[kind]["observedHours"] for row in daily),
            expected_hours,
        )

    return {
        "query": {"area": area, "start": start.isoformat(), "end": end.isoformat()},
        "unit": "MWh",
        "snapshot": metadata,
        "headline": headline,
        "daily": daily,
        "productionMix": production_mix,
        "regionalRanking": ranking,
        "expectedGroups": {kind: list(groups) for kind, groups in BASE_GROUPS.items()},
    }

# Keep the analytical workspaces independent while sharing the published sources.
app.include_router(explore_router)
app.include_router(diagnostics_router)
app.include_router(regional_router)
app.include_router(forecast_router)


@app.get("/api/health")
def health() -> dict:
    """Process liveness; readiness separately checks the published data."""
    return {"status": "ok", "dataMode": os.environ.get("ENERGY_DATA_MODE", "published")}


@app.get("/api/ready")
def ready() -> dict:
    state = coverage()
    return {"status": "ready", "coverage": state["coverage"], "snapshot": state["snapshot"]}
