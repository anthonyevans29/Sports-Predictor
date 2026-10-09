"""
API-American-Football client (api-sports.io) — the NFL DataAdapter.

NFL PHASE 1 (2026-09-05): data wiring only. This adapter is the canonical
source for NFL teams, schedules, scores, and odds, mirroring API-Football's
role for soccer. No model consumes any of this yet — per house discipline,
tracking starts Week 1 while the model earns its way in via backtest and
dress rehearsal (see backlog: NFL plan).

Design notes, learned the hard way elsewhere in this codebase:
  - Season format: NFL uses single calendar year ("2026") — the league year
    that starts in September. The cup single-year/two-year confusion (EFL,
    2026-08-27) is why this is stated at the top of the file.
  - The provider's game statuses differ from soccer's; _STATUS maps them
    conservatively — anything unknown becomes SCHEDULED rather than
    guessed-finished, so the export status filter fails safe.
  - Odds arrive via the same market shapes as api_baseball (moneyline /
    totals / spreads); the late-publication behavior for games beyond the
    provider's current day (M11) is ASSUMED to apply here too until
    observed otherwise — Kalshi remains the designed live stand-in.
  - Auth: API_AMERICAN_FOOTBALL_KEY, falling back to API_FOOTBALL_KEY
    (api-sports multi-sport subscriptions share keys).

Week semantics: the provider exposes "stage" (Pre Season / Regular Season /
Post Season) and "week" strings. We store stage in NormalizedMatch.stage and
parse the numeric week into matchday where possible — the weekly cadence
(NFL's soccer-like rhythm) keys on it.
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
from src.timeutil import utc_now_naive

log = logging.getLogger(__name__)

# Non-competitive exclusion (architect ruling 2026-09-27, H1a compare): the
# provider files the Pro Bowl (AFC vs NFC) inside the NFL league. It showed up
# as +1 game/season and 34 teams on the fresh host. These rows are exhibitions:
# they would enter the Elo walk, grading and scope counts. nfl_backtest's
# scope_line already raises a SCOPE ALERT when teams != 32, so they could not
# pass silently, but the right fix is not ingesting them. Markers are generic
# on purpose (conference all-star sides, "pro bowl" / "all-star" in the team
# name, week or stage). Every excluded row is printed as a receipt.
_ALLSTAR_TEAM_NAMES = {"AFC", "NFC"}
_ALLSTAR_MARKERS = ("PRO BOWL", "PROBOWL", "ALL-STAR", "ALL STAR", "ALLSTAR")


def _non_competitive(*texts, team_names=()) -> str | None:
    """Reason string when a game/team is an all-star exhibition, else None."""
    for n in team_names:
        if str(n or "").strip().upper() in _ALLSTAR_TEAM_NAMES:
            return f"all-star side {str(n).strip()!r}"
    for s in (*team_names, *texts):
        u = str(s or "").upper()
        for m in _ALLSTAR_MARKERS:
            if m in u:
                return f"marker {m.lower()!r} in {str(s).strip()!r}"
    return None

DIRECT_BASE = "https://v1.american-football.api-sports.io"

#: NFL league id in the provider's catalog. (id 2 is NCAA.)
NFL_LEAGUE_ID = 1
# 2026-09-25: second league in the family. id=2 receipted by Phase 0
# probe (260 teams FBS+FCS, Michigan State/Nebraska in list, ~1,500
# games/season, weeks numeric, FT/AOT/CANC + None-status class).
_CODE_TO_LEAGUE = {"NFL": NFL_LEAGUE_ID, "NCAA": 2}
def _league_for(code: str) -> int:
    return _CODE_TO_LEAGUE.get((code or "NFL").upper(), NFL_LEAGUE_ID)

#: Provider game statuses -> our MatchStatus. Conservative: unknowns stay
#: SCHEDULED so the status filter never silently treats a live game as done.
_STATUS = {
    "NS": MatchStatus.SCHEDULED,      # not started
    "Q1": MatchStatus.LIVE, "Q2": MatchStatus.LIVE,
    "Q3": MatchStatus.LIVE, "Q4": MatchStatus.LIVE,
    "OT": MatchStatus.LIVE, "HT": MatchStatus.LIVE,
    "FT": MatchStatus.FINISHED, "AOT": MatchStatus.FINISHED,
    "POST": MatchStatus.POSTPONED, "CANC": MatchStatus.CANCELLED,
}


class RateLimited(RuntimeError):
    """The provider still answered 429 after the in-call retry."""

    def __init__(self, path: str, retry_after: float):
        super().__init__(f"rate limited on {path}; retry after {retry_after:.0f}s")
        self.retry_after = retry_after


class APIAmericanFootballAdapter(DataAdapter):
    source_name = "api_american_football"
    supported_sports = frozenset({Sport.NFL})

    def __init__(self) -> None:
        key = (os.getenv("API_AMERICAN_FOOTBALL_KEY")
               or os.getenv("API_FOOTBALL_KEY") or "")
        self._headers = {"x-apisports-key": key}
        self._requests_remaining: int | None = None

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict:
        """One retry after 5s on a 429; a SECOND 429 raises RateLimited
        (retry_after from the provider's Retry-After header, else 60s) so a
        caller can defer the item and retry after the window instead of
        dropping it (ARCHITECT 2026-10-03: sync-odds-football)."""
        url = f"{DIRECT_BASE}/{path}"
        resp = requests.get(url, headers=self._headers, params=params or {},
                            timeout=30)
        if resp.status_code == 429:
            log.warning("api_american_football rate limited; sleeping 5s")
            time.sleep(5)
            resp = requests.get(url, headers=self._headers,
                                params=params or {}, timeout=30)
            if resp.status_code == 429:
                try:
                    wait = float(resp.headers.get("Retry-After") or 60)
                except ValueError:
                    wait = 60.0
                raise RateLimited(path, wait)
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
            raise RuntimeError(f"api_american_football {path}: {errs}")
        return data

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_competitions(self, sport: Sport) -> list[NormalizedCompetition]:
        if sport != Sport.NFL:
            return []
        return [
            NormalizedCompetition(
                sport=Sport.NFL, code="NFL", name="National Football League",
                area="USA", type="LEAGUE", source=self.source_name,
                source_id=str(NFL_LEAGUE_ID),
            ),
            NormalizedCompetition(
                sport=Sport.NFL, code="NCAA", name="NCAA Football",
                area="USA", type="LEAGUE", source=self.source_name,
                source_id=str(_CODE_TO_LEAGUE["NCAA"]),
            ),
        ]

    def list_teams(self, competition_code: str,
                   season: str | None = None) -> list[NormalizedTeam]:
        params = {"league": _league_for(competition_code),
                  "season": int(season) if season else utc_now_naive().year}
        data = self._get("teams", params=params)
        out: list[NormalizedTeam] = []
        for item in data.get("response") or []:
            # response items are either flat team dicts or {"team": {...}}
            t = item.get("team") if isinstance(item.get("team"), dict) else item
            tid, name = t.get("id"), t.get("name")
            if tid is None or not name:
                continue
            why = _non_competitive(team_names=(name,))
            if why:
                print(f"  excluded non-competitive team: id={tid} {name!r} ({why})", flush=True)
                continue
            out.append(NormalizedTeam(
                sport=Sport.NFL, name=name, source=self.source_name,
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
        params: dict[str, Any] = {"league": _league_for(competition_code)}
        if season:
            # Tolerate both "2026" and "2026/27" — the league year is the
            # first component either way (belt-and-braces vs format drift).
            params["season"] = int(str(season).split("/")[0])
        if date_from and date_from == date_to:
            params["date"] = date_from
        data = self._get("games", params=params)
        return self._parse_games(data, competition_code, str(params.get("season", "")))

    def get_game(self, source_id: str, competition_code: str = "NCAA") -> tuple[bool, NormalizedMatch | None]:
        """(exists, match) for ONE provider game id (GET /games?id=). exists=False
        = the provider returns no game for the id (a retired id: dedupe-matches
        --orphans, ARCHITECT 2026-10-03). exists=True with match=None = the game
        exists but is filtered (non-competitive). Raises on HTTP / RateLimited —
        the caller treats that as UNRESOLVED, never as absent."""
        data = self._get("games", params={"id": source_id})
        if not (data.get("response") or []):
            return False, None
        got = self._parse_games(data, competition_code, "")
        return True, (got[0] if got else None)

    def _parse_games(self, data: dict, competition_code: str, season: str) -> list[NormalizedMatch]:
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
            short = (status_block.get("short") if isinstance(status_block, dict)
                     else str(status_block)) or "NS"
            home = (teams.get("home") or {})
            away = (teams.get("away") or {})
            if gid is None or home.get("id") is None or away.get("id") is None:
                continue
            week_raw = game.get("week")
            why = _non_competitive(week_raw, game.get("stage"),
                                   team_names=(home.get("name"), away.get("name")))
            if why:
                print(f"  excluded non-competitive game: id={gid} {utc:%Y-%m-%d} "
                      f"{home.get('name')!r} v {away.get('name')!r} "
                      f"(week={week_raw!r}, stage={game.get('stage')!r}; {why})", flush=True)
                continue
            matchday = None
            if week_raw is not None:
                digits = "".join(c for c in str(week_raw) if c.isdigit())
                matchday = int(digits) if digits else None
            hs = (scores.get("home") or {})
            as_ = (scores.get("away") or {})
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
                sport=Sport.NFL, competition_code=(competition_code or "NFL").upper(),
                season=season,
                utc_date=utc,
                status=status,
                home_team_source_id=str(home["id"]),
                away_team_source_id=str(away["id"]),
                source=self.source_name, source_id=str(gid),
                matchday=matchday,
                stage=str(game.get("stage") or "") or None,
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
        now = utc_now_naive()
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
        marks each row current_status=True: membership in this feed is the
        truth, so the service's 14-day fixture-date filter does not apply.
        """
        # Provider quirks (verified live 2026-09-06/09): /injuries REJECTS a
        # season param ("The Season field do not exist") AND carries NO
        # position field anywhere (player = id/name/image only — raw probe
        # 2026-09-09). Position lives on the roster endpoint, so we fetch
        # the team's roster alongside and join by provider player id. One
        # extra request per team (~64/sync total); roster misses leave
        # position None, which the export treats honestly.
        # QB audit (architect 2026-09-29): positions resolve through
        # src/walters/qb_audit (by id, then exact name, then a UNIQUE
        # initial+surname); the feed is current-status, so each row carries
        # current_status=True and the service's 14-day fixture-date filter
        # (a fixture-history rule) no longer drops a player still listed.
        # A2 (ARCHITECT 2026-10-09, addendum 23): "In strict mode a failed roster read is a failed read. The QB
        # flag halves a PLAY, and a flag we could not look up is not a flag that is off. The adapter records the
        # failure; its default behaviour does not change." Recorded on `last_roster_failure` (None = the roster
        # read answered with players) for this call; the service lists it in failed_reads, which only a
        # command's --strict reads. An empty roster is recorded too: no position can resolve from it.
        from src.walters.qb_audit import resolve_position, roster_index
        self.last_roster_failure = None
        roster: list = []
        try:
            roster = self._get("players", params={
                "team": team_source_id,
                "season": int(str(season).split("/")[0]),
            }).get("response") or []
        except Exception as e:  # roster enrichment is best-effort
            log.warning("roster fetch failed for team %s: %s", team_source_id, e)
            self.last_roster_failure = f"roster fetch failed: {type(e).__name__}"
        if not roster:
            log.warning("NFL roster empty for team %s — injured players' positions "
                        "stay None (qb_listed cannot see a QB)", team_source_id)
            self.last_roster_failure = self.last_roster_failure or "roster empty"
        idx = roster_index(roster)
        data = self._get("injuries", params={"team": team_source_id})
        out: list[dict] = []
        seen: set[str] = set()
        for item in data.get("response") or []:
            player = item.get("player") or {}
            name = (player.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            position, _how = resolve_position(player, idx)
            out.append({
                "player_name": name,
                "player_position": position,
                "reason": item.get("description") or item.get("reason"),
                "type": item.get("status") or item.get("type"),
                "fixture_source_id": None,
                "fixture_date": item.get("date"),
                "current_status": True,
            })
        return out

    @property
    def requests_remaining(self) -> int | None:
        return self._requests_remaining
