"""Consistent online SQLite backups (``VACUUM INTO``) with retention. Safe while the app runs."""
import asyncio
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.database import engine

log = logging.getLogger("ada.backup")
NAME_RX = re.compile(r"^ada-\d{8}-\d{6}-\d{6}\.db$")


class BackupService:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.dir = Path(settings.backup_dir)
        self._task: asyncio.Task | None = None

    @property
    def supported(self) -> bool:
        return engine.url.get_backend_name() == "sqlite" and bool(engine.url.database)

    def backup_now(self) -> Path:
        if not self.supported:
            raise RuntimeError("Built-in backups support SQLite only")
        self.dir.mkdir(parents=True, exist_ok=True)
        dest = self.dir / f"ada-{datetime.now(timezone.utc):%Y%m%d-%H%M%S-%f}.db"
        # Raw connection: VACUUM cannot run inside SQLAlchemy's transaction.
        with sqlite3.connect(engine.url.database, timeout=30) as conn:
            conn.execute("VACUUM INTO ?", (str(dest),))
        self.prune()
        log.info("Backup written: %s", dest.name)
        return dest

    def list(self) -> list[dict]:
        if not self.dir.exists():
            return []
        files = sorted((f for f in self.dir.iterdir() if NAME_RX.match(f.name)), reverse=True)
        return [{"name": f.name, "size": f.stat().st_size,
                 "created_at": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat()}
                for f in files]

    def path_for(self, name: str) -> Path | None:
        if not NAME_RX.match(name):
            return None
        p = self.dir / name
        return p if p.is_file() else None

    def prune(self) -> None:
        for f in [self.dir / b["name"] for b in self.list()][self.s.backup_keep:]:
            f.unlink(missing_ok=True)

    def start(self) -> None:
        if self.supported:
            self._task = asyncio.create_task(self._loop(), name="ada-backups")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.backup_now)
            except Exception:
                log.exception("Scheduled backup failed")
            await asyncio.sleep(self.s.backup_interval_hours * 3600)
