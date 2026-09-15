"""
Prediction export — bulk dump of model predictions with surrounding context
for validation / review.

The full-fidelity output is JSON: every field surfaced including nested
factor breakdown and per-selection edge math. A CSV variant flattens the
headline columns for spreadsheet scanning.

Designed to answer the question "what did the model think on day X, and
why" without needing to click through 30 match-detail pages.
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.database import session_scope
from src.db.schema import (
    Competition, Injury, Match, MatchParticipant, MatchStatus, Odds,
    OddsSnapshot, PitcherSeasonStats, Prediction, PredictionOutcome, Sport, Team,
)
from src.web.preview import compute_team_form
from src.walters.value import MarketSnapshot

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

# Season-keyed promoted-club registry (2026-08-27, user decision: cohort
# flag persists ALL season). Keyed "COMP:SEASON" so it EXPIRES AUTOMATICALLY
# when the season string rolls over — the removal mechanism is the calendar.
# Maintenance: each August, add the new season's promoted set here.
PROMOTED_THIS_SEASON: dict[str, set[str]] = {
    "PL:2026/27": {"Coventry", "Hull City"},
}


def export_predictions(
    *,
    sport: Sport,
    start_date: datetime,
    end_date: datetime,
    competition_code: str | None = None,
    statuses: list[MatchStatus] | None = None,
    output_format: str = "json",
) -> str:
    """
    Build a structured export of predictions in a date range.

    Args:
        sport:            Sport.SOCCER or Sport.MLB
        start_date:       inclusive UTC datetime lower bound
        end_date:         exclusive UTC datetime upper bound
        competition_code: optional filter (e.g. "PL", "MLB")
        statuses:         optional list of statuses to include (default: any)
        output_format:    "json" or "csv"

    Returns:
        Serialized string in the requested format.
    """
    rows = _collect_rows(
        sport=sport,
        start_date=start_date,
        end_date=end_date,
        competition_code=competition_code,
        statuses=statuses,
    )
    if output_format == "json":
        return json.dumps({
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "sport": sport.value,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "competition_code": competition_code,
            "count": len(rows),
            "predictions": rows,
        }, indent=2, default=_json_safe)
    if output_format == "csv":
        return _to_csv(rows, sport)
    raise ValueError(f"Unknown output_format: {output_format!r}")


# ----------------------------------------------------------------------
# Row builder
# ----------------------------------------------------------------------

def _collect_rows(
    *,
    sport: Sport,
    start_date: datetime,
    end_date: datetime,
    competition_code: str | None,
    statuses: list[MatchStatus] | None,
) -> list[dict]:
    """Build one dict per match in the window, with prediction + context."""
    out: list[dict] = []
    with session_scope() as s:
        # Resolve competition if filtered
        comp_id = None
        if competition_code:
            comp = s.execute(
                select(Competition).where(Competition.code == competition_code)
            ).scalar_one_or_none()
            if not comp:
                raise ValueError(f"Competition {competition_code!r} not found")
            comp_id = comp.id

        # Query matches in range
        stmt = (
            select(Match)
            .options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
                selectinload(Match.competition),
            )
            .where(
                Match.sport == sport,
                Match.utc_date >= start_date,
                Match.utc_date < end_date,
            )
            .order_by(Match.utc_date.asc())
        )
        if comp_id is not None:
            stmt = stmt.where(Match.competition_id == comp_id)
        if statuses is not None:
            stmt = stmt.where(Match.status.in_(statuses))

        matches = list(s.execute(stmt).scalars())

        # Pull all predictions for these matches in one go
        match_ids = [m.id for m in matches]
        if not match_ids:
            return out

        # Latest prediction per match (highest model_version per match)
        preds_by_match: dict[int, Prediction] = {}
        for pred in s.execute(
            select(Prediction)
            .where(Prediction.match_id.in_(match_ids))
            .order_by(Prediction.computed_at.desc())
        ).scalars():
            if pred.match_id not in preds_by_match:
                preds_by_match[pred.match_id] = pred

        # Outcomes (only finished matches)
        outcomes_by_pred: dict[int, PredictionOutcome] = {}
        for outcome in s.execute(
            select(PredictionOutcome)
            .where(PredictionOutcome.prediction_id.in_(
                [p.id for p in preds_by_match.values()]
            ))
        ).scalars():
            outcomes_by_pred[outcome.prediction_id] = outcome

        # Odds for these matches
        odds_by_match: dict[int, list[Odds]] = {}
        for o in s.execute(
            select(Odds).where(Odds.match_id.in_(match_ids))
        ).scalars():
            odds_by_match.setdefault(o.match_id, []).append(o)

        # Kalshi snapshots (second, independent market source). sync-kalshi
        # writes these to OddsSnapshot(source="kalshi", market="ML") — NOT the
        # Odds table — so they must be loaded explicitly here or the export
        # silently shows bookmakers only. Latest capture per (match, selection):
        # rows are append-only, ordered DESC and first-wins per key.
        # GUARD: captures at/after first pitch are IN-GAME prices (Kalshi
        # markets stay open during play) — excluded here so even historical
        # contamination can't reach the export or downstream reads.
        start_by_id = {m.id: m.utc_date for m in matches}
        kalshi_by_match: dict[int, dict[str, OddsSnapshot]] = {}
        for snap in s.execute(
            select(OddsSnapshot)
            .where(
                OddsSnapshot.match_id.in_(match_ids),
                OddsSnapshot.source == "kalshi",
            )
            .order_by(OddsSnapshot.captured_at.desc())
        ).scalars():
            start = start_by_id.get(snap.match_id)
            if (start is not None and snap.captured_at is not None
                    and snap.captured_at >= start):
                continue  # in-game price, never pre-game truth
            per_match = kalshi_by_match.setdefault(snap.match_id, {})
            if snap.selection not in per_match:
                per_match[snap.selection] = snap

        # MLB pitcher participants + ERA join
        pitchers_by_match: dict[int, list[MatchParticipant]] = {}
        if sport == Sport.MLB:
            for p in s.execute(
                select(MatchParticipant).where(
                    MatchParticipant.match_id.in_(match_ids),
                    MatchParticipant.role == "starting_pitcher",
                )
            ).scalars():
                pitchers_by_match.setdefault(p.match_id, []).append(p)

            # Pre-fetch all pitcher stats relevant to this slate
            pitcher_source_ids = {
                p.player_source_id for ps in pitchers_by_match.values()
                for p in ps if p.player_source_id
            }
            pitcher_stats_by_source_id: dict[str, PitcherSeasonStats] = {}
            if pitcher_source_ids:
                for ps in s.execute(
                    select(PitcherSeasonStats).where(
                        PitcherSeasonStats.player_source_id.in_(pitcher_source_ids)
                    )
                ).scalars():
                    pitcher_stats_by_source_id[ps.player_source_id] = ps
        else:
            pitcher_stats_by_source_id = {}

        # Soccer injuries by team (current snapshot, not historical)
        team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
        injuries_by_team: dict[int, list[Injury]] = {}
        if sport == Sport.SOCCER and team_ids:
            for inj in s.execute(
                select(Injury).where(Injury.team_id.in_(team_ids))
            ).scalars():
                injuries_by_team.setdefault(inj.team_id, []).append(inj)

        # Unused-in-model tracked context (weather/umpire/bullpen) — MLB only.
        # Rides alongside each prediction, stamped used_in_model: false, so the
        # betting layer can see what we track vs what the model actually uses.
        unused_context_by_match: dict[int, dict] = {}
        if sport == Sport.MLB:
            try:
                from src.walters.prediction_context import build_unused_context
                unused_context_by_match = build_unused_context(s, matches)
            except Exception:
                unused_context_by_match = {}  # never let context break the export

        # Build per-match row
        for m in matches:
            row = _build_row(
                s, m,
                pred=preds_by_match.get(m.id),
                outcome=outcomes_by_pred.get(
                    preds_by_match[m.id].id if m.id in preds_by_match else None
                ),
                odds=odds_by_match.get(m.id, []),
                kalshi=kalshi_by_match.get(m.id),
                pitchers=pitchers_by_match.get(m.id, []),
                pitcher_stats_by_source_id=pitcher_stats_by_source_id,
                injuries_by_team=injuries_by_team,
                unused_context=unused_context_by_match.get(m.id),
                sport=sport,
            )
            out.append(row)
    return out


def _build_row(
    s,
    m: Match,
    *,
    pred: Prediction | None,
    outcome: PredictionOutcome | None,
    odds: list[Odds],
    kalshi: dict[str, OddsSnapshot] | None = None,
    pitchers: list[MatchParticipant],
    pitcher_stats_by_source_id: dict,
    injuries_by_team: dict,
    unused_context: dict | None = None,
    sport: Sport,
) -> dict:
    """Build one match's export dict."""
    is_baseball = sport == Sport.MLB

    row: dict[str, Any] = {
        "match_id": m.id,
        "utc_date": m.utc_date.isoformat() if m.utc_date else None,
        "status": m.status.value if m.status else None,
        "competition": m.competition.code if m.competition else None,
        "season": m.season,
        "venue": m.venue,
        "home_team": m.home_team.name if m.home_team else None,
        "away_team": m.away_team.name if m.away_team else None,
        "actual_home_score": m.home_score,
        "actual_away_score": m.away_score,
    }

    # ----- Prediction
    if pred is None:
        row["prediction"] = None
    else:
        probs = {
            "home_win": pred.home_win_prob,
            "draw": pred.draw_prob,
            "away_win": pred.away_win_prob,
        }
        # Top pick by probability
        non_null = {k: v for k, v in probs.items() if v is not None}
        top_pick = max(non_null, key=non_null.get) if non_null else None
        top_pick_prob = non_null[top_pick] if top_pick else None

        # Thing 1 & 2: conviction tier + side-vs-total expression signal.
        # Reporting only — derived from probabilities the model already
        # produced. Lets post-mortems separate actionable picks from
        # coin-flips and see when the total is the stronger read.
        from src.web.preview import classify_tier, expression_signal, bullpen_swing_flag, close_game_flag
        fb_for_tier = pred.factor_breakdown or {}
        starter_known_for_tier = (
            fb_for_tier.get("home_starter_known", True)
            and fb_for_tier.get("away_starter_known", True)
        )
        tier = (classify_tier(top_pick_prob, starter_known=starter_known_for_tier)
                if top_pick_prob is not None else None)
        # Totals are only a candidate "stronger expression" when we had a real
        # market line (over_prob is None when the line was unavailable). Without
        # that guard the model could flag an un-actionable phantom total as the
        # stronger read — the Coors failure mode.
        expression = (expression_signal(top_pick_prob, pred.over_prob)
                      if (top_pick_prob is not None and pred.over_prob is not None)
                      else None)
        bp_swing = bullpen_swing_flag(fb_for_tier) if is_baseball else None
        close_game = (close_game_flag(top_pick_prob, fb_for_tier)
                      if is_baseball and top_pick_prob is not None else None)

        row["prediction"] = {
            "model_version": pred.model_version,
            "computed_at": pred.computed_at.isoformat() if pred.computed_at else None,
            "probabilities": {k: round(v, 4) if v is not None else None
                              for k, v in probs.items()},
            "top_pick": top_pick,
            "top_pick_prob": round(top_pick_prob, 4) if top_pick else None,
            "tier": tier["tier"] if tier else None,
            "actionable": tier["actionable"] if tier else None,
            "tier_capped_by_starter": tier["capped_by_starter"] if tier else None,
            "stronger_expression": expression["stronger"] if expression else "side",
            "totals_available": pred.over_under_line is not None,
            "bullpen_swing_flag": bp_swing is not None,
            "max_bullpen_swing": bp_swing["max_swing"] if bp_swing else None,
            "close_game_flag": close_game is not None,
            "p_one_run": close_game["p_one_run"] if close_game else (fb_for_tier.get("p_one_run") if is_baseball else None),
            "p_blowup": fb_for_tier.get("p_blowup") if is_baseball else None,
            "p_home_blowup": fb_for_tier.get("p_home_blowup") if is_baseball else None,
            "p_away_blowup": fb_for_tier.get("p_away_blowup") if is_baseball else None,
            "expected_home": round(pred.expected_home_score, 3) if pred.expected_home_score is not None else None,
            "expected_away": round(pred.expected_away_score, 3) if pred.expected_away_score is not None else None,
            "over_under_line": pred.over_under_line,
            "over_prob": round(pred.over_prob, 4) if pred.over_prob is not None else None,
            "to_advance_home_prob": round(pred.to_advance_home_prob, 4) if pred.to_advance_home_prob is not None else None,
            "to_advance_away_prob": round(pred.to_advance_away_prob, 4) if pred.to_advance_away_prob is not None else None,
            "factor_breakdown": pred.factor_breakdown or {},
        }

        if not is_baseball:
            # S8 (decided 2026-08-15, executed here): soccer totals ship
            # EXCLUDED until a goals pulse exists — the model's over_prob vs
            # the default 2.5 line has zero instrumentation behind it
            # (no pulse, no shrink verification, no ledger), and emitting an
            # unmeasured number violates measure-everything-you-emit. The
            # values stay in the DB for the future goals-pulse work; they
            # just don't ship. totals_available is the explicit signal.
            row["prediction"]["totals_available"] = False
            row["prediction"]["over_under_line"] = None
            row["prediction"]["over_prob"] = None
            if row["prediction"].get("stronger_expression") == "totals":
                row["prediction"]["stronger_expression"] = "side"
            # S4: baseball-only fields don't belong on soccer rows — a soccer
            # row carrying bullpen keys (even as null) invites downstream
            # confusion about what the model consulted.
            for k in ("bullpen_swing_flag", "max_bullpen_swing",
                      "tier_capped_by_starter", "p_one_run", "p_blowup",
                      "p_home_blowup", "p_away_blowup", "close_game_flag"):
                row["prediction"].pop(k, None)

    # ----- Outcome (scored matches only)
    # Tracked-but-unused signals ride alongside every row, clearly labelled so
    # the betting layer knows what's in the model vs merely tracked.
    row["unused_context"] = unused_context

    # Honest scenario decomposition: real slices of the model's distribution +
    # context flags with no fabricated weights. Presentation layer only.
    if is_baseball and row.get("prediction"):
        try:
            from src.walters.scenarios import build_scenarios
            row["scenarios"] = build_scenarios(row["prediction"], unused_context)
        except Exception:
            row["scenarios"] = None

    if outcome is None:
        row["outcome"] = None
    else:
        row["outcome"] = {
            "log_loss": round(outcome.log_loss, 4) if outcome.log_loss is not None else None,
            "brier_score": round(outcome.brier_score, 4) if outcome.brier_score is not None else None,
            "top_pick_hit": outcome.top_pick_hit,
            "total_correct": outcome.total_correct,
            "clv_pp": round(outcome.clv * 100, 2) if outcome.clv is not None else None,
            "closing_price": outcome.closing_price,
            "closing_bookmaker": outcome.closing_bookmaker,
            "notes": outcome.notes,
        }

    # ----- Market (best price + de-vigged fair prob per selection, with edge)
    # Two independent sources side by side: bookmaker consensus (Odds table)
    # and Kalshi (OddsSnapshot source="kalshi"), so the betting layer can read
    # book/Kalshi disagreement per game instead of a single blended number.
    row["market"] = _summarize_market(pred, odds, kalshi=kalshi)

    # ----- Form (last 5 results per team) — uses preview helper
    if m.home_team:
        try:
            home_form = compute_team_form(s, m.home_team, limit=5)
            row["home_form"] = {
                "last_5": home_form.get("form_string"),
                "wins": home_form.get("wins"),
                "draws": home_form.get("draws"),
                "losses": home_form.get("losses"),
                "goals_scored": home_form.get("goals_scored"),
                "goals_conceded": home_form.get("goals_conceded"),
            }
        except Exception as e:
            log.debug("form compute failed for %s: %s", m.home_team.name, e)
            row["home_form"] = None
    if m.away_team:
        try:
            away_form = compute_team_form(s, m.away_team, limit=5)
            row["away_form"] = {
                "last_5": away_form.get("form_string"),
                "wins": away_form.get("wins"),
                "draws": away_form.get("draws"),
                "losses": away_form.get("losses"),
                "goals_scored": away_form.get("goals_scored"),
                "goals_conceded": away_form.get("goals_conceded"),
            }
        except Exception as e:
            log.debug("form compute failed for %s: %s", m.away_team.name, e)
            row["away_form"] = None

    # ----- Sport-specific add-ons
    if is_baseball:
        home_p = next((p for p in pitchers if p.team_id == m.home_team_id), None)
        away_p = next((p for p in pitchers if p.team_id == m.away_team_id), None)

        def _pitcher_dict(p):
            if p is None:
                return None
            stats = pitcher_stats_by_source_id.get(p.player_source_id) if p.player_source_id else None
            return {
                "name": p.player_name,
                "kind": p.kind,
                "era": stats.era if stats else None,
                "whip": stats.whip if stats else None,
                "k_per_9": stats.k_per_9 if stats else None,
                "innings_pitched": stats.innings_pitched if stats else None,
                "games_started": stats.games_started if stats else None,
            }

        row["pitchers"] = {
            "home": _pitcher_dict(home_p),
            "away": _pitcher_dict(away_p),
        }

        # ----- Input quality (information completeness, NOT a judgment).
        # The model already widens uncertainty for missing starters; this
        # block tells the CONSUMER how much information stood behind this
        # row so thin rows can be discounted without touching probabilities.
        # Motivating case: two Kalshi-only games where the model said ~50/50
        # on thin inputs and nothing in the row said "trust this less".
        fb = (pred.factor_breakdown or {}) if pred is not None else {}
        def _starter_quality(side_p, detail):
            if side_p is None:
                return {"listed": False, "stats": False}
            q = {"listed": True,
                 "kind": getattr(side_p, "kind", None),
                 "stats": detail is not None}
            if detail:
                q["ip"] = detail.get("ip")
                q["gs"] = detail.get("gs")
                q["shrink_w"] = detail.get("shrink_w")
                q["ip_capped"] = (detail.get("effective_ip") is not None
                                  and detail["effective_ip"] < detail["ip"])
            return q
        mkt = row.get("market") or {}
        kal = mkt.get("kalshi") or {}
        row["input_quality"] = {
            "home_starter": _starter_quality(home_p, fb.get("home_starter_detail")),
            "away_starter": _starter_quality(away_p, fb.get("away_starter_detail")),
            "starters_known": {
                "home": bool(fb.get("home_starter_known")),
                "away": bool(fb.get("away_starter_known")),
            },
            "missing_starter_shrink": fb.get("missing_starter_shrink"),
            "book_odds": mkt.get("bookmaker_count") or 0,
            "kalshi": ("two_sided" if kal.get("normalized")
                       else "one_sided" if kal else "absent"),
        }
    else:
        # Soccer: injury count per team
        home_inj = injuries_by_team.get(m.home_team_id, [])
        away_inj = injuries_by_team.get(m.away_team_id, [])
        row["injuries"] = {
            "home_count": len(home_inj),
            "away_count": len(away_inj),
            "home_names": [i.player_name for i in home_inj][:8],  # first 8 only
            "away_names": [i.player_name for i in away_inj][:8],
        }

        # ----- Input quality, soccer variant (S4/S7). Descriptive, not a
        # score — same philosophy as the MLB block. Key facts a consumer
        # needs to weigh a row: how much market corroboration exists, where
        # each side's strengths came from (promoted_default = an admitted
        # prior, its own grading cohort), and — stated, not hidden — that v1
        # tracks NO lineup information: the starting XI (~1h pre-kickoff) is
        # soccer's biggest information asymmetry and rows predate it (S7;
        # ingestion is the flagship post-launch Stage-1 candidate).
        fb_iq = (pred.factor_breakdown or {}) if pred is not None else {}
        mkt_iq = row.get("market") or {}
        kal_iq = mkt_iq.get("kalshi") or {}
        if kal_iq:
            kal_status = "three_way" if kal_iq.get("normalized") else "partial"
        else:
            kal_status = "absent"
        src_h = fb_iq.get("home_strengths_source")
        src_a = fb_iq.get("away_strengths_source")
        row["input_quality"] = {
            "strengths_source": {"home": src_h, "away": src_a},
            "strengths_backfilled": fb_iq.get("strengths_backfilled"),
            "current_season_matches": fb_iq.get("current_season_matches"),
            # Season-long cohort flag (survives graduation off the prior;
            # new_to_league below reflects only the CURRENT strengths source)
            "promoted_this_season": {
                "home": row["home_team"] in PROMOTED_THIS_SEASON.get(
                    f"{row['competition']}:{row['season']}", set()),
                "away": row["away_team"] in PROMOTED_THIS_SEASON.get(
                    f"{row['competition']}:{row['season']}", set()),
            },
            "new_to_league": {"home": src_h == "promoted_default",
                              "away": src_a == "promoted_default"},
            "lineups": "none",
            # S10 (2026-08-25): injuries ARE a live model input (capped xG
            # adjustment); state when they were last refreshed so the
            # consumer can discount an adjustment made on old data. The
            # sync wipes-and-replaces per team, so MAX(refreshed_at) across
            # both teams' rows IS the last sync moment. None = no injury
            # rows at all for either team (itself worth knowing).
            "injuries_synced_at": (
                max((i.refreshed_at for i in home_inj + away_inj),
                    default=None).isoformat()
                if (home_inj or away_inj) else None
            ),
            "book_odds": mkt_iq.get("bookmaker_count") or 0,
            "kalshi": kal_status,
        }

    return row


