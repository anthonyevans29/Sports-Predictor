"""
soccer-v23's model: THE JOINT LOG-LINEAR POISSON FIT (ARCHITECT 2026-11-02 10:50 ET, addendum 216 item 3; addendum 230
item 1(d); addendum 248 item 2(b); lane soccer-v23, #656). A DESIGN: nothing here is run on real data before the
architect's declaration (11-20) and his word (11-27). PURE: numpy and math only; no database, no clock, no globals read
at call time, no randomness. v22 (src/models/poisson.py, src/walters/training.py) is not touched and not imported.

THE EQUATIONS (216 item 3, verbatim in form), for one competition's window of finished rows r (home a, away b, the
season slot s of the row: the previous season S−1 or the fixture's season S):

    log λ_H(r) = μ + h + α_{a,s} + δ_{b,s} + β·ΔE_r
    log λ_A(r) = μ     + α_{b,s} + δ_{a,s} − β·ΔE_r

ΔE_r is the row's own pre-kickoff Elo difference (home − away, rating points, no home advantage added), walked on the
ladder by the caller and never fitted here. Internally the column is ΔE/ELO_SCALE (conditioning only); `beta` is
reported per rating point.

THE OBJECTIVE (minimised): Σ_obs (λ − y·log λ) + ½·Σ_k w_k·(D_k·φ − d_k)², the Poisson negative log-likelihood (the
log y! term dropped) plus the penalty rows:
  * every S−1 team k:              α_{k,S−1} → 0 and δ_{k,S−1} → 0, weight τ;
  * every S team k seen in S−1:    α_{k,S} − CARRY·α_{k,S−1} → 0 (and δ alike), weight τ: the per-team continuity of
                                   216 item 2 (the weight on the team's own season-S evidence is about n_k/(n_k +
                                   K_PRIOR), on its own exposure; at n_k = 0 the team reads exactly its S−1 estimate);
  * every S team k not seen in S−1 and arriving from below or from outside the store (promoted): α_{k,S} →
                                   PROMOTED_ATTACK, δ_{k,S} → PROMOTED_DEFENCE, weight τ: the persistent promoted
                                   prior, relative to S−1's zero mean;
  * every S team k not seen in S−1 and arriving from a HIGHER tier (relegated; the caller names them, from its declared
                                   pyramid: soccer_v23.PYRAMIDS): α_{k,S} → RELEGATED_ATTACK (0), δ_{k,S} →
                                   RELEGATED_DEFENCE (0), weight τ: no directional prior (a club relegated into the
                                   competition is never centred on the promoted side; a proposed ruling, spec §11);
  * β (every window, one rule): β → BETA_PRIOR_MEAN (0), precision BETA_PRIOR_PRECISION = K_PRIOR·G0 on the column
                                   ΔE/ELO_SCALE: a weak prior, so a competition's first few rows cannot drive β to an
                                   extreme (a proposed ruling, spec §11);
  * IDENTIFICATION: a HARD sum-to-zero on α_{·,S−1} and on δ_{·,S−1}, by substitution (the highest team id, last in
                                   sorted order, is the dependent one). μ and h are UNPENALISED whenever S−1 exists.
  τ = K_PRIOR·λ̄_{S−1}, λ̄_{S−1} the window's S−1 goals per team per match (the Poisson information per observation of
  a log-rate is λ, so τ is K_PRIOR matches' worth): derived inside the fit, never a free number.

216 ITEM 1 BY CONSTRUCTION. With μ and h unpenalised the score equations are ∂/∂μ: Σ(y_H − λ_H) + Σ(y_A − λ_A) = 0
and ∂/∂h: Σ(y_H − λ_H) = 0, so Σλ̂_H = Σy_H and Σλ̂_A = Σy_A EXACTLY, for any β, τ or prior (β's prior included): a league of average teams
gives e^ĥ = b/(2−b) (the data's home/away ratio) and a forecast total of 2g. No deflate-then-divide step exists. The
fit reports both residuals (I1 home, I2 away) so a test and the harness print them.

THE FIRST SEASON OF A COMPETITION IN THE WINDOW (no S−1 visible; a ruling, open question 3): α and δ penalised toward
0 with τ = K_PRIOR·G0; μ and h get a weak prior centred at μ0 = ln(G0·(2−B0)) and h0 = ln(B0/(2−B0)) (G0, B0 the
defaults of CompetitionScoringContext() converted coherently: away mean g·(2−b), home/away ratio b/(2−b); NOT b reused
as a ratio, which is 216 item 1's own mismatch), precision τ_μ = K_PRIOR·G0. There the identity is a pull, pinned as
Σ(y − λ) = τ_μ·(μ − μ0) for μ and Σ(y_H − λ_H) = τ_μ·(h − h0) for h.

THE FIT: damped Newton from a COLD start (θ = 0, μ = ln of the window's mean goals per observation, or μ0 when the
window holds no goal-bearing row), never warm-started from another fit; the Hessian is checked positive definite by
Cholesky, then np.linalg.solve; up to MAX_HALVINGS step halvings (the full step accepted when the objective does not
increase, a damped one only when it strictly decreases); converged when the FULL Newton step max|H⁻¹g| < TOL, never on
a damped displacement (Codex on #832, round 1); a line search that cannot lower the objective while the decrease is
resolvable (its Newton decrement above PRECISION_FLOOR·|objective|) refuses ("the line search stalled"), one below it
takes the full step; MAX_ITER iterations (_newton). Any failure raises
FitRefused, which refuses the run: there is no fallback.
β is fixed at 0 and labelled `beta_unidentified` when the window's ΔE takes fewer than two distinct values (one value
cannot be told from μ and h; all zero leaves the column empty).

NO TIME DECAY: every row weighs 1 (this is not S19 reopened; time decay stays rejected). NO DIXON–COLES FIT: ρ is not
estimated here; pricing applies v22's stored ρ to the fitted λ (soccer_v23.price). At a fixed ρ the DC cell factors
leave E[X] and E[Y] unchanged (p10·λ_A·ρ − p11·ρ = 0 for X; alike for Y), so fitting λ under independent Poisson and
applying DC only at pricing is coherent.

THE CONSTANTS (proposed, every one an open question for the declaration, never fitted to the pot): K_PRIOR 5.0
(poisson.py's own n/(n+5), reused), the promoted prior ln 0.85 / ln 1.15 (v22's PoissonConfig promoted priors, read
as log offsets on S−1's zero mean), the relegated prior 0 / 0 (no directional prior), CARRY 1.0 (no extra
regression), G0 1.4 and B0 1.15 (CompetitionScoringContext()'s defaults), β's prior 0 with precision K_PRIOR·G0 (the
first season's μ/h precision reused; chosen before any probe, never tuned). The declaration freezes them; the harness refuses a run whose entry differs (soccer_v23.constants_state).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

K_PRIOR = 5.0
G0 = 1.4
B0 = 1.15
PROMOTED_ATTACK_MULT = 0.85
PROMOTED_DEFENCE_MULT = 1.15
PROMOTED_ATTACK = math.log(PROMOTED_ATTACK_MULT)
PROMOTED_DEFENCE = math.log(PROMOTED_DEFENCE_MULT)
#: A club arriving from a HIGHER tier (relegated into the competition): no directional prior, S−1's zero mean.
RELEGATED_ATTACK = 0.0
RELEGATED_DEFENCE = 0.0
CARRY = 1.0
ELO_SCALE = 100.0
#: β's weak Gaussian prior (every window, one rule: no count switch), on the fit's own column ΔE/ELO_SCALE: centred at
#: 0 (no Elo increment) with K_PRIOR·G0 of precision, the first season's μ/h precision reused (no new number). Without
#: it, β overfits a competition's first few rows, whose small ΔE values come from the same results (the 2026-11-04
#: review's probe), and the walk prices later fixtures as near-certainties. In a full window the likelihood's
#: information on β (about Σλ·(ΔE/ELO_SCALE)²) dwarfs it.
BETA_PRIOR_MEAN = 0.0
BETA_PRIOR_PRECISION = K_PRIOR * G0
MAX_ITER = 100
MAX_HALVINGS = 60
TOL = 1e-12
#: THE OBJECTIVE'S RESOLUTION (relative; Codex on #832, round 1): when no step of the line search lowers the objective,
#: a Newton decrement ½·gᵀH⁻¹g at or below PRECISION_FLOOR·max(1, |objective|) is under what the objective's float
#: evaluation resolves (a sum of 2n terms carries about n·ε of relative rounding; ε 2.2e-16), so the full step is
#: taken and the loop goes on; above it the fit refuses. It never declares convergence: only max|H⁻¹g| < TOL does.
PRECISION_FLOOR = 1e-12

MU0 = math.log(G0 * (2.0 - B0))
H0 = math.log(B0 / (2.0 - B0))

PREV, CUR = "prev", "cur"


class FitRefused(RuntimeError):
    """The fit did not converge, the Hessian was not positive definite, or the window cannot identify the model. The
    harness refuses the run on it: there is no fallback to another model."""


@dataclass(frozen=True)
class Obs:
    """One finished row of the window: teams, the season slot (PREV or CUR), the goals, the row's own pre-kickoff Elo
    difference (home − away, rating points)."""
    home: int
    away: int
    slot: str
    home_goals: float
    away_goals: float
    elo_diff: float


@dataclass
class JointFit:
    mu: float
    h: float
    beta: float                                     # per rating point
    prev: dict = field(default_factory=dict)        # team -> (alpha, delta), S−1
    cur: dict = field(default_factory=dict)         # team -> (alpha, delta), S (teams with S rows in the window)
    first_season: bool = False
    relegated: frozenset = frozenset()              # teams the caller named as arriving from a higher tier
    tau: float = 0.0
    tau_mu: float = 0.0
    labels: tuple = ()
    iterations: int = 0
    last_step: float = 0.0
    n_obs: int = 0
    resid_home: float = 0.0                         # I1: Σ(y_H − λ̂_H)
    resid_away: float = 0.0                         # I2: Σ(y_A − λ̂_A)

    def strength(self, team: int) -> tuple[float, float, str]:
        """(alpha, delta, source) of `team` in season S. A team with S rows reads its fitted S parameters; a team with
        none reads the optimum of its only term, the penalty: CARRY × its S−1 parameters (seen in S−1), the relegated
        prior (not seen, named relegated), the promoted prior (not seen, S−1 exists), or 0 (the first season). Each is
        the exact optimum, not an approximation."""
        if team in self.cur:
            a, d = self.cur[team]
            return a, d, "fit"
        if team in self.prev:
            a, d = self.prev[team]
            return CARRY * a, CARRY * d, "carried"
        if self.first_season:
            return 0.0, 0.0, "first-season prior"
        if team in self.relegated:
            return RELEGATED_ATTACK, RELEGATED_DEFENCE, "relegated prior"
        return PROMOTED_ATTACK, PROMOTED_DEFENCE, "promoted prior"


def rates(fit: JointFit, home: int, away: int, elo_diff: float) -> tuple[float, float]:
    """(λ_H, λ_A) for a fixture in season S: the model's two equations with the fixture's own ΔE."""
    ah, dh, _ = fit.strength(home)
    aa, da, _ = fit.strength(away)
    x = fit.beta * elo_diff
    return math.exp(fit.mu + fit.h + ah + da + x), math.exp(fit.mu + aa + dh - x)


def _newton(objective, derivs, th: np.ndarray) -> tuple[np.ndarray, int, float]:
    """THE DAMPED NEWTON LOOP (pure; `objective(θ)` -> float, `derivs(θ)` -> (gradient, Hessian)). Returns (θ, the
    iterations, the last FULL Newton step max|H⁻¹g|).

    CONVERGENCE IS ON THE FULL NEWTON STEP ONLY: converged when max|H⁻¹g| < TOL at the current θ, never on the
    displacement a damped step made (Codex on #832, round 1: a line search halved until rounding makes the objective
    tie can move θ by less than TOL while the full step and the gradient stay large). The line search accepts the
    full step when it does not raise the objective, and a damped step only when it STRICTLY lowers it. When no step
    does (MAX_HALVINGS halvings), the Newton decrement ½·gᵀH⁻¹g (the decrease the full step predicts) decides:
      * at or below PRECISION_FLOOR·max(1, |objective|), the objective's float evaluation cannot resolve the decrease
        (the line search is blind there, not failed): the full Newton step is taken unchecked and the loop goes on;
        convergence is still only max|H⁻¹g| < TOL at a later iteration (pure Newton is quadratic that close);
      * above it (or not positive: the step is no descent direction), the fit is REFUSED, "the line search stalled":
        a damped tie is never read as convergence.
    MAX_ITER iterations without convergence refuse too."""
    obj = objective(th)
    it, full = 0, float("inf")
    while it < MAX_ITER:
        it += 1
        g, H = derivs(th)
        try:
            np.linalg.cholesky(H)
        except np.linalg.LinAlgError:
            raise FitRefused("the Hessian is not positive definite: the window does not identify the model")
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            raise FitRefused("the Hessian is singular: the window does not identify the model")
        if not np.all(np.isfinite(step)):
            raise FitRefused("a non-finite Newton step: the window does not identify the model")
        full = float(np.max(np.abs(step))) if step.size else 0.0
        if full < TOL:
            return th, it, full
        t_ = 1.0
        for _ in range(MAX_HALVINGS + 1):
            cand = th - t_ * step
            oc = objective(cand)
            if math.isfinite(oc) and (oc < obj or (oc == obj and t_ == 1.0)):
                break
            t_ /= 2.0
        else:
            dec = 0.5 * float(g @ step)
            if not (0.0 < dec <= PRECISION_FLOOR * max(1.0, abs(obj))):
                gmax = float(np.max(np.abs(g))) if g.size else 0.0
                raise FitRefused(f"the line search stalled: no step lowers the objective after {MAX_HALVINGS} halvings "
                                 f"while the full Newton step is max|Δθ| {full:.3e} (TOL {TOL:.0e}), max|gradient| "
                                 f"{gmax:.3e} and the Newton decrement {dec:.3e} is resolvable (PRECISION_FLOOR "
                                 f"{PRECISION_FLOOR:.0e} x |objective| {abs(obj):.3e}): not converged, never accepted")
            cand = th - step                                  # below the objective's resolution: pure Newton
            oc = objective(cand)
            if not math.isfinite(oc):
                raise FitRefused("a non-finite objective at the full Newton step: the window does not identify the "
                                 "model")
        th, obj = cand, oc
    raise FitRefused(f"no convergence in {MAX_ITER} iterations (last full max|Δθ| {full:.3e})")


def fit(obs: list[Obs] | tuple, relegated=frozenset()) -> JointFit:
    """The penalised joint fit over one window (see the module docstring). `obs` in the caller's order (the walk's
    kickoff order); `relegated`: the teams the caller names as arriving from a higher tier (read only for a team absent
    from the S−1 rows; every other absent team is promoted). The result depends only on its inputs, deterministically."""
    obs = list(obs)
    relegated = frozenset(relegated)
    for o in obs:
        if o.slot not in (PREV, CUR):
            raise FitRefused(f"row slot {o.slot!r} is neither {PREV!r} nor {CUR!r}")
        for v in (o.home_goals, o.away_goals, o.elo_diff):
            if not math.isfinite(v):
                raise FitRefused("a non-finite value in the window")
        if o.home_goals < 0 or o.away_goals < 0:
            raise FitRefused("a negative goal count in the window")
    prev_rows = [o for o in obs if o.slot == PREV]
    first = not prev_rows
    tprev = sorted({t for o in prev_rows for t in (o.home, o.away)})
    tcur = sorted({t for o in obs if o.slot == CUR for t in (o.home, o.away)})
    labels: list[str] = []
    if first:
        tau = K_PRIOR * G0
        tau_mu = tau
        labels.append("first season: weak mu/h prior (open question 3)")
    else:
        lam_bar = sum(o.home_goals + o.away_goals for o in prev_rows) / (2.0 * len(prev_rows))
        if lam_bar <= 0:
            raise FitRefused("the S−1 window holds no goal: the rates cannot be identified")
        tau = K_PRIOR * lam_bar
        tau_mu = 0.0
    beta_free = len({o.elo_diff for o in obs}) >= 2     # one ΔE value (or none) cannot separate β from μ and h
    if not beta_free:
        labels.append("beta_unidentified")
    if not first and len(tprev) < 2:
        raise FitRefused("the S−1 window names fewer than two teams")

    # the full parameter vector φ: [μ, h, β, α_prev..., δ_prev..., α_cur..., δ_cur...]
    np_, nc = len(tprev), len(tcur)
    i_ap = {t: 3 + j for j, t in enumerate(tprev)}
    i_dp = {t: 3 + np_ + j for j, t in enumerate(tprev)}
    i_ac = {t: 3 + 2 * np_ + j for j, t in enumerate(tcur)}
    i_dc = {t: 3 + 2 * np_ + nc + j for j, t in enumerate(tcur)}
    P = 3 + 2 * np_ + 2 * nc

    # θ → φ: drop β when unidentified; substitute the dependent S−1 team (the last in sorted order) by sum-to-zero
    free = [0, 1] + ([2] if beta_free else [])
    dep = set()
    if np_:
        dep = {i_ap[tprev[-1]], i_dp[tprev[-1]]}
    free += [i for i in range(3, P) if i not in dep]
    col = {p: j for j, p in enumerate(free)}
    A = np.zeros((P, len(free)))
    for p, j in col.items():
        A[p, j] = 1.0
    if np_:
        for idx in (i_ap, i_dp):
            last = idx[tprev[-1]]
            for t in tprev[:-1]:
                A[last, col[idx[t]]] = -1.0

    # observations: two per row
    n = len(obs)
    X = np.zeros((2 * n, P))
    y = np.zeros(2 * n)
    for r, o in enumerate(obs):
        ia = i_ap if o.slot == PREV else i_ac
        idf = i_dp if o.slot == PREV else i_dc
        e = o.elo_diff / ELO_SCALE
        X[2 * r, 0] = 1.0
        X[2 * r, 1] = 1.0
        X[2 * r, 2] = e
        X[2 * r, ia[o.home]] += 1.0
        X[2 * r, idf[o.away]] += 1.0
        y[2 * r] = o.home_goals
        X[2 * r + 1, 0] = 1.0
        X[2 * r + 1, 2] = -e
        X[2 * r + 1, ia[o.away]] += 1.0
        X[2 * r + 1, idf[o.home]] += 1.0
        y[2 * r + 1] = o.away_goals

    # penalty rows
    D_rows, d, w = [], [], []

    def pen(coefs: dict, target: float, weight: float) -> None:
        row = np.zeros(P)
        for p, c in coefs.items():
            row[p] += c
        D_rows.append(row)
        d.append(target)
        w.append(weight)

    for t in tprev:
        pen({i_ap[t]: 1.0}, 0.0, tau)
        pen({i_dp[t]: 1.0}, 0.0, tau)
    for t in tcur:
        if first:
            pen({i_ac[t]: 1.0}, 0.0, tau)
            pen({i_dc[t]: 1.0}, 0.0, tau)
        elif t in i_ap:
            pen({i_ac[t]: 1.0, i_ap[t]: -CARRY}, 0.0, tau)
            pen({i_dc[t]: 1.0, i_dp[t]: -CARRY}, 0.0, tau)
        elif t in relegated:
            pen({i_ac[t]: 1.0}, RELEGATED_ATTACK, tau)
            pen({i_dc[t]: 1.0}, RELEGATED_DEFENCE, tau)
        else:
            pen({i_ac[t]: 1.0}, PROMOTED_ATTACK, tau)
            pen({i_dc[t]: 1.0}, PROMOTED_DEFENCE, tau)
    if first:
        pen({0: 1.0}, MU0, tau_mu)
        pen({1: 1.0}, H0, tau_mu)
    if beta_free:
        pen({2: 1.0}, BETA_PRIOR_MEAN * ELO_SCALE, BETA_PRIOR_PRECISION)
    D = np.array(D_rows) if D_rows else np.zeros((0, P))
    dv, wv = np.array(d), np.array(w)

    Xt = X @ A
    Dt = D @ A

    def objective(th: np.ndarray) -> float:
        eta = Xt @ th
        r_ = Dt @ th - dv
        return float(np.sum(np.exp(eta) - y * eta) + 0.5 * np.sum(wv * r_ * r_))

    def derivs(th: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        lam = np.exp(Xt @ th)
        g = Xt.T @ (lam - y) + Dt.T @ (wv * (Dt @ th - dv))
        H = (Xt * lam[:, None]).T @ Xt + (Dt * wv[:, None]).T @ Dt
        return g, H

    th = np.zeros(len(free))
    ybar = float(y.mean()) if len(y) else 0.0
    th[0] = math.log(ybar) if ybar > 0 else MU0
    th, it, last = _newton(objective, derivs, th)

    phi = A @ th
    lam = np.exp(Xt @ th)
    res = y - lam
    out = JointFit(mu=float(phi[0]), h=float(phi[1]), beta=float(phi[2]) / ELO_SCALE,
                   prev={t: (float(phi[i_ap[t]]), float(phi[i_dp[t]])) for t in tprev},
                   cur={t: (float(phi[i_ac[t]]), float(phi[i_dc[t]])) for t in tcur},
                   first_season=first, relegated=relegated if not first else frozenset(), tau=tau, tau_mu=tau_mu, labels=tuple(labels), iterations=it,
                   last_step=last, n_obs=n,
                   resid_home=float(np.sum(res[0::2])), resid_away=float(np.sum(res[1::2])))
    return out
