## 2026-10-27 (#000: 689-ladder-exec — the LADDER's ordered NO leg priced on the row, informational, and a priced-but-ungraded LADDER line in results-tally; #689)
- src/walters/desk_policy.py `ladder_exec_block`: a LADDER row now carries `desk.ladder_exec`, the ordered BUY NO on HOME priced as a PLAY's exec block is:
  - `model_p`: the model's draw + away; `market_p`: the books' fair draw + away;
  - the NO bid / ask, mirrored from the HOME leg;
  - the taker cost at the order's own contract count, the contracts, `edge_pp` and `fee_clears`.
  - A draw pick, an unticketed HOME leg or a missing ask gives `why` and no price. `desk.exec` stays null for a LADDER.
  - No call, units, floor or order changes. Written only with the #87 addendum on, so the golden is untouched.
- src/walters/exec_cohorts.py: results-tally's EXEC COHORTS section adds, under "left out: LADDER", a line counting the LADDER rows by the NO leg's exec edge (exec >= 4 · 0 < exec < 4 · exec <= 0), with the mean edge and the unpriced rows by why. It is ungraded, notional and never pooled with PLAY.
- docs/CLI.md: the `desk.ladder_exec` row.
- Tests: tests/test_ladder_exec_689.py (new), tests/test_exec_cohorts.py. No bar moves.
