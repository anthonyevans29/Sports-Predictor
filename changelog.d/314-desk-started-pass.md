## 2026-10-06 (#314: desk-started-pass — ARCHITECT, gate-class)
- Desk: a model-sport row whose kickoff is at or before desk `as_of` is now PASS, units 0, `pass_kind` "started", reason "started - never a new call" (#313).
  - It carries no order, no value shadow and no exec block, and it is never a parlay leg.
  - An unknown kickoff is unchanged.
  - The rule has its own switch (`desk_policy.STARTED_RULE`). `base_v11()` turns it off, so the frozen golden holds (0 mismatches).
  - `desk_meta.started_rule` records the switch state.
- Cockpit: a started PASS is tagged "started", greyed like "no reference", and counted in the summary's pass split.
- Tests: `tests/test_desk_started_rule.py` (6). `scripts/cockpit_pass_class_verify.py` gains 3 started checks (19/19).
