from urllib.parse import urlparse, parse_qsl

from app_core.ingestion import EnergyStore

import app_core.loaders.mongo_utils as mu


class FakeDB(dict):
    """Dict-like object to mimic db['collection_name'] access."""
    def __getitem__(self, key):
        return f"<COLL:{key}>"


def test_ensure_auth_source_adds_defaults_when_missing():
    uri = "mongodb://localhost:27017"
    out = mu._ensure_auth_source(uri)

    q = dict(parse_qsl(urlparse(out).query))
    assert q["authSource"] == "admin"
    assert q["retryWrites"] == "true"
    assert q["w"] == "majority"
    assert q["appName"] == "Cluster007"


def test_ensure_auth_source_preserves_existing_values():
    uri = (
        "mongodb://localhost:27017"
        "?authSource=custom&retryWrites=false&w=1&appName=MyApp"
    )
    out = mu._ensure_auth_source(uri)

    q = dict(parse_qsl(urlparse(out).query))
    assert q["authSource"] == "custom"
    assert q["retryWrites"] == "false"
    assert q["w"] == "1"
    assert q["appName"] == "MyApp"


def test_get_prod_coll_for_year_selects_correct_collection(monkeypatch):
    monkeypatch.setattr(mu, "get_db", lambda: FakeDB())

    c21 = mu.get_prod_coll_for_year(2021)
    c24 = mu.get_prod_coll_for_year(2024)

    assert c21 == f"<COLL:{mu.COLL_PROD_2021}>"
    assert c24 == f"<COLL:{mu.COLL_PROD_2224}>"


def test_get_cons_coll_uses_consumption_collection(monkeypatch):
    monkeypatch.setattr(mu, "get_db", lambda: FakeDB())
    c = mu.get_cons_coll()
    assert c == f"<COLL:{mu.COLL_CONS_2124}>"


def test_load_energy_records_prefers_validated_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "energy.sqlite"
    store = EnergyStore(path)
    base = {
        "timestamp": "2026-09-01T00:00:00Z",
        "area": "NO1",
        "kind": "production",
        "group": "solar",
        "value": 42.0,
        "unit": "kWh",
        "source": "Elhub",
        "retrieved_at": "2026-09-02T00:00:00Z",
        "revision": "2026-09-01T12:00:00Z",
        "quality": "ok",
    }
    store.upsert([
        base,
        {**base, "timestamp": "2026-09-01T01:00:00Z", "value": 99.0},
    ])
    monkeypatch.setattr(mu, "get_db", lambda: (_ for _ in ()).throw(AssertionError("Mongo fallback used")))

    frame = mu.load_energy_records(
        start="2026-09-01T00:00:00Z", end="2026-09-01T01:00:00Z",
        areas=["NO1"], kinds=["Production"], groups=["solar"], snapshot_path=path,
    )

    assert frame["value"].tolist() == [42.0]
    assert str(frame["timestamp"].dtype.tz) == "UTC"


def test_energy_status_derives_current_year_from_common_validated_records(tmp_path, monkeypatch):
    path = tmp_path / "energy.sqlite"
    store = EnergyStore(path)
    rows = []
    for area in mu.PRICE_AREAS:
        for kind, groups in mu.BASE_GROUPS.items():
            for group in groups:
                rows.append({
                    "timestamp": "2026-09-01T00:00:00Z",
                    "area": area,
                    "kind": kind,
                    "group": group,
                    "value": 1.0,
                    "unit": "kWh",
                    "source": "Elhub",
                    "retrieved_at": "2026-09-02T00:00:00Z",
                    "revision": "2026-09-01T12:00:00Z",
                    "quality": "ok",
                })
    store.upsert(rows)
    monkeypatch.setattr(mu, "get_db", lambda: (_ for _ in ()).throw(AssertionError("Mongo fallback used")))

    status = mu.get_energy_status(snapshot_path=path)

    assert status["backend"] == "sqlite"
    assert status["available_years"] == [2026]
    assert status["common_complete_window"]["series_count"] == 50


def test_available_years_are_area_specific_and_do_not_require_common_window():
    coverage = [
        {
            "area": "NO1", "kind": "production", "group": "wind",
            "start": "2021-02-01T00:00:00Z", "end": "2022-01-01T00:00:00Z", "count": 8016,
        },
        {
            "area": "NO1", "kind": "consumption", "group": "household",
            "start": "2021-01-01T00:00:00Z", "end": "2026-09-01T00:00:00Z", "count": 1,
        },
        {
            "area": "NO5", "kind": "production", "group": "wind",
            "start": "2022-01-01T00:00:00Z", "end": "2026-09-01T00:00:00Z", "count": 1,
        },
    ]

    assert mu.available_years_from_coverage(coverage, area="NO1") == [2021, 2022, 2023, 2024, 2025, 2026]
    assert mu.available_years_from_coverage(coverage, area="NO5") == [2022, 2023, 2024, 2025, 2026]


def test_local_2021_boundary_hour_does_not_advertise_2020():
    coverage = [{
        "area": "NO1", "kind": "production", "group": "hydro",
        "start": "2020-12-31T23:00:00Z", "end": "2021-01-02T00:00:00Z", "count": 25,
    }]

    assert mu.available_years_from_coverage(coverage, area="NO1") == [2021]
