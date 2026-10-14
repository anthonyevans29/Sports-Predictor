"""
KALSHI SETTLED-MARKET HISTORY, the ingest (ARCHITECT 2026-10-14 10:01 ET, addendum 67 item 1; K-track data lane,
Issue #519), verbatim in part:

"What it is: a stored record of every settled Kalshi game market in our series, with the last two-sided quote before
kickoff, so the backtests and the older-season tests have a Kalshi close where no book close exists. Read-only against
the exchange (public endpoints, no key); it writes ONE new table and nothing else — no odds snapshot, no close used by
grading, no prediction row is touched; grading keeps reading what it reads today until a later ruling says otherwise."

    python cli.py kalshi-history --series KXMLBGAME [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--dry-run]
                                 [--max-calls N]

How it reads, so the receipt can be checked against it:
- The cutoff first (/historical/cutoff, one call), printed. Then both lists of the series, paged by cursor alone (no
  time filter is sent: the probe found max_close_ts does not narrow the historical list): /historical/markets
  (source 'historical', settled before the cutoff) and /markets?status=settled (source 'live'). A page that fails
  ends that list and is printed; it is never retried.
- --since / --until keep the markets whose game day falls inside them: the ticker's date (US Eastern, as the matcher
  reads it), else the close_time's UTC date; a market with neither is counted and left out when either is given.
- A market already in the table is counted and skipped: its candles are never fetched twice, and a run resumes where
  the last one stopped by the table itself.
- Matching, per event: the event's markets go through the shared matcher (kalshi_match.place: the same fit, the same
  pins, the same refusals) against the stored games of the series' own competition on the event's days, loaded as
  the syncs load them (kalshi_sync.stored_games' span, kalshi_match.day_span). Four refusals of the live sync are
  conditions of an open market and cannot hold for a settled one, so they are not read: in play (every settled game
  has started: `now` is set before any game), no price and the spread guard (a settled market's quote is its
  candles', read below), and the run's window (the window here is --since/--until, applied above). Each event is
  placed alone, so "behind an event out of step" (a rule between open events) never fires. Every other refusal is the
  matcher's own, under its own reason. A refused market is stored with match_id and side null and the reason in notes,
  never guessed, and the refusals are listed at the end of the run by reason, as the replay lists them.
- Kickoff for the window: the stored game's kickoff when matched; when unmatched, the ticker's date-and-time when the
  ticker carries a clock (the MLB shape); else no candles are fetched and notes says so. Candles:
  /historical/markets/{ticker}/candlesticks for a historical market, /series/{series}/markets/{ticker}/candlesticks for
  a live one; period_interval=1, start_ts = kickoff - 6h, end_ts = close_time. A market with no close_time fetches no
  candles (notes says so). A candle call that fails stores nothing for that market (it is listed; the next run asks
  again), and is never retried in the run.
- Per market from its candles: last_ts / last_bid / last_ask / last_mid of the last candle at or before kickoff that
  carries both a bid and an ask (a candle carries one when the shape's bid and ask keys hold a price in 0..1; a null
  is never filled, and the mid is the two's mean); candles_6h (candles whose end falls in the six hours up to
  kickoff), candles_two_sided (of those, the ones carrying both), gaps (the minutes of those six hours with no candle:
  360 less the distinct minutes present), raw_first_candle (the first candle returned, whole).
- --max-calls (default 300; the probe's whole run was 241): every call counts. At the cap the run stops cleanly: what
  it holds is stored (unless --dry-run), and it prints where it stopped (the list and its cursor, or the market whose
  candles it would have fetched next).
- --dry-run makes every read, prints what would be stored, and writes nothing (the table need not exist).

The payloads' keys (law 1: "read each by its own keys from the kept payloads of 2026-10-14 under logs/ (law 1:
enumerate the keys from those files, not from memory)"): KEYS below is the one place they are named. As built here
they are the architect's receipt of the probe's console (addendum 66 item 6: "the historical endpoint's candles carry
yes_bid.close / yes_ask.close / volume / open_interest (no _dollars suffix); the live series endpoint's carry
close_dollars / volume_fp / open_interest_fp") and the probe's own reader (scripts/kalshi_history_probe.py: markets /
cursor, candlesticks, end_period_ts, ticker / event_ticker / close_time / result). The kept files have not reached the
session that wrote this; tests/fixtures/kalshi_history/ holds them once they do, and KEYS is checked against them
(settled_time's key is read from them; until then settled_time is null).
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import requests

from src.ingestion import kalshi_match as km

TABLE = "kalshi_settled_markets"
MAX_CALLS = 300                  # the ruling's default
WINDOW_H = 6                     # "start_ts = kickoff − 6h"
PAGE_LIMIT = 200                 # the adapter's own page size (KalshiAdapter.open_markets_for_series)
MAX_PAGES = 5000                 # a guard against a cursor that never ends; reaching it is printed, never silent
EPOCH = datetime(1970, 1, 1)     # `now` for the matcher: before every game, so its in-play refusal never reads

# The one place the payloads' keys are named (see the docstring: the receipt's keys until the kept files are read).
KEYS = {
    "cutoff": "market_settled_ts",
    "list": "markets", "cursor": "cursor",
    "ticker": "ticker", "event": "event_ticker", "yes_sub_title": "yes_sub_title", "result": "result",
    "close_time": "close_time", "settled_time": None,          # None: not yet enumerated from the kept files
    "candles": "candlesticks", "end": "end_period_ts",
    # (the bid's parent, the ask's parent, the leaf) per candle shape; each shape is read by its own keys only
    "historical": ("yes_bid", "yes_ask", "close"),
    "live": ("yes_bid", "yes_ask", "close_dollars"),
}
SOURCES = (("historical", "historical/markets", {}), ("live", "markets", {"status": "settled"}))


class Capped(Exception):
    """The run reached --max-calls."""


def parse_ts(v) -> datetime | None:
    """An ISO time (Z or offset) or epoch seconds -> naive UTC; None when it is neither."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return datetime.fromtimestamp(v, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(v, str) and v.strip():
        try:
            dt = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return (dt.astimezone(timezone.utc) if dt.tzinfo else dt).replace(tzinfo=None)
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
        two = bid is not None and ask is not None
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


