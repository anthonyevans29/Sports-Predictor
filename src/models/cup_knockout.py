"""
Cup knockout "to advance" probabilities — Phase 7.

For cup knockout matches (FA Cup R4 onward, EFL Cup R3 onward, all CL/EL
KO rounds), the bookmaker market that matters most isn't "who wins in 90
minutes" but "who advances to the next round." A 1-1 draw at 90 minutes
is a tie for our prediction but is 50/50 to advance after extra time
and penalties.

Conversion:
  P(advance_H) = P(H_90) + draw_to_home_advance_share * P(D_90)
  P(advance_A) = P(A_90) + (1 - draw_to_home_advance_share) * P(D_90)

The home advantage in extra-time-plus-penalties is small but measurable —
empirically around 51-53% for the home side in single-leg cup knockouts
(the home crowd matters, but ET-pens variance dilutes most of it). For
two-legged ties the advantage is even smaller. We use a single coefficient
since the cup-match metadata in our DB doesn't reliably distinguish 1-leg
vs 2-leg outright.

For 90-min predictions in cup MATCHES that are NOT knockouts (CL group
stage, FA Cup early rounds where replays still happen — though replays
are mostly abolished now), to-advance just equals win probability — but
group-stage matches have no advance-or-die semantic anyway, so we return
None and the UI hides the column.
"""
from __future__ import annotations

# Home-team share of post-90-minute outcomes when 90-min was tied.
# Single-leg cup knockouts: home crowd has a small ~52% edge in ET+pens.
# Set conservatively; this gets fitted later once we have cup outcomes.
DRAW_TO_HOME_ADVANCE_SHARE = 0.52


def to_advance_probabilities(
    p_home_90: float,
    p_draw_90: float | None,
    p_away_90: float,
    home_share: float = DRAW_TO_HOME_ADVANCE_SHARE,
) -> tuple[float, float]:
    """
    Convert 1X2 (90-min) probabilities into 'home advances' / 'away advances'
    probabilities for a cup knockout. Sum is 1.0 since one side must advance.

    For non-soccer or 2-outcome inputs (p_draw_90 is None), this just returns
    the input probabilities — no draw mass to redistribute.
    """
    if p_draw_90 is None:
        return p_home_90, p_away_90
    p_home_adv = p_home_90 + home_share * p_draw_90
    p_away_adv = p_away_90 + (1.0 - home_share) * p_draw_90
    # Normalize defensively against any floating-point drift
    total = p_home_adv + p_away_adv
    if total > 0:
        p_home_adv /= total
        p_away_adv /= total
    return p_home_adv, p_away_adv


# Cup competitions where the to-advance market is meaningful (knockout from
# early rounds). For CL/EL we include them even though they have a group
# stage — the knockouts are the bigger-stakes market. The "is this match
# itself a knockout" call happens at predict-time based on `stage`.
KNOCKOUT_CUP_CODES = {
    "FAC",          # FA Cup (knockouts from R1, replays mostly abolished)
    "EFL",          # EFL Cup
    "CS",           # Community Shield (one-off)
    "CL",           # Champions League — KO from R16
    "EL",           # Europa League
    "WC",           # World Cup
    "UEFA_EURO",    # Euros
    "WCQ_EU",       # World Cup qualifiers — knockout playoffs
    "WCQ_SA", "WCQ_AF", "WCQ_AS", "WCQ_NA", "WCQ_OC",
}


# Stages within group-stage-having competitions where match IS a knockout.
# API-Football's "stage" field uses these strings (loosely; we match
# substrings).
KO_STAGE_SUBSTRINGS = {
    "round of 16", "quarter", "semi-final", "semi final",
    "semifinal", "final", "playoff", "play-off", "knockout",
    "1st leg", "2nd leg",
}


def is_knockout_match(competition_code: str | None, stage: str | None) -> bool:
    """
    Is this specific match a knockout where ET/pens decide it?

    For competitions that are entirely knockout (FA Cup, EFL Cup), every
    match qualifies. For mixed-format competitions (CL, EL with group stage)
    we check the stage string.
    """
    if not competition_code:
        return False
    code = competition_code.upper()
    if code not in KNOCKOUT_CUP_CODES:
        return False

    # Pure-knockout competitions: every match counts
    if code in {"FAC", "EFL", "CS"}:
        return True

    # Mixed: only if stage indicates knockout
    if stage:
        s = stage.lower()
        for needle in KO_STAGE_SUBSTRINGS:
            if needle in s:
                return True
        # If the stage is something like "Group A" or "Group Stage", not KO
        return False

    # Unknown stage in a KO-capable comp — assume not KO to be safe
    return False
