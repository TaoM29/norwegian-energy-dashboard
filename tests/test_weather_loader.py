from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

import app_core.loaders.weather as weather


class _FakeResponse:
    def __init__(self, payload, error: Exception | None = None):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error:
            raise self._error

    def json(self):
        return self._payload


def _payload(start: str, periods: int, *, unit_overrides=None, omit_at: int | None = None):
    times = pd.date_range(start, periods=periods, freq="h", tz="UTC")
    if omit_at is not None:
        times = times.delete(omit_at)
    count = len(times)
    units = dict(weather.EXPECTED_UNITS)
    units.update(unit_overrides or {})
    return {
        "hourly_units": units,
        "hourly": {
            "time": [value.strftime("%Y-%m-%dT%H:%M") for value in times],
            "temperature_2m": [1.0] * count,
            "precipitation": [0.2] * count,
            "wind_speed_10m": [4.0] * count,
            "wind_gusts_10m": [7.0] * count,
            "wind_direction_10m": [180.0] * count,
        },
    }


@pytest.fixture
def isolated_snapshots(monkeypatch, tmp_path):
    monkeypatch.setattr(weather, "WEATHER_SNAPSHOT_DIR", tmp_path / "weather")
    monkeypatch.setattr(weather.time, "sleep", lambda _delay: None)


def test_annual_loader_uses_explicit_model_units_and_utc(monkeypatch, isolated_snapshots):
    response = _FakeResponse(_payload("2023-01-01", 365 * 24))
    request = {}

    def fake_get(url, params=None, timeout=None):
        request.update(url=url, params=params, timeout=timeout)
        return response

    monkeypatch.setattr(weather.requests, "get", fake_get)
    frame = weather.load_openmeteo_era5("NO1", 2023)

    assert list(frame.columns) == ["time", *weather.OUTPUT_COLUMNS.values()]
    assert len(frame) == 365 * 24
    assert isinstance(frame["time"].dtype, pd.DatetimeTZDtype)
    assert str(frame["time"].dt.tz) == "UTC"
    assert frame["time"].is_monotonic_increasing
    assert request["url"] == weather.ARCHIVE_URL
    assert request["params"]["hourly"] == ",".join(weather.HOURLY_VARIABLES)
    assert request["params"]["models"] == "era5_seamless"
    assert request["params"]["wind_speed_unit"] == "ms"
    assert request["params"]["temperature_unit"] == "celsius"
    assert request["params"]["precipitation_unit"] == "mm"
    assert request["params"]["timezone"] == "UTC"
    assert frame.attrs["provenance"]["available_end"] == "2024-01-01T00:00:00+00:00"
    assert frame.attrs["units"]["wind_speed_10m (m/s)"] == "m/s"
    assert frame.attrs["coverage_complete"] is True
    assert frame.attrs["publication_lag_days"] == 5
    assert frame.attrs["source_expected_available_end"].endswith("+00:00")


def test_current_year_request_is_capped_to_latest_available_day(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-04T00:00:00Z"),
    )
    response = _FakeResponse(_payload("2026-01-01", 3 * 24))
    request = {}

    def fake_get(url, params=None, timeout=None):
        request["params"] = params
        return response

    monkeypatch.setattr(weather.requests, "get", fake_get)
    frame = weather.load_openmeteo_era5("NO1", 2026)

    assert request["params"]["end_date"] == "2026-01-03"
    assert frame["time"].max() == pd.Timestamp("2026-01-03T23:00:00Z")
    assert frame.attrs["available_end"] == "2026-01-04T00:00:00+00:00"
    assert frame.attrs["coverage_complete"] is False
    assert frame.attrs["source_coverage_complete"] is True


def test_trailing_nulls_trim_to_common_complete_utc_day(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-04T00:00:00Z"),
    )
    payload = _payload("2026-01-01", 3 * 24)
    for variable in weather.HOURLY_VARIABLES:
        payload["hourly"][variable][-24:] = [None] * 24
    monkeypatch.setattr(weather.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))

    frame = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    assert len(frame) == 2 * 24
    assert frame.attrs["available_end"] == "2026-01-03T00:00:00+00:00"
    assert frame.attrs["source_expected_available_end"] == "2026-01-04T00:00:00+00:00"
    assert frame.attrs["source_coverage_complete"] is False
    assert frame.attrs["variable_last_timestamp"] == {
        variable: "2026-01-02T23:00:00+00:00" for variable in weather.HOURLY_VARIABLES
    }


