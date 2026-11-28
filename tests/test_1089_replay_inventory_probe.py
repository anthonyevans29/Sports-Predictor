"""#1089 (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4) for scripts/replay_inventory_probe.py: the app's
configured database keeps its open (mode=ro, the #421 fallback); any other --db is a copy, opened mode=ro&immutable=1
with no fallback, refused before any open (exit 2) with a sidecar beside it or absent. Throwaway WAL files in tmp,
never data/."""
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine

import scripts.replay_inventory_probe as rip
from src.db.schema import Base
from src.walters import db_copy as dc

COPY_FORM = "copy: mode=ro&immutable=1 URI (no fallback)"


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: the app's schema in a WAL-mode file with one graded game, its sidecars removed."""
    eng = create_engine(f"sqlite:///{p}")
    Base.metadata.create_all(eng)
    eng.dispose()
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("INSERT INTO competitions (id, code, name, area, type, sport, external_ids) "
                "VALUES (1, 'NFL', 'NFL', 'USA', 'LEAGUE', 'NFL', '{}')")
    con.execute("INSERT INTO teams (id, name, sport, external_ids) VALUES (1, 'Home', 'NFL', '{}'), "
                "(2, 'Away', 'NFL', '{}')")
    con.execute("INSERT INTO matches (id, competition_id, sport, season, utc_date, status, home_team_id, away_team_id, "
                "home_score, away_score, external_ids) "
                "VALUES (7, 1, 'NFL', '2026', '2026-10-05 18:00:00.000000', 'FINISHED', 1, 2, 21, 17, '{}')")
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


def args(p: Path, tmp_path: Path) -> list[str]:
    return ["--db", str(p), "--exports", str(tmp_path / "none"), "--until", "2026-10-12"]


def test_a_wal_copy_is_read_through_the_copy_open_and_leaves_no_sidecar(tmp_path, capsys):
    p = wal_copy(tmp_path / "copy.db")
    before = p.read_bytes()
    assert rip.main(args(p, tmp_path)) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("REPLAY INVENTORY PROBE (ARCHITECT 2026-10-15, addendum 79 item 3; #75): read-only · "
                             f"{COPY_FORM} · graded games with kickoff in [2026-09-20, 2026-10-12) UTC: 1")
    assert "NFL: graded 1" in out
    assert dc.sidecars(p) == []
    assert p.read_bytes() == before


def test_a_copy_with_a_wal_sidecar_is_refused_exit_2_nothing_opened(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + "-wal").write_bytes(b"")
    opened = []
    monkeypatch.setattr(rip, "open_read", lambda *a, **k: opened.append("live"))
    monkeypatch.setattr(rip, "open_copy", lambda *a, **k: opened.append("copy"))
    monkeypatch.setattr(rip.db_copy, "connect_copy", lambda *a, **k: opened.append("connect"))
    assert rip.main(args(p, tmp_path)) == dc.EXIT_REFUSED == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    assert cap.err.startswith("REFUSED: ") and "has a -wal sidecar (copy.db-wal)" in cap.err
    assert opened == []


def test_an_absent_db_is_refused_exit_2_and_not_created(tmp_path, capsys):
    p = tmp_path / "absent.db"
    assert rip.main(args(p, tmp_path)) == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    assert cap.err.startswith("REFUSED: ") and "no file at" in cap.err
    assert not p.exists()
    assert sorted(x.name for x in tmp_path.iterdir()) == []


def test_the_apps_configured_database_takes_the_live_open(tmp_path, capsys, monkeypatch):
    live = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    calls, real = [], rip.open_read

    def record(p):
        calls.append(Path(p))
        return real(p)
    monkeypatch.setattr(rip, "open_read", record)
    monkeypatch.setattr(rip, "open_copy", lambda *a, **k: (_ for _ in ()).throw(AssertionError("copy open taken")))
    assert rip.main(args(live, tmp_path)) == 0
    assert calls == [live]
    assert " · mode=ro URI · graded games" in capsys.readouterr().out.splitlines()[0]
