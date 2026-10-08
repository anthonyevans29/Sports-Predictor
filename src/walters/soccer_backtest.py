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
from src.walters.evaluation import rps_1x2


# --------------------------------------------------------------------------
# S19 time-decay CANDIDATE (architect 2026-09-30, Issue #83) — BACKTEST ONLY
# --------------------------------------------------------------------------
# FROZEN A PRIORI, declared before any run (BACKLOG "S19 + S20"): ONE value,
# no grid, no selection. Dixon & Coles (1997, Appl. Statist. 46:265-280) fitted
# their time-weighting xi = 0.0065 per HALF-WEEK on English league data, i.e.
# a half-life of ln(2)/0.0065 = 106.6 half-weeks = 373 days; rounded to one
# calendar year. Not fitted on any of our data. ARCHITECT-RULE for ratification.
TIME_DECAY_HALF_LIFE_DAYS = 365.0

#: The candidate's name on the CLI (`soccer-backtest --candidate time-decay`).
TIME_DECAY_CANDIDATE = "time-decay"

#: The pre-declared evaluation set for the S19 verdict (frozen with the
#: half-life, ARCHITECT-RULE): PL, the three most recent COMPLETE seasons
#: (the S1 two-season overfit guard, plus the season that has finished since).
#: Pooled over all three; a missing season makes the verdict INVALID, never a
#: pass on a partial set.
S19_GATE_COMPETITION = "PL"
S19_GATE_SEASONS = ("2023/24", "2024/25", "2025/26")


def time_decay_weight(age_days: float, half_life_days: float) -> float:
    """w = 0.5 ** (age_days / half_life_days). A match played at the
    prediction instant weighs 1.0; one half-life earlier, 0.5. Negative ages
    (cannot occur in the leakage-free walk) clamp to 1.0."""
    if half_life_days <= 0:
        raise ValueError("half_life_days must be > 0")
    return 0.5 ** (max(0.0, age_days) / half_life_days)


