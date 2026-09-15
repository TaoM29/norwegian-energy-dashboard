"""Refresh daily at 19:37 UTC and expose the latest run through container health."""
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import subprocess
import sys
import time

STATUS_PATH = Path("data/refresh-status.json")
TIMEOUT_SECONDS = 3600


def next_run(now: datetime) -> datetime:
    target = now.replace(hour=19, minute=37, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


def read_status(path: Path = STATUS_PATH) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def write_status(status: dict, path: Path = STATUS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(status) + "\n")
    temporary.replace(path)


def healthy(path: Path = STATUS_PATH, now: datetime | None = None) -> bool:
    status = read_status(path)
    try:
        deadline = datetime.fromisoformat(status["nextRun"]) + timedelta(seconds=TIMEOUT_SECONDS + 300)
        return status["state"] in {"waiting", "running", "succeeded"} and (now or datetime.now(timezone.utc)) <= deadline
    except (KeyError, TypeError, ValueError):
        return False


def run_once(path: Path = STATUS_PATH) -> dict:
    now = datetime.now(timezone.utc)
    status = {**read_status(path), "state": "running", "lastAttempt": now.isoformat(), "nextRun": now.isoformat()}
    write_status(status, path)
    mode = "refresh" if Path("data/energy.sqlite").exists() else "backfill"
    try:
        result = subprocess.run([sys.executable, "scripts/refresh_data.py", mode], timeout=TIMEOUT_SECONDS)
        if result.returncode:
            raise RuntimeError(f"Refresh exited with code {result.returncode}")
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        status.update(state="failed", error=str(error))
        logging.error("Refresh failed: %s; published snapshots remain available", error)
    else:
        status.update(state="succeeded", lastSuccess=datetime.now(timezone.utc).isoformat(), error=None)
        logging.info("Refresh succeeded")
    status["nextRun"] = next_run(datetime.now(timezone.utc)).isoformat()
    write_status(status, path)
    return status


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        now = datetime.now(timezone.utc)
        target = next_run(now)
        previous = read_status()
        # A restart must not turn a failed run green before a successful refresh.
        write_status({**previous, "state": "failed" if previous.get("state") in {"failed", "running"} else "waiting", "nextRun": target.isoformat()})
        logging.info("Next refresh: %s", target.isoformat())
        time.sleep((target - now).total_seconds())
        run_once()


if __name__ == "__main__":
    if "--healthcheck" in sys.argv:
        raise SystemExit(0 if healthy() else 1)
    if "--once" in sys.argv:
        logging.basicConfig(level=logging.INFO)
        raise SystemExit(0 if run_once()["state"] == "succeeded" else 1)
    main()
