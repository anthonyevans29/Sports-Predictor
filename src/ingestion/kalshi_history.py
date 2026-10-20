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
    python cli.py kalshi-history place-chain --anchor EVENT --ruling "<the anchor's ruling>"
                                 (--backup PATH | --dry-run)      # the anchored chain, addendum 148 item 2
    python cli.py kalshi-history place-chain --list --series S    # its read-only listing (no network, no write)

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
  across-events rule, as on main"; addendum 137 item 1, option (c): "A placed stored row NOT placed by ruling claims
  both its stored side and the side its date names; a row placed by ruling claims its stored side only, so 3(b)'s
  motivating case stands. The principle that decides it: this head's refusals must be a superset of main's, the one
  designed exception being a ruled row."): a placed stored row listed in the run is placed with its event (so the
  event is placed on all its legs) and is never placed or moved itself; one placed by ruling claims only its stored
  side (its date placement is read by nothing), and every other also claims the side its date names, in the
  across-events rule, as on main. A refused stored row has no stored side: it
  is placed by date with its event and claims there, as main has it, and is never written again (a stored refusal is
  never turned into a placement by a later run). That read of the stored rows covers a market whose ticker carries a
  clock (the identity hold's series; KXMLBGAME of the five), a side a row placed by ruling holds (its notes carry
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
  A held row the hold never releases is placed only by a ruling: `kalshi-history place-held` (place_held below),
  or, behind an anchor ruled into place, by `kalshi-history place-chain` (place_chain below; addendum 148 item 2).
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
    write_refused: list = field(default_factory=list)        # (ticker, why): a new row written unplaced at the write
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
                 stored: frozenset = frozenset(), stored_on: dict | None = None) -> tuple[dict, dict, list]:
    """{ticker: (game id, kickoff, side)} placed, {ticker: reason} refused, the matcher's lines. Each event is placed
    alone, on the stored games of its own days (kalshi_match.day_span, as kalshi_sync.stored_games loads them).
    `holds` ({event: (earlier event, why, words)}, identity_holds): an event held there keeps no placement: each market
    of it that the matcher placed is refused under the hold's reason, before the claims rule reads (a market the
    matcher refused keeps its own reason, as for "behind", addendum 55 item 3); its line is in the lines.
    `stored` (the tickers of stored rows placed BY RULING, listed in range): placed with their event, so the event is
    placed on all its legs, but never placed by date themselves (ARCHITECT 2026-10-18, addendum 132 item 3(b);
    addendum 134 item 3, option (ii); addendum 137 item 1, option (c): "a row placed by ruling claims its stored side
    only"): they are left out of `placed` and of the claims rule here, and run_history reads them by their stored
    (match_id, side). Every other stored row, placed or refused, is placed by date and claims here, as on main (a
    placed one also claims its stored side in run_history's read, option (c)); run_history never writes it again.
    `stored_on` ({(match_id, side): [tickers]}, the stored sides of the placed stored rows listed in range): a side
    two or more markets claim here that one of them holds is named on the claims line, `; stored on <ticker> (nothing
    already placed is moved)`, so the line names the stored row that holds it, which is not moved."""
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
            held = sorted((stored_on or {}).get((mid, side), ()))
            lines.append(f"  ✗ match {mid} {side}: {len(ts)} markets of {len({km.event_of({'ticker': t}) for t in ts})} "
                         f"events claim it ({', '.join(sorted(ts))}): all refused"
                         + (f"; stored on {', '.join(held)} (nothing already placed is moved)" if held else ""))
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
            # a stored row listed in range that HAS a placement enters the claims rule by its stored (match_id, side)
            # (addendum 132 item 3(b), option (ii) by addendum 134 item 3); a refused or held stored row has no stored
            # side and keeps its date claim in the across-events rule, as on main. ARCHITECT 2026-10-19, addendum 137
            # item 1, option (c): "A placed stored row NOT placed by ruling claims both its stored side and the side its
            # date names; a row placed by ruling claims its stored side only, so 3(b)'s motivating case stands. The
            # principle that decides it: this head's refusals must be a superset of main's, the one designed exception
            # being a ruled row." So only a ruled row is left out of the date claims (`ruled_listed`); every other
            # placed stored row is placed by date here too, as on main, and never written again
            with_side = {t for t, _, _, mid, _, _ in mine if mid is not None}
            listed = {m.get(KEYS["ticker"]) for _, m in in_range} & with_side
            ruled_listed = {t for t, _, _, mid, notes, _ in mine if t in listed and RULED_NOTE in (notes or "")}
            stored_on: dict[tuple, list] = {}
            for t, _, _, mid, _, side in mine:
                if t in listed:
                    stored_on.setdefault((mid, side), []).append(t)
            placed, why, lines = place_events([m for _, m in in_range], games, is_tie, holds,
                                              frozenset(ruled_listed), stored_on)
            for t in listed - ruled_listed:   # a date claim only: a placed stored row is never placed, nor moved
                placed.pop(t, None)
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
            K = KalshiSettledMarket
            # #599 item 1 (ARCHITECT 2026-10-19, addendum 136 item 3: "the new-row write re-check"): a new placed row
            # reads its side again in the write's own transaction, in the plan's own scope (a clock ticker, or a side a
            # row placed by ruling holds): a place-held that committed after the run read the table keeps the side,
            # and the new row is written unplaced, as a refused row (no quote: its candles were this match's), so a
            # ruling can place it later
            for r in run.rows:
                if r["match_id"] is None:
                    continue
                holders = sess.execute(select(K.ticker, K.notes).where(
                    K.series == series, K.match_id == r["match_id"], K.side == r["side"],
                    K.ticker != r["ticker"])).all()
                clock_t = km.ticker_stamp({"ticker": r["ticker"], "event_ticker": r["event_ticker"]})[1] is not None
                if holders and (clock_t or any(RULED_NOTE in (n or "") for _, n in holders)):
                    by = ", ".join(sorted(t for t, _ in holders))
                    what = f"match {r['match_id']} {r['side']} held by {by} at the write"
                    run.write_refused.append((r["ticker"], what))
                    run.refused[km.TWO_CLAIMS] += 1          # in the totals by reason, as the row is stored (Codex)
                    r.update(match_id=None, side=None, last_ts=None, last_bid=None, last_ask=None, last_mid=None,
                             candles_6h=None, candles_two_sided=None, gaps=None, raw_first_candle=None,
                             notes="; ".join(x for x in (f"{REFUSED_NOTE}{km.TWO_CLAIMS} ({what})",
                                                         *[n for n in (r["notes"] or "").split("; ")
                                                           if n and n.startswith("result as read")]) if x))
            sess.add_all(KalshiSettledMarket(**r) for r in run.rows)
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
    for t, why in run.write_refused:                 # #599 item 1: the side taken between the plan and the write
        echo(f"  ✗ {t}: {why}: written unplaced, refused by the matcher: {km.TWO_CLAIMS} (a ruling can place it)")
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

