"""Refresh the deployment volume daily at 19:37 UTC; retain logs and snapshots."""
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import subprocess
import sys
import time


def next_run(now: datetime) -> datetime:
    target = now.replace(hour=19, minute=37, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        now = datetime.now(timezone.utc)
        target = next_run(now)
        logging.info("Next refresh: %s", target.isoformat())
        time.sleep((target - now).total_seconds())
        mode = "refresh" if Path("data/energy.sqlite").exists() else "backfill"
        try:
            completed = subprocess.run([sys.executable, "scripts/refresh_data.py", mode], timeout=3600)
            logging.info("Refresh finished with exit code %s", completed.returncode)
        except subprocess.TimeoutExpired:
            logging.error("Refresh exceeded one hour; previous published snapshots remain available")


if __name__ == "__main__":
    main()
