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
- **Walk:** `soccer_backtest.run_soccer_backtest(code, season, min_prior=40, dixon_coles_rho, elo_goal_coeff)`, once
  per league-season. This is the existing leakage-free walk: matches in date order, each predicted from earlier
  matches only, Elo updated after each. 40 is the harness default (`soccer-backtest --min-prior`).
- **Leagues:** PD, SA, BL1, FL1, ELC (api-football league ids 140, 135, 78, 61, 40).

## 3. Test set and naive baseline

- **Test set:** seasons 2024/25 and 2025/26 of each league, the season strings as the DB stores club seasons. The run
  refuses, **before scoring anything**, if any league-season has no stored finished match. Missing data is never a
  silent DROP (law 4).
- **Naive:** per league, the H/D/A frequencies of its finished, scored 2023/24 matches. It is frozen and never
  computed from a test season. On each test match, naive log-loss = −ln(freq[actual]).

## 4. Gate (per league) and verdict

- **crit_ll:** `naive_ll − model_ll >= 0.010`, the intl-elo comparison verbatim (`intl_elo.run`). The tie is
  finding F4.
- **crit_bands:** the intl-elo-v2 calibration bands, `nhl_backtest.calibration_bands`:
  - 10pp bands, gated at n >= 100, ±5pp;
  - three (p, y) pairs per match: H, D, A.
- **Reported only:** RPS for model and naive.
- **A league survives** iff crit_ll AND crit_bands. A league that misses is DROPPED.
- **Verdict:** `PASS — surviving set <codes>` iff at least one league survives, else `FAIL — no league survives`.
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

## 7. FINDINGS for a ruling (the ruling leaves these undefined; nothing is chosen)

The one run REFUSES while any of these is open (`soccer_expansion.OPEN_FINDINGS`). A ruling closes them by editing
that tuple and this section in a reviewed PR.

- **F1 — a league without a stored 2023/24 season.** Its naive is undefined. The run refuses; `--preflight` shows
  which league.
- **F2 — promoted-club priors in the walk-forward.**
  - The existing harness walks each league-season on its own: fresh Elo, and strengths from that season's earlier
    matches only.
  - So no club carries anything across seasons, promoted or not, and the first 40 matches of each season are
    unscored.
  - Whether "the existing leakage-free walk-forward" means exactly this per-season walk, or a cross-season walk
    with a promoted-club prior, is for a ruling.
- **F3 — relegation / promotion play-off rows inside a league-season.** These are stored under the league with a
  non-regular `stage`, for example the ELC play-offs, or BL1/FL1 relegation play-offs where the provider files
  them under the league.
  - Whether they are scored, or excluded and counted, is for a ruling.
  - `--preflight` prints the test seasons' stages.
- **F4 — the tie.** The ruling says "log-loss <= naive − 0.010 (tie rejects)".
  - At exact equality, `<=` passes but "tie rejects" fails.
  - The code carries the intl-elo comparison (equality passes) until ruled.

Prerequisite, not a finding: each league's 2026/27 competition-season needs `sync-teams` once before the chains'
`sync-matches` (CLAUDE.md), on the laptop and on the host.

## 8. Chains (data only)

- `soccer-prematch` (Fri/Sat) adds `sync-matches` and `sync-odds` for PD, SA, BL1, FL1, ELC 2026/27.
- `soccer-morning-after` adds `sync-matches` for the five.
- There is no predict, no export and no Kalshi step.
- The laptop routine (docs/pl_weekly_routine.md) carries the same lines.

## 9. Laptop commands (after this declaration merges)

```
python cli.py soccer-expansion-gate --preflight     # receipts only: scores nothing, records nothing
# after F1-F4 are ruled (a PR closes OPEN_FINDINGS):
python cli.py soccer-expansion-gate                 # the ONE run; commit docs/registry/ in a PR
```
