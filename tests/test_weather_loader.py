import pandas as pd
import pytest

import app_core.loaders.weather as w


class _FakeResp:
    def __init__(self, payload, status_ok=True):
        self._payload = payload
        self._ok = status_ok
        self.requested_url = None
        self.requested_params = None

    def raise_for_status(self):
        if not self._ok:
            raise RuntimeError("HTTP error")

    def json(self):
        return self._payload


def test_load_openmeteo_era5_returns_expected_columns_and_sorted(monkeypatch):
    # unsorted times on purpose
    payload = {
        "hourly": {
            "time": ["2024-01-01T02:00", "2024-01-01T00:00", "2024-01-01T01:00"],
            "temperature_2m": [2.0, 0.0, 1.0],
            "precipitation": [0.2, 0.0, 0.1],
            "windspeed_10m": [5.0, 4.0, 4.5],
            "windgusts_10m": [8.0, 7.0, 7.5],
            "winddirection_10m": [180, 170, 175],
        }
    }
    resp = _FakeResp(payload, status_ok=True)

    def fake_get(url, params=None, timeout=None):
        resp.requested_url = url
        resp.requested_params = params
        return resp

    monkeypatch.setattr(w.requests, "get", fake_get)

    df = w.load_openmeteo_era5("NO1", 2024, timezone="Europe/Oslo")

    expected_cols = [
        "time",
        "temperature_2m (°C)",
        "precipitation (mm)",
        "wind_speed_10m (m/s)",
        "wind_gusts_10m (m/s)",
        "wind_direction_10m (°)",
    ]
    assert list(df.columns) == expected_cols
    assert len(df) == 3

    # sorted ascending by time
    assert df["time"].is_monotonic_increasing
    assert pd.api.types.is_datetime64_any_dtype(df["time"])

    # sanity check values moved with sorting
    assert df.loc[0, "temperature_2m (°C)"] == 0.0
    assert df.loc[1, "temperature_2m (°C)"] == 1.0
    assert df.loc[2, "temperature_2m (°C)"] == 2.0

    # verify request params use correct coordinates
    lat, lon = w.AREA_COORDS["NO1"]
    assert resp.requested_url == "https://archive-api.open-meteo.com/v1/archive"
    assert float(resp.requested_params["latitude"]) == float(lat)
    assert float(resp.requested_params["longitude"]) == float(lon)
    assert resp.requested_params["start_date"] == "2024-01-01"
    assert resp.requested_params["end_date"] == "2024-12-31"
    assert resp.requested_params["timezone"] == "Europe/Oslo"


def test_load_openmeteo_era5_raises_on_http_error(monkeypatch):
    resp = _FakeResp({"hourly": {}}, status_ok=False)

    def fake_get(url, params=None, timeout=None):
        return resp

    monkeypatch.setattr(w.requests, "get", fake_get)

    with pytest.raises(RuntimeError):
        w.load_openmeteo_era5("NO1", 2024)


def test_load_openmeteo_era5_invalid_area_keyerror():
    with pytest.raises(KeyError):
        w.load_openmeteo_era5("NOX", 2024)
