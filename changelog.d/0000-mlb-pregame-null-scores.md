## 2026-10-06 (#0000: mlb-pregame-null-scores — ARCHITECT, daily-class)
- MLB adapter (`src/adapters/mlb_stats_api.py`): when statsapi's coded state is S, P or PW, both scores are null.
  - statsapi sends a pre-game 0-0, which is not a score (law 4).
  - Live and final scores pass through unchanged.
- Test: `tests/test_mlb_pregame_scores.py`.
