"""
NCAA Elo v1 (#79, architect ruling 2026-09-30) — a plain Elo candidate for
college football: margin-of-victory + per-team season regression, NOTHING
ELSE. Candidate only: no production wiring, no predictions written. NCAA
stays market-only until this passes its own frozen gate
(src/walters/ncaa_backtest.py) and the architect rules.

The update math is the NFL Elo form (src/walters/nfl_backtest.py, the live
nfl_elo_v1) verbatim; the pricing/regression semantics are the NHL v1's
(src/models/nhl_elo.py: a team regresses at ITS first game of a new season,
and that game already prices on the regressed rating). The market is never
an input.

ALL CONSTANTS FIXED A PRIORI — declared in code and BACKLOG before any real-
data run; NO selection on any data (no grid, no walk-forward), never tuned
on the 2026 test season (law 3). Each is ARCHITECT-RULE:
  * k_factor 24.0 — NFL's 20 scaled for the shorter college season:
    20·sqrt(17/12) = 23.8 -> 24 (fewer games per team to find a level, with
    far more programs starting from the default).
  * home_advantage 55.0 Elo — NFL's 48 Elo ≈ 2.5 points of spread
    (19.2 Elo/pt); the conventional college home edge is ~3 points:
    3 × 19.2 = 57.6, rounded DOWN to 55 (toward the NFL value). NOT derived
    from the train home rate as the NHL v1 did: college home rates are
    inflated by scheduling (FBS programs host FCS "buy games"), and rating
    differences already carry that mismatch — deriving it would count the
    mismatch twice.
  * mov_base 2.2 — the NFL multiplier verbatim: ln(|margin|+1) ·
    base/(base + winner_elo_gap·0.001). Its autocorrelation term damps the
    40-point favourite blowouts college football is full of.
  * season_regression 0.25 — the NFL clone. Two college effects pull in
    opposite directions (more roster turnover argues for more; divisional
    stratification — lower-division programs sit far below the 1500 mean —
    argues for less), so the house value stands.
  * default_rating 1500 — a program with no prior game (FCS / lower-
    division programs appear rarely) prices at the mean: no information =
    no claim (law 4). The gate counts those cold-start test games.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NCAAEloConfig:
    k_factor: float = 24.0
    home_advantage: float = 55.0
    mov_base: float = 2.2
    season_regression: float = 0.25
    default_rating: float = 1500.0


@dataclass
class NCAAEloV1:
    cfg: NCAAEloConfig = field(default_factory=NCAAEloConfig)
    _ratings: dict[int, float] = field(default_factory=dict)
    _last_season: dict[int, str] = field(default_factory=dict)

    name = "ncaa_elo_v1"

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
