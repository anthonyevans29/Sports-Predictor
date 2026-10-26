"""
Migration (2026-10-23, ARCHITECT addendum 158 item 1(a); ncaa-elo-v2 D10): CFBD's week on the label table, in ONE
additive, idempotent script.

Architect (addendum 158 item 1(a), verbatim in part): "The 2023 ingest (D10: the CFBD 2023 both-FBS labels with the
WEEK persisted on NCAACFBDLabel — the second read scores from week 5, so the field is a precondition — plus the
provider's 2023 listing)". The spec (docs/specs/ncaa-elo-v2.md section 6): "The week. CFBD's `week` as served."

1. ncaa_cfbd_labels.week INTEGER NULL (added if missing). Existing labels keep week NULL until the next ingest of
   their season fills it (a re-ingest stamps them with that run's fetched_at, L3).
2. The one-row migration marker ncaa_cfbd_week_migration (created if missing, row written if missing). WHY: a
   ncaa_cfbd_labels created by init_db() from the current ORM carries the column, so its existence does not prove
   this backed-up migration ran. The marker is created HERE ONLY, by Core SQL, unmapped (the
   migrate_ncaa_cfbd_v2.py convention), and the ingest writes only when the column AND this marker exist.

Never deletes or rewrites a row. Running it twice changes nothing the second time.

RUN ORDER: take the daily .backup first (law 5); migrate_ncaa_cfbd_labels.py and migrate_ncaa_cfbd_v2.py must have
run. Until this runs, `ncaa-cfbd-labels` refuses to write (a --dry-run still works) and the readers carry the week as
None (D10: every game reads week unknown).

Usage:
    python migrate_ncaa_cfbd_week.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.migrate_guard import refuse_missing_db
from src.ingestion.ncaa_cfbd import V2_MIGRATION_MARKER, WEEK_COLUMN, WEEK_MIGRATION_MARKER
from src.timeutil import utc_now_naive


def main() -> int:
    engine = get_engine()
    if refuse_missing_db(engine):                               # law 5: a migration never creates a database
        return 1
    names = inspect(engine).get_table_names()
    if "matches" not in names:
        print("✗ matches table doesn't exist — not a sports_predictor DB; nothing to migrate.")
        return 1
    if "ncaa_cfbd_labels" not in names:
        print("✗ ncaa_cfbd_labels doesn't exist — run `python migrate_ncaa_cfbd_labels.py` first.")
        return 1
    if V2_MIGRATION_MARKER not in names:
        print(f"✗ no {V2_MIGRATION_MARKER} — run `python migrate_ncaa_cfbd_v2.py` first.")
        return 1
    cols = {c["name"] for c in inspect(engine).get_columns("ncaa_cfbd_labels")}
    with engine.begin() as conn:
        if WEEK_COLUMN in cols:
            print(f"· ncaa_cfbd_labels.{WEEK_COLUMN} already exists.")
        else:
            print(f"+ Adding ncaa_cfbd_labels.{WEEK_COLUMN}...")
            conn.execute(text(f"ALTER TABLE ncaa_cfbd_labels ADD COLUMN {WEEK_COLUMN} INTEGER"))
        conn.execute(text(f"CREATE TABLE IF NOT EXISTS {WEEK_MIGRATION_MARKER} ("
                          "id INTEGER PRIMARY KEY CHECK (id = 1), script VARCHAR(64) NOT NULL, "
                          "migrated_at DATETIME NOT NULL)"))
        added = conn.execute(text(f"INSERT OR IGNORE INTO {WEEK_MIGRATION_MARKER} (id, script, migrated_at) "
                                  "VALUES (1, 'migrate_ncaa_cfbd_week.py', :at)"),
                             {"at": utc_now_naive().isoformat(sep=" ")}).rowcount
        at = conn.execute(text(f"SELECT migrated_at FROM {WEEK_MIGRATION_MARKER} WHERE id = 1")).scalar()
    print(("+ Wrote" if added else "· Kept") + f" migration marker {WEEK_MIGRATION_MARKER} (migrated_at {at}); "
          "the ingest writes only with this marker present.")
    with engine.connect() as conn:
        lab = conn.execute(text(f"SELECT season, COUNT(*), COUNT({WEEK_COLUMN}) FROM ncaa_cfbd_labels "
                                "GROUP BY season ORDER BY season")).all()
    print(f"\nncaa_cfbd_labels by season (rows · with a week): "
          + (" · ".join(f"{s} {n} · {w}" for s, n, w in lab) or "none yet"))
    print("The week fills on the next non-dry `python cli.py ncaa-cfbd-labels --year YYYY` run of each season.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
