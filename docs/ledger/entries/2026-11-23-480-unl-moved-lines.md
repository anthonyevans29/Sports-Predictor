**2026-11-23 — Lane unl's record step and earliest_live move from 2026-12-01 to 2027-02-05, and three steps are appended before the record (ARCHITECT 2026-11-23 17:31 ET, addendum 480 item 3, POLICY): the corrected venue flags come from a ruled table keyed by venue id, whose lines need two read-only reads and the architect's ruling of 112 ids (480 items 1 and 2). The frozen cohort, the bar and the read are untouched.**
- **Addendum 480 item 3, verbatim:**

  > 3. WHAT IT COSTS LANE unl: THE DATE MOVES, AS 440 SAID IT WOULD. 160 item 3 and 161 item 2 stand: the
  >    verdict and the record stand on the corrected flags, with the read reported both ways. DEV 1: one
  >    roadmap PR, each move with its moved line quoting this item.
  >    (a) The step "the confirmation record, by the architect's block on the laptop from the host's
  >        pulled copy (addendum 346)": 2026-12-01 to 2027-02-05.
  >    (b) earliest_live: 2026-12-01 to 2027-02-05.
  >    (c) Three steps appended before the record: "the override table's lines ruled, from two read-only
  >        reads (addendum 480 items 1 and 2)", owner architect, due 2027-01-08; "PR ONE (#1055) rebuilt on
  >        the ruled table, a reviewable head", owner code, due 2027-01-22; "PR TWO (#336), the provenance
  >        receipt and the read both ways, a reviewable head", owner code, due 2027-01-29.
  >    (d) WHY, for the moved lines: the corrected flags' source is a ruled table whose lines need two reads
  >        and my ruling of 112 ids by name and city; Lane B's December holds the soccer-v23 run, the
  >        leagues reads and three dated builds; and by the competition's calendar the next Nations League
  >        fixtures are the March 2027 ties, so no call is missed before the new date. The frozen cohort,
  >        the bar and the read are untouched, and nothing is computed on a corrected flag before the
  >        table is merged.

- **As built, docs/roadmap.json lane unl (issue 220):**
  - Three steps are appended before the record step, each with item 3(c)'s text, owner and due, and done null:
    - "the override table's lines ruled, from two read-only reads (addendum 480 items 1 and 2)", architect, 2027-01-08;
    - "PR ONE (#1055) rebuilt on the ruled table, a reviewable head", code, 2027-01-22;
    - "PR TWO (#336), the provenance receipt and the read both ways, a reviewable head", code, 2027-01-29.
  - The record step (its wording unchanged) moves 2026-12-01 to 2027-02-05 (3(a)), and so does earliest_live (3(b)).
  - Two moved lines, appended after the base's seven, each dated 2026-11-23, with 3(d)'s why verbatim and the ruling named.
  - The state stays confirming. The dues run forward, 2026-11-16 to 2027-02-05.
- **tests/test_roadmap.py:** `test_one_moved_line_records_one_move` uses lane unl as its vehicle and moved its last step to a fixed 2026-11-20, which now goes backwards from the appended 2027 steps. Its new date is now 30 days after the lane's own earliest_live, so the dues still run forward; what it pins is unchanged.
- **Checks:** `validate()` returns no error; `python scripts/ledger.py check-roadmap --base origin/main` passes (every moved date has its moved line, and every base moved line is kept).
- Nothing here moves a bar. No prediction output changes. #1055 and PR TWO stay parked until the first appended step is done (480 item 4).
