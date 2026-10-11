## 2026-10-11 (#435: soccer-injuries-one-sided — ARCHITECT addendum 40 item 6, A ONE-SIDED LIST GETS NO CALL; Closes #430, finding #425)
- src/walters/export.py: soccer `input_quality.injuries` = {home, away}: {count, synced_at} (null where the team has no row); `injuries_synced_at` and the row's `injuries` block unchanged.
- src/walters/desk_policy.py: a soccer row with exactly one side's list empty is PASS, `pass_kind` `injuries_one_sided` (among NO_CALL_KINDS: no order, no exec, no value shadow), its reason naming the team; both empty or both listed unchanged. Own switch (`injuries_one_sided_rule_off()`), `desk_meta.injuries_one_sided_rule`. No probability changes.
- `scripts/soccer_injury_factor_receipt.py` (new, read-only): every graded PL prediction re-priced with the injury cut taken out of its expected goals; log loss both ways (all, by list-length difference, positive-edge cohort with how many keep +5pp).
- Ledger: the addendum 40 item 5 FINDING (#425) and the item 6 ruling.
- docs/CLI.md: the Desk row and the receipt row. Tests: tests/test_soccer_injuries_one_sided.py.
