"""K0 probe runs read-only against a throwaway SQLite copy of the schema."""
import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text

spec = importlib.util.spec_from_file_location(
    "k0", Path(__file__).resolve().parent.parent / "scripts" / "k0_kalshi_storage_probe.py")
k0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k0)


def test_probe_prints_schema_row_and_verdict(tmp_path, monkeypatch, capsys):
    db = tmp_path / "k0.db"
    eng = create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE competitions (id INTEGER PRIMARY KEY, code VARCHAR)"))
        c.execute(text("CREATE TABLE matches (id INTEGER PRIMARY KEY, competition_id INTEGER)"))
        c.execute(text("CREATE TABLE odds_snapshots (id INTEGER PRIMARY KEY, match_id INTEGER, "
                       "market VARCHAR(32), selection VARCHAR(32), devig_prob FLOAT, line FLOAT, "
                       "n_books INTEGER, captured_at DATETIME, source VARCHAR(32))"))
        c.execute(text("INSERT INTO competitions VALUES (1,'NFL')"))
        c.execute(text("INSERT INTO matches VALUES (7,1)"))
        c.execute(text("INSERT INTO odds_snapshots VALUES (1,7,'ML','HOME',0.535,NULL,1,"
                       "'2026-09-27 12:00:00','kalshi')"))
    before = db.read_bytes()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    assert k0.main() == 0
    out = capsys.readouterr().out
    assert "bid/ask/price columns present: NONE" in out
    assert "market=ML" in out and "devig_prob=0.535" in out and "competition='NFL'" in out
    assert "bid/ask do NOT survive" in out
    assert db.read_bytes() == before                       # read-only
