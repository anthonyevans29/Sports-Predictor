"""
Phase 7 migration: adds `to_advance_home_prob` and `to_advance_away_prob`
columns to the `predictions` table for cup-knockout to-advance markets.

Idempotent — safe to run multiple times. Preserves all existing data.

Usage:
    python migrate_phase7.py
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect, text

from src.db.database import get_engine


_NEW_COLUMNS = [
    ("to_advance_home_prob", "FLOAT"),
    ("to_advance_away_prob", "FLOAT"),
]


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)

    if "predictions" not in inspector.get_table_names():
        print("ERROR: `predictions` table doesn't exist. Run init-db first.")
        return 1

    existing_cols = {c["name"] for c in inspector.get_columns("predictions")}
    print("Inspecting predictions table...")
    print(f"  Found {len(existing_cols)} columns.")

    added = 0
    with engine.begin() as conn:
        for col_name, col_type in _NEW_COLUMNS:
            if col_name in existing_cols:
                print(f"  ✓ {col_name} already exists.")
                continue
            print(f"  + Adding column {col_name}...")
            conn.execute(text(f"ALTER TABLE predictions ADD COLUMN {col_name} {col_type}"))
            added += 1

    if added == 0:
        print("\nNothing to do — schema is already up to date.")
    else:
        print(f"\nDone. Added {added} columns.")

    print("\nTo populate the new fields, retrain and re-predict:")
    print("  python cli.py train --sport soccer")
    print("  python cli.py improve --sport soccer")
    print("  python cli.py predict --sport soccer --competition FAC --season 2025/26")
    return 0


if __name__ == "__main__":
    sys.exit(main())
