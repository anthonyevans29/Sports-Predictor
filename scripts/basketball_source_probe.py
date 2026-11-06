"""
BASKETBALL SOURCE PROBE (ARCHITECT 2026-11-05 11:40 ET, addendum 261 item 1(a); lane basketball-market-only, #839).
Read-only, zero wiring: no adapter, no Sport value, no DB, no table, no chain.

The ruling, verbatim: "THE PROVIDER PROBE, read-only, by 11-10 (one small PR: the probe script and its receipt on the
Issue; no adapter yet): candidates (i) API-Sports basketball (v1.basketball.api-sports.io — the SAME account key as
api_hockey's fallback, API_BASKETBALL_KEY falling back to API_FOOTBALL_KEY, the hockey adapter's own pattern; one
adapter covers the NBA, NCAA men's and the WNBA by league id; the plan per API product is the operator's — the probe
prints the rate-limit headers, never the key); (ii) the NBA's own public schedule and box-score JSON (no key; NBA only;
the fallback if (i)'s plan is a blocker). The probe reads, BY FIELD NAME: one day's schedule, one finished game's final
score and status, the team list for the NBA and for NCAA men's Division I, and the status vocabulary as served."

NOTHING HERE WAS CONFIRMED AGAINST A LIVE ANSWER. The probe was written where every provider host is refused by the
proxy; its field names are hypotheses taken from the shapes the repo already reads (src/adapters/api_hockey.py for
API-Sports; the NBA JSON names are the operator's to confirm). The probe exists to read them: it prints each item's
keys as served, and a required field it cannot find REFUSES that read (law 1), never guessed.

Three sections, each independent (a failure in one does not stop the next; the exit code is the worst of them):

  (i)   API-Sports basketball, v1.basketball.api-sports.io, header x-apisports-key (api_hockey's). The key: the env
        name API_BASKETBALL_KEY, else API_FOOTBALL_KEY (api_hockey's order); each set name is tried on /status and
        the receipt prints which NAME answered, never a value. Calls: /status, /leagues (once, every league; the NBA
        and NCAA league ids READ by exact name, never typed: zero or several candidates REFUSE that league, the
        candidates printed), then per league /teams (league, season), /games (league, season, date: one day's
        schedule) and /games (league, season: the season's status vocabulary). The season is the last one /leagues
        lists for that league, as served, unless --season names one. Every call line, each /status attempt
        included, prints the rate-limit headers as served (every header whose name holds "ratelimit"), and the run
        count includes every /status attempt. /status prints the subscription and request fields only; its account
        block is never printed.
  (ii)  The NBA's public JSON (no key). FIRST the site's terms (261 item 4: "no scraping of a source whose terms
        forbid it (the probe quotes the terms)"): the page the operator names with --nba-terms-url (NO default: no
        URL is typed from memory) is read and its access clauses quoted, markup stripped. With no terms URL, a
        terms read that fails, or a page with nothing to quote, the terms are NOT READ and section (ii) is REFUSED
        (or FAILED) for ingest; its reads still print. Then the schedule file (--nba-schedule-url): field presence,
        the status vocabulary, the NBA team list (the distinct homeTeam/awayTeam teamId · teamTricode · teamCity ·
        teamName), the day's games, and one box score (--nba-boxscore-url, "{game_id}" in it). The schedule and
        box-score DEFAULTS ARE UNVERIFIED HERE (no network): the operator confirms them on the first run.
  (iii) Kalshi's series listing, read through src/adapters/kalshi.py find_series (the repo's own listing path, the
        one `cli.py kalshi-probe` uses; public data, no key), filtered for basketball. Each matching series' ticker,
        title, category and tags print AS SERVED, a ticker ending "GAME" marked (the game-winner shape every wired
        series has), and every field whose name holds "fee", as served. No ticker and no fee multiplier is typed
        here (261 item 4); Kalshi's published fee schedule is a document the operator reads.

    python3 scripts/basketball_source_probe.py [--date YYYY-MM-DD] [--season S] [--out /path/receipt.json]
    python3 scripts/basketball_source_probe.py --skip nba --skip kalshi        # API-Sports only

"One finished game" is read as the first game of the day carrying both scores, printed with its status AS SERVED: the
probe does not decide what "finished" means (the status map is the wiring PR's, from this receipt), and its labels say
so.

Exit: 0 every read answered; 1 a call failed (network, HTTP, a provider error, an answer of an unexpected shape, a
section that raised, a receipt that could not be written); 2 a read REFUSED (no key answered, a league not resolved by
exact name or with no season listed, a required field not found, no scored game on the day, the NBA terms not read,
--skip naming every section, --out under data/ in any case or not writable). Writes nothing unless --out is given
(never under data/: law 5; checked before any call). Imports nothing that opens the DB.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.kalshi import KalshiAdapter  # noqa: E402  (requests and logging only: no DB)

OK, FAILED, REFUSED = 0, 1, 2

APISPORTS_BASE = "https://v1.basketball.api-sports.io"        # the host 261 item 1(a)(i) names
KEY_NAMES = ("API_BASKETBALL_KEY", "API_FOOTBALL_KEY")         # api_hockey's order: the product key, then the shared
KEY_HEADER = "x-apisports-key"                                 # api_hockey.py's header
# UNVERIFIED defaults (no network where this was written): the operator confirms them on the first run.
NBA_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
NBA_BOXSCORE_URL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
NBA_TERMS_URL = None             # no default: the operator names the terms page (no URL typed from memory, 261 item 4)
TERMS_WORDS = ("scrap", "crawl", "robot", "spider", "automated", "data mining", "commercial", "reproduc",
               "redistribut", "api", "feed", "permission")
TERMS_QUOTES, TERMS_QUOTE_CHARS, TERMS_HEAD_CHARS = 12, 400, 600
# Hypotheses for the NBA JSON's field names, each reported found or not found on the run (law 1).
NBA_GAME_FIELDS = ("gameId", "gameCode", "gameStatus", "gameStatusText", "gameDateTimeUTC", "gameDateUTC",
                   "gameDateEst", "gameTimeUTC")
NBA_DATE_FIELDS = ("gameDateTimeUTC", "gameTimeUTC", "gameDateUTC", "gameDateEst")
NBA_TEAM_FIELDS = ("teamId", "teamName", "teamCity", "teamTricode", "score")
NBA_TEAM_ID_FIELDS = ("teamId", "teamTricode", "teamCity", "teamName")     # the team list's fields, by name
NBA_BOX_REQUIRED = ("gameStatus", "gameStatusText", "homeTeam.score", "awayTeam.score")   # the box score's reads
KALSHI_KEYWORDS = ("basketball", "nba", "ncaab", "ncaam", "college basketball")
SAMPLE = 40


class Out:
    """Every printed line and the receipt pass through here: any secret value is replaced before it is shown. No error
    text is cut before it gets here (a cut inside an echoed key would leave a prefix no longer equal to the secret)."""

    def __init__(self):
        self.secrets: set[str] = set()
        self.lines: list[str] = []

    def redact(self, text: str) -> str:
        for s in sorted(self.secrets, key=len, reverse=True):
            if s:
                text = text.replace(s, "<redacted>")
        return text

    def __call__(self, line: str = "") -> None:
        line = self.redact(str(line))
        self.lines.append(line)
        print(line)


def http_get(url: str, headers: dict | None = None, params: dict | None = None, timeout: int = 30,
             text: bool = False):
    """(status or None, response headers, JSON body (or the text when `text`) or None, error text or None). Never
    raises. Error text is whole (never cut): Out redacts it before any line or receipt shows it."""
    try:
        r = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
    except Exception as e:                          # the key travels in a header, never in the URL or this text
        return None, {}, None, f"{type(e).__name__}: {e}"
    hdr = dict(r.headers or {})
    if text:
        body = getattr(r, "text", None)
    else:
        try:
            body = r.json()
        except ValueError:
            body = None
    err = None if r.status_code == 200 else f"HTTP {r.status_code}"
    if err is None and body is None:
        err = "the answer is not JSON" if not text else "the answer has no text"
    return r.status_code, hdr, body, err


def rate_headers(hdr: dict) -> dict:
    """Every header whose name holds "ratelimit", as served (names and values read, never assumed)."""
    return {k: v for k, v in (hdr or {}).items() if "ratelimit" in str(k).lower()}


def provider_errors(body) -> str | None:
    """API-Sports answers 200 with a non-empty `errors` (list or dict) on a refused call (api_hockey._get's rule)."""
    errs = body.get("errors") if isinstance(body, dict) else None
    if errs and (errs if isinstance(errs, list) else list(errs.values())):
        return json.dumps(errs, default=str)
    return None


def item_keys(o, prefix: str = "") -> list[str]:
    """Every key path of a dict, dotted, sorted (the item's shape as served)."""
    out: set[str] = set()
    if isinstance(o, dict):
        for k, v in o.items():
            out.add(prefix + str(k))
            out.update(item_keys(v, prefix + str(k) + "."))
    return sorted(out)


# ---- (i) API-Sports basketball -----------------------------------------------------------------------------------

def choose_key(env, get=http_get) -> tuple[str | None, str | None, dict | None, list[tuple[str, str, dict | None]],
                                          int]:
    """(the env NAME that answered, its value, the /status body, [(name, outcome, rate-limit headers or None)], the
    number of /status calls made). Each set name in KEY_NAMES' order is tried on /status; the first that answers with
    no provider error and a non-empty 'response' object is used for every call. Every attempt is metered, so every
    attempt is counted."""
    tried: list[tuple[str, str, dict | None]] = []
    n = 0
    for name in KEY_NAMES:
        key = (env.get(name) or "").strip()
        if not key:
            tried.append((name, "not set", None))
            continue
        status, hdr, body, err = get(f"{APISPORTS_BASE}/status", headers={KEY_HEADER: key})
        n += 1
        err = err or provider_errors(body)
        resp = body.get("response") if isinstance(body, dict) else None
        if err is None and not isinstance(resp, dict):     # a shape it cannot read never chooses the key
            err = f"/status 'response' is {type(resp).__name__}, not an object"
        elif err is None and not resp:
            err = "/status 'response' is an empty object"
        if err:
            tried.append((name, f"set, refused: {err}", rate_headers(hdr)))
            continue
        tried.append((name, "set, answered", rate_headers(hdr)))
        return name, key, body, tried, n
    return None, None, None, tried, n


def status_summary(body) -> dict:
    """The subscription and request fields of /status only; the account block (a name and an email) never."""
    resp = body.get("response") if isinstance(body, dict) else None
    resp = resp if isinstance(resp, dict) else {}
    sub, req = resp.get("subscription") or {}, resp.get("requests") or {}
    return {"subscription": {k: sub.get(k) for k in ("plan", "active", "end")},
            "requests": {k: req.get(k) for k in ("current", "limit_day")}}


def league_parts(item: dict) -> tuple[dict, dict, list]:
    """(league, country, seasons) of a /leagues item, flat or nested under "league" (api_hockey reads both)."""
    lg = item.get("league") if isinstance(item.get("league"), dict) else item
    country = item.get("country") if isinstance(item.get("country"), dict) else (lg.get("country") or {})
    seasons = item.get("seasons") or lg.get("seasons") or []
    return lg, country if isinstance(country, dict) else {"name": country}, seasons if isinstance(seasons, list) else []


def league_candidates(items: list, words=("nba", "ncaa")) -> list[dict]:
    """Every league whose served name holds one of `words` (case-insensitive; every league when `words` is None): id,
    name, type, country, seasons."""
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        lg, country, seasons = league_parts(it)
        name = str(lg.get("name") or "")
        if words is None or any(w in name.lower() for w in words):
            out.append({"id": lg.get("id"), "name": name, "type": lg.get("type"), "country": country.get("name"),
                        "seasons": [s.get("season") if isinstance(s, dict) else s for s in seasons]})
    return out


def pick_league(cands: list[dict], name: str, country: str | None = None) -> tuple[dict | None, str]:
    """The one candidate whose served name equals `name` (case-insensitive; and whose country equals `country` when
    given). Zero or several: None, with the reason. Never a substring, never a typed id."""
    hits = [c for c in cands if c["name"].casefold() == name.casefold()
            and (country is None or str(c["country"] or "").casefold() == country.casefold())]
    if len(hits) == 1:
        return hits[0], f"id {hits[0]['id']} read by exact name {name!r}" + (f" in {country!r}" if country else "")
    where = f" in {country!r}" if country else ""
    return None, (f"{len(hits)} leagues named exactly {name!r}{where} (exactly one required; pass --nba-league / "
                  f"--ncaa-league with the served name, or --league-country)")


TEAM_REQUIRED = ("id", "name")


def team_rows(items: list) -> list[dict]:
    out = []
    for it in items or []:
        if isinstance(it, dict):
            t = it.get("team") if isinstance(it.get("team"), dict) else it
            out.append({"id": t.get("id"), "name": t.get("name"), "code": t.get("code")})
    return out


GAME_REQUIRED = ("id", "date", "status", "teams.home", "teams.away", "scores")


def game_row(g: dict) -> dict:
    """One /games item read by field name, flat or nested under "game" (api_hockey's rule). Totals are read with no
    falsy default (a side's 0 stays 0: api_hockey's falsy-zero lesson)."""
    game = g.get("game") if isinstance(g.get("game"), dict) else g
    teams = g.get("teams") if isinstance(g.get("teams"), dict) else {}
    scores = g.get("scores") if isinstance(g.get("scores"), dict) else {}
    st = game.get("status")
    d = game.get("date")

    def total(x):
        return x.get("total") if isinstance(x, dict) else x

    home, away = teams.get("home"), teams.get("away")
    missing = [f for f, ok in (("id", game.get("id") is not None), ("date", d is not None),   # absent or null:
                               ("status", st is not None),                                   # not served
                               ("teams.home", isinstance(home, dict)), ("teams.away", isinstance(away, dict)),
                               ("scores", g.get("scores") is not None)) if not ok]
    return {"id": game.get("id"),
            "date": d.get("date") if isinstance(d, dict) else d,
            "timestamp": d.get("timestamp") if isinstance(d, dict) else game.get("timestamp"),
            "status_short": st.get("short") if isinstance(st, dict) else st,
            "status_long": st.get("long") if isinstance(st, dict) else None,
            "home": (home or {}).get("name"), "away": (away or {}).get("name"),
            "home_id": (home or {}).get("id"), "away_id": (away or {}).get("id"),
            "home_total": total(scores.get("home")), "away_total": total(scores.get("away")),
            "missing": missing}


def vocabulary(rows: list[dict]) -> dict:
    """Every distinct (short | long) status pair as served, with its count."""
    return dict(sorted(Counter(f"{r['status_short']} | {r['status_long']}" for r in rows).items()))


def first_scored(rows: list[dict]) -> dict | None:
    """The first game carrying both totals. The probe does not decide what "final" means: the status prints as
    served beside the score, and the status map is the wiring PR's, from this receipt."""
    return next((r for r in rows if r["home_total"] is not None and r["away_total"] is not None), None)


def apisports_section(a, env, say: Out, get=http_get) -> tuple[int, dict]:
    for n in KEY_NAMES:                  # every key value read is a secret before any line prints, used or refused
        v = env.get(n) or ""
        say.secrets.update(x for x in (v, v.strip()) if x.strip())
    say("\n(i) API-SPORTS BASKETBALL · " + APISPORTS_BASE)
    name, key, body, tried, n_status = choose_key(env, get)
    for n, why, h in tried:
        say(f"  key {n}: {why}" + (f" · rate-limit {h}" if h is not None else ""))
    rec: dict = {"keys_tried": [{"name": n, "outcome": why, "rate_limit": h} for n, why, h in tried],
                 "key_name_used": name, "calls": n_status}
    if not key:
        say(f"  API-Sports calls this run: {n_status} (every /status attempt included)")
        say("  REFUSED: no key name answered /status (" + " · ".join(KEY_NAMES) + "); operator hand step "
            "(261 item 3): the API-Sports basketball product on the account")
        return REFUSED, rec
    rec["status"] = status_summary(body)
    say(f"  key used: {name} (the value is never printed)")
    say(f"  /status: subscription {rec['status']['subscription']} · requests {rec['status']['requests']}")
    calls = [n_status]
    rc = OK

    def call(path, params):
        status, h, b, err = get(f"{APISPORTS_BASE}/{path}", headers={KEY_HEADER: key}, params=params)
        calls[0] += 1
        rec["calls"] = calls[0]
        err = err or provider_errors(b)
        items = b.get("response") if isinstance(b, dict) else None
        if err is None and not isinstance(items, list):
            err = ("no 'response' field" if not isinstance(b, dict) or "response" not in b
                   else f"'response' is {type(items).__name__}, not a list")
        say(f"  /{path} {json.dumps(params, sort_keys=True)} · HTTP {status} · "
            f"{len(items) if isinstance(items, list) else '?'} items · rate-limit {rate_headers(h)}"
            + (f" · FAILED: {err}" if err else ""))
        return (None if err else items), err

    leagues, err = call("leagues", {})
    if err:
        say(f"\n  API-Sports calls this run: {calls[0]} (every /status attempt included)")
        return FAILED, rec
    cands = league_candidates(leagues)
    rec["league_candidates"] = cands
    say(f"  LEAGUES holding 'NBA' or 'NCAA' in their served name ({len(cands)} of {len(leagues)}):")
    for c in cands:
        say(f"    id {c['id']} · {c['name']!r} · type {c['type']!r} · country {c['country']!r} · "
            f"seasons tail {c['seasons'][-4:]}")
    rec["leagues"] = {}
    every = league_candidates(leagues, words=None)  # an override names a served league, whatever its name holds
    for label, want in (("NBA", a.nba_league), ("NCAA men's Division I", a.ncaa_league)):
        lg, how = pick_league(every, want, a.league_country)
        say(f"\n  {label}: {how}")
        if lg is None:
            rc = max(rc, REFUSED)
            rec["leagues"][label] = {"refused": how}
            continue
        season = a.season if a.season else (lg["seasons"][-1] if lg["seasons"] else None)
        if season is None:
            say(f"  REFUSED: {label}: /leagues lists no season for id {lg['id']}; pass --season as served")
            rc = max(rc, REFUSED)
            rec["leagues"][label] = {"id": lg["id"], "name": lg["name"], "refused": "no season listed"}
            continue
        say(f"  season {season!r} ({'--season' if a.season else 'the last /leagues lists, as served'})")
        L = {"id": lg["id"], "name": lg["name"], "season": season}
        rec["leagues"][label] = L
        teams, err = call("teams", {"league": lg["id"], "season": season})
        if err:
            rc = max(rc, FAILED)
        else:
            tr = team_rows(teams)
            L["teams"] = tr
            say(f"  TEAMS: {len(tr)} · first item's keys {item_keys(teams[0]) if teams else []}")
            names = sorted(str(t["name"]) for t in tr)
            more = f" · (+{len(names) - SAMPLE} more)" if len(names) > SAMPLE else ""
            say("    " + " · ".join(names[:SAMPLE]) + more)
            bad_t = [(i, [f for f in TEAM_REQUIRED if t[f] is None]) for i, t in enumerate(tr)]
            bad_t = [(i, m) for i, m in bad_t if m]
            if not tr or len(tr) < len(teams):
                say("  REFUSED: /teams served no team" if not teams else
                    f"  REFUSED: /teams served {len(teams) - len(tr)} item(s) that are not objects")
                rc = max(rc, REFUSED)
            elif bad_t:
                say(f"  REFUSED: required field(s) not found in {len(bad_t)} of {len(tr)} teams (the first such, item "
                    f"{bad_t[0][0]}: {', '.join(bad_t[0][1])}; required: {', '.join(TEAM_REQUIRED)})")
                rc = max(rc, REFUSED)
        day, err = call("games", {"league": lg["id"], "season": season, "date": a.date})
        rows: list[dict] = []
        if err:
            rc = max(rc, FAILED)
        else:
            rows = [game_row(g) for g in day if isinstance(g, dict)]
            L["day"] = {"date": a.date, "games": rows}
            say(f"  ONE DAY'S SCHEDULE ({a.date}): {len(rows)} game{'' if len(rows) == 1 else 's'} · first item's "
                f"keys {item_keys(day[0]) if day else []}")
            bad = [(i, r["missing"]) for i, r in enumerate(rows) if r["missing"]]
            if bad:
                say(f"  REFUSED: required field(s) not found in {len(bad)} of {len(rows)} games (the first such, item "
                    f"{bad[0][0]}: {', '.join(bad[0][1])}; required: {', '.join(GAME_REQUIRED)})")
                rc = max(rc, REFUSED)
                rows = []
            else:
                for r in rows[:SAMPLE]:
                    say(f"    #{r['id']} {r['date']} {r['away']} @ {r['home']} · status {r['status_short']!r} | "
                        f"{r['status_long']!r} · {r['away_total']}-{r['home_total']}")
                fin = first_scored(rows)
                if fin:
                    L["both_totals"] = fin
                    say(f"  ONE GAME WITH BOTH TOTALS (the first on the day; finished is not decided here): "
                        f"#{fin['id']} {fin['away']} {fin['away_total']} @ {fin['home']} {fin['home_total']} · "
                        f"status short {fin['status_short']!r} · long {fin['status_long']!r} (as served; the status "
                        "map is the wiring PR's)")
                else:
                    say(f"  REFUSED: no game on {a.date} carries both totals; pass --date of a played day")
                    rc = max(rc, REFUSED)
        season_games, err = call("games", {"league": lg["id"], "season": season})
        if err:
            rc = max(rc, FAILED)
            src = f"the day's {len(rows)} games only: the season call failed"
            L["vocabulary"] = vocabulary(rows)
        else:                            # the season's games hold the day's: each game is counted once
            vr = [game_row(g) for g in season_games if isinstance(g, dict)]
            src = f"{len(vr)} season games, each once"
            L["vocabulary"] = vocabulary(vr)
        L["vocabulary_source"] = src
        say(f"  STATUS VOCABULARY as served (short | long: count; {src}):")
        for k, n in L["vocabulary"].items():
            say(f"    {k}: {n}")
    say(f"\n  API-Sports calls this run: {calls[0]} (every /status attempt included)")
    return rc, rec


# ---- (ii) the NBA's public JSON ----------------------------------------------------------------------------------

def find_games(doc) -> list[dict]:
    """Every dict holding both "homeTeam" and "awayTeam" (the structural hypothesis, printed with its count)."""
    out, stack = [], [doc]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if isinstance(o.get("homeTeam"), dict) and isinstance(o.get("awayTeam"), dict):
                out.append(o)
            stack.extend(reversed(list(o.values())))
        elif isinstance(o, list):
            stack.extend(reversed(o))
    return out


def nba_row(g: dict) -> dict:
    date_field = next((f for f in NBA_DATE_FIELDS if g.get(f)), None)
    side = lambda s: {f: (g.get(s) or {}).get(f) for f in NBA_TEAM_FIELDS}    # noqa: E731
    return {"gameId": g.get("gameId"), "date_field": date_field, "date": g.get(date_field) if date_field else None,
            "gameStatus": g.get("gameStatus"), "gameStatusText": g.get("gameStatusText"),
            "home": side("homeTeam"), "away": side("awayTeam")}


def nba_teams(games: list[dict]) -> list[dict]:
    """The distinct teams of the schedule's homeTeam/awayTeam objects, read by field name (NBA_TEAM_ID_FIELDS), in
    teamId order as served (a missing field stays None; nothing is filled in)."""
    seen: dict[tuple, dict] = {}
    for g in games:
        for s in ("homeTeam", "awayTeam"):
            t = g.get(s) if isinstance(g.get(s), dict) else {}
            row = {f: t.get(f) for f in NBA_TEAM_ID_FIELDS}
            seen.setdefault(tuple(row.values()), row)
    return sorted(seen.values(), key=lambda r: (r["teamId"] is None, str(r["teamId"]), str(r["teamTricode"])))


def terms_excerpt(page: str) -> list[str]:
    """The terms page's access clauses, quoted: script/style dropped, tags stripped, entities unescaped, split into
    sentences; every sentence holding a word that starts with one of TERMS_WORDS (up to TERMS_QUOTES, each up to TERMS_QUOTE_CHARS), or the
    page's head when none does. The probe quotes; it does not decide what the terms allow."""
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page or "")
    t = re.sub(r"(?s)<[^>]+>", "\n", t)
    t = html.unescape(t)
    parts = [re.sub(r"\s+", " ", x).strip() for x in re.split(r"(?<=[.!?])\s+|\n+", t)]
    parts = [x for x in parts if x]
    word = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in TERMS_WORDS) + ")", re.I)   # at a word's start
    hits = [x[:TERMS_QUOTE_CHARS] for x in parts if word.search(x)]
    if hits:
        return hits[:TERMS_QUOTES]
    head = " ".join(parts)[:TERMS_HEAD_CHARS]
    return [head] if head else []


