"""
Phase 12.2 migration: bullpen season stats.

Adds:
  - `bullpen_season_stats` table (new — season-to-date bullpen aggregates)

Idempotent — safe to run multiple times. Preserves all existing data.

Usage:
    python migrate_phase12_2.py
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect

from src.db.database import get_engine
from src.db.schema import Base, BullpenSeasonStats


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if "bullpen_season_stats" in existing_tables:
        print("· bullpen_season_stats table already exists.")
    else:
        print("+ Creating bullpen_season_stats table...")
        BullpenSeasonStats.__table__.create(engine)
        print("  ✓ Created.")

    print()
    print("Done.")
    print()
    print("Next steps:")
    print("  1. python cli.py sync-bullpen-stats --season 2026")
    print("     (pulls bullpen ERA/WHIP/IP for all 30 teams — ~30 API calls)")
    print("  2. python cli.py predict --sport mlb --competition MLB --season 2026")
    print("     (regenerates predictions WITH bullpen ERA blended in)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
