## 2026-10-05 (#292: NFL prediction-set scope check expects bye weeks; Kalshi-only reference's first live fire recorded)
- `nfl_backtest.scope_line(per_week=True)`, used by `predict-nfl`'s prediction set: per week, teams = 2 × games = 32 − byes, each team once. A bye week (e.g. teams=30) no longer raises SCOPE ALERT. Duplicates, more than 32 teams, or non-NFL rows still do. Ratings and backtest keep the 32-team check. Test: `test_prediction_set_expects_32_minus_byes_per_week`.
- Recorded: the Kalshi-only reference fired live (NYY@TB 23:11Z, mid 0.475, spread 1c, +3.1pp → PASS below floor).