def test_variable_specific_tail_uses_earliest_common_boundary(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-04T00:00:00Z"),
    )
    payload = _payload("2026-01-01", 3 * 24)
    payload["hourly"]["wind_gusts_10m"][-24:] = [None] * 24
    monkeypatch.setattr(weather.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))

    frame = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    assert frame.attrs["available_end"] == "2026-01-03T00:00:00+00:00"
    assert frame.attrs["variable_last_timestamp"]["wind_gusts_10m"] == "2026-01-02T23:00:00+00:00"
    assert frame.attrs["variable_last_timestamp"]["temperature_2m"] == "2026-01-03T23:00:00+00:00"


def test_partial_utc_day_is_not_published(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-03T00:00:00Z"),
    )
    payload = _payload("2026-01-01", 2 * 24)
    for variable in weather.HOURLY_VARIABLES:
        payload["hourly"][variable][-12:] = [None] * 12
    monkeypatch.setattr(weather.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))

    frame = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    assert len(frame) == 24
    assert frame.attrs["available_end"] == "2026-01-02T00:00:00+00:00"
    assert set(frame.attrs["variable_last_timestamp"].values()) == {"2026-01-02T11:00:00+00:00"}


def test_recent_current_year_prefix_is_reused_before_ttl(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-03T00:00:00Z"),
    )
    calls = 0
    payload = _payload("2026-01-01", 2 * 24)
    for variable in weather.HOURLY_VARIABLES:
        payload["hourly"][variable][-24:] = [None] * 24

    def fake_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _FakeResponse(payload)

    monkeypatch.setattr(weather.requests, "get", fake_get)
    first = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)
    second = weather.load_openmeteo_era5("NO1", 2026)

    assert calls == 1
    assert first.attrs["available_end"] == second.attrs["available_end"]
    assert second.attrs["cache_status"] == "snapshot"
    assert second.attrs["source_coverage_complete"] is False


def test_internal_null_is_rejected_instead_of_trimmed(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-03T00:00:00Z"),
    )
    payload = _payload("2026-01-01", 2 * 24)
    payload["hourly"]["temperature_2m"][12] = None
    monkeypatch.setattr(weather.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))

    frame = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    assert frame.empty
    assert "internal missing" in frame.attrs["provenance"]["error"]


def test_shorter_valid_prefix_does_not_replace_better_snapshot(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-03T00:00:00Z"),
    )
    monkeypatch.setattr(
        weather.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(_payload("2026-01-01", 2 * 24)),
    )
    first = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)
    snapshot_path = next(weather.WEATHER_SNAPSHOT_DIR.glob("*.json"))
    snapshot_before = snapshot_path.read_bytes()

    shorter = _payload("2026-01-01", 2 * 24)
    for variable in weather.HOURLY_VARIABLES:
        shorter["hourly"][variable][-24:] = [None] * 24
    monkeypatch.setattr(weather.requests, "get", lambda *args, **kwargs: _FakeResponse(shorter))
    fallback = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    assert fallback.attrs["cache_status"] == "stale_snapshot"
    assert fallback.attrs["available_end"] == first.attrs["available_end"]
    assert snapshot_path.read_bytes() == snapshot_before


def test_internal_gap_is_retried_and_a_valid_response_is_published(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-04T00:00:00Z"),
    )
    inconsistent = _payload("2026-01-01", 3 * 24)
    inconsistent["hourly"]["precipitation"][36] = None
    responses = [inconsistent, _payload("2026-01-01", 3 * 24)]
    calls = 0

    def fake_get(*args, **kwargs):
        nonlocal calls
        response = responses[calls]
        calls += 1
        return _FakeResponse(response)

    monkeypatch.setattr(weather.requests, "get", fake_get)

    frame = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    assert calls == 2
    assert len(frame) == 3 * 24
    assert frame.attrs["cache_status"] == "network"
    assert frame.attrs["available_end"] == "2026-01-04T00:00:00+00:00"


