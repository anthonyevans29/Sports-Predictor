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

## ncaa-elo-v2's confirmation machinery (ARCHITECT 2026-11-03, addendum 230 item 1(b))

The ruling, verbatim: "ncaa-elo-v2's CONFIRMATION MACHINERY (lane ncaa: "PASS, CONFIRMED on 100 fixtures ... D8: the neutral flag before kickoff and the shadow's record against the close"; the 100th fixture 11-21, the record 11-23) — PR BY 11-08, on a tag before the 11-09 run: the college shadow export on the ncaa-schedule chain (the NHL shadow's shape: the entry's probabilities per fixture, market-only, never a call), its grade against the Kalshi close (the close record's KXNCAAFGAME rule), the neutral flag on each row before kickoff with its rule stated (never a provider fact), the confirmation counter to 100; dormant while the verdict is null or FAIL."

- **The chain step.** `ncaa-schedule`'s LAST step, after the listing reads and `refresh-by-id`: `export-ncaa-predictions --id ncaa-elo-v2 --dormant-ok` (`chains.NCAA_SHADOW_STEP`). UNMETERED (the DB and the registry only). Not a sync step: a real failure stops the chain and pages. A `refresh-by-id` failure stops the chain before it, so that run writes no shadow file.
- **Dormant.** `frozen()`'s verdict refusal for the v2 binding (pass_only) is `ShadowDormant` (a `ShadowRefused`); v1r's verdict refusal stays a plain `ShadowRefused` naming addendum 24 item 2(d) (exit 2 with or without the flag: v1r never wakes, so it is never dormant). With `--dormant-ok` it prints `DORMANT: the registry records <no verdict | the verdict X> for ncaa-elo-v2: dormant while the verdict is null or FAIL (...)`, writes nothing and exits 0. Without the flag it exits 2 as before. Every other refusal exits 2 either way.
- **Coverage.** `SHADOW_BINDS["export-ncaa-predictions"]` reads the export's own registry preconditions for the step's `--id` (`frozen` and `bound_scale`), and the step's model is the binding its `--id` names (`ncaa_elo_v2`). Dormant or refused: NCAA reads MARKET-ONLY with the export's reason. On a PASS: `MARKET-ONLY · shadow v2`.
- **The neutral flag before kickoff.** Every row carries `prediction.neutral_rule` (`NEUTRAL_PREGAME_RULE`): D8's text, verbatim, and why the flag is unknown. No stored source of ours carries a pregame flag for an upcoming college game: the CFBD side table labels completed games only, and the american-football adapter stores no venue. So `neutral` stays null, `neutral_flag` says unknown, and the price is the listed home's. A derived rule would change the text and the value together, by a ruling.
- **The grade against the Kalshi close.** `vs_kalshi_close`: `{model_version: vs_close.block}`, one name per binding, never pooled. The close is `paper.guarded_two_way_close`, the close record's own function (`close_record` calls it too). Exclusions are counted first by the shadow's own identity guard (`identity_mismatch`: the row's teams and kickoff are not this match's), then in the record's order: `fenced_2023` / `fenced_2026` (until ncaa-elo-v2's run is recorded), `three_way`, `no_result`, `tie`, `mismatched` (`kalshi_legs.mismatched`, then the HOME row the close reads), `no_close`. The fences and the three-way board are tested before the result, as `paper.close_record` tests them, so a fenced game with no result or a tie counts as fenced. Each finished call in the window lands in exactly one: n plus the exclusions is the window's calls. The book line (`close_1x2` + the stale-book rule) stays beside it.
- **The counter to 100.** `confirmation_counter` / `counter_line`, printed last by `ncaa-shadow-grade`. While ncaa-elo-v2's verdict is null or FAIL it prints DORMANT with the reason; for v1r (`--id ncaa-elo-v1r`, the grade's default) it prints REFUSED with v1r's own verdict and ruling, never 230's dormancy. After a PASS it shows `ncaa_v1r_gate.confirmation_count`: the same games as `confirmation_read`, with n scored of `n_games`, the cohort's state and size, pending by status, and releases due. Beside them it gives the cohort fixtures holding a shadow row before kickoff. It prints counts only: no log-loss, no baseline, no verdict. The read and its record stay `ncaa-confirm --id ncaa-elo-v2`'s.

## Not done here (on purpose)

- **On one chain only.** Since addendum 230 item 1(b) the v2 binding runs on the host's `ncaa-schedule` (dormant until a PASS). It is not on `ncaa-market` or the laptop's morning chain.
- **No Cockpit change.** The Cockpit is the separately published artifact; how it shows NCAA shadow rows is a Cockpit change.
- **Not run on a real DB.** The sample file in the PR comes from a scratch SQLite in the session scratchpad.
