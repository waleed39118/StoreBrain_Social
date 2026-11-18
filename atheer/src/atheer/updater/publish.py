"""Publisher-side tooling: build a content bundle, manifest, and detached signature.

Run on a trusted build machine; the private key never reaches clinic devices.
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atheer.updater.service import ALLOWED_SUFFIXES, sha256


def generate_keypair() -> tuple[bytes, str]:
    """Returns (private key PEM, base64 public key for ATHEER_UPDATE_PUBLIC_KEY)."""
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return pem, base64.b64encode(pub).decode()


def build_release(source_dir: Path, version: str, bundle_url: str, private_key_pem: bytes) -> tuple[bytes, bytes, bytes]:
    """Returns (bundle.zip, manifest.json, manifest.json.sig)."""
    files: dict[str, str] = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(p for p in source_dir.rglob("*") if p.is_file()):
            if path.suffix.lower() not in ALLOWED_SUFFIXES:
                raise ValueError(f"Not allowed in content bundle: {path}")
            rel = path.relative_to(source_dir).as_posix()
            data = path.read_bytes()
            files[rel] = sha256(data)
            zf.writestr(rel, data)
    bundle = buf.getvalue()
    manifest = json.dumps(
        {"format": 1, "version": version, "bundle_url": bundle_url, "sha256": sha256(bundle), "files": files},
        sort_keys=True,
    ).encode()
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    assert isinstance(key, Ed25519PrivateKey)
    signature = base64.b64encode(key.sign(manifest))
    return bundle, manifest, signature
