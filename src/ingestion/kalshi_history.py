"""
KALSHI SETTLED-MARKET HISTORY, the ingest (ARCHITECT 2026-10-14 10:01 ET, addendum 67 item 1; K-track data lane,
Issue #519), verbatim in part:

"What it is: a stored record of every settled Kalshi game market in our series, with the last two-sided quote before
kickoff, so the backtests and the older-season tests have a Kalshi close where no book close exists. Read-only against
the exchange (public endpoints, no key); it writes ONE new table and nothing else — no odds snapshot, no close used by
grading, no prediction row is touched; grading keeps reading what it reads today until a later ruling says otherwise."

    python cli.py kalshi-history --series KXMLBGAME [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--dry-run]
                                 [--max-calls N]
    python cli.py kalshi-history place-held --ticker TICKER --match-id N --ruling "<addendum>"
                                 (--backup PATH | --dry-run)      # the ruled re-place, addendum 130 item 2(c)

How it reads, so the receipt can be checked against it:
- The cutoff first (/historical/cutoff, one call), printed. Then both lists of the series, paged by cursor alone (no
  time filter is sent: the probe found max_close_ts does not narrow the historical list): /historical/markets
  (source 'historical', settled before the cutoff) and /markets?status=settled (source 'live'). A list that does not
  reach its end (a page that fails or holds no list, a cursor that comes back, the page guard) is printed, never
  retried (a 429 alone is first asked again, as below, for any call: the cutoff, a page or a candle call), and nothing
  of the run is placed or stored, as for the cap: an event split across the cut would be
  matched on part of its legs. The series' competition must be in the DB, or the run refuses before any call.
- --since / --until keep the markets whose game day falls inside them: the ticker's date (US Eastern, as the matcher
  reads it), else the close_time's UTC date; a market with neither is counted and left out when either is given.
- A market already in the table is counted and skipped: its candles are never fetched twice, and a run resumes where
  the last one stopped by the table itself. The one exception is a held row (the identity hold, below).
- Matching, per event: the event's markets go through the shared matcher (kalshi_match.place: the same fit, the same
  pins, the same refusals) against the stored games of the series' own competition on the event's days, loaded as
  the syncs load them (kalshi_sync.stored_games' span, kalshi_match.day_span); the claims rule is read across the
  events, as one place() call reads it (two markets claiming one side of one game are both refused), and across the
  stored rows of the series: a market the run would write (a new row, or a stored held row whose hold cleared)
  placed on a side a stored row holds under another ticker is refused under the same reason, and the stored row is
  not moved (place_held refuses the same: two settled markets are never stored on one side of one game). A stored
  row that holds a placement is read by its stored (match_id, side), never placed by date again (ARCHITECT
  2026-10-18, addendum 132 item 3(b): "Stored rows enter the claims rule as stored; only the run's new markets and
  the held rows it places are placed by date"; addendum 134 item 3, option (ii): "only a stored row that HAS a
  placement enters the claims rule by its stored (match_id, side); a refused stored row keeps its date claim in the
  across-events rule, as on main"): a placed stored row listed in the run is placed with its event (so the event is
  placed on all its legs), but its date placement is read by nothing. A refused stored row has no stored side: it
  is placed by date with its event and claims there, as main has it, and is never written again (a refusal never
  becomes a placement on a later run). That read of the stored rows covers a market whose ticker carries a clock
  (the identity hold's series; KXMLBGAME of the five), a side a row placed by ruling holds (its notes carry
  RULED_NOTE, "placed by ruling: "), and, on any series, a side a placed stored row listed in range holds (the rows
  main's claims rule read across the events, there by their date). Otherwise a date-only series (NFL, NHL,
  NCAA, the soccer series) is placed as main places it, run by run: a day-off twin stored by one run (NCAA's
  Friday-dated 26OCT16 events) and its own-date event placed on the same sides by a later run that does not list
  the twin both stand; that case is the NCAA date-keyed tiebreak's (addendum 130 item 3(b)). Four refusals of the
  live sync are conditions of an open market and cannot hold for a settled one, so they are not read: in play (every
  settled game has started: `now` is set before any game), no price and the spread guard (a settled market's quote
  is its candles', read below), and the run's window (the window here is --since/--until, applied above). Each event
  is placed alone, so "behind an event out of step" (a rule between open events) never fires; the identity hold
  (below) is this path's own rule for a clock series. Every other refusal is the matcher's own, under its own
  reason. A refused market is stored with match_id and side null and the reason in notes, never guessed, and the
  refusals are listed at the end of the run by reason, as the replay lists them.
- Kickoff for the window: the stored game's kickoff when matched; when unmatched, the ticker's date-and-time when the
  ticker carries a clock (the MLB shape); else no candles are fetched and notes says so. Candles:
  /historical/markets/{ticker}/candlesticks for a historical market, /series/{series}/markets/{ticker}/candlesticks for
  a live one; period_interval=1, start_ts = kickoff - 6h, end_ts = close_time. A market with no close_time, or whose
  window starts at or after its close_time, fetches no candles (notes says so). A candle call the exchange refuses
  for good (a 4xx other than 408 / 429) stores the market with no quote and the status in notes; any other failure
  stores nothing for it (listed; the next run asks again). A 429 is asked again in the run (ARCHITECT 2026-10-17,
  addendum 104 item 2: "on a 429, wait and retry the same call once (2s, then 5s) before counting it failed; one line
  in the receipt "429 retries: N""): after 2 s, then after 5 s, each a call against the cap; a third 429 counts the
  call failed. Nothing else is retried in the run.
- Per market from its candles: last_ts / last_bid / last_ask / last_mid of the last candle at or before kickoff that
  carries both a bid and an ask (a null is never filled, and the mid is the two's mean); candles_6h (candles whose end
  falls in the six hours up to kickoff), candles_two_sided (of those, the ones carrying both), gaps (the minutes of
  those six hours with no candle: 360 less the distinct minutes present), raw_first_candle (the first candle
  returned, whole). A candle carries both when its bid and ask, read by the shape's own keys, are two-sided as ruling
  9 of #286 defines it (ARCHITECT 2026-10-06, "two-sided = 0 < bid <= ask < 1"): the kept files send an empty side
  at size zero, priced 0.00 (a bid) or 1.00 (an ask; 0.00 on two legs) (yes_bid_size_fp / yes_ask_size_fp "0.00" on
  all 400 markets of the kept pages), and an empty side is not a quote. This reading of the ruling here is for the
  architect's read on #521.
- THE IDENTITY HOLD (ARCHITECT 2026-10-18 09:58 ET, addendum 127 item 3(c); it stands, addendum 130 item 2(c)),
  verbatim: "for a clock series, an event whose pair has an earlier-dated event of the same two names that is
  unsettled, or is out of step on its own date, is NOT placed by date; it is stored with match_id null and a reason of
  its own ("identity hold: earlier event <ticker> of the pair unsettled/out of step"), and — the one exception to
  "inserted once" — a HELD row (match_id null with that reason) is re-read by a later run and placed when the hold
  clears. Nothing already placed is ever moved by the ingest." How it is read here:
  - A clock series is read per event, as the matcher reads it (kalshi_match.behind_out_of_step: an event whose
    ticker carries no clock is outside the rule). Of the five series only KXMLBGAME's tickers carry a clock; NFL,
    NHL, NCAA and the soccer series are unchanged. The pair is the matcher's group: the event's two names
    (kalshi_match._names), in either order.
  - Out of step on its own date is the matcher's own rule (addendum 54 item 6), read by
    kalshi_match.behind_out_of_step itself with `now` before every game, so that rule's other half ("its date is
    before the day of the run", an open event past its day) never reads: no game of the pair's two teams on the
    event's date (US Eastern; a row that is not a game is not one), and a numbered event (G1, G2) is never out of
    step itself.
  - Unsettled: an earlier-dated event the exchange lists as open in this run. The two settled lists cannot show it,
    so a run that lists any clock ticker also lists the series' open markets (/markets?status=open, the call the live
    sync makes, KalshiAdapter.open_markets_for_series), paged as the other lists are; they are read for the hold
    only, never placed or stored, and a cut in that list stores nothing, as for the others. An event listed settled
    (in either list, or stored) is settled. An event between close and settlement (status closed) is in no list read,
    so it holds nothing under either half (out of step reads only the events the run knows of), and a later event of
    its pair is placed by date. RULED (addendum 132 item 4(e)): listing the series' closed markets too, for the hold
    only, is its OWN small follow-up PR, not a hold on #598 (Issue #603; the list's status for a closed market is in
    no kept payload).
  - Earlier-dated events are every event of the pair the run knows of: both settled lists whole (not only the
    markets inside --since/--until), the stored rows of the series, and the open list. THE BOUND (ARCHITECT
    2026-10-18 13:55 ET, addendum 132 item 3(c)), verbatim: "an earlier event of the pair binds only when its ticker
    date is within 10 days before the event's date. A series never spans more than that (a seven-game series runs
    nine days); a regular-season rainout in May would otherwise hold every later event of the pair for the season.
    Inside the bound, held rows that the hold never releases are placed by ruling — that is the cost this season;
    #478's 2027 lane (the series-game-number key, with seriesGameNumber stored from now) retires the manual step"
    (HOLD_BOUND_DAYS: 10 days before binds, 11 does not).
  - The hold, like the matcher's "behind" (addendum 55 item 3), is for a market that would otherwise have been placed:
    a market refused for a reason of its own keeps that reason. A held market claims no game (the claims rule reads
    the rest). Its notes carry the ruled reason; no candles are fetched for it (the ticker's clock identifies nothing
    about a game that moved, addendum 127 item 3(a)): they are read when it is placed.
  - The one exception to "inserted once": a stored row with match_id null whose notes carry the hold's reason is read
    again by every run that lists it inside --since/--until. When the run places it (the hold has cleared and the
    matcher places it, on a side no stored row holds), its match_id, side, source, fetched_at and quote are written,
    its candles fetched then on the stored kickoff, and "hold cleared <run time>: placed by the ingest" is appended to
    its notes. The write reads the row and its side again, as place_held does: a row no longer held, or a side another
    row of the series took since the run read the table, is not written. A held row the run holds again, or whose
    hold has cleared but the matcher refuses (a stored row holding its side included), is left exactly as stored. A
    row with a match_id, and a row refused for any other reason, is never read again.
  A held row the hold never releases is placed only by a ruling: `kalshi-history place-held` (place_held below).
- --max-calls (default 300; the probe's whole run was 241): every call counts. At the cap the run stops cleanly: what
  it holds is stored (unless --dry-run), and it prints where it stopped (the list and its cursor, or the market whose
  candles it would have fetched next).
- --dry-run makes every read, prints what would be stored, and writes nothing (the table need not exist). A run
  without it writes only when migrate_kalshi_settled_markets.py has run: the table AND that script's migration marker
  (MIGRATION_MARKER below; an init_db()-created table does not count).

The payloads' keys (law 1: "read each by its own keys from the kept payloads of 2026-10-14 under logs/ (law 1:
enumerate the keys from those files, not from memory)"): KEYS below is the one place they are named, enumerated from
the five kept files (2026-10-14 11:54Z, branch laptop/kalshi-payloads-1014, addendum 68 item 5), trimmed into
tests/fixtures/kalshi_history/, where the tests check every key against them. Every key of the architect's receipt
(addendum 66 item 6: "the historical endpoint's candles carry yes_bid.close / yes_ask.close / volume / open_interest
(no _dollars suffix); the live series endpoint's carry close_dollars / volume_fp / open_interest_fp") and of the
probe's reader (scripts/kalshi_history_probe.py: markets / cursor, candlesticks, end_period_ts, ticker / event_ticker /
close_time / result) is the files' own; settled_time's, which the receipt did not name, is settlement_ts (on every
market of both kept pages). As the files send them: a price is a dollar string ("0.4500"); a time is ISO with a
fraction of 0 to 6 digits ("…24.64689Z"); end_period_ts is epoch seconds; a zero-volume minute of the historical shape
carries price.close / open / high / low / mean null (price.previous set) with its bid and ask present; and a tied NFL
game settles both legs as result "scalar" (0.50), stored as kalshi_result null with the result as read in notes.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import requests

from src.ingestion import kalshi_match as km
from src.walters.k_receipt import leg_two_sided

TABLE = "kalshi_settled_markets"
# The migration marker (Codex P2 on #521; the convention of ncaa_cfbd.MIGRATION_MARKER, Codex on #333).
# KalshiSettledMarket is mapped in Base.metadata, so ANY init_db() (create_all, run by many scheduled commands) creates
# an empty kalshi_settled_markets; the table's existence does not prove the backed-up migration ran.
# migrate_kalshi_settled_markets.py, and nothing else, creates this one-row table by Core SQL (deliberately NOT mapped,
# so create_all can never make it), and a run without --dry-run writes only when both exist.
MIGRATION_MARKER = "kalshi_settled_markets_migration"
MAX_CALLS = 300                  # the ruling's default
WINDOW_H = 6                     # "start_ts = kickoff − 6h"
PAGE_LIMIT = 200                 # the adapter's own page size (KalshiAdapter.open_markets_for_series)
MAX_PAGES = 5000                 # a guard against a cursor that never ends; reaching it is printed, never silent
EPOCH = datetime(1970, 1, 1)     # `now` for the matcher: before every game, so its in-play refusal never reads

# The one place the payloads' keys are named, as the kept files of 2026-10-14 name them (the docstring).
KEYS = {
    "cutoff": "market_settled_ts",
    "list": "markets", "cursor": "cursor",
    "ticker": "ticker", "event": "event_ticker", "yes_sub_title": "yes_sub_title", "result": "result",
    "close_time": "close_time", "settled_time": "settlement_ts",
    "candles": "candlesticks", "end": "end_period_ts",
    # (the bid's parent, the ask's parent, the leaf) per candle shape; each shape is read by its own keys only
    "historical": ("yes_bid", "yes_ask", "close"),
    "live": ("yes_bid", "yes_ask", "close_dollars"),
}
SOURCES = (("historical", "historical/markets", {}), ("live", "markets", {"status": "settled"}))
# The identity hold's list (addendum 127 item 3(c), "unsettled"): the series' open markets, the live sync's own call
# (KalshiAdapter.open_markets_for_series: /markets, status "open"). Read only by a run that lists a clock ticker;
# never placed or stored.
OPEN_SOURCE = ("open", "markets", {"status": "open"})

# The identity hold's reason, as ruled (addendum 127 item 3(c)): "identity hold: earlier event <ticker> of the pair
# unsettled/out of step". A held row is match_id null with this reason in its notes (is_held).
HOLD_NOTE = "identity hold: earlier event {event} of the pair {why}"
HOLD_UNSETTLED, HOLD_OUT_OF_STEP = "unsettled", "out of step"
_HOLD_RX = re.compile(r"(?:^|; )identity hold: earlier event (\S+) of the pair (unsettled|out of step)(?=;|$)")
HOLD_NO_CANDLES = "no candles fetched: identity hold (its candles are read when it is placed)"
# THE BOUND ON "EARLIER-DATED" (ARCHITECT 2026-10-18 13:55 ET, addendum 132 item 3(c)): "an earlier event of the pair
# binds only when its ticker date is within 10 days before the event's date" (0 < days <= 10 binds; 11 does not)
HOLD_BOUND_DAYS = 10
HOLD_MARK = "  ⏸ "                                       # a held event's console line
# what placing a stored held row writes (the one exception to "inserted once"); nothing else of the row moves
REPLACE_COLS = ("match_id", "side", "source", "fetched_at", "last_ts", "last_bid", "last_ask", "last_mid", "candles_6h",
                "candles_two_sided", "gaps", "raw_first_candle", "notes")
REFUSED_NOTE = "refused by the matcher: "
# what place_held appends to a row it places (addendum 130 item 2(c)); the claims rule reads it on a date-only series
RULED_NOTE = "placed by ruling: "


_FRACTION = re.compile(r"\.(\d+)")


def migrated(rs) -> bool:
    """True only when migrate_kalshi_settled_markets.py ran: the table exists AND the marker table that script alone
    writes holds its row. An init_db()-created table without the marker is NOT migrated."""
    from sqlalchemy import inspect, text
    try:
        ins = inspect(rs.get_bind())
        if not (ins.has_table(TABLE) and ins.has_table(MIGRATION_MARKER)):
            return False
        return bool(rs.execute(text(f"SELECT COUNT(*) FROM {MIGRATION_MARKER}")).scalar())
    except Exception:  # noqa: BLE001 - an unreadable marker is not a migration
        return False


class Capped(Exception):
    """The run reached --max-calls."""


class ListCut(Exception):
    """A list did not reach its end (a page failed or held no list, the cursor came back, the page guard): nothing of
    it is placed or stored, as for the cap (an event split across the cut would be matched on part of its legs)."""


def parse_ts(v) -> datetime | None:
    """An ISO time (Z or offset) or epoch seconds -> naive UTC; None when it is neither. The fraction is read to six
    digits on every Python the project runs (3.10's fromisoformat takes only three or six; the kept files send four
    and five too, "…24.64689Z")."""
    try:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return datetime.fromtimestamp(v, tz=timezone.utc).replace(tzinfo=None)
        if isinstance(v, str) and v.strip():
            iso = v.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(_FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], iso, count=1))
            return (dt.astimezone(timezone.utc) if dt.tzinfo else dt).replace(tzinfo=None)
    except (ValueError, OverflowError, OSError):     # unreadable (e.g. a millisecond epoch): None, never a crash
        return None
    return None


def _price(v) -> float | None:
    """A price as the exchange sends it (a number or a numeric string, in dollars) -> float in 0..1, else None.
    A null stays null: never filled."""
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if 0.0 <= x <= 1.0 else None


def bid_ask(candle: dict, shape: str) -> tuple[float | None, float | None]:
    """(bid, ask) of one candle, read by its shape's own keys (no key of the other shape is ever read)."""
    pb, pa, leaf = KEYS[shape]
    b, a = candle.get(pb), candle.get(pa)
    return (_price(b.get(leaf)) if isinstance(b, dict) else None,
            _price(a.get(leaf)) if isinstance(a, dict) else None)


