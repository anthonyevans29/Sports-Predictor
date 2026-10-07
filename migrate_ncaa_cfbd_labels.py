"""
Migration (2026-10-07, ARCHITECT item 6, NCAA CFBD LABEL LANE, #176 probe read):
creates ncaa_cfbd_labels — the side table keyed by our match id that carries
CollegeFootballData's orientation (same / swapped), neutral flag, both scores
(in OUR orientation) and season for NCAA matches (ruling (1)). The matches
table is never rewritten.

Additive and idempotent: creates one table (and its indexes) if missing;
never deletes or rewrites anything.

RUN ORDER: take the daily .backup first (law 5); on the host, sp_deploy
prints the exact `--run-migrations` command (backup + this, under one lock).
Until it runs, `ncaa-cfbd-labels` refuses to write (a --dry-run still works)
and the NCAA stream reads every game from the matches row (100% uncovered).

Usage:
    python migrate_ncaa_cfbd_labels.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.schema import NCAACFBDLabel


def main() -> int:
    engine = get_engine()
    names = inspect(engine).get_table_names()
    if "matches" not in names:
        print("✗ matches table doesn't exist — not a sports_predictor DB; nothing to migrate.")
        return 1
    if "ncaa_cfbd_labels" in names:
        print("· ncaa_cfbd_labels already exists.")
    else:
        print("+ Creating ncaa_cfbd_labels...")
        NCAACFBDLabel.__table__.create(engine, checkfirst=True)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT season, COUNT(*) FROM ncaa_cfbd_labels GROUP BY season "
                                 "ORDER BY season")).all()
    print("\nncaa_cfbd_labels rows by season: " + (" · ".join(f"{s} {n}" for s, n in rows) or "none yet")
          + "  (filled by `python cli.py ncaa-cfbd-labels --year 2025 --year 2026`)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
