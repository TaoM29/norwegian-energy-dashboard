#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.ingestion import DEFAULT_DATABASE, EnergyStore, RefreshService


def _nonnegative_days(value: str) -> int:
    days = int(value)
    if days < 0:
        raise argparse.ArgumentTypeError("weather grace days must be nonnegative")
    return days


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
    result.add_argument(
        "--weather-grace-days", type=_nonnegative_days, default=0,
        help="During refresh, retain validated weather within this many days of expected coverage and retrieval (default: strict)",
    )
    result.add_argument("--report", type=Path, help="Refresh report path (default: beside the database)")
    return result


def _weather_grace_error(frame, year: int, expected_end: datetime, now: datetime, grace_days: int) -> str | None:
    """Explain why a previously validated snapshot cannot be retained for this run."""
    if grace_days == 0:
        return "weather grace is disabled"
    if frame.empty or frame.attrs.get("cache_status") != "stale_snapshot":
        return "no validated snapshot to retain"
    if year != (expected_end - timedelta(microseconds=1)).year:
        return "historical weather must refresh successfully"
    provenance = frame.attrs.get("provenance", {})
    try:
        start = datetime.fromisoformat(provenance["available_start"])
        end = datetime.fromisoformat(provenance["available_end"])
        retrieved = datetime.fromisoformat(provenance["retrieved_at"])
        if any(value.utcoffset() != timedelta(0) for value in (start, end, retrieved)):
            return "snapshot timestamps must be UTC"
        annual_start = datetime(year, 1, 1, tzinfo=timezone.utc)
        if start != annual_start or start != frame["time"].iloc[0] or end != frame["time"].iloc[-1] + timedelta(hours=1):
            return "snapshot coverage does not match the validated annual series"
        if end <= start or end > expected_end or retrieved > now:
            return "snapshot timestamps are outside expected source coverage"
        grace = timedelta(days=grace_days)
        if expected_end - end > grace:
            return f"weather coverage is more than {grace_days} days behind the expected source boundary"
        if now - retrieved > grace:
            return f"last successful weather retrieval is more than {grace_days} days old"
    except (KeyError, TypeError, ValueError, IndexError):
        return "snapshot freshness metadata is missing or invalid"
    return None


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = [f"## Public data refresh: {report['state']}", "",
                 f"Energy rows fetched: {report['energy_rows']}. Weather grace: {report['weather_grace_days']} days.", ""]
        if report["state"] == "degraded":
            lines += ["Some weather snapshots were retained after source failures. Their coverage and retrieval times are unchanged.", ""]
        for item in report["weather"]:
            detail = (
                f"{item['area']}/{item['year']}: {item['outcome']}; "
                f"exclusive coverage end {item['available_end']}; retrieved {item['retrieved_at']}"
            )
            if item.get("error"):
                detail += f"; {item['error']}"
            if item.get("reason"):
                detail += f"; {item['reason']}"
            lines.append(f"- {html.escape(detail)}")
        if report.get("error"):
            lines += ["", html.escape(report["error"])]
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    now = datetime.now(timezone.utc)
    report_path = args.report or args.database.parent / "refresh-report.json"
    report = {
        "state": "succeeded", "attempted_at": now.isoformat(), "mode": args.mode,
        "weather_grace_days": args.weather_grace_days, "energy_rows": 0, "weather": [],
    }
    try:
        service = RefreshService(EnergyStore(args.database))
        count = service.backfill() if args.mode == "backfill" else service.refresh(days=args.days)
    except Exception as error:
        report.update(state="failed", error=f"Energy refresh failed: {error}")
        _write_report(report_path, report)
        raise
    report["energy_rows"] = count
    failures = []
    if not args.skip_weather:
        from app_core.loaders.weather import AREA_COORDS, era5_available_end, load_openmeteo_era5
        current_year = now.year
        expected_end = era5_available_end(now).to_pydatetime()
        source_year = (expected_end - timedelta(microseconds=1)).year
        years = range(2021, current_year + 1) if args.mode == "backfill" else [current_year - 1, current_year]
        for year in years:
            if datetime(year, 1, 1, tzinfo=timezone.utc) >= expected_end:
                continue  # At New Year, ERA5 may only cover the previous calendar year.
            for area in AREA_COORDS:
                item = {
                    "area": area, "year": year, "status": "unavailable", "outcome": "failed",
                    "available_end": None, "retrieved_at": None,
                    "expected_end": min(expected_end, datetime(year + 1, 1, 1, tzinfo=timezone.utc)).isoformat(),
                }
                report["weather"].append(item)
                try:
                    frame = load_openmeteo_era5(area, year, force_refresh=year == source_year)
                except Exception as error:
                    message = f"Weather refresh failed for {area}/{year}: {error}"
                    item.update(error=str(error), reason="weather loader failed")
                    failures.append(message)
                    logging.error("%s", message)
                    continue
                status = frame.attrs.get("cache_status")
                logging.info("Weather %s %s: %d hours (%s)", area, year, len(frame), status)
                provenance = frame.attrs.get("provenance", {})
                item.update(
                    status=status, outcome="validated",
                    available_end=provenance.get("available_end"),
                    retrieved_at=provenance.get("retrieved_at"),
                    source_coverage_complete=bool(
                        not frame.empty and frame["time"].iloc[-1] + timedelta(hours=1)
                        >= min(expected_end, datetime(year + 1, 1, 1, tzinfo=timezone.utc))
                    ),
                )
                if frame.empty or status == "stale_snapshot":
                    reason = provenance.get("refresh_error") or provenance.get("error") or "no valid weather data"
                    retained = (
                        f"; previous snapshot retained (exclusive end: {provenance.get('available_end')}, "
                        f"retrieved: {provenance.get('retrieved_at')})"
                        if status == "stale_snapshot" else ""
                    )
                    message = f"Weather refresh failed for {area}/{year}: {reason}{retained}"
                    grace_error = _weather_grace_error(
                        frame, year, expected_end, now,
                        args.weather_grace_days if args.mode == "refresh" else 0,
                    )
                    item.update(error=reason, reason=grace_error)
                    if grace_error is None:
                        item["outcome"] = "retained"
                        report["state"] = "degraded"
                        logging.warning("%s; retained within the %d-day weather grace period", message, args.weather_grace_days)
                        if os.environ.get("GITHUB_ACTIONS") == "true":
                            annotation = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
                            print(f"::warning title=Weather freshness degraded::{annotation}")
                    else:
                        item["outcome"] = "failed"
                        failures.append(f"{message}; {grace_error}")
    if failures:
        report.update(state="failed", error="\n".join(failures))
    _write_report(report_path, report)
    if failures:
        raise RuntimeError(report["error"])
    logging.info("Refresh %s: %d energy rows fetched; report: %s", report["state"], count, report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
