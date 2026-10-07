# soccer-expansion-v1 — declaration (GATE-CLASS; declared before any read of the test seasons)

Registry id `soccer-expansion-v1` (docs/registry/experiments.json). The code is `src/walters/soccer_expansion.py`.
It is declared here and **not run**: nobody runs `soccer-backtest` on these leagues before this declaration merges,
and afterwards the command refuses them while the experiment is unrun.

## 1. The ruling (ARCHITECT 2026-10-07, verbatim)

> "The 2026-09-19 coverage decision (PD, SA, BL1, FL1 + ELC on the production soccer model) was never executed and
> predates the confirmation doctrine (#212). It now runs as ONE registered experiment, soccer-expansion-v1.
> Candidate: the PRODUCTION soccer model exactly as shipped: production params resolved at run time, no refit, no
> per-league tuning, the existing leakage-free walk-forward. Test set: seasons 2024/25 + 2025/26 of each of the five
> leagues, min_prior at the harness default. Gate, PER LEAGUE: log-loss <= naive - 0.010 on the same matches (tie
> rejects), naive = that league's own H/D/A frequencies from its 2023/24 season (frozen, never from the test
> seasons), plus the intl-elo-v2 calibration bands (10pp, n>=100, +-5pp, three pairs per match); RPS reported. A
> league that misses its own gate is DROPPED from the candidate; the verdict is PASS iff at least one league remains,
> and it names the surviving set. Confirmation: the first 60 league games of the surviving set kicking off after the
> verdict, pooled, cohort frozen by fixture id with the intl-elo-v2 machinery (unscoreable-only substitution);
> CONFIRMED iff pooled log-loss <= ln 3 AND < the pooled naive - 0.010 on the same games; per-league lines reported,
> not gated. Until CONFIRMED every one of these leagues is SHADOW: engine model_shadow, never a Desk call, never an
> order line, nothing that enters PL's evaluate / improve / results-tally / n=30 read. On CONFIRMED: Desk SOCCER
> policy unchanged, half units until 30 graded per league. PL is untouched throughout."

Also ruled the same day:
- "Nobody runs soccer-backtest on these leagues before the declaration merges."
- "Kalshi series for the five leagues: the operator's kalshi-probe receipt comes first; pin nothing until it is
  ruled."

## 2. Candidate (operational)

- **Model:** the production soccer model version, resolved at run time by the same helper `soccer-backtest` uses
  (`_soccer_prod_poisson`: production `dixon_coles_rho` and `elo_goal_coeff` from the stored model parameters).
  The run refuses if no production model resolves; nothing is faked.
- **Walk:** `soccer_backtest.run_soccer_backtest(code, season, min_prior=40, dixon_coles_rho, elo_goal_coeff,
  stage_filter=is_regular, batch_same_kickoff=True)`, once per league-season. This is the existing leakage-free walk:
  matches in date order, each predicted from earlier matches only. 40 is the harness default
  (`soccer-backtest --min-prior`). Ruled 2026-10-07 (section 7a): each league-season from a cold start, the two
  test seasons pooled per league (F2); regular-season rows only (F3); fixtures sharing a kickoff predicted before
  any of them updates Elo or the prior (F5). Both arguments are opt-in and default off, so every other caller
  of the walk is unchanged.
- **Leagues:** PD, SA, BL1, FL1, ELC (api-football league ids 140, 135, 78, 61, 40).

## 3. Test set and naive baseline

- **Test set:** the regular-season rows (F3) of seasons 2024/25 and 2025/26 of each league, the season strings as
  the DB stores club seasons. The run refuses, **before scoring anything**, if a kept league's test season would
  score nothing. Missing data is never a silent DROP (law 4).
- **Naive:** per league, the H/D/A frequencies of its finished, scored 2023/24 regular-season matches (F3). It is
  frozen and never computed from a test season. On each test match, naive log-loss = −ln(freq[actual]).
- **No complete stored 2023/24 (F1):** the league is DROPPED from the candidate before the run, never read, named
  with the reason. It is not a FAIL (section 7a).

## 4. Gate (per league) and verdict

- **crit_ll (F4, ruled: TIES REJECT):** `model_ll < naive_ll − 0.010` on unrounded values, no tolerance; equality
  fails.
- **crit_bands:** the intl-elo-v2 calibration bands, `nhl_backtest.calibration_bands`:
  - 10pp bands, gated at n >= 100, ±5pp;
  - three (p, y) pairs per match: H, D, A.
