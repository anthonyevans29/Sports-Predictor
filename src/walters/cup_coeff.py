"""
Cup fix-v2 (architect spec 2026-09-25): tune the cup path's elo_goal_coeff
in TWO contexts — same-league ties (both clubs' domestic leagues equal) and
cross-league ties — by as-of, leave-self-out log-loss on PRIOR cup matches,
EXCLUDING the exam's competition-seasons.

Why: rulings 5/6 made cup strengths own-league-relative and delegated
cross-league separation to Elo + bonus, but the PL-tuned 0.0008 mutes that
delegate — strong lower-division sides price as tier-equals.

Mechanics:
  * pool = every FINISHED match of every CUP/INTL soccer competition-season in
    the DB, minus the exam's: the key's own (comp, season) pairs AND the
    EFL / CL / UEL (+ EL alias) competitions in every season the key covers;
  * each pool fixture is priced on the EXACT shipped cup path in report-only
    mode (as-of leave-self-out strengths, ruling B) at every grid coeff in one
    pass (cup_coeff_grid); nothing is written;
  * the two contexts are separable (a fixture's coeff comes from its own
    context only), so each context takes the grid value minimizing its mean
    3-way log-loss vs the 90-minute-labelled result; ties -> the smaller coeff
    (grid is ascending from the status quo 0.0008).
Read-only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# FROZEN a priori (logged in BACKLOG before any run). Ascending from the
# status quo so an exact tie keeps the smaller, closer-to-current value.
CUP_COEFF_GRID: tuple[float, ...] = (0.0008, 0.0012, 0.0016, 0.0020, 0.0024,
                                     0.0030, 0.0040, 0.0050)
CONTEXTS = ("same_league", "cross_league")
EXAM_COMPS = {"EFL", "CL", "UEL", "EL"}   # EL = the adapter's alias for UEL


def exam_exclusions(key_rows: list[dict], key_seasons: set[str]) -> set[tuple[str, str]]:
    """(comp, season) pairs that must never enter tuning: the key's own pairs
    plus every EFL/CL/UEL/EL competition in every season the key covers."""
    out = {(r["comp"], s) for r in key_rows for s in key_seasons}
    out |= {(c, s) for c in EXAM_COMPS for s in key_seasons}
    return out


def _outcome_index(hs: int, as_: int) -> int:
    return 0 if hs > as_ else (2 if as_ > hs else 1)


@dataclass
class CoeffTuning:
    pool: list[tuple[str, str]] = field(default_factory=list)
    table: dict[str, list[tuple[float, float | None, int]]] = field(default_factory=dict)
    best: dict[str, float] = field(default_factory=dict)
    n: dict[str, int] = field(default_factory=dict)
    market_only: int = 0


def select_from_losses(losses: dict[str, dict[float, list[float]]],
                       grid: tuple[float, ...]) -> CoeffTuning:
    """Pure: per-context argmin of mean loss over the grid (first in grid order
    on ties). A context with no rows gets no entry — the base coeff applies."""
    t = CoeffTuning()
    for ctx in CONTEXTS:
        rows = []
        for c in grid:
            xs = losses.get(ctx, {}).get(c, [])
            rows.append((c, (sum(xs) / len(xs)) if xs else None, len(xs)))
        t.table[ctx] = rows
        t.n[ctx] = rows[0][2]
        scored = [r for r in rows if r[1] is not None]
        if scored:
            t.best[ctx] = min(scored, key=lambda r: r[1])[0]   # min() keeps the first
    return t


def tuning_pool(exclude: set[tuple[str, str]]) -> list[tuple[str, str]]:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport

    with session_scope() as s:
        pairs = s.execute(
            select(Competition.code, Match.season).distinct()
            .join(Match, Match.competition_id == Competition.id)
            .where(Competition.sport == Sport.SOCCER,
                   Competition.type.in_(("CUP", "INTL")),
                   Match.status == MatchStatus.FINISHED)
        ).all()
    return sorted((c, se) for c, se in pairs if (c, se) not in exclude)


def tune_cup_coeffs(exclude: set[tuple[str, str]],
                    grid: tuple[float, ...] = CUP_COEFF_GRID) -> CoeffTuning:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus
    from src.walters.training import _generate_predictions_soccer

    pool = tuning_pool(exclude)
    losses: dict[str, dict[float, list[float]]] = {c: {g: [] for g in grid} for c in CONTEXTS}
    market_only = 0
    for code, season in pool:
        rows = _generate_predictions_soccer(code, season, include_finished=True,
                                            cup_coeff_grid=grid)
        ids = [r["match_id"] for r in rows if "grid_probs" in r]
        with session_scope() as s:
            done = {m.id: (m.home_score, m.away_score) for m in s.execute(
                select(Match).where(Match.id.in_(ids), Match.status == MatchStatus.FINISHED,
                                    Match.home_score.is_not(None),
                                    Match.away_score.is_not(None))).scalars()}
        for r in rows:
            if r.get("market_only"):
                market_only += 1
                continue
            if r["match_id"] not in done:          # scheduled rows: nothing to score
                continue
            y = _outcome_index(*done[r["match_id"]])
            for c, probs in r["grid_probs"].items():
                losses[r["cup_context"]][c].append(-math.log(max(probs[y], 1e-12)))
    t = select_from_losses(losses, grid)
    t.pool, t.market_only = pool, market_only
    return t
