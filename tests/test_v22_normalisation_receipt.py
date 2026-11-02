"""THE v22 NORMALISATION RECEIPT (ARCHITECT 2026-11-02 10:50 ET, addendum 216 item 1(b)), READ-ONLY.

THE RULING, item 1(b) verbatim: "(b) Code's receipt PR, read-only: one test that drives the REAL estimate_strengths and
the real forecast with the review's synthetic league and pins the −8.7% total (the review's script is the receipt's
citation, not repository code — it reimplements the equations), plus a read-only line that evaluates the same
expressions on the production model's stored PL context (g and b as stored) and prints the implied average-team
rating, total and home/away ratio; posted on the Issue; (c) NO change to v22: the fix is a candidate through the frozen
gate, never a patch to a live model."

CITED, NOT COPIED: the review (the operator's GPT, 2026-11-02) and its normalisation_diagnostic.py (the operator
supplied it; sha256 a91de689b0aa67cd4ef8548ef28bda62930ca871ca52cd2e4d9eee52bf44b677), which reimplements the equations
and cites src/walters/training.py blob c1bdcd4b4fd7b315ffe96f31f60aed6fc5681546 and src/models/poisson.py blob
e9ccab21b640f0b5a051bdbd55d446f7426af717, exactly origin/main's blobs on 2026-11-02. Nothing of it is in the repository;
this test calls the repository's own functions: src/models/poisson.py estimate_strengths (the home deflation by b,
poisson.py:180-184; both averages divided by the undeflated g, poisson.py:205-206; the n/(n+5) shrinkage on
n = min(len(gf), len(ga)), poisson.py:213-219; the 0.25 floor, poisson.py:222-223) and predict_match (home
λ = g·b·A_H·D_A·elo and away λ = g·A_A·D_H·elo, poisson.py:272-284; the 0.05 floor, poisson.py:291-292).

THE REVIEW'S LEAGUE, REPRODUCED EXACTLY THROUGH THE REAL CODE (the headline test): two equally strong teams, 20 games at
each venue (team 1 at home to team 2, then team 2 at home to team 1); each venue's 20 games are 18 at 2-1 and 2 at 0-3
(index % 10 == 9 gives 0-3), so the home mean is 1.8, the away mean 1.2, 3.000 goals per match in. The context:
g = 120 / 80 = 1.5 and b = 1.8 / 1.5 = 1.2 (inside the clamp). training.py builds it inline in _train_fresh_soccer
(training.py:196-214) inside a DB session, with no pure helper to call, so this file computes it with the same
expressions (context_from below) and pins g 1.5, b 1.2. n = 40 per team, so the shrinkage weight is 40/45; equal Elo; no
injury, lineup or XI factors. The real code gives attack and defence 0.911111 for both teams (the review's printed
figures to 1e-15; the last bit is the interpreter's), home λ 1.494222, away λ 1.245185, total 2.7394074074074064 (−8.6864%): the review's own
asserted total 2.739407407407407, to 1e-9. Under one interpreter the floats agree to the last bit (on Python 3.11
the real code and the review's script both compute 2.7394074074074064; 3.12's compensated float sum can move the last
bit of both alike); the review's literal 2.739407407407407 is the exact value 1.5·2.2·(41/45)² = 18491/6750
rounded to 16 digits, which is within 4.4e-16 of the float and inside the review's own abs_tol of 1e-12.
Before shrinkage the same equations give the average-team rating (3−b)/2 = 0.9 and a total 1.5·2.2·0.9² = 2.673
(−10.9%); the n/(n+5) pull toward 1.0 at n = 40 brings it to 2.7394. NO difference between the real code and the
review's reimplementation for this league: the same n (min of the two lists), the same 1.0 shrinkage target (no prior;
the live caller passes none, training.py:525), the same clamp; the floors (0.25, 0.05) are not reached; the Elo
multipliers are exp(0) = 1 exactly; Dixon–Coles rho reweights cells only, never λ (shown). The live caller's 30-match
switch (training.py:476/489) would not fire on 40 finished matches.

THE ADDENDUM'S "about −8% at b = 1.15" (the average-team derivation): a league of AVERAGE teams, 20 teams, a double
round robin (380 matches, 38 per team), every match scored home g·b and away g·(2−b) (floats; the true means), g = 1.5.
At b = 1.15 the real code, with the n/(n+5) shrinkage undone exactly (raw = (out − (1 − w)) / w, w = 38/43), gives the
pre-shrinkage rating 0.925 and 3.000 in, 2.759 out (−8.02%): the addendum's figure is the pre-shrinkage average-team
figure at b = 1.15; the review's −8.7% is at b = 1.2 with n = 40 shrinkage. As run over that 38-game season the b = 1.15
league reads 2.812 (−6.28%).

NEUTRALISATIONS (each stated):
  * Elo: both sides 1500, so elo_diff = 0 and both Elo multipliers are exp(0) = 1 exactly (poisson.py:267-269).
  * Match factors: factor_adjustment=None (poisson.py:286), no injuries, no lineups.
  * Shrinkage: n/(n+5) toward 1.0 cannot be switched off in estimate_strengths (poisson.py:213-214). The review league
    is pinned AS RUN (n = 40); the average-team tests recover the pre-shrinkage rating from the REAL output exactly and
    drive the real predict_match on it, the as-run (n = 38) forecast pinned beside it.
  * Dixon–Coles rho does not enter λ (poisson.py:303-311 reweights cells only); PoissonConfig() default.

WHAT IS PINNED (the addendum's equations, item 1): per-team average rating (3−b)/2 (0.925 at b = 1.15, 0.9 at b = 1.2)
before shrinkage; forecast total g·(1+b)·((3−b)/2)²; the home/away ratio the model expresses is b, the data's b/(2−b).

THIRD READER of the stored contexts (beside the live path and, by default only, the backtest): the improve gate's
holdout scorer, src/walters/training.py:2053-2120 (_score_model_on_holdout_soccer, contexts read at :2073-2074 and
taken per competition at :2082; called from improve at :1810-1811).
"""
from __future__ import annotations

