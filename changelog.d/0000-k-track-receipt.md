## 2026-10-06 (#0000: k-track-receipt — the #87 executable-edge receipt, with #75's call-to-fill reconciliation — ARCHITECT)
- New READ-ONLY `k-track-receipt`:
  - **Ladders:** every pre-kickoff Kalshi ladder captured 2026-09-23 → end of 10-07, by sport: spreads, two-sidedness (0 < bid ≤ ask < 1), and the fee-clear rate at taker and maker cost (the Desk's K2 4pp rule; `venue.kalshi_exec` costs), versus the live model's pick and versus the venue engine's book reference, never pooled.
  - **Fills** (`--ledger` reads the Cockpit's ledger export): executed-position CLV and fee-adjusted edge, plus #75's call-to-fill reconciliation, exactly one disposition per eligible call.
- `src/walters/ledger_fills.py` ports the Cockpit's fill classification and executedPositions line for line. `scripts/ledger_fills_parity_verify.py` runs the Cockpit's JS and the port on one ledger: 24/24.
- Tests: `tests/test_k_track_receipt.py`.
