"""
Calibration diagnostic — measures whether the model's stated probabilities
match observed outcomes.

A well-calibrated model that says "63%" should win ~63% of the time across
all such predictions. This module bins scored predictions by their top-pick
probability and compares predicted vs actual hit rate per bin.

Key outputs:
  - Reliability table (per-bin predicted vs actual)
  - Expected Calibration Error (ECE): sample-weighted average gap
  - Per-bin sample counts (so sparse bins can be discounted)

This is a *diagnostic*, not a fix. It tells us whether a calibration
problem exists and how big it is, before we decide whether to apply any
correction. Reading a calibration table off a small sample is itself a
trap — bins with <10 games are basically noise and flagged as such.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import (
    Match, Prediction, PredictionOutcome, Sport,
)


@dataclass
class CalibrationBin:
    """One confidence bucket in the reliability table."""
    low: float           # bin lower edge, e.g. 0.60
    high: float          # bin upper edge, e.g. 0.65
    count: int = 0
    predicted_sum: float = 0.0   # sum of predicted top-pick probs
    hits: int = 0                # number that actually hit

    @property
    def predicted_avg(self) -> float:
        return self.predicted_sum / self.count if self.count else 0.0

    @property
    def actual_rate(self) -> float:
        return self.hits / self.count if self.count else 0.0

    @property
    def gap(self) -> float:
        """Actual minus predicted. Negative = overconfident."""
        return self.actual_rate - self.predicted_avg

    @property
    def reliable(self) -> bool:
        """Whether this bin has enough samples to be worth interpreting."""
        return self.count >= 10


@dataclass
class CalibrationReport:
    sport: str
    total: int
    overall_hit_rate: float
    avg_log_loss: float
    ece: float                       # expected calibration error
    bins: list[CalibrationBin] = field(default_factory=list)
    window_days: int | None = None

    def reliable_bins(self) -> list[CalibrationBin]:
        return [b for b in self.bins if b.reliable and b.count > 0]


def compute_calibration(
    *,
    sport: Sport,
    window_days: int | None = None,
    bin_width: float = 0.05,
) -> CalibrationReport:
    """
    Build a calibration report for scored predictions.

    Args:
        sport: which sport to analyze
        window_days: if set, only include predictions for matches in the
                     last N days. None = all scored predictions.
        bin_width: confidence bin granularity (default 0.05 = 5% bins)

    Returns a CalibrationReport.
    """
    # Build bins from 0.50 up to 1.00 (top-pick prob is always >= ~0.33,
    # but for win/loss markets the top pick is by definition >= 0.5 in a
    # two-way market and >= ~0.34 in a three-way. We bin from 0.30 to be safe.)
    edges = []
    e = 0.30
    while e < 1.0 + 1e-9:
        edges.append(round(e, 2))
        e += bin_width
    bins = [CalibrationBin(low=edges[i], high=edges[i + 1])
            for i in range(len(edges) - 1)]

    cutoff = None
    if window_days is not None:
        cutoff = datetime.utcnow() - timedelta(days=window_days)

    total = 0
    hit_total = 0
    log_loss_sum = 0.0
    log_loss_n = 0

    with session_scope() as s:
        stmt = (
            select(Prediction, PredictionOutcome, Match)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == sport)
        )
        if cutoff is not None:
            stmt = stmt.where(Match.utc_date >= cutoff)

        for pred, outcome, match in s.execute(stmt):
            if outcome.top_pick_hit is None:
                continue
            # Determine the top-pick probability
            probs = [pred.home_win_prob, pred.away_win_prob]
            if pred.draw_prob is not None:
                probs.append(pred.draw_prob)
            top_prob = max(probs)

            total += 1
            hit = bool(outcome.top_pick_hit)
            if hit:
                hit_total += 1

            if outcome.log_loss is not None:
                log_loss_sum += outcome.log_loss
                log_loss_n += 1

            # Place into bin
            for b in bins:
                if b.low <= top_prob < b.high:
                    b.count += 1
                    b.predicted_sum += top_prob
                    if hit:
                        b.hits += 1
                    break

    # Expected Calibration Error: sample-weighted average |gap|
    ece = 0.0
    if total > 0:
        for b in bins:
            if b.count > 0:
                ece += (b.count / total) * abs(b.gap)

    return CalibrationReport(
        sport=sport.value,
        total=total,
        overall_hit_rate=(hit_total / total) if total else 0.0,
        avg_log_loss=(log_loss_sum / log_loss_n) if log_loss_n else 0.0,
        ece=ece,
        bins=[b for b in bins if b.count > 0],
        window_days=window_days,
    )


def suggested_temperature(report: CalibrationReport) -> float | None:
    """
    If the report shows systematic overconfidence in the reliable bins,
    suggest a temperature-scaling factor to pull probabilities toward 0.5.

    Returns None when there isn't enough reliable data, or when the model
    is already well-calibrated (ECE small). Otherwise returns a factor t
    in (0, 1] where the adjustment would be:
        p_adj = 0.5 + (p_raw - 0.5) * t
    t = 1.0 means no change; t < 1.0 pulls toward 0.5.

    This is a *suggestion* for review, not an auto-applied change.
    """
    reliable = report.reliable_bins()
    if len(reliable) < 3:
        return None  # not enough reliable bins to judge

    # Total reliable sample
    n = sum(b.count for b in reliable)
    if n < 50:
        return None

    # Weighted average overconfidence: how much predicted exceeds actual
    # for bins above 0.5 (where overconfidence shows as predicted > actual)
    num = 0.0
    den = 0.0
    for b in reliable:
        if b.predicted_avg <= 0.5:
            continue
        # distance of predicted from 0.5 vs distance of actual from 0.5
        pred_dist = b.predicted_avg - 0.5
        actual_dist = b.actual_rate - 0.5
        if pred_dist <= 0:
            continue
        # the ratio actual_dist / pred_dist is the implied temperature for
        # this bin; weight by count
        ratio = max(0.0, actual_dist / pred_dist)
        num += ratio * b.count
        den += b.count

    if den == 0:
        return None
    t = num / den
    # Clamp to sensible range; only suggest if meaningfully < 1
    t = max(0.3, min(1.0, t))
    if t >= 0.95:
        return None  # basically calibrated, no adjustment worth making
    return round(t, 3)
