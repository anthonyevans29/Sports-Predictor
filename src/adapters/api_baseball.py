"""
API-Baseball client — complement, not replacement.

Designed to fill specific gaps in MLB Stats API coverage:
  - Odds (the headline use case)
  - Future: player season stats, injury reports, batting lineups

This intentionally is NOT a full DataAdapter subclass. The MLB Stats API
adapter is the canonical source for matches, scores, schedules, pitchers,
and standings — those fields are NEVER overwritten by API-Baseball data.

Design principles:
  - MLB Stats API is source of truth where both APIs cover the same field.
  - API-Baseball is queried only for things MLB Stats API can't provide.
  - Match identification uses (date ± 6h, normalized team names) since
    the two APIs don't share game IDs.
  - Rate-limit aware: logs x-requests-remaining; bails politely on 429.

Auth: uses API_BASEBALL_KEY env var if set, otherwise falls back to
API_FOOTBALL_KEY (API-Sports allows the same key across products on
multi-sport subscriptions).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

log = logging.getLogger(__name__)

# API-Baseball base URL (RapidAPI variant — most API-Sports customers use this).
# Direct api-sports.io subscriptions use https://v1.baseball.api-sports.io/
# We try the direct host first (which is what paid API-Sports keys use),
# falling back to the RapidAPI host if a key looks like a RapidAPI key.
DIRECT_BASE = "https://v1.baseball.api-sports.io"

# MLB league ID in API-Baseball's catalog. Stable.
MLB_LEAGUE_ID = 1


@dataclass
class OddsRow:
    """One bookmaker's price for one selection in one market for one game."""
    api_baseball_game_id: int
    commence_time: datetime          # game start, UTC
    home_team: str                   # raw upstream name
    away_team: str
    market: str                      # "1X2" (moneyline), "TOTALS", "SPREADS"
    selection: str                   # "HOME", "AWAY", "OVER", "UNDER", "HOME_SPREAD", "AWAY_SPREAD"
    bookmaker: str
    price_decimal: float
    line: float | None = None        # totals line or spread, None for moneyline


class APIBaseballError(Exception):
    """Raised when API-Baseball returns an error or auth fails."""


