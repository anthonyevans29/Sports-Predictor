**2026-10-31 — BUILT (ARCHITECT 2026-10-31 15:10 ET, addendum 194 item 2; #749): the mlb-pitchers-v1 gate's three write-failure paths refuse and leave nothing, before the 11-06 run. No bar moves.**
- **The ruling, verbatim:** "#749 ITEMS 1, 2 AND 3 — all three, one small follow-up PR, before the 11-06 run: item 1 (a partial reservation write would spend the one run without a read — a law-3 hazard, the reservation file removed on a failed write and GateRefused named), item 3 (one rollback around the whole freeze sequence), item 2 (a non-numeric cohort token refuses naming the file; one line). Tests for each; the freeze-and-run block waits for its merge. Due 11-04."
- **Built:**
  - item 1: `reserve` removes the file on a failed write and refuses, naming the error;
  - item 2: `frozen_ids` refuses a non-id token, naming the file;
  - item 3: `freeze` has one rollback around the create, write, reload and save, which removes the file and restores the ledger's bytes.
- **Code's reading:** item 3's rollback also restores `docs/registry/experiments.json`'s bytes. `registry.save` opens the ledger with "w" (it truncates first), so a save that fails partway would otherwise leave a truncated registry. `registry.save` itself is unchanged; it is shared code beyond this lane.
- **Codex round 1 on #751 (two P2s, fixed):**
  - the freeze restores the ledger's bytes only when its own save had begun ("the ledger was not written" otherwise), so another command's update made between the snapshot and an earlier failure is never overwritten;
  - a reservation whose removal also fails is refused as "could NOT be removed … remove by hand", never as "not spent".
