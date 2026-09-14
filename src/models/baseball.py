"""
Baseball scoring model.

Three components compose the prediction:

1. **Pythagorean win expectation** (Bill James, refined by Pinto/Davenport).
   The classic relationship: WinPct = R^x / (R^x + RA^x). With x≈1.83 for MLB.
   This gives us a baseline "talent gap" between two teams using full-season
   runs scored and runs allowed.

2. **Negative binomial run distribution.** Run scoring in baseball isn't
   Poisson — it's overdispersed (the variance exceeds the mean) because of
   crooked innings, the platoon effect, lineup turnover. Negative binomial
   fits the actual distribution much better than Poisson. We parameterize
   it by mean and a dispersion parameter k.

3. **Starting pitcher adjustment.** In baseball this is huge — way bigger
   than any soccer player effect. A great starter knocks ~0.5 runs off a
   team's expected scoring; a bad one adds 0.5+. We model this as a
   multiplicative adjustment on the opposing team's expected runs, derived
   from the pitcher's recent ERA vs league ERA.

Output:
  - p_home_win, p_away_win (no draws in baseball)
  - expected runs each side
  - over/under probability for a configurable line (default 8.5 runs)
  - most likely scoreline
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

#: Pythagorean exponent for MLB. Originally 2 (James 1979), refined to 1.83.
DEFAULT_PYTH_EXPONENT = 1.83

#: Mean total runs per MLB game (combined both teams). Modern era ~9.0.
DEFAULT_LEAGUE_RUNS_PER_GAME = 9.0

#: Negative binomial dispersion parameter k. Lower = more variance.
#: Empirical fit on MLB run distributions: k ≈ 4.0 (vs Poisson which would be ∞).
DEFAULT_DISPERSION_K = 4.0

#: Home field advantage in baseball — small, and SHRINKING leaguewide.
#: [2026-06-06 calibration finding] The old 0.15 implied a ~52% home win
#: rate, but 2026 actual is ~49.1% (home advantage has been declining for
#: years). This made HOME picks systematically overconfident: home picks
#: calibrated at -4.5pp overall and -13pp when high-confidence, while AWAY
#: picks were near-perfect (+0.1pp). The inflated home term, stacked onto an
#: already-favored home team, was the main driver of the 60-70% overconfidence
#: (NOT the bullpen swing, which affected far fewer games). Cut 0.15 → 0.08
#: to calibrate most of the gap while staying conservative on a one-season
#: sample (didn't go to 0 — some home edge is real: last at-bat, familiarity).
#: To revert: set DEFAULT_HOME_RUN_BOOST = 0.15 (or home_run_boost=0.15 on the
#: config). Old behavior exactly reproduced.
DEFAULT_HOME_RUN_BOOST = 0.08
PRIOR_HOME_RUN_BOOST = 0.15  # pre-2026-06-06 value, for reference/revert

#: League-average ERA used as the baseline for pitcher quality. Recent years ~4.20.
DEFAULT_LEAGUE_ERA = 4.20

#: Max runs we cap the discrete distribution at. P(≥20 runs in a game) is negligible.
MAX_RUNS = 20


@dataclass
class BaseballConfig:
    pyth_exponent: float = DEFAULT_PYTH_EXPONENT
    league_runs_per_game: float = DEFAULT_LEAGUE_RUNS_PER_GAME
    dispersion_k: float = DEFAULT_DISPERSION_K
    home_run_boost: float = DEFAULT_HOME_RUN_BOOST
    league_era: float = DEFAULT_LEAGUE_ERA
    max_runs: int = MAX_RUNS
    default_total_line: float = 8.5
    # Phase 12.5: how the pitcher multiplier is anchored.
    #   "team_ra" (new, default) — anchor to the team's own runs-allowed so
    #     pitching isn't double-counted (team RA already encodes it). Only
    #     the deviation of this start from the team norm adjusts runs.
    #   "league" (old behavior) — anchor to flat league ERA. Double-counts
    #     pitching but kept for A/B comparison and quick revert.
    # To revert: set pitcher_anchor_mode="league" and pitcher_damping=0.5.
    pitcher_anchor_mode: str = "team_ra"
    pitcher_damping: float = 0.35  # was 0.5 under "league" anchor
    # Phase 12.6: mid-band probability recalibration. The 60-70% confidence
    # band is empirically overconfident (~-16pp on n=355) while 50-60% and
    # 70%+ are well-calibrated. This applies a monotonic, continuity-preserving
    # compression to favorite probabilities that fall in [recal_lo, recal_hi],
    # pulling them toward recal_target while leaving the calibrated regions
    # untouched. Disabled by default (recal_enabled=False) — turn on via
    # set-config after reviewing the before/after. Reversible.
    recal_enabled: bool = True
    recal_lo: float = 0.60      # band lower edge (50-60% below is untouched)
    recal_hi: float = 0.70      # band upper edge (70%+ above is untouched)
    recal_target: float = 0.555  # where recal_lo maps to (bottom of compressed band)
    # Phase 12.7: market blend. Empirically (post-recal, n=56) the model is
    # well-calibrated when it AGREES with the market (+5pp) but badly
    # overconfident when it DISAGREES (-20pp, and -35pp on >8pp disagreements):
    # its disagreements are, on average, the model missing market information
    # (scratches, weather, sharp money), not finding value. This blends the
    # model probability partway toward the de-vigged market probability:
    #   p_blended = (1 - w) * p_model + w * p_market
    # The blend SELF-TARGETS disagreement: when model≈market it does nothing;
    # it only bites when they diverge, scaled by divergence. w<1 deliberately
    # PRESERVES the model as an independent voice — it does NOT collapse to the
    # market (the whole point is still to catch games the market gets wrong),
    # it just stops the model betting full confidence on disagreements that
    # have been mostly wrong. Disabled by default; enable via set-config.
    market_blend_enabled: bool = False
    market_blend_w: float = 0.5  # 0 = pure model, 1 = pure market; 0.5 = split
    # Phase 12.8: run-input regression-to-mean. The expected-runs formula
    # multiplies favorite RS by opponent RA: home_xr = (RS * opp_RA)/league.
    # Both inputs are regression-prone, and the model only shrinks them for
    # small SAMPLES (n/(n+10)) — by midseason that's ~off. So two extreme,
    # un-regressed inputs COMPOUND multiplicatively: the offense-mechanism
    # diagnostic showed high-fav-offense AND weak-opponent games at -23.5pp
    # (vs -6 / -10 for either alone, +7 for both-normal). The fix shrinks each
    # team's RS/RA toward league mean BEFORE multiplying, so extremes get
    # pulled in and the product can't compound two tails. Strength derived from
    # the luck/talent variance split (~40-59% would be 'correct'); we default
    # to a CONSERVATIVE 0.25 to avoid flattening real edges. Leaves league-
    # average inputs untouched by construction. Disabled by default; enable via
    # set-config. The shrink is toward `run_shrink_mean` (league r/g per team).
    run_shrink_enabled: bool = False
    run_shrink_frac: float = 0.25   # fraction of the way from observed to mean
    run_shrink_mean: float = 4.4    # league runs/game per team (shrink target)
    # Phase 12.9: starter shrinkage on STARTER-RELEVANT innings. The starter
    # ERA shrink (30 IP halflife) denominates on total season IP — which for
    # converted relievers / openers is mostly RELIEF innings. Relief ERA is a
    # biased estimator of the same arm's performance as a starter (times-
    # through-order penalty), so a 3-start pitcher with 67 relief-heavy IP
    # enters ~70% unshrunk on a sample that mostly doesn't transfer. When
    # enabled, the shrink weight uses effective_ip = min(ip, per_start × GS):
    # career-long starters are untouched (ip < 6×GS is normal), while low-GS
    # pitchers shrink on the innings their starts could plausibly represent.
    # Disabled by default; enable via set-config AFTER the leakage-free
    # backtest confirms it (same discipline as run_shrink).
    starter_eff_ip_enabled: bool = False
    starter_ip_per_start: float = 6.0  # cap: innings credited per start

    def as_dict(self) -> dict:
        return {
            "pyth_exponent": self.pyth_exponent,
            "league_runs_per_game": self.league_runs_per_game,
            "dispersion_k": self.dispersion_k,
            "home_run_boost": self.home_run_boost,
            "league_era": self.league_era,
            "max_runs": self.max_runs,
            "default_total_line": self.default_total_line,
            "pitcher_anchor_mode": self.pitcher_anchor_mode,
            "pitcher_damping": self.pitcher_damping,
            "recal_enabled": self.recal_enabled,
            "recal_lo": self.recal_lo,
            "recal_hi": self.recal_hi,
            "recal_target": self.recal_target,
            "market_blend_enabled": self.market_blend_enabled,
            "market_blend_w": self.market_blend_w,
            "run_shrink_enabled": self.run_shrink_enabled,
            "run_shrink_frac": self.run_shrink_frac,
            "run_shrink_mean": self.run_shrink_mean,
            "starter_eff_ip_enabled": self.starter_eff_ip_enabled,
            "starter_ip_per_start": self.starter_ip_per_start,
        }


def starter_shrink_weight(ip: float, games_started: int, cfg: "BaseballConfig",
                          halflife_ip: float = 30.0) -> tuple[float, float]:
    """
    Shrink weight for a starter's ERA toward league average.

    Returns (effective_ip, w) where w = eff_ip / (eff_ip + halflife) is the
    weight on the OBSERVED ERA (1-w goes to league average).

    With starter_eff_ip_enabled, effective innings are capped at
    per_start × GS so relief-heavy IP doesn't masquerade as starter evidence;
    otherwise effective_ip is raw IP (legacy behavior, bit-identical).
    """
    eff_ip = float(ip)
    if getattr(cfg, "starter_eff_ip_enabled", False):
        eff_ip = min(eff_ip, getattr(cfg, "starter_ip_per_start", 6.0)
                     * max(games_started, 0))
    w = eff_ip / (eff_ip + halflife_ip) if eff_ip > 0 else 0.0
    return eff_ip, w


@dataclass
class TeamRunProfile:
    """A team's offensive and defensive run rates over a recent window."""

    runs_scored_per_game: float = 4.5  # half the league avg
    runs_allowed_per_game: float = 4.5
    # Phase 12.1: breakdown into season vs recent components for visibility.
    # These are the inputs to the final blended numbers above. None when
    # recent weighting didn't apply (small sample or recent_weight=0).
    rsg_season: float | None = None
    rag_season: float | None = None
    rsg_recent: float | None = None
    rag_recent: float | None = None
    games_recent: int = 0

    def as_dict(self) -> dict:
        return {
            "runs_scored_per_game": self.runs_scored_per_game,
            "runs_allowed_per_game": self.runs_allowed_per_game,
        }


