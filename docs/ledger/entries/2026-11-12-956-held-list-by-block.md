**2026-11-12 — RULED (ARCHITECT 2026-11-12 12:25 ET, addendum 356 item 2): #956 closed by option (b). THE HELD LIST and `TIMERS_BY_BLOCK` stay two lists.**
- **The ruling:**
  - `TIMERS_BY_BLOCK` is a timer's class: how it is ever enabled. THE HELD LIST is a state: off today, entering and leaving with an addendum.
  - The rule that joins them, verbatim: "a `TIMERS_BY_BLOCK` timer is on THE HELD LIST from the merge that ships it until my block enables it; the enabling block's addendum takes it off."
- **The held list now:**
  - `sp-tennis-daily.timer` (288 item 5);
  - `sp-ncaamb-daily.timer` (entered when #957 merged);
  - `sp-availability-graph.timer` (entered with 356).
- **The hold search:** `C=NCAAMB` now prints ncaamb-daily marked "(on THE HELD LIST: not enabled on the host)", never as a live trigger. The search still does not read T11.
- **The finding:** Lane B (Dev 2) found it in the NCAAMB wiring PR's review; section O is Dev 1's.