def test_transport_and_content_failures_share_one_retry_budget(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-04T00:00:00Z"),
    )
    inconsistent = _payload("2026-01-01", 3 * 24)
    inconsistent["hourly"]["precipitation"][36] = None
    outcomes = [
        weather.requests.ConnectionError("temporary outage"),
        _FakeResponse(inconsistent),
        _FakeResponse(_payload("2026-01-01", 3 * 24)),
    ]
    calls = 0
    delays = []

    def fake_get(*args, **kwargs):
        nonlocal calls
        outcome = outcomes[calls]
        calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(weather.requests, "get", fake_get)
    monkeypatch.setattr(weather.time, "sleep", delays.append)

    frame = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    assert calls == weather.WEATHER_MAX_ATTEMPTS
    assert delays == [0.5, 1.0]
    assert len(frame) == 3 * 24
    assert frame.attrs["cache_status"] == "network"


def test_repeated_internal_gap_retains_snapshot_with_detailed_error(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-03T00:00:00Z"),
    )
    monkeypatch.setattr(
        weather.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(_payload("2026-01-01", 2 * 24)),
    )
    original = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)
    snapshot_path = next(weather.WEATHER_SNAPSHOT_DIR.glob("*.json"))
    snapshot_before = snapshot_path.read_bytes()

    inconsistent = _payload("2026-01-01", 2 * 24)
    inconsistent["hourly"]["precipitation"][12] = None
    calls = 0

    def fake_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _FakeResponse(inconsistent)

    monkeypatch.setattr(weather.requests, "get", fake_get)

    fallback = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    assert calls == weather.WEATHER_MAX_ATTEMPTS
    pd.testing.assert_frame_equal(original, fallback)
    assert fallback.attrs["cache_status"] == "stale_snapshot"
    assert "internal missing or non-finite value for precipitation" in fallback.attrs["provenance"]["refresh_error"]
    assert snapshot_path.read_bytes() == snapshot_before


def test_repeated_internal_gap_without_snapshot_remains_unavailable(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-03T00:00:00Z"),
    )
    inconsistent = _payload("2026-01-01", 2 * 24)
    inconsistent["hourly"]["precipitation"][12] = None
    calls = 0

    def fake_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _FakeResponse(inconsistent)

    monkeypatch.setattr(weather.requests, "get", fake_get)

    frame = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    assert calls == weather.WEATHER_MAX_ATTEMPTS
    assert frame.empty
    assert frame.attrs["cache_status"] == "unavailable"
    assert "precipitation at 2026-01-01T12:00:00+00:00" in frame.attrs["provenance"]["error"]
    assert list(weather.WEATHER_SNAPSHOT_DIR.glob("*.json")) == []


def test_shorter_prefix_is_retried_before_falling_back_to_snapshot(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-03T00:00:00Z"),
    )
    monkeypatch.setattr(
        weather.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(_payload("2026-01-01", 2 * 24)),
    )
    weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-04T00:00:00Z"),
    )
    responses = [_payload("2026-01-01", 24), _payload("2026-01-01", 3 * 24)]
    calls = 0

    def fake_get(*args, **kwargs):
        nonlocal calls
        response = responses[calls]
        calls += 1
        return _FakeResponse(response)

    monkeypatch.setattr(weather.requests, "get", fake_get)

    frame = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    assert calls == 2
    assert frame.attrs["cache_status"] == "network"
    assert frame.attrs["available_end"] == "2026-01-04T00:00:00+00:00"


def test_last_known_good_survives_outage_and_bad_refresh(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-02T00:00:00Z"),
    )
    monkeypatch.setattr(weather.requests, "get", lambda *args, **kwargs: _FakeResponse(_payload("2026-01-01", 24)))
    first = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)
    snapshot_path = next(weather.WEATHER_SNAPSHOT_DIR.glob("*.json"))
    snapshot_before = snapshot_path.read_bytes()

    monkeypatch.setattr(
        weather.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse({}, RuntimeError("source offline")),
    )
    fallback = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)

    pd.testing.assert_frame_equal(first, fallback)
    assert fallback.attrs["cache_status"] == "stale_snapshot"
    assert "source offline" in fallback.attrs["provenance"]["refresh_error"]
    assert snapshot_path.read_bytes() == snapshot_before

    bad_units = _payload("2026-01-01", 24, unit_overrides={"wind_speed_10m": "km/h"})
    monkeypatch.setattr(weather.requests, "get", lambda *args, **kwargs: _FakeResponse(bad_units))
    fallback = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)
    assert fallback.attrs["cache_status"] == "stale_snapshot"
    assert snapshot_path.read_bytes() == snapshot_before


