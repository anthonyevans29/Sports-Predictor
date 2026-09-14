"""
Team strength derivation from player scores — Phase 6b.

Converts a starting XI (list of player scores + positions) into two numbers:
attack rating and defense rating. These get blended with team-level Elo-derived
attack/defense factors to produce player-aware predictions.

Design choices documented inline; key points:

- Position-weighted contribution. Attackers contribute most to attack rating,
  defenders most to defense, midfielders meaningfully to both, GK only to
  defense (and only modestly — keeper score reflects shot-stopping, but team
  defense is mostly about the back line and structure).

- Output is on the same 0-100 scale as the player scores. A team of all
  "league-average" players (every score = 50) produces attack=50, defense=50.
  An "all 80s" XI produces ~80 / ~80.

- We compare today's XI to the team's *season-average XI* to compute a delta.
  That delta is what we apply as a multiplicative adjustment to Poisson xG.
  This way, a team that always fields a strong XI doesn't double-count
  (since their Elo already reflects that strength). The lineup signal is
  *relative to the team's own baseline*.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.models.player_score import (
    POSITION_ATTACKER,
    POSITION_DEFENDER,
    POSITION_GOALKEEPER,
    POSITION_MIDFIELDER,
    PlayerScoreBreakdown,
    _normalize_position,
    compute_player_score,
)

# Position contribution weights to attack vs defense ratings.
# Each row sums to 1.0 across players-per-position so a balanced XI's
# attack rating is roughly its average attacker score.
ATTACK_WEIGHTS = {
    POSITION_ATTACKER: 1.0,
    POSITION_MIDFIELDER: 0.5,
    POSITION_DEFENDER: 0.15,
    POSITION_GOALKEEPER: 0.05,
}

DEFENSE_WEIGHTS = {
    POSITION_ATTACKER: 0.10,
    POSITION_MIDFIELDER: 0.45,
    POSITION_DEFENDER: 1.0,
    POSITION_GOALKEEPER: 0.6,
}


@dataclass
class XIStrength:
    """Aggregate attack/defense ratings for a starting XI."""
    attack: float
    defense: float
    # How many of the 11 positions had identifiable player scores.
    # Below 8 we consider the XI "unreliable" and weight it less.
    players_with_scores: int = 11
    # Per-player contributions for tracing
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "attack": round(self.attack, 1),
            "defense": round(self.defense, 1),
            "players_with_scores": self.players_with_scores,
            "notes": self.notes,
        }


def compute_xi_strength(player_scores: list[tuple[str, float, str]]) -> XIStrength:
    """
    Aggregate an XI into (attack_rating, defense_rating).

    Args:
      player_scores: list of (player_name, score, position_raw) tuples for
                     the 11 starters. Position is the raw API position
                     string (e.g. "Attacker", "Midfielder") which we
                     normalize into one of our four buckets.

    Returns XIStrength with both ratings on a 0-100 scale, and a count
    of how many players had identifiable scores. Players with score=None
    (no season stats) are treated as score=50 (league average) to avoid
    penalizing a team for a fresh signing or returning loanee.
    """
    if not player_scores:
        return XIStrength(attack=50.0, defense=50.0, players_with_scores=0)

    attack_num = 0.0
    attack_w = 0.0
    defense_num = 0.0
    defense_w = 0.0
    players_with_scores = 0

    for name, score, pos_raw in player_scores:
        bucket = _normalize_position(pos_raw)
        if score is None:
            # Unknown player: assume league-average. Better than excluding.
            effective_score = 50.0
        else:
            effective_score = score
            players_with_scores += 1

        atk_w = ATTACK_WEIGHTS.get(bucket, 0.3)
        def_w = DEFENSE_WEIGHTS.get(bucket, 0.3)

        attack_num += effective_score * atk_w
        attack_w += atk_w
        defense_num += effective_score * def_w
        defense_w += def_w

    attack = attack_num / attack_w if attack_w > 0 else 50.0
    defense = defense_num / defense_w if defense_w > 0 else 50.0

    return XIStrength(
        attack=attack,
        defense=defense,
        players_with_scores=players_with_scores,
    )


def compute_team_baseline_xi(
    all_player_scores: list[tuple[str, float, str]],
    typical_xi_size: int = 11,
) -> XIStrength:
    """
    Compute a team's "season-average XI" — what the XI strength looks like
    when the team fields their typical first-choice lineup.

    Heuristic: take the top 11 players by score, ranked. For position
    balance, take top 4 defenders, 3 midfielders, 3 attackers, 1 keeper
    if available, else just top 11.

    This is the baseline we compare today's actual XI against.
    """
    if not all_player_scores:
        return XIStrength(attack=50.0, defense=50.0, players_with_scores=0)

    by_pos: dict[str, list] = {
        POSITION_GOALKEEPER: [],
        POSITION_DEFENDER: [],
        POSITION_MIDFIELDER: [],
        POSITION_ATTACKER: [],
    }
    for name, score, pos_raw in all_player_scores:
        if score is None:
            continue
        bucket = _normalize_position(pos_raw)
        by_pos.setdefault(bucket, []).append((name, score, pos_raw))

    # Sort each position by score
    for bucket in by_pos:
        by_pos[bucket].sort(key=lambda t: -t[1])

    # Pick a position-balanced top XI. If a team has fewer than the target
    # at a position, take what's there and let the others backfill.
    targets = {
        POSITION_GOALKEEPER: 1,
        POSITION_DEFENDER: 4,
        POSITION_MIDFIELDER: 3,
        POSITION_ATTACKER: 3,
    }
    selected: list = []
    for bucket, n in targets.items():
        selected.extend(by_pos[bucket][:n])

    # If we ended up under 11 (small squad), fill with next-best regardless of position
    if len(selected) < typical_xi_size:
        remaining = []
        for bucket, n in targets.items():
            remaining.extend(by_pos[bucket][n:])
        remaining.sort(key=lambda t: -t[1])
        selected.extend(remaining[: typical_xi_size - len(selected)])

    return compute_xi_strength(selected[:typical_xi_size])


def xi_adjustment_multipliers(
    today_xi: XIStrength,
    season_baseline: XIStrength,
    confidence_weight: float = 0.5,
) -> tuple[float, float, list[str]]:
    """
    Compute the multipliers to apply to a team's attack and defense xG.

    Logic:
      delta_attack = (today_xi.attack - season_baseline.attack)
      multiplier_attack = 1 + (delta_attack / 100) * confidence_weight * SENSITIVITY

    A 10-point drop in XI attack rating below baseline translates to a
    ~7% drop in expected xG at confidence_weight=1.0. Conservative on purpose
    — player scores are v1 and overweighting them on top of team Elo would
    double-count.

    Returns (attack_xg_multiplier, defense_xg_multiplier, notes).
    The defense multiplier is for the OPPONENT's xG — a stronger defense
    means the opponent scores less.
    """
    SENSITIVITY = 0.007  # per rating point delta

    notes = []

    if today_xi.players_with_scores < 8:
        notes.append(f"Only {today_xi.players_with_scores}/11 starters had scores — XI adj. muted.")
        confidence_weight *= today_xi.players_with_scores / 11

    attack_delta = today_xi.attack - season_baseline.attack
    defense_delta = today_xi.defense - season_baseline.defense

    # Attack: stronger XI attack → multiplier > 1 (more xG)
    attack_mult = 1.0 + attack_delta * SENSITIVITY * confidence_weight
    # Defense: stronger XI defense → multiplier < 1 on the OPPONENT's xG
    # (note the SIGN FLIP — a positive defense_delta means we're stronger
    # defensively, which suppresses opp xG)
    defense_mult = 1.0 - defense_delta * SENSITIVITY * confidence_weight

    # Clip extreme effects — we never want player ratings alone to swing
    # xG by more than 25% in either direction.
    attack_mult = max(0.75, min(1.25, attack_mult))
    defense_mult = max(0.75, min(1.25, defense_mult))

    if abs(attack_delta) >= 3:
        sign = "+" if attack_delta > 0 else "−"
        notes.append(
            f"XI attack {today_xi.attack:.1f} vs season-avg {season_baseline.attack:.1f} "
            f"({sign}{abs(attack_delta):.1f}) → "
            f"{'+' if attack_mult > 1 else '−'}{abs(attack_mult - 1) * 100:.1f}% own xG"
        )
    if abs(defense_delta) >= 3:
        sign = "+" if defense_delta > 0 else "−"
        notes.append(
            f"XI defense {today_xi.defense:.1f} vs season-avg {season_baseline.defense:.1f} "
            f"({sign}{abs(defense_delta):.1f}) → "
            f"{'+' if defense_mult > 1 else '−'}{abs(defense_mult - 1) * 100:.1f}% opp xG"
        )

    return attack_mult, defense_mult, notes


# Confidence weights based on the lineup kind. Higher confidence in confirmed
# lineups (close to kickoff, source of truth) than projected (heuristic).
CONFIDENCE_BY_KIND = {
    "confirmed": 0.7,
    "projected": 0.3,
}
