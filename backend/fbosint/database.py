"""Database engine/session management (SQLite by default, PostgreSQL compatible)."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings, get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _sqlite_pragmas(dbapi_conn, _record) -> None:  # pragma: no cover - trivial
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def init_engine(settings: Settings | None = None) -> Engine:
    global _engine, _SessionLocal
    s = settings or get_settings()
    s.ensure_dirs()
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if s.is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(s.database_url, **kwargs)
    if s.is_sqlite:
        event.listen(_engine, "connect", _sqlite_pragmas)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        init_engine()
    if _engine is None:  # pragma: no cover
        raise RuntimeError("database_not_initialised")
    return _engine


def create_all() -> None:
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(get_engine())


def SessionLocal() -> Session:  # noqa: N802 - factory-style name
    if _SessionLocal is None:
        init_engine()
    if _SessionLocal is None:  # pragma: no cover
        raise RuntimeError("database_not_initialised")
    return _SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
