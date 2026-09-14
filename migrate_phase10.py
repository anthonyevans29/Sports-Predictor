"""
Phase 10 migration: adds `source` and `line` columns to the `odds` table.

`source` lets multiple data providers coexist (API-Football for soccer,
API-Baseball for MLB) and supports per-source idempotent replacement.
`line` carries the totals/spread value (e.g. 8.5 over/under, ±1.5 run line).

Idempotent — safe to run multiple times. Preserves all existing data.

Usage:
    python migrate_phase10.py
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect, text

from src.db.database import get_engine


_NEW_COLUMNS = [
    ("source", "VARCHAR(32)"),
    ("line", "FLOAT"),
]


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)

    if "odds" not in inspector.get_table_names():
        print("ERROR: `odds` table doesn't exist. Run init-db first.")
        return 1

    existing_cols = {c["name"] for c in inspector.get_columns("odds")}
    print("Inspecting odds table...")
    print(f"  Found {len(existing_cols)} columns.")

    added = 0
    with engine.begin() as conn:
        for col_name, col_type in _NEW_COLUMNS:
            if col_name in existing_cols:
                print(f"  ✓ {col_name} already exists.")
                continue
            print(f"  + Adding column {col_name}...")
            conn.execute(text(f"ALTER TABLE odds ADD COLUMN {col_name} {col_type}"))
            added += 1

        # Add index on source for fast per-source delete-and-replace
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("odds")}
        if "ix_odds_source" not in existing_indexes:
            print("  + Creating index ix_odds_source...")
            conn.execute(text("CREATE INDEX ix_odds_source ON odds (source)"))

    if added == 0:
        print("\nNothing to do — schema is already up to date.")
    else:
        print(f"\nDone. Added {added} columns.")
    print("\nTo pull MLB odds (requires API_BASEBALL_KEY in .env):")
    print("  python cli.py sync-odds --competition MLB --season 2026")
    return 0


if __name__ == "__main__":
    sys.exit(main())
