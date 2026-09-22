"""Package published snapshots for upload; application code deploys from Git."""
from hashlib import file_digest
from pathlib import Path
import sqlite3
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / ".vercel-deploy" / "api"
REQUIRED_STUDIES = (
    "demand-sensitivity.json",
    "demand-anomalies.json",
    "demand-changes.json",
)


def prepare(root: Path = ROOT, stage: Path = STAGE) -> Path:
    """Write a complete archive atomically so a failed run preserves the last one."""
    studies = [root / "data" / "analyses" / name for name in REQUIRED_STUDIES]
    missing = [str(path) for path in studies if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise FileNotFoundError("Required saved studies are missing or empty: " + ", ".join(missing))

    stage.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=stage) as temporary:
        temporary_dir = Path(temporary)
        database = temporary_dir / "energy.sqlite"
        with sqlite3.connect((root / "data" / "energy.sqlite").as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(database) as destination:
                # The backup is temporary; avoid a second large rollback journal.
                destination.execute("PRAGMA journal_mode=OFF")
                source.backup(destination)
        package = temporary_dir / "snapshots.tar.gz"
        with tarfile.open(package, "w:gz") as archive:
            archive.add(database, arcname="data/energy.sqlite")
            database.unlink()
            for name in ("weather", "file.geojson"):
                archive.add(root / "data" / name, arcname=f"data/{name}")
            for name in ("manifest.json", "results"):
                archive.add(root / "data/forecasts" / name, arcname=f"data/forecasts/{name}")
            for study in studies:
                archive.add(study, arcname=f"data/analyses/{study.name}")
        destination = stage / "snapshots.tar.gz"
        package.replace(destination)
    return destination


def main() -> None:
    package = prepare()
    print(STAGE)
    print(f"Snapshot upload: {package.stat().st_size / 1024**2:.1f} MB")
    with package.open("rb") as archive:
        print(f"SHA-256: {file_digest(archive, 'sha256').hexdigest()}")


if __name__ == "__main__":
    main()
