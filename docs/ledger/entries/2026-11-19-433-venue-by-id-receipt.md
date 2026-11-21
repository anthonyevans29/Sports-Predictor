**2026-11-19 — The by-id venue receipt, read-only tooling (addendum 433 item 4; #276, #220; #1057).**
- **Ruling (433 item 4, in part):** "For every venue id stored on a copy (--db COPY, 346's fence [...]): the provider's answer by id, one call each, the answers kept under logs/, a call cap, resumable from the kept answers. It prints counts [...] It reads no score and no result, writes no row, and prints no log-loss."
- **Why (433 items 1 to 3):** the stored venue country comes from one dictionary across the by-country answers, with the later country written last. The class is not two ids. The mended derivation is ruled from this receipt (433 item 3(e)).
- **What landed:** `intl-venue-by-id`, which reads no match row, plus 12 tests. My review before the PR found five P2s, all fixed.
- **Saved fixtures:** their venue name and city are within reach through `--fixtures-dir`, the intl-sync --save folder (exports/intl_daily on the host).
- **Next:** the architect's block runs the receipt on the laptop on the pulled copy. He says by Monday 2026-11-23, on its console, whether the record's 2026-12-01 holds (433 item 6).
