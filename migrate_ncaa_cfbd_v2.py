"""
Migration (2026-10-08, ARCHITECT addendum 10 item 3 J4 + addendum 11 item 2 L1):
the CFBD label lane's second schema step, in ONE additive, idempotent script.

Architect (addendum 11): "If one migrate script can add the column and create
the table while staying additive and idempotent, make it one."

1. J4 (verbatim): "The side table stores CFBD's seasonType as served: a
   nullable column with its own migrate script, filled on the next ingest,
   carried on Game as data only. Nothing in matches or teams is rewritten by
   any of this."
   -> ncaa_cfbd_labels.season_type VARCHAR(32) NULL (added if missing).
2. L1 (verbatim): "Every non-dry ingest writes one ingest record per season to
   a new table with its own additive migrate script: season, division,
   fetched_at, payload_file, records, in scope, joined, and the unlabelled
   games as the receipt lists them. A run that joins nothing still writes its
   record."
   -> ncaa_cfbd_ingest_records (created if missing).

Never deletes or rewrites a row; existing labels keep season_type NULL until
the next ingest fills it. Running it twice is a no-op the second time.

RUN ORDER: take the daily .backup first (law 5); migrate_ncaa_cfbd_labels.py
must have run (it creates the side table). Until this runs, `ncaa-cfbd-labels`
refuses to write (a --dry-run still works), the readers carry season_type as
None, and coverage reads "no ingest record" (NOT covered) for every season.

Usage:
    python migrate_ncaa_cfbd_v2.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.schema import NCAACFBDIngestRecord


def main() -> int:
    engine = get_engine()
    names = inspect(engine).get_table_names()
    if "matches" not in names:
        print("✗ matches table doesn't exist — not a sports_predictor DB; nothing to migrate.")
        return 1
    if "ncaa_cfbd_labels" not in names:
        print("✗ ncaa_cfbd_labels doesn't exist — run `python migrate_ncaa_cfbd_labels.py` first.")
        return 1
    cols = {c["name"] for c in inspect(engine).get_columns("ncaa_cfbd_labels")}
    with engine.begin() as conn:
        if "season_type" in cols:
            print("· ncaa_cfbd_labels.season_type already exists.")
        else:
            print("+ Adding ncaa_cfbd_labels.season_type...")
            conn.execute(text("ALTER TABLE ncaa_cfbd_labels ADD COLUMN season_type VARCHAR(32)"))
    if "ncaa_cfbd_ingest_records" in names:
        print("· ncaa_cfbd_ingest_records already exists.")
    else:
        print("+ Creating ncaa_cfbd_ingest_records...")
        NCAACFBDIngestRecord.__table__.create(engine, checkfirst=True)
    with engine.connect() as conn:
        lab = conn.execute(text("SELECT season, COALESCE(season_type, '(null)') AS st, COUNT(*) "
                                "FROM ncaa_cfbd_labels GROUP BY season, st ORDER BY season, st")).all()
        rec = conn.execute(text("SELECT season, COUNT(*), MAX(fetched_at) FROM ncaa_cfbd_ingest_records "
                                "GROUP BY season ORDER BY season")).all()
    print("\nncaa_cfbd_labels by season and season_type: "
          + (" · ".join(f"{s} {t} {n}" for s, t, n in lab) or "none yet"))
    print("ncaa_cfbd_ingest_records by season: "
          + (" · ".join(f"{s} {n} record(s), latest {at}" for s, n, at in rec) or "none yet"))
    print("Both fill on the next non-dry `python cli.py ncaa-cfbd-labels` run (division fbs only, L4).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
