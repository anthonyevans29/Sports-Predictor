# ncaa-elo-v1r — declaration (GATE-CLASS; declared before any read of the test set)

Registry id `ncaa-elo-v1r` (docs/registry/experiments.json), status `declared`, run and verdict null. ARCHITECT
2026-10-08, addendum 11, item 3, PR A. Step (a), the design receipt, is done (section 3). This document is step (b);
step (c), the shadow on the declared stream, is section 5.

**Nothing here runs the gate.** The gate command, `--preflight`, the reservation and the confirmation command are
PR B. Nobody scores a 2025 game before PR B merges and the architect gives the word (D6).

Test set (registry `test_set`, exact): "NCAA FBS 2025 regular season (CFBD both-FBS labels; warm-up 2024)".

## 1. The declaration (ARCHITECT 2026-10-08, addendum 11 item 3, RULED, verbatim)

> "D1. Candidate: NCAAEloV1 with its constants untouched: k_factor 24, home_advantage 55, mov_base 2.2, season_regression 0.25, default_rating 1500. neutral_site_rule is no_home_advantage_at_neutral: a game whose label says neutral is priced and updated with home advantage 0. A label without a neutral flag is treated as non-neutral and counted.

> D2. Stream: stored NCAA games that carry a current CFBD both-FBS label, seasons 2024, 2025 and 2026, in order of stored kickoff then match id. Home and away, the scores and the neutral flag come from the label; team ids are merged as J2 rules. Every such game is walked, postseason included. A game with level scores is a data defect: skipped, counted and listed.

> D3. Split: 2024 is warm-up, update only. The test set is the 2025 games whose season_type is exactly 'regular': predict, then update. A 2025 game with any other season_type, or none, is walked and never scored. The gate scores no 2026 game.

> D4. Baseline: one number, frozen before any test game is scored: the home win rate of the stream's 2024 non-neutral games whose season_type is 'regular'. It is the baseline's home probability in every non-neutral test game; at a neutral site the baseline is 0.5.

> D5. Gate. Under 500 scored games the run is INVALID. PASS iff all four hold on the scored games. (1) Margin: model log-loss < baseline log-loss - 0.010, unrounded; ties reject. (2) Level: the mean of the model's home probabilities and the realized home win rate differ by no more than 5pp. (3) Spread: the calibration slope b lies within 0.20 of 1, where b is the slope of the maximum-likelihood logistic fit of the result on the model's log-odds, logit P(home win) = a + b * logit(p), with p clipped to [0.000001, 0.999999]; a fit that does not converge fails. (4) Range: every rating after the last 2025 game walked lies within 1000 to 2000. Reported, never gated: #79's 10pp bands, the constant-0.5 log-loss, Brier, the intercept a, cold starts (a team's first game in the stream), and the log-loss split neutral and non-neutral.

> D6. Preconditions, in code. The gate run refuses unless 2024 and 2025 are covered as L2 and L3 rule; the shadow and the confirmation read refuse unless 2024, 2025 and 2026 are. If a season misses, nothing in this declaration bends to fit it: I rule again. The run is one run: a reservation written before the first read, the scored ids recorded, and it starts only on my word. --preflight scores nothing and prints, per season, the stream by season_type, the neutral count, the coverage and the D4 baseline. I confirm the season_type census before the run.

> D7. Confirmation: the first 100 stored NCAA fixtures, by kickoff then id, that kick off after the verdict and whose two teams, as merged ids, both carry a current label at the freeze; any status; frozen once by fixture id with the intl-elo-v2 machinery. A cancelled fixture is released and replaced by the next eligible one. A finished fixture without a label is pending, never replaced. Scored by the same replay as the gate, the label's flags applied, every cohort fixture whatever its season_type. CONFIRMED iff log-loss <= 0.6931 and < the D4 baseline's log-loss - 0.010 on the same games. confirmation_plan: n_games 100, metric log_loss, bar 0.6931, must_beat_reference true, reference the D4 baseline on the same games minus 0.010.

> D8. What a pass does not do. PASS and CONFIRMED do not make college football a call. The Desk stays market-only for NCAA until a separate policy ruling, and that ruling needs the neutral flag before kickoff and the shadow's record against the close. Until then the shadow prices an upcoming game with the listed home's advantage and says on the row that the neutral flag is unknown.

> D9. Prior reads of this test set: none. The 2026-09-30 run of v1 (all divisions, scrambled 2025 labels, VOID by the 2026-10-01 ruling) scored 2026 games; the entry names it."