def two_sided(bid: float | None, ask: float | None) -> bool:
    """Ruling 9 of #286 (ARCHITECT 2026-10-06): "two-sided = 0 < bid <= ask < 1" (k_receipt.leg_two_sided). A 0.00
    bid, or a 1.00 or 0.00 ask, is an empty side, as the kept files send it."""
    return leg_two_sided(bid, ask)


def window_stats(candles: list, kickoff: datetime, shape: str) -> dict:
    """The row's quote and counts from one market's candles (the docstring's list)."""
    cs = [c for c in candles if isinstance(c, dict)]
    lo = kickoff - timedelta(hours=WINDOW_H)
    out = {"last_ts": None, "last_bid": None, "last_ask": None, "last_mid": None, "candles_6h": 0,
           "candles_two_sided": 0, "gaps": None, "raw_first_candle": cs[0] if cs else None}
    minutes, last = set(), None
    for c in cs:
        end = parse_ts(c.get(KEYS["end"]))
        if end is None or end > kickoff:
            continue
        bid, ask = bid_ask(c, shape)
        two = two_sided(bid, ask)
        if two and (last is None or end > last[0]):
            last = (end, bid, ask)
        if end > lo:
            out["candles_6h"] += 1
            out["candles_two_sided"] += two
            minutes.add(end.replace(second=0, microsecond=0))
    out["gaps"] = WINDOW_H * 60 - len(minutes)
    if last:
        out.update(last_ts=last[0], last_bid=last[1], last_ask=last[2], last_mid=round((last[1] + last[2]) / 2, 6))
    return out


