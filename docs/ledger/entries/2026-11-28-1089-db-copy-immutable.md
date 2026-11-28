**2026-11-28 — every --db of the 16 scripts is read by one rule (src/walters/db_copy.py): the app's configured database, by resolved path or by identity, is the live file and keeps its open; any other --db is a copy, opened mode=ro&immutable=1 with no fallback, and refused before any open, exit 2, the path printed and never a row, under data/, with a sidecar beside it, or absent; the two live-file receipts refuse a --db that is not the configured database (ARCHITECT 2026-11-23, addendum 462 item 6; ruled by ARCHITECT 2026-11-27, addendum 582 item 4; #1089).**
- **The order, verbatim (ARCHITECT 2026-11-23 12:46 ET, addendum 462 item 6):**

  > 6. DEV 1 — A FINDING, ONE ISSUE (track:ops, class:finding, sport:all, size:M): 16 scripts under scripts/
  >    take --db and open it mode=ro WITHOUT immutable=1, against 198 item 6(ii). My count at 476674f4, by
  >    grep: kalshi_leg_audit, lineup_timing_probe, mlb_pitcher_asof_receipt, mlb_pitcher_probe,
  >    mlb_pitcher_season_receipt, ncaa_hawaii_receipt, ncaa_rekey_receipt, nfl_close_restate_receipt,
  >    nfl_injury_position_probe, nfl_neutral_site_receipt, nhl_gsax_feasibility,
  >    nhl_starter_timing_probe, replay_inventory_probe, results_tally_cohort_receipt,
  >    soccer_injury_factor_receipt, soccer_rating_coverage. A grep is a hypothesis (law 1): read each and
  >    say on the Issue, per script, what its --db may name (the live file, a copy, or either) and which
  >    open it uses, kalshi_leg_audit's fallback to a plain path with query_only among them (#421). Then
  >    one PR, read-only tooling: a --db that names a copy opens with immutable=1 beside mode=ro, on the
  >    pattern the other 16 already use; the live file keeps its open. Reviewable head by Friday
  >    2026-12-04. Until it merges, my blocks run none of the 16 on a fresh copy without my reading its
  >    open first.

- **The rule, verbatim (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4):**

  > 4. DEV 1 — Q2, #1089's RULE: YES, AS YOU PROPOSE, (a) TO (e), NO NEW FLAG.
  >    (a) The live file is the app's configured database, by resolved path and by identity, and keeps
  >        its open. Any other --db is a copy: mode=ro with immutable=1 and no fallback.
  >    (b) A copy is refused before any open, nothing read, exit 2, the message naming which case: under
  >        data/; a sidecar beside it; the file absent. The path is printed, never a row.
  >    (c) The two live-file receipts refuse a --db that is not the configured database, as you say.
  >    (d) A machine whose configuration is not loaded reads its own live file as a copy under data/ and
  >        refuses. That is the conservative answer and it stands; the help line says so.
  >    (e) The smaller findings stay on the Issue but where (a) and (b) touch their lines. One PR,
  >        read-only tooling, a head by 2026-12-04. 462 item 6's last sentence stands until it merges.

- **What changed:**
  - **`src/walters/db_copy.py`, new:**
    - `classify(db)` gives ("live", path) for the configured database and ("copy", path) after `check_copy`. check_copy runs mlb_pitchers_gate.check_db, the standing --db fence, then the sidecar check.
    - `connect_copy` and `copy_engine` open through the percent-encoded file URI with `?mode=ro&immutable=1`, with no fallback.
    - `require_live` serves the two live-file receipts.
    - CopyRefused is raised before any open, and also for an empty --db, a path that cannot be resolved, and a copy SQLite cannot open, so each script prints one line and exits 2.
  - **The 14 scripts that take either file:** the live open is kept as it was, with #421's fallback where it had one. Copies go through db_copy. A copy that opens but cannot be read is one REFUSED line and exit 2.
  - **The two live-file receipts** (nfl_close_restate_receipt, results_tally_cohort_receipt): `require_live`, 582 item 4(c). Their `os.environ.setdefault("DATABASE_URL", ...)` did nothing once the configuration was loaded, and is removed.
  - **Help lines:** each `--db` help line says the rule, with 582 item 4(d)'s words.
  - **Docstrings:** they give the plain-path fallback to the live file alone.
  - **Docs:** docs/CLI.md and scripts/README.md rows are rewritten inside their own lines, because other files cite those lines by number.
- **Pins moved, as 582 item 4(b) and (c) rule:**
  - **Absent-file tests:** each still asserts that no file is created, and now asserts exit 2 and the REFUSED line naming the path.
    - tests/test_lineup_timing_probe.py::test_no_database_file_is_never_created
    - tests/test_mlb_pitcher_probe.py::test_it_writes_nothing_and_never_creates_a_database
    - tests/test_nhl_gsax_feasibility.py::test_no_database_is_never_created
    - tests/test_replay_inventory_probe.py::test_the_probe_never_creates_a_database_and_writes_nothing
    - tests/test_mlb_pitcher_asof_receipt.py::test_it_writes_nothing_and_refuses_a_missing_db
    - tests/test_nfl_stale_book_close.py::test_the_restate_receipt_refuses_a_missing_db_and_creates_none
  - **The copy's open in a header:** tests/test_replay_inventory_probe.py::test_the_header_names_the_keys_the_schema_and_the_closing_files.
  - **The live receipts' tests:** their scratch file is now named as the configured database, and every assertion is kept.
    - tests/test_nfl_stale_book_close.py: test_the_restate_receipt_prints_both_records_and_writes_nothing, test_the_receipt_leaves_a_void_row_out_of_its_tally_and_names_it, test_the_receipt_refuses_when_the_db_changes_between_its_passes
    - tests/test_book_source_times_615.py: test_the_cohort_receipt_prints_before_and_after_from_one_db_state (its missing-file half now names the absent case), test_the_cohort_receipt_refuses_when_the_db_changes_between_its_passes, test_the_cohort_receipt_holds_one_clock_and_leaves_grading_close_as_main_runs_it
- **Left on #1089 (582 item 4(e)):**
  - A copy whose tables are there but whose columns are not (an older schema) still ends in the script's own traceback, with no fallback and nothing written.
  - ncaa_rekey_receipt's `--reconstruct-merges --backup` file keeps its old open, because it is not a --db.
  - With no --db, each script's default open is as it was.
- Read-only tooling: no Desk call, export or model output changes. 462 item 6's last sentence stands until this merges.
