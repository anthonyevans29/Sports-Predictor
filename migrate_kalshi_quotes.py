"""
Migration (2026-09-27, K-track K1): odds_snapshots.yes_bid / yes_ask — the
executable Kalshi quotes behind each snapshot, in dollars (0.00-1.00).

Adds to odds_snapshots:
  - yes_bid  FLOAT   (NULL for book rows and pre-migration kalshi rows)
  - yes_ask  FLOAT

Why (K0 receipt): kalshi_sync read yes_bid/yes_ask but stored only a derived
price (devig_prob: the midpoint, or a single side, or last price). Executable
edge needs the ask. Backfill is impossible (quotes were never kept) and is
not attempted. Additive and idempotent; never deletes or rewrites.

RUN ORDER: take the daily .backup first (law 5), then run this BEFORE any
chain after merging — the ORM maps the columns, so queries on odds_snapshots
fail with "no such column" until they exist. Then the next sync-kalshi-*
starts filling them; re-run this script for the receipt.

Usage:
    python migrate_kalshi_quotes.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine

NEW_COLS = ("yes_bid", "yes_ask")


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)
    if "odds_snapshots" not in inspector.get_table_names():
        print("✗ odds_snapshots table doesn't exist — nothing to migrate.")
        return 1
    cols = {c["name"] for c in inspector.get_columns("odds_snapshots")}
    with engine.begin() as conn:
        for col in NEW_COLS:
            if col in cols:
                print(f"· odds_snapshots.{col} already exists.")
            else:
                print(f"+ Adding odds_snapshots.{col}...")
                conn.execute(text(f"ALTER TABLE odds_snapshots ADD COLUMN {col} FLOAT"))
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT market, COUNT(*), SUM(yes_bid IS NOT NULL), SUM(yes_ask IS NOT NULL), "
            "MAX(CASE WHEN yes_ask IS NOT NULL THEN captured_at END) "
            "FROM odds_snapshots WHERE source = 'kalshi' GROUP BY market ORDER BY market"
        )).all()
    print("\nKalshi snapshots carrying quotes (receipt):")
    print(f"  {'market':<6} {'rows':>7} {'with_bid':>9} {'with_ask':>9}  latest quoted capture")
    if not rows:
        print("  (no kalshi rows)")
    for market, n, nb, na, last in rows:
        print(f"  {market:<6} {n:>7} {int(nb or 0):>9} {int(na or 0):>9}  {last or '—'}")
    print("with_bid/with_ask = 0 = no sync since migrating (pre-migration rows stay NULL; "
          "no backfill possible).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