**Correction to D9 (ARCHITECT 2026-10-08, addendum 14 item 2(a), #368, RULED, verbatim).** D9 stays quoted as issued
above; this correction stands beside it:

> "For 'Prior reads of this test set: none.' read 'No candidate has been scored on this test set. One outcome figure of the test season was read before this declaration: its non-neutral home win rate on the labels then held, 0.597 on 652 games (operator console, ingest of 2026-10-08 14:07Z; the label sanity check ordered on 2026-10-07, when 2025 was the warm-up season). D5 (2) compares the model with a figure of that kind and was declared with it known. D5 (1), (3) and (4) were not informed by it.'"

**Correction to D9 IN FORCE (ARCHITECT 2026-10-08, addendum 15 item 1(a), #368, RULED, verbatim), superseding the
addendum 14 correction above, which stays quoted as issued:** "That correction was itself incomplete: it named one
figure and one read." The one in force:

> "For 'Prior reads of this test set: none.' read: 'No candidate has been scored on this test set. The season's home win rate and mean home margin were read before this declaration, more than once. Under the provider's labels, since found scrambled: 0.489 in the void v1 run (2026-09-30); by stage and by month in ncaa-audit, FBS 0.404 with -6.05 points (2026-10-01); 0.489 at the source in resync-diff (2026-10-01); 0.445 with -2.67 points in the #176 probe (2026-10-07). Under CFBD's labels: 0.597 with +5.23 points on non-neutral games in the same probe, which also printed both figures for the season's 64 neutral-site games; and 0.597 on 652 labelled non-neutral games (operator console, 2026-10-08 14:07Z). Declared with these figures known: D1's neutral-site rule, D4, and D5's tests (2) and (3). Fixed before any of them was read: D1's constants, and the margin of 0.010, the rating range and the 500 games, which are #79's (frozen 2026-09-30, before any run).'"

No candidate has been scored on the test set, so the registry's prior reads stay empty. D5 does not change.

**The test-season fence (addendum 14 item 2(b), #368, RULED, verbatim):**

> "Until the one run of ncaa-elo-v1r is recorded, no command prints an outcome figure of the 2025 season. ncaa-cfbd-coverage prints no 2025 home win rate in either block; counts, coverage, the season_type census and the neutral counts stay. ncaa-backtest and ncaa-audit refuse, exit 2, naming this ruling: both print 2025 rates, and the first scores a candidate. The join receipts keep listing single games with their scores; that is how a join is checked. After the run is recorded the lines and the two commands return."

In code: `ncaa_backtest.TEST_SEASON_FENCE`, lifted only by `registry` recording the run (`v1r_run_recorded`).
`ncaa-cfbd-coverage` prints "withheld until the ncaa-elo-v1r run is recorded" where a 2025 home win rate stood, in the
v1r block and in #79's block (whose 2025 sanity-read line is dropped); 2024 and 2026 lines are unchanged.
`ncaa-backtest` and `ncaa-audit` refuse with exit 2 before reading anything. `resync-diff --competition NCAA` withholds
its home win rate line when the listing includes 2025 (`--season 2025` or no season), by the ruling's first sentence.
That reading was accepted as built (addendum 15 item 1). The fence's one remaining hole, closed by addendum 15 item
1(b) (verbatim): "scripts/ncaa_source_probe.py prints the home win rate and the mean home margin for any year it is
given; the 2026-10-07 figures came from it. Until the run is recorded, for 2025 its two rate-and-margin lines print n and the withheld notice in place of the rates and margins. The rest of its receipt stays."

**What the fence does not cover (addendum 15 item 3, #372 item 2, RULED, verbatim):** "The fence covers figures across games: a rate, a margin, a count of wins. A single game listed with its score is how a defect is checked, in the join receipts and in D2's list alike. D2 orders such a game skipped, counted and listed, and the gate never scores it. Nothing is redacted."

## 2. The architect's note on D5 (verbatim)

> "Tests (2) and (3) replace #79's band rule for this declaration only, before any v1r number exists. #79's own declaration is untouched, and my sentence in addendum 10 that its acceptance numbers do not move stands for #79. For v1r the margin, the rating range and the 500 games are #79's; the calibration test is D5's."

#79's own declaration, its code (`ncaa_backtest.run_gate`, `crit_bands`) and its numbers are not changed by this
document.

## 3. Design receipt (step (a)): OK

`docs/receipts/ncaa-v1r-design-2026-10-08.md`, from `scripts/ncaa_v1r_design_receipt.py` (seeded; reads no stored
game). Stop condition: **OK**. In the first setting (110, 140), D5 (2)&(3) passes in 87.0% of seasons (the floor is
85%) and #79's band rule as coded in 29.5% (the ceiling is 60%). The other settings: (150, 170) 59.5% / 31.0%;
(190, 210) 15.5% / 24.0%. Mean slope 0.985 / 1.160 / 1.335.

These are the numbers of the current receipt, re-run after Codex's P2 on #365. The cross-conference round (I5) is now
drawn uniformly over the valid matchings by rejection sampling; the earlier randomized greedy draw was not uniform.
The first run, with the greedy draw, read 87.5% / 26.5% in the first setting; its stop condition was OK as well.
The script also imports the shared D1 wrapper (section 5). Re-running it after that change alone gave output
identical to the first receipt except the runtime line.

## 4. The registry entry

Declared through `registry.declare` (the repo's declare path), so `declared_at`, `status: declared`, `run: null`,
`verdict: null` and the checked `confirmation_plan` are the function's. `declare` keeps only its own fields, so the
keys below were added to the same entry afterwards:

| key | value | why |
|---|---|---|
| `test_set` | "NCAA FBS 2025 regular season (CFBD both-FBS labels; warm-up 2024)" | the ruling's exact string |
| `gate` | D5 verbatim, after "D5. Gate. " | |
| `confirmation_window` | D7 verbatim, after "D7. Confirmation: " | |
| `confirmation_plan` | `{n_games 100, metric log_loss, bar 0.6931, must_beat_reference true, reference "the D4 baseline on the same games minus 0.010"}` | D7's numbers; passes `registry.check_plan` |
| `training_cutoff` | none fitted; D2/D3/D4 in one line | |
| `neutral_site_rule` | `no_home_advantage_at_neutral` | the shadow's precondition (`ncaa_shadow.NEUTRAL_RULE_KEY`) |
| `constants` | `{k_factor 24.0, home_advantage 55.0, mov_base 2.2, season_regression 0.25, default_rating 1500.0}` | the shadow's precondition (`ncaa_shadow.CONSTANTS_KEY`, must equal `NCAAEloConfig()`) |
| `ratified` | the D5 note verbatim | soccer-expansion-v1's key for pre-run rulings |
| `design_receipt` | the receipt path and its verdict | |
| `prior_reads_note` | D9 verbatim, then "CORRECTION (...addendum 14 item 2(a), #368, verbatim)" and the correction | see below |

**Prior reads.** The registry records prior reads only inside a run (`run.prior_reads`, computed by
`registry.record_run` from earlier runs on the same test set or overlapping scored ids). intl-elo-v2 has its one
prior read there. A declared entry has no run, and the VOID 2026-09-30 v1 run is not in the registry. So the entry
names it in its own key, `prior_reads_note`: D9 verbatim, with the addendum 14 correction beside it in the
same note. `registry.prior_reads` on this test set returns none: no candidate has been scored on it.

## 5. The shadow on the declared stream (step (c))

`export-ncaa-predictions` (`src/walters/ncaa_shadow.py`) now walks D2's stream and checks D6. Everything else is
unchanged: engine `model_shadow`, the gate status on every row, the market block, FBS teams from current labels,
grading, never a Desk call.

- **D2 stream** (`ncaa_backtest.v1r_stream`, `V1RStream`):
  - Only games with a CURRENT label (L3). Stale labels are counted and listed; unlabelled games are counted. Neither is walked.
  - Seasons `V1R_SEASONS` = 2024, 2025, 2026, read from the label's season (the CFBD year). A current label in another season is counted (`outside`) and not walked.
  - Every stored NCAA match that carries a label is read (`load_v1r_games`), whatever our local status or scores (Codex on #365). A current label on a row we hold as SCHEDULED or unscored is walked on the label's scores, so the stream counts the same current labels the coverage fact does. Our FINISHED rows without a label are read only to be counted as unlabelled.
  - Home and away, the scores and the neutral flag are the label's (`game_from_rows`, unchanged). Team ids go through the J2 merge.
  - Order: stored kickoff, then match id. There is no stage or season_type exclusion, so postseason games are walked.
  - A level score is skipped, counted per season and listed (match id, CFBD id, season, kickoff, score).
  - Per season, the receipt prints the walked count, the season_type census, the neutral count, the count with no neutral flag, and the non-neutral home win rate.
  - `#79`'s all-division stream (`load_games` + `build_stream`) is unchanged and still feeds `ncaa-backtest`.
- **D1 wrapper.** There is one shared class, `ncaa_backtest.NeutralRuleElo`. It moved there from the shadow's own `V1R`; `ncaa_shadow.V1R` is now an alias.
  - A game whose label says neutral is priced and updated with home advantage 0: the model's cfg is replaced for the call, then restored.
  - A labelled game without a neutral flag is non-neutral and counted (`neutral_unflagged` in the file's `fit`).
  - `scripts/ncaa_v1r_design_receipt.py`'s `NeutralAwareElo` is now a subclass of it that only records the scored pairs.
  - `NCAAEloV1` is untouched.
- **D6 coverage.** `coverage_guard` checks 2024, 2025 and 2026 through `ncaa_cfbd.stored_coverage` (L2 + L3) and names every season that misses: no record, under 95%, or current labels short of the record's joined count. `fit` asks `stored_coverage` for exactly those three seasons. `ncaa-cfbd-coverage` always prints the three, plus any other season with a record, and states whether the condition holds in ALL THREE.
- **D8 rows.** Every upcoming row carries `home_adv_applied` (the listed home's, 55), `home_adv_basis` ("listed home (neutral flag unknown before the game)"), `neutral: null` and `neutral_flag: "unknown before the game"`. An upcoming game never reads a label.
- **The file's `fit`.** It now carries `walked_by_season`, `season_type_census`, `level_scores_skipped` / `level_scores_listed`, `neutral_updates`, `neutral_unflagged` and `outside_seasons_not_walked`. These replace `train_n` / `test_n` / `excluded` / `ties_skipped`, which were #79's split.

## 6. Readings (chosen where the ruling was silent; ACCEPTED AS BUILT, ARCHITECT 2026-10-08, addendum 15 item 4)

The architect's words (verbatim): "(1) A stream game's season is its label's season, and the model regresses on it.
(2) Upcoming games keep the shadow's stage skip for now, since it cannot fire on the stored stage labels. Note on
#359 that the skip has to go before bowl season: D2 and D7 take the postseason, and the shadow should too."

1. **Season.** A stream game's season is its label's season (the CFBD `--year`, the season each ingest record and the coverage fact are keyed by), not `matches.season`. That is also the season `NCAAEloV1` regresses on. Where the two differ, the ingest already lists the game.
2. **Upcoming games.** Upcoming games keep the shadow's existing stage-marker skip (`exclusion_reason`). It never fires on the stored division labels (#359). It has to go before bowl season: D2 and D7 take the postseason, and the shadow should too (noted on #359).

## 7. Not in this PR (PR B)

The gate command (D3, D4, D5), `--preflight` (D6), the one-run reservation and scored-id record (D6), and the
confirmation command and cohort freeze (D7).

## 8. Commands (PR B)

ARCHITECT 2026-10-08, addendum 11, item 3, PR B (verbatim): "PR B, after PR A: the gate command for D3 to D6 with
--preflight, the reservation and the one recorded run, on the soccer-expansion-v1 pattern; then the confirmation
command for D7 on the intl-elo-confirm pattern. #79's ncaa-backtest stays as it is." Code:
`src/walters/ncaa_v1r_gate.py`; tests: `tests/test_ncaa_v1r_gate.py` (synthetic only).

### `ncaa-v1r-gate --preflight` (D6)

- Refuses unless the entry is declared and unrun and no reservation exists (as `soccer-expansion-gate --preflight`).
- Scores nothing: no model is built, nothing is reserved or recorded.
- Prints, per season 2024 / 2025 / 2026:
  - the stream by season_type;
  - the neutral count and the no-flag count;
  - the level scores skipped;
  - the coverage line (L2 + L3).
- Then the D4 baseline, the test-set size (the 2025 `regular` games) and whether the gate's seasons (2024, 2025) and
  the confirmation's (2024, 2025, 2026) are covered.
- No 2025 or 2026 outcome is computed or printed. The architect confirms the season_type census from this output
  (D6).

### `ncaa-v1r-gate --architect-word "<the word, verbatim>"` (D3-D6): the one run

**Preconditions.** Each is checked in this order before the reservation and before the first read. Any failure
refuses with exit 2, and nothing is read or written.
  1. The entry is declared and unrun, and no reservation file exists.
  2. `OPEN_ITEMS` is empty. It ships holding D6's census confirmation, as soccer-expansion-v1's `OPEN_FINDINGS` held
     its findings. A PR quoting the architect's confirmation empties it.
  3. `--architect-word` is given and is not blank. The word is written into the reservation and the run record.
  4. 2024 and 2025 are covered (L2 + L3, `ncaa_cfbd.stored_coverage`). Each season that misses is named.

**Reservation.** `docs/registry/ncaa-elo-v1r.started.json`, the soccer-expansion-v1 pattern:
  - The registry's cross-ref guard runs first (`registry.cross_ref_guard`, #329 RULED 2026-10-08). `--no-fetch` skips
    its fetch, and the receipt says other clones were not checked.
  - The file is an exclusive create.
  - A reservation without a recorded run refuses every later attempt until the architect rules.

**First read.** `load_v1r_stream()` (D2) is called only after the reservation exists.

**Walk** (`run_gate`, pure):
  - The D4 baseline is computed first, before any test game is scored: the stream's 2024 non-neutral games whose
    season_type is exactly `regular`. A label without a neutral flag counts as non-neutral (D1).
  - The stream is walked in order with the shared D1 wrapper `NeutralRuleElo`.
  - 2024 games are update only.
  - 2025 `regular` games are predicted, then updated.
  - Every other 2025 game is walked and never scored.
  - The walk ends after the last 2025 game. Ratings are read there, for D5 (4). A 2026 game is never scored. One that
    kicks off before the last 2025 game is walked (D2: every stream game is walked) and counted.

**Verdict** (D5):
  - Under 500 scored games: INVALID.
  - PASS iff all four hold:
    - (1) log-loss < baseline − 0.010, strict and unrounded, so a tie rejects;
    - (2) |mean p − realized home rate| <= 0.05;
    - (3) |b − 1| <= 0.20, with non-convergence failing;
    - (4) every rating within 1000 to 2000.
  - (2) and (3) are `ncaa_backtest.level_gap / level_ok / logistic_slope / slope_ok`. The design receipt imports the
    same functions, so its D5 numbers and the gate's are computed identically. Re-running the receipt after the
    extraction gave output identical to before.

**Reported, never gated:** #79's bands, the constant-0.5 log-loss, Brier (model and baseline), the intercept a, cold
starts, and log-loss on neutral and non-neutral games.

**Record.** `registry.record_run`: the scored ids (sidecar + sha256), the result and the word. A second run is refused.

### `ncaa-v1r-confirm` (D7, the intl-elo-confirm pattern)

- **Refuses** unless the entry has its run (carrying the D4 `baseline_home_rate`) and a PASS verdict, and 2024, 2025
  and 2026 are covered (D6).
- **Eligible fixtures:** stored NCAA fixtures kicking off after the verdict, by kickoff then id, whose two teams, as J2
  merged ids, both carry a current label (`ncaa_shadow.fbs_teams`). Any status.
- **`--freeze-cohort`** freezes the first 100 once, through `registry.freeze_confirmation_cohort`, which calls the
  cross-ref guard before it writes.
- **`--substitute`** releases a cancelled cohort fixture and records the next eligible fixture after the cohort as its
  replacement:
  - The replacement is never cancelled itself and never one used before.
  - `registry.substitute_cohort_fixture` makes the write.
  - A finished fixture without a label is pending and never replaced. Postponed, scheduled and live fixtures stay too.
- **Scoring:** the gate's replay, i.e. the D1 wrapper over the D2 stream.
  - A cohort fixture with a current label is predicted, then updated, whatever its season_type. The label's neutral
    flag applies to the model and to the baseline.
  - The baseline is the run record's frozen D4 rate (0.5 at a neutral site).
- **`--record --ruling`** needs the frozen cohort fully labelled. It writes `registry.record_confirmation`, which
  computes CONFIRMED iff log-loss <= 0.6931 and log-loss < (D4 baseline log-loss − 0.010) on the same games. A tie
  fails.

### What was chosen where the ruling is silent (open to correction)

1. **The architect's word.** It is two things: the `OPEN_ITEMS` code gate, emptied by a PR (the soccer-expansion-v1
   pattern), and `--architect-word`, recorded.
2. **INVALID is recorded.** A run under 500 scored games is recorded as INVALID: the one read is spent. `--preflight`
   prints the test-set size beforehand.
3. **The end of the walk.** The gate walk stops after the last 2025 game. 2026 games after it are not walked; they
   cannot change anything D5 measures.
4. **A confirmation fixture without a current label** in the D2 seasons (2024-2026) stays pending. This includes a
   fixture whose label season would be 2027.
