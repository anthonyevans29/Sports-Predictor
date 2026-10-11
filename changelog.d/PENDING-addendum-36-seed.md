## 2026-10-11 (addendum-36-seed — ARCHITECT addendum 36 items 1, 3 and 4; Refs #410)
- Ledger: the item 1 FINDING (the host's soccer model runs on default or other clubs' ratings) with its receipt, the BACKLOG entry for #410.
- docs/specs/hosting-h1.md B4: the item 3 amendment (the seeded ratings and team_to_league are the training database's state, not configuration; the host's soccer model rows are evidence of nothing until the cutover).
- docs/specs/h2-cutover-runbook.md: one check after `install` and before `flip`: the installed database's PL export equals the laptop's last file from that database, number for number (`compare_exports.py`, VERDICT: CLEAN).
- `scripts/soccer_rating_coverage.py` (new, read-only): per team of a competition and season, its id, name, production league rating or MISSING, and team_to_league; totals. Tests: tests/test_soccer_rating_coverage.py.
