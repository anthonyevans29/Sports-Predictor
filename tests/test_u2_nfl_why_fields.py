"""U2 (2026-09-27): NFL predictions export carries the model's "why" fields."""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team


@pytest.fixture(scope="module")
def game():
    init_db()
    now = datetime.utcnow()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.sport == Sport.NFL,
                                                   Competition.code == "NFL")).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="USA", type="LEAGUE")
            s.add(comp)
        t = [Team(sport=Sport.NFL, name=f"U2-{i}", external_ids={"u2": str(i)}) for i in range(3)]
        s.add_all(t)
        s.flush()

        def mk(h, a, when, status=MatchStatus.FINISHED, hs=None, as_=None):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season="2026", utc_date=when,
                      status=status, home_team_id=t[h].id, away_team_id=t[a].id,
                      home_score=hs, away_score=as_)
            s.add(m)
            return m

        kick = now + timedelta(days=2)
        mk(0, 2, kick - timedelta(days=7), hs=31, as_=10)     # U2-0 home win, 7 days before
        mk(2, 1, kick - timedelta(days=4), hs=13, as_=20)     # U2-1 away win, 4 days before
        mk(1, 0, kick - timedelta(days=11), status=MatchStatus.CANCELLED)  # ignored for rest
        up = mk(0, 1, kick, status=MatchStatus.SCHEDULED)
        s.flush()
        ids = {"up": up.id, "home": t[0].id, "away": t[1].id}
    from src.walters.nfl_predict import predict_nfl
    predict_nfl()
    return ids


def test_export_carries_elo_rest_and_home_adv(game, tmp_path):
    from src.walters.nfl_backtest import NFLEloConfig, _expected_home
    from src.walters.nfl_predict import _current_ratings, export_nfl_predictions
    doc = json.loads(open(export_nfl_predictions(out_dir=str(tmp_path))).read())
    row = {r["match_id"]: r for r in doc["predictions"]}[game["up"]]
    st, cfg = _current_ratings(), NFLEloConfig()
    assert row["elo_home"] == round(st.ratings[game["home"]], 1)
    assert row["elo_away"] == round(st.ratings[game["away"]], 1)
    assert row["elo_gap"] == pytest.approx(row["elo_home"] - row["elo_away"], abs=0.11)
    assert row["home_adv_applied"] == cfg.home_advantage == 48.0
    assert row["elo_home"] > 1500 > row["elo_away"] - 100            # both teams won once
    # the "why" reproduces the stored prediction (same ratings + home advantage)
    p = _expected_home(cfg, st, game["home"], game["away"])
    assert row["prediction"]["home_win_prob"] == pytest.approx(round(p, 4), abs=1e-4)
    # rest from the schedule: home last played 7 days before, away 4; cancelled ignored
    assert row["rest_days_home"] == 7.0 and row["rest_days_away"] == 4.0
    # additive: existing contract fields untouched
    for k in ("market_divergence_pp", "quarantine", "kalshi_prob", "venue_flag", "prediction"):
        assert k in row


def test_drift_receipt_silent_in_normal_chain_and_warns_on_drift(game, tmp_path, monkeypatch):
    from click.testing import CliRunner

    from cli import cli
    from src.db.schema import Prediction
    from src.walters.nfl_predict import export_nfl_predictions
    rc = {}
    export_nfl_predictions(out_dir=str(tmp_path), receipts=rc)
    assert rc["elo_drift_games"] == []                         # back-to-back: silent
    monkeypatch.chdir(tmp_path)
    assert "ELO DRIFT" not in CliRunner().invoke(cli, ["export-nfl-predictions"]).output
    # predictions written 3 days ago -> the game finished 2 days ago post-dates them
    with session_scope() as s:
        p = s.execute(select(Prediction).where(Prediction.match_id == game["up"])).scalar_one()
        p.computed_at = datetime.utcnow() - timedelta(days=3)
    rc = {}
    export_nfl_predictions(out_dir=str(tmp_path), receipts=rc)
    assert rc["elo_drift_games"] == ["U2-1 @ U2-2"]
    out = CliRunner().invoke(cli, ["export-nfl-predictions"]).output
    assert "⚠ ELO DRIFT: 1 NFL game(s) finished after the predictions were written" in out
    doc = json.loads(open(export_nfl_predictions(out_dir=str(tmp_path))).read())
    assert all("_computed_at" not in r for r in doc["predictions"])   # internal key never ships
