## 2026-10-11 (#PENDING: closing-file — ARCHITECT addendum 40 item 2, ONE CLOSING, ONE PAGE, ONE FILE; Closes #428, finding #423)
- deploy/hosting/closing.py: a closing run whose page went out writes `exports/closing_<FAMILY>_<start>.json` (the page's games only, each row as the export gave it, `count` the rows kept, a `closing` block: family, start, run_id, match_ids, called_off) after the phone accepted the page and before the push; a failed write is receipted and notified, never rerun. The run's export step writes `logs/<run id>.<slate name>` (`--out {export_out}`), so a closing run never writes, replaces or moves the slate file. The receipt records both files and their sha256 and `page.at`.
- deploy/hosting/chains.py: the three closing chains' export step takes `--out {export_out}`. cli.py / nfl_predict.py: `export-nfl-predictions --out PATH`.
- src/walters/venue_quote_age.py: `closing_` among the Desk export names.
- `scripts/closing_file_backfill.py` (new): rebuilds the closing files of past paged runs from the exports-mirror clone's history by the receipt's sha256 (run once, before the 2026-10-18 06:10Z squash). Never opens the database.
- Ledger: the addendum 40 item 1 FINDING (#423) and the item 2 ruling.
- docs/CLI.md: the closing-run, export-nfl-predictions and backfill rows. Tests: tests/test_closing_file.py; tests/test_closing_runs.py updated for the logs/ export.
