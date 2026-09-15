from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterator, Optional
from zoneinfo import ZoneInfo

from .elhub import ElhubClient, validate_preserves_existing
from .store import EnergyStore


OSLO = ZoneInfo("Europe/Oslo")
BACKFILL_START_LOCAL = date(2021, 1, 1)


class RefreshService:
    def __init__(
        self,
        store: EnergyStore,
        *,
        client: Optional[ElhubClient] = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.store = store
        self.client = client or ElhubClient()
        self.now = now
        self.logger = logger or logging.getLogger(__name__)

    def backfill(self, *, end: Optional[date] = None) -> int:
        return self._run(
            "backfill",
            BACKFILL_START_LOCAL,
            end or self._published_end(),
        )

    def refresh(self, *, days: int = 7, end: Optional[date] = None) -> int:
        if days < 1:
            raise ValueError("days must be at least one")
        published_end = end or self._published_end()
        recent_start = published_end - timedelta(days=days)
        latest = self.store.latest_observation()
        if latest is not None:
            # Re-request the latest source day as well as all later missing days.
            missing_start = latest.astimezone(OSLO).date()
            start = min(recent_start, missing_start)
        else:
            start = recent_start
        return self._run("refresh", start, published_end)

    def _published_end(self) -> date:
        # Elhub publishes after measurement. Exclude yesterday as well as today,
        # including when a delayed scheduled run crosses Oslo midnight.
        return self.now().astimezone(OSLO).date() - timedelta(days=1)

    def _run(
        self,
        mode: str,
        start: date,
        end: date,
    ) -> int:
        started = self.now().astimezone(timezone.utc)
        staging = self.store.prepare_staging()
        fetched = 0
        try:
            for chunk_start, chunk_end in date_chunks(start, end):
                for kind in ("production", "consumption"):
                    self.logger.info(
                        "Fetching %s %s to %s", kind, chunk_start, chunk_end
                    )
                    rows = self.client.fetch(kind, chunk_start, chunk_end)
                    interval_start = datetime.combine(
                        chunk_start, datetime.min.time(), OSLO
                    ).astimezone(timezone.utc)
                    interval_end = datetime.combine(
                        chunk_end, datetime.min.time(), OSLO
                    ).astimezone(timezone.utc)
                    existing = staging.query(
                        start=interval_start,
                        end=interval_end,
                        kinds=[kind],
                    )
                    validate_preserves_existing(existing, rows)
                    fetched += staging.upsert(rows)
            finished = self.now().astimezone(timezone.utc)
            staging.record_run(
                started_at=started,
                finished_at=finished,
                mode=mode,
                status="success",
                fetched_rows=fetched,
            )
            self.store.publish(staging)
            self.logger.info("Published %s snapshot with %d fetched rows", mode, fetched)
            return fetched
        except Exception as exc:
            try:
                staging.path.unlink(missing_ok=True)
            finally:
                finished = self.now().astimezone(timezone.utc)
                self.store.record_run(
                    started_at=started,
                    finished_at=finished,
                    mode=mode,
                    status="failed",
                    fetched_rows=fetched,
                    message=str(exc)[:1000],
                )
            raise


def date_chunks(start: date, end: date, days: int = 28) -> Iterator[tuple[date, date]]:
    if end <= start:
        raise ValueError("end date must be after start date")
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=days), end)
        yield cursor, chunk_end
        cursor = chunk_end
