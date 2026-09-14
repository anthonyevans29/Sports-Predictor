"""
Miss analysis — exploratory, broad sweep over categories to find where the
model underperforms its OWN predicted probability.

The disciplined version of "categorize what we got wrong." We do NOT bucket
losses alone (that always finds spurious patterns). Instead, for every
categorical dimension, each bucket reports:
    n, actual win rate, predicted win rate, gap (actual − predicted), ±SE
A category is a real "miss category" only if actual materially trails predicted
BEYOND sampling noise — which automatically controls for how often each category
should win.

HARD discipline (multiple comparisons): we test many buckets across many
dimensions, so 1-2 WILL look significant by chance. A bucket earns follow-up
only if the gap is large, well-sampled, clears ~2 SE, AND ideally shows a
gradient across an ordered dimension (not one lone bucket poking out). The
command prints this caveat and flags accordingly.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import timezone

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import (Match, Prediction, PredictionOutcome, Team, Sport, Odds)
from src.walters.value import MarketSnapshot


def _wilson_se(k, n):
    """Standard error of a proportion (simple)."""
    if n == 0:
        return None
    p = k / n
    return math.sqrt(p * (1 - p) / n) if n > 0 else None


def run_miss_analysis():
    """
    Returns {dimension: [(bucket_label, n, actual, predicted, gap, se), ...]}.
    """
    dims: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    # each bucket accumulates (won:0/1, predicted_prob)

    with session_scope() as s:
        rows = list(s.execute(
            select(Prediction, Match, PredictionOutcome)
            .join(Match, Match.id == Prediction.match_id)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .where(Match.sport == Sport.MLB,
                   PredictionOutcome.top_pick_hit.isnot(None))
        ).all())

        # market edge per match (for the agreement/disagreement dimension)
        # (compute lazily only where odds exist)
        odds_by_match = defaultdict(list)
        for o in s.execute(select(Odds).where(Odds.market == "1X2")).scalars():
            odds_by_match[o.match_id].append(o)

        for pred, m, oc in rows:
            probs = {"home": pred.home_win_prob, "away": pred.away_win_prob}
            nn = {k: v for k, v in probs.items() if v is not None}
            if not nn:
                continue
            side = max(nn, key=nn.get)
            p = nn[side]
            won = 1 if oc.top_pick_hit else 0
            rec = (won, p)
            fb = pred.factor_breakdown or {}

            # --- dimension: favorite side ---
            dims["favorite_side"]["home fav" if side == "home" else "road fav"].append(rec)

            # --- dimension: probability tier ---
            if p < 0.53:
                tier = "toss-up (<53%)"
            elif p < 0.57:
                tier = "lean (53-57%)"
            elif p < 0.62:
                tier = "solid (57-62%)"
            else:
                tier = "strong (≥62%)"
            dims["confidence_tier"][tier].append(rec)

            # --- dimension: day vs night (local) ---
            if m.utc_date:
                hr = m.utc_date.replace(tzinfo=timezone.utc).astimezone().hour
                dims["day_night"]["day (<17h)" if hr < 17 else "night (≥17h)"].append(rec)

            # --- dimension: close-game flag ---
            cg = pred.factor_breakdown is not None  # placeholder guard
            # use computed helpers' stored proxies where present in fb
            p1r = fb.get("p_one_run")
            if p1r is not None:
                dims["one_run_risk"]["high 1-run (≥.24)" if p1r >= 0.24 else "low 1-run"].append(rec)

            # --- dimension: starter known vs uncertain ---
            sk = fb.get("home_starter_known", True) and fb.get("away_starter_known", True)
            dims["starter_known"]["both known" if sk else "starter uncertain"].append(rec)

            # --- dimension: stronger expression ---
            se_expr = None
            # recompute simple: side vs total leaning from over_prob/tier isn't stored;
            # use whether an over/under line existed as a proxy for totals-in-play
            if pred.over_under_line is not None:
                se_expr = "total line present"
            else:
                se_expr = "no total line"
            dims["totals_availability"][se_expr].append(rec)

            # --- dimension: park (top venues only, rest bucketed) ---
            venue = m.venue or "unknown"
            dims["park"][venue].append(rec)

            # --- dimension: run environment (projected total) ---
            eh, ea = pred.expected_home_score, pred.expected_away_score
            if eh is not None and ea is not None:
                tot = eh + ea
                if tot < 8:
                    rb = "low (<8)"
                elif tot < 9:
                    rb = "mid (8-9)"
                else:
                    rb = "high (≥9)"
                dims["run_environment"][rb].append(rec)

            # --- dimension: market agreement vs disagreement ---
            odds = odds_by_match.get(m.id)
            if odds:
                by_sel = defaultdict(list)
                for o in odds:
                    by_sel[o.selection].append((o.bookmaker, o.price_decimal))
                imp = MarketSnapshot(market="1X2", by_selection=by_sel).average_implied()
                over = sum(imp.values())
                sel = "HOME" if side == "home" else "AWAY"
                if over > 0 and sel in imp:
                    mkt_p = imp[sel] / over
                    dims["market"]["agree (model=mkt fav)" if mkt_p >= 0.5
                                   else "disagree (model=mkt dog)"].append(rec)

    # summarize
    out = {}
    for dim, buckets in dims.items():
        rows_out = []
        for label, recs in buckets.items():
            n = len(recs)
            if n == 0:
                continue
            wins = sum(w for w, _ in recs)
            actual = wins / n
            predicted = sum(pp for _, pp in recs) / n
            gap = actual - predicted
            se = _wilson_se(wins, n)
            rows_out.append((label, n, actual, predicted, gap, se))
        # sort parks by n desc and keep top; others alpha
        rows_out.sort(key=lambda r: -r[1])
        out[dim] = rows_out
    return out
