from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests

from app_core.ingestion import ElhubClient, ElhubError, EnergyStore, RefreshService
from app_core.ingestion.models import AREAS, BASE_GROUPS


OSLO = ZoneInfo("Europe/Oslo")


class FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def payload_for(kind: str, start: date, end: date):
    attribute = f"{kind}PerGroupMbaHour"
    group_field = f"{kind}Group"
    start_utc = datetime.combine(start, datetime.min.time(), OSLO).astimezone(timezone.utc)
    end_utc = datetime.combine(end, datetime.min.time(), OSLO).astimezone(timezone.utc)
    records = []
    cursor = start_utc
    while cursor < end_utc:
        for area in AREAS:
            for group in BASE_GROUPS[kind]:
                records.append(
                    {
                        "startTime": cursor.isoformat().replace("+00:00", "Z"),
                        "endTime": (cursor + timedelta(hours=1))
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "priceArea": area,
                        group_field: group,
                        "quantityKwh": 1.0,
                        "lastUpdatedTime": "2026-09-14T08:00:00Z",
                    }
                )
        cursor += timedelta(hours=1)
    return {"data": [{"attributes": {attribute: records}}]}


def row(
    timestamp="2026-09-13T00:00:00Z",
    area="NO1",
    kind="production",
    group="solar",
    value=1.0,
    revision="2026-09-14T08:00:00Z",
):
    return {
        "timestamp": timestamp,
        "area": area,
        "kind": kind,
        "group": group,
        "value": value,
        "unit": "kWh",
        "source": "Elhub Energy Data API",
        "retrieved_at": "2026-09-14T09:00:00Z",
        "revision": revision,
        "quality": "ok" if value is not None else "missing",
    }


@pytest.mark.parametrize(
    ("start", "end", "hours"),
    [
        (date(2026, 3, 29), date(2026, 3, 30), 23),
        (date(2025, 10, 26), date(2025, 10, 27), 25),
    ],
)
def test_elhub_fetch_is_dst_safe_and_uses_supported_parameters(start, end, hours):
    session = FakeSession([FakeResponse(payload_for("production", start, end))])
    client = ElhubClient(
        session=session, now=lambda: datetime(2026, 9, 14, tzinfo=timezone.utc)
    )

    rows = client.fetch("production", start, end)

    assert len(rows) == hours * len(AREAS) * len(BASE_GROUPS["production"])
    _, params, _ = session.calls[0]
    assert params == {
        "dataset": "PRODUCTION_PER_GROUP_MBA_HOUR",
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
    }
    assert {record["unit"] for record in rows} == {"kWh"}
    assert all(record["timestamp"].endswith("Z") for record in rows)


