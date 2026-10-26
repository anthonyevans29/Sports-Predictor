## 2026-10-26 (#000: 700-fence-label-season — the v2 fences read the CFBD label's season as well as the stored one, #700)
- src/walters/ncaa_backtest.py:
  - `label_seasons(s, matches)` reads each match's CFBD label: season, season_type and week, read in chunks.
  - `v2_fenced_ids(s, matches)` returns the 2023-fenced and 2026-fenced ids while the ncaa-elo-v2 run is unrecorded.
  - A match is a 2023 candidate when its stored season or its label's season is 2023, and is fenced unless its label shows it outside the scored set. No label counts as fenced (law 4).
  - A match is 2026-fenced when either season is 2026.
- src/ingestion/resync_diff.py: `_fenced_2023_ids` uses the shared helper. A fenced game is left out of the home-rate line, counted as `fenced_2023_out_of_rate`; ARCHITECT 2026-10-26 15:15 ET: "aggregates, samples and rates over fenced games stay masked". Its sample line stays masked. `export-fixtures`' refusal reads the same helper.
- src/walters/paper.py: the NCAA close record fences by the stored or the label's season, since `_result` reads the label's outcome.
- Item 2 of #700 (the kickoff receipt) is settled with no change by the 15:15 ET ruling: single-game score lines stay visible.
- Tests: tests/test_ncaa_2023_fence.py `test_700_*` and tests/test_close_record_paper.py `test_700_*`. Closes #700. No bar moves.