#: Addendum 104 item 2: the waits before the same call is asked again after a 429 (2 s, then 5 s).
RETRY_429_WAITS = (2, 5)
_wait = time.sleep                                         # the tests replace it; the run waits for real


class Calls:
    """Every call to the exchange, counted against the cap; a failed call is recorded. A 429 alone is asked again
    (RETRY_429_WAITS), each retry a call against the cap and counted in `retries_429`; nothing else is retried."""

    def __init__(self, adapter, cap: int):
        self.adapter, self.cap = adapter, cap
        self.made = 0
        self.retries_429 = 0
        self.failed: list[str] = []

    def get(self, path: str, params: dict | None = None):
        """(answer, None) or (None, why). Raises Capped before a call past the cap. A retry is never made past
        the cap: a 429 that meets the cap counts the call failed (the next run asks again)."""
        if self.made >= self.cap:
            raise Capped()
        waits = list(RETRY_429_WAITS)
        while True:
            self.made += 1
            try:
                data = self.adapter._get(path, params)
            except requests.HTTPError as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status == 429 and waits and self.made < self.cap:
                    self.retries_429 += 1
                    _wait(waits.pop(0))
                    continue
                why = f"status {status}"
            except Exception as e:  # noqa: BLE001 - a call that fails is recorded and the run goes on without it
                why = f"{type(e).__name__}: {e}"
            else:
                if isinstance(data, dict):
                    return data, None
                why = "an answer that is not an object"
            break
        self.failed.append(f"{path} {json.dumps(params or {}, sort_keys=True)}: {why}")
        return None, why


def competition_for(series: str, adapter) -> tuple[str | None, bool]:
    """(the series' own competition, whether it is a soccer series with a Tie leg). The one map the syncs read
    (kalshi_sync.series_competition), and the soccer path's own (KalshiAdapter.SOCCER_GAME_SERIES)."""
    from src.ingestion.kalshi_sync import series_competition
    comp = series_competition(series)
    if comp is None:
        rev = [c for c, s in adapter.SOCCER_GAME_SERIES.items() if s == series]
        comp = rev[0] if len(rev) == 1 else None
    return comp, comp is not None and comp in adapter.SOCCER_GAME_SERIES


def game_day(m: dict) -> date | None:
    """The market's game day: the ticker's date (US Eastern), else its close_time's UTC date."""
    d, _ = km.ticker_stamp(m)
    if d is not None:
        return d
    ct = parse_ts(m.get(KEYS["close_time"]))
    return ct.date() if ct else None


def _refused_for_good(why: str | None) -> bool:
    """A candle call the exchange refused for good: an HTTP 4xx other than 408 and 429. Its market is stored with a
    null quote and the status in notes, so the run never asks it again; a transport error, a 5xx, a 408, a 429 or a
    200 with no list is not stored, and the next run asks again (a 429 is first asked again in this run: Calls)."""
    m = re.match(r"status (\d{3})$", why or "")
    return bool(m) and 400 <= int(m.group(1)) < 500 and int(m.group(1)) not in (408, 429)


def _settled_price(_m) -> float:
    """The matcher's price reader for a settled market: never None, so its no-price refusal is not read (a settled
    market's quote is its candles', read by window_stats)."""
    return 0.0


@dataclass
class Run:
    series: str
    dry_run: bool
    cutoff: str | None = None
    listed: Counter = field(default_factory=Counter)        # by source
    out_of_range: int = 0
    no_day: int = 0
    already: int = 0
    rows: list = field(default_factory=list)                 # what is (or would be) stored
    refused: Counter = field(default_factory=Counter)        # by the matcher's reason
    refused_lines: list = field(default_factory=list)
    candle_calls: int = 0
    candle_failed: list = field(default_factory=list)        # (ticker, why): nothing stored for them
    no_candles: Counter = field(default_factory=Counter)     # why no candles were fetched
    stopped: str = ""
    list_notes: list = field(default_factory=list)
    no_ticker: int = 0
    duplicates: int = 0
    candle_refused: int = 0                                  # 4xx answers: stored with a null quote
    # the identity hold (addendum 127 item 3(c))
    open_read: bool = False                                  # the open list was read (a clock ticker was listed)
    hold_lines: list = field(default_factory=list)           # one per held event
    held_new: int = 0                                        # new rows kept with match_id null under the hold
    held_still: int = 0                                      # stored held rows the run holds again (left as stored)
    held_refused: list = field(default_factory=list)         # stored held rows: hold cleared, the matcher refuses
    replaced: list = field(default_factory=list)             # stored held rows placed (the one exception)
    replace_skipped: list = field(default_factory=list)      # (ticker, why): a held row not written at the write
    claimed_by: dict = field(default_factory=dict)           # ticker -> ("<match> <side>", the stored rows holding it)