PLACE_HELD_CALLS = 6                     # the cutoff and one candle call, each with the two 429 retries of addendum
                                         # 104 item 2 (#599 item 2: the endpoint is read by the cutoff at placement)


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
    from src.db.schema import KalshiSettledMarket as K
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
        tg = _ruled_target(rs, before, match_id, adapter)
    if not dry_run and not ready:
        raise ValueError(f"REFUSED: {TABLE} is not migrated (no migration marker {MIGRATION_MARKER}): nothing is "
                         "written; --dry-run reads without it")
    if len("; ".join(x for x in (before["notes"], f"{RULED_NOTE}{ruling}") if x)) + 200 > 2000:
        raise ValueError("REFUSED: the notes would pass the column's 2000 characters: shorten the ruling; nothing is "
                         "written")
    echo(f"kalshi-history place-held {ticker} → match {match_id} · "
         f"{'DRY RUN: nothing is written' if dry_run else f'writes this one row of {TABLE}'} · ruling: {ruling}")
    echo(f"  before: {row_line(before)}")
    echo(_target_line(tg))
    if not dry_run and guard is not None:
        guard()
    calls = Calls(adapter, PLACE_HELD_CALLS)
    after = _placed_after(before, tg, at, (f"{RULED_NOTE}{ruling}",), calls, lambda: _read_cutoff(calls), echo)
    echo(f"  after:  {row_line(after)}")
    if dry_run:
        echo("  DRY RUN: nothing written")
        return {"before": before, "after": after, "written": False}
    with session_scope() as sess:
        _write_placed(sess, before, after)
    echo(f"  ✓ placed: {ticker} on match {match_id} {tg['side']} (one row written)")
    return {"before": before, "after": after, "written": True}


