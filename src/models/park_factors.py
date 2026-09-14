"""
Park factors for MLB run scoring — Phase 12.

A park factor multiplies the expected total runs in a game. PF=1.20 at Coors
means 20% more scoring than at a neutral park; PF=0.90 at Petco means 10% less.

We apply the same factor to BOTH teams' expected runs at predict time. This
is a simplification — strictly, batter and pitcher park factors can differ,
and some pitchers are more park-sensitive than others. We use a single combined
factor per park, which is what most public analyses do.

Sources: Baseball Reference 3-year park factors (averaged 2023-2025) and
ESPN park factors. These two sources broadly agree; we picked the midpoint
when they diverged. Values are conservative — we'd rather under-correct than
over-correct, because park factor is just one input alongside team profiles
and pitcher ERA.

For non-MLB sports (soccer), park factors are not used — the effect size at
this level of competition is well below model noise.

Wind direction at Wrigley Field gets a special bonus: wind blowing out makes
it a hitter's park; wind blowing in makes it a pitcher's park. No other park
has wind effects strong enough to justify the complexity.
"""
from __future__ import annotations


# Park factors for run scoring. 1.0 = neutral.
# Drawn from public sources (Baseball Reference 3yr avg + ESPN). Where sources
# disagreed by >0.03, we picked the conservative middle.
_PARK_FACTORS: dict[str, float] = {
    # Hitter's parks
    "Coors Field":              1.21,    # Colorado — altitude, by far the most extreme
    "Great American Ball Park": 1.06,    # Cincinnati — short porch in RF
    "Fenway Park":              1.05,    # Boston — Green Monster but small overall
    "Citizens Bank Park":       1.05,    # Philadelphia
    "Globe Life Field":         1.04,    # Texas (retractable roof — neutral-ish)
    "Yankee Stadium":           1.03,    # short RF porch helps lefties
    "Camden Yards":             1.02,    # Baltimore — recent wall changes reduced PF (alias)
    "Oriole Park at Camden Yards": 1.02,  # canonical name from MLB Stats API
    "Wrigley Field":            1.02,    # base value; wind direction modifies (see below)
    "Chase Field":              1.02,    # Arizona — retractable roof, slight hitter park
    "American Family Field":    1.01,    # Milwaukee — retractable roof
    "Journey Bank Ballpark":    1.01,    # Milwaukee renamed 2026 (same park)
    "Rogers Centre":            1.01,    # Toronto — retractable roof, slight hitter park

    # Neutral parks
    "Truist Park":              1.00,    # Atlanta
    "Nationals Park":           1.00,    # Washington
    "Angel Stadium":            1.00,    # LAA
    "Minute Maid Park":         1.00,    # Houston
    "PNC Park":                 1.00,    # Pittsburgh
    "Citi Field":               1.00,    # NYM
    "Target Field":             1.00,    # Minnesota
    "Progressive Field":        1.00,    # Cleveland
    "Comerica Park":            0.99,    # Detroit
    "Guaranteed Rate Field":    0.99,    # Chicago White Sox (old name, kept as alias)
    "Rate Field":               0.99,    # Chicago White Sox (current name as of 2025)
    "Busch Stadium":            0.99,    # St. Louis
    "Kauffman Stadium":         0.99,    # Kansas City
    "Sutter Health Park":       0.99,    # A's temp 2025+

    # Pitcher's parks
    "Dodger Stadium":           0.97,    # Los Angeles
    "loanDepot park":           0.96,    # Miami — large outfield, dome
    "Oracle Park":              0.95,    # San Francisco — cold, wind off bay, deep RF
    "T-Mobile Park":            0.93,    # Seattle — heavy marine air
    "Tropicana Field":          0.93,    # Tampa Bay — dome
    "Petco Park":               0.91,    # San Diego — by far the most extreme pitcher's park
}

#: Conservative default — unknown venues get neutral treatment.
DEFAULT_PARK_FACTOR = 1.0


def get_park_factor(venue: str | None) -> float:
    """
    Return the run-scoring multiplier for an MLB venue, or 1.0 if unknown.

    Soccer venues / unknown venues / missing venue → 1.0 (neutral). Caller
    can multiply both teams' expected runs by this value at predict time.

    Tries exact match first; falls back to substring match for handling
    name variants like "Oriole Park at Camden Yards" matching "Camden Yards"
    in case the upstream feed drifts on stadium naming.
    """
    if not venue:
        return DEFAULT_PARK_FACTOR
    # Exact match — fast path
    if venue in _PARK_FACTORS:
        return _PARK_FACTORS[venue]
    # Substring fallback. Both directions: "Camden Yards" in "Oriole Park at
    # Camden Yards", or "Rate Field" matching just by partial overlap.
    # Use the longest matching key to disambiguate when multiple match.
    matches = [k for k in _PARK_FACTORS if k in venue or venue in k]
    if matches:
        # Prefer the longest match to avoid e.g. "Park" matching everything
        best = max(matches, key=len)
        # Only accept the fuzzy match if at least 8 chars overlap — guards
        # against meaningless 1-2 char substring matches.
        if len(best) >= 8:
            return _PARK_FACTORS[best]
    return DEFAULT_PARK_FACTOR


def get_wrigley_wind_adjustment(
    wind_mph: float | None,
    wind_direction_compass: str | None,
) -> float:
    """
    Special-case wind adjustment for Wrigley Field.

    Wrigley is the only MLB park where wind direction has well-documented,
    large enough effects on run scoring to be worth modeling. Wind blowing
    out toward the lake → big hitter's park. Wind blowing in off the lake
    → pitcher's park.

    Wrigley's outfield faces roughly NE (toward Lake Michigan). So:
      - Wind from S/SW (blowing OUT toward the lake) → boost hitters
      - Wind from N/NE (blowing IN from the lake) → suppress hitters
      - East/West winds → neutral (cross-winds, hard to characterize)

    Args:
        wind_mph: wind speed in mph. None or 0 → no adjustment.
        wind_direction_compass: "N", "NE", "E", "SE", "S", "SW", "W", "NW".

    Returns:
        multiplier to apply on top of the base Wrigley PF (1.02). Returns 1.0
        when wind is light (<8 mph) or direction is unknown/crosswind.
    """
    if not wind_mph or not wind_direction_compass:
        return 1.0
    if wind_mph < 8:
        return 1.0  # too gentle to matter

    direction = wind_direction_compass.upper()
    # Out toward the lake (favors hitters)
    if direction in ("S", "SW", "SSW", "SSE"):
        # Scale with wind strength — capped at 15mph contribution
        intensity = min(wind_mph, 15) / 15
        return 1.0 + 0.08 * intensity  # up to +8% additional
    # In off the lake (favors pitchers)
    if direction in ("N", "NE", "NNE", "NNW"):
        intensity = min(wind_mph, 15) / 15
        return 1.0 - 0.06 * intensity  # down to -6% additional
    return 1.0
