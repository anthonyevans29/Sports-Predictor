## 2026-10-06 (#293: NFL grading — one record definition in nfl-grade and RESULTS.md — ARCHITECT)
- ARCHITECT 2026-10-06: `nfl-grade` and the RESULTS.md NFL section state the record the way the results file does (#290). Rows count from `live_since` onward. A tie is a PUSH, outside the hit denominator; it was a hit for an away pick. Pre-live rows sit under their own heading, never pooled.
- `grade_nfl` returns `games`/`decided`/`hits`/`pushes` and a `pre_live` tally. It skips unscored FINISHED rows (the #289 rule), and `days_back=None` means season to date. Log-loss keeps the gate's tie convention, averaged over live rows.
- RESULTS.md's NFL section reads the season to date, no longer a rolling 30 days. It prints `Sides: **H/D** · pushes P` and a pre-live sub-heading.
- RESULTS.md: a sport whose outcomes carry no log loss prints `Mean log-loss: — (n=0)` instead of raising ZeroDivisionError. The new test's shared-DB run surfaced this.
- Test: `test_nfl_grade_and_results_md_state_the_one_record_definition`.
- Review fix (Codex on #293): `nfl-grade` defaults to the season to date, the stated record. Before, the CLI called `grade_nfl()` with its 8-day default. `--days N` keeps the rolling read. Test: `test_nfl_grade_cli_defaults_to_the_season_record`.
