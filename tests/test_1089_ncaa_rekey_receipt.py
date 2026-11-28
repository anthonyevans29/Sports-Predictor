"""#1089 for scripts/ncaa_rekey_receipt.py (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4): the app's configured
database keeps its open (sp_common.ro_connect; open_read, #421's fallback, under --reconstruct-merges); any other --db
is a copy, opened mode=ro&immutable=1 with no fallback, refused before any open (exit 2, nothing read) under data/,
with a sidecar beside it, or absent. Copies here are throwaway WAL files in tmp; the provider is never asked."""
import sqlite3
import sys
from pathlib import Path

import pytest

from src.walters import db_copy as dc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ncaa_rekey_receipt as rr  # noqa: E402

NOW = "2092-10-03T16:48:00"


def _tables(con):
    con.execute("CREATE TABLE competitions (id INTEGER PRIMARY KEY, code TEXT)")
    con.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY, competition_id INTEGER, home_team_id INTEGER, "
                "away_team_id INTEGER, utc_date TEXT, status TEXT, status_raw TEXT, home_score INTEGER, "
                "away_score INTEGER, external_ids TEXT)")
    con.execute("CREATE TABLE odds (id INTEGER PRIMARY KEY, match_id INTEGER REFERENCES matches(id))")
    con.execute("CREATE TABLE odds_snapshots (id INTEGER PRIMARY KEY, match_id INTEGER REFERENCES matches(id))")
    con.execute("INSERT INTO competitions VALUES (1, 'C1089')")
    con.execute("INSERT INTO teams VALUES (1, 'Georgia 1089'), (2, 'Alabama 1089')")
    con.execute("INSERT INTO matches VALUES (7, 1, 2, 1, '2092-10-03T19:48:00', 'SCHEDULED', 'NS', NULL, NULL, "
                "'{\"api_american_football\": \"23612\"}')")
    con.commit()


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: a WAL-mode file with the receipt's tables, its sidecars checkpointed away."""
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    _tables(con)
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


def _no_open(monkeypatch):
    """Every open the script could take fails the test: the refusal must come before any of them."""
    def boom(*a, **k):
        raise AssertionError("opened")
    monkeypatch.setattr(rr.c, "ro_connect", boom)
    monkeypatch.setattr(rr, "open_read", boom)
    monkeypatch.setattr(dc, "connect_copy", boom)
    monkeypatch.setattr(sqlite3, "connect", boom)


def test_a_copy_is_read_through_immutable_and_leaves_no_sidecar(tmp_path, capsys):
    p = wal_copy(tmp_path / "copy.db")
    assert rr.main(["--competition", "C1089", "--db", str(p), "--now", NOW, "--ids", "7"]) == 0
    out = capsys.readouterr().out
    assert "(read-only, copy: mode=ro&immutable=1)" in out
    assert "1. rows 1 ·" in out and "id 7 · Georgia 1089 @ Alabama 1089" in out
    assert dc.sidecars(p) == []                                       # no -wal, no -shm beside it


def test_reconstruct_on_a_copy_takes_the_copy_open_not_the_fallback(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    pre = tmp_path / "pre.backup"                                     # rollback-journal file: the --backup's own open
    con = sqlite3.connect(pre)
    _tables(con)
    con.close()
    opened = []
    real = rr.open_read

    def record(path):
        opened.append(Path(path))
        return real(path)
    monkeypatch.setattr(rr, "open_read", record)
    assert rr.main(["--competition", "C1089", "--db", str(p), "--now", NOW, "--reconstruct-merges",
                    "--backup", str(pre)]) == 0
    out = capsys.readouterr().out
    assert "RECONSTRUCTION: merges 0" in out
    assert opened == [pre]                                            # the --db copy never reaches open_read
    assert dc.sidecars(p) == []


def test_a_copy_with_a_wal_sidecar_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + "-wal").write_bytes(b"")
    _no_open(monkeypatch)
    assert rr.main(["--competition", "C1089", "--db", str(p), "--now", NOW]) == dc.EXIT_REFUSED == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "-wal sidecar (copy.db-wal)" in out and "NCAA RE-KEY RECEIPT" not in out


def test_an_absent_db_is_refused_exit_2_and_not_created(tmp_path, capsys, monkeypatch):
    p = tmp_path / "absent.db"
    _no_open(monkeypatch)
    assert rr.main(["--competition", "C1089", "--db", str(p), "--now", NOW]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "no file at" in out and "NCAA RE-KEY RECEIPT" not in out
    assert not p.exists() and dc.sidecars(p) == []


def test_the_configured_database_keeps_its_live_open(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "live.db")
    monkeypatch.setattr(dc, "app_db", lambda: p.resolve())
    calls = []
    real = rr.c.ro_connect

    def record(path):
        calls.append(path)
        return real(path)
    monkeypatch.setattr(rr.c, "ro_connect", record)

    def no_copy(*a, **k):
        raise AssertionError("copy open taken for the live file")
    monkeypatch.setattr(dc, "connect_copy", no_copy)
    assert rr.main(["--competition", "C1089", "--db", str(p), "--now", NOW]) == 0
    assert calls == [Path(str(p))]
    out = capsys.readouterr().out
    assert f"db {p} (read-only) ·" in out and "immutable" not in out


def test_no_db_keeps_the_live_open(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "configured.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{p}")
    calls = []
    real = rr.c.ro_connect

    def record(path):
        calls.append(path)
        return real(path)
    monkeypatch.setattr(rr.c, "ro_connect", record)
    monkeypatch.setattr(dc, "classify", lambda db: pytest.fail("classify asked without a --db"))
    assert rr.main(["--competition", "C1089", "--now", NOW]) == 0
    assert calls == [p]
    assert f"db {p} (read-only) ·" in capsys.readouterr().out


def test_the_db_help_line_says_the_rule(capsys):
    with pytest.raises(SystemExit):
        rr.main(["--help"])
    help_text = " ".join(capsys.readouterr().out.split())
    for words in ("configured database keeps its open", "mode=ro&immutable=1", "under data/", "-wal/-shm/-journal",
                  "absent", "without the app's configuration loaded reads its live file as a copy",
                  "addendum 582 item 4"):
        assert words in help_text
