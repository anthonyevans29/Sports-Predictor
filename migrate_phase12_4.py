"""
Phase 12.4 migration: recent bullpen form columns.

Adds to bullpen_season_stats:
  - recent_era              FLOAT
  - recent_innings_pitched  FLOAT
  - recent_window_days      INTEGER
  - recent_refreshed_at     DATETIME

Idempotent — safe to run multiple times. Preserves all existing data.

Usage:
    python migrate_phase12_4.py
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect, text

from src.db.database import get_engine


_NEW_COLS = [
    ("recent_era", "FLOAT"),
    ("recent_innings_pitched", "FLOAT"),
    ("recent_window_days", "INTEGER"),
    ("recent_refreshed_at", "DATETIME"),
]


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)

    if "bullpen_season_stats" not in inspector.get_table_names():
        print("✗ bullpen_season_stats table doesn't exist.")
        print("  Run migrate_phase12_2.py first.")
        return 1

    existing_cols = {c["name"] for c in inspector.get_columns("bullpen_season_stats")}

    added = 0
    with engine.begin() as conn:
        for col_name, col_type in _NEW_COLS:
            if col_name in existing_cols:
                print(f"· bullpen_season_stats.{col_name} already exists.")
                continue
            print(f"+ Adding bullpen_season_stats.{col_name}...")
            conn.execute(text(
                f"ALTER TABLE bullpen_season_stats ADD COLUMN {col_name} {col_type}"
            ))
            added += 1

    print()
    print(f"Done. Added {added} columns to bullpen_season_stats.")
    print()
    print("Next steps:")
    print("  1. python cli.py sync-bullpen-stats --season 2026")
    print("     (now pulls season + last-10-day recent form per team)")
    print("  2. python cli.py predict --sport mlb --competition MLB --season 2026")
    print("     (recent bullpen form now blended 70/30 into the prediction)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
