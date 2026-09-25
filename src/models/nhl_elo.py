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


# --------------------------------------------------------------------------
# v2 candidate (architect scope 2026-09-25): retuned params + ONE feature,
# rest days. Nothing else.
# --------------------------------------------------------------------------

B2B_HOURS = 36.0      # < 36h since the previous start = back-to-back
RESTED_HOURS = 120.0  # >= 5 days (or no previous game) = fully rested


def rest_adjustment(rest_h: float | None, b2b_penalty: float, rest_per_day: float) -> float:
    """Additive Elo adjustment for one team, back-to-back emphasised:
    B2B -> -b2b_penalty; otherwise +rest_per_day per extra day off beyond
    the standard one (2 days between starts = 0), capped at +2 days. No
    previous game / a long break counts as fully rested (+2)."""
    if rest_h is None or rest_h >= RESTED_HOURS:
        return 2 * rest_per_day
    if rest_h < B2B_HOURS:
        return -b2b_penalty
    days = int(rest_h / 24.0 + 0.5)   # half-up (Python's round() is banker's)
    extra = min(max(days - 2, 0), 2)
    return extra * rest_per_day


@dataclass(frozen=True)
class NHLEloConfigV2(NHLEloConfig):
    b2b_penalty: float = 0.0
    rest_per_day: float = 0.0


@dataclass
class NHLEloV2(NHLEloV1):
    """v1 + rest. The adjustment sits inside the expected score used by BOTH
    predict and update, so ratings don't absorb scheduling fatigue."""
    cfg: NHLEloConfigV2 = field(default_factory=NHLEloConfigV2)

    name = "nhl_elo_v2"

    def _rest_diff(self, g) -> float:
        h = rest_adjustment(getattr(g, "home_rest_h", None), self.cfg.b2b_penalty, self.cfg.rest_per_day)
        a = rest_adjustment(getattr(g, "away_rest_h", None), self.cfg.b2b_penalty, self.cfg.rest_per_day)
        return h - a

    def _expected_game(self, g) -> float:
        diff = (self.rating(g.away_id)
                - (self.rating(g.home_id) + self.cfg.home_advantage + self._rest_diff(g)))
        return 1.0 / (1.0 + 10 ** (diff / 400.0))

    def predict(self, g) -> float:
        for tid in (g.home_id, g.away_id):
            self._regress_if_new_season(tid, g.season)
        return self._expected_game(g)

    def update(self, g) -> None:
        for tid in (g.home_id, g.away_id):
            self._regress_if_new_season(tid, g.season)
        exp_h = self._expected_game(g)
        won = 1.0 if g.home_score > g.away_score else 0.0
        rh, ra = self.rating(g.home_id), self.rating(g.away_id)
        edge = self.cfg.home_advantage + self._rest_diff(g)
        gap = (rh + edge - ra) if won else (ra - rh - edge)
        margin = abs(g.home_score - g.away_score)
        mov = math.log(margin + 1.0) * (self.cfg.mov_base / (self.cfg.mov_base + max(gap, 0.0) * 0.001))
        delta = self.cfg.k_factor * mov * (won - exp_h)
        self._ratings[g.home_id] = rh + delta
        self._ratings[g.away_id] = ra - delta


@dataclass
class NHLEloV3(NHLEloV2):
    """Same model form as v2 (MOV + regression + rest); v3 differs only in
    how its parameters are SELECTED (walk-forward validation inside 2024)."""
    name = "nhl_elo_v3"