import math

import pytest

from src.models.poisson import (CompetitionScoringContext, PoissonConfig, TeamStrength, estimate_strengths,
                                predict_match)

G = 1.5                    # 3.000 goals per match in
N_TEAMS = 20
PER_TEAM = 2 * (N_TEAMS - 1)            # 38 matches per team (19 home, 19 away)
W = PER_TEAM / (PER_TEAM + 5)          # poisson.py:214, the shrinkage weight


def league(g: float, b: float) -> list[dict]:
    """The average-team league: every fixture of a double round robin, scored at the true means."""
    return [{"home_team_id": h, "away_team_id": a, "home_score": g * b, "away_score": g * (2 - b)}
            for h in range(N_TEAMS) for a in range(N_TEAMS) if h != a]


def context_from(matches: list[dict]) -> CompetitionScoringContext:
    """training.py:196-214's formulas on the synthetic league (no DB): g = total / (2 × matches), b = home mean / g,
    clamped to [1.0, 1.30]."""
    total = sum(m["home_score"] + m["away_score"] for m in matches)
    home = sum(m["home_score"] for m in matches)
    avg = total / (2 * len(matches))
    boost = (home / len(matches)) / avg
    return CompetitionScoringContext(avg_goals_per_team_per_match=avg,
                                     home_field_goal_boost=max(1.0, min(1.30, boost)))


def closed_form(g: float, b: float) -> dict:
    """The addendum's equations (item 1), verbatim in form."""
    r = (3 - b) / 2
    total = g * (1 + b) * r * r
    return {"rating": r, "total": total, "deficit": total / (2 * g) - 1, "ratio_model": b, "ratio_data": b / (2 - b)}


