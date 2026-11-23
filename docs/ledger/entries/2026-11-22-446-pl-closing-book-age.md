**2026-11-22 — The PL closing-page book age receipt, read-only tooling: per closing page, the books' prices' age at the export by the provider's stamp, else by the last stored change (addendum 446 item 2; Refs #348).**
- **Ruling (446 item 2), verbatim:**

  > 2. THE BOOKS' PRICES ON A CLOSING PAGE CAN BE THE SLATE'S, HOURS OLD. On 2026-11-21 the books' fair
  >    probabilities for all six games that kicked off at 12:30Z and 15:00Z are identical to four places
  >    on the 11:00Z slate and on their closing pages of 11:55Z and 14:25Z, home, draw and away. The
  >    17:30Z game's moved, and so did today's Hull City game between 11:30Z and 13:25Z. Kalshi's quotes
  >    on the same pages were captured at the closing run. #348 already says the close's age is our
  >    capture's and not the quote's; this is what that costs on a matchday: the close we grade against,
  >    and the reference the Desk's edge is taken from, stood about three and a half hours behind for
  >    five games.
  >    THE RECEIPT, read-only: from the code, what the closing chain asks the provider for books and what
  >    stamp of its own each answer carries; and from the host's stored odds, for each Premier League
  >    closing page of 2026/27, the age of the books' prices at the page's export by the provider's own
  >    stamp where one is stored, else by the last stored change. Then say what it would take to print
  >    the quote's own age beside the capture's on the page and in results-tally. No build until I rule.

- **What landed:**
  - scripts/pl_closing_book_age_receipt.py, the stored-odds half. It reads every PL 2026/27 row of every closing page and the copy's api_football 1X2 snapshot sessions.
  - The priced session is validated against the page's fair to 4 places. A page that matches an earlier session, or none, is labelled and counted, never forced.
  - Capture, stamp, last-change and headline ages at the export. Unknowns stay in the denominator by cause; "at least" marks a lower bound.
  - The M3 / M4 read and the page's line_move cross-check.
  - It sits behind #688's --db fence, and has 59 tests.
  - The "from the code" half and "what it would take" are prose for the PR body and #348, each with file:line. No build beyond the receipt, no change to v22, the injuries feed or the Desk.
- **Next:** the architect's block runs the receipt on the host's pulled copy with the mirror's host/ pages. He rules on it; nothing is built before that.
