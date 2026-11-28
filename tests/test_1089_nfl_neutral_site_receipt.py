"""#1089 (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4) on scripts/nfl_neutral_site_receipt.py: the app's
configured database keeps its mode=ro open; any other --db is a copy, opened mode=ro&immutable=1 with no fallback and
refused before any open (exit 2) under data/, with a sidecar beside it, or absent. Throwaway files in tmp_path only;
a fake provider, no network, nothing under data/."""
import hashlib
import importlib.util
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from src.walters import db_copy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nsr_1089", ROOT / "scripts" / "nfl_neutral_site_receipt.py")
nsr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nsr)


def _ts(s):
    return int(datetime.fromisoformat(s + "+00:00").timestamp())


def _row(gid, ko, home, away, venue):
    g = {"id": gid, "stage": "Regular Season", "week": "Week 1", "status": {"short": "FT"},
         "date": {"timestamp": _ts(ko), "date": ko[:10], "time": ko[11:16]},
         "venue": {"name": venue[0], "city": venue[1]}}
    return {"game": g, "teams": {"home": {"id": home, "name": f"Team {home}"},
                                 "away": {"id": away, "name": f"Team {away}"}},
            "scores": {"home": {"total": 24}, "away": {"total": 17}}}


ROWS = [_row(1, "2026-09-13T17:00", 1, 2, ("A Field", "A")), _row(2, "2026-09-20T17:00", 1, 2, ("A Field", "A")),
        _row(3, "2026-09-27T17:00", 2, 1, ("B Field", "B")), _row(4, "2026-10-04T17:00", 2, 1, ("B Field", "B")),
        _row(5, "2026-10-18T13:30", 1, 2, ("Wembley Stadium", "London"))]


def fake(calls):
    def get(path, **p):
        calls.append((path, p))
        return 200, {}, ROWS if p["season"] == 2026 else []
    return get


def _schema(p: Path, wal: bool) -> Path:
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{p}", future=True)
    Base.metadata.create_all(eng)
    eng.dispose()
    if wal:                                                       # a fresh .backup-like copy: WAL, sidecars gone
        con = sqlite3.connect(p)
        con.execute("PRAGMA journal_mode=WAL")
        con.close()
        for s in db_copy.SIDECARS:
            p.with_name(p.name + s).unlink(missing_ok=True)
    return p


def run(tmp_path, db, calls, code):
    out = []
    argv = ["--seasons", "2026", "--save", str(tmp_path / "pay"), "--games-cache", str(tmp_path / "cov"),
            "--db", str(db)]
    assert nsr.main(argv, echo=out.append, get=fake(calls)) == code
    return "\n".join(out)


def _no_copy_open(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a copy open was attempted")
    monkeypatch.setattr(db_copy, "connect_copy", boom)
    monkeypatch.setattr(db_copy, "copy_engine", boom)


def test_a_wal_copy_is_read_through_the_copy_open_and_leaves_nothing_beside_it(tmp_path, monkeypatch):
    p = _schema(tmp_path / "copy.db", wal=True)
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    seen = []
    real = db_copy.copy_engine
    monkeypatch.setattr(db_copy, "copy_engine", lambda path: seen.append(path) or real(path))
    out = run(tmp_path, p, [], 0)
    assert seen == [p.resolve(), p.resolve()]                    # both opens are the copy's, never the plain one
    assert f"(mode=ro, --db {p}, a copy: mode=ro&immutable=1)" in out
    assert "NFL matches by season none" in out
    assert db_copy.sidecars(p) == []                              # immutable=1: no -wal / -shm written beside it
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before
    with nsr.ro_session(str(p)) as s:                             # and never written
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError
        with pytest.raises(OperationalError):
            s.execute(text("CREATE TABLE x (a)"))
    assert db_copy.sidecars(p) == []


@pytest.mark.parametrize("side", db_copy.SIDECARS)
def test_a_copy_with_a_sidecar_is_refused_exit_2_nothing_opened(tmp_path, monkeypatch, side):
    p = _schema(tmp_path / "copy.db", wal=True)
    p.with_name(p.name + side).write_bytes(b"")
    _no_copy_open(monkeypatch)
    calls = []
    out = run(tmp_path, p, calls, 2)
    assert out.splitlines()[-1].startswith("REFUSED: ") and f"has a {side} sidecar ({p.name}{side})" in out
    assert calls == [] and "D the database" not in out          # nothing read, no provider call


def test_an_absent_copy_is_refused_exit_2_and_never_created(tmp_path, monkeypatch):
    p = tmp_path / "absent.db"
    _no_copy_open(monkeypatch)
    calls = []
    out = run(tmp_path, p, calls, 2)
    assert "REFUSED: no DB file at --db" in out and calls == []
    assert not p.exists() and db_copy.sidecars(p) == []


def test_a_copy_under_data_is_refused_exit_2(tmp_path, monkeypatch):
    from src.walters import mlb_pitchers_gate as mp
    data = tmp_path / "data"
    data.mkdir()
    p = _schema(data / "x.db", wal=True)
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    _no_copy_open(monkeypatch)
    calls = []
    out = run(tmp_path, p, calls, 2)
    assert "REFUSED: " in out and "under the repo's data/" in out and calls == []


def test_the_apps_configured_database_takes_the_live_open(tmp_path, monkeypatch):
    import sqlalchemy
    p = _schema(tmp_path / "sports.db", wal=False)
    monkeypatch.setattr(db_copy, "app_db", lambda: p.resolve())
    _no_copy_open(monkeypatch)                                    # the live file never takes the copy's open
    urls = []
    real = sqlalchemy.create_engine
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda url, **k: urls.append((url, k)) or real(url, **k))
    out = run(tmp_path, p, [], 0)
    live = [(u, k) for u, k in urls if u == f"sqlite:///file:{p.resolve().as_posix()}?mode=ro&uri=true"]
    assert len(live) == 2 and all(k["connect_args"] == {"uri": True, "check_same_thread": False} for _u, k in live)
    assert f"(mode=ro, --db {p}):" in out and "immutable" not in out.split("NFL matches")[0].split("D the database")[1]