def run_real(g: float, b: float) -> dict:
    """Drive the real estimate_strengths and predict_match on the league; return the pre-shrinkage rating (exact
    inversion of the real output), the forecast on it, and the as-run (shrunk) forecast."""
    matches = league(g, b)
    ctx = context_from(matches)
    st = estimate_strengths(matches, ctx)
    assert len(st) == N_TEAMS
    atts = {round(s.attack, 12) for s in st.values()}
    defs = {round(s.defense, 12) for s in st.values()}
    assert len(atts) == 1 and len(defs) == 1          # every team equal, as the average-team derivation has it
    att, dfn = st[0].attack, st[0].defense
    raw_att, raw_def = (att - (1 - W)) / W, (dfn - (1 - W)) / W
    cfg = PoissonConfig()
    pre = TeamStrength(attack=raw_att, defense=raw_def)
    p = predict_match(1500.0, 1500.0, pre, pre, ctx, cfg)
    p_shrunk = predict_match(1500.0, 1500.0, st[0], st[1], ctx, cfg)
    data_total = 2 * ctx.avg_goals_per_team_per_match
    return {"ctx": ctx, "att_shrunk": att, "def_shrunk": dfn, "raw_att": raw_att, "raw_def": raw_def,
            "home_xg": p.home_xg, "away_xg": p.away_xg, "total": p.home_xg + p.away_xg,
            "deficit": (p.home_xg + p.away_xg) / data_total - 1, "ratio_model": p.home_xg / p.away_xg,
            "data_total": data_total, "total_shrunk": p_shrunk.home_xg + p_shrunk.away_xg}


def review_league() -> list[dict]:
    """The review's league (normalisation_diagnostic.py, sha256 a91de689…b677), built as the same match dicts the live
    caller hands estimate_strengths (training.py:515-524): team 1 at home to team 2 twenty times, then team 2 at home to
    team 1 twenty times; at each venue index % 10 == 9 is 0-3, every other game 2-1 (integer scores, as stored)."""
    out = []
    for home, away in ((1, 2), (2, 1)):
        for index in range(20):
            hs, as_ = (0, 3) if index % 10 == 9 else (2, 1)
            out.append({"home_team_id": home, "away_team_id": away, "home_score": hs, "away_score": as_})
    return out


