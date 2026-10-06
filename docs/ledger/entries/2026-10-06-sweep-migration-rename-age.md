**2026-10-06 — SWEEP (ARCHITECT 2026-10-05 rule): post-merge Codex finding on merged #304.**
- **Finding:** "Preserve migration age across migration-to-migration renames". This thread was unanswered after merge.
- **Verified on main:** add `migrate_temp.py`, then `migrate_y.py`, then rename temp → `migrate_x.py`. The plan was `run ['migrate_y.py', 'migrate_x.py']` with nothing undetermined, reversing the real introduction order.
- **Fix:** history is walked oldest first (topological order, merge diffs included via `-m`, `--no-renames`). A commit diff that deletes a migration, or a path carrying a migration's age, taints every path it adds. A new migration added in a tainted diff is undetermined, so the operator orders it. This holds whatever the rename similarity, through intermediate names, and with intermediate names reused later.
- **Receipt:** every new test fails on the pre-fix code and passes here. `pytest`: 799 passed, 1 skipped.
