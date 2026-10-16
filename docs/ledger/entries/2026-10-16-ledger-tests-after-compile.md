**2026-10-16 — FIX (main's CI red on the v1.4.0 commit, ARCHITECT 2026-10-16 09:29 ET, addendum 84 item 1): three tests read a ledger fragment that the compile folds and deletes (#551).**
- **The fact:** CI's smoke job on c546168, the ledger compile ruled as v1.4.0 ("the operator cuts it once CI on that commit is green"), failed. The fragments job was skipped.
  - A local run on c546168 gives 3 failed, 2260 passed, 4 skipped.
  - The three tests read `docs/ledger/entries/2026-10-08-ncaa-v1r-declaration.md`, which the compile folded into BACKLOG.md and deleted: test_ncaa_v1r_declaration's D1-D9 verbatim check, and test_ncaa_v1r_fence's two D9-correction checks.
  - Everything they quote is in BACKLOG.md verbatim, under the entry's heading, exactly once.
- **The fix (tests only, no behaviour):**
  - `tests/ledger_text.entry_text` reads the fragment while it exists and the folded block after the compile.
  - The three tests read through it.
  - A guard test keeps any test from reading a fragment file directly again.
- **The tag:** c546168 itself stays red. The tag is the architect's to re-rule: on the merge commit of this fix, or on c546168 with this read.
