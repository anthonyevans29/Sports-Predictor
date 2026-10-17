"""
Migration (2026-10-14, ARCHITECT addendum 67 item 1, KALSHI SETTLED-MARKET HISTORY; Issue #519): creates
kalshi_settled_markets, the one table `kalshi-history` writes: "a stored record of every settled Kalshi game market in
our series, with the last two-sided quote before kickoff, so the backtests and the older-season tests have a Kalshi
close where no book close exists." One row per market ticker (unique).

Additive and idempotent: creates the table if missing, plus the one-row migration marker
kalshi_settled_markets_migration (Codex P2 on #521); never deletes or rewrites; touches no other table. Until it runs,
`kalshi-history --dry-run` still reads and prints, and a run without --dry-run refuses.

WHY THE MARKER (the convention of migrate_ncaa_cfbd_labels.py, Codex on #333): KalshiSettledMarket is mapped in
Base.metadata, so any init_db() (create_all, run by many scheduled commands) creates an empty kalshi_settled_markets;
the table's existence does not prove this backed-up migration ran. The marker is created HERE ONLY, by Core SQL (it is
not mapped, so create_all can never make it). The ingest writes only when table AND marker exist. If init_db() already
created the (empty) table, this script keeps it and writes the marker.

RUN ORDER: take the daily .backup first (law 5); on the host, sp_deploy prints the exact `--run-migrations` command
(backup + this, under one lock).

Usage:
    python migrate_kalshi_settled_markets.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.migrate_guard import refuse_missing_db
from src.db.schema import KalshiSettledMarket
from src.ingestion.kalshi_history import MIGRATION_MARKER
from src.timeutil import utc_now_naive


def main() -> int:
    engine = get_engine()
    if refuse_missing_db(engine):                               # law 5: a migration never creates a database
        return 1
    names = inspect(engine).get_table_names()
    if "matches" not in names:
        print("✗ matches table doesn't exist — not a sports_predictor DB; nothing to migrate.")
        return 1
    if "kalshi_settled_markets" in names:
        print("· kalshi_settled_markets already exists.")
    else:
        print("+ Creating kalshi_settled_markets...")
        KalshiSettledMarket.__table__.create(engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE IF NOT EXISTS {MIGRATION_MARKER} ("
                          "id INTEGER PRIMARY KEY CHECK (id = 1), script VARCHAR(64) NOT NULL, "
                          "migrated_at DATETIME NOT NULL)"))
        added = conn.execute(text(f"INSERT OR IGNORE INTO {MIGRATION_MARKER} (id, script, migrated_at) "
                                  "VALUES (1, 'migrate_kalshi_settled_markets.py', :at)"),
                             {"at": utc_now_naive().isoformat(sep=" ")}).rowcount
        at = conn.execute(text(f"SELECT migrated_at FROM {MIGRATION_MARKER} WHERE id = 1")).scalar()
    print(("+ Wrote" if added else "· Kept") + f" migration marker {MIGRATION_MARKER} (migrated_at {at}); "
          "kalshi-history writes only with this marker present.")
    with engine.connect() as conn:
        n, last = conn.execute(text("SELECT COUNT(*), MAX(fetched_at) FROM kalshi_settled_markets")).one()
    print(f"\nkalshi_settled_markets: {n} market(s) stored; latest fetch {last or '—'}")
    print("0 rows = no kalshi-history run since migrating (the operator's block runs it, after the architect's read).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