- **Reported only:** RPS for model and naive.
- **A league survives** iff crit_ll AND crit_bands. A league that misses is DROPPED.
- **Verdict:** `PASS — surviving set <codes>` iff at least one league survives, else `FAIL — no league survives`.
  A league dropped before the run (F1) is named apart:
  `· dropped before the run (no complete stored 2023/24 baseline; not gated): <code> (<reason>)`.
  The record carries `dropped` (the gate's drops) and `dropped_before_run` (code -> reason) separately.
  The verdict is computed; the architect rules.
- **Reported beside the gate, never gated:** the same scored matches against stored closing odds (bookmaker
  `fdcuk_close` from `soccer-odds-history`, proportionally de-vigged), where held:
  - priced / unpriced counts;
  - model vs market log-loss;
  - the >= +5pp positive-edge cohort (n, hits, mean edge), on the model's top pick vs the close.
- **Recording:** `registry.record_run` writes the scored-ids sidecar `docs/registry/ids/soccer-expansion-v1.txt`
  (every scored test match id, dropped leagues included) and the per-league result. The operator commits
  docs/registry/ in a PR.

## 5. Confirmation (executable plan in the registry)

- `confirmation_plan`: n_games 60, log_loss, bar 1.0986 (ln 3), must beat the pooled naive − 0.010 on the same
  games.
- **Cohort:** the first 60 league games of the surviving set kicking off after the verdict. It is frozen by fixture
  id with the intl-elo-v2 machinery: `registry.freeze_confirmation_cohort`, with unscoreable-only substitution.
- Per-league lines are reported, not gated.
- The confirm command is built after the verdict, once the surviving set exists. It is not part of this declaration.

## 6. Shadow (until CONFIRMED)

- `export-soccer-expansion-shadow` prices the five leagues' scheduled matches in the window (72h default) with the
  production model.
  - The walk covers the current season's finished matches before now, using the same harness walk.
  - Below min_prior finished matches, a league prices nothing, and that is counted.
- It writes `exports/soccer_expansion_shadow_<stamp>.json`:
  - engine `model_shadow` (the Desk's `normalize` skips it; the Cockpit renders it in the greyed shadow card);
  - per-row `gate_verdict` from the registry;
  - `contains_predictions: false`.
- It writes no Prediction row. So nothing reaches `evaluate`, `improve`, the results tally or the PL n=30 read.
- `soccer-expansion-shadow-grade` (read-only) compares the shadow's top pick to the three-way book close (the #207
  close contract), per league.

## 7. FINDINGS (F1–F5 ruled 2026-10-07, section 7a; F6 OPEN)

The one run REFUSES while any finding is open (`soccer_expansion.OPEN_FINDINGS`). **F6 is not ruled, so the run
still refuses.** A ruling closes it by editing that tuple and this section in a reviewed PR.

- **F1 — a league without a stored 2023/24 season.** RULED (7a): dropped before the run.
- **F2 — promoted-club priors in the walk-forward.** RULED (7a): the per-season cold-start walk, no cross-season
  prior.
- **F3 — relegation / promotion play-off rows inside a league-season.** RULED (7a): regular-season rounds only.
- **F4 — the tie.** RULED (7a): TIES REJECT.
- **F5 — fixtures sharing a kickoff** (Codex on #326). RULED (7a): batched for this gate, opt-in, default off.
- **F6 — a league with no gated calibration band** (Codex on #326). **OPEN, not ruled.**
  - The bands criterion is the intl-elo-v2 one verbatim: every band with >= 100 observations is within ±5pp, so a
    league where no band reaches 100 passes it vacuously and is gated on log-loss alone.
  - The same rule stands in the intl-elo-v2, NHL and NCAA gates. Whether this gate treats an empty gated-band set as
    a pass, a DROP, or a refusal (and with what pre-read threshold) is for a ruling. The code is unchanged.

## 7a. Rulings on F1–F5 (ARCHITECT 2026-10-07, addendum 3, item B, verbatim)

> "F1: a league without a complete stored 2023/24 season has no baseline and is DROPPED from the candidate before the run, named with that reason. Not a FAIL; it may be declared later on its own. F2: yes. The gate uses the harness as every PL verdict has: each league-season walked on its own from a cold start, min_prior 40, the two test seasons pooled per league. No cross-season prior is added; that would be a different instrument and a different experiment. F3: only regular-season rounds are scored and walked. Play-off rows (relegation, promotion or championship rounds stored inside a league-season) are excluded from the test seasons and from the 2023/24 baseline. The preflight prints every distinct stage / round label per league-season with its count and placement; a label the code cannot place refuses the run, never guessed; the architect confirms the placement from the preflight before the run. F4: TIES REJECT. PASS iff log-loss < naive - 0.010 on unrounded values; equality fails. The confirmation's second criterion is already strict. Recorded as a finding, no run record touched: intl-elo's gate text says 'tie rejects' while its code passes equality; immaterial to its verdict (0.7889 against 1.0424). F5: for THIS gate the walk predicts every fixture sharing a kickoff timestamp before any of them updates the state. An opt-in argument of run_soccer_backtest, default off, so every existing command reproduces its recorded numbers. This gate is an absolute test against a baseline that cannot see same-kickoff results, so the model must not either. No past verdict is reopened: each compared two arms on the same walk."

It rules F1–F5 only. F6 is not ruled and stays in `OPEN_FINDINGS`: the run still refuses.

### Built

- **F1:** before the run, `baseline_complete` judges each league's 2023/24. A league without a complete stored
  season is dropped from the candidate (no test-season read for it) and named with its reason in the verdict, the
  record (`dropped_before_run`) and the reservation file. `--preflight` prints the judgement per league.
- **F2:** no code change. The walk is per league-season from a cold start (fresh Elo, strengths from that season's
  earlier rows), min_prior 40, the two test seasons pooled per league. This was already the behaviour.
- **F3:** `placement(label)` (pure) maps a stored stage label to `regular`, `playoff` or None (cannot place).
  - `Match.stage` stores api-football's fixture `league.round` verbatim (`adapters/api_football.py`; the soccer
    default adapter). `Match.matchday` is the integer parsed from it, and is not used here.
  - `regular`: exactly `Regular Season - <n>` (full match, case-sensitive).
  - `playoff`: a label naming a play-off, relegation, promotion or championship round, or a (quarter-, semi-)
    final.
  - Anything else, NULL and empty included: None.
  - `--preflight` prints every distinct label per league-season (2023/24 and both test seasons) with its count and
    placement. Any unplaced label refuses the run, before the reservation. **The architect confirms the placement
    from the preflight before the run.**
  - The walk takes `stage_filter=is_regular` (an opt-in argument of `run_soccer_backtest`, default None = every
    row): play-off rows are neither scored nor walked. `naive_for`, `finished_count` and `scoreable_count` apply
    the same filter.
- **F4:** `crit_ll = ll_model < ll_naive − 0.010`, unrounded, no tolerance. Equality fails (pinned by a test at
  exact equality). intl-elo's own code is untouched (finding below).
- **F5:** `run_soccer_backtest(batch_same_kickoff=True)`, opt-in, default False. Every fixture sharing an identical
  kickoff timestamp is predicted from the same state before any of them updates Elo or the prior. The default walk
  is byte-identical to the pre-change walk (pinned by a test). `scoreable_count` mirrors the batched predicate: a row
  scores iff at least min_prior rows have a strictly earlier kickoff and both its clubs are among them.

### Readings chosen where the ruling is silent (for the architect)

1. **"Complete stored season" (F1):** over the league's stored 2023/24 regular-season rows (STALE_ORPHAN rows
   excluded: never a fixture, ruling 2026-10-03), at least one exists, every one is FINISHED with both scores, and
   they form a full double round-robin: T distinct clubs, exactly T×(T−1) rows, each ordered home/away pair once.
   This is derived from what the DB stores, with no per-league constant. A partly synced season, a duplicate row or a
   postponed / cancelled fixture makes it incomplete, so the league is dropped and named with the counts.
2. **All five dropped before the run:** the run refuses ("nothing to test"), before the reservation. It does not
   record a FAIL.
3. **Placement vocabulary (F3):** only the exact api-football league-round form is regular. The play-off keywords
   are listed in `PLAYOFF_ROUND` (play-off, relegation, promotion, championship round, quarter- / semi- / final). Everything else is unplaced and refuses, NULL included. No label was enumerated
   from the production DB here (none exists in this environment): the preflight is the enumeration, and the
   architect confirms it before the run.
4. **Census scope (F3):** the unplaced-label refusal covers every stored row (any status but STALE_ORPHAN) of all five
   leagues' 2023/24 and both test seasons, including a league that F1 then drops. The completeness judgement
   needs every 2023/24 label placed; for the test seasons this is simply the more conservative choice.
5. **Batch key (F5):** "the same kickoff" = an identical stored `utc_date` (to the second). Within a batch, the Elo
   updates apply in the walk's sort order after every prediction of the batch.
6. **The shadow** (`export-soccer-expansion-shadow`) is not the gate. It keeps its existing walk (no stage filter,
   no batching).

### Ledger finding (no run record touched)

intl-elo's gate text says "tie rejects" while its code passes equality (`intl_elo.py`,
`(ll_naive - ll_model) >= LL_MARGIN - 1e-12`). This is immaterial to its verdict (0.7889 against 1.0424). It is
recorded as a finding only: no code and no registry run record is touched.

