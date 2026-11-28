"""#1089 on scripts/soccer_injury_factor_receipt.py (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4): the app's
configured database keeps its open (mode=ro URI, else #421's query_only fallback); any other --db is a copy, opened
mode=ro&immutable=1 with no fallback, refused before any open (exit 2) under data/, with a sidecar beside it, absent or
empty, and refused (exit 2, one line) where immutable=1 cannot read it. Copies here are throwaway WAL files in tmp_path;
the under-data/ case points the fence's data/ at a tmp folder; nothing under the repo's data/ is opened or created."""
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

import scripts.soccer_injury_factor_receipt as rc
from src.walters import db_copy as dc


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy (tests/test_db_copy.py's shape): a WAL-mode file, its sidecars checkpointed away."""
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    for t in rc.COPY_PROBE_TABLES:                                          # every table the probe asks for
        con.execute(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY)")
    con.execute("INSERT INTO predictions VALUES (1)")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


def _no_open(monkeypatch):
    """Every open the script could take fails the test: a refusal opens nothing."""
    def boom(*a, **k):
        raise AssertionError("opened")
    monkeypatch.setattr(rc, "open_session", boom)
    monkeypatch.setattr(rc, "query_only_engine", boom)
    monkeypatch.setattr(dc, "copy_engine", boom)
    monkeypatch.setattr(dc, "connect_copy", boom)


def test_a_copy_is_read_through_immutable_and_leaves_no_sidecar(tmp_path, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    monkeypatch.setattr(rc, "open_session", lambda *_: (_ for _ in ()).throw(AssertionError("live open on a copy")))
    s, form = rc.open_db(str(p))
    try:
        assert form == rc.COPY_FORM
        assert s.execute(text("SELECT count(*) FROM predictions")).scalar() == 1
        with pytest.raises(Exception, match="readonly|read-only"):          # never written
            s.execute(text("INSERT INTO predictions VALUES (2)"))
    finally:
        s.close()
    assert dc.sidecars(p) == []                                             # immutable=1: nothing beside it


def test_main_reads_a_copy_and_says_which_open(tmp_path, monkeypatch, capsys):
    p = wal_copy(tmp_path / "copy.db")
    seen = []
    monkeypatch.setattr(rc, "rows", lambda s, comp: (seen.append(
        s.execute(text("SELECT count(*) FROM predictions")).scalar()) or [], {}))
    monkeypatch.setattr(rc, "report", lambda *a, **k: None)
    assert rc.main(["--db", str(p)]) == 0
    assert seen == [1]
    assert f"read-only open: {rc.COPY_FORM}" in capsys.readouterr().out
    assert dc.sidecars(p) == []


@pytest.mark.parametrize("side", dc.SIDECARS)
def test_a_copy_with_a_sidecar_is_refused_exit_2_nothing_opened(tmp_path, monkeypatch, capsys, side):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + side).write_bytes(b"")
    before = p.read_bytes()
    _no_open(monkeypatch)
    assert rc.main(["--db", str(p)]) == dc.EXIT_REFUSED == 2
    err = capsys.readouterr()
    assert err.err.startswith("REFUSED: ") and f"has a {side} sidecar" in err.err and "copy.db" + side in err.err
    assert "read-only open" not in err.out
    assert p.read_bytes() == before
    assert sorted(x.name for x in tmp_path.iterdir()) == sorted(["copy.db", "copy.db" + side])


def test_an_absent_db_is_refused_exit_2_and_never_created(tmp_path, monkeypatch, capsys):
    p = tmp_path / "absent.db"
    _no_open(monkeypatch)
    assert rc.main(["--db", str(p)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("REFUSED: ") and "no file at" in err and str(p) in err
    assert "nothing created, nothing read" in err and "the gate" not in err
    assert not p.exists() and list(tmp_path.iterdir()) == []


def test_the_apps_configured_database_takes_the_live_open(tmp_path, monkeypatch):
    live = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    calls = []
    monkeypatch.setattr(rc, "open_session", lambda p: calls.append(p) or ("SESSION", "live form"))
    monkeypatch.setattr(dc, "copy_engine", lambda *_: (_ for _ in ()).throw(AssertionError("copy open on live")))
    assert rc.open_db(str(live)) == ("SESSION", "live form")
    assert calls == [Path(str(live))]                                       # db_path(arg), as before #1089
    link = tmp_path / "link.db"                                             # by identity: a hard link is the file
    link.hardlink_to(live)
    assert rc.open_db(str(link)) == ("SESSION", "live form") and calls[-1] == Path(str(link))


def test_no_db_keeps_the_configured_open(monkeypatch):
    calls = []
    monkeypatch.setattr(rc, "open_session", lambda p: calls.append(p) or ("SESSION", "live form"))
    monkeypatch.setattr(dc, "classify", lambda *_: (_ for _ in ()).throw(AssertionError("classified")))
    assert rc.open_db(None) == ("SESSION", "live form")
    assert calls == [rc.db_path(None)]


def test_a_copy_under_data_is_refused_exit_2_nothing_opened(tmp_path, monkeypatch, capsys):
    """582 item 4(b), under data/: the fence's data/ is pointed at a tmp folder (tests/test_db_copy.py's shape)."""
    from src.walters import mlb_pitchers_gate as mp
    data = tmp_path / "data"
    data.mkdir()
    p = wal_copy(data / "x.db")
    before = p.read_bytes()
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    _no_open(monkeypatch)
    assert rc.main(["--db", str(p)]) == 2
    out = capsys.readouterr()
    assert out.err.startswith("REFUSED: ") and "under the repo's data/" in out.err and str(p) in out.err
    assert out.out == ""
    assert p.read_bytes() == before and [x.name for x in data.iterdir()] == ["x.db"]


def test_an_empty_db_is_refused_exit_2(monkeypatch, capsys):
    _no_open(monkeypatch)
    assert rc.main(["--db", ""]) == 2
    out = capsys.readouterr()
    assert out.err.startswith("REFUSED: --db is empty: ") and out.out == ""


def _one_refused_line(err: str, p: Path, cls: str):
    lines = [x for x in err.splitlines() if x.strip()]
    assert len(lines) == 1 and lines[0].startswith(f"REFUSED: --db {p}: cannot be read through a mode=ro&immutable=1")
    assert f"({cls}:" in lines[0] and "Traceback" not in err


def test_a_copy_that_is_not_sqlite_is_refused_exit_2_one_line(tmp_path, monkeypatch, capsys):
    p = tmp_path / "notdb.db"
    p.write_bytes(b"this is not a SQLite database file, only text " * 40)
    before = p.read_bytes()
    monkeypatch.setattr(rc, "open_session", lambda *_: (_ for _ in ()).throw(AssertionError("fallback taken")))
    monkeypatch.setattr(rc, "rows", lambda *_: (_ for _ in ()).throw(AssertionError("read past the probe")))
    assert rc.main(["--db", str(p)]) == 2
    out = capsys.readouterr()
    _one_refused_line(out.err, p, "DatabaseError")
    assert out.out == "" and p.read_bytes() == before
    assert [x.name for x in tmp_path.iterdir()] == ["notdb.db"]                # nothing created beside it


def test_a_copy_missing_a_table_is_refused_exit_2_one_line(tmp_path, monkeypatch, capsys):
    p = tmp_path / "thin.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE predictions (id INTEGER PRIMARY KEY)")      # the rest of rows()'s tables missing
    con.commit()
    con.close()
    closed = []
    real = dc.connect_copy

    def spy(path):
        con = real(path)

        class C:
            def execute(self, *a):
                return con.execute(*a)

            def close(self):
                closed.append(True)
                con.close()
        return C()
    monkeypatch.setattr(dc, "connect_copy", spy)
    monkeypatch.setattr(rc, "open_session", lambda *_: (_ for _ in ()).throw(AssertionError("fallback taken")))
    assert rc.main(["--db", str(p)]) == 2
    out = capsys.readouterr()
    _one_refused_line(out.err, p, "OperationalError")
    assert "prediction_outcomes" in out.err and closed == [True] and out.out == ""
    assert [x.name for x in tmp_path.iterdir()] == ["thin.db"]


def _refuse_immutable_open(monkeypatch, after: int = 0):
    """sqlite3.connect (db_copy's module reference is the sqlite3 module's own) raises OperationalError for a URI that
    carries immutable=1, once `after` such opens have gone through, and delegates to the real connect otherwise, so only
    the copy open fails. Returns the immutable URIs asked for."""
    real = sqlite3.connect
    asked = []

    def stub(database, *args, **kwargs):
        if "immutable=1" in str(database):
            asked.append(str(database))
            if len(asked) > after:
                raise sqlite3.OperationalError("unable to open database file")
        return real(database, *args, **kwargs)
    monkeypatch.setattr(dc.sqlite3, "connect", stub)
    return asked


def _opened_refusal(err: str, p: Path):
    lines = [x for x in err.splitlines() if x.strip()]
    assert lines == [f"REFUSED: --db {p.resolve()}: cannot be opened through a mode=ro&immutable=1 URI "
                     "(OperationalError); no fallback; nothing read"]
    assert "Traceback" not in err


def test_a_copy_the_fence_passes_but_sqlite_cannot_open_is_refused_one_line_exit_2_nothing_beside_it(
        tmp_path, monkeypatch, capsys):
    p = wal_copy(tmp_path / "copy.db")                            # the copy is built before the stub goes in
    before = sorted(x.name for x in tmp_path.iterdir())
    data_before = p.read_bytes()
    asked = _refuse_immutable_open(monkeypatch)
    monkeypatch.setattr(rc, "open_session", lambda *_: (_ for _ in ()).throw(AssertionError("fallback taken")))
    monkeypatch.setattr(rc, "query_only_engine", lambda *_: (_ for _ in ()).throw(AssertionError("fallback taken")))
    monkeypatch.setattr(rc, "rows", lambda *_: (_ for _ in ()).throw(AssertionError("read past the open")))
    assert rc.main(["--db", str(p)]) == dc.EXIT_REFUSED == 2
    out = capsys.readouterr()
    _opened_refusal(out.err, p)
    assert str(p.resolve()) in out.err and out.out == ""
    assert len(asked) == 1 and asked[0].endswith("?mode=ro&immutable=1")
    assert sorted(x.name for x in tmp_path.iterdir()) == before   # nothing created beside it
    assert p.read_bytes() == data_before


def test_the_engines_own_open_failing_is_refused_one_line_exit_2_before_any_read(tmp_path, monkeypatch, capsys):
    """The probe's open goes through, the engine's first open does not (the file gone unreadable between them): the
    engine's first use is inside open_db, so main prints the one REFUSED line, exit 2, nothing on stdout, no row read."""
    p = wal_copy(tmp_path / "copy.db")
    before = sorted(x.name for x in tmp_path.iterdir())
    asked = _refuse_immutable_open(monkeypatch, after=1)
    monkeypatch.setattr(rc, "open_session", lambda *_: (_ for _ in ()).throw(AssertionError("fallback taken")))
    monkeypatch.setattr(rc, "rows", lambda *_: (_ for _ in ()).throw(AssertionError("read past the open")))
    assert rc.main(["--db", str(p)]) == 2
    out = capsys.readouterr()
    _opened_refusal(out.err, p)
    assert out.out == "" and len(asked) == 2
    assert sorted(x.name for x in tmp_path.iterdir()) == before


def test_copy_engine_passes_copy_refused_through_sqlalchemy_unwrapped(tmp_path, monkeypatch):
    """The creator's CopyRefused is not a DBAPI error: SQLAlchemy's pool lets it out as itself, never wrapped in
    sqlalchemy.exc.DBAPIError, through the engine and through an ORM Session alike."""
    import sqlalchemy.exc
    from sqlalchemy.orm import Session
    p = wal_copy(tmp_path / "copy.db")
    _refuse_immutable_open(monkeypatch)
    eng = dc.copy_engine(p)
    with pytest.raises(dc.CopyRefused) as ei:
        eng.connect()
    assert type(ei.value) is dc.CopyRefused and not isinstance(ei.value, sqlalchemy.exc.SQLAlchemyError)
    s = Session(eng)
    try:
        with pytest.raises(dc.CopyRefused) as ei:
            s.execute(text("SELECT 1"))
        assert type(ei.value) is dc.CopyRefused and not isinstance(ei.value, sqlalchemy.exc.SQLAlchemyError)
    finally:
        s.close()
