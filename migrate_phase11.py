"""
Phase 11 migration: pitcher stats + CLV.

Adds:
  - `pitcher_season_stats` table (new — season-to-date pitching aggregates)
  - `prediction_outcomes.clv`              FLOAT     (CLV percentage-point delta)
  - `prediction_outcomes.closing_price`    FLOAT     (best available close)
  - `prediction_outcomes.closing_bookmaker` VARCHAR(64)

Idempotent — safe to run multiple times. Preserves all existing data.

Usage:
    python migrate_phase11.py
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.schema import Base, PitcherSeasonStats


_OUTCOME_COLS = [
    ("clv", "FLOAT"),
    ("closing_price", "FLOAT"),
    ("closing_bookmaker", "VARCHAR(64)"),
]


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)

    table_names = set(inspector.get_table_names())

    # 1. Create pitcher_season_stats if it doesn't exist
    if "pitcher_season_stats" in table_names:
        print("✓ pitcher_season_stats table exists.")
    else:
        print("+ Creating pitcher_season_stats table...")
        # Create only the new table — don't touch other tables' schemas
        PitcherSeasonStats.__table__.create(bind=engine)
        print("  ✓ Created.")

    # 2. Add new columns to prediction_outcomes
    if "prediction_outcomes" not in table_names:
        print("ERROR: prediction_outcomes table doesn't exist. Run init-db first.")
        return 1

    existing_cols = {c["name"] for c in inspector.get_columns("prediction_outcomes")}
    added = 0
    with engine.begin() as conn:
        for col_name, col_type in _OUTCOME_COLS:
            if col_name in existing_cols:
                print(f"✓ prediction_outcomes.{col_name} already exists.")
                continue
            print(f"+ Adding prediction_outcomes.{col_name}...")
            conn.execute(text(
                f"ALTER TABLE prediction_outcomes ADD COLUMN {col_name} {col_type}"
            ))
            added += 1

    if added == 0:
        print("\nNothing to do — schema is already up to date.")
    else:
        print(f"\nDone. Added {added} columns to prediction_outcomes.")

    print("\nNext steps:")
    print("  1. python cli.py sync-pitcher-stats --season 2026")
    print("     (pulls ERA/WHIP/K9 for ~30 starting pitchers)")
    print("  2. python cli.py sync-injuries --competition MLB --season 2026")
    print("     (uses API-Baseball — needs API_BASEBALL_KEY or falls back to API_FOOTBALL_KEY)")
    print("  3. python cli.py predict --sport mlb --competition MLB --season 2026")
    print("     (regenerates predictions WITH pitcher ERA wired in)")
    print("  4. python cli.py evaluate --sport mlb")
    print("     (backfills CLV on existing outcomes if odds were stored at score time)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
