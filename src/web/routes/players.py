"""
Player rankings — league-wide leaderboard.

GET /players?competition=PL&season=2025/26&position=Attacker

Surfaces the top-rated players in a competition+season filtered by position.
Driven by PlayerSeasonStats + player_score.compute_player_score.

Currently soccer-only (Phase 6a). Baseball player ratings will plug in here
once we sync per-pitcher and per-batter season stats.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.database import session_scope
from src.db.schema import (
    Competition,
    CompetitionTeam,
    PlayerSeasonStats,
    Sport,
    Team,
)
from src.models.player_score import rank_team
from src.web.dependencies import resolve_league_code, resolve_sport

router = APIRouter(prefix="/players")

# Position-bucket filters that show up in the UI
POSITION_FILTERS = ["All", "Attacker", "Midfielder", "Defender", "Goalkeeper"]


@router.get("", response_class=HTMLResponse)
async def leaderboard(
    request: Request,
    competition: str | None = None,
    season: str | None = None,
    position: str | None = None,
    min_minutes: int = 270,
    limit: int = 100,
):
    templates = request.state.templates
    active_sport = resolve_sport(request)

    # Default competition: whatever the user has set in the nav
    if not competition:
        competition = resolve_league_code(request)
    if not position:
        position = "All"

    if active_sport != "soccer":
        return templates.TemplateResponse(
            request, "players.html",
            {
                "rankings": [],
                "competition": competition,
                "season": season,
                "season_options": [],
                "position": position,
                "position_options": POSITION_FILTERS,
                "min_minutes": min_minutes,
                "active_sport": active_sport,
                "comp_options": [],
                "not_supported": True,
            },
        )

    with session_scope() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == competition)
        ).scalar_one_or_none()

        if not comp:
            return templates.TemplateResponse(
                request, "players.html",
                {
                    "rankings": [],
                    "competition": competition,
                    "season": season,
                    "season_options": [],
                    "position": position,
                    "position_options": POSITION_FILTERS,
                    "min_minutes": min_minutes,
                    "active_sport": active_sport,
                    "comp_options": [],
                    "not_found": True,
                },
            )

        # Season dropdown options: distinct seasons we have player stats for
        # in this competition's teams.
        team_ids_q = (
            select(CompetitionTeam.team_id)
            .where(CompetitionTeam.competition_id == comp.id)
        )
        team_ids = [tid for tid in s.execute(team_ids_q).scalars()]

        season_options: list[str] = []
        if team_ids:
            season_options = sorted({
                row for row in s.execute(
                    select(PlayerSeasonStats.season)
                    .where(PlayerSeasonStats.team_id.in_(team_ids))
                    .distinct()
                ).scalars() if row
            }, reverse=True)

        # Default to most recent season if none specified
        if not season and season_options:
            season = season_options[0]

        rankings: list[dict] = []
        if season and team_ids:
            stats_rows = list(s.execute(
                select(PlayerSeasonStats)
                .options(selectinload(PlayerSeasonStats.player),
                         selectinload(PlayerSeasonStats.team))
                .where(
                    PlayerSeasonStats.team_id.in_(team_ids),
                    PlayerSeasonStats.season == season,
                    PlayerSeasonStats.minutes >= min_minutes,
                )
            ).scalars())
            ranked = rank_team(stats_rows)

            # Attach team name and filter by position bucket
            team_name_by_id = {t.id: t.name for t in s.execute(
                select(Team).where(Team.id.in_(team_ids))
            ).scalars()}

            for r in ranked:
                r["team_name"] = team_name_by_id.get(r["team_id"], "?")
                if position == "All" or r["position_bucket"] == position:
                    rankings.append(r)
                    if len(rankings) >= limit:
                        break

        # All competitions in this sport for the dropdown
        comp_options = list(s.execute(
            select(Competition).where(Competition.sport == Sport.SOCCER)
            .order_by(Competition.name)
        ).scalars())

    return templates.TemplateResponse(
        request, "players.html",
        {
            "rankings": rankings,
            "competition": competition,
            "season": season,
            "season_options": season_options,
            "position": position,
            "position_options": POSITION_FILTERS,
            "min_minutes": min_minutes,
            "active_sport": active_sport,
            "comp_options": [{"code": c.code, "name": c.name} for c in comp_options],
        },
    )
