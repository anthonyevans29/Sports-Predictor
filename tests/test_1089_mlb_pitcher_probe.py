"""#1089 on scripts/mlb_pitcher_probe.py (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4): the app's configured
database keeps its open (open_read: mode=ro, #421's fallback); any other --db is a copy, opened mode=ro&immutable=1 with
no fallback, and refused before any open (exit 2) under data/, with a sidecar beside it, or absent. Copies here are
throwaway WAL files in tmp_path, built from the app's own schema; never data/, never the configured DB."""
import importlib.util
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from src.db.schema import Base
from src.walters import db_copy as dc

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mlb_pitcher_probe_1089", ROOT / "scripts" / "mlb_pitcher_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: the app's schema in a WAL-mode file, its sidecars checkpointed away."""
    eng = create_engine(f"sqlite:///{p}")
    Base.metadata.create_all(eng)
    eng.dispose()
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    assert dc.sidecars(p) == []
    return p


def run(db, capsys):
    rc = probe.main(["--db", str(db), "--no-network"])
    return rc, capsys.readouterr().out


def test_a_copy_is_read_through_its_own_open_and_leaves_no_sidecar(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    seen = []
    real = dc.connect_copy
    monkeypatch.setattr(probe.db_copy, "connect_copy", lambda path: seen.append(path) or real(path))
    monkeypatch.setattr(probe, "open_read", lambda *a: pytest.fail("a copy took the live file's open"))
    rc, out = run(p, capsys)
    assert rc == 0 and seen == [p.resolve()]
    assert "opened via mode=ro URI with immutable=1 (a copy; no fallback)" in out
    assert "competition MLB: games by stored season none" in out                       # read, nothing stored
    assert dc.sidecars(p) == []                                                        # immutable=1: nothing beside it


@pytest.mark.parametrize("side", dc.SIDECARS)
def test_a_copy_with_a_sidecar_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch, side):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + side).write_bytes(b"")
    monkeypatch.setattr(probe.sqlite3, "connect", lambda *a, **k: pytest.fail("a refused copy was opened"))
    monkeypatch.setattr(probe.db_copy, "connect_copy", lambda *a: pytest.fail("a refused copy was opened"))
    rc, out = run(p, capsys)
    assert rc == 2 == dc.EXIT_REFUSED
    assert f"REFUSED: --db {p} has a {side} sidecar (copy.db{side})" in out
    assert "D0 database" not in out and "games by stored season" not in out           # the path printed, never a row


def test_an_absent_copy_is_refused_exit_2_and_never_created(tmp_path, capsys, monkeypatch):
    p = tmp_path / "absent.db"
    monkeypatch.setattr(probe.sqlite3, "connect", lambda *a, **k: pytest.fail("an absent copy was opened"))
    rc, out = run(p, capsys)
    assert rc == 2 and f"REFUSED: --db {p}: no file at" in out and "nothing created, nothing read" in out
    assert "the gate never creates one" not in out and "D0 database" not in out
    assert not p.exists() and dc.sidecars(p) == []


def test_an_empty_db_is_refused_exit_2_never_read_as_no_db(capsys, monkeypatch):
    monkeypatch.setattr(probe, "open_read", lambda *a: pytest.fail("an empty --db took the live file's open"))
    monkeypatch.setattr(probe.db_copy, "connect_copy", lambda *a: pytest.fail("an empty --db was opened"))
    rc, out = run("", capsys)
    assert rc == 2 and "REFUSED: --db is empty: " in out and "D0 database" not in out


@pytest.mark.parametrize("case", ["not_sqlite", "no_matches_table"])
def test_a_copy_immutable_cannot_read_is_one_refused_line_exit_2(tmp_path, capsys, monkeypatch, case):
    """582 item 4 on a copy past the fence: not a SQLite file, or a table the probe needs missing; one REFUSED line
    naming the path and the error class, the connection closed, no traceback, no fallback, nothing beside it."""
    p = tmp_path / "copy.db"
    if case == "not_sqlite":
        p.write_bytes(b"this is not a sqlite database, not even close" * 20)
    else:
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE competitions (id INTEGER)")
        con.commit()
        con.close()
    before = sorted(x.name for x in tmp_path.iterdir())
    closed = []
    real = dc.connect_copy

    def tracked(path):
        con = real(path)

        class Wrap:
            def execute(self, *a):
                return con.execute(*a)

            def close(self):
                closed.append(True)
                con.close()
        return Wrap()
    monkeypatch.setattr(probe.db_copy, "connect_copy", tracked)
    monkeypatch.setattr(probe, "open_read", lambda *a: pytest.fail("a copy took the live file's open"))
    rc, out = run(p, capsys)
    lines = [ln for ln in out.splitlines() if "REFUSED" in ln]
    err = "DatabaseError" if case == "not_sqlite" else "OperationalError"
    assert rc == 2 and len(lines) == 1 and f"REFUSED: --db {p.resolve()}: " in lines[0] and err in lines[0]
    assert "no fallback; nothing read" in lines[0] and "Traceback" not in out and "D0 database" not in out
    assert closed == [True]
    assert sorted(x.name for x in tmp_path.iterdir()) == before                        # nothing created beside it


