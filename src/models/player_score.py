"""
Player power-score model — Phase 6a.

Computes a single rating per player from their season stats. Design goals:

1. **Transparent.** Every number can be traced back to source stats. No
   black-box ML — this is a weighted composite with explainable parts.

2. **Position-aware.** A goalkeeper with 50 saves shouldn't be rated against
   a striker with 20 goals on the same scale. Position-specific weight maps.

3. **Per-90 normalized.** Raw counters favor minutes. We normalize to per-90
   to surface efficiency, then weight by minutes played so a great player
   with 200 minutes doesn't outrank a great player with 2,000.

4. **Shrunk for small samples.** A player with 90 minutes and 1 goal has a
   90-minute goals-per-90 of 1.0 — silly. We shrink rates toward league
   averages using a Bayesian-ish weighting (more minutes = more weight on
   actual rate, fewer minutes = more weight on prior).

5. **Composite to a 0-100 scale.** Final score is bounded for UI sanity.
   League average outfield = 50. Star players cluster ~75-85. World-class
   100s should be rare (think peak Messi).

This is v1. Real iteration happens after the rankings show up in the UI
and you look at them and say "where the hell is Rice." The weights and
priors below are starting points, not gospel.
"""
from __future__ import annotations

from dataclasses import dataclass

# Position categories — derived from API-Football's "position" field which
# returns strings like "Attacker", "Midfielder", "Defender", "Goalkeeper".
POSITION_ATTACKER = "Attacker"
POSITION_MIDFIELDER = "Midfielder"
POSITION_DEFENDER = "Defender"
POSITION_GOALKEEPER = "Goalkeeper"


def _normalize_position(raw: str | None) -> str:
    """Map a raw position string to one of the four buckets."""
    if not raw:
        return POSITION_MIDFIELDER  # safe default
    raw_lower = raw.lower()
    if "goal" in raw_lower or raw_lower == "g":
        return POSITION_GOALKEEPER
    if "defen" in raw_lower or raw_lower == "d":
        return POSITION_DEFENDER
    if "midfield" in raw_lower or raw_lower == "m":
        return POSITION_MIDFIELDER
    if "attack" in raw_lower or "forward" in raw_lower or "striker" in raw_lower or raw_lower in ("a", "f"):
        return POSITION_ATTACKER
    return POSITION_MIDFIELDER


# Per-90 weights per position. Each row is the contribution per
# (stat-per-90) point. Sum of weights ≈ comparable across positions so
# scores are commensurate.
#
# Example: an attacker scoring 0.5 goals/90 contributes 0.5 * 18 = 9 to
# their raw score. A midfielder with the same rate contributes 0.5 * 14 = 7.
# Defenders get less credit for goals (rare) and more for tackles.
WEIGHTS: dict[str, dict[str, float]] = {
    POSITION_ATTACKER: {
        "goals_per_90": 18.0,
        "assists_per_90": 9.0,
        "shots_per_90": 1.5,
        "shots_on_target_per_90": 2.5,
        "key_passes_per_90": 2.5,
        "dribbles_per_90": 1.5,
        "duels_won_per_90": 0.8,
        "tackles_per_90": 0.3,
        "interceptions_per_90": 0.3,
        # discipline penalties
        "yellow_per_90": -1.5,
        "red_per_90": -10.0,
    },
    POSITION_MIDFIELDER: {
        "goals_per_90": 14.0,
        "assists_per_90": 10.0,
        "shots_on_target_per_90": 2.0,
        "key_passes_per_90": 4.0,
        "dribbles_per_90": 2.0,
        "tackles_per_90": 2.5,
        "interceptions_per_90": 2.5,
        "duels_won_per_90": 1.5,
        "pass_accuracy_bonus": 5.0,   # accuracy >= 85% bonus
        "yellow_per_90": -1.0,
        "red_per_90": -8.0,
    },
    POSITION_DEFENDER: {
        "goals_per_90": 12.0,
        "assists_per_90": 8.0,
        "tackles_per_90": 3.5,
        "interceptions_per_90": 3.5,
        "duels_won_per_90": 2.0,
        "key_passes_per_90": 2.0,
        "pass_accuracy_bonus": 4.0,
        "yellow_per_90": -1.0,
        "red_per_90": -8.0,
    },
    POSITION_GOALKEEPER: {
        "saves_per_90": 4.0,
        "clean_sheet_rate": 25.0,  # cs / appearances
        "goals_conceded_per_90": -8.0,
        "pass_accuracy_bonus": 3.0,
        "yellow_per_90": -1.0,
        "red_per_90": -8.0,
    },
}