def _summarize_market(
    pred: Prediction | None,
    odds: list[Odds],
    kalshi: dict[str, "OddsSnapshot"] | None = None,
) -> dict | None:
    """
    Per-selection summary: best price, de-vigged fair probability, edge vs model.

    Only computes 1X2 (the main market); totals/spreads omitted to keep
    the export readable. The full per-bookmaker grid is in Odds anyway.

    If Kalshi snapshots exist for the game, a "kalshi" sub-block is attached
    with the latest capture per side — kept SEPARATE from the book consensus
    (never blended) so book-vs-Kalshi disagreement stays readable downstream.
    """
    kalshi_block = _summarize_kalshi(pred, kalshi)
    if not odds:
        # Kalshi may still have priced the game even when book odds are absent.
        if kalshi_block:
            return {"selections": {}, "bookmaker_count": 0, "kalshi": kalshi_block}
        return None
    one_x_two = [o for o in odds if o.market == "1X2"]
    if not one_x_two:
        out = {"selections": {}, "bookmaker_count": 0}
        if kalshi_block:
            out["kalshi"] = kalshi_block
        return out

    by_selection: dict[str, list[tuple[str, float]]] = {}
    for o in one_x_two:
        by_selection.setdefault(o.selection, []).append((o.bookmaker, o.price_decimal))

    snap = MarketSnapshot(market="1X2", by_selection=by_selection)
    implied = snap.average_implied()
    overround = sum(implied.values()) or 1.0

    selections = {}
    for sel, books in by_selection.items():
        bookmaker, best_price = max(books, key=lambda b: b[1])
        fair_prob = (implied.get(sel, 0) / overround) if overround > 0 else None
        # Model prob for this selection (HOME → home_win_prob, etc.)
        model_prob = None
        if pred:
            if sel == "HOME":
                model_prob = pred.home_win_prob
            elif sel == "DRAW":
                model_prob = pred.draw_prob
            elif sel == "AWAY":
                model_prob = pred.away_win_prob
        edge_pp = None
        if model_prob is not None and fair_prob is not None:
            edge_pp = round((model_prob - fair_prob) * 100, 2)
        selections[sel] = {
            "best_price": best_price,
            "best_bookmaker": bookmaker,
            "fair_prob": round(fair_prob, 4) if fair_prob is not None else None,
            "model_prob": round(model_prob, 4) if model_prob is not None else None,
            "edge_pp": edge_pp,
        }
    out = {
        "selections": selections,
        "bookmaker_count": len({bm for books in by_selection.values() for bm, _ in books}),
        "overround_pct": round((overround - 1) * 100, 2),
    }
    if kalshi_block:
        # Book-vs-Kalshi disagreement per side (Kalshi normalized prob minus
        # book fair prob, in pp). Positive = Kalshi likes the side more than
        # the books do. Only computable where both sources priced the side.
        disagreement = {}
        for sel, kprob in (kalshi_block.get("prob") or {}).items():
            fair = (selections.get(sel) or {}).get("fair_prob")
            if kprob is not None and fair is not None:
                disagreement[sel] = round((kprob - fair) * 100, 2)
        if disagreement:
            kalshi_block["vs_book_pp"] = disagreement
        out["kalshi"] = kalshi_block
    return out


