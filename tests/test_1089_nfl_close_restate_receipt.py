"""scripts/nfl_close_restate_receipt.py under #1089 (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4): one of the
two live-file receipts (item 4(c)). Its --db must be the app's configured database, which keeps its open (mode=ro and
the data_version check); any other file is refused before any open, exit 2, nothing read. Throwaway files in tmp."""
import importlib.util
import json
import sqlite3
from pathlib import Path

from src.walters import db_copy as dc


def _mod():
    spec = importlib.util.spec_from_file_location(
        "nfl_close_restate_receipt", Path(__file__).resolve().parent.parent / "scripts" / "nfl_close_restate_receipt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: a WAL-mode file with one table, its sidecars checkpointed away."""
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY)")
    con.execute("INSERT INTO matches VALUES (1)")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


def _record_connects(monkeypatch):
    """Every sqlite3.connect the receipt makes (the probe and SQLAlchemy's pysqlite both call it), recorded."""
    calls = []
    real = sqlite3.connect

    def rec(*a, **k):
        calls.append(str(a[0]) if a else str(k.get("database")))
        return real(*a, **k)
    monkeypatch.setattr(sqlite3, "connect", rec)
    return calls


def test_a_wal_copy_is_refused_before_any_open_and_nothing_is_written_beside_it(tmp_path, monkeypatch, capsys):
    p = wal_copy(tmp_path / "copy.db")
    before = p.read_bytes()
    ex = tmp_path / "exports"
    ex.mkdir()
    calls = _record_connects(monkeypatch)
    assert _mod().main(["--db", str(p), "--exports", str(ex)]) == dc.EXIT_REFUSED == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "is not the app's configured database" in out
    assert calls == []                                                  # nothing opened
    assert dc.sidecars(p) == [] and p.read_bytes() == before            # nothing beside it, nothing written


def test_a_copy_with_a_wal_sidecar_is_refused_and_the_sidecar_left_as_it_was(tmp_path, monkeypatch, capsys):
    p = wal_copy(tmp_path / "copy.db")
    side = p.with_name(p.name + "-wal")
    side.write_bytes(b"stale")
    ex = tmp_path / "exports"
    ex.mkdir()
    calls = _record_connects(monkeypatch)
    assert _mod().main(["--db", str(p), "--exports", str(ex)]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and str(p) in out and "nothing read" in out
    assert calls == [] and side.read_bytes() == b"stale" and dc.sidecars(p) == ["copy.db-wal"]


def test_an_absent_db_is_refused_and_never_created(tmp_path, monkeypatch, capsys):
    p = tmp_path / "absent.db"
    calls = _record_connects(monkeypatch)
    assert _mod().main(["--db", str(p), "--exports", str(tmp_path)]) == 2
    assert capsys.readouterr().out.startswith("REFUSED: ")
    assert calls == [] and not p.exists()


def test_the_apps_configured_database_takes_the_live_open(tmp_path, monkeypatch, capsys):
    live = tmp_path / "sports.db"
    con = sqlite3.connect(live)                                         # a rollback-journal file: no sidecar to make
    con.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    ex = tmp_path / "exports"
    ex.mkdir()
    from src.db import database
    from src.walters import nfl_predict
    seen = {}

    def fake_export(out_dir):
        seen.setdefault("engines", []).append(str(database._engine.url))
        with database._engine.connect() as c:
            seen["n"] = c.exec_driver_sql("SELECT count(*) FROM matches").scalar()
        f = Path(out_dir) / "nfl_results.json"
        f.write_text(json.dumps({"record": {}, "results": []}))
        return str(f)
    monkeypatch.setattr(nfl_predict, "export_nfl_results", fake_export)
    monkeypatch.setattr(nfl_predict, "grade_nfl", lambda days_back=None, exports_dir=None: {})
    calls = _record_connects(monkeypatch)
    assert _mod().main(["--db", str(live), "--exports", str(ex)]) == 0
    out = capsys.readouterr().out
    assert "read-only: db sports.db (mode=ro)" in out and "data_version unchanged" in out
    # the live open as before: the data_version probe on "?mode=ro" (no immutable=1) and the engine's mode=ro URI
    assert f"{live.resolve().as_uri()}?mode=ro" in calls
    assert all("immutable" not in c for c in calls)
    assert seen["n"] == 0 and len(seen["engines"]) == 2
    assert all("mode=ro" in e and "immutable" not in e for e in seen["engines"])
    assert dc.sidecars(live) == []
