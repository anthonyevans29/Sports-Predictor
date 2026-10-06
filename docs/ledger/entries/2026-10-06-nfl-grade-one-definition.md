**2026-10-06 — RULED + BUILT (ARCHITECT): NFL grading, one record definition.**
- **Ruling (verbatim):** "the push and pre-live rules apply everywhere the record is stated: nfl-grade, the NFL section of RESULTS.md, and the season-to-date results file use ONE definition — live_since onward, ties as pushes outside the hit denominator, pre-live rows under their own heading."
- **Built:**
  - `grade_nfl` returns `games`, `decided`, `hits` and `pushes` for live rows, plus a separate `pre_live` tally.
  - The per-game line reads `PUSH` for a tie, the summary reads `sides H/D decided (+P push)`, and pre-live rows print under their own line.
  - Log-loss and the CLV means cover live rows only.
  - The RESULTS.md NFL section is season to date from `live_since`, with a `### NFL pre-live (…; never pooled)` sub-heading.
- **Unchanged:** the gate and its tie convention, every prediction, and the results-file contract.
- **Operator:** after merge, run `python cli.py nfl-grade` and regenerate RESULTS.md.
