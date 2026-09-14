"""
Value detection.

Walters' essential edge: a price is "value" when the model thinks the true
probability is higher than the implied probability of the bookmaker's price.
Bookmakers build a margin (overround) into their odds — typically 4-7% on
1X2 — so you need to clear that margin AND have an honest model edge before
you've found anything real.

Math:
  implied_prob = 1.0 / price_decimal
  fair_implied_prob = implied_prob / book_overround   (de-vigged)
  edge_pct = (model_prob / fair_implied_prob) - 1.0

We work with the *de-vigged* implied probability for honesty. A naked
implied of 33% on a draw doesn't mean the book actually thinks it's 33%;
it means they're charging more than 33% to insure against it. The
overround is the sum of implied probabilities across all selections;
dividing each one by that sum gives the book's true belief about the
outcome distribution.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValueOpportunity:
    market: str          # "1X2", "OU_2.5", etc.
    selection: str       # "HOME", "DRAW", "AWAY", "OVER", "UNDER"
    bookmaker: str
    price: float         # decimal odds at the bookmaker
    model_prob: float    # our probability
    implied_prob: float  # raw implied (1/price)
    fair_prob: float     # de-vigged book belief
    edge_pct: float      # (model_prob / fair_prob) - 1

    def as_dict(self) -> dict:
        return {
            "market": self.market,
            "selection": self.selection,
            "bookmaker": self.bookmaker,
            "price": self.price,
            "model_prob": round(self.model_prob, 4),
            "implied_prob": round(self.implied_prob, 4),
            "fair_prob": round(self.fair_prob, 4),
            "edge_pct": round(self.edge_pct, 4),
        }


@dataclass
class MarketSnapshot:
    """
    All odds for a single market across bookmakers, grouped by selection.

    Used to compute overround (book margin) and the best available price
    for each selection.
    """

    market: str
    # selection -> list of (bookmaker, price)
    by_selection: dict[str, list[tuple[str, float]]]

    def best_price(self, selection: str) -> tuple[str, float] | None:
        """Best (highest) price for this selection across all books."""
        offers = self.by_selection.get(selection, [])
        if not offers:
            return None
        return max(offers, key=lambda x: x[1])

    def average_implied(self) -> dict[str, float]:
        """Average implied probability per selection. Used for de-vig."""
        out = {}
        for sel, offers in self.by_selection.items():
            if not offers:
                continue
            implied = [1.0 / p for _bm, p in offers]
            out[sel] = sum(implied) / len(implied)
        return out


def detect_value(
    market_snapshot: MarketSnapshot,
    model_probs: dict[str, float],
    min_edge_pct: float = 0.03,
) -> list[ValueOpportunity]:
    """
    Walk through each selection and flag any where the model edge clears
    `min_edge_pct` against the best available price.

    `model_probs` maps selection -> probability (must sum to ~1.0 within
    the market). For 1X2 that's {"HOME": 0.5, "DRAW": 0.3, "AWAY": 0.2}.

    Returns a list of ValueOpportunity, sorted by edge descending. Empty
    list = no value, nothing to bet.
    """
    implied = market_snapshot.average_implied()
    overround = sum(implied.values())
    if overround <= 0:
        return []

    opportunities: list[ValueOpportunity] = []
    for selection, model_prob in model_probs.items():
        best = market_snapshot.best_price(selection)
        if best is None:
            continue
        bookmaker, price = best
        raw_implied = 1.0 / price
        # De-vig using the market's overround
        fair_prob = implied[selection] / overround
        edge = (model_prob / fair_prob) - 1.0 if fair_prob > 0 else 0.0
        if edge >= min_edge_pct:
            opportunities.append(ValueOpportunity(
                market=market_snapshot.market,
                selection=selection,
                bookmaker=bookmaker,
                price=price,
                model_prob=model_prob,
                implied_prob=raw_implied,
                fair_prob=fair_prob,
                edge_pct=edge,
            ))

    return sorted(opportunities, key=lambda v: -v.edge_pct)
