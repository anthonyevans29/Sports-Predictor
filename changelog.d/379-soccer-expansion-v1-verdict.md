## 2026-10-09 (#379: soccer-expansion-v1 verdict: PASS, surviving set PD; confirmation window open)
- The one gate run is spliced from the operator's branch `laptop/soccer-expansion-v1-run-record` (35135c4) by cherry-pick, byte for byte: the registry entry's run, `docs/registry/ids/soccer-expansion-v1.txt` (3,445 ids) and `docs/registry/soccer-expansion-v1.started.json`.
  - Candidate production v22 (rho -0.1, elo_goal_coeff 0.0008), run at 2026-10-09T12:24:56Z, no prior read.
- The verdict is recorded with the architect's ruling verbatim (addendum 20).
  - PASS, surviving set PD (log-loss 1.0027 against 1.0506; every gated band held).
  - SA, BL1, FL1 and ELC beat their log-loss bars but are dropped on calibration; they stay in the shadow.
  - The closing market beat the candidate in all five leagues (reported, never gated).
  - Status `confirming`, verdict recorded at 2026-10-09T12:47:39Z. The confirmation is the first 60 PD league games kicking off after that time.
- Until CONFIRMED, PD is a shadow: never a Desk call, never an order line.
