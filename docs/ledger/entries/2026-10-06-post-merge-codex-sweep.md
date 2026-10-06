**2026-10-06 — SWEEP (ARCHITECT 2026-10-05 rule): post-merge Codex findings on merged #296 / #297.**
- **Five unanswered findings were verified on main; all five reproduce:**
  - #296 copies: an unchanged copy was planned as runnable.
  - #296 merge grouping: a merged branch's ordered migrations were marked "added together".
  - #297 ledger validation: a malformed `fills` gave a traceback.
  - #297 shared city words: a Giants–Rams fill fit a Jets–Chargers call, even on #299's head.
  - #297 unpriced count: it was not windowed.
- **Fixed here:** the first three, each with a test that fails before the fix and passes after. The merge-grouping case was also reproduced on the old code with a standalone script.
- **Fixed on #299** (the open PR that rewrites that code): the last two. The thread replies name the commits.
