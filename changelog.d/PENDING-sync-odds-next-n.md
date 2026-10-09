## 2026-10-09 (#PENDING: sync_odds --limit means the next N; Closes #387)
- `IngestionService.sync_odds` (soccer path) now orders its candidates by kickoff (`utc_date`), then `id`, before `--limit` is applied, so the limit prices the next N scheduled games instead of the first N in storage order. `--match-ids` is unchanged: the same set is priced (now fetched in kickoff order).
- The window service's `sync-odds --limit <n>` (deploy/hosting/sp_run.py) now prices that competition's next n scheduled games; the premise in deploy/hosting/chains.py ("sync_odds takes the next N scheduled games") is now true. Neither file changed.
- Test: tests/test_sync_odds_next_n.py (three upcoming games stored out of kickoff order, limit 2: the two earliest are priced; fails on main).
