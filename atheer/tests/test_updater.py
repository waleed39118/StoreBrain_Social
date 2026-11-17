from __future__ import annotations

import io
import json
import zipfile

import pytest

from atheer.updater.publish import build_release, generate_keypair
from atheer.updater.service import ContentUpdater, UpdateError

URL = "https://updates.example/manifest.json"


class FakeServer:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def fetch(self, url: str, limit: int) -> bytes:
        return self.files[url]

    def publish(self, src, version, pem, *, tamper=None):
        bundle_url = f"https://updates.example/{version}.zip"
        bundle, manifest, sig = build_release(src, version, bundle_url, pem)
        if tamper:
            bundle, manifest, sig = tamper(bundle, manifest, sig)
        self.files.update({URL: manifest, URL + ".sig": sig, bundle_url: bundle})


@pytest.fixture
def keys():
    return generate_keypair()


@pytest.fixture
def src(tmp_path):
    d = tmp_path / "src"
    (d / "terminology").mkdir(parents=True)
    (d / "terminology" / "ar.json").write_text(json.dumps({"BP": "ضغط الدم"}), encoding="utf-8")
    return d


def make(tmp_path, pub, server, **kw):
    return ContentUpdater(tmp_path / "content", pub, fetch=server.fetch, **kw)


def test_install_upgrade_noop_and_rollback(tmp_path, keys, src):
    pem, pub = keys
    server, updater = FakeServer(), None
    updater = make(tmp_path, pub, server)

    server.publish(src, "2026.11.1", pem)
    assert updater.check_and_apply(URL) == "2026.11.1"
    assert json.loads((updater.current_path() / "terminology/ar.json").read_text("utf-8"))["BP"] == "ضغط الدم"

    assert updater.check_and_apply(URL) is None  # same version
    (src / "terminology" / "en.json").write_text("{}")
    server.publish(src, "2026.11.2", pem)
    assert updater.check_and_apply(URL) == "2026.11.2"
    server.publish(src, "2026.10.9", pem)
    assert updater.check_and_apply(URL) is None  # downgrade refused

    assert updater.rollback() == "2026.11.1"
    assert updater.current_version == "2026.11.1"


def test_rejects_bad_signature(tmp_path, keys, src):
    pem, _ = keys
    _, other_pub = generate_keypair()
    server = FakeServer()
    server.publish(src, "1.0", pem)
    with pytest.raises(UpdateError, match="signature"):
        make(tmp_path, other_pub, server).check_and_apply(URL)


def test_rejects_tampered_bundle(tmp_path, keys, src):
    pem, pub = keys
    server = FakeServer()
    server.publish(src, "1.0", pem, tamper=lambda b, m, s: (b + b"x", m, s))
    updater = make(tmp_path, pub, server)
    with pytest.raises(UpdateError, match="checksum"):
        updater.check_and_apply(URL)
    assert updater.current_version is None


def test_rejects_code_files(tmp_path, keys, src):
    (src / "evil.py").write_text("import os")
    with pytest.raises(ValueError):
        build_release(src, "1.0", "https://x/1.zip", keys[0])


def test_failed_health_check_keeps_current(tmp_path, keys, src):
    pem, pub = keys
    server = FakeServer()
    server.publish(src, "1.0", pem)
    good = make(tmp_path, pub, server)
    good.check_and_apply(URL)

    (src / "terminology" / "ar.json").write_text("{broken", encoding="utf-8")
    server.publish(src, "1.1", pem)
    with pytest.raises(json.JSONDecodeError):
        good.check_and_apply(URL)
    assert good.current_version == "1.0"
    assert not any(p.name.startswith(".") for p in good.releases.iterdir())


def test_rejects_path_traversal(tmp_path, keys):
    import base64
    import hashlib

    from cryptography.hazmat.primitives import serialization

    pem, pub = keys
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../escape.json", "{}")
    bundle = buf.getvalue()
    manifest = json.dumps({
        "format": 1, "version": "1.0", "bundle_url": "https://u/b.zip",
        "sha256": hashlib.sha256(bundle).hexdigest(),
        "files": {"../escape.json": hashlib.sha256(b"{}").hexdigest()},
    }).encode()
    key = serialization.load_pem_private_key(pem, None)
    server = FakeServer()
    server.files = {URL: manifest, URL + ".sig": base64.b64encode(key.sign(manifest)), "https://u/b.zip": bundle}
    with pytest.raises(UpdateError, match="Unsafe path"):
        make(tmp_path, pub, server).check_and_apply(URL)
    assert not (tmp_path / "content" / "escape.json").exists()