def _summarize_kalshi(
    pred: Prediction | None,
    kalshi: dict[str, "OddsSnapshot"] | None,
) -> dict | None:
    """
    Serialize the latest Kalshi capture per side.

    Raw yes-probs come from two SEPARATE Kalshi markets (one per team), each a
    bid/ask midpoint — the pair rarely sums to exactly 1. When both sides are
    present we also emit a sum-normalized pair ("prob") so comparisons against
    the de-vigged book consensus are apples-to-apples; edges use the normalized
    number. With only one side priced, "prob" carries the raw value unchanged
    and "normalized" is false so downstream knows not to trust the complement.
    """
    if not kalshi:
        return None
    raw = {sel: round(snap.devig_prob, 4) for sel, snap in kalshi.items()
           if snap.devig_prob is not None}
    if not raw:
        return None
    total = sum(raw.values())
    # Full outcome set: 3 legs when a DRAW market exists (soccer 1X2),
    # else 2 (MLB moneyline). Normalizing a PARTIAL set would silently
    # inflate the present legs, so partial sets ship raw + normalized=False.
    expected = 3 if "DRAW" in kalshi else 2
    two_sided = len(raw) >= expected and total > 0
    prob = ({sel: round(v / total, 4) for sel, v in raw.items()}
            if two_sided else dict(raw))
    model_edge = {}
    if pred:
        model_by_sel = {"HOME": pred.home_win_prob, "AWAY": pred.away_win_prob,
                        "DRAW": getattr(pred, "draw_prob", None)}
        for sel, kprob in prob.items():
            mp = model_by_sel.get(sel)
            if mp is not None and kprob is not None:
                model_edge[sel] = round((mp - kprob) * 100, 2)
    captured = max(
        (snap.captured_at for snap in kalshi.values() if snap.captured_at),
        default=None,
    )
    return {
        "raw_yes_prob": raw,
        "raw_sum": round(total, 4),
        "prob": prob,
        "normalized": two_sided,
        "model_edge_pp": model_edge or None,
        "captured_at": captured.isoformat() if captured else None,
    }


