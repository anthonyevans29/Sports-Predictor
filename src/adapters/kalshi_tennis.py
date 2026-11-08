"""
THE TENNIS ADAPTER: Kalshi's two tour series are the FIXTURE source AND the RESULTS source (ARCHITECT 2026-11-05 11:40
ET, addendum 261 item 2(c); 2026-11-06 11:40 ET, addendum 269 items 1-3; 12:20 ET, addendum 270 item 4; lane
tennis-market-only, #838). Market-only: no model, no call, no Desk family (261 item 4).

WHERE TENNIS DIFFERS FROM THE NBA'S WIRING (PR #848, api_basketball), and why, by the rulings:
- There is NO third-party fixture source. 269 item 1, the opening: "the two tour series are the fixture source AND
  the results source of the market-only record (a settled market names its winner; a scalar settlement is its own
  status, never a winner); the 12-12 wiring date STANDS on Kalshi alone." So this adapter reads Kalshi's own
  /markets listing (public, no key) and turns each event of KXATPMATCH / KXWTAMATCH into one fixture; the shared
  matcher (kalshi_match.place) then places the same series' open markets on those rows (src/ingestion/tennis_kalshi.py).
- PLAYERS AS TEAMS (261 item 2(a): "sport TENNIS, external_ids kind player"): every Team row of sport TENNIS is one
  player, named by the market's yes_sub_title, the player's FULL NAME as served (269 item 1 K2: 'Alice Tubello',
  'Leyre Romero Gormaz'). Its external id under this source is "<tour>|<the name, case-folded>" (a letter-case-only
  difference is one player: addendum 238 item 2(b), "a refusal on letter case alone was never the intent of the
  matcher's own comparison"; the receipt serves 'AYNUR MOVLYAMOVA' as an expiration_value). Kalshi serves no player id
  that this lane has read, so none is used. No alias table: 261 item 2(c) says "an alias table built only from
  receipts", and no receipt names an alias yet (ALIASES is empty).
- THE MATCHER KEYS ON yes_sub_title, NEVER THE EVENT TITLE (269 item 1 K2): the event's two players are its two
  markets' yes_sub_title; the event title (surnames only, 'Hontama vs Linette') is never read.

Addendum 269 item 3, verbatim (the wiring PR "gains these from the receipt, read before anything is mapped"): "(a) the
matcher on yes_sub_title with the ambiguity sentinel (the probe's key rule — surname plus initial — is the probe's; the
adapter stores the full name as served and matches on it); (b) the result map: 'yes' / 'no' → the winner =
expiration_value, the loser the other market's player; 'scalar' → the status SETTLED_SCALAR (or the vocabulary's word
Code proposes), NO winner, the fraction kept as the settlement value — it is the ledger's truth for any position; '' →
not settled; (c) BEFORE the status map, the series' contract_terms_url (served in the listing's keys) is read and the
clause on incomplete matches — retirement, walkover, suspension — QUOTED on the PR, so the scalar cases are mapped by
the venue's own rule and never by inference; (d) the adapter pages to the last page always: a cursor left is a
refusal, never a partial count; (e) the fee M for the two series from the published schedule, matched by series; (f)
the Kalshi series read beside each other's: the two tour series only."

What the receipt served (269 item 1 K3, verbatim): "Status words as served: active, closed, finalized (ATP: active 6,
closed 10, finalized 1,392; WTA: active 8, finalized 1,720). THE SETTLEMENT, as served on finalized markets: result
'yes' / 'no' with settlement_value_dollars 1 / 0 and expiration_value = THE WINNER'S FULL NAME (ATP 675 / 675; WTA
816 / 816); result 'scalar' with a FRACTIONAL settlement value (ATP 42 of 1,392 — 3%; WTA 88 of 1,720 — 5%) and an
EMPTY expiration_value; result '' on the 10 ATP markets closed but not yet settled."

What stays NULL AND LABELLED (269 item 2, verbatim): "the score, the sets, the retirement's point and the official
winner of an incomplete match are facts the record stores as NULL AND LABELLED (law 4) until a source serves them under
terms we have read." So every tennis row's scores are null (SCORES_NULL_LABEL), a retirement or a walkover that settled
yes/no is not told apart from a completed match (Kalshi serves no such word), and a scalar match has no winner.

RETIREMENTS AND WALKOVERS, BY THE VENUE'S OWN WORDS (ARCHITECT 2026-11-08, addendum 288 item 3, THE MEANING, verbatim:
"SETTLED_SCALAR = the match did not occur (injury, walkover, forfeiture or cancellation before a ball was played) and
the venue settled at "a fair price" — 20 ATP and the WTA scalar events, the fractions kept verbatim; a retirement AFTER
a ball is played produces a yes/no settlement, the advancing player the winner — FINISHED, as built (287's reading
confirmed by the venue's words)"). So a yes/no settlement is stored FINISHED with full_time_result set, a retirement
after a ball included, and a 'scalar' settlement is SETTLED_SCALAR, never a winner, as built; the map still reads the
served result word only and infers nothing from the clause. Kalshi serves no retirement or walkover word on a yes/no
settlement (269 item 1 K3), so a retirement is not told apart from a completed match.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from src.adapters.base import DataAdapter
from src.adapters.normalized import (
    NormalizedCompetition,
    NormalizedMatch,
    NormalizedMatchStats,
    NormalizedTeam,
)
from src.db.schema import MatchStatus, Result, Sport

log = logging.getLogger(__name__)

SOURCE = "kalshi_tennis"

# THE TWO TOUR SERIES, AND NOTHING ELSE (269 item 1 K1, verbatim: "the two tour series READ as served: KXATPMATCH 'ATP
# Tennis Match' and KXWTAMATCH 'WTA Tennis Match' (category Sports, tags Tennis, frequency custom). [...] the market-only
# record is the two tour series and nothing else"; item 3(f): "the two tour series only"). The competition code is the
# tour; the competition name is the series title as served.
SERIES: dict[str, str] = {"ATP": "KXATPMATCH", "WTA": "KXWTAMATCH"}
SERIES_TITLE: dict[str, str] = {"ATP": "ATP Tennis Match", "WTA": "WTA Tennis Match"}
# OUT OF SCOPE (269 item 1 K1: "Also listed and OUT OF SCOPE: KXATPEXACTMATCH / KXWTAEXACTMATCH (exact score), the
# doubles series, KXATPCHALLENGERMATCH / KXWTACHALLENGERMATCH, the ITF series, the exhibitions, KXDAVISCUPMATCH,
# KXUNITEDCUPMATCH (the United Cup's own series [...]), and the per-tournament annual series"; 269 item 2: "the United
# Cup's series is out of scope"; addendum 284 item 1(b): "the United Cup, exact-score, doubles, Challenger and ITF
# series out of scope"). The tickers below are the ones the stage-1 digest on #838 printed as served
# (issuecomment-6690719842); nothing here reads them: they are named so a test can prove none is selected.
OUT_OF_SCOPE = ("KXUNITEDCUPMATCH", "KXATPEXACTMATCH", "KXWTAEXACTMATCH", "KXATPDOUBLES", "KXWTADOUBLES",
                "KXMIXEDDOUBLESMATCH", "KXLAVERCUPDOUBLESMATCH", "KXATPCHALLENGERDOUBLES", "KXITFDOUBLES",
                "KXITFWDOUBLES", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXCHALLENGERMATCH", "KXITFMATCH",
                "KXITFWMATCH", "KXDAVISCUPMATCH", "KXLAVERCUPMATCH", "KXEXHIBITIONMEN", "KXEXHIBITIONWOMEN",
                "KXTENNISEXHIBITION", "KXSIXKINGSMATCH", "KXSIXKINGSSLAMMATCH", "KXATPTIEBREAK")
# The alias table (261 item 2(c): "built only from receipts"): EMPTY, no receipt names one. {served name: player name}.
ALIASES: dict[str, str] = {}

# The listing, as the probe read it: the stage-1 digest's K3 console lines (#838 issuecomment-6690719842, e.g.
# "KXATPMATCH /markets status=settled: 1392 markets, 7 page(s)") and scripts/tennis_source_probe.py's MARKET_STATUSES,
# each status to its last page. (The words "active, closed, finalized" quoted elsewhere here are the ruling's, 269
# item 1 K3; these three listing filters are the digest's and the probe's, not the ruling's text.) Read in this order;
# a market read twice (its status moved between two reads) is taken from the later.
MARKET_STATUSES = ("open", "closed", "settled")
PAGE_LIMIT = 200                 # the adapter's page size (KalshiAdapter.open_markets_for_series)
MAX_PAGES = 200                  # a safety bound only: reaching it with a cursor left is a REFUSAL, never a count

# THE KICKOFF, RULED (ARCHITECT 2026-11-08 07:55 ET, addendum 288 item 1, on the served receipt's THE TIMES; 286 item
# 4(a)). The evidence, verbatim: "occurrence_datetime is served on 1,362 of 1,372 ATP markets and sits +7 h to +29 h after
# 00:00 UTC of the ticker's date — the ticker's date is the US-Eastern calendar day of the start (02:00–24:00 ET), and
# expected_expiration_time carries the same instant on every market (the same offset table)". The ruling, verbatim:
# "RULED: a tennis row's kickoff = the event's occurrence_datetime, as served, UTC; both markets of the event must carry
# the same value (a difference refuses the event with its own label, counted); absent on both → expected_expiration_time
# by the same rule; absent on all four → the row is stored with the conservative UTC+14 instant AND the label
# START_UNREAD, so it is never captured and the receipt counts it. The stored kickoff is re-read on every sync (a
# postponed match's market "will remain open and close after the rescheduled match has finished (within two weeks)" —
# the venue's own words below — so the instant moves and the row follows it). The coverage day is the ET day of the
# kickoff, which is the ticker's date; the shared matcher's date-only rule therefore reads the right row; the IN_PLAY
# refusal fires at the real start."
# As built (kickoff(), below): per accepted event, occurrence_datetime first, then expected_expiration_time, each by the
# same rule; the kickoff's source is counted per fixture (Listing.kickoff_sources) and stored on the row's
# external_ids[KICKOFF_EXT_KEY]; a refusal is counted in Listing.refused by its label and is never a fixture. The cases
# the ruling does not name are decided conservatively and put to the architect (the PR body's OPEN ITEMS): a key whose
# value is JSON null or a blank string is read as NOT SERVED on that market (it carries no instant); a key served on
# ONE market only is not "the same value" on both, so it REFUSES the event under its own label (it never falls through
# to the next key: the fallback is ruled for "absent on both" only); a served value that does not read as an ISO
# instant WITH an offset (Z or +hh:mm; a naive time names no zone) REFUSES the event under its own label; two values
# naming the same instant in two spellings are the same value (the comparison is of the instant). START_UNREAD keeps
# kickoff_utc(day) below: 00:00 of the ticker's date at UTC+14 (the day before at 10:00 UTC), the first instant of
# that date anywhere, so no stored price could be in play; the capture refuses the row whatever its instant
# (src/ingestion/tennis_kalshi.py, START_UNREAD_ROW).
EARLIEST_OFFSET = timedelta(hours=14)
OCCURRENCE_KEY = "occurrence_datetime"
EXPIRATION_KEY = "expected_expiration_time"
KICKOFF_KEYS = (OCCURRENCE_KEY, EXPIRATION_KEY)                 # read in this order (288 item 1)
START_UNREAD = "START_UNREAD"                                    # the ruling's own label: no start served on any key
KICKOFF_SOURCES = (OCCURRENCE_KEY, EXPIRATION_KEY, START_UNREAD)  # a fixture's kickoff source, one of these, counted
# The row's external_ids key that carries its kickoff source (one of KICKOFF_SOURCES), rewritten on every sync; the
# capture reads it (only a row whose kickoff was read from a served key is ever captured).
KICKOFF_EXT_KEY = "kalshi_kickoff"
KICKOFF_LABEL = ("kickoff = the event's occurrence_datetime as served, UTC, the same on both markets; absent on both, "
                 "expected_expiration_time by the same rule (addendum 288 item 1)")
START_UNREAD_LABEL = ("START_UNREAD: no occurrence_datetime or expected_expiration_time served on either market; the row "
                      "is stored at 00:00 of the ticker's date at UTC+14 and NEVER captured (addendum 288 item 1; law 4)")
SCORES_NULL_LABEL = ("score, sets, the retirement's point and an incomplete match's official winner: NULL AND "
                     "LABELLED (addendum 269 item 2)")

# Refusal reasons for an event (counted; never a fixture).
NO_DATE = "no date in the ticker"
NOT_TWO_MARKETS = "the event does not serve exactly two markets"
NOT_TWO_PLAYERS = "the event's markets do not name two players (yes_sub_title)"
OUTSIDE_SERIES = "a ticker outside the series"
# THE KICKOFF's refusals (addendum 288 item 1: "a difference refuses the event with its own label, counted"; the
# one-market and unreadable cases are this PR's conservative reading, put to the architect). Never a fixture.
OCCURRENCE_DIFFER = "the event's two markets serve different occurrence_datetime instants"
EXPIRATION_DIFFER = ("occurrence_datetime not served on either market and the two markets serve different "
                     "expected_expiration_time instants")
OCCURRENCE_ONE_MARKET = "occurrence_datetime served on one market of the event only"
EXPIRATION_ONE_MARKET = ("occurrence_datetime not served on either market and expected_expiration_time served on one "
                         "market only")
OCCURRENCE_UNREAD = "a served occurrence_datetime that does not read as an ISO instant with an offset"
EXPIRATION_UNREAD = ("occurrence_datetime not served on either market and a served expected_expiration_time that does "
                     "not read as an ISO instant with an offset")
KICKOFF_REFUSALS = {OCCURRENCE_KEY: (OCCURRENCE_DIFFER, OCCURRENCE_ONE_MARKET, OCCURRENCE_UNREAD),
                    EXPIRATION_KEY: (EXPIRATION_DIFFER, EXPIRATION_ONE_MARKET, EXPIRATION_UNREAD)}


class Refused(RuntimeError):
    """A read this adapter will not complete (a cursor left, a repeated cursor, an answer of the wrong shape). Raised
    before anything is written: a cursor left is a refusal, never a partial count (269 item 3(d))."""


def read_all(get, series: str, status: str, *, max_pages: int = MAX_PAGES) -> tuple[list[dict], int]:
    """(every market of `series` under `status`, pages read): GET /markets paged by its cursor TO THE LAST PAGE (269
    item 3(d): "the adapter pages to the last page always: a cursor left is a refusal, never a partial count").
    The last page is the one that serves no cursor (absent, null or empty). A cursor served twice is a loop the read
    cannot leave: REFUSED. `max_pages` reached with a cursor still served: REFUSED. An answer that is not an object,
    or that serves no 'markets' key, or whose 'markets' is not a list (an error body mid-listing included): REFUSED,
    never read as an empty last page. Never loops, never returns a partial list."""
    out: list[dict] = []
    seen: set[str] = set()
    cursor = None
    for page in range(1, max_pages + 1):
        params = {"series_ticker": series, "status": status, "limit": PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor
        data = get("markets", params)
        if not isinstance(data, dict) or not isinstance(data.get("markets"), list):
            shape = (f"keys {sorted(data)}" if isinstance(data, dict) else type(data).__name__)
            raise Refused(f"REFUSED: {series} /markets status={status} page {page}: the answer is not "
                          f"{{'markets': [...]}} ({shape}): the market set is incomplete (269 item 3(d)); "
                          "nothing is written")
        bad = sum(1 for m in data["markets"] if not isinstance(m, dict))
        if bad:                           # all or nothing (269 item 3(d)): a malformed entry is never dropped
            raise Refused(f"REFUSED: {series} /markets status={status} page {page}: {bad} market entr"
                          f"{'y is' if bad == 1 else 'ies are'} not an object: the market set is incomplete "
                          "(269 item 3(d)); nothing is written")
        out.extend(data["markets"])
        cursor = data.get("cursor")
        if not cursor:
            return out, page
        cursor = str(cursor)
        if cursor in seen:
            raise Refused(f"REFUSED: {series} /markets status={status}: page {page} served a cursor already read "
                          "(the listing would loop): the market set is incomplete; nothing is written")
        seen.add(cursor)
    raise Refused(f"REFUSED: {series} /markets status={status}: {max_pages} pages read and a cursor is still served: "
                  "the market set is incomplete (269 item 3(d): a cursor left is a refusal); nothing is written")


def name_of(market: dict) -> str:
    """The player a market's YES is on: its yes_sub_title as served, stripped (269 item 3(a)), through ALIASES."""
    nm = str(market.get("yes_sub_title") or "").strip()
    return ALIASES.get(nm, nm)


