"""
TENNIS SOURCE PROBE (ARCHITECT 2026-11-05 11:40 ET, addendum 261 item 2(b); lane tennis-market-only, #838) — read-only.

The ruling, verbatim: "(b) THE PROVIDER PROBE, read-only, by 11-14 (one small PR): FIXTURES — the Kalshi series listing
itself is a legitimate fixture source for a market-only record (the per-match markets name both players and the start
time, and nothing prices through it), probed beside any schedule source the results provider offers; RESULTS AND
HISTORY — tennis-data.co.uk's per-season files (free; results with several books' closing prices back to 2000 — the pot
for any future backtest; its terms read and quoted on the Issue), the tours' own sites (no API), the paid APIs only
named, not bought. The probe reads each candidate's actual fields (player names as served, the match time and its zone,
the result shape — sets, retirements, walkovers — and the status words) and prints them; my ruling on the sources
follows the receipt. Names are the matcher's hardest case here (surname + initial on the venue, full names elsewhere):
the probe counts how many of a week's Kalshi matches resolve to the results source by an exact rule, and the lane
expects refusals."

What it reads (law 1: every field name, column name, series ticker and status word below is READ from the answer and
printed as served; nothing is typed from memory as fact):

  K1  THE SERIES LISTING   KalshiAdapter.find_series(["tennis"]) (GET /series, the adapter's own listing path and
                           filter: title / category / tags / ticker mention the word). Every tennis series is printed,
                           ticker and title as served. The match-level series are those whose ticker or title says
                           "match" (MATCH_RULE), or the --series given; none found is a refusal, never a guess.
  K2  ONE SERIES' FIXTURES per selected series: GET /events (status open, one page) and the adapter's
                           open_markets_for_series. Printed: the keys served, the status words, every time field and
                           its zone as written, and per event (up to --sample) the two players as served: the shared
                           matcher's pair (kalshi_match._pair: the event's sibling markets' yes_sub_title, the title
                           only where they name fewer than two) beside the title / subtitle fields.
  K3  THE WEEK'S EVENTS    per selected series, /markets paged by cursor for each of MARKET_STATUSES; an event is in
                           the week when its ticker's date (kalshi_match.ticker_stamp, the day rule of addendum 44)
                           falls in --week .. --week + 6 days. Printed per series: the status words served across every
                           market read (open, closed and settled), the keys of one market read under status=settled and
                           the distinct values of every result / settlement field (a key naming result, settle or
                           expiration_value), as served: how a retirement or a walkover settles is read here.
  R1  THE RESULTS SOURCE   the index page (--index-url) and the data-file links on it, printed; the index page's
                           schedule links (href or text naming a fixture, schedule, draw or order of play: SCHEDULE_RULE),
                           printed as served and not fetched (261's "any schedule source the results provider offers",
                           or "none on the index page"); then the ATP file
                           (--atp-url) and the WTA file (--wta-url), read IN MEMORY and never stored: the URL read, the
                           file's form, the header row's column names, the distinct values of every result-shape column
                           (a header naming a comment / status / result / retirement / walkover) as served, the set
                           columns, the W/L column pairs (candidate closing-price pairs by the decimal-price rule), the
                           date format and the name format. The probe never chooses a file from the index: a tour with
                           no URL given is not read, and the run says so and exits 2.
  R2  THE TERMS            the page named by --terms-url, its text printed whole as served (quote it on the Issue; this
                           probe paraphrases nothing). Without --terms-url the terms are NOT read and the run refuses
                           (exit 2), printing the index page's candidate links (href or text naming terms, conditions,
                           disclaimer, copyright, licence or legal: TERMS_RULE); the index page is never labelled terms.
  M   THE MATCH COUNT      the week's Kalshi events against the two results files by THE EXACT RULE (below): matched /
                           refused-ambiguous / refused-unreadable / unmatched, with the reasons. NO alias table, NO
                           fuzzy match: the lane expects refusals.
  N   NAMED, NOT FETCHED   the tours' own sites (261: "no API"; not fetching them is this probe's choice, put to the
                           architect) and the paid APIs (none called, none bought: 261 item 3).

THE EXACT RULE (written before any result is read; the probe's own, for the receipt only, never an ingest rule). ONE
rule for both sides: it does not assume which side serves which form (261 says "surname + initial on the venue, full
names elsewhere"; no answer has been read here, and the receipt's name-shape lines show which side serves which).
  (1) a name's SHAPE, read from the served name (spaces collapsed): "surname + initial(s)" when it has two or more
      words and its last word is an initial (INITIAL_WORD: one or two letters, the first a capital, then a full stop,
      repeatable: "A.", "Ch.", "A.B.", "A.-B."; the trailing initial words are the initials, the words before them the
      surname); "one word" when it has fewer than two words; otherwise "full name".
  (2) a name's KEY (accents removed by NFKD, case folded): surname + initial(s) -> the surname, then the FIRST
      initial's first letter and a full stop ("De Synth A." -> "de synth a."; "Synth A.B." -> "synth a."); a full name
      -> its words after the first, then the first word's first letter and a full stop ("Ann De Synth" ->
      "de synth a."); one word -> no key.
  (3) an event is matched when its two players' keys equal, as a set, the two name keys of exactly one results row
      (ATP or WTA file) dated from 7 days before through 1 day after the event's ticker date, and no other event in
      the week fits that row.
  (4) refused-ambiguous: the event's two keys are one key; a key two different Kalshi names give in the week; a key two
      different results-file names give (dated from 7 days before the week through 7 days after it); two or more rows
      fit; one results row fits two or more Kalshi events (every one of them is refused). refused-unreadable: the
      event's markets do not name two players (the shared matcher's NO_PAIR / TITLE_CONFLICT), or a name of one word.
      Anything else is unmatched. An event ticker read twice counts once.

NETWORK AND KEYS: Kalshi's public market data and the results files need no key; the probe reads none, sends none and
prints none (KEYS line). Every call is listed with its HTTP status and every rate-limit header the answer carried.

Writes NOTHING: no database is opened or imported, no file is stored; only --out, a JSON receipt at a path the
operator names (refused under any data/ directory, law 5).

Exit: 0 every read done and the match count run on one or more of the week's events; 1 a call failed (network, HTTP
status, an answer that is not JSON or not of the shape its reader needs); 2 a refusal (an argument, a --week that is not
a completed week, an --out under data/ or not writable, no match-level series, a tour file not named or not readable, a
role column or the date format not found, no --terms-url, no Kalshi event dated in the week). Both: 1 (a failed call is
fixed first). Every reason is printed.

    python3 scripts/tennis_source_probe.py --week 2026-10-26 --terms-url <the terms page from the index> \\
        --atp-url <the ATP file's URL from the index> --wta-url <the WTA file's URL from the index> \\
        [--index-url URL] [--series TICKER ...] [--out receipt.json]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from kalshi_event_probe import is_time_field  # noqa: E402  (the event probe's time-field rule, reused)
from src.adapters.kalshi import BASE as KALSHI_BASE  # noqa: E402  (no DB: requests + logging only)
from src.adapters.kalshi import KalshiAdapter  # noqa: E402
from src.ingestion import kalshi_match as km  # noqa: E402  (no DB: re, dataclasses, zoneinfo only)

SITE = "https://www.tennis-data.co.uk/"     # the domain addendum 261 names; the operator's --index-url wins
TOURS = ("ATP", "WTA")
MATCH_RULE = re.compile(r"match", re.I)     # a match-level series: its ticker or title says "match"
MARKET_STATUSES = ("open", "closed", "settled")
MAX_PAGES = 25                              # per series and status; reaching it is printed, never silent
ROW_WINDOW = (timedelta(days=-7), timedelta(days=1))     # rule (3): a row dated 7 days before .. 1 day after
DATA_EXT = re.compile(r"\.(xlsx|xls|csv|zip)(?:$|\?)", re.I)
RATE_HEADER = re.compile(r"rate.?limit|retry-after", re.I)
RESULT_WORDS = re.compile(r"comment|status|result|retire|walkover", re.I)
SET_COLUMN = re.compile(r"^[A-Za-z]{1,2}[0-9]{1,2}$|sets?\b", re.I)
INITIAL_WORD = re.compile(r"^(?:[^\W\d_][^\W\d_]?\.-?)+$")    # rule (1): "A." / "A.B." / "Ch." / "A.-B." (first a capital)
FULL, INITIAL, ONE_WORD = "full name", "surname + initial(s)", "one word"
SCHEDULE_RULE = re.compile(r"fixture|schedule|draw|order.?of.?play", re.I)
TERMS_RULE = re.compile(r"terms|condition|disclaimer|copyright|licen[cs]e|legal", re.I)
SETTLE_FIELD = re.compile(r"result|settle|expiration_value", re.I)
SETTLE_SKIP = re.compile(r"time|_ts$|date", re.I)         # a settlement TIME is not a result shape
LIST_KEYS = ("series", "markets", "events")                 # the list keys the Kalshi readers iterate
# Rule-discovery candidates for the three columns the match count needs; matched against the header case-insensitively
# and exactly. A miss REFUSES the count and prints the header (never guessed); --date-col / --player-cols override.
ROLE_CANDIDATES = {"date": ("date",), "player_a": ("winner", "player1", "player 1", "player_1"),
                   "player_b": ("loser", "player2", "player 2", "player_2")}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S",
                "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M")
XLS_MAGIC = b"\xd0\xcf\x11\xe0"
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
NAMED_NOT_FETCHED = ("the tours' own sites, the ATP Tour's and the WTA's (261 item 2(b): \"no API\"): not fetched by "
                     "this probe (Code's choice: no API, and item 4's terms rule comes before any scraping; put to the "
                     "architect)",
                     "paid tennis data APIs: named in the PR body only; none is called and none is bought "
                     "(261 item 3)")


class Refused(Exception):
    """A refusal: the reason is printed and the run exits 2."""


class CallFailed(Exception):
    """A call that failed: recorded in the calls list; the run exits 1."""


def http_get(url: str, params: dict | None = None, timeout: int = 30):
    """GET only, no auth header, no key: (status, headers, body bytes). Tests replace this function."""
    import requests
    r = requests.get(url, params=params or {}, timeout=timeout,
                     headers={"Accept": "*/*", "User-Agent": "sports_predictor tennis_source_probe (read-only)"})
    return r.status_code, dict(r.headers), r.content


class Calls:
    """Every call this run makes, with its status and the rate-limit headers the answer carried."""

    def __init__(self, get=None):
        self.get_fn = get
        self.made: list[dict] = []

    def get(self, url: str, params: dict | None = None) -> tuple[int, dict, bytes]:
        full = url + ("?" + urlencode(params) if params else "")
        rec = {"url": full, "status": None, "rate_limit": {}, "bytes": None}
        self.made.append(rec)
        try:
            status, headers, body = (self.get_fn or http_get)(url, params)
        except Exception as e:                                   # noqa: BLE001 — recorded, then raised
            rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            raise CallFailed(rec["error"]) from e
        rec["status"], rec["bytes"] = status, len(body or b"")
        rec["rate_limit"] = {k: v for k, v in (headers or {}).items() if RATE_HEADER.search(str(k))}
        if status != 200:
            rec["error"] = f"HTTP {status}"
            raise CallFailed(f"HTTP {status} from {full}")
        return status, headers or {}, body or b""

    def failed(self) -> list[dict]:
        return [c for c in self.made if c.get("error")]


class ProbeKalshi(KalshiAdapter):
    """The adapter, its base URL and its own listing / paging methods, with every GET recorded by Calls."""

    def __init__(self, calls: Calls, base_url: str = KALSHI_BASE):
        super().__init__(base_url)
        self.calls = calls

    def _get(self, path: str, params: dict | None = None) -> dict:
        _, _, body = self.calls.get(f"{self.base}/{path.lstrip('/')}", params)
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            self.calls.made[-1]["error"] = "an answer that is not JSON"
            raise CallFailed(f"an answer that is not JSON from {path}") from e
        if not isinstance(data, dict):
            self.calls.made[-1]["error"] = "an answer that is not an object"
            raise CallFailed(f"an answer that is not an object from {path}")
        for key in LIST_KEYS:
            if key in data and not (isinstance(data[key], list) and all(isinstance(x, dict) for x in data[key])):
                self.calls.made[-1]["error"] = f"an answer whose {key!r} is not a list of objects"
                raise CallFailed(f"an answer whose {key!r} is not a list of objects from {path}")
        return data


# ---------------------------------------------------------------------------------------------------- the exact rule --

def norm(name) -> str:
    """Accents removed (NFKD, combining marks dropped), case folded, whitespace collapsed."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.casefold().split())


