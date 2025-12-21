from urllib.parse import urlparse, parse_qsl

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
