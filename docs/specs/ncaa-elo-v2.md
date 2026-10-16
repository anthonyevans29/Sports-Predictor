# ncaa-elo-v2 — declaration (GATE-CLASS; declared before any 2026 game is scored by anyone)

Registry id `ncaa-elo-v2` (docs/registry/experiments.json), status `declared`, run and verdict null. ARCHITECT
2026-10-16 07:53 ET, addendum 81, item 2 (the declaration), item 4 (the order). Roadmap lane `ncaa` (#79).

**Nothing here runs the gate.** This PR is the declaration PR of item 4: "the registry entry, docs/specs/ncaa-elo-v2.md
with D1-D11 verbatim, the gate command parameterised, the fit's printout, --preflight for both streams; nothing run".
The fit of s (D1) reads the 2024 and 2025 training games only. Its printout is the operator's, on this PR, and the PR
freezes s from it (section 4). The 2023 ingest is its own PR, due by 2026-11-01. The run is 2026-11-09, on the
architect's word.

Test set (registry `test_set`, exact): "NCAA FBS 2026 regular season as it accrues (CFBD both-FBS labels; training and warm-up 2024 and 2025)".

## 1. What v1r showed (addendum 81 item 1, verbatim)

> "1. WHAT v1r SHOWED (the FAIL of 2026-10-09, registry ncaa-elo-v1r, verbatim in part): margin passed (0.5596 vs the bar 0.6649), level passed (1.8pp), range passed, SPREAD FAILED: slope b 1.4205 outside 0.80-1.20. b above 1 means the model's log-odds are too timid: outcomes were more decided than the ratings said. That is one knob — the map from rating difference to probability — and the ruling of 10-09 allows exactly this: "its figures now show how to correct the candidate. A later college candidate may train on 2024 and 2025, and declares the 2026 regular season, as it accrues, as its test.""

## 2. The declaration (addendum 81 item 2, RULED, verbatim)

The heading as issued: "2. THE DECLARATION, ncaa-elo-v2 (D1-D9, frozen now, before any 2026 game is scored by anyone):"

> D1. Candidate: NCAAEloV1's structure and constants (k_factor 24, home_advantage 55, mov_base 2.2, season_regression 0.25, default_rating 1500, neutral rule no_home_advantage_at_neutral) with ONE fitted parameter: the logistic scale s in P(home) = 1 / (1 + 10^(-(dr + ha) / s)), fitted by maximum likelihood on the 2024 and 2025 regular-season games of the stream (D2) and then frozen; v1 is s = 400. Code's PR prints the fitted s, the fit's log-likelihood curve at s = 300..500 by 25, and the slope b that the fitted s gives on 2025 (a read of the training set, reported, not a gate). Nothing else is fitted.

> D2. Stream: as v1r's D2 (stored NCAA games with a current CFBD both-FBS label, seasons 2024, 2025, 2026, kickoff then id; labels give home/away, scores, neutral; level scores skipped, counted, listed), plus 2023 under D10.

> D3. Split: 2024 and 2025 are training (the fit of s) and warm-up (update); the test set is the 2026 games whose season_type is exactly 'regular', scored when the 500th is final and labelled (the roadmap's step, 2026-11-08; 274 were final at 2026-10-09). The gate scores no 2026 game before that day and no game after the run's stream fingerprint is taken.

> D4. Baseline: as v1r's D4, over the stream's 2024 AND 2025 non-neutral regular-season games (one number, frozen at --preflight, printed).

> D5. Gate: v1r's D5 verbatim — under 500 scored games INVALID; PASS iff margin (model log-loss < baseline − 0.010, ties reject), level (|mean p_home − home rate| ≤ 5pp), spread (b within 0.20 of 1, non-convergence fails), range (ratings within 1000-2000) — on the 2026 scored set. The reported-never-gated figures as v1r's.

> D6. Preconditions, in code: --preflight prints the census and the fingerprint; the run takes my word and the fingerprint; one run; the reservation before the first scored game (ncaa-v1r-gate's machinery, parameterised by registry id, not copied). 2023's coverage (D10) is a precondition of the SECOND read, not of the gate.

> D7. Confirmation: as v1r's D7 (the first 100 stored fixtures after the verdict, frozen once; CONFIRMED iff log-loss ≤ 0.6931 and < the D4 baseline − 0.010 on the same games).

> D8. As v1r's D8: PASS and CONFIRMED make no call; the Desk stays market-only for NCAA until a separate policy ruling needing the neutral flag before kickoff and the shadow's record against the close (vs_close on the lane).

> D9. Prior reads: the 2026 season's games through 2026-10-09 (274 both-FBS finals) were walked by v1r's shadow exports and by nothing scored; no candidate has been scored on 2026; this declaration is written with v1r's 2025 figures known (item 1), and with no figure of 2026 read beyond the shadow's own rows, which carry no verdict.

> D10. THE SECOND READ (older season as test — RULED generally here): a season that predates every training season, whose games the candidate never walked, is a legitimate additional test, and it can only BLOCK: the lane goes live only if BOTH the gate (D5 on 2026) and the second read pass; a second read that fails is a FAIL of the candidate. For v2: the 2023 FBS regular season, labels from CFBD (792 both-FBS completed games listed as of the 10-13 probe), the games from the provider's 2023 listing (3,720 listed), ingested whole by Code's PR before 2026-11-01, read ONCE by the run: ratings start at default_rating for every team (no 2022 warm-up: a cold start, so the first 4 weeks' games are walked and not scored; the scored set is 2023 regular games from week 5, which must number ≥ 500 or the second read is INVALID and I rule again), the fitted s applied, D5's four tests with D4's baseline taken from 2023's own weeks 1-4 non-neutral games. Safeguards: the season is declared whole here, nothing of it is fitted, and its census (--preflight) is read by me before the run; the run is the same one run (one word, one fingerprint covering both streams).

> D11. Kalshi close as a benchmark: kalshi_settled_markets (KXNCAAFGAME, from 2025-08-23) is read beside the verdict for the 2026 scored games where a row exists — reported, never gated — and 2023 has none; nothing in D5 moves for it. (That read waits on the table's first NCAA pull, a later block.)

## 3. The registry entry

The entry was declared through `registry.declare`, the repo's declare path. So `declared_at`, `status: declared`,
`run: null`, `verdict: null` and the checked `confirmation_plan` come from that function. `declare` keeps only its
own fields, so the keys below were added to the same entry afterwards, as for v1r:

| key | value | why |
|---|---|---|
| `test_set` | the string above | RETIRED_TEST_SETS names "the NCAA FBS 2026 regular season as it accrues" for the next college candidate |
| `gate` | D5 verbatim, after "D5. Gate: " | |
| `confirmation_window` | D7 verbatim, after "D7. Confirmation: " | |
| `confirmation_plan` | `{n_games 100, metric log_loss, bar 0.6931, must_beat_reference true, reference "the D4 baseline on the same games minus 0.010"}` | v1r's D7 numbers ("as v1r's D7"); passes `registry.check_plan` |
| `training_cutoff` | s only, then D2, D3 and D4 in one line | |
| `neutral_site_rule` | `no_home_advantage_at_neutral` | D1 |
| `constants` | `{k_factor 24.0, home_advantage 55.0, mov_base 2.2, season_regression 0.25, default_rating 1500.0}` | D1: v1's, untouched |
| `logistic_scale` | `{s, fit, rule}`: declared `{s: null, fit: null}`; frozen at s = 279.14222651259433 by addendum 93 | D1: s is frozen here, from the fit's printout (section 4); the run refuses while it is null |
| `second_read` | D10 verbatim | |
| `benchmark` | D11 verbatim | |
| `ratified` | D10's general ruling, verbatim | soccer-expansion-v1's key for pre-run rulings |
| `prior_reads_note` | D9 verbatim | `registry.prior_reads` on this test set returns none: no candidate has been scored on it |

## 4. The fit of s (D1)

`python cli.py ncaa-fit-scale --id ncaa-elo-v2` (`src/walters/ncaa_scale_fit.py`) is read-only. It writes nothing and
scores no 2026 game.

**The procedure, declared here before any fit is run:**

- **The model.** The shared D1 wrapper with s: `ncaa_backtest.NeutralRuleElo(scale=s)` over `ncaa_elo.NCAAEloV2`.
  - s replaces 400 in the stated P(home) = 1 / (1 + 10^(-(dr + ha) / s)), and nowhere else.
  - **Price only, update at 400** (ARCHITECT 2026-10-16, addendum 86 item 3, Q1, verbatim): "PRICE ONLY. s enters the stated probability and nothing else; the update keeps v1's expected score at /400, so the ratings walk exactly as NCAAEloV1's do and v1r's ratings are v2's ratings. That is what D1 means by "NCAAEloV1's structure and constants" with ONE fitted parameter and "nothing else is fitted": a scale inside the update changes the rating dynamics (the effective K), which is a second knob under one name. intl-elo-v2's reading is the house's; NHLEloV8 fitted its divisor inside the update as a different declaration."
  - In code: `NCAAEloV2` overrides `predict` only. Its update is `NCAAEloV1.update`, whose expected score is `NCAAEloV1._expected_home` at /400.
  - So at every s the ratings walk exactly as v1's do, rating for rating, neutral games included. Only the stated probability moves (tested).
  - At s = 400, v2 is v1 exactly: same probabilities, same ratings (tested).
- **The games.**
  - The D2 stream's 2024 and 2025 games, in stream order. Every one is walked: predict, then update. Postseason games and games without a season_type are walked.
  - The likelihood is over the games whose season_type is exactly 'regular'.
  - `fit()` refuses any game of another season, so no 2026 game is walked or read.
  - v1r's walk also updated on any 2026 game kicking off before the last 2025 game. The fit does not, and its printout says how many there are (none are expected).
- **The likelihood of s.** The sum of log P(result) over those games. Each game is priced before its own update by a fresh model walking from the first 2024 game. That is a cold start: the stream starts in 2024. p is clipped as `ncaa_backtest._ll` clips it (1e-12).
- **The search.**
  - First the grid: s from 100 to 1000 by 5. The best grid value wins; an exact tie goes to the value nearer 400.
  - Then a golden-section search for the maximum within one grid step either side, inside the bracket, until the interval is narrower than 1e-6.
  - The fitted s is the best of all the points evaluated.
  - A best grid value at either end of the bracket prints ON THE BRACKET EDGE. The bracket is not widened after the fact; the architect rules.
- **The printout (D1's three figures and two checks):**
  - the training stream: its counts, the 'regular' count per season, and its training fingerprint;
  - the search: the walks, and the best grid value;
  - the curve at s = 300..500 by 25: the log-likelihood and the mean log-loss it implies;
  - **FITTED s**, printed exactly (Python's repr, which round-trips), with its log-likelihood;
  - the slope b (and intercept a) that the fitted s gives on 2025's 'regular' games, using D5 (3)'s `ncaa_backtest.logistic_slope`. This is a read of the training set, reported, not a gate;
  - CHECK, against v1r's recorded run: at s = 400, b on 2025 against v1r's recorded 1.420537 (REPRODUCED or NOT REPRODUCED, to 1e-9), and v1r's stream fingerprint today against the recorded one (SAME or CHANGED).
  - The check reads v1r's own run record. 2025 is v1r's retired test season, and its figures were ruled on 2026-10-09.
- **Frozen.** The operator pastes the printout on this PR. The PR then writes s into the entry exactly as printed (`logistic_scale.s`), with `fit` = the training fingerprint, the training game count, the log-likelihood and the receipt. The run reads s from there. `--preflight` prints it, beside whether today's 2024-2025 stream is still the one the fit read (SAME, or CHANGED since the fit). On CHANGED, the frozen s stands, the line says so, and the architect reads it before the word; the run does not refuse. A frozen s whose `fit` records no training fingerprint reads UNKNOWN, never CHANGED.
- **FROZEN: s = 279.14222651259433** (ARCHITECT 2026-10-16, addendum 93). The registry entry holds it in `logistic_scale.s`, exactly as printed, with `logistic_scale.fit`:
  - the training fingerprint `a5568a48718d7ea18e7d397c8c3be4ff11c03651574c38cbcf6d06f882f3ab47`;
  - regular games 2024 752 / 2025 762;
  - log-likelihood −870.104578;
  - b_2025 0.991330;
  - fitted 2026-10-16 by the operator's block, at #553's head 4790737.
  - The fit, as read (addendum 93 item 1, verbatim): "training stream 1,606 games walked (2024 798, 2025 808); in the likelihood 1,514 'regular' games (2024 752, 2025 762); 216 walks; best grid value 280 (inside the bracket, not on an edge); FITTED s = 279.14222651259433, log-likelihood −870.104578, mean log-loss 0.574706 (at s = 400: −882.854996, 0.583127; the curve falls monotonically from 300 to 500). b on 2025 at the fitted s: 0.991330 (intercept −0.0078) — in-sample, reported, not a gate; it says the fit did what D1 asked and nothing about 2026. Both reproduction checks hold: b at s = 400 on 2025 = 1.420537 vs v1r's recorded 1.4205373351680064 → REPRODUCED; v1r's stream fingerprint today 8019c4ff… = recorded → SAME. Later-season games before the last 2025 game: 0. Cross-check (mine, arithmetic): 400 / 1.42054 = 281.6, within one grid step of the fitted value, as a price-only rescale should be. Nothing scored on 2026, nothing reserved, nothing written"
  - The console is logs/ncaa_fit_scale_2026-10-16.txt (19 lines), posted on #553.

## 5. The gate, parameterised by registry id (D6)

`src/walters/ncaa_v1r_gate.py` is the machinery v1r ran. Every function now takes the declaration it serves as a
`Spec`; `spec_of(id)` refuses an id it does not serve. The default is v1r's, so v1r is unchanged:

- `ncaa-v1r-gate` and `ncaa-v1r-confirm` keep their names and output;
- `tests/test_ncaa_v1r_gate.py` passes unchanged;
- a before/after capture of the pure outputs on four synthetic streams matched byte for byte: run_gate, the fingerprint, the preflight dict and lines, run_lines and the run record.

v2's `Spec` differs in data only. The new commands are `ncaa-gate --id ID` and `ncaa-confirm --id ID`; with
`--id ncaa-elo-v1r` they are the v1r commands. What v2 adds:

- **D1:** the model is the D1 wrapper at the FROZEN s, read from the registry entry. The run refuses while s is not frozen, before anything is read.
- **D2 and D3:** the stream is 2024-2026, as v1r's. 2024 and 2025 are update only. The test set is the 2026 games whose season_type is exactly 'regular', predicted then updated. The walk ends after the last 2026 game in the stream: no game after the fingerprint is taken.
- **D4:** one number, the 2024 AND 2025 non-neutral 'regular' home win rate, and 0.5 at a neutral site. It is printed at `--preflight`. The run computes it from the same stream, before the first scored game. The fingerprint check makes it the number the architect read.
- **D5:** v1r's four tests, the same functions (`run_gate`), on the 2026 scored set.
- **D6, in code**, in this order, each refusal exit 2 with nothing written:
  1. declared and unrun, and no reservation;
  2. the word given;
  3. the fingerprint given;
  4. s frozen;
  5. 2024, 2025 and 2026 covered (L2 + L3);
  6. then one read of both streams (`load_streams`). The run refuses unless the fingerprint matches, the 2026 scored set numbers at least 500, and D4 is defined.
  7. Then the reservation, after the #329 cross-ref guard, carrying the word, the fingerprint, s and the second read's state. Then the walk.
  - One run. The scored ids recorded are those of both reads.
- **The fingerprint** covers both streams, each as its read walks it. The 2023 games carry the week too, because D10 reads it. Its tag is `ncaa-elo-v2 stream fingerprint v1`.
- **The run record:**
  - the gate's result;
  - `second_read`, the second read's result;
  - `verdict_gate`;
  - `verdict`, combined by D10;
  - `logistic_scale`;
  - `scored_ids_by_read`, each read's count and sha256. The sidecar holds every id the run scored.
- **D7** (`ncaa-confirm --id ncaa-elo-v2`): v1r's machinery. The cohort is scored by v2's replay: its stream, the D1 wrapper at the frozen s.
- **D8:** no call. Every PASS line says the Desk stays market-only for NCAA.

## 6. The second read (D10)

- **The stream.** Stored NCAA games carrying a current CFBD both-FBS label of season 2023, kickoff then match id, level scores skipped. It comes from the same read as the main stream (`ncaa_backtest.load_v1r_streams`), and the same J2 merge applies.
- **The walk.** A fresh model at the frozen s, every team at default_rating: a cold start. Every 2023 game in the stream is walked, postseason included (D2's rule), and the range test reads the ratings after the last 2023 game walked.
- **Scored.** 2023 games whose season_type is exactly 'regular' and whose week is 5 or later.
- **The baseline (D4 of the second read).** 2023 'regular' games with a week before 5, non-neutral; 0.5 at a neutral site.
- **The week.** CFBD's `week` as served. The label table does not store it yet: the 2023 ingest PR (item 4, by 2026-11-01) adds it. Until then every game reads week unknown (`Game.week` None, law 4). A 'regular' game with no week is walked, never scored and never in the baseline, and is counted in the census. If CFBD serves a week 0, its games sit in the baseline with weeks 1-4: "weeks before 5".
- **Its preconditions never refuse the run.** These are 2023 covered (L2 + L3), its baseline defined, and 500 scored. They are printed at `--preflight`, and the architect reads the census before the run. They are carried in the reservation, and they decide the second read's result:
  - NOT READ, when 2023 is not covered;
  - INVALID, when the baseline is undefined or fewer than 500 games are scored. Then the architect rules again.
- **The combined verdict** (computed; the architect rules):
  - PASS iff both pass;
  - FAIL if either fails ("a second read that fails is a FAIL of the candidate");
  - otherwise NO VERDICT, and the architect rules again.

## 7. D11

D11's read waits on "the table's first NCAA pull, a later block". Nothing here reads `kalshi_settled_markets`. The
run records the 2026 scored ids, so the benchmark can be read beside the verdict once the table holds NCAA rows.
Nothing in D5 moves for it.

## 8. Interpretations (as built; each for the architect's confirmation)

- **I1, price only, update at 400. RULED** (ARCHITECT 2026-10-16, addendum 86 item 3, Q1, verbatim): "PRICE ONLY. s enters the stated probability and nothing else; the update keeps v1's expected score at /400, so the ratings walk exactly as NCAAEloV1's do and v1r's ratings are v2's ratings. That is what D1 means by "NCAAEloV1's structure and constants" with ONE fitted parameter and "nothing else is fitted": a scale inside the update changes the rating dynamics (the effective K), which is a second knob under one name. intl-elo-v2's reading is the house's; NHLEloV8 fitted its divisor inside the update as a different declaration." (section 4).
- **I2, the gate run's coverage.** The run needs 2024, 2025 and 2026 covered, the seasons it walks. v1r's D6 named the seasons its run walked (2024, 2025), and D6 of v2 makes only 2023's coverage a precondition "of the SECOND read, not of the gate".
- **I3, "frozen at --preflight".** The number --preflight prints is the number the run uses. The fingerprint check guarantees it; there is no separate store.
- **I4, "The gate scores no 2026 game before that day".** The run's 500 refusal enforces it. There is no date check: the roadmap's 2026-11-08 is a projection (the roadmap's own rule for a calendar step).
- **I5, the weeks.** As section 6.
- **I6, the second read's walk.** Every 2023 game is walked, postseason included, and the range is read after the last 2023 game.
- **I7, what the second read's preconditions do.** They decide its result and never refuse the run (section 6).
- **I8, the ids sidecar.** It holds both reads' ids, each read's count and sha256 in the result.
- **I9, the fit's games.** It walks 2024 and 2025 only, strictly (section 4).
- **I10, the frozen s.** Exactly as printed. A CHANGED training stream is printed, not refused (section 4).

## 9. Questions for the architect: both RULED (ARCHITECT 2026-10-16, addendum 86 item 3)

- **Q1 (D1), RULED: price only, update at 400.** The question was whether s enters the expected score the update reads, or only the price. Verbatim: "PRICE ONLY. s enters the stated probability and nothing else; the update keeps v1's expected score at /400, so the ratings walk exactly as NCAAEloV1's do and v1r's ratings are v2's ratings. That is what D1 means by "NCAAEloV1's structure and constants" with ONE fitted parameter and "nothing else is fitted": a scale inside the update changes the rating dynamics (the effective K), which is a second knob under one name. intl-elo-v2's reading is the house's; NHLEloV8 fitted its divisor inside the update as a different declaration."
  - As first built, s entered both. The PR now follows the ruling: `NCAAEloV2` overrides the price alone (section 4, I1).
- **Q2 (a 2026 fence), RULED: yes, in a separate small PR after this one merges and before 2026-11-09.** Verbatim: "YES, a 2026 fence, in v1r's form, as a SEPARATE small PR after #553 merges and before 2026-11-09: until v2's one run is recorded, no command prints an outcome figure of the 2026 season (a rate, a margin, a count of wins). ncaa-cfbd-coverage prints no 2026 home win rate or margin in either block (counts, coverage, census and neutral counts stay); ncaa-audit with 2026 among its seasons refuses, exit 2, naming this ruling (its default seasons become 2025 alone until the run); resync-diff --competition NCAA and scripts/ncaa_source_probe.py keep their single-game listings (the level ruling: a game with its score is how a defect is checked) and drop any aggregate outcome line over 2026. D9 of v2 already records every 2026 read to date; the fence keeps that list from growing. Gates bind more under the income goal, never less."
  - The question listed the four reads that print 2026 outcome figures today: `ncaa-cfbd-coverage` (both blocks), `ncaa-audit` (default seasons 2025 and 2026), `resync-diff --competition NCAA` and `scripts/ncaa_source_probe.py`.
  - Nothing in this PR changes them. The fence is its own PR.

**A note on D9, not a question.** D9 says the 2026 games through 2026-10-09 "were walked by v1r's shadow exports".
The shadow's verdict refusal, addendum 24 item 2(d), verbatim in `ncaa_shadow.VERDICT_REFUSAL`, reads "No shadow
file has been written". If that held, no shadow walk reached a file. D9 as declared records more reads than that,
never fewer, so it stands as issued.

## 10. The order from here

1. This PR is open, its checks green, nothing run (roadmap step, due 2026-10-20).
2. Q1 is ruled: price only (addendum 86 item 3). Q2 is ruled: a 2026 fence, its own PR after this one merges and before 2026-11-09.
3. The architect reads `ncaa-fit-scale` and writes the operator's block. The operator runs it on the laptop and pastes the printout on this PR. Nothing is run before that block.
4. The PR freezes s and the architect merges. The 2026 fence PR follows (Q2).
5. The 2023 ingest PR lands by 2026-11-01: the provider's 2023 listing whole, the CFBD 2023 labels and their week.
6. The 500th 2026 game is final and labelled (projected 2026-11-08). `python cli.py ncaa-gate --id ncaa-elo-v2 --preflight` goes to the architect.
7. The one run, on the word and the fingerprint (2026-11-09).
8. The #493 PR comes after both PRs, its dry-run receipt before merge.