def player_id(tour: str, name: str) -> str:
    """The player's external id under this source: the tour and the name, case-folded (one player per spelling up to
    letter case; addendum 238 item 2(b))."""
    return f"{tour}|{name.casefold()}"


def event_day(market: dict) -> date | None:
    """The event's day: the date in its ticker (269 item 1 K2: "the ticker's date is the event's day"), read by the
    shared matcher's own reader (kalshi_match.ticker_stamp). None when the ticker carries none."""
    from src.ingestion.kalshi_match import ticker_stamp
    return ticker_stamp(market)[0]


def kickoff_utc(day: date) -> datetime:
    """The START_UNREAD fallback (naive UTC) of an event dated `day`: EARLIEST_OFFSET's instant (THE KICKOFF, above)."""
    return datetime(day.year, day.month, day.day) - EARLIEST_OFFSET


# An ISO instant with its offset, as Kalshi serves its times ('2026-11-08T14:00:00Z'): seconds and a fraction optional.
_INSTANT = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:\d{2})")


def read_instant(raw) -> datetime | None:
    """A served time read as naive UTC, or None when it is not a string holding exactly an ISO instant WITH an offset
    ('Z' or +hh:mm / -hh:mm). The same on Python 3.10 and 3.12 (the fraction is cut to microseconds here, never by
    fromisoformat). A naive time names no zone, so it is not read (law 4)."""
    if not isinstance(raw, str):
        return None
    m = _INSTANT.fullmatch(raw.strip())
    if not m:
        return None
    y, mo, d, hh, mi, ss, frac, off = m.groups()
    try:
        t = datetime(int(y), int(mo), int(d), int(hh), int(mi), int(ss or 0), int(((frac or "") + "000000")[:6]))
    except ValueError:
        return None
    if off != "Z":
        sign = 1 if off[0] == "+" else -1
        oh, om = int(off[1:3]), int(off[4:6])
        if oh > 23 or om > 59:
            return None
        t -= sign * timedelta(hours=oh, minutes=om)
    return t


