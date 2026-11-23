**2026-11-23 — The laptop's morning routine as one committed list and one command: deploy/hosting/laptop_routine.py, ops tooling, no host file changed (addendum 451 item 3; #1067).**
- **Ruling (ARCHITECT 2026-11-23 08:17 ET, addendum 451 items 2 and 3), verbatim:**
  > 2. #1067, THE LAPTOP-MORNING PLAN, READ WHOLE. It is careful work and its findings stand: sp_run has no
  >    machine guard; a per-step mirror push would fire; three ruled pins would break; the backup kinds are
  >    read by todays_daily and the closing watch. Those findings are why I DO NOT BUILD IT AS DRAWN.
  >    (a) The fault to mend is small: my hand-written block dropped steps. What mends it is the step list
  >        committed and checked, and one command that runs it. Nothing more.
  >    (b) sp_run.py, sp_backup.py and chains.py are the host's runner and its commands, and deploy scripts
  >        are money-path code. A convenience for the beta machine does not change them, widen a ruled pin
  >        or add a backup kind. NONE OF THE THREE FILES IS EDITED.
  >
  > 3. WHAT IS BUILT INSTEAD, one PR, ops tooling, no host file changed:
  >    (a) A NEW MODULE, deploy/hosting/laptop_routine.py: the list and its runner. It may import from
  >        sp_run and sp_common (date_vars, append_receipt) and changes neither.
  >    (b) THE COMMAND: python deploy/hosting/laptop_routine.py [--weekly] [--dry-run].
  >        - Refuses, exit 2, nothing run, unless desk_policy.machine_role() reads "laptop".
  >        - Runs each step as the checkout's own python on cli.py, in order. A FAILING STEP NEVER STOPS THE
  >          NEXT: every exit is printed and read by me.
  >        - First line: the UTC dates it resolved. Per step, one line: its number, the command, its exit,
  >          its seconds; for a sync, the line of counts and any orientation, refusal, collision or
  >          skipped-listing line. Last line: steps run, and non-zero exits.
  >        - A step whose non-zero exit is routine (improve's rejection, if cli.py gives it one) is marked
  >          in the list with the exits that are routine, read from cli.py, and counted apart.
  >        - One receipt line per step and one for the run, by append_receipt as it is.
  >        - --dry-run prints the resolved steps and runs nothing.
  >    (c) WHAT IT DOES NOT DO, each staying in my block as today: the backup (first, under a free name; my
  >        block does not call the command if the backup failed), coverage (after the backup, before the
  >        command), the roadmap read, the mirror push, the stale count, the read of the four guarded
  >        college rows. No page is sent. No timer and no launchd job. No soccer-refresh, ever.
  >    (d) THE DAILY LIST is this morning's block, in its order (block_1123, run 13:08Z, every exit 0):
  >         1  sync-matches --competition MLB --season 2026 --date-from 2026-10-15 --date-to {tomorrow}
  >         2  retire-orphans --competition MLB --season 2026
  >         3  evaluate --sport mlb
  >         4  improve --sport mlb --hold-on-pass
  >         5  export-results --sport mlb --competition MLB
  >         6  sync-kalshi
  >         7  sync-matches --competition NBA --season 2026, one day at a time: today-2, yesterday, today,
  >            tomorrow (--date-from D --date-to D)
  >         8  the same four days for NCAAMB
  >         9  sync-teams --competition NCAA --season 2026
  >        10  sync-matches --competition NCAA --season 2026 --date-from today-8 --date-to yesterday
  >        11  dedupe-matches --competition NCAA --orphans --sample 30 (the dry run; nothing applied)
  >        12  sync-matches --competition NHL --season 2026, one day at a time: yesterday, today, tomorrow
  >        13  export-fixtures --competition NHL
  >        14  nhl-goalie-sync --start {yesterday} --end {today}
  >        15  sync-matches --competition ATP --date-from {yesterday} --date-to {tomorrow}; the same for WTA
  >        16  sync-kalshi-atp; sync-kalshi-wta
  >        17  results-tally
  >        A wait of 6 seconds follows each basketball day, as the block has it.
  >    (e) --weekly runs, BEFORE step 9, the whole-season pass as Sunday's block ran it: the list read from
  >        the laptop's database (every competition-season with a game from 2026-07-01, except MLB, ATP,
  >        WTA, WC and NCAA), then per line sync-teams and sync-matches, 6 seconds after each.
  >    (f) YOUR QUESTIONS, ruled by number: 1, 2: the backup stays in my block, nothing built. 3: item (d)
  >        10, as the block runs it. 4, 5: not carried; the host's. 6: no internationals step daily; the
  >        weekly pass carries them. 7: the six MLB steps stay through the off-season; mlb-preslate is
  >        ruled when the season nears. 8, 9: in my block. 10: no page. 11: no. 12: every step goes on, in
  >        the block's order. 13: item (e). 14: my block runs it in the morning; the first line prints the
  >        dates. 15: the two stale passages are rewritten in this PR. 16: not needed. 17: NO PIN IS
  >        WIDENED; the list lives outside CHAINS; if a pin's test still fails on the new module, tell me
  >        which before touching the test. 18: no.
  >    (g) TESTS: every step's command and options exist in cli.py (the law-1 test's method, on this list);
  >        the refusal off the laptop; a failing step does not stop the next; --dry-run runs nothing; the
  >        weekly list's exclusions.
  >    (h) Review by the stop rule as ops tooling. A reviewable head by Monday 2026-11-30. Until it is
  >        merged I keep writing the block by hand from item (d).
