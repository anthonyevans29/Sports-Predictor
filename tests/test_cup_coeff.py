"""Cup fix-v2: cup elo_goal_coeff tuned per context on PRIOR cups, exam excluded."""
import random
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.db.database import get_engine, init_db, session_scope
from src.db.schema import Base, Competition, Match, MatchStatus, ModelVersion, Sport, Team
from src.walters import cup_coeff as cc
from src.walters.training import _generate_predictions_soccer

PRIOR, EXAM = "2025/26", "2026/27"


def _counts():
    with session_scope() as s:
        return {t.name: s.execute(select(func.count()).select_from(t)).scalar_one()
                for t in Base.metadata.sorted_tables}


@pytest.fixture(scope="module")
def world():
    """PL clubs (Elo 1650) and ELC clubs (1450) in two seasons. Cup cross-league
    ties: PL wins ~85% (a gap 0.0008 badly under-prices); same-league ties are
    coin-flips. The EXAM season's cup results are pure noise."""
    init_db()
    rnd = random.Random(11)
    with session_scope() as s:
        comps = {c: Competition(sport=Sport.SOCCER, code=c, name=c, area="England", type=t)
                 for c, t in (("PL", "LEAGUE"), ("ELC", "LEAGUE"), ("EFL", "CUP"))}
        s.add_all(comps.values())
        pl = [Team(sport=Sport.SOCCER, name=f"PL{i}") for i in range(6)]
        elc = [Team(sport=Sport.SOCCER, name=f"ELC{i}") for i in range(6)]
        s.add_all(pl + elc)
        s.flush()
        ids = {"cup": {}}
        for season, y in ((PRIOR, 2025), (EXAM, 2026)):
            t0 = datetime(y, 8, 9, 15)
            for code, teams in (("PL", pl), ("ELC", elc)):
                for rd in range(5):
                    for i in range(0, 6, 2):
                        h, a = teams[(i + rd) % 6], teams[(i + 1 + rd) % 6]
                        s.add(Match(sport=Sport.SOCCER, competition_id=comps[code].id, season=season,
                                    utc_date=t0 + timedelta(days=7 * rd), status=MatchStatus.FINISHED,
                                    home_team_id=h.id, away_team_id=a.id,
                                    home_score=rnd.randint(0, 3), away_score=rnd.randint(0, 2)))
            cup = []
            for j in range(60):
                cross = j % 3 != 0
                if cross:
                    h, a = (rnd.choice(pl), rnd.choice(elc)) if j % 2 else (rnd.choice(elc), rnd.choice(pl))
                    strong_home = h in pl
                    if season == PRIOR:
                        u = rnd.random()
                        res = ("S" if u < 0.85 else "D" if u < 0.93 else "W")
                        hs, as_ = {"S": (3, 0), "D": (1, 1), "W": (0, 1)}[res]
                        if not strong_home:
                            hs, as_ = as_, hs
                    else:
                        hs, as_ = rnd.randint(0, 2), rnd.randint(0, 2)
                else:
                    grp = pl if j % 2 else elc
                    h, a = rnd.sample(grp, 2)
                    hs, as_ = rnd.randint(0, 2), rnd.randint(0, 2)
                m = Match(sport=Sport.SOCCER, competition_id=comps["EFL"].id, season=season,
                          stage="2nd Round", utc_date=t0 + timedelta(days=40, hours=j),
                          status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id,
                          home_score=hs, away_score=as_)
                s.add(m)
                cup.append(m)
            s.flush()
            ids["cup"][season] = [m.id for m in cup]
        ratings = {t.id: 1650 for t in pl} | {t.id: 1450 for t in elc}
        s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v22",
                           status="production", parameters={
                               "elo": {"league": {"ratings": ratings},
                                       "cup": {"ratings": {t: 1500 for t in ratings}}},
                               "team_to_league": {t.id: "PL" for t in pl} | {t.id: "ELC" for t in elc},
                               "contexts": {}, "poisson": {"elo_goal_coeff": 0.0008,
                                                           "dixon_coles_rho": -0.10}}))
        ids["pl"], ids["elc"] = [t.id for t in pl], [t.id for t in elc]
    yield ids
    Base.metadata.drop_all(get_engine())


def test_grid_frozen_ascending_from_status_quo():
    assert cc.CUP_COEFF_GRID == (0.0008, 0.0012, 0.0016, 0.0020, 0.0024, 0.0030, 0.0040, 0.0050)
    assert list(cc.CUP_COEFF_GRID) == sorted(cc.CUP_COEFF_GRID)


def test_select_from_losses_argmin_tie_and_empty():
    g = (0.001, 0.002, 0.003)
    t = cc.select_from_losses({"same_league": {0.001: [0.5], 0.002: [0.5], 0.003: [0.6]},
                               "cross_league": {0.001: [0.9], 0.002: [0.7], 0.003: [0.8]}}, g)
    assert t.best == {"same_league": 0.001, "cross_league": 0.002}   # tie -> smaller
    t = cc.select_from_losses({"same_league": {}, "cross_league": {0.002: [0.4]}}, g)
    assert "same_league" not in t.best and t.best["cross_league"] == 0.002


