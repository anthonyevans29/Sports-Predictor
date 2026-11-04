# Soccer backtest/production acceptance: one parity test, five pins (ARCHITECT 2026-11-04, addendum 253 item 2; addendum 251 item 2; addendum 249 item 1; addendum 248 item 2(a); addendum 230 item 1(e); read-only, gate-class by what it guards)

## The declared scope (addendum 253 item 2(a))

Test (a) is **"same inputs, shared path"** — production and the walk given the SAME context, the SAME Elo state, the SAME history and NO factor inputs produce the SAME probabilities, row for row. It pins the shared computation (Elo update, `estimate_strengths`, Poisson, Dixon-Coles) and nothing else. It passes on v22 and fails on a real divergence in that path. Nobody may read it as "production equals the walk": the five pins below say where it does not.

- **Its name says so:** `test_a_same_inputs_shared_path_production_equals_the_walk_with_one_context_one_elo_one_history_no_factors`.
- **Its precondition is its store**, which is unchanged: one season, so no prior season; no injury or lineup rows, so no factor inputs; and unique kickoffs. `test_a_the_store_meets_the_scope_s_precondition` checks all three.
- **Its comparison is `assert_same_inputs_parity`:** every row within 1e-12 on H/D/A, AND every resolved input equal. A failure is raised as one of the located gaps below when every failing row is located at that gap's inputs alone. Otherwise it is raised as plain `ParityFailure`.

## The five pins (253 item 2(c): ONE passing parity test and FIVE strict xfails on v22)

Each pin is a strict xfail on v22 whose `raises=` accepts only its own failure type. No pin's type is another's or a subclass of another's, so any other failure is red. An XPASS is also red: each pin turns red the day its gap closes. A successor takes no mark. The figures are from v22 under Python 3.12.3; the receipts assert them.

