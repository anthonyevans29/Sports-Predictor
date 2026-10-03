## 2026-10-03 (P0-3 follow-up, refs #208: fee-adjusted edge only from a recorded opening fee)
- **Cockpit `executedPositions()`** (PR #259 review 2, Anthony): the fee-adjusted edge requires `open_fee` on EVERY fill of the position (a recorded zero counts).
  - It no longer substitutes the combined/total `fees` for a missing opening fee and no longer defaults it to zero.
  - Without it the fee-adjusted edge is unavailable (null); entry-price CLV stays.
  - Positions are tagged `open_fee` / `missing` / `combined_only`, and the P&L prints both exclusion counts.
  - Opening and closing fees stay recorded separately at import (a re-import fills them in on older rows); nothing splits a combined figure.
- `scripts/cockpit_clv_verify.py` 19/19: missing-fee, combined-fee, recorded-zero and mixed-fill regressions with exclusion counts. Stored series and sizing unchanged.
