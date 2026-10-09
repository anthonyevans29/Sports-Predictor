## 2026-10-09 (#PENDING: closing runs, #390 items 6 and 7 — ARCHITECT addendum 28 item 2; references #390, does not close it)
- Rulings verbatim in `docs/ledger/entries/2026-10-09-closing-390-items-6-7.md`. Daily-class: no model, gate, threshold or Desk rule changes.
- Item 6 (RULED): `deploy/hosting/closing.py` `covered_ids`. A game is finished with only at the start its cover recorded (`covers[].start`). A finishing receipt (a success, or the last of three attempts) counts the game only while its stored start, re-read by match id (`stored_starts`, new), is still that start.
  - A game a successful run paged, whose stored start then moves, forms a group at its new start, and that group runs. So does a game paged as cancelled or postponed that is later stored as scheduled at another start.
  - On ed5ecbb, `covered_ids` was a set of match ids, so such a game got no closing and no miss.
- Item 7 (nit): `unpaged_called_off(fam, now)` is bounded to the window `schedule()` reads, [now - 6h, now + 6h) (`schedule_window`, `SCHEDULE_HOURS`, new). `with_called_off` takes the same `now`. Before this, a called-off game whose start time ended with one or two failed attempts stayed in the watch's games, and in `closing-watch --dry-run`, for good.
- Tests: `tests/test_closing_runs.py` `test_390_6_*` (2) and `test_390_7_*` (1), all three failing on ed5ecbb. One existing assertion changed only for the new signature: `unpaged_called_off("SOCCER", NOW + 1m)`.
- Not built: the note beside item 5 (not ruled).
