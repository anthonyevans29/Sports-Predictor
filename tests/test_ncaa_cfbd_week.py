"""ncaa-elo-v2 D10, THE WEEK (ARCHITECT 2026-10-23, addendum 158 item 1(a): "the CFBD 2023 both-FBS labels with the
WEEK persisted on NCAACFBDLabel — the second read scores from week 5, so the field is a precondition — plus the
provider's 2023 listing"). Pins, on synthetic fixtures only (season 2084; the API is never reached):
- CFBD's week as served: an integer is stored as it is; a week served as anything else is stored NULL and counted;
  a payload with no week field stores NULL and the receipt says NOT SERVED;
- the receipt counts the joined rows by season_type and week, and the stored NCAA matches of the year by status;
- migrate_ncaa_cfbd_week.py is additive and idempotent and writes its own marker; an init_db()-created column without
  the marker refuses a non-dry ingest (a dry run still works); drop_db() drops the marker;
- the readers carry the week (Game.week) once stored, and read None on a DB without the column."""
import json

import pytest
from sqlalchemy import inspect, select, text

from src.db.schema import NCAACFBDLabel
from src.ingestion import ncaa_cfbd as nc
from src.walters import ncaa_backtest as nb
from tests.test_ncaa_cfbd_scope_join import J4_RECS, _old_schema, _world, rec

WEEKS = {9501: 1, 9502: 1, 9503: 2, 9504: 3}                  # postseason week 1 as CFBD serves it
RECS = [dict(r, week=WEEKS[r["id"]]) for r in J4_RECS]


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db

    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    return eng


def _payload(tmp_path, monkeypatch, recs=RECS):
    monkeypatch.setattr(nc, "ALIAS_FILE", tmp_path / "aliases.json")
    (tmp_path / "aliases.json").write_text(json.dumps({"aliases": {}}))
    f = tmp_path / "cfbd_games_2084.json"
    f.write_text(json.dumps(recs))
    return f


def _migrated_to_v2(eng):
    """init_db() + the labels and v2 migrations (their markers): the week column exists (create_all made it from the
    current ORM), the week marker does not."""
    import migrate_ncaa_cfbd_labels as mig
    import migrate_ncaa_cfbd_v2 as mig2
    from src.db.database import init_db, session_scope

    init_db()
    assert mig.main() == 0 and mig2.main() == 0
    with session_scope() as s:
        return _world(s)


def _weeks_stored(eng) -> dict:
    with eng.connect() as conn:
        return dict(conn.execute(text("SELECT source_game_id, week FROM ncaa_cfbd_labels")).all())


# --- the week as served ------------------------------------------------------------------------------------------

def test_served_week_keeps_an_integer_and_nothing_else():
    assert nc.served_week(5) == (5, True) and nc.served_week(0) == (0, True)
    assert nc.served_week(None) == (None, True)                                   # not served: unknown, not wrong
    for bad in ("5", 5.0, True, [5]):
        assert nc.served_week(bad) == (None, False)                               # never parsed into a number


def test_build_labels_carries_the_week_and_counts_by_season_type_and_week(fresh_db):
    ms = _migrated_to_v2(fresh_db)
    recs = RECS + [rec(9505, "J4 B", "J4 A", 7, 3, "2084-09-27T19:00:00.000Z", week="5"),   # served as a string
                   rec(9506, "J4 D", "J4 C", 9, 6, "2084-10-04T19:00:00.000Z")]             # no week on the record
    from src.db.database import session_scope
    with session_scope() as s:
        from datetime import datetime
        teams = nc.ncaa_teams(s)
        ours = nc.load_ours(s, datetime(2084, 9, 1), datetime(2084, 12, 31), teams)
        keys, missing = nc.discover(recs[0])
        r = nc.build_labels(recs, keys, ours, teams, {}, 2084, "fbs")
        s.rollback()
    assert missing == [] and keys["week"] == "week" and r.week_field == "week"
    by = {row["match_id"]: row for row in r.rows}
    assert by[ms["reg"]]["week"] == 1 and by[ms["post"]]["week"] == 1
    assert r.weeks == {("regular", 1): 1, ("postseason", 1): 1}                     # the two joined rows
    assert r.counts["week_not_integer"] == 0                                        # 9505/9506 do not join (no match)
    line = nc.week_line(r)
    assert "read from 'week'" in line and "postseason: 1 1 | regular: 1 1" in line
    assert line.endswith("served but not an integer (stored NULL) 0")


