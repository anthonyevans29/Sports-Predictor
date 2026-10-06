**2026-10-05 — FIX + ESCALATED (Codex on merged #278, found by the merged-PR sweep): NFL results export.**
- **Fixed (P1, verified):** a FINISHED NFL match whose scores had not arrived raised `TypeError` on `home_score > away_score` and aborted the whole season-to-date export. With no rolling window, such a row stayed in scope until scored. The base query now requires both scores, as the ratings and evaluation paths do.
- **Escalated, not changed:**
  - **(a) Ties (P2):** the season record counts a tied game as a hit for an away pick. The frozen gate scores a tie as a home loss (`nfl_backtest.py:163`), so how ties count in the record is a ruling.
  - **(b) Preseason (P2):** predictions made during preseason stay in the season record, because preseason shares the season string. Excluding them changes the reconciled lifetime record.
- **Already fixed:** the Kalshi-only close's spread cap (P1, raised against a pre-#280 commit) is on main via #280.
- **Review fix (Codex on #289, verified):** the season is now chosen before unscored rows are filtered. Filtering first let an unscored opener of a new season fall back to republishing the previous season.