def _served(v) -> bool:
    """A time key served on a market: present with a value that is not JSON null and not a blank string."""
    return v is not None and not (isinstance(v, str) and not v.strip())


def kickoff(markets: list[dict], day: date) -> tuple[datetime | None, str]:
    """(the event's kickoff as naive UTC, its source) or (None, the refusal label), by THE KICKOFF's rule (addendum 288
    item 1, above): occurrence_datetime on every market, the same instant -> that instant, source OCCURRENCE_KEY;
    served on none -> expected_expiration_time by the same rule; served on neither key of any market -> kickoff_utc(day),
    source START_UNREAD. A key served on some markets only, a served value that is no ISO instant with an offset, or
    two different instants: refused under that key's label (KICKOFF_REFUSALS), never the next key."""
    for key in KICKOFF_KEYS:
        differ, one, unread = KICKOFF_REFUSALS[key]
        vals = [m.get(key) for m in markets]
        on = [v for v in vals if _served(v)]
        if not on:
            continue
        if len(on) != len(vals):
            return None, one
        inst = [read_instant(v) for v in on]
        if any(t is None for t in inst):
            return None, unread
        if len(set(inst)) != 1:
            return None, differ
        return inst[0], key
    return kickoff_utc(day), START_UNREAD


# ---------------------------------------------------------------------------------------------------------------------
# THE SERIES' CONTRACT TERMS, BEFORE THE STATUS MAP (269 item 3(c), verbatim: "BEFORE the status map, the series'
# contract_terms_url (served in the listing's keys) is read and the clause on incomplete matches — retirement,
# walkover, suspension — QUOTED on the PR, so the scalar cases are mapped by the venue's own rule and never by
# inference").
#
# THE CLAUSE, QUOTED (ARCHITECT 2026-11-08, addendum 288 item 3). The source: the served receipt's markets (the
# certification receipt's served phase, read 12:29Z on the laptop): rules_secondary ("686 distinct values, one sentence
# common to every market; CONTRACT_TERMS_QUOTE fills from this"), rules_primary (the ruling's own template of it, the
# placeholders <player>, <A>, <B> and <event> as the ruling writes them) and early_close_condition ("on every market").
# contract_terms_url "is the venue's generic "ACHIEVEMENTS.pdf" for both series — the per-market rules are the terms
# that bind, and they are now on the record." Each value below is copied byte for byte from addendum 288 item 3; no
# wording is typed here. THE MEANING the ruling records from it (SETTLED_SCALAR and a retirement) is in MatchStatus's
# docstring (src/db/schema.py). The map below still reads the served result word only.
CONTRACT_TERMS_QUOTE: dict[str, str] = {
    "rules_secondary": ("If the match does not occur (signaled by a ball being played) due to a player injury, walkover, "
                        "forfeiture, or any other cancellation (all before the match starts), the market will resolve "
                        "to a fair price in accordance with the rules. If this match is postponed or delayed, the market "
                        "will remain open and close after the rescheduled match has finished (within two weeks)."),
    "rules_primary": ("If <player> wins the <A> vs <B> professional tennis match in the <event> after a ball has been "
                      "played, then the market resolves to Yes."),
    "early_close_condition": "This market will close and expire after a winner is declared.",
}
CONTRACT_TERMS_SOURCE = ("addendum 288 item 3: the served receipt's rules_secondary (the sentence common to every "
                         "market), rules_primary (the ruling's template) and early_close_condition (every market), "
                         "KXATPMATCH and KXWTAMATCH; contract_terms_url is the venue's generic \"ACHIEVEMENTS.pdf\" "
                         "for both series")
