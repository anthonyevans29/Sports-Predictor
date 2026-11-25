## 2026-11-25 (#000: 497-1-dedupe-exit — dedupe-matches exits 1 when a provider read failed, after printing everything it printed before; a team with no provider id planned "orphan" is counted as a classification, exit 0; the routine nothing-to-do states each print one named line, exit 0 (ARCHITECT 2026-11-24, addendum 497 item 2 step (1), Q1, Q4 and Q8; MONEY-PATH; #1102))
- **src/ingestion/match_dedupe.py:**
  - `orphans()` returns a new key, `orphan_no_provider_team_id`: the ids of the "orphan" plans whose home or away team has no provider id, so the date search could match nothing. No plan entry changes.
  - New helpers, each line's words pinned by a test:
    - `unresolved_ids(r)` and `unresolved_line(ids)`: `dedupe-matches: N unresolved (provider read failed): <ids>`.
    - `no_team_id_line(ids)`: `dedupe-matches: N stale_orphan planned for a team with no provider id (a classification, not a failure)`, then `: <ids>` when N > 0.
    - `NOTHING_TO_MERGE_LINE`, `NO_CANDIDATES_LINE` and `every_live_line(n)`: `dedupe-matches: nothing to merge (no duplicate pairs)`, `dedupe-matches --orphans: nothing to do (no candidates)` and `dedupe-matches --orphans: nothing to do (every candidate live: N)`.
    - `outcome(r, orphans)` returns the lines and the exit: `EXIT_UNRESOLVED` (1) when anything is unresolved, else 0.
  - The module notes on the orphan outcomes name the exit and the classification.
- **cli.py dedupe-matches:**
  - Prints everything it printed before, in the same order: the summary, the plan, the apply counts, the state, the record line and the absent-tables line.
  - Then a new `_dedupe_outcome(r, orphans)` prints the outcome lines last.
  - `--orphans` prints the classification line on every run, zero included, and a routine line when there is no candidate or every candidate is live. When a provider read failed, it prints the unresolved line as the very last line and raises SystemExit(1). This holds for the dry run and `--apply` alike.
  - The pair path prints the routine line when there is no duplicate pair and nothing was refused at detection (no 3+ cluster, no same-or-missing-id pair, no swapped near-pair), and exits 0 either way.
  - `_dedupe_orphans` now returns its receipt (it returned None). Its printing is unchanged.
  - The command's docstring says the record line is followed by the outcome lines.
- **The failure sites** (match_dedupe.py at 7e8748e3):
  - `resolve`'s by-id lookup that raised (376-380), planned "unresolved" for the whole candidate set (586-591);
  - `games_on`'s date search that raised (388-391), whose failed day leaves the set "unresolved" (618-625).
  - Both now exit 1. The pair path (`find_pairs`, `run`) reads no provider and has no unresolved state.
- **docs/CLI.md:** the dedupe-matches row gains its Exit paragraph.
- **tests/test_dedupe_exit.py** (15, the fake provider, no network):
  - a lookup that raised: exit 1 with its line last; every earlier line is identical to `_dedupe_orphans`' own printing of the same world; the same run with the lookup answered plans and prints every other row the same and exits 0;
  - a failed search day: its whole set unresolved, exit 1; a set it does not touch keeps its plan;
  - `--apply` with an unresolved entry: the apply counts as before, the unresolved row untouched, every row equal to the module's own apply of the same world, exit 1; with nothing unresolved, exit 0;
  - Q8's classification, dry run and apply: exit 0, its line with its id, the plan's stale_orphan count unchanged;
  - Q1's three routine states, each with its pinned line and exit 0, no provider call when there is no candidate; a pair-path run with a pair, or with a 3-row cluster refused at detection, prints no routine line (the cluster's run still exits 0);
  - the lines' words; none of them read by sp_run's retry classifier, exception line or count lines, laptop_routine's SYNC_ECHO, or closing's failure markers.
- **tests/test_dedupe_orphans.py:** the CLI dry-run test's world holds a broken lookup, so it now asserts exit 1 and the unresolved line last (it asserted 0).
- **Not changed:**
  - no plan entry, no write, no stored row;
  - the refusals at apply (a unique-table conflict, the STALE_ORPHAN CHECK guard), which keep exit 0;
  - deploy/hosting/sp_run.py, chains.py, closing.py, laptop_routine.py, bootstrap.py;
  - no stop rule or go_on;
  - no prediction output.
- **tests/test_qb_hold_receipt.py (#1142, the flake; addendum 541 item 3):** the figure checks no longer read a run's paths. The SOURCES line, the WHAT WAS DONE FROM line and the closing JSON line print the run's --db, --exports and --ledger by design, and a temporary folder's name can hold a sentinel figure: under `--basetemp=.../pytest-137` the JSON line's paths hold FILL_FIGURES' "137" and three tests failed. A new helper, `_printed(out, tmp_path, fixed)`, takes each spelling of the run's folder out (as #1139 takes the printed sha256 out of test_nfl_qb_agreement_receipt.py) and asserts the folder was there to take. The five figure checks (FILL_FIGURES in three tests with the unscored-row ids and the split-fill figures, CSV_FIGURES, RULING_FIGURES with FILL_PRICE) and the no-unit/no-word check read it. They now read the SOURCES, WHAT WAS DONE FROM and JSON lines too, which were skipped whole; only the script's fixed RULING quotations (and KEYS where it was skipped) stay out. scripts/qb_hold_receipt.py and its rule do not change.

  **Ruling (ARCHITECT 2026-11-25 15:06 ET, addendum 541 item 3), verbatim:**

  > 3. DEV 1 — THE FLAKE IN tests/test_qb_hold_receipt.py IS AN ISSUE (law 6). Open it, size S. The
  >    fault is the test's: its sentinel figure is one a temporary folder's name can hold. The fix is
  >    a sentinel no path can contain, or the assertion made on the receipt's printed fields and not
  >    on the whole text. The receipt's own rule does not change. It rides a PR of yours when one is
  >    open on tests; no date.
