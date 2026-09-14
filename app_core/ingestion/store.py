from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from .models import BASE_GROUPS, parse_timestamp, utc_iso


DEFAULT_DATABASE = Path("data/energy.sqlite")


SCHEMA = """
CREATE TABLE IF NOT EXISTS energy_observations (
    timestamp TEXT NOT NULL,
    area TEXT NOT NULL,
    kind TEXT NOT NULL,
    energy_group TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    revision TEXT,
    quality TEXT NOT NULL,
    PRIMARY KEY (timestamp, area, kind, energy_group)
);
CREATE INDEX IF NOT EXISTS energy_filter_idx
    ON energy_observations(kind, area, energy_group, timestamp);
CREATE TABLE IF NOT EXISTS refresh_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    fetched_rows INTEGER NOT NULL,
    message TEXT
);
"""


class EnergyStore:
    def __init__(self, path: str | Path = DEFAULT_DATABASE) -> None:
        self.path = Path(path)

    def query(
        self,
        *,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
        areas: Optional[Sequence[str]] = None,
        kinds: Optional[Sequence[str]] = None,
        groups: Optional[Sequence[str]] = None,
    ) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if start is not None:
            clauses.append("timestamp >= ?")
            params.append(_query_timestamp(start))
        if end is not None:
            clauses.append("timestamp < ?")
            params.append(_query_timestamp(end))
        _add_in_filter(clauses, params, "area", areas)
        _add_in_filter(clauses, params, "kind", kinds)
        _add_in_filter(clauses, params, "energy_group", groups)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT timestamp, area, kind, energy_group AS 'group', value, unit, "
            "source, retrieved_at, revision, quality FROM energy_observations"
            f"{where} ORDER BY timestamp, area, kind, energy_group"
        )
        try:
            with self._connect(read_only=True) as connection:
                return [dict(row) for row in connection.execute(sql, params)]
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return []
            raise

    def coverage(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        sql = """
            SELECT area, kind, energy_group AS 'group', MIN(timestamp) AS start,
                   MAX(timestamp) AS last_observation, COUNT(*) AS count,
                   SUM(CASE WHEN value IS NOT NULL THEN 1 ELSE 0 END) AS nonnull_count
            FROM energy_observations
            GROUP BY area, kind, energy_group
            ORDER BY area, kind, energy_group
        """
        try:
            with self._connect(read_only=True) as connection:
                rows = connection.execute(sql).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return []
            raise

        result = []
        for row in rows:
            start = parse_timestamp(row["start"], "start")
            last = parse_timestamp(row["last_observation"], "last_observation")
            end = last + timedelta(hours=1)
            expected = int((end - start).total_seconds() // 3600)
            missing = max(expected - int(row["nonnull_count"]), 0)
            result.append(
                {
                    "area": row["area"],
                    "kind": row["kind"],
                    "group": row["group"],
                    "start": utc_iso(start),
                    "end": utc_iso(end),
                    "last_observation": utc_iso(last),
                    "count": int(row["count"]),
                    "expected_count": expected,
                    "missing_count": missing,
                    "is_complete": int(row["count"]) == expected and missing == 0,
                }
            )
        return result

    def common_complete_window(
        self,
        *,
        areas: Optional[Sequence[str]] = None,
        kinds: Optional[Sequence[str]] = None,
        groups: Optional[Sequence[str]] = None,
    ) -> Optional[dict[str, Any]]:
        if not self.path.exists():
            return None
        production_marks = ",".join("?" for _ in BASE_GROUPS["production"])
        consumption_marks = ",".join("?" for _ in BASE_GROUPS["consumption"])
        clauses = [
            "value IS NOT NULL",
            "quality = 'ok'",
            f"((kind = 'production' AND energy_group IN ({production_marks})) "
            f"OR (kind = 'consumption' AND energy_group IN ({consumption_marks})))",
        ]
        params: list[Any] = [
            *BASE_GROUPS["production"],
            *BASE_GROUPS["consumption"],
        ]
        _add_in_filter(clauses, params, "area", areas)
        _add_in_filter(clauses, params, "kind", kinds)
        _add_in_filter(clauses, params, "energy_group", groups)
        where = " AND ".join(clauses)
        series_sql = (
            "SELECT COUNT(*) FROM (SELECT DISTINCT area, kind, energy_group "
            f"FROM energy_observations WHERE {where})"
        )
        timestamps_sql = f"""
            SELECT timestamp, COUNT(*) AS available
            FROM energy_observations
            WHERE {where}
            GROUP BY timestamp
            HAVING available = ?
            ORDER BY timestamp
        """
        try:
            with self._connect(read_only=True) as connection:
                series_count = int(connection.execute(series_sql, params).fetchone()[0])
                if series_count == 0:
                    return None
                timestamps = [
                    parse_timestamp(row["timestamp"], "timestamp")
                    for row in connection.execute(
                        timestamps_sql, [*params, series_count]
                    )
                ]
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return None
            raise
        if not timestamps:
            return None
        start = timestamps[-1]
        for candidate in reversed(timestamps[:-1]):
            if candidate != start - timedelta(hours=1):
                break
            start = candidate
        last = timestamps[-1]
        return {
            "start": utc_iso(start),
            "end": utc_iso(last + timedelta(hours=1)),
            "last_observation": utc_iso(last),
            "series_count": series_count,
        }

    def latest_observation(self) -> Optional[datetime]:
        if not self.path.exists():
            return None
        try:
            with self._connect(read_only=True) as connection:
                value = connection.execute(
                    "SELECT MAX(timestamp) FROM energy_observations"
                ).fetchone()[0]
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return None
            raise
        return parse_timestamp(value, "timestamp") if value else None

    def prepare_staging(self) -> "EnergyStore":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staging_path = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        if self.path.exists():
            shutil.copy2(self.path, staging_path)
        staging = EnergyStore(staging_path)
        staging.initialize()
        return staging

    def publish(self, staging: "EnergyStore") -> None:
        if staging.path.parent != self.path.parent:
            raise ValueError("staging database must be in the destination directory")
        os.replace(staging.path, self.path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def upsert(self, rows: Iterable[dict[str, Any]]) -> int:
        values = [
            (
                row["timestamp"],
                row["area"],
                row["kind"],
                row["group"],
                row["value"],
                row["unit"],
                row["source"],
                row["retrieved_at"],
                row["revision"],
                row["quality"],
            )
            for row in rows
        ]
        if not values:
            return 0
        self.initialize()
        sql = """
            INSERT INTO energy_observations (
                timestamp, area, kind, energy_group, value, unit, source,
                retrieved_at, revision, quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(timestamp, area, kind, energy_group) DO UPDATE SET
                value = excluded.value,
                unit = excluded.unit,
                source = excluded.source,
                retrieved_at = excluded.retrieved_at,
                revision = excluded.revision,
                quality = excluded.quality
            WHERE (excluded.revision IS NOT NULL AND
                   (energy_observations.revision IS NULL OR
                    excluded.revision >= energy_observations.revision))
               OR (excluded.revision IS NULL AND energy_observations.revision IS NULL)
        """
        with self._connect() as connection:
            connection.executemany(sql, values)
        return len(values)

    def record_run(
        self,
        *,
        started_at: datetime,
        finished_at: datetime,
        mode: str,
        status: str,
        fetched_rows: int,
        message: Optional[str] = None,
    ) -> None:
        self.initialize()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO refresh_runs "
                "(started_at, finished_at, mode, status, fetched_rows, message) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    utc_iso(started_at),
                    utc_iso(finished_at),
                    mode,
                    status,
                    fetched_rows,
                    message,
                ),
            )

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            uri = f"file:{self.path.resolve()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
        else:
            connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection


def _query_timestamp(value: datetime | str) -> str:
    if isinstance(value, str):
        value = parse_timestamp(value, "query timestamp")
    return utc_iso(value)


def _add_in_filter(
    clauses: list[str], params: list[Any], column: str, values: Optional[Sequence[str]]
) -> None:
    if values is None:
        return
    if not values:
        clauses.append("0")
        return
    clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
    params.extend(values)