def list_source(calls: Calls, run: Run, source: str, path: str, params: dict, series: str) -> list[dict]:
    """Every market of one list, paged to its end by cursor. The cap stops the run (Capped), naming the list and the
    cursor it stopped at; a page that fails or holds no list, a cursor that comes back, and the page guard end it short
    (ListCut), printed. Never retried, but for a 429 (Calls). What was read is counted either way."""
    markets, cursor, seen = [], None, set()
    try:
        for n in range(MAX_PAGES):
            p = {"series_ticker": series, **params, "limit": PAGE_LIMIT, **({"cursor": cursor} if cursor else {})}
            try:
                data, why = calls.get(path, p)
            except Capped:
                run.stopped = (f"the cap ({calls.cap} calls) while listing {source} ({path}), before page {n + 1}"
                               f"{f' at cursor {cursor}' if cursor else ''}")
                raise
            if data is None:
                raise ListCut(f"{source}: page {n + 1} of {path} failed ({why})")
            page = data.get(KEYS["list"])
            if not isinstance(page, list):
                raise ListCut(f"{source}: page {n + 1} of {path} holds no '{KEYS['list']}' list")
            markets.extend(m for m in page if isinstance(m, dict))
            cursor = data.get(KEYS["cursor"])
            if not cursor:
                return markets
            if cursor in seen:
                raise ListCut(f"{source}: the cursor {cursor!r} came back on page {n + 1} of {path}")
            seen.add(cursor)
        raise ListCut(f"{source}: {MAX_PAGES} pages read and the cursor goes on")
    finally:
        run.listed[source] += len(markets)


def is_held(match_id, notes) -> bool:
    """A HELD row (addendum 127 item 3(c)): match_id null with the identity hold's reason in its notes."""
    return match_id is None and bool(_HOLD_RX.search(notes or ""))


def _sorted_games(games: list) -> tuple[list, list]:
    gs = sorted((g for g in games if g.utc_date), key=lambda g: g.utc_date)
    return gs, [g.utc_date for g in gs]


def _games_of(gs: list, keys: list, mks: list[dict]) -> list:
    """The stored games of the events' days (kalshi_match.day_span), from games sorted by kickoff."""
    import bisect
    span = km.day_span(mks)
    return gs[bisect.bisect_left(keys, span[0]):bisect.bisect_right(keys, span[1])] if span else []


def _event_key(mks: list[dict], is_tie) -> tuple | None:
    """(the pair, the ticker's date) of one event as the matcher's out-of-step rule reads it (behind_out_of_step: its
    two names in either order, its ticker's US Eastern date). None outside that rule: not two names, no date, or no
    clock in the ticker (a date-only series)."""
    names = km._names(mks, mks[0], is_tie)
    day, clock = km.ticker_stamp(mks[0])
    if len(names) != 2 or day is None or clock is None:
        return None
    return frozenset(n.lower() for n in names), day


def identity_holds(targets, known: dict, unsettled: set, games: list, is_tie=None) -> dict:
    """THE IDENTITY HOLD (addendum 127 item 3(c), the module docstring): {event: (earlier event, why, words)} for each
    event of `targets` (event tickers) that has an earlier-dated event of the same two names, among `known` ({event:
    its markets}: the settled lists whole, the stored rows, the open list), dated within HOLD_BOUND_DAYS before it
    (addendum 132 item 3(c)), that is unsettled (in `unsettled`, events the exchange lists open) or out of step on its
    own date. The earliest such event is named. Out of step is the matcher's own rule, read by
    kalshi_match.behind_out_of_step with `now` before every game: an earlier event E0 is out of step exactly when
    behind_out_of_step marks a later event of its pair behind it in a run of the two alone.
    No network and no database of its own: `games` is the stored games of the earlier events' days, or a loader
    called once with the earlier events' markets (kalshi_sync.stored_games' span)."""
    is_tie = is_tie or (lambda m: False)
    info = {ev: _event_key(mks, is_tie) for ev, mks in known.items() if mks}
    by_pair: dict[frozenset, list] = {}
    for ev, inf in info.items():
        if inf:
            by_pair.setdefault(inf[0], []).append((inf[1], ev))
    for evs in by_pair.values():
        evs.sort()
    if callable(games):          # a loader: the stored games of the earlier events' days only, read once
        last = {}
        for ev in targets:
            if info.get(ev):
                last[info[ev][0]] = max(last.get(info[ev][0], info[ev][1]), info[ev][1])
        games = games([m for pair, d in last.items() for d0, e0 in by_pair[pair] if d0 < d for m in known[e0]])
    gs, keys = _sorted_games(games)
    words: dict[str, str | None] = {}

    def out_of_step(e0, later):
        """The matcher's words for why e0 is out of step, or None. `later` is any later-dated event of its pair: it
        is marked behind e0 when e0 is out of step, whatever its own state (the earliest event out of step names)."""
        if e0 not in words:
            line = km.behind_out_of_step({e0: known[e0], later: known[later]}, _games_of(gs, keys, known[e0]),
                                         now=EPOCH, is_tie=is_tie, implied_prob=_settled_price).get(later)
            words[e0] = line.split(", out of step: ", 1)[1] if line else None
        return words[e0]

    held = {}
    for ev in targets:
        inf = info.get(ev)
        if not inf:
            continue
        pair, day = inf
        for d0, e0 in by_pair.get(pair, []):
            if d0 >= day:
                break
            if (day - d0).days > HOLD_BOUND_DAYS:
                continue                 # more than 10 days before: it binds nothing (addendum 132 item 3(c))
            if e0 in unsettled:
                held[ev] = (e0, HOLD_UNSETTLED, "the exchange lists it open")
                break
            w = out_of_step(e0, ev)
            if w:
                held[ev] = (e0, HOLD_OUT_OF_STEP, w)
                break
    return held


def place_events(markets: list[dict], games: list, is_tie, holds: dict | None = None,
                 stored: frozenset = frozenset()) -> tuple[dict, dict, list]:
    """{ticker: (game id, kickoff, side)} placed, {ticker: reason} refused, the matcher's lines. Each event is placed
    alone, on the stored games of its own days (kalshi_match.day_span, as kalshi_sync.stored_games loads them).
    `holds` ({event: (earlier event, why, words)}, identity_holds): an event held there keeps no placement: each market
    of it that the matcher placed is refused under the hold's reason, before the claims rule reads (a market the
    matcher refused keeps its own reason, as for "behind", addendum 55 item 3); its line is in the lines.
    `stored` (the tickers of stored rows that hold a placement; a held or refused stored row has none): placed with
    their event, so the event is placed on all its legs, but never placed by date themselves (ARCHITECT 2026-10-18,
    addendum 132 item 3(b); addendum 134 item 3, option (ii)): they are left out of `placed` and of the claims rule
    here, and run_history reads them by their stored (match_id, side). A refused stored row is placed by date and
    claims here, as on main; run_history never writes it again."""
    holds = holds or {}
    by_event: dict[str, list[dict]] = {}
    for m in markets:
        by_event.setdefault(km.event_of(m), []).append(m)
    gs, keys = _sorted_games(games)
    placed, why, lines = {}, {}, []
    for ev, mks in by_event.items():
        day_games = _games_of(gs, keys, mks)
        res = km.place(mks, day_games, now=EPOCH, lo=datetime.min, hi=datetime.max, is_tie=is_tie,
                       implied_prob=_settled_price)
        by_id = {g.id: g for g in day_games}
        held_here = []
        for (mid, side), mk in res.placed.items():
            if ev in holds:
                held_here.append(mk.get(KEYS["ticker"]))
                continue
            if mk.get(KEYS["ticker"]) not in stored:        # a placed stored row is read as stored (132 3(b), 134 3)
                placed[mk.get(KEYS["ticker"])] = (mid, by_id[mid].utc_date, side)
        why.update(res.why)
        lines.extend(res.lines)
        if held_here:
            e0, w, words = holds[ev]
            for t in held_here:
                why[t] = HOLD_NOTE.format(event=e0, why=w)
            lines.append(f"{HOLD_MARK}{ev}: {HOLD_NOTE.format(event=e0, why=w)} ({words}); held, not placed by date: "
                         f"{', '.join(sorted(held_here))}")
    # the matcher's claims rule, across events as one place() call reads it: two markets that claim one side of one
    # game are both refused (kalshi_match: "two markets claim one side of one game"); placing each event alone keeps
    # only "behind" (a rule between open events) from reading
    claims: dict[tuple, list[str]] = {}
    for t, (mid, _, side) in placed.items():
        claims.setdefault((mid, side), []).append(t)
    for (mid, side), ts in claims.items():
        if len(ts) > 1:
            for t in ts:
                del placed[t]
                why[t] = km.TWO_CLAIMS
            lines.append(f"  ✗ match {mid} {side}: {len(ts)} markets of {len({km.event_of({'ticker': t}) for t in ts})} "
                         f"events claim it ({', '.join(sorted(ts))}): all refused")
    return placed, why, lines


