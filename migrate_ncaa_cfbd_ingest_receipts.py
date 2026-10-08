"""
Migration (2026-10-08, ARCHITECT addendum 10 item 3, SCOPE; Codex on #362):
creates ncaa_cfbd_ingest_receipts — the persisted CFBD ingest receipt, one row
per season per NON-DRY `ncaa-cfbd-labels` run, written even when nothing joins.

Ruling (SCOPE, verbatim excerpt): "the side table labels at least 95% of CFBD's
completed both-FBS games in each season used, read from the ingest receipt
(joined over in scope), every unmatched game listed. The shadow's precondition
is that same fact."

Why a DB table (not a file): the host and the laptop each have their own DB,
and exports/ is mirrored and pruned; the receipt belongs next to the side table
it describes. Coverage (`ncaa-cfbd-coverage`, the NCAA shadow's precondition)
and the v1r stream's admitted labels read the LATEST receipt per season.

Additive and idempotent: creates one table (and its index) if missing; never
deletes or rewrites anything. A separate script from
migrate_ncaa_cfbd_season_type.py, which stays J4's own.

RUN ORDER: take the daily .backup first (law 5); migrate_ncaa_cfbd_labels.py
must have run. Until this runs, `ncaa-cfbd-labels` refuses to write (a
--dry-run still works) and coverage reads "no persisted ingest receipt"
(NOT met) for every season.

Usage:
    python migrate_ncaa_cfbd_ingest_receipts.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.schema import NCAACFBDIngestReceipt


def main() -> int:
    engine = get_engine()
    names = inspect(engine).get_table_names()
    if "matches" not in names:
        print("✗ matches table doesn't exist — not a sports_predictor DB; nothing to migrate.")
        return 1
    if "ncaa_cfbd_labels" not in names:
        print("✗ ncaa_cfbd_labels doesn't exist — run `python migrate_ncaa_cfbd_labels.py` first.")
        return 1
    if "ncaa_cfbd_ingest_receipts" in names:
        print("· ncaa_cfbd_ingest_receipts already exists.")
    else:
        print("+ Creating ncaa_cfbd_ingest_receipts...")
        NCAACFBDIngestReceipt.__table__.create(engine, checkfirst=True)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT season, COUNT(*), MAX(run_at) FROM ncaa_cfbd_ingest_receipts "
                                 "GROUP BY season ORDER BY season")).all()
    print("\nncaa_cfbd_ingest_receipts by season: "
          + (" · ".join(f"{s} {n} run(s), latest {at}" for s, n, at in rows) or "none yet")
          + "  (written by every non-dry `python cli.py ncaa-cfbd-labels` run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