def test_a_copy_under_data_is_refused_exit_2(tmp_path, capsys, monkeypatch):
    from src.walters import mlb_pitchers_gate as mp
    data = tmp_path / "data"
    data.mkdir()
    p = wal_copy(data / "sports.db")
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    rc, out = run(p, capsys)
    assert rc == 2 and "under the repo's data/" in out and "D0 database" not in out


def test_the_apps_configured_database_takes_the_live_open(tmp_path, capsys, monkeypatch):
    live = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    seen = []
    real = probe.open_read
    monkeypatch.setattr(probe, "open_read", lambda path: seen.append(path) or real(path))
    monkeypatch.setattr(probe.db_copy, "connect_copy", lambda *a: pytest.fail("the live file took the copy open"))
    rc, out = run(live, capsys)
    assert rc == 0 and seen == [Path(str(live))] and "opened via mode=ro URI\n" in out


def test_a_machine_without_configuration_reads_its_live_file_as_a_copy_under_data(tmp_path, capsys, monkeypatch):
    """582 item 4(d): no configuration loaded, nothing is live; the live file under data/ is a copy, refused."""
    from src.walters import mlb_pitchers_gate as mp
    data = tmp_path / "data"
    data.mkdir()
    p = wal_copy(data / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: None)
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    rc, out = run(p, capsys)
    assert rc == 2 and "under the repo's data/" in out


def test_the_db_help_line_names_the_rule(capsys):
    with pytest.raises(SystemExit):
        probe.main(["--help"])
    out = " ".join(capsys.readouterr().out.split())
    for words in ("configured database keeps its open", "mode=ro&immutable=1", "under data/",
                  "-wal/-shm/-journal sidecar", "or absent",
                  "a machine whose configuration is not loaded reads its own live file as a copy under data/ and refuses (addendum 582 item 4)"):
        assert words in out


def test_a_copy_past_the_fence_sqlite_cannot_open_is_one_refused_line_exit_2(tmp_path, capsys, monkeypatch):
    """db_copy.connect_copy (7a66e7f8) on a copy the fence passed but SQLite cannot open through mode=ro&immutable=1:
    through the probe's own main(), one REFUSED line naming the path and the error class, exit 2, no traceback, no
    fallback (no other open of it), nothing created beside it. The stub refuses only an immutable=1 URI and hands every
    other connect to the real one. The probe opens a copy by connect_copy alone (no SQLAlchemy engine); copy_engine's
    pool is proved here too to pass CopyRefused through unwrapped (a non-DBAPI error is not made a DBAPIError)."""
    p = wal_copy(tmp_path / "copy.db")
    before = sorted(x.name for x in tmp_path.iterdir())
    real = sqlite3.connect
    asked = []

    def stub(database, *a, **k):
        asked.append(str(database))
        if "immutable=1" in str(database):
            raise sqlite3.OperationalError("unable to open database file")
        return real(database, *a, **k)
    monkeypatch.setattr(dc.sqlite3, "connect", stub)
    monkeypatch.setattr(probe, "open_read", lambda *a: pytest.fail("a copy took the live file's open"))
    rc, out = run(p, capsys)
    lines = [ln for ln in out.splitlines() if "REFUSED" in ln]
    assert rc == 2 == dc.EXIT_REFUSED
    assert lines == [f"✗ REFUSED: --db {p.resolve()}: cannot be opened through a mode=ro&immutable=1 URI "
                     "(OperationalError); no fallback; nothing read"]
    assert "Traceback" not in out and "D0 database" not in out and "games by stored season" not in out
    assert asked == [dc.copy_uri(p)]                                                   # one open, the copy URI, no fallback
    assert sorted(x.name for x in tmp_path.iterdir()) == before and dc.sidecars(p) == []

    eng = dc.copy_engine(p.resolve())
    try:
        with pytest.raises(dc.CopyRefused) as ei:
            eng.connect()
    finally:
        eng.dispose()
    assert type(ei.value) is dc.CopyRefused and str(ei.value) == lines[0][2:]
    assert sorted(x.name for x in tmp_path.iterdir()) == before
