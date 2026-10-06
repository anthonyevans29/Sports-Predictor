**2026-10-06 — RULED + BUILT (ARCHITECT): the Desk's fee-clear marker gets the same 1e-9 tolerance.**
- **Ruling (verbatim):** "YES — Desk fee-clear gets the same 1e-9 tolerance, small PR; if the golden has a boundary case, note it in the PR rather than regenerating silently."
- **Built:** `desk_policy.FEE_CLEAR_EPS = 1e-9` in `exec_block` (`fee_clears`), and the same tolerance on the Cockpit's marker (`tools/cockpit.html`). An exact 4.00pp exec edge now clears; a real 3.99pp edge still misses.
- **Golden:** checked for a boundary case: none (no `edge_pp` within 1e-6 of 4). The golden is unchanged and passes 15/15.
- **Unchanged:** calls, units, tiers (K2 stays informational), and the 4pp floor itself.
