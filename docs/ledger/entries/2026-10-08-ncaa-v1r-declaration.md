**2026-10-08 — DECLARATION (ARCHITECT, addendum 11, item 3, PR A): ncaa-elo-v1r declared in the registry (status declared, not run); design receipt OK; the shadow walks the declared stream and checks 2024, 2025 and 2026.**
- **Declaration (RULED, verbatim):**
  - "D1. Candidate: NCAAEloV1 with its constants untouched: k_factor 24, home_advantage 55, mov_base 2.2, season_regression 0.25, default_rating 1500. neutral_site_rule is no_home_advantage_at_neutral: a game whose label says neutral is priced and updated with home advantage 0. A label without a neutral flag is treated as non-neutral and counted.
  - D2. Stream: stored NCAA games that carry a current CFBD both-FBS label, seasons 2024, 2025 and 2026, in order of stored kickoff then match id. Home and away, the scores and the neutral flag come from the label; team ids are merged as J2 rules. Every such game is walked, postseason included. A game with level scores is a data defect: skipped, counted and listed.
  - D3. Split: 2024 is warm-up, update only. The test set is the 2025 games whose season_type is exactly 'regular': predict, then update. A 2025 game with any other season_type, or none, is walked and never scored. The gate scores no 2026 game.
  - D4. Baseline: one number, frozen before any test game is scored: the home win rate of the stream's 2024 non-neutral games whose season_type is 'regular'. It is the baseline's home probability in every non-neutral test game; at a neutral site the baseline is 0.5.
  - D5. Gate. Under 500 scored games the run is INVALID. PASS iff all four hold on the scored games. (1) Margin: model log-loss < baseline log-loss - 0.010, unrounded; ties reject. (2) Level: the mean of the model's home probabilities and the realized home win rate differ by no more than 5pp. (3) Spread: the calibration slope b lies within 0.20 of 1, where b is the slope of the maximum-likelihood logistic fit of the result on the model's log-odds, logit P(home win) = a + b * logit(p), with p clipped to [0.000001, 0.999999]; a fit that does not converge fails. (4) Range: every rating after the last 2025 game walked lies within 1000 to 2000. Reported, never gated: #79's 10pp bands, the constant-0.5 log-loss, Brier, the intercept a, cold starts (a team's first game in the stream), and the log-loss split neutral and non-neutral.
  - D6. Preconditions, in code. The gate run refuses unless 2024 and 2025 are covered as L2 and L3 rule; the shadow and the confirmation read refuse unless 2024, 2025 and 2026 are. If a season misses, nothing in this declaration bends to fit it: I rule again. The run is one run: a reservation written before the first read, the scored ids recorded, and it starts only on my word. --preflight scores nothing and prints, per season, the stream by season_type, the neutral count, the coverage and the D4 baseline. I confirm the season_type census before the run.
  - D7. Confirmation: the first 100 stored NCAA fixtures, by kickoff then id, that kick off after the verdict and whose two teams, as merged ids, both carry a current label at the freeze; any status; frozen once by fixture id with the intl-elo-v2 machinery. A cancelled fixture is released and replaced by the next eligible one. A finished fixture without a label is pending, never replaced. Scored by the same replay as the gate, the label's flags applied, every cohort fixture whatever its season_type. CONFIRMED iff log-loss <= 0.6931 and < the D4 baseline's log-loss - 0.010 on the same games. confirmation_plan: n_games 100, metric log_loss, bar 0.6931, must_beat_reference true, reference the D4 baseline on the same games minus 0.010.
  - D8. What a pass does not do. PASS and CONFIRMED do not make college football a call. The Desk stays market-only for NCAA until a separate policy ruling, and that ruling needs the neutral flag before kickoff and the shadow's record against the close. Until then the shadow prices an upcoming game with the listed home's advantage and says on the row that the neutral flag is unknown.
  - D9. Prior reads of this test set: none. The 2026-09-30 run of v1 (all divisions, scrambled 2025 labels, VOID by the 2026-10-01 ruling) scored 2026 games; the entry names it."
