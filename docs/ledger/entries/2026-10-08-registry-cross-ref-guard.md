**2026-10-08 — #329 RULED (ARCHITECT, addendum 11, item 5): the registry cross-ref guard is built, parts 1 and 2, as one shared function called by every cohort freeze and every one-run reservation.**
- **Ruling (verbatim):** "#329 RULED: build the guard as proposed, parts 1 and 2, as one shared function. Every cohort freeze and every one-run reservation calls it: a cohort, a run record or a reservation for the experiment on any ref the clone knows refuses, naming the ref and the commit. --no-fetch stays, and the receipt then prints that other clones were not checked. Its own small PR, before PR B."
- **The finding it closes (#329):** a registry write that lives only on an unmerged laptop branch is invisible to the next freeze. That is how the VOID second intl-elo-v2 cohort (2026-10-07, e697533) was accepted.
- **Built:** `registry.cross_ref_guard`.
  - Part 2: it fetches origin `laptop/*`. A failed fetch refuses unless `--no-fetch`.
  - Part 1: it scans every local and remote-tracking ref for a cohort, a run record or a reservation of the experiment that this tree does not hold identically, and refuses naming each ref and commit. It never overwrites.
- **Callers:** `freeze_confirmation_cohort` (`intl-elo-confirm --freeze-cohort`) and `soccer_expansion.reserve` (`soccer-expansion-gate`). `--no-fetch` is added to both commands.
- **Receipt (read-only, this clone, `--no-fetch`):** intl-elo-v2 would now refuse on the VOID cohort ref and on `laptop/intl-elo-v2-run-record`. soccer-expansion-v1 passes.
- Part 3 (the hourly sweep backstop) was already live and is unchanged.
