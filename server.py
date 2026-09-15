"""Vercel entrypoint: immutable observations, temporary writable caches."""
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parent
CACHE = Path(tempfile.mkdtemp(prefix="energy-dashboard-"))
for name in ("weather", "forecasts"):
    shutil.copytree(ROOT / "data" / name, CACHE / name)
(CACHE / "forecasts" / "jobs").mkdir(exist_ok=True)
os.environ["ENERGY_DATABASE"] = str(ROOT / "data" / "energy.sqlite")
os.environ["WEATHER_SNAPSHOT_DIR"] = str(CACHE / "weather")
os.environ["FORECAST_ARTIFACT_ROOT"] = str(CACHE / "forecasts")
os.environ["FORECAST_JOBS_ENABLED"] = "false"
os.environ["ENERGY_DATA_MODE"] = "published"

from backend.main import app  # noqa: E402,F401
