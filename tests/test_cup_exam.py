"""
Cup acceptance exam: the report-only pricing mode never writes, the default
path still does, and the frozen verdict logic scores as specified.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.db.database import get_engine, init_db, session_scope
from src.db.schema import (Base, Competition, Match, MatchStatus, ModelVersion,
                           Prediction, Sport, Team)
from src.walters import cup_exam
from src.walters.training import _generate_predictions_soccer

SEASON = "2026/27"


@pytest.fixture(scope="module")
def cup_db():
    """Tiny EFL-cup world in the throwaway test DB: 4 clubs across two
    leagues, 6 finished fixtures (one already carrying a Prediction row),
    1 scheduled, and a production soccer model."""
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code="EFL", name="EFL Cup",
                           area="England", type="CUP")
        s.add(comp)
        teams = [Team(sport=Sport.SOCCER, name=n) for n in ("Arsenal", "Chelsea", "Wrexham", "Barnet")]
        s.add_all(teams)
        s.flush()
        a, c, w, b = (t.id for t in teams)
        t0 = datetime(2026, 8, 12, 19, 0)
        results = [(a, w, 3, 0), (c, b, 2, 1), (w, c, 1, 1), (b, a, 0, 2), (a, c, 1, 2), (w, b, 2, 0)]
        finished = []
        for i, (h, aw, hs, as_) in enumerate(results):
            m = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON,
                      stage="2nd Round", utc_date=t0 + timedelta(days=7 * i),
                      status=MatchStatus.FINISHED, home_team_id=h, away_team_id=aw,
                      home_score=hs, away_score=as_)
            s.add(m)
            finished.append(m)
        sched = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON,
                      stage="3rd Round", utc_date=datetime(2026, 10, 28, 19, 45),
                      status=MatchStatus.SCHEDULED, home_team_id=c, away_team_id=w)
        s.add(sched)
        s.flush()
        s.add(Prediction(match_id=finished[0].id, model_version="v-test",
                         home_win_prob=0.6, draw_prob=0.25, away_win_prob=0.15))
        s.add(ModelVersion(
            sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v-test",
            status="production",
            parameters={
                "elo": {"league": {"ratings": {a: 1650, c: 1620, w: 1450, b: 1420}},
                        "cup": {"ratings": {a: 1600, c: 1600, w: 1500, b: 1480}}},
                "team_to_league": {a: "PL", c: "PL", w: "ELC", b: "L2"},
                "contexts": {}, "poisson": {},
            },
        ))
        ids = {"finished": [m.id for m in finished], "scheduled": sched.id}
    yield ids
    Base.metadata.drop_all(get_engine())


def _row_counts():
    with session_scope() as s:
        return {t.name: s.execute(select(func.count()).select_from(t)).scalar_one()
                for t in Base.metadata.sorted_tables}


def test_report_only_mode_writes_nothing(cup_db):
    before = _row_counts()
    rows = _generate_predictions_soccer("EFL", SEASON, include_finished=True)
    after = _row_counts()
    assert after == before  # every table, Prediction included
    priced = {r["match_id"] for r in rows}
    assert set(cup_db["finished"]) <= priced  # FINISHED fixtures are priced
    # the pre-existing Prediction on a played game survives untouched
    with session_scope() as s:
        p = s.execute(select(Prediction).where(
            Prediction.match_id == cup_db["finished"][0])).scalar_one()
        assert (p.model_version, p.home_win_prob) == ("v-test", 0.6)


def test_default_path_still_writes(cup_db):
    """Regression twin: the production path is untouched and persists."""
    n = _generate_predictions_soccer("EFL", SEASON)
    assert n == 1  # SCHEDULED only
    with session_scope() as s:
        written = s.execute(select(Prediction).where(
            Prediction.match_id == cup_db["scheduled"])).scalars().all()
        assert len(written) == 1
        finished_preds = s.execute(select(func.count()).select_from(Prediction).where(
            Prediction.match_id.in_(cup_db["finished"]))).scalar_one()
        assert finished_preds == 1  # still only the seeded row


def test_report_mode_prices_identically_to_production(cup_db):
    """The exam must test what we ship: same numbers as the persisted path."""
    rows = {r["match_id"]: r for r in
            _generate_predictions_soccer("EFL", SEASON, include_finished=True)}
    with session_scope() as s:
        p = s.execute(select(Prediction).where(
            Prediction.match_id == cup_db["scheduled"])).scalar_one()
        r = rows[cup_db["scheduled"]]
        assert (r["p_home"], r["p_draw"], r["p_away"]) == \
            (p.home_win_prob, p.draw_prob, p.away_win_prob)


# --- frozen verdict logic (pure) ----------------------------------------------

def _key(mid, comp="EFL", stage="2nd Round", date="2026-09-16", fh=0.5, fd=0.25, fa=0.25):
    return {"match_id": mid, "comp": comp, "stage": stage, "date": date,
            "home": f"H{mid}", "away": f"A{mid}", "fair_home": fh, "fair_draw": fd, "fair_away": fa}


def _priced(ph, pd=0.25, pa=None):
    return {"p_home": ph, "p_draw": pd, "p_away": 1 - ph - pd if pa is None else pa}


def _world(n=10, delta=0.0, stages=("1st Round", "2nd Round")):
    key = [_key(i, stage=stages[i % len(stages)]) for i in range(n)]
    priced = {i: _priced(0.5 + delta) for i in range(n)}
    return key, priced, set(range(n))


def test_pass_when_close_to_market():
    r = cup_exam.score_exam(*_world(delta=0.02))
    assert r.verdict == "PASS" and r.mae_home_pp == pytest.approx(2.0)
    assert r.sign_selector == "stage" and r.sign_share == 1.0


def test_mae_bar_is_inclusive_at_8pp():
    assert cup_exam.score_exam(*_world(delta=0.08)).mae_pass
    assert not cup_exam.score_exam(*_world(delta=0.081)).mae_pass


def test_over_count_bar_13():
    key = [_key(i) for i in range(55)]
    ok = {i: _priced(0.5 + (0.09 if i < 13 else 0.0)) for i in range(55)}
    bad = {i: _priced(0.5 + (0.09 if i < 14 else 0.0)) for i in range(55)}
    assert cup_exam.score_exam(key, ok, set(range(55))).n_over == 13
    assert cup_exam.score_exam(key, ok, set(range(55))).over_pass
    assert not cup_exam.score_exam(key, bad, set(range(55))).over_pass


def test_systematic_inversion_fails_regardless_of_mae():
    # market favors home slightly; model favors away slightly: small MAE, flipped sign
    key = [_key(i, fh=0.40, fd=0.25, fa=0.35) for i in range(10)]
    priced = {i: _priced(0.36, 0.25, 0.39) for i in range(10)}
    r = cup_exam.score_exam(key, priced, set(range(10)))
    assert r.mae_pass and r.inversion
    assert r.verdict.startswith("FAIL — systematic sign inversion")
    assert all("SIGN" in row["flag"] for row in r.rows)


def test_sign_check_between_50_and_80_fails():
    key = [_key(i, fh=0.40, fd=0.25, fa=0.35) for i in range(10)]
    priced = {i: (_priced(0.42, 0.25, 0.33) if i < 7 else _priced(0.36, 0.25, 0.39)) for i in range(10)}
    r = cup_exam.score_exam(key, priced, set(range(10)))
    assert r.sign_share == pytest.approx(0.7) and not r.inversion and not r.sign_pass
    assert r.verdict == "FAIL — sign check"


def test_date_fallback_when_stages_do_not_distinguish():
    key = [_key(0, stage="", date="2026-09-16"), _key(1, stage="", date="2026-08-12")]
    r = cup_exam.score_exam(key, {0: _priced(0.5), 1: _priced(0.5)}, {0, 1})
    assert r.sign_selector.startswith("date-fallback") and r.sign_n == 1


def test_unmatched_excluded_and_more_than_two_invalidates():
    key, priced, known = _world(n=10)
    two_gone = known - {0, 1}
    r = cup_exam.score_exam(key, priced, two_gone)
    assert r.n_scored == 8 and not r.invalid
    assert {m["why"] for m in r.missing} == {"UNMATCHED"}
    r = cup_exam.score_exam(key, priced, known - {0, 1, 2})
    assert r.invalid and r.verdict.startswith("INVALID")


def test_unpriced_counts_toward_missing():
    key, priced, known = _world(n=10)
    for i in (0, 1, 2):
        priced.pop(i)
    r = cup_exam.score_exam(key, priced, known)
    assert r.invalid and {m["why"] for m in r.missing} == {"UNPRICED"}


def test_non_efl_rows_do_not_enter_sign_check():
    key = [_key(0, comp="CL", stage="League Stage - 1"), _key(1)]
    r = cup_exam.score_exam(key, {0: _priced(0.5), 1: _priced(0.5)}, {0, 1})
    assert r.sign_n == 1