@dataclass
class PitcherStats:
    """Recent performance for a starting pitcher."""

    name: str = ""
    era: float | None = None  # recent ERA (lower = better)
    # Phase 12.3: whether we had real starter data (vs falling back to
    # bullpen-only / neutral). Used to widen prediction uncertainty when a
    # starter is unknown — missing information should reduce confidence,
    # not be silently treated as league-average.
    starter_known: bool = True

    def as_dict(self) -> dict:
        return {"name": self.name, "era": self.era}


@dataclass
class BaseballPrediction:
    home_xr: float  # expected runs home
    away_xr: float  # expected runs away
    p_home: float
    p_away: float
    p_over: float
    p_under: float
    over_under_line: float
    most_likely_score: tuple[int, int]
    most_likely_score_prob: float
    p_one_run: float = 0.0  # P(game decided by exactly 1 run) — closeness/variance signal
    totals_available: bool = True  # False when no real market line existed (O/U is a fallback, not actionable)
    p_blowup: float = 0.0  # P(either team scores >= 7 runs) — one-team-explosion / fragile-under signal
    p_home_blowup: float = 0.0  # P(home team >= 7 runs) — one-sided blowup risk
    p_away_blowup: float = 0.0  # P(away team >= 7 runs) — one-sided blowup risk

    def as_dict(self) -> dict:
        return {
            "home_xr": round(self.home_xr, 2),
            "away_xr": round(self.away_xr, 2),
            "p_home": round(self.p_home, 4),
            "p_away": round(self.p_away, 4),
            "p_over": round(self.p_over, 4),
            "p_under": round(self.p_under, 4),
            "over_under_line": self.over_under_line,
            "totals_available": self.totals_available,
            "most_likely_score": list(self.most_likely_score),
            "most_likely_score_prob": round(self.most_likely_score_prob, 4),
            "p_one_run": round(self.p_one_run, 4),
            "p_blowup": round(self.p_blowup, 4),
            "p_home_blowup": round(self.p_home_blowup, 4),
            "p_away_blowup": round(self.p_away_blowup, 4),
        }


