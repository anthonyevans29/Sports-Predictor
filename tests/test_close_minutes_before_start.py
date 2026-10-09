"""ARCHITECT addendum 31 item 3 (#382, first half), an additive export-contract change:
"Every results row that carries close_at also carries close_minutes_before_start: whole minutes, rounded down,
from the close's capture to the stored start, and null where there is no close. It is the age of our capture, not
of the quote (#348), and the field's doc line says so. results-tally prints, for each sport that reports a close,
the median and the largest over its window, with n. Nothing is renamed and nothing is removed."

The export/tally tests run on their OWN throwaway SQLite file (SessionLocal rebound under tmp_path), so the
median / largest / n are exact and no other test's rows leak in."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as O

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.schema import Sport
from src.walters import close as C
from src.walters.close import close_block, grading_close_block

KO = datetime(2026, 10, 4, 17, 0)


def odd(bk, sel, px, at):
    return O(market="1X2", bookmaker=bk, selection=sel, price_decimal=px, captured_at=at)


def two_books(at):
    return [odd("a", "HOME", 1.8, at), odd("a", "AWAY", 2.1, at), odd("b", "HOME", 1.85, at), odd("b", "AWAY", 2.05, at)]


def test_whole_minutes_rounded_down_and_null_without_a_time():
    assert C.minutes_before_start(KO - timedelta(minutes=111, seconds=59), KO) == 111       # rounded DOWN
    assert C.minutes_before_start(KO - timedelta(seconds=59), KO) == 0
    assert C.minutes_before_start(KO - timedelta(minutes=623), KO) == 623
    assert C.minutes_before_start(None, KO) is None and C.minutes_before_start(KO, None) is None
    aware = (KO - timedelta(minutes=30, seconds=1)).replace(tzinfo=timezone.utc)
    assert C.minutes_before_start(aware, KO) == 30                                          # naive UTC vs aware UTC


def test_close_block_carries_the_field_beside_close_at():
    at = KO - timedelta(minutes=35, seconds=40)
    b = close_block(two_books(at), KO, Sport.NFL)
    assert b["close_at"] == at.isoformat() and b["close_minutes_before_start"] == 35
    for empty in (close_block([odd("a", "HOME", 1.8, at)], KO, Sport.NFL), close_block([], KO, Sport.NFL)):
        assert empty["close_at"] is None and "close_minutes_before_start" in empty
        assert empty["close_minutes_before_start"] is None                                 # no close: null


# ------------------------------------------------------------------ an isolated DB for the exports + the tally

@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    from src.db import database
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{tmp_path / 'iso.db'}", future=True)
    Base.metadata.create_all(eng)
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True,
                                     expire_on_commit=False))
    monkeypatch.chdir(tmp_path)                                    # results-tally's shadow sections read exports/
    yield
    eng.dispose()


def _world(now):
    """MLB: three priced games (ages 111, 60, 5) + one with no close; soccer: one (623); NFL: one (30)."""
    from src.db.database import session_scope
    from src.db.schema import (Competition, Match, MatchStatus, Odds, Prediction, PredictionOutcome, Result,
                               Team)
    ids = {}
    with session_scope() as s:
        comps = {}
        for sport, code in ((Sport.MLB, "MLB"), (Sport.SOCCER, "PL"), (Sport.NFL, "NFL")):
            comps[sport] = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
            s.add(comps[sport])
        s.flush()

        def game(sport, key, ko, ages, three_way=False, season="2026"):
            h, a = Team(sport=sport, name=f"Age {key} H"), Team(sport=sport, name=f"Age {key} A")
            s.add_all([h, a])
            s.flush()
            m = Match(sport=sport, competition_id=comps[sport].id, season=season, matchday=5, utc_date=ko,
                      status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id,
                      home_score=3, away_score=1)
            s.add(m)
            s.flush()
            sels = ("HOME", "DRAW", "AWAY") if three_way else ("HOME", "AWAY")
            for age in ages:
                for bk in ("bk1", "bk2"):
                    for sel, px in zip(sels, (2.0, 3.4, 3.8) if three_way else (1.8, 2.1)):
                        s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                                   captured_at=ko - age))
            p = Prediction(match_id=m.id, model_version="age-probe", home_win_prob=0.6, away_win_prob=0.4,
                           draw_prob=0.0 if three_way else None)
            s.add(p)
            s.flush()
            if sport != Sport.NFL:
                s.add(PredictionOutcome(prediction_id=p.id, actual_result=Result.HOME, actual_home_score=3,
                                        actual_away_score=1, top_pick_hit=True, log_loss=0.51))
            ids[key] = m.id

        d = now - timedelta(days=2)
        game(Sport.MLB, "m111", d, [timedelta(hours=5), timedelta(minutes=111, seconds=30)])   # the LAST capture
        game(Sport.MLB, "m60", d + timedelta(hours=1), [timedelta(minutes=60)])
        game(Sport.MLB, "m5", d + timedelta(hours=2), [timedelta(minutes=5, seconds=59)])
        game(Sport.MLB, "mnone", d + timedelta(hours=3), [])                                    # no close: null
        game(Sport.SOCCER, "s623", d, [timedelta(minutes=623, seconds=10)], three_way=True, season="2026/27")
        game(Sport.NFL, "n30", d, [timedelta(minutes=30)])
    return ids


def test_every_results_row_with_close_at_carries_the_field(iso_db, tmp_path):
    from src.timeutil import utc_now_naive
    from src.walters.export import export_results
    from src.walters.nfl_predict import export_nfl_results
    now = utc_now_naive()
    ids = _world(now)
    want = {ids["m111"]: 111, ids["m60"]: 60, ids["m5"]: 5, ids["mnone"]: None, ids["s623"]: 623, ids["n30"]: 30}
    got = {}
    for sport in (Sport.MLB, Sport.SOCCER):
        doc = json.loads(export_results(sport=sport, start_date=now - timedelta(days=5), end_date=now))
        for r in doc["results"]:
            got[r["match_id"]] = r["graded"]
    nfl = json.load(open(export_nfl_results(out_dir=str(tmp_path / "nfl"))))
    for r in nfl["results"]:
        got[r["match_id"]] = r["graded"]
    assert set(got) == set(want)
    for mid, g in got.items():
        assert "close_at" in g and "close_minutes_before_start" in g                 # present wherever close_at is
        assert g["close_minutes_before_start"] == want[mid]
        assert (g["close_at"] is None) == (want[mid] is None)
        for kept in ("close_fair", "close_books", "close_source", "clv"):             # nothing renamed or removed
            assert kept in g


def test_intl_results_rows_carry_the_field(iso_db):
    from src.db.database import append_prediction_history, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Odds, Team
    from src.walters import intl_production as ip
    ko = datetime(2098, 5, 1, 19)
    with session_scope() as s:
        c = Competition(sport=Sport.SOCCER, code="UNL", name="UNL", area="I", type="INTL")
        t = [Team(sport=Sport.SOCCER, name=f"Age Intl {i}") for i in range(4)]
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
                       captured_at=ko - timedelta(minutes=47, seconds=5)))
        rows = [{"match_id": m.id, "model_version": ip.MODEL_VERSION, "computed_at": m.utc_date - timedelta(hours=9),
                 "home_win_prob": .5, "draw_prob": .3, "away_win_prob": .2} for m in (priced, bare)]
        append_prediction_history(s.connection(), rows)
        pid, bid = priced.id, bare.id
    r = ip.results(now=datetime(2098, 6, 1))
    by = {x["match_id"]: x["graded"] for x in r["rows"]}
    assert by[pid]["close_at"] is not None and by[pid]["close_minutes_before_start"] == 47
    assert by[bid]["close_at"] is None and by[bid]["close_minutes_before_start"] is None


def test_grading_close_block_kalshi_only_carries_the_field(iso_db):
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Team
    ko = datetime(2026, 10, 4, 23, 0)
    with session_scope() as s:
        c = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="US", type="LEAGUE")
        t = [Team(sport=Sport.MLB, name=f"Age K {i}") for i in range(2)]
        s.add_all([c, *t])
        s.flush()
        m = Match(sport=Sport.MLB, competition_id=c.id, season="2026", utc_date=ko, status=MatchStatus.FINISHED,
                  home_team_id=t[0].id, away_team_id=t[1].id, home_score=1, away_score=0)
        s.add(m)
        s.flush()
        s.add(OddsSnapshot(match_id=m.id, market="ML", selection="HOME", devig_prob=0.46, n_books=1,
                           captured_at=ko - timedelta(minutes=12, seconds=30), source="kalshi",
                           yes_bid=0.45, yes_ask=0.47))
        s.flush()
        blk = grading_close_block(s, m)
    assert blk["close_reference"] == "kalshi_only" and blk["close_minutes_before_start"] == 12


def test_results_tally_prints_median_largest_and_n_per_sport(iso_db, tmp_path):
    from src.timeutil import utc_now_naive
    from src.walters.export import results_tally
    _world(utc_now_naive())
    said = []
    txt = open(results_tally(days=30, out_path=str(tmp_path / "R.md"), report=said.append)).read()
    out = "\n".join(said)
    assert "MLB: median 60 min · largest 111 min · n=3" in out                      # the null row is not counted
    assert "Soccer (PL): median 623 min · largest 623 min · n=1" in out
    assert "NFL (season to date, live rows): median 30 min · largest 30 min · n=1" in out
    assert "our capture, not the quote, #348" in out
    sections = txt.split("\n## ")
    mlb = next(x for x in sections if x.startswith("MLB"))
    assert "median 60 min, largest 111 min before start (n=3)" in mlb
    assert "median 623 min, largest 623 min before start (n=1)" in next(x for x in sections if x.startswith("Soccer"))
    assert "median 30 min, largest 30 min before start (n=1)" in next(x for x in sections if x.startswith("NFL"))