def run_soccer_backtest(competition_code: str = "PL", season: str | None = None,
                        min_prior: int = 40, dixon_coles_rho: float | None = None,
                        elo_goal_coeff: float | None = None,
                        decay_half_life_days: float | None = None,
                        detail: bool = False,
                        s14_uncertain_offset: float | None = None,
                        sealed_read: bool = False,
                        stage_filter=None,
                        batch_same_kickoff: bool = False):
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

    decay_half_life_days (S19 candidate): if set, each prior match's weight in
    the attack/defense fit is time_decay_weight(its age at M's kickoff). Elo is
    NOT decayed (its K-updates are already recency-weighted by construction).
    None = the baseline walk, unchanged. The SET of scored matches is
    identical either way (it depends only on the prior count and team
    presence), so both arms score the same games.

    detail (SOCCER-CANDIDATES, 2026-10-01): each result also carries
    home_xg / away_xg / p_over and the actual score — additive keys, off by
    default (byte-identical results for every existing caller).

    s14_uncertain_offset (S14 Stage-2 candidate, backtest-only): when the
    UNADJUSTED prediction's top pick is < 0.45, both expected-goal rates scale
    by (T + offset) / T (T = home_xg + away_xg) and the match is re-predicted.
    Confident games are untouched; the scored set is identical.

    stage_filter (soccer-expansion-v1 F3, ARCHITECT 2026-10-07): an optional
    callable stage -> bool; when set, only rows whose stored Match.stage it
    accepts are walked AND scored (rows it rejects never touch Elo or the
    prior). None = every row, unchanged.

    batch_same_kickoff (soccer-expansion-v1 F5, ARCHITECT 2026-10-07): when
    True, every fixture sharing an identical kickoff timestamp is predicted
    from the same state, before any of them updates Elo or the prior; the
    scored predicate becomes ">= min_prior rows with a strictly earlier
    kickoff, both teams among them". False (the default) = the row-by-row
    walk, so every existing command reproduces its recorded numbers.
    """
    # soccer-expansion-v1 (ARCHITECT 2026-10-07; Codex on #326): its leagues' test seasons are read ONCE, by its gate.
    # Every caller of this walk (soccer-backtest, the rho / coefficient sweeps, the candidate harnesses) is refused
    # on those leagues while the experiment is declared and unrun; only the gate passes sealed_read=True.
    if not sealed_read:
        from src.walters import soccer_expansion as _sx
        _why = _sx.guards_backtest(competition_code)
        if _why:
            raise _sx.ExpansionRefused(_why)
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
        if stage_filter is not None:
            matches = [m for m in matches if stage_filter(m.stage)]
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

        # Groups walked as one step: every group is predicted from the state
        # before it, then the whole group updates. Default: one row per group
        # (the row-by-row walk, unchanged); batched: one group per kickoff.
        if batch_same_kickoff:
            groups = []
            for m in matches:
                if groups and groups[-1][0].utc_date == m.utc_date:
                    groups[-1].append(m)
                else:
                    groups.append([m])
        else:
            groups = [[m] for m in matches]

        for group in groups:
            for m in group:
                # --- predict using ONLY prior games ---
                if len(prior) >= min_prior:
                    strength_input = [
                        {"home_team_id": p.home_team_id, "away_team_id": p.away_team_id,
                         "home_score": p.home_score, "away_score": p.away_score}
                        for p in prior
                    ]
                    weights = None
                    if decay_half_life_days is not None:
                        weights = [
                            time_decay_weight(
                                (m.utc_date - p.utc_date).total_seconds() / 86400.0,
                                decay_half_life_days)
                            for p in prior
                        ]
                    strengths = estimate_strengths(strength_input, context, weights=weights)
                    hs = strengths.get(m.home_team_id)
                    as_ = strengths.get(m.away_team_id)
                    if hs and as_:
                        pred = predict_match(
                            home_elo=elo.get(m.home_team_id),
                            away_elo=elo.get(m.away_team_id),
                            home_strength=hs, away_strength=as_,
                            context=context, config=poisson_cfg,
                        )
                        if (s14_uncertain_offset is not None
                                and max(pred.p_home, pred.p_draw, pred.p_away) < 0.45):
                            from types import SimpleNamespace
                            tot = pred.home_xg + pred.away_xg
                            mult = (tot + s14_uncertain_offset) / tot
                            pred = predict_match(
                                home_elo=elo.get(m.home_team_id),
                                away_elo=elo.get(m.away_team_id),
                                home_strength=hs, away_strength=as_,
                                context=context, config=poisson_cfg,
                                factor_adjustment=SimpleNamespace(home_xg_multiplier=mult,
                                                                  away_xg_multiplier=mult),
                            )
                        if m.home_score > m.away_score:
                            actual = "H"
                        elif m.home_score < m.away_score:
                            actual = "A"
                        else:
                            actual = "D"
                        row = {
                            "match_id": m.id,
                            "p_home": pred.p_home, "p_draw": pred.p_draw,
                            "p_away": pred.p_away, "actual": actual,
                        }
                        if detail:
                            row.update(home_xg=pred.home_xg, away_xg=pred.away_xg, p_over=pred.p_over,
                                       home_score=m.home_score, away_score=m.away_score)
                        results.append(row)

            for m in group:
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
    ll, br, rps, n = 0.0, 0.0, 0.0, 0
    for r in results:
        probs = {"H": r["p_home"], "D": r["p_draw"], "A": r["p_away"]}
        tot = sum(probs.values()) or 1.0
        probs = {k: v / tot for k, v in probs.items()}
        p_true = max(1e-12, probs[r["actual"]])
        ll += -math.log(p_true)
        rps += rps_1x2(probs["H"], probs["D"], probs["A"], r["actual"])
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
        "rps": rps / n,  # S20: REPORTED ONLY — in no acceptance criterion
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
    model_rps = market_rps = 0.0  # S20: reported only
    gaps = {"HOME": 0.0, "DRAW": 0.0, "AWAY": 0.0}
    edges = []  # (edge_pp on model top pick, pick_hit)
    for r, mkt in joined:
        mk_key, sel = KEY[r["actual"]]
        model_ll += logloss(r[mk_key])
        market_ll += logloss(mkt[sel])
        model_rps += rps_1x2(r["p_home"], r["p_draw"], r["p_away"], r["actual"])
        market_rps += rps_1x2(mkt["HOME"], mkt["DRAW"], mkt["AWAY"], r["actual"])
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
        "model_rps": model_rps / n,
        "market_rps": market_rps / n,
        "mean_abs_gap_pp": {k: 100.0 * v / n for k, v in gaps.items()},
        "mean_pick_edge_pp": sum(e for e, _ in edges) / n,
        "positive_edge": {"n": len(pos),
                          "mean_edge_pp": (sum(e for e, _ in pos) / len(pos)) if pos else None,
                          "hit_rate": (sum(h for _, h in pos) / len(pos)) if pos else None},
        "non_positive_edge": {"n": len(neg),
                              "mean_edge_pp": (sum(e for e, _ in neg) / len(neg)) if neg else None,
                              "hit_rate": (sum(h for _, h in neg) / len(neg)) if neg else None},
    }


# --------------------------------------------------------------------------
# S19 candidate vs production on the SAME splits — the existing soccer gate
# --------------------------------------------------------------------------


#: improve's holdout floor, carried over verbatim (training.improve rejects a
#: holdout under 30 matches); here a thinner set is INVALID.
MIN_GATE_N = 30


def candidate_gate_verdict(prod_log_loss: float, cand_log_loss: float,
                           min_delta: float) -> tuple[str, float]:
    """The existing promotion rule, verbatim from training.improve:
        delta = prod_loss - cand_loss  # positive = candidate better
        if delta >= min_delta: <pass>
    Anything else REJECTS, so an exact tie (delta 0) rejects. Returns
    (verdict, delta). RPS plays no part."""
    delta = prod_log_loss - cand_log_loss
    return ("PASS" if delta >= min_delta else "REJECT"), delta


def compare_candidate(base_results, cand_results, min_delta: float) -> dict:
    """Score production (base) and candidate on the identical match set.
    Refuses to compare different or empty sets (verdict INVALID): the gate is
    only meaningful when both arms scored exactly the same games."""
    base_ids = sorted(r["match_id"] for r in base_results or [])
    cand_ids = sorted(r["match_id"] for r in cand_results or [])
    if not base_ids or base_ids != cand_ids:
        return {"verdict": "INVALID", "n": len(base_ids),
                "reason": (f"match sets differ or empty (production {len(base_ids)}, "
                           f"candidate {len(cand_ids)})")}
    if len(base_ids) < MIN_GATE_N:
        # improve's own floor (training.py: holdout_size < 30 -> reject)
        return {"verdict": "INVALID", "n": len(base_ids),
                "reason": f"too few scored matches ({len(base_ids)} < {MIN_GATE_N})"}
    b = soccer_calibration(base_results)
    c = soccer_calibration(cand_results)
    verdict, delta = candidate_gate_verdict(b["log_loss"], c["log_loss"], min_delta)
    return {"verdict": verdict, "delta": delta, "min_delta": min_delta, "n": b["n"],
            "prod_log_loss": b["log_loss"], "cand_log_loss": c["log_loss"],
            "prod_rps": b["rps"], "cand_rps": c["rps"],
            "prod_brier": b["brier"], "cand_brier": c["brier"]}


def run_time_decay_comparison(competition_code: str, seasons, *, min_prior: int = 40,
                              dixon_coles_rho: float, elo_goal_coeff: float,
                              half_life_days: float = TIME_DECAY_HALF_LIFE_DAYS,
                              min_delta: float | None = None) -> dict:
    """Run production (no decay) and the S19 candidate (frozen half-life) on
    the same competition/season splits with the SAME poisson config, pool all
    seasons, and apply the existing gate. Read-only: writes nothing.

    Any missing season makes the pooled verdict INVALID (never a pass on a
    partial set)."""
    if min_delta is None:
        from src.walters.training import DEFAULT_PROMOTION_DELTA
        min_delta = DEFAULT_PROMOTION_DELTA
    kw = dict(min_prior=min_prior, dixon_coles_rho=dixon_coles_rho,
              elo_goal_coeff=elo_goal_coeff)
    per, base_all, cand_all, missing = [], [], [], []
    for season in seasons:
        base = run_soccer_backtest(competition_code, season, **kw)
        cand = run_soccer_backtest(competition_code, season,
                                   decay_half_life_days=half_life_days, **kw)
        if not base or not cand:
            missing.append(season)
            per.append({"season": season, "verdict": "MISSING", "n": 0})
            continue
        row = compare_candidate(base, cand, min_delta)
        row["season"] = season
        per.append(row)
        base_all.extend(base)
        cand_all.extend(cand)
    pooled = compare_candidate(base_all, cand_all, min_delta)
    if missing:
        pooled = {**pooled, "verdict": "INVALID",
                  "reason": f"season(s) not found / nothing scored: {', '.join(missing)}"}
    return {"competition": competition_code, "seasons": list(seasons),
            "half_life_days": half_life_days, "per_season": per,
            "pooled": pooled, "missing": missing}
