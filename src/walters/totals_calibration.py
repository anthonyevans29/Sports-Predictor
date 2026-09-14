"""
Totals calibration — the accuracy analysis we did for SIDES but never for TOTALS.

Three independent reads on graded predictions that had a real market total:

1. PROJECTED TOTAL vs ACTUAL — is the model's expected run total centered, or
   biased (projects too low/high)? This is the totals analogue of win-prob
   calibration. Reported overall + bucketed by projected level.

2. OVER/UNDER PROBABILITY calibration — when the model says X% over, does the
   over hit X%? Separate from #1: you can have a centered projection but
   miscalibrated tails if the distribution SHAPE (NegBin dispersion) is off.

3. RUN-ENVIRONMENT cut — is the projection well-centered in normal games but
   biased in high/low-scoring ones? Bias that's flat overall can hide here.

Honest notes:
  - Only games with a real market line (over_under_line not None) count — a
    fallback line isn't a market total and would pollute the read.
  - "Beats the market" is a SEPARATE question (totals CLV) not answered here;
    this measures ACCURACY of the number, which comes first. A centered,
    well-calibrated total still might not beat a sharp market line.
  - Totals markets are widely considered softer than sides — so unlike the side
    (already well-calibrated, market-efficient), a totals miscalibration found
    here could be both real AND fixable. That's the reason to look.
"""
from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import Match, Prediction, PredictionOutcome, Sport


def _mean_sd_n(vals):
    n = len(vals)
    if n == 0:
        return None, None, 0
    m = sum(vals) / n
    if n < 2:
        return m, None, n
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    return m, math.sqrt(var), n


def _collect(since=None):
    """Return list of dicts: projected_total, market_line, over_prob, actual_total.
    If `since` (datetime) given, only predictions computed on/after it — lets you
    isolate a config era (e.g. post run_shrink_frac=0.35 change)."""
    out = []
    with session_scope() as s:
        q = (
            select(Prediction, PredictionOutcome)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == Sport.MLB,
                   PredictionOutcome.actual_home_score.isnot(None),
                   PredictionOutcome.actual_away_score.isnot(None),
                   Prediction.over_under_line.isnot(None))
        )
        if since is not None:
            q = q.where(Prediction.computed_at >= since)
        rows = s.execute(q).all()
        for pred, oc in rows:
            eh, ea = pred.expected_home_score, pred.expected_away_score
            if eh is None or ea is None:
                continue
            actual = oc.actual_home_score + oc.actual_away_score
            out.append({
                "projected": eh + ea,
                "line": pred.over_under_line,
                "over_prob": pred.over_prob,
                "actual": actual,
            })
    return out


