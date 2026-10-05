## 2026-10-05 (#280: the Desk's 2c spread cap applies to the Kalshi grading close; follow-up to #278)
- **Ruling (ARCHITECT 2026-10-05, on #278, verbatim):** "apply the SAME 2c spread cap to the grading close — a wide Kalshi mid is not a reference anywhere."
- #278 merged at its earlier head, before the cap commit landed; this carries it.
- `close.close_from_kalshi` uses the Desk's own `KALSHI_ONLY["maxSpreadC"]` (2c, the same cent rounding). When the LAST two-sided pre-kickoff quote is wider, there is no Kalshi close; an older, tighter quote is stale and never substituted.
- Regression: 2c → priced; 3c → none; last quote 10c after an earlier 1c → none.
