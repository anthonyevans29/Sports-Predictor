## 2026-11-22 (#1075: 447-leagues-window-read — the leagues windows' one read as a command, and the host's pages digest (ARCHITECT 2026-11-22 09:18 ET, addendum 447 items 1-2 and 4 PR 1; lane leagues, #322))
- **cli.py `leagues-window-read`** (src/walters/leagues_read.py), run as three invocations:
  - `--preflight`: counts only, the first date the read is allowed, then the WINDOW FINGERPRINT;
  - the ONE read: `--architect-word`, `--window-fingerprint`;
  - `--record-verdict PASS|REJECT --ruling` (B1).
- **Where the read runs (B2):** on the laptop, on the host's pulled `.backup` copy (`--db`, addendum 346's fence, mode=ro + immutable=1, its sha256 before and after) and the host's pages (`--exports`).
  - A folder inside the checkout is refused, and the folder is never written (B2(b)).
  - Its digest must equal `--pages-digest`, the host's (B2(c)).
- **The refusals, in order, nothing reserved:**
  1. the arguments;
  2. the entry absent, run, ruled or reserved;
  3. the copy;
  4. the pages;
  5. the entry's checks and ruled list;
  6. a window not ready;
  7. a clock not past the UTC date of the 60th member's kickoff (B2(d));
  8. a fingerprint that differs.
  - The fingerprint covers the member ids in order, their stored rows, the ruled list, the copy's sha256, the pages digest and the frozen constants.
- **The read itself:**
  - The #329 cross-ref guard runs, then the exclusive reservation.
  - The score runs on the same copy session, then the digest, the copy's sha256 and its sidecars are taken again.
  - A failure from the reservation on leaves the read spent and records nothing.
- **What `registry.record_run` records:**
  - the 60 ids;
  - both mean log-losses, unrounded, and the computed verdict;
  - the members in order;
  - the opening `confirmation_opens_after`, the 60th member's kickoff and match id (447 C1);
  - every reached game that took no slot, by id with its cause (B2(e)): the audit's lines did not hold that before, so it is added;
  - the audit, the copy's sha256 and the pages digest.
  - The result is checked as JSON before `record_run` writes anything.
- **The read's console** prints the copy (path and sha256) and the pages (count, first, last and digest) before the reservation, and after the score says both were found unchanged. The digest and the copy are taken again after the window is read and before the reservation, so the fingerprint belongs to the digested bytes.
- **`--record-verdict`** is refused unless the run is recorded by this command, no verdict is recorded yet, the ruling is given, and the word equals the computed verdict.
- **src/walters/leagues_window.py:**
  - `pages_digest` (B2(c)): one `sha256sum` line per page, sorted by name bytewise, then hashed. It refuses a missing, empty or unreadable folder and a name sha256sum would escape.
  - `read()` and `score()` take an optional session (the copy's).
  - `membership()` adds `took_no_slot` and `last_member`.
  - The reader's print and every figure are unchanged.
- **scripts/leagues_window.py `--pages-digest`:** the same digest, the page count and the first and last file. It opens no database and writes nothing, so the host can take it before anything new is deployed.
- **Tests:** tests/test_447_leagues_window_read.py (31).
  - The digest is checked against sha256sum itself and against the script's, with no database opened.
  - Every refusal, and their order pinned two faults at a time; a folder inside the checkout (a link into it, and a worktree's main checkout) among them.
  - The day-after rule; the fingerprint's six parts; the reservation before the score.
  - The per-id account; the opening on a tie at the 60th place, ordered by id.
  - A spent read after the reservation, including a page, the copy or a sidecar that changes during the read.
  - Bytes that change between the digest and the read refuse before the reservation.
  - The guard runs before the reservation; a failed reservation write spends nothing.
  - B1's refusals both ways; the CLI's happy path with its receipt, and its REFUSED lines; the read never writes the folder; the reader's print unchanged through a copy session.

  No prediction output changes; nothing run on either machine.
