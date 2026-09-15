from datetime import date

from fastapi import HTTPException
import pandas as pd
import pytest

from app_core.ingestion.models import BASE_GROUPS
from app_core.ingestion.store import EnergyStore
from app_core.loaders import weather
from backend import data
from backend.main import _daily_rows


def test_daily_summaries_preserve_missing_groups_and_invalidate_on_revision(tmp_path, monkeypatch):
    path = tmp_path / "energy.sqlite"
    monkeypatch.setenv("ENERGY_DATABASE", str(path))
    store = EnergyStore(path)
    rows = []
    for hour in range(2):
        for group in BASE_GROUPS["production"]:
            rows.append({"timestamp": f"2025-01-01T0{hour}:00:00Z", "area": "NO1", "kind": "production", "group": group, "value": None if hour == 1 and group == "wind" else 100.25, "unit": "kWh", "source": "fixture", "retrieved_at": "2025-01-02T00:00:00Z", "revision": None, "quality": "missing" if hour == 1 and group == "wind" else "ok"})
    store.upsert(rows)
    with store._connect(read_only=True) as connection:
        original = _daily_rows(connection, "NO1", "2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z")
    staging = store.prepare_staging()
    store.publish(staging)
    with store._connect(read_only=True) as connection:
        computed = _daily_rows(connection, "NO1", "2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z")
    assert computed == original
    assert computed[("2025-01-01", "production")]["observedHours"] == 1
    daily = data.energy_daily_frame("NO1", "2025-01-01", "2025-01-02")
    assert daily.attrs["precomputed"] is True
    assert daily["value"].sum() == pytest.approx(902.25)
    assert daily.loc[daily["group"] == "wind", "observed_hours"].iloc[0] == 1
    assert data.energy_frame("NO1", "2025-01-01", "2025-01-02", groups=[]).empty
    rows[-1]["value"] = 200.0
    rows[-1]["quality"] = "ok"
    store.upsert([rows[-1]])
    revised = data.energy_daily_frame("NO1", "2025-01-01", "2025-01-02")
    assert revised.attrs["precomputed"] is False
    assert revised["value"].sum() == pytest.approx(1102.25)


def test_weather_reads_snapshot_only_and_reports_incomplete_interval(tmp_path, monkeypatch):
    monkeypatch.setattr(weather, "WEATHER_SNAPSHOT_DIR", tmp_path)
    def unexpected_request(*args, **kwargs):
        raise AssertionError("ordinary exploration must not fetch upstream")
    monkeypatch.setattr(weather, "_request_payload", unexpected_request)
    frame = pd.DataFrame({"time": pd.date_range("2025-01-01", periods=3, freq="h", tz="UTC"), **{column: [1.0, 1.5, 2.0] for column in weather.OUTPUT_COLUMNS.values()}})
    identity = weather._identity("NO1", *weather.AREA_COORDS["NO1"], 2025)
    weather._write_snapshot(weather._snapshot_path(identity), identity, {"source": weather.SOURCE, "model": weather.MODEL, "units": weather.EXPECTED_UNITS}, frame)
    result = data.weather_frame("NO1", date(2025, 1, 1), date(2025, 1, 2))
    assert len(result) == 3
    assert result.attrs["provenance"]["coverage_complete"] is False
    assert data.records(pd.DataFrame({"missing": [float("nan")]}))[0]["missing"] is None
    with pytest.raises(HTTPException) as error:
        data.weather_frame("NO2", "2025-01-01", "2025-01-02")
    assert error.value.status_code == 503