def name_key(name) -> tuple[str | None, str]:
    """Rules (1) and (2), one rule for both sides: (the key or None, the shape read from the served name)."""
    words = str(name or "").split()
    if len(words) < 2:
        return None, ONE_WORD
    i = len(words)
    while i > 1 and INITIAL_WORD.match(words[i - 1]) and words[i - 1][0].isupper():
        i -= 1
    if i < len(words):
        return norm(" ".join(words[:i])) + " " + norm(words[i][0]) + ".", INITIAL
    nw = norm(name).split()
    return " ".join(nw[1:]) + " " + nw[0][0] + ".", FULL


def key_of(name) -> str | None:
    return name_key(name)[0]


def match_week(events: list[dict], rows: list[dict], week: date) -> dict:
    """The match count. events: {event, series, names (two or the refusal's), why (None or the pair's refusal), day};
    rows: {tour, a, b, day}. Returns the counts, the reasons and samples. Only events whose day is in the week count."""
    end = week + timedelta(days=6)
    once: dict = {}
    for e in events:                                           # an event ticker read twice counts once
        once.setdefault(e["event"], e)
    inweek = [e for e in once.values() if e.get("day") is not None and week <= e["day"] <= end]
    out = {"week": [week.isoformat(), end.isoformat()], "events": len(inweek), "matched": 0, "refused_ambiguous": 0,
           "refused_unreadable": 0, "unmatched": 0, "reasons": Counter(), "matched_by_tour": Counter(),
           "matched_sample": [], "refused_sample": [], "unmatched_sample": [],
           "name_shapes": {"kalshi": Counter(), "results": Counter()}}
    # a key two different Kalshi names give in the week
    k_names: dict[str, set] = defaultdict(set)
    for n in {str(n).strip() for e in inweek for n in (e.get("names") or [])}:
        out["name_shapes"]["kalshi"][name_key(n)[1]] += 1
    for e in inweek:
        if not e.get("why") and len(e.get("names") or []) == 2:
            for n in e["names"]:
                k = key_of(n)
                if k:
                    k_names[k].add(n.strip())
    k_twice = {k: v for k, v in k_names.items() if len(v) > 1}
    # a key two different results-file names give, over the rows the week's events can reach
    lo, hi = week - timedelta(days=7), end + timedelta(days=7)
    near = [r for r in rows if r.get("day") is not None and lo <= r["day"] <= hi]
    f_names: dict[str, set] = defaultdict(set)
    for n in {str(n).strip() for r in near for n in (r["a"], r["b"])}:
        out["name_shapes"]["results"][name_key(n)[1]] += 1
    for r in near:
        for n in (r["a"], r["b"]):
            k = key_of(n)
            if k:
                f_names[k].add(str(n).strip())
    f_twice = {k: v for k, v in f_names.items() if len(v) > 1}
    by_pair: dict[frozenset, list] = defaultdict(list)
    for r in near:
        ka, kb = key_of(r["a"]), key_of(r["b"])
        if ka and kb:
            by_pair[frozenset((ka, kb))].append(r)

    def refuse(e, kind, reason):
        out[kind] += 1
        out["reasons"][reason.split(":")[0]] += 1
        if len(out["refused_sample"]) < 15:
            out["refused_sample"].append(f"{e['event']}: {' / '.join(e.get('names') or []) or '-'} · {reason}")

    pending: list[tuple[dict, dict]] = []
    for e in inweek:
        names = e.get("names") or []
        if e.get("why") or len(names) != 2:
            refuse(e, "refused_unreadable", e.get("why") or "the event's markets do not name two players")
            continue
        keys = [key_of(n) for n in names]
        if None in keys:
            refuse(e, "refused_unreadable", "a name of one word: no key under rule (1)")
            continue
        if keys[0] == keys[1]:
            refuse(e, "refused_ambiguous", f"both players map to one key: {keys[0]!r}")
            continue
        hit = next((k for k in keys if k in k_twice), None)
        if hit:
            refuse(e, "refused_ambiguous", f"a key two Kalshi names give in the week: {hit!r} <- "
                                           + ", ".join(sorted(k_twice[hit])))
            continue
        hit = next((k for k in keys if k in f_twice), None)
        if hit:
            refuse(e, "refused_ambiguous", f"a key two results-file names give: {hit!r} <- "
                                           + ", ".join(sorted(f_twice[hit])))
            continue
        fits = [r for r in by_pair.get(frozenset(keys), [])
                if e["day"] + ROW_WINDOW[0] <= r["day"] <= e["day"] + ROW_WINDOW[1]]
        if len(fits) > 1:
            refuse(e, "refused_ambiguous", f"{len(fits)} results rows fit the pair: "
                                           + ", ".join(f"{r['tour']} {r['day']}" for r in fits))
            continue
        if not fits:
            out["unmatched"] += 1
            if len(out["unmatched_sample"]) < 15:
                out["unmatched_sample"].append(f"{e['event']} {e['day']}: {names[0]} -> {keys[0]!r} · "
                                               f"{names[1]} -> {keys[1]!r}")
            continue
        pending.append((e, fits[0]))
    claims = Counter(id(r) for _, r in pending)
    for e, r in pending:
        if claims[id(r)] > 1:                                  # rule (4): one results row fits two or more events
            refuse(e, "refused_ambiguous", f"one results row fits two Kalshi events: {r['tour']} {r['day']}: "
                                           f"{r['a']} / {r['b']}")
            continue
        out["matched"] += 1
        out["matched_by_tour"][r["tour"]] += 1
        if len(out["matched_sample"]) < 5:
            out["matched_sample"].append(f"{e['event']}: {e['names'][0]} / {e['names'][1]} = {r['tour']} "
                                         f"{r['day']}: {r['a']} / {r['b']}")
    return out


