**2026-10-25 — BUILT AS A PROPOSAL and RULED (addendum 167 item 6) (ARCHITECT addendum 166 item 6(B), applying addendum 126 item 2(d)): the host's fixed-time NFL and PL predict and slate-export steps are retired, and every sync stays on its timer. `sp-nfl-predict` is renamed `sp-nfl-prematch`; `sp-soccer-friday` and `sp-soccer-saturday` run `soccer-prematch` as data only.**
- **RULED (ARCHITECT 2026-10-25 11:00 ET, addendum 167 item 6), verbatim:** "6. THE TIMERS PROPOSAL (claude/166-timers-retirement, 232ae3f) — RULED from the summary; I read the PR body when it opens:"
  - "(1) Names: APPROVED — sp-nfl-prematch.timer / chain nfl-prematch (Thu 18:00Z, Sun 14:00Z: whole-league sync-injuries NFL + capture-weather-nfl); sp-soccer-friday and sp-soccer-saturday keep their names, soccer-prematch data-only. Retired exactly as proposed: predict-nfl + export-nfl-predictions; predict PL + the PL export-predictions window. Nothing MLB."
  - "(2) The coverage hint: APPROVED as proposed; the NO SLATE FILE gap line is the signal."
  - "(3) The window chain's NFL freshen rewriting the slate file in place inside T-90: an Issue (finding, host/ops), not this PR; it joins the hard-link finding already in BACKLOG. The fix is a later small PR: freshen writes the slate's name only through the slate's own keep path, or to its own name — Code proposes in the Issue."
  - "(4) The deadline stands: merged, tagged (v1.6.1, after that morning's compare) and deployed by Thu 10-29 13:00Z."
  - "(5) DEPLOY GATE, binding: this tag is deployed only to a host whose closing watch is enabled (`systemctl is-enabled sp-closing-watch.timer` prints enabled) — my deploy block checks it first and STOPs otherwise. If the cutover takes the 10-30 fallback, the timers tag waits for it; Saturday 10-31's overwrite risk (your item 4) is then the laptop's slate on the laptop, which has no such timer — no exposure."
  - "(6) The lost files: ACCEPTED. After the cutover the slate stage's day-of files are the files; the Friday weekend-round PL file and the Thursday NFL file were the host's rehearsal shapes. The Cockpit's "latest from host" reads whatever the slate writes."
  - "PR order today: #671 → #672 → the timers PR opens in the freed slot; #632 stays a draft."
  - As ruled: the names (N1 / S1) and the retired steps stand as built; the coverage hint stands as built; the freshen finding is #673 (with Code's proposal), not this PR; the deadline is merged, tagged v1.6.1 and deployed by Thu 10-29 13:00Z; the deploy gate is the architect's block (`systemctl is-enabled sp-closing-watch.timer` prints enabled, else STOP), and with the 10-30 fallback this tag waits for the cutover; the lost files are accepted.