class Calls:
    """Every call to the exchange, counted against the cap; a failed call is recorded, never retried."""

    def __init__(self, adapter, cap: int):
        self.adapter, self.cap = adapter, cap
        self.made = 0
        self.failed: list[str] = []

    def get(self, path: str, params: dict | None = None):
        """(answer, None) or (None, why). Raises Capped before a call past the cap."""
        if self.made >= self.cap:
            raise Capped()
        self.made += 1
        try:
            data = self.adapter._get(path, params)
        except requests.HTTPError as e:
            resp = getattr(e, "response", None)
            why = f"status {getattr(resp, 'status_code', None)}"
        except Exception as e:  # noqa: BLE001 - a call that fails is recorded and the run goes on without it
            why = f"{type(e).__name__}: {e}"
        else:
            if isinstance(data, dict):
                return data, None
            why = "an answer that is not an object"
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


def list_source(calls: Calls, run: Run, source: str, path: str, params: dict, series: str) -> list[dict]:
    """Every market of one list, paged to its end by cursor. A page that fails ends the list (printed); the cap stops
    the run, naming the list and the cursor it stopped at."""
    markets, cursor = [], None
    for n in range(MAX_PAGES):
        p = {"series_ticker": series, **params, "limit": PAGE_LIMIT, **({"cursor": cursor} if cursor else {})}
        try:
            data, why = calls.get(path, p)
        except Capped:
            run.stopped = (f"the cap ({calls.cap} calls) while listing {source} ({path}), before page {n + 1}"
                           f"{f' at cursor {cursor}' if cursor else ''}")
            raise
        if data is None:
            run.list_notes.append(f"{source}: page {n + 1} of {path} failed ({why}): the list stops here")
            break
        page = data.get(KEYS["list"])
        if not isinstance(page, list):
            run.list_notes.append(f"{source}: page {n + 1} of {path} holds no '{KEYS['list']}' list: the list stops")
            break
        markets.extend(m for m in page if isinstance(m, dict))
        cursor = data.get(KEYS["cursor"])
        if not cursor:
            break
    else:
        run.list_notes.append(f"{source}: {MAX_PAGES} pages read and the cursor goes on: the list stops here")
    run.listed[source] += len(markets)
    return markets


