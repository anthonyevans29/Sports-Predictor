"""
SOCCER-CANDIDATES lane (architect 2026-10-01) — BACKTEST ONLY, verdicts only,
no production change. Two candidates, each through the EXISTING soccer gate
(training.improve's rule: pooled leakage-free 1X2 log-loss delta >= the
promotion delta, ties reject), on the pre-declared set PL 2023/24, 2024/25,
2025/26 pooled, production poisson params, RPS reported only.

EVERY CONSTANT AND PROCEDURE BELOW IS DECLARED BEFORE ANY RUN (law 3).

(a) DIXON-COLES LOW-SCORE CORRECTION, rho FITTED ON 2023/24 ONLY, FROZEN.
    Production already carries a Dixon-Coles rho (its stored poisson config;
    S18 shipped rho = -0.10). This candidate replaces that value with a rho
    fitted by maximum likelihood on PL 2023/24 alone:
      * the leakage-free walk (production params, min_prior 40) gives each
        scored 2023/24 match its expected goals (lambda, mu); rho does not
        enter lambda/mu, so they are fixed inputs;
      * the Dixon-Coles likelihood of the observed scores reduces to
        sum log tau(x, y; lambda, mu, rho) (the tau-adjusted matrix still sums
        to 1 exactly), with tau = 1 - lambda*mu*rho (0-0), 1 + mu*rho (1-0),
        1 + lambda*rho (0-1), 1 - rho (1-1), 1 otherwise;
      * rho = argmax over the grid [-0.300, +0.200] step 0.001; a grid point
        that makes any tau <= 0 is infeasible; ties go to the smallest |rho|.
    The fitted rho is printed and frozen for the evaluation. NOTE (owned): the
    ruled evaluation set includes 2023/24, the fit season, so 1/3 of the pooled
    set is in-sample; the out-of-sample pool (2024/25 + 2025/26) is REPORTED
    beside it and decides nothing (ARCHITECT-RULE if it should).

(b) S14 STAGE-2 — UNCERTAINTY-CONDITIONED TOTALS ADJUSTMENT.
    Bucket: the UNADJUSTED prediction's top-pick probability < 0.45 (the S14
    "uncertain-winner" bucket). Offset: +1.17 goals on the expected total —
    declared from the S14 verdict's measured under-projection (+1.17, n=25,
    2026-09-16), not from Stage-1's in-sample +1.0 selection. Mechanism: both
    expected-goal rates scale by (T + 1.17) / T, T = home_xg + away_xg, and
    the full score matrix (Dixon-Coles included) is recomputed — so 1X2 moves
    too (fewer draws) and the improve rule has something to judge.
    Verdict = the improve rule AND the S14 Stage-2 acceptance FROZEN
    2026-09-17 (BACKLOG "S14 STAGE-1 COMPLETE"), all on the pooled set:
      (i)   the uncertain-bucket signed total residual (actual − projected)
            moves toward zero: |cand| < |prod| (a tie rejects);
      (ii)  overall totals-direction at the 2.5 line does not degrade:
            cand hits >= prod hits (direction = p_over > 0.5 vs actual >= 3);
      (iii) the confident-bucket residual stays within ±0.15 of production.
    Requiring both is the binding reading (gates more binding, never less);
    ARCHITECT-RULE if only the improve rule was meant.
"""
from __future__ import annotations

from src.walters.soccer_backtest import compare_candidate, run_soccer_backtest

GATE_COMPETITION = "PL"
GATE_SEASONS = ("2023/24", "2024/25", "2025/26")

DC_FIT_SEASON = "2023/24"
DC_RHO_LO, DC_RHO_HI, DC_RHO_STEP = -0.300, 0.200, 0.001
OOS_SEASONS = ("2024/25", "2025/26")         # reported beside the ruled pool; decides nothing

S14_UNCERTAIN_TOP_PICK = 0.45
S14_OFFSET_GOALS = 1.17
S14_CONFIDENT_TOL = 0.15
S14_TOTAL_LINE_GOALS = 3                      # "over 2.5" = 3+ goals

DC_CANDIDATE = "dixon-coles-fit"
S14_CANDIDATE = "s14-totals"


# ------------------------------------------------------------------ (a) --

def tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def rho_grid() -> list[float]:
    n = int(round((DC_RHO_HI - DC_RHO_LO) / DC_RHO_STEP))
    return [round(DC_RHO_LO + i * DC_RHO_STEP, 3) for i in range(n + 1)]


def dc_loglik(rows: list[dict], rho: float) -> float | None:
    """sum log tau over the observed scores; None if any tau <= 0 (infeasible)."""
    import math
    ll = 0.0
    for r in rows:
        t = tau(r["home_score"], r["away_score"], r["home_xg"], r["away_xg"], rho)
        if t <= 0:
            return None
        ll += math.log(t)
    return ll


def fit_rho(rows: list[dict]) -> dict:
    """The frozen procedure: grid argmax of the DC likelihood; ties -> smallest |rho|."""
    best = None
    for rho in rho_grid():
        ll = dc_loglik(rows, rho)
        if ll is None:
            continue
        key = (ll, -abs(rho))
        if best is None or key > best[0]:
            best = (key, rho, ll)
    if best is None:
        return {"rho": None, "n": len(rows), "loglik": None}
    return {"rho": best[1], "n": len(rows), "loglik": best[2],
            "loglik_at_zero": dc_loglik(rows, 0.0)}


