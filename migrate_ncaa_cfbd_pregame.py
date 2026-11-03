"""
Migration (2026-11-03, ARCHITECT addendum 236 item 3(1)): CFBD's pregame neutral-site flag, in ONE additive,
idempotent script.

Architect (addendum 236 item 3(1), verbatim in part): "THE NEUTRAL FLAG: option (iii) — CFBD's pregame neutral-site
field for the fixture, read at the labels ingest and ruled as ours with its rule stated on every row ("neutral per
CFBD's pregame field, read <stamp>; absent: unknown, D8"); (iv)'s "unknown" where CFBD has none; never a hand table
for the current season".

1. ncaa_cfbd_pregame (created if missing; src/db/schema.py NCAACFBDPregame): one row per stored NCAA fixture joined
   to a not-completed CFBD game, CFBD's neutralSite as served, the run's fetched_at. Never a label.
2. The one-row migration marker ncaa_cfbd_pregame_migration (created if missing, row written if missing). WHY:
   NCAACFBDPregame is mapped, so any init_db() creates the table; its existence does not prove this backed-up
   migration ran. The marker is created HERE ONLY, by Core SQL, unmapped (the migrate_ncaa_cfbd_week.py
   convention), and the ingest writes the pregame rows only when the table AND this marker exist.

Never deletes or rewrites a row. Running it twice changes nothing the second time.

RUN ORDER: take the daily .backup first (law 5); migrate_ncaa_cfbd_labels.py and migrate_ncaa_cfbd_v2.py must have
run. Until this runs, `ncaa-cfbd-labels` writes the labels as before and says it did not write the pregame rows, and
every college shadow row reads the neutral flag unknown (D8). After it, one non-dry `ncaa-cfbd-labels --year 2026`
fills the rows.

Usage:
    python migrate_ncaa_cfbd_pregame.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.migrate_guard import refuse_missing_db
from src.db.schema import NCAACFBDPregame
from src.ingestion.ncaa_cfbd import PREGAME_MIGRATION_MARKER, PREGAME_TABLE, V2_MIGRATION_MARKER
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
    if PREGAME_TABLE in names:
        print(f"· {PREGAME_TABLE} already exists.")
    else:
        print(f"+ Creating {PREGAME_TABLE}...")
        NCAACFBDPregame.__table__.create(engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE IF NOT EXISTS {PREGAME_MIGRATION_MARKER} ("
                          "id INTEGER PRIMARY KEY CHECK (id = 1), script VARCHAR(64) NOT NULL, "
                          "migrated_at DATETIME NOT NULL)"))
        added = conn.execute(text(f"INSERT OR IGNORE INTO {PREGAME_MIGRATION_MARKER} (id, script, migrated_at) "
                                  "VALUES (1, 'migrate_ncaa_cfbd_pregame.py', :at)"),
                             {"at": utc_now_naive().isoformat(sep=" ")}).rowcount
        at = conn.execute(text(f"SELECT migrated_at FROM {PREGAME_MIGRATION_MARKER} WHERE id = 1")).scalar()
    print(("+ Wrote" if added else "· Kept") + f" migration marker {PREGAME_MIGRATION_MARKER} (migrated_at {at}); "
          "the ingest writes the pregame rows only with this marker present.")
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT season, COUNT(*), COUNT(neutral) FROM {PREGAME_TABLE} "
                                 "GROUP BY season ORDER BY season")).all()
    print(f"\n{PREGAME_TABLE} by season (rows · with a flag): "
          + (" · ".join(f"{s} {n} · {w}" for s, n, w in rows) or "none yet"))
    print("The rows fill on the next non-dry `python cli.py ncaa-cfbd-labels --year YYYY` run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
