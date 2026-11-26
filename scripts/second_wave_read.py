"""
THE SECOND WAVE's READ (DEV 3, ARCHITECT addendum 565 item 3), READ-ONLY, COUNTS ONLY. Three reads, three modes.

The ruling, verbatim (addendum 565 item 3, in part): "THE SECOND WAVE's READ IS AUTHORISED, counts only, two blocks of
mine. DEV 3, your questions:
 Q1 YES: Kalshi's current soccer series and their legs, for EL1 and CZE first, the nine in the pot and the ticker-only
 three beside them. From the laptop.
 Q2 YES: the football plan's daily limit as the provider's own status call serves it, and which plan the host's key
 holds (#554). At the host sitting. The plan's name and its limit are printed; no key value is.
 Q3 YES: whether the host stores EL1 and CZE 2026/27 rows, whether its whole-season list names them (yes or no, never
 the list), and CZE's remaining regular fixtures by round label. On the host's backup copy, read-only.
 Q4: with the declaration, not now. Q5: your default stands; the three are out of this wave.
 Q6: ruled from the read. If a league shows three legs and an odds share, market-only capture comes first and its
 close share is measured before any shadow date is written.
 ...
 DEV 3 — BUILD THE READ, read-only tooling of your own lane: one script with the three reads as three modes, each
 printing counts, tickers, round labels and a plan's name and limit, never a provider row, a price or a key. The
 laptop mode takes no database. The host modes read a copy opened mode=ro and immutable=1 and make one status call.
 Name the command and its arguments in the PR body; ship no block."

NOTHING HERE WAS CONFIRMED AGAINST A LIVE ANSWER. The script was written where every provider host is refused by the
proxy. Every served field name below is a hypothesis taken from the shapes the repo already reads (each cited where
it is used); a required field the read cannot find REFUSES that read (law 1), never guessed. Every ticker and league
word typed here is a SEARCH KEYWORD (a hypothesis): the receipt prints what the listing SERVES, and marks a keyword
match CANDIDATE.

THE THREE MODES

  kalshi  (Q1, the laptop). Takes NO database and imports nothing that opens one (src.adapters.kalshi: logging,
          datetime and requests; src.ingestion.kalshi_match and src.walters.k_receipt: stdlib only). Public data, no
          key. ONE series listing through the repo's own path (KalshiAdapter._get, find_series's params: GET /series
          with category=Sports, and unfiltered only when that serves no series; --listing all reads the unfiltered
          listing instead), every served cursor followed and a repeated cursor refused. It prints the listing's size,
          its category and tag vocabulary as served, and every series that looks like soccer (the word "soccer" in
          its title, category or tags, or a ticker the adapter maps or reserves for soccer; the rule is a hypothesis
          and says so), by TICKER only (no served title is printed). Then, in this order, EL1 and CZE, the nine in the pot (NED, POR, BEL, SCO, TUR, AUT, SUI,
          GRE, EL2) and the ticker-only three (2. Bundesliga, Brasileirao, MYSL): which served series match the
          reserved ticker (KalshiAdapter.SOCCER_SERIES_RESERVED, read from the adapter, never typed here), the
          ticker the 2026-10-07 receipt's comments name (an INFERENCE), or the league's search keywords (CANDIDATE;
          a candidate the soccer rule above does not pass is listed as NOT SOCCER and never read). For each matched
          series (exact, or a soccer CANDIDATE) whose ticker ends "GAME" (the game-winner shape every wired series has,
          kalshi.py resolve_soccer_series), its open events (GET /events) and open markets (GET /markets), both
          paged to the last cursor, as COUNTS: events listed, events with an open market, markets per event, events
          of exactly three legs with exactly one Tie leg (KalshiAdapter.is_tie_market, the repo's own Tie rule),
          and of those how many have every leg quoted on both sides (k_receipt.leg_two_sided over
          KalshiAdapter.yes_quotes: a COUNT, the quote never printed); and ONE event's legs as a count with its Tie
          legs counted (no leg label, no team name: the ruling's set is counts, tickers, round labels and a plan's
          name and limit). The category and tag vocabulary of the listing is printed with its counts so the soccer
          rule can be checked against what is served (served classification words, not a row; named in the PR body
          for the architect). Paced as the repo paces Kalshi: no sleep between calls, a
          429 asked again after 2 s and then 5 s (kalshi_history.Calls, addendum 104 item 2), every call and retry
          counted against --max-calls.
  status  (Q2, the host). EXACTLY ONE call: GET /status on the football provider (api_football.py's hosts and
          headers: v3.football.api-sports.io with x-apisports-key, or, when API_FOOTBALL_HOST names the RapidAPI
          host, its /v3 base with x-rapidapi-key and x-rapidapi-host). The key is read by its env NAME,
          API_FOOTBALL_KEY, from this process's environment ONLY: this script opens no .env, no host.env and no key
          file; how the environment reaches the run is the block's. It prints the NAME of the key used, never its
          value (every line passes a redaction of it), the subscription's plan and active flag and the requests'
          limit_day and current as served (basketball_source_probe.status_summary's fields), and every response
          header whose name holds "ratelimit". The account block is never read or printed. No retry: a 429 is a
          failed call. No redirect is followed (allow_redirects=False): a 3xx is a failed call, its status code
          printed and its Location never, so the one call stays one and the key header never reaches another host.
  copy    (Q3, the host's backup copy). --db COPY is required: refused under ANY directory named data (case ignored,
          as given or resolved, nhl_cohort_count's rule), by mlb_pitchers_gate.check_db (an existing file, never
          created, never the repo's data/ by path or by identity, never the app's configured database), and beside a
          -wal, -shm or -journal file (intl_shadow.copy_sidecars). Opened with sqlite3 on
          file:<copy>?mode=ro&immutable=1 (mlb_pitchers_gate.COPY_URI_QUERY; addendum 198 item 6(ii)); its sha256
          is taken before and after the read and a change refuses. It prints, for EL1 and CZE: the competition rows
          stored (count and stored sport), every stored season string with its match count, and the 2026/27 matches
          by status (MatchStatus stored as the member NAME, schema.py:68-98). The whole-season list: --fullseason-list
          FILE, else SP_FULLSEASON_LIST as this process was started (the environment is snapshot in main() before
          any repo import can run load_dotenv, so a value only in the checkout's .env is never used; host.env is
          never opened); refused under any directory named data or the checkout's data/ (law 5, before any read),
          and refused when --out names the same file as --db or the list; parsed by sp_run.fullseason_entries
          (the list's ONE parser); prints only YES or NO per code (a line whose code is EL1 / CZE, and whether that
          line's season is written 2026/27) and the number of entries, NEVER a line of the list. CZE's NON-FINISHED
          2026/27 matches (status other than FINISHED, each status counted apart) by stored round label (matches.stage,
          api-football's league.round verbatim), each label placed by soccer_v23.placement_with_source (F3's
          soccer_expansion.placement first, then addendum 456's ruled table: "Championship Group - N" in CZE is
          PLAY-OFF, 456 item 4(a)) as regular, playoff or CANNOT PLACE. The REMAINING regular total counts only
          the statuses that are still fixtures to play, SCHEDULED, POSTPONED and LIVE (schema.py:68-98); every other
          non-FINISHED status (CANCELLED; STALE_ORPHAN, "never a fixture"; SETTLED_SCALAR; a word outside the enum)
          is printed apart as NOT REMAINING, never in the total. What this mode
          imports: the fence (mlb_pitchers_gate.check_db) imports config to compare the copy against the app's
          configured database, and config runs load_dotenv on the checkout's .env (nhl_cohort_count's precedent; this
          script reads nothing from what it loads: the list path comes from the snapshot taken before); the placement (soccer_v23) imports src.db.schema, SQLAlchemy's declarations
          with no engine. src.db.database, the module that builds the engine, is never imported.

COMMANDS (named for the PR body; the architect writes the blocks):

    python3 scripts/second_wave_read.py kalshi [--listing sports|all] [--max-calls N] [--out FILE]
    python3 scripts/second_wave_read.py status [--out FILE]
    python3 scripts/second_wave_read.py copy --db COPY [--fullseason-list FILE] [--out FILE]

Every mode prints a header line naming addendum 565 item 3 and the mode, and the number of requests it made (copy:
0). --out FILE writes the same receipt as JSON (refused under any data/ directory, checked before any call). Never
printed or written: a price, a bid / ask / last / volume / open-interest field, a provider row as served, a key value,
the account block, a line of the whole-season list.

Exit (the repo's probe convention): 0 every read answered; 1 a call failed (network, HTTP, a redirect, a provider
error, an answer that is not JSON); 2 a read REFUSED (an option, the copy's fence, no key set, an answer of an
unexpected shape, a required field not served, a listing left incomplete by the call cap, the whole-season list not
given, under data/, not UTF-8 or not parsed, --out under data/, the same file as --db or the list, or not writable,
before the run or when the receipt is written). No __pycache__ is written (sys.dont_write_bytecode). Python 3.10 is the floor (CONTRIBUTING.md).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True      # nothing is written anywhere but --out (nhl_cohort_count's rule)

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import requests  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adapters.kalshi import KalshiAdapter  # noqa: E402  (logging, datetime and requests only: no DB)
from src.ingestion import kalshi_match as km  # noqa: E402  (stdlib only: event_of)

OK, FAILED, REFUSED = 0, 1, 2
RULING = "ARCHITECT addendum 565 item 3"
HEADER = "SECOND WAVE READ ({}; DEV 3) · mode {} · read-only, counts only · {}"
UNCONFIRMED = "NOTHING HERE WAS CONFIRMED AGAINST A LIVE ANSWER: typed tickers and words are search keywords"

# ---- Q1: the leagues, in the ruling's order ---------------------------------------------------------------------
# reserved: the code whose ticker KalshiAdapter.SOCCER_SERIES_RESERVED holds (read from the adapter at run time).
# inference: a ticker named only in kalshi.py's comments quoting the 2026-10-07 receipt (kalshi.py:217-218), a
# hypothesis. keywords: search words, each a hypothesis (law 1): a match by them is a CANDIDATE.
LEAGUES = (
    {"group": "first", "code": "EL1", "name": "EFL League One", "reserved": "EL1",
     "keywords": ("league one", "league 1", "efl l1")},
    {"group": "first", "code": "CZE", "name": "Czech first league", "reserved": "CZE",
     "keywords": ("czech", "chance liga", "fortuna liga")},
    {"group": "pot", "code": "NED", "name": "Eredivisie", "keywords": ("eredivisie", "netherlands", "dutch")},
    {"group": "pot", "code": "POR", "name": "Primeira Liga",
     "keywords": ("primeira", "liga portugal", "portugal", "portuguese")},
    {"group": "pot", "code": "BEL", "name": "Belgian Pro League",
     "keywords": ("belgian", "belgium", "jupiler", "pro league")},
    {"group": "pot", "code": "SCO", "name": "Scottish Premiership",
     "keywords": ("scottish", "scotland", "spfl", "premiership")},
    {"group": "pot", "code": "TUR", "name": "Super Lig",
     "keywords": ("super lig", "süper lig", "turkish", "turkey", "türkiye")},
    {"group": "pot", "code": "AUT", "name": "Austrian Bundesliga", "keywords": ("austrian", "austria")},
    {"group": "pot", "code": "SUI", "name": "Swiss Super League", "keywords": ("swiss", "switzerland")},
    {"group": "pot", "code": "GRE", "name": "Greek Super League", "keywords": ("greek", "greece")},
    {"group": "pot", "code": "EL2", "name": "EFL League Two", "keywords": ("league two", "league 2", "efl l2")},
    {"group": "ticker-only", "code": "BUNDESLIGA2", "name": "2. Bundesliga (INFERENCE)",
     "inference": "KXBUNDESLIGA2GAME", "keywords": ("2. bundesliga", "bundesliga 2")},
    {"group": "ticker-only", "code": "BRASILEIRO", "name": "Brasileirao (INFERENCE)",
     "inference": "KXBRASILEIROGAME", "keywords": ("brasileir", "brazil")},
    {"group": "ticker-only", "code": "MYSL", "name": "MYSL (a Tie leg seen on MYSL samples 2026-08-17, kalshi.py:266-267;"
     " no ticker in git)", "keywords": ("mysl", "malaysia")},
)
SOCCER_WORD = "soccer"                        # the soccer filter's word (a hypothesis): title, category or tags
PAGE_LIMIT = 200                              # KalshiAdapter.open_markets_for_series's page size
MAX_PAGES = 50                                # per listing; reaching it with a cursor still served refuses
MAX_CALLS = 200                               # --max-calls default; every call and retry counts
RETRY_429_WAITS = (2, 5)                      # kalshi_history.RETRY_429_WAITS (addendum 104 item 2)
_wait = time.sleep                            # the tests replace it; the run waits for real


class Capped(RuntimeError):
    """The call cap was reached before a call: the listing is incomplete (REFUSED, never a partial count)."""


class ReadRefused(RuntimeError):
    """A read this script will not complete: exit 2, the reason printed."""


class Out:
    """Every printed line and the receipt pass through here: a secret value is replaced before it is shown
    (basketball_source_probe.Out's rule)."""

    def __init__(self):
        self.secrets: set = set()
        self.lines: list = []

    def redact(self, text: str) -> str:
        for s in sorted(self.secrets, key=len, reverse=True):
            if s:
                text = text.replace(s, "<redacted>")
        return text

    def __call__(self, line: str = "") -> None:
        line = self.redact(str(line))
        self.lines.append(line)
        print(line)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _shown(v) -> str:
    """A stored or served string for a line: quoted, non-printable characters escaped."""
    return repr(v)


# ---- Q1: Kalshi -------------------------------------------------------------------------------------------------

class CountedKalshi(KalshiAdapter):
    """KalshiAdapter whose every call is counted against a cap and recorded (path, params, outcome, never the body).
    A 429 alone is asked again after RETRY_429_WAITS, each retry a counted call (kalshi_history.Calls' rule)."""

    def __init__(self, *args, cap: int = MAX_CALLS, **kw):
        super().__init__(*args, **kw)
        self.cap = cap
        self.made = 0
        self.retries_429 = 0
        self.calls: list = []

    def _get(self, path: str, params: dict | None = None) -> dict:
        waits = list(RETRY_429_WAITS)
        while True:
            if self.made >= self.cap:
                raise Capped("the call cap ({}) was reached".format(self.cap))
            self.made += 1
            try:
                data = super()._get(path, params)
            except requests.HTTPError as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status == 429 and waits and self.made < self.cap:
                    self.retries_429 += 1
                    self.calls.append({"path": path, "params": params, "error": "HTTP 429, asked again"})
                    _wait(waits.pop(0))
                    continue
                self.calls.append({"path": path, "params": params, "error": "HTTP {}".format(status)})
                raise
            except Exception as e:
                self.calls.append({"path": path, "params": params, "error": type(e).__name__})
                raise
            self.calls.append({"path": path, "params": params, "error": None})
            return data


def read_pages(ad: CountedKalshi, path: str, key: str, params: dict | None) -> tuple:
    """(every item of `key` across the pages, pages read, cursor served at all). Paged by `cursor` to the page that
    serves none (kalshi_tennis.read_all's rule): a repeated cursor, MAX_PAGES reached with a cursor left, an answer
    that is not {key: [...]}, or an entry that is not an object REFUSES (ReadRefused), never a partial list. A failed
    call raises as it was raised (exit 1); the cap raises Capped (exit 2)."""
    out: list = []
    seen: set = set()
    cursor = None
    served_cursor = False
    for page in range(1, MAX_PAGES + 1):
        p = dict(params or {})
        if cursor:
            p["cursor"] = cursor
        data = ad._get(path, params=p or None)
        if not isinstance(data, dict) or not isinstance(data.get(key), list):
            shape = "keys {}".format(sorted(data)) if isinstance(data, dict) else type(data).__name__
            raise ReadRefused("/{} {}: page {} is not {{'{}': [...]}} ({})".format(
                path, json.dumps(params or {}, sort_keys=True), page, key, shape))
        bad = sum(1 for x in data[key] if not isinstance(x, dict))
        if bad:
            raise ReadRefused("/{} page {}: {} entries are not objects".format(path, page, bad))
        out.extend(data[key])
        cursor = data.get("cursor")
        if not cursor:
            return out, page, served_cursor
        served_cursor = True
        cursor = str(cursor)
        if cursor in seen:
            raise ReadRefused("/{} page {} served a cursor already read (the listing would loop)".format(path, page))
        seen.add(cursor)
    raise ReadRefused("/{}: {} pages read and a cursor is still served: incomplete".format(path, MAX_PAGES))


def read_listing(ad: CountedKalshi, which: str) -> tuple:
    """(the served series, a receipt line on how it was read). find_series's params: category=Sports first and the
    unfiltered listing only when that serves no series (kalshi.py:84-90); --listing all reads the unfiltered one."""
    tries = ({"category": "Sports"}, None) if which == "sports" else (None,)
    series: list = []
    how = ""
    for params in tries:
        series, pages, cur = read_pages(ad, "series", "series", params)
        how = "GET /series {} · {} page(s){}".format(json.dumps(params or {}), pages,
                                                   " (a cursor was served and followed)" if cur else "")
        if series:
            break
    return series, how


def _hay(s: dict) -> str:
    tags = s.get("tags")
    tags = " ".join(str(t) for t in tags) if isinstance(tags, list) else str(tags or "")
    return " ".join([str(s.get("title") or ""), str(s.get("category") or ""), tags, str(s.get("ticker") or "")]).lower()


def soccer_tickers() -> set:
    """Every ticker the adapter maps or reserves for soccer, upper case (read from the adapter)."""
    return {str(t).upper() for t in list(KalshiAdapter.SOCCER_GAME_SERIES.values())
            + list(KalshiAdapter.SOCCER_SERIES_RESERVED.values())}


def is_soccer(s: dict) -> bool:
    return SOCCER_WORD in _hay(s) or str(s.get("ticker") or "").upper() in soccer_tickers()


def is_game(ticker) -> bool:
    return str(ticker or "").upper().endswith("GAME")        # kalshi.py resolve_soccer_series's game-series rule


def league_matches(lg: dict, series: list) -> dict:
    """{'exact': [(served ticker, how)], 'candidates': [(served ticker, the keyword that matched, soccer?)]}. Exact:
    the served ticker equals (case ignored) the adapter's reserved ticker or the comment's inferred one. Candidates: a
    keyword found in title, category, tags or ticker (find_series's haystack), the exact ones excluded, each flagged
    by is_soccer: only a soccer candidate is read (a rugby "premiership" or a basketball "turkish" is never read)."""
    want = {}
    if lg.get("reserved"):
        t = KalshiAdapter.SOCCER_SERIES_RESERVED.get(lg["reserved"])
        if t:
            want[str(t).upper()] = "RESERVED in the adapter ({})".format(
                KalshiAdapter.SOCCER_SERIES_RESERVED_RULING.get(lg["reserved"], "ruling not named"))
    if lg.get("inference"):
        want[lg["inference"].upper()] = "INFERENCE (kalshi.py comments quoting the 2026-10-07 receipt)"
    exact, cands = [], []
    for s in series:
        t = str(s.get("ticker") or "")
        if t.upper() in want:
            exact.append((t, want[t.upper()]))
            continue
        hay = _hay(s)
        kw = next((k for k in lg["keywords"] if k.lower() in hay), None)
        if kw:
            cands.append((t, kw, is_soccer(s)))
    return {"exact": exact, "candidates": cands, "wanted": sorted(want)}


def leg_stats(events: list, markets: list) -> dict:
    """Counts only, from the open events and markets of one series. Markets are grouped by km.event_of; the Tie leg
    is KalshiAdapter.is_tie_market; a two-sided leg is k_receipt.leg_two_sided over KalshiAdapter.yes_quotes. Never a
    price: the quotes are read to count, and no value leaves this function."""
    from src.walters.k_receipt import leg_two_sided
    by_event: dict = {}
    for m in markets:
        by_event.setdefault(km.event_of(m), []).append(m)
    listed = {str(e.get("event_ticker")) for e in events if e.get("event_ticker")}
    legs = Counter()
    three_tie = []
    tie_not_three = 0
    for ev, mks in by_event.items():
        ties = sum(1 for m in mks if KalshiAdapter.is_tie_market(m))
        legs[len(mks)] += 1
        if len(mks) == 3 and ties == 1:
            three_tie.append(ev)
        elif ties:
            tie_not_three += 1
    quoted = 0
    for ev in three_tie:
        if all(leg_two_sided(*KalshiAdapter.yes_quotes(m)) for m in by_event[ev]):
            quoted += 1
    sample_ev = sorted(three_tie)[0] if three_tie else (sorted(by_event)[0] if by_event else None)
    sample = {}
    if sample_ev is not None:              # counts only: no leg label (a team name) leaves this function
        sample = {"legs": len(by_event[sample_ev]),
                  "tie_legs": sum(1 for m in by_event[sample_ev] if KalshiAdapter.is_tie_market(m))}
    return {"events_listed": len(events), "events_listed_distinct": len(listed), "markets": len(markets),
            "events_with_open_markets": len(by_event),
            "listed_without_open_market": len(listed - set(by_event)) if listed else None,
            "legs_per_event": {str(k): v for k, v in sorted(legs.items())},
            "three_legs_one_tie": len(three_tie), "three_legs_one_tie_all_two_sided": quoted,
            "events_with_tie_not_three_legs": tie_not_three,
            "sample_event": sample_ev, "sample_legs": sample}


def read_series(ad: CountedKalshi, ticker: str) -> dict:
    events, ep, _ = read_pages(ad, "events", "events",
                               {"series_ticker": ticker, "status": "open", "limit": PAGE_LIMIT})
    markets, mp_, _ = read_pages(ad, "markets", "markets",
                                 {"series_ticker": ticker, "status": "open", "limit": PAGE_LIMIT})
    st = leg_stats(events, markets)
    st.update(events_pages=ep, markets_pages=mp_)
    return st


def kalshi_mode(a, say: Out, env=None, adapter: CountedKalshi | None = None) -> tuple:
    ad = adapter or CountedKalshi(cap=a.max_calls)
    rec: dict = {"mode": "kalshi", "base": ad.base, "listing": a.listing, "leagues": [], "series_read": {}}
    say("  " + UNCONFIRMED + ". Public data, no key; no database is opened or imported.")
    rc = OK
    try:
        series, how = read_listing(ad, a.listing)
    except Capped as e:
        say("  REFUSED: the series listing: {}; nothing read".format(e))
        return REFUSED, rec, ad.made
    except ReadRefused as e:
        say("  REFUSED: the series listing: {}".format(e))
        return REFUSED, rec, ad.made
    except Exception as e:
        say("  FAILED: the series listing did not answer ({})".format(
            ad.calls[-1]["error"] if ad.calls and ad.calls[-1]["error"] else type(e).__name__))
        return FAILED, rec, ad.made
    cats = Counter(str(s.get("category")) for s in series)
    tags = Counter(str(t) for s in series for t in (s.get("tags") if isinstance(s.get("tags"), list) else []))
    say("  LISTING: {} · {} series served".format(how, len(series)))
    say("  categories as served: {}".format(dict(sorted(cats.items()))))
    say("  tags as served ({} distinct): {}".format(len(tags), dict(sorted(tags.items()))))
    soccer = sorted((s for s in series if is_soccer(s)), key=lambda s: str(s.get("ticker") or ""))
    rec.update(listing_how=how, series_served=len(series), categories=dict(cats), tags=dict(tags),
               soccer=[{"ticker": s.get("ticker"), "game": is_game(s.get("ticker"))} for s in soccer])
    say("  SOCCER SERIES SERVED ({}; the rule, a hypothesis: the word {!r} in title, category or tags, or a ticker "
        "the adapter maps or reserves for soccer; GAME = a ticker ending GAME; tickers only):".format(
            len(soccer), SOCCER_WORD))
    for s in soccer:
        say("    {}{}".format(s.get("ticker"), " · GAME" if is_game(s.get("ticker")) else ""))
    to_read: list = []
    for lg in LEAGUES:
        m = league_matches(lg, series)
        rec["leagues"].append({"group": lg["group"], "code": lg["code"], "name": lg["name"],
                               "keywords": list(lg["keywords"]), "wanted_tickers": m["wanted"],
                               "exact": [{"ticker": t, "how": h} for t, h in m["exact"]],
                               "candidates": [{"ticker": t, "keyword": k, "soccer": sc}
                                              for t, k, sc in m["candidates"]]})
        say("\n  [{}] {} · {} · tickers looked for: {} · search keywords (hypotheses): {}".format(
            lg["group"], lg["code"], lg["name"], ", ".join(m["wanted"]) or "none", ", ".join(lg["keywords"])))
        if not m["exact"] and not m["candidates"]:
            say("    no served series matches")
        for t, h in m["exact"]:
            say("    SERVED {} · {}{}".format(t, h, " · GAME" if is_game(t) else ""))
        for t, k, sc in m["candidates"]:
            say("    CANDIDATE {} · matched keyword {!r} (a hypothesis){}{}".format(
                t, k, " · GAME" if is_game(t) else "",
                "" if sc else " · NOT SOCCER by the rule above: listed, never read"))
        for w in m["wanted"]:
            if w not in {t.upper() for t, _ in m["exact"]}:
                say("    NOT SERVED: {} is not in this listing".format(w))
        for t in [t for t, _ in m["exact"]] + [t for t, _, sc in m["candidates"] if sc]:
            if is_game(t) and t not in to_read:
                to_read.append(t)
    say("\n  GAME SERIES READ ({}; open events and open markets, counts only, no price):".format(len(to_read)))
    for t in to_read:
        try:
            st = read_series(ad, t)
        except Capped as e:
            say("    {}: REFUSED: {}; this and every later series NOT READ".format(t, e))
            rec["series_read"][t] = {"refused": str(e)}
            rc = max(rc, REFUSED)
            break
        except ReadRefused as e:
            say("    {}: REFUSED: {}".format(t, e))
            rec["series_read"][t] = {"refused": str(e)}
            rc = max(rc, REFUSED)
            continue
        except Exception as e:
            why = ad.calls[-1]["error"] if ad.calls and ad.calls[-1]["error"] else type(e).__name__
            say("    {}: FAILED ({})".format(t, why))
            rec["series_read"][t] = {"failed": why}
            rc = max(rc, FAILED)
            continue
        rec["series_read"][t] = st
        say("    {}: events listed {} · events with an open market {} · open markets {} · legs per event {}".format(
            t, st["events_listed"], st["events_with_open_markets"], st["markets"], st["legs_per_event"]))
        say("      three legs with one Tie leg: {} · of those, every leg quoted both sides: {} · events with a Tie "
            "leg but not three legs: {}".format(st["three_legs_one_tie"], st["three_legs_one_tie_all_two_sided"],
                                               st["events_with_tie_not_three_legs"]))
        if st["sample_event"] is not None:
            say("      one event ({}): {} legs, of which Tie legs {} (labels not printed)".format(
                st["sample_event"], st["sample_legs"]["legs"], st["sample_legs"]["tie_legs"]))
    rec["retries_429"] = ad.retries_429
    rec["calls"] = [{"path": c["path"], "params": c["params"], "error": c["error"]} for c in ad.calls]
    return rc, rec, ad.made


# ---- Q2: the football plan --------------------------------------------------------------------------------------

KEY_NAME = "API_FOOTBALL_KEY"                 # config.py:48 (Settings.load); BACKLOG #554: both machines read it
HOST_NAME = "API_FOOTBALL_HOST"               # config.py:49
HOST_DIRECT = "v3.football.api-sports.io"     # api_football.py _HOST_DIRECT
HOST_RAPID = "api-football-v1.p.rapidapi.com"  # api_football.py _HOST_RAPID


def status_target(env) -> tuple:
    """(url, headers, host) as APIFootballAdapter.__init__ builds them (api_football.py:211-222)."""
    host = (env.get(HOST_NAME) or "").strip() or HOST_DIRECT
    key = (env.get(KEY_NAME) or "").strip()
    if host == HOST_RAPID:
        return "https://{}/v3/status".format(host), {"x-rapidapi-key": key, "x-rapidapi-host": host}, host
    return "https://{}/status".format(host), {"x-apisports-key": key}, host


def status_mode(a, say: Out, env=None) -> tuple:
    env = os.environ if env is None else env
    raw = env.get(KEY_NAME) or ""
    say.secrets.update(x for x in (raw, raw.strip()) if x.strip())
    rec: dict = {"mode": "status", "key_name": KEY_NAME}
    if not raw.strip():
        say("  REFUSED: {} is not set in this process's environment (this script opens no env file); no call "
            "made".format(KEY_NAME))
        return REFUSED, rec, 0
    url, headers, host = status_target(env)
    rec["host"] = host
    say("  key used: {} (the value is never printed) · host {} ({})".format(
        KEY_NAME, host, "{} set".format(HOST_NAME) if (env.get(HOST_NAME) or "").strip() else "the adapter's default"))
    try:
        r = requests.get(url, headers=headers, timeout=30, allow_redirects=False)   # one call, the key stays here
    except Exception as e:
        say("  FAILED: GET /status did not answer ({})".format(type(e).__name__))
        return FAILED, rec, 1
    hdr = {k: v for k, v in dict(r.headers or {}).items() if "ratelimit" in str(k).lower()}
    rec["http"] = r.status_code
    rec["rate_limit_headers"] = hdr
    say("  GET /status · HTTP {} · rate-limit headers as served {}".format(r.status_code, hdr))
    if 300 <= int(r.status_code or 0) < 400:
        say("  FAILED: HTTP {} (a redirect, not followed; its target is not printed)".format(r.status_code))
        return FAILED, rec, 1
    if r.status_code != 200:
        say("  FAILED: HTTP {}".format(r.status_code))
        return FAILED, rec, 1
    try:
        body = r.json()
    except ValueError:
        say("  FAILED: the answer is not JSON")
        return FAILED, rec, 1
    errs = body.get("errors") if isinstance(body, dict) else None
    if errs and (errs if isinstance(errs, list) else list(errs.values()) if isinstance(errs, dict) else [errs]):
        say("  FAILED: the provider answered with errors (keys: {})".format(
            sorted(errs) if isinstance(errs, dict) else "a list of {}".format(len(errs))))
        return FAILED, rec, 1
    resp = body.get("response") if isinstance(body, dict) else None
    if not isinstance(resp, dict):
        say("  REFUSED: /status 'response' is {}, not an object".format(type(resp).__name__))
        return REFUSED, rec, 1
    sub = resp.get("subscription") if isinstance(resp.get("subscription"), dict) else {}
    req = resp.get("requests") if isinstance(resp.get("requests"), dict) else {}
    plan = {k: sub.get(k) for k in ("plan", "active")}
    reqs = {k: req.get(k) for k in ("limit_day", "current")}
    rec.update(subscription=plan, requests=reqs)
    say("  PLAN: {} · active {}".format(_shown(plan["plan"]), plan["active"]))
    say("  DAILY LIMIT: limit_day {} · current {} (requests today, as served)".format(
        reqs["limit_day"], reqs["current"]))
    missing = [n for n, v in (("response.subscription.plan", plan["plan"]),
                              ("response.requests.limit_day", reqs["limit_day"])) if v is None]
    if missing:
        say("  REFUSED: not served: {} (law 1: never guessed)".format(", ".join(missing)))
        return REFUSED, rec, 1
    return OK, rec, 1


# ---- Q3: the host's backup copy ---------------------------------------------------------------------------------

SEASON = "2026/27"                            # api_football.py:818: a two-year league season, stored "2026/27"
COPY_CODES = ("EL1", "CZE")
SPLIT_CODE = "CZE"
COPY_TABLES = ("competitions", "matches")
FINISHED = "FINISHED"                         # MatchStatus member NAME, as stored (schema.py:68-98)
# The statuses that are still fixtures to play (schema.py:68-98): CANCELLED is not one; STALE_ORPHAN is "never a
# fixture, never an odds target"; SETTLED_SCALAR did not occur. Anything outside this set is NOT REMAINING (law 4).
REMAINING = ("SCHEDULED", "POSTPONED", "LIVE")
LIST_ENV = "SP_FULLSEASON_LIST"


def _named_data(p) -> str | None:
    try:
        q = Path(str(p)).expanduser()
        parts = list(q.parts) + list(q.resolve().parts)
    except (RuntimeError, OSError) as e:
        return "{} cannot be resolved ({})".format(p, type(e).__name__)
    if any(x.casefold() == "data" for x in parts):
        return "{} is under a directory named data (law 5); name a path outside it".format(p)
    return None


def copy_uri(path: Path) -> str:
    from src.walters import mlb_pitchers_gate as mp
    return path.as_uri() + mp.COPY_URI_QUERY


def check_copy(db) -> Path:
    from src.walters import intl_shadow as us
    from src.walters import mlb_pitchers_gate as mp
    if db is None or not str(db).strip():
        raise ReadRefused("--db COPY is required (a .backup copy outside data/)")
    why = _named_data(db)
    if why:
        raise ReadRefused("--db " + why + "; nothing read")
    try:
        path = mp.check_db(db)
    except mp.GateRefused as e:
        raise ReadRefused("{}; nothing read".format(e))
    try:
        sides = us.copy_sidecars(path)
    except OSError as e:
        raise ReadRefused("--db {}: a sidecar beside it cannot be checked ({}); nothing read".format(
            db, type(e).__name__))
    if sides:
        raise ReadRefused("--db {} has a sidecar ({}): not a fresh .backup copy; immutable=1 would ignore it; "
                          "nothing read".format(db, ", ".join(sides)))
    return path


def read_copy(con) -> dict:
    """Counts only. Competitions by code alone (soccer_expansion._comp's filter); matches joined on competition_id."""
    from src.walters import soccer_v23 as v23
    out: dict = {"codes": {}}
    for code in COPY_CODES:
        comps = con.execute("SELECT id, sport FROM competitions WHERE code = ?", (code,)).fetchall()
        ids = [r[0] for r in comps]
        qs = ",".join("?" * len(ids))
        seasons, by_status = {}, {}
        if ids:
            seasons = dict(con.execute(
                "SELECT season, COUNT(*) FROM matches WHERE competition_id IN ({}) GROUP BY season "
                "ORDER BY season".format(qs), ids).fetchall())
            by_status = dict(con.execute(
                "SELECT status, COUNT(*) FROM matches WHERE competition_id IN ({}) AND season = ? GROUP BY status "
                "ORDER BY status".format(qs), ids + [SEASON]).fetchall())
        out["codes"][code] = {"competitions": len(comps), "sport": sorted({str(r[1]) for r in comps}),
                              "seasons": seasons, "season_by_status": by_status}
    ids = [r[0] for r in con.execute("SELECT id FROM competitions WHERE code = ?", (SPLIT_CODE,)).fetchall()]
    labels: dict = {}
    if ids:
        rows = con.execute(
            "SELECT stage, status, COUNT(*) FROM matches WHERE competition_id IN ({}) AND season = ? AND status != ? "
            "GROUP BY stage, status".format(",".join("?" * len(ids))), ids + [SEASON, FINISHED]).fetchall()
        for stage, status, n in rows:
            labels.setdefault(stage, Counter())[str(status)] += n
    placed = []
    regular, regular_not = Counter(), Counter()
    for stage in sorted(labels, key=lambda x: (x is None, str(x))):
        pl, by_ruling = v23.placement_with_source(SPLIT_CODE, stage)
        st = labels[stage]
        rem = Counter({k: v for k, v in st.items() if k in REMAINING})
        rest = Counter({k: v for k, v in st.items() if k not in REMAINING})
        placed.append({"label": stage, "placement": pl or "CANNOT PLACE",
                       "source": ("addendum 456 (ruled table)" if by_ruling else
                                  "soccer_expansion.placement (F3)" if pl else "none"),
                       "by_status": dict(sorted(st.items())), "n": sum(rem.values()),
                       "not_remaining": sum(rest.values())})
        if pl == "regular":
            regular.update(rem)
            regular_not.update(rest)
    out["split"] = {"code": SPLIT_CODE, "season": SEASON, "remaining_statuses": list(REMAINING), "labels": placed,
                    "regular_total": sum(regular.values()), "regular_by_status": dict(sorted(regular.items())),
                    "regular_not_remaining_total": sum(regular_not.values()),
                    "regular_not_remaining_by_status": dict(sorted(regular_not.items()))}
    return out


def list_answer(path) -> dict:
    """YES or NO per code, the entries counted; never a line. A list that does not parse is REFUSED by its line
    number only (fullseason_entries' message quotes the line, so it is never shown)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_sp_run_for_second_wave", ROOT / "deploy" / "hosting" / "sp_run.py")
    sp_run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sp_run)
    try:
        entries = sp_run.fullseason_entries(path)
    except UnicodeDecodeError:                 # a ValueError too: named for what it is, its bytes never printed
        raise ReadRefused("the whole-season list is not UTF-8 text (its bytes are not printed)")
    except ValueError as e:
        m = re.search(r" line (\d+): ", str(e))
        raise ReadRefused("the whole-season list does not parse (line {}: not CODE|SEASON; its text is not "
                          "printed)".format(m.group(1) if m else "?"))
    except OSError as e:
        raise ReadRefused("the whole-season list cannot be read ({})".format(type(e).__name__))
    ans = {"entries": len(entries)}
    for code in COPY_CODES:
        mine = [e for e in entries if e[2] == code]
        ans[code] = {"named": bool(mine), "with_season_{}".format(SEASON): any(e[3] == SEASON for e in mine)}
    return ans


def list_path(a, env) -> tuple:
    """(the whole-season list's path or None, where it came from). `env` is the snapshot main() took before any
    repo import, so a value config's load_dotenv put in os.environ later is never read."""
    if getattr(a, "fullseason_list", None):
        return a.fullseason_list, "--fullseason-list"
    v = (env.get(LIST_ENV) or "").strip()
    return (v, "{} as this process was started".format(LIST_ENV)) if v else (None, "not given")


def copy_mode(a, say: Out, env=None) -> tuple:
    from src.walters import intl_shadow as us
    env = dict(os.environ) if env is None else env
    lp, lp_from = list_path(a, env)            # read BEFORE check_copy imports config (load_dotenv)
    rec: dict = {"mode": "copy", "season": SEASON}
    say("  no network: this mode makes no call.")
    try:
        path = check_copy(a.db)
    except ReadRefused as e:
        say("  REFUSED: {}".format(e))
        return REFUSED, rec, 0
    try:
        sha_before = us.copy_sha256(path)
    except OSError as e:
        say("  REFUSED: the copy could not be hashed ({}); nothing read".format(type(e).__name__))
        return REFUSED, rec, 0
    say("  copy {} · sha256 {} (before) · opened {}".format(path, sha_before, "mode=ro&immutable=1"))
    try:
        con = sqlite3.connect(copy_uri(path), uri=True)
        try:
            for t in COPY_TABLES:
                con.execute("SELECT 1 FROM {} LIMIT 1".format(t))
            got = read_copy(con)
        finally:
            con.close()
    except sqlite3.Error as e:
        say("  REFUSED: the copy cannot be read ({}); nothing reported".format(type(e).__name__))
        return REFUSED, rec, 0
    try:
        sha_after = us.copy_sha256(path)
        sides_after = us.copy_sidecars(path)
    except OSError as e:
        say("  REFUSED: the copy could not be re-read after the read ({}); nothing reported".format(type(e).__name__))
        return REFUSED, rec, 0
    if sha_after != sha_before or sides_after:
        say("  REFUSED: the copy changed during the read (sha256 or a sidecar); nothing reported")
        return REFUSED, rec, 0
    say("  sha256 after the read: unchanged, no sidecar")
    rec.update(copy=str(path), sha256=sha_before, **got)
    rc = OK
    for code in COPY_CODES:
        c = got["codes"][code]
        say("\n  {}: competition rows stored {} (sport {}) · stored seasons {}".format(
            code, c["competitions"], c["sport"] or "none",
            {k: v for k, v in c["seasons"].items()} or "none"))
        say("    {} matches by status: {}{}".format(SEASON, c["season_by_status"] or "none",
                                                  " (total {})".format(sum(c["season_by_status"].values()))
                                                  if c["season_by_status"] else ""))
    say("\n  WHOLE-SEASON LIST ({}; yes or no only, never a line):".format(lp_from))
    if lp is None:
        say("    REFUSED: no --fullseason-list and {} was not set when this process started (host.env is never "
            "opened; a value only in the checkout's .env, which config loads for the fence, is not used); NOT "
            "READ".format(LIST_ENV))
        rec["fullseason_list"] = None
        rc = REFUSED
    else:
        try:
            ans = list_answer(lp)
        except ReadRefused as e:
            say("    REFUSED: {}".format(e))
            rec["fullseason_list"] = {"refused": str(e)}
            rc = REFUSED
        else:
            rec["fullseason_list"] = ans
            say("    entries: {}".format(ans["entries"]))
            for code in COPY_CODES:
                x = ans[code]
                say("    {}: named {} · with season {} as written: {}".format(
                    code, "YES" if x["named"] else "NO", SEASON,
                    "YES" if x["with_season_{}".format(SEASON)] else "NO"))
    sp = got["split"]
    say("\n  {} {} NOT FINISHED, by stored round label (placement: soccer_v23.placement_with_source):".format(
        SPLIT_CODE, SEASON))
    if not sp["labels"]:
        say("    none stored")
    for x in sp["labels"]:
        say("    {} · {} remaining · {} · {}".format(_shown(x["label"]), x["n"], x["placement"].upper()
                                         if x["placement"] != "CANNOT PLACE" else "CANNOT PLACE",
                                         "by {}".format(x["source"]) if x["source"] != "none" else "unplaced"))
        say("      by status {}".format(x["by_status"]))
    say("    REGULAR REMAINING ({}): {} · by status {}".format(
        ", ".join(REMAINING), sp["regular_total"], sp["regular_by_status"]))
    say("    REGULAR NOT REMAINING (other non-FINISHED statuses, not counted above): {} · by status {}".format(
        sp["regular_not_remaining_total"], sp["regular_not_remaining_by_status"]))
    return rc, rec, 0


# ---- main -------------------------------------------------------------------------------------------------------

def refuse_data(path, what: str) -> str | None:
    """Law 5: never under a directory named data (case ignored), nor under the checkout's data/ by resolved path.
    Path arithmetic only: nothing is opened."""
    p = Path(path).expanduser()
    why = _named_data(p)
    if why:
        return "REFUSED: {} {}".format(what, why)
    data = (ROOT / "data").resolve()
    try:
        r = p.resolve()
    except (RuntimeError, OSError) as e:
        return "REFUSED: {} {} cannot be resolved ({})".format(what, path, type(e).__name__)
    if r == data or data in r.parents:
        return "REFUSED: {} {} resolves under the checkout's data/ (law 5)".format(what, path)
    return None


def _same(x, y) -> bool:
    try:
        px, py = Path(x).expanduser(), Path(y).expanduser()
        if px.resolve() == py.resolve():
            return True
        return px.exists() and py.exists() and os.path.samefile(px, py)
    except (RuntimeError, OSError):
        return True                                   # cannot tell them apart: treated as the same (refused)


def refuse_out(path, keep=()) -> str | None:
    """--out: the law-5 fence, never a directory, a folder that exists and is writable, and never the same file as
    one this run reads (`keep`: --db and the whole-season list, each (option name, path))."""
    if path is None:
        return None
    p = Path(path).expanduser()
    why = refuse_data(path, "--out")
    if why:
        return why
    for name, other in keep:
        if other and _same(p, other):
            return "REFUSED: --out {} is the same file as {}; it would be overwritten".format(path, name)
    if p.is_dir():
        return "REFUSED: --out {} is a directory; name a file".format(path)
    if not p.resolve().parent.is_dir():
        return "REFUSED: --out {}: its folder does not exist".format(path)
    if not os.access(p.resolve().parent, os.W_OK) or (p.exists() and not os.access(p, os.W_OK)):
        return "REFUSED: --out {} is not writable".format(path)
    return None


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="The second wave's read ({}; read-only, counts only)".format(RULING))
    sub = ap.add_subparsers(dest="mode", required=True)
    k = sub.add_parser("kalshi", help="Q1, the laptop: Kalshi's soccer series and their legs (no database)")
    k.add_argument("--listing", choices=("sports", "all"), default="sports",
                   help="sports: GET /series category=Sports, unfiltered only if it serves none (find_series's "
                        "rule; default); all: the unfiltered listing")
    k.add_argument("--max-calls", type=int, default=MAX_CALLS, help="the call cap, every call and retry counted")
    s = sub.add_parser("status", help="Q2, the host: ONE status call, the plan's name and daily limit")
    c = sub.add_parser("copy", help="Q3, the host's backup copy (mode=ro, immutable=1)")
    c.add_argument("--db", required=True, help="a .backup copy outside any data/ directory")
    c.add_argument("--fullseason-list", default=None,
                   help="the whole-season list (default: SP_FULLSEASON_LIST from this process)")
    for p in (k, s, c):
        p.add_argument("--out", default=None, help="write the receipt as JSON here (never under data/)")
    return ap


def main(argv=None) -> int:
    env = dict(os.environ)          # the environment as started, before any repo import can run load_dotenv
    a = build_parser().parse_args(argv)
    say = Out()
    if a.mode == "kalshi" and a.max_calls < 1:
        say("REFUSED: --max-calls must be 1 or more")
        return REFUSED
    keep = ()
    if a.mode == "copy":
        lp, lp_from = list_path(a, env)
        keep = (("--db", a.db), (lp_from, lp))
        if lp is not None:
            why = refuse_data(lp, "the whole-season list ({})".format(lp_from))
            if why:
                say(why + "; nothing read")
                return REFUSED
    refused = refuse_out(a.out, keep)
    if refused:
        say(refused)
        return REFUSED
    say(HEADER.format(RULING, a.mode, _now()))
    run = {"kalshi": kalshi_mode, "status": status_mode, "copy": copy_mode}[a.mode]
    rc, rec, made = run(a, say, env=env)
    say("\n  requests made this run: {}{}".format(
        made, " (each 429 retry counted)" if a.mode == "kalshi" else ""))
    say("  EXIT {} ({})".format(rc, {OK: "answered", FAILED: "a call failed", REFUSED: "refused"}[rc]))
    if a.out:
        receipt = {"read": "second_wave_read", "ruling": RULING, "mode": a.mode, "run_at": _now(),
                   "requests": made, "exit": rc, "record": rec, "lines": say.lines}
        try:
            Path(a.out).expanduser().write_text(say.redact(json.dumps(receipt, indent=1, default=str)) + "\n",
                                                encoding="utf-8")
        except OSError as e:
            say("REFUSED: --out {} could not be written ({}); the lines above are the run's only record".format(
                a.out, type(e).__name__))
            return REFUSED
    return rc


if __name__ == "__main__":
    sys.exit(main())
