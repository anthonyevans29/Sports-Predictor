"""
NHL-GOALIE lane (b), architect 2026-09-30: the goalie term for candidate v5.

"each starter's rolling save% over expected (shrunk toward league mean,
decayed), applied as a rating adjustment".

The quantity, per goalie, strictly AS OF a game (only appearances that
started >= AS_OF_GAP_H hours before it — our match clock and the API's can
differ by minutes, and a game must never see its own result):

    gsaa_rate = sum_w(saves - m * shots) / (sum_w(shots) + PRIOR_SHOTS)

  * w         = 0.5 ** (age_days / HALF_LIFE_DAYS) — exponential decay;
  * m         = the as-of league save% (decayed, blended with BOOT_SV);
  * PRIOR_SHOTS pseudo-shots at exactly league average = the shrinkage.
  * Every appearance with shots counts toward the goalie's history (relief
    included); only the STARTER's rate prices a game.

To Elo points: goals_edge = gsaa_rate x (as-of league shots per team-game),
and ELO_PER_GOAL = (400 / ln 10) x PYTH_EXP / (as-of league goals per
team-game) — the local slope of a Pythagorean win model (win% = GF^x /
(GF^x + GA^x)) at league-average scoring, i.e. what one goal per game of
prevention is worth. No fitted scale.

EVERY CONSTANT BELOW IS FIXED A PRIORI (law 3) — declared before any NHL
run, never selected on 2024 or 2025. ARCHITECT-RULE to ratify before the
operator scores v5:
  HALF_LIFE_DAYS 180  — about one season of memory, recent form weighted
  PRIOR_SHOTS   2000  — save% needs ~1,000-3,000 shots to stabilise (the
                        split-half literature); 2,000 is the middle
  PYTH_EXP       2.0  — the classic hockey Pythagorean exponent
  BOOT_*              — league priors used only while history is thin,
                        blended with pseudo-counts BOOT_SHOTS / BOOT_GAMES
  AS_OF_GAP_H      6  — no goalie plays twice within 6 hours
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

HALF_LIFE_DAYS = 180.0
PRIOR_SHOTS = 2000.0
PYTH_EXP = 2.0
BOOT_SV = 0.900
BOOT_SHOTS_PG = 30.0
BOOT_GOALS_PG = 3.0
BOOT_SHOTS = 5000.0      # pseudo-shots behind the league save% prior
BOOT_GAMES = 50.0        # pseudo team-games behind the per-game priors
AS_OF_GAP_H = 6.0
ELO_PER_LOGIT = 400.0 / math.log(10)


@dataclass(frozen=True)
class Appearance:
    start: datetime
    nhl_game_id: int
    side: str
    goalie_id: int
    shots: int
    saves: int


def _w(age_days: float) -> float:
    return 0.5 ** (max(age_days, 0.0) / HALF_LIFE_DAYS)


@dataclass
class GoalieTracker:
    """Walk-forward goalie state. Feed it every appearance (any order); it
    ingests them chronologically as games are priced (advance_to)."""
    appearances: list[Appearance]
    _i: int = 0
    _g: dict[int, list[float]] = field(default_factory=dict)       # goalie -> [shots_w, gsaa_w, t_days]
    _lg: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0])
    # league (decayed): shots, saves, team-games, goals, t_days
    _pending: dict[tuple[int, str], list[int]] = field(default_factory=dict)

    def __post_init__(self):
        self.appearances = sorted((a for a in self.appearances if a.shots is not None and a.saves is not None),
                                  key=lambda a: (a.start, a.nhl_game_id, a.side, a.goalie_id))

    @staticmethod
    def _days(t: datetime) -> float:
        return t.timestamp() / 86400.0

    def league(self) -> tuple[float, float, float]:
        """(save%, shots per team-game, goals per team-game), as of now."""
        shots, saves, games, goals, _ = self._lg
        sv = (saves + BOOT_SV * BOOT_SHOTS) / (shots + BOOT_SHOTS)
        spg = (shots + BOOT_SHOTS_PG * BOOT_GAMES) / (games + BOOT_GAMES)
        gpg = (goals + BOOT_GOALS_PG * BOOT_GAMES) / (games + BOOT_GAMES)
        return sv, spg, gpg

    def _decay_league(self, t: float) -> None:
        f = _w(t - self._lg[4]) if self._lg[4] else 1.0
        self._lg = [self._lg[0] * f, self._lg[1] * f, self._lg[2] * f, self._lg[3] * f, t]

    def _ingest(self, a: Appearance) -> None:
        t = self._days(a.start)
        m, _, _ = self.league()                        # the mean BEFORE this appearance
        g = self._g.get(a.goalie_id)
        if g is None:
            g = self._g[a.goalie_id] = [0.0, 0.0, t]
        f = _w(t - g[2])
        g[0], g[1], g[2] = g[0] * f + a.shots, g[1] * f + (a.saves - m * a.shots), t
        self._decay_league(t)
        self._lg[0] += a.shots
        self._lg[1] += a.saves
        self._lg[3] += a.shots - a.saves
        key = (a.nhl_game_id, a.side)
        if key not in self._pending:                   # one team-game per game side
            self._pending[key] = [1]
            self._lg[2] += 1.0

    def advance_to(self, t: datetime) -> None:
        cutoff = t - timedelta(hours=AS_OF_GAP_H)
        while self._i < len(self.appearances) and self.appearances[self._i].start < cutoff:
            self._ingest(self.appearances[self._i])
            self._i += 1

    def gsaa_rate(self, goalie_id: int | None, t: datetime) -> float:
        """Shrunk, decayed saves above league average per shot, as of t."""
        g = self._g.get(goalie_id) if goalie_id is not None else None
        if g is None:
            return 0.0
        f = _w(self._days(t) - g[2])
        return (g[1] * f) / (g[0] * f + PRIOR_SHOTS)

    def elo_adjustment(self, goalie_id: int | None, t: datetime) -> float:
        """Elo points for this starter (0 when unknown / no history)."""
        if goalie_id is None:
            return 0.0
        _, spg, gpg = self.league()
        goals_edge = self.gsaa_rate(goalie_id, t) * spg
        return ELO_PER_LOGIT * PYTH_EXP / gpg * goals_edge
