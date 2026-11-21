## 2026-11-19 (#1057: 433-venue-by-id-receipt — the by-id venue receipt, read-only tooling (ARCHITECT 2026-11-19, addendum 433 item 4; #276, #220))
- **cli.py `intl-venue-by-id --db COPY [--out-dir logs/venue_by_id] [--max-calls 700] [--plan] [--fixtures-dir DIR]` (src/ingestion/intl_venue_by_id.py):**
  - For every venue id stored on a `.backup` copy (under 346's fence), it asks the provider by id, one call each.
  - Each answer is kept under logs/ before it is used; runs are capped and resumable.
  - It prints counts: agrees, differs, stored country unknown, served without a country, not served, and served under more than one country.
  - For each id that differs, it prints its games by home country, with the flag now and under the by-id country, and names the cohort fixtures.
  - `--fixtures-dir` adds the grounds the saved fixtures name for each id.
  - It reads no score and no result, writes no row, and prints no log-loss.
- **Tests:** tests/test_433_venue_by_id_receipt.py, 12 tests.
- **docs/CLI.md:** the row. Nothing run.
