"""
Teams routes.

GET /teams           — list teams in the active sport context (filterable by ?q=...)
GET /teams/{id}      — team detail: upcoming + recent fixtures across all comps
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from src.db.database import session_scope
from src.db.schema import Match, MatchStatus, Sport, Team
from src.web import preferences
from src.web.dependencies import resolve_sport

router = APIRouter(prefix="/teams")


@router.get("", response_class=HTMLResponse)
async def list_teams(request: Request, q: str | None = None):
    templates = request.state.templates
    active_sport = resolve_sport(request)
    sport_enum = Sport.SOCCER if active_sport == "soccer" else Sport.MLB

    with session_scope() as s:
        stmt = (
            select(Team)
            .where(Team.sport == sport_enum)
            .order_by(Team.area.is_(None), Team.area, Team.name)
        )
        if q:
            stmt = stmt.where(Team.name.ilike(f"%{q}%"))
        teams = list(s.execute(stmt).scalars())

    return templates.TemplateResponse(
        request,
        "teams.html",
        {"teams": teams, "q": q or "", "active_sport": active_sport},
    )


@router.get("/{team_id}", response_class=HTMLResponse)
async def team_detail(request: Request, team_id: int):
    templates = request.state.templates

    with session_scope() as s:
        team = s.get(Team, team_id)
        if not team:
            raise HTTPException(status_code=404, detail=f"Team {team_id} not found.")

        now = datetime.utcnow()

        match_load = (
            selectinload(Match.competition),
            selectinload(Match.home_team),
            selectinload(Match.away_team),
        )

        upcoming_q = (
            select(Match)
            .options(*match_load)
            .where(
                or_(Match.home_team_id == team.id, Match.away_team_id == team.id),
                Match.utc_date >= now,
                Match.status != MatchStatus.CANCELLED,
            )
            .order_by(Match.utc_date.asc())
            .limit(15)
        )
        upcoming = list(s.execute(upcoming_q).scalars())

        recent_q = (
            select(Match)
            .options(*match_load)
            .where(
                or_(Match.home_team_id == team.id, Match.away_team_id == team.id),
                Match.status == MatchStatus.FINISHED,
            )
            .order_by(Match.utc_date.desc())
            .limit(15)
        )
        recent = list(s.execute(recent_q).scalars())

        # Quick form summary (last 5 results: W/D/L from this team's perspective)
        form: list[str] = []
        for m in recent[:5]:
            if m.full_time_result is None:
                continue
            is_home = m.home_team_id == team.id
            ft = m.full_time_result.value
            if ft == "D":
                form.append("D")
            elif (ft == "H" and is_home) or (ft == "A" and not is_home):
                form.append("W")
            else:
                form.append("L")

        is_pinned = team_id in preferences.get_pinned_team_ids()

        # Streak KPIs (baseball) — team-profile stat, not a prediction input.
        streak_kpi = None
        if team.sport == Sport.MLB:
            from src.walters.team_streaks import team_streak_kpis
            streak_kpi = team_streak_kpis(s, team.id, season=None)

        # Squad rankings for soccer teams. Find the most recent season with
        # PlayerSeasonStats for this team and rank players by power score.
        squad_rankings: list[dict] = []
        squad_season: str | None = None
        if team.sport == Sport.SOCCER:
            from src.db.schema import PlayerSeasonStats
            from src.models.player_score import rank_team
            latest_season = s.execute(
                select(PlayerSeasonStats.season)
                .where(PlayerSeasonStats.team_id == team_id)
                .order_by(PlayerSeasonStats.season.desc())
                .limit(1)
            ).scalar_one_or_none()
            if latest_season:
                squad_season = latest_season
                stats_rows = list(s.execute(
                    select(PlayerSeasonStats)
                    .options(selectinload(PlayerSeasonStats.player))
                    .where(
                        PlayerSeasonStats.team_id == team_id,
                        PlayerSeasonStats.season == latest_season,
                    )
                ).scalars())
                squad_rankings = rank_team(stats_rows)

        return templates.TemplateResponse(
            request,
            "team_detail.html",
            {
                "team": team,
                "upcoming": upcoming,
                "recent": recent,
                "form": form,
                "is_pinned": is_pinned,
                "squad_rankings": squad_rankings,
                "squad_season": squad_season,
                "streak_kpi": streak_kpi,
            },
        )
