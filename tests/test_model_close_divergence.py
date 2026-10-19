"""ARCHITECT 2026-10-19 (addendum 137 item 3, #612), an export-contract change, verbatim: "#612 (the `clv` field) —
RULED as declared: `graded.model_close_divergence` written beside `graded.clv` in the three results exports with the
same value and the one-sentence comment at each writer; `clv` stays as an alias through v1.5.0 and is removed in the
release after (the removal is its own line in that release's changelog); the tests pin the new key and the alias; the
external morning-run consumer is the alias's reason."

The three writers: export-results (the stored value, `prediction_outcomes.clv`), export-nfl-results (computed at
write on the book close) and export-intl-results (computed at write, argmax pick). Each test runs on its OWN
throwaway SQLite file (SessionLocal rebound under tmp_path)."""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.schema import Sport


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    from src.db import database
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{tmp_path / 'iso.db'}", future=True)
    Base.metadata.create_all(eng)
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True,
                                     expire_on_commit=False))
    monkeypatch.chdir(tmp_path)
    yield
    eng.dispose()


def _both(g):
    """The new key and the alias: both present, the same value."""
    assert "model_close_divergence" in g and "clv" in g, sorted(g)
    assert g["model_close_divergence"] == g["clv"]
    return g["model_close_divergence"]


def _world(now):
    """MLB: one game with a stored divergence (0.0453), one with none; NFL: one game priced by two books."""
    from src.db.database import session_scope
    from src.db.schema import (Competition, Match, MatchStatus, Odds, Prediction, PredictionOutcome, Result,
                               Team)
    ids = {}
    with session_scope() as s:
        comps = {}
        for sport, code in ((Sport.MLB, "MLB"), (Sport.NFL, "NFL")):
            comps[sport] = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
            s.add(comps[sport])
        s.flush()

        def game(sport, key, ko, priced, stored=None):
            h, a = Team(sport=sport, name=f"Div {key} H"), Team(sport=sport, name=f"Div {key} A")
            s.add_all([h, a])
            s.flush()
            m = Match(sport=sport, competition_id=comps[sport].id, season="2026", matchday=5, utc_date=ko,
                      status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=3, away_score=1)
            s.add(m)
            s.flush()
            if priced:
                for bk in ("bk1", "bk2"):
                    for sel, px in (("HOME", 1.8), ("AWAY", 2.1)):
                        s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                                   captured_at=ko - timedelta(minutes=30)))
            p = Prediction(match_id=m.id, model_version="div-probe", home_win_prob=0.6, away_win_prob=0.4)
            s.add(p)
            s.flush()
            if sport != Sport.NFL:
                s.add(PredictionOutcome(prediction_id=p.id, actual_result=Result.HOME, actual_home_score=3,
                                        actual_away_score=1, top_pick_hit=True, log_loss=0.51, clv=stored))
            ids[key] = m.id

        d = now - timedelta(days=2)
        game(Sport.MLB, "stored", d, True, stored=0.0453)
        game(Sport.MLB, "none", d + timedelta(hours=1), False)
        game(Sport.NFL, "nfl", d, True)
    return ids


def test_export_results_writes_the_stored_divergence_under_both_keys(iso_db):
    from src.timeutil import utc_now_naive
    from src.walters.export import export_results
    now = utc_now_naive()
    ids = _world(now)
    doc = json.loads(export_results(sport=Sport.MLB, start_date=now - timedelta(days=5), end_date=now))
    by = {r["match_id"]: r["graded"] for r in doc["results"]}
    assert set(by) == {ids["stored"], ids["none"]}
    assert _both(by[ids["stored"]]) == 0.0453                   # the STORED value, as written, under both keys
    assert _both(by[ids["none"]]) is None


def test_export_nfl_results_writes_the_pick_divergence_under_both_keys(iso_db, tmp_path):
    from src.timeutil import utc_now_naive
    from src.walters.nfl_predict import export_nfl_results
    ids = _world(utc_now_naive())
    doc = json.load(open(export_nfl_results(out_dir=str(tmp_path / "nfl"))))
    by = {r["match_id"]: r["graded"] for r in doc["results"]}
    g = by[ids["nfl"]]
    fair_h = (1 / 1.8) / (1 / 1.8 + 1 / 2.1)                      # both books 1.8 / 2.1, de-vigged
    assert _both(g) == round(0.6 - fair_h, 4)                    # p >= 0.5 picks HOME
    assert g["model_close_divergence"] == round(0.6 - g["close_home_prob"], 4)


def test_export_intl_results_writes_the_pick_divergence_under_both_keys(iso_db):
    from src.db.database import append_prediction_history, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Odds, Team
    from src.walters import intl_production as ip
    ko = datetime(2098, 5, 1, 19)
    with session_scope() as s:
        c = Competition(sport=Sport.SOCCER, code="UNL", name="UNL", area="I", type="INTL")
        t = [Team(sport=Sport.SOCCER, name=f"Div Intl {i}") for i in range(4)]
        s.add_all([c, *t])
        s.flush()
        priced = Match(sport=Sport.SOCCER, competition_id=c.id, season="2097/98", utc_date=ko,
                       status=MatchStatus.FINISHED, status_raw="FT", home_team_id=t[0].id, away_team_id=t[1].id,
                       home_score_90=2, away_score_90=0, home_score=2, away_score=0)
        bare = Match(sport=Sport.SOCCER, competition_id=c.id, season="2097/98", utc_date=ko + timedelta(days=1),
                     status=MatchStatus.FINISHED, status_raw="FT", home_team_id=t[2].id, away_team_id=t[3].id,
                     home_score_90=0, away_score_90=0, home_score=0, away_score=0)
        s.add_all([priced, bare])
        s.flush()
        for sel, px in (("HOME", 2.0), ("DRAW", 3.4), ("AWAY", 3.8)):
            s.add(Odds(match_id=priced.id, bookmaker="bk", market="1X2", selection=sel, price_decimal=px,
                       captured_at=ko - timedelta(minutes=47)))
        rows = [{"match_id": m.id, "model_version": ip.MODEL_VERSION, "computed_at": m.utc_date - timedelta(hours=9),
                 "home_win_prob": .5, "draw_prob": .3, "away_win_prob": .2} for m in (priced, bare)]
        append_prediction_history(s.connection(), rows)
        pid, bid = priced.id, bare.id
    by = {x["match_id"]: x["graded"] for x in ip.results(now=datetime(2098, 6, 1))["rows"]}
    g = by[pid]
    assert _both(g) == round(0.5 - g["close_fair"]["HOME"], 4)   # the argmax pick, HOME
    assert g["model_close_divergence"] is not None
    assert _both(by[bid]) is None                                # no close: null under both keys

