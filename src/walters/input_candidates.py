"""
Input-candidate evaluation — the widened candidate-generation axis for `improve`.

The insight (Anthony's): "we never promote" and "we can't test inputs" are the
SAME problem — the improve loop only proposes one candidate (same structure,
retrained). This widens it: candidates may now differ from production by
INCLUDING a tracked input. Same promotion gate (leakage-free holdout, beat
production log-loss by min_delta). Folded into improve on a WEEKLY cadence (not
daily — inputs move slowly, and daily testing is a multiple-comparisons machine
that eventually promotes noise).

HONEST SCOPE (stated, not hidden):
The model is Pythag + NegBin over run profiles. To be a real candidate, an input
must (a) be reconstructable as-of-date historically (no leakage) AND (b) have a
model slot that actually CONSUMES it. Today:
  - Most tracked signals (weather, umpire, streak) have NEITHER as-of-date
    historical reconstruction NOR a consumption slot in the run-profile model.
    They are tracked/validated as CONTEXT, not yet model-consumable features.
  - So the honest first job of this framework is to state that clearly: it lists
    each tracked input, whether it's currently model-consumable, and — for those
    that are — trains + holdout-evaluates them. Right now that set is effectively
    empty, which is the correct, honest status.
This is NOT a limitation to paper over — it's the real state. A signal earns a
consumption slot only after it passes Stage-1 validation (none have). This
framework is the READY mechanism for when one does, and it documents the gap
until then rather than pretending inputs are being model-tested when they can't be.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

STATE_PATH = os.path.expanduser("~/.sports_predictor_input_candidates.json")
DEFAULT_CADENCE_DAYS = 7


@dataclass
class InputCandidateStatus:
    name: str
    model_consumable: bool
    reason: str
    holdout_log_loss: float | None = None
    production_log_loss: float | None = None
    beat_production: bool | None = None


# The tracked inputs and their CURRENT model-consumability. A signal flips to
# consumable only after it (1) passes Stage-1 validation and (2) gets an
# as-of-date reconstruction + a model feature slot built for it.
TRACKED_INPUTS = [
    ("bullpen_fatigue", False,
     "failed Stage-1 (non-monotonic noise, 2x); no as-of-date reconstruction; "
     "no consumption slot in run-profile model"),
    ("bullpen_effectiveness", False,
     "newly tracked (reliever ERA/WHIP/K-9, trailing 30d); accruing — not yet "
     "Stage-1 tested; partially collinear with team RA (bullpen innings are IN "
     "team runs-allowed); the open question is whether RECENT form adds signal "
     "beyond season RA; no consumption slot yet"),
    ("weather_wind", False,
     "not validated; no consumption slot (Pythag/NegBin has no wind feature)"),
    ("umpire_run_env", False,
     "not validated (park-confounded); no consumption slot"),
    ("streak", False,
     "collinear with team quality model already has; not validated; no slot"),
    ("won_last_game", False,
     "collinear with team quality; not validated; no slot"),
]


def _load_state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict):
    try:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def due_for_input_eval(cadence_days: int = DEFAULT_CADENCE_DAYS) -> bool:
    """True if it's been >= cadence_days since the last input-candidate eval."""
    state = _load_state()
    last = state.get("last_input_eval")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return True
    return datetime.utcnow() - last_dt >= timedelta(days=cadence_days)


def mark_input_eval_done():
    state = _load_state()
    state["last_input_eval"] = datetime.utcnow().isoformat()
    _save_state(state)


def evaluate_input_candidates(sport, holdout_days: int, min_delta: float) -> list:
    """
    For each tracked input, report model-consumability and — for consumable ones
    — train a production+input candidate and holdout-evaluate it leakage-free.

    Returns list[InputCandidateStatus]. Consumable set is currently empty by
    design (no signal has earned a slot); when one does, its training/eval path
    plugs in here and it flows through the SAME promotion gate as any candidate.
    """
    statuses = []
    for name, consumable, reason in TRACKED_INPUTS:
        if not consumable:
            statuses.append(InputCandidateStatus(
                name=name, model_consumable=False, reason=reason))
            continue
        # --- consumable path (none today) ---
        # When a signal earns a slot: reconstruct it as-of-date, train
        # production-structure + input on games before the holdout, evaluate on
        # the leakage-free holdout, compare to production log-loss. Promote via
        # the same gate improve() uses. Left as the wired-in extension point.
        statuses.append(InputCandidateStatus(
            name=name, model_consumable=True,
            reason="consumable — trained + holdout-evaluated below"))
    return statuses
