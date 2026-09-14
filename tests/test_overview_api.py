from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app_core.ingestion.models import AREAS, BASE_GROUPS
from backend.main import app


SCHEMA = """
CREATE TABLE energy_observations (
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
CREATE INDEX energy_filter_idx
    ON energy_observations(kind, area, energy_group, timestamp);
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    database = tmp_path / "energy.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(SCHEMA)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for hour in range(72):
        timestamp = (start + timedelta(hours=hour)).isoformat().replace("+00:00", "Z")
        for area_index, area in enumerate(AREAS, start=1):
            for kind, groups in BASE_GROUPS.items():
                for group_index, group in enumerate(groups, start=1):
                    value = float(
                        1000 * (area_index if kind == "consumption" else group_index)
                    )
                    if (
                        timestamp == "2026-01-01T05:00:00Z"
                        and area == "NO1"
                        and kind == "consumption"
                        and group == "household"
                    ):
                        value = None
                    rows.append(
                        (
                            timestamp,
                            area,
                            kind,
                            group,
                            value,
                            "kWh",
                            "Elhub Energy Data API",
                            "2026-01-04T12:00:00Z",
                            None,
                            "missing" if value is None else "ok",
                        )
                    )
    connection.executemany(
        "INSERT INTO energy_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    connection.commit()
    connection.close()
    monkeypatch.setenv("ENERGY_DATABASE", str(database))
    yield TestClient(app), database


def test_coverage_uses_common_complete_utc_days(client):
    api, _ = client
    response = api.get("/api/coverage")

    assert response.status_code == 200
    body = response.json()
    assert body["areas"] == list(AREAS)
    assert body["coverage"] == {"start": "2026-01-01", "end": "2026-01-04"}
    assert body["suggestedRange"] == {
        "start": "2026-01-01",
        "end": "2026-01-04",
    }
    assert body["snapshot"]["source"] == "Elhub Energy Data API"
    assert body["snapshot"]["retrievedAt"] == "2026-01-04T12:00:00Z"
    assert body["snapshot"]["version"]


def test_overview_aggregates_half_open_window_and_reports_partial_data(client):
    api, _ = client
    response = api.get(
        "/api/overview",
        params={"area": "NO1", "start": "2026-01-01", "end": "2026-01-03"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == {
        "area": "NO1",
        "start": "2026-01-01",
        "end": "2026-01-03",
    }
    assert body["unit"] == "MWh"
    assert body["headline"]["consumption"] == {
        "mwh": 239.0,
        "observedHours": 47,
        "expectedHours": 48,
        "partial": True,
    }
    assert body["headline"]["production"] == {
        "mwh": 720.0,
        "observedHours": 48,
        "expectedHours": 48,
        "partial": False,
    }
    assert body["daily"][0]["consumption"]["mwh"] == 119.0
    assert body["daily"][0]["consumption"]["partial"] is True
    assert body["daily"][1]["consumption"]["mwh"] == 120.0
    assert body["daily"][1]["consumption"]["partial"] is False
    assert [item["mwh"] for item in body["productionMix"]] == [48, 96, 144, 192, 240]
    assert sum(item["share"] for item in body["productionMix"]) == pytest.approx(1)
    assert [item["area"] for item in body["regionalRanking"]] == [
        "NO5",
        "NO4",
        "NO3",
        "NO2",
        "NO1",
    ]
    assert body["regionalRanking"][-1]["partial"] is True
    assert body["expectedGroups"] == {
        kind: list(groups) for kind, groups in BASE_GROUPS.items()
    }


@pytest.mark.parametrize(
    "params",
    [
        {"area": "SE1", "start": "2026-01-01", "end": "2026-01-02"},
        {"area": "NO1", "start": "bad", "end": "2026-01-02"},
        {"area": "NO1", "start": "2026-01-02", "end": "2026-01-02"},
        {"area": "NO1", "start": "2025-01-01", "end": "2026-01-03"},
    ],
)
def test_overview_rejects_invalid_bounds(client, params):
    api, _ = client
    assert api.get("/api/overview", params=params).status_code == 422


def test_coverage_rejects_snapshot_missing_a_required_series(client):
    api, database = client
    connection = sqlite3.connect(database)
    connection.execute(
        "DELETE FROM energy_observations WHERE area = 'NO5' AND kind = 'production' "
        "AND energy_group = 'wind'"
    )
    connection.commit()
    connection.close()

    response = api.get("/api/coverage")
    assert response.status_code == 503
    assert "missing required base series" in response.json()["detail"]


def test_overview_keeps_partial_sum_when_an_expected_group_is_absent(client):
    api, database = client
    connection = sqlite3.connect(database)
    connection.execute(
        "DELETE FROM energy_observations WHERE area = 'NO1' AND kind = 'production' "
        "AND energy_group = 'wind'"
    )
    connection.commit()
    connection.close()

    response = api.get(
        "/api/overview",
        params={"area": "NO1", "start": "2026-01-02", "end": "2026-01-03"},
    )
    assert response.status_code == 200
    production = response.json()["headline"]["production"]
    assert production == {
        "mwh": 240.0,
        "observedHours": 0,
        "expectedHours": 24,
        "partial": True,
    }
    wind = next(
        item for item in response.json()["productionMix"] if item["group"] == "wind"
    )
    assert wind["mwh"] is None
    assert wind["partial"] is True


def test_missing_database_returns_503(tmp_path, monkeypatch):
    monkeypatch.setenv("ENERGY_DATABASE", str(tmp_path / "missing.sqlite"))
    api = TestClient(app)

    assert api.get("/api/coverage").status_code == 503
    assert api.get(
        "/api/overview",
        params={"area": "NO1", "start": "2026-01-01", "end": "2026-01-02"},
    ).status_code == 503


def test_headline_rounds_only_after_summing_daily_observations(client):
    api, database = client
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE energy_observations SET value = 0.004 "
            "WHERE area = 'NO1' AND kind = 'production'"
        )
    body = api.get(
        "/api/overview",
        params={"area": "NO1", "start": "2026-01-01", "end": "2026-01-04"},
    ).json()
    # 3 days × 24 hours × 5 groups × 0.004 kWh = 0.00144 MWh.
    assert all(day["production"]["mwh"] == 0 for day in body["daily"])
    assert body["headline"]["production"]["mwh"] == 0.001
