"""
Bankroll / staking module.

Implements fractional Kelly with a hard cap. The math says full Kelly is
growth-optimal, but it's brutal in practice — drawdowns hurt, and your edge
estimate is never as precise as the formula assumes. Walters' descendants
universally use ¼ or ⅛ Kelly. We default to ¼ Kelly with a max-stake cap of
2% of bankroll on any one bet.

Kelly fraction (for a 2-outcome bet):
  f* = (bp - q) / b
where
  b = decimal_odds - 1  (net win per unit staked)
  p = true probability of winning
  q = 1 - p
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StakeRecommendation:
    fraction_of_bankroll: float   # fractional Kelly result, capped
    raw_kelly_fraction: float     # what full Kelly says (unclamped, uncapped)
    reasoning: str

    def as_dict(self) -> dict:
        return {
            "fraction_of_bankroll": round(self.fraction_of_bankroll, 4),
            "raw_kelly_fraction": round(self.raw_kelly_fraction, 4),
            "reasoning": self.reasoning,
        }


def kelly_fraction(probability: float, decimal_odds: float) -> float:
    """Full Kelly fraction. Can be negative when there's no edge."""
    if decimal_odds <= 1.0:
        return 0.0
    b = decimal_odds - 1.0
    p = probability
    q = 1.0 - p
    return (b * p - q) / b


def recommend_stake(
    probability: float,
    decimal_odds: float,
    kelly_fraction_used: float = 0.25,
    max_stake_pct: float = 0.02,
) -> StakeRecommendation:
    """
    Walters-style stake recommendation as a fraction of bankroll.

    - Returns 0 if no edge (negative Kelly).
    - Applies fractional Kelly (default ¼) for safety.
    - Caps at `max_stake_pct` per bet (default 2% — survives a long bad streak).
    """
    raw = kelly_fraction(probability, decimal_odds)
    if raw <= 0:
        return StakeRecommendation(
            fraction_of_bankroll=0.0,
            raw_kelly_fraction=raw,
            reasoning="No edge (Kelly ≤ 0). Do not bet.",
        )

    fractional = raw * kelly_fraction_used
    capped = min(fractional, max_stake_pct)

    reasoning_parts = [
        f"Full Kelly = {raw:.2%}",
        f"×{kelly_fraction_used} fraction = {fractional:.2%}",
    ]
    if capped < fractional:
        reasoning_parts.append(f"Capped at {max_stake_pct:.0%}")

    return StakeRecommendation(
        fraction_of_bankroll=capped,
        raw_kelly_fraction=raw,
        reasoning=" → ".join(reasoning_parts),
    )