Before any league is scored, the run also refuses a test season the walk would score nothing in (Codex on #326).
It checks the walk's own predicate from fixture order and team ids only, on the regular-season rows: a row is
scored once at least min_prior rows have a strictly earlier kickoff and both its teams appear among them (F5
batched; `soccer_expansion.scoreable_count`; no score is read).

The one run RESERVES the gate (Codex on #326). After every pre-check (open findings, unplaced labels, the F1
pre-run drops, the scoreable check) and before the first test-season read, it
creates `docs/registry/soccer-expansion-v1.started.json` exclusively. A second, concurrent, interrupted or failed
attempt is refused while that file exists without a recorded run: the read is spent, recorded or not, and nothing
reruns without an architect ruling. The run record keeps each league's calibration band rows.

Prerequisite, not a finding: each league's 2026/27 competition-season needs `sync-teams` once before the chains'
`sync-matches` (CLAUDE.md), on the laptop and on the host.

## 8. Chains (data only)

- `soccer-prematch` (Fri/Sat) adds `sync-matches` and `sync-odds` for PD, SA, BL1, FL1, ELC 2026/27.
- `soccer-morning-after` adds `sync-matches` for the five.
- There is no predict and no export. The Kalshi step is CAPTURE ONLY (below).
- The laptop routine (docs/pl_weekly_routine.md) carries the same lines.

## 8a. Kalshi series (ARCHITECT 2026-10-07, addendum 2, verbatim)

Ruled from the operator's kalshi-probe receipt of 2026-10-07 (131 series matched):

> "PD -> KXLALIGAGAME (La Liga Game); SA -> KXSERIEAGAME (Serie A Game; not KXBBSERIEAGAME, KXSERIEAWGAME or KXBRASILEIROGAME); BL1 -> KXBUNDESLIGAGAME (Bundesliga Game; not KXBUNDESLIGA2GAME, KXBBLGAME or KXWDBBLGAME); FL1 -> KXLIGUE1GAME (Ligue 1 Game); ELC -> KXEFLCHAMPIONSHIPGAME (EFL Championship Game). Recorded, not wired: EL1 -> KXEFLL1GAME, EFL -> KXEFLCUPGAME, CZE -> KXCZEFLGAME. A pinned series never makes a league live."

- `src/adapters/kalshi.py` `SOCCER_GAME_SERIES` pins the five (resolved without discovery). EL1, EFL and CZE are in
  `SOCCER_SERIES_RESERVED`: `sync-kalshi-soccer --competition <code>` refuses them, naming the series and the ruling.
- Each league's `sync-kalshi-soccer --competition <code>` runs on the shadow chain (`soccer-prematch`, Friday and
  Saturday) and the laptop routine, as CAPTURE ONLY (`chains.KALSHI_CAPTURE_ONLY`).
- They are deliberately NOT in `WINDOW_KALSHI`: the window card spans every competition, and a capture-only league
  adds no Kalshi line to it. No chain predicts or exports these leagues, so no Desk call is ever made on them.
- The fee schedule (`venue.KALSHI_FEE_M`) does not list these series: an unlisted series is priced at the default
  taker M=1 with no maker cost assumed (conservative unknowns), which matters only once a league is live.

## 9. Laptop commands (after this declaration merges)

```
python cli.py soccer-expansion-gate --preflight     # receipts only: scores nothing, records nothing
# F1-F5 ruled 2026-10-07; after F6 is ruled (a PR closes OPEN_FINDINGS) and the architect confirms the F3
# placement from the preflight:
python cli.py soccer-expansion-gate                 # the ONE run; commit docs/registry/ (incl. the .started.json) in a PR
```
