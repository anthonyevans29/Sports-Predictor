**2026-10-09 — soccer-expansion-v1: the confirmation cohort, frozen on the laptop and spliced (ARCHITECT addendum 20 item 3).**
- The ruling (verbatim): "After the merge the operator pulls, freezes the cohort and pushes laptop/soccer-expansion-v1-cohort. Splice that the same way, in its own PR."
- Spliced by cherry-pick from `laptop/soccer-expansion-v1-cohort` at 716c56c, never retyped. Byte-identical to the branch:
  - `docs/registry/experiments.json`: the entry's `confirmation_cohort` only; no other key or entry changes.
  - `docs/registry/ids/soccer-expansion-v1.cohort.txt`: 60 ids, sha256 6ede4e7877ba….
- The cohort: frozen 2026-10-09T14:14:16Z (selected 14:14:14Z), 60 PD fixtures, all scheduled at the freeze, from 311 eligible stored.
  - First kickoff 2026-10-09T19:00:00Z, last 2026-11-22T16:00:00Z.
  - All kick off after the verdict's recorded time, 2026-10-09T12:47:39Z.
  - Rule as declared: the first eligible stored PD regular-season fixtures by (kickoff, id), not in the test set, not a stale orphan, any status.
- CONFIRMED iff the pooled log-loss is <= ln 3 and < the naive minus 0.010 on the same games. Until then PD is a shadow: never a Desk call, never an order line. The lane Issue #322 stays open.
