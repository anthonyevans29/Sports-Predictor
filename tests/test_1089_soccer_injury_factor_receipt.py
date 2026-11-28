"""#1089 on scripts/soccer_injury_factor_receipt.py (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4): the app's
configured database keeps its open (mode=ro URI, else #421's query_only fallback); any other --db is a copy, opened
mode=ro&immutable=1 with no fallback, refused before any open (exit 2) with a sidecar beside it or absent. Copies here
are throwaway WAL files in tmp_path; nothing under data/ is opened or created."""
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
    con.execute("CREATE TABLE predictions (id INTEGER PRIMARY KEY)")
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
