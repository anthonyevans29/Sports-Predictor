**2026-10-05 — RECORDED + FIX (operator): Kalshi-only reference fired live; the NFL prediction-set scope check expects bye weeks.**
- **Recorded (operator receipt):** "kalshi-only reference fired live: NYY@TB 23:11Z, mid 0.475, spread 1c, +3.1pp → PASS below floor." This is the first live Desk use of the Kalshi-only reference (#160). It was inside the 2c cap, and the edge was under the floor, so the Desk passed.
- **Fix (operator):** "the SCOPE ALERT teams=30 on predict-nfl is bye weeks (two teams off) — teach the check to expect 32 − 2×byes."
  - `scope_line(..., per_week=True)` for the weekly prediction set checks each week: no team plays twice, and teams = 2 × games = 32 − byes (never above 32). It prints `W<n> <g>g, byes=<b>`.
  - A bye week no longer alerts. A team twice in one week, more than 32 teams, or a non-NFL row still does.
  - An 8-day window that reaches the next week's TNF is fine, because weeks are checked separately.
  - The multi-week streams (ratings, backtest) keep the full 32-team check.