def test_snapshot_is_idempotent_for_complete_year(monkeypatch, isolated_snapshots):
    calls = 0

    def fake_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _FakeResponse(_payload("2023-01-01", 365 * 24))

    monkeypatch.setattr(weather.requests, "get", fake_get)
    first = weather.load_openmeteo_era5("NO2", 2023)
    second = weather.load_openmeteo_era5("NO2", 2023)

    assert calls == 1
    assert first.attrs["provenance"]["location"] == "NO2"
    assert second.attrs["cache_status"] == "snapshot"
    pd.testing.assert_frame_equal(first, second)


@pytest.mark.parametrize(
    "payload",
    [
        _payload("2026-01-01", 24, unit_overrides={"wind_speed_10m": "km/h"}),
        _payload("2026-01-01", 24, omit_at=5),
    ],
)
def test_invalid_units_or_hourly_gap_is_unavailable(monkeypatch, isolated_snapshots, payload):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-02T00:00:00Z"),
    )
    monkeypatch.setattr(weather.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))
    frame = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)
    assert frame.empty
    assert frame.attrs["cache_status"] == "unavailable"


def test_non_finite_values_are_unavailable(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp("2026-01-02T00:00:00Z"),
    )
    payload = _payload("2026-01-01", 24)
    payload["hourly"]["wind_speed_10m"][7] = float("inf")
    monkeypatch.setattr(weather.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))
    frame = weather.load_openmeteo_era5("NO1", 2026, force_refresh=True)
    assert frame.empty
    assert "non-finite" in frame.attrs["provenance"]["error"]


def test_transient_request_failures_are_retried(monkeypatch, isolated_snapshots):
    calls = 0
    delays = []

    def fake_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise weather.requests.ConnectionError("temporary outage")
        return _FakeResponse(_payload("2023-01-01", 365 * 24))

    monkeypatch.setattr(weather.requests, "get", fake_get)
    monkeypatch.setattr(weather.time, "sleep", delays.append)
    frame = weather.load_openmeteo_era5("NO1", 2023, force_refresh=True)

    assert len(frame) == 365 * 24
    assert calls == 3
    assert delays == [0.5, 1.0]


def test_nontransient_http_error_is_not_retried(monkeypatch, isolated_snapshots):
    calls = 0
    delays = []
    response = weather.requests.Response()
    response.status_code = 400
    error = weather.requests.HTTPError("bad request", response=response)

    def fake_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise error

    monkeypatch.setattr(weather.requests, "get", fake_get)
    monkeypatch.setattr(weather.time, "sleep", delays.append)

    frame = weather.load_openmeteo_era5("NO1", 2023, force_refresh=True)

    assert calls == 1
    assert delays == []
    assert frame.empty
    assert frame.attrs["cache_status"] == "unavailable"
    assert "bad request" in frame.attrs["provenance"]["error"]


def test_missing_annual_segment_makes_multiyear_request_unavailable(monkeypatch):
    def fake_annual(*, latitude, longitude, location, year, force_refresh):
        if year == 2023:
            frame, _, _ = weather._frame_from_response(_payload("2023-12-31", 24))
            frame.attrs["provenance"] = {"cache_status": "snapshot"}
            return frame
        return weather._empty_weather({"cache_status": "unavailable", "error": "offline"})

    monkeypatch.setattr(weather, "_load_location_year", fake_annual)
    frame = weather.load_openmeteo_point(
        59.9,
        10.7,
        pd.Timestamp("2023-12-31T00:00:00Z"),
        pd.Timestamp("2024-01-02T00:00:00Z"),
    )
    assert frame.empty
    assert frame.attrs["cache_status"] == "unavailable"


def test_outage_without_snapshot_is_empty_not_zero(monkeypatch, isolated_snapshots):
    monkeypatch.setattr(
        weather.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse({}, RuntimeError("source offline")),
    )
    frame = weather.load_openmeteo_era5("NO1", 2023, force_refresh=True)
    assert frame.empty
    assert frame.attrs["cache_status"] == "unavailable"
    assert frame["precipitation (mm)"].sum() == 0  # empty sum, no synthesized rows


def test_utc_only_and_invalid_area(isolated_snapshots):
    with pytest.raises(ValueError, match="UTC"):
        weather.load_openmeteo_era5("NO1", 2023, timezone="Europe/Oslo")
    with pytest.raises(KeyError):
        weather.load_openmeteo_era5("NOX", 2023)


def test_era5_available_end_is_an_exclusive_utc_boundary():
    now = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
    assert weather.era5_available_end(now) == pd.Timestamp("2026-09-10T00:00:00Z")
