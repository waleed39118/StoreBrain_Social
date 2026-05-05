"""
core/logger.py — نظام تسجيل مركزي
"""
from __future__ import annotations
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR      = Path.home() / ".storebrain_social" / "logs"
LOG_FILE     = LOG_DIR / "app.log"
_initialized = False


def setup_logging(level: int = logging.INFO) -> None:
    global _initialized
    if _initialized:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = RotatingFileHandler(LOG_FILE, maxBytes=3 * 1024 * 1024,
                              backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(ch)
    for lib in ("urllib3", "requests", "PIL", "httpx"):
        logging.getLogger(lib).setLevel(logging.WARNING)
    _initialized = True


def get_logger(name: str) -> logging.Logger:
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)