def test_the_review_league_reproduces_exactly_through_the_real_code():
    """THE HEADLINE (item 1(b)): the review's synthetic league through the REAL estimate_strengths and the REAL
    predict_match pins the −8.7% total: 3.000 in, 2.739407407407407 out (−8.6864%), at b = 1.2 with n = 40 shrinkage.
    Any difference between the real code and the review's reimplementation would fail a pin below; there is none."""
    matches = review_league()
    assert len(matches) == 40
    home_mean = sum(m["home_score"] for m in matches) / len(matches)
    away_mean = sum(m["away_score"] for m in matches) / len(matches)
    assert home_mean == pytest.approx(1.8, abs=1e-12) and away_mean == pytest.approx(1.2, abs=1e-12)
    # the context by training.py:196-214's own expressions (inline in _train_fresh_soccer, no pure helper without a DB)
    ctx = context_from(matches)
    assert ctx.avg_goals_per_team_per_match == pytest.approx(1.5, abs=1e-12)
    assert ctx.home_field_goal_boost == pytest.approx(1.2, abs=1e-12)
    assert 1.0 < ctx.home_field_goal_boost < 1.30                        # inside the clamp, not at it
    # the same figures as CompetitionScoringContext(g=1.5, b=1.2) given directly
    direct = CompetitionScoringContext(avg_goals_per_team_per_match=1.5, home_field_goal_boost=1.2)

    st = estimate_strengths(matches, ctx)
    assert set(st) == {1, 2}
    assert estimate_strengths(matches, direct) == st
    # attack and defence 0.911111 for both teams: the review's printed dict to 1e-15. The last bit depends on the
    # interpreter, not on the model: Python 3.12's sum() of floats is compensated (3.11's is not), so the real code
    # and the review's script both print (0.9111111111111111, 0.9111111111111106) under 3.11 and 0.9111111111111111
    # for all four under 3.12 (CI's).
    for got, review in (((st[1].attack, st[1].defense), (0.9111111111111111, 0.9111111111111106)),
                        ((st[2].attack, st[2].defense), (0.9111111111111106, 0.9111111111111111))):
        assert got == pytest.approx(review, abs=1e-15)
    for s in st.values():
        assert s.attack == pytest.approx(41 / 45, abs=1e-12) and s.defense == pytest.approx(41 / 45, abs=1e-12)
        # n = 40 per team (w = 40/45) on the pre-shrinkage average-team rating (3 − b)/2 = 0.9
        w = 40 / 45
        assert (s.attack - (1 - w)) / w == pytest.approx((3 - 1.2) / 2, abs=1e-12)
        assert (s.defense - (1 - w)) / w == pytest.approx(0.9, abs=1e-12)

    cfg = PoissonConfig()
    p = predict_match(1500.0, 1500.0, st[1], st[2], ctx, cfg)
    # v22's rho (−0.10) reweights cells only: λ is unchanged
    p_rho = predict_match(1500.0, 1500.0, st[1], st[2], ctx, PoissonConfig(dixon_coles_rho=-0.10))
    assert (p_rho.home_xg, p_rho.away_xg) == (p.home_xg, p.away_xg)
    total = p.home_xg + p.away_xg
    deficit = total / (home_mean + away_mean) - 1
    pre = 1.5 * (1 + 1.2) * 0.9 ** 2                                    # the equations before shrinkage
    print(f"\nRECEIPT the review's league: in {home_mean:.6f}/{away_mean:.6f}/{home_mean + away_mean:.6f}; g "
          f"{ctx.avg_goals_per_team_per_match:.6f} b {ctx.home_field_goal_boost:.6f}; attack/defence "
          f"{st[1].attack:.6f}/{st[1].defense:.6f} and {st[2].attack:.6f}/{st[2].defense:.6f}")
    print(f"RECEIPT the review's league: out home {p.home_xg:.6f} away {p.away_xg:.6f} total {total!r} "
          f"({deficit * 100:+.4f}%); before shrinkage (rating 0.9) {pre:.4f} ({(pre / 3 - 1) * 100:+.2f}%); "
          f"ratio model {p.home_xg / p.away_xg:.4f} vs data {home_mean / away_mean:.4f}")
    assert p.home_xg == pytest.approx(1.494222, abs=5e-7)
    assert p.away_xg == pytest.approx(1.245185, abs=5e-7)
    assert total == pytest.approx(2.739407407407407, abs=1e-9)          # the review's asserted total
    assert round(deficit * 100, 4) == -8.6864
    assert round(deficit * 100, 1) == -8.7
    # before shrinkage: 1.5·2.2·0.9² = 2.673 (−10.9%); the n/(n+5) pull toward 1.0 brings it to 2.7394
    assert round(pre, 3) == 2.673 and round((pre / 3 - 1) * 100, 1) == -10.9
    assert total == pytest.approx(1.5 * 2.2 * (41 / 45) ** 2, abs=1e-12)
    # the ratio: the model expresses b (1.2); the data's is b/(2−b) (1.5)
    assert p.home_xg / p.away_xg == pytest.approx(1.2, abs=1e-12)
    assert home_mean / away_mean == pytest.approx(1.2 / (2 - 1.2), abs=1e-12)


def test_the_context_is_training_py_s_g_and_b():
    ctx = context_from(league(G, 1.15))
    assert ctx.avg_goals_per_team_per_match == pytest.approx(1.5, abs=1e-12)
    assert ctx.home_field_goal_boost == pytest.approx(1.15, abs=1e-12)


