"""#1089 (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4) for scripts/soccer_rating_coverage.py: the app's configured
database keeps its open; any other --db is a copy, opened mode=ro&immutable=1 with no fallback, and refused before any
open (exit 2, nothing read) under data/, with a sidecar beside it, absent or empty; a copy it cannot read is refused in one
line. Every file here is a throwaway in tmp_path (data/ is a tmp folder the fence is pointed at, never the repo's)."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import soccer_rating_coverage as rc  # noqa: E402
from src.walters import db_copy as dc  # noqa: E402
from src.walters import mlb_pitchers_gate as mp  # noqa: E402

ARGS = ["--competition", "PL", "--season", "2026/27", "--db"]


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: a WAL-mode file with the receipt's tables, its sidecars checkpointed away."""
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE competitions (id INTEGER PRIMARY KEY, sport TEXT, code TEXT);
        CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE matches (id INTEGER PRIMARY KEY, competition_id INT, season TEXT, home_team_id INT,
                              away_team_id INT);
        CREATE TABLE model_versions (id INTEGER PRIMARY KEY, sport TEXT, model_family TEXT, version TEXT,
                                     status TEXT, parameters TEXT);
    """)
    con.execute("INSERT INTO competitions VALUES (1, 'SOCCER', 'PL')")
    con.executemany("INSERT INTO teams VALUES (?, ?)", [(10, "Arsenal"), (11, "Leeds")])
    con.execute("INSERT INTO matches VALUES (1, 1, '2026/27', 10, 11)")
    params = {"elo": {"league": {"ratings": {"10": 1705.5}}, "cup": {"ratings": {}}}, "team_to_league": {"10": "PL"}}
    con.execute("INSERT INTO model_versions VALUES (1, 'SOCCER', 'soccer_elo_poisson', 'v22', 'production', ?)",
                (json.dumps(params),))
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


def test_1_a_wal_copy_is_read_through_the_copy_open_and_nothing_is_left_beside_it(tmp_path, capsys):
    p = wal_copy(tmp_path / "copy.db")
    before = p.read_bytes()
    assert rc.main(ARGS + [str(p)]) == 0
    out = capsys.readouterr().out
    assert "read-only open: copy: mode=ro&immutable=1 URI (no fallback; addendum 582 item 4)" in out
    assert "TOTALS teams 2 · in the table 1 · MISSING 1" in out
    assert dc.sidecars(p) == []                                   # no -wal, -shm or -journal created
    assert p.read_bytes() == before


def test_2_a_copy_with_a_wal_sidecar_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + "-wal").write_bytes(b"")
    opened = []
    monkeypatch.setattr(rc, "open_read", lambda *a, **k: opened.append(a))
    monkeypatch.setattr(dc, "connect_copy", lambda *a, **k: opened.append(a))
    assert rc.main(ARGS + [str(p)]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "-wal sidecar (copy.db-wal)" in out and str(p) in out
    assert opened == []
    assert "read-only open" not in out and "TOTALS" not in out    # nothing read


def test_3_an_absent_db_is_refused_exit_2_and_not_created(tmp_path, capsys):
    p = tmp_path / "absent.db"
    assert rc.main(ARGS + [str(p)]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "no file at" in out and str(p) in out
    assert out.rstrip().endswith("; nothing created, nothing read") and "the gate never creates one" not in out
    assert len(out.strip().splitlines()) == 1
    assert not p.exists() and dc.sidecars(p) == []


def test_4_the_apps_configured_database_takes_the_live_open(tmp_path, monkeypatch):
    live = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    calls = []
    real = rc.open_read

    def record(path):
        calls.append(Path(path))
        return real(path)
    monkeypatch.setattr(rc, "open_read", record)
    monkeypatch.setattr(dc, "connect_copy", lambda *a, **k: (_ for _ in ()).throw(AssertionError("copy open")))
    assert rc.main(ARGS + [str(live)]) == 0
    assert [c.resolve() for c in calls] == [live.resolve()]


def test_5_a_copy_under_data_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    p = wal_copy(data / "x.db")
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    opened = []
    monkeypatch.setattr(rc, "open_read", lambda *a, **k: opened.append(a))
    monkeypatch.setattr(dc, "connect_copy", lambda *a, **k: opened.append(a))
    assert rc.main(ARGS + [str(p)]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "under the repo's data/" in out and str(p) in out
    assert len(out.strip().splitlines()) == 1
    assert opened == [] and "read-only open" not in out and "TOTALS" not in out


def test_6_an_empty_db_is_refused_exit_2_nothing_opened(capsys, monkeypatch):
    opened = []
    monkeypatch.setattr(rc, "open_read", lambda *a, **k: opened.append(a))
    monkeypatch.setattr(dc, "connect_copy", lambda *a, **k: opened.append(a))
    assert rc.main(ARGS + [""]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: --db is empty: ") and len(out.strip().splitlines()) == 1
    assert opened == []


def test_7_a_copy_that_is_not_sqlite_is_refused_in_one_line_and_closed(tmp_path, capsys, monkeypatch):
    p = tmp_path / "junk.db"
    p.write_bytes(b"not a sqlite file" * 64)
    before = p.read_bytes()
    closed = []
    real = dc.connect_copy

    def track(path):
        con = real(path)

        class C:
            def execute(self, *a):
                return con.execute(*a)

            def close(self):
                closed.append(True)
                con.close()
        return C()
    monkeypatch.setattr(dc, "connect_copy", track)
    assert rc.main(ARGS + [str(p)]) == 2
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith(f"REFUSED: --db {p}: ") and "DatabaseError" in lines[0]
    assert "Traceback" not in out and "read-only open" not in out and "TOTALS" not in out
    assert closed == [True]
    assert p.read_bytes() == before and dc.sidecars(p) == []
    assert sorted(x.name for x in tmp_path.iterdir()) == ["junk.db"]


def test_8_a_copy_missing_a_table_is_refused_in_one_line(tmp_path, capsys):
    p = wal_copy(tmp_path / "copy.db")
    con = sqlite3.connect(p)
    con.execute("DROP TABLE teams")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    assert rc.main(ARGS + [str(p)]) == 2
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith(f"REFUSED: --db {p}: ") and "OperationalError" in lines[0]
    assert "no such table: teams" in lines[0] and "TOTALS" not in out
    assert dc.sidecars(p) == [] and sorted(x.name for x in tmp_path.iterdir()) == ["copy.db"]


def test_9_the_help_line_carries_582_item_4_d(capsys):
    import pytest
    with pytest.raises(SystemExit):
        rc.main(["--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert ("a machine whose configuration is not loaded reads its own live file as a copy under data/ and refuses "
            "(addendum 582 item 4)") in out
