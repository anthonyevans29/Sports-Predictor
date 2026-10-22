## 2026-10-22 (#000: 569-sync-cause — ARCHITECT addendum 153 item 2, #569's cause lane; the dedupe is its own PR after this one)
- **#569 RULED (the cause), verbatim:** "The statsapi upsert looks a gamePk up across the sport's rows, not the competition's, and a run holds the DB lock the host's chains hold (the laptop's syncs today take none)."
- src/ingestion/service.py: `SPORT_WIDE_SOURCES = {"mlb_stats_api"}`. sync_matches' prefetch reads the sport's rows for a statsapi sync, so a gamePk stored on any MLB row is updated, never created again. Every other source's lookup stays the competition's own; the re-key index (api_american_football) is unchanged.
  - Receipt: one gamePk (849818) stored on a second MLB competition's row; main's sync creates a second row (`created=1`, rows 50546 and 50547); with the change it updates 50546 (`created=0 updated=1`).
- cli.py: `sync-teams` and `sync-matches` run under `sp_common.db_lock`, the chains' flock, when run by hand, printing one line while they wait. Run as a step of a run that holds it, they take none.
  - deploy/hosting/sp_common.py: `db_lock` sets `SP_DB_LOCK_HELD` in os.environ while held (restored after; every step runner inherits os.environ), and takes an optional `on_wait` callback.
- tests/conftest.py: the suite's default `SP_LOCK` is under its throwaway dir, so a test's sync never locks the checkout's logs/db.lock.
- docs/CLI.md: the sync-teams and sync-matches rows.
