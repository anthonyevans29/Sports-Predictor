**2026-10-12 — BUILT (#467, Codex's P2 on #465 in its second round; order: addendum 50 item 7): sync_lineups maps a lineup by every provider id a team row answers to. PR #469, stacked on #465.**
- **Finding:** `sync_lineups` wipes a match's lineups, then maps the response's team ids by each team's own provider id only; after `merge-teams`, a lineup carrying the merged-in id mapped to no team and that side's lineup was lost.
- **The architect (addendum 50 item 5):** "#467 before any merge in a sport that stores lineups: agreed. It is my check at each dry run too."
