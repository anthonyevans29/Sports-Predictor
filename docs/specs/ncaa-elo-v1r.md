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
- Its last line is the stream fingerprint (addendum 17 item 1): `STREAM FINGERPRINT <sha256 hex> (<n> games: ...)`.
  The run takes the hex as `--stream-fingerprint`.

**The fingerprint** (`ncaa_v1r_gate.stream_fingerprint`). It is a sha256 over the stream exactly as the gate walks it
(`walked()`): every stream game up to and including the last 2025 game, in walk order (stored kickoff, then match
id). Each game carries `FINGERPRINT_FIELDS`, every field the walk reads or orders by:

| field | read by |
|---|---|
| `match_id` | the scored ids; the order's tie-break |
| `utc_date` | the order (stored kickoff) |
| `season` | the label season: the split, D4, `NCAAEloV1`'s season regression |
| `season_type` | the test set (exactly `regular`), D4, the not-scored census |
| `home_id`, `away_id` | the J2 merged ids: the ratings, the cold starts |
| `home_score`, `away_score` | the result and `NCAAEloV1`'s margin of victory |
| `neutral` | D1's home advantage 0, D4's non-neutral games, the baseline's 0.5 |
| `label_source` | `NeutralRuleElo`'s count of labels without a neutral flag (reported) |

The serialization is JSON with sorted keys and no whitespace: a version tag, the field names, then one list per game.
A level score is not in the stream (D2 skips it), so it is not in the fingerprint. A 2026 game after the last 2025
game is not walked and is not in it either. A 2026 game kicking off before the last 2025 game is walked, so it is in
it.

### `ncaa-v1r-gate --architect-word "<the word, verbatim>"` (D3-D6): the one run