def _window_problem(kickoff: datetime | None, close_time: datetime | None) -> str | None:
    """Why no candles are fetched for a market with this kickoff, or None."""
    if kickoff is None:
        return "no candles fetched: unmatched and the ticker carries no clock"
    if close_time is None:
        return "no candles fetched: the market carries no close_time"
    if kickoff - timedelta(hours=WINDOW_H) >= close_time:
        return "no candles fetched: the window (kickoff - 6h) starts at or after close_time"
    return None


def candle_call(series: str, source: str, ticker: str, kickoff: datetime, close_time: datetime) -> tuple[str, dict]:
    """(path, params) of one market's candle call: its source's endpoint, kickoff - 6h to close_time, one minute."""
    path = (f"historical/markets/{ticker}/candlesticks" if source == "historical"
            else f"series/{series}/markets/{ticker}/candlesticks")
    return path, {"start_ts": int((kickoff - timedelta(hours=WINDOW_H)).replace(tzinfo=timezone.utc).timestamp()),
                  "end_ts": int(close_time.replace(tzinfo=timezone.utc).timestamp()), "period_interval": 1}


def _new_row(series: str, source: str, m: dict, fetched_at: datetime, placed: dict, why: dict, run: "Run") -> tuple:
    """(row, notes, kickoff or None) for one market before its candles."""
    ticker = m.get(KEYS["ticker"])
    mid, ko, side = placed.get(ticker, (None, None, None))
    row = {"ticker": ticker, "event_ticker": m.get(KEYS["event"]), "series": series, "side": side, "match_id": mid,
           "yes_sub_title": m.get(KEYS["yes_sub_title"]), "kalshi_result": None,
           "close_time": parse_ts(m.get(KEYS["close_time"])),
           "settled_time": parse_ts(m.get(KEYS["settled_time"])),
           "source": source, "fetched_at": fetched_at, "last_ts": None, "last_bid": None, "last_ask": None,
           "last_mid": None, "candles_6h": None, "candles_two_sided": None, "gaps": None, "raw_first_candle": None}
    notes = []
    res = m.get(KEYS["result"])
    if res in ("yes", "no"):
        row["kalshi_result"] = res
    elif res not in (None, ""):
        notes.append(f"result as read: {res!r}")
    held = mid is None and bool(_HOLD_RX.search(why.get(ticker) or ""))
    if held:
        notes.append(why[ticker])                    # the hold's own reason (addendum 127 item 3(c)), not the matcher's
    elif mid is None:
        notes.append(f"{REFUSED_NOTE}{why.get(ticker) or 'not placed'}")
    kickoff = ko
    if kickoff is None and not held:
        _, kickoff = km.ticker_stamp(m)
    nok = HOLD_NO_CANDLES if held else _window_problem(kickoff, row["close_time"])
    if nok:
        run.no_candles[nok] += 1
        notes.append(nok)
        kickoff = None
    return row, notes, kickoff


