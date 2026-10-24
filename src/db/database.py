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
    The v2 marker (ncaa_cfbd_v2_migration, written only by
    migrate_ncaa_cfbd_v2.py, #367) is dropped for the same reason, and so is
    kalshi_settled_markets_migration (written only by
    migrate_kalshi_settled_markets.py; Codex on #521), and so is
    cup_lineup_observations_migration (written only by
    migrate_cup_lineup_observations.py; addendum 158 item 3(a)). They are the only
    unmapped tables in the schema (migrate_*.py otherwise add columns/indexes to
    mapped tables, which drop with them)."""
    from sqlalchemy import text

    from src.ingestion.cup_lineups_live import MIGRATION_MARKER as CUP_LINEUPS_MARKER
    from src.ingestion.kalshi_history import MIGRATION_MARKER as KALSHI_HISTORY_MARKER
    from src.ingestion.ncaa_cfbd import MIGRATION_MARKER, V2_MIGRATION_MARKER

    Base.metadata.drop_all(_engine)
    with _engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {MIGRATION_MARKER}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {V2_MIGRATION_MARKER}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {KALSHI_HISTORY_MARKER}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {CUP_LINEUPS_MARKER}"))


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


# PROVIDER PLAYER ID (ARCHITECT 2026-10-17, addendum 112 item 10, #458): "key by provider player id, name as display
# only". injuries.player_source_id is unmapped (the ORDER LINE note; schema.py Injury): written after the flush and
# read by guarded Core SQL, only when the column exists. Before migrate_injury_player_source_id.py nothing is written
# and every reader gets no id. The existence check is per call, never cached (as has_kalshi_ticker).
def has_injury_player_id() -> bool:
    """injuries.player_source_id exists (migrate_injury_player_source_id.py ran). One PRAGMA per call."""
    from sqlalchemy import inspect
    try:
        return "player_source_id" in {c["name"] for c in inspect(_engine).get_columns("injuries")}
    except Exception:
        return False


def write_injury_player_ids(session, pairs) -> int:
    """Store the provider's player id on injuries rows after a flush. `pairs` = [(injury_id, provider id | None)];
    None or empty is left NULL. A no-op (0) until the migration has added the column."""
    rows = [{"i": i, "p": str(p)} for i, p in pairs if i is not None and p is not None and str(p).strip()]
    if not rows or not has_injury_player_id():
        return 0
    from sqlalchemy import text
    session.execute(text("UPDATE injuries SET player_source_id = :p WHERE id = :i"), rows)
    return len(rows)


def read_injury_player_ids(session, ids) -> dict:
    """{injury_id: provider player id} for the given ids that carry one; {} before the migration."""
    ids = sorted({i for i in ids if i is not None})
    if not ids or session is None or not has_injury_player_id():
        return {}
    from sqlalchemy import bindparam, text
    q = text("SELECT id, player_source_id FROM injuries WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True))
    return {i: str(p) for i, p in session.execute(q, {"ids": ids}) if p is not None and str(p).strip()}


# THE SERIES FIELDS (ARCHITECT 2026-10-18, addendum 130 item 2(b); #476, #478): "the laptop's statsapi sync stores
# `seriesGameNumber`, `gamesInSeries`, `seriesDescription` and `rescheduledFrom` on the match row (additive columns by
# the unmapped pattern, like #588's; migration by hand after the backup)". matches.series_game_number,
# games_in_series, series_description and rescheduled_from are unmapped (the ORDER LINE note; schema.py Match):
# written after the flush by guarded Core SQL, only when all four exist. Before migrate_match_series_fields.py nothing
# is written. The one reader: retire-orphans' receipt (2) (ARCHITECT 2026-10-20, addendum 146 item 3(a)(2), "the
# series arithmetic from the #605 fields"; src.ingestion.mlb_orphans, by read_match_series). No export, Desk, matcher
# or card reads them. The existence check is per call, never cached (as has_kalshi_ticker), and is made on the
# session's own connection.
SERIES_COLUMNS = ("series_game_number", "games_in_series", "series_description", "rescheduled_from")


def has_match_series(conn=None) -> bool:
    """matches carries all four series columns (migrate_match_series_fields.py ran). One PRAGMA per call, on `conn`
    when given (the writing session's connection), else the app's engine."""
    from sqlalchemy import inspect
    try:
        return set(SERIES_COLUMNS) <= {c["name"] for c in inspect(conn if conn is not None else _engine)
                                       .get_columns("matches")}
    except Exception:
        return False


def write_match_series(session, pairs) -> int:
    """Store each game's own series fields on its match row after a flush. `pairs` = [(match_id, {column: value |
    None})]: every one of the four columns is written for the row from that row's own dict, NULL where the game's
    entry gave none (never a value from another game). A row named twice keeps the last pair (the sync's order: the
    same listing entry its status and kickoff were last written from). A no-op (0) until the migration has added the
    columns. Returns the rows written."""
    last: dict = {}
    for i, fields in pairs:
        if i is not None and fields is not None:
            last[i] = {"i": i, **{c: fields.get(c) for c in SERIES_COLUMNS}}
    if not last or not has_match_series(session.connection()):
        return 0
    from sqlalchemy import text
    session.execute(text("UPDATE matches SET " + ", ".join(f"{c} = :{c}" for c in SERIES_COLUMNS)
                         + " WHERE id = :i"), list(last.values()))
    return len(last)


def read_match_series(session, ids) -> dict | None:
    """{match_id: {column: value | None}} for the given ids, the four SERIES_COLUMNS as stored (retire-orphans'
    receipt (2), addendum 146 item 3(a)(2)); an id with no row is left out. None until the migration has added the
    columns (the caller says so: no receipt, law 4). Read by guarded Core SQL on the session's own connection, the IN
    list chunked."""
    if not has_match_series(session.connection()):
        return None
    from sqlalchemy import bindparam, text
    ids = sorted({i for i in ids if i is not None})
    q = text("SELECT id, " + ", ".join(SERIES_COLUMNS) + " FROM matches WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True))
    out: dict = {}
    for k in range(0, len(ids), 500):
        for i, *vals in session.execute(q, {"ids": ids[k:k + 500]}):
            out[i] = dict(zip(SERIES_COLUMNS, vals))
    return out


# SOURCE TIME (ARCHITECT 2026-10-09, addendum 32 item 4; addendum 35 item 2, RULED): odds.source_updated_at and
# odds_snapshots.source_updated_at "follow the ORDER LINE note of 2026-10-04 in schema.py: not mapped in the ORM,
# written and read by guarded Core SQL, and only when the column exists. A pull or a deploy before the migration
# keeps working: nothing fails, nothing is written to the field, and every export shows it null." The existence
# check is per call, never cached (as has_kalshi_ticker).
SOURCE_TIME_TABLES = ("odds", "odds_snapshots")
_STORE_FMT = "%Y-%m-%d %H:%M:%S.%f"          # the ORM's SQLite DateTime storage form


def has_source_time(table: str, bind=None) -> bool:
    """<table>.source_updated_at exists (migrate_odds_source_updated_at.py ran). One PRAGMA per call, on `bind` (the
    session's own engine or connection: the database the read or write will run on) or, without one, the app's
    engine."""
    if table not in SOURCE_TIME_TABLES:
        return False
    from sqlalchemy import inspect
    try:
        return "source_updated_at" in {c["name"] for c in inspect(bind if bind is not None else _engine)
                                       .get_columns(table)}
    except Exception:
        return False


def _bind_of(session):
    """The engine or connection a Session (or a Connection) runs on; None when it cannot be read."""
    try:
        return session.get_bind() if hasattr(session, "get_bind") else session
    except Exception:
        return None


def write_source_times(session, table: str, pairs) -> int:
    """Store the provider's source time on rows of `table` after a flush. `pairs` = [(row_id, naive UTC
    datetime | None)]; None is left NULL. A no-op (0) until the migration has added the column."""
    rows = [{"i": i, "t": t.strftime(_STORE_FMT)} for i, t in pairs if i is not None and t is not None]
    if not rows or not has_source_time(table, _bind_of(session)):
        return 0
    from sqlalchemy import text
    session.execute(text(f"UPDATE {table} SET source_updated_at = :t WHERE id = :i"), rows)
    return len(rows)


def _parse_stored(v):
    from datetime import datetime
    if v is None or isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v))
    except ValueError:
        return None


def attach_source_times(session, rows) -> list:
    """THE reader (addendum 35 item 2: "The three export blocks read it through one guarded helper"): set the
    plain attribute `source_updated_at` on each ORM row (Odds or OddsSnapshot) from its table's column, None
    before the migration or where unknown. Returns the rows, so callers keep src.timeutil.oldest_source_time."""
    rows = list(rows)
    by_table: dict = {}
    for r in rows:
        t = getattr(getattr(r, "__table__", None), "name", None)
        if t in SOURCE_TIME_TABLES:
            by_table.setdefault(t, []).append(r)
    for t, rs in by_table.items():
        vals: dict = {}
        ids = sorted({r.id for r in rs if getattr(r, "id", None) is not None})
        if ids and session is not None and has_source_time(t, _bind_of(session)):
            from sqlalchemy import bindparam, text
            q = text(f"SELECT id, source_updated_at FROM {t} WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True))
            vals = {i: _parse_stored(v) for i, v in session.execute(q, {"ids": ids})}
        for r in rs:
            r.source_updated_at = vals.get(getattr(r, "id", None))
    return rows


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
