"""The record against the close: one helper, so every family's record block reads alike.

ARCHITECT 2026-10-13 17:15 ET (addendum 63 item 3), verbatim: "Every results export (NFL, MLB, PL, and the INTL and NHL
grades) carries, in its record block, over the decided games that have a close: the games, the model's log-loss, the
close's, the paired difference close minus model, its bootstrap 95% interval on the paired per-game differences
(10,000 resamples, a fixed seed), and the count of games the model beat the close. The Cockpit shows that line beside
the win rate. A win rate is never printed without it."

Each family feeds `block()` one pair per decided game with a close: the model's probability of the outcome that
happened, and the close's probability of the same outcome, both as the record's own rows carry them (so the file
reconciles with any reader that recomputes it from the rows). A game with no close, or no decided outcome (an NFL tie
is a push), is not fed. Per game, the log-loss is -ln(max(p, 1e-12)), the floor every grade here uses; the paired
difference is the close's log-loss minus the model's, so a positive mean is the model ahead; the model beat the close
in a game where its log-loss is strictly lower (a tie is not a beat). The interval is a percentile bootstrap (the
250th and 9,750th of the 10,000 sorted resampled means) of the mean difference, resampling games, with a seed pinned
to the ruling's date; fewer than two games have no interval. The block is a function of the set of games, never of
their order (the pairs are sorted first), and carries no negative zero, so the laptop's file and the host's agree on
the same games and the Cockpit prints the file's figures as Python does.
"""
from __future__ import annotations

import math
import random

SEED = 20261013          # pinned: the ruling's date (the repo's convention for seeded bootstraps)
RESAMPLES = 10_000       # the ruling's count
EPS = 1e-12              # the log-loss floor of every grade here (evaluation._log_loss_one, the NFL and INTL rows)
RULE = ("over the decided games that have a close: per game, log-loss -ln(max(p, 1e-12)) of the outcome that happened; "
        "close minus model; the model beat the close where its log-loss is strictly lower; a percentile bootstrap "
        "(2.5, 97.5) of the mean difference over games, 10,000 resamples, seed 20261013 (ARCHITECT 2026-10-13, "
        "addendum 63 item 3)")


def log_loss(p: float) -> float:
    """The log-loss of one game: -ln of the probability given to the outcome that happened, floored at 1e-12."""
    return -math.log(max(float(p), EPS))


def _ci(d: list[float], seed: int, resamples: int) -> list[float] | None:
    """Percentile bootstrap 95% interval of the mean of d, resampling games with replacement. None under two games.

    Pure Python's random.Random, as unl_ladders.skew_test and mlb_actionable.bootstrap_ci: its stream is the same on
    every machine, so the laptop's file and the host's agree on the same games (deploy/hosting/compare_exports.py
    diffs every field before a tag). numpy's Generator promises no stream across its versions."""
    n = len(d)
    if n < 2:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(d, k=n)) / n for _ in range(resamples))
    return [_r4(means[int(0.025 * resamples)]), _r4(means[int(0.975 * resamples) - 1])]


def _r4(x: float) -> float:
    """Four places, and never a negative zero (the Cockpit prints the file's figures and must print the same)."""
    return round(x, 4) + 0.0


def block(pairs, seed: int = SEED, resamples: int = RESAMPLES) -> dict:
    """The record's line against the close, from (model p of the outcome, close p of the outcome) per decided game
    with a close. Every key is always present; with no game the figures are null and the count 0."""
    # sorted first: the block is a function of the set of games, never of their order, which comes from machine-local
    # ids or SQLite's order among games at one kickoff (the laptop's file and the host's must agree on the same games)
    pairs = sorted((float(m), float(c)) for m, c in pairs)
    out = {"games": len(pairs), "model_log_loss": None, "close_log_loss": None, "close_minus_model": None,
           "ci95": None, "model_beat_close": 0, "resamples": resamples, "seed": seed}
    if not pairs:
        return out
    lm = [log_loss(m) for m, _ in pairs]
    lc = [log_loss(c) for _, c in pairs]
    d = [c - m for m, c in zip(lm, lc)]
    n = len(d)
    out.update({"model_log_loss": _r4(sum(lm) / n), "close_log_loss": _r4(sum(lc) / n),
                "close_minus_model": _r4(sum(d) / n), "ci95": _ci(d, seed, resamples),
                "model_beat_close": sum(1 for x in d if x > 0)})
    return out


