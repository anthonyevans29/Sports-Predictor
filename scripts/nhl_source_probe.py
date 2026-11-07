"""
NHL SOURCE PROBE (ARCHITECT 2026-11-06 19:40 ET, addendum 279 items 3(a) and 5; lane nhl, #105) — read-only.
Zero wiring: no adapter, no Sport value, no DB, no table, no chain.

The ruling, verbatim (item 3(a)): "DEMONSTRATED PREGAME ACCESS — a read-only probe (scripts/nhl_source_probe.py, one small
PR in a code slot, the basketball/tennis probes' pattern: the key by NAME from .env, never printed; the endpoint and
field names as served; exit codes) run by the operator on the LAPTOP with a trial or evaluation key the operator obtains
from the vendor, on a game day, printing for that day's games the projected starting goaltenders WITH THE SOURCE'S OWN
STAMP (the field that says when the projection was published) against the games' start times — "pregame" is a stamp
before the start, read from the response, not from our clock"
Item 5, verbatim in part: "the NHL probe PR (item 3(a)) opens in the next free code slot with the probe's sections (the
vendor's /status or equivalent by key NAME; the NHL games of the day; the projected-starters endpoint with every field
name as served and the stamp field identified by the vendor's documentation, quoted; the terms URL given on the command
line and the retention clause quoted; Kalshi KXNHLGAME untouched) and no adapter"
Item 3(c), verbatim in part: "the figure never written into the repo, an Issue or a PR (238's rule applies to vendor
prices as to units: the decision is recorded, the number is not)."

NOTHING HERE WAS CONFIRMED AGAINST A LIVE ANSWER. The probe was written where every provider host is refused by the
proxy and the vendor's documentation cannot be read. EVERY endpoint path, the base URL, the key header and every field
name default below is UNVERIFIED: a CLI option the operator confirms against the vendor's documentation on the first
run. The stamp field has NO default at all (--stamp-field, required for section 3): it is named from the documentation,
never typed from memory, and its documentation sentence is quoted on the command line (--stamp-quote). The probe prints
every field name as served; a required field it cannot find REFUSES that read (law 1), never guessed.

THE KEY: the env NAME SPORTSDATAIO_NHL_KEY, read from .env or the environment, never printed (every line and the
receipt pass through a redactor holding its value). One name, no fallback: the vendor issues a key per product (the
operator confirms), and the repo names a key by its product (API_HOCKEY_KEY, API_BASEBALL_KEY); there is no shared
SportsDataIO key in .env to fall back to, and a second name tried would spend a metered trial call on a key that is not
the NHL product's. The key travels in one request header (--key-header, UNVERIFIED default Ocp-Apim-Subscription-Key),
never in a URL: a base or path naming a key is REFUSED before any call. The terms page is read with no key.

Four sections, each independent (a failure in one does not stop the next), in this order:

  (1) STATUS     the vendor's status read or its equivalent (--status-path, UNVERIFIED default a current-season read):
                 one GET with the key by NAME. Printed: HTTP status, the rate-limit headers as served, every field
                 NAME of the answer as served, and the VALUES of the --status-value-field names only (an allow-list,
                 the basketball probe's status rule; UNVERIFIED default season fields): no billing figure under a name
                 the price rule misses, no account field. A price-class name (PRICE_FIELD / PRICE_WORD: price, cost,
                 fee, plan, subscription, rate, tier ...) never prints its value; a bare answer prints its type only.
                 A 401/403 is REFUSED (the key not accepted); so is a 200 whose object answer carries an error field
                 (ERROR_KEYS: code, message, error ...); any other failure FAILED. When the read does not answer,
                 sections 2 and 3 make no call (REFUSED: a metered trial is not spent on a key that did not answer);
                 --skip status runs them without it.
  (2) GAMES      the NHL games of --date (a UTC calendar day, stated as such; default today UTC; the vendor's own day
                 boundary is its documentation's, so the day's games are printed AS SERVED, never filtered by a zone
                 assumed here): --games-path, "{date}" (YYYY-MM-DD) or "{date_mon}" (YYYY-MON-DD, month upper case) in
                 it. Printed: the field names as served, and per game its id, teams, status, the start field
                 (--start-field) AS SERVED with its zone or offset as written, and every other time-like field as
                 served with its zone. Required per game: the id, start, home and away fields; one not served (absent,
                 null or empty) REFUSES that game; a game id served more than once REFUSES every row for it (none is
                 picked).
  (3) STARTERS   the projected-starters endpoint (--starters-path): every field name as served (the union over items),
                 and per game the projected starting goaltender per team (--home-goalie-field, --away-goalie-field: the
                 goalie as served, its non-price fields) with THE SOURCE'S OWN STAMP (--stamp-field, repeatable, a
                 dotted path such as A.B for a per-goalie stamp; REQUIRED, no default) against the game's start time
                 from section 2 (joined by --game-id-field). Per game and stamp: the stamp AS SERVED, the start AS
                 SERVED, how each was read, and whether the stamp is BEFORE the start, from the response values only,
                 never our clock. A value with no zone stated is read only in --served-zone (an IANA name the
                 operator takes from the vendor's documentation; NO default); without it, a value with no zone REFUSES
                 that game, and so does a wall time that zone skips or repeats at a clock change (never a guessed
                 reading). Stamp and start are compared as instants in UTC. A stamp that is missing, null, empty, a
                 bare number or unparseable REFUSES that game; so does a game with no goaltender served for a side
                 (absent, null, empty, an empty list, an object whose every value is null or empty), more than one
                 goaltender served for a side (every entry printed, none picked), no start time read, a GameID served
                 by more than one starters item (every item printed, the game counted once), or (a game of section 2)
                 no starters item.
                 Without --stamp-quote (the documentation's sentence naming the stamp field, quoted by the operator)
                 the section prints its reads and is REFUSED: the stamp's identification is not on the receipt.
  (4) TERMS      the vendor's terms (279 item 3(b): "the vendor's terms on storing and keeping the data after the
                 subscription ends"): the page --terms-url names (NO default: no URL is typed here) is read, markup
                 stripped, and EVERY sentence holding a retention or storage word (TERMS_RETENTION_WORDS) quoted first,
                 none dropped; sentences holding only a generic word (TERMS_GENERIC_WORDS) fill the quote up to
                 TERMS_QUOTES, the rest counted on the receipt, a cut marked with its full length. With no terms URL
                 the terms are NOT READ and the section is REFUSED; a read that fails is FAILED; a page with nothing to
                 quote, or a retention passage too long to quote whole, is REFUSED. The probe quotes; it does not
                 decide what the terms allow.

  KALSHI: NONE. KXNHLGAME is untouched (279 item 5): this probe imports no Kalshi code and makes no Kalshi call; the
  nhl-daily market-only chain and KXNHLGAME run on regardless (279 item 3).

PRICES: no price, quote or billing figure is read into a receipt or printed (279 item 3(c)). A price-class field prints
by NAME only, at any depth (a goaltender served as a list included); any currency figure in any printed text (a terms
page included) is replaced by "<figure not printed>". The raw answers are never written: the receipt holds the printed
reads only.

TRIAL DATA: whether the vendor alters the values a trial key is served is the vendor's documentation's to say, and the
operator's to quote with the receipt; the probe cannot tell.

    python3 scripts/nhl_source_probe.py --stamp-field <FIELD FROM THE DOCS> --stamp-quote "<THE DOCS' SENTENCE>" \\
        --terms-url <THE VENDOR'S TERMS PAGE> [--served-zone <IANA ZONE FROM THE DOCS>] [--date YYYY-MM-DD] \\
        [--base-url URL] [--key-header NAME] [--status-path P] [--games-path P] [--starters-path P] \\
        [--game-id-field F] [--start-field F] [--home-team-field F] [--away-team-field F] [--status-field F] \\
        [--status-value-field F ...] [--home-goalie-field F] [--away-goalie-field F] \\
        [--skip status|games|starters|terms] [--out /path/receipt.json]

Exit: 0 every read answered; 1 a call failed (network, HTTP other than 401/403, an answer that is not JSON or not of the
shape its reader needs, a section that raised, a receipt that could not be written); 2 a read REFUSED (the key not set
or not accepted, a required field not served, a stamp missing or unparseable, a value with no zone and no
--served-zone, no --stamp-field or --stamp-quote, a 200 carrying an error body, a duplicated game id, the terms not
read, --skip naming every section, a key in a URL, --out under data/ in any case or not writable, a bad --date or
--served-zone). Both: 1 (a failed call is fixed first,
the tennis probe's rule). Writes nothing unless --out is given (never under data/: law 5; checked before any call).
Imports nothing that opens the DB.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

ROOT = Path(__file__).resolve().parents[1]

OK, FAILED, REFUSED = 0, 1, 2
SECTIONS = ("status", "games", "starters", "terms")

KEY_NAME = "SPORTSDATAIO_NHL_KEY"           # the product's key, by NAME (the docstring says why one name)
# UNVERIFIED defaults (no network and no vendor documentation where this was written): the operator confirms each one
# against the vendor's documentation on the first run, and passes the documented value where it differs.
BASE_URL = "https://api.sportsdata.io/v3/nhl"
KEY_HEADER = "Ocp-Apim-Subscription-Key"
STATUS_PATH = "/scores/json/CurrentSeason"
GAMES_PATH = "/scores/json/GamesByDate/{date_mon}"
STARTERS_PATH = "/projections/json/StartingGoaltendersByDate/{date_mon}"
GAME_ID_FIELD, START_FIELD, STATUS_FIELD = "GameID", "DateTime", "Status"
HOME_TEAM_FIELD, AWAY_TEAM_FIELD = "HomeTeam", "AwayTeam"
HOME_GOALIE_FIELD, AWAY_GOALIE_FIELD = "HomeGoaltender", "AwayGoaltender"
# No default, ever: the stamp field, the served zone and the terms URL are the operator's, read from the vendor.
STAMP_FIELD = None
SERVED_ZONE = None
TERMS_URL = None

MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
RATE_HEADER = re.compile(r"rate.?limit|retry-after|quota", re.I)
# A price-class field: its NAME prints, its value never does (279 item 3(c)); salaries and betting lines included.
PRICE_FIELD = re.compile(r"price|cost|fee|amount|charge|bill|invoice|payment|quote|currency|usd|dollar|salary|"
                         r"subscription|plan|moneyline|spread|odds|overunder|payout|wager|per.?month|per.?year", re.I)
# Whole words of a camelCase or snake_case field name that are price-class too ("MonthlyRate", "Tier"), matched as
# words so that "GeneratedAt" is not read as a rate.
PRICE_WORD = re.compile(r"^(?:rates?|monthly|annual|annually|yearly|tiers?|premium|discount|tax|vat|tariff)$",
                        re.I)
# The status answer prints every field NAME as served and the VALUES of these names only (an allow-list, the basketball
# probe's status_summary rule: no billing figure under a name the price rule misses, no account field). UNVERIFIED
# hypotheses (season fields), each printed served or not served; the operator names others with --status-value-field.
STATUS_VALUE_FIELDS = ("Season", "SeasonType", "ApiSeason")
# A 200 whose object answer carries one of these top-level names is an error body, not an answer (compared without
# case, whole names only).
ERROR_KEYS = ("code", "statuscode", "status_code", "message", "error", "errors", "errormessage", "error_message",
              "fault")
TIME_FIELD = re.compile(r"date|time|day|updated|stamp|created|modified|published", re.I)
# A currency figure in any printed text: a currency sign then a digit (the #813 guard's dollar rule, widened to the
# euro and pound signs), or a number beside a currency word. Replaced before any line or receipt shows it.
FIGURE = re.compile("[$＄﹩€£][ \t ]*[+\\-−]?[ \t ]*\\.?[0-9][0-9,.]*"
                    r"|\b[0-9][0-9,.]*[ \t ]*(?:USD|EUR|GBP|dollars?)\b|\b(?:USD|EUR|GBP)[ \t ]*[0-9][0-9,.]*",
                    re.I)
KEY_IN_URL = re.compile(r"key\s*=|\{key", re.I)
# Retention words first: every passage holding one is quoted, ahead of the generic ones, never dropped (279 items 3(b)
# and 5: "the retention clause quoted"). Generic words fill the quote up to TERMS_QUOTES, the rest counted.
TERMS_RETENTION_WORDS = ("retain", "retention", "store", "stored", "storing", "storage", "cache", "caching", "delet",
                         "destroy", "purg", "terminat", "expir", "cancel", "archiv", "persist")
TERMS_GENERIC_WORDS = ("database", "licen", "redistribut", "copy", "copies", "own")
TERMS_WORDS = TERMS_RETENTION_WORDS + TERMS_GENERIC_WORDS
TERMS_QUOTES, TERMS_QUOTE_CHARS, TERMS_HEAD_CHARS = 20, 600, 600
TERMS_RETENTION_CHARS = 3000                 # a retention passage longer than this is cut, marked, and REFUSED
SAMPLE = 40


class Out:
    """Every printed line and the receipt pass through here: any secret value and any currency figure is replaced
    before it is shown. No error text is cut before it gets here (a cut inside an echoed key would leave a prefix no
    longer equal to the secret)."""

    def __init__(self):
        self.secrets: set[str] = set()
        self.lines: list[str] = []

    def redact(self, text: str) -> str:
        for s in sorted(self.secrets, key=len, reverse=True):
            if s:
                text = text.replace(s, "<redacted>")
        return FIGURE.sub("<figure not printed>", text)

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
    """Every header whose name holds rate-limit, retry-after or quota, as served (names and values read, never
    assumed; none served prints {})."""
    return {k: v for k, v in (hdr or {}).items() if RATE_HEADER.search(str(k))}


def priced(path: str) -> bool:
    """A field path any of whose segments is price-class (a PRICE_FIELD fragment, or a PRICE_WORD as a whole word of
    the camelCase or snake_case name): its value never prints."""
    for seg in (x for x in re.split(r"[.\[\]]+", path) if x):
        if PRICE_FIELD.search(seg):
            return True
        if any(PRICE_WORD.match(w) for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+", seg)):
            return True
    return False


def item_keys(o, prefix: str = "") -> list[str]:
    """Every key path of a dict, dotted, sorted (the item's shape as served); a nested list's elements, every one of
    them (a field served on a later element only included), as "key[]"."""
    out: set[str] = set()
    if isinstance(o, dict):
        for k, v in o.items():
            out.add(prefix + str(k))
            out.update(item_keys(v, prefix + str(k) + "."))
    elif isinstance(o, list):
        for x in o:
            out.update(item_keys(x, prefix.rstrip(".") + "[]."))
    return sorted(out)


def field_union(items: list) -> list[str]:
    """The union of every item's key paths, sorted: every field name as served across the answer."""
    out: set[str] = set()
    for it in items:
        out.update(item_keys(it))
    return sorted(out)


def names_line(fields: list[str]) -> str:
    return " · ".join(f + (" (price-class: name only)" if priced(f) else "") for f in fields)


def safe_scalars(o, prefix: str = "") -> dict:
    """The scalar fields of a dict as served, dotted, a price-class field's value replaced (its name kept)."""
    out: dict = {}
    if isinstance(o, dict):
        for k, v in o.items():
            p = prefix + str(k)
            if isinstance(v, (dict, list)):
                if isinstance(v, dict):
                    out.update(safe_scalars(v, p + "."))
                else:
                    out[p] = f"<list of {len(v)}>"
            else:
                out[p] = "<value not printed: price-class field>" if priced(p) else v
    return out


def safe_repr(v) -> str:
    """Any served value as text with every price-class value replaced, at any depth: a dict by its safe scalars, a list
    entry by entry, a scalar as served. Never a raw repr of a container."""
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}={x!r}" for k, x in safe_scalars(v).items()) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(safe_repr(x) for x in v) + "]"
    return repr(v)


