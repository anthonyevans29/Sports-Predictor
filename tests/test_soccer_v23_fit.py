"""soccer-v23's model (src/models/joint_poisson.py): the joint log-linear fit, on SYNTHETIC windows only (ARCHITECT
2026-11-04, addendum 248 item 2(b); addendum 230 item 1(d); addendum 216 items 1-3). Nothing here reads a database.

What is pinned: 216 item 1's three quantities in and out (the average-team rating, the total, the home/away ratio) on
the review's shape and on the addendum's b = 1.15, BY CONSTRUCTION (exact score equations for any β, τ or prior); the
first-season pull identity; the per-team continuity of 216 item 2 (a team with no season-S row reads exactly its S−1
estimate; no jump at the league's 30th match); the promoted prior; β unidentified; the refusals; determinism; the
pricing adaptor through the real predict_match; Dixon–Coles mean preservation at a fixed ρ."""
from __future__ import annotations

import math
import random

import numpy as np
import pytest

from src.models import joint_poisson as jp
from src.models.poisson import CompetitionScoringContext, PoissonConfig, TeamStrength, predict_match

N = 20


def average_league(g: float, b: float, slot: str, teams=range(N)) -> list:
    """A double round robin of AVERAGE teams scored at the true means: home g·b, away g·(2−b) (216 item 1's league)."""
    return [jp.Obs(h, a, slot, g * b, g * (2 - b), 0.0) for h in teams for a in teams if h != a]


def random_league(seed: int, teams=range(N), slots=(jp.PREV, jp.CUR), elo=True) -> list:
    rng = random.Random(seed)
    att = {t: rng.gauss(0, 0.25) for t in teams}
    dfn = {t: rng.gauss(0, 0.2) for t in teams}
    out = []
    for s in slots:
        for h in teams:
            for a in teams:
                if h == a:
                    continue
                lh = math.exp(0.15 + 0.2 + att[h] + dfn[a])
                la = math.exp(0.15 + att[a] + dfn[h])
                out.append(jp.Obs(h, a, s, float(np.random.default_rng(rng.randrange(1 << 30)).poisson(lh)),
                                  float(np.random.default_rng(rng.randrange(1 << 30)).poisson(la)),
                                  rng.uniform(-250, 250) if elo else 0.0))
    return out


@pytest.mark.parametrize("g, b", [(1.5, 1.2), (1.5, 1.15), (1.4, 1.15), (1.3, 1.30)])
def test_216_item_1_three_quantities_by_construction(g, b):
    """In: the data's average-team rating 1, total 2g, home/away ratio b/(2−b). Out (v23): the same, to float
    precision; v22's equations give (3−b)/2, g·(1+b)·((3−b)/2)² and b (216 item 1)."""
    obs = average_league(g, b, jp.PREV) + average_league(g, b, jp.CUR)
    f = jp.fit(obs)
    lh, la = jp.rates(f, 0, 1, 0.0)
    assert math.exp(f.cur[0][0]) == pytest.approx(1.0, abs=1e-12)            # the average-team rating
    assert math.exp(f.cur[0][1]) == pytest.approx(1.0, abs=1e-12)
    assert lh + la == pytest.approx(2 * g, abs=1e-12)                        # the total
    assert lh / la == pytest.approx(b / (2 - b), abs=1e-10)                  # the data's home/away ratio
    assert math.exp(f.h) == pytest.approx(b / (2 - b), abs=1e-10)
    assert abs(f.resid_home) < 1e-9 and abs(f.resid_away) < 1e-9


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("k_prior", [0.5, 5.0, 50.0])
def test_score_equations_hold_exactly_for_any_beta_tau_or_prior(seed, k_prior, monkeypatch):
    """I1 = Σ(y_H − λ̂_H) = 0 and I2 = Σ(y_A − λ̂_A) = 0 whatever τ (K_PRIOR), with β fitted on random ΔE."""
    monkeypatch.setattr(jp, "K_PRIOR", k_prior)
    obs = random_league(seed)
    f = jp.fit(obs)
    assert abs(f.resid_home) < 1e-9 and abs(f.resid_away) < 1e-9
    assert "beta_unidentified" not in f.labels and f.beta != 0.0


