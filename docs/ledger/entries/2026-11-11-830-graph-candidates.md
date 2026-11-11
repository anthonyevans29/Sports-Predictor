**2026-11-11 — DOCS (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 4): the graph projection's one-page candidate comparison, docs/specs/availability-graph-candidates.md; lane availability-record, #830 step 5 (due 11-20). Nothing installed; the architect picks on it; the rebuild (due 11-25) follows the pick. No date moves.**
- **Ruling (verbatim, 252 item 4, in part):** "Code's first PR for this step is a one-page comparison of the embedded candidates — name, licence, maintenance state as of the PR's date (that field moved this year; the state is checked, not remembered), Python binding, Cypher dialect, file format — and I pick on it; nothing is installed before the pick."
- **As read (2026-11-11, PyPI's JSON and named sources):**
  - Kùzu is archived (2025-10-10, last release 0.11.3).
  - LadybugDB, Kùzu's community fork, released 0.22.0–0.22.3 between 10-25 and 11-06, with a dev build on 11-11.
  - RyuGraph's last release was 2025-12-06.
  - Bighorn has no package.
  - FalkorDBLite runs a managed Redis/FalkorDB server process, its engine is SSPL v1, and it needs Python >= 3.12.
  - lance-graph runs partial Cypher over Lance/Arrow tables.
- **For the architect:** the three candidates that meet "embedded, file-based, no server, Cypher" as written are one lineage and one dialect (Kùzu, LadybugDB, RyuGraph). The page states each fact and no preference.
