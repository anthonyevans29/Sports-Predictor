## 2026-10-06 (#0000: k-exec-addendum — #87 executable edge, Desk v1.1 addendum — ARCHITECT-RULE)
- **Cost = ask + taker fee** (`desk_policy.taker_cost_for`): the contract the order line buys, at its ask, plus 0.07·M·P(1−P) rounded to the nearest cent per fill. The maker cost is shown for reference only.
- **TAKE at the ask by default.** Join-bid applies only at a spread of 3c or more, in the order line, the exec block and the Cockpit's ledger join bid. The 2026-09-30 join-bid doctrine is superseded.
- **Sizing.** A PLAY gets full tier units only when its exec edge is at least 4pp. Otherwise, or with no executable quote, it gets HALF units. Quarantine, floors, tiers and ladders are unchanged.
- **Venue.** The 5pp fair threshold stands, AND the exec edge (book fair − cost) must clear 4pp. A venue call with no executable quote is PASS with no reference.
- **Parlays.** Ticket Π market = Π executable cost; a ticket with an unpriced leg is not offered (counted). Each ticket carries `fair_p`, each leg's `exec_cost`, and the independence-estimate label.
- New read-only `desk-rescore FILES…`: the published PLAYs, re-scored under the addendum at each file's own as_of, showing which would have been halved.
- `desk_meta.exec_addendum` stamps every file. The frozen pre-F1c golden still holds under `base_v11()`.
- New tests: `tests/test_desk_exec_addendum.py` and `scripts/cockpit_exec_addendum_verify.py`.
