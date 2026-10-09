# NCAA shadow (ARCHITECT 2026-10-07, addendum 6 item 1)

## The ruling (verbatim)

> "NCAA SHADOW. Once #333's coverage receipt shows 95% on both seasons and ncaa-elo-v1r is declared in the registry with its constants frozen, ship export-ncaa-predictions and ncaa-shadow-grade on the NHL shadow's pattern: engine model_shadow, the gate status on every row ('UNGATED — shadow only' until the verdict, then the verdict), FBS games in the next 36 hours, the market block beside each row, graded on results and on model-vs-close from the last shadow file before kickoff. Never a call, never a venue input, never in the ledger. The shadow starts before the gate run and changes nothing about it: the one run, the verdict and the confirmation cohort stand as declared, and the shadow's live record is not gate evidence. Target: the Saturday 2026-10-10 slate. If the labels are not in by Friday night, say so and Saturday stays market-only."

Build instruction: "Build it now on a branch so it is ready when the labels are. It does not run on a real DB before the coverage receipt is read."

## Commands

- `python cli.py export-ncaa-predictions [--hours 36]` writes `exports/ncaa_shadow_<YYYY-MM-DD_HHMM>.json` and nothing to the DB.
- `python cli.py ncaa-shadow-grade [--days 30]` is read-only. It reads the shadow files on disk.

## Preconditions (code, not a checklist)

`export-ncaa-predictions` refuses with exit 2 and a stated reason, writing nothing, unless both of these hold:

1. **The declaration exists.** The registry holds `ncaa-elo-v1r`, and its entry states `neutral_site_rule` as one of:
   - `home_advantage_at_neutral`
   - `no_home_advantage_at_neutral`

   #333 ruled that "whether v1r applies home advantage at neutral sites is a declaration question". The shadow therefore never chooses; it reads the key. The entry must also freeze `constants` = v1's untouched values (`k_factor` 24, `home_advantage` 55, `mov_base` 2.2, `season_regression` 0.25, `default_rating` 1500); anything else refuses (Codex on #344). **The declaration PR must carry both keys** (named here, for the architect).
2. **Coverage holds (restated 2026-10-08).** SCOPE (ARCHITECT 2026-10-08, verbatim): "the side table labels at least 95% of CFBD's completed both-FBS games in each season used, read from the ingest receipt (joined over in scope), every unmatched game listed. The shadow's precondition is that same fact." The shadow checks it with `ncaa_cfbd.stored_coverage` (`coverage_guard`) for 2024, 2025 and 2026: D6 of the ncaa-elo-v1r declaration (ARCHITECT 2026-10-08, addendum 11 item 3; docs/specs/ncaa-elo-v1r.md), "the shadow and the confirmation read refuse unless 2024, 2025 and 2026 are" covered. Every season that misses is named. LABEL SET (ARCHITECT 2026-10-08, addendum 11): the fact is the season's latest ingest record (`ncaa_cfbd_ingest_records`), joined over in scope, at least 95%; the payload file is never opened; a season with no record, or whose current labels do not number the record's joined count, refuses with its reason (L2, L3). The walk and the FBS team set (`fbs_teams`) read CURRENT labels only: fetched_at equal to the season's latest record's (L3). It is re-checked on every run, so a side table that regresses stops the shadow. (Until 2026-10-08 this was the side table's share of the gate's all-division stream, `ncaa_backtest.label_coverage`; that ratio is now information only.)

The architect's read of the receipt is what leads to (1). The code never declares anything in the registry.

## Model

