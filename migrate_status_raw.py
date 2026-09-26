"""
Migration (2026-09-26): matches.status_raw — the provider's own status code.

Adds to matches:
  - status_raw  VARCHAR(16)   (NULL until the next sync touches the row)

Why: our MatchStatus vocabulary collapses provider codes (hockey FT / AOT /
AP all map to FINISHED), so OT/SO wins were indistinguishable in the DB —
the H2 reopening groundwork needs them. Additive and idempotent: safe to
run multiple times; preserves all existing data; never deletes or rewrites.

RUN ORDER: take the daily .backup first (law 5), then run this BEFORE any
chain after merging — the ORM now maps the column, so queries on `matches`
fail with "no such column" until it exists.

Receipt: prints the NHL status_raw vocabulary. Right after migrating, every
row is NULL; after the next FULL NHL sync
(`python cli.py sync-matches --competition NHL --seasons 3`), re-run this
script (it is a no-op for the schema) and the counts show FT / AOT / AP.

Usage:
    python migrate_status_raw.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)
    if "matches" not in inspector.get_table_names():
        print("✗ matches table doesn't exist — nothing to migrate.")
        return 1

    cols = {c["name"] for c in inspector.get_columns("matches")}
    with engine.begin() as conn:
        if "status_raw" in cols:
            print("· matches.status_raw already exists.")
        else:
            print("+ Adding matches.status_raw...")
            conn.execute(text("ALTER TABLE matches ADD COLUMN status_raw VARCHAR(16)"))

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT m.season, COALESCE(m.status_raw, '(null)') AS raw, COUNT(*) "
            "FROM matches m JOIN competitions c ON c.id = m.competition_id "
            "WHERE c.code = 'NHL' AND m.status = 'FINISHED' "
            "GROUP BY m.season, raw ORDER BY m.season, raw"
        )).all()
    print("\nNHL FINISHED rows by status_raw (receipt):")
    if not rows:
        print("  (no NHL finished rows)")
    for season, raw, n in rows:
        print(f"  {season}  {raw:<8} {n}")
    print("\nAll (null) = not re-synced yet: run a full NHL sync, then re-run this script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
