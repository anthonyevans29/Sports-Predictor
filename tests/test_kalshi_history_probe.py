"""Kalshi history probe (ARCHITECT 2026-10-13, addendum 60 item 7): offline runs, no network, no database.

"Read-only: no database, and nothing written but its own --out file and its kept payloads under logs/. It follows
scripts/lineup_history_probe.py: the base URL and the pace are the adapter's own, never from memory; it never stops on
an error; a payload that is missing is a finding; nothing it prints is cut; the whole output is pasted to me."
"""
import importlib.util
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

spec = importlib.util.spec_from_file_location(
    "khp", Path(__file__).resolve().parent.parent / "scripts" / "kalshi_history_probe.py")
khp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(khp)

from src.adapters import kalshi as kalshi_mod  # noqa: E402

NOW = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
CUTOFF = {"market_settled_ts": "2026-08-12T00:00:00Z", "trades_created_ts": "2026-08-12T00:00:00Z",
          "orders_updated_ts": "2026-09-27T00:00:00Z", "market_positions_last_updated_ts": "2026-08-12T00:00:00Z"}


def _mk(event, side, close, result="yes"):
    return {"ticker": f"{event}-{side}", "event_ticker": event, "close_time": close, "result": result,
            "status": "finalized"}


HIST_PAGE1 = [_mk("KXNHLGAME-26APR01AAABBB", "AAA", "2026-04-02T02:00:00Z"),
              _mk("KXNHLGAME-26APR01AAABBB", "BBB", "2026-04-02T02:00:00Z", "no")]
HIST_PAGE2 = [_mk("KXNHLGAME-26MAY10CCCDDD", "CCC", "2026-05-11T01:30:00Z"),
              _mk("KXNHLGAME-26JUN14CARVGK", "CAR", "2026-06-15T02:58:23Z")]
LIVE = [_mk("KXNHLGAME-26OCT10EEEFFF", "EEE", "2026-10-11T02:30:00Z")]


def _candles(n=361, start=1781564903):
    return [{"end_period_ts": start + 60 * i, "yes_bid": {"close_dollars": "0.5200"},
             "yes_ask": {"close_dollars": "0.5300"}, "price": {}} for i in range(n)]


def _http(status, text='{"error": "x"}'):
    resp = requests.Response()
    resp.status_code = status
    resp._content = text.encode()
    return requests.HTTPError(f"{status}", response=resp)


class Fake:
    """Routes the adapter's _get by path, in the receipts' shapes."""

    def __init__(self, overrides=None):
        self.asked = []
        self.overrides = overrides or {}

    def __call__(self, path, params=None):
        self.asked.append((path, dict(params or {})))
        p = params or {}
        for key, val in self.overrides.items():
            if path.startswith(key):
                if isinstance(val, Exception):
                    raise val
                return val(path, p) if callable(val) else val
        if path == "historical/cutoff":
            return CUTOFF
        if path == "historical/markets":
            return ({"markets": HIST_PAGE2, "cursor": ""} if p.get("cursor") == "c2"
                    else {"markets": HIST_PAGE1, "cursor": "c2"})
        if path == "markets":
            return {"markets": LIVE, "cursor": None}
        if path.endswith("/candlesticks"):
            return {"ticker": path.split("/")[-2], "candlesticks": _candles()}
        raise _http(404, '{"error": "not found"}')


def _adapter(fake):
    a = kalshi_mod.KalshiAdapter()
    a._get = fake
    return a


def _run(tmp_path, monkeypatch, fake=None, argv=("--series", "KXNHLGAME")):
    out, fake = [], fake or Fake()
    monkeypatch.chdir(tmp_path)
    rc = khp.main(list(argv), echo=out.append, adapter=_adapter(fake), logs=tmp_path / "logs", now=NOW)
    return rc, "\n".join(out), fake


def test_the_base_and_the_pace_are_the_adapters_own(monkeypatch, tmp_path):
    import time

    def no_sleep(*a):
        raise AssertionError("the probe paused: the adapter's pace has no pause")
    monkeypatch.setattr(time, "sleep", no_sleep)
    rc, text, _ = _run(tmp_path, monkeypatch)
    assert rc == 0 and f"base {kalshi_mod.BASE} (the adapter's)" in text
    assert khp.PAGE_LIMIT == 200                                   # open_markets_for_series' own page size


def test_q0_prints_the_cutoffs_four_timestamps(monkeypatch, tmp_path):
    rc, text, _ = _run(tmp_path, monkeypatch)
    for k, v in CUTOFF.items():
        assert f"  {k}: {v!r}" in text


