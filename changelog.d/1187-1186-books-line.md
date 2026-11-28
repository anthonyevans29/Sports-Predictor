## 2026-11-28 (#1187: 1186-books-line — the BOOKS line in the closing book-gap receipt, and the model engine's count pin as built (ARCHITECT 2026-11-28, addendum 590 item 7: read-only, files only))
- **The question (587 item 4, #1186):** at a PL close one row held one priced book where its slate held nine. The model engine sets no floor on books before a PLAY or a LADDER. The architect rules from the count.
- **(b) THE BOOKS LINE:** `scripts/closing_book_gap_receipt.py` gains a per-family BOOKS section, read from the page alone (files only), for SOCCER (PL 2026/27) and NFL. It covers every counted row from the family's first closing page on the record, which it prints, and not only the stamped window. It gives:
  - `market.bookmaker_count` (the complete books, the Desk's `books`) as 0, 1, 2, 3, 4 or more, and absent;
  - `market.bookmaker_count_quoted` beside it ("not on the page" on NFL);
  - the rows under four split by `desk.call`, with how many are PLAY or LADDER on the books' reference;
  - 0 apart, by cause: the unpriced close (quoted, no book complete) and a Kalshi-only block (no book quoted);
  - on NFL, a row whose `fair_source` is not 1X2 counted apart, and a line saying the unpriced close cannot be told from an NFL page (it writes no block for it), in place of a count;
  - under `--from`/`--through`, the first page is named as the bound's, and a start whose latest page cannot be told is named as out.

  It gives rows and distinct games and the JSON summary's `families.<FAM>.books`. It reads no new desk key, and no unit, order, amount or bookmaker name.
- **(c) ONE PIN AS BUILT:** a model PLAY and a LADDER on one, two or three books give the same desk block, byte for byte, as on nine. Beside it, the one place the model chain reads the count: a floor PASS on fewer than three books turns noref (PASSCLASS). The pin rules nothing.
- **Tests:** `tests/test_1186_books_line.py` (new, 24). Against main's receipt, 19 fail; the 5 that pass are the four as-built pins and the never-read check.
