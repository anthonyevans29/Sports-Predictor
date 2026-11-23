**2026-11-23 — BUILT (ARCHITECT 2026-11-23 08:54 ET, addendum 453 item 3(d)): `soccer-expansion-confirm --db COPY`, the twin of `intl-elo-confirm --db`, so the PD substitution (453 item 2) and the record of 2026-12-22 run on the host's pulled .backup copy and their registry change lands in a PR.**
- **Ruling (verbatim, addendum 453 items 2 and 3):**
  > 2. RULED: 16204 IS RELEASED AND REPLACED UNDER THE COHORT'S OWN DECLARED RULE, THIS WEEK.
  >    (a) The entry's confirmation window says "cohort frozen by fixture id with the intl-elo-v2 machinery
  >        (unscoreable-only substitution)", and that rule (ARCHITECT 2026-10-02) releases a cancelled or
  >        abandoned fixture. 223 item 2(a)'s "no release, no substitution class" refused a NEW class, one
  >        made to get a fenced fixture out of the way. It did not strike the rule the cohort was frozen
  >        under. An abandoned game is that rule's own case.
  >    (b) AS BUILT IS THE RULE. I read substitutions_due on main 93ff8119: "last" is the latest (kickoff,
  >        id) among the cohort's ids as stored at the run, and the replacement is the first eligible
  >        fixture later than it, never in the cohort, not unscoreable. On today's copy that passes over
  >        16263, which kicks off before 16257, and names 16267. I do not re-read "the 61st" against the
  >        order of the freeze.
  >    (c) THE SUBSTITUTION IS RECORDED BEFORE 16267 KICKS OFF (2026-11-27T20:00Z), so that its replacement
  >        is named while its result is unknown. Not later. I want it run on Wednesday 2026-11-25.
  >    (d) The replacement is fenced like every post-stamp cohort fixture. Nothing reads it before
  >        leagues-pd-v1's verdict. The record's day does not move.
  >
  > 3. WHERE IT RUNS: I AMEND MY OWN 346 ITEM 1, FOR --substitute ONLY, AND SAY WHY.
  >    (a) 346 item 1 refused --freeze-cohort and --substitute on a copy: "they are registry decisions made
  >        on the writer of record's own store, not on a copy". For soccer that store is the host's, and
  >        the host's checkout is a tag that is never written, so as ruled no substitution can be recorded
  >        at all. I wrote that line when none was due and did not see it.
  >    (b) AMENDED: --substitute may run on a copy that is the writer of record's own .backup, pulled and
  >        read the same morning by my block. The pick is mechanical from the stored kickoffs; the
  >        substitution's evidence carries the copy's file name and sha256. A kickoff the provider moves
  >        between that backup and the run is not seen; that is accepted and stated here. --freeze-cohort
  >        stays refused on a copy: nothing needs it.
  >    (c) DEV 2: confirm or correct my reading in 2(b) from the code, on #322, today. That is all I ask
  >        of you here; 452 item 6 is otherwise answered by this item. Your order is unchanged: the
  >        declaration PR, then 447's three.
  >    (d) DEV 1 — YOUR NEXT BUILD, ahead of the laptop routine: --db COPY on soccer-expansion-confirm, the
  >        twin of what you built on intl-elo-confirm (346 item 1): the same fence (check_db, no sidecar,
  >        mode=ro and immutable=1), the copy's path and sha256 printed first, serving the no-flag read,
  >        --record and, by (b), --substitute; the registry writes land in the laptop checkout's
  >        docs/registry as before. With --substitute the pick is printed before anything is written, and
  >        the evidence gains the copy's file name and sha256. Without --db nothing changes, pinned byte
  >        for byte. --freeze-cohort with --db stays refused. intl-elo-confirm is not touched.
  >        The record of 2026-12-22 needs this --db in any case: the command has none today.
  >    (e) It decides a production status, so it is reviewed as money-path (346 item 3). A reviewable head
  >        by Tuesday 2026-11-24 evening; it merges Wednesday morning and my block runs the substitution
  >        that day. The last hour that keeps 2(c) is Friday 2026-11-27 before 20:00Z. If Wednesday
  >        cannot be met, say so on Tuesday; the fallback is mine to rule.
- **As built:**
  - `--db PATH` on `soccer-expansion-confirm`. The fence is `intl-elo-confirm --db`'s, called and not changed: `mlb_pitchers_gate.check_db`, no `-wal`, `-shm` or `-journal` beside the copy (checked before the read and again after it), and the tables the read needs probed through mode=ro&immutable=1.
  - The copy's path and sha256 print first, before any read. The whole read runs on `mlb_pitchers_gate.readonly_session(copy)`, the gate's walk and the production model's NOTE included.
  - `--db` serves the no-flag read, `--record` and `--substitute`. `--freeze-cohort` with `--db` is refused (exit 2, nothing read or written).
  - With `--substitute`, one `PICK` line per release prints before anything is written: the released id, its raw code, the replacement and its kickoff, and the (kickoff, id) it was measured from. The substitution's evidence gains `copy_file` and `copy_sha256`.
  - The registry writes land in this checkout's `docs/registry/` as before.
- **The rule of the pick is the code as built (453 item 2(b)):** `substitutions_due`'s rule is unchanged. Each item it returns also carries `last`, the (kickoff, id) it already computed, so the console can print it. `confirmation_read` and `run_soccer_backtest` take an optional session, as `intl_shadow.confirmation_read` does; None reads the app's database as before.
- **Unchanged:** the command without `--db`, pinned byte for byte (console and registry bytes) against captures taken from origin/main 93ff8119's code on Python 3.12 and 3.10; `intl-elo-confirm`; every refusal; the computation, the cohort, the plan and the bar.
- **Order (453 item 3(e)):** a reviewable head by Tuesday 2026-11-24 evening; it merges Wednesday morning; the architect's block runs the substitution that day, before 16267 kicks off (2026-11-27T20:00Z).
