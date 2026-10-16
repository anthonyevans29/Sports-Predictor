## 2026-10-16 (#566: web-ncaa-fence — ARCHITECT addendum 99 items 2(2) and 5; #560)
- src/walters/ncaa_backtest.py: `v2_fence_view(code, season)` returns the withheld notice while the shown season is NCAA's 2026 and the ncaa-elo-v2 run is unrecorded, else None.
- src/web/routes/home.py + templates/league_dashboard.html: the league view (`/?league=NCAA`) withholds its 2026 league table until the run is recorded. The table's place reads "withheld until the ncaa-elo-v2 run is recorded" (the 2026 fence, addendum 86 item 3, Q2). Its single-game lists stay (the level ruling); every other league is unchanged.
- docs/RELEASES.md: the ritual's step 2 makes `logs/` first (`mkdir -p logs && python3 scripts/release_notes.py ...`). A fresh or cleaned checkout has no `logs/`, and the redirect failed before the script ran (#560, Codex on #558 round 2).
- tests/test_web_ncaa_fence.py (3):
  - the helper: NCAA 2026 alone, lifted by the recorded run;
  - the league view: the notice in the table's place, the single games kept, the table back once recorded;
  - the release step's `mkdir -p logs`.