# ------------------------------------------------------------------------------------------------------- Kalshi side --

def zone_of(v) -> str:
    """The zone a time value states as written: Z, an offset, epoch seconds, or none stated."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return "epoch seconds"
    s = str(v or "").strip()
    if not s:
        return "empty"
    if s.endswith("Z"):
        return "Z"
    m = re.search(r"[+-]\d{2}:?\d{2}$", s)
    if m and re.search(r"\d[T ]\d", s):
        return f"offset {m.group(0)}"
    return "no zone stated"


def event_pairs(markets: list[dict]) -> list[dict]:
    """Markets grouped by event (kalshi_match.event_of), the two players by the shared matcher's _pair, the day by its
    ticker_stamp (the day rule). Markets are de-duplicated by ticker (one market can come back under two statuses)."""
    seen, by_ev = set(), defaultdict(list)
    for mk in markets:
        t = mk.get("ticker")
        if t in seen:
            continue
        seen.add(t)
        by_ev[km.event_of(mk)].append(mk)
    out = []
    for ev, mks in by_ev.items():
        names, why = km._pair(mks, mks[0], KalshiAdapter.is_tie_market)
        day, clock = km.ticker_stamp(mks[0])
        out.append({"event": ev, "names": names, "why": why, "day": day, "clock_utc": clock,
                    "statuses": sorted({str(m.get("status")) for m in mks})})
    return out


def kalshi_series(k: ProbeKalshi, wanted: list[str] | None, echo) -> tuple[list[dict], list[str]]:
    echo("K1 SERIES LISTING (KalshiAdapter.find_series(['tennis']): GET /series, the adapter's filter)")
    found = k.find_series(["tennis"])
    if not any(c["url"].startswith(f"{k.base}/series") and not c.get("error") for c in k.calls.made):
        raise CallFailed("the series listing was not read (every GET /series failed; the calls are listed below)")
    echo(f"  tennis series as served: {len(found)}")
    if found:
        echo("  keys served (first series): " + ", ".join(sorted(found[0])))
    for s in found:
        echo(f"    {s.get('ticker')!s:<28} {s.get('title')!r} · category {s.get('category')!r} · tags {s.get('tags')!r}"
             + (f" · frequency {s.get('frequency')!r}" if "frequency" in s else ""))
    if wanted:
        listed = {s.get("ticker") for s in found}
        echo("  selected by --series: " + ", ".join(f"{t}{'' if t in listed else ' (NOT in the listing)'}"
                                                  for t in dict.fromkeys(wanted)))
        return found, list(dict.fromkeys(wanted))
    sel = [s.get("ticker") for s in found
           if MATCH_RULE.search(str(s.get("ticker") or "")) or MATCH_RULE.search(str(s.get("title") or ""))]
    sel = list(dict.fromkeys(t for t in sel if t))
    echo(f"  selected by the rule (ticker or title says {MATCH_RULE.pattern!r}): " + (", ".join(sel) or "none"))
    if not sel:
        raise Refused("no tennis series in the listing is match-level by the rule; pass --series from the listing "
                      "above (never guessed)")
    return found, sel


def fixtures(k: ProbeKalshi, series: str, sample: int, echo) -> dict:
    """K2: one series' open events and markets, as served."""
    rec: dict = {"series": series}
    echo(f"\nK2 FIXTURES · series {series}")
    try:
        evs = k._get("events", {"series_ticker": series, "status": "open", "limit": 200}).get("events") or []
        rec["events_open_page"] = len(evs)
        echo(f"  GET /events (open, one page): {len(evs)} events"
             + (" · keys " + ", ".join(sorted(evs[0])) if evs else ""))
        for e in evs[:sample]:
            echo(f"    event {e.get('event_ticker')!r} · title {e.get('title')!r} · sub_title {e.get('sub_title')!r}")
            for f in sorted(x for x in e if is_time_field(x)):
                echo(f"      {f} = {e[f]!r} ({zone_of(e[f])})")
    except CallFailed as x:
        echo(f"  GET /events failed: {x}")
    mks = k.open_markets_for_series(series)
    rec["markets_open"] = len(mks)
    echo(f"  open markets (open_markets_for_series): {len(mks)}"
         + (" · keys " + ", ".join(sorted(mks[0])) if mks else ""))
    status = Counter(str(m.get("status")) for m in mks)
    rec["status_words"] = dict(status)
    echo("  status words as served: " + (", ".join(f"{s} {n}" for s, n in sorted(status.items())) or "none"))
    zones: dict[str, Counter] = defaultdict(Counter)
    for m in mks:
        for f in m:
            if is_time_field(f):
                zones[f][zone_of(m[f])] += 1
    rec["time_fields"] = {f: dict(c) for f, c in sorted(zones.items())}
    for f, c in sorted(zones.items()):
        echo(f"  time field {f}: " + ", ".join(f"{z} {n}" for z, n in sorted(c.items())))
    pairs = event_pairs(mks)
    rec["events_from_markets"] = len(pairs)
    by_ev = defaultdict(list)
    for m in mks:
        by_ev[km.event_of(m)].append(m)
    rec["sample"] = []
    for p in pairs[:sample]:
        ms = by_ev[p["event"]]
        echo(f"    event {p['event']} · ticker date {p['day']} · players (the shared matcher's pair): "
             + (" / ".join(p["names"]) or "-") + (f" · REFUSED: {p['why']}" if p["why"] else ""))
        shown = ("ticker", "status", "title", "subtitle", "yes_sub_title", "no_sub_title")
        for m in ms:
            echo("      market " + " · ".join(f"{f}={m.get(f)!r}" for f in shown if f in m))
            for f in sorted(x for x in m if is_time_field(x)):
                echo(f"        {f} = {m[f]!r} ({zone_of(m[f])})")
        rec["sample"].append({"event": p["event"], "names": p["names"], "why": p["why"],
                              "day": p["day"].isoformat() if p["day"] else None, "markets": ms})
    return rec


