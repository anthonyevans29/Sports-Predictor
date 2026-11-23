## 2026-11-23 (#PR: 449-v23-declaration — soccer-v23's declaration, and check_plan's reference-only bar (ARCHITECT 2026-11-23 08:05 ET, addendum 449 items 1-6; GATE-CLASS; lane soccer-v23, #656))
- **docs/registry/experiments.json:** the `soccer-v23` entry, written by hand and appended after leagues-bl1-v1 (item 6(a)), as addendum 449 states it:
  - declared_at 2026-11-23T13:05:00Z;
  - the gate is BAR_TEXT as #1070 merged it, sha256 `d4778a27…2371c4`;
  - the slots: LEAGUE_REGULAR, score_under_prior, day, cut 2026-10-30T15:00:00Z, availability_on false. `v22_recorded` holds PL 2024/25 and PL 2025/26, n 340 each, log-loss 0.9956 and 1.0465, with the one source verbatim;
  - frozen_constants: the 21 listed keys and values, equal to `code_constants()` on the base;
  - the prose fields verbatim;
  - confirmation_window verbatim, and confirmation_plan with the reference-only bar;
  - status declared, run and verdict null.
  - Nothing else in the file moves.
- **src/walters/registry.py (item 6(b), 447 C3 (c1)):**
  - `check_plan` admits `bar: null` only with `must_beat_reference` true and a named reference.
  - `record_confirmation` then reads metric < reference alone: strict, a tie fails, no fixed ceiling, and no TypeError.
  - A null bar on any other plan refuses.
  - Every other plan keeps today's rule.
- **Tests:**
  - tests/test_449_v23_declaration.py (17): the real file read for each of items 1-6(a), 6(b) both ways, and 6(c) (constants_state, slots_state and bar_state read it clean; check_plan takes its plan; `declared_unrun` returns it).
  - The leagues pin by position is found by id (test_leagues_declaration_220.py).
  - The harness's real-registry test now holds the declared, unrun entry, and its synthetic fixture drops the real entry.
  - The text test that no entry exists now holds exactly one, declared and unrun.
- **The texts that said no entry exists** now say it is declared and not run: soccer_v23.py's docstring and refusal texts, `soccer-v23-gate --help`, the docs/CLI.md row, and the spec's state and §12. Every soccer_v23.py line citation is unchanged.
- **Side effect:** the shadow export's dormant reason on the host now reads "verdict reads null, not PASS" where it read "no soccer-v23 entry". It is still dormant.

  Nothing of soccer-v23 run on real data; no prediction output changes.
