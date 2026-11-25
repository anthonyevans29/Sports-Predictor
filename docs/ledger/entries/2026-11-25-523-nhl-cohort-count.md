**2026-11-25 — The NHL cohort count, read-only tooling for the architect's laptop count (addendum 523 item 2; item (f) of DEV 3's read on #105; DEV 4, Lane D; Refs #105; #1126).**
- **Ruling (523 item 2, in part):** "THE NHL COHORT COUNT, read-only tooling, scripts/nhl_cohort_count.py with its tests. It is item (f) of DEV 3's read on #105 (comment 7146331897), built as a command so that my block runs one tested line and no SQL of mine".
- **What landed:**
  - `scripts/nhl_cohort_count.py --db COPY [--after DATE ...]`, read-only. It prints Q0 to Q6 as counts: stage by status, the six internationals apart, month by status in America/New_York dates, the played games against the goalie table's type, the 2026-27 shot events by month, the games to come after each date, and the 2023-24 shot games.
  - Its tests, on synthetic copies only.
- **Names:** every name is read from the schema and the code first. No stage name is assumed. The six are FOUND only by 445 item 3(b)'s attributes; otherwise NOT FOUND and counted for nothing.
- **Nothing was run on a real copy.** No model, no rating, no figure of any candidate. The count is the architect's block.