# --------------------------------------------------------------------------
# Profile estimation
# --------------------------------------------------------------------------


def estimate_run_profiles(
    matches: list[dict],
    recent_weight: float = 0.30,
    recent_window: int = 10,
    recent_min: int = 5,
) -> dict[int, TeamRunProfile]:
    """
    From a list of finished games (dicts with home_team_id/away_team_id/
    home_score/away_score, and optionally utc_date), compute per-team
    scored/allowed run rates.

    Phase 12.1: blends season-to-date averages with recent-form averages.
    A team in a 5-game cold streak gets its expected runs pulled down
    proportionally without overreacting to noise.

    The blend is:
        profile = (1 - recent_weight) * season_avg + recent_weight * recent_avg

    With defaults (recent_weight=0.30, recent_window=10), this means:
        - The team's last 10 games count for 30% of the projection
        - Season-to-date counts for the other 70%
        - Teams with fewer than `recent_min` recent games use season only

    To enable recent weighting, callers should include `utc_date` in each
    game dict. Without it, the function falls back to plain season averages
    (preserving the prior behavior).

    Light shrinkage toward 4.5 RPG for teams with few games (regularization)
    is applied to the SEASON component before blending. Recent average is
    used as-is; the blend itself dampens recent extremes.

    Args:
        matches: list of dicts with home_team_id, away_team_id, home_score,
                 away_score, and optionally utc_date.
        recent_weight: float in [0,1]. Default 0.30. Pass 0.0 to disable
                       recent-form blending entirely (old behavior).
        recent_window: int. Last N games to count as "recent". Default 10.
        recent_min: int. Below this number of recent games, skip recent
                    weighting for that team. Default 5.
    """
    scored: dict[int, list[tuple[float, object]]] = {}
    allowed: dict[int, list[tuple[float, object]]] = {}

    for m in matches:
        h = m["home_team_id"]
        a = m["away_team_id"]
        hs = m["home_score"]
        as_ = m["away_score"]
        if hs is None or as_ is None:
            continue
        # utc_date may be None if caller didn't pass it; we still store the
        # game but recent weighting will be skipped for teams missing dates.
        date = m.get("utc_date")
        scored.setdefault(h, []).append((hs, date))
        allowed.setdefault(h, []).append((as_, date))
        scored.setdefault(a, []).append((as_, date))
        allowed.setdefault(a, []).append((hs, date))

    profiles: dict[int, TeamRunProfile] = {}
    for team_id in set(scored) | set(allowed):
        s_list = scored.get(team_id, [])
        a_list = allowed.get(team_id, [])

        # ---- Season averages (existing behavior)
        s_values = [v for v, _ in s_list]
        a_values = [v for v, _ in a_list]
        rsg_season = sum(s_values) / len(s_values) if s_values else 4.5
        rag_season = sum(a_values) / len(a_values) if a_values else 4.5
        # Shrink toward league avg for small samples — 10 games of regularization
        n = min(len(s_values), len(a_values))
        weight = n / (n + 10)
        rsg_season = weight * rsg_season + (1 - weight) * 4.5
        rag_season = weight * rag_season + (1 - weight) * 4.5

        # ---- Recent averages (Phase 12.1)
        # Only attempt if recent_weight > 0 and we have dated games. Sort
        # team's games by date descending (most recent first), take top N.
        rsg = rsg_season
        rag = rag_season
        rsg_recent = None
        rag_recent = None
        games_recent = 0
        if recent_weight > 0.0:
            dated_s = [(v, d) for v, d in s_list if d is not None]
            dated_a = [(v, d) for v, d in a_list if d is not None]
            if len(dated_s) >= recent_min and len(dated_a) >= recent_min:
                dated_s.sort(key=lambda t: t[1], reverse=True)
                dated_a.sort(key=lambda t: t[1], reverse=True)
                recent_s = [v for v, _ in dated_s[:recent_window]]
                recent_a = [v for v, _ in dated_a[:recent_window]]
                rsg_recent = sum(recent_s) / len(recent_s)
                rag_recent = sum(recent_a) / len(recent_a)
                games_recent = min(len(recent_s), len(recent_a))
                rsg = (1 - recent_weight) * rsg_season + recent_weight * rsg_recent
                rag = (1 - recent_weight) * rag_season + recent_weight * rag_recent

        profiles[team_id] = TeamRunProfile(
            runs_scored_per_game=max(2.0, rsg),
            runs_allowed_per_game=max(2.0, rag),
            rsg_season=round(rsg_season, 3),
            rag_season=round(rag_season, 3),
            rsg_recent=round(rsg_recent, 3) if rsg_recent is not None else None,
            rag_recent=round(rag_recent, 3) if rag_recent is not None else None,
            games_recent=games_recent,
        )
    return profiles


