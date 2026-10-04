## 2026-10-04 (#273: cutover-readiness: the ruled #85 criteria in one read-only readout; ARCHITECT lane 2)
- **Ruled criteria (2026-10-02, verbatim):** "cutover when (a) 5 consecutive morning compares show only explained classes, (b) the host has run a full day on a tag carrying #246 with desk calls emitted, (c) parity harness green on that tag — earliest Oct 8 stands."
- **`cli.py cutover-readiness`** (`deploy/hosting/cutover_readiness.py`) prints:
  - (a) the five-compare streak from the exports mirror, pairing laptop/<date> with host/<date> as the Action does: dates, verdicts, and the classes named per divergent line;
  - (b) the host tag, days on it, whether it carries #246 (`git merge-base --is-ancestor`), and desk calls emitted per chain (chain receipts' exports, read from the mirror);
  - (c) `scripts/desk_parity_verify.py` run on that tag in a scratch git worktree;
  - a `GO` / `NOT-YET — <each unmet>` line (exit 0/1), including the earliest date.
- **Conservative naming (law 4):** the tool machine-names only identical, capture timing (market / Kalshi / price fields and the Desk fields that follow them, on matched rows) and the guarded code-version skew. Rows or files on one side only and model fields are UNNAMED, and they break the streak unless `--named` names that date, which then prints as operator-named. GO is a readout, never the decision.
- **Receipts:** 7 new tests; a synthetic five-day mirror + host receipts read GO with the real parity run on v1.2.2 (14/14 GREEN); v1.1.0 does not carry #246, v1.2.0 and v1.2.2 do.