# ---------------------------------------------------------------------------------------------------------------------

# THE STATUS MAP (269 item 3(b)), by the served `result` word, EXACTLY these four and no other; the market's `status`
# word as served must be 'finalized' (269 item 1 K3: the settlement "as served on finalized markets") for a settled
# reading. Every other combination stays SCHEDULED, labelled by status_raw and counted (law 4): an unmapped result word,
# a result key not served, a settled word on a market not 'finalized', the two markets disagreeing, a 'yes' whose
# expiration_value is not its own player's name.
RESULT_YES, RESULT_NO, RESULT_SCALAR, RESULT_NONE = "yes", "no", "scalar", ""
RESULT_WORDS = (RESULT_YES, RESULT_NO, RESULT_SCALAR, RESULT_NONE)
FINALIZED = "finalized"
STATUS_WORDS = ("active", "closed", FINALIZED)          # as served (269 item 1 K3); any other is printed and counted

# Why a settled-looking event stays SCHEDULED (counted; printed by the receipt).
UNMAPPED_RESULT = "a result word outside 'yes' / 'no' / 'scalar' / ''"
RESULT_ABSENT = "no result key served"
NOT_FINALIZED = "settled word on a market not 'finalized'"
DISAGREE = "the two markets' results disagree"
WINNER_MISMATCH = "expiration_value is not the 'yes' market's player"
SCALAR_VALUE_UNREAD = "a 'scalar' settlement whose settlement_value_dollars is not a fraction in [0, 1] on both markets"