def run_dixon_coles_candidate(*, prod_rho: float, elo_goal_coeff: float, min_prior: int = 40,
                              min_delta: float | None = None) -> dict:
    """Fit rho on 2023/24 (production params, rho-free lambdas), freeze it,
    then gate it against production's rho on the pooled ruled set."""
    if min_delta is None:
        from src.walters.training import DEFAULT_PROMOTION_DELTA
        min_delta = DEFAULT_PROMOTION_DELTA
    fit_rows = run_soccer_backtest(GATE_COMPETITION, DC_FIT_SEASON, min_prior,
                                   dixon_coles_rho=prod_rho, elo_goal_coeff=elo_goal_coeff,
                                   detail=True)
    if not fit_rows:
        return {"verdict": "INVALID", "reason": f"fit season {DC_FIT_SEASON} not found / nothing scored"}
    fit = fit_rho(fit_rows)
    if fit["rho"] is None:
        return {"verdict": "INVALID", "reason": "no feasible rho on the grid", "fit": fit}
    out = _pooled(lambda season: (
        run_soccer_backtest(GATE_COMPETITION, season, min_prior,
                            dixon_coles_rho=prod_rho, elo_goal_coeff=elo_goal_coeff),
        run_soccer_backtest(GATE_COMPETITION, season, min_prior,
                            dixon_coles_rho=fit["rho"], elo_goal_coeff=elo_goal_coeff)),
        min_delta)
    out["fit"] = fit
    out["prod_rho"] = prod_rho
    oos_b = [r for x in out["_arms"] if x[0] in OOS_SEASONS for r in x[1]]
    oos_c = [r for x in out["_arms"] if x[0] in OOS_SEASONS for r in x[2]]
    out["oos_pooled"] = compare_candidate(oos_b, oos_c, min_delta)     # REPORTED ONLY
    out.pop("_arms")
    return out


# ------------------------------------------------------------------ (b) --

def s14_criteria(base: list[dict], cand: list[dict]) -> dict:
    """The S14 Stage-2 acceptance (frozen 2026-09-17) on paired detail rows.
    Buckets come from the PRODUCTION arm's top pick (identical membership)."""
    by_c = {r["match_id"]: r for r in cand}
    unc_b, unc_c, conf_b, conf_c = [], [], [], []
    hits_b = hits_c = 0
    for b in base:
        c = by_c[b["match_id"]]
        actual = b["home_score"] + b["away_score"]
        rb, rc = actual - (b["home_xg"] + b["away_xg"]), actual - (c["home_xg"] + c["away_xg"])
        top = max(b["p_home"], b["p_draw"], b["p_away"])
        (unc_b if top < S14_UNCERTAIN_TOP_PICK else conf_b).append(rb)
        (unc_c if top < S14_UNCERTAIN_TOP_PICK else conf_c).append(rc)
        over = actual >= S14_TOTAL_LINE_GOALS
        hits_b += (b["p_over"] > 0.5) == over
        hits_c += (c["p_over"] > 0.5) == over
    mean = lambda v: sum(v) / len(v) if v else None
    ub, uc, cb, cc = mean(unc_b), mean(unc_c), mean(conf_b), mean(conf_c)
    i = ub is not None and uc is not None and abs(uc) < abs(ub)
    ii = hits_c >= hits_b
    iii = cb is None or (cc is not None and abs(cc - cb) <= S14_CONFIDENT_TOL)
    return {"n_uncertain": len(unc_b), "n_confident": len(conf_b),
            "uncertain_residual": (ub, uc), "confident_residual": (cb, cc),
            "direction_hits": (hits_b, hits_c), "n": len(base),
            "i_toward_zero": i, "ii_direction_not_worse": ii, "iii_confident_within_tol": iii,
            "pass": bool(i and ii and iii)}


def run_s14_candidate(*, prod_rho: float, elo_goal_coeff: float, min_prior: int = 40,
                      min_delta: float | None = None) -> dict:
    if min_delta is None:
        from src.walters.training import DEFAULT_PROMOTION_DELTA
        min_delta = DEFAULT_PROMOTION_DELTA
    kw = dict(dixon_coles_rho=prod_rho, elo_goal_coeff=elo_goal_coeff, detail=True)
    out = _pooled(lambda season: (
        run_soccer_backtest(GATE_COMPETITION, season, min_prior, **kw),
        run_soccer_backtest(GATE_COMPETITION, season, min_prior,
                            s14_uncertain_offset=S14_OFFSET_GOALS, **kw)),
        min_delta)
    base_all = [r for x in out["_arms"] for r in x[1]]
    cand_all = [r for x in out["_arms"] for r in x[2]]
    out.pop("_arms")
    if out["pooled"]["verdict"] == "INVALID":
        out["s14"] = None
        out["verdict"] = "INVALID"
        return out
    out["s14"] = s14_criteria(base_all, cand_all)
    out["verdict"] = "PASS" if (out["pooled"]["verdict"] == "PASS" and out["s14"]["pass"]) else "REJECT"
    return out


# ---------------------------------------------------------------- shared --

def _pooled(arms_for_season, min_delta: float) -> dict:
    per, arms, missing, base_all, cand_all = [], [], [], [], []
    for season in GATE_SEASONS:
        base, cand = arms_for_season(season)
        if not base or not cand:
            missing.append(season)
            per.append({"season": season, "verdict": "MISSING", "n": 0})
            continue
        row = compare_candidate(base, cand, min_delta)
        row["season"] = season
        per.append(row)
        arms.append((season, base, cand))
        base_all.extend(base)
        cand_all.extend(cand)
    pooled = compare_candidate(base_all, cand_all, min_delta)
    if missing:
        pooled = {**pooled, "verdict": "INVALID",
                  "reason": f"season(s) not found / nothing scored: {', '.join(missing)}"}
    return {"competition": GATE_COMPETITION, "seasons": list(GATE_SEASONS), "per_season": per,
            "pooled": pooled, "missing": missing, "_arms": arms,
            "verdict": pooled["verdict"]}
