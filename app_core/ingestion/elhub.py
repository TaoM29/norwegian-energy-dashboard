from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

import requests

from .models import (
    AREAS,
    BASE_GROUPS,
    DATASETS,
    EnergyObservation,
    observation_from_record,
    parse_timestamp,
    validate_local_dates,
)


OSLO = ZoneInfo("Europe/Oslo")
API_URL = "https://api.elhub.no/energy-data/v0/price-areas"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ElhubError(RuntimeError):
    """The public Elhub response could not safely be ingested."""


class ElhubClient:
    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        max_attempts: int = 3,
        timeout: float = 30.0,
        backoff_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        logger: Optional[logging.Logger] = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self.session = session or requests.Session()
        self.max_attempts = max_attempts
        self.timeout = timeout
        self.backoff_seconds = backoff_seconds
        self.sleep = sleep
        self.now = now
        self.logger = logger or logging.getLogger(__name__)

    def fetch(self, kind: str, start: date, end: date) -> list[dict]:
        """Fetch and validate one Oslo-local, end-exclusive period of at most 28 days."""
        validate_local_dates(start, end)
        if end - start > timedelta(days=28):
            raise ValueError("Elhub requests are limited to 28 days")
        if kind not in DATASETS:
            raise ValueError(f"unsupported energy kind: {kind}")

        dataset, attribute = DATASETS[kind]
        params = {
            "dataset": dataset,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
        }
        response = self._get(params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ElhubError("Elhub returned invalid JSON") from exc

        retrieved_at = self.now().astimezone(timezone.utc)
        records = list(_records(payload, attribute))
        try:
            observations = [
                observation_from_record(record, kind, retrieved_at) for record in records
            ]
            self._validate_complete(observations, kind, start, end)
        except (TypeError, ValueError) as exc:
            raise ElhubError(str(exc)) from exc
        return [row.as_dict() for row in observations]

    def _get(self, params: Mapping[str, str]):
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(API_URL, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                if attempt == self.max_attempts:
                    raise ElhubError(
                        f"Elhub request failed after {self.max_attempts} attempts"
                    ) from exc
                self._wait(attempt, None)
                continue

            if response.status_code < 400:
                return response
            if response.status_code not in RETRYABLE_STATUS or attempt == self.max_attempts:
                raise ElhubError(
                    f"Elhub returned HTTP {response.status_code} on attempt {attempt}"
                )
            self._wait(attempt, response.headers.get("Retry-After"))
        raise AssertionError("retry loop did not return or raise")

    def _wait(self, attempt: int, retry_after: Optional[str]) -> None:
        delay = _retry_after_seconds(retry_after, self.now())
        if delay is None:
            delay = self.backoff_seconds * (2 ** (attempt - 1))
        delay = min(max(delay, 0.0), 60.0)
        self.logger.warning("Elhub request failed; retrying in %.1f seconds", delay)
        self.sleep(delay)

    @staticmethod
    def _validate_complete(
        rows: list[EnergyObservation], kind: str, start: date, end: date
    ) -> None:
        if not rows:
            raise ElhubError("Elhub returned no observations")

        expected_start = datetime.combine(start, datetime.min.time(), OSLO).astimezone(
            timezone.utc
        )
        expected_end = datetime.combine(end, datetime.min.time(), OSLO).astimezone(
            timezone.utc
        )
        expected_hours = set()
        cursor = expected_start
        while cursor < expected_end:
            expected_hours.add(cursor)
            cursor += timedelta(hours=1)

        seen: set[tuple[str, str, str, str]] = set()
        series_hours: dict[tuple[str, str], set[datetime]] = {}
        null_required: list[str] = []
        for row in rows:
            key = (row.timestamp, row.area, row.kind, row.group)
            if key in seen:
                raise ElhubError(f"duplicate observation: {'/'.join(key)}")
            seen.add(key)
            timestamp = parse_timestamp(row.timestamp, "timestamp")
            if not expected_start <= timestamp < expected_end:
                raise ElhubError(f"observation outside requested interval: {row.timestamp}")
            if row.group in BASE_GROUPS[kind]:
                series_hours.setdefault((row.area, row.group), set()).add(timestamp)
                if row.value is None:
                    null_required.append(f"{row.area}/{row.group}/{row.timestamp}")

        if null_required:
            raise ElhubError(f"missing required quantity: {null_required[0]}")
        area_hours: dict[str, set[datetime]] = {}
        for (area, group), actual in series_hours.items():
            area_hours.setdefault(area, set()).update(actual)
            first = min(actual)
            last = max(actual)
            expected_series = set()
            cursor = first
            while cursor <= last:
                expected_series.add(cursor)
                cursor += timedelta(hours=1)
            missing = expected_series - actual
            if missing:
                raise ElhubError(
                    f"gap in {area}/{kind}/{group}: {len(missing)} missing hours"
                )
        for area, covered_hours in area_hours.items():
            if covered_hours != expected_hours:
                raise ElhubError(
                    f"Elhub response does not cover the complete requested interval for {area}"
                )
        missing_areas = set(AREAS) - set(area_hours)
        if missing_areas:
            raise ElhubError(
                f"Elhub response has no base observations for {sorted(missing_areas)[0]}"
            )


def validate_preserves_existing(
    existing: Iterable[Mapping[str, object]], incoming: Iterable[Mapping[str, object]]
) -> None:
    """Reject a refresh that omits base-series observations already published."""
    existing_keys = {
        (row["timestamp"], row["area"], row["kind"], row["group"])
        for row in existing
        if row.get("group") in BASE_GROUPS.get(str(row.get("kind")), ())
    }
    incoming_keys = {
        (row["timestamp"], row["area"], row["kind"], row["group"])
        for row in incoming
        if row.get("group") in BASE_GROUPS.get(str(row.get("kind")), ())
    }
    dropped = existing_keys - incoming_keys
    if dropped:
        timestamp, area, kind, group = sorted(dropped)[0]
        raise ElhubError(
            f"refresh dropped existing observation: {area}/{kind}/{group}/{timestamp}"
        )


def _records(payload: object, attribute: str) -> Iterable[Mapping[str, object]]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("data"), list):
        raise ElhubError("Elhub response has no data list")
    for item in payload["data"]:
        if not isinstance(item, Mapping):
            raise ElhubError("Elhub data item is not an object")
        attributes = item.get("attributes")
        if not isinstance(attributes, Mapping):
            raise ElhubError("Elhub data item has no attributes object")
        values = attributes.get(attribute)
        if values is None:
            continue
        if not isinstance(values, list):
            raise ElhubError(f"Elhub attribute {attribute} is not a list")
        for record in values:
            if not isinstance(record, Mapping):
                raise ElhubError("Elhub observation is not an object")
            yield record


def _retry_after_seconds(value: Optional[str], now: datetime) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return (retry_at - now).total_seconds()
