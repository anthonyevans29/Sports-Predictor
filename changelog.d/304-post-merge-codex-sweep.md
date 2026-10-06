## 2026-10-06 (#304: post-merge-codex-sweep — post-merge Codex findings on #296 and #297)
- `sp_deploy` migration plan:
  - An UNCHANGED copy of an existing migration (`C100`) is reported with the renames and never planned as runnable. `-M` alone reported it as an addition. A new migration written from an old one's template stays new.
  - Only a migration's FIRST appearance groups it with a commit, so a merged branch's ordered migrations are no longer "added together" just because `log -m` re-lists them in the merge commit.
- `k-track-receipt --ledger` refuses an export whose `calls`, `fills` or `system_picks` is not a list of objects, instead of a traceback.
- The other two post-merge #297 findings (shared city words, the windowed unpriced count) are fixed on #299, which rewrites that code.
