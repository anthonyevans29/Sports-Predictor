"""
Leakage-free soccer backtest — the disciplined equivalent of the MLB backtest.

The existing holdout eval (_score_model_on_holdout_soccer) LEAKS: it computes
team strengths from ALL finished matches in the season (including the match being
predicted and everything after it) and loads Elo from the FINAL trained state.
Every "prediction" is therefore contaminated, so its calibration numbers can't be
trusted.

This module fixes that the same way MLB's run_backtest does: walk the season's
matches in DATE ORDER, and for each match predict it using ONLY prior matches —
  * Elo: walked game-by-game (start-of-season ratings, update_after_match after
    each), so the rating used to predict match M reflects only games before M.
  * Strengths: recomputed from finished matches strictly BEFORE M's date.
A minimum number of prior games is required before a match is scored (early-season
matches have too little data to be meaningful), mirroring the MLB min-40 guard.

Outputs 1X2 calibration: for probability buckets, does an X% home/draw/away
prediction actually happen X% of the time? Plus multiclass log-loss and Brier,
the honest accuracy numbers we never trustworthily had for soccer.
"""
from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport
from src.models.elo import EloState, EloConfig, update_after_match, apply_season_regression
from src.models.poisson import (estimate_strengths, predict_match, PoissonConfig,
                                 CompetitionScoringContext)


def run_soccer_backtest(competition_code: str = "PL", season: str | None = None,
                        min_prior: int = 40, dixon_coles_rho: float | None = None,
                        elo_goal_coeff: float | None = None):
    """
    Walk `competition_code`/`season` in date order, predict each match using only
    prior matches (leakage-free). Returns a list of per-match result dicts:
      {p_home, p_draw, p_away, actual}  (actual in {"H","D","A"})
    plus None if the competition/season isn't found.

    dixon_coles_rho: if set, overrides the Poisson config's rho (the low-score /
    draw correction) — used by the rho sweep to find the value that best fixes
    the draw under-prediction.

    min_prior: skip matches until this many finished prior matches exist in the
    season (early-season strengths are noise). MLB used 40.
    """
    with session_scope() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            return None

        q = select(Match).where(
            Match.competition_id == comp.id,
            Match.status == MatchStatus.FINISHED,
        )
        if season:
            q = q.where(Match.season == season)
        matches = list(s.execute(q).scalars())
        # sort by kickoff time — the spine of leakage safety
        matches = [m for m in matches
                   if m.utc_date and m.home_score is not None and m.away_score is not None]
        matches.sort(key=lambda m: m.utc_date)
        if not matches:
            return None

        context = CompetitionScoringContext()
        elo = EloState(config=EloConfig())
        poisson_cfg = PoissonConfig()
        import dataclasses
        if dixon_coles_rho is not None:
            poisson_cfg = dataclasses.replace(poisson_cfg, dixon_coles_rho=dixon_coles_rho)
        if elo_goal_coeff is not None:
            # the S1 lever: exp(coeff*elo_diff/2) goal multiplier — damping the
            # coefficient compresses win-leg probabilities toward consensus
            poisson_cfg = dataclasses.replace(poisson_cfg, elo_goal_coeff=elo_goal_coeff)

        results = []
        prior = []  # finished matches strictly before the current one

        for m in matches:
            # --- predict using ONLY prior games ---
            if len(prior) >= min_prior:
                strength_input = [
                    {"home_team_id": p.home_team_id, "away_team_id": p.away_team_id,
                     "home_score": p.home_score, "away_score": p.away_score}
                    for p in prior
                ]
                strengths = estimate_strengths(strength_input, context)
                hs = strengths.get(m.home_team_id)
                as_ = strengths.get(m.away_team_id)
                if hs and as_:
                    pred = predict_match(
                        home_elo=elo.get(m.home_team_id),
                        away_elo=elo.get(m.away_team_id),
                        home_strength=hs, away_strength=as_,
                        context=context, config=poisson_cfg,
                    )
                    if m.home_score > m.away_score:
                        actual = "H"
                    elif m.home_score < m.away_score:
                        actual = "A"
                    else:
                        actual = "D"
                    results.append({
                        "match_id": m.id,
                        "p_home": pred.p_home, "p_draw": pred.p_draw,
                        "p_away": pred.p_away, "actual": actual,
                    })

            # --- AFTER predicting, update Elo + add to prior (order matters!) ---
            nh, na = update_after_match(
                elo.get(m.home_team_id), elo.get(m.away_team_id),
                m.home_score, m.away_score, elo.config,
            )
            elo.set(m.home_team_id, nh)
            elo.set(m.away_team_id, na)
            prior.append(m)

        return results


