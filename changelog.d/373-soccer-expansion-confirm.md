## 2026-10-08 (#373: soccer-expansion-confirm, the soccer-expansion-v1 confirmation window on the intl-elo-confirm pattern)
- New command `soccer-expansion-confirm` (ARCHITECT 2026-10-08, addendum 11, item 4). Flags: `--freeze-cohort`, `--substitute`, `--record --ruling TEXT` and `--no-fetch`; no flag prints progress. Flags and refusals mirror `intl-elo-confirm`, and the writes go through the same registry functions.
- Refusals: it refuses unless the registry holds the run record, a PASS verdict and a non-empty surviving set.
- Cohort: the first 60 fixtures by (kickoff, id) of the surviving leagues. Each must be a regular-season round (F3; an unplaced label refuses a freeze or substitution it could precede), kick off after the verdict, and be neither a test-set id nor a stale orphan; any status counts. The cohort is frozen once, after the cross-ref guard (#329).
- Substitution: only unscoreable fixtures are released, using the intl predicate unchanged. A FT row still waiting for its score stays pending.
- The read: the gate's own walk (per league-season cold start, min_prior 40, F5 batching) at the run record's rho / elo_goal_coeff. It reports pooled log-loss vs the pooled naive − 0.010, with per-league lines (reported, not gated).
- Naive source: the run record's per-league 2023/24 `naive_freq`. Only when one is absent does `naive_for` recompute it, and it is labelled.
- `registry.record_confirmation` computes the outcome: bar 1.0986 inclusive, reference strict, so a tie fails.
- Docs: CLI.md row; spec section 5a.
- Tests: 17 new tests (`tests/test_soccer_expansion_confirm.py`, synthetic leagues, tmp registry).
