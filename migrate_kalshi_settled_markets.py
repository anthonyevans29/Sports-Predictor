"""
Migration (2026-10-14, ARCHITECT addendum 67 item 1, KALSHI SETTLED-MARKET HISTORY; Issue #519): creates
kalshi_settled_markets, the one table `kalshi-history` writes: "a stored record of every settled Kalshi game market in
our series, with the last two-sided quote before kickoff, so the backtests and the older-season tests have a Kalshi
close where no book close exists." One row per market ticker (unique).

Additive and idempotent: creates one table if missing; never deletes or rewrites; touches no other table. Until it
runs, `kalshi-history --dry-run` still reads and prints, and a run without --dry-run refuses.

RUN ORDER: take the daily .backup first (law 5); on the host, sp_deploy prints the exact `--run-migrations` command
(backup + this, under one lock).

Usage:
    python migrate_kalshi_settled_markets.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.schema import KalshiSettledMarket


def main() -> int:
    from src.walters.venue_quote_age import db_file_path
    path = db_file_path()
    if path is not None and not path.is_file():                 # law 5: a migration never creates a database
        print(f"✗ no DB file at {path} — nothing to migrate (a migration never creates a database).")
        return 1
    engine = get_engine()
    names = inspect(engine).get_table_names()
    if "matches" not in names:
        print("✗ matches table doesn't exist — not a sports_predictor DB; nothing to migrate.")
        return 1
    if "kalshi_settled_markets" in names:
        print("· kalshi_settled_markets already exists.")
    else:
        print("+ Creating kalshi_settled_markets...")
        KalshiSettledMarket.__table__.create(engine, checkfirst=True)
    with engine.connect() as conn:
        n, last = conn.execute(text("SELECT COUNT(*), MAX(fetched_at) FROM kalshi_settled_markets")).one()
    print(f"\nkalshi_settled_markets: {n} market(s) stored; latest fetch {last or '—'}")
    print("0 rows = no kalshi-history run since migrating (the operator's block runs it, after the architect's read).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
