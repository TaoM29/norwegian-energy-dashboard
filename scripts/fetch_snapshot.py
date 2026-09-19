"""Download the pinned public snapshot so Git builds need no local data."""
from hashlib import sha256
import json
from pathlib import Path
import tarfile
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    snapshot = json.loads((ROOT / "data/snapshot.json").read_text())
    with tempfile.TemporaryFile() as archive:
        digest = sha256()
        with urlopen(snapshot["url"], timeout=120) as response:
            while chunk := response.read(1024 * 1024):
                archive.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != snapshot["sha256"]:
            raise ValueError("Published snapshot checksum does not match snapshot.json")
        archive.seek(0)
        with tarfile.open(fileobj=archive, mode="r:gz") as source:
            source.extractall(ROOT, filter="data")
    print("Published observations and saved forecasts are ready.")


if __name__ == "__main__":
    main()
