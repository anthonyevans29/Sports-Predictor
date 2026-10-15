**2026-10-15 — DONE (ARCHITECT 2026-10-15 10:16 ET, addendum 74 item 2): the pitcher probe prints the games with neither starter, their months and provenance, and whether a sync-appearances re-run fills them (#507, #535).**
- **Item 2, verbatim:** "THE PITCHER RECEIPT'S MISSING LINE (addendum 72 item 2; #507; small, read-only): scripts/mlb_pitcher_probe.py prints, for each season, the games with neither starter recorded: their date range, count by month, and which sync wrote them (whatever provenance column the row carries; print which you used). Then, from the code, whether a re-run of the sync that writes pitcher_appearances over that range would fill them or a command is missing — one sentence in the probe's output, from a read of the sync, not a guess. The run is mine (Friday's block)."
- **Read for it (law 1):**
  - The only writer of pitcher_appearances is `cli.py sync-appearances` (MLB, `--season`, default `--backfill`, `--limit 2000`, `--refresh`).
  - It targets a finished game by its statsapi id (`matches.external_ids['mlb_stats_api']`, the baseball adapter's source) when no row's `source_game_id` holds that id.
  - It skips a game whose id has rows unless `--refresh` (which deletes and re-captures them), and skips a game with no statsapi id always.
  - The provenance a matches row carries is its `external_ids` keys; pitcher_appearances itself carries only `captured_at`.
- The probe's sentence states that reading with the season's own counts.
