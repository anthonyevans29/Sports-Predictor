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

NOT BUILT, PUT TO THE ARCHITECT: 261 item 2(c)'s wiring list (the roadmap's tennis wiring step) names "results from
the chosen results source with retirements and walkovers as their own status". Kalshi serves no retirement or
walkover word on a yes/no settlement (269 item 1 K3: the result words are 'yes' / 'no' / 'scalar' / ''), and the
venue's own rule on incomplete matches waits on the contract-terms quote (269 item 3(c), below), so no such status
exists here. A yes/no settlement is stored FINISHED with full_time_result set; whether that should hold for a match
the venue settled yes/no after a retirement or walkover, given 269 item 2's "the official winner of an incomplete
match" NULL AND LABELLED, is the ruling's question.
"""
from __future__ import annotations

import logging
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

# THE KICKOFF (law 4), OPEN FOR A RULING (P1 on the PR). Time keys ARE served on every KXATPMATCH / KXWTAMATCH market:
# the stage-1 digest (#838 issuecomment-6690719842, K3 "keys served") lists occurrence_datetime, open_time,
# close_time, expected_expiration_time, expiration_time and latest_expiration_time. What is UNREAD is their tennis
# semantics: no record prints their values beside the ticker's date, and the shared matcher's own ruling reads
# occurrence_datetime on a date-only ticker as "an expected expiration" that "places nothing and refuses nothing"
# (addendum 44 item 1, kalshi_match's docstring), not as a start; 269 item 1 K2 says only "Times Z; the ticker's date
# is the event's day". So no served key is read as a start here. A row needs an instant (matches.utc_date), and the
# shared matcher's in-play gate refuses a market once that instant has passed (kalshi_match.IN_PLAY), so the instant
# chosen decides whether an in-play price can ever be stored as a pre-match one. The conservative instant: the FIRST
# instant of the ticker's date anywhere on earth, 00:00 at UTC+14, i.e. the day before at 10:00 UTC. No match dated D
# starts before it, whatever zone the ticker's date is read in, so a stored price is pre-match. THE COST IS LARGE: every
# market of an event dated D is IN_PLAY from D-1 10:00 UTC, and the digest shows a Nov 7 event (KXWTAMATCH-26NOV07...)
# open at ~15:12Z on Nov 6, already past that instant: the capture and the close are close to empty by construction
# (tests/test_tennis_kalshi_wiring.py pins it). The timer ships disabled, so nothing captures until the architect's
# block; the receipt's served phase prints the time keys beside the ticker's date (THE TIMES) so a start field, or
# another instant, can be ruled on that receipt. The row also reads on the coverage page's US Eastern day before D.
EARLIEST_OFFSET = timedelta(hours=14)
KICKOFF_LABEL = "kickoff = 00:00 of the ticker's date at UTC+14 (no served start time read; law 4)"
SCORES_NULL_LABEL = ("score, sets, the retirement's point and an incomplete match's official winner: NULL AND "
                     "LABELLED (addendum 269 item 2)")

# Refusal reasons for an event (counted; never a fixture).
NO_DATE = "no date in the ticker"
NOT_TWO_MARKETS = "the event does not serve exactly two markets"
NOT_TWO_PLAYERS = "the event's markets do not name two players (yes_sub_title)"
OUTSIDE_SERIES = "a ticker outside the series"


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
        out.extend(m for m in data["markets"] if isinstance(m, dict))
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
    """The stored kickoff (naive UTC) of an event dated `day`: EARLIEST_OFFSET's instant (see above)."""
    return datetime(day.year, day.month, day.day) - EARLIEST_OFFSET


