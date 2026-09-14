"""
League standings calculator.

Pure function that takes a list of finished Match objects and returns a sorted
league table. No DB writes, no caching — computed fresh each request. For
20-team leagues with ~380 matches this is sub-millisecond, so caching isn't
worth the invalidation complexity yet.

Ranking rules (standard FIFA/UEFA):
  1. Points (3 W, 1 D, 0 L)
  2. Goal difference
  3. Goals for
  4. Alphabetical (deterministic tie-break for display)

Some leagues use head-to-head or away goals as tie-breakers, and we'll add
that when we need league-specific accuracy. For a dashboard view, the standard
rules are close enough.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from src.db.schema import Match, MatchStatus, Result


@dataclass
class StandingRow:
    team_id: int
    team_name: str
    team_tla: str | None
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    # Last 5 results as W/D/L list, most recent last
    form: list[str] = field(default_factory=list)

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    @property
    def points(self) -> int:
        # Soccer 3/1/0. For sports without draws (baseball), drawn is always 0,
        # so this still returns 3 * wins — useful as a sort key even when the
        # table is displayed as W/L/Pct.
        return self.won * 3 + self.drawn

    @property
    def win_pct(self) -> float:
        """Win percentage — used for baseball-style standings."""
        total_decided = self.won + self.lost
        if total_decided <= 0:
            return 0.0
        return self.won / total_decided

    def as_dict(self) -> dict:
        """Detach from session-bound state for safe template use."""
        return {
            "team_id": self.team_id,
            "team_name": self.team_name,
            "team_tla": self.team_tla,
            "played": self.played,
            "won": self.won,
            "drawn": self.drawn,
            "lost": self.lost,
            "goals_for": self.goals_for,
            "goals_against": self.goals_against,
            "goal_difference": self.goal_difference,
            "points": self.points,
            "win_pct": round(self.win_pct, 3),
            "form": self.form,
        }


def compute_standings(matches: Iterable[Match], sport: str = "soccer") -> list[dict]:
    """
    Build a standings table from an iterable of finished Match objects.

    `matches` must be eager-loaded with home_team and away_team relationships
    or this will trigger lazy loads. The caller (web route) is responsible.

    For baseball, ranks by win percentage then run differential.
    For soccer, ranks by points → goal diff → goals for.

    Returns a list of dicts ordered by rank (1st = index 0).
    """
    rows: dict[int, StandingRow] = {}
    # For form: collect (utc_date, team_id, result_char) tuples, then sort
    # per-team by date and keep the last 5.
    form_entries: dict[int, list[tuple]] = {}

    for m in matches:
        if m.status != MatchStatus.FINISHED:
            continue
        if m.home_score is None or m.away_score is None:
            continue

        home = m.home_team
        away = m.away_team
        if not home or not away:
            continue

        # Ensure each team has a row
        for t in (home, away):
            if t.id not in rows:
                rows[t.id] = StandingRow(
                    team_id=t.id, team_name=t.name, team_tla=t.tla
                )
                form_entries[t.id] = []

        h_row = rows[home.id]
        a_row = rows[away.id]
        h_row.played += 1
        a_row.played += 1
        h_row.goals_for += m.home_score
        h_row.goals_against += m.away_score
        a_row.goals_for += m.away_score
        a_row.goals_against += m.home_score

        # Result for form + W/D/L
        if m.home_score > m.away_score:
            h_row.won += 1
            a_row.lost += 1
            form_entries[home.id].append((m.utc_date, "W"))
            form_entries[away.id].append((m.utc_date, "L"))
        elif m.home_score < m.away_score:
            a_row.won += 1
            h_row.lost += 1
            form_entries[home.id].append((m.utc_date, "L"))
            form_entries[away.id].append((m.utc_date, "W"))
        else:
            h_row.drawn += 1
            a_row.drawn += 1
            form_entries[home.id].append((m.utc_date, "D"))
            form_entries[away.id].append((m.utc_date, "D"))

    # Attach form (last 5, oldest → newest visually)
    for team_id, row in rows.items():
        entries = sorted(form_entries.get(team_id, []), key=lambda x: x[0])
        row.form = [r for (_dt, r) in entries[-5:]]

    if sport == "baseball":
        # Baseball: rank by win pct desc, then run differential desc.
        ranked = sorted(
            rows.values(),
            key=lambda r: (-r.win_pct, -r.goal_difference, r.team_name.lower()),
        )
    else:
        # Soccer / default: points → GD → GF → name
        ranked = sorted(
            rows.values(),
            key=lambda r: (-r.points, -r.goal_difference, -r.goals_for, r.team_name.lower()),
        )
    return [r.as_dict() for r in ranked]
