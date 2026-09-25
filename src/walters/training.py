"""
Model training & improvement loop.

This is the orchestrator. It glues the pure-function model components in
`src/models/` to the database. Four high-level operations:

  1. `train_fresh()` — fit a brand-new model from all available history.
     Creates a candidate ModelVersion. Doesn't auto-promote.

  2. `generate_predictions()` — for every upcoming (SCHEDULED) match in a
     given competition+season, run the current production model and write
     a Prediction row.

  3. `evaluate_finished()` — for every Prediction whose match has just
     finished, score it and write a PredictionOutcome.

  4. `improve()` — the full nightly loop:
        a) evaluate_finished() to score yesterday's predictions
        b) train_fresh() to make a candidate
        c) compare candidate vs production on a holdout window
        d) promote the candidate if it beats production by `min_delta` log-loss
        e) otherwise mark candidate as "rejected"

This is the Walters edge in code form — the model is never done, it's always
reacting to what it just got wrong.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from dataclasses import replace as dc_replace
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.db.database import session_scope
from src.db.schema import (
    Competition,
    Match,
    MatchStatus,
    ModelVersion,
    Prediction,
    PredictionOutcome,
    Result,
    Sport,
    Team,
)
from src.models.elo import (
    EloConfig,
    EloState,
    TrainMatch,
    train as train_elo,
)
from src.models.poisson import (
    CompetitionScoringContext,
    PoissonConfig,
    estimate_strengths,
    predict_match,
)
from src.walters.evaluation import aggregate, score_1x2, score_over_under

log = logging.getLogger(__name__)

# Per-sport model families. The improvement loop and evaluation logic are
# sport-agnostic but each sport has its own training/prediction code path.
MODEL_FAMILY = "soccer_elo_poisson"  # backwards-compat for older callers
MODEL_FAMILIES: dict[Sport, str] = {
    Sport.SOCCER: "soccer_elo_poisson",
    Sport.MLB: "mlb_pythag_negbin",
}


def _family_for(sport: Sport) -> str:
    family = MODEL_FAMILIES.get(sport)
    if family is None:
        raise ValueError(f"No model family registered for sport {sport}")
    return family

#: Minimum holdout-log-loss improvement (in raw units) for a candidate to
#: replace the production model. ~0.005 is a conservative threshold for
#: 1X2 — it means the new model is ~0.5% better in cross-entropy, which on
#: a few hundred matches is reasonably real signal.
DEFAULT_PROMOTION_DELTA = 0.005

#: How many days of recent finished matches to use as the holdout window
#: when comparing candidate vs production.
DEFAULT_HOLDOUT_DAYS = 30


# --------------------------------------------------------------------------
# Train
# --------------------------------------------------------------------------


@dataclass
class TrainResult:
    version: str
    train_size: int
    # Soccer-specific. None for other sports.
    elo_state: EloState | None = None
    competition_contexts: dict[str, CompetitionScoringContext] = field(default_factory=dict)


def train_fresh(
    sport: Sport = Sport.SOCCER,
    notes: str | None = None,
) -> TrainResult:
    """
    Fit a fresh model for the given sport.

    Dispatches to a sport-specific trainer:
      - SOCCER → Elo + Poisson model
      - MLB    → Pythagorean + negative binomial model

    Creates a "candidate" ModelVersion. Does NOT promote it — that's the
    job of `improve()`.
    """
    if sport == Sport.SOCCER:
        return _train_fresh_soccer(notes=notes)
    if sport == Sport.MLB:
        return _train_fresh_mlb(notes=notes)
    raise ValueError(f"Training not yet supported for sport {sport}")


def _production_params(s, sport: Sport) -> dict | None:
    """Parameters dict of the current production model for `sport`, or None."""
    from sqlalchemy import select as _select
    mv = s.execute(
        _select(ModelVersion)
        .where(ModelVersion.sport == sport, ModelVersion.status == "production")
        .order_by(ModelVersion.id.desc())
    ).scalars().first()
    return dict(mv.parameters or {}) if mv else None


def _train_fresh_soccer(notes: str | None = None) -> TrainResult:
    """
    Fit a fresh soccer model (Elo + Poisson) from all finished matches.

    Phase 7: maintains TWO Elo states — one trained on league matches, one
    on cup matches. League Elo is the primary "team strength" signal; cup
    Elo captures "this team performs differently in knockouts." At predict
    time the two are blended (heavy weight on league).
    """
    sport = Sport.SOCCER
    family = _family_for(sport)
    with session_scope() as s:
        finished = _load_finished_matches(s, sport)
        if not finished:
            raise RuntimeError(
                "No finished soccer matches in DB. Run sync-matches before training."
            )

        # Group by competition type — LEAGUE matches train league-Elo, CUP
        # matches train cup-Elo. They run as independent ladders so cross-comp
        # cup variance doesn't pollute the underlying league strength signal.
        league_matches: list[Match] = []
        cup_matches: list[Match] = []
        for m in finished:
            ctype = (m.competition.type or "LEAGUE").upper()
            if ctype in ("CUP", "INTL"):
                cup_matches.append(m)
            else:
                league_matches.append(m)

        def _to_train(matches: list[Match]) -> list[TrainMatch]:
            return [
                TrainMatch(
                    home_team_id=m.home_team_id,
                    away_team_id=m.away_team_id,
                    home_score=m.home_score,
                    away_score=m.away_score,
                    season=f"{m.competition.code}:{m.season}",
                )
                for m in sorted(matches, key=lambda x: x.utc_date)
            ]

        elo_state_league = train_elo(_to_train(league_matches))
        elo_state_cup = train_elo(_to_train(cup_matches))

        # Group by competition for separate scoring contexts (used for both
        # league and cup matches by Poisson — context is per competition,
        # not per Elo state).
        by_comp: dict[str, list[Match]] = {}
        for m in finished:
            by_comp.setdefault(m.competition.code, []).append(m)

        # Competition contexts: empirical league averages, computed per
        # competition+season pair so a 2023/24 PL prediction uses the right
        # baseline goal rate.
        contexts: dict[str, CompetitionScoringContext] = {}
        for code, matches in by_comp.items():
            total_goals = 0
            total_team_matches = 0
            home_goals = 0
            home_matches = 0
            for m in matches:
                if m.home_score is None or m.away_score is None:
                    continue
                total_goals += m.home_score + m.away_score
                total_team_matches += 2
                home_goals += m.home_score
                home_matches += 1
            if total_team_matches > 0:
                avg = total_goals / total_team_matches
                home_avg = home_goals / home_matches if home_matches else avg
                boost = home_avg / avg if avg > 0 else 1.15
                contexts[code] = CompetitionScoringContext(
                    avg_goals_per_team_per_match=avg,
                    home_field_goal_boost=max(1.0, min(1.30, boost)),
                )
            else:
                contexts[code] = CompetitionScoringContext()

        # Map team → most-recent-league-they-played-in, for cup-match
        # cross-league bonus lookups at predict time.
        from collections import defaultdict
        team_to_league: dict[int, str] = {}
        team_last_league_match: dict[int, datetime] = {}
        for m in league_matches:
            for tid in (m.home_team_id, m.away_team_id):
                if (tid not in team_last_league_match
                        or m.utc_date > team_last_league_match[tid]):
                    team_to_league[tid] = m.competition.code
                    team_last_league_match[tid] = m.utc_date

        # Create the version row
        version_str = _next_version_string(s, sport, family)

        # CONFIG INHERITANCE (critical): candidates must carry the PRODUCTION
        # model's tuned poisson config (rho, elo_goal_coeff, promoted priors…),
        # not dataclass defaults — otherwise the first promoted refresh would
        # silently revert every set-soccer-config recalibration. Defaults are
        # only the base layer so NEW fields added since the last edit get
        # sensible values.
        prod_params = _production_params(s, sport) or {}
        inherited_poisson = {**PoissonConfig().as_dict(),
                             **(prod_params.get("poisson") or {})}
        params = {
            "elo": {
                # Dual Elo: league is primary, cup is secondary.
                "league": elo_state_league.as_dict(),
                "cup": elo_state_cup.as_dict(),
            },
            "poisson": inherited_poisson,
            "contexts": {k: v.as_dict() for k, v in contexts.items()},
            "team_to_league": team_to_league,
        }
        if prod_params.get("manual_config_edits"):
            # audit history survives promotion
            params["manual_config_edits"] = prod_params["manual_config_edits"]

        mv = ModelVersion(
            sport=sport,
            model_family=family,
            version=version_str,
            parent_version=_current_production_version(s, sport),
            status="candidate",
            parameters=params,
            train_size=len(finished),
            notes=notes,
        )
        s.add(mv)
        log.info(
            "Trained %s %s on %d matches (%d league, %d cup)",
            family, version_str, len(finished), len(league_matches), len(cup_matches),
        )

    return TrainResult(
        version=version_str,
        train_size=len(finished),
        elo_state=elo_state_league,  # caller-facing — most useful single state
        competition_contexts=contexts,
    )


def _train_fresh_mlb(notes: str | None = None) -> TrainResult:
    """
    Fit a fresh MLB model.

    Unlike soccer where we precompute Elo state at train time, the MLB model's
    parameters are mostly hyperparameters (Pythagorean exponent, dispersion
    k, home boost, league ERA). Team-specific run profiles are computed at
    predict time from the most recent season's data, since they shift fast.
    So training is mostly a configuration snapshot. The model still gets a
    version because we may tune hyperparameters over time.

    We also compute and store league-wide averages (avg RPG, league ERA)
    derived from observed data so the prediction code uses realistic baselines.
    """
    from src.models.baseball import BaseballConfig

    sport = Sport.MLB
    family = _family_for(sport)
    with session_scope() as s:
        finished = _load_finished_matches(s, sport)
        if not finished:
            raise RuntimeError(
                "No finished MLB games in DB. Run sync-matches before training."
            )

        # Empirical league averages from finished games
        total_runs = 0
        games_counted = 0
        for m in finished:
            if m.home_score is not None and m.away_score is not None:
                total_runs += m.home_score + m.away_score
                games_counted += 1
        league_rpg = (total_runs / games_counted) if games_counted else 9.0

        # CONFIG INHERITANCE (critical): start from PRODUCTION's tuned config
        # (run_shrink, starter cap, home boost…) and overlay only the
        # DATA-DERIVED field (league RPG). Stamping fresh defaults here meant
        # every candidate carried run_shrink_frac=0.25 etc. — production's
        # tuned values survived only because every candidate kept losing; one
        # promotion would have silently reverted weeks of recalibration.
        prod_params = _production_params(s, sport) or {}
        inherited = {**BaseballConfig().as_dict(),
                     **(prod_params.get("baseball_config") or {})}
        inherited["league_runs_per_game"] = round(league_rpg, 2)
        config = BaseballConfig(**{k: v for k, v in inherited.items()
                                   if k in BaseballConfig().as_dict()})

        version_str = _next_version_string(s, sport, family)
        params = {
            "baseball_config": config.as_dict(),
            "trained_on_games": games_counted,
        }
        if prod_params.get("manual_config_edits"):
            params["manual_config_edits"] = prod_params["manual_config_edits"]

        mv = ModelVersion(
            sport=sport,
            model_family=family,
            version=version_str,
            parent_version=_current_production_version(s, sport),
            status="candidate",
            parameters=params,
            train_size=games_counted,
            notes=notes,
        )
        s.add(mv)
        log.info("Trained %s %s on %d games (league RPG=%.2f)",
                 family, version_str, games_counted, league_rpg)

    return TrainResult(
        version=version_str,
        train_size=games_counted,
        elo_state=None,  # baseball doesn't carry Elo state
        competition_contexts={},
    )


# --------------------------------------------------------------------------
# Predict
# --------------------------------------------------------------------------


def generate_predictions(
    competition_code: str,
    season: str,
    model_version: str | None = None,
    sport: Sport = Sport.SOCCER,
    only_match_id: int | None = None,
) -> int:
    """
    Run the current production model and write Prediction rows for every
    SCHEDULED match in the given competition/season.

    Sport-aware: soccer uses the Elo+Poisson pipeline; MLB uses the
    Pythagorean+negative-binomial pipeline.

    If `only_match_id` is set, predicts just that match — used by the
    per-match refresh button.

    Returns count of predictions written. Re-running for the same matches
    is idempotent — existing predictions are replaced.
    """
    if sport == Sport.SOCCER:
        return _generate_predictions_soccer(competition_code, season, model_version, only_match_id)
    if sport == Sport.MLB:
        return _generate_predictions_mlb(competition_code, season, model_version, only_match_id)
    raise ValueError(f"Predictions not yet supported for sport {sport}")


def _generate_predictions_soccer(
    competition_code: str,
    season: str,
    model_version: str | None = None,
    only_match_id: int | None = None,
    include_finished: bool = False,
    cup_coeffs: dict | None = None,
    cup_coeff_grid: tuple | None = None,
) -> int | list[dict]:
    """Soccer prediction pipeline (Elo + Poisson).

    If only_match_id is set, predicts just that match instead of all
    scheduled matches in the competition+season. Used for per-match
    refresh button.

    include_finished=True is the cup acceptance exam's REPORT-ONLY mode
    (spec frozen 2026-09-25): FINISHED matches are priced alongside
    SCHEDULED ones, and the computed rows are RETURNED as dicts — nothing
    is persisted (no Prediction deletes/inserts, session rolled back), so
    the graded ledger never sees a prediction for a played game. The
    default path is unchanged and still returns the count written.

    Cup fix-v2 (architect spec 2026-09-25): cup/intl fixtures take
    elo_goal_coeff by CONTEXT — "same_league" (both clubs' domestic
    leagues equal) or "cross_league" — from `cup_coeffs` (an in-memory
    override, used by cup-exam's tuning) or, if absent, the model's
    top-level parameters["cup_elo_goal_coeff"]; neither set = the base
    poisson coeff, i.e. unchanged behavior. League competitions ignore
    both. `cup_coeff_grid` (report-only) also prices each cup row at
    every grid coeff, for tuning on the exact shipped path.
    """
    sport = Sport.SOCCER
    written = 0
    report_rows: list[dict] = []
    with session_scope() as s:
        mv = _resolve_model_version(s, model_version, sport)
        params = mv.parameters or {}

        # Phase 7: ModelVersion may have either:
        #   - new shape: parameters["elo"] = {"league": {...}, "cup": {...}}
        #   - legacy shape: parameters["elo"] = {...}  (single Elo state)
        # Handle both.
        elo_raw = params.get("elo", {}) or {}
        if "league" in elo_raw or "cup" in elo_raw:
            elo_league = EloState.from_dict(elo_raw.get("league", {}))
            elo_cup = EloState.from_dict(elo_raw.get("cup", {}))
        else:
            # Legacy: single state. Use it for league, and as the cup fallback.
            elo_league = EloState.from_dict(elo_raw)
            elo_cup = EloState.from_dict(elo_raw)
        team_to_league = params.get("team_to_league", {})
        # team_to_league may have integer-key drift from JSON serialization
        team_to_league = {int(k): v for k, v in team_to_league.items()}

        contexts_raw = params.get("contexts", {})
        contexts = {
            k: CompetitionScoringContext(**v) for k, v in contexts_raw.items()
        }
        poisson_cfg = PoissonConfig(**params.get("poisson", {}))

        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            raise RuntimeError(f"Competition {competition_code} not in DB.")

        # Phase 7: cup-mode flag. Cup matches and international/continental
        # competitions both use blended Elo with cross-league adjustment —
        # they're knockouts across leagues and the league bonus matters.
        is_cup_competition = (comp.type or "LEAGUE").upper() in ("CUP", "INTL")

        # Build per-team attack/defense strengths. Try the requested season
        # first; if too few finished matches (early in a new season), pull in
        # the previous season's matches as a fallback so strengths exist.
        MIN_MATCHES_FOR_STRENGTHS = 30  # ~3 matchweeks of PL

        finished_q = (
            select(Match)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .where(
                Match.competition_id == comp.id,
                Match.season == season,
                Match.status == MatchStatus.FINISHED,
            )
        )
        finished_matches = list(s.execute(finished_q).scalars())

        if len(finished_matches) < MIN_MATCHES_FOR_STRENGTHS:
            # Pull last season's finished matches as a backfill
            prior_q = (
                select(Match)
                .options(selectinload(Match.home_team), selectinload(Match.away_team))
                .where(
                    Match.competition_id == comp.id,
                    Match.season != season,
                    Match.status == MatchStatus.FINISHED,
                )
                .order_by(Match.utc_date.desc())
                .limit(500)  # roughly one PL season
            )
            prior = list(s.execute(prior_q).scalars())
            log.info(
                "Only %d finished matches in %s; backfilling with %d from prior seasons",
                len(finished_matches), season, len(prior),
            )
            strengths_backfilled = True
            n_current_season = len(finished_matches)
            finished_matches = finished_matches + prior
        else:
            strengths_backfilled = False
            n_current_season = len(finished_matches)

        context = contexts.get(competition_code, CompetitionScoringContext())
        strength_input = [
            {
                "home_team_id": m.home_team_id,
                "away_team_id": m.away_team_id,
                "home_score": m.home_score,
                "away_score": m.away_score,
            }
            for m in finished_matches
            if m.home_score is not None and m.away_score is not None
        ]
        strengths = estimate_strengths(strength_input, context)
        if include_finished:
            # cup-exam --detail receipts (read-only): the fit pool behind the
            # strengths above, per-team sample sizes, and which fixtures sit
            # inside their own fit window.
            fit_ids = {fm.id for fm in finished_matches
                       if fm.home_score is not None and fm.away_score is not None}
            fit_n: dict[int, int] = {}
            for row in strength_input:
                for tid in (row["home_team_id"], row["away_team_id"]):
                    fit_n[tid] = fit_n.get(tid, 0) + 1

        # Upcoming matches to predict (report-only mode widens to FINISHED)
        priced_statuses = [MatchStatus.SCHEDULED]
        if include_finished:
            priced_statuses.append(MatchStatus.FINISHED)
        upcoming_q = (
            select(Match)
            .where(
                Match.competition_id == comp.id,
                Match.season == season,
                Match.status.in_(priced_statuses),
            )
            .order_by(Match.utc_date.asc())
        )
        upcoming = list(s.execute(upcoming_q).scalars())

        if only_match_id is not None:
            upcoming = [m for m in upcoming if m.id == only_match_id]

        # Load current injuries by team_id — refreshed by `sync-injuries`.
        # If the table is empty (no sync yet), this just yields {}.
        from src.db.schema import Injury, Lineup, Player, PlayerSeasonStats
        from src.models.factors import (
            injury_adjustment, lineup_adjustment,
            rest_days_adjustment, xi_strength_adjustment,
        )
        from src.models.player_score import compute_player_score
        from src.models.team_strength import (
            CONFIDENCE_BY_KIND, compute_team_baseline_xi,
            compute_xi_strength, xi_adjustment_multipliers,
        )

        injuries_by_team: dict[int, list] = {}
        for inj in s.execute(select(Injury)).scalars():
            injuries_by_team.setdefault(inj.team_id, []).append(inj)

        # Lineup kind by (match_id, team_id) — refined granularity over the
        # match-level kind, since home & away can have different lineup states.
        lineup_kind_by_match_team: dict[tuple[int, int], str] = {}
        for ln in s.execute(
            select(Lineup.match_id, Lineup.team_id, Lineup.kind).distinct()
        ).all():
            mid, tid, kind = ln
            # If we have confirmed lineup, that beats projected
            current = lineup_kind_by_match_team.get((mid, tid))
            if current != "confirmed":
                lineup_kind_by_match_team[(mid, tid)] = kind
        # Backwards-compat: keep the match-level dict too for factor_breakdown
        lineup_kind_by_match: dict[int, str] = {}
        for (mid, tid), kind in lineup_kind_by_match_team.items():
            current = lineup_kind_by_match.get(mid)
            if current != "confirmed":
                lineup_kind_by_match[mid] = kind

        # Starters per (match_id, team_id) — used for lineup_adjustment
        starters_by_match_team: dict[tuple[int, int], list] = {}
        for ln in s.execute(
            select(Lineup).where(Lineup.is_starter == True)  # noqa: E712
        ).scalars():
            starters_by_match_team.setdefault((ln.match_id, ln.team_id), []).append(ln)

        # Recent-XI frequency per team. For each team in the upcoming set,
        # look back at their last 10 confirmed lineups and count appearances.
        upcoming_team_ids = {m.home_team_id for m in upcoming} | {m.away_team_id for m in upcoming}
        recent_xi_freq_by_team: dict[int, dict[str, float]] = {}
        for team_id in upcoming_team_ids:
            recent_lineups = list(s.execute(
                select(Lineup)
                .where(
                    Lineup.team_id == team_id,
                    Lineup.kind == "confirmed",
                    Lineup.is_starter == True,  # noqa: E712
                )
                .order_by(Lineup.refreshed_at.desc())
                .limit(110)  # 10 matches × 11 starters
            ).scalars())
            if not recent_lineups:
                continue
            matches_seen: set[int] = set()
            counts: dict[str, int] = {}
            for ln in recent_lineups:
                matches_seen.add(ln.match_id)
                counts[ln.player_name] = counts.get(ln.player_name, 0) + 1
            total = max(1, len(matches_seen))
            recent_xi_freq_by_team[team_id] = {
                name: c / total for name, c in counts.items()
            }

        # Phase 6b: per-team player score lookups + season-baseline XI strength.
        # For each team in the upcoming set, load PlayerSeasonStats, compute
        # scores, and key by player_name (so lineup rows — which store name,
        # not player_id — can resolve).
        player_scores_by_team_name: dict[tuple[int, str], tuple[float, str]] = {}
        team_baseline_xi: dict[int, object] = {}
        for team_id in upcoming_team_ids:
            stats_rows = list(s.execute(
                select(PlayerSeasonStats)
                .where(PlayerSeasonStats.team_id == team_id)
                .order_by(PlayerSeasonStats.refreshed_at.desc())
                # Take most-recent-season stats; quick & dirty for now.
                .limit(60)
            ).scalars())
            if not stats_rows:
                continue
            # Eagerly fetch player rows
            player_ids = {row.player_id for row in stats_rows}
            players_by_id = {
                p.id: p for p in s.execute(
                    select(Player).where(Player.id.in_(player_ids))
                ).scalars()
            }
            # Most recent season only
            most_recent_season = max(r.season for r in stats_rows)
            current_rows = [r for r in stats_rows if r.season == most_recent_season]

            team_squad_tuples: list[tuple[str, float, str]] = []
            for r in current_rows:
                player = players_by_id.get(r.player_id)
                if not player:
                    continue
                # Set position on stats row for player_score logic
                r.position = player.position  # type: ignore[attr-defined]
                breakdown = compute_player_score(r)
                player_scores_by_team_name[(team_id, player.name)] = (
                    breakdown.score, player.position or "",
                )
                team_squad_tuples.append((player.name, breakdown.score, player.position or ""))
            if team_squad_tuples:
                team_baseline_xi[team_id] = compute_team_baseline_xi(team_squad_tuples)

        # Phase 7: helper to compute a team's effective Elo for this match.
        # League matches: use league_elo directly.
        # Cup matches: blend league_elo + cup_elo, and apply a cross-league
        # bonus based on which league the team usually plays in. This is the
        # core of the cup-Elo logic.
        from src.models.league_strength import league_bonus
        LEAGUE_BLEND_WEIGHT = 0.7  # weight on league_elo when blending in cup mode

        def _effective_elo(team_id: int) -> float:
            base = elo_league.get(team_id)
            if not is_cup_competition:
                return base
            cup = elo_cup.get(team_id)
            blended = LEAGUE_BLEND_WEIGHT * base + (1 - LEAGUE_BLEND_WEIGHT) * cup
            # Cross-league adjustment — a team's home league determines how
            # we read their Elo against teams from other leagues.
            home_league = team_to_league.get(team_id)
            blended += league_bonus(home_league)
            return blended

        # Cup fix (architect spec 2026-09-25): cup/intl strengths come from the
        # as-of, leave-self-out domestic league-season fit blended toward the
        # cup-season fit by n/(n+5); unrated / no-domestic-league teams are
        # market-only (ruling B). League competitions never take this branch.
        cup_src = None
        market_only: dict[int, str] = {}
        if is_cup_competition:
            from src.models.cup_strengths import load_cup_strength_source
            cup_src = load_cup_strength_source(s, comp, season, contexts,
                                               set(elo_league.ratings))
        # never read from params["poisson"]: PoissonConfig(**...) rejects unknown keys
        cup_coeff_map = cup_coeffs if cup_coeffs is not None else (params.get("cup_elo_goal_coeff") or {})

        # Promoted-team default prior: clubs in the upcoming set with NO
        # strengths (no matches in the window) get a conservative
        # below-average profile instead of having every game dropped.
        # Exported per-side as strengths_source so downstream can discount
        # and we can grade these rows as their own cohort.
        from src.models.poisson import TeamStrength as _TS
        promoted_default_ids: set[int] = set()
        for _tid in (upcoming_team_ids if cup_src is None else ()):
            if _tid not in strengths:
                strengths[_tid] = _TS(
                    attack=poisson_cfg.promoted_attack_prior,
                    defense=poisson_cfg.promoted_defense_prior,
                )
                promoted_default_ids.add(_tid)
        if promoted_default_ids:
            _names = []
            for _tid in promoted_default_ids:
                _t = s.get(Team, _tid)
                _names.append(_t.name if _t else f"team_id={_tid}")
            log.info(
                "Promoted-team default prior applied (attack=%.2f, defense=%.2f): %s "
                "— rows carry strengths_source=promoted_default.",
                poisson_cfg.promoted_attack_prior,
                poisson_cfg.promoted_defense_prior,
                ", ".join(sorted(_names)))

        skipped_no_strengths: dict[str, int] = {}
        for m in upcoming:
            home_elo = _effective_elo(m.home_team_id)
            away_elo = _effective_elo(m.away_team_id)
            cup_receipt: dict = {}
            fixture_cfg = poisson_cfg          # league path: always the base config
            if cup_src is not None:
                got = cup_src.for_fixture(m.home_team_id, m.away_team_id, m.utc_date)
                if isinstance(got, str):          # ruling B: never priced
                    market_only[m.id] = got
                    if include_finished:
                        report_rows.append({"match_id": m.id, "model_version": mv.version,
                                            "market_only": got})
                    continue
                home_side, away_side, cup_info = got
                home_str, away_str = home_side.strength, away_side.strength
                cup_receipt = {
                    "fit_pool_n": cup_info["cup_pool_n"],
                    "strengths_backfilled": False,
                    "self_in_fit": m.id in cup_info["used_ids"],
                    "home_fit_n": home_side.cup_n, "away_fit_n": away_side.cup_n,
                    "home_strengths_source": "domestic+cup", "away_strengths_source": "domestic+cup",
                    "home_dom_league": home_side.dom_league, "away_dom_league": away_side.dom_league,
                    "home_dom_n": home_side.dom_n, "away_dom_n": away_side.dom_n,
                    "home_cup_w": round(home_side.cup_w, 3), "away_cup_w": round(away_side.cup_w, 3),
                }
                cup_context = ("same_league" if home_side.dom_league == away_side.dom_league
                               else "cross_league")
                fixture_cfg = dc_replace(poisson_cfg, elo_goal_coeff=cup_coeff_map.get(
                    cup_context, poisson_cfg.elo_goal_coeff))
                cup_receipt["cup_context"] = cup_context
                cup_receipt["elo_goal_coeff"] = fixture_cfg.elo_goal_coeff
            else:
                home_str = strengths.get(m.home_team_id)
                away_str = strengths.get(m.away_team_id)
            if home_str is None or away_str is None:
                # reported-not-silent: a promoted/new club with no matches in
                # the strengths window drops ALL its games here — name it.
                for tid, st in ((m.home_team_id, home_str), (m.away_team_id, away_str)):
                    if st is None:
                        t = s.get(Team, tid)
                        name = t.name if t else f"team_id={tid}"
                        skipped_no_strengths[name] = skipped_no_strengths.get(name, 0) + 1
                continue

            # Build factor adjustment for this match. Compose:
            #   injuries  ×  lineup-adjustment  ×  xi-strength
            home_inj = injuries_by_team.get(m.home_team_id, [])
            away_inj = injuries_by_team.get(m.away_team_id, [])
            inj_factor = injury_adjustment(home_injuries=home_inj, away_injuries=away_inj)

            home_starters = starters_by_match_team.get((m.id, m.home_team_id), [])
            away_starters = starters_by_match_team.get((m.id, m.away_team_id), [])
            lu_factor = lineup_adjustment(
                home_starters=home_starters,
                away_starters=away_starters,
                home_recent_xi_freq=recent_xi_freq_by_team.get(m.home_team_id),
                away_recent_xi_freq=recent_xi_freq_by_team.get(m.away_team_id),
            )

            # Phase 6b — XI strength adjustment from player scores.
            # Only meaningful if we have lineup data AND player scores for the team.
            xi_factor = xi_strength_adjustment()  # default no-op
            xi_notes: list[str] = []
            home_xi_obj = None
            away_xi_obj = None
            home_atk_mult = home_def_mult = away_atk_mult = away_def_mult = 1.0

            home_baseline = team_baseline_xi.get(m.home_team_id)
            away_baseline = team_baseline_xi.get(m.away_team_id)

            def _xi_tuples(starters: list, team_id: int) -> list[tuple[str, float, str]]:
                """Resolve lineup rows to (name, score, position) for XI computation."""
                out = []
                for ln in starters:
                    key = (team_id, ln.player_name)
                    if key in player_scores_by_team_name:
                        score, pos = player_scores_by_team_name[key]
                        out.append((ln.player_name, score, pos))
                    else:
                        # Player has no season stats: assume 50 (avg), position
                        # from lineup row if available
                        out.append((ln.player_name, None, ln.player_position or "Midfielder"))
                return out

            if home_starters and home_baseline is not None:
                home_xi_tuples = _xi_tuples(home_starters, m.home_team_id)
                home_xi_obj = compute_xi_strength(home_xi_tuples)
                hk = lineup_kind_by_match_team.get((m.id, m.home_team_id), "projected")
                home_conf = CONFIDENCE_BY_KIND.get(hk, 0.3)
                home_atk_mult, home_def_mult, home_notes = xi_adjustment_multipliers(
                    home_xi_obj, home_baseline, home_conf,
                )
                xi_notes.extend(f"home: {n}" for n in home_notes)

            if away_starters and away_baseline is not None:
                away_xi_tuples = _xi_tuples(away_starters, m.away_team_id)
                away_xi_obj = compute_xi_strength(away_xi_tuples)
                ak = lineup_kind_by_match_team.get((m.id, m.away_team_id), "projected")
                away_conf = CONFIDENCE_BY_KIND.get(ak, 0.3)
                away_atk_mult, away_def_mult, away_notes = xi_adjustment_multipliers(
                    away_xi_obj, away_baseline, away_conf,
                )
                xi_notes.extend(f"away: {n}" for n in away_notes)

            if home_atk_mult != 1.0 or home_def_mult != 1.0 or away_atk_mult != 1.0 or away_def_mult != 1.0:
                xi_factor = xi_strength_adjustment(
                    home_atk_mult=home_atk_mult, home_def_mult=home_def_mult,
                    away_atk_mult=away_atk_mult, away_def_mult=away_def_mult,
                    notes=xi_notes,
                )

            factor = inj_factor.combine(lu_factor).combine(xi_factor)

            pred = predict_match(
                home_elo=home_elo,
                away_elo=away_elo,
                home_strength=home_str,
                away_strength=away_str,
                context=context,
                config=fixture_cfg,
                factor_adjustment=factor,
            )

            # Phase 7: compute "to advance" probabilities for cup knockouts.
            # For 90-min draws, redistribute draw mass to ET/pens (slight home edge).
            from src.models.cup_knockout import is_knockout_match, to_advance_probabilities
            is_knockout = is_knockout_match(comp.code, m.stage)
            if is_knockout:
                p_adv_home, p_adv_away = to_advance_probabilities(
                    pred.p_home, pred.p_draw, pred.p_away,
                )
            else:
                p_adv_home = p_adv_away = None

            if include_finished:
                # REPORT-ONLY: return the priced row; never touch Prediction.
                report_rows.append({
                    "match_id": m.id,
                    "model_version": mv.version,
                    "p_home": pred.p_home,
                    "p_draw": pred.p_draw,
                    "p_away": pred.p_away,
                    "home_elo": round(home_elo, 1),
                    "away_elo": round(away_elo, 1),
                    "home_league": team_to_league.get(m.home_team_id),
                    "away_league": team_to_league.get(m.away_team_id),
                    "home_league_bonus": round(league_bonus(team_to_league.get(m.home_team_id)), 1) if is_cup_competition else None,
                    "away_league_bonus": round(league_bonus(team_to_league.get(m.away_team_id)), 1) if is_cup_competition else None,
                    # Diagnostics (cup-exam --detail): raw inputs to
                    # _effective_elo. in_pot = the team has a trained league
                    # rating; otherwise EloState.get fell back to the default.
                    "home_in_pot": m.home_team_id in elo_league.ratings,
                    "away_in_pot": m.away_team_id in elo_league.ratings,
                    "home_league_elo": round(elo_league.get(m.home_team_id), 1),
                    "away_league_elo": round(elo_league.get(m.away_team_id), 1),
                    "home_cup_elo": round(elo_cup.get(m.home_team_id), 1),
                    "away_cup_elo": round(elo_cup.get(m.away_team_id), 1),
                    "default_elo": elo_league.config.starting_rating,
                    # Strength-fit receipts: pool = this competition-season's
                    # finished matches (+ prior seasons of the SAME competition
                    # when < MIN_MATCHES_FOR_STRENGTHS).
                    "fit_pool_n": len(strength_input),
                    "strengths_backfilled": strengths_backfilled,
                    "self_in_fit": m.id in fit_ids,
                    "home_fit_n": fit_n.get(m.home_team_id, 0),
                    "away_fit_n": fit_n.get(m.away_team_id, 0),
                    "home_strengths_source": ("promoted_default"
                        if m.home_team_id in promoted_default_ids else "matches"),
                    "away_strengths_source": ("promoted_default"
                        if m.away_team_id in promoted_default_ids else "matches"),
                    "home_attack": round(home_str.attack, 3),
                    "home_defense": round(home_str.defense, 3),
                    "away_attack": round(away_str.attack, 3),
                    "away_defense": round(away_str.defense, 3),
                    "elo_goal_coeff": poisson_cfg.elo_goal_coeff,
                    **cup_receipt,
                    **({"grid_probs": {
                        c: (lambda q: (q.p_home, q.p_draw, q.p_away))(predict_match(
                            home_elo=home_elo, away_elo=away_elo,
                            home_strength=home_str, away_strength=away_str,
                            context=context, config=dc_replace(poisson_cfg, elo_goal_coeff=c),
                            factor_adjustment=factor))
                        for c in cup_coeff_grid}}
                       if (cup_coeff_grid and cup_src is not None) else {}),
                })
                continue

            # Upsert: delete prior predictions for this (match, version) then insert
            existing = s.execute(
                select(Prediction).where(
                    Prediction.match_id == m.id,
                    # NOTE (S13, 2026-08-23): intentionally NOT keyed on
                    # model_version. Keying on version left ghost rows from
                    # prior production versions (v13/v15 relics) that
                    # evaluate then graded alongside the live prediction,
                    # triplicating results. Predictions table is
                    # current-only per match; history lives in outcomes.
                )
            ).scalars().all()
            for old in existing:
                s.delete(old)

            s.add(Prediction(
                match_id=m.id,
                model_version=mv.version,
                home_win_prob=pred.p_home,
                draw_prob=pred.p_draw,
                away_win_prob=pred.p_away,
                expected_home_score=pred.home_xg,
                expected_away_score=pred.away_xg,
                over_under_line=pred.over_under_line,
                over_prob=pred.p_over,
                under_prob=pred.p_under,
                to_advance_home_prob=p_adv_home,
                to_advance_away_prob=p_adv_away,
                factor_breakdown={
                    "home_elo": round(home_elo, 1),
                    "away_elo": round(away_elo, 1),
                    "home_strengths_source": ("promoted_default"
                        if m.home_team_id in promoted_default_ids else "matches"),
                    "away_strengths_source": ("promoted_default"
                        if m.away_team_id in promoted_default_ids else "matches"),
                    # Early-season honesty: "matches" can mean LAST season's.
                    # The market prices summer (transfers, managers); a
                    # matches-only model cannot — consumers should discount
                    # accordingly until current-season matches accumulate.
                    "strengths_backfilled": strengths_backfilled,
                    "current_season_matches": n_current_season,
                    "home_attack": round(home_str.attack, 3),
                    "home_defense": round(home_str.defense, 3),
                    "away_attack": round(away_str.attack, 3),
                    "away_defense": round(away_str.defense, 3),
                    "most_likely_score": list(pred.most_likely_score),
                    "home_injuries_count": len(home_inj),
                    "away_injuries_count": len(away_inj),
                    "factor_notes": factor.notes,
                    "lineup_kind": lineup_kind_by_match.get(m.id),
                    # Phase 6b: XI-strength signals (None if unavailable)
                    "home_xi_attack": round(home_xi_obj.attack, 1) if home_xi_obj else None,
                    "home_xi_defense": round(home_xi_obj.defense, 1) if home_xi_obj else None,
                    "away_xi_attack": round(away_xi_obj.attack, 1) if away_xi_obj else None,
                    "away_xi_defense": round(away_xi_obj.defense, 1) if away_xi_obj else None,
                    "home_baseline_attack": round(home_baseline.attack, 1) if home_baseline else None,
                    "home_baseline_defense": round(home_baseline.defense, 1) if home_baseline else None,
                    "away_baseline_attack": round(away_baseline.attack, 1) if away_baseline else None,
                    "away_baseline_defense": round(away_baseline.defense, 1) if away_baseline else None,
                    # Phase 7: cup-mode and to-advance metadata
                    "is_cup_mode": is_cup_competition,
                    "is_knockout": is_knockout,
                    "home_league": team_to_league.get(m.home_team_id),
                    "away_league": team_to_league.get(m.away_team_id),
                    "home_league_bonus": round(league_bonus(team_to_league.get(m.home_team_id)), 1) if is_cup_competition else None,
                    "away_league_bonus": round(league_bonus(team_to_league.get(m.away_team_id)), 1) if is_cup_competition else None,
                },
            ))
            written += 1

        if market_only:
            log.warning("Market-only (ruling B, never priced): %d cup fixture(s) — %s",
                        len(market_only), "; ".join(sorted(set(market_only.values()))))
        if skipped_no_strengths:
            detail = ", ".join(f"{n} ({c} games)" for n, c in
                               sorted(skipped_no_strengths.items()))
            log.warning(
                "⚠ Skipped predictions — no strengths (new/promoted club with no "
                "matches in the strengths window): %s. These games have NO "
                "prediction rows until the club has played (or a promoted-team "
                "prior is added).", detail)
        if include_finished:
            # Belt and braces: whatever the pricing path touched in this
            # session, the commit at session_scope exit writes nothing.
            s.rollback()
            log.info("Priced %d fixtures (report-only, nothing written) for %s %s using model %s",
                     len(report_rows), competition_code, season, mv.version)
            return report_rows
        log.info("Wrote %d predictions for %s %s using model %s",
                 written, competition_code, season, mv.version)
    return written


def _generate_predictions_mlb(
    competition_code: str,
    season: str,
    model_version: str | None = None,
    only_match_id: int | None = None,
) -> int:
    """
    MLB prediction pipeline.

    For each scheduled game:
      1. Compute each team's recent run profile from the same season's
         finished games (cold-start fallback to prior season if needed).
      2. Look up probable starting pitchers (if loaded as MatchParticipant rows).
      3. Run predict_game().
      4. Persist as a Prediction. We re-use the same Prediction table: home/away
         probabilities are direct (no draws), expected_*_score holds expected
         runs, factor_breakdown holds baseball-specific context.
    """
    from src.db.schema import MatchParticipant
    from src.models.baseball import (
        BaseballConfig,
        PitcherStats,
        TeamRunProfile,
        estimate_run_profiles,
        predict_game,
    )

    sport = Sport.MLB
    written = 0
    MIN_GAMES_FOR_PROFILES = 30  # ~10 games per team minimum

    with session_scope() as s:
        mv = _resolve_model_version(s, model_version, sport)
        params = mv.parameters or {}
        cfg = BaseballConfig(**params.get("baseball_config", {}))

        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            raise RuntimeError(f"Competition {competition_code} not in DB.")

        # Finished games for run profiles. Cold-start: backfill with last season.
        finished_q = (
            select(Match)
            .options(
                selectinload(Match.home_team), selectinload(Match.away_team)
            )
            .where(
                Match.competition_id == comp.id,
                Match.season == season,
                Match.status == MatchStatus.FINISHED,
            )
        )
        finished = list(s.execute(finished_q).scalars())

        if len(finished) < MIN_GAMES_FOR_PROFILES:
            prior_q = (
                select(Match)
                .options(
                    selectinload(Match.home_team), selectinload(Match.away_team)
                )
                .where(
                    Match.competition_id == comp.id,
                    Match.season != season,
                    Match.status == MatchStatus.FINISHED,
                )
                .order_by(Match.utc_date.desc())
                .limit(1000)  # ~30% of an MLB season
            )
            prior = list(s.execute(prior_q).scalars())
            log.info(
                "Only %d finished MLB games in %s; backfilling with %d from prior seasons",
                len(finished), season, len(prior),
            )
            finished = finished + prior

        profile_input = [
            {
                "home_team_id": m.home_team_id,
                "away_team_id": m.away_team_id,
                "home_score": m.home_score,
                "away_score": m.away_score,
                "utc_date": m.utc_date,
            }
            for m in finished
            if m.home_score is not None and m.away_score is not None
        ]
        profiles = estimate_run_profiles(profile_input)

        # Pitcher stats by player_source_id → blended starter+bullpen ERA.
        # Starters come from sync_pitchers (probable starters per game),
        # season ERA from sync_pitcher_stats, bullpen ERA from
        # sync_bullpen_stats. The blend + shrinkage happens in
        # _resolve_pitcher below.
        # Lookups by match_id/team_id → starting pitcher (name + source_id)
        pitcher_by_match_team: dict[tuple[int, int], tuple[str, str | None]] = {}
        for p in s.execute(
            select(MatchParticipant).where(MatchParticipant.role == "starting_pitcher")
        ).scalars():
            pitcher_by_match_team[(p.match_id, p.team_id)] = (
                p.player_name, p.player_source_id,
            )

        # Phase 11: pitcher ERA lookup. Pull season ERA for any pitcher in
        # pitcher_by_match_team. Wraps a defensive sample-shrinkage so a
        # pitcher with very few innings doesn't dominate the prediction.
        from src.db.schema import PitcherSeasonStats, BullpenSeasonStats
        # source_id -> (era, ip, games_started)
        pitcher_era_by_source_id: dict[str, tuple[float, float, int]] = {}
        source_ids_needed = {
            sid for (_, sid) in pitcher_by_match_team.values()
            if sid is not None
        }
        if source_ids_needed:
            for ps in s.execute(
                select(PitcherSeasonStats).where(
                    PitcherSeasonStats.player_source_id.in_(source_ids_needed)
                )
            ).scalars():
                if ps.era is not None and ps.innings_pitched > 0:
                    pitcher_era_by_source_id[ps.player_source_id] = (
                        ps.era, ps.innings_pitched, ps.games_started or 0,
                    )

        # Phase 12.2: load bullpen ERA per team for the season.
        # team_id -> (era, ip)
        bullpen_era_by_team_id: dict[int, tuple[float, float]] = {}
        # Phase 12.4: also track the season/recent split for visibility
        bullpen_detail_by_team_id: dict[int, dict] = {}
        # Recent bullpen form blend weight — same 70/30 shape as offense
        # recent-form. Deliberately moderate: bullpen performance is noisy,
        # three bad outings can be collapse or just variance.
        BULLPEN_RECENT_WEIGHT = 0.30
        for bp in s.execute(
            select(BullpenSeasonStats).where(BullpenSeasonStats.season == season)
        ).scalars():
            if bp.era is None or bp.innings_pitched <= 0:
                continue
            season_era = bp.era
            # Blend in recent form if available
            effective_era = season_era
            if bp.recent_era is not None:
                effective_era = ((1 - BULLPEN_RECENT_WEIGHT) * season_era
                                 + BULLPEN_RECENT_WEIGHT * bp.recent_era)
            bullpen_era_by_team_id[bp.team_id] = (effective_era, bp.innings_pitched)
            bullpen_detail_by_team_id[bp.team_id] = {
                "season_era": round(season_era, 2),
                "recent_era": round(bp.recent_era, 2) if bp.recent_era is not None else None,
                "effective_era": round(effective_era, 2),
                "recent_ip": bp.recent_innings_pitched,
            }

        # Starter typically pitches ~5.5 IP, bullpen ~3.5 IP in modern MLB.
        # Blend at those weights for an "effective whole-game ERA" the
        # opponent will face.
        STARTER_WEIGHT = 5.5 / 9.0  # 0.611
        BULLPEN_WEIGHT = 3.5 / 9.0  # 0.389
        # Bullpen halflife is larger than starter halflife: bullpens
        # aggregate over many pitchers and innings, so their ERA is more
        # stable. Most teams hit 50+ IP within the first month of the
        # season; this mainly handles April / season-start cases.
        BULLPEN_HALFLIFE_IP = 50.0

        from src.models.baseball import starter_shrink_weight
        # (match_id, team_id) -> raw→shrunk starter trail for factor_breakdown,
        # so the export shows WHAT the model actually used, not just raw stats.
        starter_detail_by_key: dict[tuple[int, int], dict] = {}

        def _resolve_pitcher(match_id: int, team_id: int) -> PitcherStats | None:
            """
            Return PitcherStats with a blended starter+bullpen ERA.

            The starter ERA contributes 61% (5.5 IP / 9), the bullpen ERA
            contributes 39% (3.5 IP / 9). Both are shrunk toward league
            average by IP before blending. The result represents the
            expected ERA the opponent's hitters will face over the whole
            game, not just the starter.

            Behavior table:
              - Starter has stats, team has bullpen stats → full blend
              - Starter is a reliever (games_started==0) → use only
                bullpen ERA (the team will likely use bullpen-game pattern)
              - Starter has no stats but team has bullpen → use bullpen
                weighted at 50% (with 50% neutral) — neutral on the
                unknown half, bullpen on the known half
              - No data at all → era=None (neutral, handled by
                _pitcher_multiplier)
            """
            key = (match_id, team_id)
            if key not in pitcher_by_match_team:
                return None
            name, source_id = pitcher_by_match_team[key]

            # 1) Resolve starter component (shrunk toward league avg)
            starter_era = None
            if source_id and source_id in pitcher_era_by_source_id:
                era, ip, gs = pitcher_era_by_source_id[source_id]
                if gs == 0:
                    # Reliever being used as opener / bullpen game.
                    # Skip starter component entirely.
                    starter_era = None
                else:
                    # Sample shrinkage toward league avg, 30 IP halflife.
                    # Effective IP may be capped at per_start × GS (Phase
                    # 12.9, config-gated) so relief-heavy innings don't
                    # masquerade as starter evidence.
                    eff_ip, w = starter_shrink_weight(ip, gs, cfg)
                    starter_era = w * era + (1 - w) * cfg.league_era
                    starter_detail_by_key[key] = {
                        "raw_era": round(era, 2),
                        "ip": round(ip, 1),
                        "gs": gs,
                        "effective_ip": round(eff_ip, 1),
                        "shrink_w": round(w, 3),
                        "shrunk_era": round(starter_era, 2),
                    }

            # 2) Resolve bullpen component (shrunk toward league avg)
            bullpen_era = None
            if team_id in bullpen_era_by_team_id:
                bp_era, bp_ip = bullpen_era_by_team_id[team_id]
                w = bp_ip / (bp_ip + BULLPEN_HALFLIFE_IP)
                bullpen_era = w * bp_era + (1 - w) * cfg.league_era

            # 3) Blend
            if starter_era is not None and bullpen_era is not None:
                blended = (STARTER_WEIGHT * starter_era +
                           BULLPEN_WEIGHT * bullpen_era)
                return PitcherStats(name=name, era=blended, starter_known=True)
            elif starter_era is not None:
                # No bullpen data — blend starter with league avg for bullpen
                blended = (STARTER_WEIGHT * starter_era +
                           BULLPEN_WEIGHT * cfg.league_era)
                return PitcherStats(name=name, era=blended, starter_known=True)
            elif bullpen_era is not None:
                # Bullpen-game or unknown starter — use bullpen ERA but pull
                # halfway to league avg to reflect that we don't know what
                # the starter portion looks like. Starter is NOT known here.
                blended = 0.5 * bullpen_era + 0.5 * cfg.league_era
                return PitcherStats(name=name, era=blended, starter_known=False)
            else:
                # No data at all — starter unknown
                return PitcherStats(name=name, era=None, starter_known=False)

        # Upcoming games
        upcoming = list(s.execute(
            select(Match)
            .where(
                Match.competition_id == comp.id,
                Match.season == season,
                Match.status == MatchStatus.SCHEDULED,
            )
            .order_by(Match.utc_date.asc())
        ).scalars())

        if only_match_id is not None:
            upcoming = [m for m in upcoming if m.id == only_match_id]

        for m in upcoming:
            home_profile = profiles.get(m.home_team_id)
            away_profile = profiles.get(m.away_team_id)
            if home_profile is None or away_profile is None:
                continue

            home_pitcher = _resolve_pitcher(m.id, m.home_team_id)
            away_pitcher = _resolve_pitcher(m.id, m.away_team_id)

            # Phase 12: park factor — multiplies expected runs based on venue.
            # Coors +21%, Petco -9%, most parks neutral. Adjustment is
            # symmetric: applies the same multiplier to both teams.
            from src.models.factors import park_factor_adjustment
            park_adj = park_factor_adjustment(m.venue, sport_is_baseball=True)

            # Phase 12.9: pull the real market over/under line so totals are
            # computed against the actual book number, not a hardcoded 8.5.
            # Use the median of synced TOTALS lines (consensus across books).
            from src.db.schema import Odds
            tot_lines = list(s.execute(
                select(Odds.line).where(Odds.match_id == m.id,
                                        Odds.market == "TOTALS",
                                        Odds.line.isnot(None))
            ).scalars())
            market_total = None
            if tot_lines:
                tot_lines.sort()
                market_total = tot_lines[len(tot_lines) // 2]

            pred = predict_game(
                home_profile=home_profile,
                away_profile=away_profile,
                home_pitcher=home_pitcher,
                away_pitcher=away_pitcher,
                config=cfg,
                factor_adjustment=park_adj,
                market_total_line=market_total,
            )

            # Phase 12.3: missing-starter uncertainty.
            # When a starter is unknown, the model has been treating the
            # missing data as league-average, which produces falsely
            # confident predictions (calibration diagnostic showed the
            # 60-70% bins were overconfident, and several of those games
            # had null starters). Less information should mean less
            # confidence, so we shrink the win probabilities toward 50/50
            # proportional to how much starter info is missing.
            #
            # One side unknown → shrink factor 0.88 (mild pull)
            # Both sides unknown → shrink factor 0.76 (stronger pull)
            # This only touches games with missing starters; games with
            # both starters confirmed are unaffected.
            missing = 0
            if home_pitcher is None or not home_pitcher.starter_known:
                missing += 1
            if away_pitcher is None or not away_pitcher.starter_known:
                missing += 1
            if missing > 0:
                shrink = 0.88 if missing == 1 else 0.76
                p_home_adj = 0.5 + (pred.p_home - 0.5) * shrink
                p_away_adj = 0.5 + (pred.p_away - 0.5) * shrink
                # Renormalize (no draws in baseball, so they should sum to 1
                # already, but guard against drift)
                tot = p_home_adj + p_away_adj
                pred.p_home = p_home_adj / tot
                pred.p_away = p_away_adj / tot

            # Phase 12.7: market blend (no-op unless cfg.market_blend_enabled).
            # Pull the model probability partway toward the de-vigged market
            # probability. Self-targets disagreement: does nothing when model
            # agrees with the book, bites when they diverge. Preserves model as
            # an independent voice (w<1) — does NOT collapse to market.
            if getattr(cfg, "market_blend_enabled", False):
                from src.db.schema import Odds as _Odds
                from src.walters.value import MarketSnapshot as _Snap
                _odds = list(s.execute(
                    select(_Odds).where(_Odds.match_id == m.id,
                                        _Odds.market == "1X2")
                ).scalars())
                if _odds:
                    _by_sel: dict[str, list[tuple[str, float]]] = {}
                    for _o in _odds:
                        _by_sel.setdefault(_o.selection, []).append(
                            (_o.bookmaker, _o.price_decimal))
                    _snap = _Snap(market="1X2", by_selection=_by_sel)
                    _implied = _snap.average_implied()
                    _over = sum(_implied.values())
                    if _over > 0 and "HOME" in _implied and "AWAY" in _implied:
                        _mkt_home = _implied["HOME"] / _over
                        _mkt_away = _implied["AWAY"] / _over
                        w = cfg.market_blend_w
                        ph = (1 - w) * pred.p_home + w * _mkt_home
                        pa = (1 - w) * pred.p_away + w * _mkt_away
                        _t = ph + pa
                        if _t > 0:
                            pred.p_home = ph / _t
                            pred.p_away = pa / _t
            existing = s.execute(
                select(Prediction).where(
                    Prediction.match_id == m.id,
                    # NOTE (S13, 2026-08-23): intentionally NOT keyed on
                    # model_version. Keying on version left ghost rows from
                    # prior production versions (v13/v15 relics) that
                    # evaluate then graded alongside the live prediction,
                    # triplicating results. Predictions table is
                    # current-only per match; history lives in outcomes.
                )
            ).scalars().all()
            for old in existing:
                s.delete(old)

            s.add(Prediction(
                match_id=m.id,
                model_version=mv.version,
                home_win_prob=pred.p_home,
                draw_prob=None,  # no draws in baseball
                away_win_prob=pred.p_away,
                expected_home_score=pred.home_xr,
                expected_away_score=pred.away_xr,
                over_under_line=pred.over_under_line if pred.totals_available else None,
                over_prob=pred.p_over if pred.totals_available else None,
                under_prob=pred.p_under if pred.totals_available else None,
                factor_breakdown={
                    "home_rs_pg": round(home_profile.runs_scored_per_game, 2),
                    "home_ra_pg": round(home_profile.runs_allowed_per_game, 2),
                    "away_rs_pg": round(away_profile.runs_scored_per_game, 2),
                    "away_ra_pg": round(away_profile.runs_allowed_per_game, 2),
                    # Phase 12.1: season vs recent run averages
                    "home_rs_season": home_profile.rsg_season,
                    "home_rs_recent": home_profile.rsg_recent,
                    "home_ra_season": home_profile.rag_season,
                    "home_ra_recent": home_profile.rag_recent,
                    "away_rs_season": away_profile.rsg_season,
                    "away_rs_recent": away_profile.rsg_recent,
                    "away_ra_season": away_profile.rag_season,
                    "away_ra_recent": away_profile.rag_recent,
                    "home_games_recent": home_profile.games_recent,
                    "away_games_recent": away_profile.games_recent,
                    "home_pitcher": home_pitcher.name if home_pitcher else None,
                    "away_pitcher": away_pitcher.name if away_pitcher else None,
                    # Phase 12.3: whether each starter was known (vs fallback)
                    "home_starter_known": home_pitcher.starter_known if home_pitcher else False,
                    "away_starter_known": away_pitcher.starter_known if away_pitcher else False,
                    "missing_starter_shrink": (0.88 if missing == 1 else 0.76) if missing > 0 else None,
                    # Pitcher ERA — now the BLENDED starter+bullpen value.
                    # See raw components below for the underlying numbers.
                    "home_pitcher_era": round(home_pitcher.era, 2)
                        if home_pitcher and home_pitcher.era is not None else None,
                    "away_pitcher_era": round(away_pitcher.era, 2)
                        if away_pitcher and away_pitcher.era is not None else None,
                    # Phase 12.2/12.4: bullpen ERA component (effective =
                    # season blended 70/30 with recent form)
                    "home_bullpen_era": round(bullpen_era_by_team_id[m.home_team_id][0], 2)
                        if m.home_team_id in bullpen_era_by_team_id else None,
                    "away_bullpen_era": round(bullpen_era_by_team_id[m.away_team_id][0], 2)
                        if m.away_team_id in bullpen_era_by_team_id else None,
                    "home_bullpen_detail": bullpen_detail_by_team_id.get(m.home_team_id),
                    "away_bullpen_detail": bullpen_detail_by_team_id.get(m.away_team_id),
                    # Phase 12.9: raw → shrunk starter trail (None when no
                    # starter stats / reliever-opener). shrunk_era is the
                    # STARTER component before the 61/39 bullpen blend;
                    # home_pitcher_era above remains the blended figure.
                    "home_starter_detail": starter_detail_by_key.get((m.id, m.home_team_id)),
                    "away_starter_detail": starter_detail_by_key.get((m.id, m.away_team_id)),
                    "league_era": cfg.league_era,
                    "pitcher_anchor_mode": cfg.pitcher_anchor_mode,
                    "home_run_boost": cfg.home_run_boost,
                    # Phase 12: park factor
                    "park_factor": round(park_adj.home_xg_multiplier, 3),
                    "park_notes": park_adj.notes,
                    "venue": m.venue,
                    "most_likely_score": list(pred.most_likely_score),
                    "p_one_run": round(pred.p_one_run, 4),
                    "p_blowup": round(pred.p_blowup, 4),
                    "p_home_blowup": round(pred.p_home_blowup, 4),
                    "p_away_blowup": round(pred.p_away_blowup, 4),
                },
            ))
            written += 1

        log.info("Wrote %d MLB predictions for %s %s using model %s",
                 written, competition_code, season, mv.version)
    return written


# --------------------------------------------------------------------------
# Evaluate
# --------------------------------------------------------------------------


def evaluate_finished(sport: Sport = Sport.SOCCER) -> int:
    """
    For every Prediction whose match has finished but doesn't yet have a
    PredictionOutcome, score it.

    Sport-aware: soccer uses 1X2 scoring (H/D/A), baseball uses winner-only
    scoring (H/A — no draws).

    Returns count of new outcomes written.
    """
    from src.walters.evaluation import score_winner

    written = 0
    with session_scope() as s:
        stmt = (
            select(Prediction)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.status == MatchStatus.FINISHED, Match.sport == sport)
        )
        for pred in s.execute(stmt).scalars():
            # Skip if outcome already exists
            if pred.outcome is not None:
                continue
            match = pred.match
            if match.home_score is None or match.away_score is None:
                continue

            # Sport-specific scoring
            if sport == Sport.SOCCER:
                if match.full_time_result is None:
                    continue
                actual_letter = match.full_time_result.value
                score = score_1x2(
                    p_home=pred.home_win_prob,
                    p_draw=pred.draw_prob or 0.0,
                    p_away=pred.away_win_prob,
                    actual=actual_letter,
                )
            else:
                # Baseball / 2-outcome sports — derive H/A from scores directly
                if match.home_score > match.away_score:
                    actual_letter = "H"
                elif match.away_score > match.home_score:
                    actual_letter = "A"
                else:
                    # Tied final (suspended/postponed weirdness in baseball) — skip
                    continue
                score = score_winner(
                    p_home=pred.home_win_prob,
                    p_away=pred.away_win_prob,
                    actual=actual_letter,
                )

            ou_correct = None
            if pred.over_under_line is not None and pred.over_prob is not None:
                total = match.home_score + match.away_score
                ou_correct, _ou_notes = score_over_under(
                    pred.over_prob,
                    pred.under_prob or (1 - pred.over_prob),
                    total,
                    pred.over_under_line,
                )

            # Phase 11: Closing-line value. Compare our top-pick probability
            # to the bookmaker's de-vigged implied probability for that same
            # selection, using the latest odds snapshot we have for this match.
            # Positive CLV = our model was on the value side of the close.
            clv = None
            closing_price = None
            closing_bookmaker = None
            from src.db.schema import Odds
            from src.walters.value import MarketSnapshot

            # Find our top-pick selection from the prediction
            pred_probs = {
                "HOME": pred.home_win_prob or 0.0,
                "DRAW": pred.draw_prob or 0.0,
                "AWAY": pred.away_win_prob or 0.0,
            }
            # Strip 0-prob selections (baseball has no draw)
            pred_probs = {k: v for k, v in pred_probs.items() if v > 0}
            top_pick_sel = max(pred_probs, key=pred_probs.get) if pred_probs else None

            if top_pick_sel is not None:
                odds_rows = list(s.execute(
                    select(Odds).where(
                        Odds.match_id == match.id,
                        Odds.market == "1X2",
                    )
                ).scalars())
                if odds_rows:
                    # Group by selection
                    by_sel: dict[str, list[tuple[str, float]]] = {}
                    for o in odds_rows:
                        by_sel.setdefault(o.selection, []).append(
                            (o.bookmaker, o.price_decimal)
                        )
                    snap = MarketSnapshot(market="1X2", by_selection=by_sel)
                    implied = snap.average_implied()
                    overround = sum(implied.values())
                    if overround > 0 and top_pick_sel in implied:
                        fair_prob = implied[top_pick_sel] / overround
                        clv = pred_probs[top_pick_sel] - fair_prob
                        best = snap.best_price(top_pick_sel)
                        if best:
                            closing_bookmaker, closing_price = best

            s.add(PredictionOutcome(
                prediction_id=pred.id,
                actual_result=match.full_time_result,
                actual_home_score=match.home_score,
                actual_away_score=match.away_score,
                log_loss=score.log_loss,
                brier_score=score.brier_score,
                rps=score.rps,
                top_pick_hit=score.top_pick_hit,
                total_correct=ou_correct,
                notes=score.notes,
                clv=clv,
                closing_price=closing_price,
                closing_bookmaker=closing_bookmaker,
            ))
            written += 1

        # M11b (2026-08-25): CLV backfill for late-arriving closers.
        # UTC-rollover games get their book odds only after their UTC date
        # becomes "today" — usually after the morning grading has already
        # written the outcome with clv=NULL. Revisit those outcomes once
        # odds exist and fill CLV in place. Idempotent: only touches rows
        # where clv IS NULL and 1X2 odds are now present.
        from src.db.schema import Odds
        from src.walters.value import MarketSnapshot

        backfilled = 0
        null_clv_stmt = (
            select(PredictionOutcome)
            .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
            .join(Match, Match.id == Prediction.match_id)
            .where(PredictionOutcome.clv.is_(None), Match.sport == sport)
        )
        for outcome in s.execute(null_clv_stmt).scalars():
            pred = outcome.prediction
            match = pred.match
            pred_probs = {
                "HOME": pred.home_win_prob or 0.0,
                "DRAW": pred.draw_prob or 0.0,
                "AWAY": pred.away_win_prob or 0.0,
            }
            pred_probs = {k: v for k, v in pred_probs.items() if v > 0}
            if not pred_probs:
                continue
            top_pick_sel = max(pred_probs, key=pred_probs.get)
            odds_rows = list(s.execute(
                select(Odds).where(
                    Odds.match_id == match.id,
                    Odds.market == "1X2",
                )
            ).scalars())
            if not odds_rows:
                continue
            by_sel: dict[str, list[tuple[str, float]]] = {}
            for o in odds_rows:
                by_sel.setdefault(o.selection, []).append(
                    (o.bookmaker, o.price_decimal)
                )
            snap = MarketSnapshot(market="1X2", by_selection=by_sel)
            implied = snap.average_implied()
            overround = sum(implied.values())
            if overround <= 0 or top_pick_sel not in implied:
                continue
            fair_prob = implied[top_pick_sel] / overround
            outcome.clv = pred_probs[top_pick_sel] - fair_prob
            best = snap.best_price(top_pick_sel)
            if best:
                outcome.closing_bookmaker, outcome.closing_price = best
            backfilled += 1
        if backfilled:
            log.info("CLV backfilled for %d outcomes (late closers).", backfilled)

    log.info("Wrote %d new prediction outcomes.", written)
    return written


# --------------------------------------------------------------------------
# Improve — the full nightly loop
# --------------------------------------------------------------------------


@dataclass
class ImproveResult:
    candidate_version: str
    production_version: str | None
    promoted: bool
    candidate_log_loss: float | None
    production_log_loss: float | None
    holdout_size: int
    reasoning: str


def improve(
    sport: Sport = Sport.SOCCER,
    holdout_days: int = DEFAULT_HOLDOUT_DAYS,
    min_delta: float = DEFAULT_PROMOTION_DELTA,
) -> ImproveResult:
    """
    The model improvement loop.

    Steps:
      1. Score any unscored predictions (so we have fresh evaluation data).
      2. Train a fresh candidate from current state.
      3. Generate candidate predictions for the holdout window's finished
         matches (those we have actual outcomes for).
      4. Compare candidate vs production on the holdout.
      5. Promote if candidate beats production by min_delta in log loss.
    """
    # Step 1: bring evaluation up to date
    evaluate_finished(sport=sport)

    # Step 2: train candidate
    train_result = train_fresh(sport=sport, notes="auto-train (improve loop)")
    candidate_version = train_result.version

    # Step 3+4: compare on holdout
    cutoff = datetime.utcnow() - timedelta(days=holdout_days)

    with session_scope() as s:
        production_version = _current_production_version(s, sport)

        holdout_matches = _load_holdout_matches(s, sport, cutoff)
        holdout_size = len(holdout_matches)

        # If no production model yet, just promote the candidate
        if production_version is None:
            _set_status(s, sport, candidate_version, "production")
            return ImproveResult(
                candidate_version=candidate_version,
                production_version=None,
                promoted=True,
                candidate_log_loss=None,
                production_log_loss=None,
                holdout_size=holdout_size,
                reasoning="No existing production model — candidate promoted.",
            )

        if holdout_size < 30:
            # Not enough data to make a confident promotion decision
            _set_status(s, sport, candidate_version, "rejected")
            return ImproveResult(
                candidate_version=candidate_version,
                production_version=production_version,
                promoted=False,
                candidate_log_loss=None,
                production_log_loss=None,
                holdout_size=holdout_size,
                reasoning=f"Holdout too small ({holdout_size} < 30). Candidate rejected.",
            )

        cand_loss = _score_model_on_holdout(s, candidate_version, holdout_matches, sport=sport)
        prod_loss = _score_model_on_holdout(s, production_version, holdout_matches, sport=sport)

        # Persist holdout stats on the candidate row
        _update_candidate_holdout_stats(s, candidate_version, holdout_size, cand_loss, sport=sport)

        if cand_loss is None or prod_loss is None:
            _set_status(s, sport, candidate_version, "rejected")
            return ImproveResult(
                candidate_version=candidate_version,
                production_version=production_version,
                promoted=False,
                candidate_log_loss=cand_loss,
                production_log_loss=prod_loss,
                holdout_size=holdout_size,
                reasoning="Could not score one of the models on holdout. Rejected.",
            )

        delta = prod_loss - cand_loss  # positive = candidate better (lower loss)
        if delta >= min_delta:
            _shelve_current_production(s, sport)
            _set_status(s, sport, candidate_version, "production", promote=True)
            return ImproveResult(
                candidate_version=candidate_version,
                production_version=production_version,
                promoted=True,
                candidate_log_loss=cand_loss,
                production_log_loss=prod_loss,
                holdout_size=holdout_size,
                reasoning=(
                    f"Candidate log-loss {cand_loss:.4f} beats production "
                    f"{prod_loss:.4f} by {delta:.4f} (threshold {min_delta:.4f}). "
                    f"Promoted."
                ),
            )

        _set_status(s, sport, candidate_version, "rejected")
        return ImproveResult(
            candidate_version=candidate_version,
            production_version=production_version,
            promoted=False,
            candidate_log_loss=cand_loss,
            production_log_loss=prod_loss,
            holdout_size=holdout_size,
            reasoning=(
                f"Candidate log-loss {cand_loss:.4f} did not beat production "
                f"{prod_loss:.4f} by {min_delta:.4f}. Rejected."
            ),
        )


# --------------------------------------------------------------------------
# DB helpers
# --------------------------------------------------------------------------


def _load_finished_matches(s: Session, sport: Sport) -> list[Match]:
    """Pull all finished matches with scores + team/competition relationships."""
    stmt = (
        select(Match)
        .options(
            selectinload(Match.competition),
            selectinload(Match.home_team),
            selectinload(Match.away_team),
        )
        .where(Match.sport == sport, Match.status == MatchStatus.FINISHED)
        .order_by(Match.utc_date.asc())
    )
    return [
        m for m in s.execute(stmt).scalars()
        if m.home_score is not None and m.away_score is not None
    ]


def _load_holdout_matches(s: Session, sport: Sport, cutoff: datetime) -> list[Match]:
    stmt = (
        select(Match)
        .options(
            selectinload(Match.competition),
            selectinload(Match.home_team),
            selectinload(Match.away_team),
        )
        .where(
            Match.sport == sport,
            Match.status == MatchStatus.FINISHED,
            Match.utc_date >= cutoff,
        )
    )
    return [
        m for m in s.execute(stmt).scalars()
        if m.home_score is not None and m.away_score is not None
    ]


def _next_version_string(s: Session, sport: Sport, family: str) -> str:
    """Find the next vN.0.0 string. Simple — we don't do semver minor bumps."""
    existing = list(
        s.execute(
            select(ModelVersion.version).where(
                ModelVersion.sport == sport, ModelVersion.model_family == family
            )
        ).scalars()
    )
    # Versions look like "v1", "v2", etc. Strip and find max.
    max_n = 0
    for v in existing:
        if v and v.startswith("v"):
            try:
                n = int(v[1:].split(".")[0])
                max_n = max(max_n, n)
            except ValueError:
                continue
    return f"v{max_n + 1}"


def _current_production_version(s: Session, sport: Sport) -> str | None:
    row = s.execute(
        select(ModelVersion.version).where(
            ModelVersion.sport == sport,
            ModelVersion.model_family == _family_for(sport),
            ModelVersion.status == "production",
        )
    ).scalar_one_or_none()
    return row


def _resolve_model_version(
    s: Session, version: str | None, sport: Sport,
) -> ModelVersion:
    """Resolve a version string to a ModelVersion row. Defaults to production."""
    if version is None:
        version = _current_production_version(s, sport)
        if version is None:
            raise RuntimeError(
                "No production model yet. Run `python cli.py train` first."
            )
    mv = s.execute(
        select(ModelVersion).where(
            ModelVersion.sport == sport,
            ModelVersion.model_family == _family_for(sport),
            ModelVersion.version == version,
        )
    ).scalar_one_or_none()
    if mv is None:
        raise RuntimeError(f"Model version {version} not found.")
    return mv


def _set_status(
    s: Session, sport: Sport, version: str, status: str, promote: bool = False,
) -> None:
    mv = s.execute(
        select(ModelVersion).where(
            ModelVersion.sport == sport,
            ModelVersion.model_family == _family_for(sport),
            ModelVersion.version == version,
        )
    ).scalar_one()
    mv.status = status
    if promote:
        mv.promoted_at = datetime.utcnow()


def _shelve_current_production(s: Session, sport: Sport) -> None:
    rows = s.execute(
        select(ModelVersion).where(
            ModelVersion.sport == sport,
            ModelVersion.model_family == _family_for(sport),
            ModelVersion.status == "production",
        )
    ).scalars()
    for mv in rows:
        mv.status = "shelved"


def _score_model_on_holdout(
    s: Session, version: str, holdout: list[Match], sport: Sport = Sport.SOCCER,
) -> float | None:
    """
    Score a model's predictions on the holdout matches by re-running the
    model and computing average log-loss against actuals. Pure replay —
    doesn't touch the predictions table.

    Soccer: replays Elo+Poisson against per-match strengths.
    MLB: replays Pythagorean+negbin with run profiles computed from
         finished games *before* each holdout date (to avoid info leak).
    """
    if sport == Sport.SOCCER:
        return _score_model_on_holdout_soccer(s, version, holdout)
    if sport == Sport.MLB:
        return _score_model_on_holdout_mlb(s, version, holdout)
    return None


def _score_model_on_holdout_soccer(
    s: Session, version: str, holdout: list[Match],
) -> float | None:
    sport = Sport.SOCCER
    mv_row = s.execute(
        select(ModelVersion).where(
            ModelVersion.model_family == _family_for(sport),
            ModelVersion.version == version,
        )
    ).scalar_one_or_none()
    if mv_row is None:
        return None

    params = mv_row.parameters or {}
    # Phase 7: handle both dual-Elo and legacy-flat shapes
    elo_raw = params.get("elo", {}) or {}
    if "league" in elo_raw or "cup" in elo_raw:
        elo_state = EloState.from_dict(elo_raw.get("league", {}))
    else:
        elo_state = EloState.from_dict(elo_raw)
    contexts_raw = params.get("contexts", {})
    contexts = {k: CompetitionScoringContext(**v) for k, v in contexts_raw.items()}
    poisson_cfg = PoissonConfig(**params.get("poisson", {}))

    losses: list[float] = []
    for m in holdout:
        if m.full_time_result is None:
            continue
        comp_code = m.competition.code if m.competition else ""
        context = contexts.get(comp_code, CompetitionScoringContext())
        season_matches = s.execute(
            select(Match).where(
                Match.competition_id == m.competition_id,
                Match.season == m.season,
                Match.status == MatchStatus.FINISHED,
            )
        ).scalars()
        strength_input = [
            {
                "home_team_id": sm.home_team_id,
                "away_team_id": sm.away_team_id,
                "home_score": sm.home_score,
                "away_score": sm.away_score,
            }
            for sm in season_matches
            if sm.home_score is not None and sm.away_score is not None
        ]
        strengths = estimate_strengths(strength_input, context)
        h_str = strengths.get(m.home_team_id)
        a_str = strengths.get(m.away_team_id)
        if not h_str or not a_str:
            continue
        pred = predict_match(
            home_elo=elo_state.get(m.home_team_id),
            away_elo=elo_state.get(m.away_team_id),
            home_strength=h_str,
            away_strength=a_str,
            context=context,
            config=poisson_cfg,
        )
        score = score_1x2(
            pred.p_home, pred.p_draw, pred.p_away, m.full_time_result.value
        )
        losses.append(score.log_loss)
    if not losses:
        return None
    return sum(losses) / len(losses)


def _score_model_on_holdout_mlb(
    s: Session, version: str, holdout: list[Match],
) -> float | None:
    """
    Replay the MLB model over the holdout window.

    For each holdout game:
      1. Pull the BaseballConfig from this model version's params.
      2. Compute home/away run profiles using only games finished BEFORE
         this game's date (avoids information leak from same-day or later
         results).
      3. Run predict_game() with neutral pitching (pitcher ERA wiring
         is Phase 5.2 work, deliberately omitted here so soccer's improve
         loop parity isn't blocked).
      4. Score via score_winner (H/A only — no draws).

    Returns average log-loss across all scoreable holdout games, or None
    if too few games scored cleanly.
    """
    sport = Sport.MLB
    mv_row = s.execute(
        select(ModelVersion).where(
            ModelVersion.model_family == _family_for(sport),
            ModelVersion.version == version,
        )
    ).scalar_one_or_none()
    if mv_row is None:
        return None

    from src.models.baseball import (
        BaseballConfig, estimate_run_profiles, predict_game,
    )
    from src.walters.evaluation import score_winner

    params = mv_row.parameters or {}
    cfg = BaseballConfig(**params.get("baseball_config", {}))

    losses: list[float] = []
    for m in holdout:
        if m.home_score is None or m.away_score is None:
            continue
        # Determine actual winner — baseball never draws but defensively skip ties
        if m.home_score > m.away_score:
            actual = "H"
        elif m.away_score > m.home_score:
            actual = "A"
        else:
            continue

        # Run profiles from finished games BEFORE this match's date.
        # Cap at 500 games to keep replay fast.
        prior_matches = list(s.execute(
            select(Match)
            .where(
                Match.sport == Sport.MLB,
                Match.status == MatchStatus.FINISHED,
                Match.utc_date < m.utc_date,
            )
            .order_by(Match.utc_date.desc())
            .limit(500)
        ).scalars())

        profile_input = [
            {
                "home_team_id": pm.home_team_id,
                "away_team_id": pm.away_team_id,
                "home_score": pm.home_score,
                "away_score": pm.away_score,
                "utc_date": pm.utc_date,
            }
            for pm in prior_matches
            if pm.home_score is not None and pm.away_score is not None
        ]
        if len(profile_input) < 30:
            # Not enough history to compute meaningful profiles
            continue
        profiles = estimate_run_profiles(profile_input)
        h_profile = profiles.get(m.home_team_id)
        a_profile = profiles.get(m.away_team_id)
        if h_profile is None or a_profile is None:
            continue

        pred = predict_game(
            home_profile=h_profile,
            away_profile=a_profile,
            config=cfg,
        )
        score = score_winner(pred.p_home, pred.p_away, actual)
        losses.append(score.log_loss)

    if not losses:
        return None
    return sum(losses) / len(losses)


def _update_candidate_holdout_stats(
    s: Session, version: str, holdout_size: int, log_loss: float | None,
    sport: Sport = Sport.SOCCER,
) -> None:
    mv = s.execute(
        select(ModelVersion).where(
            ModelVersion.model_family == _family_for(sport),
            ModelVersion.version == version,
        )
    ).scalar_one()
    mv.holdout_size = holdout_size
    mv.holdout_log_loss = log_loss


# ---------------------------------------------------------------------------
# S6: weekly soccer state refresh (Elo/contexts) with a SANITY gate.
# ---------------------------------------------------------------------------

def soccer_weekly_refresh(max_rating_drift: float = 80.0) -> dict:
    """
    Weekly in-season refresh: retrain soccer Elo state + contexts from all
    finished matches and promote — gated by SANITY checks, not a performance
    holdout.

    WHY NOT A PERFORMANCE GATE: the candidate inherits production's poisson
    config verbatim, so the leakage-free backtest (which re-walks Elo
    internally from prior matches) scores production and candidate
    IDENTICALLY — it evaluates config, not frozen state. And the legacy
    holdout comparison is self-graded homework (candidate trained through the
    holdout window; the exact contaminated eval the backlog disavowed for
    soccer). For "same config, fresher state", the real risk is DATA
    CORRUPTION poisoning the state — bad scores, duplicate matches, a broken
    sync — so that's what gets gated:

      1. data monotonicity: train_size >= production's train_size
      2. config inheritance: candidate poisson == production poisson, exactly
      3. Elo health: finite ratings, plausible band, league-mean conservation
      4. bounded drift: no common team's league Elo moved more than
         `max_rating_drift` since production. Calibration: a normal week is
         <~40 pts, a legit two-game week with big wins ~70-80, and a
         fabricated run of 19-0s measured 99 — default 80 catches corruption
         while clearing real weeks (override for double-gameweek anomalies)

    Performance verdicts stay where they belong: forward grading week over
    week, and the market-scored backtest for CONFIG changes.
    """
    evaluate_finished(sport=Sport.SOCCER)

    # S15 (2026-08-25): skip-guard. Training is deterministic, so retraining
    # on unchanged data can only mint a twin of production (v17/v18 proved
    # it: same data, drift 0) and leaves phantom versions in the ledger.
    # Compare the current trainable-match count to production's train_size
    # BEFORE training; if nothing new has finished, skip entirely. Uses the
    # same count the trainer would report, via its own counting path.
    from sqlalchemy import func as _func
    with session_scope() as s:
        prod = s.execute(
            select(ModelVersion).where(
                ModelVersion.sport == Sport.SOCCER,
                ModelVersion.status == "production")
        ).scalars().first()
        if prod is not None and prod.train_size:
            current_n = s.execute(
                select(_func.count(Match.id)).where(
                    Match.sport == Sport.SOCCER,
                    Match.status == MatchStatus.FINISHED,
                    Match.home_score.is_not(None),
                    Match.away_score.is_not(None),
                )
            ).scalar() or 0
            if current_n <= (prod.train_size or 0):
                msg = (f"No new completed matches since {prod.version} "
                       f"(trainable {current_n} <= {prod.train_size}) — "
                       f"refresh skipped, {prod.version} remains production.")
                log.info(msg)
                return {"promoted": False, "candidate": None,
                        "skipped": True, "reason": msg, "checks": []}

    train_result = train_fresh(sport=Sport.SOCCER,
                               notes="weekly state refresh (S6)")
    cand_version = train_result.version
    checks: list[str] = []

    def _reject(reason: str) -> dict:
        with session_scope() as s:
            _set_status(s, Sport.SOCCER, cand_version, "rejected")
        return {"promoted": False, "candidate": cand_version,
                "reason": reason, "checks": checks}

    with session_scope() as s:
        prod_version = _current_production_version(s, Sport.SOCCER)
        if prod_version is None:
            _set_status(s, Sport.SOCCER, cand_version, "production")
            return {"promoted": True, "candidate": cand_version,
                    "reason": "no production model — candidate promoted",
                    "checks": checks}
        prod_params = _production_params(s, Sport.SOCCER) or {}
        from sqlalchemy import select as _select
        cand = s.execute(
            _select(ModelVersion).where(
                ModelVersion.sport == Sport.SOCCER,
                ModelVersion.version == cand_version)
        ).scalars().first()
        cand_params = dict(cand.parameters or {})
        prod_row = s.execute(
            _select(ModelVersion).where(
                ModelVersion.sport == Sport.SOCCER,
                ModelVersion.version == prod_version)
        ).scalars().first()

        # 1) monotone data
        prev_n = prod_row.train_size or 0
        if (cand.train_size or 0) < prev_n:
            return _reject(f"train_size shrank: {cand.train_size} < {prev_n} "
                           "(data loss — investigate sync before refreshing)")
        checks.append(f"data: {prev_n} -> {cand.train_size} matches ✓")

        # 2) config inheritance. NOT byte equality: production models trained
        # before a config field existed lack that key, and the candidate is
        # SUPPOSED to add it at its dataclass default (base-layer design). The
        # invariant is: every key production HAS must carry the same value in
        # the candidate; extra candidate keys are new fields, named not
        # rejected. (v1 of this check demanded equality and rejected v14 for
        # having promoted-prior keys v13 predates — failed safe, fixed here.)
        prod_pz = prod_params.get("poisson") or {}
        cand_pz = cand_params.get("poisson") or {}
        diffs = [k for k, v in prod_pz.items() if cand_pz.get(k) != v]
        if diffs:
            return _reject("candidate poisson config differs from production on "
                           f"inherited keys {diffs} — refusing to promote a "
                           "silent recalibration")
        new_keys = sorted(set(cand_pz) - set(prod_pz))
        checks.append("config: all production values inherited ✓"
                      + (f" (new fields at defaults: {', '.join(new_keys)})"
                         if new_keys else ""))

        # 3) Elo health
        cand_league = ((cand_params.get("elo") or {}).get("league") or {})
        ratings = cand_league.get("ratings") or {}
        vals = [float(v) for v in ratings.values()]
        if not vals:
            return _reject("candidate has no league Elo ratings")
        import math as _math
        if any(not _math.isfinite(v) for v in vals):
            return _reject("non-finite Elo rating in candidate")
        lo, hi = min(vals), max(vals)
        if lo < 900 or hi > 2200:
            return _reject(f"Elo out of plausible band: min {lo:.0f}, max {hi:.0f}")
        mean = sum(vals) / len(vals)
        start = float(cand_league.get("starting_rating", 1500.0) or 1500.0)
        if abs(mean - start) > 60:
            return _reject(f"league Elo mean {mean:.0f} drifted from {start:.0f} "
                           "(conservation broken — suspect duplicated results)")
        checks.append(f"elo: n={len(vals)} range {lo:.0f}-{hi:.0f} mean {mean:.0f} ✓")

        # 4) bounded weekly drift vs production.
        # JSON round-tripping stringifies dict keys, so candidate (in-memory,
        # int keys) and production (DB-loaded, str keys) MUST be normalized to
        # a common key type — otherwise every lookup misses and drift reads 0,
        # which is a gate that never fires. Also refuse if nothing overlaps.
        prod_ratings_raw = (((prod_params.get("elo") or {}).get("league") or {})
                            .get("ratings") or {})
        prod_ratings = {str(k): float(v) for k, v in prod_ratings_raw.items()}
        cand_ratings = {str(k): float(v) for k, v in ratings.items()}
        common = set(cand_ratings) & set(prod_ratings)
        if not common:
            return _reject("no overlapping teams between candidate and "
                           "production Elo — cannot verify drift; refusing")
        worst_name, worst = None, 0.0
        for tid in common:
            d = abs(cand_ratings[tid] - prod_ratings[tid])
            if d > worst:
                worst, worst_name = d, tid
        checks.append(f"drift basis: {len(common)} common teams")

        # 4b) rating-spread guard (2026-09-01, from the v19 rejection): the
        # drift check caught Arsenal moving 179 pts, but the real signal was
        # the whole table collapsing (range 1368-1691 -> 1469-1532). A
        # candidate whose spread over the COMMON teams shrinks below 60% of
        # production's is a compressed fit, not a data refresh — refuse.
        _pc = [prod_ratings[t] for t in common]
        _cc = [cand_ratings[t] for t in common]
        prod_spread = (max(_pc) - min(_pc)) if len(_pc) > 1 else 0.0
        cand_spread = (max(_cc) - min(_cc)) if len(_cc) > 1 else 0.0
        if prod_spread > 0 and cand_spread < 0.60 * prod_spread:
            return _reject(f"Elo spread compression: candidate {cand_spread:.0f} vs "
                           f"production {prod_spread:.0f} over {len(common)} common "
                           f"teams ({cand_spread/prod_spread:.0%}) — fit collapsed "
                           f"toward the mean, not a data refresh")
        checks.append(f"spread: {cand_spread:.0f} vs {prod_spread:.0f} "
                      f"({(cand_spread/prod_spread if prod_spread else 1):.0%} of production) ✓")

        if worst > max_rating_drift:
            return _reject(f"Elo drift {worst:.0f} for team_id={worst_name} exceeds "
                           f"{max_rating_drift:.0f}/week — suspect corrupted scores")
        checks.append(f"drift: max {worst:.0f} pts (limit {max_rating_drift:.0f}) ✓")

        # promote
        _shelve_current_production(s, Sport.SOCCER)
        _set_status(s, Sport.SOCCER, cand_version, "production", promote=True)
        return {"promoted": True, "candidate": cand_version,
                "previous": prod_version,
                "reason": "all sanity checks passed", "checks": checks}
