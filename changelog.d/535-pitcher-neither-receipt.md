## 2026-10-15 (#535: pitcher-neither-receipt — ARCHITECT addendum 74 item 2, #507)
- scripts/mlb_pitcher_probe.py (read-only): per season, the finished games with neither starter recorded.
  - Their date range and count by month (stored kickoff, UTC).
  - Their provenance: `matches.external_ids` keys, printed as read (mlb_stats_api = statsapi's sync-matches; api_baseball = the api-sports fallback).
  - The split as `cli.py sync-appearances` reads a game: no pitcher_appearances row for its statsapi id / rows but no starter / no statsapi id.
  - One sentence from the code: a re-run of `sync-appearances --season YYYY` writes rows for the first group where statsapi's boxscore answers, at most `--limit` games a run (default 2000, in no set order). It writes a starter only where the boxscore's per-game `gamesStarted` is 1. The second group is skipped unless `--refresh`.
  - `--refresh` makes every finished game with a statsapi id a target and deletes their rows, committed before any request. A game whose request fails or returns nothing is left with no rows, so the sentence says to take a .backup first. The third group is skipped either way, so for it a command is missing.
- tests/test_mlb_pitcher_probe.py: 1 new, on the throwaway DB (2025: four games with no row and one with a reliever row only; 2024: one game with no statsapi id).
