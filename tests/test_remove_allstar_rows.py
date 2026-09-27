"""Host-only Pro Bowl cleanup (architect ruling 2026-09-27: targeted delete on
the REHEARSAL DB authorized). Real schema, seeded AFC/NFC rows with dependent
prediction -> outcome and odds rows: dry-run changes nothing; --apply backs up,
cascades children-first through the declared FKs, and leaves competitive rows
intact; the laptop (no host marker) is refused."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

HOSTING = Path(__file__).resolve().parent.parent / "deploy" / "hosting"
sys.path.insert(0, str(HOSTING))
import remove_allstar_rows as rar  # noqa: E402
import sp_common as c  # noqa: E402


def put(con, table, **given):
    """Insert a row supplying every NOT NULL column without a default, with a
    type-appropriate filler: columns come from PRAGMA table_info, never guessed."""
    row = dict(given)
    for _, name, typ, notnull, default, pk in con.execute(f"PRAGMA table_info({table})"):
        if name in row or not notnull or default is not None or pk:
            continue
        t = (typ or "").upper()
        row[name] = 0 if ("INT" in t or "FLOAT" in t or "REAL" in t or "NUM" in t
                          or "BOOL" in t) else ("{}" if "JSON" in t else "x")
    con.execute(f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                list(row.values()))


@pytest.fixture
def host(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from src.db.schema import Base
    db = tmp_path / "host.db"
    eng = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    eng.dispose()
    con = sqlite3.connect(db)
    put(con, "competitions", id=1, sport="NFL", code="NFL", name="NFL")
    names = [f"Club {i}" for i in range(32)] + ["AFC", "NFC"]
    for i, n in enumerate(names, 1):
        put(con, "teams", id=i, sport="NFL", name=n)
        put(con, "competition_teams", competition_id=1, team_id=i, season="2025")
    for gid, h, a in [(1, 1, 2), (2, 3, 4), (3, 33, 34)]:  # game 3 = Pro Bowl (AFC v NFC)
        put(con, "matches", id=gid, sport="NFL", competition_id=1, season="2025",
            utc_date="2026-02-01 20:00:00", status="FINISHED", home_team_id=h, away_team_id=a)
    put(con, "predictions", id=7, match_id=3)
    put(con, "predictions", id=8, match_id=1)
    put(con, "prediction_outcomes", prediction_id=7)
    put(con, "prediction_outcomes", prediction_id=8)
    put(con, "odds_snapshots", match_id=3)
    con.commit()
    con.close()
    marker = tmp_path / "host.env"
    marker.write_text("SP_HOST_NAME=test-host\n")
    monkeypatch.setattr(c, "HOST_ENV", marker)
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "r.jsonl"))
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    monkeypatch.setenv("SP_BACKUP_DIR", str(tmp_path / "bk"))
    return tmp_path, db


def counts(db):
    con = sqlite3.connect(db)
    out = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
           for t in ("teams", "matches", "competition_teams", "predictions",
                     "prediction_outcomes", "odds_snapshots")}
    con.close()
    return out


def test_laptop_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "absent.env")
    assert rar.main([]) == 2


def test_dry_run_changes_nothing_and_lists_rows(host, capsys):
    tmp, db = host
    before = counts(db)
    assert rar.main([]) == 0
    out = capsys.readouterr().out
    assert "'AFC'" in out and "'NFC'" in out and "dry-run: nothing deleted" in out
    assert "prediction_outcomes: 1 row(s)" in out and "matches: 1 row(s)" in out
    assert counts(db) == before and not (tmp / "bk").exists()


def test_apply_backs_up_cascades_and_keeps_competitive_rows(host, capsys):
    tmp, db = host
    assert rar.main(["--apply"]) == 0
    out = capsys.readouterr().out
    assert counts(db) == {"teams": 32, "matches": 2, "competition_teams": 32,
                          "predictions": 1, "prediction_outcomes": 1, "odds_snapshots": 0}
    assert "pre-counts:  games {'NFL 2025': 3}  teams {'NFL': 34}" in out
    assert "post-counts: games {'NFL 2025': 2}  teams {'NFL': 32}" in out
    bk = list((tmp / "bk").glob("sports_*_precleanup_*.db"))
    assert len(bk) == 1 and (tmp / "bk" / (bk[0].name + ".sha256")).exists()
    rec = [json.loads(x) for x in (tmp / "r.jsonl").read_text().splitlines()][-1]
    assert rec["kind"] == "cleanup" and rec["applied"] and rec["deleted"]["matches"] == 1
    # idempotent: a second run finds nothing, takes no backup
    assert rar.main(["--apply"]) == 0 and "nothing to remove" in capsys.readouterr().out
    assert len(list((tmp / "bk").glob("*.db"))) == 1


def test_precleanup_backup_is_not_a_daily(host):
    import sp_backup
    tmp, _ = host
    assert sp_backup.run_backup("precleanup")["exit"] == 0
    assert sp_backup.todays_daily() is None
