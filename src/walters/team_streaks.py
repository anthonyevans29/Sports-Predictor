"""
Team-level streak KPIs — a tracked property of each club, derived from finished
games. This is NOT a prediction input; it's a high-level KPI for the team
profile (like a stat you'd glance at), computed on demand from Match rows.

"Average winning streak length" = mean length of the team's winning streaks over
the games considered. A team that goes W W L W W W L has two winning streaks
(length 2 and 3) → average 2.5. Games are ordered by date; ties/draws (rare in
MLB, absent) break a streak.
"""
from __future__ import annotations

from sqlalchemy import select, or_

from src.db.schema import Match, MatchStatus


def team_results_chrono(s, team_id: int, season: str | None = None) -> list[bool]:
    """Ordered list of True(win)/False(loss) for a team's finished games."""
    q = (
        select(Match)
        .where(
            or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
            Match.status == MatchStatus.FINISHED,
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
        )
        .order_by(Match.utc_date.asc())
    )
    if season is not None:
        q = q.where(Match.season == season)
    out = []
    for m in s.execute(q).scalars():
        is_home = m.home_team_id == team_id
        won = (m.home_score > m.away_score) if is_home else (m.away_score > m.home_score)
        out.append(bool(won))
    return out


def streak_kpis(results: list[bool]) -> dict:
    """
    From an ordered W/L list, compute streak KPIs:
      games, wins, win_pct, current_streak (+n win / -n loss),
      longest_win_streak, num_win_streaks, avg_win_streak_len.
    """
    n = len(results)
    if n == 0:
        return {"games": 0, "wins": 0, "win_pct": None, "current_streak": 0,
                "longest_win_streak": 0, "num_win_streaks": 0,
                "avg_win_streak_len": None}

    wins = sum(results)
    # collect lengths of consecutive winning runs
    win_runs: list[int] = []
    run = 0
    for w in results:
        if w:
            run += 1
        else:
            if run > 0:
                win_runs.append(run)
            run = 0
    if run > 0:
        win_runs.append(run)

    # current streak: sign = win/loss, magnitude = length of the trailing run
    cur = 0
    last = results[-1]
    for w in reversed(results):
        if w == last:
            cur += 1
        else:
            break
    current_streak = cur if last else -cur

    return {
        "games": n,
        "wins": wins,
        "win_pct": round(wins / n, 3),
        "current_streak": current_streak,
        "longest_win_streak": max(win_runs) if win_runs else 0,
        "num_win_streaks": len(win_runs),
        "avg_win_streak_len": round(sum(win_runs) / len(win_runs), 2) if win_runs else None,
    }


def team_streak_kpis(s, team_id: int, season: str | None = None) -> dict:
    return streak_kpis(team_results_chrono(s, team_id, season))