def test_q1_pages_the_historical_list_to_its_end_and_reads_the_settled_list(monkeypatch, tmp_path):
    rc, text, fake = _run(tmp_path, monkeypatch)
    hist_calls = [p for path, p in fake.asked if path == "historical/markets"]
    assert [c.get("cursor") for c in hist_calls] == [None, "c2"]
    assert all(c["series_ticker"] == "KXNHLGAME" and "max_close_ts" not in c for c in hist_calls)
    assert ("markets", {"series_ticker": "KXNHLGAME", "status": "settled", "limit": 200}) in fake.asked
    assert ("Q1 historical: 4 markets · 3 events · first close 2026-04-02T02:00:00Z · "
            "last close 2026-06-15T02:58:23Z") in text
    assert "events by month: {'2026-04': 1, '2026-05': 1, '2026-06': 1}" in text
    assert "Q1 live settled: 1 markets · 1 events · first close 2026-10-11T02:30:00Z" in text
    assert "Q1 both sides: 5 markets · 4 events" in text


def test_q2_takes_the_first_middle_and_last_event_and_reads_six_hours_of_minutes(monkeypatch, tmp_path):
    rc, text, fake = _run(tmp_path, monkeypatch)
    picked = [ln for ln in text.splitlines() if ln.startswith("  Q2 event ")]
    assert [ln.split()[2] for ln in picked] == ["KXNHLGAME-26APR01AAABBB:", "KXNHLGAME-26JUN14CARVGK:",
                                                "KXNHLGAME-26OCT10EEEFFF:"]
    candle_calls = [(path, p) for path, p in fake.asked if path.endswith("/candlesticks")]
    assert ("historical/markets/KXNHLGAME-26JUN14CARVGK-CAR/candlesticks",
            {"start_ts": int(datetime(2026, 6, 14, 20, 58, 23, tzinfo=timezone.utc).timestamp()),
             "end_ts": int(datetime(2026, 6, 15, 2, 58, 23, tzinfo=timezone.utc).timestamp()),
             "period_interval": 1}) in candle_calls
    assert any(path == "series/KXNHLGAME/markets/KXNHLGAME-26OCT10EEEFFF-EEE/candlesticks" for path, _ in candle_calls)
    assert "361 came back, 361 carry both a bid and an ask" in text
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("#")]
    numbers = sorted({int(ln.split()[0][1:]) for ln in lines})
    assert numbers == [1, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360, 361]   # first, every 30th, last
    assert "yes_bid close '0.5200' · yes_ask close '0.5300'" in text


def test_it_keeps_one_raw_payload_of_each_kind_under_logs(monkeypatch, tmp_path):
    rc, text, _ = _run(tmp_path, monkeypatch)
    kept = sorted(p.name for p in (tmp_path / "logs").iterdir())
    assert kept == [f"kalshi_history_20261013T150000Z_{k}.json" for k in
                    ("cutoff", "historical_candlesticks", "historical_markets_page", "live_candlesticks",
                     "settled_markets_page")]
    page = json.loads((tmp_path / "logs" / "kalshi_history_20261013T150000Z_historical_markets_page.json").read_text())
    assert page == {"markets": HIST_PAGE1, "cursor": "c2"}                 # the raw page, whole
    assert sorted(p.name for p in tmp_path.iterdir()) == ["logs"]       # nothing else written


def test_it_never_stops_and_a_refused_call_is_listed_with_its_status(monkeypatch, tmp_path):
    fake = Fake({"historical/cutoff": _http(503, "unavailable"),
                 "historical/markets/KXNHLGAME-26JUN14CARVGK-CAR": _http(429, '{"error": "too many requests"}'),
                 "series/": lambda path, p: {"something": "else"}})
    rc, text, _ = _run(tmp_path, monkeypatch, fake)
    assert rc == 0
    assert "Q0 — /historical/cutoff\n  ✗ refused or failed (status 503)" in text
    assert "KXNHLGAME-26JUN14CARVGK-CAR (historical" in text and "refused or failed (status 429)" in text
    assert 'no candlesticks list; the answer whole: {"something": "else"}' in text
    assert "✗ status 429 · historical/markets/KXNHLGAME-26JUN14CARVGK-CAR/candlesticks" in text
    assert '{"error": "too many requests"}' in text                     # the refusal's body, whole
    assert text.splitlines()[-1].startswith("✓ Kalshi history probe complete")


def test_a_list_page_of_another_shape_or_a_cursor_that_repeats_ends_the_paging_with_a_note(monkeypatch, tmp_path):
    fake = Fake({"historical/markets": lambda path, p: {"markets": HIST_PAGE1, "cursor": "loop"},
                 "markets": lambda path, p: {"rows": []}})
    rc, text, _ = _run(tmp_path, monkeypatch, fake)
    assert "historical/markets: the cursor 'loop' came back twice; paging stops" in text
    assert 'page 1 of markets: no markets list; the answer whole: {"rows": []}' in text
    assert rc == 0