# --------------------------------------------------------------------------
# Negative binomial PMF
# --------------------------------------------------------------------------


def _negbin_pmf(mean: float, k: float, x: int) -> float:
    """
    Negative binomial probability mass at integer x.

    Parameterized by mean (mu) and dispersion (k). When k → ∞ this reduces
    to Poisson. Lower k = more variance, which fits baseball run distributions.

    P(X=x) = C(x+k-1, x) * (k/(k+mu))^k * (mu/(k+mu))^x
    """
    if mean <= 0:
        return 1.0 if x == 0 else 0.0
    p = k / (k + mean)
    # log space for numerical stability
    log_coef = math.lgamma(x + k) - math.lgamma(k) - math.lgamma(x + 1)
    log_pmf = log_coef + k * math.log(p) + x * math.log(1 - p)
    return math.exp(log_pmf)


def _negbin_vector(mean: float, k: float, max_x: int) -> np.ndarray:
    """Pre-computed PMF over 0..max_x."""
    return np.array([_negbin_pmf(mean, k, x) for x in range(max_x + 1)])


# --------------------------------------------------------------------------
# Pitcher impact
# --------------------------------------------------------------------------


def _pitcher_multiplier(
    pitcher: PitcherStats | None,
    league_era: float,
    team_ra_per_game: float | None = None,
    anchor_mode: str = "team_ra",
    damping: float = 0.35,
) -> float:
    """
    Convert a starting pitcher's (blended starter+bullpen) ERA into a
    multiplier on the opposing team's expected runs.

    IMPORTANT — avoiding double-counting (Phase 12.5):
    The opposing team's `runs_allowed_per_game` ALREADY reflects that
    team's season pitching, including these same arms. If we also applied
    the pitcher's full ERA-vs-league signal, we'd count the team's pitching
    twice — once in their RA, once here — inflating confidence in games
    with a clear pitching edge (a likely contributor to the 60-70%
    overconfidence the calibration diagnostic found).

    anchor_mode:
      "team_ra" (default) — reference = the team's own RA-as-ERA, so only
        the DEVIATION of this start from the team norm adjusts runs. No
        double-count.
      "league" (legacy) — reference = flat league ERA. Double-counts
        pitching; kept for A/B comparison and quick revert.

    Effect is dampened and capped — ERA in a partial season is noisy.
    """
    if pitcher is None or pitcher.era is None or pitcher.era <= 0:
        return 1.0
    if anchor_mode == "team_ra" and team_ra_per_game and team_ra_per_game > 0:
        reference = team_ra_per_game
    else:
        reference = league_era
    ratio = pitcher.era / reference
    # Cap the effect: deviations beyond ±40% are noise
    ratio = max(0.7, min(1.4, ratio))
    return 1.0 + damping * (ratio - 1.0)


