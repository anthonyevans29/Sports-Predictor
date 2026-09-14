"""
MLB Stats API adapter.

Official MLB.com endpoint. Free, no API key required. Rate limits are
generous but undocumented; we throttle modestly out of politeness.

Base URL: https://statsapi.mlb.com/api/v1

Key endpoints we use:
  /teams?sportId=1                        — all 30 MLB teams
  /schedule?sportId=1&season=2026         — full season schedule
  /game/{gamePk}/boxscore                 — per-game stats (final score, line score)
  /game/{gamePk}/feed/live                — full game feed (used to find starting pitchers)
  /standings?leagueId=103,104             — division standings (AL=103, NL=104)

Competition codes we expose:
  MLB           — Regular season + playoffs (unified, like API-Football's PL)
  MLB_SPRING    — Spring Training (optional)

Season strings normalize as e.g. "2026" — MLB seasons are single-year unlike soccer.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

from src.adapters.base import DataAdapter
from src.adapters.normalized import (
    NormalizedCompetition,
    NormalizedMatch,
    NormalizedMatchStats,
    NormalizedTeam,
)
from src.db.schema import MatchStatus, Result, Sport

log = logging.getLogger(__name__)

_BASE_URL = "https://statsapi.mlb.com/api/v1"
_RATE_LIMIT_SECONDS = 0.5  # plenty fast — public endpoint, ~120 req/min is fine
_SPORT_ID_MLB = 1


# Game status codes from MLB Stats API.
# Reference: /game?sportId=1 returns status.detailedState and status.codedGameState
# We map by codedGameState which is the most stable.
_STATUS_MAP = {
    "S": MatchStatus.SCHEDULED,   # Scheduled
    "P": MatchStatus.SCHEDULED,   # Pre-Game
    "PW": MatchStatus.SCHEDULED,  # Warmup
    "I": MatchStatus.LIVE,        # In Progress
    "MA": MatchStatus.LIVE,       # Manager Challenge
    "MC": MatchStatus.LIVE,       # Manager Challenge
    "MR": MatchStatus.LIVE,       # Manager Challenge
    "F": MatchStatus.FINISHED,    # Final
    "FT": MatchStatus.FINISHED,   # Final: Tied (extras-eligible games rarely)
    "O": MatchStatus.FINISHED,    # Game Over (sometimes used pre-Final)
    "C": MatchStatus.CANCELLED,   # Cancelled
    "D": MatchStatus.POSTPONED,   # Postponed (also "DR" depending on version)
    "DR": MatchStatus.POSTPONED,
    "PR": MatchStatus.POSTPONED,
    "SU": MatchStatus.POSTPONED,  # Suspended
}


# Competition code → (api_filter, name, type, season_format)
_COMPETITIONS: dict[str, dict] = {
    "MLB": {
        "name": "Major League Baseball",
        "area": "USA",
        "type": "LEAGUE",
        "sport_id": 1,
        "game_types": ["R", "F", "D", "L", "W"],  # Regular + all postseason rounds
    },
    "MLB_SPRING": {
        "name": "MLB Spring Training",
        "area": "USA",
        "type": "LEAGUE",
        "sport_id": 1,
        "game_types": ["S"],  # Spring Training
    },
}


class MLBStatsAPIAdapter(DataAdapter):
    source_name = "mlb_stats_api"
    supported_sports = frozenset({Sport.MLB})

    def __init__(self):
        self._session = requests.Session()
        # No auth headers — public API
        self._session.headers.update({"User-Agent": "sports-predictor/0.5 (local app)"})
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
        url = f"{_BASE_URL}/{path.lstrip('/')}"
        log.debug("GET %s params=%s", url, params)
        resp = self._session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            log.warning("Rate limited by MLB Stats API, sleeping 30s")
            time.sleep(30)
            resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Public adapter API
    # ------------------------------------------------------------------

    def list_competitions(self, sport: Sport) -> list[NormalizedCompetition]:
        if sport != Sport.MLB:
            return []
        return [
            NormalizedCompetition(
                sport=Sport.MLB,
                code=code,
                name=meta["name"],
                area=meta["area"],
                type=meta["type"],
                source=self.source_name,
                source_id=code,  # MLB doesn't have a numeric league ID we use
            )
            for code, meta in _COMPETITIONS.items()
        ]

    def list_teams(self, competition_code: str, season: str | None = None) -> list[NormalizedTeam]:
        meta = _COMPETITIONS.get(competition_code)
        if not meta:
            return []
        params: dict = {"sportId": meta["sport_id"]}
        if season:
            params["season"] = self._season_to_year(season)
        data = self._get("teams", params=params)
        out: list[NormalizedTeam] = []
        for t in data.get("teams", []):
            venue = t.get("venue") or {}
            out.append(NormalizedTeam(
                sport=Sport.MLB,
                name=t.get("name", ""),
                short_name=t.get("teamName"),
                tla=t.get("abbreviation"),
                area=(t.get("locationName") or t.get("league", {}).get("name")),
                founded=t.get("firstYearOfPlay"),
                venue=venue.get("name"),
                source=self.source_name,
                source_id=str(t["id"]),
            ))
        return out

    def list_matches(
        self,
        competition_code: str,
        season: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[NormalizedMatch]:
        meta = _COMPETITIONS.get(competition_code)
        if not meta:
            return []

        params: dict = {
            "sportId": meta["sport_id"],
            "gameType": ",".join(meta["game_types"]),
        }
        if season:
            params["season"] = self._season_to_year(season)
        if date_from:
            params["startDate"] = date_from
        if date_to:
            params["endDate"] = date_to

        data = self._get("schedule", params=params)
        out: list[NormalizedMatch] = []
        for date_block in data.get("dates", []):
            for game in date_block.get("games", []):
                parsed = self._parse_game(game, competition_code)
                if parsed is not None:
                    out.append(parsed)
        return out

    def get_match_stats(self, match_source_id: str) -> list[NormalizedMatchStats]:
        """
        Per-team box-score stats. Baseball stats are very different from soccer:
        runs/hits/errors/HR/SO/BB at the team level, plus pitcher lines. We
        normalize the headline numbers into the shared `extra_stats` dict.

        Soccer-specific columns (shots, possession, xG) stay null for MLB rows.
        """
        try:
            data = self._get(f"game/{match_source_id}/boxscore")
        except requests.HTTPError:
            return []

        teams_block = data.get("teams") or {}
        out: list[NormalizedMatchStats] = []
        for side_key in ("home", "away"):
            side = teams_block.get(side_key) or {}
            team = side.get("team") or {}
            team_source_id = str(team.get("id", ""))
            if not team_source_id:
                continue
            t_stats = (side.get("teamStats") or {})
            batting = t_stats.get("batting") or {}
            pitching = t_stats.get("pitching") or {}
            extra = {
                "runs": batting.get("runs"),
                "hits": batting.get("hits"),
                "home_runs": batting.get("homeRuns"),
                "rbi": batting.get("rbi"),
                "strikeouts_batter": batting.get("strikeOuts"),
                "walks_batter": batting.get("baseOnBalls"),
                "left_on_base": batting.get("leftOnBase"),
                "earned_runs": pitching.get("earnedRuns"),
                "strikeouts_pitcher": pitching.get("strikeOuts"),
                "walks_pitcher": pitching.get("baseOnBalls"),
                "hits_allowed": pitching.get("hits"),
                "innings_pitched": pitching.get("inningsPitched"),
            }
            extra = {k: v for k, v in extra.items() if v is not None}
            out.append(NormalizedMatchStats(
                match_source_id=str(match_source_id),
                team_source_id=team_source_id,
                source=self.source_name,
                # Soccer-shaped fields stay None for MLB
                extra_stats=extra,
            ))
        return out

    def get_game_umpire_environment(self, match_source_id: str) -> dict | None:
        """
        TRACKING helper: from a finished game's boxscore, extract the plate
        umpire and the run/K/BB environment. Returns None if the game isn't
        final or the data is missing. Defensive against shape changes — a
        missing field degrades to None rather than raising, so a sync over many
        games never dies on one odd row.

        Boxscore shape (stable): top-level `officials` is a list of
        {officialType, official:{fullName}}; `teams.{home,away}.teamStats.
        batting` has runs/strikeOuts/baseOnBalls/homeRuns.
        """
        try:
            data = self._get(f"game/{match_source_id}/boxscore")
        except requests.HTTPError:
            return None

        # plate umpire
        plate = None
        for off in (data.get("officials") or []):
            if (off.get("officialType") or "").lower() in ("home plate", "homeplate", "plate"):
                plate = (off.get("official") or {}).get("fullName")
                break

        teams_block = data.get("teams") or {}

        def _sum(stat: str) -> int | None:
            total = 0
            seen = False
            for side_key in ("home", "away"):
                b = ((teams_block.get(side_key) or {}).get("teamStats") or {}).get("batting") or {}
                v = b.get(stat)
                if v is not None:
                    seen = True
                    try:
                        total += int(v)
                    except (TypeError, ValueError):
                        pass
            return total if seen else None

        def _team_name(side_key: str) -> str | None:
            return ((teams_block.get(side_key) or {}).get("team") or {}).get("name")

        runs = _sum("runs")
        # a game with no runs recorded for either side is almost certainly not final
        if plate is None and runs is None:
            return None

        return {
            "plate_umpire": plate,
            "home_team": _team_name("home"),
            "away_team": _team_name("away"),
            "total_runs": runs,
            "strikeouts": _sum("strikeOuts"),
            "walks": _sum("baseOnBalls"),
            "home_runs": _sum("homeRuns"),
        }

    def get_game_pitcher_appearances(self, match_source_id: str) -> list[dict] | None:
        """
        TRACKING helper: per-pitcher appearances from a finished game's boxscore,
        for deriving bullpen/starter USAGE (pitches thrown, recency) — which the
        season-aggregate bullpen endpoint can't give us. Returns a list of
        {team_source_id, pitcher_id, pitcher_name, pitches, outs, is_starter}
        or None if the game has no pitching data (not final).

        Boxscore shape: teams.{home,away}.players is a dict of "ID{personId}" →
        {person:{id,fullName}, stats:{pitching:{numberOfPitches, outs, ...}},
        gameStatus:{...}}. A pitcher with no pitching stats didn't pitch. We mark
        the starter as the pitcher with the most outs whose 'gamesStarted'==1 when
        available, else the max-outs pitcher per team (good-enough heuristic; the
        usage signal we care about is reliever pitch counts, not starter ID).
        """
        try:
            data = self._get(f"game/{match_source_id}/boxscore")
        except requests.HTTPError:
            return None

        teams_block = data.get("teams") or {}
        out: list[dict] = []
        any_pitching = False
        for side_key in ("home", "away"):
            side = teams_block.get(side_key) or {}
            team_id = str((side.get("team") or {}).get("id", "")) or None
            players = side.get("players") or {}
            for _pid, pdata in players.items():
                pitching = ((pdata.get("stats") or {}).get("pitching") or {})
                if not pitching:
                    continue
                pitches = pitching.get("numberOfPitches")
                outs = pitching.get("outs")
                if pitches is None and outs is None:
                    continue
                any_pitching = True
                season_stats = ((pdata.get("seasonStats") or {}).get("pitching") or {})
                gs = season_stats.get("gamesStarted")
                person = pdata.get("person") or {}
                def _i(v):
                    try:
                        return int(v) if v not in (None, "") else 0
                    except (ValueError, TypeError):
                        return 0
                out.append({
                    "team_source_id": team_id,
                    "pitcher_id": str(person.get("id", "")),
                    "pitcher_name": person.get("fullName"),
                    "pitches": _i(pitches),
                    "outs": _i(outs),
                    # heuristic: a pitcher credited with a game start this game.
                    # boxscore per-game 'gamesStarted' lives in stats.pitching too.
                    "is_starter": _i(pitching.get("gamesStarted")) == 1,
                    # effectiveness (per-appearance line) — for bullpen PERFORMANCE
                    # tracking, distinct from the usage/availability we already had.
                    "earned_runs": _i(pitching.get("earnedRuns")),
                    "hits_allowed": _i(pitching.get("hits")),
                    "walks_allowed": _i(pitching.get("baseOnBalls")),
                    "strikeouts": _i(pitching.get("strikeOuts")),
                })
        if not any_pitching:
            return None
        return out

    # ------------------------------------------------------------------
    # Baseball-specific: probable starting pitchers
    # ------------------------------------------------------------------


    def get_probable_pitchers(self, match_source_id: str) -> dict[str, dict]:
        """
        Return probable starting pitchers for ONE game.

        Uses /schedule?gamePk=...&hydrate=probablePitcher (the recommended
        endpoint per the MLB Stats API community docs). The probable
        pitcher data is embedded under teams.{home,away}.probablePitcher
        at the game level — NOT under gameData.probablePitchers on
        /feed/live (which is an old code path that returns empty for
        upcoming games).

        Cheap (1 call) but if you're checking many games, prefer
        get_probable_pitchers_for_date() which batches by date.
        """
        try:
            data = self._get(
                "schedule",
                params={
                    "sportId": 1,
                    "gamePk": match_source_id,
                    "hydrate": "probablePitcher",
                },
            )
        except requests.HTTPError:
            return {}

        dates = data.get("dates") or []
        for date_block in dates:
            for game in date_block.get("games") or []:
                if str(game.get("gamePk")) != str(match_source_id):
                    continue
                return self._extract_probables(game)
        return {}

    def get_probable_pitchers_for_date(
        self, date_iso: str,
    ) -> dict[str, dict[str, dict]]:
        """
        Return probable pitchers for ALL games on a single date.

        Batch path — one API call returns ~15 games' probables. Used by
        sync_pitchers to avoid 30 sequential per-game calls.

        Args:
          date_iso: "YYYY-MM-DD"

        Returns:
          {game_source_id: {"home": {player_id, name},
                            "away": {player_id, name}}}

        Empty dict on failure (network or shape) — caller treats as no data.
        """
        try:
            data = self._get(
                "schedule",
                params={
                    "sportId": 1,
                    "date": date_iso,
                    "hydrate": "probablePitcher",
                },
            )
        except requests.HTTPError:
            return {}

        out: dict[str, dict[str, dict]] = {}
        for date_block in data.get("dates") or []:
            for game in date_block.get("games") or []:
                game_pk = game.get("gamePk")
                if game_pk is None:
                    continue
                probables = self._extract_probables(game)
                if probables:
                    out[str(game_pk)] = probables
        return out

    @staticmethod
    def _extract_probables(game: dict) -> dict[str, dict]:
        """
        Pull probable pitchers out of a /schedule game block.

        The hydrated shape is:
          game.teams.{home,away}.probablePitcher.{id, fullName}
        """
        out: dict[str, dict] = {}
        teams = game.get("teams") or {}
        for side in ("home", "away"):
            block = teams.get(side) or {}
            probable = block.get("probablePitcher") or {}
            if not probable:
                continue
            name = probable.get("fullName", "")
            pid = probable.get("id", "")
            if not name:
                continue
            out[side] = {
                "player_id": str(pid),
                "name": name,
            }
        return out

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_game(self, game: dict, competition_code: str) -> NormalizedMatch | None:
        teams = game.get("teams") or {}
        home_block = teams.get("home") or {}
        away_block = teams.get("away") or {}
        home_team = home_block.get("team") or {}
        away_team = away_block.get("team") or {}
        if not home_team.get("id") or not away_team.get("id"):
            return None

        status_block = game.get("status") or {}
        coded_state = status_block.get("codedGameState", "S")
        status = _STATUS_MAP.get(coded_state, MatchStatus.SCHEDULED)

        # Date: "gameDate" is ISO 8601 UTC
        utc_str = game.get("gameDate", "")
        try:
            utc_date = datetime.fromisoformat(utc_str.replace("Z", "+00:00")).astimezone(
                timezone.utc
            ).replace(tzinfo=None)
        except ValueError:
            return None

        home_score = home_block.get("score")
        away_score = away_block.get("score")

        # Result. Baseball has no draws — if scores are tied at "finished",
        # something's odd (suspended/postponed). Treat as None.
        result: Result | None = None
        if status == MatchStatus.FINISHED and home_score is not None and away_score is not None:
            if home_score > away_score:
                result = Result.HOME
            elif away_score > home_score:
                result = Result.AWAY
            else:
                result = None  # very rare: suspended-as-tie

        # Season: MLB seasons are single-year (2026, not 2025/26)
        season_year = game.get("season") or utc_str[:4]
        season = str(season_year)

        # Venue
        venue = (game.get("venue") or {}).get("name")

        return NormalizedMatch(
            sport=Sport.MLB,
            competition_code=competition_code,
            season=season,
            utc_date=utc_date,
            status=status,
            home_team_source_id=str(home_team["id"]),
            away_team_source_id=str(away_team["id"]),
            source=self.source_name,
            source_id=str(game.get("gamePk", game.get("gameId", ""))),
            matchday=None,  # baseball doesn't really have matchdays
            stage=game.get("gameType"),  # R/F/D/L/W = regular/wildcard/division/championship/world series
            home_score=home_score,
            away_score=away_score,
            home_score_ht=None,
            away_score_ht=None,
            full_time_result=result,
            venue=venue,
            referee=None,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _season_to_year(season: str) -> int:
        """Soccer-style '2025/26' just takes the first year; '2026' stays."""
        if "/" in season:
            return int(season.split("/")[0])
        return int(season)

    # ------------------------------------------------------------------
    # Phase 11: Pitcher season stats
    # ------------------------------------------------------------------

    def get_pitcher_season_stats(
        self, person_id: str, season: int,
    ) -> dict | None:
        """
        Fetch one pitcher's season-to-date stats from MLB Stats API.

        Endpoint: /api/v1/people/{personId}/stats?stats=season&group=pitching

        Returns a dict with the parsed stats, or None if no data exists for
        this pitcher in this season (e.g. AAA call-up who hasn't pitched).

        One call per pitcher. Cheap.
        """
        url = f"{_BASE_URL}/people/{person_id}/stats"
        params = {
            "stats": "season",
            "group": "pitching",
            "season": season,
        }
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            log.debug("Pitcher stats fetch failed for %s: %s", person_id, e)
            return None

        # Response shape: { "stats": [ { "type": {...}, "group": {...}, "splits": [...] } ] }
        # We want stats[0].splits[0].stat
        stats_list = data.get("stats") or []
        if not stats_list:
            return None
        splits = stats_list[0].get("splits") or []
        if not splits:
            return None
        # Take the first split (regular season). Players who appeared in
        # multiple game types will have multiple splits — we just want the
        # primary season aggregate, which is always first.
        stat = splits[0].get("stat") or {}
        player_info = splits[0].get("player") or {}
        team_info = splits[0].get("team") or {}

        # MLB Stats API returns ERA and WHIP as strings ("3.45"). Parse defensively.
        def _to_float(v):
            try:
                return float(v) if v not in (None, "-.--", "") else None
            except (ValueError, TypeError):
                return None

        def _to_int(v):
            try:
                return int(v) if v not in (None, "") else 0
            except (ValueError, TypeError):
                return 0

        # innings_pitched is reported like "127.2" meaning 127 and 2/3 innings.
        # We convert to decimal: 127.2 → 127.667.
        ip_raw = stat.get("inningsPitched") or "0"
        try:
            if "." in str(ip_raw):
                whole, frac = str(ip_raw).split(".")
                ip = int(whole) + int(frac) / 3.0
            else:
                ip = float(ip_raw)
        except (ValueError, AttributeError):
            ip = 0.0

        return {
            "player_source_id": str(person_id),
            "player_name": player_info.get("fullName") or "",
            "team_source_id": str(team_info.get("id")) if team_info.get("id") else None,
            "games": _to_int(stat.get("gamesPitched")),
            "games_started": _to_int(stat.get("gamesStarted")),
            "innings_pitched": round(ip, 2),
            "earned_runs": _to_int(stat.get("earnedRuns")),
            "runs_allowed": _to_int(stat.get("runs")),
            "hits_allowed": _to_int(stat.get("hits")),
            "walks": _to_int(stat.get("baseOnBalls")),
            "strikeouts": _to_int(stat.get("strikeOuts")),
            "home_runs_allowed": _to_int(stat.get("homeRuns")),
            "era": _to_float(stat.get("era")),
            "whip": _to_float(stat.get("whip")),
            "k_per_9": _to_float(stat.get("strikeoutsPer9Inn")),
            "bb_per_9": _to_float(stat.get("walksPer9Inn")),
        }

    def get_team_bullpen_stats(
        self, team_source_id: str | int, season: int,
    ) -> dict | None:
        """
        Return team-level bullpen aggregate pitching stats for one team.

        Uses /teams/{teamId}/stats with statSplits + sitCodes=rp (relief
        pitching). One API call per team. Phase 12.2 — backs the bullpen
        component of effective team ERA for predictions.

        Args:
          team_source_id: MLB Stats API team ID
          season: integer season (e.g. 2026)

        Returns a dict with the same shape as PitcherSeasonStats columns
        (minus games_started, since bullpens by definition don't start):
          {games, innings_pitched, earned_runs, runs_allowed, hits_allowed,
           walks, strikeouts, home_runs_allowed, saves, blown_saves,
           era, whip, k_per_9, bb_per_9}

        Returns None when the API returns no data (team doesn't exist or
        no relief stats yet this season). Caller should treat None as
        "use neutral bullpen" rather than failing the sync.
        """
        try:
            data = self._get(
                f"teams/{team_source_id}/stats",
                params={
                    "stats": "statSplits",
                    "group": "pitching",
                    "sitCodes": "rp",
                    "season": season,
                    "sportId": 1,
                },
            )
        except requests.HTTPError:
            return None

        # Response shape: {stats: [{splits: [{stat: {...}, ...}]}]}
        stats_list = data.get("stats") or []
        if not stats_list:
            return None
        splits = stats_list[0].get("splits") or []
        if not splits:
            return None
        # Use the first (and usually only) relief-pitching split
        stat = splits[0].get("stat") or {}
        if not stat:
            return None

        def _to_float(v):
            try:
                return float(v) if v not in (None, "") else None
            except (ValueError, TypeError):
                return None

        def _to_int(v):
            try:
                return int(v) if v not in (None, "") else 0
            except (ValueError, TypeError):
                return 0

        # MLB Stats API returns innings as a string like "127.2" meaning
        # 127 2/3 innings — we convert thirds to decimal here.
        def _ip_to_decimal(v):
            try:
                if v is None or v == "":
                    return 0.0
                s = str(v)
                if "." in s:
                    whole, frac = s.split(".")
                    return int(whole) + int(frac) / 3.0
                return float(s)
            except (ValueError, TypeError):
                return 0.0

        return {
            "games": _to_int(stat.get("gamesPlayed") or stat.get("gamesPitched")),
            "innings_pitched": _ip_to_decimal(stat.get("inningsPitched")),
            "earned_runs": _to_int(stat.get("earnedRuns")),
            "runs_allowed": _to_int(stat.get("runs")),
            "hits_allowed": _to_int(stat.get("hits")),
            "walks": _to_int(stat.get("baseOnBalls")),
            "strikeouts": _to_int(stat.get("strikeOuts")),
            "home_runs_allowed": _to_int(stat.get("homeRuns")),
            "saves": _to_int(stat.get("saves")),
            "blown_saves": _to_int(stat.get("blownSaves")),
            "era": _to_float(stat.get("era")),
            "whip": _to_float(stat.get("whip")),
            "k_per_9": _to_float(stat.get("strikeoutsPer9Inn")),
            "bb_per_9": _to_float(stat.get("walksPer9Inn")),
        }

    def get_team_bullpen_recent(
        self,
        team_source_id: str | int,
        season: int,
        start_date: str,
        end_date: str,
    ) -> dict | None:
        """
        Return recent-window bullpen stats for one team (Phase 12.4).

        Uses /teams/{teamId}/stats with byDateRange + sitCodes=rp to get
        relief pitching over a rolling window (e.g. last 10 days). Captures
        a bullpen that's recently caving or locking in — signal the season
        aggregate is too slow to reflect.

        Args:
          team_source_id: MLB Stats API team ID
          season: integer season
          start_date / end_date: "YYYY-MM-DD" window bounds (inclusive)

        Returns {era, innings_pitched, earned_runs, runs_allowed} or None
        when the API returns no relief data for the window (e.g. all-star
        break, rainouts, too few appearances).
        """
        try:
            data = self._get(
                f"teams/{team_source_id}/stats",
                params={
                    "stats": "byDateRange",
                    "group": "pitching",
                    "sitCodes": "rp",
                    "startDate": start_date,
                    "endDate": end_date,
                    "season": season,
                    "sportId": 1,
                },
            )
        except requests.HTTPError:
            return None

        stats_list = data.get("stats") or []
        if not stats_list:
            return None
        splits = stats_list[0].get("splits") or []
        if not splits:
            return None
        stat = splits[0].get("stat") or {}
        if not stat:
            return None

        def _to_float(v):
            try:
                return float(v) if v not in (None, "") else None
            except (ValueError, TypeError):
                return None

        def _to_int(v):
            try:
                return int(v) if v not in (None, "") else 0
            except (ValueError, TypeError):
                return 0

        def _ip_to_decimal(v):
            try:
                if v is None or v == "":
                    return 0.0
                s = str(v)
                if "." in s:
                    whole, frac = s.split(".")
                    return int(whole) + int(frac) / 3.0
                return float(s)
            except (ValueError, TypeError):
                return 0.0

        return {
            "era": _to_float(stat.get("era")),
            "innings_pitched": _ip_to_decimal(stat.get("inningsPitched")),
            "earned_runs": _to_int(stat.get("earnedRuns")),
            "runs_allowed": _to_int(stat.get("runs")),
        }
