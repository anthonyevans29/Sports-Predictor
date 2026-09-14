"""
Migration: add per-appearance bullpen EFFECTIVENESS columns to
pitcher_appearances (earned_runs, hits_allowed, walks_allowed, strikeouts).

Idempotent — safe to run multiple times. Existing appearance rows keep these as
NULL (they predate the capture); new syncs populate them.

Usage:
    python migrate_bullpen_effectiveness.py

Then re-capture to backfill the new fields on historical games:
    python cli.py sync-appearances --competition MLB --season 2026 --backfill
    python cli.py sync-appearances --competition MLB --season 2025 --backfill
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect, text

from src.db.database import get_engine, init_db


NEW_COLUMNS = [
    ("pitcher_appearances", "earned_runs", "INTEGER"),
    ("pitcher_appearances", "hits_allowed", "INTEGER"),
    ("pitcher_appearances", "walks_allowed", "INTEGER"),
    ("pitcher_appearances", "strikeouts", "INTEGER"),
]


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    added = 0
    for table, column, coldef in NEW_COLUMNS:
        if table not in existing_tables:
            print(f"  (table {table} missing; create_all will handle)")
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        if column in existing_cols:
            print(f"  ✓ {table}.{column} already exists")
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}"))
        print(f"  + Added {table}.{column}")
        added += 1

    print("\nEnsuring any missing tables exist...")
    init_db()

    print(f"\nDone. {added} column(s) added.")
    print("Now backfill the new fields:")
    print("  python cli.py sync-appearances --competition MLB --season 2026 --backfill")
    print("  python cli.py sync-appearances --competition MLB --season 2025 --backfill")
    return 0


if __name__ == "__main__":
    sys.exit(main())