def test_a_week_served_as_a_string_is_stored_null_and_counted():
    from datetime import datetime
    teams = {1: "W A", 2: "W B"}
    ours = [nc.Ours(10, datetime(2084, 9, 6, 19), "2084", 1, 2, nc.our_norm("W A"), nc.our_norm("W B"), 31, 10)]
    recs = [rec(9601, "W A", "W B", 31, 10, "2084-09-06T19:00:00.000Z", week="1")]
    keys, _ = nc.discover(recs[0])
    r = nc.build_labels(recs, keys, ours, teams, {}, 2084, "fbs")
    assert r.rows[0]["week"] is None and r.counts["week_not_integer"] == 1
    assert r.weeks == {("regular", None): 1}
    assert "regular: unknown 1" in nc.week_line(r) and nc.week_line(r).endswith("(stored NULL) 1")


def test_a_payload_without_a_week_field_says_not_served():
    from datetime import datetime
    teams = {1: "W A", 2: "W B"}
    ours = [nc.Ours(10, datetime(2084, 9, 6, 19), "2084", 1, 2, nc.our_norm("W A"), nc.our_norm("W B"), 31, 10)]
    recs = [rec(9601, "W A", "W B", 31, 10, "2084-09-06T19:00:00.000Z")]
    keys, _ = nc.discover(recs[0])
    r = nc.build_labels(recs, keys, ours, teams, {}, 2084, "fbs")
    assert keys["week"] is None and r.rows[0]["week"] is None
    assert "NOT SERVED: the payload has no week field" in nc.week_line(r)


# --- the migration, its marker and the ingest ------------------------------------------------------------------

def test_init_db_column_without_the_marker_refuses_then_the_migration_unlocks_and_fills(fresh_db, tmp_path,
                                                                                       monkeypatch, capsys):
    import migrate_ncaa_cfbd_week as mig_week
    from src.db.database import session_scope

    ms = _migrated_to_v2(fresh_db)
    f = _payload(tmp_path, monkeypatch)
    assert "week" in {c["name"] for c in inspect(fresh_db).get_columns("ncaa_cfbd_labels")}   # create_all made it
    with session_scope() as s:
        assert nc.v2_migrated(s) and nc.has_week(s) and not nc.week_migrated(s)
    with pytest.raises(nc.CFBDError, match="no migration marker ncaa_cfbd_week_migration") as e:
        nc.run([2084], from_file=str(f), out=lambda *_: None)
    assert "take the .backup, then run `python migrate_ncaa_cfbd_week.py`" in str(e.value)
    assert _weeks_stored(fresh_db) == {}                                            # nothing written
    lines = []
    assert nc.run([2084], from_file=str(f), dry_run=True, out=lines.append) == 0    # a dry run still works
    out = "\n".join(lines)
    assert "OUR STORED NCAA MATCHES of season 2084" in out and ": 3 · finished 3" in out
    assert "WEEK (D10, CFBD week as served; read from 'week')" in out and _weeks_stored(fresh_db) == {}

    capsys.readouterr()
    assert mig_week.main() == 0
    out = capsys.readouterr().out
    assert "· ncaa_cfbd_labels.week already exists." in out and "+ Wrote migration marker ncaa_cfbd_week_migration" in out
    assert mig_week.main() == 0 and "· Kept migration marker ncaa_cfbd_week_migration" in capsys.readouterr().out
    with fresh_db.connect() as conn:
        assert conn.execute(text(f"SELECT id, script FROM {nc.WEEK_MIGRATION_MARKER}")).all() == [
            (1, "migrate_ncaa_cfbd_week.py")]
    lines = []
    assert nc.run([2084], from_file=str(f), out=lines.append) == 0
    assert _weeks_stored(fresh_db) == {9501: 1, 9502: 1}
    games = {g.match_id: g for g in nb.load_v1r_games(("2084",))}
    assert games[ms["reg"]].week == 1 and games[ms["post"]].week == 1
    assert {g.match_id: g.week for g in nb.load_games()}[ms["fcs"]] is None          # no label: no week