# ----------------------------------------------------------------------
# CSV serialization (headline columns only, no nested structure)
# ----------------------------------------------------------------------

def _to_csv(rows: list[dict], sport: Sport) -> str:
    """Flatten headline columns into CSV. Loses nested data — use JSON for full."""
    is_baseball = sport == Sport.MLB
    buf = StringIO()

    columns = [
        "match_id", "utc_date", "competition", "home_team", "away_team",
        "status", "actual_home_score", "actual_away_score",
        "top_pick", "top_pick_prob",
        "tier", "actionable", "stronger_expression",
        "bullpen_swing_flag", "max_bullpen_swing",
        "p_home", "p_draw", "p_away",
        "expected_home", "expected_away",
        "to_advance_home_prob", "to_advance_away_prob",
        "best_home_price", "best_home_book",
        "best_away_price", "best_away_book",
        "edge_home_pp", "edge_away_pp",
        "log_loss", "top_pick_hit", "clv_pp",
        "home_last_5", "away_last_5",
    ]
    if is_baseball:
        columns.extend([
            "home_pitcher_name", "home_pitcher_era",
            "away_pitcher_name", "away_pitcher_era",
        ])
    else:
        columns.extend(["home_injuries", "away_injuries"])

    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()

    for row in rows:
        flat = {
            "match_id": row["match_id"],
            "utc_date": row["utc_date"],
            "competition": row["competition"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "status": row["status"],
            "actual_home_score": row["actual_home_score"],
            "actual_away_score": row["actual_away_score"],
        }
        pred = row.get("prediction")
        if pred:
            flat["top_pick"] = pred["top_pick"]
            flat["top_pick_prob"] = pred["top_pick_prob"]
            flat["tier"] = pred.get("tier")
            flat["actionable"] = pred.get("actionable")
            flat["stronger_expression"] = pred.get("stronger_expression")
            flat["bullpen_swing_flag"] = pred.get("bullpen_swing_flag")
            flat["max_bullpen_swing"] = pred.get("max_bullpen_swing")
            probs = pred["probabilities"]
            flat["p_home"] = probs["home_win"]
            flat["p_draw"] = probs["draw"]
            flat["p_away"] = probs["away_win"]
            flat["expected_home"] = pred["expected_home"]
            flat["expected_away"] = pred["expected_away"]
            flat["to_advance_home_prob"] = pred.get("to_advance_home_prob")
            flat["to_advance_away_prob"] = pred.get("to_advance_away_prob")

        mkt = row.get("market") or {}
        sels = mkt.get("selections", {})
        if "HOME" in sels:
            flat["best_home_price"] = sels["HOME"]["best_price"]
            flat["best_home_book"] = sels["HOME"]["best_bookmaker"]
            flat["edge_home_pp"] = sels["HOME"]["edge_pp"]
        if "AWAY" in sels:
            flat["best_away_price"] = sels["AWAY"]["best_price"]
            flat["best_away_book"] = sels["AWAY"]["best_bookmaker"]
            flat["edge_away_pp"] = sels["AWAY"]["edge_pp"]

        outcome = row.get("outcome")
        if outcome:
            flat["log_loss"] = outcome["log_loss"]
            flat["top_pick_hit"] = outcome["top_pick_hit"]
            flat["clv_pp"] = outcome["clv_pp"]

        if row.get("home_form"):
            flat["home_last_5"] = row["home_form"]["last_5"]
        if row.get("away_form"):
            flat["away_last_5"] = row["away_form"]["last_5"]

        if is_baseball:
            pitchers = row.get("pitchers") or {}
            hp = pitchers.get("home")
            ap = pitchers.get("away")
            if hp:
                flat["home_pitcher_name"] = hp.get("name")
                flat["home_pitcher_era"] = hp.get("era")
            if ap:
                flat["away_pitcher_name"] = ap.get("name")
                flat["away_pitcher_era"] = ap.get("era")
        else:
            inj = row.get("injuries") or {}
            flat["home_injuries"] = inj.get("home_count")
            flat["away_injuries"] = inj.get("away_count")

        writer.writerow(flat)

    return buf.getvalue()


def _json_safe(o):
    """Default serializer for JSON for types that aren't natively JSON."""
    if isinstance(o, datetime):
        return o.isoformat()
    if hasattr(o, "value"):  # Enum
        return o.value
    return str(o)


# ----------------------------------------------------------------------
# Results export — pairs each graded prediction with its actual outcome,
# for the external prediction model to consume in the morning run.
# ----------------------------------------------------------------------

def export_results(
    *,
    sport: Sport,
    start_date: datetime,
    end_date: datetime,
    competition_code: str | None = None,
    output_format: str = "json",
) -> str:
    """
    Export GRADED games (prediction + actual outcome) in a date range. Unlike
    export_predictions (forward-looking, scheduled games), this is backward-
    looking: what did we predict, and what happened. Only includes games with a
    written outcome. Keyed by match so the consumer can join to the prediction
    file it already has.
    """
    from src.db.schema import Prediction, PredictionOutcome, Match, Team
    from sqlalchemy import select
    from src.db.database import session_scope

    rows = []
    with session_scope() as s:
        q = (
            select(Prediction, PredictionOutcome, Match)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == sport,
                   Match.utc_date >= start_date,
                   Match.utc_date < end_date,
                   PredictionOutcome.actual_home_score.isnot(None))
        )
        if competition_code:
            from src.db.schema import Competition
            comp = s.execute(
                select(Competition).where(Competition.code == competition_code)
            ).scalar_one_or_none()
            if comp:
                q = q.where(Match.competition_id == comp.id)

        for pred, oc, m in s.execute(q).all():
            home = m.home_team.name if m.home_team else None
            away = m.away_team.name if m.away_team else None
            # S17 (2026-09-01): the label MUST consider the draw. Bournemouth-
            # Everton (MW2) had draw 0.3389 > home 0.3383; grading was correct
            # (evaluate includes draw) but this label said home_win. Include
            # draw_prob and assert label/grade consistency — loudly.
            probs = {"home_win": pred.home_win_prob,
                     "draw": getattr(pred, "draw_prob", None),
                     "away_win": pred.away_win_prob}
            nn = {k: v for k, v in probs.items() if v is not None}
            top_side = max(nn, key=nn.get) if nn else None
            _res_to_pick = {"H": "home_win", "D": "draw", "A": "away_win"}
            if (top_side and oc.actual_result is not None
                    and oc.top_pick_hit is not None):
                _expected_hit = (_res_to_pick.get(oc.actual_result.value)
                                 == top_side)
                if _expected_hit != bool(oc.top_pick_hit):
                    log.error(
                        "S17 ASSERTION: match %s label %s vs graded hit=%s "
                        "(actual %s) — label/grade inconsistency",
                        m.id, top_side, oc.top_pick_hit,
                        oc.actual_result.value)
            proj_total = None
            if pred.expected_home_score is not None and pred.expected_away_score is not None:
                proj_total = round(pred.expected_home_score + pred.expected_away_score, 2)
            actual_total = None
            if oc.actual_home_score is not None and oc.actual_away_score is not None:
                actual_total = oc.actual_home_score + oc.actual_away_score
            rows.append({
                "match_id": m.id,
                "date": m.utc_date.isoformat() if m.utc_date else None,
                "away_team": away, "home_team": home,
                # what we predicted
                "predicted": {
                    "top_pick": top_side,
                    "top_pick_prob": round(nn[top_side], 4) if top_side else None,
                    "home_win_prob": pred.home_win_prob,
                    "draw_prob": getattr(pred, "draw_prob", None),
                    "away_win_prob": pred.away_win_prob,
                    "projected_total": proj_total,
                    "over_under_line": pred.over_under_line,
                    "over_prob": pred.over_prob,
                },
                # what happened
                "actual": {
                    "home_score": oc.actual_home_score,
                    "away_score": oc.actual_away_score,
                    "total_runs": actual_total,
                    "result": oc.actual_result.value if oc.actual_result else None,
                },
                # how the prediction graded
                "graded": {
                    "top_pick_hit": oc.top_pick_hit,
                    "total_correct": oc.total_correct,
                    "total_error": (round(actual_total - proj_total, 2)
                                    if (actual_total is not None and proj_total is not None) else None),
                    "log_loss": oc.log_loss,
                    "brier_score": oc.brier_score,
                    "clv": oc.clv,
                    "closing_price": oc.closing_price,
                },
            })

    rows.sort(key=lambda r: (r["date"] or "", r["match_id"]))
    payload = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "sport": sport.value,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "competition_code": competition_code,
        "count": len(rows),
        "totals_pulse": _compute_totals_pulse(rows),
        "results": rows,
    }
    if output_format == "json":
        return json.dumps(payload, indent=2, default=_json_safe)
    raise ValueError(f"Unknown output_format: {output_format!r}")


