"""
One-shot migration: bring an existing pre-Phase-2 SQLite DB up to current schema.

Idempotent — safe to run multiple times. Detects what's missing and adds only
the missing columns / tables.

Usage:
    python migrate_phase2.py

After this finishes, your existing data (matches, teams, stats, etc.) is
preserved AND the new tables exist. You can immediately run:
    python cli.py train
    python cli.py improve
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect, text

from src.db.database import get_engine, init_db


# (table, column, sqlite_column_definition)
NEW_PREDICTION_COLUMNS = [
    ("predictions", "over_under_line", "FLOAT"),
    ("predictions", "over_prob", "FLOAT"),
    ("predictions", "under_prob", "FLOAT"),
]


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)

    print("Inspecting current schema...")
    existing_tables = set(inspector.get_table_names())
    print(f"  Found {len(existing_tables)} tables: {sorted(existing_tables)}")

    # 1) Add any missing columns to existing tables
    columns_added = 0
    for table, column, coldef in NEW_PREDICTION_COLUMNS:
        if table not in existing_tables:
            # Table doesn't exist; create_all() will handle it below
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        if column in existing_cols:
            print(f"  ✓ {table}.{column} already exists")
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}"))
        print(f"  + Added {table}.{column}")
        columns_added += 1

    # 2) Create any tables that are in the schema but not in the DB
    print("\nCreating any missing tables via SQLAlchemy.create_all()...")
    init_db()  # idempotent — creates only missing tables

    # 3) Verify the new Phase 2 tables exist now
    inspector = inspect(engine)
    final_tables = set(inspector.get_table_names())
    new_tables = final_tables - existing_tables
    if new_tables:
        print(f"  + Created tables: {sorted(new_tables)}")
    else:
        print("  ✓ All Phase 2 tables already present.")

    print(f"\nDone. {columns_added} columns added, {len(new_tables)} tables created.")
    print("You can now run: python cli.py train")
    return 0


if __name__ == "__main__":
    sys.exit(main())
