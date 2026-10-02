## 2026-10-02 (#256: NCAA market chain syncs results before the export; closes #254)
- `ncaa-market` (host `sp-ncaa-market`, Thu / Fri / Sat) now runs `sync-matches --competition NCAA --season 2026` for yesterday and today as single-day calls, before `sync-kalshi-ncaa` and `export-fixtures`. Games finished since the last run (Thursday's slate before Friday's export) leave the window instead of reading SCHEDULED.
- The laptop routine is documented in `docs/CLI.md` (Market-only competitions); `docs/specs/hosting-h1.md` timer table updated. tests/test_hosting_pack.py (+1).
