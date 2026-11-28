"""scripts/nhl_starter_timing_probe.py --stored --db (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4; #1089): the
app's configured database keeps its open; any other --db is a copy, opened mode=ro&immutable=1 with no fallback, and
refused before any open (exit 2) with a sidecar beside it or absent. Copies here are throwaway WAL files in tmp."""
import importlib.util
import sqlite3
import types
from pathlib import Path

import pytest

from src.walters import db_copy as dc

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("nhl_starter_timing_probe_1089",
                                               ROOT / "scripts" / "nhl_starter_timing_probe.py")
tp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tp)


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: a WAL-mode file with the appearances table, its sidecars checkpointed away."""
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE nhl_goalie_appearances (id INTEGER PRIMARY KEY, nhl_game_id INT, game_start TEXT, "
                "captured_at TEXT, is_starter INT)")
    con.execute("INSERT INTO nhl_goalie_appearances (nhl_game_id, game_start, captured_at, is_starter) "
                "VALUES (2025020001, '2025-10-08 23:00:00', '2025-10-08 20:00:00', 1)")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


def _no_open(monkeypatch):
    """Every open the script could take raises: a refusal must come before any of them."""
    def boom(*a, **k):
        raise AssertionError("opened")
    monkeypatch.setattr(tp, "sqlite3", types.SimpleNamespace(connect=boom, OperationalError=sqlite3.OperationalError))
    monkeypatch.setattr(dc, "connect_copy", boom)


def test_a_copy_is_read_through_immutable_and_leaves_no_sidecar(tmp_path, capsys):
    p = wal_copy(tmp_path / "copy.db")
    before = p.read_bytes()
    assert tp.main(["--stored", "--db", str(p)]) == 0
    out = capsys.readouterr().out
    assert "read-only (mode=ro URI with immutable=1 (a copy; no fallback))" in out
    assert "2025-26: rows 1" in out and "pre-game knowledge: 1 row(s) captured before their game's start (of 1)" in out
    assert dc.sidecars(p) == [] and p.read_bytes() == before


def test_a_copy_with_a_wal_sidecar_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + "-wal").write_bytes(b"")
    _no_open(monkeypatch)
    assert tp.main(["--stored", "--db", str(p)]) == dc.EXIT_REFUSED == 2
    cap = capsys.readouterr()
    assert cap.err.startswith("REFUSED: ") and "has a -wal sidecar (copy.db-wal)" in cap.err
    assert "rows" not in cap.out and "nhl_goalie_appearances, read-only" not in cap.out


def test_an_absent_db_is_refused_exit_2_and_never_created(tmp_path, capsys, monkeypatch):
    p = tmp_path / "absent.db"
    _no_open(monkeypatch)
    assert tp.main(["--stored", "--db", str(p)]) == 2
    assert "no file at" in capsys.readouterr().err
    assert not p.exists()


def test_the_apps_configured_database_takes_the_live_open(tmp_path, capsys, monkeypatch):
    live = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    calls = []

    def connect(*a, **k):
        calls.append((a, k))
        return sqlite3.connect(*a, **k)
    monkeypatch.setattr(tp, "sqlite3", types.SimpleNamespace(connect=connect, OperationalError=sqlite3.OperationalError))

    def no_copy(*a, **k):
        raise AssertionError("the copy open was taken for the live file")
    monkeypatch.setattr(tp, "open_copy", no_copy)
    monkeypatch.setattr(dc, "connect_copy", no_copy)
    assert tp.main(["--stored", "--db", str(live)]) == 0
    assert calls[0] == ((live.resolve().as_uri() + "?mode=ro",), {"uri": True})     # the live file's open, as before
    assert "read-only (mode=ro URI) · the stored starters" in capsys.readouterr().out


def test_a_copy_under_data_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch):
    from src.walters import mlb_pitchers_gate as mp
    data = tmp_path / "data"                     # a tmp folder stands in for data/: nothing under the repo's data/
    data.mkdir()
    p = wal_copy(data / "x.db")
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    _no_open(monkeypatch)
    assert tp.main(["--stored", "--db", str(p)]) == 2
    cap = capsys.readouterr()
    assert cap.err.startswith("REFUSED: ") and "under the repo's data/" in cap.err and str(p) in cap.err
    assert "rows" not in cap.out and cap.out == ""


def test_an_absent_db_names_the_helpers_tail(tmp_path, capsys, monkeypatch):
    p = tmp_path / "absent.db"
    _no_open(monkeypatch)
    assert tp.main(["--stored", "--db", str(p)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("REFUSED: ") and str(p) in err and "; nothing created, nothing read" in err
    assert "the gate never creates one" not in err and not p.exists()


@pytest.mark.parametrize("db", ["", "   "])
def test_an_empty_db_is_refused_exit_2_never_the_default_file(db, capsys, monkeypatch):
    _no_open(monkeypatch)
    assert tp.main(["--stored", "--db", db]) == 2
    cap = capsys.readouterr()
    assert cap.err.startswith("REFUSED: --db is empty: ") and cap.out == ""


@pytest.mark.parametrize("kind", ["not sqlite", "no table"])
def test_an_unreadable_copy_is_one_refused_line_exit_2_nothing_beside_it(kind, tmp_path, capsys):
    p = tmp_path / "bad.db"
    if kind == "not sqlite":
        p.write_bytes(b"this is not a SQLite database file, only text" * 40)
    else:
        con = sqlite3.connect(p)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE other (id INTEGER PRIMARY KEY)")
        con.commit()
        con.close()
        for s in dc.SIDECARS:
            p.with_name(p.name + s).unlink(missing_ok=True)
    before = sorted(x.name for x in tmp_path.iterdir())
    assert tp.main(["--stored", "--db", str(p)]) == 2
    cap = capsys.readouterr()
    lines = cap.err.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith(f"REFUSED: --db {p}: cannot be read through a mode=ro&immutable=1")
    assert ("DatabaseError" if kind == "not sqlite" else "OperationalError") in lines[0]
    assert "Traceback" not in cap.err and cap.out == ""
    assert sorted(x.name for x in tmp_path.iterdir()) == before and dc.sidecars(p) == []


def test_a_copy_sqlite_cannot_open_is_one_refused_line_exit_2_through_main(tmp_path, capsys, monkeypatch):
    """A copy that passes the fence (a fresh WAL copy, no sidecar) but that SQLite refuses at connect time: connect_copy's
    CopyRefused reaches main's refusal, one line naming the path, exit 2, no traceback, nothing created beside it."""
    p = wal_copy(tmp_path / "copy.db")                       # built with the real connect, before the stub
    before = sorted(x.name for x in tmp_path.iterdir())
    real = sqlite3.connect
    seen = []

    def connect(database, *a, **k):
        if "immutable=1" in str(database):
            seen.append(str(database))
            raise sqlite3.OperationalError("unable to open database file")
        return real(database, *a, **k)
    monkeypatch.setattr(dc.sqlite3, "connect", connect)      # the sqlite3 module's connect: delegate all but the copy
    assert dc.check_copy(p) == p.resolve()                   # the fence passes it
    assert tp.main(["--stored", "--db", str(p)]) == dc.EXIT_REFUSED == 2
    cap = capsys.readouterr()
    lines = cap.err.strip().splitlines()
    assert len(lines) == 1 and lines[0] == (f"REFUSED: --db {p.resolve()}: cannot be opened through a mode=ro&immutable=1 "
                                            "URI (OperationalError); no fallback; nothing read")
    assert seen == [dc.copy_uri(p)]                          # the copy's one open was the immutable URI, and nothing else
    assert "Traceback" not in cap.err and cap.out == ""
    assert sorted(x.name for x in tmp_path.iterdir()) == before and dc.sidecars(p) == []


def test_the_help_line_carries_582_item_4d():
    h = " ".join(tp.parser().format_help().split())
    assert ("a machine whose configuration is not loaded reads its own live file as a copy under data/ and refuses "
            "(addendum 582 item 4)") in h
