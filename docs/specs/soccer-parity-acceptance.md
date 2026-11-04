# Soccer backtest/production acceptance: three tests (ARCHITECT 2026-11-04, addendum 251 item 2; addendum 249 item 1; addendum 248 item 2(a); addendum 230 item 1(e); read-only, gate-class by what it guards)

## The rulings (verbatim)

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
- The three tests: `tests/test_soccer_parity_acceptance.py`.
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

## The three tests

### (a) The parity test, with the context injected (no xfail)

- **What it does.** For every row the default walk scores, production runs at the row's instant. The walk then runs with the stored context production read at that instant, and its row is compared with production's.
- **The criterion.** Per row, max |p_production − p_walk| over home/draw/away must be at most **1e-12**, and every resolved input must be equal. No average is taken. A row missing from either path fails, and an empty report never passes.
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

## The successor's obligation (251 item 2)

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
3. Append it to `PREDICTORS`. All three tests parametrize over `PREDICTORS`. A successor takes **no** mark: `KNOWN_CONTEXT_GAP` and `KNOWN_NORMALISATION_LEAN` hold v22 only, and (a) has no mark list at all.

## What does not change

v22 does not change. Neither do its constants, training, `estimate_strengths`, `predict_match`, any bar, threshold, roadmap date or registry value. The walk's default path is byte-identical. The fix to either finding is a candidate through the frozen gate (addendum 216 item 1(c); addendum 251 item 2), never a patch to a live model.
