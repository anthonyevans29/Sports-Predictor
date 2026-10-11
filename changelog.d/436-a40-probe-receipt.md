## 2026-10-11 (#436: a40-probe-receipt — ARCHITECT addendum 40 items 4 (PROBE FIRST) and 7 (RECEIPT FIRST); Refs #432, #426)
- `scripts/nfl_injury_position_probe.py` (new, read-only): for the stored NFL injured players whose position did not resolve, the player id from the provider's own /injuries answer (by exact name; our rows store no id), then GET /players?id=: does the provider answer a position? For the operator's run; console on #432.
- `scripts/ncaa_hawaii_receipt.py` (new, read-only): our teams named like Hawai'i (ids, source ids, game counts), the three games, and the provider's answer for team 59 and team 901. For the operator's run; console on #426.
- Ledger: the addendum 40 item 7 FINDING (#426).
- docs/CLI.md: their rows. Tests: tests/test_a40_probe_and_receipt.py.
- Codex round 1: the probe's `--out` never aliases the database, its sidecars or data/; a provider errors envelope is a failed read (`provider error`), never "not in the feed"; a player left out by `--limit` has its console line; player objects are printed whole.
