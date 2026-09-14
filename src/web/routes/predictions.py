"""
Model predictions and performance dashboard.

Filtered by the active sport context (set via the nav pill). Each sport gets
its own model version table, calibration plot, and post-mortem feed — mixing
soccer and baseball stats together would conflate two very different model
families and produce meaningless aggregate numbers.

Three sections per sport:
  - Top stats per model version: log loss, Brier, RPS, top-pick accuracy
  - Calibration data: when the model said X%, did it happen X% of the time?
  - Recent prediction outcomes feed (the post-mortems)
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.db.database import session_scope
from src.db.schema import Match, ModelVersion, Prediction, PredictionOutcome, Sport
from src.web.dependencies import resolve_sport

router = APIRouter(prefix="/predictions")


def _build_rich_post_mortem(
    outcome,
    pred,
    match,
    factor_breakdown: dict,
) -> dict:
    """
    Build a structured post-mortem comparing model expectations to actuals.

    Returns a dict with three sections:
      - expected: what the model thought
      - actual: what happened
      - analysis: which factors dominated and whether they validated, plus
                  any "should-watch" patterns

    Surfaces signal beyond the templated headline note. The aim is for the
    user to be able to read this and understand WHY a prediction was right
    or wrong — not just whether it was.
    """
    is_baseball = match.sport == Sport.MLB

    # Probabilities and labels
    p_home = (pred.home_win_prob or 0)
    p_draw = pred.draw_prob if pred.draw_prob is not None else None
    p_away = (pred.away_win_prob or 0)

    # Predicted outcome (top pick)
    if p_draw is not None:
        candidates = [("H", p_home), ("D", p_draw), ("A", p_away)]
    else:
        candidates = [("H", p_home), ("A", p_away)]
    top_pick, top_pick_p = max(candidates, key=lambda c: c[1])

    # Actual outcome from scores
    actual_letter = None
    if match.home_score is not None and match.away_score is not None:
        if match.home_score > match.away_score:
            actual_letter = "H"
        elif match.away_score > match.home_score:
            actual_letter = "A"
        else:
            actual_letter = "D"

    home_name = match.home_team.name if match.home_team else "Home"
    away_name = match.away_team.name if match.away_team else "Away"
    outcome_label = {
        "H": f"{home_name} win",
        "D": "Draw",
        "A": f"{away_name} win",
    }

    # ----- Expected section
    expected_lines: list[str] = []
    expected_lines.append(
        f"Model favored {outcome_label[top_pick]} at {top_pick_p * 100:.0f}%."
    )
    if pred.expected_home_score is not None and pred.expected_away_score is not None:
        expected_lines.append(
            f"Expected score around {pred.expected_home_score:.1f}–{pred.expected_away_score:.1f}."
        )
        # Was a low-scoring or high-scoring game expected?
        total_xg = pred.expected_home_score + pred.expected_away_score
        if not is_baseball:
            if total_xg < 2.0:
                expected_lines.append(f"A low-scoring affair was expected (xG total {total_xg:.1f}).")
            elif total_xg > 3.0:
                expected_lines.append(f"A high-scoring affair was expected (xG total {total_xg:.1f}).")

    # Factor highlights for soccer
    if not is_baseball:
        elo_diff = (factor_breakdown.get("home_elo") or 0) - (factor_breakdown.get("away_elo") or 0)
        if abs(elo_diff) >= 100:
            stronger = home_name if elo_diff > 0 else away_name
            expected_lines.append(
                f"Elo gap favored {stronger} ({abs(elo_diff):.0f} points)."
            )
        # Lineup state
        lk = factor_breakdown.get("lineup_kind")
        if lk == "confirmed":
            expected_lines.append("Used confirmed lineups.")
        elif lk == "projected":
            expected_lines.append("Used projected lineups — actual XI may have differed.")
        elif lk is None:
            expected_lines.append("No lineup data available at prediction time.")
        # XI strength deltas
        for side, name in (("home", home_name), ("away", away_name)):
            atk = factor_breakdown.get(f"{side}_xi_attack")
            base = factor_breakdown.get(f"{side}_baseline_attack")
            if atk is not None and base is not None and abs(atk - base) >= 5:
                direction = "weaker" if atk < base else "stronger"
                expected_lines.append(
                    f"{name}'s XI was rated {direction} than their season-average "
                    f"({atk:.0f} vs {base:.0f})."
                )
    else:
        # Baseball: pitcher + run profile
        hp = factor_breakdown.get("home_pitcher")
        ap = factor_breakdown.get("away_pitcher")
        hp_era = factor_breakdown.get("home_pitcher_era")
        ap_era = factor_breakdown.get("away_pitcher_era")
        h_known = factor_breakdown.get("home_starter_known", True)
        a_known = factor_breakdown.get("away_starter_known", True)

        if hp or ap:
            hp_str = hp or "—"
            ap_str = ap or "—"
            if hp_era is not None:
                hp_str = f"{hp_str} ({hp_era:.2f} blended ERA)"
            if ap_era is not None:
                ap_str = f"{ap_str} ({ap_era:.2f} blended ERA)"
            expected_lines.append(
                f"Pitchers: {hp_str} (H) vs {ap_str} (A). "
                f"ERA shown is starter+bullpen blended (61/39)."
            )
            if not h_known or not a_known:
                if not h_known and not a_known:
                    who = "Both starters"
                elif not h_known:
                    who = f"{home_name}'s starter"
                else:
                    who = f"{away_name}'s starter"
                expected_lines.append(
                    f"{who} unconfirmed — confidence reduced toward 50/50."
                )

    # ----- Actual section
    actual_lines: list[str] = []
    if actual_letter is not None and match.home_score is not None:
        score_label = "Goals" if not is_baseball else "Runs"
        actual_lines.append(
            f"Final: {home_name} {match.home_score}–{match.away_score} {away_name} "
            f"({outcome_label[actual_letter]})."
        )
        # Compare actual goals to expected
        if pred.expected_home_score is not None and pred.expected_away_score is not None:
            actual_total = match.home_score + match.away_score
            xg_total = pred.expected_home_score + pred.expected_away_score
            diff = actual_total - xg_total
            if abs(diff) >= 1.5:
                direction = "higher than expected" if diff > 0 else "lower than expected"
                actual_lines.append(
                    f"{score_label.lower()} total ({actual_total}) was {direction} "
                    f"(model expected ~{xg_total:.1f})."
                )

    # ----- Analysis section: where did we win/lose
    analysis_lines: list[str] = []
    if actual_letter is None:
        analysis_lines.append("Match outcome wasn't recorded properly.")
    else:
        actual_p = {"H": p_home, "D": p_draw or 0, "A": p_away}[actual_letter]
        # Top pick analysis
        if outcome.top_pick_hit:
            if actual_p >= 0.6:
                analysis_lines.append(
                    f"Strong call — model's top pick ({outcome_label[top_pick]} at "
                    f"{top_pick_p * 100:.0f}%) landed."
                )
            elif actual_p >= 0.4:
                analysis_lines.append(
                    f"Right call but a coin-flip ({actual_p * 100:.0f}%). "
                    f"Don't read too much into close ones."
                )
            else:
                analysis_lines.append(
                    f"Got it right on a low-confidence pick ({actual_p * 100:.0f}%). "
                    f"Likely a bit of variance going our way."
                )
        else:
            # We lost — categorize the miss
            confidence_gap = top_pick_p - actual_p
            if confidence_gap >= 0.30:
                analysis_lines.append(
                    f"Big miss — model gave {outcome_label[top_pick]} {top_pick_p * 100:.0f}% "
                    f"but actual was {outcome_label[actual_letter]} at {actual_p * 100:.0f}%."
                )
            elif confidence_gap >= 0.10:
                analysis_lines.append(
                    f"Wrong top pick but tight — {outcome_label[top_pick]} at {top_pick_p * 100:.0f}% "
                    f"vs {outcome_label[actual_letter]} at {actual_p * 100:.0f}%. Variance, mostly."
                )
            else:
                analysis_lines.append(
                    f"Coin-flip game where the model had a slight lean the wrong way "
                    f"({top_pick_p * 100:.0f}% vs {actual_p * 100:.0f}%)."
                )

        # Draw-specific learning
        if actual_letter == "D" and p_draw is not None and p_draw < 0.20:
            analysis_lines.append(
                f"Draw probability was only {p_draw * 100:.0f}% — model tends to under-weight draws "
                f"in evenly-matched games. Watch this pattern."
            )

        # Log-loss interpretation
        if outcome.log_loss is not None:
            if outcome.log_loss < 0.7:
                analysis_lines.append(
                    f"Log-loss {outcome.log_loss:.2f} — better than a 50/50 baseline (~0.69)."
                )
            elif outcome.log_loss > 1.5:
                analysis_lines.append(
                    f"Log-loss {outcome.log_loss:.2f} — significantly worse than baseline. "
                    f"Model was confident in the wrong direction."
                )

        # Phase 11: Closing-line value commentary. Positive CLV = the model
        # was on the value side of the close, even when the outcome itself
        # didn't land. Negative CLV = the market disagreed with us and was
        # right to do so. CLV is independent of win/loss — it's about whether
        # the model's *probability* was a fair price.
        if getattr(outcome, "clv", None) is not None:
            clv_pp = outcome.clv * 100  # convert delta to percentage points
            if outcome.closing_price and outcome.closing_bookmaker:
                price_str = f" (close {outcome.closing_bookmaker} @ {outcome.closing_price:.2f})"
            else:
                price_str = ""
            if clv_pp >= 3.0:
                analysis_lines.append(
                    f"Model was on the value side of close: +{clv_pp:.1f}pp vs market{price_str}."
                )
            elif clv_pp <= -3.0:
                analysis_lines.append(
                    f"Model lagged the close by {abs(clv_pp):.1f}pp{price_str} — "
                    f"market priced this outcome more conservatively than the model."
                )
            # |CLV| < 3pp = noise, don't surface

    return {
        "expected": expected_lines,
        "actual": actual_lines,
        "analysis": analysis_lines,
    }


@router.get("", response_class=HTMLResponse)
async def predictions_dashboard(request: Request):
    templates = request.state.templates
    active_sport = resolve_sport(request)
    sport_enum = Sport.SOCCER if active_sport == "soccer" else Sport.MLB

    with session_scope() as s:
        # Model versions for this sport only, newest first
        model_versions = list(s.execute(
            select(ModelVersion)
            .where(ModelVersion.sport == sport_enum)
            .order_by(ModelVersion.created_at.desc())
        ).scalars())

        # Per-model aggregate stats — joined to sport via the underlying Match
        model_stats: list[dict] = []
        for mv in model_versions:
            rows = list(s.execute(
                select(PredictionOutcome)
                .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
                .join(Match, Match.id == Prediction.match_id)
                .where(
                    Prediction.model_version == mv.version,
                    Match.sport == sport_enum,
                )
            ).scalars())
            if not rows:
                continue
            n = len(rows)
            ll_vals = [r.log_loss for r in rows if r.log_loss is not None]
            br_vals = [r.brier_score for r in rows if r.brier_score is not None]
            avg_ll = sum(ll_vals) / len(ll_vals) if ll_vals else 0
            avg_brier = sum(br_vals) / len(br_vals) if br_vals else 0
            top_pick_acc = sum(1 for r in rows if r.top_pick_hit) / n
            model_stats.append({
                "version": mv.version,
                "status": mv.status,
                "n": n,
                "log_loss": round(avg_ll, 4),
                "brier_score": round(avg_brier, 4),
                "top_pick_accuracy": round(top_pick_acc, 3),
                "created_at": mv.created_at,
            })

        production_version = next(
            (mv.version for mv in model_versions if mv.status == "production"), None
        )

        # Calibration bins for the production model in this sport
        calibration_points: list[dict] = []
        if production_version:
            buckets: dict[int, list[int]] = defaultdict(list)
            preds_q = (
                select(Prediction, PredictionOutcome, Match)
                .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
                .join(Match, Match.id == Prediction.match_id)
                .where(
                    Prediction.model_version == production_version,
                    Match.sport == sport_enum,
                )
            )
            # Sport-specific probability columns:
            #   Soccer: H/D/A
            #   Baseball: H/A only (no draws)
            if sport_enum == Sport.SOCCER:
                prob_cols = [
                    ("home_win_prob", "H"),
                    ("draw_prob", "D"),
                    ("away_win_prob", "A"),
                ]
            else:
                prob_cols = [
                    ("home_win_prob", "H"),
                    ("away_win_prob", "A"),
                ]

            for pred, outcome, match in s.execute(preds_q).all():
                # Determine actual letter — outcome.actual_result is set for
                # soccer but may be None for baseball (no Result.HOME/AWAY in
                # eval, just inferred from scores).
                if outcome.actual_result is not None:
                    actual_letter = outcome.actual_result.value
                elif outcome.actual_home_score is not None and outcome.actual_away_score is not None:
                    actual_letter = "H" if outcome.actual_home_score > outcome.actual_away_score else "A"
                else:
                    continue

                for prob_attr, letter in prob_cols:
                    p = getattr(pred, prob_attr) or 0.0
                    bucket = min(9, int(p * 10))
                    buckets[bucket].append(1 if actual_letter == letter else 0)

            for bucket in range(10):
                vals = buckets.get(bucket, [])
                if not vals:
                    continue
                avg_predicted = (bucket + 0.5) / 10
                actual_rate = sum(vals) / len(vals)
                calibration_points.append({
                    "predicted_pct": round(avg_predicted * 100, 1),
                    "actual_pct": round(actual_rate * 100, 1),
                    "n": len(vals),
                })

        # Recent post-mortems for this sport. Dedupe by match — when a match
        # has multiple Prediction rows (from different model versions, or
        # repeated `predict` runs), show only the most recent evaluation.
        # Over-fetch then dedupe in Python; cheaper than a window-function
        # query and SQLite doesn't support DISTINCT ON.
        feed_q = (
            select(PredictionOutcome, Prediction, Match)
            .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
            .join(Match, Match.id == Prediction.match_id)
            .options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
                selectinload(Match.competition),
            )
            .where(Match.sport == sport_enum)
            .order_by(PredictionOutcome.evaluated_at.desc())
            .limit(200)  # over-fetch for dedupe
        )
        seen_match_ids: set[int] = set()
        feed: list[dict] = []
        for outcome, pred, match in s.execute(feed_q).all():
            if match.id in seen_match_ids:
                continue
            seen_match_ids.add(match.id)
            # Build a richer post-mortem from the factor_breakdown and actuals.
            fb = pred.factor_breakdown or {}
            rich_notes = _build_rich_post_mortem(
                outcome=outcome,
                pred=pred,
                match=match,
                factor_breakdown=fb,
            )
            feed.append({
                "match_id": match.id,
                "date": match.utc_date,
                "home": match.home_team.name if match.home_team else "?",
                "away": match.away_team.name if match.away_team else "?",
                "competition": match.competition.code if match.competition else "",
                "home_score": match.home_score,
                "away_score": match.away_score,
                "p_home_pct": round((pred.home_win_prob or 0) * 100, 1),
                "p_draw_pct": round((pred.draw_prob or 0) * 100, 1) if pred.draw_prob is not None else None,
                "p_away_pct": round((pred.away_win_prob or 0) * 100, 1),
                "expected_home_score": (
                    round(pred.expected_home_score, 2)
                    if pred.expected_home_score is not None else None
                ),
                "expected_away_score": (
                    round(pred.expected_away_score, 2)
                    if pred.expected_away_score is not None else None
                ),
                "log_loss": round(outcome.log_loss, 3) if outcome.log_loss is not None else None,
                "top_pick_hit": outcome.top_pick_hit,
                "headline": outcome.notes or "",
                "rich_notes": rich_notes,
                "model_version": pred.model_version,
                # Phase 11: CLV is independent of win/loss — it's about
                # whether the model's probability matched the market close.
                "clv": getattr(outcome, "clv", None),
                "clv_pct": round(outcome.clv * 100, 1) if getattr(outcome, "clv", None) is not None else None,
                "closing_price": getattr(outcome, "closing_price", None),
                "closing_bookmaker": getattr(outcome, "closing_bookmaker", None),
            })
            if len(feed) >= 30:
                break

        # Counts for this sport's header card
        total_predictions = s.execute(
            select(func.count()).select_from(Prediction)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == sport_enum)
        ).scalar_one()
        total_evaluated = s.execute(
            select(func.count()).select_from(PredictionOutcome)
            .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == sport_enum)
        ).scalar_one()

    return templates.TemplateResponse(
        request,
        "predictions.html",
        {
            "model_stats": model_stats,
            "calibration_points": calibration_points,
            "production_version": production_version,
            "feed": feed,
            "total_predictions": total_predictions,
            "total_evaluated": total_evaluated,
            "active_sport": active_sport,
            "is_baseball": sport_enum == Sport.MLB,
        },
    )