def _compute_totals_pulse(rows, blowup_threshold: float = 6.0):
    """
    Robust daily totals diagnostics, serialized so the audit layer sees them (not
    just the console). Separates central tendency (mean/median), robustness
    (trimmed mean), and outliers (blowup count, non-blowup mean/MAE). A point
    projection can't predict blowups, so a couple of them distort the raw mean —
    these fields expose that immediately. Diagnostic only; not a calibration verdict.
    """
    errs = sorted(r["graded"]["total_error"] for r in rows
                  if r["graded"].get("total_error") is not None)
    m = len(errs)
    if m == 0:
        return None
    mean_e = sum(errs) / m
    median_e = errs[m // 2] if m % 2 else (errs[m // 2 - 1] + errs[m // 2]) / 2
    # trimmed mean: floor k at 1 once n>=6 so the trim actually bites on small slates
    k = max(1, int(m * 0.10)) if m >= 6 else 0
    trimmed = errs[k:m - k] if (m - 2 * k) > 0 else errs
    trimmed_mean = sum(trimmed) / len(trimmed)
    typical = [e for e in errs if abs(e) <= blowup_threshold]
    blowups = m - len(typical)
    non_blowup_mean = (sum(typical) / len(typical)) if typical else None
    non_blowup_mae = (sum(abs(e) for e in typical) / len(typical)) if typical else None
    return {
        "games": m,
        "mean_error": round(mean_e, 3),
        "median_error": round(median_e, 3),
        "trimmed_mean_error": round(trimmed_mean, 3),
        "blowup_count": blowups,
        "blowup_threshold": blowup_threshold,
        "non_blowup_mean_error": round(non_blowup_mean, 3) if non_blowup_mean is not None else None,
        "non_blowup_mae": round(non_blowup_mae, 3) if non_blowup_mae is not None else None,
    }


def export_fixtures(
    competition_code: str,
    start: str | None = None,
    end: str | None = None,
    out_dir: str = "exports",
) -> str:
    """
    MARKET-ONLY fixtures export (U-request 2026-09-08): matches, results
    where finished, book consensus where odds exist. Reads matches + odds
    tables ONLY — physically incapable of carrying model output. Built for
    competitions behind the cup acceptance gate (EFL, CL): gives the
    consumer fixture awareness and market context with zero prediction
    fields, top-level flag says so explicitly.
    """
    import json as _json
    import os as _os
    from datetime import datetime as _dt, timedelta as _td

    from sqlalchemy import select as _select

    from src.db.database import session_scope as _scope
    from src.db.schema import Competition as _Comp, Match as _Match, Odds as _Odds
    from src.walters.value import MarketSnapshot as _Snap

    with _scope() as s:
        comp = s.execute(_select(_Comp).where(
            _Comp.code == competition_code)).scalars().first()
        if comp is None:
            raise ValueError(f"unknown competition {competition_code}")
        q = _select(_Match).where(_Match.competition_id == comp.id)
        lo = _dt.fromisoformat(start) if start else _dt.utcnow() - _td(days=2)
        hi = (_dt.fromisoformat(end) + _td(days=1)) if end else _dt.utcnow() + _td(days=7)
        q = q.where(_Match.utc_date >= lo, _Match.utc_date < hi).order_by(_Match.utc_date)
        rows = []
        for m in s.execute(q).scalars():
            odds_rows = list(s.execute(_select(_Odds).where(
                _Odds.match_id == m.id, _Odds.market == "1X2")).scalars())
            market = None
            if odds_rows:
                by_sel: dict[str, list[tuple[str, float]]] = {}
                cap = None
                for o in odds_rows:
                    by_sel.setdefault(o.selection, []).append(
                        (o.bookmaker, o.price_decimal))
                    if cap is None or o.captured_at > cap:
                        cap = o.captured_at
                snap = _Snap(market="1X2", by_selection=by_sel)
                implied = snap.average_implied()
                over = sum(implied.values()) or 1.0
                market = {
                    "bookmaker_count": len({o.bookmaker for o in odds_rows}),
                    "captured_at": cap.isoformat() if cap else None,
                    "fair_prob": {k: round(v / over, 4)
                                  for k, v in implied.items()},
                }
            rows.append({
                "match_id": m.id,
                "utc_date": m.utc_date.isoformat(),
                "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                "stage": m.stage,
                "matchday": m.matchday,
                "home_team": m.home_team.name if m.home_team else None,
                "away_team": m.away_team.name if m.away_team else None,
                "home_score": m.home_score,
                "away_score": m.away_score,
                "market": market,
            })
    _os.makedirs(out_dir, exist_ok=True)
    label = (f"{start}_to_{end}" if start and end
             else _dt.utcnow().strftime("%Y-%m-%d"))
    path = _os.path.join(out_dir, f"fixtures_{competition_code}_{label}.json")
    payload = {
        "exported_at": _dt.utcnow().isoformat() + "Z",
        "competition_code": competition_code,
        "contains_predictions": False,
        "note": ("Market-only fixtures file: schedule, results, book "
                 "consensus. NO model output — this competition is behind "
                 "the cup acceptance gate."),
        "count": len(rows),
        "fixtures": rows,
    }
    with open(path, "w") as f:
        _json.dump(payload, f, indent=2)
    return path


def results_tally(days: int = 30, out_path: str = "RESULTS.md") -> str:
    """Rolling results document (2026-09-15, user request): last-N-day
    sides/log-loss/CLV per sport, regenerated on demand. Auto-generated —
    do not hand-edit."""
    import math
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import (Match, MatchStatus, Prediction,
                               PredictionOutcome, Sport)

    lines = [f"# Results — rolling {days} days",
             f"\n_Auto-generated by `python cli.py results-tally` at "
             f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}Z. "
             f"Record is variance, not signal._\n"]
    with session_scope() as s:
        cutoff = datetime.utcnow() - timedelta(days=days)
        for sport, label in ((Sport.MLB, "MLB"), (Sport.SOCCER, "Soccer (PL)")):
            # Outcomes link via prediction_id -> Prediction -> Match
            # (2026-09-15 hotfix: first ship guessed match_id; read the
            # schema, then write the join).
            q = (select(PredictionOutcome, Match)
                 .join(Prediction,
                       Prediction.id == PredictionOutcome.prediction_id)
                 .join(Match, Match.id == Prediction.match_id)
                 .where(Match.sport == sport, Match.utc_date >= cutoff))
            rows = s.execute(q).all()
            n = len(rows)
            if not n:
                lines.append(f"## {label}\n\nNo graded games in window.\n")
                continue
            hits = sum(1 for oc, m in rows if oc.top_pick_hit)
            lls = [oc.log_loss for oc, m in rows if oc.log_loss is not None]
            clvs = [oc.clv for oc, m in rows
                    if getattr(oc, "clv", None) is not None]
            lines.append(
                f"## {label}\n\n- Sides: **{hits}/{n}** ({hits/n:.1%})\n"
                f"- Mean log-loss: {sum(lls)/len(lls):.4f} (n={len(lls)})\n"
                f"- Mean CLV: {sum(clvs)/len(clvs)*100:+.2f}pp (n={len(clvs)} priced)\n")
        # NFL from the grade join (no outcome rows during rehearsal)
        try:
            from src.walters.nfl_predict import grade_nfl
            r = grade_nfl(days_back=days)
            if r.get("ok"):
                lines.append(
                    f"## NFL (rehearsal)\n\n- Sides: **{r['hits']}/{r['games']}**"
                    f" ({r['hits']/r['games']:.1%})\n"
                    f"- Mean log-loss: {r['logloss']:.4f}\n"
                    f"- Mean pick-vs-close: {r['mean_clv_pp']:+.2f}pp\n")
        except Exception:
            lines.append("## NFL (rehearsal)\n\nGrade unavailable.\n")
    lines.append("\nDeep detail: `BACKLOG.md`. Change history: `CHANGELOG.md`.\n")
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    return out_path
