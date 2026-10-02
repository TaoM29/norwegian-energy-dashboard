from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

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

    def backfill(self) -> int:
        return 1


class _FrozenDatetime(datetime):
    instant = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        value = cls.instant
        return value if tz is None else value.astimezone(tz)


def _successful_frame() -> pd.DataFrame:
    frame = pd.DataFrame({"time": [pd.Timestamp("2026-01-01T00:00:00Z")]})
    frame.attrs["cache_status"] = "network"
    frame.attrs["provenance"] = {"cache_status": "network"}
    return frame


def _stale_weather_frame(
    year: int,
    available_end: str,
    retrieved_at: str,
    *,
    reason: str = "Open-Meteo returned an inconsistent publication tail",
) -> pd.DataFrame:
    end = pd.Timestamp(available_end)
    times = pd.date_range(
        pd.Timestamp(year=year, month=1, day=1, tz="UTC"),
        end - pd.Timedelta(hours=1),
        freq="h",
    )
    frame = pd.DataFrame({
        "time": times,
        **{column: 1.0 for column in weather.OUTPUT_COLUMNS.values()},
    })
    provenance = {
        "cache_status": "stale_snapshot",
        "available_start": times[0].isoformat(),
        "available_end": end.isoformat(),
        "retrieved_at": pd.Timestamp(retrieved_at).isoformat(),
        "refresh_error": reason,
    }
    frame.attrs["cache_status"] = "stale_snapshot"
    frame.attrs["provenance"] = provenance
    return frame


def _freeze_refresh_clock(monkeypatch, instant: datetime, expected_end: str) -> None:
    class FrozenDatetime(_FrozenDatetime):
        pass

    FrozenDatetime.instant = instant
    monkeypatch.setattr(refresh_data, "datetime", FrozenDatetime)
    monkeypatch.setattr(
        weather,
        "era5_available_end",
        lambda now=None: pd.Timestamp(expected_end),
    )


def _install_refresh_fakes(monkeypatch, areas, loader) -> None:
    monkeypatch.setattr(refresh_data, "EnergyStore", lambda _path: object())
    monkeypatch.setattr(refresh_data, "RefreshService", _RefreshService)
    monkeypatch.setattr(weather, "AREA_COORDS", dict.fromkeys(areas, (59.9139, 10.7522)))
    monkeypatch.setattr(weather, "load_openmeteo_era5", loader)


def test_refresh_reuses_previous_year_and_forces_current_year(monkeypatch, tmp_path):
    _freeze_refresh_clock(monkeypatch, datetime(2026, 10, 3, tzinfo=timezone.utc), "2026-09-29T00:00:00Z")
    calls = []

    def fake_load(area, year, *, force_refresh):
        calls.append((area, year, force_refresh))
        return _successful_frame()

    monkeypatch.setattr(refresh_data, "EnergyStore", lambda _path: object())
    monkeypatch.setattr(refresh_data, "RefreshService", _RefreshService)
    monkeypatch.setattr(weather, "AREA_COORDS", {"NO1": (59.9139, 10.7522)})
    monkeypatch.setattr(weather, "load_openmeteo_era5", fake_load)

    assert refresh_data.main(["refresh", "--database", str(tmp_path / "energy.sqlite")]) == 0

    current_year = 2026
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
        refresh_data.main([
            "refresh",
            "--database", str(tmp_path / "energy.sqlite"),
            "--weather-grace-days", "7",
        ])

    assert "previous snapshot retained" not in str(raised.value)


def test_weather_grace_accepts_only_recent_well_formed_newest_year_snapshot():
    now = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)
    expected_end = datetime(2026, 9, 29, tzinfo=timezone.utc)
    frame = _stale_weather_frame(
        2026,
        "2026-09-25T00:00:00Z",
        "2026-10-02T19:37:00Z",
    )

    assert refresh_data._weather_grace_error(frame, 2026, expected_end, now, 7) is None
    assert refresh_data._weather_grace_error(frame, 2025, expected_end, now, 7) is not None


@pytest.mark.parametrize(
    "mutation",
    [
        "coverage_too_old",
        "retrieval_too_old",
        "future_coverage",
        "future_retrieval",
        "wrong_frame_start",
        "mismatched_available_start",
        "mismatched_available_end",
        "empty",
        "not_stale",
    ],
)
def test_weather_grace_rejects_old_future_or_malformed_snapshot(mutation):
    now = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)
    expected_end = datetime(2026, 9, 29, tzinfo=timezone.utc)
    frame = _stale_weather_frame(
        2026,
        "2026-09-25T00:00:00Z",
        "2026-10-02T19:37:00Z",
    )

    if mutation == "coverage_too_old":
        frame = _stale_weather_frame(2026, "2026-09-21T00:00:00Z", "2026-10-02T19:37:00Z")
    elif mutation == "retrieval_too_old":
        frame.attrs["provenance"]["retrieved_at"] = "2026-09-25T19:00:00+00:00"
    elif mutation == "future_coverage":
        frame = _stale_weather_frame(2026, "2026-09-30T00:00:00Z", "2026-10-02T19:37:00Z")
    elif mutation == "future_retrieval":
        frame.attrs["provenance"]["retrieved_at"] = "2026-10-04T00:00:00+00:00"
    elif mutation == "wrong_frame_start":
        frame = frame.iloc[1:].reset_index(drop=True)
    elif mutation == "mismatched_available_start":
        frame.attrs["provenance"]["available_start"] = "2026-01-02T00:00:00+00:00"
    elif mutation == "mismatched_available_end":
        frame.attrs["provenance"]["available_end"] = "2026-09-24T00:00:00+00:00"
    elif mutation == "empty":
        frame = frame.iloc[0:0]
    elif mutation == "not_stale":
        frame.attrs["cache_status"] = "network"

    assert refresh_data._weather_grace_error(frame, 2026, expected_end, now, 7) is not None


