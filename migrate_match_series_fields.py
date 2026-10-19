"""
Migration (2026-10-18, ARCHITECT addendum 130 item 2(b); #476, #478): the statsapi series fields on the match row.

Adds to matches:
  - series_game_number  INTEGER      statsapi seriesGameNumber  (NULL = the game's entry gave none)
  - games_in_series     INTEGER      statsapi gamesInSeries
  - series_description  VARCHAR(64)  statsapi seriesDescription
  - rescheduled_from    VARCHAR(32)  statsapi rescheduledFrom, ISO-8601 UTC "%Y-%m-%dT%H:%M:%SZ"

Why (RULED, addendum 130 item 2(b)): "DATA NOW, so the 2027 rule has it and so the reconciliation below has a
receipt: the laptop's statsapi sync stores `seriesGameNumber`, `gamesInSeries`, `seriesDescription` and
`rescheduledFrom` on the match row (additive columns by the unmapped pattern, like #588's; migration by hand after the
backup). Code: one small PR, data only, no reader changes its behaviour." The laptop's statsapi sync-matches stores
each game's own four fields (NULL for a field its entry does not give). The api-sports fallback (the host's MLB path)
and every other source write nothing: their rows stay NULL. No backfill: the next statsapi sync over a window writes
the rows it lists. Additive and idempotent; never deletes or rewrites.

RUN ORDER: any order. The columns are NOT mapped in the ORM (the ORDER LINE note in schema.py, as #588 did for
injuries.player_source_id): sync-matches writes them by guarded Core SQL only when all four exist, and nothing reads
them, so a pull or a deploy before this script keeps working and stores nothing. Run by hand, after the daily
.backup (law 5).

Receipt: per competition, the match rows and how many carry each field, and how many carry none. Right after
migrating every row is NULL; after the next laptop `sync-matches --competition MLB` over a window, re-run this script
(a no-op for the schema) and the MLB rows that window listed show the fields.

Usage:
    python migrate_match_series_fields.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import SERIES_COLUMNS, get_engine
from src.db.migrate_guard import refuse_missing_db

NEW_COLS = (
    ("series_game_number", "INTEGER"),
    ("games_in_series", "INTEGER"),
    ("series_description", "VARCHAR(64)"),
    ("rescheduled_from", "VARCHAR(32)"),
)
assert tuple(c for c, _ in NEW_COLS) == SERIES_COLUMNS          # one list of the four, the writer's


def main() -> int:
    engine = get_engine()
    if refuse_missing_db(engine):                               # law 5: a migration never creates a database
        return 1
    inspector = inspect(engine)
    if "matches" not in inspector.get_table_names():
        print("✗ matches table doesn't exist — nothing to migrate.")
        return 1

    cols = {c["name"] for c in inspector.get_columns("matches")}
    with engine.begin() as conn:
        for col, typ in NEW_COLS:
            if col in cols:
                print(f"· matches.{col} already exists.")
            else:
                print(f"+ Adding matches.{col}...")
                conn.execute(text(f"ALTER TABLE matches ADD COLUMN {col} {typ}"))

    print("\nMatch rows carrying the statsapi series fields (receipt):")
    print(f"  {'competition':<14} {'rows':>8} {'game_no':>8} {'in_series':>9} {'descr':>8} {'resched':>8} "
          f"{'none':>8}")
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT COALESCE(c.code, '(none)'), COUNT(*), "
            "  SUM(m.series_game_number IS NOT NULL), SUM(m.games_in_series IS NOT NULL), "
            "  SUM(m.series_description IS NOT NULL), SUM(m.rescheduled_from IS NOT NULL), "
            "  SUM(m.series_game_number IS NULL AND m.games_in_series IS NULL "
            "      AND m.series_description IS NULL AND m.rescheduled_from IS NULL) "
            "FROM matches m LEFT JOIN competitions c ON c.id = m.competition_id "
            "GROUP BY 1 ORDER BY 1"
        )).all()
    if not rows:
        print("  (no rows)")
    for code, n, g, t, d, r, none in rows:
        print(f"  {code:<14} {n:>8} {int(g or 0):>8} {int(t or 0):>9} {int(d or 0):>8} {int(r or 0):>8} "
              f"{int(none or 0):>8}")
    print("none = rows carrying none of the four: right after migrating, every row (no backfill). Only rows the "
          "laptop's statsapi sync-matches lists are filled, each from its own game; a field the game's entry does not "
          "give stays NULL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
