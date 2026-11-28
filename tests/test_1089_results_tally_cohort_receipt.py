"""scripts/results_tally_cohort_receipt.py under #1089 (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4(c)): one of
the two live-file receipts. Its --db must be the app's configured database, which keeps its mode=ro open and its
data_version check; any other --db is refused before any open, exit 2, nothing created beside it. Throwaway files in
tmp only."""
import importlib.util
import os
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from src.walters import db_copy as dc

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "results_tally_cohort_receipt.py"


def _mod():
    spec = importlib.util.spec_from_file_location("rtc1089", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: a WAL-mode file with one table, its sidecars checkpointed away (test_db_copy's)."""
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY)")
    con.execute("INSERT INTO matches VALUES (1)")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


@pytest.fixture
def opens(monkeypatch):
    """Every sqlite3.connect the script makes (its probe, and its engine's connections through sqlite3.dbapi2, the
    module SQLAlchemy's pysqlite dialect calls), recorded and passed on."""
    import sqlite3.dbapi2 as dbapi2
    real, seen = sqlite3.connect, []

    def spy(*a, **k):
        seen.append(str(a[0]) if a else str(k.get("database")))
        return real(*a, **k)
    monkeypatch.setattr(sqlite3, "connect", spy)
    monkeypatch.setattr(dbapi2, "connect", spy)
    return seen


def test_a_copy_that_is_not_the_configured_database_is_refused_before_any_open(tmp_path, capsys, opens):
    p = wal_copy(tmp_path / "copy.db")
    (tmp_path / "exports").mkdir()
    opens.clear()
    assert _mod().main(["--db", str(p), "--exports", str(tmp_path / "exports")]) == dc.EXIT_REFUSED
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: --db ") and "is not the app's configured database" in out
    assert "## " not in out and opens == []                   # nothing opened, nothing read
    assert dc.sidecars(p) == []                               # nothing written beside it


def test_a_copy_with_a_wal_sidecar_is_refused_and_nothing_is_opened(tmp_path, capsys, opens):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + "-wal").write_bytes(b"")
    (tmp_path / "exports").mkdir()
    opens.clear()
    assert _mod().main(["--db", str(p), "--exports", str(tmp_path / "exports")]) == dc.EXIT_REFUSED
    out = capsys.readouterr().out
    assert out.startswith(f"REFUSED: --db {p} ") and "is not the app's configured database" in out
    assert opens == [] and not p.with_name(p.name + "-shm").exists()


def test_a_copy_under_data_is_refused_and_nothing_is_opened(tmp_path, capsys, monkeypatch, opens):
    """A copy under data/ (the fence's data/ pointed at a tmp folder: nothing under the repo's data/ is touched): this
    live-file receipt refuses it as not the configured database, exit 2, before any open."""
    from src.walters import mlb_pitchers_gate as mp
    data = tmp_path / "data"
    data.mkdir()
    p = wal_copy(data / "sports.db")
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    (tmp_path / "exports").mkdir()
    opens.clear()
    assert _mod().main(["--db", str(p), "--exports", str(tmp_path / "exports")]) == dc.EXIT_REFUSED
    out = capsys.readouterr().out
    assert out.startswith(f"REFUSED: --db {p} ") and "is not the app's configured database" in out
    assert "## " not in out and opens == [] and dc.sidecars(p) == []


def test_an_absent_db_is_refused_and_never_created(tmp_path, capsys, opens):
    p = tmp_path / "absent.db"
    (tmp_path / "exports").mkdir()
    opens.clear()
    assert _mod().main(["--db", str(p), "--exports", str(tmp_path / "exports")]) == dc.EXIT_REFUSED
    out = capsys.readouterr().out
    assert out.startswith(f"REFUSED: --db {p} ") and "is not the app's configured database" in out
    assert opens == [] and not p.exists()


def test_an_absent_configured_database_is_refused_as_absent_and_never_created(tmp_path, capsys, monkeypatch, opens):
    """The configured database itself absent: the live open's own refusal names the path and the absent case."""
    p = tmp_path / "sports.db"
    (tmp_path / "exports").mkdir()
    monkeypatch.setattr(dc, "app_db", lambda: p.resolve())
    opens.clear()
    assert _mod().main(["--db", str(p), "--exports", str(tmp_path / "exports")]) == dc.EXIT_REFUSED
    out = capsys.readouterr().out
    assert out.startswith(f"REFUSED: --db {p}: no file at {p.resolve()}") and "nothing created, nothing read" in out
    assert opens == [] and not p.exists() and dc.sidecars(p) == []


def test_with_no_configuration_the_db_never_becomes_the_configured_one(tmp_path, capsys, monkeypatch, opens):
    """582 item 4(d): with no configuration loaded nothing is live, and the refusal lands before the script defaults
    DATABASE_URL to the --db (else the --db would configure itself as the live file)."""
    p = wal_copy(tmp_path / "sports.db")
    (tmp_path / "exports").mkdir()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(dc, "app_db", lambda: None)
    opens.clear()
    assert _mod().main(["--db", str(p), "--exports", str(tmp_path / "exports")]) == dc.EXIT_REFUSED
    assert "is not the app's configured database" in capsys.readouterr().out
    assert "DATABASE_URL" not in os.environ and opens == []


def test_the_configured_database_takes_the_live_open(tmp_path, capsys, monkeypatch, opens):
    """With db_copy.app_db pointed at a throwaway file, the script reads it through its live open as today: the
    mode=ro probe (data_version) and the mode=ro engine, never immutable=1."""
    from src.db.schema import Base
    live = tmp_path / "sports.db"
    eng = create_engine(f"sqlite:///{live}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    (tmp_path / "exports").mkdir()
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    opens.clear()
    assert _mod().main(["--db", str(live), "--exports", str(tmp_path / "exports")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("RESULTS.md divergence cohorts BEFORE / AFTER") and "(mode=ro)" in out
    assert f"{live.resolve().as_uri()}?mode=ro" in opens                       # the data_version probe
    assert any(o.startswith(f"file:{live.resolve().as_posix()}?mode=ro") for o in opens)   # the engine's open
    assert not any("immutable=1" in o for o in opens)