class APIBaseballClient:
    """
    Thin client. Not a full DataAdapter — by design.

    Usage:
        client = APIBaseballClient.from_env()
        odds = client.list_odds_for_date(date="2026-05-22", season=2026)
    """

    def __init__(self, api_key: str, base_url: str = DIRECT_BASE):
        if not api_key:
            raise APIBaseballError("No API key provided")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._last_remaining: int | None = None

    @classmethod
    def from_env(cls) -> "APIBaseballClient | None":
        """
        Construct from environment variables. Returns None if no key is set,
        so callers can degrade gracefully.

        Tries API_BASEBALL_KEY first, then API_FOOTBALL_KEY as a fallback
        for users with multi-sport API-Sports subscriptions using one key.
        """
        key = os.environ.get("API_BASEBALL_KEY") or os.environ.get("API_FOOTBALL_KEY")
        if not key:
            log.info("No API-Baseball key in env (set API_BASEBALL_KEY)")
            return None
        return cls(api_key=key)

    @property
    def requests_remaining(self) -> int | None:
        """Last seen value of x-ratelimit-requests-remaining header (None if unseen)."""
        return self._last_remaining

    def _get(self, path: str, params: dict | None = None) -> dict:
        """
        GET with API-Sports auth header. Raises APIBaseballError on bad status.
        Logs rate-limit headers when present.
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"x-apisports-key": self.api_key}
        try:
            r = requests.get(url, params=params or {}, headers=headers, timeout=15)
        except requests.RequestException as e:
            raise APIBaseballError(f"GET {path}: {e}") from e

        # Headers are case-insensitive; requests handles that
        remaining = r.headers.get("x-ratelimit-requests-remaining")
        if remaining is not None:
            try:
                self._last_remaining = int(remaining)
                log.debug("API-Baseball: %s requests remaining", remaining)
            except ValueError:
                pass

        if r.status_code == 429:
            raise APIBaseballError(
                "Rate-limited by API-Baseball. Try again later."
            )
        if r.status_code == 401 or r.status_code == 403:
            raise APIBaseballError(
                f"Auth failed ({r.status_code}). Check API_BASEBALL_KEY "
                f"or confirm baseball is on your subscription."
            )
        if not r.ok:
            raise APIBaseballError(f"GET {path}: HTTP {r.status_code} — {r.text[:200]}")

        try:
            data = r.json()
        except ValueError as e:
            raise APIBaseballError(f"GET {path}: not JSON ({e})") from e

        # API-Sports nests errors inside the response body, not just the status code.
        errors = data.get("errors")
        if errors:
            # Errors can be a dict (field → msg) or a list. Both annoying.
            if isinstance(errors, dict) and errors:
                raise APIBaseballError(f"GET {path}: API error {errors}")
            if isinstance(errors, list) and errors:
                raise APIBaseballError(f"GET {path}: API error {errors}")
        return data

    # ------------------------------------------------------------------
    # Teams (used for source-id mapping)
    # ------------------------------------------------------------------

    def list_teams(self, season: int) -> list[dict]:
        """
        List all MLB teams for a given season. One API call.

        Used to populate the API-Baseball team source IDs on our Team
        rows, so future syncs (injuries) can target teams by their
        API-Baseball ID.

        Returns: list of {"id": int, "name": str, "code": str|None}
        """
        params = {"league": MLB_LEAGUE_ID, "season": season}
        data = self._get("teams", params=params)
        out = []
        for item in data.get("response") or []:
            tid = item.get("id")
            name = item.get("name")
            if tid is None or not name:
                continue
            out.append({
                "id": int(tid),
                "name": name,
                "code": item.get("code"),
            })
        return out

    # ------------------------------------------------------------------
    # Injuries
    # ------------------------------------------------------------------
    # NOTE: API-Baseball doesn't expose an /injuries endpoint. Confirmed
    # by the docs page (https://api-sports.io/documentation/baseball/v1):
    # endpoints are Timezone / Seasons / Countries / Leagues / Teams /
    # Standings / Games / Odds / Bets / Bookmakers. No injuries.
    # The football, NFL, and rugby products have it; baseball does not.

    def list_odds_window(self, season: int) -> list[OddsRow]:
        """
        Pull all currently-available MLB pre-match odds in one request.

        API-Baseball's /odds endpoint accepts: game, league, season, bet,
        bookmaker. It does NOT support `date` or `page`. Calling with just
        league+season returns whatever's in the active pre-match window
        (1-7 days before each game, per their docs) in a single response.

        We don't paginate because the endpoint doesn't paginate.

        Returns a flat list of OddsRow — one per (game, market, selection,
        bookmaker). De-duped just in case the API ever returns overlap.
        """
        rows: list[OddsRow] = []
        seen: set[tuple] = set()

        params = {"league": MLB_LEAGUE_ID, "season": season}
        data = self._get("odds", params=params)
        response = data.get("response") or []

        for game_block in response:
            for row in self._parse_game_odds(game_block):
                key = (
                    row.api_baseball_game_id, row.bookmaker,
                    row.market, row.selection, row.line,
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)

        return rows

    def list_games_on_date(self, season: int, date_str: str) -> list[dict]:
        """
        M11a helper: list the provider's games for one calendar date
        (YYYY-MM-DD, provider-side). Used to resolve provider game ids for
        UTC-rollover matches the bulk odds window omitted.
        """
        data = self._get("games", params={
            "league": MLB_LEAGUE_ID, "season": season, "date": date_str,
        })
        return data.get("response") or []

    def list_odds_for_game(self, season: int, game_id: int) -> list[OddsRow]:
        """
        M11a helper: targeted per-game odds request. The bulk window
        excludes games whose provider-side date hasn't arrived yet; this
        asks for one game explicitly. Returns [] if the provider has not
        published odds for it (which is itself the answer to the M11
        mechanism question — see backlog).
        """
        rows: list[OddsRow] = []
        seen: set[tuple] = set()
        data = self._get("odds", params={
            "league": MLB_LEAGUE_ID, "season": season, "game": game_id,
        })
        for game_block in data.get("response") or []:
            for row in self._parse_game_odds(game_block):
                key = (
                    row.api_baseball_game_id, row.bookmaker,
                    row.market, row.selection, row.line,
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
        return rows

    def _parse_game_odds(self, game_block: dict):
        """Parse one game's odds block into OddsRows. Yields zero or more."""
        game = game_block.get("game") or {}
        game_id = game.get("id")
        if game_id is None:
            return
        # commence_time
        game_dt_raw = (game.get("date") or "")
        try:
            commence_time = datetime.fromisoformat(
                game_dt_raw.replace("Z", "+00:00")
            )
            if commence_time.tzinfo is not None:
                commence_time = commence_time.astimezone(tz=None).replace(tzinfo=None)
        except (ValueError, AttributeError):
            return

        teams = game.get("teams") or {}
        home_team = (teams.get("home") or {}).get("name") or ""
        away_team = (teams.get("away") or {}).get("name") or ""
        if not home_team or not away_team:
            return

        for bm in game_block.get("bookmakers", []):
            bm_name = bm.get("name") or "?"
            for bet in bm.get("bets", []):
                market_name = (bet.get("name") or "").strip()
                parsed_market, parser = _MARKET_PARSERS.get(market_name, (None, None))
                if parser is None:
                    continue
                for value in bet.get("values", []):
                    for ow in parser(value):
                        yield OddsRow(
                            api_baseball_game_id=game_id,
                            commence_time=commence_time,
                            home_team=home_team,
                            away_team=away_team,
                            market=parsed_market,
                            selection=ow["selection"],
                            bookmaker=bm_name,
                            price_decimal=ow["price"],
                            line=ow.get("line"),
                        )


