**2026-10-26 — BUILT (#700, the follow-up of #697's review rounds 2-3; queue order ARCHITECT 2026-10-26 16:10 ET): the ncaa-elo-v2 fences read the CFBD label's season as well as the stored one, in resync-diff, export-fixtures and the NCAA close record. No bar moves.**
- **The order, verbatim:** "order: #700 → the MLB as-of pitcher receipt (roadmap 10-28) → the QB packet (10-30) → #689, #690 → #688 (script; the run is the operator's) → #699/#693/#696; #608/#382 scripts after #688."
- **The findings** (Codex on #697, threads r4381322689 and r4381693449):
  - resync-diff and the close record picked fenced games by the stored `Match.season` alone.
  - A match stored under another season but labelled 2023 week 5+ (the ingest's `season_disagree` case) could therefore enter a sample, the home-rate line or the close log-loss.
- **Built:** one helper, `ncaa_backtest.v2_fenced_ids`. A 2023 candidate is a match whose stored or label season is 2023, fenced unless its label shows weeks 1-4 regular or the postseason. A 2026-fenced match is one whose stored or label season is 2026.
  - resync-diff keeps fenced games out of its home-rate line (counted) and masks their samples, under the ruling of 2026-10-26 15:15 ET: "aggregates, samples and rates over fenced games stay masked".
  - The close record and `export-fixtures` read the same membership.
- **Item 2 of #700** (the kickoff receipt's single-game scores) is closed with no change by that ruling: "single-game score lines STAY visible everywhere".
