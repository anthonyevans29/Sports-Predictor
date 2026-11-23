## 2026-11-23 (#1086: 447-leagues-policy — the leagues' confirmation policy, 447's PR 2 (ARCHITECT 2026-11-22, addendum 447 item 3 C1-C3 and item 4; addendum 448 items 1-2; GATE-CLASS; lane leagues, #322))
- **src/walters/leagues_window.py:**
  - **The fence while confirming (447 C2; 448 item 1(a), one site):** while an entry is `confirming`, `fence_cutoff` returns the opening's kickoff less one microsecond. Every consumer's "after the cut" therefore fences every game at or after the opening's kickoff. The opening is the 60th member's kickoff and id, `run.result.confirmation_opens_after`, read by `opening()`.
    - A confirming entry with no readable opening keeps the window's own fence (law 4). Its refusal and its print say so; they never say the verdict is unrecorded or that the fence holds from the opening.
    - `opening()` reads an opening only in the form the registry compares: kickoff to the second with the Z, and an integer match id.
    - The confirming case has its own refusal wording, naming the opening as inclusive and printing it whole.
  - **After the confirmation is recorded (448 item 1(b))** the fence lifts, CONFIRMED or NOT_CONFIRMED, as after a REJECT.
  - **The print and the module docstring** say so (448 item 1(c)).
  - **`RULED_PLAN` and `plan_refusal` (448 item 2(b)):** the leagues read's refusal of an entry whose stored plan is not the ruled plan. It is called in `leagues_read.check_entry`, after the spent checks and before the reservation check, so the preflight and the read both refuse at the entry, before the copy is opened (the call placed by ARCHITECT 2026-11-23, addendum 459 item 2(a), in the push that merged #1075's main).
- **src/walters/registry.py, `record_confirmation`:**
  - It runs `check_plan` on the stored plan (448 item 2).
  - For an entry whose run record carries the opening, the first game must be NOT EARLIER than the opening's kickoff (447 C1(b)). Both values are written to the second with the Z and compared as strings; any other form refuses (448 item 1(d), `INSTANT_Z`). An entry without the opening keeps today's rule, after `verdict.at`. A run record that holds an opening which cannot be read (a kickoff not in that form, or no integer match id) refuses; it never falls back to `verdict.at`.
- **docs/registry/experiments.json:** the five leagues entries hold the ruled plan {n_games 60, log_loss, bar null, must_beat_reference true, the close}, by direct edit (447 C3(a); 448 item 2). Each `confirmation_plan_note` keeps its words and gains 448 item 2(a)'s sentence, verbatim and the same in all five, before the closing 223 item 2(d) sentence.
- **Tests:**
  - tests/test_447_leagues_policy.py (new): the fence, the opening, the string comparison, check_plan on the stored plan, the notes, the refusal, the print, and C3(b): an entry at production changes no export and no Desk call.
  - tests/test_leagues_declaration_220.py: the plan pin, amended to the ruled plan (448 item 2).
  - tests/test_leagues_window.py: the six old fixtures carry the status, and the confirmation record, the rule reads (448 item 1(c)). tests/test_leagues_export.py: two fixtures likewise.
  - tests/test_447_leagues_window_read.py: the entry fixture holds the ruled plan, as the real entries do. One new test: a stored plan that is not the ruled plan refuses the preflight and the read, and nothing is reserved.
  - tests/test_449_v23_declaration.py: a bare-null stored plan is now refused by `check_plan`, in its own words, before anything is written (448 item 2). It was refused before too, but later, in `record_confirmation`'s "no bar to read".
- **docs/CLI.md:** the soccer-expansion-confirm row's fence sentence follows 448 items 1(a)-(b).

  No bar, threshold or verdict moves. Nothing is run on real data. No prediction output changes.
