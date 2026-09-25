"""Market-only fixtures export — the NHL launch vehicle (2026-10-07)."""
import json
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import func, select

from src.db.database import get_engine, init_db, session_scope
from src.db.schema import (Base, Competition, Match, MatchStatus, Odds, OddsSnapshot, Sport,
                           Team)
from src.walters.export import export_fixtures

KICK = datetime.utcnow().replace(microsecond=0) + timedelta(days=2)


def _counts():
    with session_scope() as s:
        return {t.name: s.execute(select(func.count()).select_from(t)).scalar_one()
                for t in Base.metadata.sorted_tables}


@pytest.fixture(scope="module")
def nhl():
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.NHL, code="NHL", name="NHL", area="USA", type="LEAGUE")
        s.add(comp)
        t = [Team(sport=Sport.NHL, name=n) for n in ("Bruins", "Leafs", "Rangers", "Habs")]
        s.add_all(t)
        s.flush()
        g1 = Match(sport=Sport.NHL, competition_id=comp.id, season="2026", utc_date=KICK,
                   status=MatchStatus.SCHEDULED, home_team_id=t[0].id, away_team_id=t[1].id)
        g2 = Match(sport=Sport.NHL, competition_id=comp.id, season="2026",
                   utc_date=KICK + timedelta(hours=3), status=MatchStatus.SCHEDULED,
                   home_team_id=t[2].id, away_team_id=t[3].id)
        s.add_all([g1, g2])
        s.flush()
        early, late, ingame = KICK - timedelta(hours=20), KICK - timedelta(hours=2), KICK + timedelta(minutes=30)
        for book, h_old, h_new in (("BookA", 2.40, 1.80), ("BookB", 2.30, 1.90)):
            for cap, h in ((early, h_old), (late, h_new)):
                s.add(Odds(match_id=g1.id, source="api-hockey", bookmaker=book, market="1X2",
                           selection="HOME", price_decimal=h, captured_at=cap))
                s.add(Odds(match_id=g1.id, source="api-hockey", bookmaker=book, market="1X2",
                           selection="AWAY", price_decimal=round(1 / (1.05 - 1 / h), 3),
                           captured_at=cap))
        s.add(Odds(match_id=g1.id, source="api-hockey", bookmaker="BookA", market="1X2",
                   selection="HOME", price_decimal=9.0, captured_at=ingame))       # in-game
        s.add(Odds(match_id=g1.id, source="api-hockey", bookmaker="BookA", market="TOTALS",
                   selection="OVER", price_decimal=1.9, captured_at=late, line=5.5))
        for sel, p in (("HOME", 0.55), ("AWAY", 0.45)):
            s.add(OddsSnapshot(match_id=g1.id, market="ML", selection=sel, devig_prob=p,
                               n_books=1, captured_at=late, source="kalshi"))
        s.add(OddsSnapshot(match_id=g1.id, market="ML", selection="HOME", devig_prob=0.99,
                           n_books=1, captured_at=ingame, source="kalshi"))          # in-game
        s.add(OddsSnapshot(match_id=g2.id, market="ML", selection="HOME", devig_prob=0.6,
                           n_books=1, captured_at=late, source="kalshi"))            # one-sided
        ids = {"g1": g1.id, "g2": g2.id}
    yield ids
    Base.metadata.drop_all(get_engine())


def test_nhl_fixtures_file_shape_consensus_and_kalshi(nhl, tmp_path):
    before = _counts()
    rc = {}
    path = export_fixtures("NHL", out_dir=str(tmp_path), receipts=rc)
    assert _counts() == before                               # read-only
    doc = json.loads(open(path).read())
    assert doc["contains_predictions"] is False and "SUSPENDED" in doc["note"]
    rows = {r["match_id"]: r for r in doc["fixtures"]}
    g1, g2 = rows[nhl["g1"]], rows[nhl["g2"]]
    # consensus = LATEST pre-kickoff capture per (book, selection); in-game 9.0 ignored
    mk = g1["market"]
    assert mk["bookmaker_count"] == 2 and set(mk["fair_prob"]) == {"HOME", "AWAY"}
    ih = (1 / 1.80 + 1 / 1.90) / 2
    ia = (1.05 - 1 / 1.80 + 1.05 - 1 / 1.90) / 2
    assert mk["fair_prob"]["HOME"] == pytest.approx(ih / (ih + ia), abs=2e-4)
    # Kalshi: in-game 0.99 excluded; statuses in the predictions-export vocabulary
    assert g1["kalshi"]["status"] == "two_sided" and g1["kalshi"]["prob"]["HOME"] == 0.55
    assert g1["input_quality"] == {"book_odds": 2, "kalshi": "two_sided"}
    assert g2["market"] is None and g2["input_quality"] == {"book_odds": 0, "kalshi": "one_sided"}
    assert rc["fixtures"] == 2 and rc["with_books"] == 1
    assert (rc["kalshi_two_sided"], rc["kalshi_one_sided"], rc["kalshi_absent"]) == (1, 1, 0)
    assert rc["odds_labels"][("1X2", "HOME")] == 5 and rc["odds_labels"][("TOTALS", "OVER")] == 1


def test_cli_prints_label_receipt_and_warns_without_1x2(nhl, tmp_path, monkeypatch):
    from cli import cli
    monkeypatch.chdir(tmp_path)
    out = CliRunner().invoke(cli, ["export-fixtures", "--competition", "NHL"]).output
    assert "1X2/HOME×5" in out and "kalshi two-sided 1 / one-sided 1 / absent 0" in out
    assert "none are labelled 1X2" not in out
    with session_scope() as s:                              # relabel: the join now finds nothing
        for o in s.execute(select(Odds).where(Odds.market == "1X2")).scalars():
            o.market = "ML"
    try:
        out = CliRunner().invoke(cli, ["export-fixtures", "--competition", "NHL"]).output
        assert "none are labelled 1X2" in out and "with book consensus 0" in out
    finally:
        with session_scope() as s:
            for o in s.execute(select(Odds).where(Odds.market == "ML")).scalars():
                o.market = "1X2"
