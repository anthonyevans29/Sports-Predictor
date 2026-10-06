## 2026-10-06 (#305: sweep-migration-rename-age — post-merge Codex finding on #304)
- `sp_deploy` migration plan: a migration RENAMED from another migration inside the deploy range (migrate_temp.py → migrate_x.py) carries the source's age, not the rename commit's. It is now undetermined, never planned at the rename's position. On main, add temp, add y, then rename temp → x planned `run [y, x]`, reversing the real order.
- Review fixes (Codex on #305):
  - Renames are scanned with `-m`, so merge-result renames count.
  - Rename CHAINS through intermediate names (migrate_temp → holding.py → migrate_x) are followed.
  - The scan runs before ordering, so an ambiguous migration is listed once and never in the ordered part.
- Review fixes, round 2 (Codex on #305):
  - Moves no longer depend on git's similarity-based rename detection. A move that also rewrote the file (below `-M`'s 50% threshold) planned `run [y, x]`. Now any commit diff that deletes a migration, or a path carrying a migration's age, taints the paths it adds. A new migration added in a tainted diff is undetermined.
  - Taint follows time (topological order, oldest first). A later reuse of an intermediate name (`holding.py`) no longer reaches back and blocks a valid `[x, y]` plan.
- Review fix, round 3 (Codex on #305): taint only accumulates. A merge that replayed a side branch's `holding.py` (renamed from a migration) as a plain addition used to clear its taint, so a later `holding.py` → `migrate_x.py` planned `run [y, x]`.