def run_history(series: str, *, since: date | None = None, until: date | None = None, dry_run: bool = False,
                max_calls: int = MAX_CALLS, adapter=None, echo=print, now: datetime | None = None) -> Run:
    """The ingest (the module docstring), in four steps: the lists (network), the matching (a database read), the
    candles (network), the insert (this table only; never under --dry-run). Prints its receipt through `echo`."""
    from sqlalchemy import inspect, select

    from src.adapters.kalshi import KalshiAdapter
    from src.db.database import session_scope
    from src.db.schema import Competition, KalshiSettledMarket
    from src.ingestion.kalshi_sync import stored_games
    from src.timeutil import utc_now_naive
    from src.walters.venue_quote_age import readonly_session

    adapter = adapter or KalshiAdapter()
    run = Run(series=series, dry_run=dry_run)
    fetched_at = now or utc_now_naive()
    comp_code, soccer = competition_for(series, adapter)
    if comp_code is None:
        raise ValueError(f"REFUSED: {series} is not a series the syncs read (venue.KALSHI_SERIES_BY_COMPETITION, "
                         "KalshiAdapter.SOCCER_GAME_SERIES): nothing is listed")
    with readonly_session() as rs:
        has_table = inspect(rs.get_bind()).has_table(TABLE)
        ready = migrated(rs)
        comp_id = rs.execute(select(Competition.id).where(Competition.code == comp_code)).scalar_one_or_none()
    if comp_id is None:                                       # as the syncs answer: nothing is listed or stored
        raise ValueError(f"REFUSED: competition {comp_code} (of {series}) is not in the DB: sync-competitions, "
                         "sync-teams and sync-matches first; nothing is listed or stored")
    if not ready and not dry_run:
        raise ValueError(f"REFUSED: {TABLE} is not migrated (no migration marker {MIGRATION_MARKER}; an "
                         "init_db()-created table does not count): take the daily .backup, then run "
                         "`python migrate_kalshi_settled_markets.py`; --dry-run reads without it")
    is_tie = adapter.is_tie_market if soccer else None
    calls = Calls(adapter, max_calls)
    echo(f"kalshi-history {series} ({comp_code}{', three legs' if soccer else ''}) · "
         f"{'DRY RUN: nothing is written' if dry_run else f'writes {TABLE} only'} · max calls {max_calls}")

    # 1. the cutoff and both lists (network); the open list too when a clock ticker is listed (the identity hold)
    listed: list[tuple[str, dict]] = []
    opened: list[dict] = []
    try:
        cut, cwhy = calls.get("historical/cutoff")
        run.cutoff = cut.get(KEYS["cutoff"]) if cut else None
        echo(f"  cutoff {KEYS['cutoff']}: {run.cutoff or f'not read ({cwhy})'}")
        for source, path, params in SOURCES:
            listed += [(source, m) for m in list_source(calls, run, source, path, params, series)]
        if any(km.ticker_stamp(m)[1] is not None for _, m in listed):
            run.open_read = True
            opened = list_source(calls, run, *OPEN_SOURCE, series)
    except Capped:
        # a list cut short is never half-read: an event split across the cut would be matched on part of its legs
        listed, opened = [], []
        run.stopped += "; nothing is placed or stored from a list cut short (a larger --max-calls lists it whole)"
    except ListCut as e:
        listed, opened = [], []
        run.list_notes.append(f"{e}: the list stops here, and nothing is placed or stored from a list that did not "
                              "reach its end (the next run lists it whole)")

    # 2. the matching: every listed market in range, stored or not, so an event is always placed on all its legs
    uniq, in_range, seen = [], [], set()
    for source, m in listed:
        t = m.get(KEYS["ticker"])
        if not t:
            run.no_ticker += 1
            continue
        if t in seen:
            run.duplicates += 1
            continue
        seen.add(t)
        uniq.append(m)
        day = game_day(m)
        if (since or until) and day is None:
            run.no_day += 1
            continue
        if (since and day < since) or (until and day > until):
            run.out_of_range += 1
            continue
        in_range.append((source, m))
    stored: set = set()
    held_stored: dict = {}                                   # ticker -> notes of a stored HELD row (is_held)
    placed, why = {}, {}
    if in_range:
        with readonly_session() as rs:
            mine = []
            if has_table:
                K = KalshiSettledMarket
                stored = set(rs.execute(select(K.ticker)).scalars())
                mine = rs.execute(select(K.ticker, K.event_ticker, K.yes_sub_title, K.match_id, K.notes, K.side)
                                  .where(K.series == series)).all()
            held_stored = {t: notes for t, _, _, mid, notes, _ in mine if is_held(mid, notes)}
            holds = {}
            targets = {km.event_of(m) for _, m in in_range if km.ticker_stamp(m)[1] is not None}
            if targets:
                # every event of the series the run knows of: both settled lists whole (not only --since/--until),
                # the stored rows, and the open list (unsettled: listed open, and in neither settled list nor stored)
                known: dict[str, list[dict]] = {}
                settled_evs = set()
                for m in uniq:
                    known.setdefault(km.event_of(m), []).append(m)
                    settled_evs.add(km.event_of(m))
                for t, ev, yst, _, _, _ in mine:
                    if t not in seen:
                        ev = ev or km.event_of({"ticker": t})
                        known.setdefault(ev, []).append({"ticker": t, "event_ticker": ev, "yes_sub_title": yst})
                        settled_evs.add(ev)
                open_evs = set()
                for m in opened:
                    t = m.get(KEYS["ticker"])
                    if t and t not in seen and t not in stored and km.event_of(m) not in settled_evs:
                        known.setdefault(km.event_of(m), []).append(m)
                        open_evs.add(km.event_of(m))
                holds = identity_holds(targets, known, open_evs,
                                       lambda mks: stored_games(rs, [comp_id], mks), is_tie)
            games = stored_games(rs, [comp_id], [m for _, m in in_range])
            # a stored row listed in range that HAS a placement enters the claims rule as stored, never placed by date
            # (addendum 132 item 3(b), option (ii) by addendum 134 item 3); a refused or held stored row has no stored
            # side and keeps its date claim in the across-events rule, as on main
            with_side = {t for t, _, _, mid, _, _ in mine if mid is not None}
            listed = {m.get(KEYS["ticker"]) for _, m in in_range} & with_side
            placed, why, lines = place_events([m for _, m in in_range], games, is_tie, holds, frozenset(listed))
            # the claims rule read across the stored rows too, each by its stored (match_id, side): a market this run
            # would write (a new row, or a stored held row whose hold cleared) placed on a side a stored row of the
            # series holds under another ticker is refused, under the matcher's reason, and the stored row is not moved
            # (place_held refuses the same: two settled markets are never stored on one side of one game). Its scope: a
            # market whose ticker carries a clock (the identity hold's series), a side a row placed by ruling holds
            # (RULED_NOTE), or a side a placed stored row listed in range holds (the rows main's claims rule read across
            # the events, there by their date). A date-only series' other stored rows are read as main reads them: a
            # day-off twin across runs is the NCAA tiebreak's (addendum 130 item 3(b))
            taken: dict[tuple, set] = {}
            ruled = set()
            for t, _, _, mid, notes, side in mine:
                if mid is not None:
                    taken.setdefault((mid, side), set()).add(t)
                    if RULED_NOTE in (notes or ""):
                        ruled.add(t)
            clock = {m.get(KEYS["ticker"]) for _, m in in_range if km.ticker_stamp(m)[1] is not None}
            for t, (mid, _, side) in list(placed.items()):
                others = taken.get((mid, side), set()) - {t}
                if others and (t not in stored or t in held_stored) and (t in clock or others & (ruled | listed)):
                    del placed[t]
                    why[t] = km.TWO_CLAIMS
                    run.claimed_by[t] = (f"{mid} {side}", sorted(others))
                    lines.append(f"  ✗ match {mid} {side}: stored on {', '.join(sorted(others))} (nothing already "
                                 f"placed is moved); {t} claims it too: refused")
            run.refused_lines = [ln for ln in lines if not ln.startswith(HOLD_MARK)]
            run.hold_lines = [ln for ln in lines if ln.startswith(HOLD_MARK)]

    # 3. the candles (network), market by market, for the ones not yet stored, and for a stored HELD row the run
    # places (the one exception to "inserted once", addendum 127 item 3(c)); every other stored row is skipped
    todo = [(s, m) for s, m in in_range
            if m.get(KEYS["ticker"]) not in stored or (m.get(KEYS["ticker"]) in held_stored
                                                       and m.get(KEYS["ticker"]) in placed)]
    run.already = len(in_range) - len(todo)
    # a hold line is printed for an event with a row this run writes or reads again, not for one stored and placed
    live_evs = {km.event_of(m) for _, m in in_range
                if m.get(KEYS["ticker"]) not in stored or m.get(KEYS["ticker"]) in held_stored}
    run.hold_lines = [ln for ln in run.hold_lines if ln[len(HOLD_MARK):].split(":", 1)[0] in live_evs]
    for _, m in in_range:
        t = m.get(KEYS["ticker"])
        if t in held_stored and t not in placed:
            if _HOLD_RX.search(why.get(t) or ""):
                run.held_still += 1                          # held again: left exactly as stored
            else:
                run.held_refused.append((t, why.get(t) or "not placed"))   # left as stored too
    for i, (source, m) in enumerate(todo):
        row, notes, kickoff = _new_row(series, source, m, fetched_at, placed, why, run)
        if kickoff is not None:
            ticker = row["ticker"]
            path, params = candle_call(series, source, ticker, kickoff, row["close_time"])
            try:
                data, cwhy = calls.get(path, params)
            except Capped:
                run.stopped = (f"the cap ({calls.cap} calls) before the candles of {ticker} ({source}); "
                               f"{len(todo) - i} market(s) left for the next run, which skips the stored ones"
                               + (f" ({len(run.candle_failed) - run.candle_refused} market(s) whose candle call "
                                  "failed this run are asked again first)"
                                  if len(run.candle_failed) > run.candle_refused else ""))
                break
            run.candle_calls += 1
            candles = data.get(KEYS["candles"]) if data else None
            if not isinstance(candles, list):
                run.candle_failed.append((ticker, cwhy or f"no '{KEYS['candles']}' list"))
                if not _refused_for_good(cwhy):
                    continue                                # not stored: the next run asks again
                notes.append(f"candle call refused ({cwhy}): no quote")   # a 4xx answer: stored, never asked again
                run.candle_refused += 1
            else:
                row.update(window_stats(candles, kickoff, source))
                if row["last_ts"] is None:
                    notes.append("no two-sided candle at or before kickoff")
        if row["ticker"] in held_stored:
            # the held row placed: its stored notes kept, the clearing appended, then what its candles said
            row["notes"] = "; ".join([held_stored[row["ticker"]],
                                      f"hold cleared {fetched_at:%Y-%m-%d %H:%M}Z: placed by the ingest"]
                                     + [n for n in notes if not n.startswith("result as read")])
            run.replaced.append(row)
            continue
        row["notes"] = "; ".join(notes) or None
        run.rows.append(row)
        if row["match_id"] is None:
            if _HOLD_RX.search(why.get(row["ticker"]) or ""):
                run.held_new += 1
            else:
                run.refused[why.get(row["ticker"]) or "not placed"] += 1

    # 4. the insert: this table and nothing else; a stored held row the run placed is written in place (only while it
    # is still a held row: nothing with a match_id is ever moved)
    if not dry_run and (run.rows or run.replaced):
        with session_scope() as sess:
            sess.add_all(KalshiSettledMarket(**r) for r in run.rows)
            K = KalshiSettledMarket
            for r in list(run.replaced):
                sess.flush()                                 # the rows added and placed above are read too
                obj = sess.execute(select(K).where(K.ticker == r["ticker"])).scalar_one_or_none()
                if obj is None or not is_held(obj.match_id, obj.notes):
                    run.replaced.remove(r)
                    run.replace_skipped.append((r["ticker"], "no longer a held row at the write (placed or changed "
                                                             "since it was read)"))
                    continue
                # the side read again at the write, as place_held reads it: a row of the series that took it after
                # the run read the table keeps it, and the held row is left as it is
                held_by = sess.execute(select(K.ticker).where(K.series == series, K.match_id == r["match_id"],
                                                              K.side == r["side"], K.ticker != r["ticker"])
                                       ).scalars().all()
                if held_by:
                    run.replaced.remove(r)
                    run.replace_skipped.append((r["ticker"], f"match {r['match_id']} {r['side']} is held by "
                                                             f"{', '.join(sorted(held_by))} at the write (two settled "
                                                             "markets are never stored on one side of one game)"))
                    continue
                for c in REPLACE_COLS:
                    setattr(obj, c, r[c])
    _receipt(run, calls, echo)
    return run


