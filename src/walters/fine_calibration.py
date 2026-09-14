"""
Fine-grained calibration — configurable band width + honest error bars.

The tension this module manages: finer bands (1-point: 50%, 51%, 52%…) give
higher resolution but each band holds fewer games, so its actual win-rate is
noisier. This module keeps the fine resolution but makes the noise VISIBLE:
  - every band shows n and a Wilson 95% interval (so a thin band reads as
    directional, not precise);
  - a coarse grouping (default 5pp) is shown alongside for the statistically
    honest read;
  - a monotonicity check on the coarse bands captures the trend that survives
    noise even when individual fine bands don't.

Read fine bands for texture; trust the coarse bands + monotonic trend for the
verdict.
"""
from __future__ import annotations

import math
from datetime import datetime

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import Match, Prediction, PredictionOutcome, Sport


def _wilson(k, n, z=1.96):
    """Wilson score interval for a binomial proportion. Returns (lo, hi)."""
    if n == 0:
        return (None, None)
    phat = k / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _collect(since: datetime | None, actionable_min: float | None):
    """Return list of (pick_prob, won 0/1) for graded MLB predictions."""
    with session_scope() as s:
        q = (
            select(Prediction, PredictionOutcome)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == Sport.MLB,
                   PredictionOutcome.top_pick_hit.isnot(None))
        )
        if since is not None:
            q = q.where(Prediction.computed_at >= since)
        rows = s.execute(q).all()

    out = []
    for pred, oc in rows:
        probs = [p for p in (pred.home_win_prob, pred.away_win_prob) if p is not None]
        if not probs:
            continue
        p = max(probs)  # probability on the model's pick
        if actionable_min is not None and p < actionable_min:
            continue
        out.append((p, 1 if oc.top_pick_hit else 0))
    return out


def _band(records, width, lo_bound=0.50, hi_bound=1.00):
    """Bucket records into bands of `width` from lo_bound to hi_bound."""
    bands = {}
    edge = lo_bound
    while edge < hi_bound - 1e-9:
        top = min(edge + width, hi_bound)
        key = (round(edge, 4), round(top, 4))
        bands[key] = []
        edge = top
    for p, won in records:
        for (lo, hi) in bands:
            if lo <= p < hi or (hi >= hi_bound and p >= lo and p <= hi):
                bands[(lo, hi)].append((p, won))
                break
    rows = []
    for (lo, hi), recs in sorted(bands.items()):
        n = len(recs)
        if n == 0:
            continue
        wins = sum(w for _, w in recs)
        actual = wins / n
        predicted = sum(p for p, _ in recs) / n
        wlo, whi = _wilson(wins, n)
        rows.append({
            "lo": lo, "hi": hi, "n": n, "actual": actual,
            "predicted": predicted, "gap": actual - predicted,
            "ci_lo": wlo, "ci_hi": whi,
        })
    return rows


def fine_calibration(since=None, width=0.01, actionable_min=None):
    """
    Returns dict with 'fine' (width-band rows), 'coarse' (5pp-band rows),
    'n_total', and 'monotonic' (bool over well-sampled coarse bands).
    """
    records = _collect(since, actionable_min)
    n_total = len(records)
    fine = _band(records, width)
    coarse = _band(records, 0.05)

    # monotonic trend over coarse bands with enough sample (n>=25)
    sampled = [r for r in coarse if r["n"] >= 25]
    monotonic = None
    if len(sampled) >= 3:
        actuals = [r["actual"] for r in sampled]
        monotonic = all(actuals[i] <= actuals[i + 1] + 0.02
                        for i in range(len(actuals) - 1))
    return {"fine": fine, "coarse": coarse, "n_total": n_total,
            "monotonic": monotonic}