- **v1 with its constants untouched.** `NCAAEloConfig()`: k 24, home advantage 55, mov_base 2.2, regression 0.25, default rating 1500. The update math is `NCAAEloV1`'s verbatim.
- **Neutral rule.** Under `no_home_advantage_at_neutral`, a game whose CFBD neutral flag is true prices and updates with home advantage 0.
  - An upcoming game has no side-table row, so its neutral flag is unknown. The listed home's advantage is applied and the row says so (D8): `home_adv_applied`, `home_adv_basis` "listed home (neutral flag unknown before the game)", `neutral: null`, `neutral_flag: "unknown before the game"` (law 4).
  - A labelled game without a neutral flag is non-neutral and counted (D1; `neutral_unflagged` in the file's `fit`).
  - The wrapper is `ncaa_backtest.NeutralRuleElo` (`ncaa_shadow.V1R` is an alias), shared with the design receipt script.
- **Walk-forward** over the ncaa-elo-v1r stream, D2 (ARCHITECT 2026-10-08, addendum 11 item 3): stored games carrying a CURRENT CFBD both-FBS label (L3), seasons 2024, 2025 and 2026 by the label's season, in order of stored kickoff then match id, postseason included (`ncaa_backtest.v1r_stream`). A stored game without a current label is neither walked nor scored and is counted (`unlabelled_not_walked`, `stale_labels_not_walked`). A level score is a data defect: skipped, counted and listed (`level_scores_skipped`, `level_scores_listed`). Every game before now, then the predictions. The file's `fit` also carries `walked_by_season`, `season_type_census` and `outside_seasons_not_walked`.
- **Team merge (J2, 2026-10-08).** Team ids whose html-unescaped names are identical are one team, keyed by the lowest id, for the walk, the FBS test and the upcoming games. A read-time mapping; `teams` is never written. Every group and every changed name is listed in the file's `fit.team_merge`.

## Rows and file

- **File stamp:** the file is named `ncaa_shadow_<YYYY-MM-DD_HHMMSS>.json`, created exclusively (a rerun never overwrites an artifact; Codex on #344), and stamped `sport: "ncaa"`, `competition: "NCAA"`, `family: "NCAAF"`, `engine: "model_shadow"`, `model_version: "ncaa_elo_v1r"`, `registry_id`, `contains_predictions: false`, `gate_evidence: false`.
- **Every row carries:**
  - the fixtures export's own row (`_fixture_row`: the market block, Kalshi and execution fields);
  - `competition` / `family` / `engine` / `model_version` / `gate_verdict`;
  - a `prediction` block: home/away probability, top pick, both Elos, home advantage applied, neutral.
- **`gate_verdict`** is `UNGATED — shadow only` until the registry records a verdict for `ncaa-elo-v1r`, then that verdict.
- **FBS:** both teams appear in the CFBD side table, whose ingest's default scope is both-FBS completed games. Any other game is skipped and counted (`not_both_fbs`), never priced. *Reading chosen, for the architect:* the side table stores no classification. If it were built with `--division ''` (all classifications), this test would admit non-FBS teams.
- **Never a call:** `desk_policy` and the window card already skip `engine == "model_shadow"`. The shadow is never a venue input and never logged to the ledger.

## Grading (`ncaa-shadow-grade`)

- **The call** is the LAST shadow row written before kickoff. Its teams, kickoff and competition must be the match's own (match ids are machine-local and reusable); a mismatch is counted, never graded (Codex on #344).
- **Results:**
  - The result is the CFBD side-table score in our orientation where a row exists, else the matches row.
  - Hit rate, log-loss and Brier of the shadow probability.
  - A tied final is a data defect, skipped and counted.
- **Model-vs-close:**
  - Pick-vs-close against the stored 1X2 book close (the #167/#207 contract; nfl-grade's rule).
  - Value-side-vs-close from the earliest pre-kickoff book snapshot.
  - Unpriced and unanchored games are counted, never guessed.
- **Label:** every per-game grade line and the summary say NOT gate evidence.

## Not done here (on purpose)

- **Not on any chain.** It is not on `ncaa-market` or the host. Wiring it in follows the preconditions, by ruling.
- **No Cockpit change.** The Cockpit is the separately published artifact; how it shows NCAA shadow rows is a Cockpit change.
- **Not run on a real DB.** The sample file in the PR comes from a scratch SQLite in the session scratchpad.