def nba_terms(a, say: Out, get=http_get) -> tuple[int, dict]:
    """261 item 4: the probe quotes the terms. Read FIRST, before the schedule. No URL: NOT READ, REFUSED for ingest."""
    if not a.nba_terms_url:
        say("  TERMS NOT READ (no --nba-terms-url given; no URL is typed here): section (ii) is REFUSED for ingest "
            "until the terms are quoted (261 item 4); its reads below are the probe's, not an ingest")
        return REFUSED, {"url": None, "read": False}
    status, hdr, page, err = get(a.nba_terms_url, text=True)
    say(f"  TERMS {a.nba_terms_url} · HTTP {status}" + (f" · FAILED: {err}" if err else ""))
    if err:
        say("  TERMS NOT READ: section (ii) is not cleared for ingest until they are quoted (261 item 4)")
        return FAILED, {"url": a.nba_terms_url, "read": False, "http": status, "error": err}
    quoted = terms_excerpt(page)
    if not quoted:
        say("  TERMS NOT QUOTED (the page yields no text to quote): section (ii) is REFUSED for ingest until the "
            "terms are quoted (261 item 4)")
        return REFUSED, {"url": a.nba_terms_url, "read": False, "http": status, "chars": len(page), "quoted": []}
    say(f"  TERMS QUOTED ({len(quoted)} passage{'' if len(quoted) == 1 else 's'} holding an access word "
        f"{list(TERMS_WORDS)}, or the page's head; the architect reads what they allow):")
    for q in quoted:
        say(f'    "{q}"')
    return OK, {"url": a.nba_terms_url, "read": True, "http": status, "chars": len(page), "quoted": quoted}


