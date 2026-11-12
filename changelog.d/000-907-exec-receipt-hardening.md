## 2026-11-12 (#000: 907-exec-receipt-hardening — scripts/exec_non_positive_receipt.py: three hardening items from Codex's third review of #903 (#907; the review stop rule's follow-up Issue).)
- **Built (read-only, no call changes):**
  - (1) A prediction row whose `match_id` is a list or an object is a malformed row, listed on an UNREADABLE line and skipped. The run goes on; before, the unhashable key stopped the receipt.
  - (2) A `predictions` that is not a list (an object, a scalar, null, or no key at all) makes its file UNREADABLE, never an empty file read.
  - (3) Of the files holding one (family, start stamp), only the newest (exported_at, then folder) is read, whole. Older copies are listed SUPERSEDED and none of their rows is read, so a game the newer copy dropped is not re-added from the stale copy. An unreadable newest copy makes the start UNREADABLE; an older copy never stands in for it (law 4).
- **Console:** `files read` counts neither unreadable nor superseded files, and a `superseded copies: N` count joins that line.
- **Unchanged:** every count's meaning, the blocks, the SUMMARY line, the exit codes; nothing is written.
