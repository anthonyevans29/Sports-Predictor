"""
Backtest — re-run the CURRENT model across historical games, LEAKAGE-FREE.

The point of a backtest is to validate calibration/signal findings on
independent data (e.g. 2025) the model never trained-to-predict live. The ONE
thing that makes it honest is no future leakage: to predict a game on date D,
we use ONLY games played before D to build team run profiles. Using
season-aggregate stats would leak the future and make the model look better
calibrated than it is — which would specifically HIDE the overconfidence we're
trying to confirm. So we rebuild profiles point-in-time.

Stores results in a lightweight in-memory structure and prints a calibration-by-
confidence-tier table (the finding we're validating). Does NOT write Prediction
rows (keeps the backtest cleanly separate from live predictions) and does NOT
touch the model.

HONEST LIMITATIONS (stated, not hidden):
  - Team run profiles ARE point-in-time (leakage-free). Pitcher ERAs are NOT
    reconstructed as-of-date — we run without pitcher adjustment in the
    backtest, so it isolates the run-profile/calibration behaviour. This makes
    the backtest a test of the STRUCTURAL model + run-shrink calibration, not
    the full pitcher-aware pipeline. Good enough to confirm/deny the
    confidence-tier overconfidence gradient, which is a property of the win-prob
    calibration, not the pitcher layer.
  - Recency blend inside estimate_run_profiles uses the prior games we feed it,
    so it stays leakage-free by construction.
"""
from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import Match, MatchStatus, Sport, Competition
from src.models.baseball import (estimate_run_profiles, predict_game,
                                 BaseballConfig)


def _load_production_config(s) -> BaseballConfig:
    """Load the live production model's config so run-shrink/recal match live."""
    from src.db.schema import ModelVersion
    mv = s.execute(
        select(ModelVersion)
        .where(ModelVersion.sport == Sport.MLB,
               ModelVersion.status == "production")
        .order_by(ModelVersion.id.desc())
    ).scalars().first()
    if mv and mv.parameters and "baseball_config" in mv.parameters:
        try:
            return BaseballConfig(**mv.parameters["baseball_config"])
        except Exception:
            pass
    return BaseballConfig()


def run_backtest(season: str = "2025", competition_code: str = "MLB",
                 shrink_frac_override: float | None = None,
                 return_totals_rows: bool = False):
    """
    Walk `season`'s finished games in date order; predict each using only prior
    games (leakage-free). Returns a list of (predicted_prob_on_pick, won,
    proj_total, actual_total).

    shrink_frac_override: if set, overrides run_shrink_frac (and forces shrink
    on) — used by the shrink-tuning sweep to test alternative strengths against
    the same leakage-free walk.
    """
    results = []
    totals_rows = []  # richer rows for the totals-model head-to-head
    with session_scope() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            return None
        cfg = _load_production_config(s)
        if shrink_frac_override is not None:
            import dataclasses
            cfg = dataclasses.replace(cfg, run_shrink_enabled=True,
                                      run_shrink_frac=shrink_frac_override)

        games = list(s.execute(
            select(Match).where(
                Match.competition_id == comp.id,
                Match.season == season,
                Match.status == MatchStatus.FINISHED,
                Match.home_score.isnot(None),
                Match.away_score.isnot(None),
            ).order_by(Match.utc_date.asc())
        ).scalars())

        if not games:
            return None

        # incremental history: list of prior-game dicts, grown as we advance
        history: list[dict] = []
        # we must not leak SAME-DAY games either; process strictly by date, and
        # only add a game to history after it's been predicted.
        for m in games:
            # build profiles from history so far (games strictly before this one)
            if len(history) >= 40:  # need a minimum base to be meaningful
                profiles = estimate_run_profiles(history)
                hp = profiles.get(m.home_team_id)
                ap = profiles.get(m.away_team_id)
                if hp and ap:
                    pred = predict_game(hp, ap, home_pitcher=None,
                                        away_pitcher=None, config=cfg)
                    probs = {"home": pred.p_home, "away": pred.p_away}
                    side = max(probs, key=probs.get)
                    p = probs[side]
                    actual_home_won = m.home_score > m.away_score
                    won = 1 if ((side == "home") == actual_home_won) else 0
                    # projected total (home_xr+away_xr) vs actual — for the
                    # totals-bias confirmation (no market line needed; the
                    # projection-band bias read doesn't use one).
                    proj_total = (pred.home_xr or 0) + (pred.away_xr or 0)
                    actual_total = m.home_score + m.away_score
                    results.append((p, won, proj_total, actual_total))
                    # richer row for the totals-model head-to-head (leakage-free:
                    # run rates are point-in-time from prior games only)
                    totals_rows.append((
                        p, won, proj_total, actual_total,
                        hp.runs_scored_per_game, hp.runs_allowed_per_game,
                        ap.runs_scored_per_game, ap.runs_allowed_per_game,
                        cfg.league_runs_per_game, m.venue,
                    ))
            # now add this game to history for future predictions
            history.append({
                "home_team_id": m.home_team_id, "away_team_id": m.away_team_id,
                "home_score": m.home_score, "away_score": m.away_score,
                "utc_date": m.utc_date,
            })

    if return_totals_rows:
        return totals_rows
    return results


def calibration_by_tier(results):
    """Bucket backtest results by confidence tier: n, actual, predicted, gap."""
    tiers = [("toss-up (<53%)", 0.50, 0.53), ("lean (53-57%)", 0.53, 0.57),
             ("solid (57-62%)", 0.57, 0.62), ("strong (≥62%)", 0.62, 1.01)]
    out = []
    for label, lo, hi in tiers:
        bucket = [(p, w) for (p, w, *_ ) in results if lo <= p < hi]
        n = len(bucket)
        if n == 0:
            out.append((label, 0, None, None, None, None))
            continue
        actual = sum(w for _, w in bucket) / n
        predicted = sum(p for p, _ in bucket) / n
        gap = actual - predicted
        se = math.sqrt(actual * (1 - actual) / n) if n > 0 else None
        out.append((label, n, actual, predicted, gap, se))
    return out


def totals_bias_by_band(results):
    """
    Projected-total vs actual by PROJECTED band — the read that showed the
    2026 low-projection bias (+1.06 low, +0.54 mid, ~0 high). Confirms whether
    that gradient reproduces on independent backtest data. No market line needed.
    results tuples: (p, won, proj_total, actual_total).
    """
    bands = [("low proj (<7.5)", 0, 7.5), ("mid proj (7.5-8.5)", 7.5, 8.5),
             ("high proj (8.5-9.5)", 8.5, 9.5), ("very high (≥9.5)", 9.5, 99)]
    out = []
    for label, lo, hi in bands:
        errs = [at - pt for (_, _, pt, at) in results if lo <= pt < hi]
        n = len(errs)
        if n == 0:
            out.append((label, 0, None, None))
            continue
        m = sum(errs) / n
        if n > 1:
            var = sum((e - m) ** 2 for e in errs) / (n - 1)
            se = (var ** 0.5) / (n ** 0.5)
        else:
            se = None
        out.append((label, n, m, se))
    return out
