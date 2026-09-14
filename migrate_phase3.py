"""
Phase 3 migration: add the `injuries` table.

Idempotent — safe to run multiple times. Preserves all existing data.

Usage:
    python migrate_phase3.py
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect

from src.db.database import get_engine, init_db


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)

    existing = set(inspector.get_table_names())
    print(f"Inspecting current schema...")
    print(f"  Found {len(existing)} tables.")

    if "injuries" in existing:
        print("  ✓ injuries table already exists. Nothing to do.")
        return 0

    print("\nCreating Phase 3 tables via SQLAlchemy.create_all()...")
    init_db()

    inspector = inspect(engine)
    after = set(inspector.get_table_names())
    new_tables = after - existing
    print(f"  + Created tables: {sorted(new_tables)}")

    print("\nDone.")
    print("Next steps:")
    print("  python cli.py sync-injuries --competition PL --season 2025/26")
    print("  python cli.py predict       --competition PL --season 2025/26")
    return 0


if __name__ == "__main__":
    sys.exit(main())
