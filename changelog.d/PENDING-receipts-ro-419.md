## 2026-10-11 (#PENDING: receipts-ro-419 — #419 + #421 (addendum 38 item 4) + #422 item 5; Closes #419, #421)
- `scripts/kalshi_leg_audit.py` (#419): every count straight from `odds_snapshots`, orphans (no match row) on their own line; `--since` validated as `YYYY-MM-DD` (exit 2 otherwise); a graded query that fails is `NOT CHECKED` and exits 1; the IN list is chunked.
- `scripts/kalshi_leg_audit.py` and `scripts/soccer_rating_coverage.py` (#421 RULED): a copy that refuses mode=ro is opened on the plain path with `PRAGMA query_only = ON`, and the console says which form it used.
- `scripts/soccer_rating_coverage.py` (#422 item 5 RULED): the competition is looked up as soccer; a code with none, or more than one, refuses.
- docs/CLI.md: both rows. Tests: tests/test_kalshi_leg_audit.py, tests/test_soccer_rating_coverage.py.