def test_a_pre_week_db_reads_week_none_and_the_migration_adds_the_column(fresh_db, tmp_path, monkeypatch, capsys):
    """The laptop case: labels written before the column existed. Readers never fail and read week None; the
    migration adds the column (rows keep NULL); the next ingest fills it (rows updated, never deleted)."""
    import migrate_ncaa_cfbd_v2 as mig2
    import migrate_ncaa_cfbd_week as mig_week
    from src.db.database import session_scope

    _old_schema(fresh_db)
    with session_scope() as s:
        ms = _world(s)
    f = _payload(tmp_path, monkeypatch)
    assert mig2.main() == 0
    with session_scope() as s:
        assert not nc.has_week(s) and not nc.week_migrated(s)
    assert {g.match_id: g.week for g in nb.load_games()} == {ms["reg"]: None, ms["post"]: None, ms["fcs"]: None}
    with pytest.raises(nc.CFBDError, match="migrate_ncaa_cfbd_week.py"):
        nc.run([2084], from_file=str(f), out=lambda *_: None)
    capsys.readouterr()
    assert mig_week.main() == 0 and "+ Adding ncaa_cfbd_labels.week" in capsys.readouterr().out
    col = {c["name"]: c for c in inspect(fresh_db).get_columns("ncaa_cfbd_labels")}["week"]
    assert col["nullable"] is True
    lines = []
    assert nc.run([2084], from_file=str(f), out=lines.append) == 0
    assert _weeks_stored(fresh_db) == {9501: 1, 9502: 1}
    again = []
    assert nc.run([2084], from_file=str(f), out=again.append) == 0
    assert any("inserted 0 · updated 0 · unchanged 2" in x for x in again)


def test_a_reingest_after_the_migration_fills_the_week_on_rows_written_without_it(fresh_db, tmp_path, monkeypatch):
    import migrate_ncaa_cfbd_week as mig_week
    from src.db.database import session_scope

    _migrated_to_v2(fresh_db)
    assert mig_week.main() == 0
    no_week = _payload(tmp_path, monkeypatch, recs=J4_RECS)
    assert nc.run([2084], from_file=str(no_week), out=lambda *_: None) == 0
    assert _weeks_stored(fresh_db) == {9501: None, 9502: None}
    f = tmp_path / "with_week.json"
    f.write_text(json.dumps(RECS))
    lines = []
    assert nc.run([2084], from_file=str(f), out=lines.append) == 0
    assert any("inserted 0 · updated 2 · unchanged 0" in x for x in lines)
    assert _weeks_stored(fresh_db) == {9501: 1, 9502: 1}
    with session_scope() as s:
        assert {r.week for r in s.execute(select(NCAACFBDLabel)).scalars()} == {1}


def test_the_migration_refuses_before_the_v2_migration(fresh_db, capsys):
    import migrate_ncaa_cfbd_labels as mig
    import migrate_ncaa_cfbd_week as mig_week
    from src.db.database import init_db

    init_db()
    assert mig.main() == 0
    capsys.readouterr()
    assert mig_week.main() == 1 and "run `python migrate_ncaa_cfbd_v2.py` first" in capsys.readouterr().out
    assert not inspect(fresh_db).has_table(nc.WEEK_MIGRATION_MARKER)


def test_drop_db_drops_the_week_marker(fresh_db):
    import migrate_ncaa_cfbd_week as mig_week
    from src.db.database import drop_db, init_db, session_scope

    _migrated_to_v2(fresh_db)
    assert mig_week.main() == 0 and inspect(fresh_db).has_table(nc.WEEK_MIGRATION_MARKER)
    drop_db()                                                                      # the init-db --force path
    init_db()
    assert not inspect(fresh_db).has_table(nc.WEEK_MIGRATION_MARKER)
    with session_scope() as s:
        assert nc.has_week(s) and not nc.week_migrated(s)
