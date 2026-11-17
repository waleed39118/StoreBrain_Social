"""Signed content updates: terminology, prompts, voice models. Never executable code.

Flow: fetch manifest + detached Ed25519 signature → verify against pinned key →
refuse downgrades → download bundle → verify bundle and per-file SHA-256 →
safe-extract to staging → health check → atomic pointer swap → prune old
releases. Any failure leaves the current release untouched; ``rollback()``
restores the previous one. Application *code* updates go through CI and a
human-approved deployment, not this channel.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import os
import shutil
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, Field, ValidationError

from atheer.core.config import Settings

logger = logging.getLogger(__name__)

ALLOWED_SUFFIXES = frozenset({".json", ".txt", ".csv", ".onnx"})
MAX_BUNDLE_BYTES = 300 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
KEEP_RELEASES = 3
POINTER = "current.json"


class UpdateError(Exception):
    pass


class Manifest(BaseModel):
    format: int = Field(1, ge=1, le=1)
    version: str = Field(pattern=r"^\d+(\.\d+){1,3}$")  # e.g. 2026.11.17.1
    bundle_url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: dict[str, str]  # relative path → sha256

    @property
    def version_key(self) -> tuple[int, ...]:
        return parse_version(self.version)


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def https_fetch(url: str, limit: int) -> bytes:
    if not url.startswith("https://"):
        raise UpdateError(f"Refusing non-HTTPS update URL: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "atheer-updater"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - scheme checked above
        data = resp.read(limit + 1)
    if len(data) > limit:
        raise UpdateError(f"Download exceeds {limit} bytes: {url}")
    return data


Fetcher = Callable[[str, int], bytes]
HealthCheck = Callable[[Path], None]  # raise to reject a release


def default_health_check(release: Path) -> None:
    """Every JSON file must parse; extend with domain checks (e.g. required terminology keys)."""
    for path in release.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


class ContentUpdater:
    def __init__(
        self,
        content_dir: Path,
        public_key_b64: str,
        *,
        fetch: Fetcher = https_fetch,
        health_check: HealthCheck = default_health_check,
    ) -> None:
        self.root = Path(content_dir)
        self.releases = self.root / "releases"
        self.releases.mkdir(parents=True, exist_ok=True)
        self._key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        self._fetch = fetch
        self._health_check = health_check

    # ------------------------------------------------------------- state

    def _pointer(self) -> dict[str, Any]:
        try:
            return json.loads((self.root / POINTER).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def _write_pointer(self, data: dict[str, Any]) -> None:
        tmp = self.root / f"{POINTER}.tmp"
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self.root / POINTER)  # atomic on POSIX and Windows

    @property
    def current_version(self) -> str | None:
        return self._pointer().get("current")

    def current_path(self) -> Path | None:
        v = self.current_version
        return self.releases / v if v else None

    # ------------------------------------------------------------- update

    def fetch_manifest(self, manifest_url: str) -> Manifest:
        raw = self._fetch(manifest_url, MAX_MANIFEST_BYTES)
        sig = self._fetch(manifest_url + ".sig", 1024)
        try:
            self._key.verify(base64.b64decode(sig.strip()), raw)
        except (InvalidSignature, ValueError) as exc:
            raise UpdateError("Manifest signature verification failed") from exc
        try:
            return Manifest.model_validate_json(raw)
        except ValidationError as exc:
            raise UpdateError(f"Invalid manifest: {exc}") from exc

    def check_and_apply(self, manifest_url: str) -> str | None:
        """Returns the newly installed version, or None if already up to date."""
        manifest = self.fetch_manifest(manifest_url)
        current = self.current_version
        if current and manifest.version_key <= parse_version(current):
            return None
        self.apply(manifest)
        return manifest.version

    def apply(self, manifest: Manifest) -> None:
        bundle = self._fetch(manifest.bundle_url, MAX_BUNDLE_BYTES)
        if sha256(bundle) != manifest.sha256:
            raise UpdateError("Bundle checksum mismatch")

        target = self.releases / manifest.version
        staging = self.releases / f".{manifest.version}.staging"
        shutil.rmtree(staging, ignore_errors=True)
        try:
            self._extract(bundle, manifest, staging)
            self._health_check(staging)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        shutil.rmtree(target, ignore_errors=True)
        os.replace(staging, target)

        previous = self.current_version
        self._write_pointer({"current": manifest.version, "previous": previous})
        logger.info("Content updated %s → %s", previous, manifest.version)
        self._prune()

    def rollback(self) -> str:
        ptr = self._pointer()
        previous = ptr.get("previous")
        if not previous or not (self.releases / previous).is_dir():
            raise UpdateError("No previous release available for rollback")
        self._write_pointer({"current": previous, "previous": None})
        logger.warning("Content rolled back %s → %s", ptr.get("current"), previous)
        return previous

    # ------------------------------------------------------------- internals

    @staticmethod
    def _extract(bundle: bytes, manifest: Manifest, dest: Path) -> None:
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            names = {i.filename for i in zf.infolist() if not i.is_dir()}
            if names != set(manifest.files):
                raise UpdateError("Bundle contents do not match manifest file list")
            if sum(i.file_size for i in zf.infolist()) > MAX_BUNDLE_BYTES:
                raise UpdateError("Bundle expands beyond size limit")  # zip-bomb guard
            for name, expected in manifest.files.items():
                rel = PurePosixPath(name)
                if rel.is_absolute() or ".." in rel.parts or "\\" in name:
                    raise UpdateError(f"Unsafe path in bundle: {name}")
                if rel.suffix.lower() not in ALLOWED_SUFFIXES:
                    raise UpdateError(f"File type not allowed in content bundle: {name}")
                data = zf.read(name)
                if sha256(data) != expected:
                    raise UpdateError(f"Checksum mismatch for {name}")
                out = dest.joinpath(*rel.parts)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)

    def _prune(self) -> None:
        ptr = self._pointer()
        keep = {ptr.get("current"), ptr.get("previous")}
        versions = sorted(
            (p for p in self.releases.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: parse_version(p.name),
            reverse=True,
        )
        for path in versions[KEEP_RELEASES:]:
            if path.name not in keep:
                shutil.rmtree(path, ignore_errors=True)


async def run_update_loop(settings: Settings, is_quiet: Callable[[], bool]) -> None:
    """Background task: periodically check for updates; apply only when the clinic is quiet."""
    assert settings.update_manifest_url and settings.update_public_key
    updater = ContentUpdater(settings.content_dir, settings.update_public_key)
    while True:
        try:
            if await asyncio.to_thread(is_quiet):
                version = await asyncio.to_thread(updater.check_and_apply, settings.update_manifest_url)
                if version:
                    logger.info("Installed content release %s", version)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - never crash the clinic over an update
            logger.exception("Content update failed; current release unchanged")
        await asyncio.sleep(settings.update_interval_minutes * 60)