**Preconditions.** Each is checked in this order before the reservation. Any failure refuses with exit 2; nothing
is scored or written.
  1. The entry is declared and unrun, and no reservation file exists.
  2. `--architect-word` is given and is not blank. The word is written into the reservation and the run record.
     There is no `OPEN_ITEMS` gate (addendum 17 item 1).
  3. `--stream-fingerprint` is given and is not blank.
  4. 2024 and 2025 are covered (L2 + L3, `ncaa_cfbd.stored_coverage`). Each season that misses is named.
  5. The stream is loaded (`load_v1r_stream()`, the same read `--preflight` makes; no model is built, nothing is
     scored). Its fingerprint must equal `--stream-fingerprint`. A mismatch refuses, printing both (addendum 17 item 1).
  6. The scored set (the 2025 games whose season_type is exactly `regular`, the level scores already skipped by D2)
     must number at least 500. Under 500 the run refuses and records nothing (addendum 17 item 2, #79's rule).
  7. The D4 baseline must be defined: the stream's 2024 games include a non-neutral game whose season_type is exactly
     `regular`. Otherwise the run refuses and records nothing, as under 500; it is not an INVALID run and the read is
     not spent (addendum 21 item 4 (2)).

**Reservation.** `docs/registry/ncaa-elo-v1r.started.json`, the soccer-expansion-v1 pattern:
  - The registry's cross-ref guard runs first (`registry.cross_ref_guard`, #329 RULED 2026-10-08). `--no-fetch` skips
    its fetch, and the receipt says other clones were not checked.
  - The file is an exclusive create.
  - A reservation without a recorded run refuses every later attempt until the architect rules.
  - It carries the word, the fingerprint, the walked game count and the scored-set size.

**The first game scored** comes after the reservation exists. The walk runs over the same stream object whose
fingerprint was checked, so the stream walked is the stream the word refers to.

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
  - Under 500 scored games: the run refused before the reservation (precondition 6). `run_gate` keeps an INVALID
    verdict for that case as a pure-function backstop; `run()` cannot reach it.
  - An undefined D4 baseline: the run refused before the reservation (precondition 7). `run_gate` raises the same
    refusal as a pure-function backstop; it returns no verdict, so there is no INVALID for this case.
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

**Record.** `registry.record_run`: the scored ids (sidecar + sha256), the result, and the word with the
fingerprint beside it (`architect_word`, `stream_fingerprint`). A second run is refused.

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

### PR B's four choices: RULED (ARCHITECT 2026-10-08 18:56 ET, addendum 17)

These were "open to correction" when PR B was first built. The architect ruled on all four (verbatim):

1. **The architect's word.** "The run takes my word as --architect-word, verbatim, and writes it into the
   reservation and the run record. There is no OPEN_ITEMS gate: one lock is enough, and this is the one that leaves my
   word in the record. What the word needs is to refer to one stream. --preflight ends with one line, a fingerprint of
   the 2024 and 2025 stream exactly as the gate would walk it: the games in order, with every label field the gate
   reads. The run takes that fingerprint as a required option and refuses, before the reservation, when the stream it
   is about to walk no longer matches. The fingerprint is recorded beside the word."

   Built: `OPEN_ITEMS` is removed; `--stream-fingerprint` is required; preconditions 2, 3 and 5 above.
2. **Under 500.** "The scored set is known before any game is scored: the 2025 games whose season_type is exactly
   'regular', less the level scores. If it numbers under 500 the run refuses before the reservation and records
   nothing; no game has been scored. That is #79's rule: not scored, re-run later, the bar does not move."

   Built: precondition 6 above. This replaces "INVALID is recorded".
3. **The end of the walk.** "The walk ends after the last 2025 game: as built."
4. **A confirmation fixture without a current label.** "A confirmation fixture without a current label stays
   pending, never replaced: as built. The first 100 fixtures after an October verdict are all 2026 games, so the 2027
   case cannot arise in this cohort."

**Consequence of rulings 1 and 2 for D6's "a reservation written before the first read".** Both refusals come before
the reservation and need the stream, so the run now loads the stream (the read `--preflight` already makes: counts
and the fingerprint, nothing scored) before the reservation. The reservation still precedes the first game scored.

### #375's two readings: RULED (ARCHITECT 2026-10-09, addendum 21 item 4)

The architect ruled on the two readings PR B made (verbatim, each):

1. **The stream read before the reservation: ACCEPTED.** "What D6 seals is the scoring of the test season: a game priced by the candidate and compared with its result. Loading the stream to fingerprint it and to count the scored set scores nothing and prints no figure across games; the preflight makes the same load. The reservation is written before any game is scored."

   This is the reading in the paragraph above ("Consequence of rulings 1 and 2"), accepted as written. Nothing
   changed in the code.
2. **An undefined D4 baseline.** "When 2024 has no non-neutral regular game, D4 is undefined and nothing can be scored: the run refuses before the reservation and records nothing, as it does under 500 games. It is not an INVALID run and the read is not spent."

   Built: precondition 7 above. It replaces the earlier path, which reserved, walked nothing and recorded an INVALID
   run with 0 scored ids.

## 9. The run and the verdict: FAIL (ARCHITECT 2026-10-09, addendum 24)

The one run was made on the operator's laptop on the architect's word and spliced into main by cherry-pick from
`laptop/ncaa-elo-v1r-run-record` at 130b481, byte for byte (`docs/registry/experiments.json` blob 362c9b7 before the
verdict, `docs/registry/ids/ncaa-elo-v1r.txt` f73c15a, `docs/registry/ncaa-elo-v1r.started.json` da8bb22). The
verdict was then recorded with `registry.record_verdict("ncaa-elo-v1r", "FAIL", <ruling>)`; the entry's status is
`closed`, the verdict's recorded time 2026-10-09T17:49:27Z.

### The run's figures, from the record (`run.result` of the registry entry; rounded to six places here)

- Run at 2026-10-09T16:18:32Z; 762 scored games (the 2025 regular season), ids `docs/registry/ids/ncaa-elo-v1r.txt`,
  ids sha256 `d1951e833d3eded5424a3afb89eb101e7a671bb34fbc0ba1c4133ab176a2913b`; prior reads 0.
- Stream fingerprint `8019c4ffc49c9cf1f46eaf1c286894dced92fa7beaedfd59d1aec8ee839780ea`, 1606 stream games; walked by
  season 798 (2024) and 808 (2025), 2026 walked 0, not walked after the last 2025 game 274; 2025 walked, not scored:
  postseason 46. Census: 2024 regular 752 and postseason 46; 2025 regular 762 and postseason 46; 2026 regular 274.
  Coverage 2024 1.0, 2025 1.0. Level scores skipped: none. Neutral updates 140, unflagged 0.
- D4 baseline: home rate 0.594142 on 717 games (the 2024 non-neutral regular season).

D5's four tests (PASS iff all four hold):

| Test | Record | Criterion | Result |
|---|---|---|---|
| (1) Margin | model log-loss 0.559642; baseline 0.674889 | < bar 0.664889 (baseline - 0.010) | passes |
| (2) Level | mean home probability 0.573688; realized home rate 0.591864; gap -1.818pp | within 5pp | passes |
| (3) Spread | slope b 1.420537 (fit converged: True) | 0.80 to 1.20 | FAILS |
| (4) Range | ratings 1121.1 to 1906.2 over 136 teams; outliers none | 1000 to 2000 | passes |

The record's verdict field: "FAIL — (3) spread".

Reported, never gated: intercept a -0.007828; constant-0.5 log-loss 0.693147; Brier model 0.189646, baseline 0.240928;
log-loss neutral 0.633099 (n 23), non-neutral 0.557355 (n 739); cold starts 2. #79's 10pp bands:

| Band | n | Stated | Realized | Gap | #79's rule (information) |
|---|---|---|---|---|---|
| 0-10% | 3 | 0.074476 | 0.000000 | -7.45pp | not gated |
| 10-20% | 13 | 0.168125 | 0.153846 | -1.43pp | not gated |
| 20-30% | 60 | 0.257371 | 0.183333 | -7.40pp | not gated |
| 30-40% | 67 | 0.353163 | 0.298507 | -5.47pp | not gated |
| 40-50% | 113 | 0.450779 | 0.424779 | -2.60pp | ok |
| 50-60% | 141 | 0.550102 | 0.581560 | +3.15pp | ok |
| 60-70% | 155 | 0.647678 | 0.683871 | +3.62pp | ok |
| 70-80% | 119 | 0.744848 | 0.806723 | +6.19pp | outside 5pp |
| 80-90% | 78 | 0.846718 | 0.935897 | +8.92pp | not gated |
| 90-100% | 13 | 0.927967 | 1.000000 | +7.20pp | not gated |

The architect's word for the run, as the record holds it: "ARCHITECT, 2026-10-09 12:16 ET: the preflight is read and clean, and I confirm the season_type census: 2024 regular 752 and postseason 46; 2025 regular 762 and postseason 46. The D4 baseline is 0.594142 on 717 games and the test set numbers 762. Run ncaa-elo-v1r once on the stream 8019c4ffc49c9cf1f46eaf1c286894dced92fa7beaedfd59d1aec8ee839780ea."

### The ruling, verbatim (ARCHITECT 2026-10-09 12:30 ET, addendum 24 item 1; the registry entry's `verdict.ruling`)

"ARCHITECT, 2026-10-09 12:30 ET. ncaa-elo-v1r: FAIL. The one run (recorded 2026-10-09T16:18:32Z; 762 scored games, the 2025 regular season; ids sha256 d1951e833d3eded5424a3afb89eb101e7a671bb34fbc0ba1c4133ab176a2913b; stream 8019c4ffc49c9cf1f46eaf1c286894dced92fa7beaedfd59d1aec8ee839780ea) passes three of D5's four tests and fails the third. (1) Margin: model log-loss 0.559642 against a bar of 0.664889, the baseline's 0.674889 less 0.010: passes. (2) Level: mean home probability 0.573688, realized home rate 0.591864, a gap of 1.818pp against 5pp: passes. (3) Spread: slope b 1.420537, outside 0.80 to 1.20: fails. (4) Range: ratings 1121.1 to 1906.2 over 136 teams, inside 1000 to 2000: passes. D5 reads PASS iff all four hold, so the verdict is FAIL. The bar does not move and the run is not repeated. No confirmation window opens and no cohort is frozen. College football stays market-only. The 2025 regular season is retired as a college test season with this run: its figures now show how to correct the candidate, and a second candidate scored on it would be fitted to it. A later college candidate may train on 2024 and 2025, and declares the 2026 regular season, as it accrues, as its test."

### What the verdict changes (addendum 24 item 2), as built

- (b) `registry.RETIRED_TEST_SETS` retires this test set ("NCAA FBS 2025 regular season (CFBD both-FBS labels; warm-up 2024)"): ncaa-elo-v1r was its last candidate;
  declare "the NCAA FBS 2026 regular season as it accrues (>= 500 games)" instead.
- (c) `ncaa-backtest` refuses, exit 2, naming the ruling, with or without `--baselines-only`, for good. `GATE_STATUS`
  is `CLOSED` and its line carries the ruling's date (2026-10-09). The module `ncaa_backtest` stays.
- (d) `export-ncaa-predictions` refuses, exit 2, naming the ruling, while the registry records a verdict other than
  PASS for ncaa-elo-v1r. No college shadow file has been written. `ncaa-shadow-grade` is untouched.
- (e) The #368 test-season fence lifted by itself when the run record reached main (`v1r_run_recorded`): the 2025
  lines of `ncaa-cfbd-coverage` and `resync-diff`, and `ncaa-audit`, return. No code.
- No confirmation window opens and no cohort is frozen. College football stays market-only. The next candidate is
  the architect's to declare; nothing is built toward it.
