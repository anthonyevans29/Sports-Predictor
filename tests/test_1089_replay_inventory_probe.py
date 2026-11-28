"""#1089 (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4) for scripts/replay_inventory_probe.py: the app's
configured database keeps its open (mode=ro, the #421 fallback); any other --db is a copy, opened mode=ro&immutable=1
with no fallback, refused before any open (exit 2) under data/, with a sidecar beside it, absent or empty, and a copy
immutable=1 cannot read is refused in one line. Throwaway WAL files in tmp, never the repo's data/ (the under-data case
points the fence's data/ at a tmp folder)."""
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine

import scripts.replay_inventory_probe as rip
from src.db.schema import Base
from src.walters import db_copy as dc
from src.walters import mlb_pitchers_gate as mp

COPY_FORM = "copy: mode=ro&immutable=1 URI (no fallback)"


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: the app's schema in a WAL-mode file with one graded game, its sidecars removed."""
    eng = create_engine(f"sqlite:///{p}")
    Base.metadata.create_all(eng)
    eng.dispose()
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("INSERT INTO competitions (id, code, name, area, type, sport, external_ids) "
                "VALUES (1, 'NFL', 'NFL', 'USA', 'LEAGUE', 'NFL', '{}')")
    con.execute("INSERT INTO teams (id, name, sport, external_ids) VALUES (1, 'Home', 'NFL', '{}'), "
                "(2, 'Away', 'NFL', '{}')")
    con.execute("INSERT INTO matches (id, competition_id, sport, season, utc_date, status, home_team_id, away_team_id, "
                "home_score, away_score, external_ids) "
                "VALUES (7, 1, 'NFL', '2026', '2026-10-05 18:00:00.000000', 'FINISHED', 1, 2, 21, 17, '{}')")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


def args(p: Path, tmp_path: Path) -> list[str]:
    return ["--db", str(p), "--exports", str(tmp_path / "none"), "--until", "2026-10-12"]


def test_a_wal_copy_is_read_through_the_copy_open_and_leaves_no_sidecar(tmp_path, capsys):
    p = wal_copy(tmp_path / "copy.db")
    before = p.read_bytes()
    assert rip.main(args(p, tmp_path)) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("REPLAY INVENTORY PROBE (ARCHITECT 2026-10-15, addendum 79 item 3; #75): read-only · "
                             f"{COPY_FORM} · graded games with kickoff in [2026-09-20, 2026-10-12) UTC: 1")
    assert "NFL: graded 1" in out
    assert dc.sidecars(p) == []
    assert p.read_bytes() == before


def test_a_copy_with_a_wal_sidecar_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + "-wal").write_bytes(b"")
    opened = []
    monkeypatch.setattr(rip, "open_read", lambda *a, **k: opened.append("live"))
    monkeypatch.setattr(rip, "open_copy", lambda *a, **k: opened.append("copy"))
    monkeypatch.setattr(rip.db_copy, "connect_copy", lambda *a, **k: opened.append("connect"))
    assert rip.main(args(p, tmp_path)) == dc.EXIT_REFUSED == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    assert cap.err.startswith("REFUSED: ") and "has a -wal sidecar (copy.db-wal)" in cap.err
    assert opened == []


def test_an_absent_db_is_refused_exit_2_and_not_created(tmp_path, capsys):
    p = tmp_path / "absent.db"
    assert rip.main(args(p, tmp_path)) == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    assert cap.err.startswith("REFUSED: ") and f"no file at {p.resolve()}" in cap.err
    assert cap.err.rstrip().endswith("; nothing created, nothing read") and "the gate" not in cap.err
    assert not p.exists()
    assert sorted(x.name for x in tmp_path.iterdir()) == []


def test_the_apps_configured_database_takes_the_live_open(tmp_path, capsys, monkeypatch):
    live = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    calls, real = [], rip.open_read

    def record(p):
        calls.append(Path(p))
        return real(p)
    monkeypatch.setattr(rip, "open_read", record)
    monkeypatch.setattr(rip, "open_copy", lambda *a, **k: (_ for _ in ()).throw(AssertionError("copy open taken")))
    assert rip.main(args(live, tmp_path)) == 0
    assert calls == [live]
    assert " · mode=ro URI · graded games" in capsys.readouterr().out.splitlines()[0]


def test_a_copy_under_data_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    p = wal_copy(data / "x.db")
    before = p.read_bytes()
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    opened = []
    monkeypatch.setattr(rip, "open_read", lambda *a, **k: opened.append("live"))
    monkeypatch.setattr(rip.db_copy, "connect_copy", lambda *a, **k: opened.append("connect"))
    assert rip.main(args(p, tmp_path)) == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    err = cap.err.splitlines()
    assert len(err) == 1 and err[0].startswith(f"REFUSED: --db {p} resolves under the repo's data/")
    assert opened == []
    assert p.read_bytes() == before and sorted(x.name for x in data.iterdir()) == ["x.db"]