- **Item 6(B), verbatim:** "(B) THE TIMERS RETIREMENT PR (ops class, AFTER (A), not a Monday blocker; merged and tagged before Thursday 10-29 13:00Z — Thursday's nfl-predict at 18:00Z and the watch's TNF slate would otherwise both write the same exports/ name, the in-place rewrite BACKLOG already names): addendum 126 item 2(d) rules the host's fixed-time PREDICTION timers retired by the cutover. Law 1 first: enumerate from deploy/hosting/chains.py what each of sp-nfl-predict, sp-soccer-friday and sp-soccer-saturday actually runs, step by step. Retire ONLY the predict + slate-export steps the watch's slate stage duplicates; a weekly ratings refresh, a grade, a results export or a whole-season sync that one of those chains also carries is KEPT (moved to its own unit or left in a renamed chain — propose, do not decide). The PR body lists each unit: each step, kept or retired, and why; the T11 lists; the host config change (the timers.enabled lines) as a TERMINAL (host) step I block out; CI's timers check updated. I rule the list from the PR body before merge."
- **Addendum 126 item 2(d), verbatim (BACKLOG 2026-10-18, the addendum 126 entry, #590):** "(d) Before the cutover the laptop is the machine for every family (its watch runs every minute while it is awake; a laptop asleep at the due time means the first tick after waking — the page says the run was late, with the minutes). After the cutover the host's watch does it for SOCCER and NFL (the fence lifts), and MLB stays the laptop's to the season's last game. The host's fixed-time timers (nfl-predict Sun 14:00Z — AFTER a 9:30 ET London kickoff) are retired by the cutover PR; they are not fixed by hand this week."
- **The in-place rewrite it cites:** BACKLOG 2026-10-18 (the addendum 126 entry), "Open for the architect" item 2, "The hard link". In short: the slate's `exports/<slate file>` and its kept `logs/<run id>.<name>` are one file under two names. Every export writer opens its `--out` in place (`open(path, "w")`). So a later export to the same exports/ name ("a prematch chain such as soccer-prematch's Saturday window file, or a host timer's export before the cutover PR retires it") rewrites the kept logs/ copy too, and the slate receipt's sha256 then matches neither name.
- **The slate stage, enumerated (law 1).**
  - The code: `deploy/hosting/closing.py` `slate_steps` (:2370) is `resolve_steps` (:1506), the closing's own resolution, word for word. SOCCER's export also gains `--start`/`--end` (`soccer_window`, :2349).
  - The chains it resolves: `chains.CHAINS["nfl-closing"]` / `["soccer-closing"]` (chains.py :409/:412), built by `_closing_from_freshen` (:398) from `freshen:NFL` (:323) and `freshen:SOCCER` (:348), with `_CLOSING_ADD` (:384).
  - Resolved for a synthetic 2026-10-31 day:
    - NFL: `sync-matches --competition NFL --season 2026 --date-from D --date-to D --match-ids <day's>` · `sync-injuries --competition NFL --season 2026 --match-ids <day's> --strict` · `sync-odds-football --match-ids <day's>` · `sync-kalshi-nfl` · `predict-nfl` · `export-nfl-predictions --desk --out logs/<run id>.nfl_predictions_<date>.json`, linked into `exports/nfl_predictions_<date>.json`.
    - SOCCER: `sync-matches --competition PL --season 2026/27 --date-from D --date-to D --match-ids <day's>` · `sync-odds --competition PL --season 2026/27 --match-ids <day's>` · `sync-injuries --competition PL --season 2026/27 --match-ids <day's> --strict` · `sync-kalshi-soccer --competition PL` · `predict --sport soccer --competition PL --season 2026/27` · `export-predictions --sport soccer --competition PL --status scheduled --desk --start S --end E --out logs/<run id>.soccer_PL_<date>.json`, linked into `exports/soccer_PL_<S>_to_<E>.json`.
  - It never runs `capture-weather-nfl`, an unscoped `sync-injuries` / `sync-odds` / `sync-matches`, or any expansion-league step.
- **Per unit (a step retires only where the slate stage runs the same command for the same family):**
  - `sp-nfl-predict.timer` (Thu 18:00, Sun 14:00 UTC) → chain `nfl-predict`. It becomes `sp-nfl-prematch.timer` → chain `nfl-prematch`, same calendar lines:

    | step | kept / retired | why |
    |---|---|---|
    | `sync-injuries --competition NFL --season 2026` | KEPT | A sync. The slate's own is scoped (`--match-ids <day's> --strict`), so the whole-league sync is not duplicated. Still step 1 (Exhibit 1 guard). |
    | `capture-weather-nfl` | KEPT | The slate stage never runs it, and no other host chain does. Tracking only: no model reads it. |
    | `predict-nfl` | RETIRED | The slate stage runs `predict-nfl`, word for word. |
    | `export-nfl-predictions` | RETIRED | The slate stage runs it (`--desk --out logs/…`) and links it into `exports/nfl_predictions_<date>.json`. That is the name this export's default writes on Thu 18:00Z and Sun 14:00Z (UTC date = ET date). |
  - `sp-soccer-friday.timer` (Fri 14:00 UTC) and `sp-soccer-saturday.timer` (Sat 10:30 Europe/London) → chain `soccer-prematch`. Both are unchanged; the chain runs data only:

    | step | kept / retired | why |
    |---|---|---|
    | `sync-matches --competition PL --season 2026/27` | KEPT | A whole-season sync (ruled KEPT). The slate's is by date for the day's ids. |
    | `sync-odds --competition PL --season 2026/27` | KEPT | A sync. The slate's is scoped to the day's ids. |
    | `sync-injuries --competition PL --season 2026/27` | KEPT | A sync. The slate's is scoped (`--strict`). |
    | `sync-matches` + `sync-odds` for PD, SA, BL1, FL1, ELC (10 steps) | KEPT | Whole-season data syncs of the expansion leagues. The slate stage never runs them. |
    | `sync-kalshi-soccer --competition` PD, SA, BL1, FL1, ELC (5 steps) | KEPT | Capture only. The slate stage never runs them. |
    | `sync-kalshi-soccer` (PL by default) | KEPT | The slate runs the same command (`--competition PL`), but it is a sync, and the ruling retires only predict and export. |
    | `predict --sport soccer --competition PL --season 2026/27` | RETIRED | The slate stage runs it, word for word. |
    | `export-predictions --sport soccer --competition PL --start {sat} --end {sat_plus3} --status scheduled` | RETIRED | The slate stage runs the same export (`--desk`, its own window, `--out logs/…`). It links the result into `exports/soccer_PL_<sat>_to_<sat_plus3>.json`, which is this export's own name on a Saturday (`soccer_window` = `sp_run.date_vars`). |
  - None of the three chains carries a weekly ratings refresh, a grade or a results export.
- **Alternatives considered.** Built: N1 and S1. Each one is listed in the PR body.
  - NFL:
    - N1 (built): rename the chain and the timer (`nfl-prematch` / `sp-nfl-prematch.timer`).
    - N2: keep the timer's name and point it at the renamed chain.
    - N3: keep the chain's name and drop its two steps.
    - N4: move the two kept steps into `nfl-lines`, which runs daily.
    - N5: retire the whole timer (refused: it drops the weather capture and the whole-league injury sync).
    - N6: keep `nfl-predict` as a by-hand chain (refused: a by-hand export is an in-place writer of the slate name).
  - SOCCER:
    - S1 (built): keep the `soccer-prematch` name and both timers.
    - S2: rename the chain `soccer-prematch-data` and re-point both timers.
    - S3: fold the syncs into the hourly window chain.
    - S4: retire both timers (refused: it drops the expansion data, the capture-only Kalshi and the PL whole-season sync).
- **The T11 lists:** `TIMERS` swaps `sp-nfl-predict.timer` for `sp-nfl-prematch.timer`, and nothing else moves (16 / 3 / 1). The Schedule table's three rows are rewritten, and the London-Sundays note and the H0-10 midweek line now say what runs. The T11 test (`test_the_t11_lists_the_shipped_timers_and_the_schedule_table_agree`) passes unchanged. New tests pin the calendars, the kept steps, the retired steps against `closing.slate_steps`, the shared file names, and that no timer's chain predicts or exports NFL or PL.
- **For the architect:**
  1. The rename, the soccer name, and the host block (TERMINAL, in the PR body).
  2. The coverage hint. `coverage`'s gap hint derives from chains.py (`writer_chains`). It now finds no writer chain for NFL or PL, so "— nfl-predict has not run" / "— soccer-prematch has not run" no longer print. The NO SLATE FILE gap line still does, and the Today tile's "writer chains" reads none. The spec's example ("PL: 4 GAMES, 0 PREDICTION ROWS — soccer-prematch has not run") no longer reproduces. The other way is a hint that names the slate run (a coverage text change).
  3. The window's freshens. `freshen:NFL`'s `export-nfl-predictions` (no `--out`) writes `exports/nfl_predictions_<UTC date>.json` in place, inside T-90, on the host after the flip. That is the same in-place rewrite, outside this ruling's scope; ruled to #673 by addendum 167 item 6(3) (fixed-time timers). `freshen:SOCCER`'s dateless export writes `soccer_PL_<today>.json`, which is not the window name.
  4. Order on the host after the flip:
     - Sat 10-31: `sp-soccer-saturday` fires at 10:30Z (GMT). With a 12:30 UK kickoff, the PL slate is due 06:00 EDT = 10:00Z, so before this PR the chain's export would rewrite the slate's file in place, with no `--desk`.
     - Thu 10-29: `nfl-predict` at 18:00Z runs before a 20:15 ET TNF slate (due 21:45Z), and the slate's rename replaces its file.
     - A London Sunday's slate is due 07:00 ET, before the 14:00Z run.
  5. The deploy order. The tag that carries this changes what the host predicts. Deployed before the host's closing watch is enabled (the flip, h2-cutover-runbook section 1 step 5b), it leaves the host with no NFL or PL prediction file until the watch runs.
  6. Stale docstrings. closing.py's `soccer_window` / `slate_file` docstrings still describe the prematch export. They are left as they were, to keep closing.py out of this diff.
