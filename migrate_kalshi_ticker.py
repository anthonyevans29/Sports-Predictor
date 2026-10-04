"""
Migration (2026-10-04, ORDER LINE): odds_snapshots.market_ticker — the Kalshi
market ticker of each stored leg, so the Desk writes a copy-exact order line.

Adds to odds_snapshots:
  - market_ticker  VARCHAR(64)  (NULL for book rows and pre-migration kalshi rows)

Why (ARCHITECT 2026-10-04): sync-kalshi-* resolved each leg's ticker and kept
only its prices. Backfill is impossible (the tickers were never stored) and is
not attempted. Additive and idempotent; never deletes or rewrites.

RUN ORDER: take the daily .backup first (law 5), then run this. The column is
DEFERRED in the ORM and written / read only once it exists, so a deploy before
the migration keeps working (tickers simply stay null). The next sync-kalshi-*
starts filling it; re-run this script for the receipt.

Usage:
    python migrate_kalshi_ticker.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)
    if "odds_snapshots" not in inspector.get_table_names():
        print("✗ odds_snapshots table doesn't exist — nothing to migrate.")
        return 1
    cols = {c["name"] for c in inspector.get_columns("odds_snapshots")}
    with engine.begin() as conn:
        if "market_ticker" in cols:
            print("· odds_snapshots.market_ticker already exists.")
        else:
            print("+ Adding odds_snapshots.market_ticker...")
            conn.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT market, COUNT(*), SUM(market_ticker IS NOT NULL), "
            "MAX(CASE WHEN market_ticker IS NOT NULL THEN captured_at END) "
            "FROM odds_snapshots WHERE source = 'kalshi' GROUP BY market ORDER BY market"
        )).all()
    print("\nKalshi snapshots carrying a ticker (receipt):")
    print(f"  {'market':<6} {'rows':>7} {'with_ticker':>12}  latest ticketed capture")
    if not rows:
        print("  (no kalshi rows)")
    for market, n, nt, last in rows:
        print(f"  {market:<6} {n:>7} {int(nt or 0):>12}  {last or '—'}")
    print("with_ticker = 0 = no sync since migrating (pre-migration rows stay NULL; no backfill possible).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
