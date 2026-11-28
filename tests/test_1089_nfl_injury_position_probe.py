"""#1089 (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4) for scripts/nfl_injury_position_probe.py: the app's
configured database keeps its open (open_read, #421's rule); any other --db is a copy, opened mode=ro&immutable=1 with
no fallback, refused with exit 2 before any open under data/, with a sidecar beside it, or absent. Copies are throwaway
WAL files in tmp_path; the provider is never asked (no stored name, and get_json is fenced)."""
import sqlite3
from pathlib import Path

import pytest

from src.walters import db_copy as dc
import scripts.nfl_injury_position_probe as pp


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: a WAL-mode file with the tables the probe reads (no rows), sidecars removed."""
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE injuries (id INTEGER PRIMARY KEY, team_id INTEGER, player_name TEXT, "
                "player_position TEXT, refreshed_at TEXT)")
    con.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT, external_ids TEXT)")
    con.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY, competition_id INTEGER, home_team_id INTEGER, "
                "away_team_id INTEGER)")
    con.execute("CREATE TABLE competitions (id INTEGER PRIMARY KEY, code TEXT)")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


@pytest.fixture(autouse=True)
def _no_provider(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the provider is never asked in these tests")
    monkeypatch.setattr(pp, "get_json", refuse)


def _no_open(monkeypatch):
    calls = []
    monkeypatch.setattr(pp, "open_read", lambda p: calls.append(("live", p)) or (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(dc, "connect_copy", lambda p: calls.append(("copy", p)) or (_ for _ in ()).throw(AssertionError))
    return calls


def test_a_copy_is_read_through_mode_ro_immutable_and_leaves_no_sidecar(tmp_path, capsys):
    p = wal_copy(tmp_path / "copy.db")
    assert pp.main(["--db", str(p)]) == 0
    out = capsys.readouterr().out
    assert "read-only open: copy: mode=ro&immutable=1 URI (no fallback; addendum 582 item 4)" in out
    assert "stored NFL injured players with no position: 0" in out
    assert dc.sidecars(p) == []


def test_a_copy_with_a_wal_sidecar_is_refused_exit_2_nothing_opened(tmp_path, monkeypatch, capsys):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + "-wal").write_bytes(b"")
    calls = _no_open(monkeypatch)
    assert pp.main(["--db", str(p)]) == dc.EXIT_REFUSED == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "has a -wal sidecar (copy.db-wal)" in out
    assert calls == []


def test_an_absent_db_is_refused_exit_2_and_never_created(tmp_path, monkeypatch, capsys):
    p = tmp_path / "absent.db"
    calls = _no_open(monkeypatch)
    assert pp.main(["--db", str(p)]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "no file at" in out
    assert calls == [] and not p.exists()
    assert dc.sidecars(p) == []


def test_the_apps_configured_database_takes_the_live_open(tmp_path, monkeypatch, capsys):
    live = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    calls = []

    def live_open(p):
        calls.append(p)
        return sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True), "mode=ro URI"
    monkeypatch.setattr(pp, "open_read", live_open)
    monkeypatch.setattr(dc, "connect_copy", lambda p: (_ for _ in ()).throw(AssertionError("copy open on live")))
    assert pp.main(["--db", str(live)]) == 0
    assert calls == [Path(str(live))]
    assert "read-only open: mode=ro URI" in capsys.readouterr().out
