"""
Migration (2026-10-08, ARCHITECT addendum 10 item 3, J4): ncaa_cfbd_labels.season_type
— CollegeFootballData's seasonType as served, on the CFBD side table.

Ruling (verbatim): "J4. The side table stores CFBD's seasonType as served: a
nullable column with its own migrate script, filled on the next ingest, carried
on Game as data only. Nothing in matches or teams is rewritten by any of this."

Adds to ncaa_cfbd_labels:
  - season_type  VARCHAR(32)  NULL  (NULL until the next `ncaa-cfbd-labels` run)

Additive and idempotent: safe to run multiple times; adds one nullable column
if missing; never deletes or rewrites a row (existing rows keep NULL until the
next ingest fills them).

RUN ORDER: take the daily .backup first (law 5), then run this BEFORE the next
ingest. migrate_ncaa_cfbd_labels.py must have run first (it creates the table;
on a DB where it creates the table now, the column is already there and this
script is a no-op). Until this runs, `ncaa-cfbd-labels` refuses to write (a
--dry-run still works) and the readers (ncaa-backtest, ncaa-cfbd-coverage, the
NCAA shadow) read every other column and carry season_type as None.

Usage:
    python migrate_ncaa_cfbd_season_type.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine


def main() -> int:
    engine = get_engine()
    names = inspect(engine).get_table_names()
    if "matches" not in names:
        print("✗ matches table doesn't exist — not a sports_predictor DB; nothing to migrate.")
        return 1
    if "ncaa_cfbd_labels" not in names:
        print("✗ ncaa_cfbd_labels doesn't exist — run `python migrate_ncaa_cfbd_labels.py` first "
              "(it creates the table with this column).")
        return 1
    cols = {c["name"] for c in inspect(engine).get_columns("ncaa_cfbd_labels")}
    with engine.begin() as conn:
        if "season_type" in cols:
            print("· ncaa_cfbd_labels.season_type already exists.")
        else:
            print("+ Adding ncaa_cfbd_labels.season_type...")
            conn.execute(text("ALTER TABLE ncaa_cfbd_labels ADD COLUMN season_type VARCHAR(32)"))
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT season, COALESCE(season_type, '(null)') AS st, COUNT(*) "
                                 "FROM ncaa_cfbd_labels GROUP BY season, st ORDER BY season, st")).all()
    print("\nncaa_cfbd_labels rows by season and season_type (receipt): "
          + (" · ".join(f"{s} {t} {n}" for s, t, n in rows) or "none yet"))
    print("All (null) = not re-ingested since migrating: run `python cli.py ncaa-cfbd-labels` (filled as served).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