def totals_calibration(since=None):
    recs = _collect(since=since)
    n = len(recs)
    if n == 0:
        return None

    # --- 1. projected vs actual (bias) ---
    errors = [r["actual"] - r["projected"] for r in recs]
    mean_err, sd_err, _ = _mean_sd_n(errors)
    se_err = (sd_err / math.sqrt(n)) if sd_err else None
    mae = sum(abs(e) for e in errors) / n

    # bucket by projected level
    proj_buckets = defaultdict(list)
    for r in recs:
        p = r["projected"]
        if p < 7.5:
            k = "low proj (<7.5)"
        elif p < 8.5:
            k = "mid proj (7.5-8.5)"
        elif p < 9.5:
            k = "high proj (8.5-9.5)"
        else:
            k = "very high (≥9.5)"
        proj_buckets[k].append(r["actual"] - r["projected"])
    proj_rows = []
    for k in ("low proj (<7.5)", "mid proj (7.5-8.5)", "high proj (8.5-9.5)", "very high (≥9.5)"):
        if k in proj_buckets:
            m, sd, nb = _mean_sd_n(proj_buckets[k])
            se = (sd / math.sqrt(nb)) if sd and nb > 1 else None
            proj_rows.append((k, nb, m, se))

    # --- 2. over/under probability calibration ---
    # bucket by model over_prob, compare to actual over rate vs the market line
    ou = [r for r in recs if r["over_prob"] is not None]
    ou_buckets = defaultdict(list)  # band -> list of (over_prob, did_over)
    for r in ou:
        did_over = 1 if r["actual"] > r["line"] else (0 if r["actual"] < r["line"] else None)
        if did_over is None:
            continue  # push
        p = r["over_prob"]
        band = int(p * 10) / 10  # 0.0,0.1,... group into 10pp bands
        ou_buckets[band].append((p, did_over))
    ou_rows = []
    for band in sorted(ou_buckets):
        recs_b = ou_buckets[band]
        nb = len(recs_b)
        pred_p = sum(p for p, _ in recs_b) / nb
        act_p = sum(d for _, d in recs_b) / nb
        se = math.sqrt(act_p * (1 - act_p) / nb) if nb > 0 else None
        ou_rows.append((f"{band*100:.0f}-{band*100+10:.0f}%", nb, pred_p, act_p, se))

    # --- 3. run-environment cut (actual scoring env, not projected) ---
    env_buckets = defaultdict(list)
    for r in recs:
        a = r["actual"]
        if a <= 6:
            k = "low-scoring (≤6)"
        elif a <= 9:
            k = "normal (7-9)"
        elif a <= 12:
            k = "high (10-12)"
        else:
            k = "blowup (≥13)"
        env_buckets[k].append(r["actual"] - r["projected"])
    env_rows = []
    for k in ("low-scoring (≤6)", "normal (7-9)", "high (10-12)", "blowup (≥13)"):
        if k in env_buckets:
            m, sd, nb = _mean_sd_n(env_buckets[k])
            se = (sd / math.sqrt(nb)) if sd and nb > 1 else None
            env_rows.append((k, nb, m, se))

    # over-rate vs line overall (is the model's line-relative read biased?)
    decided = [r for r in recs if r["actual"] != r["line"]]
    over_rate = (sum(1 for r in decided if r["actual"] > r["line"]) / len(decided)
                 if decided else None)

    # --- 4. residual by MARKET LINE band ---
    # Bucket by the market's total line (not the model's projection). For each
    # band show BOTH: market residual (actual − line) = did games at this line
    # level go over/under the market, and model residual (actual − projected) =
    # the model's own error there. Where the two DIVERGE is where the model's
    # number differs from the market by line level — the betting-relevant cut
    # the projected-total buckets can't show.
    line_buckets = defaultdict(list)  # band -> list of (actual, line, projected)
    for r in recs:
        ln = r["line"]
        if ln is None:
            continue
        if ln < 7.5:
            k = "low line (<7.5)"
        elif ln < 8.5:
            k = "mid line (7.5-8.5)"
        elif ln < 9.5:
            k = "high line (8.5-9.5)"
        else:
            k = "very high (≥9.5)"
        line_buckets[k].append((r["actual"], ln, r["projected"]))
    line_rows = []
    for k in ("low line (<7.5)", "mid line (7.5-8.5)", "high line (8.5-9.5)", "very high (≥9.5)"):
        if k not in line_buckets:
            continue
        recs_b = line_buckets[k]
        nb = len(recs_b)
        mkt_resid = [a - ln for (a, ln, _) in recs_b]        # actual − market line
        mdl_resid = [a - pj for (a, _, pj) in recs_b]        # actual − model projection
        mdl_mkt = [pj - ln for (_, ln, pj) in recs_b]        # model projection − market line
        mkt_m, mkt_sd, _ = _mean_sd_n(mkt_resid)
        mdl_m, mdl_sd, _ = _mean_sd_n(mdl_resid)
        mm_m, _, _ = _mean_sd_n(mdl_mkt)
        mkt_se = (mkt_sd / math.sqrt(nb)) if mkt_sd and nb > 1 else None
        mdl_se = (mdl_sd / math.sqrt(nb)) if mdl_sd and nb > 1 else None
        # over-rate vs the market line within this band
        dec = [(a, ln) for (a, ln, _) in recs_b if a != ln]
        over_b = (sum(1 for a, ln in dec if a > ln) / len(dec)) if dec else None

        # --- edge-candidate flag (all five conditions, else null) ---
        # 1. market meaningfully off at this line level
        # 2. model close to actual
        # 3. model actually DISAGREED with the line (not just both-off-and-lucky)
        # 4. model's disagreement points the SAME way as the market's miss
        # 5. enough sample (per-band bar deliberately high — beating a market
        #    line is an extraordinary claim)
        MKT_MIN, MDL_MAX, DIFF_MIN, N_MIN = 0.75, 0.40, 0.50, 150
        same_direction = (mkt_m is not None and mm_m is not None
                          and (mkt_m > 0) == (mm_m > 0))
        is_candidate = (
            mkt_m is not None and mdl_m is not None and mm_m is not None
            and abs(mkt_m) > MKT_MIN
            and abs(mdl_m) < MDL_MAX
            and abs(mm_m) > DIFF_MIN
            and same_direction
            and nb >= N_MIN
        )
        line_rows.append((k, nb, mkt_m, mkt_se, mdl_m, mdl_se, mm_m, over_b, is_candidate))

    # overall verdict: any band a candidate?
    any_candidate = any(row[8] for row in line_rows)

    return {
        "n": n, "mean_err": mean_err, "se_err": se_err, "mae": mae,
        "proj_rows": proj_rows, "ou_rows": ou_rows, "env_rows": env_rows,
        "over_rate": over_rate, "n_decided": len(decided),
        "line_rows": line_rows, "any_candidate": any_candidate,
        "flag_thresholds": (0.75, 0.40, 0.50, 150),
    }
