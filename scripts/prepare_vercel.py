"""Package published snapshots for upload; application code deploys from Git."""
from hashlib import file_digest
from pathlib import Path
import sqlite3
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / ".vercel-deploy" / "api"
STAGE.mkdir(parents=True, exist_ok=True)
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

with (STAGE / "snapshots.tar.gz").open("rb") as archive:
    print(f"SHA-256: {file_digest(archive, 'sha256').hexdigest()}")