def field_presence(games: list[dict]) -> dict:
    """For each hypothesised name: how many games carry it (0 = not served under that name)."""
    pres = {f: sum(1 for g in games if f in g) for f in NBA_GAME_FIELDS}
    for s in ("homeTeam", "awayTeam"):
        pres.update({f"{s}.{f}": sum(1 for g in games if f in (g.get(s) or {})) for f in NBA_TEAM_FIELDS})
    return pres


def nba_section(a, say: Out, get=http_get) -> tuple[int, dict]:
    say("\n(ii) THE NBA'S PUBLIC JSON (no key; NBA only) · the URLs are UNVERIFIED here: the operator confirms them")
    tcode, terms = nba_terms(a, say, get)
    code, rec = _nba_reads(a, say, get)
    rec["terms"] = terms
    return max(tcode, code), rec


def _nba_reads(a, say: Out, get=http_get) -> tuple[int, dict]:
    say(f"  schedule {a.nba_schedule_url}")
    status, hdr, doc, err = get(a.nba_schedule_url)
    rec: dict = {"schedule_url": a.nba_schedule_url, "http": status}
    say(f"  HTTP {status} · rate-limit {rate_headers(hdr)}" + (f" · FAILED: {err}" if err else ""))
    if err:
        return FAILED, rec
    games = find_games(doc)
    rec["top_level_keys"] = sorted(doc) if isinstance(doc, dict) else type(doc).__name__
    if not games:
        say(f"  REFUSED: no object holds both homeTeam and awayTeam · top-level keys {rec['top_level_keys']}")
        return REFUSED, rec
    rec["field_presence"] = field_presence(games)
    say(f"  {len(games)} game objects · first one's keys {item_keys(games[0])[:60]}")
    say("  FIELDS by name (games carrying each; 0 = not served under that name): "
        + " · ".join(f"{k} {v}" for k, v in rec["field_presence"].items()))
    rows = [nba_row(g) for g in games]
    vocab = Counter(f"{r['gameStatus']} | {r['gameStatusText']}" for r in rows)
    rec["vocabulary"] = dict(sorted(vocab.items()))
    say(f"  STATUS VOCABULARY as served (gameStatus | gameStatusText: count; {len(vocab)} distinct, the 25 commonest):")
    for k, n in vocab.most_common(25):
        say(f"    {k}: {n}")
    rec["teams"] = nba_teams(games)
    say(f"  NBA TEAMS (distinct homeTeam/awayTeam, by {' · '.join(NBA_TEAM_ID_FIELDS)}): {len(rec['teams'])}"
        " (as served: a schedule may also hold non-NBA opponents or placeholders)")
    for t in rec["teams"][:SAMPLE * 2]:
        say("    " + " · ".join(str(t[f]) for f in NBA_TEAM_ID_FIELDS))
    if len(rec["teams"]) > SAMPLE * 2:
        say(f"    (+{len(rec['teams']) - SAMPLE * 2} more)")
    day = [r for r in rows if r["date"] and str(r["date"]).startswith(a.date)]
    rec["day"] = {"date": a.date, "games": day}
    if not any(r["date_field"] for r in rows):
        say(f"  REFUSED: no date field among {', '.join(NBA_DATE_FIELDS)}")
        return REFUSED, rec
    say(f"  ONE DAY'S SCHEDULE ({a.date}, matched on each game's first served date field): {len(day)} "
        f"game{'' if len(day) == 1 else 's'}")
    for r in day[:SAMPLE]:
        say(f"    {r['gameId']} {r['date_field']}={r['date']} {r['away']['teamTricode']} @ {r['home']['teamTricode']} "
            f"· {r['gameStatus']!r} | {r['gameStatusText']!r} · {r['away']['score']}-{r['home']['score']}")
    fin = next((r for r in day if r["home"]["score"] not in (None, 0) and r["away"]["score"] not in (None, 0)), None)
    if fin is None:
        say(f"  REFUSED: no game on {a.date} carries two non-zero scores; pass --date of a played day")
        return REFUSED, rec
    url = a.nba_boxscore_url.replace("{game_id}", str(fin["gameId"]))
    status, hdr, box, err = get(url)
    rec["scored_game"] = {"gameId": fin["gameId"], "boxscore_url": url, "http": status}
    say(f"  ONE GAME WITH TWO NON-ZERO SCORES (the first on the day; finished is not decided here): box score {url} "
        f"· HTTP {status}" + (f" · FAILED: {err}" if err else ""))
    if err:
        return FAILED, rec
    found = find_games(box)
    if not found:
        say(f"  REFUSED: the box score holds no object with both homeTeam and awayTeam · top-level keys "
            f"{sorted(box) if isinstance(box, dict) else type(box).__name__}")
        return REFUSED, rec
    g = found[0]
    r = nba_row(g)
    rec["scored_game"].update({"keys": item_keys(g)[:80], "row": r})
    say(f"    keys {item_keys(g)[:40]}")
    served = {"gameStatus": r["gameStatus"], "gameStatusText": r["gameStatusText"],
              "homeTeam.score": r["home"]["score"], "awayTeam.score": r["away"]["score"]}
    absent = [f for f in NBA_BOX_REQUIRED if served[f] is None]
    if absent:
        rec["scored_game"]["refused"] = f"not served: {', '.join(absent)}"
        say(f"  REFUSED: the box score serves no {', '.join(absent)} (by name, or null): the final score and status "
            "were not read")
        return REFUSED, rec
    say(f"    {r['gameId']} · gameStatus {r['gameStatus']!r} | gameStatusText {r['gameStatusText']!r} · "
        f"{r['away']['teamTricode']} {r['away']['score']} @ {r['home']['teamTricode']} {r['home']['score']} "
        "(status as served; the status map is the wiring PR's)")
    return OK, rec


