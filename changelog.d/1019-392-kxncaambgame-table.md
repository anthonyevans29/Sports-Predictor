## 2026-11-15 (#1019: 392-kxncaambgame-table — KXNCAAMBGAME's first name table, as data (ARCHITECT 2026-11-15, addendum 392 items 2 and 4; #955))
- **src/ingestion/kalshi_tables/KXNCAAMBGAME.json:** the 253 lines of the architect's file (name | key | id, exactly as printed, in its order), ruled "ARCHITECT 2026-11-15, addendum 392 item 2". KXNCAAMBGAME is now placed by its table alone (387 item 3).
- **The 60 marked names are not in it:** their events refuse under the reason naming them. All 60 are ruled as lines for the series' second data PR (393 item 2; 394 item 1). The three watched lines are confirmed (393 item 1). No code changes.
- **tests/test_392_kxncaambgame_table.py:**
  - every shipped table loads under the strict loader;
  - this one's count (253) and sha256;
  - the series placed by it.
- **The two test files that pinned the no-table state now follow the shipped folder:**
  - tests/test_ncaamb_kalshi_wiring.py's scorer tests read an empty table folder;
  - test_387's repo-state test follows the shipped folder.

  The folder's README names the table.