def test_exam_exclusions_cover_key_pairs_and_el_alias():
    ex = cc.exam_exclusions([{"comp": "EFL"}, {"comp": "CL"}], {EXAM})
    assert {("EFL", EXAM), ("CL", EXAM), ("UEL", EXAM), ("EL", EXAM)} <= ex
    assert ("EFL", PRIOR) not in ex


def test_pool_excludes_exam_season(world):
    assert cc.tuning_pool(cc.exam_exclusions([{"comp": "EFL"}], {EXAM})) == [("EFL", PRIOR)]


def test_context_coeffs_applied_and_default_unchanged(world):
    base = {r["match_id"]: r for r in _generate_predictions_soccer("EFL", PRIOR, include_finished=True)}
    empty = {r["match_id"]: r for r in _generate_predictions_soccer("EFL", PRIOR, include_finished=True,
                                                                     cup_coeffs={})}
    tuned = {r["match_id"]: r for r in _generate_predictions_soccer(
        "EFL", PRIOR, include_finished=True,
        cup_coeffs={"same_league": 0.0012, "cross_league": 0.0050})}
    for mid, r in base.items():
        assert r["elo_goal_coeff"] == 0.0008                        # nothing persisted: base coeff
        assert (r["p_home"], r["p_draw"]) == (empty[mid]["p_home"], empty[mid]["p_draw"])
        want = 0.0012 if r["cup_context"] == "same_league" else 0.0050
        assert tuned[mid]["elo_goal_coeff"] == want
    ctxs = {r["cup_context"] for r in base.values()}
    assert ctxs == {"same_league", "cross_league"}


def test_grid_probs_equal_the_shipped_path(world):
    grid = (0.0008, 0.0030)
    rows = _generate_predictions_soccer("EFL", PRIOR, include_finished=True, cup_coeff_grid=grid)
    at30 = {r["match_id"]: r for r in _generate_predictions_soccer(
        "EFL", PRIOR, include_finished=True,
        cup_coeffs={"same_league": 0.0030, "cross_league": 0.0030})}
    for r in rows:
        assert r["grid_probs"][0.0008] == (r["p_home"], r["p_draw"], r["p_away"])
        o = at30[r["match_id"]]
        assert r["grid_probs"][0.0030] == (o["p_home"], o["p_draw"], o["p_away"])


def test_league_pricing_ignores_cup_coeffs(world):
    a = _generate_predictions_soccer("PL", PRIOR, include_finished=True)
    b = _generate_predictions_soccer("PL", PRIOR, include_finished=True,
                                     cup_coeffs={"same_league": 0.05, "cross_league": 0.05},
                                     cup_coeff_grid=(0.05,))
    assert [(r["p_home"], r["p_draw"]) for r in a] == [(r["p_home"], r["p_draw"]) for r in b]
    assert all("grid_probs" not in r and "cup_context" not in r for r in b)


def test_persisted_top_level_key_is_read_without_breaking_poisson_config(world):
    with session_scope() as s:
        mv = s.execute(select(ModelVersion).where(ModelVersion.version == "v22")).scalar_one()
        saved = dict(mv.parameters)
        mv.parameters = {**saved, "cup_elo_goal_coeff": {"cross_league": 0.0040}}
    try:
        rows = _generate_predictions_soccer("EFL", PRIOR, include_finished=True)
        assert {r["elo_goal_coeff"] for r in rows if r["cup_context"] == "cross_league"} == {0.0040}
        assert {r["elo_goal_coeff"] for r in rows if r["cup_context"] == "same_league"} == {0.0008}
    finally:
        with session_scope() as s:
            mv = s.execute(select(ModelVersion).where(ModelVersion.version == "v22")).scalar_one()
            mv.parameters = saved


def test_tuning_recovers_cross_league_gap_writes_nothing_and_ignores_exam(world):
    excl = cc.exam_exclusions([{"comp": "EFL"}], {EXAM})
    before = _counts()
    t = cc.tune_cup_coeffs(excl)
    assert _counts() == before
    assert t.pool == [("EFL", PRIOR)] and t.n["cross_league"] == 40 and t.n["same_league"] == 20
    assert t.best["cross_league"] > 0.0008                 # the muted delegate is un-muted
    # exam-season cup results cannot move the selection
    with session_scope() as s:
        saved = {mid: (s.get(Match, mid).home_score, s.get(Match, mid).away_score)
                 for mid in world["cup"][EXAM]}
        for mid in world["cup"][EXAM]:
            m = s.get(Match, mid)
            m.home_score, m.away_score = 0, 5
    try:
        assert cc.tune_cup_coeffs(excl).best == t.best
    finally:
        with session_scope() as s:
            for mid, (hs, as_) in saved.items():
                m = s.get(Match, mid)
                m.home_score, m.away_score = hs, as_
