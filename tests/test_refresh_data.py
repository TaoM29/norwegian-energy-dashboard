from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from app_core.loaders import weather
from scripts import refresh_data


class _RefreshService:
    def __init__(self, _store):
        pass

    def refresh(self, *, days: int) -> int:
        assert days == 7
        return 1


def _successful_frame() -> pd.DataFrame:
    frame = pd.DataFrame({"time": [pd.Timestamp("2026-01-01T00:00:00Z")]})
    frame.attrs["cache_status"] = "network"
    frame.attrs["provenance"] = {"cache_status": "network"}
    return frame


def test_refresh_reuses_previous_year_and_forces_current_year(monkeypatch, tmp_path):
    calls = []

    def fake_load(area, year, *, force_refresh):
        calls.append((area, year, force_refresh))
        return _successful_frame()

    monkeypatch.setattr(refresh_data, "EnergyStore", lambda _path: object())
    monkeypatch.setattr(refresh_data, "RefreshService", _RefreshService)
    monkeypatch.setattr(weather, "AREA_COORDS", {"NO1": (59.9139, 10.7522)})
    monkeypatch.setattr(weather, "load_openmeteo_era5", fake_load)

    assert refresh_data.main(["refresh", "--database", str(tmp_path / "energy.sqlite")]) == 0

    current_year = datetime.now(timezone.utc).year
    assert calls == [
        ("NO1", current_year - 1, False),
        ("NO1", current_year, True),
    ]


def test_refresh_failure_surfaces_weather_refresh_error(monkeypatch, tmp_path):
    frame = _successful_frame()
    frame.attrs["cache_status"] = "stale_snapshot"
    frame.attrs["provenance"] = {
        "cache_status": "stale_snapshot",
        "refresh_error": "Open-Meteo returned an internal missing or non-finite value for precipitation",
        "available_end": "2026-09-25T00:00:00+00:00",
        "retrieved_at": "2026-09-26T19:37:00+00:00",
    }

    monkeypatch.setattr(refresh_data, "EnergyStore", lambda _path: object())
    monkeypatch.setattr(refresh_data, "RefreshService", _RefreshService)
    monkeypatch.setattr(weather, "AREA_COORDS", {"NO1": (59.9139, 10.7522)})
    monkeypatch.setattr(weather, "load_openmeteo_era5", lambda *args, **kwargs: frame)

    with pytest.raises(RuntimeError, match="internal missing or non-finite value for precipitation") as raised:
        refresh_data.main(["refresh", "--database", str(tmp_path / "energy.sqlite")])

    message = str(raised.value)
    assert "previous snapshot retained" in message
    assert "exclusive end: 2026-09-25T00:00:00+00:00" in message
    assert "retrieved: 2026-09-26T19:37:00+00:00" in message


def test_unavailable_refresh_reports_error_without_retained_snapshot_claim(monkeypatch, tmp_path):
    frame = pd.DataFrame({"time": pd.Series([], dtype="datetime64[ns, UTC]")})
    frame.attrs["cache_status"] = "unavailable"
    frame.attrs["provenance"] = {
        "cache_status": "unavailable",
        "error": "Open-Meteo returned no complete UTC day across all variables",
    }

    monkeypatch.setattr(refresh_data, "EnergyStore", lambda _path: object())
    monkeypatch.setattr(refresh_data, "RefreshService", _RefreshService)
    monkeypatch.setattr(weather, "AREA_COORDS", {"NO1": (59.9139, 10.7522)})
    monkeypatch.setattr(weather, "load_openmeteo_era5", lambda *args, **kwargs: frame)

    with pytest.raises(RuntimeError, match="no complete UTC day") as raised:
        refresh_data.main(["refresh", "--database", str(tmp_path / "energy.sqlite")])

    assert "previous snapshot retained" not in str(raised.value)