@dataclass
class Settlement:
    status: MatchStatus
    status_raw: str                       # the markets' status word(s) as served, e.g. 'finalized' ('active/closed')
    winner: str | None = None             # the winner's name (the 'yes' market's yes_sub_title), FINISHED only
    why: str | None = None                # why a settled-looking event stays SCHEDULED, else None
    served: dict = field(default_factory=dict)   # {ticker: {result, settlement_value_dollars, expiration_value}}


def _word(v) -> str:
    return "none" if v is None else str(v)


def _fraction(v) -> float | None:
    """settlement_value_dollars as served (a decimal string, e.g. "0.3300") read as a fraction in [0, 1], else None."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(str(v).strip())
    except ValueError:
        return None
    return x if 0.0 <= x <= 1.0 else None


def settle(markets: list[dict]) -> Settlement:
    """The event's status from its two markets as served (269 item 3(b)):
      - both '' (or not served as settled): not settled -> SCHEDULED;
      - both 'scalar', both 'finalized', each serving settlement_value_dollars as a fraction in [0, 1] -> SETTLED_SCALAR,
        NO winner, the fraction kept (served); a scalar pair without both fractions -> SCHEDULED, SCALAR_VALUE_UNREAD;
      - one 'yes' and one 'no', both 'finalized', every non-empty expiration_value the 'yes' market's player (compared
        case-folded, addendum 238 item 2(b)) -> FINISHED, the winner = expiration_value's player, the loser the other;
      - anything else -> SCHEDULED, labelled `why`, never a winner (law 4).
    status_raw is the markets' status word as served ('active', 'closed', 'finalized'), two words joined by '/' when
    they differ."""
    words = sorted({_word(m.get("status")) for m in markets})
    raw = "/".join(words)
    results = [m.get("result") if "result" in m else None for m in markets]
    served = {}
    for m in markets:
        r = m.get("result")
        if r not in (None, RESULT_NONE):
            served[str(m.get("ticker"))] = {k: m.get(k) for k in ("result", "settlement_value_dollars",
                                                                  "expiration_value")}
    if any(r is None for r in results):
        return Settlement(MatchStatus.SCHEDULED, raw, why=RESULT_ABSENT, served=served)
    if any(r not in RESULT_WORDS for r in results):
        return Settlement(MatchStatus.SCHEDULED, raw, why=UNMAPPED_RESULT, served=served)
    if all(r == RESULT_NONE for r in results):
        return Settlement(MatchStatus.SCHEDULED, raw)                     # '' -> not settled (269 item 3(b))
    if any(str(m.get("status")) != FINALIZED for m in markets):
        return Settlement(MatchStatus.SCHEDULED, raw, why=NOT_FINALIZED, served=served)
    if all(r == RESULT_SCALAR for r in results):
        # the fraction is the ledger's truth for a scalar settlement: both markets must serve it, or the event stays
        # SCHEDULED, labelled (law 4), never a settled row without its fraction
        if not all(_fraction(m.get("settlement_value_dollars")) is not None for m in markets):
            return Settlement(MatchStatus.SCHEDULED, raw, why=SCALAR_VALUE_UNREAD, served=served)
        return Settlement(MatchStatus.SETTLED_SCALAR, raw, served=served)  # never a winner
    if sorted(results) == [RESULT_NO, RESULT_YES]:
        yes = next(m for m in markets if m.get("result") == RESULT_YES)
        winner = name_of(yes)
        exp = [str(m.get("expiration_value") or "").strip() for m in markets]
        if winner and all(e.casefold() == winner.casefold() for e in exp if e) and any(exp):
            return Settlement(MatchStatus.FINISHED, raw, winner=winner, served=served)
        return Settlement(MatchStatus.SCHEDULED, raw, why=WINNER_MISMATCH, served=served)
    return Settlement(MatchStatus.SCHEDULED, raw, why=DISAGREE, served=served)


@dataclass
class Fixture:
    """One accepted event: its ticker, day, the two players (home = the name that sorts first, case-folded: a tennis
    match has no home side; the order is ours, stable across reads, and reads no title), its settlement, and its
    kickoff (naive UTC) with the kickoff's source (one of KICKOFF_SOURCES; addendum 288 item 1)."""
    event: str
    day: date
    home: str
    away: str
    settlement: Settlement
    markets: list = field(default_factory=list)
    kickoff: datetime | None = None
    kickoff_source: str = START_UNREAD


