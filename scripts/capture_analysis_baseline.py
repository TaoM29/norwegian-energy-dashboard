#!/usr/bin/env python3
"""Capture deterministic Phase 0 numerical baselines from tracked fixture data."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep numerical-library threading explicit before importing NumPy/SciPy.
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np
import pandas as pd
import scipy
import sklearn
import statsmodels

from app_core.analysis.data_quality import lof_precip_anomalies, spc_outliers_dct
from app_core.analysis.sarimax_utils import (
    mae,
    mase,
    rmse,
    rolling_origin_backtest_sarimax,
)
from app_core.analysis.spectrogram import production_spectrogram
from app_core.analysis.stl import stl_decompose_elhub

ENERGY_PATH = ROOT / "data/elhub_prod_by_group_hour_2021.csv"
WEATHER_PATH = ROOT / "data/open-meteo-subset.csv"
DEFAULT_OUTPUT = ROOT / "docs/baseline/analysis"
REPEATS = 5
RTOL = 1e-10
ATOL = 1e-10

ENERGY_START = pd.Timestamp("2021-01-01T00:00:00Z")
ENERGY_END = pd.Timestamp("2021-02-01T00:00:00Z")
FORECAST_START = pd.Timestamp("2021-01-01T00:00:00Z")
FORECAST_END = pd.Timestamp("2021-07-01T00:00:00Z")

STL_PARAMS = {"area": "NO1", "group": "solar", "period": 24, "seasonal": 13, "trend": 365, "robust": True}
SPECTROGRAM_PARAMS = {"area": "NO1", "group": "solar", "window_len": 168, "overlap": 84, "freq_units": "cpd"}
SPC_PARAMS = {"keep_frac": 0.01, "k_sigma": 3.0, "interp_limit": 6}
LOF_PARAMS = {"contamination": 0.01, "n_neighbors": 60, "roll_hours": 24}
FORECAST_PARAMS = {
    "freq": "D",
    "horizon": 7,
    "step_size": 7,
    "folds": 3,
    "m_seasonal": 7,
    "order": (1, 0, 0),
    "seasonal_order": (1, 0, 0, 7),
    "eval_no_exog": True,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def frame_metadata(df: pd.DataFrame, time_col: str) -> dict[str, Any]:
    parsed = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    return {
        "rows": int(len(df)),
        "columns": list(df.columns),
        "raw_time_first": None if df.empty else str(df[time_col].iloc[0]),
        "raw_time_last": None if df.empty else str(df[time_col].iloc[-1]),
        "parsed_time_min": None if parsed.notna().sum() == 0 else parsed.min().isoformat(),
        "parsed_time_max": None if parsed.notna().sum() == 0 else parsed.max().isoformat(),
        "missing_by_column": {column: int(df[column].isna().sum()) for column in df.columns},
        "unparseable_time_rows": int(parsed.isna().sum()),
    }


def compare_arrays(expected: Any, actual: Any, label: str) -> float:
    left = np.asarray(expected)
    right = np.asarray(actual)
    if left.shape != right.shape:
        raise AssertionError(f"{label}: shape differs: {left.shape} != {right.shape}")
    if left.dtype.kind in "biufc" and right.dtype.kind in "biufc":
        if not np.allclose(left, right, rtol=RTOL, atol=ATOL, equal_nan=True):
            raise AssertionError(f"{label}: numerical values differ")
        finite = np.isfinite(left.astype(float)) & np.isfinite(right.astype(float))
        return float(np.max(np.abs(left.astype(float)[finite] - right.astype(float)[finite]))) if finite.any() else 0.0
    if not np.array_equal(left, right):
        raise AssertionError(f"{label}: values differ")
    return 0.0


def compare_frames(expected: pd.DataFrame, actual: pd.DataFrame, label: str) -> float:
    if list(expected.columns) != list(actual.columns):
        raise AssertionError(f"{label}: schema differs")
    if not expected.index.equals(actual.index):
        raise AssertionError(f"{label}: index/time axis differs")
    largest = 0.0
    for column in expected.columns:
        largest = max(largest, compare_arrays(expected[column].to_numpy(), actual[column].to_numpy(), f"{label}.{column}"))
    return largest


def timed_repeated(
    name: str,
    function: Callable[[], Any],
    compare: Callable[[Any, Any], float],
    timings: list[dict[str, Any]],
    agreements: dict[str, Any],
) -> Any:
    started = time.perf_counter_ns()
    reference = function()
    elapsed = (time.perf_counter_ns() - started) / 1_000_000
    timings.append({"method": name, "sample_kind": "first_call", "sample": 0, "elapsed_ms": elapsed})
    maximum_difference = 0.0
    for sample in range(1, REPEATS + 1):
        started = time.perf_counter_ns()
        observed = function()
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        timings.append({"method": name, "sample_kind": "repeat", "sample": sample, "elapsed_ms": elapsed})
        maximum_difference = max(maximum_difference, compare(reference, observed))
    agreements[name] = {
        "repeats_compared_to_first": REPEATS,
        "rtol": RTOL,
        "atol": ATOL,
        "schema_and_time_axes_exact": True,
        "max_abs_numeric_difference": maximum_difference,
    }
    return reference


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    timings: list[dict[str, Any]] = []
    agreements: dict[str, Any] = {}
    method_warnings: dict[str, list[str]] = {}

    def capture_warnings(method: str, function: Callable[[], Any]) -> Any:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = function()
        messages = method_warnings.setdefault(method, [])
        for warning in caught:
            message = f"{warning.category.__name__}: {warning.message}"
            if message not in messages:
                messages.append(message)
        return result

    def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
        return pd.read_csv(ENERGY_PATH), pd.read_csv(WEATHER_PATH)

    def compare_inputs(left: tuple[pd.DataFrame, pd.DataFrame], right: tuple[pd.DataFrame, pd.DataFrame]) -> float:
        compare_frames(left[0], right[0], "energy_input")
        compare_frames(left[1], right[1], "weather_input")
        return 0.0

    energy_raw, weather_raw = timed_repeated("load_tracked_csvs", load_inputs, compare_inputs, timings, agreements)

    energy = energy_raw.copy()
    energy["start_time"] = pd.to_datetime(energy["start_time"], errors="coerce", utc=True)
    selected_energy = energy.loc[
        (energy["price_area"] == "NO1")
        & (energy["production_group"] == "solar")
        & (energy["start_time"] >= ENERGY_START)
        & (energy["start_time"] < ENERGY_END)
    ].copy()

    weather = weather_raw.copy()
    # This matches the existing page parsing. Naive strings are labelled UTC; they
    # are not shifted, and no location/model provenance is inferred.
    weather["time"] = pd.to_datetime(weather["time"], errors="coerce", utc=True)
    weather = weather.sort_values("time").reset_index(drop=True)
    energy_times = pd.DatetimeIndex(selected_energy["start_time"].dropna().unique()).sort_values()
    weather_times = pd.DatetimeIndex(weather["time"].dropna().unique()).sort_values()

    def run_stl() -> pd.DataFrame:
        figures, details, _ = stl_decompose_elhub(selected_energy, **STL_PARAMS)
        result = pd.DataFrame({"time": figures["observed"].data[0].x})
        for component in ("observed", "seasonal", "trend", "resid"):
            result[component] = np.asarray(figures[component].data[0].y, dtype=float)
        result.attrs["details"] = details
        return result.set_index("time")

    stl_frame = timed_repeated("stl_decompose_elhub", run_stl, lambda a, b: compare_frames(a, b, "stl"), timings, agreements)

    def run_spectrogram() -> dict[str, np.ndarray]:
        _, frequency_cph, time_axis, magnitude = production_spectrogram(selected_energy, **SPECTROGRAM_PARAMS)
        return {
            "frequency_cph": np.asarray(frequency_cph, dtype=float),
            "frequency_cpd": np.asarray(frequency_cph, dtype=float) * 24.0,
            "time_ns_since_epoch": pd.DatetimeIndex(time_axis).as_unit("ns").asi8,
            "magnitude": np.asarray(magnitude, dtype=float),
        }

    def compare_spectrogram(left: dict[str, np.ndarray], right: dict[str, np.ndarray]) -> float:
        if left.keys() != right.keys():
            raise AssertionError("spectrogram schema differs")
        if not np.array_equal(left["time_ns_since_epoch"], right["time_ns_since_epoch"]):
            raise AssertionError("spectrogram time axis differs")
        return max(
            compare_arrays(left[key], right[key], f"spectrogram.{key}")
            for key in left
            if key != "time_ns_since_epoch"
        )

    spectrogram_values = timed_repeated("production_spectrogram", run_spectrogram, compare_spectrogram, timings, agreements)

    temperature = weather.set_index("time")["temperature_2m (°C)"].sort_index()

    def run_spc() -> tuple[pd.DataFrame, Any]:
        frame, summary = spc_outliers_dct(temperature, **SPC_PARAMS)
        return frame.set_index("time"), summary

    def compare_spc(left: tuple[pd.DataFrame, Any], right: tuple[pd.DataFrame, Any]) -> float:
        if left[1] != right[1]:
            raise AssertionError("SPC summary differs")
        return compare_frames(left[0], right[0], "spc")

    (spc_frame, spc_summary) = timed_repeated("spc_outliers_dct", run_spc, compare_spc, timings, agreements)

    def run_lof() -> tuple[pd.DataFrame, int]:
        frame, neighbors = capture_warnings("lof_precip_anomalies", lambda: lof_precip_anomalies(weather, **LOF_PARAMS))
        return frame.set_index("time"), neighbors

    def compare_lof(left: tuple[pd.DataFrame, int], right: tuple[pd.DataFrame, int]) -> float:
        if left[1] != right[1]:
            raise AssertionError("LOF effective neighbors differs")
        return compare_frames(left[0], right[0], "lof")

    (lof_frame, lof_neighbors) = timed_repeated("lof_precip_anomalies", run_lof, compare_lof, timings, agreements)

    snow_function_names = {
        "compute_Qupot",
        "_sector_index",
        "sector_transport",
        "tabler_transport",
        "compute_yearly",
        "average_sectors",
    }
    snow_source = ROOT / "pages/21_Snow_Drift.py"
    snow_tree = ast.parse(snow_source.read_text(encoding="utf-8"), filename=str(snow_source))
    snow_nodes = [node for node in snow_tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in snow_function_names]
    if {node.name for node in snow_nodes} != snow_function_names:
        raise RuntimeError("Could not extract all unchanged Snow Drift function definitions")
    snow_namespace: dict[str, Any] = {"np": np, "pd": pd}
    exec(compile(ast.Module(body=snow_nodes, type_ignores=[]), str(snow_source), "exec"), snow_namespace)
    snow_input = weather.copy()
    snow_input["season"] = snow_input["time"].dt.year.where(snow_input["time"].dt.month >= 7, snow_input["time"].dt.year - 1)
    snow_params = {"T": 3000.0, "F": 30000.0, "theta": 0.5}

    def run_snow_drift() -> tuple[pd.DataFrame, np.ndarray]:
        yearly = snow_namespace["compute_yearly"](snow_input, **snow_params)
        sectors = np.asarray(snow_namespace["average_sectors"](snow_input), dtype=float)
        return yearly, sectors

    def compare_snow(left: tuple[pd.DataFrame, np.ndarray], right: tuple[pd.DataFrame, np.ndarray]) -> float:
        return max(compare_frames(left[0], right[0], "snow_drift.yearly"), compare_arrays(left[1], right[1], "snow_drift.sectors"))

    snow_yearly, snow_sectors = timed_repeated("snow_drift_page_functions", run_snow_drift, compare_snow, timings, agreements)

    forecast_hourly = energy.loc[
        (energy["price_area"] == "NO1")
        & (energy["production_group"] == "solar")
        & (energy["start_time"] >= FORECAST_START)
        & (energy["start_time"] < FORECAST_END)
    ].set_index("start_time")["quantity_kwh"].sort_index()
    forecast_daily = forecast_hourly.resample("D").sum()

    def run_backtest(series: pd.Series = forecast_daily) -> tuple[pd.DataFrame, dict[str, Any]]:
        return capture_warnings(
            "rolling_origin_backtest_sarimax",
            lambda: rolling_origin_backtest_sarimax(series, None, **FORECAST_PARAMS),
        )

    def forecast_frame(result: tuple[pd.DataFrame, dict[str, Any]]) -> pd.DataFrame:
        summary, artifacts = result
        last = pd.concat(
            [artifacts["y_test"].rename("actual"), artifacts["baseline"].rename("seasonal_naive"), artifacts["sarimax_no_exog"].rename("sarimax_no_exog")],
            axis=1,
        )
        flat_summary = summary.set_index("model")
        return pd.concat({"summary": flat_summary.stack(), "last": last.stack()}).to_frame("value")

    def compare_backtest(left: tuple[pd.DataFrame, dict[str, Any]], right: tuple[pd.DataFrame, dict[str, Any]]) -> float:
        return compare_frames(forecast_frame(left), forecast_frame(right), "backtest")

    backtest_summary, backtest_artifacts = timed_repeated("rolling_origin_backtest_sarimax", run_backtest, compare_backtest, timings, agreements)

    # Recover every matched fold's forecasts through the unchanged helper by
    # truncating the same series at each original fold's test end.
    horizon = int(FORECAST_PARAMS["horizon"])
    last_cutoff = len(forecast_daily) - horizon - 1
    cut_positions = [last_cutoff - int(FORECAST_PARAMS["step_size"]) * k for k in range(int(FORECAST_PARAMS["folds"]))][::-1]
    fold_predictions: list[pd.DataFrame] = []
    fold_metrics: list[dict[str, Any]] = []
    for fold_number, cutoff in enumerate(cut_positions, start=1):
        fold_series = forecast_daily.iloc[: cutoff + 1 + horizon]
        single_params = dict(FORECAST_PARAMS)
        single_params["folds"] = 1
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, fold_artifacts = rolling_origin_backtest_sarimax(fold_series, None, **single_params)
        actual = fold_artifacts["y_test"]
        baseline = fold_artifacts["baseline"]
        sarimax = fold_artifacts["sarimax_no_exog"]
        fold_frame = pd.concat(
            [actual.rename("actual"), baseline.rename("seasonal_naive"), sarimax.rename("sarimax_no_exog")], axis=1
        ).reset_index(names="time")
        fold_frame.insert(0, "fold", fold_number)
        fold_frame.insert(1, "cutoff_position", cutoff)
        fold_frame.insert(2, "train_end", forecast_daily.index[cutoff])
        fold_predictions.append(fold_frame)
        for model, prediction in (("Seasonal naive", baseline), ("SARIMAX (no exog)", sarimax)):
            fold_metrics.append(
                {
                    "fold": fold_number,
                    "cutoff_position": cutoff,
                    "train_end": forecast_daily.index[cutoff],
                    "test_start": actual.index[0],
                    "test_end": actual.index[-1],
                    "model": model,
                    "MAE": mae(actual, prediction),
                    "RMSE": rmse(actual, prediction),
                    "MASE": mase(actual, prediction, forecast_daily.iloc[: cutoff + 1], int(FORECAST_PARAMS["m_seasonal"])),
                }
            )
    fold_predictions_frame = pd.concat(fold_predictions, ignore_index=True)
    fold_metrics_frame = pd.DataFrame(fold_metrics)

    recomputed_summary = fold_metrics_frame.groupby("model")[["MAE", "RMSE", "MASE"]].agg(["mean", "std"])
    for model in backtest_summary["model"]:
        for metric in ("MAE", "RMSE", "MASE"):
            for statistic in ("mean", "std"):
                expected = float(backtest_summary.loc[backtest_summary["model"] == model, f"{metric}_{statistic}"].iloc[0])
                observed = float(recomputed_summary.loc[model, (metric, statistic)])
                if not np.isclose(expected, observed, rtol=RTOL, atol=ATOL):
                    raise AssertionError(f"forecast fold reconstruction differs for {model} {metric}_{statistic}")

    stl_frame.reset_index().to_csv(output / "stl_components.csv", index=False, float_format="%.17g")
    np.savez(output / "spectrogram.npz", **spectrogram_values)
    spc_frame.reset_index().to_csv(output / "spc_temperature.csv", index=False, float_format="%.17g")
    lof_frame.reset_index().to_csv(output / "lof_precipitation.csv", index=False, float_format="%.17g")
    snow_yearly.to_csv(output / "snow_drift_partial_seasons.csv", index=False, float_format="%.17g")
    pd.DataFrame({"sector_index": np.arange(16), "average_transport_kg_per_m": snow_sectors}).to_csv(
        output / "snow_drift_sectors.csv", index=False, float_format="%.17g"
    )
    backtest_summary.to_csv(output / "forecast_summary.csv", index=False, float_format="%.17g")
    fold_metrics_frame.to_csv(output / "forecast_fold_metrics.csv", index=False, float_format="%.17g")
    fold_predictions_frame.to_csv(output / "forecast_fold_predictions.csv", index=False, float_format="%.17g")
    pd.DataFrame(timings).to_csv(output / "timings.csv", index=False, float_format="%.9f")

    deterministic_files = [
        "stl_components.csv",
        "spectrogram.npz",
        "spc_temperature.csv",
        "lof_precipitation.csv",
        "snow_drift_partial_seasons.csv",
        "snow_drift_sectors.csv",
        "forecast_summary.csv",
        "forecast_fold_metrics.csv",
        "forecast_fold_predictions.csv",
    ]
    source_files = [
        "app_core/analysis/stl.py",
        "app_core/analysis/spectrogram.py",
        "app_core/analysis/data_quality.py",
        "app_core/analysis/sarimax_utils.py",
        "pages/21_Snow_Drift.py",
        "scripts/capture_analysis_baseline.py",
    ]

    summary = {
        "inputs": {
            "energy": {"path": str(ENERGY_PATH.relative_to(ROOT)), "sha256": sha256(ENERGY_PATH), **frame_metadata(energy_raw, "start_time")},
            "weather": {"path": str(WEATHER_PATH.relative_to(ROOT)), "sha256": sha256(WEATHER_PATH), **frame_metadata(weather_raw, "time")},
        },
        "selections": {
            "energy_analysis": {
                "area": "NO1",
                "production_group": "solar",
                "half_open_interval_utc": [ENERGY_START.isoformat(), ENERGY_END.isoformat()],
                "rows": int(len(selected_energy)),
                "time_min": selected_energy["start_time"].min().isoformat(),
                "time_max": selected_energy["start_time"].max().isoformat(),
                "missing_quantity_kwh": int(selected_energy["quantity_kwh"].isna().sum()),
                "duplicate_timestamps": int(selected_energy["start_time"].duplicated().sum()),
                "missing_hourly_grid_slots": int(len(pd.date_range(ENERGY_START, ENERGY_END, freq="h", inclusive="left").difference(energy_times))),
            },
            "weather_analysis": {
                "rows": int(len(weather)),
                "parsed_time_min": weather["time"].min().isoformat(),
                "parsed_time_max": weather["time"].max().isoformat(),
                "duplicate_timestamps": int(weather["time"].duplicated().sum()),
                "missing_hourly_grid_slots_within_covered_span": int(
                    len(pd.date_range(weather_times.min(), weather_times.max(), freq="h").difference(weather_times))
                ),
                "timestamp_treatment": "Naive CSV strings parsed with utc=True, matching the existing page; no time shift applied.",
                "provenance_constraint": "The tracked file does not identify location, weather model, or authoritative units provenance; none is inferred here.",
            },
            "forecast": {
                "area": "NO1",
                "production_group": "solar",
                "half_open_hourly_interval_utc": [FORECAST_START.isoformat(), FORECAST_END.isoformat()],
                "hourly_rows": int(len(forecast_hourly)),
                "daily_rows": int(len(forecast_daily)),
                "daily_time_min": forecast_daily.index.min().isoformat(),
                "daily_time_max": forecast_daily.index.max().isoformat(),
                "missing_daily_values": int(forecast_daily.isna().sum()),
                "duplicate_hourly_timestamps": int(forecast_hourly.index.duplicated().sum()),
                "missing_hourly_grid_slots": int(
                    len(pd.date_range(FORECAST_START, FORECAST_END, freq="h", inclusive="left").difference(forecast_hourly.index))
                ),
                "exogenous_data": None,
                "reason_no_exogenous_data": "Tracked weather and energy fixtures cover different years and were not joined.",
            },
        },
        "parameters": {
            "stl": STL_PARAMS,
            "spectrogram": SPECTROGRAM_PARAMS,
            "spc": SPC_PARAMS,
            "lof": LOF_PARAMS,
            "snow_drift": {
                **snow_params,
                "function_loading": "Definitions extracted unchanged from pages/21_Snow_Drift.py with Python ast and executed without page UI/data-loading code.",
                "functions": sorted(snow_function_names),
            },
            "forecast": {key: list(value) if isinstance(value, tuple) else value for key, value in FORECAST_PARAMS.items()},
        },
        "compact_results": {
            "stl": {
                "n_points": int(len(stl_frame)),
                "resid_mean": float(stl_frame["resid"].mean()),
                "resid_std_sample": float(stl_frame["resid"].std()),
                "resid_max_abs": float(stl_frame["resid"].abs().max()),
            },
            "spectrogram": {
                "frequency_bins": int(len(spectrogram_values["frequency_cph"])),
                "time_bins": int(len(spectrogram_values["time_ns_since_epoch"])),
                "magnitude_shape": list(spectrogram_values["magnitude"].shape),
                "magnitude_max": float(spectrogram_values["magnitude"].max()),
            },
            "spc": {
                "n_points": int(spc_summary.n_points),
                "n_outliers": int(spc_summary.n_outliers),
                "sigma_robust": float(spc_summary.sigma_robust),
                "keep_k": int(spc_summary.keep_k),
                "max_abs_satv": float(spc_summary.max_abs_satv),
            },
            "lof": {
                "n_points": int(len(lof_frame)),
                "n_anomalies": int(lof_frame["is_anom"].sum()),
                "effective_n_neighbors": int(lof_neighbors),
                "max_lof_score": float(lof_frame["lof_score"].max()),
            },
            "snow_drift": {
                "season_rows": int(len(snow_yearly)),
                "seasons": snow_yearly["season"].tolist(),
                "partial_input": True,
                "qt_kg_per_m": [float(value) for value in snow_yearly["Qt (kg/m)"].tolist()],
                "sector_sum_kg_per_m": float(snow_sectors.sum()),
            },
            "forecast_summary": backtest_summary.to_dict(orient="records"),
            "forecast_fold_count": int(len(cut_positions)),
            "forecast_test_points_per_model": int(len(fold_predictions_frame)),
        },
        "repeat_agreement": agreements,
        "captured_method_warnings": method_warnings,
        "source_sha256": {path: sha256(ROOT / path) for path in source_files},
        "deterministic_artifact_sha256": {name: sha256(output / name) for name in deterministic_files},
    }
    json_dump(output / "summary.json", summary)

    environment = {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "scikit-learn": sklearn.__version__,
            "statsmodels": statsmodels.__version__,
        },
        "timing_method": "time.perf_counter_ns around each helper call in one sequential process; excludes input preparation and artifact serialization unless the method is load_tracked_csvs",
        "cache_state": "first_call is the first invocation after imports/input preparation; repeats 1-5 are immediate warm-process calls; OS filesystem cache was not flushed",
        "thread_environment": {name: os.environ[name] for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
        "timings_are_not": ["browser latency", "network latency", "live source latency", "an operational forecast benchmark"],
    }
    json_dump(output / "environment.json", environment)
    print(json.dumps(summary["compact_results"], indent=2))


if __name__ == "__main__":
    main()
