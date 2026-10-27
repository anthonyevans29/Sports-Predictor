**2026-10-27 — BUILT (ARCHITECT 2026-10-26 12:05 ET, #690): results-tally's floor-blocked line. Read-only; the floor is frozen; no call, units or floor moves.**
- **The ruling, verbatim:** "(3) FLOOR-BLOCKED COHORT (results-tally, read-only line): rows PASS by the 0.50 floor with exec >= 4 at the close (10-25: Newcastle, +8.6, won), counted notionally as "PASS by floor, exec >= 4", W-L and notional units, never pooled; the floor is frozen and this line is its receipt."
- **Built:** the EXEC COHORTS section adds the line per family with a probability floor. It counts the final closing row of each game, selected as the PLAY cells select theirs.
- **Readings for the architect:**
  1. **The edge floor:** the Desk writes pass_kind "floor" for the edge floor too, so a row is in only when the pick's model p is under the family's own pMin (0.50 for SOCCER and INTL). NFL and MLB have no probability floor and print no such line.
  2. **The notional stake:** 1u (BASE_UNITS) at `desk.exec.cost`. That is the size a PASS row's exec block is priced at (call_exec_block prices a PASS at the base unit), so the cost and the stake are the same order's.
  3. **A line that always prints:** a family with a probability floor prints the line at 0 when nothing qualifies, read as "this line is its receipt".
- **Codex round 1 on #717, fixed:**
  - **P1:** INTL floor rows are graded on the 90-minute result (`intl_shadow.result_90`). An AET or PEN game without a 90-minute score stays open, never graded on the later score.
  - **Labels:** a void row keeps its label, re-dated or placeholder kickoff.
  - **Non-finite probability:** a non-finite model_p is never read in.
  - **Engine:** only model-engine rows are read; a venue PASS is never the probability floor.
  - **For the architect:** the PLAY cells' grading (`result_of`) is unchanged here. INTL is DARK, so no INTL PLAY row exists on either machine today.