@dataclass
class Listing:
    fixtures: list = field(default_factory=list)
    refused: Counter = field(default_factory=Counter)     # reason -> events
    refused_events: dict = field(default_factory=dict)    # event -> reason
    pages: dict = field(default_factory=dict)             # status -> pages read
    markets: int = 0
    status_words: Counter = field(default_factory=Counter)
    result_words: Counter = field(default_factory=Counter)
    kickoff_sources: Counter = field(default_factory=Counter)   # KICKOFF_SOURCES word -> fixtures (288 item 1)
    # event -> its two markets as served, for the events refused by the kickoff rule only: never a fixture, read by the
    # certification receipt alone (288 item 2(b): the expiration_value SHAPES are read on every unmapped event)
    kickoff_refused_markets: dict = field(default_factory=dict)


def build(tour: str, markets: list[dict]) -> Listing:
    """The fixtures of one tour from its markets (every status), grouped by event_ticker as served. An event is a
    fixture when its ticker carries a date, it serves exactly two markets naming two different players, and its kickoff
    reads by THE KICKOFF's rule (addendum 288 item 1); otherwise it is refused by its reason, counted, and never a
    fixture (the ambiguity sentinel of 269 item 3(a))."""
    series = SERIES[tour]
    lst = Listing(markets=len(markets))
    by_event: dict[str, dict[str, dict]] = {}
    for m in markets:
        lst.status_words[_word(m.get("status"))] += 1
        lst.result_words[repr(m.get("result")) if "result" in m else "<absent>"] += 1
        ev = str(m.get("event_ticker") or "")
        tk = str(m.get("ticker") or "")
        if not ev.startswith(f"{series}-") or not tk.startswith(f"{series}-"):
            lst.refused[OUTSIDE_SERIES] += 1
            lst.refused_events[ev or tk] = OUTSIDE_SERIES
            continue
        by_event.setdefault(ev, {})[tk] = m           # a ticker read twice: the later read (MARKET_STATUSES order)
    for ev in sorted(by_event):
        mks = list(by_event[ev].values())

        def refuse(why):
            lst.refused[why] += 1
            lst.refused_events[ev] = why
        day = event_day(mks[0])
        if day is None:
            refuse(NO_DATE)
            continue
        if len(mks) != 2:
            refuse(NOT_TWO_MARKETS)
            continue
        names = [name_of(m) for m in mks]
        if not all(names) or names[0].casefold() == names[1].casefold():
            refuse(NOT_TWO_PLAYERS)
            continue
        ko, src = kickoff(mks, day)
        if ko is None:
            refuse(src)
            lst.kickoff_refused_markets[ev] = mks
            continue
        home, away = sorted(names, key=lambda n: (n.casefold(), n))
        lst.kickoff_sources[src] += 1
        lst.fixtures.append(Fixture(ev, day, home, away, settle(mks), mks, kickoff=ko, kickoff_source=src))
    return lst


