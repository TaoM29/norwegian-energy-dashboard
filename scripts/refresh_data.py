#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.ingestion import DEFAULT_DATABASE, EnergyStore, RefreshService


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Build or refresh the public Elhub energy snapshot."
    )
    result.add_argument("mode", choices=("backfill", "refresh"))
    result.add_argument(
        "--database", type=Path, default=DEFAULT_DATABASE, help="SQLite snapshot path"
    )
    result.add_argument(
        "--days", type=int, default=7, help="recent days to reconcile during refresh"
    )
    result.add_argument("--skip-weather", action="store_true", help="Refresh energy only")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    service = RefreshService(EnergyStore(args.database))
    if args.mode == "backfill":
        count = service.backfill()
    else:
        count = service.refresh(days=args.days)
    if not args.skip_weather:
        from app_core.loaders.weather import AREA_COORDS, load_openmeteo_era5
        current_year = datetime.now(timezone.utc).year
        years = range(2021, current_year + 1) if args.mode == "backfill" else [current_year - 1, current_year]
        for year in years:
            for area in AREA_COORDS:
                frame = load_openmeteo_era5(area, year, force_refresh=True)
                status = frame.attrs.get("cache_status")
                logging.info("Weather %s %s: %d hours (%s)", area, year, len(frame), status)
                if frame.empty or status == "stale_snapshot":
                    raise RuntimeError(f"Weather refresh failed for {area}/{year}; previous snapshot retained")
    logging.info("Refresh complete: %d energy rows fetched", count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