def test_graceful_retention_checks_all_areas_and_writes_degraded_report(monkeypatch, tmp_path, capsys):
    now = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)
    expected_end = "2026-09-29T00:00:00Z"
    _freeze_refresh_clock(monkeypatch, now, expected_end)
    calls = []

    def fake_load(area, year, *, force_refresh):
        calls.append((area, year, force_refresh))
        if year == 2026:
            return _stale_weather_frame(
                2026,
                "2026-09-25T00:00:00Z",
                "2026-10-02T19:37:00Z",
                reason=f"temporary publication inconsistency for {area}",
            )
        return _successful_frame()

    _install_refresh_fakes(monkeypatch, ("NO1", "NO2"), fake_load)
    report_path = tmp_path / "refresh-report.json"
    summary_path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    assert refresh_data.main([
        "refresh",
        "--database", str(tmp_path / "energy.sqlite"),
        "--weather-grace-days", "7",
        "--report", str(report_path),
    ]) == 0

    assert calls == [
        ("NO1", 2025, False),
        ("NO2", 2025, False),
        ("NO1", 2026, True),
        ("NO2", 2026, True),
    ]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["state"] == "degraded"
    retained = [row for row in report["weather"] if row["outcome"] == "retained"]
    assert {(row["area"], row["year"]) for row in retained} == {("NO1", 2026), ("NO2", 2026)}
    assert {row["status"] for row in retained} == {"stale_snapshot"}
    assert {row["available_end"] for row in retained} == {"2026-09-25T00:00:00+00:00"}
    assert {row["retrieved_at"] for row in retained} == {"2026-10-02T19:37:00+00:00"}
    assert {row["expected_end"] for row in retained} == {"2026-09-29T00:00:00+00:00"}
    assert all(row["error"].startswith("temporary publication inconsistency") for row in retained)
    assert all(row["reason"] is None for row in retained)
    assert not any(row["source_coverage_complete"] for row in retained)
    assert "Public data refresh: degraded" in summary_path.read_text()
    assert "NO2/2026: retained" in summary_path.read_text()
    assert "::warning title=Weather freshness degraded::" in capsys.readouterr().out


def test_strict_refresh_still_fails_stale_snapshot_and_writes_failed_report(monkeypatch, tmp_path):
    now = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)
    _freeze_refresh_clock(monkeypatch, now, "2026-09-29T00:00:00Z")
    stale = _stale_weather_frame(2026, "2026-09-25T00:00:00Z", "2026-10-02T19:37:00Z")
    _install_refresh_fakes(
        monkeypatch,
        ("NO1",),
        lambda _area, year, *, force_refresh: stale if year == 2026 else _successful_frame(),
    )
    report_path = tmp_path / "strict-report.json"

    with pytest.raises(RuntimeError, match="Weather refresh failed"):
        refresh_data.main([
            "refresh",
            "--database", str(tmp_path / "energy.sqlite"),
            "--report", str(report_path),
        ])

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["state"] == "failed"
    failed = [row for row in report["weather"] if row["outcome"] == "failed"]
    assert [(row["area"], row["year"]) for row in failed] == [("NO1", 2026)]
    assert failed[0]["error"]


def test_ineligible_grace_snapshot_fails_after_checking_all_areas(monkeypatch, tmp_path):
    now = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)
    _freeze_refresh_clock(monkeypatch, now, "2026-09-29T00:00:00Z")
    calls = []
    too_old = _stale_weather_frame(2026, "2026-09-20T00:00:00Z", "2026-10-02T19:37:00Z")

    def fake_load(area, year, *, force_refresh):
        calls.append((area, year, force_refresh))
        return too_old if year == 2026 else _successful_frame()

    _install_refresh_fakes(monkeypatch, ("NO1", "NO2"), fake_load)
    report_path = tmp_path / "failed-grace-report.json"

    with pytest.raises(RuntimeError, match="Weather refresh failed"):
        refresh_data.main([
            "refresh",
            "--database", str(tmp_path / "energy.sqlite"),
            "--weather-grace-days", "7",
            "--report", str(report_path),
        ])

    assert calls[-2:] == [("NO1", 2026, True), ("NO2", 2026, True)]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["state"] == "failed"
    assert {(row["area"], row["year"]) for row in report["weather"] if row["outcome"] == "failed"} == {
        ("NO1", 2026),
        ("NO2", 2026),
    }


