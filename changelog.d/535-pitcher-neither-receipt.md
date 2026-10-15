## 2026-10-15 (#535: pitcher-neither-receipt — ARCHITECT addendum 74 item 2, #507)
- scripts/mlb_pitcher_probe.py (read-only): per season, the finished games with neither starter recorded.
  - Their date range and count by month (stored kickoff, UTC).
  - Their provenance: `matches.external_ids` keys, printed as read (mlb_stats_api = statsapi's sync-matches; api_baseball = the api-sports fallback).
  - The split as `cli.py sync-appearances` reads a game: no pitcher_appearances row for its statsapi id / rows but no starter / no statsapi id.
  - One sentence from the code: a re-run of `sync-appearances --season YYYY` fills the first group where statsapi's boxscore answers. The second is skipped unless `--refresh`. The third is skipped either way, so for it a command is missing.
- tests/test_mlb_pitcher_probe.py: 1 new, on the throwaway DB (2025: four games with no row and one with a reliever row only; 2024: one game with no statsapi id).
