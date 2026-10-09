"""
Migration (2026-10-09, ARCHITECT addendum 32 item 4): odds.source_updated_at
and odds_snapshots.source_updated_at — the provider's own time for a game's odds.

Adds:
  - odds.source_updated_at            DATETIME  (NULL = unknown)
  - odds_snapshots.source_updated_at  DATETIME  (NULL = unknown)

Why (RULED, addendum 32 item 3): "response[].update is the provider's own time
for a game's odds: one per game, neither our fetch time nor the fixture's. It is
read as the newest that any quote in the answer can be; a quote may be older. It
is stored and shown as source_updated_at and described in those words, never as
the time of a quote. A row without it has an unknown source time, and unknown is
never read as fresh." Only sync-odds-football (american football: NFL + NCAA)
fills it; every other source stays NULL. No backfill: the old rows' source
times were never kept. Additive and idempotent; never deletes or rewrites.

RUN ORDER: take the daily .backup first (law 5), then run this BEFORE any chain
after pulling — the ORM now maps both columns, so every odds / odds_snapshots
query fails with "no such column" until they exist.

Receipt: per table and source, the rows that carry source_updated_at and the
rows that do not. Right after migrating every row is NULL; after the next
sync-odds-football, re-run this script (a no-op for the schema) and the
api_american_football rows show the field.

Usage:
    python migrate_odds_source_updated_at.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine

TABLES = ("odds", "odds_snapshots")


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    missing = [t for t in TABLES if t not in names]
    if missing:
        print(f"✗ {', '.join(missing)} table(s) don't exist — nothing to migrate.")
        return 1

    with engine.begin() as conn:
        for table in TABLES:
            cols = {c["name"] for c in inspector.get_columns(table)}
            if "source_updated_at" in cols:
                print(f"· {table}.source_updated_at already exists.")
            else:
                print(f"+ Adding {table}.source_updated_at...")
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN source_updated_at DATETIME"))

    print("\nRows carrying source_updated_at (receipt):")
    print(f"  {'table':<15} {'source':<24} {'rows':>8} {'with':>8} {'without':>8}  newest source time")
    with engine.connect() as conn:
        for table in TABLES:
            rows = conn.execute(text(
                f"SELECT COALESCE(source, '(null)'), COUNT(*), SUM(source_updated_at IS NOT NULL), "
                f"MAX(source_updated_at) FROM {table} GROUP BY 1 ORDER BY 1"
            )).all()
            if not rows:
                print(f"  {table:<15} (no rows)")
            for src, n, nw, last in rows:
                nw = int(nw or 0)
                print(f"  {table:<15} {src:<24} {n:>8} {nw:>8} {n - nw:>8}  {last or '—'}")
    print("with = 0 = no sync-odds-football since migrating (pre-migration rows stay NULL; no backfill: "
          "their source times were never kept). Only api_american_football rows are ever filled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