# Priors per position. These are roughly league-average per-90 rates.
# They're used to shrink a small-sample player's raw rates toward the
# league average for their position.
PRIORS_PER_90: dict[str, dict[str, float]] = {
    POSITION_ATTACKER: {
        "goals_per_90": 0.35, "assists_per_90": 0.20, "shots_on_target_per_90": 1.0,
        "shots_per_90": 2.5, "key_passes_per_90": 1.0, "dribbles_per_90": 1.5,
        "duels_won_per_90": 4.0, "tackles_per_90": 0.8, "interceptions_per_90": 0.4,
    },
    POSITION_MIDFIELDER: {
        "goals_per_90": 0.10, "assists_per_90": 0.15, "shots_on_target_per_90": 0.5,
        "key_passes_per_90": 1.2, "dribbles_per_90": 1.0, "tackles_per_90": 1.8,
        "interceptions_per_90": 1.2, "duels_won_per_90": 5.0,
    },
    POSITION_DEFENDER: {
        "goals_per_90": 0.05, "assists_per_90": 0.05, "tackles_per_90": 2.2,
        "interceptions_per_90": 1.8, "duels_won_per_90": 5.5, "key_passes_per_90": 0.4,
    },
    POSITION_GOALKEEPER: {
        "saves_per_90": 3.0, "goals_conceded_per_90": 1.2,
    },
}


#: Below this, the player is "low-sample" and we shrink heavily.
SHRINKAGE_MINUTES_HALFLIFE = 900  # 10 full matches

#: Per-90 metric normalization — clip extreme values for stability.
MAX_PER_90 = {
    "goals_per_90": 1.5,
    "assists_per_90": 1.0,
    "shots_per_90": 6.0,
    "shots_on_target_per_90": 3.0,
    "key_passes_per_90": 5.0,
    "dribbles_per_90": 6.0,
    "tackles_per_90": 6.0,
    "interceptions_per_90": 6.0,
    "duels_won_per_90": 12.0,
    "saves_per_90": 8.0,
}


@dataclass
class PlayerScoreBreakdown:
    """A score plus enough trace info to explain it in the UI."""

    score: float
    position_bucket: str
    minutes_played: int
    appearances: int
    minutes_weight: float   # 0..1, how much we trust the rate stats
    per_90: dict[str, float]
    contributions: dict[str, float]  # weighted contribution per stat
    raw_subtotal: float
    league_avg_baseline: float
    notes: list[str]

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "position_bucket": self.position_bucket,
            "minutes_played": self.minutes_played,
            "appearances": self.appearances,
            "minutes_weight": round(self.minutes_weight, 2),
            "per_90": {k: round(v, 2) for k, v in self.per_90.items()},
            "contributions": {k: round(v, 2) for k, v in self.contributions.items()},
            "raw_subtotal": round(self.raw_subtotal, 1),
            "league_avg_baseline": round(self.league_avg_baseline, 1),
            "notes": self.notes,
        }


def _per_90(value: float | None, minutes: int) -> float:
    """Per-90 rate. Returns 0 for zero minutes (caller handles via shrinkage)."""
    if not minutes or value is None:
        return 0.0
    return (value / minutes) * 90.0


def _shrink(raw_rate: float, prior_rate: float, minutes: int) -> float:
    """
    Bayesian shrinkage toward the prior. With minutes=0 returns prior; with
    minutes >> halflife returns raw. Halflife = SHRINKAGE_MINUTES_HALFLIFE.

    Formula: weight = minutes / (minutes + halflife)
    shrunk  = weight * raw_rate + (1 - weight) * prior_rate
    """
    if minutes <= 0:
        return prior_rate
    w = minutes / (minutes + SHRINKAGE_MINUTES_HALFLIFE)
    return w * raw_rate + (1 - w) * prior_rate


