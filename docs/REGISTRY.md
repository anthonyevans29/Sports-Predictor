# Experiment registry and the confirmation doctrine (#212)

**Ruled** (ARCHITECT 2026-10-01, external review): "experiment registry
(candidate, training cutoff, scored match ids, prior reads) + DOCTRINE: a gate
pass is followed by a declared future-confirmation window before production
(NFL's two-week ratification generalized). Existing verdicts unchanged."
**2026-10-02:** "the registry (#212) records every candidate from here."

## The ledger

`docs/registry/experiments.json` is tracked in git and reviewed in PRs. It never
lives under `data/`. Each run's scored match ids go in a sidecar file,
`docs/registry/ids/<id>.txt`, alongside their count and sha256. The module is
`src/walters/registry.py`.

| Step | When | What it records | Refuses |
|---|---|---|---|
| **declare** | in the candidate's PR, **before any run** | id, sport, lane, candidate, the frozen declaration document, training cutoff, test set, gate, the **confirmation window** (prose) AND its executable **confirmation_plan** {n_games, metric, bar, must_beat_reference, reference} | an incomplete declaration or plan; a duplicate id |
| **run** | the ONE scored run | scored match ids, result, **prior reads** (every earlier run on the same test set or with overlapping ids) | a run of an undeclared id; **a second run of the same id** (a test set is read once) |
| **verdict** | the architect's ruling, verbatim | PASS / FAIL / REJECT / WITHDRAWN | a verdict without a run |
| **cohort** (optional; intl-elo-v2) | as soon as the schedule holds the window | the confirmation COHORT: the first n_games eligible fixture ids, chosen whatever their status (never from available results), frozen once (sidecar `<id>.cohort.txt` + sha256). The read must then score exactly this set; a pending label leaves it incomplete, never replaced (review on #248, 2026-10-02) | a second freeze; anything but exactly n_games distinct ids; a test-set id |
| **substitution** (frozen cohorts) | when a cohort fixture becomes UNSCOREABLE (cancelled / abandoned; awarded / walkover) | ARCHITECT 2026-10-02: the fixture is RELEASED and replaced by the next eligible fixture after the cohort (61st, 62nd …), recorded with the raw provider code as reason and evidence ("unscoreable is the criterion, not the status label"); the frozen file never changes, the effective cohort applies the substitutions | evidence that is not a cancelled or finished-unscoreable fixture (a postponed or unplayed game stays); no raw code; a released id returning; a replacement already in the cohort or from the test set |
| **confirmation** | after the declared window | the confirmation READ: its scored match ids (sidecar `<id>.confirm.txt` + sha256) and result; the outcome is **computed** from the plan (metric <= bar and, when required, < the reference on the same games; a tie fails), never stated | outside a window (no PASS); a scored set that is not exactly the frozen cohort (when one is frozen); fewer games than the plan; any game starting before the verdict; any game from the scored test set; a result without the plan's metric (or the reference's) |

**Prior reads** make a test set's history visible. A candidate that wins on a
test set read five times before says so in its own record. NHL's 2025 test set
has five prior reads already (v1 through v5).

## The confirmation doctrine

1. A gate **PASS is not production.** The entry moves to `confirming`.
2. Every declaration names its **confirmation window** before the run: future
   games the model never saw, the read that confirms it, and what would not
   confirm it. NFL's two-week ratification is the template.
3. Production follows only when the window closes with a recorded,
   **computed** CONFIRMED outcome that carries its scored ids and result
   (`production_allowed()`). An immediate or incomplete confirmation is
   refused. Review on #222 (2026-10-02) reproduced declare → run → PASS →
   CONFIRMED in one second; the regression test pins that it now fails.
4. A NOT_CONFIRMED outcome closes the entry. The bar does not move.

## Run records are never rewritten

**ARCHITECT 2026-10-02:** "never rewrite a run record". A run record's stored
prior-read count is what its machine computed at record time. When a laptop
computed it before an earlier run was spliced into its ledger, the entry gains
an annotation, `ledger_count_at_record` (plus a one-line `ledger_count_note`),
beside the untouched run block. **The live count is the ledger's**
(`registry.prior_reads`). The first case is nhl-v7: 5 recorded, 6 in the ledger.

## Retired test sets (doctrine, binding)

**ARCHITECT 2026-10-02** (verbatim; from the external review, now binding):
"the 2025 test season has been read 7 times. After v8 it is RETIRED as a test
set; any later NHL candidate declares 2026-27 (as it accrues, >=600 games) as
its test season."

| Test set | Reads | Last candidate allowed | Declare instead |
|---|---|---|---|
| NHL 2025 (2025-26 regular season; nhl_backtest TEST_SEASON, train 2024) | 7 before v8 (v1–v5 seeds, v6, v7); v8 is the 8th | `nhl-v8` | NHL 2026-27 regular season, as it accrues (≥ 600 games) |

- **Enforced in code:** `registry.RETIRED_TEST_SETS`. `declare()` and
  `record_run()` refuse any id other than the last allowed one on a retired
  test set, and the refusal names what to declare instead.
- **Why:** each read of a test set spends it. After many reads, a "pass" on
  that set is selection, not evidence. The prior-read count shows the cost;
  retirement stops the spending.

## Pre-registry verdicts

The verdicts already on record are seeded unchanged: NHL v1–v5, S19, DC-fit,
S14 stage 2 and cups fix-v2. Their scored ids were not recorded, and the
ledger says so; nothing is reconstructed. They count as prior reads of their
test sets.

## CLI

- `python cli.py registry`: the ledger, read-only. One line per entry with
  status, result, verdict and prior-read count.
- `python cli.py registry --id ID`: one entry in full, including its prior
  reads.
