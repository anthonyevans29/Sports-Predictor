"""
Migration (2026-10-23, ARCHITECT addendum 158 item 3(a), CUPS STEP B; lane cups, #106): creates
cup_lineup_observations, the one table `observe-cup-lineups` writes: the LIVE T-15 observation store, "per fixture the
scheduled poll time and the actual observation time, eleven team-mapped starters per side, the FIRST complete
observation preserved and every later correction appended (never replaced) [...] and explicit rows for failed, partial
or late observations." One row per (fixture, kickoff, poll), append-only: the unique key holds the stored kickoff, so
a re-dated fixture starts a fresh poll set and the old kickoff's rows are kept as they were (Codex on #662).

Additive and idempotent: creates the table if missing, plus the one-row migration marker
cup_lineup_observations_migration; never deletes or rewrites; touches no other table. Until it runs,
`observe-cup-lineups --dry-run` still reads and prints, and a run without --dry-run refuses.

WHY THE MARKER (the convention of migrate_kalshi_settled_markets.py and migrate_ncaa_cfbd_labels.py, Codex on #333):
CupLineupObservation is mapped in Base.metadata, so any init_db() (create_all) creates an empty table; the table's
existence does not prove this backed-up migration ran. The marker is created HERE ONLY, by Core SQL. The ingest writes
only when table AND marker exist.

RUN ORDER: take the daily .backup first (law 5); on the host, sp_deploy prints the exact `--run-migrations` command
(backup + this, under one lock).

Usage:
    python migrate_cup_lineup_observations.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.migrate_guard import refuse_missing_db
from src.db.schema import CupLineupObservation
from src.ingestion.cup_lineups_live import MIGRATION_MARKER, TABLE
from src.timeutil import utc_now_naive


def main() -> int:
    engine = get_engine()
    if refuse_missing_db(engine):                               # law 5: a migration never creates a database
        return 1
    names = inspect(engine).get_table_names()
    if "matches" not in names:
        print("✗ matches table doesn't exist — not a sports_predictor DB; nothing to migrate.")
        return 1
    if TABLE in names:
        print(f"· {TABLE} already exists.")
    else:
        print(f"+ Creating {TABLE}...")
        CupLineupObservation.__table__.create(engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE IF NOT EXISTS {MIGRATION_MARKER} ("
                          "id INTEGER PRIMARY KEY CHECK (id = 1), script VARCHAR(64) NOT NULL, "
                          "migrated_at DATETIME NOT NULL)"))
        added = conn.execute(text(f"INSERT OR IGNORE INTO {MIGRATION_MARKER} (id, script, migrated_at) "
                                  "VALUES (1, 'migrate_cup_lineup_observations.py', :at)"),
                             {"at": utc_now_naive().isoformat(sep=" ")}).rowcount
        at = conn.execute(text(f"SELECT migrated_at FROM {MIGRATION_MARKER} WHERE id = 1")).scalar()
    print(("+ Wrote" if added else "· Kept") + f" migration marker {MIGRATION_MARKER} (migrated_at {at}); "
          "observe-cup-lineups writes only with this marker present.")
    with engine.connect() as conn:
        n, last = conn.execute(text(f"SELECT COUNT(*), MAX(observed_at) FROM {TABLE}")).one()
    print(f"\n{TABLE}: {n} observation(s) stored; latest {last or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