def test_elhub_retries_are_bounded():
    waits = []
    session = FakeSession(
        [
            requests.ConnectionError("offline"),
            FakeResponse(status_code=503, headers={"Retry-After": "2"}),
            FakeResponse(payload_for("consumption", date(2026, 1, 1), date(2026, 1, 2))),
        ]
    )
    client = ElhubClient(
        session=session,
        max_attempts=3,
        backoff_seconds=0.25,
        sleep=waits.append,
        now=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    client.fetch("consumption", date(2026, 1, 1), date(2026, 1, 2))

    assert len(session.calls) == 3
    assert waits == [0.25, 2.0]


def test_partial_response_is_rejected_and_missing_is_not_zero():
    payload = payload_for("production", date(2026, 1, 1), date(2026, 1, 2))
    records = payload["data"][0]["attributes"]["productionPerGroupMbaHour"]
    records[0]["quantityKwh"] = None
    client = ElhubClient(session=FakeSession([FakeResponse(payload)]))

    with pytest.raises(ElhubError, match="missing required quantity"):
        client.fetch("production", date(2026, 1, 1), date(2026, 1, 2))


def test_structurally_absent_historical_group_remains_unavailable():
    payload = payload_for("production", date(2021, 1, 1), date(2021, 1, 2))
    records = payload["data"][0]["attributes"]["productionPerGroupMbaHour"]
    records[:] = [
        item
        for item in records
        if not (item["priceArea"] == "NO5" and item["productionGroup"] == "wind")
    ]
    client = ElhubClient(session=FakeSession([FakeResponse(payload)]))

    rows = client.fetch("production", date(2021, 1, 1), date(2021, 1, 2))

    assert not any(
        item["area"] == "NO5" and item["group"] == "wind" for item in rows
    )


def test_gap_within_an_observed_series_is_rejected():
    payload = payload_for("production", date(2026, 1, 1), date(2026, 1, 2))
    records = payload["data"][0]["attributes"]["productionPerGroupMbaHour"]
    del records[2 * len(AREAS) * len(BASE_GROUPS["production"])]
    client = ElhubClient(session=FakeSession([FakeResponse(payload)]))

    with pytest.raises(ElhubError, match="gap in"):
        client.fetch("production", date(2026, 1, 1), date(2026, 1, 2))


@pytest.mark.parametrize("bad_value", [-1, float("nan"), float("inf")])
def test_invalid_quantities_are_rejected(bad_value):
    payload = payload_for("production", date(2026, 1, 1), date(2026, 1, 2))
    records = payload["data"][0]["attributes"]["productionPerGroupMbaHour"]
    records[0]["quantityKwh"] = bad_value
    client = ElhubClient(session=FakeSession([FakeResponse(payload)]))

    with pytest.raises(ElhubError, match="invalid quantity"):
        client.fetch("production", date(2026, 1, 1), date(2026, 1, 2))


def test_non_hourly_source_interval_is_rejected():
    payload = payload_for("production", date(2026, 1, 1), date(2026, 1, 2))
    records = payload["data"][0]["attributes"]["productionPerGroupMbaHour"]
    records[0]["endTime"] = records[0]["startTime"]
    client = ElhubClient(session=FakeSession([FakeResponse(payload)]))

    with pytest.raises(ElhubError, match="interval is not one hour"):
        client.fetch("production", date(2026, 1, 1), date(2026, 1, 2))


def test_store_upsert_is_idempotent_and_keeps_newest_revision(tmp_path):
    store = EnergyStore(tmp_path / "energy.sqlite")
    original = row(value=2.0, revision="2026-09-14T08:00:00Z")
    older = row(value=99.0, revision="2026-09-14T07:00:00Z")
    newer = row(value=3.0, revision="2026-09-14T10:00:00Z")

    store.upsert([original])
    store.upsert([original])
    store.upsert([older])
    store.upsert([newer])

    rows = store.query(
        start="2026-09-13T00:00:00Z", end="2026-09-13T01:00:00Z"
    )
    assert len(rows) == 1
    assert rows[0]["value"] == 3.0
    assert rows[0]["revision"] == "2026-09-14T10:00:00Z"


def test_store_reports_group_coverage_and_common_complete_window(tmp_path):
    store = EnergyStore(tmp_path / "energy.sqlite")
    rows = []
    for hour in range(2):
        timestamp = f"2026-01-01T0{hour}:00:00Z"
        for area in AREAS:
            for kind, groups in BASE_GROUPS.items():
                for group in groups:
                    rows.append(row(timestamp, area, kind, group))
    store.upsert(rows)

    coverage = store.coverage()
    common = store.common_complete_window()

    assert len(coverage) == 50
    assert all(item["is_complete"] for item in coverage)
    assert common == {
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-01T02:00:00Z",
        "last_observation": "2026-01-01T01:00:00Z",
        "series_count": 50,
    }
    assert store.common_complete_window(areas=["NO5"], groups=["wind"]) == {
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-01T02:00:00Z",
        "last_observation": "2026-01-01T01:00:00Z",
        "series_count": 1,
    }


class PartialClient:
    def __init__(self, good_rows):
        self.good_rows = good_rows
        self.calls = 0

    def fetch(self, kind, start, end):
        self.calls += 1
        if self.calls == 1:
            return self.good_rows
        raise ElhubError("partial upstream response")


class CompleteClient:
    def fetch(self, kind, start, end):
        group = "solar" if kind == "production" else "household"
        return [row(kind=kind, group=group)]


class DroppedSeriesClient:
    def fetch(self, kind, start, end):
        group = "solar" if kind == "production" else "household"
        return [row(kind=kind, group=group, revision="2026-09-15T08:00:00Z")]


def test_repeated_refresh_does_not_create_duplicates(tmp_path):
    store = EnergyStore(tmp_path / "energy.sqlite")
    service = RefreshService(
        store,
        client=CompleteClient(),
        now=lambda: datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
    )

    service.refresh(days=1, end=date(2026, 9, 14))
    service.refresh(days=1, end=date(2026, 9, 14))

    records = store.query()
    assert len(records) == 2
    assert {(item["kind"], item["group"]) for item in records} == {
        ("production", "solar"),
        ("consumption", "household"),
    }


def test_failed_refresh_preserves_last_known_good_observations(tmp_path):
    database = tmp_path / "energy.sqlite"
    store = EnergyStore(database)
    existing = row(value=7.0)
    store.upsert([existing])
    replacement = row(value=9.0, revision="2026-09-15T08:00:00Z")
    service = RefreshService(
        store,
        client=PartialClient([replacement]),
        now=lambda: datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
    )

    with pytest.raises(ElhubError, match="partial upstream"):
        service.refresh(days=1, end=date(2026, 9, 14))

    assert store.query()[0]["value"] == 7.0
    assert not list(Path(tmp_path).glob(".energy.sqlite.*.tmp"))


def test_refresh_that_drops_existing_series_preserves_snapshot(tmp_path):
    store = EnergyStore(tmp_path / "energy.sqlite")
    store.upsert([row(group="solar", value=7.0), row(group="wind", value=8.0)])
    service = RefreshService(
        store,
        client=DroppedSeriesClient(),
        now=lambda: datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
    )

    with pytest.raises(ElhubError, match="refresh dropped existing observation"):
        service.refresh(days=1, end=date(2026, 9, 14))

    assert {(item["group"], item["value"]) for item in store.query()} == {
        ("solar", 7.0),
        ("wind", 8.0),
    }


def test_absent_store_is_a_safe_empty_source(tmp_path):
    store = EnergyStore(tmp_path / "missing.sqlite")
    assert store.query() == []
    assert store.coverage() == []
    assert store.common_complete_window() is None
