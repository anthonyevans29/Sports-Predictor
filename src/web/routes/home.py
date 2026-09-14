"""
League dashboard — the new home page.

Shows the user's selected league with:
  - Today's & next-7-days fixtures
  - League table (for round-robin competitions) OR stage breakdown (for cups)
  - Recent results
  - "My clubs" sidebar with Arsenal pinned by default

The "drill down to a club" path is unchanged — clicking any team takes you
to /teams/{id}, the existing focused club view.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.db.database import session_scope
from src.db.schema import Competition, Match, MatchStats, MatchStatus, Sport, Team
from src.web import preferences
from src.web.dependencies import LEAGUE_COOKIE, resolve_league_code, set_league_cookie
from src.web.standings import compute_standings

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """The league dashboard. Default league = PL unless cookie/prefs override."""
    templates = request.state.templates
    league_code = resolve_league_code(request)
    now = datetime.utcnow()

    with session_scope() as s:
        # Auto-pin the focus team (Arsenal) on first run if it exists and
        # the user hasn't pinned anything yet.
        _autopin_focus_team_if_needed(s)

        # All competitions we have, for the league selector dropdown
        all_comps = list(
            s.execute(
                select(Competition).order_by(Competition.area, Competition.name)
            ).scalars()
        )

        comp = s.execute(
            select(Competition).where(Competition.code == league_code)
        ).scalar_one_or_none()

        # Fall back to PL if the requested league isn't in the DB
        if comp is None:
            comp = s.execute(
                select(Competition).where(Competition.code == "PL")
            ).scalar_one_or_none()
            if comp is not None:
                league_code = "PL"

        # Pick the season to display: most recent one we have matches for
        chosen_season: str | None = None
        if comp:
            chosen_season = s.execute(
                select(Match.season)
                .where(Match.competition_id == comp.id)
                .order_by(Match.season.desc())
                .limit(1)
            ).scalar_one_or_none()

        # ---- Fixtures: today + next 7 days, then scheduled-only fallback ----
        upcoming_fixtures: list[dict] = []
        recent_results: list[dict] = []
        standings: list[dict] = []
        value_edges: list[dict] = []
        latest_by_match: dict[int, "Prediction"] = {}
        no_data = comp is None or chosen_season is None

        if not no_data:
            match_load = (
                selectinload(Match.home_team),
                selectinload(Match.away_team),
                selectinload(Match.competition),
            )

            # Upcoming: from now → +7 days. If empty, expand to next 10 anywhere.
            window_end = now + timedelta(days=7)
            upcoming_q = (
                select(Match)
                .options(*match_load)
                .where(
                    Match.competition_id == comp.id,
                    Match.season == chosen_season,
                    Match.utc_date >= now,
                    Match.utc_date <= window_end,
                    Match.status != MatchStatus.CANCELLED,
                )
                .order_by(Match.utc_date.asc())
            )
            upcoming_matches = list(s.execute(upcoming_q).scalars())

            if not upcoming_matches:
                # Fallback: next 10 scheduled, no date cap
                upcoming_q2 = (
                    select(Match)
                    .options(*match_load)
                    .where(
                        Match.competition_id == comp.id,
                        Match.season == chosen_season,
                        Match.utc_date >= now,
                        Match.status != MatchStatus.CANCELLED,
                    )
                    .order_by(Match.utc_date.asc())
                    .limit(10)
                )
                upcoming_matches = list(s.execute(upcoming_q2).scalars())

            upcoming_fixtures = [_fixture_dict(m) for m in upcoming_matches]

            # Attach predictions (production model only) to each upcoming fixture.
            # If no predictions exist yet, the badge area on the dashboard just
            # doesn't render — no error, no broken UI.
            if upcoming_matches:
                from src.db.schema import Prediction
                match_ids = [m.id for m in upcoming_matches]
                prediction_rows = list(s.execute(
                    select(Prediction).where(Prediction.match_id.in_(match_ids))
                ).scalars())
                # Group by match_id, keep most recent computed_at per match
                latest_by_match: dict[int, Prediction] = {}
                for p in prediction_rows:
                    existing = latest_by_match.get(p.match_id)
                    if existing is None or (p.computed_at and existing.computed_at and p.computed_at > existing.computed_at):
                        latest_by_match[p.match_id] = p
                for fixture in upcoming_fixtures:
                    pred = latest_by_match.get(fixture["id"])
                    if pred is not None:
                        fixture["prediction"] = _prediction_dict(pred)

            # Value edges: compare each prediction to the best available 1X2 odds.
            # Only renders if odds have been loaded.
            value_edges = _compute_value_edges(s, upcoming_matches, latest_by_match) if upcoming_matches else []

            # Recent: last 10 finished
            recent_q = (
                select(Match)
                .options(*match_load)
                .where(
                    Match.competition_id == comp.id,
                    Match.season == chosen_season,
                    Match.status == MatchStatus.FINISHED,
                )
                .order_by(Match.utc_date.desc())
                .limit(10)
            )
            recent_matches = list(s.execute(recent_q).scalars())
            recent_results = [_fixture_dict(m) for m in recent_matches]

            # Standings — only for league-type competitions
            if comp.type == "LEAGUE":
                all_finished_q = (
                    select(Match)
                    .options(selectinload(Match.home_team), selectinload(Match.away_team))
                    .where(
                        Match.competition_id == comp.id,
                        Match.season == chosen_season,
                        Match.status == MatchStatus.FINISHED,
                    )
                )
                all_finished = list(s.execute(all_finished_q).scalars())
                # Baseball-style standings if this is an MLB competition
                standings_sport = "baseball" if comp.code in ("MLB", "MLB_SPRING") else "soccer"
                standings = compute_standings(all_finished, sport=standings_sport)

        # ---- Sidebar: pinned clubs ----
        pinned_ids = preferences.get_pinned_team_ids()
        pinned_clubs: list[dict] = []
        if pinned_ids:
            pinned_teams = list(
                s.execute(select(Team).where(Team.id.in_(pinned_ids))).scalars()
            )
            for t in pinned_teams:
                pinned_clubs.append({
                    "id": t.id,
                    "name": t.name,
                    "tla": t.tla,
                    "area": t.area,
                })

        # ---- Top-line DB counts (small footer card) ----
        counts = {
            "competitions": s.execute(
                select(func.count()).select_from(Competition)
            ).scalar_one(),
            "teams": s.execute(select(func.count()).select_from(Team)).scalar_one(),
            "matches": s.execute(select(func.count()).select_from(Match)).scalar_one(),
            "stats_rows": s.execute(
                select(func.count()).select_from(MatchStats)
            ).scalar_one(),
        }

        # Detach competition into plain dict for the template
        comp_dict = None
        if comp:
            comp_dict = {
                "id": comp.id,
                "code": comp.code,
                "name": comp.name,
                "area": comp.area,
                "type": comp.type,
            }

        # Same for the competition list (dropdown)
        all_comps_list = [
            {"code": c.code, "name": c.name, "area": c.area} for c in all_comps
        ]

    return templates.TemplateResponse(
        request,
        "league_dashboard.html",
        {
            "competition": comp_dict,
            "all_comps": all_comps_list,
            "league_code": league_code,
            "chosen_season": chosen_season,
            "upcoming_fixtures": upcoming_fixtures,
            "recent_results": recent_results,
            "standings": standings,
            "standings_sport": "baseball" if (comp_dict and comp_dict["code"] in ("MLB", "MLB_SPRING")) else "soccer",
            "pinned_clubs": pinned_clubs,
            "value_edges": value_edges,
            "counts": counts,
            "no_data": no_data,
        },
    )


@router.get("/set-league/{code}")
async def set_league(code: str, request: Request):
    """Set the league cookie and redirect home. Also updates the saved default."""
    preferences.set_default_league(code.upper())
    resp = RedirectResponse(url="/", status_code=302)
    set_league_cookie(resp, code.upper())
    return resp


@router.get("/set-sport/{sport}")
async def set_sport(sport: str, request: Request):
    """
    Switch sport context. Clears the league cookie so the dashboard re-defaults
    to the right league for the new sport (PL for soccer, MLB for baseball).
    """
    from src.web.dependencies import set_sport_cookie
    sport = sport.lower()
    if sport not in ("soccer", "baseball"):
        sport = "soccer"
    resp = RedirectResponse(url="/", status_code=302)
    set_sport_cookie(resp, sport)
    # Clear league cookie so dashboard picks fresh default for this sport
    resp.delete_cookie(LEAGUE_COOKIE)
    return resp


@router.post("/pin-team/{team_id}")
async def pin_team(team_id: int, request: Request):
    """
    Pin a team. HTMX response varies by who called:
      - From sidebar's existing pin/unpin: target was the sidebar → return sidebar partial
      - From team detail page's pin button: target was the button itself → return button partial
    """
    preferences.pin_team(team_id)
    return await _render_pin_response(request, team_id)


@router.post("/unpin-team/{team_id}")
async def unpin_team(team_id: int, request: Request):
    """Unpin a team. Same dual-response pattern as pin."""
    preferences.unpin_team(team_id)
    return await _render_pin_response(request, team_id)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _fixture_dict(m: Match) -> dict:
    """Convert a Match into a plain dict, safe for templates after session close."""
    return {
        "id": m.id,
        "utc_date": m.utc_date,
        "status": m.status.value if m.status else "",
        "stage": m.stage,
        "matchday": m.matchday,
        "home_id": m.home_team.id if m.home_team else None,
        "home_name": m.home_team.name if m.home_team else "?",
        "home_tla": (m.home_team.tla if m.home_team else None),
        "away_id": m.away_team.id if m.away_team else None,
        "away_name": m.away_team.name if m.away_team else "?",
        "away_tla": (m.away_team.tla if m.away_team else None),
        "home_score": m.home_score,
        "away_score": m.away_score,
        "competition_code": m.competition.code if m.competition else "",
    }


def _prediction_dict(p) -> dict:
    """Render a Prediction into a plain dict for templates."""
    # Determine "pick": highest probability among H/D/A
    probs = {
        "H": p.home_win_prob or 0.0,
        "D": p.draw_prob or 0.0,
        "A": p.away_win_prob or 0.0,
    }
    pick = max(probs, key=probs.get)
    return {
        "model_version": p.model_version,
        "p_home": p.home_win_prob,
        "p_draw": p.draw_prob,
        "p_away": p.away_win_prob,
        "p_home_pct": round((p.home_win_prob or 0) * 100, 1),
        "p_draw_pct": round((p.draw_prob or 0) * 100, 1),
        "p_away_pct": round((p.away_win_prob or 0) * 100, 1),
        "xg_home": round(p.expected_home_score or 0, 2),
        "xg_away": round(p.expected_away_score or 0, 2),
        "pick": pick,  # "H", "D", or "A"
        "pick_prob_pct": round(max(probs.values()) * 100, 1),
        "factor_breakdown": p.factor_breakdown or {},
    }


def _autopin_focus_team_if_needed(s) -> None:
    """
    If the user has nothing pinned and we can find a focus team (Arsenal),
    pin it. One-time convenience so the sidebar isn't empty on first run.
    """
    if preferences.get_pinned_team_ids():
        return
    focus_name = preferences.get_focus_team_name()
    focus = s.execute(
        select(Team).where(Team.name.ilike(f"%{focus_name}%"))
    ).scalars().first()
    if focus:
        preferences.pin_team(focus.id)


async def _render_pin_response(request: Request, team_id: int):
    """
    Pick the right HTMX partial based on which element HTMX targeted.
    HTMX always sends the HX-Target header with the target's id, but on
    elements targeting `this` it may be unset — fall back on the request path.
    """
    templates = request.state.templates
    target = request.headers.get("HX-Target", "")
    is_pinned = team_id in preferences.get_pinned_team_ids()

    if target == "pinned-sidebar":
        # Sidebar swap path
        pinned_ids = preferences.get_pinned_team_ids()
        pinned_clubs: list[dict] = []
        if pinned_ids:
            with session_scope() as s:
                for t in s.execute(select(Team).where(Team.id.in_(pinned_ids))).scalars():
                    pinned_clubs.append(
                        {"id": t.id, "name": t.name, "tla": t.tla, "area": t.area}
                    )
        return templates.TemplateResponse(
            request,
            "partials/pinned_clubs.html",
            {"pinned_clubs": pinned_clubs},
        )

    # Default: assume the pin/unpin button on a team page is the target.
    # Return a button partial that flips state.
    return templates.TemplateResponse(
        request,
        "partials/pin_button.html",
        {"team_id": team_id, "is_pinned": is_pinned},
    )


def _compute_value_edges(s, upcoming_matches: list, latest_by_match: dict) -> list[dict]:
    """
    For each upcoming match with both a prediction AND loaded odds, compute
    the model's edge against the best available 1X2 price (de-vigged).

    Returns the top edges, sorted by edge percent, capped at 8. Empty list
    if no odds are loaded.
    """
    from src.db.schema import Odds
    from src.walters.value import MarketSnapshot, detect_value

    if not upcoming_matches or not latest_by_match:
        return []

    match_ids = [m.id for m in upcoming_matches]
    odds_rows = list(s.execute(
        select(Odds).where(Odds.match_id.in_(match_ids), Odds.market == "1X2")
    ).scalars())
    if not odds_rows:
        return []

    # Group odds by match_id and selection
    by_match: dict[int, dict[str, list[tuple]]] = {}
    for o in odds_rows:
        by_match.setdefault(o.match_id, {}).setdefault(o.selection, []).append((o.bookmaker, o.price_decimal))

    edges: list[dict] = []
    match_lookup = {m.id: m for m in upcoming_matches}
    for match_id, sels in by_match.items():
        pred = latest_by_match.get(match_id)
        if pred is None:
            continue
        snapshot = MarketSnapshot(market="1X2", by_selection=sels)
        model_probs = {
            "HOME": pred.home_win_prob or 0.0,
            "DRAW": pred.draw_prob or 0.0,
            "AWAY": pred.away_win_prob or 0.0,
        }
        opps = detect_value(snapshot, model_probs, min_edge_pct=0.05)
        if not opps:
            continue
        match = match_lookup.get(match_id)
        if match is None:
            continue
        for opp in opps:
            sel_to_label = {
                "HOME": match.home_team.name if match.home_team else "?",
                "AWAY": match.away_team.name if match.away_team else "?",
                "DRAW": "Draw",
            }
            edges.append({
                "match_id": match_id,
                "match_date": match.utc_date,
                "home_name": match.home_team.name if match.home_team else "?",
                "away_name": match.away_team.name if match.away_team else "?",
                "selection_label": sel_to_label.get(opp.selection, opp.selection),
                "selection": opp.selection,
                "bookmaker": opp.bookmaker,
                "price": opp.price,
                "model_prob_pct": round(opp.model_prob * 100, 1),
                "fair_prob_pct": round(opp.fair_prob * 100, 1),
                "edge_pct": round(opp.edge_pct * 100, 1),
            })

    edges.sort(key=lambda e: -e["edge_pct"])
    return edges[:8]