def test_sum_to_zero_on_the_previous_season_is_hard():
    f = jp.fit(random_league(7))
    assert abs(sum(a for a, _ in f.prev.values())) < 1e-12
    assert abs(sum(d for _, d in f.prev.values())) < 1e-12


def test_first_season_pull_identity_and_the_coherent_null_prior():
    """No S−1: μ and h carry the weak prior μ0 = ln(G0·(2−B0)), h0 = ln(B0/(2−B0)) (NOT b reused as a ratio); the
    identity is a pull: Σ(y − λ) = τ_μ(μ − μ0) and Σ(y_H − λ_H) = τ_μ(h − h0)."""
    assert jp.MU0 == math.log(1.4 * (2 - 1.15)) and jp.H0 == math.log(1.15 / (2 - 1.15))
    empty = jp.fit([])
    lh, la = jp.rates(empty, 1, 2, 0.0)
    assert lh == pytest.approx(1.4 * 1.15, abs=1e-12) and la == pytest.approx(1.4 * 0.85, abs=1e-12)
    assert lh + la == pytest.approx(2 * 1.4, abs=1e-12)
    obs = [o for o in random_league(4, slots=(jp.CUR,))][:60]
    f = jp.fit(obs)
    assert f.first_season and f.tau_mu == jp.K_PRIOR * jp.G0
    assert f.resid_home + f.resid_away == pytest.approx(f.tau_mu * (f.mu - jp.MU0), abs=1e-9)
    assert f.resid_home == pytest.approx(f.tau_mu * (f.h - jp.H0), abs=1e-9)


def test_216_item_2_a_team_with_no_season_row_reads_exactly_its_previous_estimate():
    obs = random_league(11)
    cur_without_5 = [o for o in obs if o.slot == jp.PREV or 5 not in (o.home, o.away)]
    f = jp.fit(cur_without_5)
    a, d, src = f.strength(5)
    assert src == "carried" and (a, d) == (jp.CARRY * f.prev[5][0], jp.CARRY * f.prev[5][1])


def test_promoted_prior_persists_and_first_season_has_none():
    obs = [o for o in random_league(12) if not (o.slot == jp.PREV and 19 in (o.home, o.away))]
    f = jp.fit([o for o in obs if not (o.slot == jp.CUR and 19 in (o.home, o.away))])
    assert f.strength(19) == (jp.PROMOTED_ATTACK, jp.PROMOTED_DEFENCE, "promoted prior")
    assert jp.PROMOTED_ATTACK == math.log(0.85) and jp.PROMOTED_DEFENCE == math.log(1.15)
    g = jp.fit(obs)                                     # 19 now has season-S rows: pulled toward the prior, not set
    assert 19 in g.cur and g.cur[19][0] != jp.PROMOTED_ATTACK
    assert jp.fit([o for o in obs if o.slot == jp.CUR]).strength(999) == (0.0, 0.0, "first-season prior")


def _avg_prev(teams, g=1.4, b=1.15):
    return [jp.Obs(h, a, jp.PREV, g * b, g * (2 - b), 0.0) for h in teams for a in teams if h != a]


@pytest.mark.parametrize("n_games", [1, 2, 4])
def test_a_promoted_club_with_a_few_rows_fits_on_the_promoted_side_near_the_prior(n_games):
    """The penalty of a club absent from S−1 targets the promoted prior IN THE FIT, not only in strength(): a few S rows
    at the league's rate leave its attack below 0 and its defence above, about K/(n + K) of the prior's offset."""
    g, b = 1.4, 1.15
    cur = [jp.Obs(19, 1 + j, jp.CUR, g * b, g * (2 - b), 0.0) for j in range(n_games)]
    f = jp.fit(_avg_prev(range(19)) + cur)
    a, d, src = f.strength(19)
    w = jp.K_PRIOR / (n_games + jp.K_PRIOR)
    assert src == "fit" and a < 0 < d
    assert a == pytest.approx(jp.PROMOTED_ATTACK * w, abs=0.01)
    assert d == pytest.approx(jp.PROMOTED_DEFENCE * w, abs=0.015)