# ---------------------------------------------------------------------------------------------------------------------
# THE SERIES' CONTRACT TERMS, BEFORE THE STATUS MAP (269 item 3(c), verbatim: "BEFORE the status map, the series'
# contract_terms_url (served in the listing's keys) is read and the clause on incomplete matches — retirement,
# walkover, suspension — QUOTED on the PR, so the scalar cases are mapped by the venue's own rule and never by
# inference").
#
# TODO-FOR-RECEIPT (OPEN, put to the architect): THE CLAUSE IS NOT QUOTED HERE. No record in the repo holds the text of
# KXATPMATCH's or KXWTAMATCH's contract terms: the stage-1 digest (#838 issuecomment-6690719842) prints neither
# contract_terms_url's value nor the markets' rules_primary / rules_secondary / early_close_condition (it lists them
# among the keys served), and this container cannot reach Kalshi. The source is the series listing's contract_terms_url
# for each series, and the markets' own rules_primary / rules_secondary / early_close_condition; the certification
# receipt's served phase (scripts/tennis_certification_receipt.py) prints them verbatim on the laptop, and the PR quotes
# them from that console. NO WORDING IS INVENTED HERE. Until the clause is quoted, the map below reads no clause: it
# maps only what 269 item 3(b) rules by the served result word ('yes' / 'no' / 'scalar' / ''), it infers nothing about
# retirement, walkover or suspension, and a scalar market is never a winner whatever the clause says.
CONTRACT_TERMS_QUOTE: str | None = None
CONTRACT_TERMS_SOURCE = ("the series listing's contract_terms_url (KXATPMATCH, KXWTAMATCH) and the markets' "
                         "rules_primary / rules_secondary / early_close_condition, printed verbatim by "
                         "scripts/tennis_certification_receipt.py's served phase on the laptop")
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


@dataclass
class Settlement:
    status: MatchStatus
    status_raw: str                       # the markets' status word(s) as served, e.g. 'finalized' ('active/closed')
    winner: str | None = None             # the winner's name (the 'yes' market's yes_sub_title), FINISHED only
    why: str | None = None                # why a settled-looking event stays SCHEDULED, else None
    served: dict = field(default_factory=dict)   # {ticker: {result, settlement_value_dollars, expiration_value}}


def _word(v) -> str:
    return "none" if v is None else str(v)


def settle(markets: list[dict]) -> Settlement:
    """The event's status from its two markets as served (269 item 3(b)):
      - both '' (or not served as settled): not settled -> SCHEDULED;
      - both 'scalar', both 'finalized' -> SETTLED_SCALAR, NO winner, the fraction kept (served);
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
    match has no home side; the order is ours, stable across reads, and reads no title), and its settlement."""
    event: str
    day: date
    home: str
    away: str
    settlement: Settlement
    markets: list = field(default_factory=list)


@dataclass
class Listing:
    fixtures: list = field(default_factory=list)
    refused: Counter = field(default_factory=Counter)     # reason -> events
    refused_events: dict = field(default_factory=dict)    # event -> reason
    pages: dict = field(default_factory=dict)             # status -> pages read
    markets: int = 0
    status_words: Counter = field(default_factory=Counter)
    result_words: Counter = field(default_factory=Counter)


def build(tour: str, markets: list[dict]) -> Listing:
    """The fixtures of one tour from its markets (every status), grouped by event_ticker as served. An event is a
    fixture when its ticker carries a date and it serves exactly two markets naming two different players; otherwise
    it is refused by its reason, counted, and never a fixture (the ambiguity sentinel of 269 item 3(a))."""
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
        home, away = sorted(names, key=lambda n: (n.casefold(), n))
        lst.fixtures.append(Fixture(ev, day, home, away, settle(mks), mks))
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
                utc_date=kickoff_utc(fx.day), status=st.status, status_raw=st.status_raw,
                home_team_source_id=player_id(tour, fx.home), away_team_source_id=player_id(tour, fx.away),
                source=SOURCE, source_id=fx.event,
                full_time_result=res,                # scores stay None: NULL AND LABELLED (269 item 2)
                settlement=st.served or None))
        return out

    def get_match_stats(self, match_source_id: str) -> list[NormalizedMatchStats]:
        return []                                   # no stats source (269 item 2)
