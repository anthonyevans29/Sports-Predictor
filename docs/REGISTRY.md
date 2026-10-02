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
| **declare** | in the candidate's PR, **before any run** | id, sport, lane, candidate, the frozen declaration document, training cutoff, test set, gate, **confirmation window** | an incomplete declaration; a duplicate id |
| **run** | the ONE scored run | scored match ids, result, **prior reads** (every earlier run on the same test set or with overlapping ids) | a run of an undeclared id; **a second run of the same id** (a test set is read once) |
| **verdict** | the architect's ruling, verbatim | PASS / FAIL / REJECT / WITHDRAWN | a verdict without a run |
| **confirmation** | after the declared window | CONFIRMED / NOT_CONFIRMED (verbatim ruling) | a confirmation outside a window |

**Prior reads** make a test set's history visible. A candidate that wins on a
test set read five times before says so in its own record. NHL's 2025 test set
has five prior reads already (v1 through v5).

## The confirmation doctrine

1. A gate **PASS is not production.** The entry moves to `confirming`.
2. Every declaration names its **confirmation window** before the run: future
   games the model never saw, the read that confirms it, and what would not
   confirm it. NFL's two-week ratification is the template.
3. Production follows only when the window closes with a recorded
   **CONFIRMED** ruling (`production_allowed()`).
4. A NOT_CONFIRMED outcome closes the entry. The bar does not move.

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
