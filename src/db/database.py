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
from sqlalchemy.event import listens_for as _listens_for
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from src.db.schema import Base

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

    # Create the SQLite directory at CONNECT time, not import time
    # (2026-09-26): importing the package (e.g. CI's `import cli` smoke)
    # must not create an empty data/ directory. do_connect fires before
    # the DBAPI connect, so the first real connection still finds it.
    @_event.listens_for(_engine, "do_connect")
    def _ensure_sqlite_dir(dialect, conn_rec, cargs, cparams):
        if settings.database_url.startswith("sqlite:///"):
            db_path = settings.database_url.replace("sqlite:///", "")
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

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
    """Drop all tables. DESTRUCTIVE. Used for clean rebuilds in dev.

    drop_all() drops only MAPPED tables, so the unmapped one-row migration
    marker (ncaa_cfbd_labels_migration, written only by
    migrate_ncaa_cfbd_labels.py) is dropped here explicitly (Codex on #333):
    otherwise it survives, init_db() recreates an empty ncaa_cfbd_labels, and
    the ingest's guard reads "migrated" for a table the migration never made.
    It is the only unmapped table in the schema (migrate_*.py otherwise add
    columns/indexes to mapped tables, which drop with them)."""
    from sqlalchemy import text

    from src.ingestion.ncaa_cfbd import MIGRATION_MARKER

    Base.metadata.drop_all(_engine)
    with _engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {MIGRATION_MARKER}"))


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


def has_kalshi_ticker() -> bool:
    """odds_snapshots.market_ticker exists (migrate_kalshi_ticker.py ran).
    Checked on every call (one PRAGMA), never cached: a stale answer either
    way would write to a missing column or hide stored tickers."""
    from sqlalchemy import inspect
    try:
        return "market_ticker" in {c["name"] for c in inspect(_engine).get_columns("odds_snapshots")}
    except Exception:
        return False


def write_kalshi_tickers(session, pairs) -> int:
    """ORDER LINE: store each Kalshi leg's market ticker on its snapshot row.
    `pairs` = [(snapshot_id, ticker)] after a flush. A no-op (0) until
    migrate_kalshi_ticker.py has added the column (the column is unmapped)."""
    rows = [{"i": i, "t": t} for i, t in pairs if i is not None and t]
    if not rows or not has_kalshi_ticker():
        return 0
    from sqlalchemy import text
    session.execute(text("UPDATE odds_snapshots SET market_ticker = :t WHERE id = :i"), rows)
    return len(rows)


def read_kalshi_tickers(session, ids) -> dict:
    """{snapshot_id: market_ticker} for the given ids; {} before the migration."""
    ids = sorted({i for i in ids if i is not None})
    if not ids or session is None or not has_kalshi_ticker():
        return {}
    from sqlalchemy import bindparam, text
    q = text("SELECT id, market_ticker FROM odds_snapshots WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True))
    return {i: t for i, t in session.execute(q, {"ids": ids}) if t}


# PREDICTION HISTORY (ARCHITECT 2026-10-06, #87): every Prediction INSERT, from any
# write path (predict-nfl, soccer and MLB predict, future ones), is appended to
# prediction_history in the SAME transaction: a rolled-back run (a dry run, a
# failed chain) leaves no history, a committed one always does. Before
# migrate_prediction_history.py has created the table, predictions still write
# and the history is skipped with a warning (conservative: the predict path
# never fails on the record keeping). Checked per flush, never cached.
_HISTORY_COLS = ("match_id", "model_version", "computed_at", "home_win_prob", "draw_prob", "away_win_prob")


def has_prediction_history(conn) -> bool:
    from sqlalchemy import inspect
    try:
        return inspect(conn).has_table("prediction_history")
    except Exception:
        return False


def append_prediction_history(conn, rows: list[dict]) -> int:
    """Append rows ({match_id, model_version, computed_at, home_win_prob, draw_prob,
    away_win_prob}) to prediction_history; returns how many were written. The ONE
    append path: the Prediction flush listener below and a model sport that writes
    no Prediction row (the production INTL export, ARCHITECT 2026-10-07 addendum 3,
    item C) both go through it. Table missing: nothing written, a warning, 0."""
    from src.db.schema import PredictionHistory
    from src.timeutil import utc_now_naive
    if not rows:
        return 0
    if not has_prediction_history(conn):
        import logging
        logging.getLogger(__name__).warning(
            "prediction_history missing: %d prediction(s) not recorded — run migrate_prediction_history.py",
            len(rows))
        return 0
    now = utc_now_naive()
    conn.execute(PredictionHistory.__table__.insert(),
                 [{**{k: r.get(k) for k in _HISTORY_COLS},
                   "computed_at": r.get("computed_at") or now, "recorded_at": now} for r in rows])
    return len(rows)


@_listens_for(Session, "after_flush")
def _append_prediction_history(session, _ctx):
    from src.db.schema import Prediction
    new = [o for o in session.new if isinstance(o, Prediction)]
    if not new:
        return
    append_prediction_history(session.connection(), [{k: getattr(o, k) for k in _HISTORY_COLS} for o in new])


def get_engine():
    """Expose the engine for migrations / inspection."""
    return _engine
