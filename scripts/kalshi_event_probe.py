"""
KALSHI EVENT PAYLOAD PROBE (ARCHITECT 2026-10-10, addendum 37 item 2, Law 1 first): "fetch by event ticker the raw
markets of the events in the receipt (ticker, event_ticker, title, yes_sub_title, occurrence_datetime and every other
time the payload carries), put them in the PR, and say what the ticker's date and occurrence_datetime are measured
against. If the payload does not support "the event's day", stop and tell me what it does support."

READ-ONLY: public market data, GET only, no key. Two calls per event:
  GET /events/{event_ticker}                    the event object (every field printed)
  GET /markets?event_ticker={event_ticker}      its markets, ANY status (settled markets included)

For every market it prints ticker, event_ticker, status, title, subtitle, yes_sub_title, no_sub_title, and EVERY
field whose name says it is a time (time / date / _ts / timestamp / expiration / occurrence), verbatim. Then, per
event, the ticker's date stamp as written (e.g. 26OCT10) and, where a time stamp is in the ticker (HHMM), its ET
reading. Nothing is interpreted beyond that: the ruling is read from the console.

Defaults: the nine events of the addendum 37 receipt (series KXNCAAFGAME). `--event` replaces them; `--out` appends
one JSON line per event (event object + raw markets) for the PR.

    python3 scripts/kalshi_event_probe.py [--event KXNCAAFGAME-26OCT10NDSUUNLV ...] [--out probe.jsonl]
           [--base https://external-api.kalshi.com/trade-api/v2]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://external-api.kalshi.com/trade-api/v2"      # src/adapters/kalshi.py BASE (public market data)
RECEIPT_EVENTS = ("KXNCAAFGAME-26OCT10KUUTAH", "KXNCAAFGAME-26OCT10HOUKSU", "KXNCAAFGAME-26OCT10UGAALA",
                  "KXNCAAFGAME-26OCT10FAMUALST", "KXNCAAFGAME-26OCT10UNDUNI", "KXNCAAFGAME-26OCT10NDSUUNLV",
                  "KXNCAAFGAME-26OCT10CCARMRSH", "KXNCAAFGAME-26OCT10SCSTCHSO", "KXNCAAFGAME-26OCT10COOKAAMU")
NAME_FIELDS = ("ticker", "event_ticker", "status", "title", "subtitle", "yes_sub_title", "no_sub_title")
TIME_WORDS = ("time", "date", "_ts", "timestamp", "expiration", "occurrence")
STAMP = re.compile(r"-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})(\d{4})?")


def is_time_field(name: str) -> bool:
    n = name.lower()
    return any(w in n for w in TIME_WORDS)


def get_json(base: str, path: str, params: dict | None = None, fetch=None) -> dict:
    """GET only. `fetch(url) -> dict` is injectable (tests); default urllib."""
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    if fetch is not None:
        return fetch(url)
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def markets_of(base: str, event: str, fetch=None) -> list[dict]:
    out, cursor = [], None
    while True:
        params = {"event_ticker": event, "limit": 200}
        if cursor:
            params["cursor"] = cursor
        data = get_json(base, "markets", params, fetch)
        out.extend(data.get("markets") or [])
        cursor = data.get("cursor")
        if not cursor:
            return out


def ticker_stamp(ticker: str) -> dict:
    """The date stamp as written in the ticker, and an HHMM time stamp if there is one (read as ET by
    KalshiAdapter.ticker_start for the series that carry it). Nothing else is inferred."""
    m = STAMP.search(ticker or "")
    if not m:
        return {"stamp": None}
    return {"stamp": f"{m.group(1)}{m.group(2)}{m.group(3)}", "yy": m.group(1), "mon": m.group(2),
            "dd": m.group(3), "hhmm": m.group(4)}


def market_lines(mk: dict) -> list[str]:
    lines = ["  market " + " · ".join(f"{k}={mk.get(k)!r}" for k in NAME_FIELDS if k in mk)]
    for k in sorted(mk):
        if is_time_field(k):
            lines.append(f"    {k} = {mk[k]!r}")
    return lines


def probe(events, base: str = BASE, fetch=None, out=None, echo=print) -> dict:
    counts = {"events": 0, "markets": 0, "errors": 0}
    for ev in events:
        counts["events"] += 1
        echo(f"EVENT {ev}  ticker stamp {ticker_stamp(ev)}")
        rec = {"event_ticker": ev}
        try:
            evd = get_json(base, f"events/{ev}", None, fetch)
            e = evd.get("event") or evd
            rec["event"] = e
            echo("  event fields: " + ", ".join(sorted(e)))
            for k in sorted(e):
                if is_time_field(k) or k in ("title", "sub_title", "series_ticker", "event_ticker"):
                    echo(f"    {k} = {e[k]!r}")
        except Exception as x:                                   # noqa: BLE001 — a probe reports, never hides
            counts["errors"] += 1
            echo(f"  event GET failed: {type(x).__name__}: {x}")
        try:
            mks = markets_of(base, ev, fetch)
            rec["markets"] = mks
            counts["markets"] += len(mks)
            echo(f"  markets: {len(mks)}")
            for mk in mks:
                for line in market_lines(mk):
                    echo(line)
        except Exception as x:                                   # noqa: BLE001
            counts["errors"] += 1
            echo(f"  markets GET failed: {type(x).__name__}: {x}")
        if out is not None:
            out.write(json.dumps(rec, default=str) + "\n")
    echo(f"KALSHI-EVENT-PROBE {json.dumps(counts)}")
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--event", action="append", help="event ticker (repeatable); default: the receipt's events")
    ap.add_argument("--out", help="append one JSON line per event (event + raw markets)")
    ap.add_argument("--base", default=BASE)
    a = ap.parse_args(argv)
    events = a.event or list(RECEIPT_EVENTS)
    if a.out:
        with open(a.out, "a") as f:
            c = probe(events, a.base, out=f)
    else:
        c = probe(events, a.base)
    return 1 if c["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
