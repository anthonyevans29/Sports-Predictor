"""#1089 on scripts/nhl_gsax_feasibility.py (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4): the app's configured
database keeps its open (open_read: mode=ro, #421's fallback); any other --db is a copy, opened mode=ro&immutable=1 with
no fallback, and refused before any open (exit 2) under data/, with a sidecar beside it, or absent. Copies here are
throwaway WAL files in tmp_path; never data/, never the configured DB."""
import importlib.util
import sqlite3
from pathlib import Path

import pytest

from src.walters import db_copy as dc

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nhl_gsax_feasibility_1089", ROOT / "scripts" / "nhl_gsax_feasibility.py")
gx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gx)

SHOTS = """CREATE TABLE nhl_shot_events (id INTEGER PRIMARY KEY, nhl_game_id INT, event_id INT, match_id INT,
    game_start TEXT, game_type INT, period INT, period_type TEXT, time_in_period_s INT, event_type TEXT, shot_type TEXT,
    side TEXT, owner_side TEXT, team_abbrev TEXT, shooter_id INT, goalie_id INT, x REAL, y REAL, zone_code TEXT,
    home_defending_side TEXT, situation_code TEXT, captured_at TEXT)"""
APPS = """CREATE TABLE nhl_goalie_appearances (id INTEGER PRIMARY KEY, nhl_game_id INT, match_id INT, game_start TEXT,
    game_type INT, side TEXT, team_abbrev TEXT, goalie_id INT, goalie_name TEXT, is_starter INT, shots_against INT,
    saves INT, goals_against INT, toi_seconds INT, decision TEXT, captured_at TEXT)"""


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: the two tables the receipt reads in a WAL-mode file, one stored shot, its sidecars
    checkpointed away."""
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(SHOTS)
    con.execute(APPS)
    con.execute("INSERT INTO nhl_shot_events (nhl_game_id, event_id, game_start, game_type, period, period_type, "
                "event_type, side, owner_side, goalie_id, x, y, home_defending_side, situation_code) "
                "VALUES (2024020101, 1, '2024-11-01 23:00:00', 2, 1, 'REG', 'shot-on-goal', 'home', 'home', 8470000, "
                "70.0, 5.0, 'left', '1551')")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    assert dc.sidecars(p) == []
    return p


def test_a_copy_is_read_through_its_own_open_and_leaves_no_sidecar(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    seen = []
    real = dc.connect_copy
    monkeypatch.setattr(dc, "connect_copy", lambda path: seen.append(path) or real(path))
    monkeypatch.setattr(gx, "open_read", lambda *a: pytest.fail("a copy took the live file's open"))
    assert gx.main(["--db", str(p)]) == 0
    out = capsys.readouterr().out
    assert seen == [p.resolve()]
    assert "DB copy.db (mode=ro URI with immutable=1 (a copy; no fallback))" in out
    assert "2024-25 regular season (type 2)" in out                                  # read
    assert dc.sidecars(p) == []                                                      # immutable=1: nothing beside it


@pytest.mark.parametrize("side", dc.SIDECARS)
def test_a_copy_with_a_sidecar_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch, side):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + side).write_bytes(b"")
    monkeypatch.setattr(gx.sqlite3, "connect", lambda *a, **k: pytest.fail("a refused copy was opened"))
    monkeypatch.setattr(dc, "connect_copy", lambda *a: pytest.fail("a refused copy was opened"))
    monkeypatch.setattr(gx, "open_read", lambda *a: pytest.fail("a refused copy was opened"))
    rc = gx.main(["--db", str(p)])
    cap = capsys.readouterr()
    assert rc == 2 == dc.EXIT_REFUSED
    assert f"REFUSED: --db {p} has a {side} sidecar (copy.db{side})" in cap.err
    assert cap.out == ""                                                             # the path printed, never a row


def test_an_absent_copy_is_refused_exit_2_and_never_created(tmp_path, capsys, monkeypatch):
    p = tmp_path / "absent.db"
    monkeypatch.setattr(gx.sqlite3, "connect", lambda *a, **k: pytest.fail("an absent copy was opened"))
    rc = gx.main(["--db", str(p)])
    cap = capsys.readouterr()
    assert rc == 2 and cap.err.startswith("REFUSED: ") and f"no file at {p}" in cap.err and cap.out == ""
    assert "nothing created, nothing read" in cap.err and cap.err.count("\n") == 1
    assert not p.exists() and dc.sidecars(p) == []


def test_an_empty_db_is_refused_exit_2_never_read_as_the_default(capsys, monkeypatch):
    monkeypatch.setattr(gx, "open_read", lambda *a: pytest.fail("an empty --db took the live open"))
    monkeypatch.setattr(dc, "connect_copy", lambda *a: pytest.fail("an empty --db was opened"))
    rc = gx.main(["--db", ""])
    cap = capsys.readouterr()
    assert rc == 2 and cap.err.startswith("REFUSED: --db is empty: ") and cap.out == ""


@pytest.mark.parametrize("case", ["not_sqlite", "no_shot_table"])
def test_an_unreadable_copy_is_refused_exit_2_one_line_nothing_beside_it(tmp_path, capsys, monkeypatch, case):
    """582 item 4(a): a copy that passes the fence but cannot be read through immutable=1 is one REFUSED line naming
    the path and the error class, exit 2, no traceback and no fallback; nothing is created beside it."""
    p = tmp_path / "copy.db"
    if case == "not_sqlite":
        p.write_bytes(b"this is not a SQLite database file, only text" * 20)
    else:
        con = sqlite3.connect(p)
        con.execute(APPS)
        con.commit()
        con.close()
    before = p.read_bytes()
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
    monkeypatch.setattr(gx, "open_read", lambda *a: pytest.fail("an unreadable copy fell back to the live open"))
    rc = gx.main(["--db", str(p)])
    cap = capsys.readouterr()
    cls = "DatabaseError" if case == "not_sqlite" else "OperationalError"
    assert rc == 2 and cap.out == ""
    assert cap.err == (f"REFUSED: --db {p.resolve()}: the copy cannot be read through mode=ro&immutable=1 ({cls}); "
                       "no fallback; nothing read\n")
    assert closed == [True]
    assert p.read_bytes() == before and dc.sidecars(p) == []
    assert sorted(x.name for x in tmp_path.iterdir()) == ["copy.db"]


def test_a_copy_under_data_is_refused_exit_2(tmp_path, capsys, monkeypatch):
    from src.walters import mlb_pitchers_gate as mp
    data = tmp_path / "data"
    data.mkdir()
    p = wal_copy(data / "sports.db")
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    monkeypatch.setattr(dc, "connect_copy", lambda *a: pytest.fail("a refused copy was opened"))
    rc = gx.main(["--db", str(p)])
    cap = capsys.readouterr()
    assert rc == 2 and "under the repo's data/" in cap.err and cap.out == ""


def test_the_apps_configured_database_takes_the_live_open(tmp_path, capsys, monkeypatch):
    live = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    seen = []
    real = gx.open_read
    monkeypatch.setattr(gx, "open_read", lambda path: seen.append(path) or real(path))
    monkeypatch.setattr(dc, "connect_copy", lambda *a: pytest.fail("the live file took the copy open"))
    assert gx.main(["--db", str(live)]) == 0
    out = capsys.readouterr().out
    assert seen == [Path(str(live))] and "DB sports.db (mode=ro URI)" in out


def test_a_machine_without_configuration_reads_its_live_file_as_a_copy_under_data(tmp_path, capsys, monkeypatch):
    """582 item 4(d): no configuration loaded, nothing is live; the live file under data/ is a copy, refused."""
    from src.walters import mlb_pitchers_gate as mp
    data = tmp_path / "data"
    data.mkdir()
    p = wal_copy(data / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: None)
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    monkeypatch.setattr(gx, "open_read", lambda *a: pytest.fail("an unconfigured machine took the live open"))
    rc = gx.main(["--db", str(p)])
    assert rc == 2 and "under the repo's data/" in capsys.readouterr().err


def test_a_copy_sqlite_cannot_open_is_one_refused_line_exit_2_nothing_beside_it(tmp_path, capsys, monkeypatch):
    """db_copy.connect_copy (7a66e7f8): a copy that passes the fence but that SQLite cannot open through
    mode=ro&immutable=1 raises CopyRefused at connect time; through main() that is one REFUSED line naming the path,
    exit 2, no traceback, no fallback, nothing created beside it."""
    p = wal_copy(tmp_path / "copy.db")
    before = p.read_bytes()
    real = sqlite3.connect
    asked = []

    def connect(database, *a, **k):
        if "immutable=1" in str(database):
            asked.append(str(database))
            raise sqlite3.OperationalError("unable to open database file")
        return real(database, *a, **k)
    monkeypatch.setattr(dc.sqlite3, "connect", connect)
    monkeypatch.setattr(gx, "open_read", lambda *a: pytest.fail("a copy SQLite cannot open fell back to the live open"))
    rc = gx.main(["--db", str(p)])
    cap = capsys.readouterr()
    assert asked == [dc.copy_uri(p.resolve())]                                       # the copy's URI, asked once
    assert rc == 2 == dc.EXIT_REFUSED and cap.out == ""
    assert cap.err == (f"REFUSED: --db {p.resolve()}: cannot be opened through a mode=ro&immutable=1 URI "
                       "(OperationalError); no fallback; nothing read\n")
    assert "Traceback" not in cap.err and cap.err.count("\n") == 1
    assert p.read_bytes() == before and dc.sidecars(p) == []
    assert sorted(x.name for x in tmp_path.iterdir()) == ["copy.db"]
