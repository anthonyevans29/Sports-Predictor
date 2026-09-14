"""
Helpers shared across web routes.

Resolves "which league is the user looking at right now" and "which sport"
— cookies take precedence over saved preferences, which fall back to soccer/PL.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import Response

from src.web import preferences

#: Cookie name for the per-browser selected league. Survives across visits
#: but resets if the user clears cookies — that's fine, they pick again.
LEAGUE_COOKIE = "sp_league"
SPORT_COOKIE = "sp_sport"

# Competitions that belong to baseball; everything else maps to soccer.
_BASEBALL_COMP_CODES = {"MLB", "MLB_SPRING"}


def sport_for_competition(code: str | None) -> str:
    """Return 'soccer' or 'baseball' for a competition code. Soccer is the default."""
    if code and code.upper() in _BASEBALL_COMP_CODES:
        return "baseball"
    return "soccer"


def is_baseball_competition(code: str | None) -> bool:
    return code is not None and code.upper() in _BASEBALL_COMP_CODES


def resolve_sport(request: Request) -> str:
    """
    Return 'soccer' or 'baseball' for this request.

    Order of precedence:
      1. ?sport= query param
      2. sp_sport cookie
      3. inferred from sp_league cookie (MLB → baseball)
      4. 'soccer'
    """
    qp = request.query_params.get("sport")
    if qp:
        return qp.lower()
    cookie = request.cookies.get(SPORT_COOKIE)
    if cookie:
        return cookie.lower()
    # Infer from league cookie
    league_cookie = request.cookies.get(LEAGUE_COOKIE, "")
    if league_cookie.upper() in _BASEBALL_COMP_CODES:
        return "baseball"
    return "soccer"


def resolve_league_code(request: Request) -> str:
    """
    Pick the league code for this request. Order of precedence:
      1. ?league=XX query param (explicit user action right now)
      2. sp_league cookie
      3. user preferences default
      4. PL (or MLB if the resolved sport is baseball)
    """
    qp = request.query_params.get("league")
    if qp:
        return qp.upper()
    cookie = request.cookies.get(LEAGUE_COOKIE)
    if cookie:
        return cookie.upper()
    # Default to MLB if sport context is baseball
    if resolve_sport(request) == "baseball":
        return "MLB"
    return preferences.get_default_league()


def set_league_cookie(response: Response, code: str) -> None:
    """Persist the user's league choice to the browser."""
    response.set_cookie(
        LEAGUE_COOKIE,
        code.upper(),
        max_age=60 * 60 * 24 * 365,
        samesite="lax",
        httponly=False,
    )
    # Also keep the sport cookie in sync so the nav switcher stays consistent
    sport = "baseball" if code.upper() in _BASEBALL_COMP_CODES else "soccer"
    response.set_cookie(
        SPORT_COOKIE,
        sport,
        max_age=60 * 60 * 24 * 365,
        samesite="lax",
        httponly=False,
    )


def set_sport_cookie(response: Response, sport: str) -> None:
    """Persist the user's sport choice."""
    response.set_cookie(
        SPORT_COOKIE,
        sport.lower(),
        max_age=60 * 60 * 24 * 365,
        samesite="lax",
        httponly=False,
    )
