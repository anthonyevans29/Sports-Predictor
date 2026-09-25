"""
NHL Elo v1 (H-track Phase 2, 2026-09-25) — margin-of-victory + per-team
season regression, NOTHING ELSE (architect spec). OT/SO weighting, back-to-
back rest and goalie injuries are R-track hypotheses, not v1 features.

Cloned from the NFL v1 shape (src/walters/nfl_backtest.py). Parameters are
FIXED A PRIORI — set before any NHL data run and never tuned on the 2025
test season (law 3):
  * k_factor 6.0 — NFL's 20 scaled for 82-game seasons and a noisier sport
    (more games, smaller per-game information); an a-priori prior.
  * mov_base 2.2 — the NFL multiplier form verbatim: ln(|margin|+1) ·
    base/(base + winner_elo_gap·0.001). OT/SO wins are 1-goal margins
    (provider totals include the deciding goal) — no special weighting.
  * season_regression 0.25 — NFL clone; a club regresses toward 1500 at
    ITS first game of a new season (stream-interleaving-immune).
  * home_advantage — NOT a memory value: derived from the TRAIN season's
    realized home-win rate (400·log10(p/(1-p))), frozen before scoring.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NHLEloConfig:
    k_factor: float = 6.0
    mov_base: float = 2.2
    season_regression: float = 0.25
    default_rating: float = 1500.0
    home_advantage: float = 0.0


def home_advantage_from_rate(p_home: float) -> float:
    """Elo points that make two equal teams price at the observed home rate."""
    p = min(max(p_home, 1e-6), 1 - 1e-6)
    return 400.0 * math.log10(p / (1 - p))


@dataclass
class NHLEloV1:
    cfg: NHLEloConfig = field(default_factory=NHLEloConfig)
    _ratings: dict[int, float] = field(default_factory=dict)
    _last_season: dict[int, str] = field(default_factory=dict)

    name = "nhl_elo_v1"

    def rating(self, team_id: int) -> float:
        return self._ratings.get(team_id, self.cfg.default_rating)

    def _regress_if_new_season(self, team_id: int, season: str) -> None:
        prev = self._last_season.get(team_id)
        if prev is not None and prev != season:
            r = self.rating(team_id)
            self._ratings[team_id] = r + self.cfg.season_regression * (self.cfg.default_rating - r)
        self._last_season[team_id] = season

    def _expected_home(self, home_id: int, away_id: int) -> float:
        diff = self.rating(away_id) - (self.rating(home_id) + self.cfg.home_advantage)
        return 1.0 / (1.0 + 10 ** (diff / 400.0))

    def predict(self, g) -> float:
        # Regression is part of the rating a game is priced on: a club's
        # first game of a new season prices on its regressed rating.
        for tid in (g.home_id, g.away_id):
            self._regress_if_new_season(tid, g.season)
        return self._expected_home(g.home_id, g.away_id)

    def update(self, g) -> None:
        for tid in (g.home_id, g.away_id):
            self._regress_if_new_season(tid, g.season)
        exp_h = self._expected_home(g.home_id, g.away_id)
        won = 1.0 if g.home_score > g.away_score else 0.0
        rh, ra = self.rating(g.home_id), self.rating(g.away_id)
        gap = (rh + self.cfg.home_advantage - ra) if won else (ra - rh - self.cfg.home_advantage)
        margin = abs(g.home_score - g.away_score)
        mov = math.log(margin + 1.0) * (self.cfg.mov_base / (self.cfg.mov_base + max(gap, 0.0) * 0.001))
        delta = self.cfg.k_factor * mov * (won - exp_h)
        self._ratings[g.home_id] = rh + delta
        self._ratings[g.away_id] = ra - delta

    def ratings(self) -> dict[int, float]:
        return dict(self._ratings)
