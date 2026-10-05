## 2026-10-05 (#279: resync matches by natural key before creating (second re-key); dedupe skips absent tables / refuses a schema behind the code; reconstruction learns the ruled classes)
- **(A) Second re-key (ARCHITECT, verbatim):** "the provider re-keyed Abilene Christian@West Florida a SECOND time (24146 → 24111) after Saturday's dedupe … Make the resync match by natural key (home, away, kickoff ±12h) when the incoming id is unknown, before creating a row."
  - The hole: the natural-key fallback skipped a stored row whose own id was STILL in the listing (and one already re-keyed this run) as "a different game", then CREATED the new id: a twin. The 10-03 test pinned that creation.
  - Now an unknown id is created only when no live stored row holds its natural key. One free candidate is re-keyed. A candidate whose id is still listed (the provider serving both ids), already claimed this run, or ambiguous is REFUSED (skipped, receipted), never created.
  - An incoming id found in a row's `<source>_prev` history goes back to that row. Cancelled / stale_orphan rows are never candidates.
- **(B) dedupe `--apply` crash (ARCHITECT):** "no such table: intl_venue_resolved". The reference sweep now skips tables absent from the live DB (they hold no references) and names them. `dedupe-matches` / `--orphans` refuse a schema behind the code with the remedy (`python cli.py init-db`, additive, never --force; the transaction rolls back) instead of a traceback.
- **(C) #277 reconstruction 30/30, RULED ACCOUNTED (ARCHITECT).** The tool now knows the ruled classes:
  - **created after the backup:** a rowid above the backup's max;
  - **re-pointed:** a table keyed BY match_id has rowid == match_id, so the re-point moves the row to a new rowid with identical content; such rows are paired;
  - **placeholder kickoff:** 04:00Z → real kickoff within 24h.
  A clean merge carrying them reads ACCOUNTED; a replaced row, a gone row or any other shift still reads REVIEW. Also fixed: a rowid-alias key reported the match id under the column's own name and leaked it into the content.
- **Receipts:** pytest 703 passed / 1 skipped (+6: refuse-not-create on a still-listed id; second re-key after a dedupe (refused while both listed, re-keyed after, history id goes back); two new ids for one row; absent table skipped; schema refusal without a traceback; the three accounted classes).
- **Review fixes (Codex on #279):**
  - P1: a row created in the run joins the natural-key index, so two unseen ids for one fixture in one listing create once and refuse the second.
  - P2: only a missing table / column ("no such table/column", "has no column named") is refused as "behind the code"; a locked or read-only DB, disk I/O and other operational errors keep their own diagnostic.
  - P2: an empty backup table's max rowid is 0, so every current row in it is post-backup.
  - P2: the placeholder class requires the destination to be a REAL kickoff (not another 04:00Z) within 24h.
  - pytest 706 passed / 1 skipped (+3).
