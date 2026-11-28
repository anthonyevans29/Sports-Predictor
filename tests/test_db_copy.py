"""src/walters/db_copy (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4; #1089): the live file is the app's
configured database and keeps its open; any other --db is a copy, opened mode=ro&immutable=1 with no fallback, refused
before any open under data/, with a sidecar beside it, or absent. Copies here are throwaway WAL files in tmp."""
import sqlite3
from pathlib import Path

import pytest

from src.walters import db_copy as dc


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


def test_a_copy_classifies_as_copy_and_opens_without_writing_a_sidecar(tmp_path):
    p = wal_copy(tmp_path / "copy.db")
    kind, path = dc.classify(p)
    assert (kind, path) == ("copy", p.resolve())
    con = dc.connect_copy(path)
    assert con.execute("SELECT count(*) FROM matches").fetchone() == (1,)
    con.close()
    assert dc.sidecars(p) == []                                   # immutable=1: nothing created beside it
    with pytest.raises(sqlite3.OperationalError):                 # and never written
        c2 = dc.connect_copy(path)
        c2.execute("INSERT INTO matches VALUES (2)")


def test_the_engine_reads_the_copy_through_the_same_uri(tmp_path):
    from sqlalchemy import text
    p = wal_copy(tmp_path / "copy.db")
    eng = dc.copy_engine(dc.check_copy(p))
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM matches")).scalar() == 1
    eng.dispose()
    assert dc.sidecars(p) == []


@pytest.mark.parametrize("side", dc.SIDECARS)
def test_a_copy_with_a_sidecar_is_refused_before_any_open(tmp_path, side):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + side).write_bytes(b"")
    with pytest.raises(dc.CopyRefused, match=f"has a {side} sidecar"):
        dc.classify(p)


def test_an_absent_copy_is_refused_and_never_created(tmp_path):
    p = tmp_path / "absent.db"
    with pytest.raises(dc.CopyRefused, match="no file at"):
        dc.classify(p)
    assert not p.exists()


def test_a_copy_under_data_is_refused(monkeypatch, tmp_path):
    from src.walters import mlb_pitchers_gate as mp
    data = tmp_path / "data"
    data.mkdir()
    p = wal_copy(data / "x.db")
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    with pytest.raises(dc.CopyRefused, match="under the repo's data/"):
        dc.classify(p)


def test_the_apps_configured_database_is_live_by_path_and_by_identity(monkeypatch, tmp_path):
    live = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    assert dc.classify(live) == ("live", live.resolve())
    link = tmp_path / "link.db"
    link.hardlink_to(live)
    assert dc.is_live(link)                                       # by identity: a hard link is the same file
    assert dc.require_live(live) == live.resolve()


def test_with_no_configuration_nothing_is_live(monkeypatch, tmp_path):
    """582 item 4(d): a machine whose configuration is not loaded reads its own live file as a copy (and under data/,
    refuses)."""
    p = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: None)
    assert not dc.is_live(p)
    with pytest.raises(dc.CopyRefused, match="not the app's configured database"):
        dc.require_live(p)


def test_a_refusal_names_the_path_and_no_row(tmp_path):
    p = tmp_path / "absent.db"
    with pytest.raises(dc.CopyRefused) as e:
        dc.check_copy(p)
    assert str(p) in str(e.value) and str(e.value).startswith("REFUSED: ")
