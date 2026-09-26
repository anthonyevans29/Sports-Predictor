"""matches.status_raw (2026-09-26): the provider's status code survives ingestion."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine, select, text

from src.adapters.api_hockey import APIHockeyAdapter
from src.adapters.normalized import NormalizedMatch
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team
from src.ingestion.service import IngestionService, SyncResult


def _game(gid, short, hs=3, as_=2):
    g = {"game": {"id": gid, "date": {"timestamp": 1760000000 + gid}, "stage": None, "week": None},
         "teams": {"home": {"id": 1}, "away": {"id": 2}},
         "scores": {"home": hs, "away": as_}}
    if short is not None:
        g["game"]["status"] = {"short": short}
    return g


def test_hockey_adapter_keeps_raw_code(monkeypatch):
    a = APIHockeyAdapter()
    payload = {"response": [_game(1, "FT"), _game(2, "AOT"), _game(3, "AP"),
                            _game(4, None), _game(5, "NS", None, None)]}
    monkeypatch.setattr(a, "_get", lambda *args, **kw: payload)
    got = {int(m.source_id): m for m in a.list_matches("NHL", season="2025")}
    assert {k: m.status_raw for k, m in got.items()} == {1: "FT", 2: "AOT", 3: "AP", 4: None, 5: "NS"}
    # the mapped vocabulary is unchanged: FT/AOT/AP all FINISHED
    assert all(got[k].status == MatchStatus.FINISHED for k in (1, 2, 3))
    assert got[5].status == MatchStatus.SCHEDULED


def test_ingestion_persists_and_never_blanks_status_raw():
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.NHL, code="NHLRAW", name="x", area="x", type="LEAGUE")
        h = Team(sport=Sport.NHL, name="H", external_ids={"api-hockey": "h1"})
        a = Team(sport=Sport.NHL, name="A", external_ids={"api-hockey": "a1"})
        s.add_all([comp, h, a])
        s.flush()
        svc = IngestionService.__new__(IngestionService)
        nm = NormalizedMatch(sport=Sport.NHL, competition_code="NHLRAW", season="2025",
                             utc_date=datetime(2025, 11, 1), status=MatchStatus.FINISHED,
                             home_team_source_id="h1", away_team_source_id="a1",
                             source="api-hockey", source_id="g1", home_score=3, away_score=2,
                             status_raw="AOT")
        cache: dict = {}
        m = svc._upsert_match(s, nm, comp, SyncResult(), cache)
        assert m.status_raw == "AOT"
        nm.status_raw = None                        # a later sync without the code
        svc._upsert_match(s, nm, comp, SyncResult(), cache)
        assert m.status_raw == "AOT"
        nm.status_raw = "AP"                        # a corrected code overwrites
        svc._upsert_match(s, nm, comp, SyncResult(), cache)
        assert m.status_raw == "AP"


def test_migration_adds_column_idempotently_and_prints_receipt(tmp_path, monkeypatch, capsys):
    import migrate_status_raw as mig

    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:                          # a pre-migration schema, no status_raw
        c.execute(text("CREATE TABLE competitions (id INTEGER PRIMARY KEY, code VARCHAR)"))
        c.execute(text("CREATE TABLE matches (id INTEGER PRIMARY KEY, competition_id INTEGER, "
                       "season VARCHAR, status VARCHAR)"))
        c.execute(text("INSERT INTO competitions VALUES (1, 'NHL')"))
        c.execute(text("INSERT INTO matches VALUES (1, 1, '2025', 'FINISHED')"))
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    assert mig.main() == 0
    out = capsys.readouterr().out
    assert "+ Adding matches.status_raw" in out and "2025  (null)" in out
    with eng.connect() as c:
        assert c.execute(text("SELECT id, season FROM matches")).all() == [(1, "2025")]  # data kept
        c.execute(text("SELECT status_raw FROM matches")).all()
    assert mig.main() == 0                          # second run: no-op
    assert "already exists" in capsys.readouterr().out


def test_orm_enum_stores_names_so_the_receipt_filter_matches():
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.NHL, code="NHLENUM", name="x", area="x", type="LEAGUE")
        t = Team(sport=Sport.NHL, name="T")
        s.add_all([comp, t])
        s.flush()
        s.add(Match(sport=Sport.NHL, competition_id=comp.id, season="2025",
                    utc_date=datetime(2025, 11, 1), status=MatchStatus.FINISHED,
                    home_team_id=t.id, away_team_id=t.id, status_raw="FT"))
    with session_scope() as s:
        raw = s.execute(text("SELECT status FROM matches WHERE status_raw = 'FT'")).scalar()
    assert raw == "FINISHED"
