#!/usr/bin/env python3
"""Run and publish the reproducible five-area forecast benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.analysis.forecast_evaluation import (  # noqa: E402
    run_evaluation,
    validate_evaluation_config,
)
from backend.forecast_jobs import (  # noqa: E402
    ForecastStore,
    capture_execution_context,
    publish_result_artifact,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate matched 24-hour household-demand forecasts from published local "
            "snapshots and write an immutable JSON result artifact."
        )
    )
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--result-id", default=None)
    parser.add_argument("--areas", nargs="+", default=["NO1", "NO2", "NO3", "NO4", "NO5"])
    parser.add_argument(
        "--models",
        nargs="+",
        default=["seasonal_naive", "ridge", "gradient_boosting", "sarimax"],
    )
    parser.add_argument("--horizon-hours", type=int, default=24)
    parser.add_argument("--train-window-days", type=int, default=120)
    parser.add_argument("--validation-origin", action="append", dest="validation_origins")
    parser.add_argument("--calibration-origin", action="append", dest="calibration_origins")
    parser.add_argument("--holdout-origin", action="append", dest="holdout_origins")
    parser.add_argument(
        "--weather-mode",
        choices=["historical_only", "realized_future_upper_bound"],
        default="historical_only",
    )
    parser.add_argument("--energy-publication-lag-hours", type=int, default=48)
    parser.add_argument("--weather-publication-lag-hours", type=int, default=120)
    parser.add_argument("--interval-coverage", type=float, default=0.8)
    parser.add_argument("--random-seed", type=int, default=20250915)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    requested = {
        "areas": args.areas,
        "models": args.models,
        "horizon_hours": args.horizon_hours,
        "train_window_days": args.train_window_days,
        "weather_mode": args.weather_mode,
        "energy_publication_lag_hours": args.energy_publication_lag_hours,
        "weather_publication_lag_hours": args.weather_publication_lag_hours,
        "interval_coverage": args.interval_coverage,
        "random_seed": args.random_seed,
    }
    # The engine owns the benchmark split defaults. Explicit CLI origins replace
    # the corresponding split without duplicating scientific constants here.
    for key in ("validation_origins", "calibration_origins", "holdout_origins"):
        value = getattr(args, key)
        if value:
            requested[key] = value
    config = validate_evaluation_config(requested)
    execution_context = capture_execution_context()

    def progress(fraction: float, message: str) -> None:
        if not args.quiet:
            print(f"[{fraction:6.1%}] {message}", file=sys.stderr, flush=True)

    started = time.monotonic()
    payload = run_evaluation(config, progress=progress, cancelled=lambda: False)
    result = publish_result_artifact(
        ForecastStore(args.artifact_root),
        kind="evaluation",
        config=config,
        payload=payload,
        duration_seconds=time.monotonic() - started,
        result_id=args.result_id,
        execution_context=execution_context,
    )
    output_path = ForecastStore(args.artifact_root).results_dir / f"{result['id']}.json"
    print(
        json.dumps(
            {
                "id": result["id"],
                "path": str(output_path),
                "areas": config["areas"],
                "models": config["models"],
                "validationOrigins": config["validation_origins"],
                "calibrationOrigins": config["calibration_origins"],
                "holdoutOrigins": config["holdout_origins"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
