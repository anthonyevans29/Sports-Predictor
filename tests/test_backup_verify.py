"""ARCHITECT 2026-10-03: dedupe-matches --apply refused a real 245 MB .backup with "unable to open
database file" — the read-only open was f"file:{path}?mode=ro", invalid for a Windows absolute path
(and any path with a space, # or ?). The shared verifier opens Path.as_uri() and names WHICH check
failed and the path it tried. Tested against a REAL backup file in a directory with a space and '#'."""
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.db.database import get_engine, init_db


def _backup_of_live(dest: Path) -> Path:
    init_db()
    live = get_engine().url.database
    dest.parent.mkdir(parents=True, exist_ok=True)
    src, dst = sqlite3.connect(live), sqlite3.connect(dest)
    with dst:
        src.backup(dst)                       # the .backup API, as the operator takes it
    src.close()
    dst.close()
    return dest


def run(args):
    from cli import cli
    return CliRunner().invoke(cli, args)


def test_a_real_backup_in_an_awkward_path_verifies(tmp_path):
    bp = _backup_of_live(tmp_path / "my backups #1" / "sports 2026-10-03.db")
    out = run(["dedupe-matches", "--competition", "NCAA", "--apply", "--backup", str(bp)])
    assert "backup verified:" in out.output and "integrity ok" in out.output, out.output


def test_tilde_is_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _backup_of_live(tmp_path / "backups" / "sports.db")
    out = run(["dedupe-matches", "--competition", "NCAA", "--apply", "--backup", "~/backups/sports.db"])
    assert "backup verified:" in out.output, out.output


@pytest.mark.parametrize("make,check", [
    (lambda p: None, "check: --backup given"),
    (lambda p: str(p / "nope.db"), "check: file exists"),
    (lambda p: str(p), "check: is a file"),
])
def test_each_refusal_names_its_check_and_path(tmp_path, make, check):
    arg = make(tmp_path)
    out = run(["dedupe-matches", "--competition", "NCAA", "--apply"] + (["--backup", arg] if arg else []))
    assert out.exit_code != 0 and check in out.output, out.output
    if arg:
        assert arg in out.output                                   # the path it tried


def test_not_a_database_and_count_mismatch_are_named(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not sqlite at all" * 100)
    out = run(["dedupe-matches", "--competition", "NCAA", "--apply", "--backup", str(junk)])
    assert "check: opens as SQLite" in out.output or "check: integrity_check" in out.output, out.output
    small = tmp_path / "small.db"
    con = sqlite3.connect(small)
    live = sqlite3.connect(get_engine().url.database).execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    con.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY)")
    con.executemany("INSERT INTO matches (id) VALUES (?)", [(i,) for i in range(live + 1)])
    con.commit()
    con.close()
    out = run(["dedupe-matches", "--competition", "NCAA", "--apply", "--backup", str(small)])
    assert "check: matches count = live" in out.output and f"has {live + 1}, the live DB {live}" in out.output, out.output


def _fail_uri(monkeypatch):
    """The macOS refusal (ARCHITECT 2026-10-03): the read-only URI form raises "unable to open database
    file" on an existing backup. Every other open is real."""
    real = sqlite3.connect

    def fake(target, *a, **kw):
        if kw.get("uri"):
            raise sqlite3.OperationalError("unable to open database file")
        return real(target, *a, **kw)
    monkeypatch.setattr(sqlite3, "connect", fake)


def test_macos_path_uri_refusal_falls_back_to_a_plain_read(tmp_path, monkeypatch):
    bp = _backup_of_live(tmp_path / "Users" / "anthonyevans" / "backups" / "sports_preorphans.db")
    before = bp.read_bytes()
    _fail_uri(monkeypatch)
    out = run(["dedupe-matches", "--competition", "NCAA", "--apply", "--backup", str(bp)])
    assert "backup verified:" in out.output, out.output
    assert "opened via plain path, query_only" in out.output
    assert "after: uri mode=ro: OperationalError: unable to open database file" in out.output
    assert "integrity ok (quick_check)" in out.output and "journal_mode" in out.output
    assert bp.read_bytes() == before                                    # the fallback read wrote nothing


def test_both_open_forms_failing_names_both(tmp_path, monkeypatch):
    junk = tmp_path / "Users" / "anthonyevans" / "backups" / "junk.db"
    junk.parent.mkdir(parents=True)
    junk.write_bytes(b"not sqlite at all" * 100)
    _fail_uri(monkeypatch)
    out = run(["dedupe-matches", "--competition", "NCAA", "--apply", "--backup", str(junk)])
    assert out.exit_code != 0 and "check: opens as SQLite with table matches" in out.output, out.output
    assert "uri mode=ro: OperationalError: unable to open database file" in out.output
    assert "plain path, query_only: DatabaseError" in out.output and str(junk) in out.output


def test_the_plain_fallback_cannot_write(tmp_path):
    """query_only: the fallback form is a read — a write through it raises."""
    db = tmp_path / "x.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY)")
    con.commit()
    con.execute("PRAGMA query_only = ON")
    with pytest.raises(sqlite3.OperationalError):
        con.execute("INSERT INTO matches (id) VALUES (1)")
    con.close()
