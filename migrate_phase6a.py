"""
Phase 6a migration: add the `player_season_stats` table.

Idempotent — safe to run multiple times. Preserves all existing data.

The new table holds per-season player stats which power the player
power-rating system. Existing `players` table is unchanged.

Usage:
    python migrate_phase6a.py
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect

from src.db.database import get_engine, init_db


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)

    existing = set(inspector.get_table_names())
    print("Inspecting current schema...")
    print(f"  Found {len(existing)} tables.")

    if "player_season_stats" in existing:
        print("  ✓ player_season_stats table already exists. Nothing to do.")
        return 0

    print("\nCreating Phase 6a tables via SQLAlchemy.create_all()...")
    init_db()

    inspector = inspect(engine)
    after = set(inspector.get_table_names())
    new_tables = after - existing
    print(f"  + Created tables: {sorted(new_tables)}")

    print("\nDone.")
    print("Next steps:")
    print("  python cli.py sync-players --competition PL --season 2025/26")
    print("  # ...then open http://localhost:8000/players")
    return 0


if __name__ == "__main__":
    sys.exit(main())
