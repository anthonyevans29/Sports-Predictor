"""
Database engine and session management.

Usage:
    from src.db.database import session_scope
    with session_scope() as session:
        session.add(...)
        # Auto-commits on success, rolls back on exception.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from src.db.schema import Base

# Ensure the SQLite directory exists if using sqlite
if settings.database_url.startswith("sqlite:///"):
    db_path = settings.database_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

_engine = create_engine(
    settings.database_url,
    echo=False,
    future=True,
    # SQLite specific: allow cross-thread for PyQt UI
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

# 2026-09-21 (morning-lag finding): journal_mode persists in the file but
# synchronous is PER-CONNECTION — db-tune's NORMAL applied only to its own
# session, so app connections ran WAL+FULL (fsync per commit; a 2,511-row
# update loop = the minute-plus lag). Install the pragmas on EVERY
# connection at the engine level.
if "sqlite" in settings.database_url:
    from sqlalchemy import event as _event

    @_event.listens_for(_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


SessionLocal = sessionmaker(
    bind=_engine,
    autoflush=False,
    autocommit=False,
    future=True,
    # Critical for the web layer: when we return ORM objects to templates,
    # we want them to keep the attributes that were loaded while the session
    # was open. Without this, accessing any attribute on a "finished" object
    # triggers a refresh against a closed session → DetachedInstanceError.
    expire_on_commit=False,
)


def init_db() -> None:
    """Create all tables. Safe to call repeatedly."""
    Base.metadata.create_all(_engine)


def drop_db() -> None:
    """Drop all tables. DESTRUCTIVE. Used for clean rebuilds in dev."""
    Base.metadata.drop_all(_engine)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Transactional scope for a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine():
    """Expose the engine for migrations / inspection."""
    return _engine