def row_line(r: dict) -> str:
    """One row as the dry run lists it (and place-held prints it before and after)."""
    q = (f"last {r['last_ts']:%Y-%m-%d %H:%M}Z bid {r['last_bid']} ask {r['last_ask']} mid {r['last_mid']}"
         if r["last_ts"] else "no last quote")
    st = f"{r['settled_time']:%Y-%m-%d %H:%M:%S}Z" if r["settled_time"] else "-"
    return (f"{r['ticker']} · {r['source']} · match {r['match_id'] or '-'} {r['side'] or '-'} · result "
            f"{r['kalshi_result'] or '-'} · settled {st} · {q} · 6h {r['candles_6h']} two-sided "
            f"{r['candles_two_sided']} gaps {r['gaps']}" + (f" · {r['notes']}" if r["notes"] else ""))


def _receipt(run: Run, calls: Calls, echo) -> None:
    w = "would be stored" if run.dry_run else "stored"
    echo(f"  cutoff read at the start: {run.cutoff or 'none'}")
    echo(f"  markets listed: {run.listed['historical'] + run.listed['live']} (historical {run.listed['historical']}, "
         f"live settled {run.listed['live']})"
         + (f" · open, read for the identity hold only (never placed or stored) {run.listed['open']}"
            if run.open_read else "")
         + (f" · outside --since/--until {run.out_of_range}" if run.out_of_range else "")
         + (f" · no game day to filter {run.no_day}" if run.no_day else "")
         + (f" · no ticker {run.no_ticker}" if run.no_ticker else "")
         + (f" · listed twice (the first kept) {run.duplicates}" if run.duplicates else ""))
    for note in run.list_notes:
        echo(f"  ✗ {note}")
    placed = sum(1 for r in run.rows if r["match_id"] is not None)
    echo(f"  {w}: {len(run.rows)} (placed on a stored game {placed}, refused and kept {len(run.rows) - placed}) · "
         f"already stored {run.already}")
    if run.held_new or run.held_still or run.replaced or run.held_refused or run.hold_lines or run.replace_skipped:
        pl = "would be placed" if run.dry_run else "placed"
        echo(f"  identity hold (clock series; ARCHITECT 2026-10-18, addendum 127 item 3(c)): new rows held "
             f"{run.held_new} (kept with match_id null; a later run reads them again) · stored held rows held again "
             f"{run.held_still} (left as stored) · stored held rows {pl}, the hold cleared {len(run.replaced)}"
             + (f" · stored held rows whose hold cleared but the matcher refuses, left as stored "
                f"{len(run.held_refused)}" if run.held_refused else ""))
        for ln in run.hold_lines:
            echo(ln)
        for t, why in run.held_refused:
            echo(f"    {t}: hold cleared; refused by the matcher: {why}"
                 + (f" (match {run.claimed_by[t][0]} is stored on {', '.join(run.claimed_by[t][1])})"
                    if t in run.claimed_by else ""))
        for t, why in run.replace_skipped:
            echo(f"  ✗ {t}: {why}: left as it is")
    if run.refused:
        echo("  refused by the matcher, by reason (kept with match_id null):")
        for r, n in sorted(run.refused.items(), key=lambda x: (-x[1], x[0])):
            echo(f"    {n:>5}  {r}")
        for ln in run.refused_lines:
            echo(ln)
    echo(f"  candle calls made: {run.candle_calls} · calls in all: {calls.made} of {calls.cap}")
    for nok, n in sorted(run.no_candles.items()):
        echo(f"    {n:>5}  {nok}")
    echo(f"  429 retries: {calls.retries_429}")
    if run.candle_failed:
        echo(f"  ✗ candle calls that failed: {len(run.candle_failed)} ({run.candle_refused} refused for good: stored "
             f"with no quote; {len(run.candle_failed) - run.candle_refused} not stored: the next run asks again)")
        for t, why in run.candle_failed:
            echo(f"    {t}: {why}")
    written = run.rows + run.replaced      # every row the run writes: new rows and stored held rows placed in place
    nolast = sum(1 for r in written if r["last_ts"] is None)
    echo(f"  rows with last_ts null (no two-sided candle before kickoff, or no candles): {nolast}")
    echo(f"  rows with settled_time null: {sum(1 for r in written if r['settled_time'] is None)}")
    if run.dry_run:
        for r in run.rows:
            echo(f"    {row_line(r)}")
        for r in run.replaced:
            echo(f"    (stored held row, would be placed) {row_line(r)}")
    if run.stopped:
        echo(f"  STOPPED at {run.stopped}")


# ---- THE RULED RE-PLACE (ARCHITECT 2026-10-18 10:10 ET, addendum 130 item 2(c)) ------------------------------------

PLACE_HELD_CALLS = 3                     # one candle call and the two 429 retries of addendum 104 item 2


