"""
Retroactive diagnostic: does bullpen depletion explain overrated favorites?

Tests Anthony's hypothesis on HISTORICAL data we already have. For every graded
prediction, we reconstruct the FAVORITE's bullpen state as of that game's date
(reliever appearances / heavy outings / back-to-back arms in the prior 3 days,
from pitcher_appearances) and ask:

    Do favorites with DEPLETED bullpens underperform their predicted win rate
    by more than favorites with RESTED bullpens?

The model is calibrated overall (~54%), so the honest test is not "do depleted
favorites lose" (every favorite loses sometimes) but "do they win LESS than the
model said they would" — i.e. is there a calibration gap that tracks bullpen
fatigue. We compare predicted win-prob vs actual win-rate WITHIN each bucket.

This reads only; it changes nothing. It's a measurement to rule the hypothesis
in or out before we consider building a feature.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import (Match, Prediction, PredictionOutcome,
                           PitcherAppearance, Team, Sport)


def _team_source_ids(s) -> dict[int, str]:
    """team.id → mlb_stats_api source id (appearances are keyed by source id)."""
    out = {}
    for t in s.execute(select(Team)).scalars():
        sid = (t.external_ids or {}).get("mlb_stats_api")
        if sid:
            out[t.id] = str(sid)
    return out


def run_bullpen_diagnostic(lookback_days: int = 3, heavy_pitches: int = 30):
    """
    Returns a dict with per-bucket {n, predicted, actual, gap} where gap =
    actual_winrate - mean_predicted_prob (negative = favorites overrated).
    """
    with session_scope() as s:
        team_sid = _team_source_ids(s)

        # all graded predictions with their match + outcome
        rows = list(s.execute(
            select(Prediction, Match, PredictionOutcome)
            .join(Match, Match.id == Prediction.match_id)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .where(Match.sport == Sport.MLB,
                   PredictionOutcome.top_pick_hit.isnot(None))
        ).all())

        # preload all appearances once, index by (team_sid, date)
        appearances = list(s.execute(select(PitcherAppearance)).scalars())
        by_team_date = defaultdict(list)  # team_sid -> list[(date, pitches, is_starter)]
        for a in appearances:
            if a.team_source_id and a.game_date:
                by_team_date[a.team_source_id].append(
                    (a.game_date.date(), a.pitches or 0, a.pitcher_id, bool(a.is_starter)))

        results = []  # (depletion_score, predicted_prob, won)
        for pred, m, out in rows:
            probs = {"home": pred.home_win_prob, "away": pred.away_win_prob}
            nn = {k: v for k, v in probs.items() if v is not None}
            if not nn:
                continue
            fav_side = max(nn, key=nn.get)
            fav_prob = nn[fav_side]
            if fav_prob < 0.50:
                continue
            fav_team_id = m.home_team_id if fav_side == "home" else m.away_team_id
            fav_sid = team_sid.get(fav_team_id)
            if not fav_sid or not m.utc_date:
                continue

            gdate = m.utc_date.date()
            window_start = gdate - timedelta(days=lookback_days)
            recent = [x for x in by_team_date.get(fav_sid, [])
                      if window_start <= x[0] < gdate and not x[3]]  # relievers only
            relievers = {x[2] for x in recent}
            heavy = sum(1 for x in recent if x[1] >= heavy_pitches)
            # depletion score: appearances + heavy outings (simple, transparent)
            depletion = len(recent) + heavy

            won = bool(out.top_pick_hit)
            results.append((depletion, fav_prob, won))

    if not results:
        return None

    # bucket by depletion: rested (low) vs depleted (high), split at median
    depletions = sorted(r[0] for r in results)
    median = depletions[len(depletions) // 2]
    buckets = {"rested (≤ median)": [], "depleted (> median)": []}
    for dep, prob, won in results:
        key = "depleted (> median)" if dep > median else "rested (≤ median)"
        buckets[key].append((prob, won))

    # also a finer 3-way cut for transparency
    lo, hi = depletions[len(depletions)//3], depletions[2*len(depletions)//3]
    three = {"low": [], "mid": [], "high": []}
    for dep, prob, won in results:
        k = "high" if dep > hi else ("low" if dep <= lo else "mid")
        three[k].append((prob, won))

    def summarize(pairs):
        n = len(pairs)
        if not n:
            return None
        pred = sum(p for p, _ in pairs) / n
        act = sum(1 for _, w in pairs if w) / n
        return {"n": n, "predicted": pred, "actual": act, "gap": act - pred}

    return {
        "median_depletion": median, "total": len(results),
        "two_way": {k: summarize(v) for k, v in buckets.items()},
        "three_way": {k: summarize(v) for k, v in three.items()},
        "tertile_cuts": {"low_max": lo, "high_min": hi},
    }