def test_receipt_at_the_default_b_1_15():
    real, cf = run_real(G, 1.15), closed_form(G, 1.15)
    print(f"\nRECEIPT b=1.15 g=1.5: rating (pre-shrinkage) attack {real['raw_att']:.6f} defense {real['raw_def']:.6f} "
          f"(addendum (3-b)/2 = {cf['rating']:.6f}); as-run n=38 {real['att_shrunk']:.6f}")
    print(f"RECEIPT b=1.15: in {real['data_total']:.3f} out {real['total']:.4f} ({real['deficit'] * 100:+.2f}%); "
          f"addendum g(1+b)((3-b)/2)^2 = {cf['total']:.4f}; as-run n=38 out {real['total_shrunk']:.4f} "
          f"({(real['total_shrunk'] / real['data_total'] - 1) * 100:+.2f}%)")
    print(f"RECEIPT b=1.15: home/away ratio the model expresses {real['ratio_model']:.4f}, the data's "
          f"{cf['ratio_data']:.4f}")
    # the average-team rating (3−b)/2 = 0.925, before shrinkage, both attack and defence
    assert real["raw_att"] == pytest.approx(0.925, abs=1e-12)
    assert real["raw_def"] == pytest.approx(0.925, abs=1e-12)
    # as run (n = 38): w·0.925 + (1 − w)·1.0
    assert real["att_shrunk"] == pytest.approx(W * 0.925 + (1 - W), abs=1e-12)
    # the forecast: home λ = g·b·r², away λ = g·r²; total g·(1+b)·r²
    assert real["home_xg"] == pytest.approx(1.5 * 1.15 * 0.925 ** 2, abs=1e-12)
    assert real["away_xg"] == pytest.approx(1.5 * 0.925 ** 2, abs=1e-12)
    assert real["total"] == pytest.approx(cf["total"], abs=1e-12)
    assert real["data_total"] == pytest.approx(3.0, abs=1e-12)
    assert round(real["total"], 3) == 2.759 and round(real["deficit"] * 100, 1) == -8.0
    # the ratio: the model expresses b (1.15); the data's is b/(2−b) (1.35)
    assert real["ratio_model"] == pytest.approx(1.15, abs=1e-12)
    assert round(cf["ratio_data"], 2) == 1.35
    # the as-run season (n = 38) still under-forecasts: shrinkage toward 1.0 masks part of the deficit, not all
    assert real["total_shrunk"] < real["data_total"]
    assert real["total_shrunk"] == pytest.approx(1.5 * 2.15 * (W * 0.925 + (1 - W)) ** 2, abs=1e-12)


@pytest.mark.parametrize("b", [1.0, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30])
def test_the_real_code_is_the_addendum_s_equations_across_the_clamp_range(b):
    real, cf = run_real(G, b), closed_form(G, b)
    assert real["raw_att"] == pytest.approx(cf["rating"], abs=1e-12)
    assert real["raw_def"] == pytest.approx(cf["rating"], abs=1e-12)
    assert real["total"] == pytest.approx(cf["total"], abs=1e-12)
    assert real["ratio_model"] == pytest.approx(b, abs=1e-12)
    if b == 1.0:
        assert real["deficit"] == pytest.approx(0.0, abs=1e-12)      # no home effect: no deficit
    else:
        assert real["deficit"] < 0                                   # every b > 1: fewer goals out than in


def test_the_deficit_scales_with_g_not_in_percent():
    """g only scales: the % deficit depends on b alone (g·(1+b)·r² / 2g)."""
    for g in (1.2, 1.4, 1.5, 1.7):
        assert run_real(g, 1.15)["deficit"] == pytest.approx(closed_form(G, 1.15)["deficit"], abs=1e-12)


def test_the_mass_moves_toward_draw_and_away():
    """The structural direction (item 1: "toward fewer goals and away/draw mass"): against a forecast at the data's
    own means (home g·b, away g·(2−b)), the real forecast's p_draw is higher and its p_home lower."""
    b = 1.15
    real = run_real(G, b)
    ctx = real["ctx"]
    cfg = PoissonConfig()
    pre = TeamStrength(real["raw_att"], real["raw_def"])
    model = predict_match(1500.0, 1500.0, pre, pre, ctx, cfg)
    # the data's means through the same function: unit ratings, the away side's rate set by a factor multiplier
    from types import SimpleNamespace
    unit = TeamStrength(1.0, 1.0)
    truth = predict_match(1500.0, 1500.0, unit, unit, ctx, cfg,
                          factor_adjustment=SimpleNamespace(home_xg_multiplier=1.0, away_xg_multiplier=2 - b))
    assert truth.home_xg + truth.away_xg == pytest.approx(3.0, abs=1e-12)
    print(f"\nRECEIPT 1X2 at b=1.15: model H/D/A {model.p_home:.4f}/{model.p_draw:.4f}/{model.p_away:.4f} vs the data's "
          f"means {truth.p_home:.4f}/{truth.p_draw:.4f}/{truth.p_away:.4f}")
    assert model.p_draw > truth.p_draw
    assert model.p_home < truth.p_home
    assert model.p_away > truth.p_away
    assert math.isclose(model.p_home + model.p_draw + model.p_away, 1.0, abs_tol=1e-12)