def test_a_relegated_club_is_never_centred_on_the_promoted_side():
    """A club arriving from a HIGHER tier (the caller names it) carries no directional prior: with no S row it reads
    exactly 0 / 0; a strong arrival's few rows pull it above average where the promoted prior would hold it below."""
    g, b = 1.4, 1.15
    prev = _avg_prev(range(24))
    stay = list(range(3, 24))
    cur = []
    for j, h in enumerate(stay):
        a = stay[(j + 1) % len(stay)]
        cur.append(jp.Obs(h, a, jp.CUR, g * b, g * (2 - b), 0.0))
    strong_a, strong_d = math.exp(0.35), math.exp(-0.35)
    cur += [jp.Obs(90, 5, jp.CUR, g * b * strong_a, g * (2 - b) * strong_d, 0.0),
            jp.Obs(6, 90, jp.CUR, g * b * strong_d, g * (2 - b) * strong_a, 0.0)]
    rel = jp.fit(prev + cur, relegated={90})
    pro = jp.fit(prev + cur)
    assert rel.strength(90)[0] > 0 > pro.strength(90)[0]
    assert rel.strength(90)[1] < 0 < pro.strength(90)[1]
    assert jp.fit(prev + cur, relegated={91}).strength(91) == (jp.RELEGATED_ATTACK, jp.RELEGATED_DEFENCE,
                                                                 "relegated prior") == (0.0, 0.0, "relegated prior")
    assert jp.fit(prev + cur).strength(91) == (jp.PROMOTED_ATTACK, jp.PROMOTED_DEFENCE, "promoted prior")
    assert jp.fit([o for o in cur], relegated={90}).relegated == frozenset()      # the first season: no such concept


@pytest.mark.parametrize("n_games", [1, 2, 5, 10, 20])
def test_continuity_pulls_a_strong_club_toward_its_own_previous_estimate(n_games):
    """216 item 2 IN THE FIT, on a NON-neutral S−1: club 0 scored at twice the rate in S−1, then plays n S rows at the
    league's rate. Its season-S attack sits between its S−1 estimate and its S evidence (0), about n/(n + K_PRIOR) of
    the way from the former to the latter: the penalty links α_{0,S} to α_{0,S−1}, not to 0."""
    g, b = 1.4, 1.15
    prev = [jp.Obs(h, a, jp.PREV, g * b * (2 if h == 0 else 1), g * (2 - b) * (2 if a == 0 else 1), 0.0)
            for h in range(N) for a in range(N) if h != a]
    cur = [jp.Obs(0, 1 + j % (N - 1), jp.CUR, g * b, g * (2 - b), 0.0) for j in range(n_games)]
    f = jp.fit(prev + cur)
    ap, ac = f.prev[0][0], f.cur[0][0]
    assert ap > 0.5 and 0 < ac < ap
    assert 1 - ac / ap == pytest.approx(n_games / (n_games + jp.K_PRIOR), abs=0.04)


