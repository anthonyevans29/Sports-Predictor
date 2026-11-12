"""
api-basketball adapter (ARCHITECT 2026-11-06 12:35 ET, addendum 271 item 3; lane basketball-market-only, #839) —
cloned from api_hockey's proven shape (itself cloned from the american-football adapter), with the receipt's
differences ruled in 271 item 3(a)-(g). The NBA (#848; addendum 272 item 5: "The wiring PR of 11-19 is NBA-only
[...]; NCAA men's follows it at 12-05 on the same adapter") and NCAA men's, NCAAMB (ARCHITECT 2026-11-12, addendum 352
item 2, the plan approved; the same adapter, nothing else in it changes).

  (a) source_name 'api_basketball', Sport.BASKETBALL, base v1.basketball.api-sports.io, the x-apisports-key header.
      THE KEY (271 item 2): "API_BASKETBALL_KEY first, API_FOOTBALL_KEY as the fallback — exactly the hockey adapter's
      pattern and exactly what the probe did". `key_name` says which NAME was read; the value is never printed.
  THE LEAGUE: the code -> provider league id map, each READ by exact name on #839's receipt: NBA, id 12 (2026-11-06
      17:14Z: "NBA: id 12 read by exact name 'NBA'"); NCAAMB, id 116 (17:18Z: "NCAA men's Division I: id 116 read by
      exact name 'NCAA'"). Every /leagues read re-checks that the served league with that id carries exactly the
      map's name; any other competition code is REFUSED (never served one league's games under another code, which
      api_hockey's ignored competition_code would do).
  (b) THE SEASON: "the provider serves NBA and NCAA seasons as STRINGS '2026-2027' [...] the hockey adapter's
      int(season) does NOT carry over. Our season string stays int-style "2026" [...]; the adapter picks the
      provider's season by reading /leagues for the league and taking the served season that STARTS with our year
      ('2026-2027' for "2026"); none served → refuse, never compute one." /leagues is read with NO parameter (the
      probe's call, 428 items: no filter vocabulary is read, law 1), once per adapter instance. A missing season is a
      refusal too (api_hockey's utc-year default computes one). The stored season is OURS ("2026"), never the
      provider's string.
  (c) THE STATUS MAP, by SHORT code (_STATUS): NS, FT, AOT (FINISHED; the overtime flag is status_raw 'AOT', the
      hockey AOT precedent), CANC (both long forms), POST. Every other code stays SCHEDULED with its code kept in
      status_raw (counted on the certification receipt); NO live code is mapped; an absent status stays SCHEDULED
      with status_raw None, and no score-presence inference is made (it is not in 3(c)).
  (d) THE DATE: the kickoff is the served top-level `timestamp` (UTC), else the served ISO date with its offset; a
      date with no offset is never given a zone (the listing is dropped and counted). A range (date_from ≠ date_to)
      is never sent upstream: the whole season's listing is read, and a RANGE line says so before the fetch.
  (g) THE SCORES: home/away_score = scores.<side>.total as served (a 0 stays 0: api_hockey's falsy-zero lesson).
      THE QUARTERS ARE NOT KEPT (ARCHITECT 2026-11-06, addendum 274 item 2(10): "the transient reading STANDS;
      nothing is kept, no file under exports/, no column"; 271 item 3(g) CORRECTED to "not persisted"):
      quarter_1..4 and over_time are read nowhere and written nowhere; the served item rides NormalizedMatch.raw
      for the sync's life only and is gone when it exits.
  METERING (3(f)): each call prints one line with the provider's x-ratelimit-requests-remaining as served.
  NO /odds: list_odds is NOT overridden (base: [] with no call); /odds for basketball was never probed.
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections import Counter
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

DIRECT_BASE = "https://v1.basketball.api-sports.io"
KEY_NAMES = ("API_BASKETBALL_KEY", "API_FOOTBALL_KEY")      # 271 item 2: the product key, then the shared key
KEY_HEADER = "x-apisports-key"
REMAINING_HEADER = "x-ratelimit-requests-remaining"

#: Our competition code -> (the provider's league id, its served name). READ on #839's receipt by exact name
#: (2026-11-06 17:14Z, "NBA: id 12 read by exact name 'NBA'"), re-checked on every /leagues read.
#: NCAAMB (ARCHITECT 2026-11-05, addendum 261 item 1(c): "competition code NCAAMB (never "NCAA", which is football),
#: the same adapter"; 2026-11-12, addendum 352 item 2, the plan approved): league 116, READ on #839's receipt by exact
#: served name (2026-11-06 17:18Z, "NCAA men's Division I: id 116 read by exact name 'NCAA'"; 'NCAA Women' is league
#: 423 and not ours). The served name is 'NCAA'; our code is NCAAMB, so nothing keyed on the football code "NCAA"
#: reads it (every check on that code is an exact match).
LEAGUES: dict[str, tuple[int, str]] = {"NBA": (12, "NBA"), "NCAAMB": (116, "NCAA")}
#: The competition rows list_competitions emits, by our code: (name, area), the area as /leagues serves it.
_COMPETITIONS = {"NBA": ("National Basketball Association", "USA"),
                 "NCAAMB": ("NCAA Men's Basketball (Division I)", "USA")}

#: THE STATUS MAP (271 item 3(c)), by the served SHORT code. Conservative: every other code stays SCHEDULED (law 4);
#: no live code is mapped until a live-day receipt names them.
_STATUS = {
    "NS": MatchStatus.SCHEDULED,       # Not Started
    "FT": MatchStatus.FINISHED,        # Game Finished
    "AOT": MatchStatus.FINISHED,       # After Over Time: the overtime flag is status_raw 'AOT' (the hockey precedent)
    "CANC": MatchStatus.CANCELLED,     # both long forms served ('Cancelled', 'Game Cancelled'); keyed on the short
    "POST": MatchStatus.POSTPONED,     # Game Postponed (the NCAA receipt's code)
}

OUR_SEASON = re.compile(r"^\d{4}$")


class Refused(RuntimeError):
    """A read the adapter will not make or cannot place (a competition it does not serve, a season it will not
    compute, a league whose served name does not match). The message starts REFUSED and names why."""


def map_status(short: str | None) -> MatchStatus:
    """The ruled map (271 item 3(c)): the served short code -> our status; anything else (absent included) SCHEDULED."""
    return _STATUS.get(short, MatchStatus.SCHEDULED) if short else MatchStatus.SCHEDULED


def served_short(item: dict) -> str | None:
    """The served status SHORT code verbatim, None when absent (read before any default: an absent status stays
    absent in status_raw)."""
    game = item.get("game") if isinstance(item.get("game"), dict) else item
    st = game.get("status")
    raw = st.get("short") if isinstance(st, dict) else (str(st) if st not in (None, "") else None)
    return None if raw in (None, "", "None") else str(raw)


def kickoff_utc(item: dict) -> datetime | None:
    """271 item 3(d): the served top-level `timestamp` (seconds, UTC) first; else the served ISO date carrying its
    offset, converted to UTC. Naive UTC out (the matches column's convention). None when neither is readable: a date
    with no offset is never given a zone by assumption."""
    game = item.get("game") if isinstance(item.get("game"), dict) else item
    ts = game.get("timestamp")
    d = game.get("date")
    if ts is None and isinstance(d, dict):            # tolerated: a nested date block (api_hockey's shape)
        ts = d.get("timestamp")
    if ts is not None and not isinstance(ts, bool):
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    raw = d.get("date") if isinstance(d, dict) else d
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def side_total(scores: Any, side: str):
    """scores.<side>.total as served (a bare value tolerated); no falsy default: a 0 stays 0."""
    x = scores.get(side) if isinstance(scores, dict) else None
    return x.get("total") if isinstance(x, dict) else x


def league_parts(item: dict) -> tuple[dict, list]:
    """(league, seasons) of a /leagues item, flat or nested under "league" (the probe's league_parts); each season
    as served, read from a {"season": ...} item or a bare value."""
    lg = item.get("league") if isinstance(item.get("league"), dict) else item
    seasons = item.get("seasons") or lg.get("seasons") or []
    if not isinstance(seasons, list):
        seasons = []
    return lg, [s.get("season") if isinstance(s, dict) else s for s in seasons]


def pick_season(served: list, ours: str) -> Any:
    """271 item 3(b): the ONE served season that STARTS with our year ('2026-2027' for "2026"; a served 2026 too),
    the next character, if any, not a digit. As served (never re-typed). None served, or several: Refused, the served
    list in the message. Never computed."""
    hits = [s for s in served if s is not None and str(s).startswith(ours)
            and (len(str(s)) == len(ours) or not str(s)[len(ours)].isdigit())]
    if len(hits) == 1:
        return hits[0]
    listed = ", ".join(repr(s) for s in served) or "none"
    if not hits:
        raise Refused(f"REFUSED: no served season starts with {ours!r} (served: {listed}); the adapter never computes "
                      "one (addendum 271 item 3(b))")
    raise Refused(f"REFUSED: {len(hits)} served seasons start with {ours!r} ({', '.join(repr(s) for s in hits)}); "
                  "exactly one required (addendum 271 item 3(b))")


class APIBasketballAdapter(DataAdapter):
    source_name = "api_basketball"
    supported_sports = frozenset({Sport.BASKETBALL})

    #: Whether this instance's listings are written (sync-matches) or only read: the range note says which (the
    #: american-football adapter's #570 note).
    listing_writes = True

    def __init__(self) -> None:
        self.key_name: str | None = next((n for n in KEY_NAMES if (os.getenv(n) or "").strip()), None)
        key = (os.getenv(self.key_name) or "").strip() if self.key_name else ""
        self._headers = {KEY_HEADER: key}
        self._requests_remaining: int | None = None
        self._leagues: list | None = None
        self.calls = 0
        #: the last list_teams / list_matches read's dropped listings: reason -> [provider ids] (law 4: counted)
        self.last_dropped: dict[str, list] = {}

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{DIRECT_BASE}/{path}"
        resp = requests.get(url, headers=self._headers, params=params or {}, timeout=30)
        self.calls += 1
        if resp.status_code == 429:
            # 3(f): the rate-limited answer is a provider request too: counted above, and metered on its own line
            rem429 = resp.headers.get(REMAINING_HEADER)
            print(f"api_basketball /{path} {params or {}} · HTTP 429 · rate limited, one retry in 5s · "
                  f"{REMAINING_HEADER} {rem429 if rem429 is not None else 'not served'}", flush=True)
            log.warning("api_basketball rate limited; sleeping 5s")
            time.sleep(5)
            resp = requests.get(url, headers=self._headers, params=params or {}, timeout=30)
            self.calls += 1
        resp.raise_for_status()
        rem = resp.headers.get(REMAINING_HEADER)
        if rem is not None:
            try:
                self._requests_remaining = int(rem)
            except ValueError:
                pass
        data = resp.json()
        items = data.get("response") if isinstance(data, dict) else None
        n = len(items) if isinstance(items, list) else "?"
        # 3(f): every API-Sports run prints the day's remaining requests, as served
        print(f"api_basketball /{path} {params or {}} · HTTP {resp.status_code} · {n} items · "
              f"{REMAINING_HEADER} {rem if rem is not None else 'not served'}", flush=True)
        errs = data.get("errors") if isinstance(data, dict) else None
        if errs and (errs if isinstance(errs, list) else list(errs.values())):
            raise RuntimeError(f"api_basketball {path}: {errs}")
        return data

    # ------------------------------------------------------------------
    # The league and the season (271 item 3(b))
    # ------------------------------------------------------------------

    @staticmethod
    def league_id(competition_code: str) -> int:
        hit = LEAGUES.get(str(competition_code or "").upper())
        if hit is None:
            raise Refused(f"REFUSED: competition {competition_code!r} is not served by api_basketball (the map holds "
                          f"{', '.join(LEAGUES)} only; NCAA men's basketball is NCAAMB, never NCAA)")
        return hit[0]

    def leagues(self) -> list:
        """/leagues, no parameter (the probe's call), read once per instance."""
        if self._leagues is None:
            items = self._get("leagues").get("response")
            self._leagues = items if isinstance(items, list) else []
        return self._leagues

    def served_seasons(self, competition_code: str) -> list:
        """The seasons /leagues serves for the competition's league, as served and in served order. Refused unless
        exactly one served league carries the id and its served name is exactly the map's."""
        self.league_id(competition_code)                     # refuses a code the map does not hold
        lid, name = LEAGUES[str(competition_code).upper()]
        hits = []
        for it in self.leagues():
            if isinstance(it, dict):
                lg, seasons = league_parts(it)
                if lg.get("id") == lid:
                    hits.append((lg, seasons))
        if len(hits) != 1:
            raise Refused(f"REFUSED: /leagues serves {len(hits)} leagues with id {lid} (exactly one required)")
        lg, seasons = hits[0]
        if str(lg.get("name") or "") != name:
            raise Refused(f"REFUSED: /leagues names league {lid} {lg.get('name')!r}, not {name!r} (the id was read by "
                          "exact name on #839's receipt; a different name is not guessed through)")
        return seasons

    def provider_season(self, competition_code: str, season: str | None) -> Any:
        """Our int-style season ("2026") -> the provider's served season ('2026-2027'), by 271 item 3(b)."""
        self.league_id(competition_code)
        ours = str(season).strip() if season is not None else ""
        if not ours:
            raise Refused("REFUSED: a season is required (int-style, e.g. --season 2026); the adapter never computes "
                          "one (addendum 271 item 3(b))")
        if not OUR_SEASON.match(ours):
            raise Refused(f"REFUSED: season {season!r} is not int-style (our NBA season string is the start year, "
                          "e.g. \"2026\" for 2026-27; addendum 261 item 1(b))")
        return pick_season(self.served_seasons(competition_code), ours)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_competitions(self, sport: Sport) -> list[NormalizedCompetition]:
        if sport != Sport.BASKETBALL:
            return []
        # area: /leagues serves the country as 'USA' (#839's receipt), for the NBA and for NCAA men's
        return [NormalizedCompetition(
            sport=Sport.BASKETBALL, code=code, name=_COMPETITIONS[code][0], area=_COMPETITIONS[code][1],
            type="LEAGUE", source=self.source_name, source_id=str(LEAGUES[code][0]),
        ) for code in LEAGUES]

    def list_teams(self, competition_code: str,
                   season: str | None = None) -> list[NormalizedTeam]:
        served = self.provider_season(competition_code, season)
        data = self._get("teams", params={"league": self.league_id(competition_code), "season": served})
        out: list[NormalizedTeam] = []
        dropped: dict[str, list] = {}
        for item in data.get("response") or []:
            if not isinstance(item, dict):
                dropped.setdefault("not an object", []).append(None)
                continue
            t = item.get("team") if isinstance(item.get("team"), dict) else item
            tid, name = t.get("id"), t.get("name")
            if tid is None or not name:
                dropped.setdefault("no id or name", []).append(tid)
                continue
            country = t.get("country")
            out.append(NormalizedTeam(
                sport=Sport.BASKETBALL, name=name, source=self.source_name,
                source_id=str(tid), short_name=t.get("code"), tla=t.get("code"),
                # the served country's name (a Canadian franchise is not typed 'USA'), else unknown
                area=(country.get("name") if isinstance(country, dict) else None) or None,
            ))
        self._report_dropped("teams", dropped)
        return out

    # ------------------------------------------------------------------
    # Matches
    # ------------------------------------------------------------------

    def range_note(self, season: str | None, date_from: str | None, date_to: str | None) -> str | None:
        """The american-football adapter's #570 note: /games takes one `date`, so a range is never sent; the whole
        season's listing is read (and, under sync-matches, written). None when no range was asked."""
        if not (date_from or date_to) or date_from == date_to:
            return None
        what = "reading and writing" if self.listing_writes else "reading"
        return (f"RANGE {date_from or ''}..{date_to or ''} is not supported by this provider: {what} the whole "
                f"{season} listing")

    def list_matches(self, competition_code: str, season: str | None = None,
                     date_from: str | None = None,
                     date_to: str | None = None) -> list[NormalizedMatch]:
        served = self.provider_season(competition_code, season)
        code = str(competition_code).upper()
        ours = str(season).strip()
        note = self.range_note(ours, date_from, date_to)
        if note:
            print(note, flush=True)
        params: dict[str, Any] = {"league": self.league_id(code), "season": served}
        if date_from and date_from == date_to:
            params["date"] = date_from
        data = self._get("games", params=params)
        out: list[NormalizedMatch] = []
        dropped: dict[str, list] = {}
        for g in data.get("response") or []:
            if not isinstance(g, dict):
                dropped.setdefault("not an object", []).append(None)
                continue
            game = g.get("game") if isinstance(g.get("game"), dict) else g
            teams = g.get("teams") if isinstance(g.get("teams"), dict) else {}
            scores = g.get("scores") if isinstance(g.get("scores"), dict) else {}
            gid = game.get("id")
            home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
            away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
            if gid is None:
                dropped.setdefault("no id", []).append(None)
                continue
            if home.get("id") is None or away.get("id") is None:
                dropped.setdefault("no team id", []).append(gid)
                continue
            utc = kickoff_utc(g)
            if utc is None:
                dropped.setdefault("no readable kickoff", []).append(gid)
                continue
            short = served_short(g)
            week = game.get("week")
            stage = game.get("stage")
            out.append(NormalizedMatch(
                sport=Sport.BASKETBALL, competition_code=code,
                season=ours,                                   # OUR string ("2026"), never the provider's
                utc_date=utc,
                status=map_status(short),
                home_team_source_id=str(home["id"]),
                away_team_source_id=str(away["id"]),
                source=self.source_name, source_id=str(gid),
                # a served week stored as a matchday only when it is a whole number as served (never digit-mined)
                matchday=(week if isinstance(week, int) and not isinstance(week, bool)
                          else int(week) if isinstance(week, str) and week.isdigit() else None),
                stage=str(stage) if stage not in (None, "") else None,     # as served
                status_raw=short,                              # 'AOT' is the overtime flag (the hockey precedent)
                home_score=side_total(scores, "home"),
                away_score=side_total(scores, "away"),
                raw=g,                                         # transient: NOT KEPT (274 item 2(10)), read nowhere
            ))
        self._report_dropped("games", dropped)
        return out

    def _report_dropped(self, what: str, dropped: dict[str, list]) -> None:
        """Law 4: a listing the adapter cannot place is counted on a printed line, never silent."""
        self.last_dropped = dropped
        if dropped:
            parts = " · ".join(f"{why} {len(ids)}" for why, ids in dropped.items())
            ids = [str(i) for v in dropped.values() for i in v if i is not None]
            print(f"api_basketball /{what}: {sum(len(v) for v in dropped.values())} listing(s) not read ({parts})"
                  + (f": {', '.join(ids)}" if ids else ""), flush=True)

    def get_match_stats(self, match_source_id: str) -> list[NormalizedMatchStats]:
        return []

    @property
    def requests_remaining(self) -> int | None:
        return self._requests_remaining


def status_counts(items: list) -> Counter:
    """short code (None for absent) -> count, over a /games response's items."""
    return Counter(served_short(g) for g in items if isinstance(g, dict))