def test_an_unresolved_series_is_listed_and_not_probed(monkeypatch, tmp_path):
    monkeypatch.setattr(khp, "series_plan", lambda adapter, only: [
        {"series": "(unresolved CNL)", "competition": "CNL", "path": "soccer", "unresolved": "reserved"}])
    rc, text, fake = _run(tmp_path, monkeypatch, argv=())
    assert "=== (unresolved CNL) (CNL): not resolved (reserved) — not probed ===" in text
    assert [path for path, _ in fake.asked] == ["historical/cutoff"]


def test_the_series_are_kalshi_replays_series_plan():
    from src.ingestion import kalshi_replay
    assert khp.series_plan is kalshi_replay.series_plan


def test_out_is_written_and_never_under_data(monkeypatch, tmp_path):
    rc, text, _ = _run(tmp_path, monkeypatch, argv=("--series", "KXNHLGAME", "--out", str(tmp_path / "probe.json")))
    doc = json.loads((tmp_path / "probe.json").read_text())
    assert rc == 0 and doc["cutoff"] == CUTOFF and doc["series"][0]["series"] == "KXNHLGAME"
    out = []
    assert khp.main(["--out", str(khp.ROOT / "data" / "x.json")], echo=out.append, adapter=_adapter(Fake())) == 2
    assert out[0].startswith("REFUSED: --out") and not (khp.ROOT / "data" / "x.json").exists()


def test_it_opens_no_database(monkeypatch, tmp_path):
    def no(*a, **k):
        raise AssertionError("the probe opened a database")
    monkeypatch.setattr(sqlite3, "connect", no)
    rc, _, _ = _run(tmp_path, monkeypatch)
    assert rc == 0


def test_nothing_it_prints_is_cut():
    import inspect
    assert "[:" not in inspect.getsource(khp).replace("[:]", "")


@pytest.mark.parametrize("v, want", [
    ("2026-06-15T02:58:23Z", "2026-06-15T02:58:23Z"), (1781492303, "2026-06-15T02:58:23Z"),
    ("2026-03-31T23:30:00-04:00", "2026-04-01T03:30:00Z"), ("2026-03-31T23:30:00", "2026-03-31T23:30:00Z"),
    ("not a time", "-"), (None, "-"), (True, "-")])
def test_times_are_read_as_iso_or_epoch_seconds(v, want):
    assert khp.iso(khp.parse_ts(v)) == want


@pytest.mark.parametrize("n, want", [(1, [1]), (29, [1, 29]), (30, [1, 30]), (31, [1, 30, 31]), (60, [1, 30, 60])])
def test_the_first_every_thirtieth_and_the_last_candle(n, want):
    _, lines = khp.candle_lines(_candles(n))
    assert [int(ln.split()[0][1:]) for ln in lines] == want


def test_an_offset_close_time_is_read_in_utc_for_its_month(monkeypatch, tmp_path):
    late = [_mk("KXNHLGAME-26MAR31GGGHHH", "GGG", "2026-03-31T23:30:00-04:00")]
    fake = Fake({"historical/markets": lambda path, p: {"markets": late, "cursor": ""}})
    rc, text, _ = _run(tmp_path, monkeypatch, fake)
    assert "first close 2026-04-01T03:30:00Z" in text and "events by month: {'2026-04': 1}" in text


def test_q3_lists_every_call_made_with_its_status(monkeypatch, tmp_path):
    fake = Fake({"historical/markets/KXNHLGAME-26JUN14CARVGK-CAR": _http(429, '{"error": "too many requests"}')})
    rc, text, fake = _run(tmp_path, monkeypatch, fake)
    q3 = text.split("\nQ3 — the calls\n", 1)[1].split("\nkept payloads", 1)[0].splitlines()
    rows = [ln for ln in q3 if ln.startswith(("  ✓ ", "  ✗ "))]
    assert len(rows) == len(fake.asked) and q3[0] == f"  {len(fake.asked)} calls · {len(fake.asked) - 1} answered · 1 refused or failed"
    assert "  ✓ status 200 · historical/cutoff {}" in rows
    assert ('  ✓ status 200 · historical/markets {"cursor": "c2", "limit": 200, "series_ticker": "KXNHLGAME"}' in rows), rows
    assert [ln for ln in rows if ln.startswith("  ✗ ")] == [
        '  ✗ status 429 · historical/markets/KXNHLGAME-26JUN14CARVGK-CAR/candlesticks '
        + json.dumps(next(p for path, p in fake.asked if path.startswith("historical/markets/KXNHLGAME-26JUN14")),
                     sort_keys=True) + ' · {"error": "too many requests"}']
