"""
Phase 13 migration: player props (PrizePicks-style projection & grading).

Adds:
  - `player_game_logs` table (new — per-player, per-match stat lines; the
    raw material prop projections are built from)
  - `prop_picks` table (new — a graded prop line: what PrizePicks offered
    vs. what the model projected)

Idempotent — safe to run multiple times. Preserves all existing data.

Usage:
    python migrate_phase13_props.py
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect

from src.db.database import get_engine
from src.db.schema import PlayerGameLog, PropPick


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for name, model in (
        ("player_game_logs", PlayerGameLog),
        ("prop_picks", PropPick),
    ):
        if name in existing_tables:
            print(f"· {name} table already exists.")
        else:
            print(f"+ Creating {name} table...")
            model.__table__.create(engine)
            print("  ✓ Created.")

    print()
    print("Done.")
    print()
    print("Next steps:")
    print("  1. python cli.py sync-player-match-stats --competition PL --season \"2026/27\"")
    print("     (pulls per-fixture player stat lines for recently finished matches)")
    print("  2. python cli.py grade-props --sport soccer --player \"Erling Haaland\" \\")
    print("       --stat shots_on_target --line 1.5")
    print("     (grades one line against the model's rolling projection)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
