## 2026-10-07 (#324: mlb-actionable-receipt — ARCHITECT, read-only receipt)
- New read-only command `mlb-actionable-receipt` (#321). It reads graded MLB predictions that have a book close, season to date, with the postseason split out.
  - Rows: the prediction layer's tier (`classify_tier`) × the edge vs the close (<0, 0-4, 4-8, 8-15, >=15pp). ARCHITECT 2026-10-07 (addendum 3 D), verbatim: "Negative edges get their own bucket: <0, 0-4, 4-8, 8-15, >=15. Kalshi-only closes stay excluded and are counted on the receipt. Nothing else changes." This receipt is the review instrument for the MLB big-edge quarantine (#327).
  - Columns: n, mean model p, mean close fair p, hit rate, hit − close (pp) with a pinned-seed bootstrap 95% CI, and flat-stake ROI at the close fair price.
  - The header says the edge is against the CLOSE, a proxy for the Desk's T-60 reference.
  - Writes `docs/receipts/` via `--out`.
- No policy change.
