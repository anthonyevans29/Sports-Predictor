## 2026-10-07 (#0000: mlb-actionable-receipt — ARCHITECT, read-only receipt)
- New read-only command `mlb-actionable-receipt` (#321). It reads graded MLB predictions that have a book close, season to date, with the postseason split out.
  - Rows: the prediction layer's tier (`classify_tier`) × the edge vs the close (<4, 4-8, 8-15, >=15pp).
  - Columns: n, mean model p, mean close fair p, hit rate, hit − close (pp) with a pinned-seed bootstrap 95% CI, and flat-stake ROI at the close fair price.
  - The header says the edge is against the CLOSE, a proxy for the Desk's T-60 reference.
  - Writes `docs/receipts/` via `--out`.
- No policy change.
