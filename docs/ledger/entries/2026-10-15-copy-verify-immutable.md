**2026-10-15 — RULED (ARCHITECT 2026-10-15 10:14 ET, addendum 73 item 4): closing.take_backup and sp_migrate open their copies immutable, as sp_backup and pull_backup do (#532, #534).**
- **Item 4, verbatim:** "#532 (Code's finding beside #531: closing.take_backup and sp_migrate verify their copies mode=ro): RULED a small PR of the same shape (copy_integrity for the copies; the final copy's open in take_backup likewise), after #528's fixes; its PR body says, from the laptop's own closing receipts, whether take_backup has ever failed on the Mac (the closings of 10-14 and 10-15 ran: the receipt decides what the Mac does with that copy, not a guess)."
- In #534:
  - `take_backup` checks its `.partial` and opens its finished copy immutable (`copy_integrity`, `copy_connect`).
  - `sp_migrate` reads the pack's own copy immutable. The installed DB stays mode=ro: it is the live one from then on (#340).
  - `table_counts` of a copy goes the same way.
- **The Mac's receipt:** the closing receipts live on the laptop (logs/receipts.jsonl), which this session cannot read. The PR body gives the operator the command that prints each closing run's `backup` block. Whether `take_backup` ran or failed on 10-14 and 10-15 is read from that output, not guessed.
