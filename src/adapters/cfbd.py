"""
CollegeFootballData.com (CFBD) adapter — the college football DataAdapter.

CFB PHASE 13.1 (player props): data wiring for one purpose — feeding
PlayerGameLog so prop projections (src/walters/props.py) have real per-game
college football stat lines. Not a full team-prediction pipeline like NFL/
soccer/MLB; no model consumes this yet.

API shape (verified against https://api.collegefootballdata.com/api-docs.json
2026-09-18, not assumed from memory):
  - Auth: `Authorization: Bearer <CFBD_API_KEY>`.
  - GET /teams/fbs?year=YYYY -> [{id, school, mascot, abbreviation, ...}]
  - GET /games?year=YYYY&seasonType=regular&classification=fbs
    -> [{id, season, week, startDate, completed, homeId, homeTeam,
         homePoints, awayId, awayTeam, awayPoints, ...}]
  - GET /games/players?id=<gameId> -> per-game player stats. `year` is
    documented as "required unless `id` is specified", so filtering by
    game id alone (our get_fixture_player_stats contract) is supported.
    Shape: [{id, teams: [{team (NAME, not id), conference, homeAway,
             points, categories: [{name, types: [{name, athletes:
             [{id, name, stat (STRING, may be composite e.g. "18-25")}]}]}]}]}]

Team-name -> team-id resolution: /games/players gives the team as a NAME
string, not the numeric id /teams/fbs and /games use. We resolve it via a
per-season name->id cache built from /teams/fbs (school names are the same
provider's canonical form on both endpoints, so an exact match is reliable —
if it ever misses, we skip that team's rows rather than guess (refuse-safe,
same discipline as the Kalshi/team matchers)).

Season format: single calendar year ("2026"), same as NFL/MLB.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

from src.adapters.base import DataAdapter
from src.adapters.normalized import (
    NormalizedCompetition,
    NormalizedMatch,
    NormalizedMatchStats,
    NormalizedTeam,
)
from src.db.schema import MatchStatus, Sport

log = logging.getLogger(__name__)

BASE = "https://api.collegefootballdata.com"


class CFBDAdapter(DataAdapter):
    source_name = "cfbd"
    supported_sports = frozenset({Sport.CFB})

    def __init__(self) -> None:
        key = os.getenv("CFBD_API_KEY", "")
        self._headers = {"Authorization": f"Bearer {key}"} if key else {}
        # year -> {school_name: team_source_id}, built lazily from /teams/fbs
        self._team_ids_by_year: dict[int, dict[str, str]] = {}

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{BASE}/{path}"
        resp = requests.get(url, headers=self._headers, params=params or {}, timeout=30)
        if resp.status_code == 429:
            log.warning("cfbd rate limited; sleeping 5s")
            time.sleep(5)
            resp = requests.get(url, headers=self._headers, params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _team_ids_for_year(self, year: int) -> dict[str, str]:
        if year not in self._team_ids_by_year:
            data = self._get("teams/fbs", params={"year": year})
            self._team_ids_by_year[year] = {
                t["school"]: str(t["id"])
                for t in data
                if t.get("id") is not None and t.get("school")
            }
        return self._team_ids_by_year[year]

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_competitions(self, sport: Sport) -> list[NormalizedCompetition]:
        if sport != Sport.CFB:
            return []
        return [NormalizedCompetition(
            sport=Sport.CFB, code="CFB", name="NCAA Division I FBS Football",
            area="USA", type="LEAGUE", source=self.source_name, source_id="fbs",
        )]

    def list_teams(self, competition_code: str, season: str | None = None) -> list[NormalizedTeam]:
        year = int(str(season).split("/")[0]) if season else datetime.utcnow().year
        data = self._get("teams/fbs", params={"year": year})
        out: list[NormalizedTeam] = []
        for t in data:
            tid, name = t.get("id"), t.get("school")
            if tid is None or not name:
                continue
            out.append(NormalizedTeam(
                sport=Sport.CFB, name=name, source=self.source_name,
                source_id=str(tid), short_name=t.get("abbreviation"),
                tla=t.get("abbreviation"), area="USA",
            ))
        return out

    # ------------------------------------------------------------------
    # Matches
    # ------------------------------------------------------------------

    def list_matches(
        self, competition_code: str, season: str | None = None,
        date_from: str | None = None, date_to: str | None = None,
    ) -> list[NormalizedMatch]:
        year = int(str(season).split("/")[0]) if season else datetime.utcnow().year
        data = self._get("games", params={
            "year": year, "seasonType": "regular", "classification": "fbs",
        })
        out: list[NormalizedMatch] = []
        for g in data:
            gid, home_id, away_id = g.get("id"), g.get("homeId"), g.get("awayId")
            start = g.get("startDate")
            if gid is None or home_id is None or away_id is None or not start:
                continue
            utc = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            utc = utc.astimezone(timezone.utc).replace(tzinfo=None) if utc.tzinfo else utc
            status = MatchStatus.FINISHED if g.get("completed") else MatchStatus.SCHEDULED
            out.append(NormalizedMatch(
                sport=Sport.CFB, competition_code="CFB", season=str(g.get("season") or year),
                utc_date=utc, status=status,
                home_team_source_id=str(home_id), away_team_source_id=str(away_id),
                source=self.source_name, source_id=str(gid),
                matchday=g.get("week"), stage=str(g.get("seasonType") or "") or None,
                home_score=g.get("homePoints"), away_score=g.get("awayPoints"),
            ))
        return out

    def get_match_stats(self, match_source_id: str) -> list[NormalizedMatchStats]:
        # Team-level box score not needed for the player-props use case.
        return []

    # ------------------------------------------------------------------
    # Player props (Phase 13.1)
    # ------------------------------------------------------------------

    def get_fixture_player_stats(self, fixture_source_id: str) -> list[dict]:
        """
        Per-player stats for ONE game, from /games/players?id=. Same return
        contract as APIFootballAdapter.get_fixture_player_stats (consumed
        generically by IngestionService.sync_player_match_stats):
          {"player_source_id", "player_name", "team_source_id", "minutes",
           "stats": {stat_key: float}}

        stat_key is "{category}_{type}" lowercased, e.g. "passing_yds",
        "rushing_td", "receiving_rec". Composite stats CFBD reports as a
        string (e.g. "C/ATT": "18-25") fail the float() parse and are
        skipped rather than guessed at.

        CFBD reports no snap/play count here, so `minutes` is always None
        — an honest gap, not a fabricated 0.
        """
        games = self._get("games", params={"id": fixture_source_id})
        if not games:
            return []
        year = games[0].get("season")
        team_ids = self._team_ids_for_year(year) if year else {}

        data = self._get("games/players", params={"id": fixture_source_id})
        # athlete_id -> {"name": str, "team_source_id": str, "stats": {...}}
        by_athlete: dict[str, dict] = {}
        for game in data:
            for team_block in game.get("teams", []):
                team_name = team_block.get("team")
                team_source_id = team_ids.get(team_name)
                if not team_source_id:
                    log.warning(
                        "cfbd: couldn't resolve team '%s' to a team_id for game %s — skipping its rows",
                        team_name, fixture_source_id,
                    )
                    continue
                for category in team_block.get("categories", []):
                    cat_name = (category.get("name") or "").lower()
                    for stat_type in category.get("types", []):
                        stat_name = (stat_type.get("name") or "").lower()
                        if not cat_name or not stat_name:
                            continue
                        stat_key = f"{cat_name}_{stat_name}"
                        for ath in stat_type.get("athletes", []):
                            aid, name = ath.get("id"), ath.get("name")
                            if not aid or not name:
                                continue
                            try:
                                value = float(ath.get("stat"))
                            except (TypeError, ValueError):
                                continue
                            entry = by_athlete.setdefault(aid, {
                                "name": name, "team_source_id": team_source_id, "stats": {},
                            })
                            entry["stats"][stat_key] = value

        return [
            {
                "player_source_id": aid,
                "player_name": info["name"],
                "team_source_id": info["team_source_id"],
                "minutes": None,
                "stats": info["stats"],
            }
            for aid, info in by_athlete.items()
        ]
