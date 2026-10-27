**2026-10-27 — BUILT (ARCHITECT 2026-10-26 11:55 ET item (2); 2026-10-27 15:20 ET item 2, #382): the book-stamp age receipt. Read-only; nothing moves; a per-family STALE_BOOK_H is the architect's ruling after it.**
- **The request, verbatim:** "(2) #382 (book-stamp age at the close): extend the age receipt to the full distribution of close_book_stamp_age_h on every NFL closing row since Week 3 and every PL row since #615's stamping began, by kickoff slot; by book ONLY where bookmaker-level rows were retained — the stamp is the provider's response time, not a quote time, and rows with no stamp count in the denominator as unknown, never backfilled. 10-25's seven rows at 11–22 h, under the 24 h flag, are the observation that prompts it. A per-family STALE_BOOK_H is a ruling after the receipt."
- **Built:** `scripts/book_stamp_age_receipt.py` reads the database mode=ro and writes nothing.
- **Readings for the architect:**
  1. **"Every NFL closing row since Week 3":** no closing file exists before 10-11, and a closing file carries no age. The unit is every graded live NFL game, each with the age through the grader's own close path. So "closing row" is read as "the game's graded close".
  2. **"Since #615's stamping began":** the soccer stamp is written by #629 (merge fb722251, 2026-10-20 14:42 ET). When a machine pulled #629 is not in the code, so the receipt prints the first stamped kickoff. The unstamped games after the merge are unknown (b).
  3. **Unknowns:** they are split into four causes, all in the denominator: (a) no column, (b) unstamped, (c) partly stamped, (d) no priced book close at all. Whether (d) belongs in the stamp denominator is the architect's call; it is in it, labelled.
  4. **By book:** the provider stamps one answer, not a book, so a per-book age equals the game's. The per-book table shows which games each book priced. The receipt measures how many games' priced rows carry more than one distinct stamp; it is expected to be 0. A PL close from a book snapshot is consensus only, counted, with no book.
  5. **By kickoff slot:** no classifier exists in the code, so the receipt prints its own table for approval.
     - NFL, in ET: TNF (Thu 19:00 on), Thu day (before 19:00, the Thanksgiving games), MNF, Sun international (before 12:00), early (12:00–14:59), late (15:00–18:59), SNF (19:00 on).
     - PL, in UK time: the weekday and the local kickoff time.
  6. **The age:** labelled "provider-stamp age (a lower bound on quote age)", unrounded and never clamped.
  7. **The machine:** the receipt names the database it read. Since the cutover the host writes the closings, so each machine's receipt is its own.
  8. **Re-dates:** a DB-only read cannot label them, so `--exports` applies `redated.void_label` where closing files exist.
- **Review before the PR (an adversarial pass, confirmed findings fixed):**
  - A `--pl-since` with a UTC offset is refused, because the SQLite bind drops the offset.
  - An `--exports` directory with no closing file reads UNLABELLED, never labelled.
  - A database file without the app's tables is refused, exit 2.
  - The Thanksgiving day games get their own slot.
  - With no stamp column, the header says games with no priced close stay (d).
  - The docstring says the database file is never written, though SQLite may create its WAL sidecars.
