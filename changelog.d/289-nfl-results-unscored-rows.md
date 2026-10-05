## 2026-10-05 (#289: NFL results export skips FINISHED rows with no scores instead of crashing — Codex on #278)
- `export_nfl_results`: the base query requires both scores. A FINISHED row with null scores made `home_score > away_score` raise `TypeError` and aborted the season-to-date file. Test: `test_a_finished_row_without_scores_is_skipped_not_a_crash` (fails on main, passes here).
- Escalated, unchanged: tie grading in the record and preseason predictions in the season record.
