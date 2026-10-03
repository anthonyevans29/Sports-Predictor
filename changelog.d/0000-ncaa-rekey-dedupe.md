## 2026-10-03 (NCAA duplicate rows: the resync re-keys instead of duplicating; dedupe-matches; export prefers the finished row)
- `IngestionService.sync_matches` (american-football family): a source-id miss falls back to the natural key: same competition, same home and away team, kickoff within 12h, and the stored id absent from the listing. The stored row is UPDATED and takes the new id; the old id is kept as `<source>_prev`. Ambiguous candidates or a home/away-swapped pair are refused and receipted, never created. `SyncResult` reports `rekeyed` / `rekey_refused`.
- `python cli.py dedupe-matches --competition NCAA [--apply --backup PATH]`: the receipt of how each duplicate pair differs. Apply merges the newer row into the older, referenced one: references are re-pointed, the empty row is deleted, and conflicts are refused.
- `export-fixtures` carries one row per fixture, preferring the finished one, and counts `duplicates_suppressed`.
- tests/test_ncaa_rekey_dedupe.py (5).