def place_events(markets: list[dict], games: list, is_tie) -> tuple[dict, dict, list]:
    """{ticker: (game id, kickoff, side)} placed, {ticker: reason} refused, the matcher's lines. Each event is placed
    alone, on the stored games of its own days (kalshi_match.day_span, as kalshi_sync.stored_games loads them)."""
    import bisect
    by_event: dict[str, list[dict]] = {}
    for m in markets:
        by_event.setdefault(km.event_of(m), []).append(m)
    gs = sorted((g for g in games if g.utc_date), key=lambda g: g.utc_date)
    keys = [g.utc_date for g in gs]
    placed, why, lines = {}, {}, []
    for ev, mks in by_event.items():
        span = km.day_span(mks)
        day_games = gs[bisect.bisect_left(keys, span[0]):bisect.bisect_right(keys, span[1])] if span else []
        res = km.place(mks, day_games, now=EPOCH, lo=datetime.min, hi=datetime.max, is_tie=is_tie,
                       implied_prob=_settled_price)
        by_id = {g.id: g for g in day_games}
        for (mid, side), mk in res.placed.items():
            placed[mk.get(KEYS["ticker"])] = (mid, by_id[mid].utc_date, side)
        why.update(res.why)
        lines.extend(res.lines)
    return placed, why, lines


def _new_row(series: str, source: str, m: dict, fetched_at: datetime, placed: dict, why: dict, run: "Run") -> tuple:
    """(row, notes, kickoff or None) for one market before its candles."""
    ticker = m.get(KEYS["ticker"])
    mid, ko, side = placed.get(ticker, (None, None, None))
    row = {"ticker": ticker, "event_ticker": m.get(KEYS["event"]), "series": series, "side": side, "match_id": mid,
           "yes_sub_title": m.get(KEYS["yes_sub_title"]), "kalshi_result": None,
           "close_time": parse_ts(m.get(KEYS["close_time"])),
           "settled_time": parse_ts(m.get(KEYS["settled_time"])) if KEYS["settled_time"] else None,
           "source": source, "fetched_at": fetched_at, "last_ts": None, "last_bid": None, "last_ask": None,
           "last_mid": None, "candles_6h": None, "candles_two_sided": None, "gaps": None, "raw_first_candle": None}
    notes = []
    res = m.get(KEYS["result"])
    if res in ("yes", "no"):
        row["kalshi_result"] = res
    elif res not in (None, ""):
        notes.append(f"result as read: {res!r}")
    if mid is None:
        notes.append(f"refused by the matcher: {why.get(ticker) or 'not placed'}")
    kickoff = ko
    if kickoff is None:
        _, kickoff = km.ticker_stamp(m)
    nok = None
    if kickoff is None:
        nok = "no candles fetched: unmatched and the ticker carries no clock"
    elif row["close_time"] is None:
        nok = "no candles fetched: the market carries no close_time"
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
    if not has_table and not dry_run:
        raise ValueError(f"REFUSED: {TABLE} does not exist (run migrate_kalshi_settled_markets.py after the daily "
                         ".backup); --dry-run reads without it")
    is_tie = adapter.is_tie_market if soccer else None
    calls = Calls(adapter, max_calls)
    echo(f"kalshi-history {series} ({comp_code}{', three legs' if soccer else ''}) · "
         f"{'DRY RUN: nothing is written' if dry_run else f'writes {TABLE} only'} · max calls {max_calls}")

    # 1. the cutoff and both lists (network)
    listed: list[tuple[str, dict]] = []
    try:
        cut, cwhy = calls.get("historical/cutoff")
        run.cutoff = cut.get(KEYS["cutoff"]) if cut else None
        echo(f"  cutoff {KEYS['cutoff']}: {run.cutoff or f'not read ({cwhy})'}")
        for source, path, params in SOURCES:
            listed += [(source, m) for m in list_source(calls, run, source, path, params, series)]
    except Capped:
        # a list cut short is never half-read: an event split across the cut would be matched on part of its legs
        listed = []
        run.stopped += "; nothing is placed or stored from a list cut short (a larger --max-calls lists it whole)"

    # 2. the matching: every listed market in range, stored or not, so an event is always placed on all its legs
    in_range, seen = [], set()
    for source, m in listed:
        t = m.get(KEYS["ticker"])
        if not t:
            run.no_ticker += 1
            continue
        if t in seen:
            run.duplicates += 1
            continue
        seen.add(t)
        day = game_day(m)
        if (since or until) and day is None:
            run.no_day += 1
            continue
        if (since and day < since) or (until and day > until):
            run.out_of_range += 1
            continue
        in_range.append((source, m))
    stored: set = set()
    placed, why = {}, {}
    if in_range:
        with readonly_session() as rs:
            if has_table:
                stored = set(rs.execute(select(KalshiSettledMarket.ticker)).scalars())
            comp_id = rs.execute(select(Competition.id).where(Competition.code == comp_code)).scalar_one_or_none()
            if comp_id is None:
                run.list_notes.append(f"competition {comp_code} is not in the DB: every market is refused for no fit")
            games = stored_games(rs, [comp_id] if comp_id else [], [m for _, m in in_range])
            placed, why, run.refused_lines = place_events([m for _, m in in_range], games, is_tie)

    # 3. the candles (network), market by market, for the ones not yet stored
    todo = [(s, m) for s, m in in_range if m.get(KEYS["ticker"]) not in stored]
    run.already = len(in_range) - len(todo)
    for i, (source, m) in enumerate(todo):
        row, notes, kickoff = _new_row(series, source, m, fetched_at, placed, why, run)
        if kickoff is not None:
            ticker = row["ticker"]
            path = (f"historical/markets/{ticker}/candlesticks" if source == "historical"
                    else f"series/{series}/markets/{ticker}/candlesticks")
            params = {"start_ts": int((kickoff - timedelta(hours=WINDOW_H)).replace(tzinfo=timezone.utc).timestamp()),
                      "end_ts": int(row["close_time"].replace(tzinfo=timezone.utc).timestamp()),
                      "period_interval": 1}
            try:
                data, cwhy = calls.get(path, params)
            except Capped:
                run.stopped = (f"the cap ({calls.cap} calls) before the candles of {ticker} ({source}); "
                               f"{len(todo) - i} market(s) left for the next run, which skips the stored ones")
                break
            run.candle_calls += 1
            candles = data.get(KEYS["candles"]) if data else None
            if not isinstance(candles, list):
                run.candle_failed.append((ticker, cwhy or f"no '{KEYS['candles']}' list"))
                continue
            row.update(window_stats(candles, kickoff, source))
            if row["last_ts"] is None:
                notes.append("no two-sided candle at or before kickoff")
        row["notes"] = "; ".join(notes) or None
        run.rows.append(row)
        if row["match_id"] is None:
            run.refused[why.get(row["ticker"]) or "not placed"] += 1

    # 4. the insert: this table and nothing else
    if not dry_run and run.rows:
        with session_scope() as sess:
            sess.add_all(KalshiSettledMarket(**r) for r in run.rows)
    _receipt(run, calls, echo)
    return run


