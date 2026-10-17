"""
Migration (2026-10-17, ARCHITECT addendum 112 item 10; #458): injuries.player_source_id, the provider's own player
id for an injury-report entry.

Adds:
  - injuries.player_source_id  VARCHAR(64)  (NULL = no provider id stored)

Why (RULED, addendum 112 item 10): "#458 — the window page keys QB news by team and player name, so two same-name
injured QBs collapse. RULED: key by provider player id, name as display only; the test uses two same-name players."
sync-injuries stores the id the american-football feed gives each entry (`response[].player.id`; NFL and NCAA share
the adapter); the window card carries it on each qb_news item as `player_id` and the window pager keys a player by
it. Every other source stays NULL (its read keeps no id). No backfill: the old rows' ids were never kept, and the
next sync-injuries rewrites each team's rows with them (it wipes and replaces a team's list). Additive and
idempotent; never deletes or rewrites.

RUN ORDER: any order. The column is NOT mapped in the ORM (the ORDER LINE note in schema.py, as addendum 35 item 2
ruled for odds.source_updated_at): sync-injuries writes it by guarded Core SQL only when it exists, and the window
card reads it the same way, so a pull or a deploy before this script keeps working: no id is stored, every qb_news
item carries player_id null, and the pager keys those items by team and name as before. Run by hand, after the
daily .backup (law 5).

Receipt: per source, the injuries rows that carry player_source_id and the rows that do not. Right after migrating
every row is NULL; after the next sync-injuries for NFL / NCAA, re-run this script (a no-op for the schema) and the
api_american_football rows show the field.

Usage:
    python migrate_injury_player_source_id.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.migrate_guard import refuse_missing_db


def main() -> int:
    engine = get_engine()
    if refuse_missing_db(engine):                               # law 5: a migration never creates a database
        return 1
    inspector = inspect(engine)
    if "injuries" not in inspector.get_table_names():
        print("✗ injuries table doesn't exist — nothing to migrate.")
        return 1

    cols = {c["name"] for c in inspector.get_columns("injuries")}
    with engine.begin() as conn:
        if "player_source_id" in cols:
            print("· injuries.player_source_id already exists.")
        else:
            print("+ Adding injuries.player_source_id...")
            conn.execute(text("ALTER TABLE injuries ADD COLUMN player_source_id VARCHAR(64)"))

    print("\nInjuries rows carrying player_source_id (receipt):")
    print(f"  {'source':<24} {'rows':>8} {'with':>8} {'without':>8}")
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT COALESCE(source, '(null)'), COUNT(*), SUM(player_source_id IS NOT NULL) "
            "FROM injuries GROUP BY 1 ORDER BY 1"
        )).all()
    if not rows:
        print("  (no rows)")
    for src, n, nw in rows:
        nw = int(nw or 0)
        print(f"  {src:<24} {n:>8} {nw:>8} {n - nw:>8}")
    print("with = 0 = no sync-injuries since migrating (pre-migration rows stay NULL; no backfill: their ids were "
          "never kept). Only api_american_football rows (NFL, NCAA) are ever filled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