# --------------------------------------------------------------------------
# Predict
# --------------------------------------------------------------------------


def _recalibrate_favorite_prob(p: float, cfg: BaseballConfig) -> float:
    """
    Recalibrate an overconfident MID-BAND favorite probability, leaving the
    calibrated neighbors untouched.

    Empirically (n=355): 50-60% calibrated, 60-70% overconfident (~-16pp),
    70%+ calibrated (+2pp). The fix compresses ONLY [recal_lo, recal_hi) toward
    the band's true rate and leaves everything else as identity:

        p < recal_lo          -> p                      (50-60% untouched)
        recal_lo <= p < recal_hi -> linear into [recal_target, recal_hi_out]
        p >= recal_hi         -> p                      (70%+ untouched)

    The 70%+ band is deliberately NOT shrunk: it already wins ~76% on ~74%
    predicted, so pulling it down would make it underconfident. The two bands
    need to move in opposite-enough ways that a single smooth curve can't do
    it; a clamp on 60-70% can. There's a small discontinuity at recal_hi,
    which is immaterial in practice (negligible predictive mass sits exactly
    at the boundary, and ordering within each region is preserved).

    recal_target = where recal_lo maps to (the bottom of the compressed band).
    The band's upper input (recal_hi) maps to recal_hi_out, kept just under
    recal_hi so the compressed band sits below the untouched 70%+ region.
    Conservative by design: maps 67% -> ~59%, not to the raw noisy 43.6%
    (n=39) — corrects the real overconfidence without overfitting the thin
    extreme cell or ever inverting a pick.
    """
    if not cfg.recal_enabled:
        return p
    lo, hi, target = cfg.recal_lo, cfg.recal_hi, cfg.recal_target
    if p < lo or p >= hi:
        return p
    # Compress [lo, hi) into [target, hi_out), hi_out just below hi.
    hi_out = hi - 0.10  # top of band compresses to ~0.60 when hi=0.70
    frac = (p - lo) / (hi - lo)
    return target + frac * (hi_out - target)


