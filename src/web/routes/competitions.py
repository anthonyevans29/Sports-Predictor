"""
Competitions routes.

GET /competitions          — list competitions in the active sport context
GET /competitions/{code}   — detail: teams in current season + recent matches
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.db.database import session_scope
from src.db.schema import Competition, CompetitionTeam, Match, MatchStatus, Sport, Team
from src.web.dependencies import resolve_sport

router = APIRouter(prefix="/competitions")


@router.get("", response_class=HTMLResponse)
async def list_competitions(request: Request):
    templates = request.state.templates
    active_sport = resolve_sport(request)
    sport_enum = Sport.SOCCER if active_sport == "soccer" else Sport.MLB

    with session_scope() as s:
        stmt = (
            select(Competition, func.count(Match.id).label("match_count"))
            .join(Match, Match.competition_id == Competition.id, isouter=True)
            .where(Competition.sport == sport_enum)
            .group_by(Competition.id)
            .order_by(Competition.area, Competition.name)
        )
        rows = [(c, n) for c, n in s.execute(stmt).all()]

    return templates.TemplateResponse(
        request,
        "competitions.html",
        {"rows": rows, "active_sport": active_sport},
    )


@router.get("/{code}", response_class=HTMLResponse)
async def competition_detail(request: Request, code: str, season: str | None = None):
    templates = request.state.templates

    with session_scope() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == code)
        ).scalar_one_or_none()
        if not comp:
            raise HTTPException(status_code=404, detail=f"Competition '{code}' not found.")

        # All seasons we have for this competition
        seasons_q = (
            select(Match.season)
            .where(Match.competition_id == comp.id)
            .distinct()
            .order_by(Match.season.desc())
        )
        seasons = [r for r in s.execute(seasons_q).scalars() if r]

        # If season not specified, pick the most recent we have
        chosen_season = season or (seasons[0] if seasons else None)

        # Teams in chosen season
        teams: list[Team] = []
        if chosen_season:
            teams_q = (
                select(Team)
                .join(CompetitionTeam, CompetitionTeam.team_id == Team.id)
                .where(
                    CompetitionTeam.competition_id == comp.id,
                    CompetitionTeam.season == chosen_season,
                )
                .order_by(Team.name)
            )
            teams = list(s.execute(teams_q).scalars())

        # Recent finished matches (up to 20)
        recent_matches_q = (
            select(Match)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .where(
                Match.competition_id == comp.id,
                Match.status == MatchStatus.FINISHED,
            )
            .order_by(Match.utc_date.desc())
            .limit(20)
        )
        if chosen_season:
            recent_matches_q = recent_matches_q.where(Match.season == chosen_season)
        recent_matches = list(s.execute(recent_matches_q).scalars())

        # Upcoming matches (next 10)
        upcoming_q = (
            select(Match)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .where(
                Match.competition_id == comp.id,
                Match.status != MatchStatus.FINISHED,
                Match.status != MatchStatus.CANCELLED,
            )
            .order_by(Match.utc_date.asc())
            .limit(10)
        )
        if chosen_season:
            upcoming_q = upcoming_q.where(Match.season == chosen_season)
        upcoming = list(s.execute(upcoming_q).scalars())

    return templates.TemplateResponse(
        request,
        "competition_detail.html",
        {
            "competition": comp,
            "seasons": seasons,
            "chosen_season": chosen_season,
            "teams": teams,
            "recent_matches": recent_matches,
            "upcoming": upcoming,
        },
    )
