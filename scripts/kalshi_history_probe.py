"""
KALSHI HISTORY PROBE (ARCHITECT 2026-10-13 11:08 ET, addendum 60 item 7) — read-only.

The finding, verbatim: "Kalshi keeps the price history of its settled markets: the bid and the ask, minute by minute.
docs/historical_backfill_assessment.md (2026-07-06) lists odds history as not recoverable for past games; for a game
Kalshi listed, that no longer holds."

The probe, verbatim: "Read-only: no database, and nothing written but its own --out file and its kept payloads under
logs/. It follows scripts/lineup_history_probe.py: the base URL and the pace are the adapter's own, never from memory;
it never stops on an error; a payload that is missing is a finding; nothing it prints is cut; the whole output is
pasted to me."

  Q0  /historical/cutoff            the cutoff's four timestamps, and the answer whole
  Q1  per series the syncs read     (kalshi-replay's series_plan): the settled markets on both sides of the cutoff,
                                    /historical/markets paged to its end by cursor and /markets?status=settled paged
                                    the same way. Per series and side: markets, events, the first and the last
                                    close_time, and the events by month (a month is the month of the event's first
                                    close_time)
  Q2  per series, three events      its first, its middle one and its last, by close_time. For each market of the
                                    three: the one-minute candlesticks of the six hours before its close_time (a
                                    market of the historical list from /historical/markets/{ticker}/candlesticks, one
                                    of the live list from /series/{series}/markets/{ticker}/candlesticks). How many
                                    came back, how many carry both a bid and an ask, and the end time, yes_bid close
                                    and yes_ask close of the first, of every thirtieth and of the last
  Q3  the calls                     each call made, and each one refused with its status

The base URL is the adapter's (src/adapters/kalshi.py BASE, through KalshiAdapter._get); the pace is the adapter's
(it sends one request after another and sleeps between none, so this probe sleeps between none either). Paging is by
cursor alone: the architect's reads found max_close_ts does not narrow the historical list, so no time filter is sent.
It keeps one raw payload of each kind it meets under logs/ (public market data): the cutoff, a historical market list
page, a settled market list page, a historical candlestick reply and a live candlestick reply. The operator sends those
files with the console. Nothing is ingested and no table is touched.

    python3 scripts/kalshi_history_probe.py [--series KXNHLGAME ...] [--out probe.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.kalshi import KalshiAdapter  # noqa: E402
from src.ingestion.kalshi_replay import series_plan  # noqa: E402

CUTOFF_KEYS = ("market_settled_ts", "trades_created_ts", "orders_updated_ts", "market_positions_last_updated_ts")
PAGE_LIMIT = 200                 # the adapter's own page size (KalshiAdapter.open_markets_for_series)
WINDOW_H = 6                     # "the six hours before its close_time"
EVERY = 30                       # "of the first, of every thirtieth and of the last"
MAX_PAGES = 5000                 # a guard against a cursor that never ends; reaching it is printed, never silent


class Calls:
    """Every call the adapter makes in this run, with its status (Q3): the adapter's own _get is wrapped, so a call
    made inside the series plan is listed too. A call that fails is recorded and the probe goes on."""

    def __init__(self, adapter: KalshiAdapter):
        self.adapter = adapter
        self.made: list[dict] = []
        self._raw = adapter._get
        adapter._get = self._recorded

    def _recorded(self, path: str, params: dict | None = None):
        rec = {"path": path, "params": dict(params or {})}
        self.made.append(rec)
        try:
            data = self._raw(path, params)
        except requests.HTTPError as e:
            resp = getattr(e, "response", None)
            rec["status"] = getattr(resp, "status_code", None)
            rec["error"] = resp.text if resp is not None else str(e)
            raise
        except Exception as e:  # noqa: BLE001 - recorded, then raised to the adapter's own caller
            rec["status"] = None
            rec["error"] = f"{type(e).__name__}: {e}"
            raise
        rec["status"] = 200
        return data

    def get(self, path: str, params: dict | None = None):
        """(answer or None, status). Never raises."""
        try:
            data = self._recorded(path, params)
        except Exception:  # noqa: BLE001 - never stops: a failed call is a finding, already recorded
            return None, self.made[-1].get("status")
        if not isinstance(data, dict):
            self.made[-1]["error"] = f"an answer that is not an object: {json.dumps(data, default=str)}"
            return None, self.made[-1].get("status")
        return data, 200


class Keeper:
    """One raw payload of each kind, under logs/ (law 5: never under data/)."""

    def __init__(self, stamp: str, logs: Path | None = None):
        self.dir = Path(logs or ROOT / "logs")
        self.stamp = stamp
        self.kept: dict[str, str] = {}

    def keep(self, kind: str, payload) -> None:
        if kind in self.kept or payload is None:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"kalshi_history_{self.stamp}_{kind}.json"
        path.write_text(json.dumps(payload, indent=1, default=str))
        self.kept[kind] = str(path)


def parse_ts(v) -> datetime | None:
    """An ISO time (Z or offset) or epoch seconds -> aware UTC; None when it is neither."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return datetime.fromtimestamp(v, tz=timezone.utc)
    if isinstance(v, str) and v.strip():
        try:
            dt = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def iso(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else "-"


def page_all(calls: Calls, keeper: Keeper, path: str, params: dict, kind: str, echo=print) -> tuple[list, list]:
    """Every market of a list, paged to its end by cursor. (markets, notes); a page that fails ends the paging and
    is a note, never a stop."""
    markets, notes, cursor, seen = [], [], None, set()
    for n in range(MAX_PAGES):
        p = {**params, "limit": PAGE_LIMIT, **({"cursor": cursor} if cursor else {})}
        data, status = calls.get(path, p)
        if data is None:
            notes.append(f"page {n + 1} of {path} refused or failed (status {status}): the list stops here")
            break
        keeper.keep(kind, data)
        page = data.get("markets")
        if not isinstance(page, list):
            notes.append(f"page {n + 1} of {path}: no markets list; the answer whole: "
                         f"{json.dumps(data, sort_keys=True, default=str)}")
            break
        markets.extend(m for m in page if isinstance(m, dict))
        cursor = data.get("cursor")
        if not cursor:
            break
        if cursor in seen:
            notes.append(f"{path}: the cursor {cursor!r} came back twice; paging stops")
            break
        seen.add(cursor)
    else:
        notes.append(f"{path}: {MAX_PAGES} pages read and the cursor has not ended; paging stops")
    return markets, notes


def summarize(markets: list[dict]) -> dict:
    """Markets, events, first and last close_time, events by month (the month of an event's first close_time)."""
    closes = [(parse_ts(m.get("close_time")), m) for m in markets]
    timed = [(t, m) for t, m in closes if t is not None]
    first_close: dict[str, datetime] = {}
    for t, m in timed:
        ev = m.get("event_ticker")
        if ev is not None and (ev not in first_close or t < first_close[ev]):
            first_close[ev] = t
    events = {m.get("event_ticker") for m in markets if m.get("event_ticker") is not None}
    by_month = Counter(t.strftime("%Y-%m") for t in first_close.values())
    return {
        "markets": len(markets), "events": len(events),
        "markets_without_close_time": len(markets) - len(timed),
        "markets_without_event": sum(1 for m in markets if m.get("event_ticker") is None),
        "first_close": iso(min((t for t, _ in timed), default=None)),
        "last_close": iso(max((t for t, _ in timed), default=None)),
        "events_by_month": dict(sorted(by_month.items())),
    }


def three_events(sides: dict[str, list[dict]]) -> list[tuple[str, list[tuple[str, dict]]]]:
    """The first, the middle and the last event of the series by close_time, each with its markets and the side
    (historical or live) each market came from. Deduped."""
    by_event: dict[str, list[tuple[str, dict]]] = {}
    first: dict[str, datetime] = {}
    for side, markets in sides.items():
        for m in markets:
            ev, t = m.get("event_ticker"), parse_ts(m.get("close_time"))
            if ev is None or t is None:
                continue
            by_event.setdefault(ev, []).append((side, m))
            first[ev] = min(t, first.get(ev, t))
    order = sorted(first, key=lambda e: (first[e], e))
    if not order:
        return []
    picks, out = [order[0], order[len(order) // 2], order[-1]], []
    for ev in picks:
        if ev not in [e for e, _ in out]:
            out.append((ev, by_event[ev]))
    return out


def _close(c: dict, key: str):
    """A candlestick's close for yes_bid or yes_ask, as sent: the dollars field when there is one, else the close."""
    v = c.get(key)
    if isinstance(v, dict):
        for k in ("close_dollars", "close"):
            if v.get(k) is not None:
                return v.get(k)
        return None
    return v


def candle_lines(candles: list) -> tuple[dict, list[str]]:
    """Q2's counts and the lines of the first, every thirtieth and the last candlestick."""
    cs = [c for c in candles if isinstance(c, dict)]
    both = sum(1 for c in cs if _close(c, "yes_bid") is not None and _close(c, "yes_ask") is not None)
    idx = sorted(set(list(range(0, len(cs), EVERY)) + ([len(cs) - 1] if cs else [])))
    lines = []
    for i in idx:
        c = cs[i]
        end = c.get("end_period_ts")
        lines.append(f"#{i + 1} end {iso(parse_ts(end))} ({end!r}) · yes_bid close {_close(c, 'yes_bid')!r} · "
                     f"yes_ask close {_close(c, 'yes_ask')!r}")
    return {"returned": len(candles), "objects": len(cs), "with_bid_and_ask": both}, lines


def probe_series(calls: Calls, keeper: Keeper, plan: dict, echo=print) -> dict:
    series = plan["series"]
    echo(f"\n=== {series} ({plan['competition']}, path {plan['path']}) ===")
    hist, hnotes = page_all(calls, keeper, "historical/markets", {"series_ticker": series},
                            "historical_markets_page", echo)
    live, lnotes = page_all(calls, keeper, "markets", {"series_ticker": series, "status": "settled"},
                            "settled_markets_page", echo)
    out = {"series": series, "competition": plan["competition"], "sides": {}, "candles": []}
    for side, markets, notes in (("historical", hist, hnotes), ("live settled", live, lnotes)):
        summ = summarize(markets)
        out["sides"][side] = {**summ, "notes": notes}
        echo(f"  Q1 {side}: {summ['markets']} markets · {summ['events']} events · first close {summ['first_close']} · "
             f"last close {summ['last_close']} · without close_time {summ['markets_without_close_time']} · "
             f"without event {summ['markets_without_event']}")
        echo(f"     events by month: {summ['events_by_month'] or 'none'}")
        for note in notes:
            echo(f"     ✗ {note}")
    both = summarize(hist + live)
    out["both"] = both
    echo(f"  Q1 both sides: {both['markets']} markets · {both['events']} events · first close {both['first_close']} · "
         f"last close {both['last_close']}")
    picks = three_events({"historical": hist, "live settled": live})
    if not picks:
        echo("  Q2: no event with a close_time on either side: nothing to sample")
    for ev, markets in picks:
        echo(f"  Q2 event {ev}: {len(markets)} market(s)")
        for side, m in markets:
            ticker, close = m.get("ticker"), parse_ts(m.get("close_time"))
            if not ticker or close is None:
                echo(f"    a market with no ticker or close_time: {json.dumps(m, sort_keys=True, default=str)}")
                continue
            start = close - timedelta(hours=WINDOW_H)
            params = {"start_ts": int(start.timestamp()), "end_ts": int(close.timestamp()), "period_interval": 1}
            if side == "historical":
                path, kind = f"historical/markets/{ticker}/candlesticks", "historical_candlesticks"
            else:
                path, kind = f"series/{series}/markets/{ticker}/candlesticks", "live_candlesticks"
            data, status = calls.get(path, params)
            head = (f"    {ticker} ({side}; result {m.get('result')!r}; close {iso(close)}; "
                    f"window {iso(start)} to {iso(close)})")
            if data is None:
                echo(f"{head}: refused or failed (status {status}) — a missing payload is a finding")
                out["candles"].append({"ticker": ticker, "side": side, "status": status})
                continue
            keeper.keep(kind, data)
            candles = data.get("candlesticks")
            if not isinstance(candles, list):
                echo(f"{head}: no candlesticks list; the answer whole: {json.dumps(data, sort_keys=True, default=str)}")
                out["candles"].append({"ticker": ticker, "side": side, "status": status, "no_list": True})
                continue
            counts, lines = candle_lines(candles)
            echo(f"{head}: {counts['returned']} came back, {counts['with_bid_and_ask']} carry both a bid and an ask")
            if candles:
                echo(f"      the first candlestick whole: {json.dumps(candles[0], sort_keys=True, default=str)}")
            for line in lines:
                echo(f"      {line}")
            out["candles"].append({"ticker": ticker, "side": side, "status": status, **counts, "lines": lines})
    return out


def out_refusal(out: str) -> str | None:
    """--out never lands under data/ (law 5)."""
    tgt = Path(out).resolve()
    data = (ROOT / "data").resolve()
    if tgt == data or data in tgt.parents:
        return f"REFUSED: --out {out} is under data/ (law 5)"
    return None


def main(argv=None, echo=print, adapter: KalshiAdapter | None = None, logs: Path | None = None,
         now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description="addendum 60 item 7: Kalshi's price history of settled markets")
    ap.add_argument("--series", nargs="*", help="only these series or competitions (as kalshi-replay --series)")
    ap.add_argument("--out", help="write the results here as JSON (never under data/)")
    a = ap.parse_args(argv)
    if a.out and (why := out_refusal(a.out)):
        echo(why)
        return 2
    adapter = adapter or KalshiAdapter()
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    calls, keeper = Calls(adapter), Keeper(stamp, logs)
    echo(f"Kalshi history probe · base {adapter.base} (the adapter's) · the adapter's pace (no pause) · {stamp}")

    echo("\nQ0 — /historical/cutoff")
    cut, status = calls.get("historical/cutoff")
    if cut is None:
        echo(f"  ✗ refused or failed (status {status}) — a missing payload is a finding")
    else:
        keeper.keep("cutoff", cut)
        for k in CUTOFF_KEYS:
            echo(f"  {k}: {cut.get(k)!r}" + ("" if k in cut else "  (not in the answer)"))
        echo(f"  the answer whole: {json.dumps(cut, sort_keys=True, default=str)}")

    try:
        plan = series_plan(adapter, a.series)
    except Exception as e:  # noqa: BLE001 - never stops
        echo(f"\n✗ the series plan could not be read ({type(e).__name__}: {e}); no series probed")
        plan = []
    echo(f"\nseries (kalshi-replay's series_plan): {[p['series'] for p in plan]}")
    results = []
    for p in plan:
        if p.get("unresolved"):
            echo(f"\n=== {p['series']} ({p['competition']}): not resolved ({p['unresolved']}) — not probed ===")
            results.append({"series": p["series"], "competition": p["competition"], "unresolved": p["unresolved"]})
            continue
        try:
            results.append(probe_series(calls, keeper, p, echo))
        except Exception as e:  # noqa: BLE001 - never stops: an answer of an unexpected shape is a finding
            echo(f"  ✗ {p['series']}: {type(e).__name__}: {e} — continuing")
            results.append({"series": p["series"], "error": f"{type(e).__name__}: {e}"})

    echo("\nQ3 — the calls")
    refused = [c for c in calls.made if c.get("status") != 200 or c.get("error")]
    echo(f"  {len(calls.made)} calls · {len(calls.made) - len(refused)} answered · {len(refused)} refused or failed")
    for c in refused:
        echo(f"  ✗ status {c.get('status')} · {c['path']} {json.dumps(c['params'], sort_keys=True)} · "
             f"{c.get('error')}")
    echo("\nkept payloads (send these with the console):")
    for kind, path in sorted(keeper.kept.items()):
        echo(f"  {kind}: {path}")
    if not keeper.kept:
        echo("  none")
    if a.out:
        Path(a.out).write_text(json.dumps({"stamp": stamp, "base": adapter.base, "cutoff": cut, "series": results,
                                           "calls": calls.made, "kept": keeper.kept}, indent=1, default=str))
        echo(f"\nresults written to {a.out}")
    echo("\n✓ Kalshi history probe complete — paste this whole output to the architect. Nothing was ingested.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
