"""
Team bullpen EFFECTIVENESS — reliever-only run prevention over a window.

Distinct from bullpen AVAILABILITY (who's rested, which we already track). This
is how well the relievers have PITCHED: bullpen ERA, WHIP, K/9 over a trailing
window, derived from the per-appearance effectiveness fields (earned_runs, hits,
walks, strikeouts, outs) captured from the boxscore.

HONEST NOTE on where this can add signal: the model already estimates each
team's run prevention via the RA side of its Pythagorean profile, and bullpen
innings are PART of team RA — so bullpen quality is PARTIALLY already in the
model. Where this might add information beyond team RA is the RECENT / fatigued
/ trending piece that season-long RA lags on. That's the hypothesis to validate
(Stage-1: does bullpen effectiveness predict residuals AFTER controlling for team
RA?), not an assumption. Tracked as used_in_model: false until it proves out.

Team-level here; per-appearance rows keep pitcher_id so a reliever-level view
(tracking individual relievers like we do starters) can be built on the same
data later without re-capture.
"""
from __future__ import annotations

from datetime import timedelta
from collections import defaultdict

from sqlalchemy import select

from src.db.schema import PitcherAppearance


def team_bullpen_effectiveness(s, team_source_id: str, as_of, window_days: int = 30) -> dict | None:
    """
    Reliever-only effectiveness for a team over the `window_days` before `as_of`.
    Returns {bullpen_era, whip, k_per_9, innings, appearances, earned_runs} or
    None if no reliever data in window. Leakage-safe: strictly before as_of.
    """
    if not team_source_id or as_of is None:
        return None
    start = as_of - timedelta(days=window_days)
    rows = list(s.execute(
        select(PitcherAppearance).where(
            PitcherAppearance.team_source_id == team_source_id,
            PitcherAppearance.is_starter == False,  # noqa: E712
            PitcherAppearance.game_date >= start,
            PitcherAppearance.game_date < as_of,
        )
    ).scalars())
    # only rows that actually have effectiveness captured
    rows = [r for r in rows if r.outs is not None and r.earned_runs is not None]
    if not rows:
        return None

    total_outs = sum(r.outs or 0 for r in rows)
    if total_outs == 0:
        return None
    innings = total_outs / 3.0
    er = sum(r.earned_runs or 0 for r in rows)
    hits = sum(r.hits_allowed or 0 for r in rows)
    bb = sum(r.walks_allowed or 0 for r in rows)
    k = sum(r.strikeouts or 0 for r in rows)

    era = (er * 9.0) / innings if innings > 0 else None
    whip = (hits + bb) / innings if innings > 0 else None
    k9 = (k * 9.0) / innings if innings > 0 else None

    return {
        "bullpen_era": round(era, 2) if era is not None else None,
        "whip": round(whip, 2) if whip is not None else None,
        "k_per_9": round(k9, 1) if k9 is not None else None,
        "innings": round(innings, 1),
        "appearances": len(rows),
        "earned_runs": er,
        "window_days": window_days,
    }


def all_teams_bullpen_effectiveness(s, as_of, window_days: int = 30) -> dict:
    """{team_source_id: effectiveness dict} for every team with reliever data."""
    start = as_of - timedelta(days=window_days)
    rows = list(s.execute(
        select(PitcherAppearance).where(
            PitcherAppearance.is_starter == False,  # noqa: E712
            PitcherAppearance.game_date >= start,
            PitcherAppearance.game_date < as_of,
        )
    ).scalars())
    by_team = defaultdict(list)
    for r in rows:
        if r.team_source_id and r.outs is not None and r.earned_runs is not None:
            by_team[r.team_source_id].append(r)

    out = {}
    for tid, rs in by_team.items():
        total_outs = sum(r.outs or 0 for r in rs)
        if total_outs == 0:
            continue
        innings = total_outs / 3.0
        er = sum(r.earned_runs or 0 for r in rs)
        hits = sum(r.hits_allowed or 0 for r in rs)
        bb = sum(r.walks_allowed or 0 for r in rs)
        k = sum(r.strikeouts or 0 for r in rs)
        out[tid] = {
            "bullpen_era": round(er * 9.0 / innings, 2) if innings else None,
            "whip": round((hits + bb) / innings, 2) if innings else None,
            "k_per_9": round(k * 9.0 / innings, 1) if innings else None,
            "innings": round(innings, 1),
            "appearances": len(rs),
        }
    return out
