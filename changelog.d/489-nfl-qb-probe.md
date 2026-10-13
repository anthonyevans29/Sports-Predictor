## 2026-10-13 (#489: nfl-qb-probe — ARCHITECT addendum 59 item 5(h); lane nfl-qb, #427)
- scripts/nfl_qb_probe.py: the read-only quarterback probe, for the NFL seasons 2023 to 2026. It follows scripts/lineup_history_probe.py.
  - Ids come from the adapter's own mapping: `_CODE_TO_LEAGUE["NFL"]` and `DIRECT_BASE` from src/adapters/api_american_football.py; QB position names from qb_audit.QB_POSITIONS.
  - Q0 /status. Q1 /leagues coverage per season, verbatim.
  - Q2 per season: three finished games (first, middle, last) through /games/statistics/players. It prints the raw shape, the groups, the passing players with every stat name and value, every key or stat name that says "start" (or that none does), and the most attempts, labelled OUR READ.
  - Q3 the next unplayed game: /games?id, /games/statistics/players and both rosters' quarterbacks, verbatim.
  - A per-season summary at the end.
  - It never stops on an error, writes nothing, opens no database, and never prints the key. The operator runs it and pastes the whole output to the architect.
- Tests: tests/test_nfl_qb_probe.py (13), offline.
