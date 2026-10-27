## 2026-10-27 (#717: 690-floor-blocked — results-tally's floor-blocked line: PASS by the 0.50 floor with exec >= 4 at the close, notional, never pooled; #690)
- src/walters/exec_cohorts.py `floor_blocked` and the EXEC COHORTS section:
  - Per family with a probability floor (SOCCER, INTL: pMin 0.50), a line "PASS by floor, exec >= 4". It counts the closing rows PASS by the probability floor (the pick's model_p under the family's pMin) with exec >= 4 at the close (`desk.exec.edge_pp`, basis taker).
  - The Desk writes pass_kind "floor" for the edge floor too, so the two are told apart by the probability.
  - Figures: W-L-P and notional units at 1u (BASE_UNITS, the size a PASS row's exec block is priced at) at `desk.exec.cost`. Rows not in this DB, with teams differing or re-dated are counted apart.
  - It never enters a PLAY cell or the n=30 counter, and prints 0 when nothing qualifies (the frozen floor's receipt).
- Codex round 1 on #717: INTL floor rows are graded on the 90-minute result (an AET / PEN game without a 90-minute score stays open); a void row keeps its label (re-dated or placeholder kickoff); a non-finite model_p is never read in; and only a model-engine row is (a venue PASS is never the probability floor).
- docs/CLI.md: the results-tally row.
- Tests: tests/test_exec_cohorts.py. No bar moves; read-only line.
