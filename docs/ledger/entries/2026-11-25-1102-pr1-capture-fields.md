**2026-11-25 — #1102 PR1, THE FIELDS: run_started_at, books_captured_at, books_source_updated_at, kalshi_legs_captured_at (addendum 529 item 3(a), 532 item 2, 534 item 4; gate-class: an export contract; #1136).**
- **F1** `run_started_at`, top level: the slate run's held start. It comes from `--run-start` on the slate's export step alone (526 Q1). No key without it; a bad value exits 2.
- **F2 and F4** on the priced 1X2 block: the session's oldest capture (as the closing watch reads its books), and `close.book_stamp` on the same close. F4 is null where a priced row is unstamped, and on every MLB row (#628).
- **F3** `kalshi_legs_captured_at` beside `kalshi_legs`: each leg's last capture before kickoff, null with it.
- **Compares:** the daily compare masks all four. The PL check leaves `run_started_at` out by name and compares F2-F4 (526 Q2).
- **Nothing else moves:** no probability, no call, no Desk read, no bar, no date and no held timer. The stale_price rule is PR2's.
