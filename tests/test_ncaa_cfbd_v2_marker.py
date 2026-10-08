"""#367 (Codex P2 on #362; ARCHITECT 2026-10-08, addendum 13 item 1): the v2 migration's own marker.

init_db() (create_all) creates ncaa_cfbd_ingest_records and, from the current ORM, ncaa_cfbd_labels.season_type,
so their existence does not prove migrate_ncaa_cfbd_v2.py (the post-backup migration) ran. Pins, on synthetic
fixtures only:
- init_db()-created table + column, no v2 marker -> a non-dry ingest refuses (a dry run still works);
- after the script -> the marker row exists -> the ingest proceeds;
- the script is idempotent (twice -> one marker row, the second run prints "Kept");
- a DB migrated by the pre-#367 script (objects present, no marker) -> re-running the script writes the marker
  and changes nothing else;
- drop_db() (init-db --force) drops the unmapped v2 marker with the rest."""
import json

import pytest
from sqlalchemy import inspect, text

from src.ingestion import ncaa_cfbd as nc
from tests.test_ncaa_cfbd_scope_join import J4_RECS, _world


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


def _labels_migrated(eng, tmp_path, monkeypatch):
    """init_db() + migrate_ncaa_cfbd_labels.py (its marker), a synthetic world, a payload file. The v2 objects
    exist (create_all made them); the v2 marker does not."""
    import migrate_ncaa_cfbd_labels as mig
    from src.db.database import init_db, session_scope

    init_db()
    assert mig.main() == 0
    with session_scope() as s:
        _world(s)
    monkeypatch.setattr(nc, "ALIAS_FILE", tmp_path / "aliases.json")
    (tmp_path / "aliases.json").write_text(json.dumps({"aliases": {}}))
    f = tmp_path / "cfbd_games_2084.json"
    f.write_text(json.dumps(J4_RECS))
    return f


def _records(eng) -> int:
    with eng.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM ncaa_cfbd_ingest_records")).scalar()


def _marker_rows(eng) -> list:
    with eng.connect() as conn:
        return conn.execute(text(f"SELECT id, script FROM {nc.V2_MIGRATION_MARKER}")).all()


def _snapshot(eng, skip=()) -> dict:
    """Every table's columns and rows (the marker tables excluded on request)."""
    insp = inspect(eng)
    out = {}
    with eng.connect() as conn:
        for t in sorted(insp.get_table_names()):
            if t in skip:
                continue
            cols = [c["name"] for c in insp.get_columns(t)]
            out[t] = (cols, sorted(map(tuple, conn.execute(text(f'SELECT * FROM "{t}"')).all()), key=repr))
    return out


def test_init_db_created_v2_objects_without_the_marker_refuse_a_non_dry_ingest(fresh_db, tmp_path, monkeypatch):
    from src.db.database import session_scope

    f = _labels_migrated(fresh_db, tmp_path, monkeypatch)
    insp = inspect(fresh_db)
    assert insp.has_table(nc.RECORD_TABLE)                                         # the incidental objects ...
    assert "season_type" in {c["name"] for c in insp.get_columns("ncaa_cfbd_labels")}
    assert not insp.has_table(nc.V2_MIGRATION_MARKER)                              # ... no marker
    with session_scope() as s:
        assert nc.migrated(s) and nc.records_ready(s) and nc.has_season_type(s) and not nc.v2_migrated(s)
    with pytest.raises(nc.CFBDError, match="no migration marker ncaa_cfbd_v2_migration") as e:
        nc.run([2084], from_file=str(f), out=lambda *_: None)
    assert "take the .backup, then run `python migrate_ncaa_cfbd_v2.py`" in str(e.value)
    assert _records(fresh_db) == 0                                                  # nothing written
    assert nc.run([2084], from_file=str(f), dry_run=True, out=lambda *_: None) == 0   # a dry run still works
    assert _records(fresh_db) == 0


