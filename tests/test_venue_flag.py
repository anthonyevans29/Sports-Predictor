"""NFL export venue lie detector (2026-09-26): book fair vs Kalshi, WARNING ONLY."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import (Competition, Match, MatchStatus, Odds, OddsSnapshot, Prediction,
                           Sport, Team)
from src.walters import venue


def test_kalshi_home_prob_rules():
    k = datetime(2026, 9, 27, 17)
    snaps = [NS(source="kalshi", selection="HOME", devig_prob=0.30, captured_at=k - timedelta(hours=5)),
             NS(source="kalshi", selection="HOME", devig_prob=0.52, captured_at=k - timedelta(hours=1)),
             NS(source="kalshi", selection="AWAY", devig_prob=0.50, captured_at=k - timedelta(hours=1)),
             NS(source="kalshi", selection="HOME", devig_prob=0.99, captured_at=k + timedelta(minutes=5))]
    r = venue.kalshi_home_prob(snaps, k)                       # latest pre-kickoff; in-play ignored
    assert r["home"] == pytest.approx(0.52 / 1.02)
    assert venue.kalshi_home_prob(snaps[:2], k) is None        # one-sided -> None
    assert venue.venue_gap(0.60, 0.51) == (9.0, "STALE-BOOK?")
    assert venue.venue_gap(0.60, 0.53) == (7.0, None)          # below 8pp: silent
    assert venue.venue_gap(None, 0.5) == (None, None)


@pytest.fixture(scope="module")
def slate():
    init_db()
    now = datetime.utcnow()
    kick = now + timedelta(days=2)
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.sport == Sport.NFL,
                                                   Competition.code == "NFL")).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="USA", type="LEAGUE")
            s.add(comp)
        t = [Team(sport=Sport.NFL, name=n, external_ids={"venue_test": n})
             for n in ("VF Browns", "VF Panthers", "VF Bears", "VF Eagles")]
        s.add_all(t)
        s.flush()

        def game(h, a, model_home, book_home, kal_home):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season="2026", utc_date=kick,
                      status=MatchStatus.SCHEDULED, home_team_id=t[h].id, away_team_id=t[a].id)
            s.add(m)
            s.flush()
            s.add(Prediction(match_id=m.id, model_version="nfl_elo_v1", home_win_prob=model_home,
                             away_win_prob=1 - model_home, draw_prob=None))
            for bk in ("b1", "b2", "b3", "b4"):   # fair = book_home exactly (symmetric vig-free)
                s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection="HOME",
                           price_decimal=1 / book_home, captured_at=now))
                s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection="AWAY",
                           price_decimal=1 / (1 - book_home), captured_at=now))
            for sel, p in (("HOME", kal_home), ("AWAY", 1 - kal_home)):
                s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=p,
                                   n_books=1, captured_at=now, source="kalshi"))
            return m.id

        # stale book: books say home 0.25, Kalshi says 0.52 -> 27pp gap; model 0.55
        stale = game(0, 1, 0.55, 0.25, 0.52)
        # venues agree: book 0.60, kalshi 0.62 -> silent
        agree = game(2, 3, 0.64, 0.60, 0.62)
        return {"stale": stale, "agree": agree}


def _odds_kwargs_ok():
    cols = {c.name for c in Odds.__table__.columns}
    return {"bookmaker", "market", "selection", "price_decimal", "captured_at"} <= cols


def test_flag_fires_on_stale_book_and_quarantine_is_untouched(slate, tmp_path):
    assert _odds_kwargs_ok()
    from src.walters.nfl_predict import export_nfl_predictions
    doc = json.loads(open(export_nfl_predictions(out_dir=str(tmp_path))).read())
    rows = {r["match_id"]: r for r in doc["predictions"]}
    st = rows[slate["stale"]]
    assert st["market"]["fair_prob"]["HOME"] == pytest.approx(0.25, abs=1e-4)
    assert st["kalshi_prob"] == pytest.approx(0.52, abs=1e-4)
    assert st["venue_gap_pp"] == 27.0 and st["venue_flag"] == "STALE-BOOK?"
    # quarantine keys on the BOOK divergence exactly as ratified: 55 - 25 = 30pp -> true
    assert st["market_divergence_pp"] == 30.0 and st["quarantine"] is True
    ag = rows[slate["agree"]]
    assert ag["venue_gap_pp"] == 2.0 and ag["venue_flag"] is None
    assert ag["market_divergence_pp"] == 4.0 and ag["quarantine"] is False
    assert "WARNING ONLY" in doc["note"]


def test_cli_prints_the_venue_check(slate, tmp_path, monkeypatch):
    from cli import cli
    monkeypatch.chdir(tmp_path)          # the CLI writes exports/ relative to cwd
    out = CliRunner().invoke(cli, ["export-nfl-predictions"]).output
    assert "STALE-BOOK? flagged: 1" in out
    assert "VF Panthers @ VF Browns" in out and "gap=27.0pp" in out and "quarantine=True" in out
