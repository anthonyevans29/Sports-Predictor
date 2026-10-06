**2026-10-05 — BUILT (ARCHITECT #286 ruling 3): `unl-ladder-receipt`, the read-only per-game UNL ladder receipt and the frozen skew test.**
- **Ruling (verbatim):** "YES — a read-only receipt command printing per-game rows (match, legs, bid/ask, spread, two-sided, capture time, series); its output for the 30 is committed under docs/receipts/ via PR."
- **Built:** `python cli.py unl-ladder-receipt [--skew-test] [--out docs/receipts/<file>]` (`src/walters/unl_ladders.py`).
  - Every UNL game kicking off after the freeze cutoff gets one row, with each leg's bid/ask, spread and two-sidedness, the capture time and the series (from stored tickers).
  - Rows also carry the book probability and the favorite gap.
  - The sample is the first 30 games qualifying under `docs/specs/unl-venue-skew-test.md`. Every other game is listed with its exclusion reason.
  - `--skew-test` runs the frozen test only when the sample is complete.
  - It writes nothing to the DB, and `--out` refuses `data/`.
- **Depends on:** stored leg tickers (`migrate_kalshi_ticker.py`, #272) for the series column. Without a ticker, a game reads "series UNKNOWN" and is excluded, never guessed. With #285's pin, every UNL capture carries KXUEFANLGAME.
- **Operator:** run it after each UNL window. When it reads `SAMPLE: 30/30 (complete)`, run with `--skew-test --out docs/receipts/unl-skew-30.txt` and open the PR.
