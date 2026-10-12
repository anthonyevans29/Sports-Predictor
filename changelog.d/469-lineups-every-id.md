## 2026-10-12 (#469: lineups-every-id — #467, Codex on #465)
- src/ingestion/service.py `sync_lineups`: a lineup row's team is found by every provider id a team row answers to (`team_merge.source_ids`: its own id first, then the ids a merge recorded), so a merged row's recorded id no longer loses that side's lineup after the match's lineups are wiped.
- Tests: tests/test_team_merge.py (a lineup carrying a merged row's recorded id is kept).