def soccer_calibration(results):
    """
    1X2 calibration: bucket predictions by probability and compare predicted vs
    actual frequency, separately for home/draw/away. Plus multiclass log-loss and
    Brier. Returns a dict for the CLI to render.
    """
    if not results:
        return None

    # per-outcome calibration bins (0-10%,...,90-100%)
    def bins_for(outcome_key, actual_letter):
        bins = defaultdict(lambda: [0, 0])  # bucket -> [pred_sum, hits]
        for r in results:
            p = r[outcome_key]
            b = min(9, int(p * 10))
            bins[b][0] += p
            bins[b][1] += 1 if r["actual"] == actual_letter else 0
        rows = []
        for b in sorted(bins):
            pred_sum, _ = bins[b]
            cnt = sum(1 for r in results if int(min(9, int(r[outcome_key] * 10))) == b)
            hits = bins[b][1]
            n = cnt
            if n == 0:
                continue
            avg_pred = pred_sum / n
            act = hits / n
            se = math.sqrt(act * (1 - act) / n) if n > 0 else None
            rows.append((f"{b*10}-{b*10+10}%", n, avg_pred, act, se))
        return rows

    # log-loss + brier (multiclass over H/D/A)
    ll, br, n = 0.0, 0.0, 0
    for r in results:
        probs = {"H": r["p_home"], "D": r["p_draw"], "A": r["p_away"]}
        tot = sum(probs.values()) or 1.0
        probs = {k: v / tot for k, v in probs.items()}
        p_true = max(1e-12, probs[r["actual"]])
        ll += -math.log(p_true)
        for k in ("H", "D", "A"):
            y = 1.0 if r["actual"] == k else 0.0
            br += (probs[k] - y) ** 2
        n += 1

    # overall frequencies (sanity: does the model's mean match base rates?)
    base = {k: sum(1 for r in results if r["actual"] == k) / len(results)
            for k in ("H", "D", "A")}
    mean_pred = {
        "H": sum(r["p_home"] for r in results) / len(results),
        "D": sum(r["p_draw"] for r in results) / len(results),
        "A": sum(r["p_away"] for r in results) / len(results),
    }

    return {
        "n": n,
        "log_loss": ll / n,
        "brier": br / n,
        "home_bins": bins_for("p_home", "H"),
        "draw_bins": bins_for("p_draw", "D"),
        "away_bins": bins_for("p_away", "A"),
        "base_rates": base,
        "mean_pred": mean_pred,
    }


def market_comparison(results):
    """
    Join backtest predictions to stored closing odds (bookmaker fdcuk_close)
    and answer the pre-launch question the MLB side needed weeks of forward
    data for: HOW DOES THE MODEL COMPARE TO THE CLOSING MARKET on the exact
    same games?

    Reports (only over games where closing odds exist):
      * model vs market multiclass log-loss (market = proportionally de-vigged
        closing 1X2 — the strongest public benchmark there is)
      * mean |model − market| per outcome (how far we sit from consensus)
      * close_edge_pp on the model's top pick: model prob − market fair prob,
        i.e. the CLV-at-close analog, split by sign with hit rates — the raw
        material for soccer's OWN thermometer-vs-income-engine verdict.
    Returns None if no closing odds are stored for any backtested game.
    """
    from src.db.schema import Odds

    by_id = {r["match_id"]: r for r in results if r.get("match_id")}
    if not by_id:
        return None

    with session_scope() as s:
        rows = s.execute(
            select(Odds).where(
                Odds.match_id.in_(list(by_id)),
                Odds.bookmaker == "fdcuk_close",
                Odds.market == "1X2",
            )
        ).scalars()
        prices: dict[int, dict[str, float]] = defaultdict(dict)
        for o in rows:
            prices[o.match_id][o.selection] = o.price_decimal

    joined = []
    for mid, p in prices.items():
        if {"HOME", "DRAW", "AWAY"} <= set(p):
            r = by_id[mid]
            inv = {k: 1.0 / v for k, v in p.items()}
            tot = sum(inv.values())
            mkt = {k: inv[k] / tot for k in inv}  # proportional de-vig
            joined.append((r, mkt))
    if not joined:
        return None

    def logloss(prob_for_actual):
        return -math.log(max(prob_for_actual, 1e-12))

    KEY = {"H": ("p_home", "HOME"), "D": ("p_draw", "DRAW"), "A": ("p_away", "AWAY")}
    n = len(joined)
    model_ll = market_ll = 0.0
    gaps = {"HOME": 0.0, "DRAW": 0.0, "AWAY": 0.0}
    edges = []  # (edge_pp on model top pick, pick_hit)
    for r, mkt in joined:
        mk_key, sel = KEY[r["actual"]]
        model_ll += logloss(r[mk_key])
        market_ll += logloss(mkt[sel])
        for sel2, rk in (("HOME", "p_home"), ("DRAW", "p_draw"), ("AWAY", "p_away")):
            gaps[sel2] += abs(r[rk] - mkt[sel2])
        # model's top pick and its edge vs market fair prob
        pick_rk, pick_sel = max(
            (("p_home", "HOME"), ("p_draw", "DRAW"), ("p_away", "AWAY")),
            key=lambda t: r[t[0]],
        )
        edge_pp = (r[pick_rk] - mkt[pick_sel]) * 100.0
        hit = KEY[r["actual"]][1] == pick_sel
        edges.append((edge_pp, hit))

    pos = [(e, h) for e, h in edges if e > 0]
    neg = [(e, h) for e, h in edges if e <= 0]
    return {
        "games": n,
        "model_log_loss": model_ll / n,
        "market_log_loss": market_ll / n,
        "mean_abs_gap_pp": {k: 100.0 * v / n for k, v in gaps.items()},
        "mean_pick_edge_pp": sum(e for e, _ in edges) / n,
        "positive_edge": {"n": len(pos),
                          "mean_edge_pp": (sum(e for e, _ in pos) / len(pos)) if pos else None,
                          "hit_rate": (sum(h for _, h in pos) / len(pos)) if pos else None},
        "non_positive_edge": {"n": len(neg),
                              "mean_edge_pp": (sum(e for e, _ in neg) / len(neg)) if neg else None,
                              "hit_rate": (sum(h for _, h in neg) / len(neg)) if neg else None},
    }
