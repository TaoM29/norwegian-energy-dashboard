"""Expand the locally prepared snapshot during the Vercel build."""
from pathlib import Path
import tarfile

archive = Path("snapshots.tar.gz")
with tarfile.open(archive) as source:
    source.extractall(".", filter="data")
archive.unlink()
