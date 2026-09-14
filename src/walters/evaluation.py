"""
Prediction evaluation.

After matches finish, score each prediction so we can see how the model is
doing. Stored in `prediction_outcomes` table; surfaced in the UI via
/predictions (Phase 3).

Metrics:
  - **Log loss** (cross-entropy): standard probabilistic loss. Penalizes
    confident wrong calls hardest. Lower = better. Baseline market ≈ 0.93,
    naive 33/33/33 ≈ 1.099.
  - **Brier score**: mean squared error between predicted prob vector and
    one-hot actual. 0 = perfect, 0.667 = always 33/33/33. Less sensitive to
    extreme misses than log loss.
  - **RPS** (Ranked Probability Score): accounts for ordinal nature of
    HOME/DRAW/AWAY — predicting AWAY when HOME wins is "worse" than
    predicting DRAW. Standard in soccer literature.
  - **Top-pick hit**: did the highest-probability outcome happen? Binary.

Auto-generated post-mortems are kept short and templated. No LLM calls.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class OutcomeScore:
    log_loss: float
    brier_score: float
    rps: float
    top_pick_hit: bool
    notes: str


def _log_loss_one(p: float) -> float:
    """Log loss for a single-outcome probability. Floor to avoid -inf on 0."""
    return -math.log(max(p, 1e-12))


def score_1x2(
    p_home: float,
    p_draw: float,
    p_away: float,
    actual: str,   # "H", "D", or "A"
) -> OutcomeScore:
    """Score a 1X2 prediction. `actual` is one of H/D/A."""
    # One-hot the actual
    actual_vec = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}.get(actual)
    if actual_vec is None:
        raise ValueError(f"Unknown actual result: {actual!r}")

    # Probability vector
    probs = (p_home, p_draw, p_away)
    eps = 1e-12

    # Log loss = -log(p_actual)
    if actual == "H":
        ll = _log_loss_one(p_home)
    elif actual == "D":
        ll = _log_loss_one(p_draw)
    else:
        ll = _log_loss_one(p_away)

    # Brier = mean squared error
    brier = sum((p - a) ** 2 for p, a in zip(probs, actual_vec)) / 3.0

    # RPS: cumulative squared difference. Order matters: H < D < A.
    cum_pred = [0.0, 0.0]
    cum_pred[0] = p_home
    cum_pred[1] = p_home + p_draw
    cum_actual = [0.0, 0.0]
    cum_actual[0] = actual_vec[0]
    cum_actual[1] = actual_vec[0] + actual_vec[1]
    rps = sum((cp - ca) ** 2 for cp, ca in zip(cum_pred, cum_actual)) / 2.0

    # Top pick hit
    top_idx = max(range(3), key=lambda i: probs[i])
    actual_idx = ["H", "D", "A"].index(actual)
    top_pick_hit = top_idx == actual_idx

    notes = _build_notes(p_home, p_draw, p_away, actual, top_pick_hit, ll)

    return OutcomeScore(
        log_loss=ll,
        brier_score=brier,
        rps=rps,
        top_pick_hit=top_pick_hit,
        notes=notes,
    )


def _build_notes(
    p_home: float, p_draw: float, p_away: float,
    actual: str, top_pick_hit: bool, log_loss: float,
) -> str:
    """Templated post-mortem text. Kept short and factual."""
    probs = {"H": p_home, "D": p_draw, "A": p_away}
    actual_p = probs[actual]
    top_label = max(probs.items(), key=lambda kv: kv[1])
    label_text = {"H": "home win", "D": "draw", "A": "away win"}

    if top_pick_hit:
        if actual_p >= 0.6:
            return f"Confident {label_text[actual]} call ({actual_p:.0%}) landed."
        return f"Top pick {label_text[actual]} ({actual_p:.0%}) was correct."

    # Wrong call. How wrong?
    diff = top_label[1] - actual_p
    if diff >= 0.3:
        return (
            f"Big miss: model favored {label_text[top_label[0]]} at {top_label[1]:.0%}, "
            f"actual was {label_text[actual]} at {actual_p:.0%}."
        )
    return (
        f"Top pick wrong: predicted {label_text[top_label[0]]} ({top_label[1]:.0%}), "
        f"got {label_text[actual]} ({actual_p:.0%})."
    )


def score_winner(
    p_home: float,
    p_away: float,
    actual: str,   # "H" or "A"
) -> OutcomeScore:
    """
    Score a 2-outcome (home/away) prediction. Used for baseball, tennis,
    any sport with no draws.
    """
    if actual not in ("H", "A"):
        raise ValueError(f"Unknown actual result: {actual!r}")

    if actual == "H":
        ll = _log_loss_one(p_home)
        top_pick_hit = p_home >= p_away
    else:
        ll = _log_loss_one(p_away)
        top_pick_hit = p_away > p_home

    probs = (p_home, p_away)
    actual_vec = (1, 0) if actual == "H" else (0, 1)
    brier = sum((p - a) ** 2 for p, a in zip(probs, actual_vec)) / 2.0
    # RPS for 2-outcome is just Brier on the first cell — degenerates
    rps = (p_home - actual_vec[0]) ** 2

    # Templated note
    label_text = {"H": "home win", "A": "away win"}
    actual_p = p_home if actual == "H" else p_away
    top_p = max(p_home, p_away)
    top_letter = "H" if p_home >= p_away else "A"
    if top_pick_hit:
        if actual_p >= 0.65:
            notes = f"Confident {label_text[actual]} call ({actual_p:.0%}) landed."
        else:
            notes = f"Top pick {label_text[actual]} ({actual_p:.0%}) was correct."
    else:
        diff = top_p - actual_p
        if diff >= 0.3:
            notes = (
                f"Big miss: model favored {label_text[top_letter]} at {top_p:.0%}, "
                f"actual was {label_text[actual]} at {actual_p:.0%}."
            )
        else:
            notes = (
                f"Top pick wrong: predicted {label_text[top_letter]} ({top_p:.0%}), "
                f"got {label_text[actual]} ({actual_p:.0%})."
            )

    return OutcomeScore(
        log_loss=ll, brier_score=brier, rps=rps,
        top_pick_hit=top_pick_hit, notes=notes,
    )


def score_over_under(
    p_over: float, p_under: float, total_goals: int, line: float
) -> tuple[bool, str]:
    """Evaluate an over/under prediction. Returns (correct, notes)."""
    actual_over = total_goals > line
    predicted_over = p_over > p_under
    correct = actual_over == predicted_over
    if correct:
        return True, f"Total {total_goals} {'over' if actual_over else 'under'} {line} ✓"
    return False, (
        f"Predicted {'over' if predicted_over else 'under'} {line}, "
        f"actual {total_goals} ({'over' if actual_over else 'under'})"
    )


# --------------------------------------------------------------------------
# Aggregate metrics across many predictions (for model_version stats)
# --------------------------------------------------------------------------


@dataclass
class AggregateMetrics:
    n: int
    avg_log_loss: float
    avg_brier: float
    avg_rps: float
    top_pick_accuracy: float


def aggregate(scores: list[OutcomeScore]) -> AggregateMetrics | None:
    if not scores:
        return None
    n = len(scores)
    return AggregateMetrics(
        n=n,
        avg_log_loss=sum(s.log_loss for s in scores) / n,
        avg_brier=sum(s.brier_score for s in scores) / n,
        avg_rps=sum(s.rps for s in scores) / n,
        top_pick_accuracy=sum(1 for s in scores if s.top_pick_hit) / n,
    )