def week_markets(k: ProbeKalshi, series: str, echo) -> dict[str, list[dict]]:
    """K3: /markets for the series, each status paged by cursor to MAX_PAGES, by the status filter it was read under.
    A failed status is printed and skipped."""
    by_filter: dict[str, list[dict]] = {}
    for st in MARKET_STATUSES:
        out = by_filter.setdefault(st, [])
        cursor, n, pages = None, 0, 0
        try:
            while pages < MAX_PAGES:
                params = {"series_ticker": series, "status": st, "limit": 200}
                if cursor:
                    params["cursor"] = cursor
                data = k._get("markets", params)
                pages += 1
                got = data.get("markets") or []
                out.extend(got)
                n += len(got)
                cursor = data.get("cursor")
                if not cursor:
                    break
            echo(f"  {series} /markets status={st}: {n} markets, {pages} page(s)"
                 + (f" · MAX_PAGES {MAX_PAGES} reached: later pages not read" if cursor else ""))
        except CallFailed as x:
            echo(f"  {series} /markets status={st}: failed after {n} markets: {x}")
    return by_filter


def settlement_shape(series: str, by_filter: dict[str, list[dict]], echo) -> dict:
    """K3, as served: the status words across every market read, one settled market's keys, and the distinct values of
    every result / settlement field (SETTLE_FIELD, time fields excluded) over the markets read under closed / settled."""
    allm = [m for ms in by_filter.values() for m in ms]
    words = Counter(str(m.get("status")) for m in allm)
    echo(f"  {series} status words as served, every market read ({', '.join(MARKET_STATUSES)}): "
         + (", ".join(f"{w} {n}" for w, n in sorted(words.items())) or "none"))
    rec: dict = {"status_words": dict(words), "settled_keys": None, "settled_fields": {}}
    settled = by_filter.get("settled") or []
    if settled:
        rec["settled_keys"] = sorted(settled[0])
        echo(f"  {series} a market read under status=settled, keys served: " + ", ".join(rec["settled_keys"]))
    else:
        echo(f"  {series} a market read under status=settled: none read")
    done = [m for st in ("closed", "settled") for m in by_filter.get(st) or []]
    fields = sorted({f for m in done for f in m if SETTLE_FIELD.search(f) and not SETTLE_SKIP.search(f)})
    for f in fields:
        c = Counter((isinstance(m[f], str), m[f] if isinstance(m[f], str) else json.dumps(m[f])) for m in done if f in m)
        rec["settled_fields"][f] = {v: n for (_, v), n in c.items()}
        echo(f"  {series} result / settlement field {f!r}, distinct values as served: "
             + ", ".join(f"{repr(v) if is_str else v} {n}" for (is_str, v), n in sorted(c.items())[:20])
             + (f" · {len(c) - 20} more" if len(c) > 20 else ""))
    if done and not fields:
        echo(f"  {series} result / settlement fields: none by the rule {SETTLE_FIELD.pattern!r}")
    return rec


