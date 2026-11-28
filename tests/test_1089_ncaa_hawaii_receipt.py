"""#1089 for scripts/ncaa_hawaii_receipt.py (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4): the app's configured
database keeps its open (open_read, #421's rule); any other --db is a copy, opened mode=ro&immutable=1 with no fallback,
refused before any open (exit 2, nothing read) under data/, with a sidecar beside it, or absent. Copies here are
throwaway WAL files in tmp; the provider is never asked (--no-provider)."""
import sqlite3
from pathlib import Path

import pytest

from src.walters import db_copy as dc
import scripts.ncaa_hawaii_receipt as hr


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: a WAL-mode file with the receipt's three tables, its sidecars checkpointed away."""
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE competitions (id INTEGER PRIMARY KEY, code TEXT)")
    con.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT, sport TEXT, external_ids TEXT)")
    con.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY, competition_id INTEGER, season TEXT, utc_date TEXT, "
                "status TEXT, external_ids TEXT, home_team_id INTEGER, away_team_id INTEGER)")
    con.execute("INSERT INTO competitions VALUES (1, 'C1089')")
    con.execute("INSERT INTO teams VALUES (1, 'Hawai''i 1089', 'NFL', '{\"api_american_football\": \"901\"}')")
    con.execute("INSERT INTO teams VALUES (2, 'Wyoming 1089', 'NFL', '{}')")
    con.execute("INSERT INTO matches VALUES (32536, 1, '2026', '2026-09-06', 'FINISHED', '{}', 2, 1)")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


def _no_open(monkeypatch):
    """Every open the script could take fails the test: the refusal must come before any of them."""
    def boom(*a, **k):
        raise AssertionError("opened")
    monkeypatch.setattr(hr, "open_read", boom)
    monkeypatch.setattr(dc, "connect_copy", boom)
    monkeypatch.setattr(sqlite3, "connect", boom)


def test_a_copy_is_read_through_immutable_and_leaves_no_sidecar(tmp_path, capsys):
    p = wal_copy(tmp_path / "copy.db")
    assert hr.main(["--db", str(p), "--no-provider"]) == 0
    out = capsys.readouterr().out
    assert "read-only open: copy: mode=ro&immutable=1 URI (no fallback; addendum 582 item 4)" in out
    assert "team 1 · \"Hawai'i 1089\"" in out and "match 32536 · C1089 2026" in out
    assert dc.sidecars(p) == []                                       # no -wal, no -shm beside it


def test_a_copy_with_a_wal_sidecar_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + "-wal").write_bytes(b"")
    _no_open(monkeypatch)
    assert hr.main(["--db", str(p), "--no-provider"]) == dc.EXIT_REFUSED == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "-wal sidecar (copy.db-wal)" in out and "read-only open" not in out


def test_an_absent_db_is_refused_exit_2_and_not_created(tmp_path, capsys, monkeypatch):
    p = tmp_path / "absent.db"
    _no_open(monkeypatch)
    assert hr.main(["--db", str(p), "--no-provider"]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "no file at" in out
    assert not p.exists() and dc.sidecars(p) == []


def test_the_configured_database_keeps_its_live_open(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "live.db")
    monkeypatch.setattr(dc, "app_db", lambda: p.resolve())
    calls = []
    real = hr.open_read

    def record(path):
        calls.append(path)
        return real(path)
    monkeypatch.setattr(hr, "open_read", record)

    def no_copy(*a, **k):
        raise AssertionError("copy open taken for the live file")
    monkeypatch.setattr(dc, "connect_copy", no_copy)
    assert hr.main(["--db", str(p), "--no-provider"]) == 0
    assert calls == [Path(str(p))]
    assert "read-only open: mode=ro URI" in capsys.readouterr().out


def test_no_db_keeps_the_live_open(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "configured.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{p}")
    calls = []
    real = hr.open_read

    def record(path):
        calls.append(path)
        return real(path)
    monkeypatch.setattr(hr, "open_read", record)
    monkeypatch.setattr(dc, "classify", lambda db: pytest.fail("classify asked without a --db"))
    assert hr.main(["--no-provider"]) == 0
    assert calls == [p]
    assert "read-only open: mode=ro URI" in capsys.readouterr().out


def test_the_db_help_line_says_the_rule(capsys):
    with pytest.raises(SystemExit):
        hr.main(["--help"])
    help_text = " ".join(capsys.readouterr().out.split())
    for words in ("configured database keeps its open", "the live file's alone", "mode=ro&immutable=1", "under data/",
                  "-wal/-shm/-journal", "absent",
                  "a machine whose configuration is not loaded reads its own live file as a copy under data/ and "
                  "refuses (addendum 582 item 4)"):
        assert words in help_text


def test_a_copy_under_data_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch):
    from src.walters import mlb_pitchers_gate as mp
    data = tmp_path / "data"                                          # a tmp data/, never the repo's
    data.mkdir()
    p = wal_copy(data / "x.db")
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    _no_open(monkeypatch)
    assert hr.main(["--db", str(p), "--no-provider"]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "under the repo's data/" in out and "read-only open" not in out
    assert out.count("\n") == 1 and dc.sidecars(p) == []


def test_an_empty_db_is_refused_exit_2_nothing_opened(capsys, monkeypatch):
    _no_open(monkeypatch)
    assert hr.main(["--db", "", "--no-provider"]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: --db is empty: ") and out.count("\n") == 1


def test_the_absent_message_says_nothing_created_nothing_read(tmp_path, capsys):
    assert hr.main(["--db", str(tmp_path / "absent.db"), "--no-provider"]) == 2
    out = capsys.readouterr().out
    assert "; nothing created, nothing read" in out and "the gate never creates one" not in out


@pytest.mark.parametrize("kind", ["not_sqlite", "missing_table"])
def test_an_unreadable_copy_is_refused_in_one_line_exit_2_nothing_beside_it(tmp_path, capsys, kind):
    p = tmp_path / "copy.db"
    if kind == "not_sqlite":
        p.write_bytes(b"this is not a SQLite file at all, " * 64)
    else:
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT, sport TEXT, external_ids TEXT)")
        con.commit()
        con.close()
    before = sorted(x.name for x in tmp_path.iterdir())
    assert hr.main(["--db", str(p), "--no-provider"]) == 2
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert len(lines) == 1 and lines[0].startswith(f"REFUSED: --db {p.resolve()}: cannot be read through a "
                                                   "mode=ro&immutable=1 URI (")
    assert ("DatabaseError" if kind == "not_sqlite" else "OperationalError") in lines[0]
    assert "Traceback" not in out and "read-only open" not in out
    assert sorted(x.name for x in tmp_path.iterdir()) == before       # nothing created beside it


def test_an_unreadable_copy_closes_its_connection(tmp_path, monkeypatch, capsys):
    p = tmp_path / "copy.db"
    p.write_bytes(b"not sqlite " * 100)
    closed = []
    real = dc.connect_copy

    class Rec:
        def __init__(self, con):
            self.con = con

        def execute(self, *a):
            return self.con.execute(*a)

        def close(self):
            closed.append(True)
            self.con.close()
    monkeypatch.setattr(dc, "connect_copy", lambda path: Rec(real(path)))
    assert hr.main(["--db", str(p), "--no-provider"]) == 2
    assert closed == [True]
