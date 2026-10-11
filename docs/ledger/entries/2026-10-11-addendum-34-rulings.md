**2026-10-11 — RULINGS (ARCHITECT 2026-10-09 19:44 ET, addendum 34 items 2 and 3, recorded by item 7): #404's two questions (grade_nfl accepted as grading; the close-age line follows the field) and the #340 mode=ro thread (stands as built).**
- **Rulings (verbatim):**
  > 2. #404, THE TWO QUESTIONS IN ITS BODY.
  > - grade_nfl. It collects the age of a close it already computes and returns one more key. That is grading, not
  >   model code, and addendum 31 named nfl_predict.py as a caller. ACCEPTED as built.
  > - RULED, the shadow sections: "The age line follows the field: a sport prints it when its results rows carry
  >   close_at. The NHL and UNL shadow sections carry none and print none. No graded row gains close_at by this."
  > - The readers of clv and value_side_clv are listed as I asked. I rule on the rename from that list, not tonight.
  >
  > 3. THE mode=ro THREAD (#340, 4211712334), which #409 leaves to me. RULED: "It stands as built: mode=ro, never
  > immutable. In a receipt, read-only means that the database's content is never written. The -wal and -shm files
  > are SQLite's own, as for every reader of a WAL database, the app included." Answer the thread with that. It is
  > then answered for the sweep.
- **What they settle:**
  - #404 (merged 2026-10-11): `grade_nfl` returning one more key (the close's age) is grading, not model code; ACCEPTED as built. The results-tally close-age line prints for a sport whose results rows carry `close_at` (MLB, Soccer, NFL); the NHL and UNL shadow sections carry none and print none; no graded row gains `close_at`. The rename of `clv` / `value_side_clv` is not ruled (the readers' list is with the architect).
  - #340 thread 4211712334 (Codex P2, "Prevent read-only sessions from creating WAL sidecars"): stands as built, `mode=ro`, never `immutable`. Answered on the thread (4241462115) with the ruling; answered for the sweep.
- Nothing is built by this entry.