def compute_player_score(stats_row) -> PlayerScoreBreakdown:
    """
    Compute a 0-100 power score for a player given their PlayerSeasonStats row.

    Pass a SQLAlchemy PlayerSeasonStats object or any object with the same
    attribute names — counters and pass_accuracy.

    Algorithm:
      1. Bucket player by position.
      2. Compute raw per-90 rates for every counter we care about.
      3. Shrink each rate toward its position's league-average prior, weighted
         by minutes played.
      4. Clip to MAX_PER_90 ranges so a single 200-minute spree can't
         dominate.
      5. Multiply each shrunk rate by the position's weight; sum.
      6. Add bonuses (pass accuracy, clean sheets).
      7. Subtract per-90 penalties for cards.
      8. Shift to a centered 0-100 scale, where 50 is league-average for the
         position. Currently scaled linearly around a position baseline.
    """
    position = _normalize_position(getattr(stats_row, "position", None) or
                                    getattr(stats_row.player, "position", None)
                                    if hasattr(stats_row, "player") else None)

    minutes = int(getattr(stats_row, "minutes", 0) or 0)
    apps = int(getattr(stats_row, "appearances", 0) or 0)
    weights = WEIGHTS[position]
    priors = PRIORS_PER_90[position]

    # Compute per-90 rates for each input stat
    rates_raw = {
        "goals_per_90": _per_90(stats_row.goals, minutes),
        "assists_per_90": _per_90(stats_row.assists, minutes),
        "shots_per_90": _per_90(stats_row.shots, minutes),
        "shots_on_target_per_90": _per_90(stats_row.shots_on_target, minutes),
        "key_passes_per_90": _per_90(stats_row.key_passes, minutes),
        "dribbles_per_90": _per_90(stats_row.dribble_success, minutes),
        "tackles_per_90": _per_90(stats_row.tackles, minutes),
        "interceptions_per_90": _per_90(stats_row.interceptions, minutes),
        "duels_won_per_90": _per_90(stats_row.duels_won, minutes),
        "yellow_per_90": _per_90(stats_row.yellow_cards, minutes),
        "red_per_90": _per_90(stats_row.red_cards, minutes),
        "saves_per_90": _per_90(stats_row.saves, minutes) if stats_row.saves is not None else 0.0,
        "goals_conceded_per_90": (
            _per_90(stats_row.goals_conceded, minutes) if stats_row.goals_conceded is not None else 0.0
        ),
    }

    # Shrink each rate (only counters that have a prior — cards we leave raw,
    # they should hurt regardless of sample).
    rates_shrunk = {}
    for k, v in rates_raw.items():
        if k in priors:
            rates_shrunk[k] = _shrink(v, priors[k], minutes)
        else:
            rates_shrunk[k] = v

    # Clip extremes
    for k, v in list(rates_shrunk.items()):
        cap = MAX_PER_90.get(k)
        if cap is not None and v > cap:
            rates_shrunk[k] = cap

    # Apply weights
    contributions: dict[str, float] = {}
    raw_subtotal = 0.0
    for stat_key, weight in weights.items():
        if stat_key == "pass_accuracy_bonus":
            # Bonus only if pass accuracy >= 85%
            pa = getattr(stats_row, "pass_accuracy", None)
            if pa is not None and pa >= 0.85:
                contribution = weight * ((pa - 0.85) / 0.15)  # 0 at 85%, 1.0× weight at 100%
            else:
                contribution = 0.0
        elif stat_key == "clean_sheet_rate":
            cs = getattr(stats_row, "clean_sheets", None) or 0
            rate = (cs / apps) if apps > 0 else 0.0
            contribution = weight * rate
        elif stat_key in rates_shrunk:
            contribution = weight * rates_shrunk[stat_key]
        else:
            contribution = 0.0
        if contribution != 0:
            contributions[stat_key] = contribution
            raw_subtotal += contribution

    # League-avg baseline: what would a "perfectly average" player at this
    # position score? Used as the 50-anchor in the final scale. Includes
    # both positive contributors AND negatives like goals_conceded for
    # keepers — otherwise the position baseline is artificially low and
    # everyone scores too high.
    baseline = 0.0
    for stat_key, weight in weights.items():
        if stat_key in priors:
            baseline += weight * priors[stat_key]
        elif stat_key == "pass_accuracy_bonus":
            # Assume league-average pass accuracy ~80% → no bonus
            pass
        elif stat_key == "clean_sheet_rate":
            # Average keeper clean-sheet rate ~25%
            baseline += weight * 0.25

    # Convert raw to 0-100. The linear shift around the position baseline:
    # 50 at baseline, every additional weighted point adds ~3.5 to the score.
    # Calibrated so an elite player (rate at ~3x prior across all weighted
    # categories) lands roughly 80-90, and a league-average player lands
    # near 50. Iterate after seeing real ranked data.
    score = 50.0 + (raw_subtotal - baseline) * 3.5
    score = max(0.0, min(100.0, score))

    # Confidence weight for downstream consumers
    minutes_weight = minutes / (minutes + SHRINKAGE_MINUTES_HALFLIFE) if minutes > 0 else 0.0

    notes = []
    if minutes < 270:
        notes.append(f"low sample ({minutes} min)")
    if rates_shrunk["red_per_90"] > 0:
        notes.append("has red card(s)")

    return PlayerScoreBreakdown(
        score=score,
        position_bucket=position,
        minutes_played=minutes,
        appearances=apps,
        minutes_weight=minutes_weight,
        per_90={k: round(v, 3) for k, v in rates_raw.items()},
        contributions=contributions,
        raw_subtotal=raw_subtotal,
        league_avg_baseline=baseline,
        notes=notes,
    )


def rank_team(stats_rows: list, top_n: int | None = None) -> list[dict]:
    """
    Rank a team's players by power score.

    Pass a list of PlayerSeasonStats rows. Returns a list of dicts ordered
    by score desc, each containing the score breakdown plus player metadata.
    """
    ranked = []
    for row in stats_rows:
        breakdown = compute_player_score(row)
        player_obj = getattr(row, "player", None)
        ranked.append({
            "player_id": row.player_id,
            "name": player_obj.name if player_obj else "?",
            "position": player_obj.position if player_obj else None,
            "team_id": row.team_id,
            "season": row.season,
            "score": breakdown.score,
            "position_bucket": breakdown.position_bucket,
            "minutes": breakdown.minutes_played,
            "appearances": breakdown.appearances,
            "minutes_weight": breakdown.minutes_weight,
            "notes": breakdown.notes,
            "breakdown": breakdown.as_dict(),
        })
    ranked.sort(key=lambda r: -r["score"])
    if top_n:
        ranked = ranked[:top_n]
    return ranked
