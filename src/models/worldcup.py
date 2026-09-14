"""
World Cup — MARKET-DERIVED predictions (NOT the club Elo/Poisson model).

This module is deliberately self-contained and imports NOTHING from the club
soccer model (Elo, Poisson, league_strength). That separation is the WALL:
World Cup national-team matches cannot be rated by a club-league model, so we
do not try. Instead we surface the BOOKMAKER MARKET's view, de-vigged into
honest probabilities.

Why market-derived, not modelled:
  - The club model has no national-team ratings; running it would fire the
    "unknown league" fallback and produce confidently-wrong numbers.
  - The World Cup market is sharp; a from-scratch national-team model would,
    best case, reproduce it. So we read it rather than reinvent it.
  - 64 games / 4 years => nothing to calibrate. This is EXPLORATORY and is
    labelled "market-derived, not a model prediction" everywhere it surfaces.
    It must never be graded/calibrated like the MLB model or set precedent
    for it.

Decisions (locked 2026-06-07):
  1. NO winner shown when the market has none. If 1X2 odds are absent, return
     None — never guess.
  2. Underdog-path layer stays MANUAL (qualitative, on request). Not here.
  3. De-vig method = simple proportional (divide each implied prob by the
     overround / sum of implieds). Same approach as walters/value.py.
"""
from __future__ import annotations

from dataclasses import dataclass


# Minimum number of 1X2 selections we need to call a market present. A real
# 1X2 market has all three (HOME/DRAW/AWAY); anything less is too thin to
# trust, so we decline (decision #1).
_REQUIRED_SELECTIONS = {"HOME", "DRAW", "AWAY"}


@dataclass
class MarketDerivedPrediction:
    """
    A market-derived World Cup match read. Explicitly NOT a model output.
    """
    match_id: int
    home_team: str | None
    away_team: str | None
    # de-vigged fair probabilities (sum to ~1.0)
    p_home: float
    p_draw: float
    p_away: float
    favorite: str          # "HOME" | "AWAY" | "DRAW"-never-favorite fallback
    overround: float       # book margin we removed (e.g. 1.06 = 6%)
    n_bookmakers: int      # how many price rows fed the average
    source: str = "market-derived"  # provenance label — never "model"

    def as_dict(self) -> dict:
        return {
            "match_id": self.match_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "probabilities": {
                "home_win": round(self.p_home, 4),
                "draw": round(self.p_draw, 4),
                "away_win": round(self.p_away, 4),
            },
            "favorite": self.favorite,
            "overround": round(self.overround, 4),
            "n_bookmakers": self.n_bookmakers,
            "source": self.source,
            "note": ("Market-derived (de-vigged bookmaker odds), NOT a model "
                     "prediction. National-team matches are not rated by the "
                     "club model."),
        }


def devig_1x2(prices: dict[str, float]) -> dict[str, float] | None:
    """
    Simple proportional de-vig of a 1X2 market.

    prices: {"HOME": decimal, "DRAW": decimal, "AWAY": decimal}
    Returns {"HOME","DRAW","AWAY"} fair probabilities summing to ~1.0, or
    None if any selection is missing or non-positive (decision #1: no guess).
    """
    if not _REQUIRED_SELECTIONS.issubset(prices.keys()):
        return None
    implied = {}
    for sel in _REQUIRED_SELECTIONS:
        price = prices.get(sel)
        if price is None or price <= 1.0:   # decimal odds must be > 1.0
            return None
        implied[sel] = 1.0 / price
    overround = sum(implied.values())
    if overround <= 0:
        return None
    fair = {sel: implied[sel] / overround for sel in implied}
    fair["_overround"] = overround
    return fair


def market_prediction_for_match(
    match_id: int,
    home_team: str | None,
    away_team: str | None,
    odds_rows: list,  # iterable of objects with .selection and .price_decimal
) -> MarketDerivedPrediction | None:
    """
    Build a market-derived prediction for one World Cup match.

    Returns None (no prediction) when:
      - either team is null (unqualified knockout slot — skip it), OR
      - the 1X2 market is absent/thin (decision #1: no winner without market).

    When multiple bookmaker rows exist per selection, average the decimal
    prices first, then de-vig — a simple consensus price.
    """
    # Skip unqualified knockout fixtures — no teams, no read.
    if home_team is None or away_team is None:
        return None

    # Gather decimal prices per 1X2 selection, averaging across bookmakers.
    by_sel: dict[str, list[float]] = {}
    for row in odds_rows:
        sel = getattr(row, "selection", None)
        price = getattr(row, "price_decimal", None)
        if sel in _REQUIRED_SELECTIONS and price and price > 1.0:
            by_sel.setdefault(sel, []).append(price)

    if not _REQUIRED_SELECTIONS.issubset(by_sel.keys()):
        return None  # market absent/thin -> no winner (decision #1)

    avg_prices = {sel: sum(v) / len(v) for sel, v in by_sel.items()}
    n_books = max(len(v) for v in by_sel.values())

    fair = devig_1x2(avg_prices)
    if fair is None:
        return None

    p_home, p_draw, p_away = fair["HOME"], fair["DRAW"], fair["AWAY"]
    # Favorite = higher of the two sides (a draw is never the "favorite" to
    # advance/win; it's a separate outcome). If the market is a dead heat we
    # still report the marginally higher side, but callers can see they're
    # near-equal from the probabilities.
    favorite = "HOME" if p_home >= p_away else "AWAY"

    return MarketDerivedPrediction(
        match_id=match_id,
        home_team=home_team,
        away_team=away_team,
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        favorite=favorite,
        overround=fair["_overround"],
        n_bookmakers=n_books,
    )
