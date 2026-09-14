"""
Elo rating engine.

Each team carries a separate Elo rating per competition. PL Elo and FA Cup Elo
are different rooms — talent pools, intensity, and home advantage all differ.
Mixing them poisons both ratings.

Standard FIDE-style Elo formula, with two soccer-specific extensions:

  1. Goal-difference weighting (per Hvattum & Arntzen 2010, FootballClubElo):
     a 4-0 moves ratings more than a 1-0. We use the same multiplier they do:
     mult = 1 + ln(1 + |gd|) so 1-0 = 1.0x, 2-0 = 1.10x, 3-0 = 1.39x, 4-0 = 1.61x.

  2. Home advantage as a rating bonus applied only at evaluation time
     (not stored in the rating). Calibrated per competition.

Pure functions — no DB access. The training loop in walters/training.py
loads matches, calls these, persists results.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable


#: Default starting rating for a brand-new team. The absolute value doesn't
#: matter (it's all relative); 1500 is the conventional starting point.
DEFAULT_RATING = 1500.0

#: Default K-factor — how much one match can move a rating. Higher = more
#: reactive (good for short seasons, bad for noisy results). 20 is a common
#: soccer value; FootballClubElo uses 30 with a margin multiplier.
DEFAULT_K = 20.0

#: Default home advantage in rating points. Roughly 65 pts ≈ a 60% home
#: win rate in evenly-matched teams, which matches the PL long-run baseline.
DEFAULT_HOME_ADVANTAGE = 65.0


@dataclass
class EloConfig:
    k_factor: float = DEFAULT_K
    home_advantage: float = DEFAULT_HOME_ADVANTAGE
    starting_rating: float = DEFAULT_RATING

    #: Damping toward starting rating between seasons. 0.25 = pull each
    #: rating 25% of the way back to the mean. Prevents stale strong teams.
    season_regression: float = 0.25

    def as_dict(self) -> dict:
        return {
            "k_factor": self.k_factor,
            "home_advantage": self.home_advantage,
            "starting_rating": self.starting_rating,
            "season_regression": self.season_regression,
        }


@dataclass
class EloState:
    """In-memory rating table for one competition."""

    ratings: dict[int, float] = field(default_factory=dict)  # team_id -> rating
    config: EloConfig = field(default_factory=EloConfig)

    def get(self, team_id: int) -> float:
        return self.ratings.get(team_id, self.config.starting_rating)

    def set(self, team_id: int, rating: float) -> None:
        self.ratings[team_id] = rating

    def as_dict(self) -> dict:
        return {
            "config": self.config.as_dict(),
            "ratings": {str(k): v for k, v in self.ratings.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EloState":
        cfg = EloConfig(**data.get("config", {}))
        ratings = {int(k): float(v) for k, v in data.get("ratings", {}).items()}
        return cls(ratings=ratings, config=cfg)


# --------------------------------------------------------------------------
# Pure math
# --------------------------------------------------------------------------


def expected_score(rating_a: float, rating_b: float) -> float:
    """Probability team A beats team B. Excludes draws — for soccer we'll
    convert this into a 3-way distribution via the Poisson model."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def goal_diff_multiplier(home_score: int, away_score: int) -> float:
    """Larger margins move ratings more. Caps at a soft asymptote."""
    gd = abs(home_score - away_score)
    if gd <= 1:
        return 1.0
    return 1.0 + math.log(gd)


def update_after_match(
    home_rating: float,
    away_rating: float,
    home_score: int,
    away_score: int,
    config: EloConfig,
) -> tuple[float, float]:
    """
    Return new (home_rating, away_rating) after one finished match.

    `home_score` and `away_score` are full-time goals.
    """
    # Home advantage shifts the expectation but is NOT added to the rating
    # we store — it's a kickoff condition, not skill.
    eff_home = home_rating + config.home_advantage
    expected_home = expected_score(eff_home, away_rating)

    # Actual result encoded as a 0..1 score for the home side
    if home_score > away_score:
        actual_home = 1.0
    elif home_score < away_score:
        actual_home = 0.0
    else:
        actual_home = 0.5

    mult = goal_diff_multiplier(home_score, away_score)
    delta = config.k_factor * mult * (actual_home - expected_home)

    return home_rating + delta, away_rating - delta


def apply_season_regression(state: EloState) -> None:
    """
    Pull each rating partway back to the starting rating. Called between
    seasons so teams don't carry full historical strength forever (real
    teams turn over, managers leave, players age).
    """
    r = state.config.season_regression
    mean = state.config.starting_rating
    for team_id in list(state.ratings.keys()):
        cur = state.ratings[team_id]
        state.ratings[team_id] = cur + r * (mean - cur)


# --------------------------------------------------------------------------
# Bulk training: feed in chronologically sorted matches
# --------------------------------------------------------------------------


@dataclass
class TrainMatch:
    """Minimal match info needed to update Elo. Decouples from ORM."""

    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int
    season: str


def train(
    matches: Iterable[TrainMatch],
    config: EloConfig | None = None,
) -> EloState:
    """
    Run Elo through a chronologically sorted list of finished matches.
    Returns the final state.

    The caller is responsible for chronological ordering and for filtering
    out unfinished or score-less matches.
    """
    state = EloState(config=config or EloConfig())
    last_season: str | None = None

    for m in matches:
        # Between-season regression to the mean
        if last_season is not None and m.season != last_season:
            apply_season_regression(state)
        last_season = m.season

        home_r = state.get(m.home_team_id)
        away_r = state.get(m.away_team_id)
        new_home, new_away = update_after_match(
            home_r, away_r, m.home_score, m.away_score, state.config
        )
        state.set(m.home_team_id, new_home)
        state.set(m.away_team_id, new_away)

    return state
