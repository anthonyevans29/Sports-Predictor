"""
API-Football (api-sports.io) adapter.

Supports both auth modes:
  - Direct API-Sports: https://v3.football.api-sports.io with x-apisports-key header
  - RapidAPI: https://api-football-v1.p.rapidapi.com/v3 with x-rapidapi-* headers

Picked via API_FOOTBALL_HOST env var. Defaults to direct (most common).

Why this adapter exists alongside Football-Data.org:
  - Covers ALL of Arsenal's competitions, including FA Cup, EFL Cup, Europa League
    and Conference League — which FD.org gates behind paid tiers.
  - Provides rich per-fixture stats (shots, possession, xG, cards) that FD.org
    doesn't expose. We populate MatchStats from this adapter, not from FD.org.
  - Has bookmaker odds endpoint (Phase 2 — value detection).

Coverage trade-off: API-Football's free tier is 100 requests/DAY (vs FD.org's
10/min). Use it for the competitions FD.org doesn't cover, and for stats
enrichment after fixtures are loaded — not for bulk historical backfill on PL.

API reference: https://www.api-football.com/documentation-v3
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

from config import settings
from src.adapters.base import DataAdapter
from src.adapters.normalized import (
    NormalizedCompetition,
    NormalizedMatch,
    NormalizedMatchStats,
    NormalizedTeam,
)
from src.db.schema import MatchStatus, Result, Sport

log = logging.getLogger(__name__)

# Default host = direct API-Sports. Override via env var for RapidAPI.
_HOST_DIRECT = "v3.football.api-sports.io"
_HOST_RAPID = "api-football-v1.p.rapidapi.com"

# Rate limit. Free tier is 100/day; we throttle to ~10/min which gives users
# 6 minutes of work before they need to wait. Paid plans can override.
_RATE_LIMIT_SECONDS = 6.5

# ----------------------------------------------------------------------
# Competition code mapping
# ----------------------------------------------------------------------
# We keep canonical codes (PL, CL, FAC, EFL, EL, UECL) consistent across all
# adapters. This adapter translates them to API-Football's integer league IDs.
#
# To find an ID for a competition not listed here, hit /leagues?name=<name>
# and inspect the response.
_CODE_TO_LEAGUE_ID: dict[str, int] = {
    # England
    "PL": 39,        # Premier League
    "ELC": 40,       # Championship
    "EL1": 41,       # League One (pyramid project, 2026-08-27)
    "EL2": 42,       # League Two (pyramid project, 2026-08-27)
    "FAC": 45,       # FA Cup
    "EFL": 48,       # EFL Cup (Carabao Cup)
    "CS": 528,       # Community Shield
    # Europe (UEFA)
    "CL": 2,         # Champions League
    "UEL": 3,        # Europa League (added 2026-08-27, pyramid+Europe backfill)
    "EL": 3,         # Europa League
    "UECL": 848,     # Conference League
    # CL/UEL feeder leagues (2026-09-19 scoped expansion: data-only,
    # rating enrichment for European opponents we already price).
    # Aug-May calendars only — calendar-year leagues (NOR/SWE) deferred
    # pending single-year season-string support in the --seasons helper.
    "NED": 88,       # Eredivisie
    "POR": 94,       # Primeira Liga
    "BEL": 144,      # Belgian Pro League
    "SCO": 179,      # Scottish Premiership
    "TUR": 203,      # Süper Lig
    "AUT": 218,      # Austrian Bundesliga
    "SUI": 207,      # Swiss Super League
    "GRE": 197,      # Greek Super League
    "CZE": 345,      # Czech Fortuna Liga
    # Spain / Italy / Germany / France
    "PD": 140,       # La Liga
    "SA": 135,       # Serie A
    "BL1": 78,       # Bundesliga
    "FL1": 61,       # Ligue 1
    # FIFA international
    "WC":      1,    # FIFA World Cup
    "WCQ_EU":  32,   # World Cup Qualifying - Europe
    "WCQ_SA":  34,   # World Cup Qualifying - South America
    "WCQ_AF":  29,   # World Cup Qualifying - Africa
    "WCQ_AS":  30,   # World Cup Qualifying - Asia
    "WCQ_NA":  31,   # World Cup Qualifying - North & Central America
    "WCQ_OC":  33,   # World Cup Qualifying - Oceania
    "FRIENDLIES_INT": 10,  # International friendlies
    "UEFA_EURO": 4,  # UEFA Euro
}

_LEAGUE_ID_TO_CODE = {v: k for k, v in _CODE_TO_LEAGUE_ID.items()}

# Competitions whose "season" is a SINGLE calendar year, not a two-year
# league span. API-Football returns season as an int (e.g. 2026); for these
# we store it as "2026", NOT "2026/27". Getting this wrong silently breaks
# every season-filtered query (matches stored under "2026/27" never match a
# "2026" lookup). World Cup, Euros, and international tournaments are
# single-year events. (Domestic leagues correctly keep the "2026/27" form.)
_SINGLE_YEAR_SEASON_CODES = {
    "WC", "UEFA_EURO",
    "WCQ_EU", "WCQ_SA", "WCQ_AF", "WCQ_AS", "WCQ_NA", "WCQ_OC",
    "FRIENDLIES_INT",
}

# Default competition metadata when a code isn't pre-mapped — used in
# list_competitions to label them sensibly.
_CODE_TO_META: dict[str, tuple[str, str, str]] = {
    # code -> (name, area, type)
    "PL":   ("Premier League", "England", "LEAGUE"),
    "ELC":  ("Championship", "England", "LEAGUE"),
    "EL1":  ("League One", "England", "LEAGUE"),
    "EL2":  ("League Two", "England", "LEAGUE"),
    "FAC":  ("FA Cup", "England", "CUP"),
    "EFL":  ("EFL Cup", "England", "CUP"),
    "CS":   ("Community Shield", "England", "CUP"),
    "CL":   ("UEFA Champions League", "Europe", "INTL"),
    "UEL":  ("UEFA Europa League", "Europe", "INTL"),
    "EL":   ("UEFA Europa League", "Europe", "INTL"),
    "UECL": ("UEFA Conference League", "Europe", "INTL"),
    "NED":  ("Eredivisie", "Netherlands", "LEAGUE"),
    "POR":  ("Primeira Liga", "Portugal", "LEAGUE"),
    "BEL":  ("Pro League", "Belgium", "LEAGUE"),
    "SCO":  ("Premiership", "Scotland", "LEAGUE"),
    "TUR":  ("Süper Lig", "Turkey", "LEAGUE"),
    "AUT":  ("Bundesliga", "Austria", "LEAGUE"),
    "SUI":  ("Super League", "Switzerland", "LEAGUE"),
    "GRE":  ("Super League", "Greece", "LEAGUE"),
    "CZE":  ("Fortuna Liga", "Czechia", "LEAGUE"),
    "PD":   ("La Liga", "Spain", "LEAGUE"),
    "SA":   ("Serie A", "Italy", "LEAGUE"),
    "BL1":  ("Bundesliga", "Germany", "LEAGUE"),
    "FL1":  ("Ligue 1", "France", "LEAGUE"),
    # International
    "WC":             ("FIFA World Cup", "International", "INTL"),
    "WCQ_EU":         ("World Cup Qualifying — Europe", "International", "INTL"),
    "WCQ_SA":         ("World Cup Qualifying — South America", "International", "INTL"),
    "WCQ_AF":         ("World Cup Qualifying — Africa", "International", "INTL"),
    "WCQ_AS":         ("World Cup Qualifying — Asia", "International", "INTL"),
    "WCQ_NA":         ("World Cup Qualifying — North & Central America", "International", "INTL"),
    "WCQ_OC":         ("World Cup Qualifying — Oceania", "International", "INTL"),
    "FRIENDLIES_INT": ("International Friendlies", "International", "INTL"),
    "UEFA_EURO":      ("UEFA European Championship", "International", "INTL"),
}

# Status code translation
_STATUS_MAP = {
    "TBD": MatchStatus.SCHEDULED,
    "NS":  MatchStatus.SCHEDULED,
    "1H":  MatchStatus.LIVE,
    "HT":  MatchStatus.LIVE,
    "2H":  MatchStatus.LIVE,
    "ET":  MatchStatus.LIVE,
    "BT":  MatchStatus.LIVE,
    "P":   MatchStatus.LIVE,
    "SUSP": MatchStatus.LIVE,
    "INT": MatchStatus.LIVE,
    "LIVE": MatchStatus.LIVE,
    "FT":  MatchStatus.FINISHED,
    "AET": MatchStatus.FINISHED,
    "PEN": MatchStatus.FINISHED,
    "PST": MatchStatus.POSTPONED,
    "CANC": MatchStatus.CANCELLED,
    "ABD": MatchStatus.CANCELLED,
    "AWD": MatchStatus.FINISHED,
    "WO":  MatchStatus.FINISHED,
}


class APIFootballAdapter(DataAdapter):
    source_name = "api_football"
    supported_sports = frozenset({Sport.SOCCER})

    def __init__(self, api_key: str | None = None, host: str | None = None):
        self.api_key = api_key or settings.api_football_key
        if not self.api_key:
            raise ValueError(
                "API-Football key is required. Set API_FOOTBALL_KEY in your .env."
            )
        self.host = host or settings.api_football_host or _HOST_DIRECT
        self.base_url = (
            f"https://{self.host}/v3" if self.host == _HOST_RAPID else f"https://{self.host}"
        )

        self._session = requests.Session()
        if self.host == _HOST_RAPID:
            self._session.headers.update(
                {"x-rapidapi-key": self.api_key, "x-rapidapi-host": self.host}
            )
        else:
            self._session.headers.update({"x-apisports-key": self.api_key})

        self._last_request_ts: float = 0.0

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < _RATE_LIMIT_SECONDS:
            time.sleep(_RATE_LIMIT_SECONDS - elapsed)
        self._last_request_ts = time.monotonic()

    def _get(self, path: str, params: dict | None = None) -> dict:
        self._throttle()
        url = f"{self.base_url}/{path.lstrip('/')}"
        log.debug("GET %s params=%s", url, params)
        resp = self._session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            log.warning("Rate limited by API-Football, sleeping 60s")
            time.sleep(60)
            resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        # API-Football returns errors in payload, not always via HTTP status
        errors = payload.get("errors")
        if errors:
            # Errors can be {} or [] — only raise when there's content
            if isinstance(errors, dict) and errors:
                raise RuntimeError(f"API-Football error: {errors}")
            if isinstance(errors, list) and errors:
                raise RuntimeError(f"API-Football error: {errors}")
        return payload

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_competitions(self, sport: Sport) -> list[NormalizedCompetition]:
        """
        API-Football has 1200+ leagues globally; we don't want them all.
        Return only the curated set of competitions we map to canonical codes.
        """
        if sport != Sport.SOCCER:
            return []
        out: list[NormalizedCompetition] = []
        for code, league_id in _CODE_TO_LEAGUE_ID.items():
            name, area, comp_type = _CODE_TO_META.get(code, (code, "", "LEAGUE"))
            out.append(
                NormalizedCompetition(
                    sport=Sport.SOCCER,
                    code=code,
                    name=name,
                    area=area,
                    type=comp_type,
                    source=self.source_name,
                    source_id=str(league_id),
                )
            )
        return out

    def list_teams(self, competition_code: str, season: str | None = None) -> list[NormalizedTeam]:
        league_id = self._league_id_for(competition_code)
        params = {"league": league_id, "season": self._season_to_year(season)}
        data = self._get("teams", params=params)
        out: list[NormalizedTeam] = []
        for item in data.get("response", []):
            t = item.get("team", {})
            v = item.get("venue") or {}
            out.append(
                NormalizedTeam(
                    sport=Sport.SOCCER,
                    name=t["name"],
                    short_name=t.get("code"),
                    tla=t.get("code"),  # API-Football's "code" is a 3-letter abbrev
                    area=t.get("country"),
                    founded=t.get("founded"),
                    venue=v.get("name"),
                    source=self.source_name,
                    source_id=str(t["id"]),
                )
            )
        return out

    def list_matches(
        self,
        competition_code: str,
        season: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[NormalizedMatch]:
        league_id = self._league_id_for(competition_code)
        params: dict = {"league": league_id, "season": self._season_to_year(season)}
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to

        data = self._get("fixtures", params=params)
        out: list[NormalizedMatch] = []
        for item in data.get("response", []):
            out.append(self._parse_fixture(item, competition_code))
        return out

    def get_match_stats(self, match_source_id: str) -> list[NormalizedMatchStats]:
        """
        Per-team match stats from /fixtures/statistics. Returns one
        NormalizedMatchStats per team (2 entries for a finished fixture).
        """
        data = self._get("fixtures/statistics", params={"fixture": match_source_id})
        out: list[NormalizedMatchStats] = []
        for team_block in data.get("response", []):
            team = team_block.get("team", {})
            raw_stats = {s["type"]: s["value"] for s in team_block.get("statistics", [])}
            out.append(
                NormalizedMatchStats(
                    match_source_id=str(match_source_id),
                    team_source_id=str(team["id"]),
                    source=self.source_name,
                    shots=_to_int(raw_stats.get("Total Shots")),
                    shots_on_target=_to_int(raw_stats.get("Shots on Goal")),
                    possession_pct=_to_pct(raw_stats.get("Ball Possession")),
                    corners=_to_int(raw_stats.get("Corner Kicks")),
                    fouls=_to_int(raw_stats.get("Fouls")),
                    yellow_cards=_to_int(raw_stats.get("Yellow Cards")),
                    red_cards=_to_int(raw_stats.get("Red Cards")),
                    xg=_to_float(raw_stats.get("expected_goals")),
                    # Stash anything else for later analysis
                    extra_stats={k: v for k, v in raw_stats.items() if v is not None},
                )
            )
        return out

    def list_odds(self, match_source_id: str) -> list:
        """
        Pre-match bookmaker odds from /odds.

        Returns a list of NormalizedOdds covering Match Winner (1X2) and
        Goals Over/Under markets. We deliberately limit to those two for
        Phase 2; more markets (Asian handicap, BTTS, exact score) can be
        added when the model produces predictions for them.

        Costs 1 API request per fixture. Use sparingly — the CLI gates this
        behind a `--limit` flag like sync-stats does.
        """
        from datetime import datetime
        from src.adapters.normalized import NormalizedOdds

        data = self._get("odds", params={"fixture": match_source_id})
        out: list[NormalizedOdds] = []
        captured_at = datetime.utcnow()

        for response_item in data.get("response", []):
            for bookmaker_block in response_item.get("bookmakers", []):
                bm_name = bookmaker_block.get("name", "unknown")
                for bet in bookmaker_block.get("bets", []):
                    # API-Football market names — keep only the two we use
                    market_name = bet.get("name", "")
                    if market_name == "Match Winner":
                        for value in bet.get("values", []):
                            sel = _map_1x2_selection(value.get("value"))
                            if sel is None:
                                continue
                            try:
                                price = float(value.get("odd"))
                            except (TypeError, ValueError):
                                continue
                            out.append(NormalizedOdds(
                                match_source_id=str(match_source_id),
                                source=self.source_name,
                                bookmaker=bm_name,
                                market="1X2",
                                selection=sel,
                                price_decimal=price,
                                captured_at=captured_at,
                            ))
                    elif market_name == "Goals Over/Under":
                        for value in bet.get("values", []):
                            sel_raw = value.get("value", "")
                            try:
                                price = float(value.get("odd"))
                            except (TypeError, ValueError):
                                continue
                            # API returns "Over 2.5", "Under 2.5" etc. We only
                            # keep the canonical 2.5 line for now.
                            if "2.5" not in sel_raw:
                                continue
                            if sel_raw.startswith("Over"):
                                sel = "OVER"
                            elif sel_raw.startswith("Under"):
                                sel = "UNDER"
                            else:
                                continue
                            out.append(NormalizedOdds(
                                match_source_id=str(match_source_id),
                                source=self.source_name,
                                bookmaker=bm_name,
                                market="OU_2.5",
                                selection=sel,
                                price_decimal=price,
                                captured_at=captured_at,
                            ))
        return out

    def list_injuries(self, team_source_id: str, season: str) -> list[dict]:
        """
        Current injuries / unavailable players for a team in a given season.

        API-Football's `/injuries?team=X&season=Y` returns a fixture-by-fixture
        history — one row per (player, fixture they missed). A player out with
        a long-term injury appears once per missed fixture. We dedupe to one
        row per player, keeping the MOST RECENT fixture entry.

        This is *not* the same as a "currently injured" list. Callers downstream
        should filter by fixture_date to get truly active injuries (the API
        doesn't expose a "is currently injured" flag).

        Each dict has: player_name, player_position, reason, type,
        fixture_source_id, fixture_date (ISO timestamp string, may be None).
        """
        params = {"team": team_source_id, "season": self._season_to_year(season)}
        data = self._get("injuries", params=params)

        # Dedupe per player by fixture timestamp — keep the latest record per
        # player. Using timestamp as the comparison; None timestamps lose to
        # any real timestamp.
        by_player: dict[str, dict] = {}
        for item in data.get("response", []):
            player = item.get("player") or {}
            name = player.get("name")
            if not name or not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            fixture = item.get("fixture") or {}
            ts = fixture.get("timestamp")  # unix seconds or None
            row = {
                "player_name": name,
                "player_position": player.get("position"),
                "reason": player.get("reason"),
                "type": player.get("type"),
                "fixture_source_id": str(fixture["id"]) if fixture.get("id") else None,
                "fixture_date": fixture.get("date"),
                "_ts": ts if isinstance(ts, (int, float)) else 0,
            }
            prev = by_player.get(name)
            if prev is None or row["_ts"] > prev["_ts"]:
                by_player[name] = row

        out: list[dict] = []
        for row in by_player.values():
            row.pop("_ts", None)
            out.append(row)
        return out

    def list_lineup_confirmed(self, fixture_source_id: str) -> list[dict]:
        """
        Confirmed lineup from /fixtures/lineups. Only populated within ~1 hour
        of kickoff. Returns one dict per player slot.

        Each dict has: team_source_id, formation, is_starter, player_name,
        player_position, shirt_number.

        Skips entries where the upstream player name is missing/null (sometimes
        the API returns placeholder slots before final lineup is announced).

        Returns [] if API has no lineup yet (too early, or data not pushed).
        """
        data = self._get("fixtures/lineups", params={"fixture": fixture_source_id})
        out: list[dict] = []
        for team_block in data.get("response", []):
            team = team_block.get("team", {}) or {}
            team_source_id = str(team.get("id", ""))
            formation = team_block.get("formation")

            for slot in team_block.get("startXI", []) or []:
                p = slot.get("player") or {}
                name = p.get("name")
                if not name or not isinstance(name, str) or not name.strip():
                    continue
                out.append({
                    "team_source_id": team_source_id,
                    "formation": formation,
                    "is_starter": True,
                    "player_name": name.strip(),
                    "player_position": p.get("pos"),
                    "shirt_number": p.get("number"),
                })
            for slot in team_block.get("substitutes", []) or []:
                p = slot.get("player") or {}
                name = p.get("name")
                if not name or not isinstance(name, str) or not name.strip():
                    continue
                out.append({
                    "team_source_id": team_source_id,
                    "formation": formation,
                    "is_starter": False,
                    "player_name": name.strip(),
                    "player_position": p.get("pos"),
                    "shirt_number": p.get("number"),
                })
        return out

    def list_recent_starters(
        self, team_source_id: str, season: str, n: int = 5,
    ) -> list[dict]:
        """
        Heuristic projected lineup: the players who started for this team in
        the most recent `n` finished matches. Used for >T-20min predictions
        when no confirmed lineup is available.

        Pulls /fixtures with last={n} for the team, then /fixtures/lineups
        for each. Costs n+1 API requests. Use sparingly.
        """
        # Step 1: find the last n finished fixtures for this team
        fixtures_data = self._get(
            "fixtures",
            params={"team": team_source_id, "last": n, "season": self._season_to_year(season)},
        )
        fixture_ids: list[str] = []
        for item in fixtures_data.get("response", []):
            fid = item.get("fixture", {}).get("id")
            if fid is not None:
                fixture_ids.append(str(fid))

        # Step 2: collect starter frequency
        counts: dict[str, dict] = {}  # player_name -> {position, count, last_seen}
        for fid in fixture_ids:
            try:
                lineup_rows = self.list_lineup_confirmed(fid)
            except Exception:
                continue
            for row in lineup_rows:
                if row["team_source_id"] != str(team_source_id) or not row["is_starter"]:
                    continue
                name = row["player_name"]
                if not name:
                    continue
                if name not in counts:
                    counts[name] = {
                        "count": 0,
                        "position": row.get("player_position"),
                    }
                counts[name]["count"] += 1

        # Step 3: take the top 11 by frequency
        ranked = sorted(counts.items(), key=lambda kv: -kv[1]["count"])[:11]
        return [
            {
                "team_source_id": team_source_id,
                "formation": None,  # we don't try to reconstruct formation
                "is_starter": True,
                "player_name": name,
                "player_position": info["position"],
                "shirt_number": None,
            }
            for name, info in ranked
        ]

    def list_players(
        self, team_source_id: str, season: str,
    ) -> list[dict]:
        """
        Squad + season-to-date stats for one team.

        Hits /players?team=X&season=YYYY which paginates 20 results per page.
        For a typical PL squad of ~25-30 players this is 2 API requests.

        Returns one dict per player containing both biographical data and
        season-aggregate stats. Stats may be sparse (newly signed players)
        or zero-filled.

        Each dict:
          {
            "source_id": "523",
            "name": "M. Ødegaard",
            "position": "Midfielder",
            "date_of_birth": "1998-12-17" | None,
            "nationality": "Norway",
            "season": "2025/26",
            "team_source_id": "42",
            "competition_code": None,  # ignored; player stats aren't comp-scoped
            "stats": { ... all the counters and rates ... },
            "rating_avg": 7.2 | None,
          }
        """
        year = self._season_to_year(season)
        out: list[dict] = []
        page = 1
        while True:
            data = self._get(
                "players",
                params={"team": team_source_id, "season": year, "page": page},
            )
            response = data.get("response") or []
            if not response:
                break
            for item in response:
                parsed = self._parse_player_entry(item, season, team_source_id)
                if parsed is not None:
                    out.append(parsed)
            paging = data.get("paging") or {}
            total_pages = paging.get("total") or 1
            if page >= total_pages:
                break
            page += 1
        return out

    def _parse_player_entry(
        self, item: dict, season: str, team_source_id: str,
    ) -> dict | None:
        """
        Parse one entry from /players. Each entry is { "player": {...},
        "statistics": [ {...}, {...} ] } where statistics has one block per
        competition the player has played in this season. We sum across all
        comps to get a season-total.
        """
        p = item.get("player") or {}
        pid = p.get("id")
        name = p.get("name") or p.get("firstname") or None
        if not pid or not name:
            return None

        stats_list = item.get("statistics") or []
        if not stats_list:
            return None

        # Aggregate counters across all competitions the player appeared in
        # this season. Rates (pass accuracy, rating) we average weighted by
        # appearances.
        agg = {
            "appearances": 0,
            "lineups": 0,
            "minutes": 0,
            "goals": 0,
            "assists": 0,
            "shots": 0,
            "shots_on_target": 0,
            "key_passes": 0,
            "dribble_success": 0,
            "tackles": 0,
            "interceptions": 0,
            "duels_won": 0,
            "fouls_committed": 0,
            "fouls_drawn": 0,
            "yellow_cards": 0,
            "red_cards": 0,
            "saves": 0,
            "goals_conceded": 0,
            "clean_sheets": 0,
        }
        # Weighted averages: track (sum, weight) so we can divide at end
        rating_num, rating_w = 0.0, 0
        pass_acc_num, pass_acc_w = 0.0, 0
        position: str | None = None
        has_keeper_stats = False

        for sblock in stats_list:
            games = sblock.get("games") or {}
            agg["appearances"] += int(games.get("appearences") or 0)  # sic — API typo
            agg["lineups"] += int(games.get("lineups") or 0)
            agg["minutes"] += int(games.get("minutes") or 0)
            if not position:
                position = games.get("position")
            rating_str = games.get("rating")
            if rating_str:
                try:
                    r = float(rating_str)
                    apps = int(games.get("appearences") or 0)
                    if apps > 0:
                        rating_num += r * apps
                        rating_w += apps
                except (ValueError, TypeError):
                    pass

            shots = sblock.get("shots") or {}
            agg["shots"] += int(shots.get("total") or 0)
            agg["shots_on_target"] += int(shots.get("on") or 0)

            goals = sblock.get("goals") or {}
            agg["goals"] += int(goals.get("total") or 0)
            agg["assists"] += int(goals.get("assists") or 0)

            saves = goals.get("saves")
            conceded = goals.get("conceded")
            if saves is not None or conceded is not None:
                has_keeper_stats = True
                agg["saves"] += int(saves or 0)
                agg["goals_conceded"] += int(conceded or 0)

            passes = sblock.get("passes") or {}
            agg["key_passes"] += int(passes.get("key") or 0)
            acc = passes.get("accuracy")
            total = passes.get("total") or 0
            if acc is not None and total:
                try:
                    # API returns accuracy as integer percent (0–100), occasionally as decimal
                    acc_pct = float(acc)
                    if acc_pct > 1:
                        acc_pct = acc_pct / 100.0
                    pass_acc_num += acc_pct * int(total)
                    pass_acc_w += int(total)
                except (ValueError, TypeError):
                    pass

            tackles = sblock.get("tackles") or {}
            agg["tackles"] += int(tackles.get("total") or 0)
            agg["interceptions"] += int(tackles.get("interceptions") or 0)

            duels = sblock.get("duels") or {}
            agg["duels_won"] += int(duels.get("won") or 0)

            dribbles = sblock.get("dribbles") or {}
            agg["dribble_success"] += int(dribbles.get("success") or 0)

            fouls = sblock.get("fouls") or {}
            agg["fouls_committed"] += int(fouls.get("committed") or 0)
            agg["fouls_drawn"] += int(fouls.get("drawn") or 0)

            cards = sblock.get("cards") or {}
            agg["yellow_cards"] += int(cards.get("yellow") or 0)
            agg["red_cards"] += int(cards.get("red") or 0)

        # Date of birth
        dob = p.get("birth", {}).get("date") if isinstance(p.get("birth"), dict) else None
        # Nationality
        nationality = p.get("nationality")

        # Keeper-only fields stay None if no keeper stats reported
        if not has_keeper_stats:
            agg["saves"] = None  # type: ignore[assignment]
            agg["goals_conceded"] = None  # type: ignore[assignment]
            agg["clean_sheets"] = None  # type: ignore[assignment]

        return {
            "source_id": str(pid),
            "name": name,
            "position": position,
            "date_of_birth": dob,
            "nationality": nationality,
            "season": season,
            "team_source_id": str(team_source_id),
            "stats": agg,
            "rating_avg": (rating_num / rating_w) if rating_w > 0 else None,
            "pass_accuracy": (pass_acc_num / pass_acc_w) if pass_acc_w > 0 else None,
        }

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_fixture(self, item: dict, competition_code: str) -> NormalizedMatch:
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        score = item.get("score", {})

        status_short = fixture.get("status", {}).get("short", "NS")
        status = _STATUS_MAP.get(status_short, MatchStatus.SCHEDULED)

        # Result: API-Football marks winner via teams.home.winner / teams.away.winner
        result: Result | None = None
        if status == MatchStatus.FINISHED:
            if teams.get("home", {}).get("winner") is True:
                result = Result.HOME
            elif teams.get("away", {}).get("winner") is True:
                result = Result.AWAY
            else:
                result = Result.DRAW

        # Date — ISO 8601 with timezone
        utc_str = fixture.get("date", "")
        utc_date = (
            datetime.fromisoformat(utc_str).astimezone(timezone.utc).replace(tzinfo=None)
        )

        # Season comes back as int (e.g. 2024). Single-year tournaments
        # (World Cup, Euros, internationals) store as "2026"; domestic
        # leagues span two years and store as "2024/25".
        season_int = league.get("season")
        if season_int:
            if competition_code in _SINGLE_YEAR_SEASON_CODES:
                season = str(season_int)
            else:
                season = f"{season_int}/{str(season_int + 1)[-2:]}"
        else:
            season = ""

        # Half-time score lives under score.halftime
        ht = score.get("halftime") or {}

        venue = fixture.get("venue") or {}

        return NormalizedMatch(
            sport=Sport.SOCCER,
            competition_code=competition_code,
            season=season,
            utc_date=utc_date,
            status=status,
            home_team_source_id=str(teams["home"]["id"]),
            away_team_source_id=str(teams["away"]["id"]),
            source=self.source_name,
            source_id=str(fixture["id"]),
            matchday=_parse_round_to_matchday(league.get("round")),
            stage=league.get("round"),  # e.g. "Regular Season - 5", "Round of 16"
            home_score=goals.get("home"),
            away_score=goals.get("away"),
            home_score_ht=ht.get("home"),
            away_score_ht=ht.get("away"),
            full_time_result=result,
            venue=venue.get("name"),
            referee=fixture.get("referee"),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _league_id_for(code: str) -> int:
        if code not in _CODE_TO_LEAGUE_ID:
            raise ValueError(
                f"Unknown competition code '{code}' for API-Football. "
                f"Known: {sorted(_CODE_TO_LEAGUE_ID)}. "
                "Add it to _CODE_TO_LEAGUE_ID in src/adapters/api_football.py."
            )
        return _CODE_TO_LEAGUE_ID[code]

    @staticmethod
    def _season_to_year(season: str | None) -> int:
        """'2024/25' -> 2024. None -> current year (best guess)."""
        if not season:
            now = datetime.utcnow()
            return now.year if now.month >= 7 else now.year - 1
        return int(season.split("/")[0])


# ----------------------------------------------------------------------
# Stat coercion helpers — API-Football returns int, str, or null
# ----------------------------------------------------------------------


def _to_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _to_pct(v) -> float | None:
    """API returns possession as '52%' — strip and convert."""
    if v is None:
        return None
    if isinstance(v, str):
        v = v.rstrip("%").strip()
    return _to_float(v)


def _parse_round_to_matchday(round_str: str | None) -> int | None:
    """
    '/leagues' returns rounds like 'Regular Season - 14' for leagues
    and 'Round of 16' for cups. Extract the integer when it's a league round.
    """
    if not round_str:
        return None
    if " - " in round_str:
        try:
            return int(round_str.rsplit(" - ", 1)[1])
        except (ValueError, IndexError):
            return None
    return None


def _map_1x2_selection(api_value: str | None) -> str | None:
    """API-Football returns 'Home', 'Draw', 'Away' for 1X2. Normalize."""
    if not api_value:
        return None
    v = api_value.strip().lower()
    if v == "home":
        return "HOME"
    if v == "draw":
        return "DRAW"
    if v == "away":
        return "AWAY"
    return None
