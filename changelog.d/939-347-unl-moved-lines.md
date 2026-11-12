## 2026-11-12 (#939: 347-unl-moved-lines — lane unl's record moves to 2026-11-17: cohort fixture 41643 was rescheduled by the provider (ARCHITECT 2026-11-11 19:50 ET, addendum 347 items 1-2).)
- **Ruling (verbatim, 347 item 1, in part):** "a pending cohort fixture leaves the read incomplete; a rescheduled fixture is not UNSCOREABLE, so there is no substitution and the cohort is not touched; the record waits for the fixture. No date moves a bar."
- **docs/roadmap.json, lane unl:** three dates move, each with its moved line, the why verbatim from 347 item 2:
  - "the 60th cohort fixture (41643, kickoff 2026-11-11T21:00Z) is played": 2026-11-11 → 2026-11-16;
  - the confirmation record step: 2026-11-12 → 2026-11-17, its wording now "the confirmation record, by the architect's block on the laptop from the host's pulled copy (addendum 346)" (its moved line names the step by its wording on the base);
  - earliest_live: 2026-11-12 → 2026-11-17.
- 346 item 5's one-day move is superseded by this.
- **tests/test_roadmap.py:** two tests that pinned the real file's unl dates and its empty moved list now read them from the file, so a ruled move does not need a test edit.
- **Unchanged:** the frozen cohort, the plan, the bar, and every other lane.