# ---- (iii) Kalshi's series listing -------------------------------------------------------------------------------

class ListingRead(KalshiAdapter):
    """KalshiAdapter whose every call is recorded, so a listing that failed is told from one that matched nothing
    (find_series swallows its errors)."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.calls: list[dict] = []

    def _get(self, path: str, params: dict | None = None) -> dict:
        try:
            data = super()._get(path, params)
        except Exception as e:
            self.calls.append({"path": path, "params": params, "error": f"{type(e).__name__}: {e}"})
            raise
        self.calls.append({"path": path, "params": params, "error": None,
                           "n": len(data.get("series") or []) if isinstance(data, dict) else None})
        return data


def series_row(s: dict) -> dict:
    t = str(s.get("ticker") or "")
    return {"ticker": s.get("ticker"), "title": s.get("title"), "category": s.get("category"), "tags": s.get("tags"),
            "game_shape": t.upper().endswith("GAME"),
            "fee_fields": {k: v for k, v in s.items() if "fee" in str(k).lower()}}


def kalshi_section(say: Out, adapter: ListingRead | None = None) -> tuple[int, dict]:
    ad = adapter or ListingRead()
    say(f"\n(iii) KALSHI SERIES LISTING · {ad.base}/series via find_series {list(KALSHI_KEYWORDS)} (public, no key)")
    found = ad.find_series(list(KALSHI_KEYWORDS))
    rec: dict = {"calls": ad.calls}
    for c in ad.calls:
        say(f"  /{c['path']} {json.dumps(c['params'])} · " + (f"FAILED: {c['error']}" if c["error"]
                                                              else f"{c['n']} series listed"))
    if not ad.calls or ad.calls[-1]["error"] is not None:   # find_series reads the last call it made (an empty
        say("  FAILED: the series listing did not answer")   # filtered listing falls back to the unfiltered one)
        return FAILED, rec
    rows = [series_row(s) for s in found]
    rec["series"] = rows
    say(f"  {len(rows)} series match (ticker · title · category · tags · fee fields, all as served; "
        "GAME = a ticker ending GAME):")
    for r in rows:
        say(f"    {r['ticker']} · {r['title']!r} · {r['category']!r} · tags {r['tags']}"
            + (" · GAME" if r["game_shape"] else "") + f" · fee fields {r['fee_fields'] or 'none served'}")
    say("  The fee M is read from Kalshi's published fee schedule (a document the operator reads), never from here.")
    return OK, rec


# ---- main --------------------------------------------------------------------------------------------------------

def _load_env() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")


def refuse_out(path: Path | None) -> str | None:
    """Law 5: never under a data/ directory, compared WITHOUT case (the laptop's macOS filesystem ignores it: Data/ is
    data/), and never under the checkout's data/ by resolved path (a symlink into it included; sp_common's rule)."""
    if path is None:
        return None
    p = path.expanduser().resolve()
    data = (ROOT / "data").resolve()
    if any(x.casefold() == "data" for x in path.expanduser().parts + p.parts) or p == data or data in p.parents:
        return f"REFUSED: --out {path} is under a data/ directory (law 5); name a path outside it"
    return None


def prepare_out(path: Path) -> str | None:
    """Before any call (a metered run is never lost to an unwritable --out): not an existing directory, its parent
    made, and the file itself writable when it exists (a symlink's target included), else its folder writable. None
    when it can be written; else the REFUSED line."""
    if path.is_dir():
        return f"REFUSED: --out {path} is a directory; name a file"
    target = path.resolve()                          # a symlink's target is the file written
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return f"REFUSED: --out {path}: its folder cannot be made: {type(e).__name__}: {e}"
    if target.exists():
        if not os.access(target, os.W_OK):
            return f"REFUSED: --out {path}: the file is not writable"
    elif not os.access(target.parent, os.W_OK):
        return f"REFUSED: --out {path}: its folder is not writable"
    return None


def main(argv=None) -> int:
    yday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    ap = argparse.ArgumentParser(description="Basketball source probe (addendum 261 item 1(a); read-only)")
    ap.add_argument("--date", default=yday, help="the day whose schedule is read, YYYY-MM-DD (default: yesterday UTC)")
    ap.add_argument("--season", default=None,
                    help="API-Sports season as served, for both leagues (default: the last /leagues lists for each)")
    ap.add_argument("--nba-league", default="NBA", help="the NBA's served league name, matched exactly")
    ap.add_argument("--ncaa-league", default="NCAA", help="NCAA men's Division I's served league name, matched exactly")
    ap.add_argument("--league-country", default=None, help="also require this served country name")
    ap.add_argument("--nba-schedule-url", default=NBA_SCHEDULE_URL, help="UNVERIFIED default; the operator confirms")
    ap.add_argument("--nba-boxscore-url", default=NBA_BOXSCORE_URL,
                    help="UNVERIFIED default; {game_id} is replaced by the scored game's id")
    ap.add_argument("--nba-terms-url", default=NBA_TERMS_URL,
                    help="the NBA site's terms-of-use page, read and quoted FIRST (no default: no URL typed here; "
                         "without it section (ii) is REFUSED for ingest)")
    ap.add_argument("--skip", action="append", default=[], choices=("apisports", "nba", "kalshi"))
    ap.add_argument("--out", type=Path, default=None, help="write the JSON receipt here (never under data/)")
    a = ap.parse_args(argv)
    say = Out()
    if {"apisports", "nba", "kalshi"} <= set(a.skip):
        say("REFUSED: --skip names every section; nothing would be read")
        return REFUSED
    refused = refuse_out(a.out) or (prepare_out(a.out) if a.out else None)
    if refused:
        say(refused)
        return REFUSED
    try:
        if datetime.strptime(a.date, "%Y-%m-%d").strftime("%Y-%m-%d") != a.date:   # zero-padded, as matched
            raise ValueError(a.date)
    except ValueError:
        say(f"REFUSED: --date {a.date!r} is not YYYY-MM-DD")
        return REFUSED
    _load_env()
    say(f"BASKETBALL SOURCE PROBE (addendum 261 item 1(a), lane basketball-market-only, #839) · read-only · "
        f"day {a.date} · {datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}")
    receipt: dict = {"probe": "basketball_source_probe", "date": a.date,
                     "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sections": {}}
    rc = OK
    for name, run in (("apisports", lambda: apisports_section(a, os.environ, say)),
                      ("nba", lambda: nba_section(a, say)),
                      ("kalshi", lambda: kalshi_section(say))):
        if name in a.skip:
            say(f"\n({name}) skipped (--skip)")
            continue
        try:
            code, rec = run()
        except Exception as e:           # each section independent: an unexpected shape is FAILED, never a traceback
            say(f"  FAILED: {type(e).__name__}: {e} (section {name} stopped; the next section runs)")
            code, rec = FAILED, {"error": f"{type(e).__name__}: {e}"}
        receipt["sections"][name] = {"exit": code, **rec}
        rc = max(rc, code)
    receipt["exit"] = rc
    meaning = {OK: "every read answered", FAILED: "a call failed", REFUSED: "a read refused"}[rc]
    say(f"\nEXIT {rc} ({meaning}). This probe ingests nothing; the adapter follows the architect's ruling on this "
        "receipt.")
    if a.out:
        try:
            a.out.write_text(say.redact(json.dumps(receipt, indent=1, default=str)))
        except OSError as e:
            say(f"FAILED: the receipt was not written: {type(e).__name__}: {e} (the console above is the receipt)")
            return max(rc, FAILED)
        say(f"receipt written to {a.out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
