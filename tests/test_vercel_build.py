"""Git builds must recover the pinned data without relying on a local snapshot."""
import hashlib
import io
import json
import sqlite3
import tarfile

import pytest

from scripts import fetch_snapshot as build
from scripts import prepare_vercel


@pytest.mark.parametrize("valid_checksum", [True, False])
def test_build_downloads_and_verifies_snapshot(tmp_path, monkeypatch, valid_checksum):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as package:
        content = b"published observations"
        entry = tarfile.TarInfo("data/example.txt")
        entry.size = len(content)
        package.addfile(entry, io.BytesIO(content))
        for name in build.REQUIRED_STUDIES:
            entry = tarfile.TarInfo(name)
            entry.size = 2
            package.addfile(entry, io.BytesIO(b"{}"))
    payload = archive.getvalue()
    manifest = tmp_path / "data/snapshot.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "url": "https://example.test/snapshot.tar.gz",
        "sha256": hashlib.sha256(payload).hexdigest() if valid_checksum else "0" * 64,
    }))
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "urlopen", lambda *_args, **_kwargs: io.BytesIO(payload))

    if valid_checksum:
        build.main()
        assert (tmp_path / "data/example.txt").read_bytes() == content
    else:
        with pytest.raises(ValueError, match="checksum"):
            build.main()
        assert list((tmp_path / "data").iterdir()) == [manifest]


def test_build_rejects_archive_without_required_studies_before_extracting(tmp_path, monkeypatch):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as package:
        entry = tarfile.TarInfo("data/example.txt")
        entry.size = 4
        package.addfile(entry, io.BytesIO(b"data"))
    payload = archive.getvalue()
    manifest = tmp_path / "data/snapshot.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"url": "https://example.test/snapshot.tar.gz",
                                    "sha256": hashlib.sha256(payload).hexdigest()}))
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "urlopen", lambda *_args, **_kwargs: io.BytesIO(payload))

    with pytest.raises(ValueError, match="missing required saved studies"):
        build.main()
    assert list(manifest.parent.iterdir()) == [manifest]


def test_prepare_packages_all_studies_and_preserves_archive_on_missing_input(tmp_path):
    data = tmp_path / "data"
    (data / "weather").mkdir(parents=True)
    (data / "forecasts/results").mkdir(parents=True)
    (data / "analyses").mkdir()
    (data / "file.geojson").write_text("{}")
    (data / "forecasts/manifest.json").write_text("{}")
    with sqlite3.connect(data / "energy.sqlite") as connection:
        connection.execute("CREATE TABLE observations (value INTEGER)")
        connection.execute("INSERT INTO observations VALUES (42)")
    for name in prepare_vercel.REQUIRED_STUDIES:
        (data / "analyses" / name).write_text("{}")

    stage = tmp_path / "stage"
    package = prepare_vercel.prepare(tmp_path, stage)
    with tarfile.open(package, "r:gz") as archive:
        assert set(build.REQUIRED_STUDIES).issubset(archive.getnames())
        assert archive.extractfile("data/energy.sqlite").read().startswith(b"SQLite format 3")
    previous = package.read_bytes()
    (data / "analyses/demand-anomalies.json").unlink()
    with pytest.raises(FileNotFoundError, match="demand-anomalies.json"):
        prepare_vercel.prepare(tmp_path, stage)
    assert package.read_bytes() == previous
