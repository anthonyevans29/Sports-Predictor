"""
FastAPI application.

Mounts all routes, sets up Jinja2 templates and static files, and exposes
the `app` object that uvicorn serves.

Run via `python main.py` from the project root, which boots uvicorn and
optionally pops open the browser.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config import settings
from src.web import preferences
from src.web.guards import allowed_hosts, is_cross_site
from src.web.routes import admin, card, competitions, home, matches, players, predictions, teams

log = logging.getLogger(__name__)

WEB_ROOT = Path(__file__).parent

# Shared templates + static dirs, accessible to all route modules
templates = Jinja2Templates(directory=str(WEB_ROOT / "templates"))


def _humanize_datetime(value):
    """Filter: render a datetime as e.g. 'Sat 17 Aug 16:30'."""
    if value is None:
        return ""
    return value.strftime("%a %d %b %H:%M")


def _humanize_date(value):
    if value is None:
        return ""
    return value.strftime("%a %d %b %Y")


def _nav_context(request: Request) -> dict:
    """
    Data needed by base.html across every page: the active sport, active
    league, and the list of available leagues for that sport. Called as
    `nav_ctx(request)` inside the template.

    Wrapped in try/except so a bad DB state can't break the whole layout.
    """
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import Competition, Sport
    from src.web.dependencies import resolve_league_code, resolve_sport

    try:
        active_sport = resolve_sport(request)
        active_code = resolve_league_code(request)
        sport_enum = Sport.SOCCER if active_sport == "soccer" else Sport.MLB
        with session_scope() as s:
            comps = list(
                s.execute(
                    select(Competition)
                    .where(Competition.sport == sport_enum)
                    .order_by(Competition.area, Competition.name)
                ).scalars()
            )
            return {
                "active_sport": active_sport,
                "active_code": active_code,
                "comps": [
                    {"code": c.code, "name": c.name, "area": c.area} for c in comps
                ],
            }
    except Exception as e:
        log.warning("nav_context failed: %s", e)
        return {"active_sport": "soccer", "active_code": "PL", "comps": []}


templates.env.filters["dt"] = _humanize_datetime
templates.env.filters["d"] = _humanize_date
templates.env.globals["nav_ctx"] = _nav_context


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sports Predictor",
        description="Local browser app for Walters-style prediction modeling.",
        version="0.2.0",
    )

    # Static files (Tailwind via CDN, but our custom CSS/JS lives here)
    app.mount(
        "/static",
        StaticFiles(directory=str(WEB_ROOT / "static")),
        name="static",
    )

    # Inject templates into the request state so route handlers can access them
    @app.middleware("http")
    async def attach_templates(request: Request, call_next):
        request.state.templates = templates
        return await call_next(request)

    # Reject state-changing requests sent by other sites' pages (CSRF). See
    # guards.is_cross_site for why require_localhost alone doesn't cover this.
    @app.middleware("http")
    async def reject_cross_site(request: Request, call_next):
        if is_cross_site(
            request.method,
            request.headers.get("host"),
            request.headers.get("origin"),
            request.headers.get("referer"),
        ):
            return PlainTextResponse("Cross-site request rejected.", status_code=403)
        return await call_next(request)

    # Only answer to our own host names — blocks DNS-rebinding pages from
    # reading the UI. Added last so it runs first.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts(settings.host))

    # Route modules
    app.include_router(home.router)
    app.include_router(competitions.router)
    app.include_router(teams.router)
    app.include_router(matches.router)
    app.include_router(predictions.router)
    app.include_router(card.router)
    app.include_router(players.router)
    app.include_router(admin.router)

    # Quiet 204 for the browser's automatic favicon request — keeps logs clean
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(status_code=204)

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"ok": True}

    # Error handlers
    @app.exception_handler(404)
    async def not_found(request: Request, exc: HTTPException):
        return templates.TemplateResponse(
            request,
            "error.html",
            {"code": 404, "message": "Page not found."},
            status_code=404,
        )

    @app.exception_handler(500)
    async def server_error(request: Request, exc: HTTPException):
        log.exception("500 error: %s", exc)
        return templates.TemplateResponse(
            request,
            "error.html",
            {"code": 500, "message": "Server error."},
            status_code=500,
        )

    return app


app = create_app()
