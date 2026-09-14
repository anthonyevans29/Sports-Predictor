"""
Totals model (Step 1 scaffold) — projects TOTAL runs directly, as an explicit
alternative to the current model's byproduct total (home_xr + away_xr from the
win-probability model).

Rationale: the production model optimizes for WIN PROBABILITY; its total is a
side effect. A totals-specific projection can optimize the SUM directly and use
inputs that matter for scoring level but not for who wins — starting with the
PARK FACTOR (run-scoring multiplier), which the side model doesn't apply to the
run level.

This is Step 1 ONLY: a minimal, interpretable baseline (team run rates + park
factor + league environment). It must BEAT the current byproduct total on
leakage-free out-of-sample MAE/bias before we add anything fancier. If it can't
clear that bar on the basics, we learn it cheaply and stop. No weather/bullpen/
umpire yet — those come in Step 2, and only if they pass a totals-specific
Stage-1 test (do they predict TOTAL-runs residuals), earning a slot one at a time.

Honest notes:
  - "Beats the incumbent total" = lower MAE and/or less bias on held-out games.
  - A better total number is NOT automatically a totals-market edge (separate CLV
    question). Totals markets are softer, which is why this is worth trying.
  - Leakage-free: projections use only prior-game run rates, same as the backtest.
"""
from __future__ import annotations

from src.models.park_factors import get_park_factor


def project_total(
    home_rs: float, home_ra: float,
    away_rs: float, away_ra: float,
    league_rpg: float,
    venue: str | None = None,
    park_weight: float = 1.0,
) -> float:
    """
    Project total runs for a game directly.

    home_rs/ra, away_rs/ra: teams' runs scored / allowed per game (point-in-time).
    league_rpg: league total runs per game (both teams), e.g. ~8.9.
    venue: for park factor.
    park_weight: 0..1 dial on how strongly park factor applies (1 = full).

    Method: each team's expected runs = its offense vs opponent's defense,
    normalized to league; sum the two; scale by park factor. This differs from
    the side model in that it (a) targets the sum, and (b) applies the park
    run-multiplier to the total, which the side model does not do at run level.
    """
    lg_per_team = league_rpg / 2.0
    if lg_per_team <= 0:
        lg_per_team = 4.45

    # expected runs: offense * opponent defense / league (Pythag-style run est)
    home_xr = (home_rs * away_ra) / lg_per_team
    away_xr = (away_rs * home_ra) / lg_per_team
    total = home_xr + away_xr

    # park factor: dampened by park_weight so we can tune how hard it applies
    pf = get_park_factor(venue)
    pf_effective = 1.0 + (pf - 1.0) * park_weight
    total *= pf_effective

    return total


def compare_totals_models(results):
    """
    Compare the incumbent byproduct total vs the Step-1 totals model on the same
    leakage-free backtest games.

    `results` is the backtest output extended to carry, per game:
      (p, won, incumbent_total, actual_total, home_rs, home_ra, away_rs, away_ra,
       league_rpg, venue)

    Returns {incumbent: {...}, totals_model: {...}} each with mae, mean_err, n,
    plus the park_weight used.
    """
    import math

    def _stats(errs):
        n = len(errs)
        if n == 0:
            return {"n": 0, "mae": None, "mean_err": None, "se": None}
        mae = sum(abs(e) for e in errs) / n
        me = sum(errs) / n
        sd = (sum((e - me) ** 2 for e in errs) / (n - 1)) ** 0.5 if n > 1 else None
        se = (sd / math.sqrt(n)) if sd else None
        return {"n": n, "mae": mae, "mean_err": me, "se": se}

    inc_err, mdl_err = [], []
    for row in results:
        (_, _, inc_total, actual_total, hrs, hra, ars, ara, lg, venue) = row
        if actual_total is None or inc_total is None:
            continue
        inc_err.append(actual_total - inc_total)
        mdl_total = project_total(hrs, hra, ars, ara, lg, venue)
        mdl_err.append(actual_total - mdl_total)

    return {"incumbent": _stats(inc_err), "totals_model": _stats(mdl_err)}
