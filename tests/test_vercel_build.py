"""Git builds must recover the pinned data without relying on a local snapshot."""
import hashlib
import io
import json
import tarfile

import pytest

from deploy.vercel import build


@pytest.mark.parametrize("valid_checksum", [True, False])
def test_build_downloads_and_verifies_snapshot(tmp_path, monkeypatch, valid_checksum):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as package:
        content = b"published observations"
        entry = tarfile.TarInfo("data/example.txt")
        entry.size = len(content)
        package.addfile(entry, io.BytesIO(content))
    payload = archive.getvalue()
    manifest = tmp_path / "deploy/vercel/snapshot.json"
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
        assert not (tmp_path / "data").exists()