def place_held(ticker: str, match_id: int, ruling: str, *, dry_run: bool = False, adapter=None, echo=print,
               now: datetime | None = None, guard=None) -> dict:
    """`kalshi-history place-held` (addendum 130 item 2(c), verbatim): "`kalshi-history place-held --ticker TICKER
    --match-id N --ruling "<addendum>"` sets match_id and side on a row that has match_id null and the hold/refusal
    note, appends the ruling to its note, and fetches its candles then — a reviewed command, never a guess by the
    ingest."

    Refuses (ValueError "REFUSED: ...", nothing written) unless: the ruling is not empty; the row exists; its match_id
    is null; its notes carry the identity hold's reason or the matcher's refusal ("refused by the matcher: "); the
    match exists and is a game of the series' own competition; the event's two names (its stored rows'
    yes_sub_title) fit the match's two teams one each (kalshi_match.fit, the matcher's own fit); the side can be told
    (the market's yes team, yes_sub_title, against the fit's home name; a Tie leg is DRAW); and no other stored row of
    the series already holds that side of that match. Then the candles, on the match's stored kickoff, by the ingest's
    own call (candle_call; a 429 is asked again as the ingest asks it): the quote is the candles' (window_stats). A
    candle call that fails for now (a 5xx, a 408, a transport error, a third 429, an answer with no list) writes
    nothing and refuses, naming the call and the failure (ARCHITECT 2026-10-18, addendum 132 item 3(a): ""fetches its
    candles then" means the quote lands with the placement or the placement does not land"; the operator re-runs). A
    candle call the exchange refuses for good (a 4xx other than 408 / 429, _refused_for_good: the ingest stores that
    market with a null quote and the status in notes), or a window that cannot be read, leaves the placement with a
    null quote and says so in notes and on the console (the quote stored before, read on the ticker's clock, is not
    this kickoff's). Notes: the stored notes, then "placed by ruling: <ruling>", then what the candles said. fetched_at
    becomes the placement's time. `guard` (the CLI's backup check) is called once every refusal has been read, before
    the candle call, and never under dry_run. dry_run makes every read, the candle call included, prints what would be
    written, writes nothing (and refuses as the write would on a candle call that fails for now). Returns {"before":
    row, "after": row, "written": bool}."""
    from sqlalchemy import inspect, select

    from src.adapters.kalshi import KalshiAdapter
    from src.db.database import session_scope
    from src.db.schema import Competition, KalshiSettledMarket as K, Match
    from src.timeutil import utc_now_naive
    from src.walters.venue_quote_age import readonly_session

    ticker, ruling = (ticker or "").strip(), " ".join((ruling or "").split())
    if not ruling:
        raise ValueError("REFUSED: --ruling is empty: a re-place names the ruling it is made by")
    adapter = adapter or KalshiAdapter()
    at = now or utc_now_naive()
    with readonly_session() as rs:
        if not inspect(rs.get_bind()).has_table(TABLE):
            raise ValueError(f"REFUSED: {TABLE} does not exist: no row to place")
        ready = migrated(rs)
        r = rs.execute(select(K).where(K.ticker == ticker)).scalar_one_or_none()
        if r is None:
            raise ValueError(f"REFUSED: no row of {TABLE} has ticker {ticker!r}: nothing is placed")
        before = {c: getattr(r, c) for c in K.__table__.c.keys()}
        notes = before["notes"] or ""
        if before["match_id"] is not None:
            raise ValueError(f"REFUSED: {ticker} is already placed on match {before['match_id']} {before['side']}: "
                             "nothing already placed is moved")
        if not (_HOLD_RX.search(notes) or REFUSED_NOTE in notes):
            raise ValueError(f"REFUSED: {ticker} carries no identity hold and no refusal in its notes "
                             f"({notes or 'none'!r}): only a held or refused row is placed by ruling")
        comp_code, soccer = competition_for(before["series"], adapter)
        comp_id = (rs.execute(select(Competition.id).where(Competition.code == comp_code)).scalar_one_or_none()
                   if comp_code else None)
        g = rs.get(Match, match_id)
        if g is None:
            raise ValueError(f"REFUSED: no match {match_id}: nothing is placed")
        if comp_id is None or g.competition_id != comp_id:
            raise ValueError(f"REFUSED: match {match_id} is not a game of {before['series']}'s own competition "
                             f"({comp_code or 'none'}): nothing is placed")
        home, away = g.home_team.name, g.away_team.name
        status = str(getattr(g.status, "value", g.status))
        kickoff = g.utc_date
        sibs = rs.execute(select(K.ticker, K.yes_sub_title).where(K.event_ticker == before["event_ticker"])).all()
        is_tie = adapter.is_tie_market if soccer else (lambda m: False)
        names = []
        for t, yst in sibs:
            nm = (yst or "").strip()
            if nm and not is_tie({"ticker": t, "yes_sub_title": yst}) and nm not in names:
                names.append(nm)
        if len(names) != 2:
            raise ValueError(f"REFUSED: the stored rows of event {before['event_ticker']} name {names or 'no team'}: "
                             "the event's two names are needed to read the match's teams")
        f = km.fit((names[0], names[1]), home, away)
        if f is None:
            raise ValueError(f"REFUSED: match {match_id}'s teams ({away} at {home}) are not the event's two names "
                             f"({names[0]}, {names[1]}) one each: nothing is placed")
        home_name = f[1]
        yes = (before["yes_sub_title"] or "").strip()
        if is_tie({"ticker": ticker, "yes_sub_title": before["yes_sub_title"]}):
            side = "DRAW"
        elif yes not in names:
            raise ValueError(f"REFUSED: {ticker}'s yes team {yes!r} is neither of the event's names {names}: the side "
                             "cannot be told")
        elif home_name is None:
            raise ValueError(f"REFUSED: the names {names} cannot tell home from away on match {match_id} ({away} at "
                             f"{home}): the side cannot be told")
        else:
            side = "HOME" if yes == home_name else "AWAY"
        taken = rs.execute(select(K.ticker).where(K.series == before["series"], K.match_id == match_id,
                                                  K.side == side, K.ticker != ticker)).scalars().all()
        if taken:
            raise ValueError(f"REFUSED: match {match_id} {side} is already held by {', '.join(sorted(taken))}: two "
                             "settled markets are never stored on one side of one game")
    if not dry_run and not ready:
        raise ValueError(f"REFUSED: {TABLE} is not migrated (no migration marker {MIGRATION_MARKER}): nothing is "
                         "written; --dry-run reads without it")
    if len("; ".join(x for x in (before["notes"], f"{RULED_NOTE}{ruling}") if x)) + 200 > 2000:
        raise ValueError("REFUSED: the notes would pass the column's 2000 characters: shorten the ruling; nothing is "
                         "written")
    echo(f"kalshi-history place-held {ticker} → match {match_id} · "
         f"{'DRY RUN: nothing is written' if dry_run else f'writes this one row of {TABLE}'} · ruling: {ruling}")
    echo(f"  before: {row_line(before)}")
    echo(f"  match {match_id}: {away} at {home} · kickoff {kickoff:%Y-%m-%d %H:%M}Z ({km.et_text(kickoff)}) · "
         f"{status} · the event's names {names[0]} / {names[1]} fit it one each: {yes} is {side}")
    if not dry_run and guard is not None:
        guard()
    after = dict(before, match_id=match_id, side=side, fetched_at=at, last_ts=None, last_bid=None, last_ask=None,
                 last_mid=None, candles_6h=None, candles_two_sided=None, gaps=None, raw_first_candle=None)
    calls = Calls(adapter, PLACE_HELD_CALLS)
    nok = _window_problem(kickoff, before["close_time"])
    if nok:
        cnote = f"at placement: {nok}"
        echo(f"  candles: {nok}; the placement stands with no quote")
    else:
        path, params = candle_call(before["series"], before["source"], ticker, kickoff, before["close_time"])
        data, why = calls.get(path, params)
        candles = data.get(KEYS["candles"]) if data else None
        if not isinstance(candles, list):
            why = why or f"no '{KEYS['candles']}' list"
            if not _refused_for_good(why):
                # a failure for now (a 5xx, a 408, a transport error, a third 429, an answer with no list) writes
                # nothing (ARCHITECT 2026-10-18, addendum 132 item 3(a)), as the ingest stores nothing on it
                raise ValueError(f"REFUSED: the candle call {path} failed ({why}; 429 retries: {calls.retries_429}): "
                                 "nothing is written (the quote lands with the placement or the placement does not "
                                 "land, addendum 132 item 3(a)); run it again")
            cnote = f"candle call failed at placement ({why}): no quote; the placement stands"
            echo(f"  ✗ candles: {path} failed ({why}): the placement stands with no quote "
                 f"(429 retries: {calls.retries_429})")
        else:
            after.update(window_stats(candles, kickoff, before["source"]))
            cnote = (f"candles read at placement on match {match_id}'s kickoff"
                     + ("; no two-sided candle at or before kickoff" if after["last_ts"] is None else ""))
            echo(f"  candles: {path} from {kickoff - timedelta(hours=WINDOW_H):%Y-%m-%d %H:%M}Z to "
                 f"{before['close_time']:%Y-%m-%d %H:%M}Z: {len(candles)} candle(s) · 429 retries: "
                 f"{calls.retries_429}")
    after["notes"] = "; ".join(x for x in (before["notes"], f"{RULED_NOTE}{ruling}", cnote) if x)
    if len(after["notes"]) > 2000:
        raise ValueError(f"REFUSED: the notes would run to {len(after['notes'])} characters, past the column's 2000: "
                         "shorten the ruling; nothing is written")
    echo(f"  after:  {row_line(after)}")
    if dry_run:
        echo("  DRY RUN: nothing written")
        return {"before": before, "after": after, "written": False}
    with session_scope() as sess:
        obj = sess.execute(select(K).where(K.ticker == ticker)).scalar_one_or_none()
        if obj is None or obj.match_id is not None:
            raise ValueError(f"REFUSED: {ticker} changed before the write (placed or gone): nothing is written")
        # the side is read again in the write's own transaction: another place-held, or a history run, may have taken
        # it while the candles were read (two settled markets are never stored on one side of one game)
        clash = sess.execute(select(K.ticker).where(K.series == before["series"], K.match_id == match_id,
                                                    K.side == side, K.ticker != ticker)).scalars().all()
        if clash:
            raise ValueError(f"REFUSED: match {match_id} {side} was taken by {', '.join(sorted(clash))} before the "
                             "write: two settled markets are never stored on one side of one game; nothing is written")
        for c in REPLACE_COLS:
            setattr(obj, c, after[c])
    echo(f"  ✓ placed: {ticker} on match {match_id} {side} (one row written)")
    return {"before": before, "after": after, "written": True}
