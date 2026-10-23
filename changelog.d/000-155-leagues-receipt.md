## 2026-10-23 (#000: 155-leagues-receipt — ARCHITECT addendum 155 item 4(a) and addendum 156 item 1; a read-only receipt)
- scripts/leagues_close_receipt.py and `paper.leagues_season`. Per league (SA, BL1, FL1, ELC), for the 2026/27 games:
  - FINISHED games are scored against addendum 150's three-way Kalshi close exactly as the close record scores a three-way competition: n with a close and the close's log-loss, the bar's denominator.
  - Games still to come are read for the capture they hold now.
  - The projection is the kickoff UTC date of the 60th stored fixture on or after 2026-11-06. The earliest of the four is step (c)'s date.
- `paper._kalshi_snaps` and `paper._three_way_guards`: extracted unchanged from `close_record` (the rows the close reads and the mismatched-capture guard's inputs), so the receipt and the record read the same rows the same way.
