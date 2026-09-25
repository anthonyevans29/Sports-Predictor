"""
Poisson scoring model.

Given two teams' Elo ratings and their attack/defense scoring rates,
produces:
  - Expected goals for each side (xG_home, xG_away)
  - Probability matrix over discrete scorelines (0-0, 1-0, 1-1, …)
  - 1X2 probabilities (home/draw/away) from that matrix
  - Over/under probabilities for any line (default 2.5)

This is the standard Dixon-Coles-style model (simplified — we skip the
low-score correlation correction for now; can be added in a model bump).

Math:
  xG_home = league_avg_goals * home_attack * away_defense * home_factor
  xG_away = league_avg_goals * away_attack * home_defense
  P(home scores i) = Poisson(xG_home).pmf(i)
  P(away scores j) = Poisson(xG_away).pmf(j)
  P(scoreline i-j) = P(home=i) * P(away=j)    [assumes independence]

Home/away/draw probabilities are just sums over the relevant cells.

Elo enters as a *modifier* on attack/defense: a team rated 100 pts above
its competition mean scores ~10% more, concedes ~10% less. The exact mapping
is a parameter we'll fit later; default factor exponent = 0.0023 (≈ 100 Elo
pts -> 1.26x scoring rate).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

#: How far down we sum the scoring matrix. P(>=10 goals) is vanishingly small
#: in soccer; truncating at 10 covers all realistic outcomes.
MAX_GOALS = 10

#: Elo -> scoring multiplier exponent. Higher = Elo has bigger effect on goals.
#: 0.0023 means 100 Elo pts of advantage ≈ exp(0.23) = 1.26x scoring rate.
DEFAULT_ELO_GOAL_COEFF = 0.0023


@dataclass
class PoissonConfig:
    elo_goal_coeff: float = DEFAULT_ELO_GOAL_COEFF
    max_goals: int = MAX_GOALS
    default_total_line: float = 2.5
    # Dixon-Coles low-score correction. rho=0 → pure independent Poisson (old
    # behaviour). rho<0 inflates 0-0 and 1-1 (draws that independent Poisson
    # under-weights) and deflates 1-0/0-1. Typical fitted values ~ -0.03 to -0.15.
    dixon_coles_rho: float = 0.0
    # Promoted-team default prior: strengths for a club with NO matches in the
    # strengths window (newly promoted, not in the prior-season backfill).
    # Rather than dropping their games entirely (absent rows help nobody
    # downstream), assign a conservative below-average profile — promoted
    # sides historically score less and concede more than league average —
    # and EXPORT the fact (strengths_source=promoted_default) so the GPT
    # layer and our own records can discount/track these rows explicitly.
    promoted_attack_prior: float = 0.85
    promoted_defense_prior: float = 1.15  # >1.0 = concedes more than average

    def as_dict(self) -> dict:
        return {
            "elo_goal_coeff": self.elo_goal_coeff,
            "max_goals": self.max_goals,
            "default_total_line": self.default_total_line,
            "dixon_coles_rho": self.dixon_coles_rho,
            "promoted_attack_prior": self.promoted_attack_prior,
            "promoted_defense_prior": self.promoted_defense_prior,
        }


@dataclass
class TeamStrength:
    """Attack and defense rates *relative to league average* (1.0 = average)."""

    attack: float = 1.0
    defense: float = 1.0  # lower = better defense (fewer goals conceded)


@dataclass
class CompetitionScoringContext:
    """League-level scoring averages used as the baseline for xG."""

    avg_goals_per_team_per_match: float = 1.4  # PL long-run average ~1.4
    home_field_goal_boost: float = 1.15  # home teams score ~15% more historically

    def as_dict(self) -> dict:
        return {
            "avg_goals_per_team_per_match": self.avg_goals_per_team_per_match,
            "home_field_goal_boost": self.home_field_goal_boost,
        }


@dataclass
class MatchPrediction:
    """Output of a single match prediction."""

    home_xg: float
    away_xg: float
    p_home: float
    p_draw: float
    p_away: float
    p_over: float
    p_under: float
    over_under_line: float
    most_likely_score: tuple[int, int]
    most_likely_score_prob: float

    def as_dict(self) -> dict:
        return {
            "home_xg": round(self.home_xg, 3),
            "away_xg": round(self.away_xg, 3),
            "p_home": round(self.p_home, 4),
            "p_draw": round(self.p_draw, 4),
            "p_away": round(self.p_away, 4),
            "p_over": round(self.p_over, 4),
            "p_under": round(self.p_under, 4),
            "over_under_line": self.over_under_line,
            "most_likely_score": list(self.most_likely_score),
            "most_likely_score_prob": round(self.most_likely_score_prob, 4),
        }


# --------------------------------------------------------------------------
# Strength estimation from match history
# --------------------------------------------------------------------------


def estimate_strengths(
    matches: list[dict],
    context: CompetitionScoringContext,
    prior: dict[int, "TeamStrength"] | None = None,
) -> dict[int, TeamStrength]:
    """
    Empirical attack/defense estimation from a season's worth of matches.

    Each match is a dict with keys:
      home_team_id, away_team_id, home_score, away_score

    Attack = team's avg goals scored / league avg
    Defense = team's avg goals conceded / league avg
    Both normalized to ~1.0 across the league.

    This is a quick baseline. A proper MLE fit would jointly solve attack and
    defense parameters across all teams; we can upgrade in a later model version.

    `prior` (cup fix 2026-09-25): per-team shrinkage TARGET instead of 1.0 —
    the n/(n+5) confidence weight then blends this pool's fit toward the
    team's prior (its domestic league-season fit). None = the original 1.0
    target, byte-identical behavior for every existing caller.
    """
    league_avg = context.avg_goals_per_team_per_match
    if league_avg <= 0:
        league_avg = 1.4

    goals_for: dict[int, list[float]] = {}
    goals_against: dict[int, list[float]] = {}

    for m in matches:
        h = m["home_team_id"]
        a = m["away_team_id"]
        hs = m["home_score"]
        as_ = m["away_score"]
        # Strip the home-field boost so attack/defense are venue-neutral
        boost = context.home_field_goal_boost
        goals_for.setdefault(h, []).append(hs / boost)
        goals_against.setdefault(h, []).append(as_)
        goals_for.setdefault(a, []).append(as_)
        goals_against.setdefault(a, []).append(hs / boost)

    strengths: dict[int, TeamStrength] = {}
    for team_id in set(goals_for) | set(goals_against):
        gf = goals_for.get(team_id, [])
        ga = goals_against.get(team_id, [])
        attack = (sum(gf) / len(gf) / league_avg) if gf else 1.0
        defense = (sum(ga) / len(ga) / league_avg) if ga else 1.0
        # Light shrinkage toward 1.0 for teams with few games (regularization)
        n = min(len(gf), len(ga))
        weight = n / (n + 5)  # 5 games of regularization
        target = prior.get(team_id) if prior else None
        t_att = target.attack if target is not None else 1.0
        t_def = target.defense if target is not None else 1.0
        attack = weight * attack + (1 - weight) * t_att
        defense = weight * defense + (1 - weight) * t_def
        # Floor so a 0-goal team doesn't kill predictions
        strengths[team_id] = TeamStrength(
            attack=max(0.25, attack),
            defense=max(0.25, defense),
        )
    return strengths


# --------------------------------------------------------------------------
# Predict
# --------------------------------------------------------------------------


def _poisson_pmf(lam: float, k: int) -> float:
    """Poisson probability mass for k events given mean lam."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _poisson_vector(lam: float, max_k: int) -> np.ndarray:
    """Pre-computed PMF over 0..max_k."""
    return np.array([_poisson_pmf(lam, k) for k in range(max_k + 1)])


