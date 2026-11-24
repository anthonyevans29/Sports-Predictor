**2026-11-23 — The laptop's morning routine as one committed list and one command: deploy/hosting/laptop_routine.py, ops tooling, no host file changed (addendum 451 item 3, amended by addendum 461 items 2 to 4; #1067).**
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
- **The amendment (ARCHITECT 2026-11-23 12:45 ET, addendum 461 items 2 to 4), verbatim:**
  > 2. THE LAPTOP ROUTINE, YOUR TWO FAILING TESTS (your report on #1067, 17:27Z). You were right to stop.
  >    NEITHER TEST IS TOUCHED AND NEITHER PIN IS WIDENED. Both failures come from my own text in 451, and I
  >    amend 451, not the tests.
  >    (a) tests/test_mlb_retire_orphans.py, test_never_inside_the_watch. The pin says no file under
  >        deploy/hosting names the command, and it stands as written. 451 item 3(d) step 2 LEAVES THE
  >        ROUTINE. The dry run stays in my block, by hand, after the routine returns. The daily list is 16
  >        steps: renumber them, in the same order. 451 item 3(f) 7 is amended to match: five MLB steps stay
  >        in the routine through the off-season, and the sixth is mine.
  >    (b) tests/test_host_watch_after_flip.py, the fence's inputs. The pin says no production file outside
  >        desk_policy references a fence input, and it stands as written. 451 item 3(b) named
  >        desk_policy.machine_role(), which is a fence input; that was my error. The routine does not call
  >        it and does not name it, in code or in a string.
  >    (c) closing.mirror_role() is NOT the substitute. It reads the environment first, so a routine typed
  >        by hand on the host could be answered by the checkout's .env, which on the host says laptop
  >        (role_reading's own docstring, the #410 review). The refusal must rest on the fence's reading.
  >    (d) WHAT IS BUILT: desk_policy.not_laptop_reason(), beside not_host_reason() and on its pattern (178
  >        R6). None on the laptop; otherwise why this machine is not the laptop, by role_reading, read only:
  >        the role is host, unset, a value that is neither, or host.env exists and cannot be read. Its
  >        docstring says, as not_host_reason's does, that it is not a fence input: host_fenced never reads
  >        it. The routine calls it, prints the reason and exits 2 with nothing run when it is not None.
  >    (e) THAT FUNCTION SHIPS FIRST, AS ITS OWN SMALL PR: the function and its tests, nothing else.
  >        desk_policy is money-path code and is read alone; by the stop rule its P2s after round two are
  >        listed for me. A reviewable head by Tuesday 2026-11-24. The routine's PR follows on it and stays
  >        ops tooling. If either pinned test still fails with (a) and (d) built, name it to me before
  >        touching it, as before.
  >
  > 3. YOUR THREE QUESTIONS, RULED.
  >    (a) A PER-STEP TIMEOUT: YES. The agent runs this command, and a step that hangs must not hold the
  >        morning. Each entry of the list carries its limit in seconds, a constant in the module: 1,200 for
  >        a daily step (each single-day sync counts as its own step), 2,400 for each line of the weekly
  >        pass. At the limit the child is sent SIGTERM, then SIGKILL after 10 seconds if it has not ended.
  >        The step's line and receipt say "timed out after N s", its exit is recorded as null, it counts as
  >        a failed step, and the next step runs. A limit changes only by my ruling; the seconds printed per
  >        step are what I rule it from.
  >    (b) FAC 2026/27: AS BUILT. The module adds no competition by name; FAC stays in my block (406 item
  >        3(c)).
  >    (c) A RECEIPT THAT CANNOT BE WRITTEN: AS BUILT. The line is printed, the next step runs, the run
  >        receipt lists the steps, and the run exits 1.
  >    (d) THE EXITS, so the block can read them: 0 when every step is clean, or its exit is one the list
  >        marks routine, and every receipt is written; 1 when a step failed, timed out or went
  >        unreceipted; 2 for the refusal, nothing run.
  >
  > 4. TESTS ADDED TO 451 item 3(g): a step that outlives its limit is ended, recorded as timed out, and the
  >    next step runs (a child that sleeps, a limit of one second); a child that ignores SIGTERM is killed;
  >    the refusal's test reads not_laptop_reason on each of its four answers. The date stands: a reviewable
  >    head of the routine by Monday 2026-11-30.
- **The two readings, ruled (ARCHITECT 2026-11-23 15:20 ET, addendum 469 item 5 (1)-(2)), verbatim:**
  >    (1) THE LIMIT IS EACH COMMAND'S, AS BUILT: 2,400 s for each command of a weekly line and 1,200 s for
  >        each command of a daily step. The docs drop "pending your reading" and say so.
  >    (2) YES: a step whose output could not be fully read is unreceipted in 461 item 3(d)'s sense; the
  >        run exits 1 and the receipt says why.
- **What landed:**
  - `deploy/hosting/laptop_routine.py`: the daily list (`DAILY`) and its runner, `python deploy/hosting/laptop_routine.py [--weekly] [--dry-run]`. The list is 451 item 3(d) less its step 2, renumbered 1 to 16 in the same order (461 item 2(a)): steps 6 and 7 (NBA, NCAAMB) and 11 (NHL) one day at a time, 14 and 15 two steps each, 6 seconds after each basketball day; 26 commands in all.
  - The MLB orphan dry run is not in the list and no file under deploy/hosting names the command (461 item 2(a); the pin stands as written). It stays in the architect's block, by hand, after the routine returns. Five MLB steps stay in the routine through the off-season; the sixth is the architect's (451 item 3(f) 7, amended).
  - The refusal comes first: exit 2, nothing resolved, read or run, when `desk_policy.not_laptop_reason()` is not None; the reason is printed (461 item 2(d)). The routine names no fence input, in code or in a string (461 item 2(b)), and never rests on closing's environment-first reading (461 item 2(c)). A real run's refusal writes one receipt (`refused: not_laptop_reason`, the reason beside it; its time and run id are resolved after the read, for that receipt alone); a dry run's writes none and resolves nothing, as sp_run's dry runs write none. A read that raises is refused the same way, its error printed and receipted (by its class name alone when redacting it raises too).
  - Each step runs as `sys.executable cli.py ...` from the checkout, in order. A failing step never stops the next, and none is retried. The step's output streams indented; then one line per step (number, command, exit, seconds), and a sync step's own count, orientation, refusal, collision, skipped-listing and held lines under it (a sync: every `sync-` command, and `nhl-goalie-sync`, step 13, whose `  counts:`, `REFUSED game` and `not in our DB` lines are echoed). A non-zero step also prints its last output line. Last line: steps run, steps failed (a non-zero exit, a timed-out step and a step that could not start; the last two with exit null), non-zero exits, steps timed out and steps not started, routine exits apart.
  - The per-step timeout (461 item 3(a)): each entry carries its limit (`Step.limit_s`), a module constant: `DAILY_STEP_LIMIT` = 1200 and `WEEKLY_LINE_LIMIT` = 2400, for 461's "1,200 for a daily step (each single-day sync counts as its own step), 2,400 for each line of the weekly pass". The limit is each command's, as built, ruled by addendum 469 item 5(1): each of a weekly line's two commands gets its own 2,400 s, and each command of daily steps 14 and 15 (451's 15 and 16) its own 1,200 s. At the limit the child gets SIGTERM, then SIGKILL after `KILL_GRACE` = 10 s. The step's line and receipt say "timed out after N s", its exit is null, it counts as a failed step, and the next step runs. The routine keeps its own Popen loop: a reader thread streams the output while the main thread waits out the limit. After a clean exit, the reader is waited for as long as it is still reading, so a sync's last count line is kept. After a timeout, it is waited for the kill grace at most: a descendant that outlived the kill and keeps writing never holds the morning a further limit, and the step is also marked `output not drained`. A reader that reads nothing for the grace (a pipe held open) is left, silent; the step is then marked `output not drained`. The routine's own error while reading is marked `output not read` and the pipe is still drained, so it never reads as a timeout. Either keeps the child's exit, is named on the step's line and receipt (`output_error`), and makes the run exit 1: such a step is unreceipted in 461 item 3(d)'s sense (addendum 469 item 5(2)). No environment variable or option sets a limit; `run()` takes an override for the tests alone.
  - The exits (461 item 3(d)): 0 when every step is clean, or its exit is one the list marks routine, and every receipt is written; 1 when a step failed, timed out, could not start or went unreceipted (a step whose output is not whole included, by addendum 469 item 5(2)); 2 for the refusal, nothing run.
  - The placeholders come from sp_run's `date_vars` (UTC). It has no today-2 or today-8, so the module derives `today_minus2` and `today_minus8` the same way.
  - Routine exits, read from cli.py: `improve --sport mlb --hold-on-pass` gives a rejection NO non-zero exit. `improve_cmd` prints `✓ Candidate <v>: REJECTED` and returns 0. Its one `SystemExit(2)` is for `LegacySoccerImproveRefused`, which `training.improve` raises for soccer only. So no step carries a routine exit, and every non-zero exit counts as one. The marking (`Step.routine`) and its separate count are built and tested.
  - Receipts go through `sp_common.append_receipt` unchanged: one per step (kind `step`, unit `laptop-routine`, the shape bootstrap.py uses for its own steps) and one for the run (kind `laptop_routine`, never `chain`). A step that could not start is receipted with exit null (no exit invented) and `not_started` naming why; a step that timed out with exit null, `timed_out`, `limit_s` and `ended_by` (SIGTERM or SIGKILL). Every error the module redacts goes through one helper, `_redacted`: a receipt write, the role read, the weekly list's refusal, a step that cannot start and a read error each fall back to the error's class name alone when redacting raises too (sp_common.redact reads the checkout's `.env`, and one that is not UTF-8 raises), so no error path raises and the refusal stays exit 2. A receipt that cannot be written is printed (`receipt NOT written: ...`) and the run goes on to the next step; the run receipt lists those steps, the last line counts them, and the run exits 1 (461 item 3(c): as built).
  - `--weekly`: the list is read with `readonly_scope` (mode=ro, never created) and printed. Per line, `sync-teams` then `sync-matches`, 6 s after each, inserted before step 8 (NCAA's `sync-teams`, 451's step 9). An unreadable list refuses the run (exit 2). No competition is added by name; FAC 2026/27 stays in the architect's block (461 item 3(b): as built).
  - It does none of the backup, coverage, the MLB orphan dry run, the roadmap read, the mirror push, the stale count or the guarded college rows read. No page is sent (an `SP-PAGE:` line is printed, never delivered), and there is no timer, no launchd job and no soccer-refresh.
  - sp_run.py, sp_backup.py and chains.py are unchanged. No pin is widened and neither pinned test is touched (461 item 2).
- **The two pins (451 item 3(f) 17; 461 item 2):** tests/test_mlb_retire_orphans.py::test_never_inside_the_watch and tests/test_host_watch_after_flip.py::test_c_one_switch_the_cutover_pr_turns_off_and_the_pinned_routes_stay_shut both pass on the amended module, unedited. The refusal's function, desk_policy.not_laptop_reason(), shipped first as its own small PR (#1091, 461 item 2(e)).
- **Tests:** tests/test_laptop_routine.py. cli.py never runs: the process call is faked, and the two timeout tests (461 item 4) run a `python -c` child that sleeps (one with SIGTERM trapped) under a limit of one second. The refusal's test reads not_laptop_reason on each of its four answers. Real `python -c` children also cover the drain: a sync whose last line is its count line, behind a slow console; the routine's own read error; and a pipe held open by a grandchild. A checkout `.env` that is not UTF-8 (redact raising) on the three error paths: the role read raising (refused, exit 2, one receipt on a real run, none on a dry run), the weekly list's refusal (exit 2), and a step that cannot start (not started, the next step runs).
- **Docs:** README.md's laptop routine and docs/specs/h2-cutover-runbook.md's standing routine are rewritten (item 3(f) 15) for 16 steps, the dry run in the block, the limits and the exits. docs/CLI.md gains a row.
- **Addendum 479 item 1 (ARCHITECT 2026-11-23 17:17 ET), verbatim:**

  > 1. #1096's ROUND-TWO P2 (thread 4672345335; your report of 22:05Z), READ. The finding is right and your
  >    reading of it is the larger finding: ten of the twelve commands the routine runs can end a real
  >    failure with exit 0. RULED: IT DOES NOT BLOCK #1096. Your option (a), with one addition:
  >    (a) THE DOCS say the routine counts exits, not outcomes, and name the ten commands and the kind of
  >        failure each lets through, as your thread lists them.
  >    (b) THE ROUTINE SAYS IT TOO, where it is read: its last printed line, after the counts, reads
  >        "exits counted, not outcomes: a step that exits 0 may still have failed (see #N)", N the
  >        Issue of item 2. One line, no logic. That and (a) are your one round-three change.
  >    (c) Until item 2 is ruled I go on reading each step's own lines in the console, as I do now; the
  >        routine's count is a count of exits and I treat it as one.

- **As built (479 item 1, round three):** the module's docstring, README.md, docs/CLI.md and docs/specs/h2-cutover-runbook.md say the routine counts exits, not outcomes, and name the ten commands (the docstring with the kind of failure each lets through, as thread 4672345335 lists them; #1102 holds the lines). The run's last printed line, after the counts, is `EXITS_NOTE`, the item's words with N = #1102. One line, no logic; a dry run prints no counts and no note. No exit is changed.
- **Next:** review by the stop rule as ops tooling (451 item 3(h)); a reviewable head by Monday 2026-11-30 (461 item 4). Until it merges the architect writes the morning block by hand from 451 item 3(d), all 17 steps (461 item 5). The architect's block calls the command. Code ships no block (198 item 6(i)).
