**2026-10-08 — #367 (ARCHITECT, addendum 13 item 1): migrate_ncaa_cfbd_v2.py writes its own marker row, and the CFBD ingest's v2 readiness requires it.**
- **Ruling (verbatim):** "The marker question: a follow-up, not #362. ... Open an Issue; the marker row goes in a small PR after #365."
- **The finding it closes (#367; Codex P2 on #362):** `records_ready()` checked only that `ncaa_cfbd_ingest_records` exists. `init_db()` (create_all) creates every mapped table, so readiness could be true without the post-backup migration having run.
- **Built:**
  - `migrate_ncaa_cfbd_v2.py` creates the one-row table `ncaa_cfbd_v2_migration` (Core SQL, unmapped) and writes its row if missing (`+ Wrote` / `· Kept`). It is a table of its own, not a second row in `ncaa_cfbd_labels_migration`, because that table's id is `CHECK (id = 1)`; one marker per script.
  - `ncaa_cfbd.v2_migrated()` = season_type column + records table + marker row. It gates the non-dry ingest. The refusal tells the operator to take the .backup and run `migrate_ncaa_cfbd_v2.py`. Readers still need only the table.
  - `drop_db()` drops the v2 marker too.
- **Operator note:** if `migrate_ncaa_cfbd_v2.py` was run before this PR (main's version, no marker), the ingest refuses until it is re-run once. The re-run keeps both objects, changes nothing else, and prints `+ Wrote migration marker ncaa_cfbd_v2_migration`.
- **Tests:** an `init_db()`-created table and column without the marker refuses (fails on main: the ingest wrote); after the script the ingest proceeds; two runs leave one marker row and print `Kept`; a pre-PR-migrated DB gains the marker only (every other table's columns and rows identical).