# ------------------------------------------------------------------------------------------------------ results side --

class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.links, self._skip, self._a = [], [], 0, None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "a":
            self._a = [dict(attrs).get("href"), ""]
        if tag in ("p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag in ("p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table", "td", "th"):
            self.parts.append("\n" if tag != "td" and tag != "th" else " ")
        if tag == "a" and self._a is not None:
            self.links.append((self._a[0], " ".join(self._a[1].split())))
            self._a = None

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        if self._a is not None:
            self._a[1] += data


def page_text(body: bytes) -> tuple[str, list[tuple[str, str]]]:
    """(the page's visible text, lines kept, spaces collapsed; its links (href, text))."""
    p = _Text()
    p.feed(body.decode("utf-8", errors="replace"))
    lines = [" ".join(x.split()) for x in "".join(p.parts).splitlines()]
    return "\n".join(x for x in lines if x), [(h, t) for h, t in p.links if h]


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def xlsx_rows(z: zipfile.ZipFile) -> tuple[list[list], dict]:
    """The first worksheet's rows (cell values as served: text, or the stored number as text), stdlib only."""
    names = set(z.namelist())
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(M + "si"):
            shared.append("".join(t.text or "" for t in si.iter(M + "t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    date1904 = any(str(w.get("date1904", "")).lower() in ("1", "true") for w in wb.iter(M + "workbookPr"))
    sheets = wb.find(M + "sheets")
    first = sheets[0] if sheets is not None and len(sheets) else None
    path = None
    if first is not None and "xl/_rels/workbook.xml.rels" in names:
        for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
            if r.get("Id") == first.get(R_ID):
                t = r.get("Target") or ""
                path = t.lstrip("/") if t.startswith("/") else "xl/" + t
    if path not in names:
        ws = sorted(n for n in names if n.startswith("xl/worksheets/") and n.endswith(".xml"))
        if not ws:
            raise Refused("an xlsx with no worksheet")
        path = ws[0]
    rows = []
    for row in ET.fromstring(z.read(path)).iter(M + "row"):
        cells, nxt = {}, 0
        for c in row.findall(M + "c"):
            i = _col(c.get("r")) if c.get("r") else nxt
            nxt = i + 1
            t, v = c.get("t"), c.find(M + "v")
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(M + "t"))
            else:
                val = v.text if v is not None else None
            cells[i] = val
        rows.append([cells.get(i) for i in range(max(cells) + 1)] if cells else [])
    return rows, {"sheet": first.get("name") if first is not None else path, "date1904": date1904, "path": path}


def read_table(body: bytes, depth: int = 0) -> tuple[list[str], list[list], dict]:
    """(header, data rows, the form read). xlsx and csv by the stdlib; a legacy .xls is refused (it needs a reader
    dependency this probe does not add); a zip holding exactly one data file is read through."""
    if body[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(body))
        if "xl/workbook.xml" in z.namelist():
            rows, info = xlsx_rows(z)
            info["form"] = "xlsx"
        else:
            members = [n for n in z.namelist() if DATA_EXT.search(n)]
            if len(members) != 1 or depth:
                raise Refused(f"a zip holding {len(members)} data files ({', '.join(members) or 'none'}): not chosen")
            h, r, info = read_table(z.read(members[0]), depth + 1)
            info["form"] = f"zip member {members[0]}: {info['form']}"
            return h, r, info
    elif body[:4] == XLS_MAGIC:
        raise Refused("a legacy Excel .xls file (OLE2): reading it needs a reader dependency (xlrd), which this probe "
                      "does not add (stdlib + the repo's dependencies only)")
    else:
        try:
            text, enc = body.decode("utf-8-sig"), "utf-8"
        except UnicodeDecodeError:
            text, enc = body.decode("latin-1"), "latin-1"
        if text.lstrip()[:1] == "<":
            raise Refused("an HTML page, not a data file")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
        info = {"form": f"csv ({enc}, delimiter {dialect.delimiter!r})", "date1904": False}
    rows = [r for r in rows if any(str(x or "").strip() for x in r)]
    if not rows:
        raise Refused("an empty table")
    header = [str(x or "").strip() for x in rows[0]]
    return header, rows[1:], info


def column(header: list[str], rows: list[list], name: str) -> list:
    i = header.index(name)
    return [r[i] if i < len(r) else None for r in rows]


def roles(header: list[str], date_col=None, player_cols=None) -> tuple[dict, list[str]]:
    """The three columns the match count reads, by the candidates (exact, case-insensitive) or the flags."""
    low = {h.lower(): h for h in header}
    found = {}
    over = {"date": date_col}
    if player_cols:
        over["player_a"], over["player_b"] = player_cols
    for role, cands in ROLE_CANDIDATES.items():
        want = over.get(role)
        if want:
            found[role] = want if want in header else None
        else:
            found[role] = next((low[c] for c in cands if c in low), None)
    return found, [r for r, c in found.items() if not c]


def excel_day(v: str, date1904: bool) -> date:
    base = date(1904, 1, 1) if date1904 else date(1899, 12, 30)
    return base + timedelta(days=int(float(v)))


def date_reader(values: list, info: dict) -> tuple[str, object]:
    """(the format as read, a parser) or Refused. Numbers in an xlsx are serial days; text must parse under exactly
    one of DATE_FORMATS (or under formats that agree on every value), never a guessed order of day and month."""
    vals = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not vals:
        raise Refused("the date column holds no value")
    if info.get("form", "").endswith("xlsx") and all(re.fullmatch(r"\d+(\.\d+)?", v) for v in vals):
        sysname = "1904" if info.get("date1904") else "1900"
        return (f"Excel serial day numbers (the workbook's {sysname} date system), e.g. {vals[0]!r}",
                lambda v: excel_day(v, info.get("date1904")))
    fits = []
    for f in DATE_FORMATS:
        try:
            parsed = [datetime.strptime(v, f).date() for v in vals]
        except ValueError:
            continue
        fits.append((f, parsed))
    if not fits:
        raise Refused(f"the date values parse under none of {', '.join(DATE_FORMATS)} (e.g. {vals[0]!r})")
    if any(p != fits[0][1] for _, p in fits[1:]):
        raise Refused("the date values parse under " + " and ".join(f for f, _ in fits)
                      + " with different dates: the order of day and month is ambiguous")
    f = fits[0][0]
    return f"{f} (as text, e.g. {vals[0]!r})", lambda v: datetime.strptime(str(v).strip(), f).date()


def wl_pairs(header: list[str]) -> tuple[list[str], list[str]]:
    """(suffix stems: XW and XL both present; prefix stems: WX and LX both present), as the header names them."""
    hs = set(header)
    suffix = sorted({h[:-1] for h in hs if len(h) > 1 and h.endswith("W") and h[:-1] + "L" in hs})
    prefix = sorted({h[1:] for h in hs if len(h) > 1 and h.startswith("W") and "L" + h[1:] in hs})
    return suffix, prefix


def price_like(values: list) -> tuple[int, int]:
    """(values that read as a decimal price > 1.0 with a fraction, non-empty values)."""
    n = ok = 0
    for v in values:
        s = str(v if v is not None else "").strip()
        if not s:
            continue
        n += 1
        try:
            x = float(s)
        except ValueError:
            continue
        ok += x > 1.0 and x != int(x)
    return ok, n


def file_receipt(tour: str, url: str, header, rows, info, date_col, player_cols, echo) -> tuple[dict, list[dict]]:
    """R1 for one file: the receipt lines and the rows for the match count ([] when a role or the date refuses)."""
    rec = {"tour": tour, "url": url, "form": info.get("form"), "sheet": info.get("sheet"), "rows": len(rows),
           "header": header}
    echo(f"  form {info.get('form')}" + (f" · sheet {info['sheet']!r}" if info.get("sheet") else "")
         + f" · {len(rows)} data rows")
    echo(f"  HEADER ({len(header)} columns, as served): " + " | ".join(header))
    res_cols = [h for h in header if RESULT_WORDS.search(h)]
    rec["result_columns"] = {}
    for h in res_cols:
        c = Counter(str(v).strip() if v is not None and str(v).strip() else "(empty)" for v in column(header, rows, h))
        rec["result_columns"][h] = dict(c)
        echo(f"  result-shape column {h!r}, distinct values as served: "
             + ", ".join(f"{v!r} {n}" for v, n in c.most_common()))
    if not res_cols:
        echo(f"  result-shape columns: none in the header by the rule {RESULT_WORDS.pattern!r}")
    sets = [h for h in header if SET_COLUMN.search(h)]
    rec["set_columns"] = {h: sum(1 for v in column(header, rows, h) if v is not None and str(v).strip()) for h in sets}
    echo("  set columns by the rule " + repr(SET_COLUMN.pattern) + ": "
         + (", ".join(f"{h} ({n} filled)" for h, n in rec["set_columns"].items()) or "none"))
    suffix, prefix = wl_pairs(header)
    rec["price_pairs"] = {}
    for s in suffix:
        ok_w, n_w = price_like(column(header, rows, s + "W"))
        ok_l, n_l = price_like(column(header, rows, s + "L"))
        rec["price_pairs"][s] = {"filled": [n_w, n_l], "decimal_price_like": [ok_w, ok_l]}
    echo("  W/L column pairs by suffix (candidate closing-price pairs; filled, decimal-price-like): "
         + (", ".join(f"{s}W/{s}L ({v['filled'][0]}/{v['filled'][1]}, {v['decimal_price_like'][0]}/"
                      f"{v['decimal_price_like'][1]})" for s, v in rec["price_pairs"].items()) or "none"))
    rec["prefix_pairs"] = prefix
    echo("  W/L column pairs by prefix: " + (", ".join(f"W{s}/L{s}" for s in prefix) or "none"))
    found, missing = roles(header, date_col, player_cols)
    rec["roles"] = found
    echo("  roles for the match count (law-1 receipt): " + " · ".join(f"{r}<-{c!r}" for r, c in found.items()))
    if missing:
        raise Refused(f"{tour}: the column(s) for {', '.join(missing)} not found in the header (candidates "
                      + "; ".join(f"{r}: {', '.join(ROLE_CANDIDATES[r])}" for r in missing)
                      + "; --date-col / --player-cols name them)")
    fmt, parse = date_reader(column(header, rows, found["date"]), info)
    rec["date_format"] = fmt
    echo(f"  date format: {fmt}")
    names = Counter()
    for c in (found["player_a"], found["player_b"]):
        for v in column(header, rows, c):
            if v is not None and str(v).strip():
                names[str(v).strip()] += 1
    shapes: dict[str, list] = defaultdict(list)
    for n in names:
        shapes[name_key(n)[1]].append(n)
    rec["name_shapes"] = {k: len(v) for k, v in shapes.items()}
    echo(f"  name format ({len(names)} distinct names in {found['player_a']!r} and {found['player_b']!r}): "
         + " · ".join(f"{k} {len(v)} (e.g. " + ", ".join(repr(x) for x in sorted(v)[:5]) + ")"
                      for k, v in sorted(shapes.items())))
    out, bad = [], 0
    ia, ib, idt = header.index(found["player_a"]), header.index(found["player_b"]), header.index(found["date"])
    for r in rows:
        get = lambda i: r[i] if i < len(r) else None          # noqa: E731
        try:
            d = parse(get(idt)) if get(idt) is not None and str(get(idt)).strip() else None
        except ValueError:
            d = None
        if d is None or not get(ia) or not get(ib):
            bad += 1
            continue
        out.append({"tour": tour, "a": str(get(ia)).strip(), "b": str(get(ib)).strip(), "day": d})
    rec["rows_usable"], rec["rows_unusable"] = len(out), bad
    echo(f"  rows usable for the match count: {len(out)} · without a date or both names: {bad}")
    return rec, out


# -------------------------------------------------------------------------------------------------------------- main --

def refuse_out(path: str | None) -> str | None:
    """Law 5: the receipt is never written under a data/ directory; and a path that cannot be written is refused
    before any call, so a run's receipt is never lost at its end."""
    if not path:
        return None
    p = Path(path).expanduser()
    if "data" in p.resolve().parts:
        return f"REFUSED: --out {path} is under a data/ directory (law 5); name another path"
    if p.is_dir():
        return f"REFUSED: --out {path} is a directory; name a file"
    if not p.parent.is_dir():
        return f"REFUSED: --out {path}: its directory {p.parent} does not exist"
    return None


def main(argv=None, get=None, echo=print, today: date | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tennis source probe (addendum 261 item 2(b)), read-only")
    ap.add_argument("--week", required=True, help="the first day of the week to count (ISO date, YYYY-MM-DD)")
    ap.add_argument("--series", action="append", help="a Kalshi series ticker from the listing (repeatable); "
                                                      "default: the listing's match-level series by the rule")
    ap.add_argument("--atp-url", help="the ATP results file's URL, as the index page lists it")
    ap.add_argument("--wta-url", help="the WTA results file's URL, as the index page lists it")
    ap.add_argument("--index-url", default=SITE, help="the results source's page listing its data files")
    ap.add_argument("--terms-url", default=None, help="the results source's terms page (none: the terms are not "
                                                         "read, the candidates are listed and the run exits 2)")
    ap.add_argument("--date-col", default=None, help="the results files' date column, if not found by the rule")
    ap.add_argument("--player-cols", default=None, help="the two name columns, comma-separated, if not found")
    ap.add_argument("--kalshi-base", default=KALSHI_BASE)
    ap.add_argument("--sample", type=int, default=10, help="events printed per series in K2")
    ap.add_argument("--out", default=None, help="a JSON receipt at this path (never under data/)")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        week = date.fromisoformat(a.week)
    except ValueError:
        echo(f"REFUSED: --week {a.week!r} is not an ISO date (YYYY-MM-DD)")
        return 2
    today = today or datetime.now(timezone.utc).date()
    if week + timedelta(days=6) >= today:
        echo(f"REFUSED: --week {week} is not a completed week: it runs to {week + timedelta(days=6)}, and today (UTC) is "
             f"{today}; unplayed matches would count as unmatched. Name a week whose last day is before today")
        return 2
    why = refuse_out(a.out)
    if why:
        echo(why)
        return 2
    pcols = None
    if a.player_cols:
        pcols = [x.strip() for x in a.player_cols.split(",")]
        if len(pcols) != 2 or not all(pcols):
            echo("REFUSED: --player-cols takes two column names, comma-separated")
            return 2

    calls = Calls(get)
    refusals: list[str] = []
    failures: list[str] = []
    receipt: dict = {"probe": "tennis_source_probe", "ruling": "ARCHITECT 2026-11-05 11:40 ET, addendum 261 item 2(b)",
                     "week": week.isoformat(), "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    echo("TENNIS SOURCE PROBE (addendum 261 item 2(b); lane tennis-market-only, #838) · read-only · no DB · "
         "nothing stored")
    echo("KEYS: none read, none sent, none printed (Kalshi public market data and the results files need none)")

    # ---- Kalshi
    k = ProbeKalshi(calls, a.kalshi_base)
    events: list[dict] = []
    receipt["kalshi"] = {"base": k.base}
    try:
        listing, selected = kalshi_series(k, a.series, echo)
        receipt["kalshi"]["tennis_series"] = [{f: s.get(f) for f in ("ticker", "title", "category", "tags")}
                                              for s in listing]
        receipt["kalshi"]["selected"] = selected
        receipt["kalshi"]["fixtures"] = []
        for s in selected:
            try:
                receipt["kalshi"]["fixtures"].append(fixtures(k, s, a.sample, echo))
            except CallFailed as x:
                failures.append(f"K2 {s}: {x}")
                echo(f"  K2 {s} failed: {x}")
        echo(f"\nK3 THE WEEK'S EVENTS ({week} .. {week + timedelta(days=6)}, the ticker's date)")
        receipt["kalshi"]["week_markets"] = {}
        for s in selected:
            by_filter = week_markets(k, s, echo)
            receipt["kalshi"]["week_markets"][s] = settlement_shape(s, by_filter, echo)
            pairs = event_pairs([m for ms in by_filter.values() for m in ms])
            for p in pairs:
                p["series"] = s
            inweek = [p for p in pairs if p["day"] and week <= p["day"] <= week + timedelta(days=6)]
            echo(f"  {s}: {len(pairs)} events read · {len(inweek)} in the week · "
                 f"{sum(1 for p in pairs if p['day'] is None)} with no date in the ticker")
            events.extend(pairs)
    except Refused as x:
        refusals.append(f"K1: {x}")
        echo(f"  REFUSED: {x}")
    except CallFailed as x:
        failures.append(f"K1: {x}")
        echo(f"  FAILED: {x}")

    # ---- results source
    echo(f"\nR1 RESULTS SOURCE · index {a.index_url}")
    index_body, links = None, []
    try:
        _, _, index_body = calls.get(a.index_url)
        _, links = page_text(index_body)
        data = [(urljoin(a.index_url, h), t) for h, t in links if DATA_EXT.search(h)]
        receipt["index_data_links"] = [u for u, _ in data]
        echo(f"  data-file links on the index page ({len(data)}; the probe chooses none):")
        for u, t in data:
            echo(f"    {u}  [{t}]")
        if not data:
            others = sorted({urljoin(a.index_url, h) for h, _ in links})
            echo(f"  no data-file link; the page's links ({len(others)}): " + ", ".join(others[:60]))
        sched = [(urljoin(a.index_url, h), t) for h, t in links if SCHEDULE_RULE.search(f"{h} {t}")]
        receipt["index_schedule_links"] = [u for u, _ in sched]
        echo("  R1 schedule links on the index page (by the rule, as served; not fetched): "
             + (" · ".join(f"{u}  [{t}]" for u, t in sched) or "none on the index page"))
    except CallFailed as x:
        failures.append(f"R1 index: {x}")
        echo(f"  index page FAILED: {x}")
    rows: list[dict] = []
    receipt["results"] = []
    for tour, url in (("ATP", a.atp_url), ("WTA", a.wta_url)):
        echo(f"\n  {tour} results file: " + (url or "NOT READ (no --" + tour.lower() + "-url given)"))
        if not url:
            refusals.append(f"R1 {tour}: no --{tour.lower()}-url (the probe does not choose a file from the index)")
            continue
        try:
            _, _, body = calls.get(url)
            echo(f"  read {url} ({len(body)} bytes, held in memory, not stored)")
            header, data_rows, info = read_table(body)
            rec, got = file_receipt(tour, url, header, data_rows, info, a.date_col, pcols, echo)
            receipt["results"].append(rec)
            rows.extend(got)
        except Refused as x:
            refusals.append(f"R1 {tour}: {x}")
            echo(f"  REFUSED: {x}")
        except CallFailed as x:
            failures.append(f"R1 {tour}: {x}")
            echo(f"  FAILED: {x}")
        except (zipfile.BadZipFile, ET.ParseError, KeyError, IndexError, TypeError, ValueError, AttributeError) as x:
            refusals.append(f"R1 {tour}: the file did not read as its form says ({type(x).__name__}: {x})")
            echo(f"  REFUSED: the file did not read as its form says ({type(x).__name__}: {x})")

    # ---- terms
    if not a.terms_url:
        cands = [(urljoin(a.index_url, h), t) for h, t in links if TERMS_RULE.search(f"{h} {t}")]
        receipt["terms"] = {"url": None, "candidate_links": [u for u, _ in cands]}
        line = ("not read (no --terms-url; candidate links: "
                + (" · ".join(f"{u} [{t}]" for u, t in cands) or "none on the index page") + ")")
        echo(f"\nR2 TERMS: {line}")
        refusals.append(f"R2 terms: {line}")
    else:
        turl = a.terms_url
        echo(f"\nR2 TERMS · {turl} (the page's text as served, whole; quote it on the Issue, paraphrase nothing)")
        if turl == a.index_url:
            echo("  --terms-url names the index page itself: its text is printed as the terms by the operator's choice")
        try:
            body = index_body if turl == a.index_url and index_body is not None else calls.get(turl)[2]
            text, _ = page_text(body)
            receipt["terms"] = {"url": turl, "text": text}
            echo("----- BEGIN PAGE TEXT -----")
            echo(text)
            echo("----- END PAGE TEXT -----")
        except CallFailed as x:
            failures.append(f"R2 terms: {x}")
            echo(f"  terms page FAILED: {x}")

    # ---- the match count
    echo(f"\nM THE MATCH COUNT (the exact rule in the docstring; no alias table, no fuzzy match)")
    tours_read = {r["tour"] for r in receipt["results"] if "date_format" in r}
    once = {e["event"]: e for e in reversed(events)}
    n_week = sum(1 for e in once.values() if e["day"] and week <= e["day"] <= week + timedelta(days=6))
    if not n_week or tours_read != set(TOURS):
        why_not = []
        if not events:
            why_not.append("no Kalshi event was read")
        elif not n_week:
            why_not.append(f"0 Kalshi events dated in the week; {len(once)} read, "
                           f"{sum(1 for e in once.values() if e['day'] is None)} with no date in the ticker")
        if tours_read != set(TOURS):
            why_not.append("results file(s) not read: " + ", ".join(t for t in TOURS if t not in tours_read))
        refusals.append("M: not run: " + "; ".join(why_not))
        echo("  NOT RUN: " + "; ".join(why_not))
    else:
        r = match_week(events, rows, week)
        receipt["match_count"] = {**r, "reasons": dict(r["reasons"]), "matched_by_tour": dict(r["matched_by_tour"])}
        echo(f"  week {r['week'][0]} .. {r['week'][1]} · Kalshi events in the week {r['events']} · matched "
             f"{r['matched']} · refused-ambiguous {r['refused_ambiguous']} · refused-unreadable "
             f"{r['refused_unreadable']} · unmatched {r['unmatched']}")
        echo("  matched by tour: " + (", ".join(f"{t} {n}" for t, n in sorted(r["matched_by_tour"].items())) or "none"))
        echo("  refused reasons: " + (", ".join(f"{k_} {n}" for k_, n in r["reasons"].most_common()) or "none"))
        receipt["match_count"]["name_shapes"] = {side: dict(c) for side, c in r["name_shapes"].items()}
        echo("  name shapes · Kalshi (the week's events): "
             + (" · ".join(f"{k_} {n}" for k_, n in sorted(r["name_shapes"]["kalshi"].items())) or "none")
             + " · results files (rows near the week): "
             + (" · ".join(f"{k_} {n}" for k_, n in sorted(r["name_shapes"]["results"].items())) or "none"))
        for title, xs in (("matched (sample)", r["matched_sample"]), ("refused (sample)", r["refused_sample"]),
                          ("unmatched (sample)", r["unmatched_sample"])):
            if xs:
                echo(f"  {title}:")
                for x in xs:
                    echo(f"    {x}")

    echo("\nN NAMED, NOT FETCHED")
    for line in NAMED_NOT_FETCHED:
        echo(f"  {line}")

    echo(f"\nCALLS ({len(calls.made)}; every rate-limit header the answers carried):")
    for c in calls.made:
        echo(f"  GET {c['url']} · {c.get('error') or c['status']}"
             + (f" · {c['bytes']} bytes" if c.get("bytes") is not None else "")
             + (" · " + ", ".join(f"{h}: {v}" for h, v in c["rate_limit"].items()) if c["rate_limit"] else ""))
    receipt["calls"] = calls.made
    receipt["refusals"], receipt["failures"] = refusals, failures
    rc = 1 if failures or calls.failed() else 2 if refusals else 0
    for x in refusals:
        echo(f"REFUSED: {x}")
    for x in failures:
        echo(f"FAILED: {x}")
    if a.out:
        try:
            Path(a.out).expanduser().write_text(json.dumps(receipt, indent=1, default=str))
            echo(f"receipt written to {a.out}")
        except OSError as x:
            rc = rc or 2
            echo(f"REFUSED: the receipt could not be written to {a.out} ({type(x).__name__}: {x})")
    echo(f"TENNIS-SOURCE-PROBE exit {rc} · calls {len(calls.made)} · failed {len(calls.failed())} · "
         f"refusals {len(refusals)}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