def test_after_the_script_the_marker_unlocks_the_ingest_and_reruns_keep_one_row(fresh_db, tmp_path, monkeypatch,
                                                                               capsys):
    import migrate_ncaa_cfbd_v2 as mig2
    from src.db.database import session_scope

    f = _labels_migrated(fresh_db, tmp_path, monkeypatch)
    capsys.readouterr()
    assert mig2.main() == 0
    out = capsys.readouterr().out
    assert "+ Wrote migration marker ncaa_cfbd_v2_migration" in out
    assert "season_type already exists" in out and "ncaa_cfbd_ingest_records already exists" in out
    assert mig2.main() == 0                                                        # idempotent
    assert "· Kept migration marker ncaa_cfbd_v2_migration" in capsys.readouterr().out
    assert _marker_rows(fresh_db) == [(1, "migrate_ncaa_cfbd_v2.py")]
    with session_scope() as s:
        assert nc.v2_migrated(s)
    lines = []
    assert nc.run([2084], from_file=str(f), out=lines.append) == 0
    assert any(x.startswith("  WRITTEN ncaa_cfbd_labels:") for x in lines)
    assert _records(fresh_db) == 1


def test_a_db_migrated_before_the_marker_gets_the_marker_only(fresh_db, tmp_path, monkeypatch, capsys):
    """The laptop case: migrate_ncaa_cfbd_v2.py ran from the pre-#367 main (column added, table created, no
    marker). The ingest refuses; re-running the new script writes the marker and changes nothing else."""
    import migrate_ncaa_cfbd_v2 as mig2
    from src.db.database import session_scope

    f = _labels_migrated(fresh_db, tmp_path, monkeypatch)
    with fresh_db.begin() as conn:                         # the shipped #333 schema, then the pre-#367 script's work
        conn.execute(text("ALTER TABLE ncaa_cfbd_labels DROP COLUMN season_type"))
        conn.execute(text("DROP TABLE ncaa_cfbd_ingest_records"))
        conn.execute(text("ALTER TABLE ncaa_cfbd_labels ADD COLUMN season_type VARCHAR(32)"))
    from src.db.schema import NCAACFBDIngestRecord
    NCAACFBDIngestRecord.__table__.create(fresh_db, checkfirst=True)
    with fresh_db.begin() as conn:                         # data written before #367 must survive untouched
        conn.execute(text("INSERT INTO ncaa_cfbd_ingest_records (season, division, fetched_at, payload_file, "
                          "records, in_scope, joined, unlabelled) VALUES ('2083', 'fbs', '2026-10-07 12:00:00', "
                          "NULL, 0, 0, 0, '[]')"))
    with session_scope() as s:
        assert not nc.v2_migrated(s)
    with pytest.raises(nc.CFBDError, match="migrate_ncaa_cfbd_v2.py"):              # no lockout beyond one re-run
        nc.run([2084], from_file=str(f), out=lambda *_: None)
    before = _snapshot(fresh_db)
    assert nc.V2_MIGRATION_MARKER not in before
    capsys.readouterr()
    assert mig2.main() == 0
    out = capsys.readouterr().out
    assert "· ncaa_cfbd_labels.season_type already exists." in out
    assert "· ncaa_cfbd_ingest_records already exists." in out
    assert "+ Wrote migration marker ncaa_cfbd_v2_migration" in out
    assert _snapshot(fresh_db, skip={nc.V2_MIGRATION_MARKER}) == before             # nothing else changed
    assert _marker_rows(fresh_db) == [(1, "migrate_ncaa_cfbd_v2.py")]
    assert nc.run([2084], from_file=str(f), out=lambda *_: None) == 0
    assert _records(fresh_db) == 2


def test_drop_db_drops_the_v2_marker(fresh_db, tmp_path, monkeypatch):
    import migrate_ncaa_cfbd_v2 as mig2
    from src.db.database import drop_db, init_db, session_scope

    _labels_migrated(fresh_db, tmp_path, monkeypatch)
    assert mig2.main() == 0 and inspect(fresh_db).has_table(nc.V2_MIGRATION_MARKER)
    drop_db()                                                                      # the init-db --force path
    init_db()
    assert not inspect(fresh_db).has_table(nc.V2_MIGRATION_MARKER)
    with session_scope() as s:
        assert nc.records_ready(s) and not nc.v2_migrated(s)
