"""
League strength coefficients — Phase 7 (cup-Elo).

When teams from different leagues meet in cup competitions (FA Cup, EFL Cup,
Champions League), their league Elo ratings aren't directly comparable. A
1500-Elo Premier League team is far stronger than a 1500-Elo League One team
because the underlying competition is different.

We adjust by adding a "league bonus" to each team's Elo when comparing across
leagues. The bonuses are anchored to the Premier League at 0; weaker leagues
get negative bonuses. Numbers are calibrated from published UEFA coefficients
and observed cross-league cup results in English football.

These are v1 estimates. The "fitted from data" version waits until we have
50+ cross-league cup matches in the DB to evaluate against.

The mapping uses competition codes since we don't have a stable per-team
"home league" field — but in practice cup matches give us both teams'
competition history via CompetitionTeam, and we use the most recent league
competition as a team's "home league."
"""
from __future__ import annotations

# Bonus (in Elo points) for each league, relative to the Premier League.
# Positive = stronger than PL (none of these because PL is at the top).
# Negative = weaker than PL.
#
# Calibration logic:
#   PL = 0 (reference)
#   Championship ~ -130 Elo. Roughly translates to a ~30% win expectancy
#     drop in a head-to-head, which lines up with observed FA Cup results
#     (~25-30% win rate for Championship sides in the 4th/5th round).
#   League One ~ -260 Elo. About 60 points behind Championship.
#   League Two ~ -360 Elo.
#   National League ~ -450 Elo.
#
# Top European leagues are close to PL in strength but historically slightly
# behind in head-to-heads when controlling for team quality. UEFA coefficients
# put them within ~30 Elo of each other for the last decade.
LEAGUE_ELO_BONUS: dict[str, float] = {
    # England
    "PL": 0.0,
    "ELC": -130.0,    # Championship
    "EL1": -260.0,    # League One (if we sync it)
    "EL2": -360.0,    # League Two
    # Top European leagues (used when CL/EL teams face each other)
    # CL/UEL feeders (2026-09-19): priors pending the acceptance exam's
    # pricing check — these inform cup-tie bonuses only.
    "NED": -60.0, "POR": -55.0, "BEL": -80.0, "SCO": -110.0,
    "TUR": -90.0, "AUT": -110.0, "SUI": -110.0, "GRE": -120.0,
    "CZE": -130.0,
    "PD": -10.0,      # La Liga
    "SA": -20.0,      # Serie A
    "BL1": -25.0,     # Bundesliga
    "FL1": -50.0,     # Ligue 1
    # MLS / other
    "MLS": -200.0,
    # Cup competitions don't have a "league strength" — we never look them
    # up here, but defining 0 prevents KeyErrors if we accidentally do.
    "FAC": 0.0, "EFL": 0.0, "CS": 0.0,
    "CL": 0.0, "EL": 0.0, "WC": 0.0,
}

# Default for unknown leagues — assume mid-tier European, conservative.
DEFAULT_LEAGUE_BONUS = -100.0


def league_bonus(competition_code: str | None) -> float:
    """
    Return the Elo bonus for a team whose home league is the given comp.
    Falls back to a conservative mid-tier estimate for unknown codes.
    """
    if not competition_code:
        return DEFAULT_LEAGUE_BONUS
    return LEAGUE_ELO_BONUS.get(competition_code.upper(), DEFAULT_LEAGUE_BONUS)