def line(b: dict | None) -> str:
    """The printed line, beside every win rate. It never prints a figure the block does not hold."""
    if not b:
        return "vs close: not computed"
    n = b.get("games") or 0
    if not n:
        return "vs close: no decided game with a close"
    ci = b.get("ci95")
    interval = (f"95% {ci[0]:+.4f} to {ci[1]:+.4f}, {b.get('resamples', RESAMPLES):,} resamples, seed "
                f"{b.get('seed', SEED)}" if ci else "no interval under two games")
    k = b.get("kalshi_only_closes") or 0
    return (f"vs close: {n} game{'' if n == 1 else 's'} · model {b['model_log_loss']:.4f} · close "
            f"{b['close_log_loss']:.4f} · close − model {b['close_minus_model']:+.4f} ({interval}) · model beat the "
            f"close {b['model_beat_close']}/{n}" + (f" · {k} of the closes the Kalshi-only mid" if k else ""))


#: the outcome letters every results row uses, to the close's side names
SIDE = {"H": "HOME", "D": "DRAW", "A": "AWAY"}


def pair_from_row(row: dict) -> tuple[float, float] | None:
    """(model p, close p) of the outcome that happened, from a results row as the exports write it: predicted.{home_win,
    draw, away_win}_prob, actual.result (H/D/A; from the scores where it is null), graded.close_fair {HOME, (DRAW,) AWAY}. None when the row is not a
    decided game with a close: no close, a push, no result, or a probability missing for the outcome that happened."""
    g = row.get("graded") or {}
    if g.get("push"):
        return None
    act = row.get("actual") or {}
    res = act.get("result")
    if res is None and act.get("home_score") is not None and act.get("away_score") is not None:
        # the MLB row copies Match.full_time_result, which can be null on a scored game; the grade itself reads the
        # scores (evaluation.score_winner), so the outcome is read from them here too
        hs, aw = act["home_score"], act["away_score"]
        res = "H" if hs > aw else "A" if aw > hs else "D"
    side = SIDE.get(res or "")
    fair = g.get("close_fair")
    if not side or not isinstance(fair, dict) or fair.get(side) is None:
        return None
    pred = row.get("predicted") or {}
    p = pred.get({"HOME": "home_win_prob", "DRAW": "draw_prob", "AWAY": "away_win_prob"}[side])
    if p is None and side != "DRAW":     # a two-way row may carry only the home probability (the NFL export)
        h = pred.get("home_win_prob")
        p = None if h is None else (h if side == "HOME" else 1.0 - float(h))
    if p is None:
        return None
    return float(p), float(fair[side])


def block_from_rows(rows, seed: int = SEED, resamples: int = RESAMPLES) -> dict:
    """The block over a results file's rows: every decided row with a close, as pair_from_row reads it. Rows that
    carry the grading close's reference (MLB, PL, NFL: books, the Kalshi-only mid, ARCHITECT 2026-10-05, or the
    session's Kalshi mid for a stale book stamp, 2026-10-19 addendum 137 item 4) also say how many of the closes fed
    were a Kalshi mid (`kalshi_only_closes`: "the `kalshi_only_closes` count in the record block already exists for
    this"), so the line never hides which close it read."""
    rows = list(rows)
    fed = [(r, p) for r, p in ((r, pair_from_row(r)) for r in rows) if p is not None]
    out = block([p for _, p in fed], seed, resamples)
    if any("close_reference" in (r.get("graded") or {}) for r in rows):
        out["kalshi_only_closes"] = sum(1 for r, _ in fed if (r.get("graded") or {}).get("close_reference")
                                        in ("kalshi_only", "kalshi"))
    return out


def outcome_row(pred, oc, graded: dict) -> dict:
    """A stored prediction and its graded outcome in the results row's shape, with the close block a results row
    carries (`graded`), so a record read from the database reads its games as the results file does."""
    return {"predicted": {"home_win_prob": getattr(pred, "home_win_prob", None),
                          "draw_prob": getattr(pred, "draw_prob", None),
                          "away_win_prob": getattr(pred, "away_win_prob", None)},
            "actual": {"home_score": oc.actual_home_score, "away_score": oc.actual_away_score,
                       "result": oc.actual_result.value if oc.actual_result else None},
            "graded": graded}


def block_from_outcomes(s, rows, seed: int = SEED, resamples: int = RESAMPLES) -> dict:
    """The block over stored (Prediction, PredictionOutcome, Match) rows, each against THE grading close
    (close.grading_close_block, as the MLB and PL results rows read it). ARCHITECT 2026-10-13 (addendum 64 item 2):
    "A win rate of the model's own picks carries the line against the close" (calibration, the web dashboard)."""
    from src.walters.close import grading_close_block
    return block_from_rows((outcome_row(p, oc, grading_close_block(s, m)) for p, oc, m in rows), seed, resamples)
