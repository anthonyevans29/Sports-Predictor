"""
Match-level factor adjustments.

These multiply the base xG output from the Poisson model. The baseline
already handles team strength + home advantage; this module captures
match-specific effects:

  - Rest days since last fixture (fatigue)
  - Travel distance / time zones (away team penalty)
  - Weather (rain reduces total goals on average)
  - Squad availability (injuries, suspensions) — needs injury feed, Phase 3
  - Competition stakes (cup rounds, end-of-season dead rubbers)

Phase 2 ships rest_days only. The rest are stubbed so the prediction pipeline
has the right shape and we can plug them in later without changing the API.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FactorAdjustment:
    """
    Multiplicative adjustments applied to xG_home and xG_away.

    All factors default to 1.0 (no effect). Composing factors is just
    multiplying them together.
    """

    home_xg_multiplier: float = 1.0
    away_xg_multiplier: float = 1.0
    notes: list[str] = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []

    def combine(self, other: "FactorAdjustment") -> "FactorAdjustment":
        return FactorAdjustment(
            home_xg_multiplier=self.home_xg_multiplier * other.home_xg_multiplier,
            away_xg_multiplier=self.away_xg_multiplier * other.away_xg_multiplier,
            notes=self.notes + other.notes,
        )


def rest_days_adjustment(home_rest: int | None, away_rest: int | None) -> FactorAdjustment:
    """
    Teams playing on short rest score modestly less. Empirically the effect
    is small (1-2% per day below 4 days rest in PL). We apply a simple linear
    penalty below 4 days, capped at 8% total reduction.

    `None` means "we don't know" — treat as standard 4+ day rest.
    """
    def _penalty(days: int | None) -> float:
        if days is None or days >= 4:
            return 1.0
        # 3 days = 0.98, 2 days = 0.96, 1 day = 0.92 (after the floor)
        reduction = (4 - days) * 0.02
        return max(0.92, 1.0 - reduction)

    home_mult = _penalty(home_rest)
    away_mult = _penalty(away_rest)
    notes = []
    if home_rest is not None and home_rest < 4:
        notes.append(f"home on {home_rest}d rest (-{int((1 - home_mult) * 100)}%)")
    if away_rest is not None and away_rest < 4:
        notes.append(f"away on {away_rest}d rest (-{int((1 - away_mult) * 100)}%)")

    return FactorAdjustment(
        home_xg_multiplier=home_mult,
        away_xg_multiplier=away_mult,
        notes=notes,
    )


def injury_adjustment(
    home_injuries: list | None = None,
    away_injuries: list | None = None,
    home_xg_impact: float | None = None,
    away_xg_impact: float | None = None,
) -> FactorAdjustment:
    """
    Compute xG impact from injury lists.

    Each injury contributes a small multiplicative penalty to that team's
    expected goals. Position weights — losing a starting forward hurts
    scoring more than losing a fullback. The model doesn't know who is a
    *starter* yet (Phase 3.5 work), so we apply a flat per-player penalty
    weighted by position and cap the total at -25% (we never zero a team out).

    Backwards-compat: callers can still pass raw `home_xg_impact` floats
    if they have them already (e.g. from a manual override or testing).
    """
    if home_xg_impact is not None or away_xg_impact is not None:
        return FactorAdjustment(
            home_xg_multiplier=1.0 + (home_xg_impact or 0.0),
            away_xg_multiplier=1.0 + (away_xg_impact or 0.0),
            notes=[],
        )

    # Position weights for xG impact. Conservative — even losing a star
    # forward only knocks ~6% off team xG since teams have squads.
    POSITION_IMPACT = {
        "Attacker": 0.06,
        "Forward": 0.06,
        "Midfielder": 0.04,
        "Defender": 0.025,
        "Goalkeeper": 0.05,  # affects defense, but we apply as xG-against; for now lump in
    }
    DEFAULT_IMPACT = 0.03

    def _team_impact(injuries: list | None) -> tuple[float, list[str]]:
        if not injuries:
            return 0.0, []
        total = 0.0
        names: list[str] = []
        for inj in injuries:
            position = getattr(inj, "player_position", None) or ""
            # API positions vary: "Attacker", "Goalkeeper", or empty
            impact = POSITION_IMPACT.get(position, DEFAULT_IMPACT)
            total += impact
            names.append(getattr(inj, "player_name", "?"))
        # Cap at 25% reduction
        capped = min(0.25, total)
        return capped, names

    home_reduction, home_names = _team_impact(home_injuries)
    away_reduction, away_names = _team_impact(away_injuries)

    notes = []
    if home_names:
        notes.append(f"home missing {len(home_names)} (-{int(home_reduction * 100)}% xG)")
    if away_names:
        notes.append(f"away missing {len(away_names)} (-{int(away_reduction * 100)}% xG)")

    return FactorAdjustment(
        home_xg_multiplier=1.0 - home_reduction,
        away_xg_multiplier=1.0 - away_reduction,
        notes=notes,
    )


def weather_adjustment(rain_mm: float | None = None) -> FactorAdjustment:
    """
    Placeholder. Heavy rain (>5mm) historically reduces total goals ~6%.
    Effect is symmetric (both sides score less). Phase 3 wires a weather API.
    """
    if rain_mm is None or rain_mm < 5:
        return FactorAdjustment()
    reduction = min(0.10, 0.06 + (rain_mm - 5) * 0.005)
    mult = 1.0 - reduction
    return FactorAdjustment(
        home_xg_multiplier=mult,
        away_xg_multiplier=mult,
        notes=[f"heavy rain {rain_mm}mm (-{int(reduction * 100)}% goals)"],
    )


def lineup_adjustment(
    home_starters: list | None = None,
    away_starters: list | None = None,
    home_recent_xi_freq: dict[str, float] | None = None,
    away_recent_xi_freq: dict[str, float] | None = None,
) -> FactorAdjustment:
    """
    xG adjustment based on the *announced* starting XI vs the team's recent
    regular starters. This complements `injury_adjustment` — injuries tell us
    who's *unavailable*; lineups tell us who's *actually playing today*
    (rotation, tactical rest, surprise omissions).

    Logic:
      - For each team, compute "missing-regulars" as the count of players who
        usually start (≥50% of recent matches) but are NOT in today's XI.
      - Each missing regular knocks ~3% off team xG, capped at 15% total
        (we already capped injuries at 25% — this is on top, but the two are
        composed multiplicatively so total reduction is bounded).
      - If we have no lineup data (`starters` is None or empty), this returns
        a neutral adjustment.

    Args:
      home_starters: list of Lineup rows with is_starter=True
      away_starters: ditto
      home_recent_xi_freq: dict of player_name → freq in recent XIs (0..1).
                          If None, fallback to a neutral effect.
    """
    if not home_starters and not away_starters:
        return FactorAdjustment()

    PER_MISSING = 0.03
    MAX_REDUCTION = 0.15
    REGULAR_THRESHOLD = 0.5

    def _team_impact(
        starters: list | None,
        recent_freq: dict[str, float] | None,
    ) -> tuple[float, list[str]]:
        if not starters or not recent_freq:
            return 0.0, []
        starter_names = {getattr(s, "player_name", "") for s in starters}
        regulars = {name for name, f in recent_freq.items() if f >= REGULAR_THRESHOLD}
        missing = regulars - starter_names
        if not missing:
            return 0.0, []
        reduction = min(MAX_REDUCTION, len(missing) * PER_MISSING)
        return reduction, sorted(missing)

    home_red, home_missing = _team_impact(home_starters, home_recent_xi_freq)
    away_red, away_missing = _team_impact(away_starters, away_recent_xi_freq)

    notes = []
    if home_missing:
        notes.append(
            f"home XI missing {len(home_missing)} regular(s) "
            f"(-{int(home_red * 100)}% xG)"
        )
    if away_missing:
        notes.append(
            f"away XI missing {len(away_missing)} regular(s) "
            f"(-{int(away_red * 100)}% xG)"
        )

    return FactorAdjustment(
        home_xg_multiplier=1.0 - home_red,
        away_xg_multiplier=1.0 - away_red,
        notes=notes,
    )


def xi_strength_adjustment(
    home_atk_mult: float = 1.0,
    home_def_mult: float = 1.0,
    away_atk_mult: float = 1.0,
    away_def_mult: float = 1.0,
    notes: list[str] | None = None,
) -> FactorAdjustment:
    """
    Build a FactorAdjustment from a pair of XI strength multipliers.

    Phase 6b: composes the player-aware adjustments from team_strength.py
    into the standard FactorAdjustment shape.

    home_xg is affected by both home attack strength AND away defense strength:
      - Stronger home XI attack → more home xG
      - Stronger away XI defense → less home xG (defense multiplier is < 1)

    away_xg likewise affected by away attack and home defense.

    Note: home_def_mult and away_def_mult are "opp xG multipliers", so
    they apply to the *other* side's xG.
    """
    return FactorAdjustment(
        home_xg_multiplier=home_atk_mult * away_def_mult,
        away_xg_multiplier=away_atk_mult * home_def_mult,
        notes=notes or [],
    )


def park_factor_adjustment(venue: str | None, sport_is_baseball: bool) -> FactorAdjustment:
    """
    MLB-only park factor as a multiplicative xG adjustment.

    Applies the same factor to both home and away teams' expected runs.
    For Wrigley specifically, layers a wind-based modifier on top of the
    base park factor — but only if wind data is known and meaningful.
    (Wind direction isn't currently passed through; that's a Phase 12.1
    extension. For now Wrigley uses just its base 1.02 PF.)

    Soccer always returns the neutral identity (1.0, 1.0). The effect size
    in PL/CL stadiums is well below model noise — not worth modeling.

    Args:
        venue: stadium name as stored on Match.venue
        sport_is_baseball: short-circuits to neutral for non-MLB sports

    Returns:
        FactorAdjustment with park_factor applied to both teams. Notes
        list contains one entry when the PF is materially different from
        neutral (|PF - 1| >= 0.03).
    """
    if not sport_is_baseball:
        return FactorAdjustment()
    from src.models.park_factors import get_park_factor
    pf = get_park_factor(venue)
    notes = []
    if abs(pf - 1.0) >= 0.03:
        direction = "hitter's park" if pf > 1.0 else "pitcher's park"
        notes.append(f"{venue}: {direction} (PF {pf:.2f})")
    return FactorAdjustment(
        home_xg_multiplier=pf,
        away_xg_multiplier=pf,
        notes=notes,
    )