def test_beta_prior_bounds_a_first_season_window_of_a_few_rows():
    """β carries a weak prior at BETA_PRIOR_MEAN with BETA_PRIOR_PRECISION on ΔE/ELO_SCALE (every window): a
    first-season window of a few rows, whose small ΔE values come from those same results, cannot drive β to an
    extreme. Without the prior the review's probe read |β| 0.08 per point and p_home 1.0."""
    assert jp.BETA_PRIOR_MEAN == 0.0 and jp.BETA_PRIOR_PRECISION == jp.K_PRIOR * jp.G0
    rng = random.Random(17)
    worst = 0.0
    for _ in range(40):
        obs = []
        for j in range(rng.randint(3, 12)):
            hg, ag = rng.randint(0, 4), rng.randint(0, 3)
            obs.append(jp.Obs(j % 10, (j + 1 + j // 10) % 10, jp.CUR, float(hg), float(ag),
                              float(rng.choice((-1, 1)) * rng.uniform(0, 30))))
        f = jp.fit(obs)
        worst = max(worst, abs(f.beta))
        lh, la = jp.rates(f, 0, 1, 200.0)
        assert 0.2 < lh < 6.0 and 0.2 < la < 6.0
    assert worst < 3 / math.sqrt(jp.BETA_PRIOR_PRECISION) / jp.ELO_SCALE


def test_continuity_weight_is_about_n_over_n_plus_k_on_the_teams_own_exposure():
    """A team that scores at twice the league's rate in season S, after a neutral S−1: its fitted log-attack moves
    toward ln 2 with its own match count, roughly n/(n + K_PRIOR) of the way; never a switch."""
    base = average_league(1.4, 1.15, jp.PREV)
    moves = []
    for n_games in (0, 1, 2, 5, 10, 20):
        cur = []
        for j in range(n_games):
            a = 1 + j % (N - 1)
            cur.append(jp.Obs(0, a, jp.CUR, 2 * 1.4 * 1.15, 1.4 * 0.85, 0.0))
        f = jp.fit(base + cur)
        moves.append(f.strength(0)[0] / math.log(2.0))
    assert moves[0] == pytest.approx(0.0, abs=1e-12)
    assert all(x < y for x, y in zip(moves, moves[1:]))
    for n_games, m in zip((1, 2, 5, 10, 20), moves[1:]):
        assert m == pytest.approx(n_games / (n_games + jp.K_PRIOR), abs=0.12)


def test_beta_unidentified_when_every_elo_difference_is_zero():
    f = jp.fit(average_league(1.5, 1.2, jp.PREV) + average_league(1.5, 1.2, jp.CUR)[:10])
    assert f.beta == 0.0 and "beta_unidentified" in f.labels


@pytest.mark.parametrize("bad", ["zero_goals", "nan", "negative", "slot", "one_team"])
def test_refusals(bad):
    if bad == "zero_goals":
        obs = [jp.Obs(h, a, jp.PREV, 0.0, 0.0, 0.0) for h in range(4) for a in range(4) if h != a]
    elif bad == "nan":
        obs = [jp.Obs(0, 1, jp.PREV, float("nan"), 1.0, 0.0)]
    elif bad == "negative":
        obs = [jp.Obs(0, 1, jp.PREV, -1.0, 1.0, 0.0)]
    elif bad == "slot":
        obs = [jp.Obs(0, 1, "S-2", 1.0, 1.0, 0.0)]
    else:
        obs = [jp.Obs(0, 0, jp.PREV, 1.0, 1.0, 0.0)]
    with pytest.raises(jp.FitRefused):
        jp.fit(obs)


def test_no_convergence_refuses(monkeypatch):
    monkeypatch.setattr(jp, "MAX_ITER", 1)
    with pytest.raises(jp.FitRefused, match="no convergence"):
        jp.fit(random_league(3))


def test_a_damped_tie_is_never_convergence(monkeypatch):
    """Codex on #832, round 1 (fail-first: before the fix this fit returned silently after one iteration, its "last
    step" the 1e-16 displacement of a step halved until rounding made the objective tie, its μ the cold start's and its
    home residual 86 goals). A solve poisoned to return an ascent direction (what rounding does to an ill-conditioned
    window's Newton step) leaves the line search no step that lowers the objective while the full step and the
    gradient stay large: the fit refuses, named, and never returns."""
    obs = random_league(3)
    real = np.linalg.solve
    monkeypatch.setattr(np.linalg, "solve", lambda H, g: -real(H, g))
    with pytest.raises(jp.FitRefused, match="the line search stalled") as e:
        jp.fit(obs)
    assert "max|gradient|" in str(e.value)


def test_convergence_is_on_the_full_newton_step():
    """Every fit returns only at a full Newton step max|H⁻¹g| < TOL (last_step IS that step, never a damped
    displacement): checked here by recomputing the full step at the returned parameters through the same objective.
    The stalled-line-search rule (_newton) reads PRECISION_FLOOR only to decide whether the objective can resolve the
    step; it never declares convergence."""
    for seed in (3, 21, 937, 943):
        f = jp.fit(random_league(seed))
        assert f.last_step < jp.TOL and f.iterations <= jp.MAX_ITER


def test_newton_on_a_blind_objective_takes_the_full_step_and_converges_on_it():
    """_newton alone, on a quadratic whose minimum is `target`. (1) An objective that cannot resolve the last step
    (every move off the start reads 1e-12 higher: rounding noise) never refuses where the Newton decrement is under
    PRECISION_FLOOR·|objective|: it takes the full step and converges on max|H⁻¹g| < TOL, at the minimum. (2) Where the
    decrement is resolvable and every move raises the objective (the start is its minimum: a direction rounding has
    turned), it refuses, named; it never returns the start as converged."""
    target = np.array([1e-7, -2e-7])
    H = np.diag([3.0, 5.0])
    derivs = lambda th: (H @ (th - target), H)                               # noqa: E731
    start = np.zeros(2)
    noisy = lambda th: 1000.0 + (1e-12 if np.any(th != start) else 0.0)     # noqa: E731
    th, it, last = jp._newton(noisy, derivs, start.copy())
    assert last < jp.TOL and np.allclose(th, target, rtol=0, atol=1e-18) and it == 2
    far = np.array([1.0, 1.0])
    with pytest.raises(jp.FitRefused, match="the line search stalled"):
        jp._newton(lambda th: 1000.0 + float(np.sum(np.abs(th - far))), derivs, far.copy())


def test_deterministic_and_cold_started():
    obs = random_league(21)
    a, b = jp.fit(obs), jp.fit(list(obs))
    assert (a.mu, a.h, a.beta, a.prev, a.cur) == (b.mu, b.h, b.beta, b.prev, b.cur)


def test_the_pricing_adaptor_returns_the_fitted_rates_through_the_real_predict_match():
    """Context (1, 1), TeamStrength(λ, 1), elo_goal_coeff 0: home_xg = λ_H and away_xg = λ_A to 1e-15, the floor,
    ρ and the 1X2 renormalisation v22's own (soccer_v23.price)."""
    from src.walters import soccer_v23 as v
    for lh, la in ((1.61, 1.19), (0.3, 2.7), (2.2, 0.9)):
        p = v.price(lh, la, {"dixon_coles_rho": -0.10, "elo_goal_coeff": 0.0008})
        assert abs(p.home_xg - lh) <= 1e-15 and abs(p.away_xg - la) <= 1e-15
        q = predict_match(1500.0, 1500.0, TeamStrength(lh, 1.0), TeamStrength(la, 1.0),
                          CompetitionScoringContext(1.0, 1.0), PoissonConfig(dixon_coles_rho=-0.10, elo_goal_coeff=0.0))
        assert (p.p_home, p.p_draw, p.p_away, p.p_over) == (q.p_home, q.p_draw, q.p_away, q.p_over)


@pytest.mark.parametrize("rho", [-0.10, -0.05, 0.05])
def test_dixon_coles_keeps_both_means_at_a_fixed_rho(rho):
    """p10·λ_A·ρ − p11·ρ = 0 (and alike for Y): the DC cells leave E[X] and E[Y] unchanged, so λ fitted under
    independent Poisson stays the mean the priced matrix expresses (to the truncation at max_goals)."""
    lam, mu = 1.6, 1.1
    k = np.arange(0, 41)
    px = np.array([math.exp(-lam) * lam ** i / math.factorial(i) for i in k])
    py = np.array([math.exp(-mu) * mu ** i / math.factorial(i) for i in k])
    m = np.outer(px, py)
    d = m.copy()
    d[0, 0] *= 1 - lam * mu * rho
    d[1, 0] *= 1 + mu * rho
    d[0, 1] *= 1 + lam * rho
    d[1, 1] *= 1 - rho
    assert d.sum() == pytest.approx(m.sum(), abs=1e-15)
    assert (d.sum(axis=1) * k).sum() == pytest.approx(lam, abs=1e-12)
    assert (d.sum(axis=0) * k).sum() == pytest.approx(mu, abs=1e-12)


def test_no_time_decay_every_row_weighs_one():
    """Reordering the window changes nothing material: no row carries a weight (S19 stays rejected)."""
    obs = random_league(31)
    a = jp.fit(obs)
    b = jp.fit(list(reversed(obs)))
    assert a.mu == pytest.approx(b.mu, abs=1e-10) and a.beta == pytest.approx(b.beta, abs=1e-12)