# ----------------------------------------------------------------------
# Market parsers — convert API-Baseball's per-bookmaker schema into
# our normalized (market, selection) pairs. Each parser yields zero or
# more {"selection": str, "price": float, "line": float|None} dicts.
# ----------------------------------------------------------------------

def _parse_moneyline(value: dict) -> list[dict]:
    """Bet "Home/Away" → 1X2 selections (no draw in baseball)."""
    label = (value.get("value") or "").strip().lower()
    odds = _to_float(value.get("odd"))
    if odds is None:
        return []
    if label in ("home", "1"):
        return [{"selection": "HOME", "price": odds}]
    if label in ("away", "2"):
        return [{"selection": "AWAY", "price": odds}]
    return []


def _parse_totals(value: dict) -> list[dict]:
    """Bet "Over/Under" or "Home Totals (Over/Under)" — totals on full game."""
    label = (value.get("value") or "").strip().lower()
    odds = _to_float(value.get("odd"))
    if odds is None:
        return []
    # Line can show up in either `handicap` or be embedded in the label
    line = _to_float(value.get("handicap"))
    if line is None:
        # Try parsing "Over 8.5" or "Under 8.5"
        parts = label.split()
        if len(parts) == 2:
            line = _to_float(parts[1])
            label = parts[0]
    if label.startswith("over"):
        return [{"selection": "OVER", "price": odds, "line": line}]
    if label.startswith("under"):
        return [{"selection": "UNDER", "price": odds, "line": line}]
    return []


def _parse_spread(value: dict) -> list[dict]:
    """Run line — baseball's equivalent of point spread, almost always ±1.5."""
    label = (value.get("value") or "").strip().lower()
    odds = _to_float(value.get("odd"))
    if odds is None:
        return []
    line = _to_float(value.get("handicap"))
    if label in ("home", "1"):
        return [{"selection": "HOME_SPREAD", "price": odds, "line": line}]
    if label in ("away", "2"):
        return [{"selection": "AWAY_SPREAD", "price": odds, "line": line}]
    return []


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# Map of upstream bet name → (our market code, parser function).
# Names come from API-Baseball's bet catalogue. The most common are:
#   "Home/Away"             → moneyline
#   "Asian Handicap"        → run line / spread
#   "Over/Under"            → totals
# We deliberately match a small set rather than try to handle every prop;
# extending later is just adding to this dict.
_MARKET_PARSERS: dict[str, tuple[str, Any]] = {
    "Home/Away": ("1X2", _parse_moneyline),
    "Over/Under": ("TOTALS", _parse_totals),
    "Asian Handicap": ("SPREADS", _parse_spread),
}
