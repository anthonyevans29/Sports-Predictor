# mlb-pitchers-v1 — the pitcher-layer test (GATE-CLASS; declared 2026-10-31T15:45:00Z, nothing run)

Registry id `mlb-pitchers-v1` (docs/registry/experiments.json), status `declared`, run and verdict null, `test_cohort`
null until the freeze. ARCHITECT 2026-10-31 11:45 ET, addendum 190. Lane mlb-pitchers (#507); the snapshot finding is
Issue #746. The roadmap lines are #747's.

**Nothing here runs the gate.** This document holds the ruling verbatim (section 1), the harness that executes it
(section 2), the operator's sequence on the laptop (section 3) and Code's readings for the architect (section 4).

## 1. The ruling (addendum 190, verbatim)

> ARCHITECT 2026-10-31 11:45 ET — addendum 190: THE PITCHER-LAYER DECLARATION (lane mlb-pitchers, #507; the roadmap's 2026-10-31 step, done with this text). Written on the operator's console of 11:34 ET (laptop 78566ff5, read-only; the 10-28 figures reproduced: 2429 regular games, 3173 sides, P blend 3072 · half-weighted 101 · no input 1685).
>
> 1. THE QUESTION, pre-committed: does the pitcher layer, fed AS-OF inputs, improve the live MLB model's forecasts by the MLB bar? Two arms on the SAME games, the same Elo state and every other input identical, the raw model probability (pre any market blend) on the home side:
>    ON — mlb v2 with the pitcher layer fed the as-of reconstruction (#702's receipt: the season's appearances of games started strictly before the game; the starter + bullpen blend where the starter is listed, the half-weighted bullpen where the starter is unknown — the live path's own fallbacks, nothing new);
>    OFF — the same model with the pitcher layer off (as src/walters/backtest.py runs today).
> 2. THE COHORT, frozen: the 2026 regular-season games with BOTH sides reconstructed on a live path — 1553 games on the 10-31 console (one side 67, neither 809; 2429 in all). Code writes the ids from the receipt's per-game classification into the registry's cohort file before the run (ids/mlb-pitchers-v1.cohort.txt, sha in the entry); the run refuses unless its own re-classification reproduces 1553 and the same ids. No other 2026 cut; no 2025 (item 6).
> 3. THE METRIC AND THE BAR: mean log-loss of the home-win probability over the 1553, both arms, unrounded. PASS only if OFF − ON >= 0.0050 (the MLB `improve` bar, addendum 63 item 4); less, or a tie, REJECTS. Brier and the per-month lines print for the record and gate nothing. One read (law 3): the registry entry mlb-pitchers-v1 is DECLARED at this addendum's instant (2026-10-31T15:45:00Z) with the plan (arms, cohort sha, metric, bar) frozen in it; the MLB backtest with the pitcher layer on is fenced on 2026 while the entry is declared and unrun, the gate's run excepted — the expansion fence's precedent.
> 4. WHAT THE VERDICT DOES (live_needs): PASS — the layer stays in the live model for 2027, AND the live path must then read the as-of sums, never the snapshot (item 5), before opening day; REJECT — the layer is retired from the live model by a ruling before 2027, and the 2027 model is the OFF arm. Either way the result is the record, not a reason to retune: no constant moves on this run.
> 5. THE SNAPSHOT FINDING (the second #507 line, settled): pitcher_season_stats is a STALE SNAPSHOT — 268 of 318 rows are short exactly by appearances after their last refresh (cause 1; causes 2 and 3 zero; the 50 agreeing rows were refreshed after the pitcher's last appearance). So the live model in 2026 read starters' season lines that were behind by their most recent starts. Logged attributed in BACKLOG as a finding (an Issue, class:finding, sport:mlb): the live path's season inputs must come from the as-of reconstruction, conditional on item 4's PASS; if the layer is retired the finding closes with it. The snapshot as the model actually read it each day is NOT reconstructable (only the last refresh survives), so no third arm is run; said in the entry.
> 6. 2025: EXCLUDED, by receipt — 0 of 4860 sides reconstructable (#702, 10-28: no stored pregame starter identity; the boxscore starter is post-game, the exports begin 2026-05-24). The roadmap step's "2025 and 2026" is narrowed to 2026 by a moved line (scope, not date; Code appends it with this addendum quoted). 2025 enters only on an external as-of probable-starters source with a pregame stamp, the same class of condition as NHL's; not sought.
> 7. THE RUN: Code builds the harness as a gate-class PR (the ON arm's as-of inputs into the backtest behind one flag, the registry entry and the frozen cohort, the fence, tests on synthetic rows; the OFF arm must reproduce today's backtest exactly on the cohort — a pinned test) by 11-05; the run on the LAPTOP (MLB history is the laptop's duty) on a .backup copy outside data/ with --db, my block, 11-06; the verdict on that console the same day, recorded in the entry by Code's PR. The roadmap: this step done 10-31; a new step "harness PR" due 11-05 owner code; "the one run and the verdict" due 11-06 owner architect; earliest_live stays null (the lane has no go-live; its exit is the 2027 model).

## 2. The harness

### Modules

- **`src/walters/mlb_pitcher_asof.py`** — the as-of reconstruction. The #702 receipt's logic (`db_path`, `open_read`,
  `check_columns`, `load`, `Tally`, the kickoff-group walk `reconstruct`, the per-side classification `read_game`,
  `PATHS`) moved here without a change of logic; `scripts/mlb_pitcher_asof_receipt.py` imports it and its console is
  byte-identical (tests/test_mlb_pitcher_asof_receipt.py, unchanged, passes). Added, without changing what the receipt
  counts:
  - the recent bullpen window carries its earned runs (a fifth element of each row; rows sort on (kickoff, n) with n
    unique, so nothing reorders);
  - `classify(d, season)`: per regular-season game the receipt reads, per side, the P label (computed once by
    `read_game` and counted as before) and, for a side on a live path (a label in `PATHS`), the as-of sums: starter
    (outs, er, gs) when the starter component exists; bullpen season (outs, er) when the team has prior relief outs;
    the recent window (outs, er) when it holds 10 IP or more;
  - `cohort_ids(classification)`: the games whose BOTH sides' P label is in `PATHS` (per game, the sum over sides of
    one[k] for k in PATHS equals 2), sorted by id;
  - `pitcher_stats_asof(side, cfg)`: the ON arm's `PitcherStats`, built exactly as the live `_resolve_pitcher`
    (src/walters/training.py, `_generate_predictions_mlb`) builds them, from the as-of sums instead of
    `pitcher_season_stats` / `bullpen_season_stats`: starter era = 27·er/outs, IP = outs/3, GS (GS 0 is an opener: no
    starter component), `starter_shrink_weight(ip, gs, cfg)`; bullpen season era = 27·er/outs, IP = outs/3, the recent
    window's era = 27·er/outs when its IP ≥ 10, effective = 0.7·season + 0.3·recent, shrink w = IP/(IP + 50); the
    blend table (0.611 starter + 0.389 bullpen; starter + the league bullpen; 0.5·bullpen + 0.5·league ERA with
    starter_known False; era None). training.py is not modified: a test runs the live function on rows equal to the
    as-of sums and pins the equality of the PitcherStats and of p_home;
  - `missing_starter_shrink(...)`: the live path's Phase 12.3 shrink (0.88 for one side whose starter is not known,
    0.76 for two, renormalised), copied exactly.
- **`src/walters/backtest.py`** — ONE flag: `run_backtest(..., pitcher_layer=False, pitcher_inputs=None, session=None,
  sealed_read=False)`. The default is today's walk byte for byte (the same query, `utc_date` order with no id
  tie-break, postseason games walked, the 40-game threshold, the same history appends and same-kickoff ordering, the
  same return tuples; a test pins it against a verbatim copy of the pre-change walk). With `pitcher_layer=True` the
  SAME walk prices each game named in `pitcher_inputs` (match id → (home, away) PitcherStats) twice from the same
  profiles and config: OFF = `predict_game(hp, ap, None, None, cfg)`, the identical call; ON =
  `predict_game(hp, ap, home_ps, away_ps, cfg)` then the shrink. Raw p_home, pre any blend. It returns, in walk order,
  `(match_id, utc_date, home_won (home_score > away_score), p_home_off, p_home_on)` for those games. `session` binds the
  walk to a given session (the gate's read-only session on its --db copy); None is `session_scope()`, as today.
- **`src/walters/mlb_pitchers_gate.py`** — EID `mlb-pitchers-v1`, COHORT_N 1553, BAR 0.0050: the fence, the --db
  checks, the freeze, the one run, the score, the record.

### The fence (190 item 3)

`run_backtest(pitcher_layer=True)` on MLB with season 2026, or every season (no season), is REFUSED
(`PitcherFenceRefused`, a `FenceRefused`: every CLI caller that maps the NCAA fence prints `REFUSED: ...` and exits 2)
while the entry is declared and unrun, and while it is absent (fails closed). The refusal quotes item 3's fence sentence
verbatim. `mlb-pitchers-gate`'s own walk passes `sealed_read=True`, only after its reservation; the flag suppresses the fence only while that reservation exists (`sealed_refusal`). Lifted once the run is
recorded (`run` set). The default walk (OFF) is never fenced by it; other seasons and competitions are not fenced.

### Commands

- **`python cli.py mlb-pitchers-freeze --db COPY [--no-fetch]`** — before the run. Refused, nothing written, unless the
  entry is declared and unrun with no `test_cohort`, no cohort file and no reservation, and --db is valid; then the
  #329 cross-ref guard (before any write); then the copy's classification of 2026 must give exactly 1553 cohort ids
  (else REFUSED naming the count: the database moved). Writes `docs/registry/ids/mlb-pitchers-v1.cohort.txt` (the
  registry's format: sorted ids, one per line, a trailing newline) and the entry's `test_cohort` = {n, ids_sha256
  (`registry._ids_sha`), ids_file, frozen_at, basis (the rule, the cohort by UTC month, first and last kickoff, the
  games by sides on a path, the receipt's per-side P counts, selected_at)}. Never `confirmation_cohort`. Reads no
  outcome; prints a console.
- **`python cli.py mlb-pitchers-gate --db COPY [--no-fetch]`** — the ONE run. Before any outcome read, each refusal
  exit 2 with nothing written: declared and unrun; no reservation; `test_cohort` present and its file matching its sha
  and count (`registry._frozen_base` on the test_cohort dict); the --db checks; the copy's re-classification exactly
  1553 ids and the same set as the file; the copy's production MLB config present and buildable. Then the reservation
  `docs/registry/mlb-pitchers-v1.started.json` (O_EXCL, after the cross-ref guard; soccer_expansion.reserve's
  precedent), then the one walk with `sealed_read`. The scored set is the cohort exactly: a cohort game either arm
  cannot price (the 40-game warm-up, a missing run profile, a game not FINISHED with both scores) makes the run
  INVALID, printed with the ids and the count and recorded, never scored on a subset. Metric: mean home-side
  log-loss, ll = −(y ln p + (1 − y) ln(1 − p)), the realised side's probability floored at 1e-12 as
  `evaluation.score_winner` floors it, both arms over the cohort (`math.fsum`, in id order), unrounded (printed with
  repr). PASS iff (OFF − ON) ≥ 0.0050, else REJECT. Printed, gating nothing: Brier per arm, (p − y)², and per UTC
  month n / LL off / LL on / Brier off / Brier on. Recorded with `registry.record_run(EID, the cohort ids, result)`
  (ids/mlb-pitchers-v1.txt; status `run`). The verdict itself is recorded by Code's PR on the architect's ruling.

### --db

Required for both commands. The path must exist (never created), must not resolve under the repo's `data/` (law 5;
by resolved path, so a symlink or relative path cannot slip by; run from a git worktree, the main checkout's `data/`
too, found from git's common dir) and must not be the app's configured database; a hard link to a file directly under
any of those `data/` directories, or to the app's database, is refused by identity. It is opened read-only through a
percent-encoded `mode=ro` URI (`path.as_uri()`, so a `#` or `?` in the path cannot cut the filename or drop `mode=ro`)
by both the sqlite3 as-of loader and the SQLAlchemy session the walk reads through (`database.readonly_scope`'s
pattern, bound to the file); `_load_production_config` reads the copy's production config. An unreadable registry
(a corrupt `experiments.json`) refuses, and fences, by name; a run whose record fails after the verdict printed is
REFUSED, exit 2, naming the spent reservation.

## 3. The operator's sequence (the laptop; MLB history is the laptop's duty)

1. A `.backup` copy outside `data/` (the `.backup` API, never a file copy), from the repo root, e.g.
   `COPY="$HOME/backups/mlb_pitchers_v1_$(date +%F).db"; mkdir -p "$HOME/backups" && sqlite3 data/sports.db ".backup '$COPY'"`.
   The path is expanded by the shell before sqlite3 sees it: a `~` inside the quotes is not expanded by bash or by
   sqlite3, and the `.backup` would fail or write a literal `./~/backups/...` in the checkout.
2. `python cli.py mlb-pitchers-freeze --db "$COPY"` (the same expanded path) — paste the console.
3. Commit the registry files (`docs/registry/experiments.json`, `docs/registry/ids/mlb-pitchers-v1.cohort.txt`) in a
   PR, the 10-09 soccer cohort precedent, before the run.
4. `python cli.py mlb-pitchers-gate --db "$HOME/backups/mlb_pitchers_v1_<date>.db"` (the same copy), the architect's block,
   11-06 — paste the whole console. The run record (`experiments.json`, `ids/mlb-pitchers-v1.txt`,
   `mlb-pitchers-v1.started.json`) is committed by Code's verdict PR.

## 4. Code's readings for the architect

- **(a) The ids file name.** `ids/mlb-pitchers-v1.cohort.txt` (190 item 2's name) is also the path the registry's
  `freeze_confirmation_cohort` writes (`{eid}.cohort.txt`) and the file the #329 cross-ref guard compares as the
  "cohort" kind. Harmless here: there is no confirmation, the freeze stores the cohort under `test_cohort`, never
  `confirmation_cohort`, and `freeze_confirmation_cohort` already refuses this entry (it refuses any entry that is not
  `confirming`, and any entry with no `confirmation_plan`; this one's plan is null), so it cannot overwrite the file.
  The harness adds no refusal of its own. The guard's "cohort" kind compares the file's bytes across refs, so a stale
  branch holding a different cohort file refuses the run's reservation by name, as intended.
- **(b) Confirmation: none.** The entry's `confirmation_window` says so (addendum 190 item 7: earliest_live stays null;
  the exit is the 2027 model) and `confirmation_plan` is null, so `registry.declare` (which requires a plan) was not
  used: the entry is hand-written, as ncaa-elo-v2's extra keys were.
- **(c) The scored set is the cohort exactly.** A cohort game either arm cannot price makes the run INVALID (printed
  with its ids, recorded); it is never scored on a subset.
- **(d) The missing-starter shrink is in the ON arm** ("the live path's own fallbacks"): applied for a side whose
  PitcherStats has starter_known False. Park factor and the market blend are in neither arm (today's backtest has
  neither).
- **(e) The bar reads >= literally.** PASS iff OFF − ON ≥ 0.0050 on unrounded values: exactly 0.0050 passes, by the
  text; "a tie" is read as a tie of the arms (OFF = ON), which rejects.
- **(f) MLB has no Elo.** "The same Elo state" is read as the same run-profile history, profiles and production config:
  ONE walk prices both arms.
- **(g) The freeze is a separate command**, run before the run on the same copy, its files committed before the run.
- **(h) The roadmap lane's state and registry_id.** Ruled (ARCHITECT 2026-10-31 12:40 ET, addendum 192 item 2): the
  state becomes "declared" in #747; `registry_id` becomes "mlb-pitchers-v1" in this PR, where the entry is written,
  after #747 merges (both touch docs/roadmap.json).
- **(i) A FINISHED cohort game stored with equal scores** is scored y = 0 (not a home win) in both arms, as today's walk
  and the row contract (`home_won = home_score > away_score`) read it. Classification never reads scores, so such a
  game would stay in the cohort. MLB resumes a suspended game rather than finishing it tied, so none is expected; the
  harness neither refuses nor relabels one (that would change the scored-set rule after the declaration).
- **(j) The 10-31 counting block is superseded.** The operator's block of 10-31 counted the 1553 by replacing the
  receipt module's `read_game` with a counting wrapper. The receipt now imports `read_game` and `reconstruct` from
  `src/walters/mlb_pitcher_asof.py`, whose `reconstruct` calls its own `read_game`, so that block would count 0 on this
  code. The same figure is the freeze's own console line (`both sides on a live path N · one side N · neither N`,
  from `mlb_pitcher_asof.cohort_ids(classify(...))`), and the freeze refuses unless both is exactly 1553.
- **(k) The copy's fingerprint (Codex on #748, P1; not built, for a ruling).** The run checks that the copy reproduces
  the frozen ids, but not that it is the frozen copy. A replaced copy with the same 1553 ids and different scores,
  earned runs or production config would be read. Proposal: the freeze records a fingerprint of the rows the run reads
  (2026 MLB matches, the 2026 appearance and starting-pitcher rows, the production MLB model row); the run refuses
  before its reservation unless the copy reproduces it. It adds a refusal to the declared run, so it waits for the
  architect.