def predict_game(
    home_profile: TeamRunProfile,
    away_profile: TeamRunProfile,
    home_pitcher: PitcherStats | None = None,
    away_pitcher: PitcherStats | None = None,
    config: BaseballConfig | None = None,
    factor_adjustment=None,  # FactorAdjustment from models.factors (rest, weather, etc.)
    market_total_line: float | None = None,  # real book O/U line; falls back to cfg default
) -> BaseballPrediction:
    """
    Run the full prediction for one game.

    Steps:
      1. Compute each side's expected runs as a function of:
         - their offensive rate × opponent's defensive rate / league avg
         - home-field run boost on the home side
         - opposing pitcher's quality multiplier
      2. Apply any factor adjustments (multiplicative — rest, weather, etc.)
      3. Build the run distribution matrix via negative binomial
      4. Sum over the matrix to get win probabilities (no draws)
      5. Sum tail for over/under
    """
    cfg = config or BaseballConfig()
    league_rpg_per_team = cfg.league_runs_per_game / 2.0

    # Phase 12.8: regress run inputs toward league mean BEFORE multiplying, so
    # two extreme regression-prone inputs don't compound (no-op unless enabled,
    # and league-average inputs are untouched by construction).
    def _shrink_run(x: float) -> float:
        if not cfg.run_shrink_enabled:
            return x
        f = cfg.run_shrink_frac
        return x * (1 - f) + cfg.run_shrink_mean * f

    home_rs = _shrink_run(home_profile.runs_scored_per_game)
    home_ra = _shrink_run(home_profile.runs_allowed_per_game)
    away_rs = _shrink_run(away_profile.runs_scored_per_game)
    away_ra = _shrink_run(away_profile.runs_allowed_per_game)

    # Base expected runs: bat against opp pitching
    home_xr_base = (home_rs * away_ra) / league_rpg_per_team
    away_xr_base = (away_rs * home_ra) / league_rpg_per_team

    # Home field
    home_xr_base += cfg.home_run_boost
    # Subtract a hair from away to keep totals roughly aligned with league avg
    away_xr_base = max(2.0, away_xr_base - cfg.home_run_boost * 0.4)

    # Pitcher adjustments — the opposing pitcher modifies *your* run scoring.
    # Anchor each pitcher's multiplier to THEIR OWN team's runs-allowed so we
    # don't double-count pitching that's already in the RA term above.
    # (Mode/damping configurable via BaseballConfig for A/B + revert.)
    away_pitcher_mult = _pitcher_multiplier(
        away_pitcher, cfg.league_era, away_profile.runs_allowed_per_game,
        anchor_mode=cfg.pitcher_anchor_mode, damping=cfg.pitcher_damping)
    home_pitcher_mult = _pitcher_multiplier(
        home_pitcher, cfg.league_era, home_profile.runs_allowed_per_game,
        anchor_mode=cfg.pitcher_anchor_mode, damping=cfg.pitcher_damping)
    home_xr = home_xr_base * away_pitcher_mult
    away_xr = away_xr_base * home_pitcher_mult

    # Factor adjustments (rest, weather, etc.) — same protocol as soccer
    if factor_adjustment is not None:
        home_xr *= factor_adjustment.home_xg_multiplier
        away_xr *= factor_adjustment.away_xg_multiplier

    # Floors so the distribution doesn't degenerate
    home_xr = max(1.0, home_xr)
    away_xr = max(1.0, away_xr)

    # Run distribution matrix
    max_runs = cfg.max_runs
    home_pmf = _negbin_vector(home_xr, cfg.dispersion_k, max_runs)
    away_pmf = _negbin_vector(away_xr, cfg.dispersion_k, max_runs)
    score_matrix = np.outer(home_pmf, away_pmf)

    # Win probabilities — no draws (treat tied cells as proportional draw → split)
    p_home = float(np.tril(score_matrix, -1).sum())
    p_away = float(np.triu(score_matrix, 1).sum())
    p_tie = float(np.trace(score_matrix))
    # Distribute tied probability mass proportionally; in real life these go to extras
    if p_home + p_away > 0:
        p_home += p_tie * (p_home / (p_home + p_away))
        p_away += p_tie * (p_away / (p_home + p_away))
    total = p_home + p_away
    if total > 0:
        p_home /= total
        p_away /= total

    # Phase 12.6: mid-band recalibration (no-op unless cfg.recal_enabled).
    # Recalibrate the FAVORITE side, set the other to the complement so they
    # still sum to 1. Identity outside [recal_lo, recal_hi].
    if cfg.recal_enabled:
        if p_home >= p_away:
            p_home = _recalibrate_favorite_prob(p_home, cfg)
            p_away = 1.0 - p_home
        else:
            p_away = _recalibrate_favorite_prob(p_away, cfg)
            p_home = 1.0 - p_away

    # Over/under. Use the real book line when we have it, so the over/under
    # probability is computed against the actual market total rather than a
    # hardcoded default. When NO market line exists we still compute a fallback
    # O/U (for internal continuity) but flag totals_available=False so the
    # betting layer knows this number is NOT actionable — better to say
    # "unavailable" than to emit a confident-looking phantom line.
    totals_available = market_total_line is not None
    line = market_total_line if market_total_line is not None else cfg.default_total_line
    threshold = int(math.floor(line)) + 1
    p_over = 0.0
    for i in range(max_runs + 1):
        for j in range(max_runs + 1):
            if i + j >= threshold:
                p_over += score_matrix[i, j]
    p_over = float(p_over)
    p_under = max(0.0, 1.0 - p_over)

    # Most likely score
    idx = np.unravel_index(np.argmax(score_matrix), score_matrix.shape)
    most_likely_score = (int(idx[0]), int(idx[1]))
    most_likely_score_prob = float(score_matrix[idx])

    # Closeness signal: P(game decided by exactly one run). This is the mass on
    # the two off-diagonals of the score matrix (home wins by 1, away wins by 1).
    # A high value on a confident pick flags a high-variance, could-tip game —
    # the win probability can be "right" while the game is a near-coin-flip in
    # run terms. Surfaced for transparency; does NOT change p_home/p_away.
    p_one_run = float(np.trace(score_matrix, offset=1) + np.trace(score_matrix, offset=-1))

    # Blowup signal: P(EITHER team scores >= 7 runs), read off the same score
    # distribution. Full-game unders rarely die from both teams scoring — they
    # die from ONE team exploding. This surfaces that asymmetric tail so the
    # betting layer can route away from fragile unders (yesterday: Rays 10,
    # Marlins 14, etc.). Read-only signal; does NOT change any probability.
    # p(either >= 7) = p(home>=7) + p(away>=7) - p(both>=7)
    BLOWUP_THRESHOLD = 7
    p_home_big = float(home_pmf[BLOWUP_THRESHOLD:].sum()) if len(home_pmf) > BLOWUP_THRESHOLD else 0.0
    p_away_big = float(away_pmf[BLOWUP_THRESHOLD:].sum()) if len(away_pmf) > BLOWUP_THRESHOLD else 0.0
    p_blowup = p_home_big + p_away_big - (p_home_big * p_away_big)  # independence (same as matrix)

    return BaseballPrediction(
        home_xr=home_xr,
        away_xr=away_xr,
        p_home=p_home,
        p_away=p_away,
        p_over=p_over,
        p_under=p_under,
        over_under_line=line,
        most_likely_score=most_likely_score,
        most_likely_score_prob=most_likely_score_prob,
        p_one_run=p_one_run,
        totals_available=totals_available,
        p_blowup=p_blowup,
        p_home_blowup=p_home_big,
        p_away_blowup=p_away_big,
    )


def pythagorean_win_pct(runs_scored: float, runs_allowed: float, exponent: float = DEFAULT_PYTH_EXPONENT) -> float:
    """
    Bill James Pythagorean win expectation.

    Returns expected season-long win % given total runs scored and allowed.
    Useful as a sanity check on team strength.
    """
    if runs_scored <= 0 and runs_allowed <= 0:
        return 0.5
    rs_x = runs_scored ** exponent
    ra_x = runs_allowed ** exponent
    return rs_x / (rs_x + ra_x)
