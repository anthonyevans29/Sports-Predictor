"""
Migration (2026-10-12, ARCHITECT addendum 44 item 4, THE POSITION LOOKUP): creates player_position_answers, the kept
answers of the provider's /players?id= for listed players whose position the roster does not give: "The answer is
kept, so a player is asked once and not at every read." One row per (source, provider player id): the answer's
position field verbatim (NOT NULL). Addendum 46 item 2 (RULED): "Only an answer that gives a position is kept. An
answer that gives none, an empty answer included, leaves the player unresolved and counted. It is not a failed read,
it is not kept, and he is asked again at the next read." Nothing else of an answer is stored.

Additive and idempotent: creates one table if missing; never deletes or rewrites. It touches no other table (nothing
new is asked of the odds tables). Until it runs, sync-injuries still works (the 2026-10-04 convention: a pull or a
deploy before the migration keeps working): the lookup is made and nothing is kept, so the players are asked again at
the next read, and a warning says so.

RUN ORDER: take the daily .backup first (law 5); on the host, sp_deploy prints the exact `--run-migrations` command
(backup + this, under one lock).

Usage:
    python migrate_player_position_answers.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.migrate_guard import refuse_missing_db
from src.db.schema import PlayerPositionAnswer


def main() -> int:
    engine = get_engine()
    if refuse_missing_db(engine):                               # law 5: a migration never creates a database
        return 1
    names = inspect(engine).get_table_names()
    if "matches" not in names:
        print("✗ matches table doesn't exist — not a sports_predictor DB; nothing to migrate.")
        return 1
    if "player_position_answers" in names:
        print("· player_position_answers already exists.")
    else:
        print("+ Creating player_position_answers...")
        PlayerPositionAnswer.__table__.create(engine, checkfirst=True)
    with engine.connect() as conn:
        n, last = conn.execute(text(
            "SELECT COUNT(*), MAX(answered_at) FROM player_position_answers")).one()
    print(f"\nplayer_position_answers: {n} position(s) kept; latest {last or '—'}")
    print("0 rows = no injury read since migrating (no backfill: the answers come from the next reads).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
