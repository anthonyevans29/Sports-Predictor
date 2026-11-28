"""#1089 on scripts/lineup_timing_probe.py (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4): the app's configured
database keeps its open (open_read: mode=ro, #421's fallback); any other --db is a copy, opened mode=ro&immutable=1 with
no fallback, and refused before any open (exit 2) under data/, with a sidecar beside it, or absent. Copies here are
throwaway WAL files in tmp_path, built from the app's own schema; never data/, never the configured DB."""
import importlib.util
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from src.db.schema import Base
from src.walters import db_copy as dc

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lineup_timing_probe_1089", ROOT / "scripts" / "lineup_timing_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

DAY = "2026-10-20"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def sleep(self, s):
        raise AssertionError("no poll is made on an empty day")


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
    clock = Clock()
    rc = probe.run(["--db", str(db), "--date", DAY], clock=clock, sleep=clock.sleep)
    return rc, capsys.readouterr().out


def test_a_copy_is_read_through_its_own_open_and_leaves_no_sidecar(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    seen = []
    real = dc.connect_copy
    monkeypatch.setattr(probe.db_copy, "connect_copy", lambda path: seen.append(path) or real(path))
    monkeypatch.setattr(probe, "open_read", lambda *a: pytest.fail("a copy took the live file's open"))
    rc, out = run(p, capsys)
    assert seen == [p.resolve()]
    assert "opened via mode=ro URI with immutable=1 (a copy; no fallback)" in out
    assert "0 CL row(s) stored with a kickoff on 2026-10-20" in out and rc == 1     # read, nothing to poll
    assert dc.sidecars(p) == []                                                      # immutable=1: nothing beside it


@pytest.mark.parametrize("side", dc.SIDECARS)
def test_a_copy_with_a_sidecar_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch, side):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + side).write_bytes(b"")
    monkeypatch.setattr(probe.sqlite3, "connect", lambda *a, **k: pytest.fail("a refused copy was opened"))
    monkeypatch.setattr(probe.db_copy, "connect_copy", lambda *a: pytest.fail("a refused copy was opened"))
    rc, out = run(p, capsys)
    assert rc == 2 == dc.EXIT_REFUSED
    assert f"REFUSED: --db {p} has a {side} sidecar (copy.db{side})" in out
    assert "D0 database" not in out and "row(s) stored" not in out                  # the path printed, never a row


def test_an_absent_copy_is_refused_exit_2_and_never_created(tmp_path, capsys, monkeypatch):
    p = tmp_path / "absent.db"
    monkeypatch.setattr(probe.sqlite3, "connect", lambda *a, **k: pytest.fail("an absent copy was opened"))
    rc, out = run(p, capsys)
    assert rc == 2 and "REFUSED: " in out and str(p) in out and "D0 database" not in out
    assert not p.exists() and dc.sidecars(p) == []


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
    assert seen == [Path(str(live))] and "opened via mode=ro URI\n" in out and rc == 1


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
        probe.run(["--help"])
    out = " ".join(capsys.readouterr().out.split())
    for words in ("configured database keeps its open", "mode=ro&immutable=1", "under data/",
                  "-wal/-shm/-journal sidecar", "or absent", "reads its live file as a copy", "addendum 582 item 4"):
        assert words in out
