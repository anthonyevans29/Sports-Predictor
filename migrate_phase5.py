"""
Phase 5 migration: add the `match_participants` table.

Idempotent — safe to run multiple times. Preserves all existing data.

The new table is sport-agnostic but currently used to store MLB starting
pitchers. Future use cases (NFL QBs, NHL starting goalies) plug into the
same table via different `role` values.

Usage:
    python migrate_phase5.py
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

    if "match_participants" in existing:
        print("  ✓ match_participants table already exists. Nothing to do.")
        return 0

    print("\nCreating Phase 5 tables via SQLAlchemy.create_all()...")
    init_db()

    inspector = inspect(engine)
    after = set(inspector.get_table_names())
    new_tables = after - existing
    print(f"  + Created tables: {sorted(new_tables)}")

    print("\nDone.")
    print("Next steps for MLB:")
    print("  python cli.py sync-competitions --sport mlb")
    print("  python cli.py sync-teams        --competition MLB --season 2026")
    print("  python cli.py sync-matches      --competition MLB --season 2026")
    print("  python cli.py train             --sport mlb")
    print("  python cli.py improve           --sport mlb")
    print("  python cli.py predict           --sport mlb --competition MLB --season 2026")
    return 0


if __name__ == "__main__":
    sys.exit(main())
