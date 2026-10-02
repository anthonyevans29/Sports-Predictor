**2026-10-02 — #130 DONE: the export's `kalshi_exec_cost` alias retired (two Cockpit republishes after #88).**
- **Condition (architect ruling (1) on #129, 2026-09-30):** "retired two Cockpit republishes from now, announced in CHANGELOG". Republish count ≥ 2, per the board ruling: the #178 republish and the post-F1c republish.
- **What went:** `kalshi_exec_cost` in `venue.kalshi_exec` / `KALSHI_EXEC_NULL` (so every export row), and the pre-split fallback `exec_cost_taker ?? kalshi_exec_cost` in `desk_policy` and `tools/cockpit.html`.
- **What stayed (as ruled):** the ledger's own `kalshi_exec_cost` / `kalshi_exec_cost_maker` on call records, which the Cockpit stamps into `claim_exec_cost` / `exec_cost`. These are a different field with the taker meaning.
- **Frozen golden untouched:** `tests/golden/desk_js_v1_1.json.gz` is unchanged. The battery's pre-split rows now put the same value in `exec_cost_taker` (same RNG draws), which the deleted JS treated identically. Receipt: 810/810 frozen calls, plus values, venue and parlays, match.
- **Receipts:** pytest 605 passed; all 18 Cockpit verifies and the desk parity verify are green.