- **What landed:**
  - `deploy/hosting/laptop_routine.py`: the daily list (`DAILY`, item 3(d), in the block's order, items 7, 8 and 12 one day at a time, 15 and 16 as two steps each, 6 seconds after each basketball day) and its runner, `python deploy/hosting/laptop_routine.py [--weekly] [--dry-run]`.
  - The refusal comes first: exit 2, nothing resolved, read or run, unless `src.walters.desk_policy.machine_role()` reads `laptop`. A real run's refusal writes one receipt (`refused: machine_role`); a dry run's writes none, as sp_run's dry runs write none.
  - Each step runs as `sys.executable cli.py ...` from the checkout, in order. A failing step never stops the next, and none is retried. The step's output streams indented; then one line per step (number, command, exit, seconds), and a sync step's own count, orientation, refusal, collision, skipped-listing and held lines under it (a sync: every `sync-` command, and `nhl-goalie-sync`, step 14, whose `  counts:`, `REFUSED game` and `not in our DB` lines are echoed). A non-zero step also prints its last output line. Last line: steps run, non-zero exits, routine exits apart.
  - The placeholders come from sp_run's `date_vars` (UTC). It has no today-2 or today-8, so the module derives `today_minus2` and `today_minus8` the same way.
  - Routine exits, read from cli.py: `improve --sport mlb --hold-on-pass` gives a rejection NO non-zero exit. `improve_cmd` prints `✓ Candidate <v>: REJECTED` and returns 0. Its one `SystemExit(2)` is for `LegacySoccerImproveRefused`, which `training.improve` raises for soccer only. So no step carries a routine exit, and every non-zero exit counts as one. The marking (`Step.routine`) and its separate count are built and tested.
  - Receipts go through `sp_common.append_receipt` unchanged: one per step (kind `step`, unit `laptop-routine`, the shape bootstrap.py uses for its own steps) and one for the run (kind `laptop_routine`, never `chain`). A step that could not start is receipted with exit null (no exit invented) and `not_started` naming why. A receipt that cannot be written is printed (`receipt NOT written: ...`) and the run goes on to the next step; the run receipt lists those steps, the last line counts them, and the run exits 1. A role read that raises is an unknown role: refused, exit 2.
  - `--weekly`: the list is read with `readonly_scope` (mode=ro, never created) and printed. Per line, `sync-teams` then `sync-matches`, 6 s after each, inserted before step 9. An unreadable list refuses the run (exit 2).
  - It does none of the backup, coverage, the roadmap read, the mirror push, the stale count or the guarded college rows read. No page is sent (an `SP-PAGE:` line is printed, never delivered), and there is no timer, no launchd job and no soccer-refresh.
  - sp_run.py, sp_backup.py and chains.py are unchanged. No pin is widened.
- **Pins that fail on the new module (item 3(f) 17: named before any test is touched; no test edited; NEEDS A RULING):**
  - tests/test_mlb_retire_orphans.py::test_never_inside_the_watch: no file under deploy/hosting may name `retire-orphans`; item 3(d) step 2 is that command.
  - tests/test_host_watch_after_flip.py::test_c_one_switch_the_cutover_pr_turns_off_and_the_pinned_routes_stay_shut (the fence's pinned routes, addendum 166 / #580): no tracked production file but desk_policy may reference a fence input; item 3(b) requires the `desk_policy.machine_role()` call. It fails only once the module is tracked (it reads `git ls-files`).
- **Open for the architect:** a per-step timeout (none ruled; sp_run has none); the weekly list cannot carry a competition the laptop holds no row of (FAC 2026/27, 406 item 3(c)).
- **Tests:** tests/test_laptop_routine.py. Subprocess is faked throughout and cli.py never runs.
- **Docs:** README.md's laptop routine and docs/specs/h2-cutover-runbook.md's standing routine are rewritten (item 3(f) 15). docs/CLI.md gains a row.
- **Next:** review by the stop rule as ops tooling (item 3(h)). The architect's block calls the command. Code ships no block (198 item 6(i)).
