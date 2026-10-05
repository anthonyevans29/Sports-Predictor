## 2026-10-05 (Kalshi-only grading close reads the Kalshi ML rows two-way syncs actually store — Codex on #278)
- `close.grading_close` and `clv_restate` filtered snapshots to `market == "1X2"`. Two-way Kalshi legs are stored as `"ML"`, so the ruled kalshi_only close never saw a real quote.
- New `kalshi_close_market_filter` (1X2, plus Kalshi ML). Book sessions stay 1X2-only, and `close_from_kalshi` accepts both markets.
- Tests: fixtures use `ML`, as real syncs do. A new regression test covers the grading close and the restate, with a non-Kalshi ML row that never becomes a book close. Both fail on main and pass here.
