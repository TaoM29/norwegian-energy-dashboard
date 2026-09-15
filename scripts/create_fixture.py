#!/usr/bin/env python3
"""Create deterministic, explicitly synthetic data for offline dashboard use."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.analysis.forecast_evaluation import evaluate_frames, validate_evaluation_config  # noqa: E402
from app_core.ingestion.models import AREAS, BASE_GROUPS  # noqa: E402
from app_core.ingestion.store import EnergyStore  # noqa: E402
from app_core.loaders import weather  # noqa: E402
from backend.forecast_jobs import ForecastStore, _atomic_json  # noqa: E402


DEFAULT_OUTPUT = ROOT / "data" / "fixture"
ENERGY_START = pd.Timestamp("2025-01-01T00:00:00Z")
ENERGY_END = pd.Timestamp("2026-01-01T00:00:00Z")
POINT_YEARS = tuple(range(2021, 2027))
POINT_COORDINATE = (61.5, 9.0)
CREATED_AT = "2026-01-01T00:00:00Z"
SYNTHETIC_SOURCE = "Synthetic offline fixture — not observations"
FIXTURE_RESULT_ID = "fixture-seasonal-naive-2025"

DEFAULT_FORECAST_CONFIG: dict[str, Any] = {
    "areas": list(AREAS),
    "models": ["seasonal_naive"],
    "horizon_hours": 24,
    "train_window_days": 120,
    "validation_origins": ["2025-09-01T00:00:00Z", "2025-09-15T00:00:00Z"],
    "calibration_origins": ["2025-10-01T00:00:00Z", "2025-10-15T00:00:00Z"],
    "holdout_origins": ["2025-11-01T00:00:00Z", "2025-12-01T00:00:00Z"],
    "weather_mode": "historical_only",
    "energy_publication_lag_hours": 48,
    "weather_publication_lag_hours": 120,
    "interval_coverage": 0.8,
    "random_seed": 320,
}


def _utc(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _weather_frame(index: pd.DatetimeIndex, location_offset: float) -> pd.DataFrame:
    """Return smooth deterministic weather with recurring rain and snow events."""
    elapsed = (index - pd.Timestamp("2021-01-01T00:00:00Z")) / pd.Timedelta(hours=1)
    hour = index.hour.to_numpy(dtype=float)
    day = index.dayofyear.to_numpy(dtype=float)
    year_length = np.where(index.is_leap_year, 366.0, 365.0)
    annual = np.cos(2 * np.pi * (day - 205) / year_length)
    daily = np.sin(2 * np.pi * (hour - 8) / 24)
    storm = np.maximum(0, np.sin(2 * np.pi * (elapsed + 11 * location_offset) / (24 * 17)))
    precipitation = np.where(storm > 0.82, (storm - 0.82) * 18, 0.0)
    wind_speed = 5.2 + 1.4 * np.sin(2 * np.pi * elapsed / (24 * 6.5) + location_offset) + 1.8 * storm
    return pd.DataFrame(
        {
            "time": index,
            "temperature_2m (°C)": 5.5 + 10.5 * annual + 2.0 * daily - 0.45 * location_offset,
            "precipitation (mm)": precipitation,
            "wind_speed_10m (m/s)": wind_speed,
            "wind_gusts_10m (m/s)": wind_speed + 2.2 + 0.8 * storm,
            "wind_direction_10m (°)": np.mod(205 + elapsed * 3.7 + location_offset * 29, 360),
        }
    )


def _energy_rows(index: pd.DatetimeIndex) -> Iterator[dict[str, Any]]:
    hour = index.hour.to_numpy(dtype=float)
    day = index.dayofyear.to_numpy(dtype=float)
    annual = np.cos(2 * np.pi * (day - 15) / 365.0)
    daytime = np.maximum(0, np.sin(np.pi * (hour - 6) / 12))
    weekly = np.cos(2 * np.pi * np.arange(len(index), dtype=float) / (24 * 7))
    retrieved = CREATED_AT

    for area_number, area in enumerate(AREAS, start=1):
        scale = 0.72 + area_number * 0.13
        consumption_total = scale * (
            690_000 + 155_000 * annual + 72_000 * np.cos(2 * np.pi * (hour - 18) / 24) + 28_000 * weekly
        )
        production_total = scale * (
            760_000 + 110_000 * np.sin(2 * np.pi * (day + 45) / 365) + 42_000 * weekly
        )
        production = {
            "hydro": production_total * (0.60 + 0.05 * annual),
            "other": production_total * 0.035,
            "solar": production_total * daytime * np.maximum(0.08, 0.15 - 0.10 * annual),
            "thermal": production_total * (0.075 + 0.018 * annual),
            "wind": production_total * (0.20 + 0.055 * np.sin(2 * np.pi * np.arange(len(index)) / (24 * 9) + area_number)),
        }
        consumption_shares = {
            "cabin": 0.055,
            "household": 0.49,
            "primary": 0.075,
            "secondary": 0.17,
            "tertiary": 0.21,
        }
        for position, timestamp in enumerate(index):
            timestamp_text = timestamp.isoformat().replace("+00:00", "Z")
            for group in BASE_GROUPS["production"]:
                yield {
                    "timestamp": timestamp_text,
                    "area": area,
                    "kind": "production",
                    "group": group,
                    "value": round(max(0.0, float(production[group][position])), 6),
                    "unit": "kWh",
                    "source": SYNTHETIC_SOURCE,
                    "retrieved_at": retrieved,
                    "revision": None,
                    "quality": "ok",
                }
            for group in BASE_GROUPS["consumption"]:
                yield {
                    "timestamp": timestamp_text,
                    "area": area,
                    "kind": "consumption",
                    "group": group,
                    "value": round(float(consumption_total[position] * consumption_shares[group]), 6),
                    "unit": "kWh",
                    "source": SYNTHETIC_SOURCE,
                    "retrieved_at": retrieved,
                    "revision": None,
                    "quality": "ok",
                }


def _write_energy(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> int:
    store = EnergyStore(path)
    index = pd.date_range(start, end, freq="h", inclusive="left")
    batch: list[dict[str, Any]] = []
    total = 0
    for row in _energy_rows(index):
        batch.append(row)
        if len(batch) >= 10_000:
            total += store.upsert(batch)
            batch.clear()
    if batch:
        total += store.upsert(batch)
    store.rebuild_summaries()
    store.record_run(
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        mode="fixture",
        status="success",
        fetched_rows=total,
        message="Deterministic synthetic fixture; not fetched observations.",
    )
    return total


@contextmanager
def _snapshot_directory(path: Path) -> Iterator[None]:
    previous = os.environ.get(weather.WEATHER_SNAPSHOT_DIR_ENV)
    os.environ[weather.WEATHER_SNAPSHOT_DIR_ENV] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(weather.WEATHER_SNAPSHOT_DIR_ENV, None)
        else:
            os.environ[weather.WEATHER_SNAPSHOT_DIR_ENV] = previous


def _write_weather_year(
    *, location: str, latitude: float, longitude: float, year: int, location_offset: float
) -> tuple[Path, pd.DataFrame]:
    index = pd.date_range(f"{year}-01-01T00:00:00Z", f"{year + 1}-01-01T00:00:00Z", freq="h", inclusive="left")
    frame = weather._validate_frame(_weather_frame(index, location_offset))
    identity = weather._identity(location, latitude, longitude, year)
    final = frame["time"].iloc[-1]
    metadata = {
        **identity,
        "source": SYNTHETIC_SOURCE,
        "synthetic": True,
        "data_mode": "fixture",
        "method": "Deterministic periodic functions; no observed values or network requests.",
        "units": {weather.OUTPUT_COLUMNS[name]: weather.EXPECTED_UNITS[name] for name in weather.HOURLY_VARIABLES},
        "requested_start": index[0].isoformat(),
        "requested_end": (final + pd.Timedelta(hours=1)).isoformat(),
        "available_start": index[0].isoformat(),
        "available_end": (final + pd.Timedelta(hours=1)).isoformat(),
        "retrieved_at": CREATED_AT,
        "cache_status": "fixture",
        "coverage_complete": True,
        "source_coverage_complete": True,
        "publication_lag_days": 0,
        "variable_last_timestamp": {name: final.isoformat() for name in weather.HOURLY_VARIABLES},
    }
    path = weather._snapshot_path(identity)
    weather._write_snapshot(path, identity, metadata, frame)
    return path, frame


def _write_weather(path: Path, point_years: Sequence[int]) -> tuple[int, pd.DataFrame]:
    area_frames: list[pd.DataFrame] = []
    files = 0
    with _snapshot_directory(path):
        for offset, area in enumerate(AREAS):
            latitude, longitude = weather.AREA_COORDS[area]
            _, frame = _write_weather_year(
                location=area,
                latitude=latitude,
                longitude=longitude,
                year=2025,
                location_offset=float(offset),
            )
            frame = frame.copy()
            frame["area"] = area
            area_frames.append(frame)
            files += 1

        latitude, longitude = POINT_COORDINATE
        location = f"snow-drift:{latitude:.6f},{longitude:.6f}"
        for year in point_years:
            _write_weather_year(
                location=location,
                latitude=latitude,
                longitude=longitude,
                year=int(year),
                location_offset=2.5,
            )
            files += 1
    return files, pd.concat(area_frames, ignore_index=True)


def _write_forecast(
    root: Path,
    energy_path: Path,
    weather_frame: pd.DataFrame,
    config: Mapping[str, Any],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> int:
    normalized = validate_evaluation_config(config)
    energy_rows = EnergyStore(energy_path).query(
        start=start.to_pydatetime(),
        end=end.to_pydatetime(),
        areas=list(normalized["areas"]),
        kinds=["consumption"],
        groups=["household"],
    )
    energy_frame = pd.DataFrame(energy_rows)
    energy_frame.attrs["provenance"] = {
        "source": SYNTHETIC_SOURCE,
        "synthetic": True,
        "dataMode": "fixture",
    }
    weather_frame.attrs["provenance"] = {
        "source": SYNTHETIC_SOURCE,
        "synthetic": True,
        "dataMode": "fixture",
    }
    payload = evaluate_frames(energy_frame, weather_frame, normalized)
    payload["title"] = "Synthetic seasonal-naive fixture"
    payload["metadata"].update(
        {
            "sourceLabel": SYNTHETIC_SOURCE,
            "dataMode": "fixture",
            "synthetic": True,
            "fixtureNotice": "Generated values are for product demonstration and testing only.",
        }
    )
    result = {
        **payload,
        "id": FIXTURE_RESULT_ID,
        "kind": "evaluation",
        "createdAt": CREATED_AT,
        "metadata": {
            **payload["metadata"],
            "generatedAt": CREATED_AT,
            "runtime": {"durationSeconds": 0},
            "revision": {"commit": None, "dirty": None, "sourceFingerprint": "deterministic-fixture-v1"},
            "environment": {"generator": "scripts/create_fixture.py"},
        },
    }
    store = ForecastStore(root)
    store.save_result(result)
    manifest = json.loads(store.manifest_path.read_text(encoding="utf-8"))
    manifest["updatedAt"] = CREATED_AT
    _atomic_json(store.manifest_path, manifest)
    return len(result.get("predictions", []))


def _replace_output(staging: Path, output: Path, force: bool) -> None:
    if output.exists():
        marker = output / "fixture-manifest.json"
        if not force:
            raise FileExistsError(f"{output} already exists; pass --force to replace the generated fixture.")
        if not marker.is_file():
            raise ValueError(f"Refusing to replace {output}: fixture-manifest.json is missing.")
        shutil.rmtree(output)
    os.replace(staging, output)


def create_fixture(
    output: Path = DEFAULT_OUTPUT,
    *,
    force: bool = False,
    energy_start: str | pd.Timestamp = ENERGY_START,
    energy_end: str | pd.Timestamp = ENERGY_END,
    point_years: Sequence[int] = POINT_YEARS,
    forecast_config: Mapping[str, Any] = DEFAULT_FORECAST_CONFIG,
) -> dict[str, Any]:
    output = Path(output).expanduser().resolve()
    start, end = _utc(energy_start), _utc(energy_end)
    if start >= end:
        raise ValueError("energy_start must precede energy_end")
    if start.year != 2025 or (end - pd.Timedelta(hours=1)).year != 2025:
        raise ValueError("The offline fixture energy interval must stay within 2025.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        shutil.copyfile(ROOT / "data" / "file.geojson", staging / "file.geojson")
        energy_path = staging / "energy.sqlite"
        energy_count = _write_energy(energy_path, start, end)
        weather_files, area_weather = _write_weather(staging / "weather", point_years)
        predictions = _write_forecast(
            staging / "forecasts", energy_path, area_weather, forecast_config, start, end
        )
        manifest = {
            "schemaVersion": 1,
            "dataMode": "fixture",
            "synthetic": True,
            "source": SYNTHETIC_SOURCE,
            "generatedAt": CREATED_AT,
            "energy": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "areas": list(AREAS),
                "groupsPerKind": {kind: list(groups) for kind, groups in BASE_GROUPS.items()},
                "rows": energy_count,
            },
            "weather": {
                "areaYear": 2025,
                "pointCoordinate": {"latitude": POINT_COORDINATE[0], "longitude": POINT_COORDINATE[1]},
                "pointYears": [int(year) for year in point_years],
                "snapshotFiles": weather_files,
            },
            "forecast": {"resultId": FIXTURE_RESULT_ID, "predictions": predictions},
        }
        (staging / "fixture-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _replace_output(staging, output, force)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create deterministic synthetic 2025 energy/weather data and a prepared forecast result."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Replace an existing generated fixture directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = create_fixture(args.output, force=args.force)
    output = args.output.expanduser().resolve()
    print(
        json.dumps(
            {
                "fixture": manifest,
                "environment": {
                    "ENERGY_DATABASE": str(output / "energy.sqlite"),
                    "WEATHER_SNAPSHOT_DIR": str(output / "weather"),
                    "FORECAST_ARTIFACT_ROOT": str(output / "forecasts"),
                    "ENERGY_DATA_MODE": "fixture",
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
