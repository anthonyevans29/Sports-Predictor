**2026-10-03 — P0-3 follow-up (refs #208): the fee-adjusted closing edge needs the RECORDED opening fee; no inference from combined/total fees.**
- **Review (Anthony, PR #259, after the sign-reversal fix):** "`executedPositions()` still defaults unavailable fees to zero and substitutes total fees for a missing opening fee. Keep entry-price CLV available, but make fee-adjusted edge unavailable unless `open_fee` is present, including an explicitly verified zero. Do not infer the opening fee from combined or total fees … Add missing-fee and combined-fee regressions, with exclusion counts, before #208 closes. Preserve the existing stored series and sizing."
- **Order of events:** #259 merged and #208 auto-closed at 16:42Z, before this follow-up was pushed. This PR carries the fix and refs #208; reopening #208 is the architect's/operator's call.
- **Built:**
  - `fee_adj` is computed only when every fill has a numeric `open_fee` (an explicit CSV "0" parses to 0, an empty cell to null). Otherwise it is null, tagged `missing` / `combined_only`, and counted in the P&L line "fee-adj edge needs the recorded opening fee: N with it · M no fee recorded · K combined/total fee only (never split)".
  - Entry-price CLV is unaffected.
- **Receipts:** cockpit_clv_verify 19/19; fills 44/44, maker/taker 26/26, exec 19/19, ledger 21/21; pytest green.
