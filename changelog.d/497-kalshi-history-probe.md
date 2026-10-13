## 2026-10-13 (#497: kalshi-history-probe — ARCHITECT addendum 60 item 7; finding #496)
- scripts/kalshi_history_probe.py: the read-only probe of Kalshi's price history for settled markets.
  - It uses the adapter's own base, pace (no pause) and page size (200), through `KalshiAdapter._get`, and records every call with its status.
  - Q0: the historical cutoff.
  - Q1: for each series in kalshi-replay's `series_plan`, the historical and live settled market lists, paged by cursor to their end: markets, events, first and last close, events by month.
  - Q2: three events per series (first, middle, last), with one-minute candlesticks for the six hours before each market's close (counts; the first, every thirtieth and the last).
  - Q3: the calls, and each refused.
  - It keeps one raw payload of each kind under logs/. `--out` writes JSON and is never under data/. Nothing printed is cut. Nothing is ingested.
- Tests: tests/test_kalshi_history_probe.py (17), offline.