def _ruled_target(rs, before: dict, match_id: int, adapter) -> dict:
    """place_held's reads of the match a stored row is placed on, every refusal of them its own (ValueError
    "REFUSED: ..."): the match exists and is a game of the series' own competition; the event's two names (its stored
    rows' yes_sub_title, the event read as the history path reads it) fit the match's two teams one each
    (kalshi_match.fit); the side can be told (the market's yes team against the fit's home name; a Tie leg is DRAW);
    and no other stored row of the series already holds that side of that match. The anchored chain reads its members
    by the same function. Returns what the console prints and the write needs."""
    from sqlalchemy import select

    from src.db.schema import Competition, KalshiSettledMarket as K, Match
    ticker = before["ticker"]
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
    # the event as the history path derives it (#599 item 3: the column is nullable): a row with no event_ticker
    # reads its own ticker's event, and the siblings are the series' rows of that event read the same way
    ev = before["event_ticker"] or km.event_of({"ticker": ticker})
    sibs = [(t, yst) for t, yst, e in rs.execute(
                select(K.ticker, K.yes_sub_title, K.event_ticker).where(
                    K.series == before["series"], (K.event_ticker == ev) | K.event_ticker.is_(None))).all()
            if (e or km.event_of({"ticker": t})) == ev]
    is_tie = adapter.is_tie_market if soccer else (lambda m: False)
    names = []
    for t, yst in sibs:
        nm = (yst or "").strip()
        if nm and not is_tie({"ticker": t, "yes_sub_title": yst}) and nm not in names:
            names.append(nm)
    if len(names) != 2:
        raise ValueError(f"REFUSED: the stored rows of event {ev} name {names or 'no team'}: "
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
    return {"match_id": match_id, "home": home, "away": away, "status": status, "kickoff": kickoff, "names": names,
            "yes": yes, "side": side}


def _target_line(tg: dict) -> str:
    """place_held's match line."""
    return (f"  match {tg['match_id']}: {tg['away']} at {tg['home']} · kickoff {tg['kickoff']:%Y-%m-%d %H:%M}Z "
            f"({km.et_text(tg['kickoff'])}) · {tg['status']} · the event's names {tg['names'][0]} / {tg['names'][1]} "
            f"fit it one each: {tg['yes']} is {tg['side']}")


def _read_cutoff(calls: Calls) -> tuple[str, datetime]:
    """(the cutoff as sent, read) at placement, one call (#599 item 2); one that cannot be read writes nothing."""
    cut, cwhy = calls.get("historical/cutoff")
    cutoff = parse_ts(cut.get(KEYS["cutoff"])) if cut else None
    if cutoff is None:
        why_cut = cwhy or f"no readable {KEYS['cutoff']}"
        raise ValueError(f"REFUSED: the cutoff (historical/cutoff) could not be read ({why_cut}; 429 retries: "
                         f"{calls.retries_429}): the candle endpoint cannot be told; nothing is written; run it "
                         "again")
    return cut.get(KEYS["cutoff"]), cutoff


def _placed_after(before: dict, tg: dict, at: datetime, parts: tuple, calls: Calls, cutoff_of, echo) -> dict:
    """place_held's placement of one stored row on tg's match: the row as written (match_id, side, fetched_at, the
    candles read then, on the match's stored kickoff, and the notes: the stored notes, then `parts` (the ruling part,
    and the anchored chain's own part after it), then what the candles said). Prints place_held's candle lines.
    `cutoff_of()` gives (the cutoff as sent, read): place_held reads it here; the anchored chain once for its rows.
    A candle call that fails for now refuses (ValueError) and nothing is written (addendum 132 item 3(a))."""
    ticker, match_id, kickoff = before["ticker"], tg["match_id"], tg["kickoff"]
    after = dict(before, match_id=match_id, side=tg["side"], fetched_at=at, last_ts=None, last_bid=None, last_ask=None,
                 last_mid=None, candles_6h=None, candles_two_sided=None, gaps=None, raw_first_candle=None)
    nok = _window_problem(kickoff, before["close_time"])
    if nok:
        cnote = f"at placement: {nok}"
        echo(f"  candles: {nok}; the placement stands with no quote")
    else:
        # #599 item 2 (ARCHITECT 2026-10-19, addendum 136 item 3: "place-held's candle endpoint by the cutoff"): the
        # stored source is the list the market came from at fetch time; the cutoff moves on, so a row stored `live`
        # can be behind it by its placement. The cutoff is read now (one call, as the ingest's run starts with it) and
        # the endpoint is the row's settled_time against it; the source written is the one used. A cutoff that cannot
        # be read writes nothing (the quote lands with the placement or the placement does not land, 132 item 3(a)).
        raw_cut, cutoff = cutoff_of()
        settled = before["settled_time"]
        source = before["source"] if settled is None else ("historical" if settled < cutoff else "live")
        after["source"] = source
        echo(f"  cutoff {KEYS['cutoff']}: {raw_cut} · settled "
             + (f"{settled:%Y-%m-%d %H:%M:%S}Z" if settled else "null (the stored source stands)")
             + f" · candles from {source}" + ("" if source == before["source"] else f" (stored {before['source']})"))
        path, params = candle_call(before["series"], source, ticker, kickoff, before["close_time"])
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
            after.update(window_stats(candles, kickoff, source))
            cnote = (f"candles read at placement on match {match_id}'s kickoff"
                     + ("; no two-sided candle at or before kickoff" if after["last_ts"] is None else ""))
            echo(f"  candles: {path} from {kickoff - timedelta(hours=WINDOW_H):%Y-%m-%d %H:%M}Z to "
                 f"{before['close_time']:%Y-%m-%d %H:%M}Z: {len(candles)} candle(s) · 429 retries: "
                 f"{calls.retries_429}")
    after["notes"] = "; ".join(x for x in (before["notes"], *parts, cnote) if x)
    if len(after["notes"]) > 2000:
        raise ValueError(f"REFUSED: the notes would run to {len(after['notes'])} characters, past the column's 2000: "
                         "shorten the ruling; nothing is written")
    return after


def _write_placed(sess, before: dict, after: dict, *, held_only: bool = False) -> None:
    """place_held's write of one placed row, in the caller's transaction: the row read again (gone, or placed since,
    refuses; with `held_only`, as the anchored chain writes, a row that is no longer a HELD row refuses, as
    run_history's write reads it, KH is_held), and its side read again (another row of the series that took it while
    the candles were read refuses: two settled markets are never stored on one side of one game). A refusal is a
    ValueError, and the caller's transaction writes nothing."""
    from sqlalchemy import select

    from src.db.schema import KalshiSettledMarket as K
    ticker, match_id, side = before["ticker"], after["match_id"], after["side"]
    obj = sess.execute(select(K).where(K.ticker == ticker)).scalar_one_or_none()
    if held_only:
        if obj is None or not is_held(obj.match_id, obj.notes):
            raise ValueError(f"REFUSED: {ticker} changed before the write (no longer a held row: placed, gone or its "
                             "notes changed): nothing is written")
    elif obj is None or obj.match_id is not None:
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


# ---- THE ANCHORED CHAIN (ARCHITECT 2026-10-20 12:56 ET, addendum 148 item 2; #630) ------------------------------------
# The design posted on #630 (addendum 146 item 4), RULED on its twelve questions by addendum 148 item 2, verbatim in
# part: "Q1 after A's ticker clock, M used by A: yes. Q3 STOP: yes. Q4 yes to both (the storage definition of IN STEP;
# MAX_TICK_DRIFT 2h inclusive plus the time tie). Q5 the fourth note part after the ruling part: yes. Q6 END: yes. Q7
# "out of step" only: yes. Q8 N1 and N2: accept both. Q10 yes. Q11 the table only, no exchange call: yes. Q12 the
# listing mode in the same PR, its console in the body: yes. Q2 and Q9, the change: a shift-capable check IS wanted,
# because the shifted chain is the case the rule exists for (E17 on 50548 is the ALCS's own example, and every
# rainout-then-doubleheader pattern is a shift). A member PLACES on the count's game when EITHER check passes, and a
# result mismatch refuses under both: (a) the clock check as designed: |kickoff − ticker clock| ≤ MAX_TICK_DRIFT and no
# other unused game within 2h; or (b) the settlement bracket: the row's settled_time is after the count's game's
# kickoff and before the kickoff of the pair's next game in the list (or no next game within N1's window), the target
# is FINISHED with a stored winner, and the leg's kalshi_result agrees with that winner. The bracket is the shifted
# event's own evidence that it settled on that game and no other. A member that passes neither stays held and the chain
# STOPs (Q3). The dry run prints which check placed each row ("by clock 0.1h" or "by settlement +2.9h, before <next id>
# <ET>")."

CHAIN_NOTE = "placed by the chain of {anchor} [{k}]: {how}"   # the note's fourth part, after the ruling part (Q5)
_RULED_RX = re.compile(r"(?:^|; )placed by ruling: (.*?)(?=; |$)")


@dataclass(frozen=True)
class _Game:
    """A stored game of the pair as the chain reads it (read in the session, printed after it)."""
    id: int
    utc_date: datetime
    status: str                  # the stored status, lowercased: scheduled / live / finished (is_game rows only)
    winner: str | None           # HOME / AWAY of a FINISHED game, from full_time_result and the scores; None when
                                 # neither is stored, or when the two disagree (law 4)


def _as_game(g) -> _Game:
    st = str(getattr(g.status, "value", g.status) or "").lower()
    winner = None
    if st == "finished":
        by_result = {"H": "HOME", "A": "AWAY"}.get(getattr(g.full_time_result, "value", g.full_time_result))
        hs, aw = g.home_score, g.away_score
        by_score = None if hs is None or aw is None or hs == aw else ("HOME" if hs > aw else "AWAY")
        winner = None if (by_result and by_score and by_result != by_score) else (by_result or by_score)
    return _Game(g.id, g.utc_date, st, winner)


def _ev(r: dict) -> str:
    """A stored row's event, as the history path derives it (#599 item 3)."""
    return r["event_ticker"] or km.event_of({"ticker": r["ticker"]})


def _mks(rows: list[dict]) -> list[dict]:
    """Stored rows as the matcher reads an event's markets (ticker, event, yes team)."""
    return [{"ticker": r["ticker"], "event_ticker": _ev(r), "yes_sub_title": r["yes_sub_title"]} for r in rows]


def _h(td: timedelta) -> str:
    return f"{abs(td.total_seconds()) / 3600:.1f}h"


def _signed_h(td: timedelta) -> str:
    return ("+" if td >= timedelta(0) else "-") + _h(td)


def _refusal(notes: str) -> str:
    return (notes or "").split(REFUSED_NOTE, 1)[-1].split("; ", 1)[0]


def _row_state(r: dict) -> tuple[str, str]:
    """(kind, words) of one stored row for the chain: ruled (placed by ruling), ingest (placed by the ingest: IN STEP,
    the storage definition, addendum 148 item 2 Q4), held (is_held), refused (the matcher's refusal), none."""
    notes = r["notes"] or ""
    if r["match_id"] is not None:
        if RULED_NOTE in notes:
            return "ruled", f"ruled on {r['match_id']} {r['side']}"
        return "ingest", f"placed by the ingest on {r['match_id']} {r['side']}"
    m = _HOLD_RX.search(notes)
    if m:
        return "held", f"held, names {m.group(1)} {m.group(2)}"
    if REFUSED_NOTE in notes:
        return "refused", f"refused: {_refusal(notes)}"
    return "none", "unplaced, with no hold and no refusal in its notes"


def _chain_kind(rows: list[dict], anchor: str) -> tuple[str, str | None, int | None]:
    """(member | counted | end, the END's words, the ruled match) of one chain event (the design's section 2, as
    ruled): IN STEP (a row placed by the ingest) ENDs; every row placed by ruling on one match is COUNTED; every row
    held, each naming the anchor out of step (N2; Q7), is a MEMBER; held behind another event, or naming the anchor
    unsettled, ENDs; every row refused ENDs (Q6); anything else is mixed legs and ENDs."""
    kinds = [_row_state(r)[0] for r in rows]
    if "ingest" in kinds:
        ids = sorted({r["match_id"] for r in rows if _row_state(r)[0] == "ingest"})
        return "end", f"in step (placed by the ingest on {', '.join(str(i) for i in ids)})", None
    if all(k == "ruled" for k in kinds):
        ids = sorted({r["match_id"] for r in rows})
        if len(ids) == 1:
            return "counted", None, ids[0]
        return "end", f"mixed legs (ruled on {', '.join(str(i) for i in ids)})", None
    if all(k == "held" for k in kinds):
        named = [_HOLD_RX.search(r["notes"] or "") for r in rows]
        for m in named:
            if m.group(1) != anchor:
                return "end", f"held behind {m.group(1)} ({m.group(2)})", None
        for m in named:
            if m.group(2) != HOLD_OUT_OF_STEP:
                return "end", f"names {anchor} {m.group(2)}", None
        return "member", None, None
    if all(k == "refused" for k in kinds):
        return "end", f"refused: {'; '.join(sorted({_refusal(r['notes']) for r in rows}))}", None
    return "end", "mixed legs (" + ", ".join(sorted({_row_state(r)[0] for r in rows})) + ")", None


def _carries_ruling(notes: str | None, ruling: str) -> bool:
    """The row's notes carry `placed by ruling: <ruling>` whole: after the start or "; ", before "; " or the end."""
    return bool(re.search(r"(?:^|; )" + re.escape(f"{RULED_NOTE}{ruling}") + r"(?=; |$)", notes or ""))


def _out_of_step(ev: str, mks: list[dict], games: list, is_tie) -> str | None:
    """The identity hold's own read of `ev` (identity_holds: out of step on its own date as
    kalshi_match.behind_out_of_step reads it, `now` before every game), the matcher's words or None. identity_holds
    reads an earlier event against a later one of its pair, so the read is made against `ev`'s own markets dated a day
    on, a probe for this read and nothing else (it is never stored, listed or placed). A numbered event (G1, G2) is
    never out of step; `games` is the stored games of `ev`'s days."""
    m = km._STAMP.search(ev + "X")
    day = km.ticker_stamp({"ticker": ev, "event_ticker": ev})[0]
    if not m or day is None:
        return None
    d1 = day + timedelta(days=1)
    probe = f"{ev[:m.start()]}-{d1:%y}{km._MONTHS[d1.month - 1]}{d1:%d}{m.group(4) or ''}{ev[m.end():]}"
    pmks = [{"ticker": f"{probe}-{mk['ticker'].rsplit('-', 1)[-1]}", "event_ticker": probe,
             "yes_sub_title": mk["yes_sub_title"]} for mk in mks]
    held = identity_holds({probe}, {ev: mks, probe: pmks}, set(), games, is_tie).get(probe)
    return held[2] if held and held[0] == ev and held[1] == HOLD_OUT_OF_STEP else None


def _chain_row(r: dict, g: _Game | None, verdict: str) -> str:
    """One stored row of a chain event, as the dry run prints it (the design's section 3, per row)."""
    st = r["settled_time"]
    settled = (f"{st:%Y-%m-%d %H:%M:%S}Z" if st else "-") + (f" ({_signed_h(st - g.utc_date)})" if st and g else "")
    winner = f" · winner {g.winner or 'not stored'}" if g else ""
    return (f"    {r['ticker']} · {_row_state(r)[1]} · result {r['kalshi_result'] or '-'}{winner} · settled {settled} · "
            f"{verdict}")


def _plan_chain(rs, anchor: str, ruling: str, adapter) -> dict:
    """The chain of `anchor` read from the table and the stored games (no network): every refusal (ValueError
    "REFUSED: ..."), the console's lines, and the rows the chain places. The design's sections 1, 2 and 5 as ruled
    (addendum 148 item 2)."""
    from sqlalchemy import select

    from src.db.schema import Competition, KalshiSettledMarket as K, Match
    from src.ingestion.kalshi_sync import stored_games

    cols = K.__table__.c.keys()

    def as_rows(q):
        return sorted(({c: getattr(o, c) for c in cols} for o in rs.execute(q).scalars()), key=lambda r: r["ticker"])

    a_rows = [r for r in as_rows(select(K).where((K.event_ticker == anchor) | K.event_ticker.is_(None)))
              if _ev(r) == anchor]
    if not a_rows:
        raise ValueError(f"REFUSED: no row of {TABLE} is of event {anchor!r}: nothing is placed")
    series = sorted({r["series"] for r in a_rows})
    if len(series) != 1:
        raise ValueError(f"REFUSED: the rows of {anchor} are of {len(series)} series ({', '.join(series)}): "
                         "nothing is placed")
    series = series[0]
    comp_code, soccer = competition_for(series, adapter)
    comp_id = (rs.execute(select(Competition.id).where(Competition.code == comp_code)).scalar_one_or_none()
               if comp_code else None)
    if comp_id is None:
        raise ValueError(f"REFUSED: {series}'s competition ({comp_code or 'none'}) is not in the DB: nothing is "
                         "placed")
    is_tie = adapter.is_tie_market if soccer else (lambda m: False)
    # THE ANCHOR: every row placed by ruling, on one match M, by the ruling --ruling names
    for r in a_rows:
        if _row_state(r)[0] != "ruled":
            raise ValueError(f"REFUSED: {anchor} is not placed by ruling on every row ({r['ticker']}: "
                             f"{_row_state(r)[1]}): a chain is anchored on an event ruled into place on both legs "
                             "(kalshi-history place-held); nothing is placed")
    ids = sorted({r["match_id"] for r in a_rows})
    if len(ids) != 1:
        raise ValueError(f"REFUSED: the rows of {anchor} are ruled on {len(ids)} matches "
                         f"({', '.join(str(i) for i in ids)}): a chain is anchored on one match; nothing is placed")
    for r in a_rows:
        if not _carries_ruling(r["notes"], ruling):
            raise ValueError(f"REFUSED: {r['ticker']} does not carry 'placed by ruling: {ruling}' (its ruling: "
                             f"{'; '.join(_RULED_RX.findall(r['notes'] or '')) or 'none'}): --ruling names the "
                             "anchor's own ruling; nothing is placed")
    a_mks = _mks(a_rows)
    key = _event_key(a_mks, is_tie)
    if key is None:
        raise ValueError(f"REFUSED: {anchor} is outside the identity hold's rule (an event of two names whose ticker "
                         "carries a clock): no chain; nothing is placed")
    pair, a_day = key
    a_clock = km.ticker_stamp(a_mks[0])[1]
    mid = ids[0]
    m = rs.get(Match, mid)
    if m is None:
        raise ValueError(f"REFUSED: no match {mid} (the anchor's): nothing is placed")
    if m.competition_id != comp_id:
        raise ValueError(f"REFUSED: match {mid}, the anchor's, is not a game of {series}'s own competition "
                         f"({comp_code}): nothing is placed")
    m_status = str(getattr(m.status, "value", m.status))
    if not km.is_game(m):
        raise ValueError(f"REFUSED: match {mid}, the anchor's, is {m_status}: not a game (addendum 50 item 6(c)), so "
                         "the count cannot read from it; nothing is placed")
    words = _out_of_step(anchor, a_mks, stored_games(rs, [comp_id], a_mks), is_tie)
    if words is None:
        raise ValueError(f"REFUSED: {anchor} is not out of step on its own date (the identity hold's read: a game of "
                         f"its pair on {a_day}, or a numbered event): a chain is anchored on the out-of-step event; "
                         "nothing is placed")
    a_side = ", ".join(f"{r['ticker']} {r['side']}" for r in a_rows)
    head = [f"  anchor {anchor} · clock {km.et_text(a_clock)} · out of step: {words} · ruled on match {mid}: "
            f"{m.away_team.name} at {m.home_team.name} · kickoff {m.utc_date:%Y-%m-%d %H:%M}Z "
            f"({km.et_text(m.utc_date)}) · {m_status} · {a_side}"]

    # THE PAIR'S EVENTS, in chain order (the hold's: ticker date, then event ticker), from the table only (Q11)
    by_ev: dict[str, list[dict]] = {}
    for r in as_rows(select(K).where(K.series == series)):
        by_ev.setdefault(_ev(r), []).append(r)
    info = {ev: _event_key(_mks(rws), is_tie) for ev, rws in by_ev.items()}
    after_a = sorted((inf[1], ev) for ev, inf in info.items() if inf and inf[0] == pair and (inf[1], ev) > (a_day,
                                                                                                          anchor))
    # THE CHAIN: the events after A up to, not including, the first that ENDs it, within N1 (1-10 days after A; a twin
    # on A's own date is next in chain order and is read, Q6)
    chain, end = [], None
    for d, ev in after_a:
        if (d - a_day).days > HOLD_BOUND_DAYS:
            break
        kind, why, ruled_on = _chain_kind(by_ev[ev], anchor)
        if kind == "end":
            end = (len(chain) + 1, ev, why)
            break
        chain.append((len(chain) + 1, ev, kind, ruled_on))
    chain_evs = {ev for _, ev, _, _ in chain}

    # THE LIST: the pair's games (the design's section 2: the anchor's two names fitted one each by kalshi_match.fit,
    # as place-held fits its match; rows that are games, any status) from A's ticker clock (Q1) through N1's window
    # and a day (a member on its tenth day can take the next day's game). The fitted games, M with them, of more than
    # one pair of teams refuse, as the matcher refuses PAIR_TIE: a second team row of one club is not told apart here
    last_day = a_day + timedelta(days=HOLD_BOUND_DAYS + 1)
    hi = (datetime.combine(last_day + timedelta(days=1), datetime.min.time(), tzinfo=km.ET)
          .astimezone(km.UTC).replace(tzinfo=None))
    names = km._names(a_mks, a_mks[0], is_tie)
    stored = sorted((g for g in rs.execute(select(Match).where(
        Match.competition_id == comp_id, Match.utc_date >= a_clock, Match.utc_date < hi)).scalars()
        if g.utc_date and g.home_team and g.away_team and km.is_game(g)
        and km.fit((names[0], names[1]), g.home_team.name, g.away_team.name) is not None),
        key=lambda g: (g.utc_date, g.id))
    by_pair: dict = {}
    for g in sorted({g.id: g for g in (m, *stored)}.values(), key=lambda g: (g.utc_date, g.id)):
        by_pair.setdefault(frozenset((g.home_team_id, g.away_team_id)), []).append(g)
    if len(by_pair) > 1:
        # merge-teams pairs only team rows whose names are equal: a pair whose clubs carry other names is a namesake
        same = len({frozenset((gs[0].home_team.name, gs[0].away_team.name)) for gs in by_pair.values()}) == 1
        how = ("merge-teams first" if same else
               "another club's game fits the names (a namesake): rule the events by place-held")
        raise ValueError(f"REFUSED: the games the names {names[0]} / {names[1]} fit one each (kalshi_match.fit: match "
                         f"{mid}, the anchor's, and the list from its clock through {last_day}) are of {len(by_pair)} "
                         "pairs of teams ("
                         + "; ".join(f"teams {'/'.join(str(i) for i in sorted(p))}: "
                                     + ", ".join(f"{g.id} {g.away_team.name} at {g.home_team.name}" for g in gs)
                                     for p, gs in sorted(by_pair.items(), key=lambda x: sorted(x[0])))
                         + f"): the matcher refuses such an event ({km.PAIR_TIE}); {how}; nothing is placed")
    by_minute: dict = {}
    for g in stored:
        by_minute.setdefault(g.utc_date.replace(second=0, microsecond=0), []).append(g.id)
    twins = [i for i in by_minute.values() if len(i) > 1]
    if twins:
        raise ValueError("REFUSED: " + "; ".join(f"rows {', '.join(str(i) for i in t)} share one kickoff minute: "
                                                 "dedupe-matches has to merge them" for t in twins)
                         + ": the count cannot tell them apart; nothing is placed")
    games = [_as_game(g) for g in stored]
    nxt = {g.id: (games[i + 1] if i + 1 < len(games) else None) for i, g in enumerate(games)}
    # M is used by A; a game a stored row outside the chain holds a side of is used by its holder
    used = {mid: anchor}
    for ev in sorted(by_ev):
        if ev != anchor and ev not in chain_evs:
            for r in by_ev[ev]:
                if r["match_id"] is not None:
                    used.setdefault(r["match_id"], ev)
    head.append(f"  games after {anchor}'s clock through {last_day}: "
                + ("; ".join(f"{g.id} {km.et_text(g.utc_date)} {g.status}"
                             + (f" [used by {used[g.id]}]" if g.id in used else "") for g in games) or "none"))

    # THE COUNT: each chain event in order takes the first unused game; a ruled event is counted on its own match
    taken, stopped, events = set(used), None, []
    for k, ev, kind, ruled_on in chain:
        rows = by_ev[ev]
        clock = km.ticker_stamp(_mks(rows)[0])[1]
        out = {"k": k, "event": ev, "kind": kind, "game": None, "lines": [], "place": [], "verdicts": {}}
        events.append(out)
        lines = out["lines"]
        if stopped is not None:
            lines.append(f"  [{k}] {ev} · clock {km.et_text(clock)} · not counted: the chain stopped at [{stopped}]")
            for r in rows:
                v = (f"counted: ruled on {ruled_on}; not read: the chain stopped at [{stopped}]" if kind == "counted"
                     else f"stays held: the chain stopped at [{stopped}]")
                out["verdicts"][r["ticker"]] = v
                lines.append(_chain_row(r, None, v))
            continue
        free = [g for g in games if g.id not in taken]
        g = free[0] if free else None
        out["game"] = g
        lines.append(f"  [{k}] {ev} · clock {km.et_text(clock)} · "
                     + (f"count's game {g.id} {km.et_text(g.utc_date)} {g.status} · {_h(g.utc_date - clock)}" if g
                        else "count's game: none left in the list"))
        if kind == "counted":
            if g is not None and g.id == ruled_on:
                v = f"counted: ruled on {ruled_on}; the count's game agrees"
                taken.add(g.id)
            else:
                v = (f"counted: ruled on {ruled_on}; the count's game is "
                     + (f"{g.id}" if g else "none (the list has no game left)") + ": the chain stops")
                stopped = k
            for r in rows:
                out["verdicts"][r["ticker"]] = v
                lines.append(_chain_row(r, g, v))
            continue
        # a MEMBER: placed on the count's game when every row passes (a) the clock check or (b) the settlement
        # bracket, a result mismatch refusing under both (addendum 148 item 2); else it stays held and the chain STOPs
        fails: dict[str, str] = {}
        plans: dict[str, tuple] = {}
        if g is None:
            for r in rows:
                fails[r["ticker"]] = "no game of the pair left in the list"
        elif g.status not in ("scheduled", "finished"):
            for r in rows:
                fails[r["ticker"]] = f"game {g.id} is {g.status}"
        else:
            gap = abs(g.utc_date - clock)
            tie = [o for o in free[1:] if abs(o.utc_date - clock) <= km.MAX_TICK_DRIFT]
            clock_why = (None if gap <= km.MAX_TICK_DRIFT and not tie
                         else f"by clock {_h(g.utc_date - clock)} > {_h(km.MAX_TICK_DRIFT)} (MAX_TICK_DRIFT)"
                         if gap > km.MAX_TICK_DRIFT
                         else f"by clock: the clock also fits {tie[0].id} {km.et_text(tie[0].utc_date)}")
            nx = nxt[g.id]
            for r in rows:
                t = r["ticker"]
                try:
                    tg = _ruled_target(rs, r, g.id, adapter)
                except ValueError as e:
                    fails[t] = str(e).replace("REFUSED: ", "", 1)
                    continue
                side, res, st = tg["side"], r["kalshi_result"], r["settled_time"]
                if g.winner is not None and res in ("yes", "no") and (res == "yes") != (g.winner == side):
                    fails[t] = f"result {res}, {side} {'won' if g.winner == side else 'lost'}"
                    continue
                if clock_why is None:
                    plans[t] = (r, tg, f"by clock {_h(g.utc_date - clock)}")
                    continue
                if g.status != "finished":
                    b_why = f"game {g.id} is {g.status}, not finished"
                elif g.winner is None:
                    b_why = f"no winner stored for game {g.id}"
                elif res not in ("yes", "no"):
                    b_why = "no result stored for the leg"
                elif st is None:
                    b_why = "no settled_time"
                elif not st > g.utc_date:
                    b_why = f"settled {st:%Y-%m-%d %H:%M:%S}Z, not after game {g.id}'s kickoff"
                elif nx is not None and not st < nx.utc_date:
                    b_why = (f"settled {st:%Y-%m-%d %H:%M:%S}Z, not before the next game {nx.id}'s kickoff "
                             f"{km.et_text(nx.utc_date)}")
                else:
                    b_why = None
                if b_why is None:
                    plans[t] = (r, tg, f"by settlement {_signed_h(st - g.utc_date)}, "
                                + (f"before {nx.id} {km.et_text(nx.utc_date)}" if nx
                                   else f"no next game of the pair through {last_day}"))
                else:
                    fails[t] = f"{clock_why}; by settlement: {b_why}"
        if fails:
            stopped = k
            for r in rows:
                v = ("stays held: " + (fails.get(r["ticker"]) or "the event is placed on all its legs or on none")
                     + "; the chain stops")
                out["verdicts"][r["ticker"]] = v
                lines.append(_chain_row(r, g, v))
            continue
        taken.add(g.id)
        for r in rows:
            row, tg, how = plans[r["ticker"]]
            v = f"PLACE {tg['side']} {how}"
            out["verdicts"][r["ticker"]] = v
            item = {"line": _chain_row(r, g, v), "before": row, "tg": tg, "k": k,
                    "part": CHAIN_NOTE.format(anchor=anchor, k=k, how=how)}
            lines.append(item)
            out["place"].append(item)
    # two rows the chain places on one side of one game (an event with a third leg naming one of its two names): the
    # write's own clash read does not see an earlier row of the same transaction (autoflush is off), so the plan
    # refuses; place-held, one row a call, is untouched
    on_side: dict = {}
    for it in (it for e in events for it in e["place"]):
        on_side.setdefault((it["tg"]["match_id"], it["tg"]["side"]), []).append(it["before"]["ticker"])
    twice = {k: ts for k, ts in on_side.items() if len(ts) > 1}
    if twice:
        what = "; ".join(f"match {gid} {sd} would be taken by {len(ts)} rows ({', '.join(sorted(ts))})"
                         for (gid, sd), ts in sorted(twice.items()))
        raise ValueError(f"REFUSED: {what}: two settled markets are never stored on one side of one game; nothing is "
                         "placed")
    tail = []
    if end is not None:
        k, ev, why = end
        tail.append(f"  [{k}] {ev} · clock {km.et_text(km.ticker_stamp(_mks(by_ev[ev])[0])[1])} · END: {why}")
        tail += [_chain_row(r, None, f"END: {why}") for r in by_ev[ev]]
    # held rows naming A that the chain does not read
    outside = []
    for ev in sorted(by_ev, key=lambda e: (info[e][1] if info.get(e) else date.min, e)):
        if ev in chain_evs:
            continue
        hits = [r["ticker"] for r in by_ev[ev] if is_held(r["match_id"], r["notes"])
                and _HOLD_RX.search(r["notes"]).group(1) == anchor]
        if not hits:
            continue
        inf = info.get(ev)
        if end is not None and ev == end[1]:
            why = f"the END at [{end[0]}]: {end[2]}"
        elif inf is None:
            why = "its stored rows are not two legs of a clock event: not read (an event the table does not hold "
            why += "whole is invisible to the count)"
        elif inf[0] != pair:
            why = f"not of {anchor}'s pair"
        elif (inf[1], ev) <= (a_day, anchor):
            why = f"not after {anchor} in chain order"
        elif (inf[1] - a_day).days > HOLD_BOUND_DAYS:
            why = f"{(inf[1] - a_day).days} days after {anchor}: past N1's {HOLD_BOUND_DAYS}"
        else:
            why = f"after the END at [{end[0]}]" if end else "outside the chain"
        outside.append(f"{', '.join(hits)} ({why})")
    if outside:
        tail.append(f"  held rows naming {anchor} outside the chain: {'; '.join(outside)}")
    return {"anchor": anchor, "series": series, "head": head, "events": events, "tail": tail, "end": end,
            "stopped": stopped, "untaken": [g.id for g in games if g.id not in taken]}


def place_chain(anchor: str, ruling: str, *, dry_run: bool = False, adapter=None, echo=print,
                now: datetime | None = None, guard=None) -> dict:
    """`kalshi-history place-chain --anchor EVENT --ruling R (--backup PATH | --dry-run)`, THE ANCHORED CHAIN (ARCHITECT
    2026-10-20, addendum 148 item 2, on the design of #630; the block above quotes it). From one anchor A (an event out
    of step on its own date, ruled into place on both legs by place-held on one match M), the chain is the pair's events
    after A in the hold's chain order, within N1 (1-10 days after A), up to the first that ENDs it: an event IN STEP (a
    row placed by the ingest), refused, of mixed legs, held behind another event, or naming A unsettled. The list is the
    pair's games from A's ticker clock, the games A's two names fit one each (kalshi_match.fit, as place-held fits its
    match; fitted games, M with them, of more than one pair of teams refuse, as the matcher refuses PAIR_TIE), M used by
    A and a game a stored row outside the chain holds a side of used by its holder; each chain event in order takes the
    first unused game. A ruled event is counted on its own match, and the chain stops where that is not the count's
    game. A MEMBER (every row held, naming A out of step, N2) is placed on the count's game when each of its rows passes
    (a) the clock check (|kickoff − ticker clock| <= MAX_TICK_DRIFT and no other unused game within 2h) or (b) the
    settlement bracket (settled after the game's kickoff and before the next game's in the list, or no next game in it;
    the game FINISHED with a stored winner; the leg's kalshi_result agrees), a result mismatch refusing under both; the
    game must be SCHEDULED or FINISHED (a LIVE one holds). A member that passes neither stays held and the chain STOPs.

    The table and the stored games only, no exchange call to find the chain (Q11). Every refusal of the plan (ValueError
    "REFUSED: ...": the anchor, the list, two rows the chain would place on one side of one game, the notes cap) is read
    before anything is printed; the backup check, the cutoff that cannot be read, a candle call that fails for now and the
    write's re-reads refuse after the plan's lines are printed, and write nothing. Each row placed is placed as place_held places it (its lines, the
    candles read then on the game's kickoff, the cutoff read once for the chain), its notes the stored notes, then
    "placed by ruling: <A's ruling>", then "placed by the chain of <A> [k]: <how>", then what the candles said (the
    2000-character cap). A candle call that fails for now on any row writes nothing (all or nothing). The write is one
    transaction, each row read again as a held row and its side read again. `guard` (the CLI's backup check) is called
    once, after every refusal of the plan is read and before the first candle call, and only when there is a row to
    write; never under dry_run. dry_run makes every read, the candle calls included, and writes nothing. A chain with no
    member prints and returns (exit 0). Returns {"plan", "placed": [rows as written], "written": bool}."""
    from sqlalchemy import inspect

    from src.adapters.kalshi import KalshiAdapter
    from src.db.database import session_scope
    from src.timeutil import utc_now_naive
    from src.walters.venue_quote_age import readonly_session

    anchor, ruling = (anchor or "").strip(), " ".join((ruling or "").split())
    if not ruling:
        raise ValueError("REFUSED: --ruling is empty: the chain names the anchor's own ruling")
    if not anchor:
        raise ValueError("REFUSED: --anchor is empty: the chain is read from one anchor event")
    adapter = adapter or KalshiAdapter()
    at = now or utc_now_naive()
    with readonly_session() as rs:
        if not inspect(rs.get_bind()).has_table(TABLE):
            raise ValueError(f"REFUSED: {TABLE} does not exist: no row to place")
        ready = migrated(rs)
        plan = _plan_chain(rs, anchor, ruling, adapter)
    if not dry_run and not ready:
        raise ValueError(f"REFUSED: {TABLE} is not migrated (no migration marker {MIGRATION_MARKER}): nothing is "
                         "written; --dry-run reads without it")
    items = [it for ev in plan["events"] for it in ev["place"]]
    for it in items:
        if len("; ".join(x for x in (it["before"]["notes"], f"{RULED_NOTE}{ruling}", it["part"]) if x)) + 200 > 2000:
            raise ValueError(f"REFUSED: the notes of {it['before']['ticker']} would pass the column's 2000 characters: "
                             "nothing is written")
    echo(f"kalshi-history place-chain {anchor} · "
         + ("DRY RUN: nothing is written" if dry_run else f"writes the chain's rows of {TABLE}, in one transaction")
         + f" · ruling: {ruling}")
    for ln in plan["head"]:
        echo(ln)
    if items and not dry_run and guard is not None:
        guard()
    calls = Calls(adapter, 3 * (1 + len(items)))         # the cutoff, then one candle call per row, each with the two
    cut: list = []                                        # 429 retries of addendum 104 item 2 (PLACE_HELD_CALLS, per row)

    def cutoff_of():
        if not cut:
            cut.append(_read_cutoff(calls))
        return cut[0]

    def sub(s):
        echo(f"    {s}")
    placed = []
    for ev in plan["events"]:
        for ln in ev["lines"]:
            if isinstance(ln, str):
                echo(ln)
                continue
            echo(ln["line"])
            before, tg = ln["before"], ln["tg"]
            sub(f"  before: {row_line(before)}")
            sub(_target_line(tg))
            after = _placed_after(before, tg, at, (f"{RULED_NOTE}{ruling}", ln["part"]), calls, cutoff_of, sub)
            sub(f"  after:  {row_line(after)}")
            placed.append((ln, after))
    for ln in plan["tail"]:
        echo(ln)
    members = [ev for ev in plan["events"] if ev["kind"] == "member"]
    held = sum(1 for ev in members for v in ev["verdicts"].values() if v.startswith("stays held"))
    closing = (f"  chain: {len(plan['events'])} event(s) · {len(members)} member(s) · {len(items)} row(s) to place · "
               f"{held} stay held · games no event took: {', '.join(str(i) for i in plan['untaken']) or 'none'} · "
               f"calls {calls.made} of {calls.cap}")
    if dry_run or not items:
        echo(closing + (" · DRY RUN: nothing written" if dry_run else " · nothing to place: nothing written"))
        return {"plan": plan, "placed": [a for _, a in placed], "written": False}
    echo(closing)
    with session_scope() as sess:
        for ln, after in placed:
            _write_placed(sess, ln["before"], after, held_only=True)
    for ln, after in placed:
        echo(f"  ✓ placed: {after['ticker']} on match {after['match_id']} {after['side']} (the chain of {anchor} "
             f"[{ln['k']}])")
    echo(f"  ✓ written: {len(placed)} row(s) of {TABLE}, in one transaction")
    return {"plan": plan, "placed": [a for _, a in placed], "written": True}


def list_chains(series: str, *, adapter=None, echo=print) -> dict:
    """`kalshi-history place-chain --list --series S` (ARCHITECT 2026-10-20, addendum 148 item 2, Q12: "the listing
    mode in the same PR, its console in the body: yes"): READ-ONLY, from the table and the stored games; no network
    call, no --ruling, nothing written. Each held row of the series, by the earlier event its note names (that event's
    state in the table: refused, ruled (with its ruling, the --ruling a chain from it names), placed by the ingest,
    held, mixed legs, not stored) and its clock, with the held event's rows (why, result, settled) and the pair's games
    on its day (the matcher's day rule, its date and a day either side) with kickoff, status, the gap from its clock
    and the stored rows holding each. Anchors are ruled from it. Returns {"held_rows", "held_events", "named": {E0:
    state}}."""
    from sqlalchemy import inspect, select

    from src.adapters.kalshi import KalshiAdapter
    from src.db.schema import Competition, KalshiSettledMarket as K
    from src.ingestion.kalshi_sync import stored_games
    from src.walters.venue_quote_age import readonly_session

    series = (series or "").strip()
    adapter = adapter or KalshiAdapter()
    comp_code, soccer = competition_for(series, adapter)
    if comp_code is None:
        raise ValueError(f"REFUSED: {series} is not a series the syncs read (venue.KALSHI_SERIES_BY_COMPETITION, "
                         "KalshiAdapter.SOCCER_GAME_SERIES): nothing is listed")
    is_tie = adapter.is_tie_market if soccer else (lambda m: False)
    with readonly_session() as rs:
        if not inspect(rs.get_bind()).has_table(TABLE):
            raise ValueError(f"REFUSED: {TABLE} does not exist: no held row to list")
        comp_id = rs.execute(select(Competition.id).where(Competition.code == comp_code)).scalar_one_or_none()
        if comp_id is None:
            raise ValueError(f"REFUSED: competition {comp_code} (of {series}) is not in the DB: nothing is listed")
        cols = K.__table__.c.keys()
        by_ev: dict[str, list[dict]] = {}
        for o in rs.execute(select(K).where(K.series == series)).scalars():
            r = {c: getattr(o, c) for c in cols}
            by_ev.setdefault(_ev(r), []).append(r)
        holders: dict[int, set] = {}
        for ev, rws in by_ev.items():
            rws.sort(key=lambda r: r["ticker"])
            for r in rws:
                if r["match_id"] is not None:
                    holders.setdefault(r["match_id"], set()).add(ev)
        held_evs = {ev: [r for r in rws if is_held(r["match_id"], r["notes"])] for ev, rws in by_ev.items()}
        held_evs = {ev: hs for ev, hs in held_evs.items() if hs}
        near = {}
        for ev in held_evs:
            mks = _mks(by_ev[ev])
            names = km._names(mks, mks[0], is_tie)
            day = km.ticker_stamp(mks[0])[0]
            fits = (km._best_fits(names, day, stored_games(rs, [comp_id], mks))
                    if len(names) == 2 and day is not None else [])
            near[ev] = sorted(((g.id, g.utc_date, str(getattr(g.status, "value", g.status))) for g, _ in fits),
                              key=lambda x: (x[1], x[0]))
    by_e0: dict[str, list[str]] = {}
    for ev, hs in held_evs.items():
        for e0 in sorted({_HOLD_RX.search(r["notes"]).group(1) for r in hs}):
            by_e0.setdefault(e0, []).append(ev)

    def day_of(ev):
        return km.ticker_stamp({"ticker": ev, "event_ticker": ev})

    def state(e0):
        rws = by_ev.get(e0)
        if not rws:
            return "not stored", "not stored in the table"
        kinds = {_row_state(r)[0] for r in rws}
        if kinds == {"ruled"} and len({r["match_id"] for r in rws}) == 1:
            rulings = sorted({x for r in rws for x in _RULED_RX.findall(r["notes"] or "")})
            legs = ", ".join(f"{r['ticker']} {r['side']}" for r in rws)
            return "ruled", f"ruled on {rws[0]['match_id']} ({legs}) · placed by ruling: {' | '.join(rulings)}"
        if kinds == {"ingest"}:
            return "placed", f"placed by the ingest on {', '.join(sorted({str(r['match_id']) for r in rws}))}"
        if kinds == {"refused"}:
            return "refused", f"refused: {'; '.join(sorted({_refusal(r['notes']) for r in rws}))}"
        if kinds == {"held"}:
            return "held", "held: " + "; ".join(sorted({_row_state(r)[1] for r in rws}))
        return "mixed", "mixed legs: " + "; ".join(f"{r['ticker']} {_row_state(r)[1]}" for r in rws)

    echo(f"kalshi-history place-chain --list {series} ({comp_code}) · READ-ONLY: no network call, nothing written")
    named = {}
    for e0 in sorted(by_e0, key=lambda e: (day_of(e)[0] or date.min, e)):
        kind, words = state(e0)
        named[e0] = kind
        echo(f"  E0 {e0} · clock {km.et_text(day_of(e0)[1])} · {words}")
        for ev in sorted(by_e0[e0], key=lambda e: (day_of(e)[0] or date.min, e)):
            clock = km.ticker_stamp(_mks(by_ev[ev])[0])[1]
            rws = "; ".join(
                f"{r['ticker']} {_HOLD_RX.search(r['notes']).group(2)} result {r['kalshi_result'] or '-'} settled "
                + (f"{r['settled_time']:%Y-%m-%d %H:%M:%S}Z" if r["settled_time"] else "-")
                for r in held_evs[ev] if _HOLD_RX.search(r["notes"]).group(1) == e0)
            echo(f"    held {ev} · clock {km.et_text(clock)} · {rws}")
            echo("      the pair's games on its day: "
                 + ("; ".join(f"{gid} {km.et_text(ko)} {st}" + (f" ({_signed_h(ko - clock)})" if clock else "")
                              + (f" · held by {', '.join(sorted(holders[gid]))}" if gid in holders else "")
                              for gid, ko, st in near[ev]) or "none stored"))
    n_rows = sum(len(hs) for hs in held_evs.values())
    tally = Counter(named.values())
    echo(f"  held rows: {n_rows} in {len(held_evs)} event(s) · events they name: {len(named)} ("
         + ", ".join(f"{k} {tally.get(k, 0)}" for k in ("refused", "ruled", "placed", "held", "mixed", "not stored"))
         + ") · READ-ONLY: nothing written")
    return {"held_rows": n_rows, "held_events": len(held_evs), "named": named}
