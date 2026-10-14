**2026-10-14 — RULED + BUILT (ARCHITECT 2026-10-13 19:38 ET, addendum 64 items 2 and 3, #510, #511): the win rates of the model's own picks carry the line against the close; the PL results section reads PL alone; an unknown competition code refuses. PR #516.**
- **Item 2 (#510), verbatim:** "A win rate of the model's own picks carries the line against the close. A hit rate of the calls staked carries the calls' own record against the close, which is the ledger's mean CLV over the same calls, and nothing more. A frequency per band is calibration, not a record, and carries nothing. A receipt with a frozen format is not changed; a receipt written from now on carries the line where it prints a win rate."
- **The architect's reading of the Issue's list:**
  1. The Cockpit's ledger hit rates are unchanged: their mean CLV is their line.
  2. Calibration's overall hit rate carries the line, by the same helper, over the same games.
  3. The web dashboard's top_pick_accuracy carries the line.
  4. ncaa-shadow-grade's hit rate carries the line, per the shadow's own close.
  5. The named receipts and backtests are unchanged.
  6. CLAUDE.md's two win rates are the architect's text, rewritten in the next CLAUDE.md edit.
- **Item 3 (#511), verbatim:** "The RESULTS.md section headed Soccer (PL) reads PL rows and no other: its query filters by the competition it names. export-results with a competition code it does not know refuses, exit 2, naming the code; it never falls back to every row."
- **As built:**
  - (2) `compute_calibration(with_vs_close=True)` and the command's line;
  - (3) the web route's "Against the close" column;
  - (4) `ncaa_shadow.grade`'s `vs_close`;
  - `vs_close.outcome_row` / `block_from_outcomes`, shared with RESULTS.md;
  - item 3's query filter and the `UnknownCompetition` refusal.
- **Found on the way:** #515, a test that depends on an earlier test in its file (test hygiene only; CI green).
- Closes #510 and #511.