def _receipt(run: Run, calls: Calls, echo) -> None:
    w = "would be stored" if run.dry_run else "stored"
    echo(f"  cutoff read at the start: {run.cutoff or 'none'}")
    echo(f"  markets listed: {sum(run.listed.values())} (historical {run.listed['historical']}, "
         f"live settled {run.listed['live']})" + (f" · outside --since/--until {run.out_of_range}"
                                                  if run.out_of_range else "")
         + (f" · no game day to filter {run.no_day}" if run.no_day else "")
         + (f" · no ticker {run.no_ticker}" if run.no_ticker else "")
         + (f" · listed twice (the first kept) {run.duplicates}" if run.duplicates else ""))
    for note in run.list_notes:
        echo(f"  ✗ {note}")
    placed = sum(1 for r in run.rows if r["match_id"] is not None)
    echo(f"  {w}: {len(run.rows)} (placed on a stored game {placed}, refused and kept {len(run.rows) - placed}) · "
         f"already stored {run.already}")
    if run.refused:
        echo("  refused by the matcher, by reason (kept with match_id null):")
        for r, n in sorted(run.refused.items(), key=lambda x: (-x[1], x[0])):
            echo(f"    {n:>5}  {r}")
        for ln in run.refused_lines:
            echo(ln)
    echo(f"  candle calls made: {run.candle_calls} · calls in all: {calls.made} of {calls.cap}")
    for nok, n in sorted(run.no_candles.items()):
        echo(f"    {n:>5}  {nok}")
    if run.candle_failed:
        echo(f"  ✗ candle calls that failed (nothing stored for them; the next run asks again): {len(run.candle_failed)}")
        for t, why in run.candle_failed:
            echo(f"    {t}: {why}")
    nolast = sum(1 for r in run.rows if r["last_ts"] is None)
    echo(f"  rows with last_ts null (no two-sided candle before kickoff, or no candles): {nolast}")
    if run.dry_run:
        for r in run.rows:
            q = (f"last {r['last_ts']:%Y-%m-%d %H:%M}Z bid {r['last_bid']} ask {r['last_ask']} mid {r['last_mid']}"
                 if r["last_ts"] else "no last quote")
            echo(f"    {r['ticker']} · {r['source']} · match {r['match_id'] or '-'} {r['side'] or '-'} · result "
                 f"{r['kalshi_result'] or '-'} · {q} · 6h {r['candles_6h']} two-sided {r['candles_two_sided']} gaps "
                 f"{r['gaps']}" + (f" · {r['notes']}" if r["notes"] else ""))
    if run.stopped:
        echo(f"  STOPPED at {run.stopped}")
