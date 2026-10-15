## 2026-10-15 (#541: lineup-kind-guard, GATE-CLASS — ARCHITECT addendum 75 item 2, Q9)
- src/walters/training.py: the two whole-table lineup readers of the soccer pricing take `kind in ('projected', 'confirmed')` (`LIVE_LINEUP_KINDS`, sync-lineups' own kinds): `lineup_kind_by_match_team` and `starters_by_match_team`. A finished cup fixture's `history` rows (sync-lineups-history, #538) never reach a prediction, the report-only cup exam or the fix-v2 tuning. The recent-XI reader already reads `confirmed` only.
- src/web/routes/matches.py: the match page's lineup reads the same two kinds.
- On today's DB nothing changes: no `history` row exists until #538's first pull. The frozen receipt is the architect's block on the laptop (the PR body).
- Tests, each pinning one filter: it fails with that filter alone removed.
  - tests/test_cup_exam.py, the starters reader: the exam's rows are identical with and without a history eleven that, unguarded, reads as 11 missing regulars.
  - tests/test_cup_exam.py, the kind reader: a history eleven on a scheduled match leaves the stored lineup_kind None; unguarded it reads 'history'.
  - tests/test_lineup_kind_guard.py (2), the match page.
