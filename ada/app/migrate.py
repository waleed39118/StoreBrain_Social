"""Programmatic Alembic entry point used at startup and in tests."""
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import get_settings

ROOT = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    cfg.attributes["skip_logging"] = True  # keep the app's logging config intact
    return cfg


def upgrade_to_head() -> None:
    command.upgrade(alembic_config(), "head")
