**2026-11-22 — The leagues windows' one read as a command (addendum 447 items 1-2, 4 PR 1; #322; #1075).**
- **Ruling (447 item 2, in part):** "B1 RULED: a separate invocation ... B2 RULED: the laptop, on the host's pulled copy and the host's pages ... (c) THE DIGEST IS ONE THE HOST CAN TAKE WITH NOTHING NEW DEPLOYED ... (d) ... the read REFUSES while the UTC date of its clock is not later than the UTC date of the 60th member's kickoff ... (e) The run record accounts for every game the window's loop reached."
- **What landed:**
  - `leagues-window-read` (preflight, the one read, `--record-verdict`), with its refusals in the approved order, the fingerprint, the cross-ref guard, the O_EXCL reservation and the spent read.
  - The pages digest: sha256sum's lines, sorted bytewise, hashed; also `scripts/leagues_window.py --pages-digest`.
  - The run record carries the opening (447 C1) and the per-id account (B2(e)).
  - 31 tests. No prediction output changes.
- **Next:** the adversarial review, then the stop rule; PR 2 (the policy) by 11-27 and PR 3 by 12-11. The soccer-v23 declaration PR comes first.
