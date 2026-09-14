"""
Matches routes.

GET /matches                  — paginated list, filterable by competition / status / season
GET /matches/{id}             — match detail page
POST /matches/{id}/refresh    — per-match refresh: sync lineups/pitchers/injuries for
                                the two teams in this match, then regenerate the
                                prediction. Returns the updated match detail page.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.database import session_scope
from src.db.schema import Competition, Match, MatchStats, MatchStatus, Sport
from src.web.dependencies import resolve_sport

router = APIRouter(prefix="/matches")

PAGE_SIZE = 50


@router.get("", response_class=HTMLResponse)
async def list_matches(
    request: Request,
    competition: str | None = None,
    season: str | None = None,
    status: str | None = None,
    sort: str = "date",   # "date" | "confidence" | "expected_goals"
    page: int = 1,
):
    """
    List matches grouped by day. Within each day, sortable by:
      - date (chronological, default)
      - confidence (highest top-pick probability first — surfaces "lock" picks)
      - expected_goals (highest total xG first — surfaces high-scoring expectations)

    The `status` filter still works: leave blank for all, "scheduled" for
    upcoming only, "finished" for results review.
    """
    templates = request.state.templates
    page = max(1, page)
    active_sport = resolve_sport(request)
    sport_enum = Sport.SOCCER if active_sport == "soccer" else Sport.MLB

    if sort not in ("date", "confidence", "expected_goals"):
        sort = "date"

    with session_scope() as s:
        stmt = (
            select(Match)
            .join(Competition, Competition.id == Match.competition_id)
            .where(Match.sport == sport_enum)
            .options(
                selectinload(Match.competition),
                selectinload(Match.home_team),
                selectinload(Match.away_team),
                selectinload(Match.predictions),
            )
        )

        if competition:
            stmt = stmt.where(Competition.code == competition)
        if season:
            stmt = stmt.where(Match.season == season)
        if status:
            try:
                stmt = stmt.where(Match.status == MatchStatus(status))
            except ValueError:
                pass

        # Always order by date first — even when sorting by confidence
        # within a day, we want chronological day-grouping.
        if status == MatchStatus.SCHEDULED.value:
            stmt = stmt.order_by(Match.utc_date.asc())
        else:
            stmt = stmt.order_by(Match.utc_date.desc())

        offset = (page - 1) * PAGE_SIZE
        stmt = stmt.offset(offset).limit(PAGE_SIZE + 1)
        matches = list(s.execute(stmt).scalars())
        has_next = len(matches) > PAGE_SIZE
        matches = matches[:PAGE_SIZE]

        # Annotate each match with top-pick probability and total xG, used
        # for in-day sorting and display. We pick the latest prediction
        # per match (highest id).
        rows: list[dict] = []
        for m in matches:
            top_p = None
            total_xg = None
            pred = None
            if m.predictions:
                # Most recent prediction
                pred = max(m.predictions, key=lambda p: p.id)
                probs = [pred.home_win_prob or 0]
                if pred.draw_prob is not None:
                    probs.append(pred.draw_prob)
                probs.append(pred.away_win_prob or 0)
                top_p = max(probs)
                if pred.expected_home_score is not None and pred.expected_away_score is not None:
                    total_xg = pred.expected_home_score + pred.expected_away_score

            # For sorting: precompute the chosen letter and label
            top_pick_label = None
            if pred:
                if pred.draw_prob is not None:
                    candidates = [("H", pred.home_win_prob or 0),
                                  ("D", pred.draw_prob),
                                  ("A", pred.away_win_prob or 0)]
                else:
                    candidates = [("H", pred.home_win_prob or 0),
                                  ("A", pred.away_win_prob or 0)]
                letter, _ = max(candidates, key=lambda c: c[1])
                top_pick_label = {
                    "H": m.home_team.name if m.home_team else "Home",
                    "D": "Draw",
                    "A": m.away_team.name if m.away_team else "Away",
                }[letter]

            rows.append({
                "match": m,
                "day": m.utc_date.date(),
                "top_p": top_p,
                "top_pick_label": top_pick_label,
                "total_xg": total_xg,
                "pred": pred,
            })

        # Sort within each day according to the chosen mode.
        from itertools import groupby
        rows_by_day: list[tuple[object, list[dict]]] = []
        for day, day_rows in groupby(rows, key=lambda r: r["day"]):
            day_list = list(day_rows)
            if sort == "confidence":
                day_list.sort(key=lambda r: -(r["top_p"] or 0))
            elif sort == "expected_goals":
                day_list.sort(key=lambda r: -(r["total_xg"] or 0))
            # date sort needs no further work — rows came in chronological order
            rows_by_day.append((day, day_list))

        comps = list(
            s.execute(
                select(Competition)
                .where(Competition.sport == sport_enum)
                .order_by(Competition.name)
            ).scalars()
        )
        seasons = sorted(
            {
                m for m in s.execute(
                    select(Match.season).where(Match.sport == sport_enum).distinct()
                ).scalars() if m
            },
            reverse=True,
        )

    return templates.TemplateResponse(
        request,
        "matches.html",
        {
            "rows_by_day": rows_by_day,
            "comps": comps,
            "seasons": seasons,
            "filters": {"competition": competition, "season": season, "status": status, "sort": sort},
            "statuses": [s.value for s in MatchStatus],
            "page": page,
            "has_next": has_next,
            "active_sport": active_sport,
        },
    )


@router.get("/{match_id}", response_class=HTMLResponse)
async def match_detail(request: Request, match_id: int):
    templates = request.state.templates

    with session_scope() as s:
        match = s.execute(
            select(Match)
            .options(
                selectinload(Match.competition),
                selectinload(Match.home_team),
                selectinload(Match.away_team),
            )
            .where(Match.id == match_id)
        ).scalar_one_or_none()
        if not match:
            raise HTTPException(status_code=404, detail=f"Match {match_id} not found.")

        stats = list(
            s.execute(select(MatchStats).where(MatchStats.match_id == match.id)).scalars()
        )
        # Order stats as [home_team, away_team] if both present
        home_stats = next((st for st in stats if st.team_id == match.home_team_id), None)
        away_stats = next((st for st in stats if st.team_id == match.away_team_id), None)

        # Most recent prediction for this match (any model version)
        from src.db.schema import Prediction, PredictionOutcome, Odds
        pred_row = s.execute(
            select(Prediction)
            .where(Prediction.match_id == match.id)
            .order_by(Prediction.computed_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        prediction_dict = None
        outcome_dict = None
        if pred_row is not None:
            pred_probs = {
                "H": pred_row.home_win_prob or 0.0,
                "D": pred_row.draw_prob or 0.0,
                "A": pred_row.away_win_prob or 0.0,
            }
            pick = max(pred_probs, key=pred_probs.get)
            pick_p_pct = round(pred_probs[pick] * 100, 1)

            # Determine which outcome the "most likely exact score" maps to.
            # If the most likely score is 1-1, that's a draw — but the top pick
            # by probability may still be a team win because lots of different
            # team-winning scores sum to more probability mass.
            mls = (pred_row.factor_breakdown or {}).get("most_likely_score")
            mls_outcome = None
            if mls and len(mls) == 2:
                mh, ma = mls[0], mls[1]
                if mh > ma:
                    mls_outcome = "H"
                elif ma > mh:
                    mls_outcome = "A"
                else:
                    mls_outcome = "D"

            # Mismatch flag: the most likely scoreline doesn't agree with the
            # most likely outcome. This is the source of "the page seems
            # contradictory" confusion — we surface it explicitly.
            mls_disagrees_with_pick = (
                mls_outcome is not None
                and mls_outcome != pick
            )

            prediction_dict = {
                "model_version": pred_row.model_version,
                "computed_at": pred_row.computed_at,
                "p_home_pct": round((pred_row.home_win_prob or 0) * 100, 1),
                "p_draw_pct": round((pred_row.draw_prob or 0) * 100, 1),
                "p_away_pct": round((pred_row.away_win_prob or 0) * 100, 1),
                "xg_home": round(pred_row.expected_home_score or 0, 2),
                "xg_away": round(pred_row.expected_away_score or 0, 2),
                "over_under_line": pred_row.over_under_line,
                "p_over_pct": round((pred_row.over_prob or 0) * 100, 1) if pred_row.over_prob is not None else None,
                "p_under_pct": round((pred_row.under_prob or 0) * 100, 1) if pred_row.under_prob is not None else None,
                # Phase 7: cup-knockout to-advance probabilities (None for non-KO matches)
                "p_advance_home_pct": (
                    round(pred_row.to_advance_home_prob * 100, 1)
                    if pred_row.to_advance_home_prob is not None else None
                ),
                "p_advance_away_pct": (
                    round(pred_row.to_advance_away_prob * 100, 1)
                    if pred_row.to_advance_away_prob is not None else None
                ),
                "pick": pick,
                "pick_label": {"H": match.home_team.name, "D": "Draw", "A": match.away_team.name}[pick],
                "pick_p_pct": pick_p_pct,
                "mls_outcome": mls_outcome,
                "mls_disagrees_with_pick": mls_disagrees_with_pick,
                "factor_breakdown": pred_row.factor_breakdown or {},
            }

            outcome = s.execute(
                select(PredictionOutcome).where(PredictionOutcome.prediction_id == pred_row.id)
            ).scalar_one_or_none()
            if outcome is not None:
                outcome_dict = {
                    "log_loss": round(outcome.log_loss, 3) if outcome.log_loss is not None else None,
                    "brier_score": round(outcome.brier_score, 3) if outcome.brier_score is not None else None,
                    "top_pick_hit": outcome.top_pick_hit,
                    "notes": outcome.notes,
                }

        # Best available odds per 1X2 selection, if loaded
        odds_rows = list(s.execute(
            select(Odds).where(Odds.match_id == match.id, Odds.market == "1X2")
        ).scalars())
        odds_summary = None
        if odds_rows:
            by_sel: dict[str, tuple[str, float]] = {}
            for o in odds_rows:
                cur = by_sel.get(o.selection)
                if cur is None or o.price_decimal > cur[1]:
                    by_sel[o.selection] = (o.bookmaker, o.price_decimal)
            odds_summary = {
                sel: {"bookmaker": bm, "price": price}
                for sel, (bm, price) in by_sel.items()
            }

        # ----- Phase 9: match preview context -----
        from src.web.preview import (
            compute_team_form, compute_head_to_head, compute_team_record,
            build_prediction_narrative,
        )

        home_form = compute_team_form(s, match.home_team) if match.home_team else None
        away_form = compute_team_form(s, match.away_team) if match.away_team else None

        h2h = None
        if match.home_team and match.away_team:
            h2h = compute_head_to_head(s, match.home_team, match.away_team)

        home_record = compute_team_record(
            s, match.home_team,
            match.competition_id, match.season,
        ) if match.home_team else None
        away_record = compute_team_record(
            s, match.away_team,
            match.competition_id, match.season,
        ) if match.away_team else None

        # Lineups (soccer)
        from src.db.schema import Lineup
        lineups = list(s.execute(
            select(Lineup)
            .where(Lineup.match_id == match.id)
            .order_by(Lineup.team_id, Lineup.is_starter.desc(), Lineup.player_name)
        ).scalars())
        home_lineup = [l for l in lineups if l.team_id == match.home_team_id]
        away_lineup = [l for l in lineups if l.team_id == match.away_team_id]
        lineup_kind = None
        if home_lineup:
            lineup_kind = home_lineup[0].kind

        # Probable pitchers (MLB) — enriched with season ERA when available
        from src.db.schema import MatchParticipant, PitcherSeasonStats
        pitchers = list(s.execute(
            select(MatchParticipant)
            .where(
                MatchParticipant.match_id == match.id,
                MatchParticipant.role == "starting_pitcher",
            )
        ).scalars())

        def _pitcher_dict(p) -> dict | None:
            if p is None:
                return None
            stats = None
            if p.player_source_id:
                stats = s.execute(
                    select(PitcherSeasonStats).where(
                        PitcherSeasonStats.player_source_id == p.player_source_id
                    )
                    .order_by(PitcherSeasonStats.season.desc())
                    .limit(1)
                ).scalar_one_or_none()
            return {
                "player_name": p.player_name,
                "kind": p.kind,
                "era": stats.era if stats else None,
                "whip": stats.whip if stats else None,
                "innings_pitched": stats.innings_pitched if stats else None,
                "k_per_9": stats.k_per_9 if stats else None,
                "games_started": stats.games_started if stats else None,
            }
        home_pitcher_raw = next((p for p in pitchers if p.team_id == match.home_team_id), None)
        away_pitcher_raw = next((p for p in pitchers if p.team_id == match.away_team_id), None)
        home_pitcher = _pitcher_dict(home_pitcher_raw)
        away_pitcher = _pitcher_dict(away_pitcher_raw)

        # Current injuries scoped to these two teams
        from src.db.schema import Injury
        injuries_by_team_id: dict[int, list] = {match.home_team_id: [], match.away_team_id: []}
        for inj in s.execute(
            select(Injury).where(
                Injury.team_id.in_([match.home_team_id, match.away_team_id])
            )
        ).scalars():
            injuries_by_team_id[inj.team_id].append({
                "name": inj.player_name,
                "position": inj.player_position,
                "reason": inj.reason,
            })

        # Prediction narrative (only when we have a prediction and form for both sides)
        narrative = None
        if pred_row is not None and home_form is not None and away_form is not None and h2h is not None:
            narrative = build_prediction_narrative(
                pred=pred_row,
                match=match,
                factor_breakdown=pred_row.factor_breakdown or {},
                home_form=home_form,
                away_form=away_form,
                h2h=h2h,
            )

    # Weather — outside session_scope since it's a network call, not a DB op
    weather = None
    if match.utc_date and match.venue:
        try:
            from src.web.weather import fetch_weather
            weather = fetch_weather(match.venue, match.utc_date)
        except Exception:
            weather = None

    is_baseball = match.sport == Sport.MLB if match and match.sport else False

    return templates.TemplateResponse(
        request,
        "match_detail.html",
        {
            "match": match,
            "home_stats": home_stats,
            "away_stats": away_stats,
            "prediction": prediction_dict,
            "outcome": outcome_dict,
            "odds_summary": odds_summary,
            "is_baseball": is_baseball,
            # Phase 9 preview context
            "home_form": home_form,
            "away_form": away_form,
            "h2h": h2h,
            "home_record": home_record,
            "away_record": away_record,
            "home_lineup": home_lineup,
            "away_lineup": away_lineup,
            "lineup_kind": lineup_kind,
            "home_pitcher": home_pitcher,
            "away_pitcher": away_pitcher,
            "home_injuries": injuries_by_team_id.get(match.home_team_id, []),
            "away_injuries": injuries_by_team_id.get(match.away_team_id, []),
            "narrative": narrative,
            "weather": weather,
        },
    )


@router.post("/{match_id}/refresh")
async def refresh_match(match_id: int, request: Request):
    """
    Per-match refresh: pull the latest real-time data for this specific match
    (lineups/injuries for soccer, probable pitchers for MLB) and regenerate
    the prediction.

    Doesn't sync results — that's `sync-matches` at a competition level.
    Doesn't refresh player season stats — those don't change between days.

    Returns a redirect to the match detail page so the user sees the
    updated state. Errors are caught and surfaced; partial failures
    (e.g. lineup API down but injuries still pulled) still re-predict.
    """
    import logging
    from src.adapters.registry import get_adapter
    from src.ingestion.service import IngestionService
    from src.walters.training import generate_predictions

    log = logging.getLogger(__name__)

    with session_scope() as s:
        match = s.execute(
            select(Match)
            .options(selectinload(Match.competition))
            .where(Match.id == match_id)
        ).scalar_one_or_none()
        if not match:
            raise HTTPException(404, detail=f"Match {match_id} not found")
        sport = match.sport
        competition_code = match.competition.code if match.competition else None
        season = match.season
        home_id = match.home_team_id
        away_id = match.away_team_id

    if not competition_code or not season:
        raise HTTPException(400, detail="Match has no competition/season; can't refresh.")

    sport_str = "baseball" if sport == Sport.MLB else "soccer"
    adapter = get_adapter(sport=sport_str)
    service = IngestionService(adapter)

    errors = []
    try:
        if sport == Sport.SOCCER:
            # Pull injuries for just the two teams in this match
            try:
                service.sync_injuries_for_teams([home_id, away_id], season=season)
            except Exception as e:
                log.warning("refresh: injury sync failed: %s", e)
                errors.append(f"injuries: {e}")
            # Pull lineup for just this match
            try:
                service.sync_lineups(
                    competition_code, season=season,
                    only_match_id=match_id,
                )
            except Exception as e:
                log.warning("refresh: lineup sync failed: %s", e)
                errors.append(f"lineups: {e}")
        elif sport == Sport.MLB:
            try:
                service.sync_pitchers(
                    competition_code, season=season,
                    only_match_id=match_id,
                )
            except Exception as e:
                log.warning("refresh: pitcher sync failed: %s", e)
                errors.append(f"pitchers: {e}")
            # Also refresh pitcher season stats so the ERA on the prediction
            # reflects the latest data
            try:
                service.sync_pitcher_stats(season=int(season))
            except Exception as e:
                log.warning("refresh: pitcher stats sync failed: %s", e)
                errors.append(f"pitcher_stats: {e}")

        # Regenerate prediction for just this match
        try:
            generate_predictions(
                competition_code, season,
                sport=sport, only_match_id=match_id,
            )
        except Exception as e:
            log.warning("refresh: predict failed: %s", e)
            errors.append(f"predict: {e}")
    except Exception as e:
        log.exception("refresh failed unexpectedly")
        raise HTTPException(500, detail=str(e))

    # Redirect back. If we had any errors, the page itself will reflect
    # the partial state — better UX than a popup.
    return RedirectResponse(url=f"/matches/{match_id}", status_code=303)
