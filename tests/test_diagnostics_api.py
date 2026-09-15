from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import backend.diagnostics as diagnostics


def _energy(hours: int = 480, *, missing: int | None = None) -> pd.DataFrame:
    time = pd.date_range("2026-01-01", periods=hours, freq="h", tz="UTC")
    x = np.arange(hours, dtype=float)
    values = 100 + 0.05 * x + 15 * np.sin(2 * np.pi * x / 24)
    frame = pd.DataFrame(
        {
            "timestamp": time,
            "area": "NO1",
            "kind": "production",
            "group": "solar",
            "value": values,
            "unit": "kWh",
        }
    )
    return frame.drop(index=missing) if missing is not None else frame


def _weather(hours: int = 480, *, missing_precip: bool = False) -> pd.DataFrame:
    time = pd.date_range("2026-01-01", periods=hours, freq="h", tz="UTC")
    x = np.arange(hours, dtype=float)
    temperature = 4 + np.sin(2 * np.pi * x / 24)
    temperature[240] += 20
    precipitation = np.mod(x, 31) / 20
    precipitation[200] = 80
    if missing_precip:
        precipitation[10] = np.nan
    return pd.DataFrame(
        {
            "time": time,
            "temperature_2m (°C)": temperature,
            "precipitation (mm)": precipitation,
            "wind_speed_10m (m/s)": 5 + np.sin(x / 7),
            "wind_gusts_10m (m/s)": 8 + np.sin(x / 7),
            "wind_direction_10m (°)": np.mod(x * 4, 360),
        }
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(diagnostics, "energy_frame", lambda *args, **kwargs: _energy())
    monkeypatch.setattr(diagnostics, "weather_frame", lambda *args, **kwargs: _weather())
    monkeypatch.setattr(
        diagnostics,
        "provenance",
        lambda area, start, end: {"area": area, "energy": {"version": "fixture"}},
    )
    app = FastAPI()
    app.include_router(diagnostics.router)
    return TestClient(app)


def test_correlation_matches_centered_helper_and_normalizes_display_only(client: TestClient) -> None:
    response = client.get(
        "/api/diagnostics/correlation",
        params={
            "area": "NO1",
            "start": "2026-01-01",
            "end": "2026-01-21",
            "kind": "production",
            "group": "solar",
            "weather": "temperature_2m (°C)",
            "windowHours": 24,
            "lagHours": 0,
            "normalize": "true",
        },
    )
    assert response.status_code == 200
    body = response.json()
    expected = diagnostics.rolling_pearson_corr(
        _weather().set_index("time")["temperature_2m (°C)"],
        _energy().set_index("timestamp")["value"],
        24,
        center=True,
        min_periods=24,
    ).dropna()
    assert body["summary"]["pairedHours"] == 480
    assert body["summary"]["meanCorrelation"] == pytest.approx(expected.mean())
    assert body["units"]["weather"] == "z-score"
    assert body["metadata"]["normalization"].startswith("Population z-scores")


def test_correlation_validates_group_window_and_lag_overlap(client: TestClient) -> None:
    common = {"start": "2026-01-01", "end": "2026-01-21", "kind": "production"}
    assert client.get("/api/diagnostics/correlation", params={**common, "group": "household"}).status_code == 422
    response = client.get(
        "/api/diagnostics/correlation",
        params={**common, "group": "solar", "windowHours": 480, "lagHours": 240},
    )
    assert response.status_code == 422
    assert "paired hours" in response.json()["detail"]


def test_decomposition_returns_effective_odd_smoothers_and_bounded_spectrum(client: TestClient) -> None:
    response = client.get(
        "/api/diagnostics/decomposition",
        params={
            "start": "2026-01-01",
            "end": "2026-01-21",
            "kind": "production",
            "group": "solar",
            "period": 24,
            "seasonalSmoother": 12,
            "trendSmoother": 364,
            "spectrogramWindow": 96,
            "spectrogramOverlap": 48,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["effectiveParameters"]["seasonalSmoother"] == 13
    assert body["effectiveParameters"]["trendSmoother"] == 365
    assert len(body["components"]) == 480
    assert len(body["spectrogram"]["frequencies"]) == len(body["spectrogram"]["magnitude"])
    assert max(body["spectrogram"]["frequencies"]) <= 12
    assert all(
        len(row) == len(body["spectrogram"]["times"])
        for row in body["spectrogram"]["magnitude"]
    )

    source = _energy()
    helper_frame = pd.DataFrame(
        {
            "price_area": "NO1",
            "production_group": "solar",
            "start_time": source["timestamp"],
            "quantity_kwh": source["value"],
        }
    )
    figures, details, _ = diagnostics.stl_decompose_elhub(
        helper_frame,
        area="NO1",
        group="solar",
        period=24,
        seasonal=12,
        trend=364,
        robust=True,
        group_col="production_group",
    )
    assert details["seasonal"] == body["effectiveParameters"]["seasonalSmoother"]
    for key in ("observed", "seasonal", "trend", "resid"):
        np.testing.assert_allclose(
            [row[key] for row in body["components"]],
            np.asarray(figures[key].data[0].y, dtype=float),
            rtol=1e-12,
            atol=1e-10,
        )

    _, frequencies, spectral_times, magnitude = diagnostics.production_spectrogram(
        helper_frame,
        area="NO1",
        group="solar",
        window_len=96,
        overlap=48,
        group_col="production_group",
        freq_units="cpd",
    )
    np.testing.assert_allclose(body["spectrogram"]["frequencies"], frequencies * 24, atol=5e-9)
    assert body["spectrogram"]["times"] == [
        value.isoformat().replace("+00:00", "Z") for value in spectral_times
    ]
    np.testing.assert_allclose(body["spectrogram"]["magnitude"], magnitude, rtol=1e-12, atol=1e-10)


def test_decomposition_rejects_overlap_and_missing_hour(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    params = {
        "start": "2026-01-01",
        "end": "2026-01-21",
        "group": "solar",
        "spectrogramWindow": 48,
        "spectrogramOverlap": 48,
    }
    assert client.get("/api/diagnostics/decomposition", params=params).status_code == 422
    monkeypatch.setattr(diagnostics, "energy_frame", lambda *args, **kwargs: _energy(missing=20))
    params["spectrogramOverlap"] = 24
    response = client.get("/api/diagnostics/decomposition", params=params)
    assert response.status_code == 422
    assert "missing hours" in response.json()["detail"]


def test_quality_returns_spc_and_lof_flags_with_non_fault_label(client: TestClient) -> None:
    response = client.get(
        "/api/diagnostics/quality",
        params={"start": "2026-01-01", "end": "2026-01-21", "neighbors": 50},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["spc"]["summary"]["flags"] >= 1
    assert body["lof"]["summary"]["flags"] >= 1
    assert body["lof"]["summary"]["effectiveNeighbors"] == 50
    assert any(row["time"].startswith("2026-01-09T08:00") for row in body["lof"]["flaggedValues"])
    assert "not verified data faults" in body["metadata"]["interpretation"]

    weather = _weather()
    expected_spc, expected_spc_summary = diagnostics.spc_outliers_dct(
        weather.set_index("time")["temperature_2m (°C)"],
        keep_frac=0.01,
        k_sigma=3,
        interp_limit=6,
    )
    expected_lof, expected_neighbors = diagnostics.lof_precip_anomalies(
        weather,
        time_col="time",
        precip_col="precipitation (mm)",
        contamination=0.01,
        n_neighbors=50,
        roll_hours=24,
    )
    assert body["spc"]["summary"]["flags"] == expected_spc_summary.n_outliers
    assert body["lof"]["summary"]["effectiveNeighbors"] == expected_neighbors
    np.testing.assert_allclose(
        [row["satv"] for row in body["spc"]["values"]],
        expected_spc["satv"],
        rtol=1e-12,
        atol=1e-10,
    )
    np.testing.assert_allclose(
        [row["lof_score"] for row in body["lof"]["values"]],
        expected_lof["lof_score"],
        rtol=1e-12,
        atol=1e-10,
    )
    assert [row["time"] for row in body["spc"]["flaggedValues"]] == [
        pd.Timestamp(value).isoformat().replace("+00:00", "Z")
        for value in expected_spc.loc[expected_spc["is_outlier"], "time"]
    ]
    assert [row["time"] for row in body["lof"]["flaggedValues"]] == [
        pd.Timestamp(value).isoformat().replace("+00:00", "Z")
        for value in expected_lof.loc[expected_lof["is_anom"], "time"]
    ]


def test_quality_does_not_replace_missing_precipitation_with_zero(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        diagnostics, "weather_frame", lambda *args, **kwargs: _weather(missing_precip=True)
    )
    response = client.get(
        "/api/diagnostics/quality",
        params={"start": "2026-01-01", "end": "2026-01-21"},
    )
    assert response.status_code == 422
    assert "not treated as zero" in response.json()["detail"]


def test_chart_payload_is_capped_after_full_correlation_analysis(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(diagnostics, "energy_frame", lambda *args, **kwargs: _energy(2_000))
    monkeypatch.setattr(diagnostics, "weather_frame", lambda *args, **kwargs: _weather(2_000))
    response = client.get(
        "/api/diagnostics/correlation",
        params={"start": "2026-01-01", "end": "2026-03-26", "group": "solar"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["pairedHours"] == 2_000
    assert len(body["values"]) == diagnostics.MAX_LINE_POINTS
    assert body["metadata"]["chartPayloadLimited"] is True
