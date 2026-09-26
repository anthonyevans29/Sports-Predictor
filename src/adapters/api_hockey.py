"""
api-hockey adapter (H-track Phase 1, 2026-09-23) — cloned from the
american-football adapter's proven shape.

  - Base: v1.hockey.api-sports.io; NHL league id 57 (famous-club
    certified). Seasons are single-year ints (2026 = the 26-27 season).
  - Auth: API_HOCKEY_KEY, falling back to API_AMERICAN_FOOTBALL_KEY then
    API_FOOTBALL_KEY (bundled-plan key family).
  - Statuses: FT/AOT/ASO all map to FINISHED — scores include OT/SO by
    provider convention; the AOT/ASO distinction is preserved upstream in
    the raw status for Phase 2's OT-handling work via Match.stage capture.
  - Preseason: NOT filtered here — Phase 1 captures faithfully; exclusion
    happens at train/backtest time (the NFL preseason law).
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
    NormalizedOdds,
    NormalizedTeam,
)
from src.db.schema import MatchStatus, Sport

log = logging.getLogger(__name__)

DIRECT_BASE = "https://v1.hockey.api-sports.io"

#: NFL league id in the provider's catalog. (id 2 is NCAA.)
NHL_LEAGUE_ID = 57  # certified by famous-club receipt, Phase 0 2026-09-23

#: Provider game statuses -> our MatchStatus. Conservative: unknowns stay
#: SCHEDULED so the status filter never silently treats a live game as done.
_STATUS = {
    "NS": MatchStatus.SCHEDULED,       # not started
    "P1": MatchStatus.LIVE, "P2": MatchStatus.LIVE, "P3": MatchStatus.LIVE,
    "OT": MatchStatus.LIVE, "PT": MatchStatus.LIVE, "BT": MatchStatus.LIVE,
    "SO": MatchStatus.LIVE,            # shootout in progress
    "FT": MatchStatus.FINISHED,
    "AOT": MatchStatus.FINISHED,       # after overtime (Phase 0 receipt)
    "ASO": MatchStatus.FINISHED,       # after shootout
    "AP": MatchStatus.FINISHED,        # after penalty-shootout — the REAL
                                       # provider code (vocabulary Counter
                                       # 2026-09-23: 79 in 2024 = the ghost
                                       # count exactly; ASO was a memory
                                       # guess, kept harmlessly)
    "POST": MatchStatus.POSTPONED, "PST": MatchStatus.POSTPONED,
    "CANC": MatchStatus.CANCELLED,
}


class APIHockeyAdapter(DataAdapter):
    source_name = "api_hockey"
    supported_sports = frozenset({Sport.NHL})

    def __init__(self) -> None:
        key = (os.getenv("API_HOCKEY_KEY")
               or os.getenv("API_FOOTBALL_KEY") or "")
        self._headers = {"x-apisports-key": key}
        self._requests_remaining: int | None = None

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{DIRECT_BASE}/{path}"
        resp = requests.get(url, headers=self._headers, params=params or {},
                            timeout=30)
        if resp.status_code == 429:
            log.warning("api_hockey rate limited; sleeping 5s")
            time.sleep(5)
            resp = requests.get(url, headers=self._headers,
                                params=params or {}, timeout=30)
        resp.raise_for_status()
        rem = resp.headers.get("x-ratelimit-requests-remaining")
        if rem is not None:
            try:
                self._requests_remaining = int(rem)
            except ValueError:
                pass
        data = resp.json()
        errs = data.get("errors")
        if errs and (errs if isinstance(errs, list) else list(errs.values())):
            raise RuntimeError(f"api_hockey {path}: {errs}")
        return data

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_competitions(self, sport: Sport) -> list[NormalizedCompetition]:
        if sport != Sport.NHL:
            return []
        return [NormalizedCompetition(
            sport=Sport.NHL, code="NHL", name="National Hockey League",
            area="USA", type="LEAGUE", source=self.source_name,
            source_id=str(NHL_LEAGUE_ID),
        )]

    def list_teams(self, competition_code: str,
                   season: str | None = None) -> list[NormalizedTeam]:
        params = {"league": NHL_LEAGUE_ID,
                  "season": int(season) if season else datetime.utcnow().year}
        data = self._get("teams", params=params)
        out: list[NormalizedTeam] = []
        for item in data.get("response") or []:
            # response items are either flat team dicts or {"team": {...}}
            t = item.get("team") if isinstance(item.get("team"), dict) else item
            tid, name = t.get("id"), t.get("name")
            if tid is None or not name:
                continue
            out.append(NormalizedTeam(
                sport=Sport.NHL, name=name, source=self.source_name,
                source_id=str(tid), short_name=t.get("code"),
                tla=t.get("code"), area="USA",
            ))
        return out

    # ------------------------------------------------------------------
    # Matches
    # ------------------------------------------------------------------

    def list_matches(self, competition_code: str, season: str | None = None,
                     date_from: str | None = None,
                     date_to: str | None = None) -> list[NormalizedMatch]:
        params: dict[str, Any] = {"league": NHL_LEAGUE_ID}
        if season:
            # Tolerate both "2026" and "2026/27" — the league year is the
            # first component either way (belt-and-braces vs format drift).
            params["season"] = int(str(season).split("/")[0])
        if date_from and date_from == date_to:
            params["date"] = date_from
        data = self._get("games", params=params)
        out: list[NormalizedMatch] = []
        for g in data.get("response") or []:
            game = g.get("game") or g
            teams = g.get("teams") or {}
            scores = g.get("scores") or {}
            gid = game.get("id")
            dt_block = game.get("date") or {}
            # provider gives {"date": "...", "time": "...", "timestamp": ...}
            ts = dt_block.get("timestamp") if isinstance(dt_block, dict) else None
            if ts:
                utc = datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None)
            else:
                raw = dt_block if isinstance(dt_block, str) else dt_block.get("date")
                if not raw:
                    continue
                utc = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                utc = utc.astimezone(timezone.utc).replace(tzinfo=None) if utc.tzinfo else utc
            status_block = game.get("status") or {}
            # raw provider code BEFORE the "NS" default: an absent status must
            # stay absent in status_raw (conservative unknowns), not become "NS"
            raw_short = (status_block.get("short") if isinstance(status_block, dict)
                         else (str(status_block) if status_block else None))
            short = raw_short or "NS"
            home = (teams.get("home") or {})
            away = (teams.get("away") or {})
            if gid is None or home.get("id") is None or away.get("id") is None:
                continue
            week_raw = game.get("week")
            matchday = None
            if week_raw is not None:
                digits = "".join(c for c in str(week_raw) if c.isdigit())
                matchday = int(digits) if digits else None
            # Falsy-zero trap fixed (2026-09-23): hockey scores are bare
            # ints; `or {}` turned a shutout side's 0 into {} -> parsed
            # None -> 302 FT-null rows + the scattered SCHEDULED ghosts.
            hs = scores.get("home")
            as_ = scores.get("away")
            _h_total = hs.get("total") if isinstance(hs, dict) else hs
            _a_total = as_.get("total") if isinstance(as_, dict) else as_
            status = _STATUS.get(short, MatchStatus.SCHEDULED)
            # Score-presence beats status-absence (2026-09-05): 16 of 2024's
            # games arrive with NO status block at all but full final totals.
            # A game with both totals and no status claim is finished with
            # lazy upstream metadata — infer, but ONLY when status is absent,
            # never over an explicit live/scheduled short.
            if (short in (None, "", "None") and _h_total is not None
                    and _a_total is not None):
                status = MatchStatus.FINISHED
            out.append(NormalizedMatch(
                sport=Sport.NHL, competition_code="NHL",
                season=str(params.get("season", "")),
                utc_date=utc,
                status=status,
                home_team_source_id=str(home["id"]),
                away_team_source_id=str(away["id"]),
                source=self.source_name, source_id=str(gid),
                matchday=matchday,
                stage=str(game.get("stage") or "") or None,
                # the raw code the _STATUS map collapses (FT vs AOT vs AP):
                # OT/SO wins become distinguishable (H2 groundwork, 2026-09-26)
                status_raw=(raw_short if raw_short not in (None, "", "None") else None),
                home_score=hs.get("total") if isinstance(hs, dict) else hs,
                away_score=as_.get("total") if isinstance(as_, dict) else as_,
            ))
        return out

    def get_match_stats(self, match_source_id: str) -> list[NormalizedMatchStats]:
        # Phase 2+ (team stats feed the eventual model; not wired yet).
        return []

    # ------------------------------------------------------------------
    # Odds — same market taxonomy the rest of the system speaks
    # ------------------------------------------------------------------

    _MARKET_MAP = {
        # provider bet names -> our market labels (observed api-sports naming;
        # verified/extended from the first live pull's console)
        "Home/Away": "1X2",
        "Moneyline": "1X2",
        "Over/Under": "TOTALS",
        "Total Points": "TOTALS",
        "Asian Handicap": "SPREADS",
        "Point Spread": "SPREADS",
        "Handicap": "SPREADS",
    }

    def list_odds(self, match_source_id: str) -> list[NormalizedOdds]:
        data = self._get("odds", params={"game": match_source_id})
        now = datetime.utcnow()
        out: list[NormalizedOdds] = []
        for block in data.get("response") or []:
            for book in block.get("bookmakers") or []:
                book_name = book.get("name") or f"book_{book.get('id')}"
                for bet in book.get("bets") or []:
                    market = self._MARKET_MAP.get(bet.get("name") or "")
                    if market is None:
                        continue
                    for val in bet.get("values") or []:
                        raw_sel = str(val.get("value") or "")
                        price = val.get("odd")
                        try:
                            price_f = float(price)
                        except (TypeError, ValueError):
                            continue
                        sel, line = self._normalize_selection(market, raw_sel)
                        if sel is None:
                            continue
                        out.append(NormalizedOdds(
                            match_source_id=str(match_source_id),
                            source=self.source_name, bookmaker=book_name,
                            market=market, selection=sel,
                            price_decimal=price_f, captured_at=now,
                            line=line,
                        ))
        return out

    @staticmethod
    def _normalize_selection(market: str, raw: str) -> tuple[str | None, float | None]:
        r = raw.strip()
        if market == "1X2":
            if r.lower() in ("home", "1"):
                return "HOME", None
            if r.lower() in ("away", "2"):
                return "AWAY", None
            return None, None  # NFL moneylines have no draw leg
        low = r.lower()
        line = None
        # Preserve the SIGN — a spread of -3.5 and +3.5 are opposite bets.
        num = "".join(c for c in r if c.isdigit() or c in ".-+")
        num = num.lstrip("+")
        if num:
            try:
                line = float(num)
            except ValueError:
                line = None
        if market == "TOTALS":
            if low.startswith("over"):
                return "OVER", line
            if low.startswith("under"):
                return "UNDER", line
            return None, None
        if market == "SPREADS":
            if low.startswith("home"):
                return "HOME", line
            if low.startswith("away"):
                return "AWAY", line
            return None, None
        return None, None

    def list_injuries(self, team_source_id: str, season: str) -> list[dict]:
        """
        Current injury/status report for a team (NFL phase 1c, 2026-09-06).
        QB status is to NFL what pitcher confirmation is to MLB — this feeds
        the same Injury table and sync path the soccer side uses.

        Contract (mirrors api_football.list_injuries): one dict per player —
        player_name, player_position, reason, type, fixture_source_id,
        fixture_date. The provider's /injuries is a current-status feed (not
        fixture history), so no per-fixture dedupe is needed; we stamp
        fixture_date with the report date the provider gives (or None) and
        let the service's 14-day freshness filter do its normal job.
        """
        # Provider quirks (verified live 2026-09-06/09): /injuries REJECTS a
        # season param ("The Season field do not exist") AND carries NO
        # position field anywhere (player = id/name/image only — raw probe
        # 2026-09-09). Position lives on the roster endpoint, so we fetch
        # the team's roster alongside and join by provider player id. One
        # extra request per team (~64/sync total); roster misses leave
        # position None, which the export treats honestly.
        pos_by_id: dict[int, str] = {}
        try:
            roster = self._get("players", params={
                "team": team_source_id,
                "season": int(str(season).split("/")[0]),
            }).get("response") or []
            for rp in roster:
                p = rp.get("player") if isinstance(rp.get("player"), dict) else rp
                pid, pos = p.get("id"), (p.get("position") or p.get("group"))
                if pid is not None and pos:
                    pos_by_id[pid] = str(pos)
        except Exception as e:  # roster enrichment is best-effort
            log.warning("roster fetch failed for team %s: %s", team_source_id, e)
        data = self._get("injuries", params={"team": team_source_id})
        out: list[dict] = []
        seen: set[str] = set()
        for item in data.get("response") or []:
            player = item.get("player") or {}
            name = (player.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append({
                "player_name": name,
                "player_position": pos_by_id.get(player.get("id")),
                "reason": item.get("description") or item.get("reason"),
                "type": item.get("status") or item.get("type"),
                "fixture_source_id": None,
                "fixture_date": item.get("date"),
            })
        return out

    @property
    def requests_remaining(self) -> int | None:
        return self._requests_remaining