def test_backfill_remains_strict_when_weather_grace_is_requested(monkeypatch, tmp_path):
    now = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)
    _freeze_refresh_clock(monkeypatch, now, "2026-09-29T00:00:00Z")
    stale = _stale_weather_frame(2026, "2026-09-25T00:00:00Z", "2026-10-02T19:37:00Z")
    _install_refresh_fakes(
        monkeypatch,
        ("NO1",),
        lambda _area, year, *, force_refresh: stale if year == 2026 else _successful_frame(),
    )

    with pytest.raises(RuntimeError, match="Weather refresh failed"):
        refresh_data.main([
            "backfill",
            "--database", str(tmp_path / "energy.sqlite"),
            "--weather-grace-days", "7",
            "--report", str(tmp_path / "backfill-report.json"),
        ])


def test_successful_recovery_writes_succeeded_report(monkeypatch, tmp_path):
    now = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)
    _freeze_refresh_clock(monkeypatch, now, "2026-09-29T00:00:00Z")
    _install_refresh_fakes(monkeypatch, ("NO1",), lambda *args, **kwargs: _successful_frame())
    report_path = tmp_path / "success-report.json"

    assert refresh_data.main([
        "refresh",
        "--database", str(tmp_path / "energy.sqlite"),
        "--report", str(report_path),
    ]) == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["state"] == "succeeded"
    assert [row["outcome"] for row in report["weather"]] == ["validated", "validated"]


def test_early_january_uses_previous_source_year_and_skips_future_year(monkeypatch, tmp_path):
    now = datetime(2027, 1, 3, 20, tzinfo=timezone.utc)
    expected_end = "2026-12-30T00:00:00Z"
    _freeze_refresh_clock(monkeypatch, now, expected_end)
    calls = []
    stale = _stale_weather_frame(2026, "2026-12-27T00:00:00Z", "2027-01-02T19:37:00Z")

    def fake_load(area, year, *, force_refresh):
        calls.append((area, year, force_refresh))
        return stale if year == 2026 else _successful_frame()

    _install_refresh_fakes(monkeypatch, ("NO1",), fake_load)

    assert refresh_data.main([
        "refresh",
        "--database", str(tmp_path / "energy.sqlite"),
        "--weather-grace-days", "7",
        "--report", str(tmp_path / "january-report.json"),
    ]) == 0

    assert calls == [("NO1", 2026, True)]


def test_weather_grace_days_must_be_nonnegative():
    with pytest.raises(SystemExit):
        refresh_data.parser().parse_args(["refresh", "--weather-grace-days", "-1"])


def test_weather_write_failure_is_fatal_and_reported_after_remaining_areas(monkeypatch, tmp_path):
    now = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)
    _freeze_refresh_clock(monkeypatch, now, "2026-09-29T00:00:00Z")
    calls = []

    def load(area, year, **kwargs):
        calls.append((area, year))
        if area == "NO1" and year == 2026:
            raise OSError("snapshot write failed")
        return _successful_frame()

    _install_refresh_fakes(monkeypatch, ("NO1", "NO2"), load)
    with pytest.raises(RuntimeError, match="snapshot write failed"):
        refresh_data.main(["refresh", "--database", str(tmp_path / "energy.sqlite"), "--weather-grace-days", "7"])

    assert calls[-1] == ("NO2", 2026)
    report = json.loads((tmp_path / "refresh-report.json").read_text())
    assert report["state"] == "failed"
    assert report["weather"][-2]["outcome"] == "failed"


def test_energy_failure_cannot_be_masked_by_weather_grace(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise RuntimeError("energy source failed")

    monkeypatch.setattr(refresh_data, "RefreshService", fail)
    with pytest.raises(RuntimeError, match="energy source failed"):
        refresh_data.main(["refresh", "--database", str(tmp_path / "energy.sqlite"), "--weather-grace-days", "7"])
    report = json.loads((tmp_path / "refresh-report.json").read_text())
    assert report["state"] == "failed"
    assert report["weather"] == []


def test_grace_accepts_exact_age_limit_but_rejects_malformed_timestamps():
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)
    expected_end = datetime(2026, 9, 29, tzinfo=timezone.utc)
    frame = _stale_weather_frame(2026, "2026-09-22T00:00:00Z", "2026-09-26T00:00:00Z")
    assert refresh_data._weather_grace_error(frame, 2026, expected_end, now, 7) is None
    for value in (None, "invalid", "2026-09-26T00:00:00"):
        frame.attrs["provenance"]["retrieved_at"] = value
        assert refresh_data._weather_grace_error(frame, 2026, expected_end, now, 7) is not None