| Pin | Seeded input (its own store; never (a)'s) | v22 figure | Cause, production path | Cause, the walk | #788 row |
|---|---|---|---|---|---|
| (b) context gap, `ContextGap` | none (the default walk on (a)'s store) | 23 of 23 rows: the walk at 1.4 / 1.15 against training's g and b. Uninjected, max \|dp\| 2.886e-02 | `training.py:514` reads the stored trained context | `soccer_backtest.py:210-211` walks under `CompetitionScoringContext()` | scoring context |
| (c) normalisation, `NormalisationLean` | its own average-team league (g 1.4904, b 1.0798) | total 2.857 vs 2.981 (−4.14%); ratio 1.080 vs 1.173 | `estimate_strengths` deflates home goals by b and divides by the undeflated g (216's lean, in BOTH paths) | the same function | — (#786) |
| prior-season Elo, `EloStateGap` | a prior season of the same competition: 60 FINISHED, the lower-numbered team winning every one 2-1 (`seed_prior_season`) | 23 of 23 rows; max \|dp\| 3.481e-02; at home_elo / away_elo alone | `training.py:152` (every FINISHED soccer match), `:177` (season key), `:182` `train_elo` with per-team season regression (`elo.py:199-201`, `regress_team` `:136`) | `soccer_backtest.py:194-195` (one season), `:212` (fresh `EloState`) | Elo state |
| match factors, `FactorGap` | for team 1: one Injury row (an Attacker, `fixture_source_id` None) and confirmed XIs, three earlier XIs of eleven regulars and the target's XI with one regular dropped (`seed_match_factors`) | 7 of 23 rows (every scored row team 1 plays); max \|dp\| 3.486e-02 (the target, factor 0.94 × 0.97); at factor alone. Seeded one at a time: injury 7 / 23 at 2.403e-02, lineup 1 / 23 at 1.173e-02 | `training.py:569` (every Injury row, not as-of), `:578-586`, `:596-600`, `:606-627` (lineups; recent XI by `refreshed_at`, not as-of), `:795`, `:799`, `:858`, `:867` `factor_adjustment=factor` | `soccer_backtest.py:259-264` calls `predict_match` with no factor | match factors |
| simultaneous kickoffs, `KickoffBatchingGap` | the third target (1 v 4) moved onto the second's kickoff (3 v 5): disjoint teams, a real calendar's shape (`share_kickoff`) | 1 of 23 rows (the second of the pair); 0 outside 1e-12, \|dp\| 0; at history alone | `tests/soccer_parity.py:716` `at_instant` hides every match at or after the target kickoff (training reads what is FINISHED, `training.py:152`) | `soccer_backtest.py:228-236` (`batch_same_kickoff=False`: one row per group), `:294-302` (update after each group); the harness's call `tests/soccer_parity.py:914` passes no `batch_same_kickoff` | NEW ROW on #788 per addendum 253 item 2(b) |

- **The kickoff pin's positive control.** On the same store, v22's production against the walk with `batch_same_kickoff=True` (`V22_BATCHED_WALK_CONTROL`) passes (a)'s comparison on all 23 rows. A shared team, the probe's case C2, also moves a probability, but it is not a real calendar's shape and is not pinned.
- **The Elo pin's size differs from the #828 probe.** The probe's case A seeded its own prior season and measured 4.685e-02. The pin's ladder measures 3.481e-02 on the same 23 rows, located at the same two inputs.
- **The citations are checked.** `test_the_pins_cite_the_lines_that_hold_their_causes` checks that every file:line the three located pins cite holds the code it names.
- **Synthetic factor rows** (253 item 2(b)): "Synthetic rows in the synthetic store are allowed — 216 item 4's "historical injuries are never manufactured" governs a real backtest's inputs, not a test's fixtures, and the docstring says so."
- **Not pinned:** #788's early-season history row, the 30-match backfill at `training.py:476-500`. The walk's min_prior of 40 never scores a row below 30, so no store of this shape reaches it.

## The harness's guards (round 1, 253 item 2: "non-finite values fail outright and are never absorbed by an xfail")

- **The three-leg check.** `compare` fails a row unless the probability vectors on both paths are exactly three legs, every leg numeric and finite. The row gets `max_abs_diff` None, and the failure names the path and the problem: a leg count, a non-numeric leg, a non-finite leg, or not a vector. Such a row is never a located gap.
- **The table never crashes on the row it names.** `ParityReport.table()` formats a vector leg by leg only when every leg is a finite number. Otherwise it prints the vector's repr. Before this, a None vector or a non-numeric leg raised TypeError or ValueError out of the table, which hid the `ParityFailure`. The pins' one-line print does the same for its max |dp|: "-" when no row carries a number (every row malformed), never a TypeError ahead of the pin's `ParityFailure`.
- **A non-finite figure is a hard failure.** In (c), a non-finite normalisation figure raises `NonFiniteNormalisation`. That type is not a `NormalisationLean`, so v22's xfail cannot accept it.

## The rulings (verbatim)

Addendum 253 item 2 (ARCHITECT 2026-11-04 13:20 ET):

> "2. #828 — THE FIVE, RULED. The two harness bugs (three-leg check; non-finite values fail outright and are never absorbed by an xfail) are round 1 as Code has them, each with a fail-first test. The three coverage findings are correct as facts — every one is a live/replay difference, and three of them are already #788's table — and they are NOT reasons to seed test (a) into failing on v22. They are reasons to say what (a) tests. RULED:
> (a) THE PARITY TEST'S SCOPE IS DECLARED, in its docstring, its name and the PR body: "same inputs, shared path" — production and the walk given the SAME context, the SAME Elo state, the SAME history and NO factor inputs produce the SAME probabilities, row for row. It pins the shared computation (Elo update, estimate_strengths, Poisson, Dixon-Coles) and nothing else; it passes on v22 and fails on a real divergence in that path. Nobody may read it as "production equals the walk"; the pins below say where it does not.
> (b) THREE MORE STRICT-XFAIL PINS, one per finding, each SEEDED so the gap shows, each red (xpass) the day its gap closes, each carrying in its docstring the probe's figures (rows affected, the size of the gap, the cause by file and line) and the #788 row it pins:
> - PRIOR-SEASON ELO: a store with two seasons; production carries the regressed Elo across the boundary (training's `_train_fresh_soccer` over every finished match), the walk starts the season fresh (`run_soccer_backtest(code, season)` filters to the season and a new EloState) — the early rows of season two differ.
> - THE MATCH FACTORS: a store with an injury row and a lineup row for a target fixture; production composes injury, lineup and XI multipliers into `factor_adjustment`, the walk reconstructs none, so the rows differ. Synthetic rows in the synthetic store are allowed — 216 item 4's "historical injuries are never manufactured" governs a real backtest's inputs, not a test's fixtures, and the docstring says so.
> - SIMULTANEOUS KICKOFFS: a pair of fixtures sharing a kickoff after min_prior; production prices both from the same state (`at_instant` hides every match at or after the target kickoff), the walk with `batch_same_kickoff=False` updates between them — the second row differs. A NEW ROW on #788's table (it is not there today): Code adds it by a comment on #788 quoting this item, with the file:line pair.
> (c) THE CONTEXT-GAP PIN (251 item 2(b)) and THE NORMALISATION PIN (249 item 1(b)) stand as they are; with (b) the PR carries ONE passing parity test and FIVE strict xfails, which is the honest shape: parity where parity is claimed, a named pin for each place it is not.
> (d) THE SUCCESSOR'S OBLIGATION, restated so #828 and the v23 design PR agree: 216 item 4's direction IS the requirement — ONE prediction function taking a versioned, immutable input snapshot, invoked by replay and by live alike ("same model, same inputs at the same instant, same probabilities"). The v23 design PR shows, for each of the five rows (the context, the Elo state, the early-season history, the match factors, simultaneous kickoffs), how replay and live become identical BY CONSTRUCTION, not by test; the as-of factor inputs come only from stored as-of data (the availability record of addendum 252 is the source going forward; where the record has nothing for an era, the term is off in BOTH paths for that era and the harness says so); v22 is re-walked under the same harness beside v23; the bar is 251 item 2's. v22 does not change.
> (e) ROUNDS: the two fixes are round 1; the three pins are built under this ruling and are not a review round; Codex's next review is round 2 and the cap stands."

Addendum 251 item 2 (ARCHITECT 2026-11-04 11:50 ET):

> "2. 249 ITEM 1(a) — RULED. Code's finding is correct and verified in the source: soccer_backtest.py:200 walks every row under CompetitionScoringContext() (g 1.4, b 1.15) while production (training.py:514) reads the stored trained context of the competition (PL today g ≈ 1.49, b ≈ 1.17, as #786's receipt printed them). The reason the walk does NOT read the stored context is sound and is recorded with the finding: the stored context is fitted on the whole training pot — the same games the walk scores — so a walk that read it would leak the pot's own totals into every prior-only step. So "production == the walk, row for row" cannot hold on g and b by construction, and an xfail over the WHOLE parity test would blind the one test meant to catch a live/replay divergence. Three tests, then, in the one PR (249's two, reshaped, plus the gap's own pin):
> (a) THE PARITY TEST, with the context INJECTED: the walk gains an optional `context` parameter whose default is today's CompetitionScoringContext() (the default path byte-identical, pinned by the existing soccer-backtest golden on the fixture store — a changed default would re-measure every soccer record and is gate-class; this is not that); the test passes production's stored context to the walk and asserts production == the walk, row for row, on the synthetic store. It PASSES on v22 (the shared path — Elo, estimate_strengths, Poisson, Dixon-Coles — reproduces its gate) and fails the day a real divergence appears. No xfail.
> (b) THE CONTEXT-GAP PIN, strict xfail on v22: the walk's effective context on a competition equals production's stored context for it. It turns red (xpass) the day the two paths agree, which is the successor's obligation, and it carries the leak reason in its docstring so nobody "fixes" it by reading the stored context into the walk.
> (c) THE NORMALISATION PIN, 249 item 1(b), unchanged: strict xfail on v22 with its positive control.
> THE FINDING ISSUE (filed with the PR, `Refs #789`, `Refs #786`, never closing either): "the soccer gate's walk scores under the default context (1.4 / 1.15); production runs the trained one; neither is as-of" — its resolution is the successor's design, not a patch: soccer-v23's design PR (248 item 2(b)) must state how its harness and its production path define g and b IDENTICALLY (an as-of estimate from the prior finished games in both, or a frozen pre-pot context in both — the design chooses and says why), and must re-walk v22 under that same harness beside v23 so the comparison is like for like. v22's recorded gate figure STANDS as measured; nothing about v22 changes. THE BAR, so it never loosens: v23's pot log-loss must be at least 0.0050 below BOTH v22's recorded figure AND v22's figure re-walked on v23's harness; a tie on either is a rejection (the bar is written "below"). Option 2 (the default walk reads the stored context) is REJECTED: a leak and a gate-class re-measurement of every soccer record. Option 3 (the improve gate's holdout scorer) is REJECTED: not as-of. The parity harness Code committed locally (6be9b16a, built to 248) is the base; it reshapes to (a)–(c) and opens as 248 item 2(a)'s PR, due 11-20 as before."

Addendum 249 item 1:

> "1. 248 ITEM 2(a), CORRECTED — Code's "one thing to watch" is right. The production predictor and the backtest walk share estimate_strengths, so 216's lean lives in BOTH paths and a parity test cannot fail on it; forcing it to would make it a test of a reference walk, not of parity. Two tests, then, both in the acceptance set every soccer successor runs under:
> (a) THE PARITY TEST (#789's lane; #782's option A): production == the backtest walk, row for row, on a synthetic store — it PASSES on v22 today (that is the point: the live path reproduces its gate), and fails the day a replay/live divergence appears. No xfail.
> (b) THE NORMALISATION PIN (216 item 1(b); #786's receipt as a test): on a synthetic store with a known g and b, the model's implied average-team total against the context's (2.857 vs 2.981 on PL, −4.14%) and the home/away ratio (1.080 vs 1.173) — the lean, pinned as a strict xfail on v22 that turns red the day a path no longer leans, with a positive control. v22 does not change; v23 is judged with both tests green.
> Both in the same PR, both referring to #789 and #786 without closing them."

Addendum 248 item 2(a):

> "(a) 230 item 1(e), THE BACKTEST/PRODUCTION PARITY ACCEPTANCE TEST (#789's lane; #782's option A): a CI test that the production soccer predictor's probabilities equal the backtest walk's, row for row, on a synthetic store seeded with the v22 finding's shape (training's g and home factor b; estimate_strengths's deflation) — the test must FAIL on main's v22 path exactly where 216 found the lean, and the PR records that failure as the finding's pin, not as a fix (v22 does not change; the successor is judged under this test). Read-only machinery; gate-class by what it guards. Due 11-20; start today."

Addendum 230 item 1(e):

> "(e) BACKTEST/PRODUCTION PARITY AS AN ACCEPTANCE TEST (the lane Issue of 216; #782's option A) — PR BY 11-20, before v23's run of 11-27: a CI test that the production predictor's probabilities equal the backtest walk's on a synthetic store, row for row (the v22 finding was exactly this class: training's g against estimate_strengths's deflation); every soccer successor runs under it."

The lane is #789 (addendum 216 item 4; its acceptance test, addendum 218 item 1(A)). The parity inventory is #788. The normalisation finding is #786 (addendum 216 item 1), and its receipt is `tests/test_v22_normalisation_receipt.py`. The context-gap finding is its own Issue, filed with this PR (addendum 251 item 2).

## Where the files are

- The harness: `tests/soccer_parity.py`. It is not a test module; a successor's tests import it.
- The parity test and the five pins: `tests/test_soccer_parity_acceptance.py`.
- The walk's default path, pinned: `tests/test_soccer_backtest_default_golden.py`.
- The one production-code change: `src/walters/soccer_backtest.py`'s `run_soccer_backtest` gains an optional keyword `context` (default `None`, meaning `CompetitionScoringContext()`, as before). The CLI is not given a flag for it, and a test pins that no `soccer-backtest` call site passes one.

Everything runs on synthetic stores that the tests build on tmp SQLite files. Nothing reads `data/` or a real DB.

## The two paths and the instant

- **Production.** The predictor runs as the live chain runs it, at the match's instant. For v22:
  1. The real `_train_fresh_soccer` trains on the store as it stood at the instant, which gives training's own g and b and its Elo.
  2. `_generate_predictions_soccer(code, season, model_version=<that version>, only_match_id=<the match>)` prices the match.
  3. The probabilities are read back from the Prediction row it writes.
  4. The row also carries **production's stored context** for the competition. It is read from the ModelVersion's parameters exactly as the live path reads it: `training.py:456-459` builds the contexts, and `training.py:514` takes `contexts.get(competition_code, CompetitionScoringContext())`.
- **The walk.** `run_soccer_backtest` runs as `soccer-backtest`'s plain report calls it: `min_prior` 40, with the production row's `dixon_coles_rho` and `elo_goal_coeff` taken through `cli._soccer_prod_poisson`; plus `detail=True` for the xG (additive keys, which the CLI does not pass). With no `context` it is the gate's walk (1.4 / 1.15). With a `context`, every row is deflated and priced with that context.
- **The instant.** `at_instant` sets M and every soccer match kicking off at or after M, whatever its competition or season, to SCHEDULED with no score. Production then trains and prices M, and the store is restored. The walks run on the restored store.
- **The location.** Pass-through spies wrap each module's `estimate_strengths` and `predict_match`. The real functions run unchanged; the spies only record each call's arguments. `differing_inputs` names every input that differs between the paths: the deflation context's g and b, the forecast context's g and b, both Elo ratings, the history multiset, the weights and prior switches, the Poisson config, and the factors.

## The parity test and the first two pins (251 item 2)

### (a) The parity test, with the context injected (no xfail; its scope declared above)

- **What it does.** For every row of the store's inventory, production runs at the row's instant. The inventory is read from the store, never from a walk's output (`expected_scored`: the competition-season's finished matches in kickoff order after the walk's min_prior 40), and the default walk and every injected walk must score exactly it (`require_inventory`: a row missing or extra is a plain `ParityFailure` naming the ids; Codex on #828, round 2). The walk then runs with the stored context production read at that instant, and its row is compared with production's.
- **The criterion** (`assert_same_inputs_parity`). Per row, max |p_production − p_walk| over home/draw/away must be at most **1e-12**, and every resolved input must be equal. No average is taken. A row missing from either path fails, and an empty report never passes.
- **Why 1e-12.** Both paths end in the same deterministic `predict_match` in one process. The only noise left is the last bits of a mean summed in another order, about 1e-16 here. The default walk's difference on this store is about 1e-2. 1e-12 sits about four orders of magnitude above the noise and about ten below that difference.
- **v22: PASS.** All 23 rows are at max |dp| 0.000e+00, with no input differing. 22 distinct contexts are injected over the 23 rows: production's b moves as the instant moves, and g stays 1.5 on this store because every match has 3 goals. The shared path (Elo, `estimate_strengths`, Poisson, Dixon-Coles) reproduces production.
- **The mark.** No predictor carries one. An xfail over the whole parity test would blind it (251 item 2).

### (b) The context-gap pin (strict xfail on v22)

- **What it asserts.** On every row, the DEFAULT walk's effective context equals production's stored context for the competition at that instant. The effective context is the g and b that the walk's `estimate_strengths` deflated with and its `predict_match` priced with, as recorded by the spy.
- **v22: strict xfail.** Only the harness's `ContextGap` satisfies it, so any other error is red, and an XPASS is red. On all 23 rows the walk uses 1.4 / 1.15 while production's stored context is training's g and b at the instant; on the average row that is the store's own 1.5 / 1.2. Without the injection, that gap moves every row by more than 1e-3 (the receipt test: 23 of 23 rows outside 1e-12; the average row's max |dp| is 1.599e-02 and the worst row's 2.886e-02).
- **The leak reason** (251 item 2, verbatim, in the test's docstring): "the stored context is fitted on the whole training pot — the same games the walk scores — so a walk that read it would leak the pot's own totals into every prior-only step". Never fix this by reading the stored context into the walk (option 2, REJECTED by addendum 251 item 2).
- **Its positive control.** v22's own code with its stored context set to the walk's default passes (b), and (a) with it.

### (c) The normalisation pin (249 item 1(b); strict xfail on v22)

- **What it asserts.** On a league of average teams at a known g and b, two average teams at equal Elo price at the context's own rates: total 2g and home/away ratio b/(2−b), within 1e-9.
- **The league.** 20 teams play a double round robin scored at the true means (home g·b, away g·(2−b)). Training's expressions recover the context exactly.
  - g = 1.4904 and b = 1.0798 are chosen so 216's closed forms reproduce 249's PL figures to their printed digits.
  - 251 item 2 prints PL's stored context as "b ≈ 1.17". 249's ratio pair puts the stored b at 1.080 (b/(2−b) = 1.173), and this pin follows 249 (For the architect, in the PR).
- **v22: strict xfail.** Only `NormalisationLean` satisfies it. The real `estimate_strengths` with the n/(n+5) shrinkage undone exactly, followed by the real `predict_match`, gives:
  - average-team total **2.857** against the context's **2.981** (**−4.14%**);
  - home/away ratio **1.080** against the context's **1.173**.

  These are 216's closed forms g(1+b)((3−b)/2)² and b, to 1e-12. As run, with the shrinkage at n = 38, the total is 2.885 (−3.21%).
- **Its positive control.** The real `predict_match`, fed unit strengths at the data's rates, prices 2.981 and 1.173 and passes.

## The store (the v22 finding's shape)

- Six teams with exactly equal records play two double round robins: 60 FINISHED matches, 10 per team at each venue.
- At each venue a team wins 2-1 four times and loses 1-2 once. Every team's home mean is 1.8 and its away mean 1.2.
- So g = 1.5, the data's home factor b = 1.2, and the data's home/away ratio is 1.5 = b/(2−b).
- Then come three fixtures, each 2-1. The first of them is the **average row**, where 216's closed forms hold exactly.
- The production row carries v22's two stored Poisson values, rho −0.10 and coefficient 0.0008. The real training inherits them.

## The walk's `context` parameter, and why its default stays

- **The default is byte-identical.** `context=None` is `CompetitionScoringContext()`, exactly as the walk ran before. No golden of the walk's output existed on a fixture store, so `tests/test_soccer_backtest_default_golden.py` adds one. It was computed before the parameter existed and passes unchanged after it.
  - It pins three calls on a fixed eight-team, two-season store: the default call, the plain report's call (plus `detail=True`, which the CLI does not pass, so the additive keys are pinned too), and the season-less call with decay and batching on.
  - For each call it pins the row count, the match ids, and a sha256 over every row at nine decimals. Nine decimals, because Python 3.11 and 3.12 sum floats differently in their last bits.
  - In process, every bit: the default call, `context=None` and `context=CompetitionScoringContext()` give equal rows.
  - The receipt prints the exact float.hex digests before and after the change, on both interpreters.
- **No CLI flag.** The gate's walk stays the default. A flag would invite option 2.
- **Option 2 is REJECTED** (251 item 2): the default walk reading the stored context. It is a leak, and a gate-class re-measurement of every soccer record.
- **Option 3 is REJECTED** (251 item 2): the improve gate's holdout scorer. It is not as-of.

## The successor's obligation (251 item 2; 253 item 2(d))

- **One prediction function** (253 item 2(d), verbatim): "216 item 4's direction IS the requirement — ONE prediction function taking a versioned, immutable input snapshot, invoked by replay and by live alike ("same model, same inputs at the same instant, same probabilities"). The v23 design PR shows, for each of the five rows (the context, the Elo state, the early-season history, the match factors, simultaneous kickoffs), how replay and live become identical BY CONSTRUCTION, not by test; the as-of factor inputs come only from stored as-of data (the availability record of addendum 252 is the source going forward; where the record has nothing for an era, the term is off in BOTH paths for that era and the harness says so); v22 is re-walked under the same harness beside v23; the bar is 251 item 2's. v22 does not change."
- **What that means for the pins.** A successor takes no mark on any of the five pins, so each pin passes for it. The three located pins pass by construction under 2(d), not by a fix to the harness.

- **One definition of g and b.** soccer-v23's design PR (248 item 2(b)) states how its harness and its production path define g and b IDENTICALLY. Either both use an as-of estimate from the prior finished games, or both use a frozen pre-pot context. The design chooses and says why. Under that design, (b) passes for v23 with no mark.
- **v22 re-walked.** The design re-walks v22 under that same harness, beside v23, so the comparison is like for like. v22's recorded gate figure STANDS as measured, and nothing about v22 changes.
- **THE BAR, so it never loosens.** v23's pot log-loss must be at least **0.0050 below BOTH** v22's recorded figure **AND** v22's figure re-walked on v23's harness. A tie on either is a rejection: the bar is written "below".
- **Tests (a) and (c).** v23 is judged with (a) green, and with (c) green (249 item 1: "v23 is judged with both tests green").

## How a successor runs under it

1. Build a `SoccerPaths(name, production, walk, implied)`:
   - `production(code, season, match_id)` prices one SCHEDULED match at the store's current state. It returns a `PathRow` whose inputs carry `stored_context`, the (g, b) its production path reads for the competition.
   - `walk(code, season, context=None)` returns `{match_id: PathRow}` for every row it scores. A context passed is the one it deflates and prices every row with.
   - `implied(g, b)` returns the average-team forecast `{"home", "away"}` on `average_league(g, b)`, at equal Elo, with any sample-size shrinkage undone.
2. Record each path's resolved inputs in `PathRow.inputs`, either with `soccer_parity.recording(module)` or by the path itself, under `LOCATION_KEYS` where they apply.
3. Append it to `PREDICTORS`. The parity test and the five pins all parametrize over `PREDICTORS`. A successor takes **no** mark. `KNOWN_CONTEXT_GAP`, `KNOWN_NORMALISATION_LEAN`, `KNOWN_ELO_STATE_GAP`, `KNOWN_FACTOR_GAP` and `KNOWN_KICKOFF_BATCHING_GAP` hold v22 only, and (a) has no mark list at all.

## What does not change

v22 does not change. Neither do its constants, training, `estimate_strengths`, `predict_match`, any bar, threshold, roadmap date or registry value. The walk's default path is byte-identical. The fix to any of the five is a candidate through the frozen gate (addendum 216 item 1(c); addendum 251 item 2), never a patch to a live model.