- **Note on D5 (architect, verbatim):** "Tests (2) and (3) replace #79's band rule for this declaration only, before any v1r number exists. #79's own declaration is untouched, and my sentence in addendum 10 that its acceptance numbers do not move stands for #79. For v1r the margin, the rating range and the 500 games are #79's; the calibration test is D5's."
- **Step (a), the design receipt (stop condition OK):**
  - A seeded simulation that reads no stored game: `scripts/ncaa_v1r_design_receipt.py` → `docs/receipts/ncaa-v1r-design-2026-10-08.md`, MASTER_SEED 20261008.
  - **Spec (verbatim):** "130 teams in 10 conferences of 13. True strength in Elo points = a conference effect plus a team effect, both normal, in three settings of (conference sd, team sd): (110, 140), (150, 170), (190, 210). Team effects carry to the next season with persistence 0.85, the spread kept. Each season: 3 rounds of random cross-conference pairings, then 8 rounds of random in-conference pairings; home side by coin flip; 6% of games neutral. Margin = normal with mean (home strength - away strength + 55 unless neutral) / 21.5 points and sd 14, rounded, never level. One warm-up season from flat 1500, update only, then the test season scored predict-then-update under D1. 200 seeded seasons per setting. Report per setting: mean scored games, the model's mean slope, and the share of seasons passing #79's band rule as coded and passing D5 (2) and (3)."
  - **Stop condition (verbatim):** "If yours contradict mine beyond noise (in the first setting the model passing D5 (2) and (3) in fewer than 85% of seasons, or passing the band rule in more than 60%), stop: write no entry and tell me."
  - **Result:**

    | setting | mean scored | mean slope | band rule as coded | D5 (2)&(3) |
    |---|---|---|---|---|
    | (110, 140) | 675 | 1.000 | 26.5% | 87.5% |
    | (150, 170) | 675 | 1.158 | 32.0% | 65.0% |
    | (190, 210) | 675 | 1.337 | 27.5% | 14.5% |

  - Architect's numbers: slope 0.99 / 1.16 / 1.33; band rule 32% / 33% / 29%; D5 (2) and (3) 92% / 60% / 13%.
  - **OK:** in the first setting D5 (2)&(3) passes in 87.5% of seasons (the floor is 85%) and the band rule in 26.5% (the ceiling is 60%).
  - **Used as found:** NCAAEloV1 with its constants untouched, and the band rule as `ncaa_backtest.run_gate(...).crit_bands` (BAND_MIN_N 100, BAND_TOL 0.05, 10pp bands).
  - **Interpretations, each stated in the receipt:**
    - Strength = 1500 + conference effect + team effect. Next season's team effect = 0.85·team + sqrt(1-0.85²)·N(0, team sd); conference effects stay as they are.
    - The model's season_regression applies at the season boundary, as NCAAEloV1 does it.
    - A cross-conference round is a random perfect matching with no same-conference pair (65 games). An in-conference round pairs each shuffled conference of 13, with one bye (60 games). That makes 675 games per season.
    - A rounded 0 margin takes the sign of the raw draw.
    - The slope is a Newton maximum-likelihood fit (numpy; no dependency added). A fit that does not converge fails.
  - The script now uses the D1 wrapper shared with the shadow. Re-run, its output matches the committed receipt except the runtime line.
- **Registry (step (b)):** `ncaa-elo-v1r` was declared through `registry.declare` at 2026-10-08T16:57:23Z: status `declared`, run null, verdict null.
  - test_set: "NCAA FBS 2025 regular season (CFBD both-FBS labels; warm-up 2024)".
  - gate = D5 verbatim; confirmation_window = D7 verbatim.
  - confirmation_plan: n_games 100, log_loss, bar 0.6931, must_beat_reference true, reference "the D4 baseline on the same games minus 0.010".
  - Keys added after `declare`, which keeps only its own fields:
    - the shadow's required keys: `neutral_site_rule` no_home_advantage_at_neutral, and `constants` = v1's five;
    - `ratified`: the D5 note;
    - `design_receipt`;
    - `prior_reads_note`: D9 verbatim. The registry records prior reads only inside a run, and the VOID 2026-09-30 v1 run was never registered, so the note holds it.
  - Spec: `docs/specs/ncaa-elo-v1r.md`.
- **Shadow (step (c)):**
  - `export-ncaa-predictions` walks D2's stream (`ncaa_backtest.v1r_stream`).
    - What it walks: current labels only (L3), with the J2 merge, seasons 2024–2026 by the label's season, in kickoff-then-match-id order, postseason included.
    - What it skips: level scores, which are counted and listed.
  - It prices and updates neutral games with home advantage 0 through one shared wrapper, `ncaa_backtest.NeutralRuleElo`. A label without a neutral flag counts as non-neutral and is counted.
  - It refuses unless 2024, 2025 and 2026 are covered (D6), naming every season that misses.
  - Upcoming rows carry the home advantage applied (the listed home's) and `neutral_flag: "unknown before the game"` (D8).
  - `ncaa-cfbd-coverage` always prints 2024, 2025 and 2026.
  - Still never a Desk call. #79's all-division stream and gate are unchanged.
- **Interpretations (open to correction):**
  - A stream game's season is its label's (CFBD) season.
  - The stream still starts from our FINISHED, scored rows.
  - Upcoming games keep the existing stage-marker skip.
- **Not in this PR (PR B):** the gate command, `--preflight`, the reservation, the confirmation command.
- **Stacks on #362** (CFBD scope + join + LABEL SET), which is not yet on main.
- **Codex on #365, round 1 (both verified and fixed).**
  - P1, reading 2 withdrawn: D2 is applied as worded. `load_v1r_games` reads every stored NCAA match that carries a label, whatever our local status or scores, with home, away, scores and neutral taken from the label. A current label on our SCHEDULED or unscored row is walked, so the stream and the coverage fact count the same labels.
  - P2: the design receipt's I5 draw is now uniform over valid cross-conference matchings (rejection sampling, seeded, capped, fails loudly).
  - Re-run receipt:

    | setting | slope | band rule | D5 (2)&(3) |
    |---|---|---|---|
    | (110,140) | 0.985 | 29.5% | 87.0% |
    | (150,170) | 1.160 | 31.0% | 59.5% |
    | (190,210) | 1.335 | 24.0% | 15.5% |

  - Stop condition (verbatim, re-checked): "If yours contradict mine beyond noise (in the first setting the model passing D5 (2) and (3) in fewer than 85% of seasons, or passing the band rule in more than 60%), stop: write no entry and tell me." OK: 87.0% >= 85% and 29.5% <= 60%.
