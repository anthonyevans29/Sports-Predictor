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

## A live model's certification (addendum 214)

**ARCHITECT 2026-11-02 10:15 ET, addendum 214 item 4(b)** (verbatim): "THE REGISTRY: nfl_elo_v1's entry gets the
regression line verbatim (stream 676, the 70–80% band 7.7pp, #775 issuecomment-6580087145) and the state "UNCERTIFIED —
shadow, confirmation window (addendum 214 item 3)", with the window's definition and bar written in."

- **The entry:** `nfl-elo-v1`. Its gate predates the registry (the NFL phase-2 gate, frozen 2026-09-09; PASS that
  day; LIVE from Week 3, 2026-09-22). On the complete 2024 warm-up (#775) the same gate reads FAIL, so its verdict is
  `VOID` (the earlier PASS kept under `was`), its `regression` holds the before and after figures, and its
  `certification` is the ruled state. The window and its bar are addendum 215 item 1's: every NFL regular-season and
  postseason game with a kickoff strictly after 2026-11-02 15:15Z that reaches FINISHED with a stored close, through
  the Super Bowl, read once after 2027-02-08.
- **The status vocabulary has no "uncertified".** The entry's status is `confirming` (a forward confirmation window,
  a shadow, never a call), the closest that keeps production off. `production_allowed()` refuses any entry whose
  `certification` starts with UNCERTIFIED. With no executable `confirmation_plan` (the bar is two criteria against the
  window's own baseline, not one fixed number), `record_confirmation()` and `freeze_confirmation_cohort()` refuse it.
- **Where it is read:** an entry's `model_version` is the id a predict path writes (`nfl_predict.MODEL_VERSION`).
  `registry.uncertified_live()` finds the entry that withholds that model. `cli.py coverage`, the Cockpit's Today tile,
  then reads its competitions as not LIVE: `MARKET-ONLY`, with `shadow v1` from the confirming `nfl-confirm` lane.
  Addendum 217 item 5: "the tile reads the registry". The Desk's own market-only rule is
  `desk_policy.NFL_MARKET_ONLY_RULE` (#778); the registry entry changes no Desk call.

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