def get_path(o, path: str) -> tuple[bool, object]:
    """(served, value) for a dotted path: served False when a segment is absent (null is served, and read as such)."""
    cur = o
    for seg in path.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return False, None
        cur = cur[seg]
    return True, cur


def blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def zone_of(v) -> str:
    """The zone a time value states as written: Z, an offset, a number, or none stated."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return "a number"
    s = str(v if v is not None else "").strip()
    if not s:
        return "empty"
    if re.search(r"\d[T ]\d{2}:\d{2}.*Z$", s):
        return "Z"
    m = re.search(r"[+-]\d{2}(?::?\d{2}(?::?\d{2}(?:\.\d+)?)?)?$", s)
    if m and re.search(r"\d[T ]\d{2}:\d{2}", s):
        return f"offset {m.group(0)}"
    return "no zone stated"


def read_instant(v, zone: ZoneInfo | None) -> tuple[datetime | None, str]:
    """(the instant, how it was read) from a served value only, or (None, why not). An ISO 8601 date and time with Z or
    an offset is read as written; one with no zone is read only in the operator's --served-zone; a bare number (unit
    and epoch undocumented here), a date with no time, or any other text is not read."""
    if v is None:
        return None, "null"
    if isinstance(v, bool) or isinstance(v, (int, float)):
        return None, f"a number ({v!r}), not a time as written: its unit and epoch are the vendor's documentation's"
    s = str(v).strip()
    if not s:
        return None, "empty"
    if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", s):
        return None, f"not an ISO 8601 date and time as written: {s!r}"
    try:
        dt = datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
    except ValueError:
        return None, f"not an ISO 8601 date and time as written: {s!r}"
    if dt.tzinfo is None:
        if zone is None:
            return None, (f"{s!r} states no zone; pass --served-zone with the zone the vendor's documentation gives "
                          "for its times (quoted with the receipt)")
        a0, a1 = dt.replace(tzinfo=zone, fold=0), dt.replace(tzinfo=zone, fold=1)
        if a0.utcoffset() != a1.utcoffset():          # a wall time a clock change skips or repeats: no guessed reading
            back = a0.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
            kind = ("does not exist (the clock change skips it)" if back != dt
                    else "is ambiguous (the clock change repeats it)")
            return None, f"{s!r} states no zone and {kind} in --served-zone {zone.key}: not read, never guessed"
        return a0, f"no zone stated; read in --served-zone {zone.key}"
    label = zone_of(s)
    if not (label == "Z" or label.startswith("offset ")):
        label = f"offset {dt.utcoffset()}"
    return dt, f"{label}, as served"


def render(path: str, day: str) -> str:
    y, m, d = day.split("-")
    return path.replace("{date_mon}", f"{y}-{MONTHS[int(m) - 1]}-{d}").replace("{date}", day)


# ---- (1) the status read -----------------------------------------------------------------------------------------

def status_section(a, key: str, say: Out, get=http_get) -> tuple[int, dict]:
    url = a.base_url.rstrip("/") + a.status_path
    say(f"\n(1) STATUS (or equivalent) · GET {url} · key by NAME {KEY_NAME} in header {a.key_header} (UNVERIFIED)")
    status, hdr, body, err = get(url, headers={a.key_header: key})
    rec: dict = {"url": url, "http": status, "rate_limit": rate_headers(hdr)}
    say(f"  HTTP {status} · rate-limit {rate_headers(hdr)}" + (f" · FAILED: {err}" if err else ""))
    if err:
        rec["error"] = err
        if status in (401, 403):
            say(f"  REFUSED: the key named {KEY_NAME} was not accepted (HTTP {status}); the operator checks the "
                "trial key, the header name and the path against the vendor's documentation")
            return REFUSED, rec
        return FAILED, rec
    rec["answer_type"] = type(body).__name__
    if isinstance(body, dict):
        rec["fields"] = item_keys(body)
        say(f"  FIELDS as served ({len(rec['fields'])}): {names_line(rec['fields'])}")
        errs = [k for k in body if str(k).casefold() in ERROR_KEYS]
        if errs:
            rec["error_body"] = {k: ("<value not printed: price-class field>" if priced(str(k)) else
                                     safe_repr(body[k])) for k in errs}
            for k, v in rec["error_body"].items():
                say(f"    {k} = {v}")
            say(f"  REFUSED: HTTP 200 carrying an error body (field(s) {', '.join(map(str, errs))}): the key named "
                f"{KEY_NAME} is not shown to have answered; the operator checks the key, the header and the path")
            return REFUSED, rec
        rec["values"] = {}
        say(f"  VALUES of the --status-value-field names only (the rest by NAME above):")
        for f in a.status_value_field:
            served, v = get_path(body, f)
            if not served:
                say(f"    {f}: not served")
                continue
            if priced(f):
                shown = "<value not printed: price-class field>"
            elif isinstance(v, (dict, list)):
                shown = f"<{type(v).__name__}: its names above>"
            else:
                shown = v
            rec["values"][f] = shown
            say(f"    {f} = {shown!r}")
    elif isinstance(body, list):
        rec["items"] = len(body)
        rec["fields"] = field_union(body)
        say(f"  a list of {len(body)} · FIELDS as served: {names_line(rec['fields'])}")
    else:
        say(f"  a {type(body).__name__} as served (its value not printed: a bare answer has no field name the price "
            "rule can read)")
    say(f"  the key named {KEY_NAME} answered (the value is never printed)")
    return OK, rec


# ---- (2) the games of the day ------------------------------------------------------------------------------------

def game_row(a, g: dict) -> dict:
    """One games item, read by the field names the options give; a required field absent, null or empty is missing."""
    req = (("id", a.game_id_field), ("start", a.start_field), ("home", a.home_team_field),
           ("away", a.away_team_field))
    row: dict = {"missing": []}
    for label, f in req:
        served, v = get_path(g, f)
        row[label] = v if served else None
        if not served or blank(v):
            row["missing"].append(f)
    served, v = get_path(g, a.status_field)
    row["status"] = v if served else "<not served>"
    row["start_zone"] = zone_of(row["start"])
    row["times"] = {k: (v, zone_of(v)) for k, v in safe_scalars(g).items()
                    if TIME_FIELD.search(k) and k != a.start_field and not priced(k)}
    return row


def games_section(a, key: str, say: Out, get=http_get) -> tuple[int, dict, dict]:
    url = a.base_url.rstrip("/") + render(a.games_path, a.date)
    say(f"\n(2) THE NHL GAMES OF THE DAY · --date {a.date} (a UTC calendar day, as given; the vendor's day boundary is "
        f"its documentation's: the games print as served, unfiltered) · GET {url} (UNVERIFIED path)")
    status, hdr, body, err = get(url, headers={a.key_header: key})
    rec: dict = {"url": url, "date_utc": a.date, "http": status, "rate_limit": rate_headers(hdr)}
    if err is None and not isinstance(body, list):
        err = f"the answer is {type(body).__name__}, not a list of games"
    say(f"  HTTP {status} · {len(body) if isinstance(body, list) else '?'} items · rate-limit {rate_headers(hdr)}"
        + (f" · FAILED: {err}" if err else ""))
    if err:
        rec["error"] = err
        return (REFUSED if status in (401, 403) else FAILED), rec, {}
    items = [g for g in body if isinstance(g, dict)]
    rec["fields"] = field_union(items)
    say(f"  FIELDS as served (every game's, {len(rec['fields'])}): {names_line(rec['fields'])}")
    rows = [game_row(a, g) for g in items]
    rec["games"] = rows
    code = OK
    if len(items) < len(body):
        say(f"  REFUSED: {len(body) - len(items)} item(s) are not objects")
        code = REFUSED
    if not rows:
        say(f"  REFUSED: no game served for {a.date}; run on a game day")
        code = REFUSED
    games: dict = {}
    for r in rows[:SAMPLE * 2]:
        say(f"    game {r['id']!r} · {r['away']!r} @ {r['home']!r} · {a.status_field} {r['status']!r} · "
            f"{a.start_field} = {r['start']!r} ({r['start_zone']})")
        for k, (v, z) in r["times"].items():
            say(f"      {k} = {v!r} ({z})")
    bad = [r for r in rows if r["missing"]]
    for r in bad:
        say(f"  REFUSED: game {r['id']!r}: required field(s) not served: {', '.join(r['missing'])} (required: "
            f"{', '.join((a.game_id_field, a.start_field, a.home_team_field, a.away_team_field))})")
        code = REFUSED
    n_id: dict = {}
    for r in rows:
        if not r["missing"]:
            n_id[str(r["id"])] = n_id.get(str(r["id"]), 0) + 1
    dups = sorted(k for k, n in n_id.items() if n > 1)
    for k in dups:
        say(f"  REFUSED: game id {k!r} served {n_id[k]} times (exactly once required; none is picked): every row "
            "for it is refused")
        code = REFUSED
    for r in rows:
        if not r["missing"] and str(r["id"]) not in dups:
            games[str(r["id"])] = r
    rec["refused_games"] = [str(r["id"]) for r in bad] + dups
    return code, rec, games


# ---- (3) the projected starters ----------------------------------------------------------------------------------

def goalie_text(v) -> str:
    """The goalie as served, every price-class value replaced at any depth (a list entry by entry)."""
    return safe_repr(v)


def goalie_refusal(served: bool, g, side: str, f: str) -> str | None:
    """Why a side's projected goaltender is not read, or None: not served, null or empty; an empty list; more than one
    entry (none is picked); an object whose every value is null or empty."""
    where = f"for the {side} side under {f}"
    if not served or blank(g):
        return f"no projected goaltender served {where}"
    if isinstance(g, list):
        if not g:
            return f"an empty list served {where}"
        if len(g) > 1:
            return f"{len(g)} goaltenders served {where} (exactly one required; none is picked)"
        return goalie_refusal(True, g[0], side, f)
    if isinstance(g, dict) and all(blank(x) or x == {} or x == [] for x in safe_scalars(g).values()):
        return f"a goaltender with every value null or empty served {where}"
    return None


def compare(stamp_v, start_v, zone: ZoneInfo | None) -> dict:
    """One stamp against one start, from the served values only: BEFORE / NOT BEFORE, or REFUSED with the reason."""
    s_dt, s_how = read_instant(stamp_v, zone)
    t_dt, t_how = read_instant(start_v, zone)
    out = {"stamp": stamp_v, "stamp_read": s_how, "start": start_v, "start_read": t_how}
    if s_dt is None:
        out.update(verdict="REFUSED", why=f"the stamp is not read: {s_how}")
    elif t_dt is None:
        out.update(verdict="REFUSED", why=f"the start is not read: {t_how}")
    else:
        s_u, t_u = s_dt.astimezone(timezone.utc), t_dt.astimezone(timezone.utc)   # instants, never wall clocks
        mins = (t_u - s_u).total_seconds() / 60
        out.update(verdict="BEFORE" if s_u < t_u else "NOT BEFORE", minutes_before_start=round(mins, 1))
    return out


def starters_section(a, key: str, say: Out, games: dict | None, zone: ZoneInfo | None,
                     get=http_get) -> tuple[int, dict]:
    url = a.base_url.rstrip("/") + render(a.starters_path, a.date)
    say(f"\n(3) THE PROJECTED STARTERS · GET {url} (UNVERIFIED path) · stamp field(s) {a.stamp_field} (named by the "
        "operator from the vendor's documentation; no default)")
    rec: dict = {"url": url, "stamp_fields": a.stamp_field, "stamp_quote": a.stamp_quote,
                 "served_zone": zone.key if zone else None}
    code = OK
    if a.stamp_quote:
        say(f'  THE DOCUMENTATION ON THE STAMP, as quoted by the operator: "{a.stamp_quote}"')
    else:
        say("  REFUSED: no --stamp-quote: the documentation's sentence naming the stamp field is not on the receipt "
            "(279 item 5: \"the stamp field identified by the vendor's documentation, quoted\"); the reads still print")
        code = REFUSED
    status, hdr, body, err = get(url, headers={a.key_header: key})
    rec.update(http=status, rate_limit=rate_headers(hdr))
    if err is None and not isinstance(body, list):
        err = f"the answer is {type(body).__name__}, not a list"
    say(f"  HTTP {status} · {len(body) if isinstance(body, list) else '?'} items · rate-limit {rate_headers(hdr)}"
        + (f" · FAILED: {err}" if err else ""))
    if err:
        rec["error"] = err
        return (REFUSED if status in (401, 403) else FAILED), rec
    items = [x for x in body if isinstance(x, dict)]
    rec["fields"] = field_union(items)
    say(f"  FIELDS as served (every item's, {len(rec['fields'])}): {names_line(rec['fields'])}")
    if len(items) < len(body):
        say(f"  REFUSED: {len(body) - len(items)} item(s) are not objects")
        code = REFUSED
    for f in a.stamp_field:
        if f not in rec["fields"]:
            say(f"  the stamp field {f!r} is not among the served field names above")
    if games is None:
        say("  no start times read (section 2 skipped, refused or failed): every game's comparison is REFUSED")
    n_items: dict = {}
    for it in items:
        s_, g_ = get_path(it, a.game_id_field)
        if s_ and not blank(g_):
            n_items[str(g_)] = n_items.get(str(g_), 0) + 1
    rows, seen = [], set()
    for i, it in enumerate(items):
        id_served, gid = get_path(it, a.game_id_field)
        has_id = id_served and not blank(gid)
        row: dict = {"item": i, "game": gid if id_served else None, "goalies": {}, "stamps": [], "refused": []}
        rows.append(row)
        row["key"] = str(gid) if has_id else f"item {i}"
        if not has_id:
            row["refused"].append(f"no {a.game_id_field} served")
        else:
            seen.add(str(gid))
            if n_items[str(gid)] > 1:
                row["refused"].append(f"{a.game_id_field} {str(gid)!r} served by {n_items[str(gid)]} starters items "
                                      "(exactly one required; none is picked)")
        for side, f in (("home", a.home_goalie_field), ("away", a.away_goalie_field)):
            served, g = get_path(it, f)
            row["goalies"][side] = goalie_text(g) if served else None
            why = goalie_refusal(served, g, side, f)
            if why:
                row["refused"].append(why)
        game = (games or {}).get(str(gid)) if has_id else None
        start = game["start"] if game else None
        if game is None:
            row["refused"].append("no start time read for this game" + ("" if games is not None else
                                                                        " (section 2 not read)"))
        for f in a.stamp_field:
            s_served, s_v = get_path(it, f)
            if not s_served or blank(s_v):
                row["stamps"].append({"field": f, "stamp": s_v, "verdict": "REFUSED", "why": "the stamp is not "
                                      + ("served" if not s_served else "null or empty")})
                row["refused"].append(f"stamp {f} not served" if not s_served else f"stamp {f} null or empty")
                continue
            c = compare(s_v, start, zone) if game else {"stamp": s_v, "stamp_read": read_instant(s_v, zone)[1],
                                                        "start": None, "verdict": "REFUSED",
                                                        "why": "no start time read"}
            c["field"] = f
            row["stamps"].append(c)
            if c["verdict"] == "REFUSED" and game:
                row["refused"].append(f"stamp {f}: {c['why']}")
        row["verdict"] = ("REFUSED" if row["refused"] else
                          "PREGAME" if all(s["verdict"] == "BEFORE" for s in row["stamps"]) else "NOT PREGAME")
        say(f"    game {row['game']!r}" + (f" · {game['away']!r} @ {game['home']!r}" if game else "")
            + f" · start {a.start_field} = {start!r}")
        say(f"      projected home goaltender ({a.home_goalie_field}): {row['goalies']['home']}")
        say(f"      projected away goaltender ({a.away_goalie_field}): {row['goalies']['away']}")
        for s in row["stamps"]:
            line = f"      STAMP {s['field']} = {s['stamp']!r}"
            if s.get("stamp_read"):
                line += f" ({s['stamp_read']})"
            if s["verdict"] in ("BEFORE", "NOT BEFORE"):
                line += (f" vs start {s['start']!r} ({s['start_read']}): {s['verdict']} the start "
                         f"({s['minutes_before_start']} minutes, from the served values)")
            else:
                line += f": REFUSED: {s['why']}"
            say(line)
        say(f"      VERDICT {row['verdict']}" + (f": {'; '.join(row['refused'])}" if row["refused"] else
                                                 " (every stamp before the start, read from the response)"
                                                 if row["verdict"] == "PREGAME" else
                                                 " (a stamp at or after the start, read from the response)"))
    missing = sorted(set(games or {}) - seen)
    for gid in missing:
        say(f"    game {gid!r} (section 2): REFUSED: no starters item served for it")
        rows.append({"item": None, "game": gid, "key": gid, "goalies": {}, "stamps": [], "verdict": "REFUSED",
                     "refused": ["no starters item served"]})
    rec["games"] = rows
    by_game: dict = {}                   # a game counted once, however many items it was served by
    for r in rows:
        by_game[r["key"]] = "REFUSED" if r["verdict"] == "REFUSED" else by_game.get(r["key"], r["verdict"])
    n = {v: sum(1 for x in by_game.values() if x == v) for v in ("PREGAME", "NOT PREGAME", "REFUSED")}
    rec["counts"] = n
    say(f"  GAMES: {len(by_game)} · PREGAME {n['PREGAME']} · NOT PREGAME {n['NOT PREGAME']} · REFUSED {n['REFUSED']}")
    if not rows:
        say(f"  REFUSED: no projected starters served for {a.date}; run on a game day")
        code = REFUSED
    if n["REFUSED"]:
        code = REFUSED
    return code, rec


# ---- (4) the terms -----------------------------------------------------------------------------------------------

def cut(x: str, n: int) -> tuple[str, bool]:
    return (x, False) if len(x) <= n else (x[:n] + f" ... [cut at {n} of {len(x)} characters]", True)


def terms_read(page: str) -> dict:
    """The terms page's retention and storage clauses, quoted: script/style dropped, tags stripped, entities
    unescaped, split into sentences. EVERY sentence holding a word that starts with one of TERMS_RETENTION_WORDS is
    quoted first, in page order, none dropped (each up to TERMS_RETENTION_CHARS; one longer is cut, marked, and counted
    as cut); then the sentences holding only a generic word (TERMS_GENERIC_WORDS) fill the quote up to TERMS_QUOTES,
    each up to TERMS_QUOTE_CHARS with a cut marked, the rest counted as not quoted; the page's head when no sentence
    holds a listed word. The probe quotes; it does not decide what the terms allow."""
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page or "")
    t = re.sub(r"(?s)<[^>]+>", "\n", t)
    t = html.unescape(t)
    parts = [re.sub(r"\s+", " ", x).strip() for x in re.split(r"(?<=[.!?])\s+|\n+", t)]
    parts = [x for x in parts if x]
    def words(ws):
        return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in ws) + ")", re.I)   # at a word's start
    ret_w, gen_w = words(TERMS_RETENTION_WORDS), words(TERMS_GENERIC_WORDS)
    ret = [cut(x, TERMS_RETENTION_CHARS) for x in parts if ret_w.search(x)]
    gen = [x for x in parts if not ret_w.search(x) and gen_w.search(x)]
    room = max(TERMS_QUOTES - len(ret), 0)
    quoted = [q for q, _ in ret] + [cut(x, TERMS_QUOTE_CHARS)[0] for x in gen[:room]]
    out = {"quoted": quoted, "retention": len(ret), "retention_cut": sum(1 for _, c in ret if c),
           "not_quoted": max(len(gen) - room, 0)}
    if not quoted:
        head = " ".join(parts)
        out["quoted"] = [cut(head, TERMS_HEAD_CHARS)[0]] if head else []
    return out


def terms_excerpt(page: str) -> list[str]:
    """The quoted passages of terms_read (retention first)."""
    return terms_read(page)["quoted"]


def terms_section(a, say: Out, get=http_get) -> tuple[int, dict]:
    say("\n(4) THE VENDOR'S TERMS (279 item 3(b): storing and keeping the data after the subscription ends)")
    if not a.terms_url:
        say("  TERMS NOT READ (no --terms-url given; no URL is typed here): REFUSED until the terms page is named and "
            "its retention clause quoted (279 items 3(b) and 5)")
        return REFUSED, {"url": None, "read": False}
    status, hdr, page, err = get(a.terms_url, text=True)          # no key is sent to the terms page
    say(f"  TERMS {a.terms_url} · HTTP {status}" + (f" · FAILED: {err}" if err else ""))
    if err:
        say("  TERMS NOT READ: the retention clause is not quoted")
        return FAILED, {"url": a.terms_url, "read": False, "http": status, "error": err}
    t = terms_read(page)
    quoted = t["quoted"]
    rec = {"url": a.terms_url, "read": bool(quoted), "http": status, "chars": len(page), "quoted": quoted,
           "retention_passages": t["retention"], "retention_cut": t["retention_cut"], "not_quoted": t["not_quoted"]}
    if not quoted:
        say("  TERMS NOT QUOTED (the page yields no text to quote): REFUSED")
        return REFUSED, rec
    say(f"  TERMS QUOTED ({len(quoted)} passage{'' if len(quoted) == 1 else 's'}: first every one holding a retention "
        f"or storage word {list(TERMS_RETENTION_WORDS)} ({t['retention']}), then those holding "
        f"{list(TERMS_GENERIC_WORDS)}, "
        "or the page's head; markup stripped; the operator quotes the clause on #105 and the architect reads what it "
        "allows):")
    for q in quoted:
        say(f'    "{q}"')
    if t["not_quoted"]:
        say(f"  (+{t['not_quoted']} more passage{'' if t['not_quoted'] == 1 else 's'} holding only a generic word, not "
            "quoted; every retention passage is quoted above)")
    if t["retention_cut"]:
        say(f"  REFUSED: {t['retention_cut']} retention passage(s) longer than {TERMS_RETENTION_CHARS} characters were "
            "cut (marked above): the clause is not quoted whole; the operator quotes it from the page")
        return REFUSED, rec
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
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    U = "UNVERIFIED default; the operator confirms it against the vendor's documentation"
    ap = argparse.ArgumentParser(description="NHL source probe (addendum 279 item 3(a); read-only)")
    ap.add_argument("--date", default=today, help="the game day, YYYY-MM-DD, a UTC calendar day (default: today UTC)")
    ap.add_argument("--stamp-field", action="append", default=None,
                    help="the starters answer's field that says when the projection was published, named from the "
                         "vendor's documentation (dotted for a nested field; repeatable). NO default; required for "
                         "section 3")
    ap.add_argument("--stamp-quote", default=None,
                    help="the vendor documentation's sentence naming the stamp field, quoted (without it section 3 is "
                         "REFUSED)")
    ap.add_argument("--served-zone", default=SERVED_ZONE,
                    help="the IANA zone the vendor's documentation gives for times served with no zone (NO default: "
                         "without it such a time refuses its game)")
    ap.add_argument("--terms-url", default=TERMS_URL,
                    help="the vendor's terms page (NO default: without it the terms are NOT READ, section 4 REFUSED)")
    ap.add_argument("--base-url", default=BASE_URL, help=U)
    ap.add_argument("--key-header", default=KEY_HEADER, help=f"the header carrying {KEY_NAME}'s value; {U}")
    ap.add_argument("--status-path", default=STATUS_PATH, help=U)
    ap.add_argument("--games-path", default=GAMES_PATH, help=U + "; {date} or {date_mon} in it")
    ap.add_argument("--starters-path", default=STARTERS_PATH, help=U + "; {date} or {date_mon} in it")
    ap.add_argument("--game-id-field", default=GAME_ID_FIELD, help=U + " (both answers)")
    ap.add_argument("--start-field", default=START_FIELD, help=U + " (the games answer)")
    ap.add_argument("--home-team-field", default=HOME_TEAM_FIELD, help=U)
    ap.add_argument("--away-team-field", default=AWAY_TEAM_FIELD, help=U)
    ap.add_argument("--status-field", default=STATUS_FIELD, help=U + " (printed as served; not required)")
    ap.add_argument("--status-value-field", action="append", default=None,
                    help="a status-answer field whose VALUE prints (repeatable; every other field prints by NAME only; "
                         f"a price-class name never prints its value); {U}: {', '.join(STATUS_VALUE_FIELDS)}")
    ap.add_argument("--home-goalie-field", default=HOME_GOALIE_FIELD, help=U + " (the starters answer)")
    ap.add_argument("--away-goalie-field", default=AWAY_GOALIE_FIELD, help=U + " (the starters answer)")
    ap.add_argument("--skip", action="append", default=[], choices=SECTIONS)
    ap.add_argument("--out", type=Path, default=None, help="write the JSON receipt here (never under data/)")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return REFUSED if e.code else OK
    a.status_value_field = a.status_value_field or list(STATUS_VALUE_FIELDS)
    say = Out()
    if set(SECTIONS) <= set(a.skip):
        say("REFUSED: --skip names every section; nothing would be read")
        return REFUSED
    refused = refuse_out(a.out) or (prepare_out(a.out) if a.out else None)
    if refused:
        say(refused)
        return REFUSED
    try:
        if datetime.strptime(a.date, "%Y-%m-%d").strftime("%Y-%m-%d") != a.date:   # zero-padded, as rendered
            raise ValueError(a.date)
    except ValueError:
        say(f"REFUSED: --date {a.date!r} is not YYYY-MM-DD")
        return REFUSED
    zone = None
    if a.served_zone:
        try:
            zone = ZoneInfo(a.served_zone)
        except (ZoneInfoNotFoundError, ValueError):
            say(f"REFUSED: --served-zone {a.served_zone!r} is not an IANA zone name")
            return REFUSED
    if "starters" not in a.skip and not a.stamp_field:
        say("REFUSED: no --stamp-field: section 3 compares the source's OWN stamp with the start, and its field is "
            "named from the vendor's documentation, never typed here (pass it, or --skip starters)")
        return REFUSED
    for label, v in (("--base-url", a.base_url), ("--status-path", a.status_path), ("--games-path", a.games_path),
                     ("--starters-path", a.starters_path)):
        if KEY_IN_URL.search(v):
            say(f"REFUSED: {label} names a key in the URL; the key travels in --key-header only, never in a URL")
            return REFUSED
    _load_env()
    raw = os.environ.get(KEY_NAME) or ""
    say.secrets.update(x for x in (raw, raw.strip()) if x.strip())
    key = raw.strip()
    say(f"NHL SOURCE PROBE (addendum 279 item 3(a), lane nhl, #105) · read-only · day {a.date} (UTC) · "
        f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} (our clock: printed for the record, never compared)")
    say(f"  key {KEY_NAME}: {'set (the value is never printed)' if key else 'not set'} · KALSHI: none (KXNHLGAME "
        "untouched, 279 item 5)")
    receipt: dict = {"probe": "nhl_source_probe", "ruling": "ARCHITECT 2026-11-06 19:40 ET, addendum 279 item 3(a)",
                     "date_utc": a.date, "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "key_name": KEY_NAME, "key_set": bool(key), "sections": {}}
    codes: list[int] = []
    keyed_ok = True                      # a status read that did not answer stops the metered sections' calls
    games: dict | None = None

    def no_key(name):
        why = (f"{KEY_NAME} is not set: no call made (the operator puts the trial key in .env by that NAME)" if not key
               else "the status read did not answer: no call made (a metered trial is not spent on a key that did "
                    "not answer; --skip status runs this section without it)")
        say(f"\n({name}) REFUSED: {why}")
        return REFUSED, {"refused": why}

    for name in SECTIONS:
        if name in a.skip:
            say(f"\n({name}) skipped (--skip)")
            continue
        try:
            if name != "terms" and (not key or not keyed_ok):
                code, rec = no_key(name)
            elif name == "status":
                code, rec = status_section(a, key, say)
                keyed_ok = code == OK
            elif name == "games":
                code, rec, games = games_section(a, key, say)
                if code == FAILED:
                    games = None
            elif name == "starters":
                code, rec = starters_section(a, key, say, games, zone)
            else:
                code, rec = terms_section(a, say)
        except Exception as e:           # each section independent: an unexpected shape is FAILED, never a traceback
            say(f"  FAILED: {type(e).__name__}: {e} (section {name} stopped; the next section runs)")
            code, rec = FAILED, {"error": f"{type(e).__name__}: {e}"}
        receipt["sections"][name] = {"exit": code, **rec}
        codes.append(code)
    rc = FAILED if FAILED in codes else REFUSED if REFUSED in codes else OK
    receipt["exit"] = rc
    meaning = {OK: "every read answered", FAILED: "a call failed", REFUSED: "a read refused"}[rc]
    say(f"\nEXIT {rc} ({meaning}). This probe ingests nothing; no adapter follows without the architect's ruling on "
        "this receipt.")
    if a.out:
        try:
            a.out.write_text(say.redact(json.dumps(receipt, indent=1, default=str)))
        except OSError as e:
            say(f"FAILED: the receipt was not written: {type(e).__name__}: {e} (the console above is the receipt)")
            return FAILED
        say(f"receipt written to {a.out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
