## 2026-10-15 (#543: guard-desk-pick — ARCHITECT addendum 79 item 1, #537)
- scripts/soccer_injury_factor_receipt.py: a changed call is now graded on the Desk's own pick, not on the receipt's unrounded pick.
  - The Desk's pick is the one `desk_policy.normalize` takes from the export's 4-decimal probabilities: it walks HOME, DRAW, AWAY and moves only on a strictly greater value, so a tie goes to the first side.
  - `guard_calls` keeps the pick of the row the Desk's own run evaluated (`desk_pick`; None when the case is not evaluated). `guard_summary`'s `changed_graded` grades on it.
  - The instrument rules (`instrument()`) are kept; only the side passed to them changed. The edge and cohort lines keep the unrounded pick. The `--list` row names the Desk's pick where the two differ.
  - Two leading sides within 0.0001 of each other can round to the same value. On main, AWAY 0.50001 / DRAW 0.49997 on a draw graded "PLAY AWAY lost"; now it grades "PLAY DRAW won", the Desk's DRAW.
- tests/test_soccer_injuries_one_sided.py: 1 new test, that tie case run through `guard_calls`, `guard_summary` and the `--list` report. The summary unit test's row carries `desk_pick`.