def in_window(day: date, season: str | None, date_from: str | None, date_to: str | None) -> bool:
    """The event's day inside [date_from, date_to] (ISO dates, inclusive; either may be None) and in `season` (the
    ticker year, int-style) when one is given."""
    if season and str(day.year) != str(season):
        return False
    if date_from and day < date.fromisoformat(date_from):
        return False
    if date_to and day > date.fromisoformat(date_to):
        return False
    return True


class KalshiTennisAdapter(DataAdapter):
    """The DataAdapter for Sport.TENNIS: competitions ATP and WTA, players as teams, matches from the series' events,
    results from their settlement. `get(path, params) -> dict` is the HTTP layer (default KalshiAdapter()._get, public
    market data, no key); a test passes a fake. One read of a series serves every call on the same instance (the
    teams and the matches of one `sync-matches` step read the listing once)."""

    source_name = SOURCE
    supported_sports = frozenset({Sport.TENNIS})

    def __init__(self, get=None):
        if get is None:
            from src.adapters.kalshi import KalshiAdapter
            get = KalshiAdapter()._get
        self._http = get
        self.calls = 0
        self._cache: dict[str, Listing] = {}
        self.window: tuple[str | None, str | None] = (None, None)   # list_teams' scope (set by the sync's caller)
        # THE RE-READ's scope (cli._tennis_sync_matches): when a set, list_matches serves only these events (stored
        # rows already, re-read from the same listing), whatever their day; None (the default) reads the window.
        self.events: set[str] | None = None

    def _get(self, path: str, params: dict) -> dict:
        self.calls += 1
        return self._http(path, params)

    def listing(self, tour: str) -> Listing:
        """Every market of the tour's series under each of MARKET_STATUSES, each read to its last page, built into
        fixtures. Refused (Refused raised) for a code that is not a tour or on any paging refusal."""
        tour = tour.upper()
        if tour not in SERIES:
            raise Refused(f"REFUSED: {tour!r} is not a tennis competition this adapter serves ({', '.join(SERIES)}: "
                          "the two tour series and nothing else, addendum 269 item 1)")
        if tour in self._cache:
            return self._cache[tour]
        markets: list[dict] = []
        pages = {}
        for st in MARKET_STATUSES:
            got, n = read_all(self._get, SERIES[tour], st)
            markets.extend(got)
            pages[st] = n
        lst = build(tour, markets)
        lst.pages = pages
        self._cache[tour] = lst
        return lst

    # -- the contract ---------------------------------------------------------------------------------------------
    def list_competitions(self, sport: Sport) -> list[NormalizedCompetition]:
        if sport != Sport.TENNIS:
            return []
        # type LEAGUE: the season-long tour (the vocabulary's nearest word; a tour is no cup and no international)
        return [NormalizedCompetition(sport=Sport.TENNIS, code=code, name=SERIES_TITLE[code], area="World",
                                      type="LEAGUE", source=SOURCE, source_id=series)
                for code, series in SERIES.items()]

    def list_teams(self, competition_code: str, season: str | None = None) -> list[NormalizedTeam]:
        """The players of the tour's accepted events inside `self.window` and `season` (players as teams)."""
        lst = self.listing(competition_code)
        out: dict[str, NormalizedTeam] = {}
        for fx in lst.fixtures:
            if not in_window(fx.day, season, *self.window):
                continue
            for nm in (fx.home, fx.away):
                pid = player_id(competition_code.upper(), nm)
                out.setdefault(pid, NormalizedTeam(sport=Sport.TENNIS, name=nm, source=SOURCE, source_id=pid))
        return list(out.values())

    def list_matches(self, competition_code: str, season: str | None = None, date_from: str | None = None,
                     date_to: str | None = None) -> list[NormalizedMatch]:
        tour = competition_code.upper()
        lst = self.listing(tour)
        out = []
        for fx in lst.fixtures:
            if self.events is not None:
                if fx.event not in self.events or not in_window(fx.day, season, None, None):
                    continue
            elif not in_window(fx.day, season, date_from, date_to):
                continue
            st = fx.settlement
            res = None
            if st.status == MatchStatus.FINISHED:
                res = Result.HOME if st.winner.casefold() == fx.home.casefold() else Result.AWAY
            # THE SEASON (OPEN, put to the architect): no ruling names a tennis season string; it is the ticker's
            # calendar year, int-style as NBA / NHL. The lane is "ATP and WTA for the 2027 season" and its first PAPER
            # record is on or after 12-28 (269 item 2), so the 2027 tour season's late-December events read as "2026".
            out.append(NormalizedMatch(
                sport=Sport.TENNIS, competition_code=tour, season=str(fx.day.year),
                utc_date=fx.kickoff, status=st.status, status_raw=st.status_raw,      # 288 item 1, re-read every sync
                home_team_source_id=player_id(tour, fx.home), away_team_source_id=player_id(tour, fx.away),
                source=SOURCE, source_id=fx.event,
                full_time_result=res,                # scores stay None: NULL AND LABELLED (269 item 2)
                settlement=st.served or None, kickoff_source=fx.kickoff_source))
        return out

    def get_match_stats(self, match_source_id: str) -> list[NormalizedMatchStats]:
        return []                                   # no stats source (269 item 2)
