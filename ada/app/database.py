"""SQLAlchemy engine/session factory tuned for SQLite under concurrent API + background load."""
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


# Deterministic constraint names are required for Alembic to ALTER/DROP constraints later
# (SQLite batch migrations rebuild tables and must be able to find constraints by name).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def build_engine(url: str) -> Engine:
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 15} if is_sqlite else {},
        pool_pre_ping=True,
    )
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # noqa: ANN001
            # pysqlite's implicit transaction handling breaks SAVEPOINTs and isolation;
            # disable it and let SQLAlchemy emit BEGIN itself (official SQLAlchemy recipe).
            dbapi_conn.isolation_level = None
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")    # readers don't block the writer
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=15000")
            cur.close()

        @event.listens_for(engine, "begin")
        def _sqlite_begin(conn):  # noqa: ANN001
            # DEFERRED for reads (WAL: readers never block the writer); IMMEDIATE for writes,
            # requested via begin_write(), so lock waits go through busy_timeout instead of
            # failing with SQLITE_BUSY when a read transaction upgrades to a write.
            mode = conn.get_execution_options().get("sqlite_begin", "DEFERRED")
            conn.exec_driver_sql(f"BEGIN {mode}")
    return engine


def begin_write(db: Session) -> None:
    """Start a write transaction that takes the SQLite write lock up front.

    Ends any open read-only snapshot first. Refuses if the session holds unflushed changes,
    so no pending work is ever committed implicitly.
    """
    if db.new or db.dirty or db.deleted:
        raise RuntimeError("begin_write() called with pending changes")
    if db.in_transaction():
        db.commit()
    db.connection(execution_options={"sqlite_begin": "IMMEDIATE"})


engine = build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def init_db() -> None:
    """Bring the schema to the latest Alembic revision (idempotent, safe on every boot)."""
    from app.migrate import upgrade_to_head
    upgrade_to_head()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for background jobs."""
    db = SessionLocal()
    try:
        begin_write(db)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
