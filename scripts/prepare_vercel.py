"""Stage an API release using only code and published observation snapshots."""
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / ".vercel-deploy" / "api"
STAGE.mkdir(parents=True, exist_ok=True)
for name in ("app_core", "backend"):
    shutil.copytree(ROOT / name, STAGE / name, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for path in (ROOT / "deploy" / "vercel").iterdir():
    if path.is_file():
        shutil.copy2(path, STAGE / path.name)
shutil.copy2(ROOT / "requirements.txt", STAGE / "requirements.txt")
(STAGE / ".python-version").write_text("3.12\n")
with tempfile.TemporaryDirectory() as temporary:
    snapshot = Path(temporary) / "energy.sqlite"
    with sqlite3.connect(f"file:{ROOT / 'data/energy.sqlite'}?mode=ro", uri=True) as source:
        with sqlite3.connect(snapshot) as destination:
            source.backup(destination)
    with tarfile.open(STAGE / "snapshots.tar.gz", "w:gz") as archive:
        archive.add(snapshot, arcname="data/energy.sqlite")
        for name in ("weather", "file.geojson"):
            archive.add(ROOT / "data" / name, arcname=f"data/{name}")
        for name in ("manifest.json", "results"):
            archive.add(ROOT / "data/forecasts" / name, arcname=f"data/forecasts/{name}")
print(STAGE)
print(f"Snapshot upload: {(STAGE / 'snapshots.tar.gz').stat().st_size / 1024**2:.1f} MB")
