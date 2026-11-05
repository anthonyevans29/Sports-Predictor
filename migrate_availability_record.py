"""
Migration (2026-11-04, ARCHITECT addendum 252 item 1; lane availability-record): creates the availability record's two
tables, availability_observations and availability_assertions ("Two tables, both created by one migration, both
written by ingest commands only, both read mode=ro by everything else"), and their triggers: UPDATE and DELETE abort on
both ("NOTHING UPDATES OR DELETES A ROW"), and the two insert guards (the source and kind vocabularies; an assertion
only on the newest observation, an existing complete or partial one, with its sport and its fetched_at as
recorded_at), and the snapshot hash guard (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 1: an assertion of a
snapshot source whose observation keeps no payload_sha256 is refused; a trigger of its own, so a store migrated before
it gains it on its next run, as the recorded-clock index below). The receipt reads the triggers present before any
table is created, so a DB from before the record says
"+ Created trigger" for each on its first run and "· Kept trigger" on the next.

Additive and idempotent: creates the tables if missing, CREATE TRIGGER IF NOT EXISTS for each trigger, CREATE INDEX IF
NOT EXISTS for each index the two models declare, plus the one-row migration marker availability_record_migration; never
deletes or rewrites; touches no other table. Run twice, it keeps one set of each and says so.

THE INDEXES ON A STORE MIGRATED BEFORE (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 4: "AN INDEX IS ALLOWED in this
PR if the query needs one: it joins #831's migration (additive, idempotent, the same marker file or its own, named in
the PR body) and rides the SAME next tag"): #841 adds ix_avail_asr_sport_recorded (sport, recorded_at), the as-of
read's time cut under the recorded clock. A table this script finds already there gets every declared index it lacks,
by CREATE INDEX IF NOT EXISTS, on every run; the marker is unchanged (it says the tables were made by this backed-up
script; an index is never a reason to write or refuse). The receipt reads the indexes present before any table is
created, as for the triggers: "+ Created index" or "· Kept index", each by name.

WHY THE MARKER (the convention of migrate_cup_lineup_observations.py, Codex on #333): both models are mapped in
Base.metadata, so any init_db() (create_all) creates empty tables (with their triggers); the tables' existence does not
prove this backed-up migration ran. The marker is created HERE ONLY, by Core SQL. The record writes only when both
tables AND the marker exist.

RUN ORDER: take the daily .backup first (law 5); on the host, sp_deploy prints the exact `--run-migrations` command
(backup + this, under one lock). Addendum 252 item 7: "Thursday's migration tag does not carry any of it."

Usage:
    python migrate_availability_record.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateIndex

from src.availability.record import MIGRATION_MARKER, TABLES, TRIGGERS
from src.db.database import get_engine
from src.db.migrate_guard import refuse_missing_db
from src.db.schema import AVAILABILITY_TRIGGERS, AvailabilityAssertion, AvailabilityObservation
from src.timeutil import utc_now_naive


def main() -> int:
    engine = get_engine()
    if refuse_missing_db(engine):                               # law 5: a migration never creates a database
        return 1
    names = inspect(engine).get_table_names()
    if "matches" not in names:
        print("✗ matches table doesn't exist — not a sports_predictor DB; nothing to migrate.")
        return 1
    # the triggers present BEFORE this run, read before any table is created: creating a table fires schema.py's
    # after_create hooks, which create its triggers, so a later read would call every one of them "Kept" (law 2)
    with engine.connect() as conn:
        before = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'trigger'"))}
        before_ix = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'index'"))}
    for model in (AvailabilityObservation, AvailabilityAssertion):           # the observations first (the key)
        t = model.__tablename__
        if t in names:
            print(f"· {t} already exists.")
        else:
            print(f"+ Creating {t}...")
            model.__table__.create(engine, checkfirst=True)
    with engine.begin() as conn:
        for name, _table, sql in AVAILABILITY_TRIGGERS:
            conn.execute(text(sql))
            print(("· Kept" if name in before else "+ Created") + f" trigger {name}")
        for model in (AvailabilityObservation, AvailabilityAssertion):       # addendum 262 item 4: additive, by name
            for ix in sorted(model.__table__.indexes, key=lambda i: i.name):
                conn.execute(CreateIndex(ix, if_not_exists=True))
                print(("· Kept" if ix.name in before_ix else "+ Created") + f" index {ix.name}")
        conn.execute(text(f"CREATE TABLE IF NOT EXISTS {MIGRATION_MARKER} ("
                          "id INTEGER PRIMARY KEY CHECK (id = 1), script VARCHAR(64) NOT NULL, "
                          "migrated_at DATETIME NOT NULL)"))
        added = conn.execute(text(f"INSERT OR IGNORE INTO {MIGRATION_MARKER} (id, script, migrated_at) "
                                  "VALUES (1, 'migrate_availability_record.py', :at)"),
                             {"at": utc_now_naive().isoformat(sep=" ")}).rowcount
        at = conn.execute(text(f"SELECT migrated_at FROM {MIGRATION_MARKER} WHERE id = 1")).scalar()
    print(("+ Wrote" if added else "· Kept") + f" migration marker {MIGRATION_MARKER} (migrated_at {at}); "
          "the record writes only with this marker present.")
    with engine.connect() as conn:
        have = sorted(r[0] for r in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name IN (:a, :b)"),
            {"a": TABLES[0], "b": TABLES[1]}))
        have_ix = {r[0] for r in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name IN (:a, :b)"),
            {"a": TABLES[0], "b": TABLES[1]})}
        n_obs, last = conn.execute(text(f"SELECT COUNT(*), MAX(fetched_at) FROM {TABLES[0]}")).one()
        n_asr = conn.execute(text(f"SELECT COUNT(*) FROM {TABLES[1]}")).scalar()
    missing = sorted(set(TRIGGERS) - set(have))
    print(f"\ntriggers on the record ({len(have)}): {', '.join(have)}")
    if missing:                                                 # law 2: the receipt says what is not there
        print(f"✗ MISSING trigger(s): {', '.join(missing)}")
        return 1
    want_ix = sorted(ix.name for m in (AvailabilityObservation, AvailabilityAssertion) for ix in m.__table__.indexes)
    missing_ix = sorted(set(want_ix) - have_ix)
    print(f"indexes on the record ({len(want_ix) - len(missing_ix)} of {len(want_ix)} declared): {', '.join(want_ix)}")
    if missing_ix:
        print(f"✗ MISSING index(es): {', '.join(missing_ix)}")
        return 1
    print(f"{TABLES[0]}: {n_obs} observation(s) stored; latest fetched_at {last or '—'}")
    print(f"{TABLES[1]}: {n_asr} assertion(s) stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
