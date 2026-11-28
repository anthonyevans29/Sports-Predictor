"""#1089 (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4) for scripts/kalshi_leg_audit.py: the app's configured
database keeps its open (mode=ro, the #421 fallback); any other --db is a copy, opened mode=ro&immutable=1 with no
fallback, refused before any open (exit 2) with a sidecar beside it or absent. Throwaway WAL files in tmp, never data/."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kalshi_leg_audit as la  # noqa: E402
from src.walters import db_copy as dc  # noqa: E402


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: a WAL-mode file with the tables the audit reads, its sidecars checkpointed away."""
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE matches (id INTEGER PRIMARY KEY, utc_date TEXT, home_team_id INT, away_team_id INT);
        CREATE TABLE predictions (id INTEGER PRIMARY KEY, match_id INT);
        CREATE TABLE prediction_outcomes (id INTEGER PRIMARY KEY, prediction_id INT);
        CREATE TABLE odds_snapshots (id INTEGER PRIMARY KEY, match_id INT, selection TEXT, source TEXT,
                                     captured_at TEXT, market_ticker TEXT);
        INSERT INTO teams VALUES (1, 'Home'), (2, 'Away');
        INSERT INTO matches VALUES (7, '2026-10-10 21:00:00.000000', 1, 2);
        INSERT INTO odds_snapshots VALUES (1, 7, 'HOME', 'kalshi', '2026-10-09 22:09:52.000000', 'KXNFLGAME-26OCT10AH-H');
    """)
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


def test_a_wal_copy_is_read_through_the_copy_open_and_leaves_no_sidecar(tmp_path, capsys):
    p = wal_copy(tmp_path / "copy.db")
    before = p.read_bytes()
    assert la.main(["--db", str(p)]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "read-only open: copy: mode=ro&immutable=1 URI (no fallback)"
    assert "tickered=1" in out.strip().splitlines()[-1]
    assert dc.sidecars(p) == []
    assert p.read_bytes() == before


def test_a_copy_with_a_wal_sidecar_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + "-wal").write_bytes(b"")
    opened = []
    monkeypatch.setattr(la, "open_read", lambda *a, **k: opened.append("live"))
    monkeypatch.setattr(la, "open_copy", lambda *a, **k: opened.append("copy"))
    assert la.main(["--db", str(p)]) == dc.EXIT_REFUSED == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "has a -wal sidecar (copy.db-wal)" in out
    assert opened == []


def test_an_absent_db_is_refused_exit_2_and_not_created(tmp_path, capsys):
    p = tmp_path / "absent.db"
    assert la.main(["--db", str(p)]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "no file at" in out
    assert not p.exists()
    assert [x for x in tmp_path.iterdir()] == []


def test_the_apps_configured_database_takes_the_live_open(tmp_path, monkeypatch, capsys):
    p = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: p.resolve())
    calls = []
    real = la.open_read

    def record(path):
        calls.append(Path(path))
        return real(path)
    monkeypatch.setattr(la, "open_read", record)
    monkeypatch.setattr(la, "open_copy", lambda *a, **k: pytest.fail("the live file took the copy open"))
    assert la.main(["--db", str(p)]) == 0
    assert [c.resolve() for c in calls] == [p.resolve()]
    assert capsys.readouterr().out.splitlines()[0].startswith("read-only open: mode=ro URI")
