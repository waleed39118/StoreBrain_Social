"""Alembic environment.

* URL comes from app settings (ADA_DATABASE_URL), never hard-coded.
* ``render_as_batch`` lets SQLite perform ALTER COLUMN / DROP / constraint changes by
  table rebuild, so future migrations work on SQLite exactly as on PostgreSQL.
* ``compare_type`` / ``compare_server_default`` make autogenerate detect type changes.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401  (register all tables on Base.metadata)
from app.config import get_settings
from app.database import Base

config = context.config
if config.config_file_name and not config.attributes.get("skip_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata
_OPTS = dict(target_metadata=target_metadata, render_as_batch=True,
             compare_type=True, compare_server_default=True)


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, **_OPTS)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, **_OPTS)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