def test_an_empty_db_is_refused_exit_2(tmp_path, capsys, monkeypatch):
    opened = []
    monkeypatch.setattr(rip, "open_read", lambda *a, **k: opened.append("live"))
    monkeypatch.setattr(rip.db_copy, "connect_copy", lambda *a, **k: opened.append("connect"))
    assert rip.main(["--db", "", "--exports", str(tmp_path / "none"), "--until", "2026-10-12"]) == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    assert cap.err.splitlines() == ["REFUSED: --db is empty: name the app's configured database or a .backup copy "
                                    "outside data/; nothing read"]
    assert opened == []


def unreadable_case(p: Path, tmp_path: Path, capsys) -> str:
    before = p.read_bytes()
    assert rip.main(args(p, tmp_path)) == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    err = cap.err.splitlines()
    assert len(err) == 1 and err[0].startswith(f"REFUSED: --db {p}: cannot be read through a mode=ro&immutable=1 URI (")
    assert err[0].endswith("); no fallback; nothing read") and "Traceback" not in cap.err
    assert p.read_bytes() == before
    assert sorted(x.name for x in tmp_path.iterdir()) == [p.name]           # nothing created beside it
    return err[0]


def test_a_copy_that_is_not_a_sqlite_file_is_refused_in_one_line(tmp_path, capsys):
    p = tmp_path / "junk.db"
    p.write_bytes(b"this is not a database, not even close" * 200)
    assert "(DatabaseError: " in unreadable_case(p, tmp_path, capsys)


def test_a_copy_missing_a_table_the_probe_reads_is_refused_in_one_line(tmp_path, capsys):
    p = wal_copy(tmp_path / "copy.db")
    con = sqlite3.connect(p)
    con.execute("DROP TABLE odds")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    assert "(OperationalError: no such table: odds)" in unreadable_case(p, tmp_path, capsys)


def test_a_copy_probe_closes_its_connection_when_it_refuses(tmp_path, monkeypatch):
    p = tmp_path / "junk.db"
    p.write_bytes(b"x" * 4096)
    closed, real = [], dc.connect_copy

    class Spy:
        def __init__(self, con):
            self.con = con

        def execute(self, *a):
            return self.con.execute(*a)

        def close(self):
            closed.append(True)
            self.con.close()
    monkeypatch.setattr(rip.db_copy, "connect_copy", lambda path: Spy(real(path)))
    try:
        rip.open_copy(p)
    except dc.CopyRefused:
        pass
    else:
        raise AssertionError("an unreadable copy was opened")
    assert closed == [True]


def test_a_copy_sqlite_cannot_open_is_refused_in_one_line_through_main(tmp_path, capsys, monkeypatch):
    """A copy that passes the fence but that SQLite cannot open (connect_copy's sqlite3.Error at connect time) gives,
    through main(), one REFUSED line naming the path, exit 2, no traceback, nothing created beside it. The stub raises
    only for the immutable=1 URI; every other connect is the real one."""
    p = wal_copy(tmp_path / "copy.db")
    before = p.read_bytes()
    real, uris = sqlite3.connect, []

    def stub(database, *a, **k):
        if "immutable=1" in str(database):
            uris.append(str(database))
            raise sqlite3.OperationalError("unable to open database file")
        return real(database, *a, **k)
    monkeypatch.setattr(dc.sqlite3, "connect", stub)
    assert rip.main(args(p, tmp_path)) == dc.EXIT_REFUSED == 2
    cap = capsys.readouterr()
    assert cap.out == "" and "Traceback" not in cap.err
    assert cap.err.splitlines() == [f"REFUSED: --db {p.resolve()}: cannot be opened through a mode=ro&immutable=1 URI "
                                    "(OperationalError); no fallback; nothing read"]
    assert uris == [dc.copy_uri(p)]
    assert p.read_bytes() == before
    assert sorted(x.name for x in tmp_path.iterdir()) == [p.name]           # nothing created beside it
    # copy_engine's creator is connect_copy: SQLAlchemy passes the non-DBAPI CopyRefused through unwrapped
    from sqlalchemy.exc import SQLAlchemyError
    eng = dc.copy_engine(p)
    try:
        eng.connect()
    except dc.CopyRefused as e:
        assert not isinstance(e, SQLAlchemyError) and type(e) is dc.CopyRefused
        assert str(e) == cap.err.splitlines()[0]
    else:
        raise AssertionError("copy_engine opened a copy SQLite cannot open")
    finally:
        eng.dispose()
    assert sorted(x.name for x in tmp_path.iterdir()) == [p.name]