def predict_match(
    home_elo: float,
    away_elo: float,
    home_strength: TeamStrength,
    away_strength: TeamStrength,
    context: CompetitionScoringContext,
    config: PoissonConfig | None = None,
    factor_adjustment=None,  # FactorAdjustment from models.factors
) -> MatchPrediction:
    """
    Produce a full prediction for one match.

    Elo modifies the team's effective attack/defense via a multiplicative
    factor exp(coeff * elo_diff_from_competition_mean). We pass the raw Elo
    in and let the model treat the *difference* between home and away as
    the meaningful signal — so an "average" competition mean cancels out.
    """
    cfg = config or PoissonConfig()
    league_avg = context.avg_goals_per_team_per_match

    # Elo difference (positive = home favored). Half goes to attack, half to
    # the opponent's defense — keeps both sides' parameters moving.
    elo_diff = home_elo - away_elo
    home_elo_mult = math.exp(cfg.elo_goal_coeff * elo_diff / 2)
    away_elo_mult = math.exp(-cfg.elo_goal_coeff * elo_diff / 2)

    # Expected goals
    home_xg = (
        league_avg
        * context.home_field_goal_boost
        * home_strength.attack
        * away_strength.defense
        * home_elo_mult
    )
    away_xg = (
        league_avg
        * away_strength.attack
        * home_strength.defense
        * away_elo_mult
    )
    # Apply match-specific factor adjustments (injuries, rest, weather, etc.)
    if factor_adjustment is not None:
        home_xg *= factor_adjustment.home_xg_multiplier
        away_xg *= factor_adjustment.away_xg_multiplier

    # Floor xG so the Poisson doesn't degenerate
    home_xg = max(0.05, home_xg)
    away_xg = max(0.05, away_xg)

    # Score matrix
    max_k = cfg.max_goals
    home_pmf = _poisson_vector(home_xg, max_k)
    away_pmf = _poisson_vector(away_xg, max_k)
    score_matrix = np.outer(home_pmf, away_pmf)  # [i, j] = P(home=i, away=j)

    # Dixon-Coles low-score correction: independent Poisson under-weights draws
    # (esp. 0-0, 1-1). rho<0 inflates those cells and deflates 1-0/0-1, without
    # touching the rest of the matrix. rho=0 leaves the matrix unchanged.
    rho = cfg.dixon_coles_rho
    if rho != 0.0 and max_k >= 1:
        lam, mu = home_xg, away_xg
        score_matrix[0, 0] *= (1.0 - lam * mu * rho)
        score_matrix[1, 0] *= (1.0 + mu * rho)
        score_matrix[0, 1] *= (1.0 + lam * rho)
        score_matrix[1, 1] *= (1.0 - rho)
        # guard against any cell going negative for extreme rho
        np.clip(score_matrix, 0.0, None, out=score_matrix)

    # 1X2
    p_home = float(np.tril(score_matrix, -1).sum())  # home > away
    p_draw = float(np.trace(score_matrix))
    p_away = float(np.triu(score_matrix, 1).sum())

    # Normalize so probabilities sum to 1.0 (truncation at MAX_GOALS loses a tiny mass)
    total = p_home + p_draw + p_away
    if total > 0:
        p_home /= total
        p_draw /= total
        p_away /= total

    # Over/under
    line = cfg.default_total_line
    threshold = int(math.floor(line)) + 1  # for 2.5 line, "over" means >=3 total goals
    p_over = 0.0
    for i in range(max_k + 1):
        for j in range(max_k + 1):
            if i + j >= threshold:
                p_over += score_matrix[i, j]
    p_over = float(p_over)
    p_under = max(0.0, 1.0 - p_over)

    # Most likely score
    idx = np.unravel_index(np.argmax(score_matrix), score_matrix.shape)
    most_likely_score = (int(idx[0]), int(idx[1]))
    most_likely_score_prob = float(score_matrix[idx])

    return MatchPrediction(
        home_xg=home_xg,
        away_xg=away_xg,
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        p_over=p_over,
        p_under=p_under,
        over_under_line=line,
        most_likely_score=most_likely_score,
        most_likely_score_prob=most_likely_score_prob,
    )
