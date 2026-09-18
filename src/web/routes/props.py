"""
Player props page (Phase 13).

    GET  /props              → paste-a-board form + standalone projections browser
    POST /props/grade        → grades a pasted board, re-renders the page with results

Informational only — grading reads what the user pastes in and compares it
to the model's own rolling-average projection. Nothing here talks to
PrizePicks or any other board; there is no bet placement anywhere in this
app (see README's layer-separation rule).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from src.db.database import session_scope
from src.db.schema import Sport
from src.walters.props import grade_board, parse_board_text, project_upcoming
from src.web.dependencies import resolve_sport
from src.web.guards import require_localhost

router = APIRouter(prefix="/props")

# Sports with real PlayerGameLog data flowing today. Others render the page
# (no crash) but honestly say there's nothing to project from yet.
_SPORT_MAP = {"soccer": Sport.SOCCER, "baseball": Sport.MLB, "nfl": Sport.NFL}

_DEFAULT_STAT_BY_SPORT = {
    Sport.SOCCER: "shots_on_target",
    Sport.MLB: "hits",
    Sport.NFL: "receiving_yards",
}


@router.get("", response_class=HTMLResponse)
async def props_page(request: Request, stat: str | None = None):
    templates = request.state.templates
    active_sport = resolve_sport(request)
    sport_enum = _SPORT_MAP.get(active_sport, Sport.SOCCER)
    stat_type = stat or _DEFAULT_STAT_BY_SPORT.get(sport_enum, "shots_on_target")

    with session_scope() as s:
        projections = project_upcoming(s, sport_enum, stat_type)

    return templates.TemplateResponse(
        request,
        "props.html",
        {
            "sport_enum": sport_enum.value,
            "stat_type": stat_type,
            "projections": projections,
            "picks": None,
            "unparsed_count": 0,
        },
    )


@router.post("/grade", response_class=HTMLResponse, dependencies=[Depends(require_localhost)])
async def grade_props_page(
    request: Request,
    board_text: str = Form(...),
    board_source: str = Form(default="prizepicks"),
):
    templates = request.state.templates
    active_sport = resolve_sport(request)
    sport_enum = _SPORT_MAP.get(active_sport, Sport.SOCCER)
    stat_type = _DEFAULT_STAT_BY_SPORT.get(sport_enum, "shots_on_target")

    parsed = parse_board_text(board_text)
    unparsed_count = max(
        0,
        len([ln for ln in board_text.splitlines() if ln.strip()]) - len(parsed),
    )

    with session_scope() as s:
        picks = grade_board(s, sport_enum, board_text, board_source=board_source)
        # Detach the bits the template needs before the session closes
        picks = [
            {
                "player_name_raw": p.player_name_raw,
                "stat_type": p.stat_type,
                "line": p.line,
                "projected_mean": p.projected_mean,
                "sample_size": p.sample_size,
                "edge_pct": p.edge_pct,
                "verdict": p.verdict,
                "confidence": p.confidence,
                "note": p.note,
            }
            for p in picks
        ]
        projections = project_upcoming(s, sport_enum, stat_type)

    return templates.TemplateResponse(
        request,
        "props.html",
        {
            "sport_enum": sport_enum.value,
            "stat_type": stat_type,
            "projections": projections,
            "picks": picks,
            "unparsed_count": unparsed_count,
            "board_text": board_text,
        },
    )
