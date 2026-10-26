# Changelog

Human-readable record of what shipped, newest first. Deep detail and the
reasoning behind each change live in `BACKLOG.md`; this file is the summary.
Every drop adds an entry going forward.

## 2026-10-25 (#672: 166-records — ARCHITECT addendum 166 item 6(D), its 08:20 ET correction and its 08:25 ET postscript: records only)
- `.github/ledger/taxonomy.json`: the "Cutover ~Oct 8" milestone's description carries addendum 166 item 4's ruling (the conditional GO for Monday 2026-10-26, and the fallback Friday 2026-10-30). The title and `due_on` (2026-10-30) are unchanged.
- The day's ledger entry records Saturday's records, with the SOCCER exec cohorts as the 08:20 correction states them; T9 closed by the 2026-10-25 06:00Z weekly-fullseason run (limitation #586); the 2026-10-25 compare; and Saturday's PL grade.
- The ledger entry also carries addendum 167 item 3 (the Monday order, corrected; ARCHITECT 2026-10-25 11:00 ET), verbatim, as addendum 167 item 5 asks.

## 2026-10-25 (#671: 166-cutover-fence-off — ARCHITECT addendum 166 item 6(A): the cutover policy PR, the host fence switch off)
- src/walters/desk_policy.py: `HOST_FENCE_RULE = {"on": False}`, and the fence comment paragraph above it says the fence is lifted by this PR (2026-10-25, addendum 166 items 4(ii) and 6(A)): a machine's role no longer changes a soccer (or INTL) call. Nothing else in the module changed; host_fenced, machine_role, the reasons, host_fence_rule_off and base_v11 read the switch as before.
- Tests: the tests that asserted the fence under role host, unset or an odd value at the default now assert the lift (every soccer and INTL model row is the laptop's call, desk_meta host_fence_rule false); test_the_switch_the_cutover_pr_turns_off_is_the_one_the_fence_reads stays, showing the switch set on fences and the module's default (off) does not; the tests of the fence's mechanism turn the switch on inside the test. The frozen golden is untouched.
- docs/specs/h2-cutover-runbook.md: the 2026-10 schedule table gains addendum 166 item 4 (the conditional GO for Monday 10-26, its five conditions, the Friday 10-30 fallback) and item 5 (the Monday timetable), verbatim; the fence-check bullet reads "the tag carries #671".
- Fix round (ARCHITECT addendum 167 items 1, 2 and 4, on Codex's three findings): the table's addendum 166 item 5 rows are REPLACED by addendum 167 item 3's (the Monday order, corrected: the preflight with the timers active, then `pause`, then the deploy, then `install`), verbatim; item 4 (4)'s row is marked corrected; section 3 opens with item 2(b)'s rule (a host whose database is the old one runs a fence-on tag) and its redeploy line comes before the `systemctl start`; the "Host on a release tag" bullet says the tag is deployed between `pause` and `install`; section 1 step 2 says `pause` is step 2 on cutover day, and step 4's block names the deploy.
- Addendum 167 postscript: section 3's "Refused at install" says no same-day retry after `pause` (postscript (c)); the item 4 (4) row quotes postscript (a), condition (4) read as corrected by item 3.
- The finding it resolves: #670 (the architect's own, dated 2026-10-25). No timer, unit, chain or export change; nothing in sp_cutover.py. No bar moves.

## 2026-10-24 (#669: 164-window-capture — ARCHITECT addendum 164 item 2(a); the expansion leagues' Kalshi capture joins the hourly window chain)
- `deploy/hosting/chains.py` `WINDOW_KALSHI_CAPTURE_ONLY`: built from `KALSHI_CAPTURE_ONLY` (PD, SA, BL1, FL1, ELC), one `sync-kalshi-soccer --competition <code>` per league, so one series per call (KXLALIGAGAME, KXSERIEAGAME, KXBUNDESLIGAGAME, KXLIGUE1GAME, KXEFLCHAMPIONSHIPGAME, all mapped in the adapter's `SOCCER_GAME_SERIES`: no `--series`). A table of its own: `WINDOW_KALSHI` is unchanged and still excludes them.
- `deploy/hosting/sp_run.py` `window_plan`: after the `WINDOW_KALSHI` syncs and before the injury syncs and `window-card`, each league with its next kickoff in the window near or imminent (at most `PROX_FAR_H`, 6 h) gets its capture step, tiered as every window Kalshi sync is. A far league keeps its schedule check only; the flat plan carries the step, so the receipt's `steps_skipped_by_proximity` counts it. No export, no call, no new card or venue line: window-card reads the DB, never chains.py, and `desk_policy.SHADOW_VENUE_COMPS` still refuses a venue call on these leagues.
- docs/specs/hosting-h1.md: the Schedule table's `sp-window` row and the window service's step 2 name the capture-only step. docs/CLI.md (`sync-kalshi-soccer`) and the adapter's comment say the same.
- tests/test_hosting_pack.py: the table is `KALSHI_CAPTURE_ONLY`, one step per code, each code mapped, with no overlap with `WINDOW_KALSHI` and nothing on the card's path reading it. A seeded window (SA near, FL1 imminent, BL1 far, PD outside the window, ELC finished) plans SA's and FL1's capture only, and only those two steps differ from the plan without the table. A window with no expansion game adds none. Every planned command and option is checked against cli.py.
- On the host it goes live with the next tag's deploy. The window chain reads chains.py on every hourly run, so the first window tick after the deploy carries it. Item 2(c), the receipt's weekday re-read, is not in this PR.
- ARCHITECT 2026-10-24, addendum 165 items 1 and 4, verbatim: "1. The pager (your point 1) — RULED: no page on the five capture-only leagues. The URGENT 6pp-in-3h page exists so the operator looks at a quote the Desk can act on. PD, SA, BL1, FL1 and ELC are capture-only until a PASS and its confirmation: no export, no call, nothing to act on. A page the operator cannot act on is noise, and noise is what teaches someone to ignore the page that matters. So: the pager reads the live list (WINDOW_KALSHI) only, never the new table. Keep the move itself: write it to the window's log as one line (series, ticker, from, to, minutes to kickoff) so the capture-quality receipt of 164 item 4(b) can count large late moves per league. A logged move is a receipt; a paged one is a false alarm. Test: a 6pp move on a captured ELC quote produces the log line and no page; the same move on a PL quote still pages." "4. One check before the PR opens. 'One series per call' is right for pacing; confirm in the PR body that the five sync-kalshi-soccer steps are AFTER the live Kalshi steps in the chain, so a 429 on a shadow league never delays a live capture. If the order is the other way round, move them; a unit test that asserts the order is enough."
  - Item 1, `deploy/hosting/sp_window_page.py`:
    - `CAPTURE_ONLY` is chains' `WINDOW_KALSHI_CAPTURE_ONLY` less `WINDOW_KALSHI`.
    - A `line_move` delta on such a league is taken out before paging. It is never sent, never URGENT, never a `freshen_needed` entry, and is not counted in `deltas.line_move`.
    - `run()` prints one line per such move to the window's log (stdout; sp_run calls `run()` in-process as the window chain's post): `· capture-only line move (addendum 165 item 1): <competition> <series> <ticker> <from>-><to> (<move>pp) · <minutes> min to kickoff · venue <kalshi|book>`. It reads the Kalshi venue when that venue alarmed, else the book venue, with series and ticker `-`. Minutes are counted from the `to` capture.
    - The receipt carries `capture_only_moves` {count, lines}.
    - Every other class, and every competition in `WINDOW_KALSHI` or in neither table, pages as before.
  - `src/walters/line_move.py`: the Kalshi venue gains `to_ticker`, additive. It is the HOME leg's `odds_snapshots.market_ticker` at the `to` capture, read by row id through `paper.capture_tickers`, null where none is stored. It is written only on the window card (`line_move_for_match(..., with_ticker=True)` from `window.build_card`); the fixtures and NFL exports call it without, so their rows are unchanged. The series in the log line is that ticker up to its first `-`.
  - Item 4: the capture-only steps follow every `WINDOW_KALSHI` step in the planned window, whatever the kickoffs. This was already the plan's order, now pinned by `test_window_capture_only_kalshi_steps_come_after_every_live_kalshi_step`.

## 2026-10-24 (#667: 163-floor-pl-probe — ARCHITECT addendum 163 items 3 and 4, with addendum 163 recorded)
- docs/CLI.md, the closing-watch row: the slate floor named in one line (item 3). With the 06:00 ET floor, a kickoff before 08:30 ET gets its slate less than 150 minutes ahead (a 07:30 ET PL kickoff prints "due 06:00 ET", T-90). That is the floor, not a miss, and the closing stays at T-35. No behaviour change.
- scripts/lineup_timing_probe.py: PL is in the `--competition` choice list (item 4), read under the stored code 'PL' like every other choice. tests/test_lineup_timing_probe.py: a PL plan reads only the PL row; the refusal test now names BL1.

## 2026-10-24 (#666: 164-leagues-read — ARCHITECT addendum 164: records only)
- docs/roadmap.json, leagues lane:
  - the receipt step is done (#663, b83b041; the laptop console on #322);
  - step (c) is appended as a calendar step due 2026-12-06, ELC's 60th 2026/27 fixture on or after the 2026-11-06 declaration, with SA 2026-12-20, BL1 2027-01-09 and FL1 2027-01-16 named.
- docs/roadmap.json, cups lane: Step B is done (#662, 962c92d).
- No date moves and no bar moves. The ledger entry carries the addendum verbatim and the BL1 parity line: the harness's 40-prior rule, and BL1 holds 37 finished games.

## 2026-10-24 (#665: 162-pl-positive-edge — ARCHITECT addendum 162 item 2(a) and addendum 163 item 1: the PL positive-edge receipt for #92, with the n=30 read's table and the injury split for the n=60 read)
- `scripts/pl_positive_edge_receipt.py`, new, read-only and files only (it never opens the database). It reads the PL results exports (`exports/soccer_PL_results_*.json`) and the closing files (`exports/closing_*.json`, through `redated.closing_rows`), so the read reproduces on either machine.
- The cohort is every graded PL row whose top pick's model p is at least +5pp over the book close's fair p for the same side (`graded.close_fair`; #615's ruling). Stale stamps are counted and printed. `--min-gap-pp` defaults to 5, the ruled line, and is printed; it is not a knob.
- Per member: match id, date, teams, pick, model p, close fair and the gap; the prediction stamp; the close stamp and its ages; injury counts on both sides and the one-sided guard's state; result and score; and the Desk's final call (PLAY, LADDER, PASS or no closing row) with its closing run start. The final call is exec_cohorts' selection: the newest run's row within the Desk clock drift.
- Left out, counted and named: re-dated rows (the export's label, or void by the closing files on disk), ungraded rows, rows with no top pick, unpriced closes, and a close that is not the book close. A match held by several results files is read once, from the newest file, and each dropped copy is printed. The summary gives counts only and no verdict.
- Addendum 163 item 1: the same run prints the n=30 read's table, for the cohort and for the mirror set (gap <= -5pp). Each gives n, hits and hit rate; the close-implied rate (the mean close fair for the pick) with a 95% half-width of 1.96 x sqrt(sum p(1-p)) / n; and the model's mean probability. It also prints the hypothetical return per unit at the close's fair price (a hit 1/p - 1, a miss -1), with an approximate 95% interval of 1.96 x sd / sqrt(n), before spread and fee.
- Also printed: the 10-24 read's cells (gap >= +12pp; the draw picks), named constants and not knobs; the injury split by the one-sided guard's state and by injury presence; and the pre-registration line ("next read pre-registered at n=60 ... read once") with the cohort's n against 60. No verdict.
- tests/test_pl_positive_edge_receipt.py (18 tests). docs/CLI.md gains the script's row.

## 2026-10-23 (#663: 155-leagues-receipt — ARCHITECT addendum 155 item 4(a) and addendum 156 item 1; a read-only receipt)
- scripts/leagues_close_receipt.py and `paper.leagues_season`. Per league (SA, BL1, FL1, ELC), for the 2026/27 games:
  - FINISHED games are scored against addendum 150's three-way Kalshi close exactly as the close record scores a three-way competition: n with a close and the close's log-loss, the bar's denominator.
  - Games still to come are read for the capture they hold now.
  - The projection is the kickoff UTC date of the 60th stored fixture on or after 2026-11-06. The earliest of the four is step (c)'s date.
- `paper._kalshi_snaps` and `paper._three_way_guards`: extracted unchanged from `close_record` (the rows the close reads and the mismatched-capture guard's inputs), so the receipt and the record read the same rows the same way.
- Addendum 158 item 2(a): `src/walters/leagues_candidate.py`. `predict_as_of` is the leagues' prospective path, BEING the expansion gate's walk: a cold start over the league-season's finished regular-round games before the kickoff, same-kickoff games kept apart, the production rho and Elo coefficient, nothing fitted. The receipt's parity lines set it against `run_soccer_backtest` as the gate calls it, row for row. Every row carries the candidate id, the code sha, the input cutoff and the prediction stamp.
- Finding: the current shadow export (`soccer_expansion.price_upcoming`) is not that walk. It reads every stage, batches nothing, and takes its strengths from all finished games. The receipt reports its divergence on the same games; it is unchanged here.
- Addendum 158 item 2(b): capture quality per league and kickoff UTC weekday (`paper._quality`, `paper.quality_lines`). It gives the qualifying share, the counts by cause, the controlling capture's age and provenance, and the superseded cases.
- Codex round 1 on #663:
  - The parity read refuses (`ExpansionRefused`) when the league-season stores a stage label `soccer_expansion.placement` cannot place, NULL and empty included, read by the gate's own `stage_census`: the gate's run refuses on such a label (F3), so parity never reads as a clean pass over games both paths left out.
  - The script exits 2 with a REFUSED line when no production soccer model resolves, or when a league's parity read refuses, as cli.py's soccer-expansion commands refuse. The close part still prints.
  - Games to come: SCHEDULED games kicking off after the receipt's clock. Their captures are read as of that clock, behind the finished score's own mismatched-legs guard (`paper._guarded_three_way`, now shared by `_score_three`, unchanged in effect), with mismatched legs as their own cause. LIVE games and SCHEDULED games past their kickoff are counted apart, never in the cohort.
  - An older capture whose legs name two events is never counted as a superseded case.
  - The ledger entry says plainly that step (c) is not yet in docs/roadmap.json: it is appended in this PR from the laptop console's date.
- Codex round 2 on #663: a league whose parity read is not equal (a row unequal beyond the tolerance, or a game priced by the shadow path or the gate only) prints a NOT EQUAL line and the script exits 1; a refusal's 2 outranks it. A divergence never reads as a 0.

## 2026-10-23 (#662: 158-cups-step-b — ARCHITECT addendum 158 item 3(a); cups Step B, due 10-29)
- `observe-cup-lineups` (src/ingestion/cup_lineups_live.py) and the new table `cup_lineup_observations` (migrate_cup_lineup_observations.py: table plus marker, additive; the ingest writes only after it).
- The LIVE T-15 observation store. For the stored CL, UEL, EFL and FAC fixtures kicking off within 3 hours, each due poll is asked once and appended: T-15 (the label poll), then T-5 and T+10 (later reads that catch a correction).
- Each row holds the scheduled and observed time and the team-mapped elevens and bench, with status complete, partial, empty, failed or missed; a call more than 5 minutes late is flagged late. The first complete observation is marked and preserved, and a later complete row records whether its elevens differ from the first.
- Rows are keyed by fixture, stored kickoff and poll. A fixture that a schedule sync re-dates starts a fresh poll set with its own first complete row; the old kickoff's rows stay as they were.
- Safety (Codex review): a missing DB file is refused and never created, and `--dry-run` reads through the read-only session. A real tick holds the chains' DB lock across the due-check, the provider calls and the inserts, and an insert that meets the unique key is counted as already observed instead of crashing. The adapter is built before any row is written, so a missing API key refuses with nothing written.
- Append-only: nothing updates or deletes a row. It writes no `lineups` row and no candidate input or forecast, so the T-35 inputs stay apart from the T-15 label.

## 2026-10-23 (#660: 157-nhl-receipts — ARCHITECT addendum 157 item 2(a) and (b); read-only scripts, no model)
- scripts/nhl_gsax_feasibility.py: the GSAx feasibility receipt. Per season 2023-24..2025-26 and game type it prints:
  - the stored shot events by type, with and without a goalie_id;
  - the exclusions in the frozen xG rules' order, then the events kept but naming no goalie;
  - the one event set's shots faced, goals against and xG faced (v7's frozen fit), so the numerator and the denominator come from the same events;
  - the join of each event to the stored starters, and a boxscore cross-check per goalie-game;
  - per-goalie exposure for the regular season.
- scripts/nhl_starter_timing_probe.py: the starter timing probe, which reports the distribution (item 7). It polls the API's boxscore, landing and right-rail pages per game at T-120, T-90, T-60, T-45, T-35 (the cutoff), T-30, T-15 and puck drop, stamped by our clock. Per poll and side it records what each endpoint asserted and whether the side's identity is unique, conflicting or missing. It prints the share of games usable at the T-35 cutoff and the missing, conflicting, withdrawn and changed counts before puck drop. A T+20 read of the eventual starter checks reliability only. `--stored` counts the stored appearance rows captured before their game's start.
- Both open the DB read-only and never create one; neither writes a row. docs/CLI.md lists both.

## 2026-10-23 (#659: 162-pitcher-season — ARCHITECT addendum 162 item 1(b): the MLB pitcher lookup reads the game's season; Closes #658)
- src/walters/training.py `_generate_predictions_mlb`: the starter's PitcherSeasonStats row is keyed by (player_source_id, season) and read for the game's own season (Match.season as stored). Before, it was keyed by the source id alone, so the last row yielded won, and which row came last was the query planner's choice. A pitcher with no row for the game's season is "no stats" and takes the existing missing-starter shrink, never another season's row.
- src/walters/export.py `_collect_rows`: the `pitchers` block of an MLB row reads the same row (the game's season, with the model's own filter: era set, innings above 0), so the file shows the stats the model used and none where it had none.
- scripts/mlb_pitcher_season_receipt.py (read-only, stdlib only): rows per season, pitchers with more than one season, a day's starters and their rows (addendum 162 item 1(a)). Per postseason prediction side, what the old read took (read from the starter detail the prediction stored) against the new read, counted, with the games whose row changes named (item 1(b)'s receipt). A side it cannot place is undetermined, with its reason, and never inferred: the stored starter is not the one listed now, the detail equals no row now, or it equals rows of two seasons. A starter listed without a source id has its own count.
- tests/test_mlb_pitcher_season.py: the live lookup and the export read the game's season row; no row for it is no stats and the shrink; the receipt's classification. Two of the four tests fail on main's code.

## 2026-10-23 (#657: 158-declared-lanes — ARCHITECT addendum 158 items 1(a), 2, 3(a) and 4; with 159 and 160 item 1: records, and the ruled home-abroad list in desk_policy)
- docs/roadmap.json, lane ncaa: a step, the 2023 ingest with the week field and its census by --preflight read by the architect (code, due 2026-11-01).
- docs/roadmap.json, lane leagues:
  - The receipt step (code, 10-30) names the parity receipt and the capture quality it carries.
  - The declaration step (architect, 11-06) names the per-league timing: no earlier than 10-30 and no later than 11-06, each window counted from its own declaration.
  - live_needs names the confirmation criterion: 60 more qualifying games at the same bar, independently per league.
- docs/roadmap.json, lane cups: Step B (code, 10-29) reads as the LIVE T-15 observation store. The history ingest it named is done (#538, #541).
- Issues #655 and #656: the domestic successor lanes (restrained calibration by league; opponent-adjusted attack and defence), no date.
- Every roadmap edit is made in place, and no date moves.
- ARCHITECT addendum 159 (the shadow lanes) recorded. docs/specs/h2-cutover-runbook.md section 1 step 5 gains the UNL cohort post-check (item 1): the host's `intl-elo-confirm` read must name the same 60 cohort ids and the same labelled count as the laptop's, and a difference blocks the UNL record step.
- ARCHITECT addendum 160 item 1: `desk_policy.INTL_HOME_ABROAD` is the ruled list, Ukraine, Belarus and Israel, with the ruling quoted beside it. The semantics are unchanged: an unknown venue with a listed home side is never a call. Items 2 and 3 are recorded; item 2's venue-country override is its own PR.

## 2026-10-23 (#654: 157-nhl-nine-prep — ARCHITECT addendum 157 items 3, 4 and 5; records only, no code)
- docs/roadmap.json, nhl lane: live_needs reads the frozen bar's rule as src/walters/nhl_backtest.py writes it. That is the test log-loss at or under the home-rate baseline's minus 0.010 (LL_MARGIN), plus the calibration bands and the ratings range. Its number is read from the 600-game cohort at the run. 0.6866 is named as the rule's value on the retired 2025 cohort. The cohort is regular-season games only (the NHL API's game type 2), with the ids and counts listed in the run's receipt. A non-Elo candidate declares its own stability guards. One line, edited in place; no date moves.
- docs/roadmap.json, nhl lane: a first step, candidate nine's two receipts (code, due 2026-10-28, item 2), before the 2026-10-30 declaration it conditions.
- docs/roadmap.json, nfl-qb lane: the probe run's step is done 2026-10-23 (item 10). Its receipt is #427 comment 6367734110; the console stays in the laptop's logs.
- BACKLOG: a market-anchored NHL model is DECLINED (item 4; the doctrine stands). It may exist later only as a read-only residual diagnostic, never a Desk candidate.
- #653 opened: NHL candidate ten, a strength-specific goal model, as a later lane after nine's declaration, with no date yet (item 5).
- Items 1, 2 and 6 recorded. The receipts of item 2 ((a) GSAx feasibility, (b) the starter-timing probe) are their own PR, due 2026-10-28.

## 2026-10-23 (#652: 156-milestone-timers — ARCHITECT addendum 154 item 3 and addendum 155 item 8(b), as one small PR by addendum 156 item 4)
- The roadmap print's milestones: a milestone may carry `done` (null or {date, receipt}, a step's shape). A done milestone prints `<title> · <due_on> · done <date>` and is never counted overdue. Its due_on stays as written, so no date moves.
- .github/ledger/taxonomy.json: the milestone "Executable-edge ruling (2 wks of ladders)" is done 2026-10-20, receipt addendum 146 item 1 (the K-track ruled BINDING). docs/LEDGER.md's milestone table says so.
- A CI check (tests/test_hosting_pack.py): every shipped `deploy/hosting/systemd/*.timer` is on exactly one T11 list, every T11 name is shipped, and hosting-h1.md's Schedule table has one row per shipped timer and none other. The table gained its four missing rows (sp-intl-daily, sp-mlb-history, sp-window, sp-closing-watch).
- sp_deploy's receipt: `timers_not_enabled` and `timers_not_enabled_by_list` hold the shipped timers that /etc/sports-predictor/timers.enabled does not list (names only), with one console line. A TIMERS timer that is missing reads "!", and so does an unreadable file (no list). The timers T11 holds off (MLB_LAPTOP_ONLY, HELD_FOR_CUTOVER) print on a plain line.
- sp_common.t11_lists / shipped_timers: one reader of T11's three lists. sp_cutover.runbook_timers reads through it, with unchanged output.

## 2026-10-23 (#651: 155-day5-records — ARCHITECT addendum 155 items 3, 4, 8 and 9; records only, no code)
- docs/RELEASES.md, the v1.5.0 note: Day 5 ruled PASS (item 9). DIVERGENT on 5 files, none a code-version skew; v1.5.0 CONFIRMED as production, the host stays on the tag.
- docs/roadmap.json, cups lane: Step A, UEL, done 2026-10-22, receipt #106 comment 6365057980 (item 3: Step A closed). The EFL step's date stands.
- docs/roadmap.json, leagues lane (#322): the architect's 2026-10-23 step is done (item 4), and two steps are appended. The lane stays "to declare", and no date moves.
  - (a) The read-only receipt per league, due 2026-10-30 (code).
  - (b) The candidate declared per league, due 2026-11-06 (architect).
  - live_needs carries (c), the read at each league's 60th game and then a confirmation of 60 more. It has no date to enter: a step's due must be a real date, and (c)'s accrues.
- The host finding of item 8 (`sp-ncaa-schedule.timer` never installed on the host) is recorded in BACKLOG and on #647. Item 8(b), the timers CI check, is its own PR.

## 2026-10-22 (#650: 569-sync-cause — ARCHITECT addendum 153 item 2, #569's cause lane; the dedupe is its own PR after this one)
- **#569 RULED (the cause), verbatim:** "The statsapi upsert looks a gamePk up across the sport's rows, not the competition's, and a run holds the DB lock the host's chains hold (the laptop's syncs today take none)."
- src/ingestion/service.py: `SPORT_WIDE_SOURCES = {"mlb_stats_api"}`. sync_matches' prefetch reads the sport's rows for a statsapi sync, so a gamePk stored on any MLB row is updated, never created again. Every other source's lookup stays the competition's own; the re-key index (api_american_football) is unchanged.
  - Receipt: one gamePk (849818) stored on a second MLB competition's row; main's sync creates a second row (`created=1`, rows 50546 and 50547); with the change it updates 50546 (`created=0 updated=1`).
- cli.py: `sync-teams` and `sync-matches` run under `sp_common.db_lock`, the chains' flock, when run by hand, printing one line while they wait. Run as a step of a run that holds it, they take none.
  - deploy/hosting/sp_common.py: `db_lock` sets `SP_DB_LOCK_HELD` = `<pid>:<lock file>` in os.environ while held (restored after; every step runner inherits os.environ), takes an optional `on_wait` callback, and lets one thread of a process at a time take it. `lock_held_by_caller()` is true for the holding thread, or when the marker names another pid (an ancestor's run). `sync_lock()` takes `db_lock` unless the caller already holds it.
  - src/ingestion/service.py: `sync_teams` and `sync_matches` take `sync_lock` around the prefetch and every write (the provider fetch runs before it), so the admin UI's sync jobs (`src/web/routes/admin.py`, each in its own thread) hold it too (Codex P1 on #650).
- tests/conftest.py: the suite's `SP_LOCK` is always under its throwaway dir (set, not setdefault: an `SP_LOCK` exported by the launching shell is never used; Codex P2 on #650), and an inherited lock marker is cleared.
- docs/CLI.md: the sync-teams and sync-matches rows.

## 2026-10-22 (#649: 641-paper-mismatch — ARCHITECT addendum 152 item 4(a), #641 items 1 and 2; read-only report code)
- **#641 item 2 RULED** ("the three-way PAPER check judges as the two-way one does — the newest legs are passed into capture_mismatched, so a capture whose event no game's current legs carry is mismatched, not priced"): `paper.capture_mismatched` takes `current` (each side's newest legs, `kalshi_legs.current_tickers`) and judges it together with the capture read; `close_record`'s three-way branch reads the newest legs and `homes_of` over both sets of events.
  - The case it changes: a CL game whose last 1X2 capture is all of one event that no game's current legs carry, while its newest legs are all of another. It was priced (`{'n': 1, 'mismatched': 0}`); it is now "mismatched legs".
- **#641 item 1 APPROVED** ("judge the rows a PAPER mid reads with close_row_mismatched; a hit prints "mismatched legs ... no mid""): coverage's PAPER line judges the row(s) its mid reads with each side's newest legs before showing it.
  - Two-way: `paper.kalshi_close_read`'s HOME row(s). Three-way: `paper.leg_mids_read` (new), each leg's newest two-sided row and its ties.
  - `read_paper` reads each row's id and market_ticker (only with the legs guard on and the ticker column present), each game's newest legs and `homes_of`.
  - Codex's round-2 shape on #640 (501's older two-sided HOME quote of 502's event) now prints `Kalshi: mismatched legs (<events>): no mid (addendum 37 item 3)` instead of 502's contract.
- `paper.close_row_mismatched` judges each read row on its own selection (the HOME rows of the two-way close as before).
- Tests: the item 2 case on close_record and on `capture_mismatched` alone; coverage's two-way (Codex's shape) and three-way cases, and the same rows on one event shown as before. The read-only test's PRAGMA check allows the second read-only `PRAGMA table_info(odds_snapshots)` (read_paper's own ticker check).
- docs/CLI.md: the coverage PAPER line's and results-tally's mismatched-legs rules.

## 2026-10-22 (#648: v150-release-record — ARCHITECT addendum 154 item 1, docs/RELEASES.md step 4; records only, no code)
- docs/RELEASES.md, the release record: the `v1.5.0` row (cut 2026-10-22 13:24:24Z by the operator, commit `d15b9981edfa74379dd01089f7de23db51353d45`, tag object `358777b00f6d39de1a92f97052f3756d9b89e5c1`, release Issue #647) and its note: the compare (day 4 of 5, ruled PASS), the tag message (`--cleanup=verbatim`, all 43 headings kept), the host deploy (13:40:09Z, both new migrations after a backup) and day 5 to come.
- #647 (labels release, track:H, class:lane, sport:all, size:S; milestone v1.5.0, created for it) carries the notes in four parts and addendum 154 item 1 (a)-(d) verbatim.
- docs/RELEASES.md step 5 (ARCHITECT 2026-10-22, addendum 154 item 2, a doc nit riding this PR): the deploy is two numbered calls, (1) `sp_deploy.py [--tag vX.Y.Z]` and (2) the migration command the deploy prints, verbatim, with `--dry-run` as the recommended first call. `--run-migrations` is never passed to the deploy call: it runs only the migrations and validates their names against the current checkout (v1.5.0's first attempt was refused so, nothing changed). No code change.
- docs/specs/hosting-h1.md, the host runbook's "Deploying a release" line: run the migration command the deploy prints (one lock across the backup and every migration), not `systemctl start sp-backup.service` then each migration by hand (Codex on #648). The migrations' own docstrings are left as they are: an edited migration reads MODIFIED to the deploy's guard (#524).

## 2026-10-21 (#644: v150-records — ARCHITECT addendum 149 items 1-5; records only, no code)
- docs/roadmap.json: the cups lane's step 4 (Step A, CL, due 2026-10-20) is done 2026-10-20, receipt #106 comment 6299554002 (ARCHITECT 2026-10-20 15:28 ET, addendum 149 item 1: "roadmap: the step is done 2026-10-20"). No date moves; the next step is UEL Step A (2026-10-22).
- The ledger entry (docs/ledger/entries/2026-10-21-v150-records.md) records addendum 149 items 1-5 verbatim: the CL Step A rulings (a)-(d); the anchors ruled and placed on the laptop (held rows 34 -> 0; the five scalar E0s refused; the four twin E0s waiting on #569); the findings filed as #636, #637 and #638, with 3(b) on #569; Code's PR order; the 10-20 receipts; and where the 2026-10-21 morning block's retire receipts go (#568 and #631 comments, addendum 152 item 4(c)).
- Labels: the ad-hoc `track:K2` label was removed from #630 and #635 (#630 carries `track:K`); the empty label is the operator's to delete.
- The v1.5.0 compile follows as its own PR: CI admits a compile only as a pure fold (scripts/ledger_fragments.py `check_pr`).

## 2026-10-21 (#643: paper-rulings-151 — ARCHITECT addendum 151 items 1-2; #640's readings ruled)
- src/walters/paper.py: the three-way PAPER close as R42 RULED (b) (addendum 151 item 1, "a later capture holding any of the game's legs ENDs the search, and no older capture is substituted"): `_last_capture` (was `_last_full`) is the last capture before kickoff holding any leg; a close forms only when it holds all three two-sided within the 2c cap. The unpriced line counts by the ruled causes: `last capture incomplete` (new), `last capture over the cap`, `no capture`, and R43's fourth cause only when it counts.
- src/walters/exec_cohorts.py: the n=30 counter starts at the pre-registration (R41 RULED, addendum 151 item 2): 2026-10-19 07:40 ET (`PRE_REGISTERED`; was the rule's date, 2026-10-18 00:00 ET); earlier graded rows print beside it as `before pre-registration, not counted`.
- docs/CLI.md (results-tally row), tests (three-way close, exec cohorts, the section text). R12's git_sha lane opened as #642. Suite: 3293 passed, 4 skipped.

## 2026-10-20 (#640: paper-lane-ktrack — ARCHITECT addendum 146 items 1(v), 1(vi), 5; addendum 148 item 5; addendum 150, closes #639)
- The rulings, verbatim (ARCHITECT 2026-10-20 09:59 ET, addendum 146): 1(v) "(v) results-tally gains an "exec cohorts" block per closing family: counts, record and units at the exec cost for exec >= 4, 0 < exec < 4, exec <= 0, from the closing files on disk, read-only, so the n=30 read in (i) is automatic. Small; it may ride #431 or its own PR." 1(vi) "(vi) The exports' label "K-track: informational until the executable-edge ruling" becomes "K-track: binding (ARCHITECT 2026-10-20, addendum 146 item 1)" wherever it is written (fixtures, predictions, shadow exports, the Cockpit's copy). Wording only; one PR with (v)." 5 "5. PAPER LANE for market-only competitions (ruled 08:20 ET today, on the operator's "track them as if live"). No model number means no pick; nothing from this lane enters the ledger, the P&L or the Cockpit positions; the Desk's call stays PASS noref. Two read-only pieces, small, one PR after item 3 or riding (v): (a) coverage's SLATE line for a market-only competition carries, per game, the Kalshi mid (two-way, or the three-way mids) and, where a shadow export exists for the day, the shadow's pick and value side with their divergence against the mid, labelled PAPER and never a call. NHL today has a shadow (v7, FAILED gate); CL and NCAA have none and show the market line only. (b) results-tally gains "the close's record" per market-only competition (NHL, NCAA, CL): games with a decided result and a last two-sided Kalshi quote before kickoff (the kalshi_only close rule), the close's log-loss and the favourite's record, n. This is the bar a college or cup candidate is scored against (roadmap: "no college candidate has been scored against a close")." Addendum 148 item 5 (12:56 ET): "the PAPER lane and the K-track wording ride the next small PR after the slots clear".
- The three-way close, verbatim (ARCHITECT 2026-10-20 17:52 ET, addendum 150, #639 RULED): 1 "1. Scope. This close exists for the market-only three-way competitions' PAPER record (146 item 5(b); 149 item 1(d)): CL now, and every three-way competition the replay prices (ELC and the leagues' lanes, UEL and EFL when their series exist). It is never the Desk's graded close: a three-way board the Desk grades keeps its book close, labelled when stale (addendum 145; #629's label). The two never pool; every row of the record names its close kind." 2 "2. The quotes (Q1): ONE capture in which all three legs (HOME, AWAY, TIE) are two-sided within the 2c cap — the last such capture before kickoff, the same "last two-sided pre-kickoff session" shape as the two-way kalshi_only rule. Legs from different captures are never combined. A game with no such capture has no close: counted as unpriced on its own line, never formed from fewer than three legs (law 4)." 3 "3. The number (Q2): the three mids sum-normalized to 1 (as export._summarize_kalshi forms the venue fair); the raw sum is kept on the row as the overround. The record's log-loss is scored on the normalized three-way probabilities." 4 "4. The favourite (Q3): the largest of the three normalized probabilities, the draw included; a row whose favourite is the draw is counted and flagged on the line. cup_exam.favorite's "the draw is never the favourite" stays the exam's sign check and is not changed." 5 "5. The result basis (Q4), read from KXUCLGAME's own rules (the kept replay payload of 2026-10-20 11:46Z, logs/kalshi_replay_20261020T114645Z.json on the laptop, market KXUCLGAME-26OCT20PSGBAR-TIE), verbatim: "If Tie is the result of the PSG vs Barcelona professional Champions League soccer game originally scheduled for Oct 20, 2026 after 90 minutes plus stoppage time (does not include extra time or penalties), then the market resolves to Yes." The basis is 90 minutes plus stoppage, the same as KXUEFANLGAME's (#325) and intl_shadow.result_90. A knockout game decided in extra time or on penalties scores as its 90-minute result. The quoted text goes on #639 as the receipt; the series' rules are re-read if a market's rules_primary ever reads differently (the replay keeps every payload)." 6 "6. The limitation closes by the PR that forms this close in the PAPER-lane work (146 item 5(b)); the roadmap's cup bar is then this record. Until then CL's line reads n=0, labelled, as built."
- src/walters/venue.py: K_TRACK_NOTE reads "K-track: binding (ARCHITECT 2026-10-20, addendum 146 item 1)" on every export row that carries k_track (predictions, NFL, fixtures, window card, shadow exports: all through kalshi_exec()); comments at venue.py:40-42, export.py:473, :1243 and the Cockpit's K2 comment (tools/cockpit.html:476-477) say binding. No key added or removed; KALSHI_EXEC_NULL still carries no k_track; files on disk keep the old text.
- src/walters/redated.py: closing_rows (the closing files' rows with their family and run start, the run range and the families named); closing_starts is its projection, unchanged.
- src/walters/exec_cohorts.py (new) + results-tally: the EXEC COHORTS section (per closing family, from every closing file on disk, never exports/host/; one PLAY row per game, the newest run's within the hour of its current start; exec >= 4 (the Desk's exec_clears), 0 < exec < 4 split QB inputs clean (the pre-registered cohort) / QB-flagged or unread, exec <= 0, exec unknown; W-L-P and notional units at desk.exec.cost (a push or a void 0u whatever the cost; a cell with nothing settled reads `units —`; an edge that is not a finite number is exec unknown; units or a cost that is a bool, NaN or inf reads unpriced, never summed); LADDER, basis not taker, not in this DB, teams differ and re-dated rows left out and counted, the void ones named; the pre-registered cohort's pooled `graded k of 30` line, `n=30 reached` at 30, no verdict computed: it counts only closing runs from 2026-10-18 00:00 ET (exec_cohorts.RULE_OF_1018, the rule 1(i) names; a reading for the architect) and prints the earlier graded rows beside it, `not counted (before the rule of 2026-10-18) b`, the per-family lines keeping every row) and one console line.
- src/walters/paper.py (new) + results-tally: THE CLOSE'S RECORD (FINISHED games of the window; every line names its close kind, the two never pool). NHL and NCAA, `close: kalshi_only two-way`: close.close_from_kalshi read directly after the legs guard, books not read (the newest legs by the ruled guard, then the HOME row the close reads judged with them, paper.close_row_mismatched on its market_ticker read by SQL by row id: a row of another event, or of one whose current legs sit on another game, is mismatched legs, no close; close.py unchanged; Codex round 2 P1, R47); the close's log-loss, the favourite's record (a 0.50 close is EVEN, in n and the log-loss only), n; no decided result, an NCAA tie, mismatched legs, no Kalshi close and three-way board counted. CL always, and each other market-only three-way competition with a stored Kalshi 1X2 leg in its window, `close: kalshi three-way (one capture, normalized)` (paper.three_way_close, the record's own: never close.py, grading_close, the Desk, an export or the matcher): the last capture (one stored captured_at) before kickoff with HOME, DRAW and AWAY all two-sided; a leg of it over the 2c cap leaves no close (no older capture substituted, legs of two captures never combined); the mids sum-normalized by export._summarize_kalshi, the raw sum kept as the overround (mean printed); scored on intl_shadow.result_90 (90 minutes plus stoppage); the favourite the largest of the three, the draw included and flagged (`draw favourite k`), a top tie EVEN; no decided 90-minute result and mismatched legs left out (the newest legs by the ruled guard, then the legs of the capture the close reads, kalshi_legs.judge on their market_ticker read by SQL by row id: legs of two events get no close; Codex round 1 P1, R47); unpriced on its own line, its close kind named and the count split by cause so every printed reason is true: `  - CODE · close: kalshi three-way · unpriced u: no capture before kickoff with all three legs two-sided a; the last full capture has a leg over the 2c cap b (no older capture substituted)`, and a third cause only when it counts a game, `; the last full capture fails the close's other checks c (a leg stored twice with two quotes, a quote that is not a number, a crossed or out-of-range quote, or no normalized sum; no older capture substituted)`; each per-game row of the record names its close kind. RESULTS.md's #615 header sentence (src/walters/export.py results_tally) and docs/CLI.md's now read "a three-way board never takes a Kalshi grading close (the PAPER record's three-way close, addendum 150, is its own)" (verifier0 P3-2; wording only). One console line, each kind apart. Its pure helpers (board_of, two_way_mid, leg_mids, shadow_view) serve coverage.
- deploy/hosting/coverage_map.py: PAPER SLATE lines for every MARKET-ONLY competition with games (a header `<CODE> SLATE · PAPER, never a call (...) · n game(s) · Kalshi mid k of n · shadow s of n`, then one line per game: the two-way Kalshi mid (close_from_kalshi's own) or the three-way legs' raw mids with their sum (display only), or why there is none; the last shadow row before kickoff (each shadow module's last_calls) with its pick, value side and divergence against the mid; a row recorded for another kickoff, by the re-dated rule (redated.redated_label), or with a kickoff that cannot be read, is not shown, nor is a row exported at or after the game's current start (`shadow: exported at or after the current kickoff (an in-play row): not shown`, compared as UTC; Codex round 2 P2), and a shadow module that cannot be read hides only its own competitions' shadows (paper.shadow_comps): Codex round 1 P2s); `paper` in coverage(), `paper_lines` in coverage_v1, `slate_line` = the header; no gap claimed; the Kalshi quotes read on a second mode=ro connection (the legs guard's PRAGMA its one non-SELECT); the header line names the slate and shadow files read; a shadow row or a stored quote of the wrong kind reads `the row cannot be read: not shown` or `cannot be read (<Error>): not shown` for that game only, and the rest of coverage prints whole (exit 0); a game left with no mid by a capture time that cannot be parsed reads `Kalshi: cannot be read (a capture time cannot be read): not shown`; the value side is judged at the printed precision (under 0.05pp above its mid is none, said so) and a prediction whose legs are not the board's is never judged (`value side not judged (a two-way prediction on a three-way board)`, no divergence).
- docs/CLI.md: the results-tally and coverage rows.
- tests: test_exec_cohorts.py (new, 49), test_close_record_paper.py (new, 26), test_close_record_three_way.py (new, 49), test_paper_lane.py (new, 24), test_k_track_binding.py (new, 3); test_coverage_map.py (+50, the three-way board with an unreadable capture time among them; make_db gains `kalshi`; PIN_TEXT, the JSON keys test, the slate-line test (renamed), the JSON slate_line test and the UNKNOWN-order test updated for the ruling's addition), test_k1_kalshi_quotes.py and test_kalshi_exec_mlb_soccer.py (the label; the fixtures row's label now pinned).

## 2026-10-20 (#635: kalshi-anchored-chain — ARCHITECT addendum 148 item 2; Refs #630, #598)
- The ruling, verbatim (ARCHITECT 2026-10-20 12:56 ET, addendum 148 item 2): "#630, the anchored chain — RULED on the twelve questions, one change to the design's center: Q1 after A's ticker clock, M used by A: yes. Q3 STOP: yes. Q4 yes to both (the storage definition of IN STEP; MAX_TICK_DRIFT 2h inclusive plus the time tie). Q5 the fourth note part after the ruling part: yes. Q6 END: yes. Q7 "out of step" only: yes. Q8 N1 and N2: accept both. Q10 yes. Q11 the table only, no exchange call: yes. Q12 the listing mode in the same PR, its console in the body: yes. Q2 and Q9, the change: a shift-capable check IS wanted, because the shifted chain is the case the rule exists for (E17 on 50548 is the ALCS's own example, and every rainout-then-doubleheader pattern is a shift). A member PLACES on the count's game when EITHER check passes, and a result mismatch refuses under both: (a) the clock check as designed: |kickoff − ticker clock| ≤ MAX_TICK_DRIFT and no other unused game within 2h; or (b) the settlement bracket: the row's settled_time is after the count's game's kickoff and before the kickoff of the pair's next game in the list (or no next game within N1's window), the target is FINISHED with a stored winner, and the leg's kalshi_result agrees with that winner. The bracket is the shifted event's own evidence that it settled on that game and no other. A member that passes neither stays held and the chain STOPs (Q3). The dry run prints which check placed each row ("by clock 0.1h" or "by settlement +2.9h, before <next id> <ET>"). Tests gain: E17 placed on 50548 by settlement; a settlement after the next game's kickoff stays held; a result mismatch refuses under (b); a SCHEDULED target never places under (b). Size M, track K2; the PR opens after one of the three slots clears (#631 or #629 merging today)."
- src/ingestion/kalshi_history.py:
  - **`place_chain`, `kalshi-history place-chain --anchor EVENT --ruling R (--backup PATH | --dry-run)`:** the anchored chain as ruled. The anchor is an event out of step on its own date (the identity hold's own read, `identity_holds`) ruled into place on every row on one match M, each row carrying `placed by ruling: R`. The chain is the pair's events after it in the hold's chain order, from the table only, within N1 (1-10 days after the anchor), up to the first that ENDs it (IN STEP: a row placed by the ingest; refused; mixed legs; held behind another event; held naming the anchor `unsettled`). The list is the pair's games (the games the anchor's two names fit one each, `kalshi_match.fit`, as place-held fits its match; rows that are games) from the anchor's ticker clock through its date + 11 days; fitted games of more than one pair of teams, the anchor's match with them, refuse (a second team row of one club: merge-teams first; a namesake club's game, whose names differ: rule the events by place-held), as the matcher refuses `best fit shared by two pairs of teams`; M is used by the anchor and a game a stored row outside the chain holds is used by its holder; each chain event takes the first unused game; a ruled event is counted on its own match and stops the chain where that is not the count's game. A member (every row held naming the anchor `out of step`) is placed when each row passes (a) the clock check (`MAX_TICK_DRIFT` 2h inclusive and no other unused game within 2h) or (b) the settlement bracket (settled after the game's kickoff and before the next game's in the list, or no next game in it; the game FINISHED with a stored winner; the leg's `kalshi_result` agreeing; a drawn game's outcome is DRAW, every leg checked against it, and not a winner for (b)), a result mismatch refusing under both, the game SCHEDULED or FINISHED (LIVE stays held); one that passes neither stays held and the chain STOPs. The dry run prints the check per row (`PLACE <SIDE> by clock 0.0h`, `PLACE <SIDE> by settlement +3.6h, before 50551 2026-10-19 20:08 ET`). The note gains a fourth part after the ruling: `placed by the chain of <A> [k]: <how>`. Refusals exit 2 with nothing written (two rows the chain would place on one side of one game refuse too); a candle call that fails for now on any row writes nothing (all or nothing); one transaction, each row read again as a held row and its side read again; a chain with no member prints and exits 0.
  - **`list_chains`, `kalshi-history place-chain --list --series S`:** read-only, no network call, nothing written: each held row by the event its note names, that event's state and clock, and the pair's games on the held event's day (kickoff, status, gap, the rows holding each).
  - place-held's reads, candle read and write are now shared functions (`_ruled_target`, `_target_line`, `_read_cutoff`, `_placed_after`, `_write_placed`); place-held's behaviour is unchanged (its 52 console/after/refusal records over tests/test_kalshi_history_identity_hold.py are byte-identical before and after).
- cli.py: `kalshi-history place-chain` beside `place-held` (`--backup` required unless `--dry-run`; `--list` takes `--series` alone).
- Tests: tests/test_kalshi_history_anchored_chain.py (E17 on 50548 by settlement and Game 6 by clock, written and in the dry run; a settlement after the next game's kickoff, or before the game's own, stays held and the chain stops; a SCHEDULED target and a finished one with no stored winner never place under (b); a result mismatch under (a) and under (b); the time tie; a LIVE target; a chain with no member exits 0; a counted event off the count's game; a claimed game; one event per game; day 11 (N1); mixed legs, a twin on the anchor's date, an unsettled note naming the anchor and a hold behind another event END the chain; each refusal; a candle failure on row 2 writes nothing; the write's re-reads; the notes cap; the listing makes no network call (its stub's calls recorded) and writes nothing; the command's options; place-held unchanged; the boundaries and readings pinned: a settlement exactly at either kickoff stays held; a null result under (b); MAX_TICK_DRIFT 2h0m places and 2h1m holds; the time tie at exactly 2h; the time tie counts unused games only; the next game bounds the bracket used or not; a stored result that disagrees with the scores stores no winner; an event is placed on all its legs or on none; N1's day 10 is in the chain; Q1's makeup after a member; a second team row of one club in the list refuses; two rows on one side of one game refuse; a drawn game is checked under (a) and held under (b), and `_as_game` reads D or level scores as DRAW).
- Docs: docs/CLI.md (`kalshi-history place-chain`), the kalshi_history module docstring, the `kalshi-history` group's help.

## 2026-10-20 (#631: mlb-retire-orphans — ARCHITECT addendum 146 item 3; Closes #568)
- The ruling, verbatim (ARCHITECT 2026-10-20 09:59 ET, addendum 146 item 3): "#568 REOPENED, with a fix (one small PR, data lane, the third slot). The reopening condition is met in effect: the SLATE stage (new since the limitation) reads the dropped row as a live game, plans on it, and will page two failures tonight. The fix, as ruled: (a) A retire-orphans step for MLB, explicit, dry run first, in the morning block after the MLB sync (never inside the watch): a SCHEDULED MLB row becomes STALE_ORPHAN on TWO receipts, both printed per row: (1) the row's provider id is absent from the provider's answer for a window that covers its date (the strict read's own evidence, one call), and (2) the series arithmetic from the #605 fields shows the series decided before this row's game number: the pair's FINISHED games of the same season and stage, wins per side, against games_in_series of any row of that series (needed = ceil(gis/2)). Either receipt missing -> the row stays SCHEDULED (law 4). Never CANCELLED: the provider said nothing. Acceptance cases: 50555 (ALCS Game 7, dropped 10-20) and 50549 (MIL at LAD, dropped 10-16; its own series fields are null, so receipt (2) reads the series' other rows). The dry run's console on the laptop goes in the PR body before merge. (b) The statsapi adapter stores codedGameState verbatim in status_raw on every row it writes, as the api-football, api-hockey and api-sports paths do (NormalizedMatch.status_raw). Receipt: the ALCS rows' status_raw after one sync. (c) The coverage map marks a STALE_ORPHAN row as VOID like CANCELLED (closing.py's VOID set already has it); the Today tile stops showing a slate due for it. Tonight's two MLB failure pages are expected and are not a miss; the doctrine receipt for the day notes them as the dead row."
- cli.py: `retire-orphans --competition MLB --season 2026 [--apply --backup PATH --match-ids ID,ID]` (new). Dry run by default. Refusals, each exit 2 with no provider call and nothing written, in order: a competition other than MLB; `SP_SKIP_FAMILIES` naming MLB (the host's api-sports fallback); a `--season` that is not digits; no database file at the configured path (law 5: never created, the migrations' shared guard, #524); `--apply` without `--backup` or without `--match-ids`, or `--match-ids` without `--apply`; the backup check (`_verify_backup`, matches count = live); a DB behind the code. MLB not stored: exit 1, no provider call. `_schema_refusal` moved from `dedupe-matches`' closure to module level, unchanged, and called by both.
- src/ingestion/mlb_orphans.py (new): the planner. Candidates: the season's SCHEDULED MLB rows with a postseason stage (F/D/L/W) and no score; every other SCHEDULED row of the season past its start is printed, never a candidate.
  - Receipt (1): ONE GET for the run, the season's postseason schedule (`{sportId 1, gameType F,D,L,W, season}`, no dates, as `mlb-time-audit` reads it); ABSENT when the answer lists one game or more, not the row's gamePk, and at least one stored gamePk of the row's own series (its other rows); LISTED when it lists the row's gamePk; NO RECEIPT when the call fails, the answer lists no game, the row has no `mlb_stats_api` id, or the answer lists no game of the row's series. The ids are the answer's raw gamePks.
  - Receipt (2): the series is the rows of the row's season and stage with its two teams either way round; `games_in_series` the one value its rows carry; needed = (gis + 1) // 2; wins per side over its FINISHED games; DECIDED when a side has `needed` wins over the k FINISHED games and the series ended before this row's game (its own game number after the clinch's stored number, which must equal k, the receipt saying `after k FINISHED games` when none is stored; with its own number null, the clinch's start before its own, the same start NOT DECIDED). NO RECEIPT for gis null or disagreeing, a gis under 1 or even (a tie), the columns not migrated, a LIVE game of the series, a FINISHED game without a decided score, twin FINISHED rows, more FINISHED games than gis, a side past `needed`, two FINISHED games at the latest start, a clinch the other side won, or a clinch whose stored game number is not k. The two no-start guards cannot fire on a current-schema DB (`matches.utc_date` NOT NULL).
  - Retire on ABSENT and DECIDED only. `--apply` plans again in its own session and retires only the named rows planned retire: `STALE_ORPHAN` plus `external_ids.mlb_stats_api_orphaned_at`; nothing else on the row changes; a named row planned otherwise is REFUSED; nothing is CANCELLED or deleted. A dry run rolls back.
- src/adapters/mlb_stats_api.py: `_parse_game` stores `codedGameState` verbatim in `status_raw` (read before the "S" default; a code not given as a non-blank text is None); the mapped status and the pre-game score nulling are unchanged. New: `listed_game_pks(data)` (every entry's gamePk, raw, a null or blank one dropped), `postseason_params` and `postseason_answer` (the one GET).
- src/db/migrate_guard.py: `refuse_missing_db` names its caller (a migration by default; retire-orphans).
- src/db/database.py: `read_match_series(session, ids)`, the #605 columns' first reader (None before the migration). The "read by nothing" comments in src/db/schema.py, src/db/database.py and src/ingestion/service.py now name it.
- docs/CLI.md: the `retire-orphans` row (MLB daily operation); the morning Phase 1 lines (the dry run, then `--apply --backup PATH --match-ids <the ids the dry run planned>`); the `sync-matches` row (`status_raw`); the `coverage` row (an all-void competition has no SLATE line and no NO SLATE FILE gap); the `dedupe-matches` row (MLB goes through `retire-orphans`).
- tests/test_mlb_retire_orphans.py (new, 57): the two acceptance cases on both receipts (dry run, nothing written, the console pinned), the one call and its params, the apply on named rows only (every other column and row unchanged, never CANCELLED, a re-run finds none), a named row planned otherwise refused, the refusals and their order, MLB not stored (exit 1, no call), a DB behind the code, the CHECK guard, self-heal keeping the marker, a listed gamePk (an entry with no team ids, a bad date), a failed call, an answer with no game, an answer with no game of the row's series, a row with no id, each reachable receipt-(2) refusal (more FINISHED than gis, an even gis's tie, two FINISHED at the latest start, two FINISHED on one ET day (one game stored twice), a clinch number that is not k, a FINISHED row numbered k or more when the clinch stores none, a gis under 1 with the run going on), not decided, an own game number already played, no stored clinch number (`after k FINISHED games`), a clinch after or at this row's start, a scored SCHEDULED row and the past-start filter of the `[not a candidate]` lines, the `--season` refusal, no database file (refused, nothing created), the series either way round of one season and stage, the description printed never gated, never inside the watch (no chain or deploy/hosting file names it), and the export-predictions behaviour documented (D9).
- tests/test_mlb_status_raw.py (new, 15): every mapped code verbatim with its status unchanged, an unmapped code kept, a code not given as text is None never "S", pre-game scores still nulled; the ALCS rows' status_raw after one sync (a dropped row keeps NULL), create, update, and an entry without a code keeping the stored one.
- tests/test_coverage_map.py (+3), tests/test_cockpit_today.py (+1), tests/test_closing_runs.py (+1): STALE_ORPHAN is void like CANCELLED (named, not counted, no group, the slate due from the day's other game); a day whose only MLB game is retired (or cancelled) has no SLATE line, no NO SLATE FILE gap, null `slate` / `slate_line`; the Today tile shows the void game and no slate; the watch forms no closing and the slate stage finds no game that day.

## 2026-10-20 (#629: book-source-times — ARCHITECT addendum 137 item 4, addendum 147; Closes #615)
- The ruling, verbatim: "MLB's and PL's odds syncs never store the provider's update time (`_mlb_store_odds`, `sync_odds`), so their stamp age cannot be measured. Issue + a small data PR: both syncs write `source_updated_at` from the provider's own update field, as `sync-odds-football` does, no backfill; the 24-hour rule then applies to them forward." The fields, read from the operator's kept probe answers (laptop/odds-payloads-1020 ee84a62; addendum 147, law 1): soccer's is `response[].update`, one per fixture answer; MLB's answer carries none.
- src/adapters/api_football.py `list_odds`: every row of an answer carries its `response[].update` as `source_updated_at`, parsed by the american-football adapter's own `parse_source_updated_at` (an epoch integer or an offset-less string → None). It serves every soccer code through `sync-odds`.
- src/ingestion/service.py: `_mlb_store_odds` and `IngestionService.sync_odds` write `source_updated_at` as `sync_odds_nfl` does (`_write_book_source_times`): each odds row its own adapter row's time (None = unknown, never our clock), each appended book snapshot the oldest over the rows its close priced (`close.priced_rows`, extracted from `book_stamp`, so the odds close and the snapshot close of one game read one stamp); guarded Core SQL after a flush (a database before `migrate_odds_source_updated_at.py` writes nothing to the field). `sync-odds --competition NFL|NCAA` (the american-football adapter) now stamps its rows and snapshots too. **MLB is not stamped:** api-baseball's odds answer carries no update field (#628, a limitation of the provider, like hockey's); nothing is substituted, MLB rows store NULL and the stale-book rule never switches an MLB close.
- **PL closes now carry a stamp age.** A three-way board with a stamp more than 24 h before kickoff keeps its book close, labelled `close_stale_unswitched` (addendum 140 item 3 reading (4), pre-committed); no three-way Kalshi price is derived.
- src/walters/export.py `results_tally` (#615 comment 6270315541): the verified / retained-legacy split loads snapshots with `kalshi_close_market_filter`, as `clv_restate.restate()` does, so a divergence stored against a close priced from a Kalshi mid (the 2026-10-05 `kalshi_only` close, or the stale-book rule's `kalshi`) reproduces and counts as VERIFIED. **This moves RESULTS.md's MLB cohort counts on the day it merges**, for every stored outcome in the window; Soccer (PL) cannot move. The RESULTS.md paragraph says so and no longer calls the M11 rollover games unpriced.
- scripts/results_tally_cohort_receipt.py (new, read-only): RESULTS.md's cohort lines BEFORE (main's read) and AFTER (as built) from one DB state and one clock, the DB opened mode=ro; BEFORE narrows only the snapshots the cohort split reads, so every other line runs as on main; a write landing between the passes is refused (exit 3).
- scripts/odds_payload_probe.py: the soccer read set names `response[].update`, so a later soccer probe never reports the stored field as dropped.
- Text: the `migrate_odds_source_updated_at.py` docstring and receipt footer, the schema.py and normalized.py comments, docs/CLI.md (the `source_updated_at` sentences, `sync-odds`, `close-probe`, `results-tally`, `export-results`'s `close_book_stamp_age_h`) name every writer and the MLB limitation.
- Tests: tests/test_book_source_times_615.py (the writers, the soccer adapter on the kept answer trimmed to tests/fixtures/odds_payloads/, the stale three-way label, results-tally, the receipt).

## 2026-10-19 (#623: today-tab-followup — #606 item 2 and #597's two; ARCHITECT addendum 134 item 1, addendum 136 item 6)
- The rulings, verbatim. Addendum 134 item 1: "#606 item 2, the Today tile renders `slate` first: the Today-tab follow-up PR, approved as Code proposes." Addendum 136 item 6: "the Today-tab follow-up (#597's two + #606 item 2: the SLATE line first on the tile)".
- deploy/hosting/coverage_map.py: the coverage_v1 file carries each competition's `slate_line`, the SLATE line word for word as the console prints it under the competition's line (null where it has none: not LIVE). `_out_refusal`: an `--out` that names no file (`.`, `/`, `..`) is `COVERAGE REFUSED: --out <p> names no file`, exit 2, never a traceback (#597 item 1, Codex on #595: `out.with_name(...)` raised ValueError before the write's try); each rule (law 5's data/, #592's exports/ kind) is judged on the lexical path and on the resolved one, so a symlink already at the name, which the write replaces with a regular file there, never gets a file past either rule (#597 item 2).
- tools/cockpit.html (repo copy; the live page is republished on the operator's word): `todayTileHTML` shows the file's `slate_line` first on the tile, before the void note and the status; a NO SLATE FILE line is marked as the gap (`caution`); a competition with none, or a file written before the key, shows none (nothing derived, F1c).
- docs/CLI.md (the coverage row): `slate_line` and the two refusals.
- tests/test_cockpit_today.py: the slate line first, escaped, the gap marked, none without the key. tests/test_coverage_map.py: `--out .`, `/`, `..` refused with nothing written; a symlink at exports/today.json and under a scratch data/ refused, the link left as it was; the file's `slate_line` equals the console's line.

## 2026-10-19 (#622: model-close-divergence — ARCHITECT addendum 137 item 3; Closes #612, Refs #208, #621)
- The ruling, verbatim (addendum 137 item 3): "#612 (the `clv` field) — RULED as declared: `graded.model_close_divergence` written beside `graded.clv` in the three results exports with the same value and the one-sentence comment at each writer; `clv` stays as an alias through v1.5.0 and is removed in the release after (the removal is its own line in that release's changelog); the tests pin the new key and the alias; the external morning-run consumer is the alias's reason. The live Cockpit is unaffected: I read the published page — its `clv` is the executed-position CLV computed from fills (qty × (close − entry)), never the export's graded key. Build it as a small PR in the UI/declaration lane, after the slate follow-up 2."
- **An export-contract change (additive).** `graded.model_close_divergence` is written beside `graded.clv` with the same value in the three results exports:
  - `export-results` (src/walters/export.py): the stored value, `prediction_outcomes.clv` (VERIFIED or RETAINED-LEGACY in RESULTS.md).
  - `export-nfl-results` (src/walters/nfl_predict.py): computed at write on the row's close, the pick HOME when p ≥ 0.5.
  - `export-intl-results` (src/walters/intl_production.py): computed at write on the book close, the argmax pick.
  - What it is: model p minus close fair on the pick, a fraction (0.0453 = +4.53pp). It is NOT a closing-line value; close minus entry is the Cockpit P&L's, on executed fills. Each writer's comment says so.
- **`clv` stays as an alias through v1.5.0**, for the external morning-run consumer. It is removed in the release after, as its own changelog line (#621). Nothing else is renamed: the DB column, the in-memory `mean_clv_pp` names, `clv-report`, `clv-capture` and every executed-position `clv` are unchanged. No value changes.
- Tests: tests/test_model_close_divergence.py (each writer: both keys, the same value; a row with no close is null under both).
- Docs: docs/CLI.md (`export-results`, `export-nfl-results`, `export-intl-results`).

## 2026-10-19 (#619: nfl-stale-book-close — ARCHITECT addendum 137 item 4; Closes #614)
- The ruling, verbatim: "FOR A GRADED GAME WHOSE BOOK QUOTE CARRIES A PROVIDER STAMP MORE THAN 24 HOURS BEFORE KICKOFF, THE RECORDED CLOSE IS THE KALSHI TWO-SIDED MID CAPTURED IN THE SAME LAST PRE-KICKOFF SESSION, and the row says so (`close_reference: kalshi`, with the book stamp's age in hours beside it; the `kalshi_only_closes` count in the record block already exists for this). A NULL or absent stamp keeps the book close (unknown is not stale: law 4 labels it, it does not switch it) until the stamp is stored. Scope: every family, applied where a stamp exists — which today is NFL."
- src/walters/close.py: `stale_book_close(s, match, cl, snaps=None)` (one helper), with `book_stamp` (the oldest `source_updated_at` of the rows the book close priced, through `attach_source_times`), `stamp_age_hours`, `session_kalshi` (the newest two-sided Kalshi HOME capture within `CAPTURE_SESSION` of the book capture, before kickoff, under the 2c cap; the mismatched-legs guard first), `STALE_BOOK_H = 24`, `KALSHI_SOURCES`. A stale book close becomes the Kalshi close (`source`/`reference` "kalshi", `book_fair`, `book_captured_at`), or UNPRICED with `stale_book` when that session holds no such quote; an unknown stamp or a three-way board keeps the book (`stale_unswitched` on the latter). `grading_close` applies it to its odds and snapshot closes; `close_from_snapshots` carries `stamp_rows`. `graded_block(cl, kickoff)` builds the results row's close block (`close_reference`, `close_book_stamp_age_h` on every row, `close_kalshi` with `book_fair`/`book_at` on a stale-book close, `close_stale_book`, `close_stale_unswitched`); `grading_close_block` is it over `grading_close`.
- src/walters/nfl_predict.py: `grade_nfl` and `export_nfl_results` read `close_1x2` then `stale_book_close` (one close for the pick divergence, the value side, the close age, the row and the record); the row's block is `graded_block`; `grade_nfl`'s `vs_close` blocks carry `kalshi_only_closes` as the file's do.
- src/walters/vs_close.py: `kalshi_only_closes` counts `close_reference` "kalshi" too (the line's words unchanged, pinned to the Cockpit's). src/walters/clv_restate.py `_close_for`, src/walters/ncaa_shadow.py `grade`: the same rule. src/walters/training.py: `closing_bookmaker` reads the Kalshi source either way. cli.py `close-probe`: the stamp, its age, the replaced book close or the unpriced reason. RESULTS.md's divergence paragraph (export.py) names the rule.
- src/db/database.py: `has_source_time(table, bind=None)` checks the column on the database the read or write runs on (`attach_source_times` and `write_source_times` pass the session's bind). It checked the app's engine while the query ran on the session's, so an app database that had run the migration beside a session database that had not raised "no such column" instead of reading the stamp as unknown (found by this PR's full suite; the regression test fails on main's database.py).
- scripts/nfl_close_restate_receipt.py (new, read-only): the NFL record BEFORE (the rule left out) and AFTER (as built) from one DB state, the DB opened mode=ro, the exports' closing files copied to a scratch dir; season, every week, pre-live, `nfl-grade`'s summary and every row whose close changed.
- From the adversarial review of the diff (four lenses, each finding verified): a stale close left unpriced by the mismatched-legs guard says so (`close_stale_book` names the events and addendum 37 item 3, not the cap); the NCAA shadow grade's `vs_close` carries `kalshi_only_closes`; the receipt counts its tally and table over the rows the records read (a void row named apart), copies the closing files once, and refuses when SQLite's `data_version` moves between its passes (one DB state).
- Tests: tests/test_nfl_stale_book_close.py (24); tests/test_record_vs_close.py's and tests/test_ncaa_shadow.py's blocks carry `kalshi_only_closes`.
- Docs: docs/CLI.md (`export-nfl-results`, `close-probe`, `export-results`).

## 2026-10-19 (#618: history-hold-followup — ARCHITECT addendum 136 item 3; Closes #599, Refs #598, #603, #478)
- The ruling, verbatim (addendum 136 item 3): "SLOT 3 — the #598 follow-up (after #598 merges; same file): #599's three (the new-row write re-check; place-held's candle endpoint by the cutoff; the sibling read by `event_ticker or event_of(ticker)`), #603 (the closed-list read, for the hold only), and ONE finding from this morning's pulls: the suffix "dedupe-matches has to merge them" printed on true doubleheaders [...]. The suffix belongs ONLY where rows share a kickoff minute [...]. A doubleheader reads "two games of the pair that day; the G1/G2 suffix is not read (#478)" and no merge is suggested." #603 waits for the operator's read of a closed market's list status (addendum 138 item 4); it is not in this PR.
- src/ingestion/kalshi_history.py:
  - **#599 item 1, the new-row write re-check:** a new placed row reads its side again in the write's own transaction, in the plan's scope (a clock ticker, or a side a row placed by ruling holds); taken meanwhile by another ticker (a `place-held` committed after the run's read), it is written unplaced, refused by the matcher (`two claims`, the side and its holder in the note, no quote), and named on the receipt (`Run.write_refused`).
  - **#599 item 2, the candle endpoint by the cutoff:** `place-held` reads `/historical/cutoff` and asks the candles of `historical` when the row's `settled_time` is before it, else `live` (a null `settled_time` keeps the stored source); the source written is the one used; a cutoff it cannot read writes nothing (exit 2). `PLACE_HELD_CALLS` 3 → 6 (the cutoff and the candles, each with the two 429 retries).
  - **#599 item 3, the event read:** `place-held` reads the row's event as the history path does, `event_ticker or event_of(ticker)`, for the row and its siblings (the series' stored rows of that event).
- The ruling on Codex's escalated P2, verbatim (ARCHITECT 2026-10-19, addendum 140 item 2): "RULED on the escalated one: OPTION (b), the literal reading of 136 item 3 — the words "dedupe-matches has to merge them" belong ONLY where rows share a kickoff minute, on every ticker form. On a date-only ticker with no game number, rows of the pair at different minutes get the DECLARED TEXT, the suffix after "refused; ": `two games or a placeholder beside the real kickoff (<HH:MM> and <HH:MM> ET): dedupe-matches's dry run says which; not merged from here`. Where both hold (two rows at one minute and a third at another) the line names each, as _clock_rows_what does. The reason is law 4 and the asymmetry: a receipt that instructs a merge on rows it cannot tell apart is destructive guidance (dedupe-matches writes); a receipt that describes and points at the command's own dry run costs a read. The college placeholder case keeps its refusal unchanged; only its words change, and its test's expectation with them."
- src/ingestion/kalshi_match.py: `_date_rows_what`: "dedupe-matches has to merge them" only where rows share a kickoff minute, on every ticker form. Two stored rows of one pair on a date-only ticker at different minutes read, where the ticker carries the game number (G1, G2), "two games of the pair that day; the G1/G2 suffix is not read (#478)"; with none, the declared text "two games or a placeholder beside the real kickoff (<HH:MM> and <HH:MM> ET): dedupe-matches's dry run says which; not merged from here" (the rows' kickoff minutes in US Eastern; three or more read "A, B and C"). Where both hold, the line names each (`_clock_rows_what` takes the words for rows at different minutes). `two_rows` takes its words from its caller only. The college placeholder's refusal is unchanged; its words change.
- Tests: tests/test_kalshi_history_identity_hold.py (the write re-check with a place-held committed between the plan and the write; the cutoff source both ways, the cutoff unreadable, the null event_ticker), tests/test_kalshi_matcher_day_rule.py (the G2 doubleheader and the shared-minute pair; the college placeholder's whole line; the date-only ticker with no game number at two minutes, both holding, one minute and three minutes; the merge words only on a shared minute, on all four ticker forms).
- Docs: docs/CLI.md (`kalshi-history`, `kalshi-history place-held`), the kalshi_match module docstring.

## 2026-10-19 (#617: slate-followup-3 — ARCHITECT addendum 138 item 3; Closes #613, Refs #616)
- The rulings, verbatim (addendum 138 item 3): "(a) P1-2's reading — the bounded send (a daemon thread joined for the bound; cut, the tick goes on and the receipt says so; the page may still complete while the process lives) is APPROVED over a detached sender: a page whose outcome is never receipted is a page we cannot audit. Accepted cost: a page cut at the bound may not reach the phone; the receipt names it. (b) P1-4 — option (a): the one-run bound and SLATE_GUARD_MIN stand; a deferred slate whose kickoff comes before a later tick can run is NOT run, and its deferral page (item 2 above) is the operator's alert. The docs say so: "the slate runs on a later tick unless its kickoff comes first, and then its page says so". [...] (c) The P2 — the HELD page's bound is tested against `slate_ahead`'s closing (an MLB closing the feed did not answer for left out): RULED, test against `closing_ahead` (feed-down MLB closings included). The invariant is that no page costs a closing its T-35; the cost — the page waits while the feed is down — is bounded by the feed answering or the closing passing, and the every-game-started miss still pages at kickoff. Slate follow-up 3 carries (b)'s docs line and (c) (one line and a test)".
- deploy/hosting/closing.py: `send_slate_page` tests a stage page's bound (the HELD page, the deferral page) against `closing_ahead` over the tick's families (an MLB closing the feed did not answer for included), not the closing the slate waits for; the page's text still names that closing. `record_slate_hold` and `record_slate_deferred` take the tick's `fams` for it. The slate_watch docstring quotes (b).
- Tests (tests/test_slate_run.py): #613's P2 day (the feed down at 12:15 ET with an 8 s probe, the NFL slate held for the NFL 13:00 closing with the HELD page owed, the MLB slate's miss paging, 30 s pages): the MLB 12:51 closing is queued at its T-35, 12:16:00; on #616's head it was queued at 12:17 (T-34).
- Docs: docs/CLI.md (closing-watch: (b) verbatim in place of "#613 P1-4, with the architect", the page bound's closing, (a) on the bounded send), the runbook's slate step, `closing-watch --help`.

## 2026-10-19 (#616: slate-followup-2 — ARCHITECT addendum 137 items 2(4) and 2(5), and #613's P1-1 to P1-3; Refs #613, #607, #602, #606)
- The rulings, verbatim (addendum 137 item 2): "(4) LATE after a one-tick wait — "LATE 1 min" is noise the ruling's words produce: the LATE line prints when the run's start is more than FIVE minutes after the due time (LATE_MIN = 5; the receipt keeps the exact seconds); a one-tick deferral or hold is not late. (5) a slate deferred by the one-run rule with no 15-minute window left before its family's first unstarted kickoff PAGES, by the HELD page's mechanism and bound, with the deferral as its reason — declared text: `SLATE <FAMILY> <date> HELD for the <FAMILY2> slate (one slate run per tick) — RUN BY HAND: <block>`. (4) and (5) are the NEXT small PR (slate follow-up 2)".
- deploy/hosting/closing.py (the slate stage; ops class, the closing runs unchanged):
  - **LATE_MIN = 5** (item 2(4)): `_slate_late` prints the LATE line when the run's start is more than five minutes after the due time (was: more than one cadence); a slate receipt keeps `late_seconds`, the exact seconds, beside `late_minutes`.
  - **The deferral page** (item 2(5)): `record_slate_deferred` pages `deferred_page_text` (the declared text) when no 15-minute window is left before the family's first unstarted kickoff (`_page_owed`, shared with the HELD page: once per family and day between the two), receipted on the deferral's line as `held_page`.
  - **The stage's pages go out after the whole stage** (#613 P1-1: a HELD page sent mid-stage reserved only its own send, and a later family's page in the same tick carried the next closing to T-34): `record_slate_hold` and `record_slate_deferred` queue the page on the tick (`slate_tick["pages"]`); `watch()` sends each after the stage, against a clock read again (`send_slate_page`: only where its bound ends before the first tick that could start the closing ahead; else it waits for a later tick and the line is receipted as a plain hold). A direct `slate_watch` (no tick) sends at once.
  - **The send is cut at NOTIFY_MAX_S** (#613 P1-2: the channels' timeouts are per socket operation, so `notify_failure` took 60 s against an ntfy that answered in pieces): `_bounded_notify` runs it in a daemon thread joined for 57 s; a send still running then is left to end with the process and the receipt says `cut_at_bound_s`.
  - **slate_order is read when the stage starts** (#613 P1-3: ordered at the tick's start, a family whose first game kicked off during the tick's closings still sorted first and took the tick's one run for its later games): `watch()` passes the clock after the closings; the dry run keeps the tick's time.
- Tests (tests/test_slate_run.py): the LATE boundary (07:05:00 on time, 07:05:01 late, `late_seconds` 300 and 301); the deferral page (16 minutes left: none; 15: once, the declared text, the next tick runs the slate and pages nothing); #613's P1-1 day (MLB 12:14, NFL 12:28 and 12:51, 40 s pages; laptop and host: the 12:51 closing queued at T-35 12:16:00 and paged by T-30; with instant pages the MLB miss pages first and the HELD page after the stage); a send blocked past a 0.2 s bound is cut and receipted; P1-3's day (NFL 12:35 closing at 12:00, PL 12:03 kicking off meanwhile: the NFL slate takes the tick). The P1-1 and P1-3 tests fail on main (0bc6220). The LATE expectations of four tests move to LATE_MIN.
- Docs: docs/CLI.md (closing-watch: LATE_MIN and `late_seconds`, the deferral page, the pages after the stage and the cut send, slate_order at the stage's start, and "so every family's slate runs" corrected to what holds today, #613 P1-4 being with the architect; coverage: the SLATE rule opens with "the file", not "the newest file"), `closing-watch --help`, the runbook's slate step (LATE_MIN, the deferral page, "the soonest first unstarted kickoff", the 134 1(i) quotation whole), closing.py's comments and docstrings (the LATE reading, "a later tick", slate_order's order), and the push-fail test comment quotes the 134 1(i) ruling.
- Not built (with the architect, #613): P1-4 (the one-run bound can cost a deferred slate its kickoff where main ran it in the same tick) and the P2 on the HELD page's test leaving out a feed-down MLB closing.

## 2026-10-19 (#607: slate-followup — ARCHITECT addendum 133 items 4-5, addendum 134 item 1(ii), addendum 136 item 2; Closes #602, #604, Refs #606)
- The rulings, verbatim. Addendum 133 item 5: "5. THE FOLLOW-UP PR (one, small, after #600 merges; Code's slot after the #598 fix round): items 2, 3, 4, 5 and 8 above — the HELD page, the LATE wording, the started-before-it names, the day's-file rule, the day's counts. Declared texts are in this addendum; the ledger entry quotes them." Addendum 134 item 1(ii): "#606 item 1, the host unit's 45-minute bound against a tick that also runs slates: option (b) — at most ONE slate RUN per tick (a slate that holds, misses or is superseded does not count; the next family's slate runs on the next tick, a minute later), so a tick is bounded as before plus one chain; the bound itself does not move. It goes in the follow-up PR of 133 item 5 (the host runs no slate before the cutover)." Items 2, 3, 4, 5 and 8 of addendum 133 item 4 are quoted whole in the ledger entry.
- deploy/hosting/closing.py (the slate stage):
  - **At most one slate RUN per tick** (`watch()` keeps `slate_tick`; `slate_watch(tick=)`, `_slate_under_lock(tick=)`). An attempt is the tick's run; a hold, a miss, a refusal, a supersession and the every-game-started miss are not. A lock that cannot be taken is a failed attempt but no run. A slate due after the tick's run waits for a later tick: `record_slate_deferred` receipts it once a day as a hold (`held: one slate run per tick: the <FAMILY> slate ran this tick (a later tick runs it)`, `deferred`: that family; no step, no attempt, no page), so the LATE line's first tick is the tick that first found it due. The families go in `slate_order`: the soonest first unstarted kickoff of the day first, a family that has failed an attempt that day last (the #602 review's P1s on 9c04c7f: in a fixed MLB, NFL, SOCCER order a later kickoff took the tick until the soccer slate missed its kickoff, and a retrying family took every tick). `--dry-run` marks the second `would RUN on a later tick (one slate run per tick: <FAMILY>'s first)`, adding `; on this tick if the MLB feed does not answer` after an MLB slate that checks its feed first. A direct `slate_watch` call (tick None) has no bound. `now` is read again after the stage's own probes, so `ran_at` is the run's start.
  - **The HELD page** (item 2): `record_slate_hold(games=, now=)` pages once per family and day, card and phone, `SLATE <FAMILY> <date> HELD for closing <FAMILY> HH:MM ET (T-35 HH:MM ET) — RUN BY HAND: block_<MMDD>_<family>_slate.txt` (`held_page_text`), when the slate is held and its family's first game not started kicks off within SLATE_GUARD_MIN (15 minutes). It goes out only where its longest send (`NOTIFY_MAX_S` = 57 s: the screen 15 s, the card topic 20 s, the operator topic 20 s, plus 2 s) ends before this machine's first tick that could start the closing it waits for (`next_tick`); else a later held tick sends it (the review's P1: a 20 s page on the no-probe hold carried the NFL closing from T-35 to T-34). The hold's line carries `held_page` {text, notified}, written then even when the hold for that closing is already receipted; the tick exits 3 (NOTIFIED).
  - **The LATE line** (item 3): `LATE <m> min: due HH:MM ET, first tick HH:MM ET, run HH:MM ET`, printed whenever the run's start (`ran_at`, read in whole seconds as the receipt keeps it) is more than one cadence (60 s) after the due time, whatever held it; `<m>` from the due time to the run's start; the first tick, the earliest `queued_at` of the day's slate and slate_miss receipts. `_slate_late(..., ran_at)`; the receipt's `late_minutes` and `late` follow it.
  - **The day's counts** (item 8): `slate_calls(doc, ids)` counts the rows of the ET day's games (every call kind, by name); `beyond_day(doc, ids, void)` the others, `· +<k> beyond the day` after the counts when k > 0 (`beyond_text`); a row of a VOID game of the day (`day_void_ids`: the MLB export keeps a postponed game's row) is in neither. The page and the console line say it; the receipt keeps the day's `rows` and `calls` and `beyond_day`.
- deploy/hosting/coverage_map.py (the SLATE line):
  - **Started before it** (item 4): a file counts when it holds a desk row for every game of the day whose kickoff is after its `exported_at`, and a row for at least one game of the day (tomorrow's file exported late tonight is no slate of today); the day's games it has no row for follow as `· started before it: <ids>`, and no gap is claimed. `slate.started_before` in the JSON. Of the files that count, the one holding the most of the day's games stands, then the newest (a freshen after a kickoff leaves the started game out; the morning file still holds it).
  - **The day's file** (item 5): a file counts only when exported on the ET day. The newest file exported before the day that would count but for its export day is `slate.older` {file, exported_at} (null when a file stands; a file exported after the day is neither), named first in the brackets of every NO SLATE FILE line: `NO SLATE FILE — slate run due HH:MM ET (newest exports/<file> exported <ET>, not today's)`; the gap is claimed. The success block line says `but no file of the day holds every game of the day`.
  - **The day's counts** (item 8): the competition's games of the day; `· +<k> beyond the day` (a void game's row in neither); `slate.beyond` in the JSON.
- tests/test_coverage_map.py, #604 (the test-order leak, ARCHITECT 2026-10-19, addendum 136 item 2: "cause read first (which state outlives the file), then the one-line fix in the leaking test"): src/db/database.py binds its SQLAlchemy engine once, at the first import of the module, from DATABASE_URL. test_coverage_map's first `coverage` call (`from cli import cli` inside the test, under the `env` fixture's DATABASE_URL) was that first import whenever the file ran before any other ORM user, so the engine stayed bound to that test's scratch DB, whose `competitions` table has no `sport` column, for the rest of the session: six tests of test_closing_runs.py then failed with `table competitions has no column named sport`. The fix: `import cli` at the top of the file, so the engine binds at collection under conftest's throwaway DB. Receipt, in that order: `pytest tests/test_coverage_map.py tests/test_closing_runs.py` → 202 passed (before the line: 6 failed, 196 passed).
- deploy/hosting/sp_receipts.py: the slate key line says `; +<k> beyond the day` and a hold's `; HELD page: <text>`.
- The failed push after the link, RULED (ARCHITECT 2026-10-18, addendum 134 item 1(i)): "a PUSH that fails after the link: the checked file stands in exports/ (it passed; the next push carries it; the retry replaces it) — no restore, as built." Quoted where closing.py, docs/CLI.md and the runbook had it open; nothing built.
- docs/CLI.md (the `closing-watch` and `coverage` rows, the coverage `slate` keys), docs/specs/h2-cutover-runbook.md (the slate stage), cli.py's `closing-watch` and `coverage` help (a HELD page exits 3), the closing.py and coverage_map.py docstrings: the texts above.
- tests/test_slate_run.py: one run per tick (the second family deferred, receipted once, run on the next tick on time; the dry run says so); a miss takes no run; the HELD page once, with the declared text, and none with a window left; the day's counts and `+1 beyond the day` (page, receipt, receipts table); the LATE text. Six tests that read late from the first tick now read it from the run's start (a retry, a run after a feed miss, after a lock miss, after a hold, a late wake, a lock wait ended at the guard), each with the LATE line; the held-tick probe test reads the deferred line and runs one tick longer. tests/test_coverage_map.py: the day's counts (+1 beyond), the started-before-it file, the older file on the due line, with the watch's notes, and on the block line; a successful slate whose file left out a started game now counts; which file stands and what it counts (the most of the day's games, then the newest; a void row; no older file named once one stands; a file exported after the day; `started before it` by row). tests/test_slate_run.py, the review's P1s: a HELD page never costs the next closing its tick (a 20 s page; the NFL closing queued at T-35); one slate run a tick goes to the soonest kickoff and every slate runs (MLB, NFL and PL on one day); a family retrying a failed slate does not take every tick; `slate_order`; the void row on the page.

## 2026-10-18 (#624: kalshi-476-regression — ARCHITECT addendum 127 items 3(a) and 3(b); tests only; Refs #476)
- The rulings, verbatim. Addendum 127 item 3(a): "(a) NO MLB MATCHER CHANGE (Branch 1). The out-of-step rule refused the one market a clock key would have misplaced; the cost is the one ruled on 10-12 ("while Kalshi has not settled yesterday's market of a pair, today's is refused"). Branch 2 is not built in any case: its own warning paragraph is decisive — a clock fixed at market creation identifies nothing about a game that moved. Refusals are never turned into guesses." Item 3(b): "(b) REGRESSION TESTS, a tests-only PR: the Saturday set verbatim (2 no-game-on-date + 2 behind), states A1 and A2, the Sunday shape (2 in play), the Friday control (4 placed), the ALCS tests unchanged — today's answers pinned whatever the receipt says."
- tests/test_kalshi_476_regression.py (new, 8 tests). Each test:
  - runs the real `python cli.py sync-kalshi` (the MLB closing's step 6, no dates) in process through click, on a scratch SQLite DB of its own;
  - replaces only the HTTP fetch (`KalshiAdapter._get`) and the sync's clock (`kalshi_sync.utc_now_naive`), and widens the console so that no line wraps;
  - seeds rows 50546, 50548 and 50550 (Tampa Bay Rays at Cleveland Guardians) as #476's cause read defines them;
  - pins the whole console, the exit code, the closing's failure reader (`closing.reported_failure`: none) and the Kalshi legs stored.
- What each test pins:
  - **The Friday control** (2026-10-16 23:25:59Z): matched 4. These are the four legs main stored, on the same rows (50548 ← 26OCT161800TBCLE, 50550 ← 26OCT172000TBCLE), captured at the run's clock. Addendum 130 item 1(c) has since found these rows crossed (#594); the test pins them as today's answer.
  - **The Saturday set** (the cause read's state B: 50548 moved to Sunday 21:00Z), at each of the three closing receipts' step-6 clocks (23:34:24Z, 23:36:21Z, 23:38:20Z): `matched 0 · unmatched 4 (of which ambiguous 0) · in-play skipped 0`.
    - 26OCT161800TBCLE is refused "no game of the pair on the ticker's date" (2) and 26OCT172000TBCLE "behind an event of the same two names out of step" (2), each with main's line.
    - The MATCHED ZERO alarm prints. The step exits 0 and nothing is stored, so 50550's newest legs are still Friday's.
  - **State A1** (50548 unmoved): 2 in play + 2 behind, the behind line giving the run's day as its only reason; `matched 0 · unmatched 2 (of which ambiguous 0) · in-play skipped 2`.
  - **State A2** (50548 postponed): the Saturday set's answer, with one unstarted game in the window.
  - **The Sunday shape** (2026-10-18 11:37:58Z, 26OCT172000TBCLE alone, its TB leg at 0.54/0.55), with 50550 finished or still scheduled: 2 in play. The sample line and the summary line are main's own of that morning, byte for byte.
- tests/fixtures/kalshi_476/ (new):
  - tbcle_markets.json holds the four markets' public fields and the one quote that the operator's relayed replay carries.
  - README.md says what is copied from the consoles and what the tests write themselves: stand-in quotes, which events are open at each clock, the order, the clocks.
- Not changed: every production file, `src/ingestion/kalshi_match.py` included; tests/test_kalshi_matcher_day_rule.py (the ALCS tests, unchanged: 114 passed on main 1e355f8).

## 2026-10-18 (#605: series-game-number — ARCHITECT addendum 130 item 2(b); Refs #476, #478)
- The ruling, verbatim (addendum 130 item 2(b)): "(b) THE RIGHT KEY IS THE SERIES GAME NUMBER, and it is a 2027 lane, not a patch: #478's lane ("before Opening Day 2027") gains it — KXMLBGAME postseason/series events match by game number: the k-th event of the pair by ticker date ↔ the row whose current seriesGameNumber is k; the date rule stays for the regular season (no numbering). Gate-class, with the ALCS 2026 set (849816/849817/849818 and the three events) as its fixture. DATA NOW, so the 2027 rule has it and so the reconciliation below has a receipt: the laptop's statsapi sync stores `seriesGameNumber`, `gamesInSeries`, `seriesDescription` and `rescheduledFrom` on the match row (additive columns by the unmapped pattern, like #588's; migration by hand after the backup). Code: one small PR, data only, no reader changes its behaviour."
- Built here: the DATA NOW sentence only. The 2027 game-number rule, the gate and the reconciliation read are not built here; no matcher, export, Desk or card reads the columns.
- Schema: nullable `matches.series_game_number` (INTEGER), `games_in_series` (INTEGER), `series_description` (VARCHAR(64)) and `rescheduled_from` (VARCHAR(32), ISO-8601 UTC `YYYY-MM-DDTHH:MM:SSZ`). They are NOT mapped in the ORM (the ORDER LINE note, as #588 did for `injuries.player_source_id`): every chain reads `matches`, and a mapped column would fail every query on a DB that has not migrated. src/db/database.py: `SERIES_COLUMNS`, `has_match_series` and `write_match_series` (guarded Core SQL, only when all four columns exist; the check is made per call on the writing session's connection, never cached).
- Migration `migrate_match_series_fields.py` (new): additive, idempotent (a column already there is left, the rest are added), behind the shared guard (`refuse_missing_db`, #524). It refuses with no `matches` table. Its receipt counts, per competition, the rows carrying each field and the rows carrying none. No backfill. Run order: any (backup first, by hand). Laptop: `python migrate_match_series_fields.py`. Host: the `--run-migrations` line `sp_deploy.py` prints.
- src/adapters/mlb_stats_api.py: `series_fields(game)` reads the game's own four fields from its /schedule entry; each parsed game carries them on `NormalizedMatch.series` (new optional field, src/adapters/normalized.py; None on every other adapter). Each field is read as the entry gives it: a number is never read from text and a text is never trimmed. A field the entry does not give, or gives in a shape it does not read, is None (law 4): a number given as text or as a decimal, a true/false, an empty or blank text, a time with no zone or with spaces around it. `rescheduledFrom` is stored in UTC with a Z.
- src/ingestion/service.py `sync_matches`: after the flush, each row the listing wrote gets its own entry's four fields (NULL where that entry has none), never another game's. A game listed twice in one answer keeps its last entry's fields, the one its status and kickoff were last written from. A no-op before the migration; the run logs `series fields stored on N row(s)`. The api-sports fallback (`mlb_apisports.sync_matches`, the host's MLB path) never reaches this code and writes none.
- docs/CLI.md: the `sync-matches` row.
- tests/test_match_series_fields.py (new, 16), on the ALCS 2026 set of addendum 130 item 1(a):
  - the adapter: 849818 Game 3 of 7, 849816 Game 4 of 7, 849817 Game 5 of 7 with `rescheduledFrom` 2026-10-17T00:00:00Z, and NULLs for a regular-season game without the fields; shapes it does not read are None (a quoted number, a padded time), a text is stored untrimmed; only statsapi carries the field.
  - the ORM never names the columns.
  - `sync-matches` after the migration stores each game's own fields on 50546 / 50550 / 50548; a field a later entry drops is NULL, and rows not listed are untouched; a game listed twice keeps the entry its status and kickoff come from, both orders.
  - before the migration the sync writes its rows and nothing else; migrating fills nothing (no backfill); the next sync fills them.
  - the api-sports fallback leaves the fields as they are on a row it links and NULL on a row it creates.
  - no reader changes: the MLB predictions export with the Desk's calls, the results export, the window card and `kalshi_match.place` on the stored games give the same output before the migration and after the four fields are stored. tests/test_kalshi_exec_mlb_soccer.py's export test, unedited, passes on a migrated DB where a trigger gives every match row it inserts all four fields.
  - the migration: additive, idempotent and receipted; a partly migrated DB gets the rest; it refuses without the table and with no database file.

## 2026-10-18 (#600: slate-run — ARCHITECT addendum 126 items 1-2; #590)
- Addendum 126 items 1-2 (ARCHITECT 2026-10-18 08:30 ET), verbatim:
  > 1. THE RULE, VERBATIM (operator): "We need predictions generated ahead of the first game of every game day with a sync, no matter whether it's on the host or laptop. If it's not on the HOST, you need to alert me to run these things manually." Adopted as doctrine. Today's two misses are the receipt: NFL had 12 rows in the database since Thursday and no file until block_1018_nfl_slate.txt (08:30 ET); MLB has its row and no file (block_1018_mlb_slate.txt, 13:30–14:30 ET, VPN mode). Yesterday's PL slate was the same class. The coverage command said "rows present" and was right; "rows" is not the deliverable — a FILE with Desk calls, on the mirror, before the first kickoff, is.
  >
  > 2. THE MECHANISM — THE SLATE RUN (Code, the first slot today, ahead of the Today tab; ops class, non-gate; exports contract unchanged; the Desk unchanged):
  > (a) The closing watch (deploy/hosting/closing.py; the laptop's now, the host's after the cutover) gains a SLATE stage per closing family per ET game day: due at the first kickoff of the day minus 150 minutes, or at the watch's first tick after 06:00 ET when that is later; one run per family per day; it runs the family's prematch steps exactly as the closing run resolves them (sync-matches for the day's ids, odds, injuries/pitchers/lineups as the family has them, Kalshi, predict, then the slate export WITH --desk to the family's slate file in exports/ — nfl_predictions_<date>.json, mlb_MLB_<date>.json, soccer_PL_<start>_to_<end>.json — never the closing's logs/ path), pushes the mirror, and PAGES, card and phone: "SLATE NFL 2026-10-18: 12 rows · PLAY 1 · PASS 11 · exports/nfl_predictions_2026-10-18.json". A failed step pages "SLATE NFL FAILED: <step> — RUN BY HAND: block …" the way a closing failure pages today, attempts 3 like the closing. The closing runs at T-35 are unchanged; the slate is the morning file, the closing is the row that counts, exactly as today's coverage legend says.
  > (b) `coverage` gains a SLATE line per LIVE competition: the newest exports file of that family's slate kind that covers EVERY game of the day by match id, with its exported_at and its PLAY/PASS counts; else "NO SLATE FILE — slate run due HH:MM ET" (or, where the watch is not the machine, "— run block"). Its gap line in capitals: "NFL: 12 GAMES, ROWS 12, NO SLATE FILE". `coverage --json` carries it; the Today tab shows it first.
  > (c) Receipts the watch writes: `kind: "slate"` lines beside the closing lines, with family, date, rows, calls, file, exit; the morning page reads them as it reads the closing lines.
  > (d) Before the cutover the laptop is the machine for every family (its watch runs every minute while it is awake; a laptop asleep at the due time means the first tick after waking — the page says the run was late, with the minutes). After the cutover the host's watch does it for SOCCER and NFL (the fence lifts), and MLB stays the laptop's to the season's last game. The host's fixed-time timers (nfl-predict Sun 14:00Z — AFTER a 9:30 ET London kickoff) are retired by the cutover PR; they are not fixed by hand this week.
  > (e) Test: a synthetic day with one family's games at 09:30 and 13:00 ET: the slate is due at 07:00, runs once, writes the slate file with desk blocks, pages once; the closing groups still run at 08:55 and 12:25; a second tick does not re-run the slate; a failed export pages the RUN BY HAND text and names the block.
- deploy/hosting/closing.py: the closing watch gains a SLATE stage (item 2(a)), after its closings, per family per US Eastern day: due at the first kickoff less 150 minutes, or at the first tick after 06:00 ET when later; one run a day from the receipts (kind `slate`), three attempts; the closing's chain lock and backup; the closing chain's steps as `resolve_steps` resolves them for the day's games, word for word, the export `--desk` at the closing's own `--out logs/<run id>.<name>` (SOCCER's adds its `--start`/`--end` window), linked into the family's slate file in exports/ once its checks pass (`nfl_predictions_<date>.json`, `mlb_MLB_<date>.json`, `soccer_PL_<start>_to_<end>.json`, SOCCER's window soccer-prematch's for a Saturday to Tuesday day, the midweek override's form (the day to the day + 3) for a Wednesday to Friday day); then the mirror push, then one page: `SLATE <FAMILY> <YYYY-MM-DD>: <N> row(s) · PLAY <p> · PASS <q> · exports/<file>` (a late run adds `LATE <m> min: due HH:MM ET, run HH:MM ET`). A failure pages `SLATE <FAMILY> FAILED: <step command> — RUN BY HAND: block_<MMDD>_<family>_slate.txt · attempt k/3`. Misses (kind `slate_miss`, once a day and reason): the MLB feed unreachable, the lock held through a 5-minute wait, every game started. The family refusal (SP_SKIP_FAMILIES) writes no slate and pages nothing. The closings at T-35 are unchanged (pinned).
- deploy/hosting/coverage_map.py: a SLATE line under each LIVE competition (item 2(b)): the newest exports/ file of the family's slate kind covering every game of the day by match id, its exported_at and PLAY/PASS counts; else `NO SLATE FILE — slate run due HH:MM ET` (`— run block <block>` where this machine refuses the family), and the gap `<CODE>: <n> GAMES, ROWS <r>, NO SLATE FILE`. coverage() carries it as `slate`. Unparseable files are skipped with a reason.
- The closings first (item 2(a): "The closing runs at T-35 are unchanged"): a slate does not start while a closing the watch will still run, for any family of the tick, has its T-35 within 15 minutes (`SLATE_GUARD_MIN`) or already past, and its wait for the chain lock ends 15 minutes before that T-35; held, it runs after the closing, each closing it waits for receipted once (kind `slate`, `held`), so the newest hold names the closing it waits for now. A closing that cannot start holds no slate: while the MLB feed does not answer an MLB closing is a miss, never a run, so the guard reads the feed's answer when an MLB closing would hold a slate and, unanswered, reads the other families' closings (an on-time MNF slate had been held to kickoff and missed); an MLB slate checks its own feed before the guard (its RUN BY HAND miss at once). A closing due by the next tick holds a slate with no probe where a probe could not release it or could cost that closing its T-35 (a closing with no feed; an MLB closing the tick's feed answer says starts; with no answer, a closing with no feed due by then too, or one probe, 8 s plus 2, that could reach the first tick that could start that closing: this machine's first firing at or after its T-35, the host's whole minutes or the laptop's launchd phase); otherwise the slate stage probes once, at most once a tick, none when the tick's closings did. A held tick's probes had carried the next tick past the next closing's T-35 (an MLB closing queued at T-34.0; pinned at T-35.0, and at the laptop's :17 phase); a no-probe hold for an MLB closing the feed could not start had held a slate past a kickoff (the PL 14:30 game lost from it; pinned: the slate runs at 14:29:30 with it, one probe), and on the laptop's :52 phase, where the hold's bound was the next firing of either cadence, not the first that could start the closing (pinned: the slate runs at 14:29:47 with it, one probe; feed up, the MLB closing is queued as with no slate stage). The dry run leaves out its own tick's closings (`would RUN if they end before HH:MM ET, else held: …` where a closing after them could be inside the guard by then) and shows an MLB closing ahead both ways, with when it holds with no probe after closings that leave no feed answer (`(held with no probe if they end within 10 s before a tick at or after HH:MM ET)`, its T-35). The closings and closing misses are unchanged (pinned on a moving clock, feed down from 17:30, slate stage on and off). A hold, a refusal and a superseded line carry item 2(c)'s keys (rows, calls null). Late (item 2(d)) is judged on the first tick that found the slate due (the earliest `queued_at` of the day's slate and slate_miss receipts), so a run held for a closing or delayed by a miss on an on-time tick is not late. Every attempt's receipt line carries the declared keys, a lock that cannot be taken included. coverage's SLATE line reads the watch's slate receipts (item 2(c)): with no file, three attempts, a success or every game started name the block (`— run block … (<why>: the watch runs it no more)`; the every-game-started miss only while no game of the day is unstarted, a re-dated game being slated on the next tick); a failed attempt, a miss or a standing hold (`held since HH:MM ET (<closing>): the slate runs after it`, only while that closing is one the watch will still run: a hold for a closing done, started, inside T-5 or out of attempts drops out) is said beside the due time. The docs say what the staging does (addendum 133 item 3(a)): a failure at a step, a check or the link leaves exports/ as it was; a page that fails after the push leaves the file standing (it passed); a push that fails after the link leaves the checked file in exports/ (as built, the ruled order; open for the architect).
- deploy/hosting/sp_receipts.py: key lines for kinds `slate` (a hold included) and `slate_miss`; a slate miss counts as failing.
- The fix round (ARCHITECT 2026-10-18 16:10 ET, addendum 133 item 3; the fourteen open items ruled in item 4, recorded in the ledger entry; follow-up lane #602, limitation #601):
  - (a) STAGING: the slate's export step keeps the closing's own `--out logs/<run id>.<slate file name>` as `resolve_steps` gives it (SOCCER still gains `--start`/`--end`; nothing else is inserted). Once the checks pass (the file is this run's, carries desk_meta, holds every game of the day unstarted when the steps finished), the kept file is linked into `exports/<slate file>` by the closing file's own write (`place_file`, factored out of `write_closing_file`: a hard link to the temporary name, then the rename over the name), receipted `slate_file` {file, sha256}, the logs/ copy kept; then the push; then the page. A failure at a step, a check or the link leaves nothing in exports/ and pushes nothing; an earlier good file of the same name stays byte for byte; a link that fails is a failed attempt (`exports/<file> not linked (<error>)`). A push that fails comes after the link, so its checked file stands in exports/ as a page failure's does (as built; the ruling names only the page: open for the architect). The sentence "a file a failed attempt leaves in exports/ goes to the mirror with this machine's next push" is gone from the docs.
  - (b) coverage's SLATE line: a file of the family glob with no `predictions` list (a results export, `mlb_MLB_results_<date>.json`, `soccer_PL_results_<date>.json`) is another kind: no candidate, never listed as skipped.
  - (c) The success page counts rows by number: `1 row` on a one-game day, `2 rows` (the receipt's `rows` unchanged); the receipts table's slate key line (sp_receipts) reads the same (`1 row, PLAY 0, PASS 1`).
  - The verifiers' round on the fix: a second slate whose kept export path already exists (two watch processes entering in one UTC second share the run id `<now>-<family>-slate`) is refused under the lock before the backup and every step, receipted and notified, no attempt (#442, addendum 44 item 8: "Nothing a run kept is opened for writing a second time"; before, it wrote in place into the first attempt's kept file, which after the link is the exports/ file, and left a half-synced file there). `closing-watch --dry-run` ends a slate's plan with the exports/ file the run links (`then, once its checks pass: logs/RUN.<name> linked into exports/<slate file> · then the mirror push (--label slate) · then the page`; SOCCER's is the round's window file, which the steps alone did not name).
- docs/CLI.md (closing-watch and coverage rows), cli.py help, docs/specs/h2-cutover-runbook.md step 5b. Ops class, non-gate: the exports contract and the Desk are unchanged; the host units and timers are untouched.
- Tests: tests/test_slate_run.py (new), tests/test_coverage_map.py (the SLATE line), tests/test_closing_runs.py (the fixture keeps the slate stage off for the closing tests).

## 2026-10-18 (#598: history-identity-hold — ARCHITECT addendum 127 item 3(c), addendum 130 item 2(c), addendum 132 items 3 and 4, addendum 134 item 3; Refs #476, #594)
- The rulings, verbatim. Addendum 127 item 3(c): "(c) THE HISTORY PATH GETS AN IDENTITY HOLD (Code's "In short" 6 — the finding that matters most, because it is PERMANENT): `kalshi_history.place_events` places each event alone and a stored ticker is never re-placed, so once 26OCT172000TBCLE settles, the next pull stores Sunday's settlement and candles on Saturday's row for good. RULED: for a clock series, an event whose pair has an earlier-dated event of the same two names that is unsettled, or is out of step on its own date, is NOT placed by date; it is stored with match_id null and a reason of its own ("identity hold: earlier event <ticker> of the pair unsettled/out of step"), and — the one exception to "inserted once" — a HELD row (match_id null with that reason) is re-read by a later run and placed when the hold clears. Nothing already placed is ever moved by the ingest. Gate-adjacent (K-track data; the shared matcher untouched): one PR, with the history dry run on the TBCLE pair before and after as its receipt." Item 3(d): "(d) INTERIM, from today: the KXMLBGAME history pulls run with `--until 2026-10-14` ONLY until (c) is merged — the October series pairs are not touched by the ingest before the hold exists. The other four series are unaffected. The pulls block for tomorrow carries it." Addendum 130 item 1: "1. THE RECEIPT, in three lines." "(a) statsapi (read-only, Phase 2): gamePk 849818 = our 50546, Game 3, Oct 15, Final 2-3. gamePk 849816 = our 50550, played Oct 17 20:08 ET, Final Rays 7-3, now **Game 4 of 7**. gamePk 849817 = our 50548: the Oct 16 game, POSTPONED, rescheduled to Oct 18 21:08Z, now **Game 5 of 7** (rescheduledFrom 2026-10-17T00:00Z). MLB kept the gamePks and renumbered the games by play order." "(b) Kalshi (the morning pull, already stored at 03:24Z with match_id null): KXMLBGAME-26OCT161800TBCLE — "the game originally scheduled for Oct 16" — SETTLED at 03:20Z today, Tampa Bay YES, Cleveland NO: that is Saturday night's result (Rays 7-3, our 50550). KXMLBGAME-26OCT172000TBCLE — "originally scheduled for Oct 17" — is still OPEN (status active, expected expiration 03:00Z passed, close 10-21), quoting 54/55 this morning: that is Sunday's game (our 50548)." "(c) So Kalshi's Friday event settled on the game MLB now calls Game 4 (played Saturday), and Kalshi's Saturday event tracks Game 5 (Sunday). Kalshi's operational identity is the SERIES GAME NUMBER — the k-th event of the pair, by ticker date, is the k-th game by current seriesGameNumber — whatever its rules text says about "the game originally scheduled". Ours is the gamePk. After an in-series postponement the two cross. The four legs captured Friday 23:25Z sit on the wrong rows: 26OCT161800 belongs to 50550, 26OCT172000 to 50548. #476's mechanism, now a receipt, not a hypothesis." Item 2(c): "(c) THE HISTORY IDENTITY HOLD (127 item 3c) STANDS and gains its second half: a ruled RE-PLACE. `kalshi-history place-held --ticker TICKER --match-id N --ruling "<addendum>"` sets match_id and side on a row that has match_id null and the hold/refusal note, appends the ruling to its note, and fetches its candles then — a reviewed command, never a guess by the ingest. The first two uses, by this ruling: 26OCT161800TBCLE-TB and -CLE → 50550 (Game 4; TB yes agrees with Rays 7-3). The third, after tonight's settlement: 26OCT172000TBCLE-TB/-CLE → 50548 (Game 5). Nothing already placed is moved by the ingest; the Game 3 rows (26OCT151800 → 50546) are right and untouched." Item 2(d): "(d) INTERIM (127 item 3d) STANDS: KXMLBGAME history pulls `--until 2026-10-14` until (c) is merged."
- The fix round, verbatim (ARCHITECT 2026-10-18 13:55 ET, addendum 132 item 3): "(a) `place-held` after a candle call that fails (a 5xx, a 408, a transport error, a third 429, an answer with no list): WRITE NOTHING, say why, exit 2 — the operator re-runs. As built it stores the placement with a null quote and nothing ever reads that row's candles again; "fetches its candles then" means the quote lands with the placement or the placement does not land. (The ingest's own rule for the same failures is store-nothing; the command follows it.)" "(b) The in-run claims rule reads a STORED row by its stored (match_id, side), never by re-placing it by date. Code's own open question: once place-held makes a stored placement differ from the date placement, a stored row could refuse a new market on the side its date names while it sits on another game. Stored rows enter the claims rule as stored; only the run's new markets and the held rows it places are placed by date." "(c) THE BOUND ON "EARLIER-DATED" (Code's first open question): an earlier event of the pair binds only when its ticker date is within 10 days before the event's date. A series never spans more than that (a seven-game series runs nine days); a regular-season rainout in May would otherwise hold every later event of the pair for the season. Inside the bound, held rows that the hold never releases are placed by ruling — that is the cost this season; #478's 2027 lane (the series-game-number key, with seriesGameNumber stored from now) retires the manual step." Item 4, RULED: "(a) The open-list read for "unsettled": approved as built. (b) No candles for a held row: approved. (c) place-held's two refusals beyond the ruling's words (another competition's match; a side another row of the series holds): approved — conservative, and the ingest refuses the same state. (d) The claims rule's scope as built (clock series, and ruled rows on any series; a date-only series placed as main places it): approved — the NCAA day-off twins are the tiebreak PR's. (e) A CLOSED-but-unsettled earlier event (in neither settled list nor the open list) can let a later event be placed by date for good: a narrow window, real; Code's proposal — list the series' closed markets too, for the hold only — is approved as its OWN small follow-up PR, not a hold on #598. (f) place-held's side refusal may block the NCAA re-match: the tiebreak PR proposes the re-match's mechanics (it may need to retire a day-off twin's placement first, by ruling); place-held's refusal stands."
- The 3(b) ruling, verbatim (ARCHITECT 2026-10-18 19:58 ET, addendum 134 item 3): "#598 — RULED: 3(b) is OPTION (ii). My words aimed at a PLACED stored row ("never re-placed by date"); a refused stored row has no stored side, and a refusal that becomes a placement on the next run is exactly the guess CLAUDE.md forbids. So: only a stored row that HAS a placement enters the claims rule by its stored (match_id, side); a refused stored row keeps its date claim in the across-events rule, as on main. R1, R2 and R6 come in as regression tests."
- src/ingestion/kalshi_history.py (`kalshi-history`): THE IDENTITY HOLD (addendum 127 item 3(c)). On a clock series (a ticker that carries a clock; KXMLBGAME of the five), an event whose pair has an earlier-dated event of the same two names that is unsettled, or out of step on its own date, is not placed by date. Its markets are kept with match_id and side null and the ruled reason, `identity hold: earlier event <ticker> of the pair unsettled` / `... out of step`, and no candles are fetched for them.
  - Out of step is the matcher's own rule (addendum 54 item 6), read by `kalshi_match.behind_out_of_step` itself with the clock before every game (`identity_holds`): no game of the pair's two teams on the event's date, US Eastern. A numbered event is never out of step itself. kalshi_match.py is unchanged.
  - Unsettled is listed open by the exchange. A run that lists a clock ticker also lists the series' open markets (`/markets?status=open`, the live sync's own call), for the hold only. They are never placed or stored, and a cut in that list stores nothing, as for the other lists. The listed line counts them apart. An event closed but not yet settled is in no list read, so it holds nothing under either half and a later event of its pair is placed by date. Ruled (addendum 132 item 4(e)): listing the series' closed markets for the hold is its own small follow-up PR, not a hold on this one: Issue #603 (the lane).
  - The earlier events are every event of the pair the run knows of: both settled lists whole (not only `--since`/`--until`), the stored rows of the series, and the open list. **The bound (addendum 132 item 3(c)):** an earlier event binds only when its ticker date is 1 to 10 days before the event's date (`HOLD_BOUND_DAYS`); 11 days or more binds nothing, so a regular-season rainout no longer holds the pair's later events for the season.
  - As for the live rule's "behind" (addendum 55 item 3), the hold is for a market that would otherwise have been placed. A market the matcher refuses keeps its own reason. A held market claims no game.
  - The claims rule reads the stored rows too (a verifier's P2 on this branch): a market the run would write (a new row, or a stored held row whose hold cleared) placed on a side a stored row of the series holds under another ticker is refused under the matcher's reason (`two markets claim one side of one game`), and the stored row is not moved. place-held refuses the same state. Without it, a held row whose hold cleared was placed by date on the side a row placed by ruling held, and one side of one game carried two settled markets. A held row refused so is left as stored; the receipt names the stored row (`match 50548 AWAY is stored on ...`). A new row is stored refused, with a `✗ match ... stored on ...` line.
  - That read of the stored rows covers a market whose ticker carries a clock, and, on any series, a side a row placed by ruling holds (`placed by ruling:` in its notes). A date-only series is otherwise placed as main places it, run by run (a second verifier P2: the rule had reached every series, and refused NCAA's own-date event 26OCT17FLATEX across runs once a run with `--until 2026-10-16` had stored its day-off twin 26OCT16FLATEX). The cross-run day-off twin is the NCAA tiebreak's (addendum 130 item 3(b)). On a scratch DB, 40 cross-run scenarios over NCAA, NHL, NFL and PL stored and printed the same as main (on b75acb8, before addendum 132 item 3(b)).
  - **A placed stored row is read as stored (addendum 132 item 3(b), option (ii) by addendum 134 item 3; option (c) by addendum 137 item 1).** The claims rule across the events read every listed market's date placement, stored rows included, so a stored row placed by ruling on 50548 also claimed 50550, the game its ticker date names, and refused a new event placed there by date. Now a stored row listed in range that holds a placement is placed with its event (so the event is placed on all its legs) and is never placed or moved itself, and it claims its stored match_id and side in the stored-rows read. RULED, addendum 137 item 1, option (c), verbatim: "A placed stored row NOT placed by ruling claims both its stored side and the side its date names; a row placed by ruling claims its stored side only, so 3(b)'s motivating case stands. The principle that decides it: this head's refusals must be a superset of main's, the one designed exception being a ruled row. (c) only adds refusals; both shapes are refused as on main; the two regression tests fail on 64787b0." So a row placed by ruling claims its stored side only (`place_events` leaves it out of its placements and its claims), and every other placed stored row also claims the side its date names, in the across-events rule, as on main. A refused stored row has no stored side: it keeps its date claim, as on main, and is never written again. (Read as worded, option (i), a refused stored row claimed nothing, and a refusal became a placement on a later run: R1, R2 and R6 below.) Against main, this head's placements only become refusals, never the reverse, except where a ruled row's side differs from its date's (3(b)'s own case). On 64787b0 (option (ii) alone) the reverse also happened where a placed stored row's stored side and date side disagree without a ruling (a game re-dated, home and away corrected): its date side was claimed by nothing, so a market main refuses was placed there (half an event on a home/away correction; the day-off twin after a re-date). The two regression tests, `test_c_a_placed_stored_row_claims_its_date_side_too_after_a_home_away_correction` and `test_c_a_placed_stored_row_claims_its_date_side_after_its_game_is_re_dated`, fail on 64787b0 and pass on this head, refusing both shapes as main does. The receipt line names the stored row (`✗ match N SIDE: stored on <ticker> (nothing already placed is moved); <ticker> claims it too: refused`), and the matcher's line counts every claimant as main's does and names the stored one after them (`N markets of N events claim it (...): all refused; stored on <ticker> (nothing already placed is moved)`).
  - The one exception to "inserted once": a stored held row (match_id null with the hold's reason) is read again by every run that lists it in range. When the hold has cleared and the matcher places it, it is written in place: match_id, side, source, fetched_at and the quote, its candles fetched then on the stored kickoff, and `hold cleared <time>: placed by the ingest` appended to its notes. Held again, or cleared but refused by the matcher, it is left as stored. A row with a match_id, or refused for any other reason, is never read again. The write checks each row is still a held row, and that no other row of the series holds its side (as place-held checks it); either failing, the row is left as it is and the receipt says why.
  - The receipt: an `identity hold` line (new rows held, stored held rows held again, stored held rows placed, and cleared-but-refused when there are any), one `⏸` line per held event naming the earlier event and the matcher's words, and the no-candles count for held rows.
  - NFL, NHL, NCAA and the soccer series are unchanged (no clock in their tickers): no hold, no open list, and no read of a stored row's side except a side a row placed by ruling holds or a placed stored row listed in the run holds (addendum 132 item 3(b); addendum 134 item 3).
- `kalshi-history place-held --ticker T --match-id N --ruling "<addendum>"` (addendum 130 item 2(c)), `place_held`: the ruled re-place.
  - It refuses (exit 2, nothing written) unless: the ruling is not empty; the row exists with match_id null and a hold or `refused by the matcher:` note; the match exists in the series' own competition; its two teams are the event's two names one each (`kalshi_match.fit`, from the event's stored rows); the side can be told (the market's yes team against the match's home and away; a Tie leg is DRAW); and no other row of the series holds that side of that match.
  - It then runs the backup check, then reads the candles on the match's stored kickoff by the ingest's own call (`candle_call`; a 429 is asked again as the ingest asks it).
  - **A candle call that fails for now writes nothing (addendum 132 item 3(a)).** A 5xx, a 408, a transport error, a third 429 or an answer with no list ends the command with one line, `REFUSED: the candle call <path> failed (<why>; 429 retries: N): nothing is written (the quote lands with the placement or the placement does not land, addendum 132 item 3(a)); run it again`, and exit 2, dry or not. The row stays as stored, and the operator re-runs. Before, it stored the placement with a null quote, and nothing ever read that row's candles again.
  - A candle call the exchange refuses for good (a 4xx other than 408/429, `_refused_for_good`, as the ingest reads it) is not in the ruling's list. It keeps the as-built placement with a null quote and the status in notes, as the ingest stores such a market. A window that cannot be read is the same. The quote stored before was read on the ticker's clock, not on this kickoff.
  - Notes: the stored notes, then `placed by ruling: <ruling>`, then what the candles said. fetched_at becomes the placement's time. It prints the row before and after and writes that one row only.
  - The write takes `--backup PATH` (the dedupe-matches gate, `_verify_backup`: the backup's `kalshi_settled_markets` count must equal the live DB's). `--dry-run` makes every read and writes nothing.
- cli.py: `kalshi-history` becomes a click group that runs the pull when called with no subcommand. Every existing invocation (`kalshi-history --series S [--since] [--until] [--dry-run] [--max-calls N]`) is unchanged. `--series` is checked by hand ("Missing option '--series'.", exit 2), and the pull's options given in front of `place-held` are refused.
- src/db/schema.py: the KalshiSettledMarket docstring states the exception, the 10-day bound and place-held (nothing written on a candle call that fails for now). No column changes and no migration.
- docs/CLI.md: the `kalshi-history` row (the hold, the 10-day bound, a placed stored row read as stored, a refused one keeping its date claim) and a `kalshi-history place-held` row (exit 2 on a candle call that fails for now).
- tests/test_kalshi_history_identity_hold.py (new, 51):
  - The hold on the TBCLE pair (out of step; unsettled), the receipt's lines, a date-only series untouched, a placed row never moved.
  - A held row placed by a later run once its hold clears; held again or cleared-but-refused left as stored; a row refused for another reason not read again; the open list cut short stores nothing.
  - The claims rule across the stored rows: a cleared held row, and a new row, placed by date on the sides a row placed by ruling holds are refused and the ruled row unmoved; a side taken during the run is read again at the write.
  - The rule's scope: on a clock series a date-placed stored row refuses a new market on its side; on NCAA the own-date event 26OCT17FLATEX is placed across runs beside its stored day-off twin, as main places it; a side a ruled row holds on NCAA still refuses.
  - Addendum 132 item 3(b): 26OCT172000TBCLE, placed by ruling on 50548, no longer refuses 26OCT172010TBCLE placed by date on 50550 (the side its ticker date names), and still refuses 26OCT181708TBCLE on 50548's sides. A date-only stored twin listed beside its own-date event still refuses it, as main does.
  - Addendum 134 item 3, R1, R2 and R6 (a refused stored row keeps its date claim): R1, a cleared held row and a new event both claim 50550 and are refused, and the next run, nothing changed, writes nothing; R2, a leg whose candle call answered 503 is refused on the next run beside its stored claimant; R6, NCAA, the day-off twin 26OCT16FLATEX listed beside its own-date event stored refused (the game synced late) is refused, as main refuses it. Each fails on 5e1ad9e (3(b) as worded) and passes on 99261b9 and on this head.
  - The claims line names a stored claimant beside two new ones (a verifier's P2 on a17a133): fails on a17a133, passes here.
  - Addendum 132 item 3(c): an earlier event out of step 10 days before binds, 11 days does not, and a rainout's shape 30 days before does not; the same for an earlier event listed open at 10 and 11 days.
  - place-held: the first two and the third uses, a 429, the dry run, the guard's order, each refusal, the sides on the match's own home/away. The command's backup gate; the pull's invocation kept; kalshi_match.py names no hold.
  - Addendum 132 item 3(a): each failure for now (5xx, 408, transport error, third 429, no list) writes nothing and refuses with the call and the failure, dry or not; the command exits 2 on it with the one REFUSED line; a 404 keeps the as-built placement with a null quote.
  - The 77 tests of test_kalshi_history.py and test_kalshi_history_probe.py are unchanged and pass.
- The receipt (scratch DB, synthetic markets): before, main stores 26OCT172000TBCLE on 50550; after, it is held behind 26OCT161800TBCLE, out of step.
- **The real dry run on the TBCLE pair is an operator block (any mode).** This session's proxy refuses Kalshi's host. Run it once 26OCT172000TBCLE has settled; a dry run writes nothing.
  - Before, on main: `python cli.py kalshi-history --series KXMLBGAME --since 2026-10-15 --dry-run`
  - After, on this PR's head: `python cli.py kalshi-history --series KXMLBGAME --since 2026-10-15 --dry-run`

## 2026-10-18 (#596: readiness-mlb-binds — an MLB line on the host's list binds NOT-YET; the readout runs on the host; the intl verifier pins its role; hosting-h1 T9 installs over the list; ARCHITECT addendum 128 items 1(a), 1(b), 4; Refs #591, #593)
- **Rulings (ARCHITECT 2026-10-18 10:00 ET, addendum 128), verbatim:**

> (a) WHICH MACHINE RUNS `cutover-readiness`: the HOST, over ssh in the Thursday evening block, so (b) and (T9) read the host's own receipts and list; the laptop form (`--receipts FILE --fullseason-list FILE`) is for my dry reads only and is labelled as such on the page.
>
> (b) AN MLB LINE ON THE HOST'S LIST BINDS: NOT-YET, with the line named. The ruling excluded MLB; a list that carries it is wrong, and a readout that prints a warning and says GO is softer than the rule. Not a hold on #587 — it rides the small follow-up PR in item 4 (one condition, one test).
>
> 4. #591 (the intl verifier fails 3/8 with no role set) — approved as proposed: the verifier pins SP_EXPORTS_MIRROR_ROLE=laptop for its own process and says so in its header. #593 (hosting-h1's T9 `tee -a` duplicates on a re-run) — the docs fix as proposed (write to a temp file, print, install over the list). OPERATOR: block_1018_t9_host.txt is NEVER re-run; today's one run wrote the 26 lines once, and a second run would double them and the chain would sync each competition twice. If the list ever needs regenerating, I write a fresh block that installs over the file. One small PR carries #591 + #593 + item 1(b): tests/docs/one readout condition.

- deploy/hosting/cutover_readiness.py (item 1(b)): an MLB line on the (T9) list binds. The `⚠ MLB line(s) listed: …` line now ends "an MLB line binds: NOT-YET (addendum 128 item 1(b))" (before: "printed, not binding (whether it binds is the architect's ruling)"), and the unmet list names every MLB line: `(T9) MLB line(s) on the list: MLB|2026`. Before, a list carrying MLB could read GO. What counts as an MLB line is unchanged (`MLB`, `MLB_<kind>`, any case). The module docstring says so, and says which machine runs the readout (item 1(a)); the `--receipts` and `--fullseason-list` help strings label the laptop form.
- scripts/cockpit_intl_verify.py (#591): the verifier sets `SP_EXPORTS_MIRROR_ROLE=laptop` for its own process, before anything that reads the role is imported, and points `SP_HOST_ENV` at a path that does not exist, so no host.env decides first (`desk_policy.role_reading` reads host.env, then the environment, then the checkout's .env). tests/conftest.py pins the role the same way. The path is `scripts/.no-host.env`, never created (the way tests/conftest.py's no-host.env is never created), so no run or import leaves a temp directory behind. Its header says so. Before: with no role set (no .env: a fresh clone, CI, a cloud container) the host fence (#410) made every INTL row PASS `host_fence`, and the verifier passed 3/8. Now 8/8 with no role set, and 8/8 with `SP_EXPORTS_MIRROR_ROLE=host` exported.
- docs/specs/hosting-h1.md T9 (#593): the command writes the list to a temp file (`mktemp`), prints it, then installs it over `/etc/sports-predictor/fullseason.list` with install.sh's own owner, group and mode (`-o root -g sp -m 0640`), in a subshell whose EXIT trap removes the temp file, so a failing step fails the block and leaves the list as it was (Codex review on #596). Before, it ended `| sudo tee -a`, which kept the installed example's comment lines and, on a re-run, wrote every line again. The query and the MLB paragraph are unchanged. The step quotes the ruling, including the operator line that block_1018_t9_host.txt is never re-run.
- docs/specs/h2-cutover-runbook.md (item 1(a)): the Thu 10-22 evening row runs `cutover-readiness` on the HOST over ssh in the Thursday evening block (before: on the laptop, with the machine an open question). The ruling is quoted below addendum 113's dated items, which are unchanged. Section 0's readiness readout names the host and quotes the ruling, and labels the laptop form (`--receipts FILE --fullseason-list FILE`) "for the architect's dry reads only". On the host the readout runs without `--receipts` or `--fullseason-list`; `--named FILE` is passed when a day is operator-named (addendum 113 item 1: "operator-named with evidence in the --named file"). The ruling names the laptop form only, so the page does not credit it with the host's options. Its (T9) bullet says an MLB line binds (item 1(b), quoted), and that MLB lines are named once the list parses: an UNPARSEABLE list is NOT-YET on its own and names no MLB line (the one parser refuses the file at its first bad line). The T9 item's Why is in the past, dated: until 10-18 the host's list was the installed example, and block_1018_t9_host.txt's one run on 10-18 wrote its 26 lines (addendum 128 item 4). The T9 pre-cutover item notes that the block is never re-run. docs/CLI.md's `cutover-readiness` row says the same.
- Tests. tests/test_cutover_readiness.py: the MLB test changes from "not binding" to "binds" (the ⚠ line and the unmet item named), keeping every MLB-code case. The BOM test checks that its MLB line binds. A new test runs hosting-h1.md T9's block as written, twice, over the installed example (sqlite3, sudo and install stubbed): each run prints the list, the file holds each line once, the temp file is gone, and the install flags are install.sh's. Another pins the runbook's host label and the ruling's quote. Three more pin the docs: the host run leaves out only `--receipts` and `--fullseason-list` and keeps `--named FILE` (the schedule's row, section 0, docs/CLI.md); a list with an MLB line and a line the chain cannot parse reads UNPARSEABLE, names no MLB line, and names it once the list parses (the docs say so); the runbook's T9 Why is in the past beside the Run-once bullet. New tests/test_cockpit_intl_verify_role.py: the verifier, loaded with Playwright stubbed, pins the role over a host.env that says host, a role exported as host, and no role at all, and creates no directory to do it. Each new test, and each changed assertion, fails on main ba2efe5 and passes here.
- Refs #591, #593.

## 2026-10-18 (#595: today-tab — the Cockpit's Today tab and `coverage --json`; ARCHITECT addendum 125 item 2, Issue #589)
- Addendum 125 item 2, verbatim: "CODE SLOT A — THE "TODAY" TAB: the coverage map and the ETAs in the product, not on my page. Spec (M, non-gate, one PR, repo copy only): (a) `python cli.py coverage --json [--out PATH]` writes the dict `deploy/hosting/coverage_map.coverage()` already returns (date, now, competitions[], gaps[]; datetimes ISO-8601 Z), under `kind: "coverage_v1"`, plus `roadmap`: the lanes of docs/roadmap.json with their competitions, status and dated ETAs, read as `cli.py roadmap` reads them (no new source of truth; if a lane carries no date it prints "no ETA"). Default --out exports/coverage_<date>.json; the morning block's existing `coverage` line gains `--json`; the mirror carries it (laptop/latest/coverage.json, host/latest after the cutover). Read-only as today: mode=ro, no provider call, exit 0 whatever the gaps. (b) tools/cockpit.html gains a fifth tab, "Today", fed by that file through the existing intake (`loadDocs`: a `coverage_v1` document takes its own path like `desk_parlays_v1`, and it never resets the loaded slate — a coverage file alone must not blank `rows`). It renders, in the file's own order (LIVE, SHADOW, MARKET-ONLY, UNKNOWN): one tile per competition — the games count, the status label as the file gives it (PREDICTION for LIVE, with the model; MARKET-ONLY; SHADOW with its tag; UNKNOWN with its reasons), the writer chains, the prediction rows by model with computed_at, then the closing groups: T-35 in ET, the match ids, the file name, and the state (done with run id and exit / due with a live countdown / started with no group). The gaps in capitals at the top, exactly the file's `gaps` lines. Below the tiles, the ETAs strip from `roadmap`: one line per lane, competition · status · ETA. Nothing is computed in the page that the file does not carry (the F1c principle: viewer, not engine). The page's own clock is used only for the countdowns. (c) Receipts in the PR: `coverage --json` on a real morning (today's file pasted), `scripts/cockpit_render_verify.py` extended to load the file and assert the tiles' counts equal the file's, the existing verifiers green, the golden untouched. The title string "Betting Desk — B1 Shadow" becomes "Cockpit" in the same PR (cosmetic, named here so it is not silent)."
- **Repo copy only; the live page is republished on the operator's word** (addendum 125 items 0, 1 and 6: the republish is the operator's and the architect's ritual, never Code's).
- `python cli.py coverage --json [--out PATH]` (= `deploy/hosting/coverage_map.py --json [--out PATH]`): writes `{"kind": "coverage_v1", **coverage()}` with every datetime ISO-8601 Z (`_plain`, generic: a field coverage() gains later rides along), plus `now_et`, the line's own words per competition (`line`, `games_text`, `rows_text`, `without_rows_text`, `closing_text`, and `closing_tail`: the closing clause's words outside any group's text, `none left to run` or null, from the one function the line uses, `_closing_tail`), per model (`computed_et`) and per closing group (`run_lead`, `run_at_et`, `text`), so a reader shows them without computing them; and `roadmap`, the lanes from the new `src/roadmap.lanes_data` (`roadmap.load()` and the print's own per-lane lines, `lane_lines`, now shared by `report()`; `when` counted from the coverage day): lane, title, Issue, competitions (null where none), state, earliest_live, `eta` (`earliest live <date>` or `no ETA`), the next step, the overdue count and the print's two lines. A roadmap that does not validate: `roadmap: null` and `roadmap_unread` (law 4). Default `exports/coverage_<date>.json` (the coverage day; relative to the working directory, as every export); written whole (beside its name, then moved into place). The DB is opened mode=ro as before, no provider call, exit 0 whatever the gaps. `--out` without `--json`, an `--out` under data/, and an `--out` at the top of exports/ whose mirror kind is not `coverage` (it would be pushed and compared, not listed as machine state; Codex review) exit 2 and write nothing; a file that cannot be written exits 2 and writes no file (a missing parent folder may be left behind). With `--json` the console prints the same lines, the header saying `one export written (<path>, --json)`, then `COVERAGE JSON: <path> written (…)`. Without `--json` the output is unchanged byte for byte: a test pins main's own output on a day with every status, a void and a started game, a done run and the three kinds of gap. `roadmap`'s print is unchanged (checked against main on the real file).
- The exports mirror: no code change. `kind_of("coverage_<date>.json")` is `coverage`, so a push carries `<role>/<date>/coverage_<date>.json` and `<role>/latest/coverage.json` like every kind; the docstring says so and a test pins it (the writer's hidden temporary is never taken).
- **The compare's machine-state kind rule (Issue #592, RULED ARCHITECT 2026-10-18 10:00 ET, addendum 128 item 3, verbatim):** "#592 — RULED (needed before the Today tab's morning-block line): a coverage file is MACHINE STATE by nature — each machine's own view of the day, with `now`, `due` vs `ahead`, `started` — and can never be a divergence. Option 1, as a KIND rule: the compare treats kind `coverage` as "machine state": listed by presence on each side (one side, both sides, neither), never compared for content, never DIVERGENT, never counted toward or against criterion (a). Printed as its own line ("machine-state files: coverage laptop yes / host no"). Build it in the Today tab PR before the morning block gains `--json`; the compare's test adds the one-side and both-sides cases. Dated and latest copies both travel (option 3 declined: the dated file is the day's record)." Built: `deploy/hosting/compare_exports.py` treats kind `coverage` (the mirror's kind rule, copied as `kind_of` because the tool ships alone, and pinned to `exports_mirror.kind_of` by a test) as machine state: the dated `coverage_<date>.json` and the latest copy `coverage.json` are taken out of the comparison before any file is opened, so neither is a `·` or `✗` line, an `unparseable` line, in the compared or the one-side count, or a verdict (a folder holding only it reads NO-COVERAGE, never CLEAN); one line, always printed before the `coverage:` tally, lists presence per side (`machine-state files: coverage laptop yes / host no`; `no / no` when neither). `cutover_readiness.compare_day`, criterion (a)'s counter, applies the same rule (its `machine_state` is that line, printed under each compared date), so a coverage file is counted neither toward nor against (a). The --since window and the header's settled count treat a dated coverage file like any dated file. The mirror is unchanged: both copies already travel (pinned, and now end to end through the shipped Action). The morning block's one-line change (`python cli.py coverage` becomes `python cli.py coverage --json`) is the architect's (the operator's block file, not in the repo); Code does not write it. The rule reaches the mirror's Action only when both writers ship it: every push copies the pushing machine's own `compare_exports.py` into the mirror's `tools/`, so until the host runs a tag carrying this change, a host push puts the old comparator back and the laptop's coverage file reads DIVERGENT (a scratch mirror, the host pushing with 86b4df1's code: the Action posts DIVERGENT after the host's push and CLEAN after the laptop's next one). Criterion (a) is counted on the host (addendum 128 item 1(a)) with the tag's code. When the `--json` line goes in (after merge, or after the host's tag carries this) is the architect's (raised in the ledger entry).
- #592 receipts (the Issue's cases, the Action's flags `--since 0`, scratch folders, two real coverage_v1 files from `scripts/cockpit_coverage_file.py` on scratch DBs): HEAD 86b4df1 reads one side `· coverage_2026-10-19.json: only on laptop` DIVERGENT exit 1, and both sides `✗ coverage_2026-10-19.json: … diffs=27` DIVERGENT exit 1; this change reads CLEAN exit 0 for both, with `machine-state files: coverage laptop yes / host no` and `… laptop yes / host yes`, and the baseline is unchanged but for the new line. `cutover-readiness` on a five-day scratch mirror with a coverage file on the laptop only on the newest day: streak 0/5 (`UNNAMED coverage_2026-10-18.json: file only on laptop`) before, 5/5 after.
- #592 tests: tests/test_compare_exports_machine_state.py (new, 10: one side each way, both sides with different content, neither, a real divergence beside a coverage file still DIVERGENT, coverage files alone NO-COVERAGE, the latest copy never read, the line's place and the window, the kind pinned to the mirror's; after review, the docs naming the dated copy for the daily compare (fails on b6cceeb), and the line's scope pinned as built: presence among the files the --glob and the window select), tests/test_cutover_readiness.py (+2: compare_day lists and never counts it; the five-day streak identical with and without coverage files, a coverage-only day NO-COVERAGE), tests/test_exports_mirror.py (+1: both copies travel and the shipped Action posts CLEAN, one side and both sides). All 11 fail on 86b4df1.
- #592 docs: docs/CLI.md (the compare row, with the line's scope: presence among the files the compare selects, the Action's flags selecting the whole dated folder; the `coverage` row's `--json` file: the daily compare, the Action, compares the dated folders, so it lists the dated copy, and the latest copy is listed the same way when latest/ folders are compared by hand; the `cutover-readiness` row's (a)), docs/specs/h2-cutover-runbook.md (section 0's (a), section 2's classes: machine state is not a class), docs/specs/hosting-h1.md (the H1b compare bullets), docs/specs/exports-mirror.md (the Action: the dated copy, and the Action runs the comparator the last push shipped, so the rule holds there once both writers run code that carries it).
- tools/cockpit.html (repo copy): a fifth tab, Today. `loadDocs` lifts every coverage_v1 file out of a load first (`takeCoverage`; several in one load: the newest by its date then now, the others named) and returns before the slate's reset when nothing else was loaded, so a coverage file never blanks `rows`, shadow rows, tickets or refusals, and a slate load never clears the coverage. The tab renders the file's gaps lines at the top (`GAPS: none` when empty), one tile per competition in the file's order (games count, any void games, the status label as the file gives it with its `status_from`, the writer chains, the rows by model with computed_at or the line's rows clause, the without-rows clause, then started (no group), finished, and each closing group: state, T-35 time in ET, match ids, the done run's id and exit, a live countdown to `run_at` on every group not done, and the group's text as the line prints it, with its file name), a console-line expander, and below the ETAs strip (competitions, or the title where a lane names none · state · ETA, with the print's next-step line); roadmap null shows its reason. After the groups, the file's `closing_tail` (`none left to run`), never derived in the page. `loadDocs` draws the coverage file inside a try/catch: a file the page cannot draw (a competition entry that is not an object, named) writes its error into the Today summary, nothing of an earlier file left under it, and the slate picked with it loads as ever; an entry of a tile's rows or groups, or of the roadmap, that is not an object is labelled "not read" where it stands. `loadDocs` returns what that load did (`{coverage, coverageError, slate, refused}`) and the "Load latest from host" note is built from it, so a coverage-only load never reports an earlier load's refusals. Every string escaped (`esc`); statuses render by their label, so a status the file adds later (POT on its branch) renders the same way. The page clock drives only the countdowns. The title "Betting Desk — B1 Shadow" is "Cockpit" (its one place); the h1 chip names today.
- scripts/cockpit_coverage_file.py (new): a coverage_v1 file from the REAL command on a scratch DB built from the ORM's schema in a temporary folder (DATABASE_URL, SP_RECEIPTS and SP_HOST_ENV inside it; never data/), tomorrow in ET; `--all-done` receipts a run for every closing group of the day.
- scripts/cockpit_render_verify.py: 38 checks (was 21 on main 92c2442; 17 new Today checks): the Today tab on that file (tiles in the file's order, each games count and status label equal to the file's, the gaps lines, one ETA line per lane with "no ETA" for the three undated lanes, countdowns that move with the page clock and none on a done group, the title "Cockpit"), coverage after a slate leaves the slate, a slate after coverage leaves the tiles, a later status (POT) by its label, markup shown as text, roadmap null with its reason, a slate and a coverage file with null list entries in one load (each labelled "not read", the slate loads), a slate and a damaged coverage file in one load (the slate loads, the Today summary shows the error, no tile), and a file whose groups are all done (`--all-done`: each tile shows the file's `closing_tail`). scripts/cockpit_mirror_verify.py: 7 checks (was 6): a coverage-only load leaves the slate and its note names the coverage file and no refusal of the load before it. The golden is untouched.
- Tests: tests/test_coverage_map.py (+10: the byte-for-byte pin; kind, the coverage() dict and ISO-8601 Z throughout; the roadmap lanes as `roadmap` reads them with "no ETA"; roadmap unreadable, null and its reason; the default `--out`; the refusals; no partial file; the no-write-transaction test with `--json`; a later status carried generically; `closing_tail` when every group is done), tests/test_roadmap.py (+1: `lanes_data` is the print as data), tests/test_exports_mirror.py (+1), tests/test_cockpit_today.py (new, 13: the title, five tabs, the intake order, the render isolated in `loadDocs`, `loadDocs`'s return and the mirror note built from it, and the page's Today functions under node, the closing tail and null entries labelled among them).
- docs/CLI.md: the `coverage` row gains `--json` / `--out` and the file's shape.

## 2026-10-18 (#588: ledger-summary-page-only — #544, ARCHITECT addendum 125 item 4)
- The ruling (ARCHITECT 2026-10-18 08:20 ET, addendum 125 item 4), verbatim: "CODE SLOT C — two small ones in one PR (S): #458 as ruled in 112 item 10 (the window page keys QB news by provider player id, name display only; the test uses two same-name players); and #544, RULED now: no --desk export will ever read a ledger summary — the ledger lives in the browser and the exports are written by machines that have no browser. The counts stay in the Cockpit; `counts_source: default 0 (no ledger summary)` is the permanent reading and the postseason half-unit cap that keys on it stays ON as the conservative default (it binds only MLB postseason rows this season; the January NFL question is #86's, with the v1.2 bump). #544 becomes a limitation (label from the fixed set), docs/CLI.md and the button's text say the summary feeds nothing outside the page, and the Cockpit's Ledger card shows one line: "exports read no ledger summary; postseason rows are sized at half until v1.2". Nothing else changes; no new file path."
- tools/cockpit.html (repo copy only; live page republished on the operator's word):
  - The Ledger card shows one line under its heading, `#ledgerExportsLine`: "exports read no ledger summary; postseason rows are sized at half until v1.2".
  - The summary button reads "Export ledger summary (feeds nothing outside this page)". Its help text says no `--desk` export reads it. The note after a click no longer asks for the file to be saved as `exports/ledger_summary.json`. The code comment above `ledgerSummary()` says the same.
- docs/CLI.md, the `--desk` exports row: no `--desk` export reads a ledger summary. Every one reads `counts_source` "default 0 (no ledger summary)" permanently, and the postseason half-unit cap keyed on it stays ON. The `desk-parlays` row says its counts read the same default.
- scripts/cockpit_render_verify.py: one check, that the Ledger card shows the line exactly. It fails on the page before this change (no such line).
- Not changed, as ruled ("Nothing else changes; no new file path"): `desk_policy` (`COUNT_KEYS`, `read_ledger_summary`, `maybe_annotate`, `SP_LEDGER_SUMMARY`, the default path), `desk-parlays --ledger-summary`, the summary's content and file name, the postseason cap. The golden is untouched.
- Refs #544 (`class:limitation`, an accepted limit; it stays open).

## 2026-10-18 (#587: fullseason-readiness — T9 on the cutover runbook and the readiness line for the host's weekly full-season list, ARCHITECT addendum 122 item 3(b); Refs #586)
- **Ruling (ARCHITECT 2026-10-18 08:15 ET, addendum 122 item 3), verbatim:**

> 3. HOST WEEKLY-FULLSEASON — RULING. Cause is provisioning, not code: `/etc/sports-predictor/fullseason.list` on the host is still the installed example (comment lines only); hosting-h1.md step T9 ("generate the list from the DB, read-only; paste it as the receipt") was never run; the chain refuses by design ("lists no competitions"; sp_run.py fullseason_steps). It has failed every Sunday we hold receipts for — 10-04 on v1.2.2, 10-11 on v1.3.0, 10-18 on v1.4.0 — each time paged, none acted on: the host has NEVER done a full-season resync. I correct my own page: this morning's "host weekly-fullseason 06:00Z resynced the season" line was wrong; nothing ran. Impact today: small — the host is not the writer, the hourly window and the sport chains cover the next 24h, and the laptop's morning block syncs PL and NFL whole-season daily. Impact after the cutover: a law ("full-season weekly") unmet on the writer of record. So:
>
> (a) T9 is a PRE-CUTOVER ITEM, binding: block_1018_t9_host.txt (Tailscale) generates the list from the host DB read-only, prints it, writes every line EXCEPT MLB, prints the file, then runs the chain's dry run (resolved commands only). MLB is excluded by ruling: MLB is a laptop duty to the season's last game; a host api-sports whole-season MLB write beside the laptop's statsapi rows is #569's twin-row shape. The chain's first real run is its own timer, Sun 10-25 06:00Z — the morning page that day carries its receipt, and Friday's cutover ruling is GO only conditional on it (an added condition; the frozen criteria are not loosened).
>
> (b) Code: one Issue (limitation, host) — "weekly-fullseason never provisioned on the host: T9 unrun, failed 10-04/10-11/10-18, paged each time" — closed by the 10-25 receipt; the runbook's preflight checklist gains T9 ("fullseason.list non-empty, dry run printed"); `cutover-readiness` gains a readout line from SP_FULLSEASON_LIST — "fullseason list: N competitions" or "EMPTY → NOT-YET" (one more binding condition on the readout, in the cutover-watch PR or its own small PR); and the fact that three weekly failure pages went unacted is a process finding for the ledger, not a code change: the morning page will carry "failing units" by name from now on (it did today; the first two Sundays predate it).

- deploy/hosting/cutover_readiness.py: a new section, **(T9) WEEKLY FULL-SEASON LIST**, after (c). It is one more binding condition on the readout; the frozen (a)-(c) are unchanged. It reads the file the `SP_FULLSEASON_LIST` setting names, or the host's file passed with the new `--fullseason-list FILE` (elsewhere, as `--receipts` is). The line prints the file and `fullseason list: N competitions — <CODE|SEASON> · …`, or `fullseason list: EMPTY → NOT-YET`. These are also NOT-YET, each with its reason (law 4): the setting not set (`NOT SET`; an empty `--fullseason-list` reads `NOT SET` too, its reason naming the option, "--fullseason-list was given an empty path"), the file absent (`MISSING`), a file that cannot be read (`UNREADABLE`), and a line the chain cannot parse or fill (`UNPARSEABLE`: no `|`, an empty code or season, or a brace the chain's str.format cannot fill, such as `NFL|{season}`, which crashed the chain's resolve while the readout read ok). The readout counts through `sp_run.fullseason_resolve`, the chain's own parser and formatting, so it lists the competitions as the chain resolves them. The unmet list names `(T9) fullseason list <state>`. An MLB line (`MLB`, `MLB_<kind>`) prints with a `⚠` and does not bind: the architect rules whether it binds (the ledger entry asks).
- deploy/hosting/sp_run.py: the list's line parser is `fullseason_entries(p)`, the ONE parser, and `fullseason_resolve(p, v)` is the ONE path from the file to the commands: the parser, then `format_step`, the str.format `resolve()` fills every chain's steps with. `resolve()` runs weekly-fullseason through it and the readout counts through it, so a line the readout counts is a line the chain runs, and a line the chain fails on reads UNPARSEABLE. The refusals (setting or file missing; no competitions) are unchanged. A line without `|` raises ValueError naming the file and line (before: a bare unpack error). So does a line whose code or season is empty once stripped (`|2026`, `NFL|`, `|`): the host chain now refuses such a line at resolve instead of running `sync-matches --competition  --season 2026`, a step bound to fail, and the readout reads it UNPARSEABLE (before: counted, "N competitions"). A brace str.format cannot fill raises ValueError naming the file, the line and the str.format error (before: a bare KeyError, ValueError or IndexError from resolve). A code or season that str.format leaves empty (`NFL|{today:.0}`) is refused the same way after formatting. The list is read as utf-8-sig, so a hand-edited file's leading BOM no longer rides into the first code (before: the readout showed an invisible `<BOM>MLB|2026` beside "MLB lines: none", and the chain ran `--competition <BOM>MLB`).
- docs/specs/h2-cutover-runbook.md section 0: the pre-cutover item **T9 — "fullseason.list non-empty, dry run printed"**, binding, with the ruling's (a) verbatim, the block `block_1018_t9_host.txt` and its receipt (the generated list, the file as written with no MLB line, the chain's dry run); the readout's (T9) bullet.
- docs/specs/hosting-h1.md T9: the copy-paste query now leaves MLB out (`AND c.code NOT LIKE 'MLB%'` in its WHERE clause; before, it selected MLB and teed it into the live list, against ruling (a)), and the step quotes the ruling. docs/CLI.md: the `cutover-readiness` row (and the CLI docstring) name `--fullseason-list` and the (T9) line.
- tests/test_cutover_readiness.py, twelve tests: a populated list counts and does not bind; the installed example reads EMPTY → NOT-YET (and the chain refuses it); a missing setting or file is NOT-YET with the reason; a directory, a denied read and a line without `|` are never ok; the count is `fullseason_steps()`'s own resolution of the same file, a doubled brace included, and a brace the chain cannot fill (KeyError, ValueError, IndexError, AttributeError) fails `resolve()` and reads UNPARSEABLE with the chain's own message; an empty code or season (five lines) is refused by `resolve()` and reads UNPARSEABLE; a half str.format leaves empty is refused after formatting, and a leading BOM is dropped (an MLB line behind it is flagged); hosting-h1.md's T9 query, run as written on a synthetic DB, writes no MLB line; the module's usage line names every option; MLB lines are reported, not binding, and every code the MLB adapter exposes reads as one; `--fullseason-list` reads the named file, and an empty one reads NOT SET with the option named.
- Process finding (ledger only, no code): three weekly failure pages, 10-04 (v1.2.2), 10-11 (v1.3.0) and 10-18 (v1.4.0), went unacted. The morning page carries "failing units" by name from now on.
- Refs #586 (`class:limitation`): the receipt of the chain's first real run, Sun 10-25 06:00Z, ends it by ruling; this PR does not.

## 2026-10-17 (#588: qb-news-by-id — #458, ARCHITECT addendum 112 item 10; the key, addendum 117 item 3)
- Schema: nullable `injuries.player_source_id` (VARCHAR(64)), the provider's own player id, NOT mapped in the ORM (the ORDER LINE note, as addendum 35 item 2 ruled for `odds.source_updated_at`: every chain reads `injuries`, and the release ritual runs migrations by hand after the checkout). src/db/database.py: `has_injury_player_id`, `write_injury_player_ids`, `read_injury_player_ids` (guarded Core SQL, only when the column exists; per call, never cached).
- Migration `migrate_injury_player_source_id.py` (new): additive, idempotent, behind the shared guard (`refuse_missing_db`, #524). Its receipt counts the rows that carry the id and the rows that do not, per source. No backfill. Run order: any (backup first, by hand). Laptop: `python migrate_injury_player_source_id.py`. Host: the `--run-migrations` line `sp_deploy.py` prints.
- src/adapters/api_american_football.py `list_injuries` (NFL, NCAA): each entry's dict carries `player_source_id`, the entry's own `response[].player.id` as a string (None when the entry has none). src/ingestion/service.py stores it on the row after the flush. It is a no-op until the migration.
- src/walters/window.py (`window-card`): each `qb_news` item carries `player_id`, the row's stored id (null where the row has none).
- deploy/hosting/sp_window_page.py: QB news is keyed by team id and provider id (`id:<team_id>|<id>`); the name is display only. The key as ruled (ARCHITECT 2026-10-17 16:55 ET, addendum 117 item 3), verbatim: "#458 — the key is (team id, provider player id). The ruling named the provider id to replace the name; a player listed on two teams' reports in one window (a trade, a provider error) is two entries, and collapsing them would hide one. Build it that way; the two-team test stays." One id on two teams' reports in one window is two entries, each paged on his own team's games. An item with no id keeps the old key, `<team_id>|<name>`, and its page line says `(no provider id)`. Items with no id that share a team and name become one entry holding every status, sorted (`(no provider id, N entries)`), so one never overwrites the other.
  - A change of key is not news. A player keyed by name in the previous state and by id now is carried to his id. Where two or more ids share the old name key, that name makes no delta that run when the ids' statuses are the name entry's (a baseline); otherwise the ids fold into one name-level line that pages.
  - The old state's one entry for two id-less same-name items, read against the entry that now holds both, is a baseline only when its status is the new last item's (where the old pager was silent too); otherwise it pages.
  - Ids arriving for a pair: a baseline only when their statuses are the name entry's; otherwise the ids fold into one name-level line that pages. The same the other way round.
  - The `(no provider id)` label follows the item: a player whose row loses its id keeps the label.
  - The receipt gains `qb_rekey` {`carried`, `baseline`}.
  - The `id:` prefix keeps the id key apart from the id-less `<team_id>|<name>` key. The key change finds a player's id key by the team-and-name `name_key` each entry carries, so it carries each team's listing to that team's id key.
- docs/CLI.md: the `sync-injuries` and `window-card` rows.
- tests:
  - test_qb_news_by_id.py (new, 22), led by the ruled test: two same-name quarterbacks on one team with different ids both appear, and a status change in either pages. Then the two-team tests (addendum 117 item 3):
    - one provider id on two teams' reports in one window is two entries, and a status change on either team pages for that team, on that team's games only;
    - when the first team's game leaves the card, nothing false pages for the other (on the id-alone key it paged `Out -> Questionable`, a change nobody made);
    - one id on both teams of one game is two entries;
    - the key change carries each team's listing to its own key.

    The other tests:
    - items with no id: keyed by team and name and labelled; two of them are never merged silently.
    - a deploy before the migration pages nothing new. An id-less same-name pair is a baseline only where the old pager was silent; otherwise it pages. A state this code wrote is never read as the old format.
    - a player whose row loses its id keeps the label.
    - the first run with ids pages only real changes. The collapsed pair is a baseline when its statuses are unchanged, then each pages by his own id; changed statuses page one folded line, both ways. `run()` receipts `qb_rekey`.
    - the adapter carries each entry's own id.
    - `sync-injuries` before the migration writes its rows and no id; after it, it stores the ids, and the card and page key by them.
    - the ORM never names the column.
    - the migration: additive, idempotent and receipted; it refuses without the table and with no database file.
  - test_qb_one_news_item.py: the helper's items carry a provider id. The card's item gains `player_id` (null for a row with none).

## 2026-10-17 (#587: host-watch-after-flip — ARCHITECT addendum 113 FOR CODE, addendum 114 item 3; #85, #410)
- No code change. The host's closing watch already covers every family the laptop's watch covers today, MLB excepted: the unit runs `closing.py watch --family NFL --family SOCCER` (deploy/hosting/systemd/sp-closing-watch.service:28), and the laptop's setup script installs MLB, NFL and SOCCER when given no `--family` (scripts/setup_closing_watch.sh:72). Nothing in the watch reads `SP_WRITER_OF_RECORD` (closing.py, chains.py and the unit never name it), so the flip's writer line changes nothing in what the watch closes. Under role host, the soccer rows it closes are held by the Desk's host fence alone (desk_policy.py:190 `HOST_FENCE_RULE`, checked first at :1072), and turning that switch off lifts them. MLB stays the laptop's: the unit does not name it, and host.env's `SP_SKIP_FAMILIES=MLB` (host.env.example:23) refuses an MLB run typed by hand (closing.py:1259-1264).
- tests/test_host_watch_after_flip.py (12). In these tests the flip is the cutover PR's whole change: sp_cutover.py's own `flip` step, unchanged, writes `SP_WRITER_OF_RECORD=host` into a scratch host.env, and `HOST_FENCE_RULE` is turned off. The host's watch is the unit's own ExecStart, run with host.env loaded as its EnvironmentFile loads it. Each export step's Desk runs at that step.
  - The families: the laptop today runs MLB, NFL and SOCCER. The host's unit runs NFL and SOCCER, which is the laptop's set less MLB, and runbook section 1 step 5b uses the same two. After the flip the laptop is reinstalled for MLB only (step 7). Between the two machines every family is watched once.
  - Nothing in the watch reads the writer of record.
  - (a) After the flip (role host, writer host, switch off), one host tick closes NFL and SOCCER, both successes paged `machine: host`. The soccer rows in the closing file match the laptop's Desk calls for the same rows (Arsenal's PLAY 0.5u with its order line), none is `host_fence`, and desk_meta reads `host_fence_rule: false`. The NFL rows also match the laptop's. A hand-typed MLB run is refused "laptop only". The INTL row is a PLAY, and INTL has no closing family.
  - (a) The host's SOCCER page after the flip is the laptop's page for the same schedule and export, except the machine line. The closing file's rows are identical.
  - (b) Before the flip (role host, writer laptop, switch on), the same tick closes NFL and SOCCER. Both soccer rows are PASS `host_fence` with the ruled reason and no order. The page reads only `PASS: 2 games` and `machine: host`, and desk_meta reads `host_fence_rule: true`. NFL is unchanged.
  - The switch decides, the writer line decides nothing. Four cases: writer laptop or host, each with the switch on or off. Every case closes NFL and SOCCER. The soccer rows are `host_fence` exactly when the switch is on, and are the laptop's calls when it is off. NFL matches the laptop in all four.
  - (c) There is one switch, and the routes below that could lift the fence beside it are pinned shut. It is the only `{"on": bool}` switch with FENCE in its name, and the only switch the fence's read path (`host_fenced`, `role_reading`, `machine_role`, `_env_file`) names. Each of the four reads exactly the desk_policy module-level names it reads today, an imported module (`os`, `io`) included: `host_fenced` the switch, `HOST_FENCE_SPORTS`, `role_reading`, `HOST_FENCE_REASON`, `HOST_ENV_UNREADABLE` and the two role-unknown reasons; `role_reading` `_env_file`, `os`, `HOST_ENV_DEFAULT`, `DOTENV`, `HOST_ENV_UNREADABLE`, `ROLE_ENV` and `ROLES`; `machine_role` `role_reading`; `_env_file` `io` and `HOST_ENV_UNREADABLE`. So a new name read on the path (a constant, a helper that reads the environment, a bool) fails the test. The path's strings hold no WRITER and no upper-case key but `SP_HOST_ENV`. The fence is called in one place, first in `_desk_call`. Across the tracked production Python files (git ls-files), `HOST_FENCE_RULE` is assigned only at its definition and in desk_policy's two context managers that turn it off and restore it (`base_v11`, `host_fence_rule_off`). Every reference counts, not only a call: a name or an attribute (so an alias such as `off = dp.host_fence_rule_off`, or a write through one), an import, or a string in code. In desk_policy the switch is referenced only as its definition and as `HOST_FENCE_RULE["on"]` (in `host_fenced`, `annotate`'s desk_meta and the two context managers), and neither context manager is referenced in its code. No other tracked production Python file references the switch, and only four verify/battery scripts reference a context manager (scripts/cockpit_btrack_verify.py, cockpit_desk_files.py, cockpit_window_verify.py, desk_battery.py, each `dp.base_v11`). The fence's other inputs, which a file could rebind to lift the fence with the switch still on (`dp.host_fenced = lambda r: None`, `dp.HOST_FENCE_SPORTS = ()`), are referenced by no tracked production Python file but desk_policy, counted the same way: `host_fenced`, `role_reading`, `machine_role`, `HOST_FENCE_SPORTS`, `HOST_FENCE_REASON`, the two role-unknown reasons and `HOST_ENV_UNREADABLE`. A script reaches a context manager when it is one of the four, imports one that reaches (every dotted part of an import counts, and every name a `from` import takes), or names one in a string its code uses (a path it runs as a child process, a module importlib loads): 30 scripts today. None of them is imported or named in code by cli.py, config.py (which cli.py imports), src/, deploy/ or the laptop's setup scripts, except the parity harness (scripts/desk_parity_verify.py), which cutover-readiness runs as a child process in a scratch worktree of a release tag (criterion (c)) and does not import. The files on those paths that are not Python (the units, timers, shell scripts and env files) name no reaching script, and neither the switch, nor a context manager, nor a fence input, anywhere in them. desk_meta's `host_fence_rule` is that switch. Not pinned: another file rebinding `role_reading`'s own inputs (`_env_file`, `HOST_ENV_DEFAULT`, `DOTENV`, `ROLE_ENV`, `ROLES`), and edits inside desk_policy beyond the references above (a second module-level rebinding of a fence input, or `_desk_call` setting the fence's answer aside); those are read in review.
  - (c) The flip without the switch is still fenced in a fresh process. On the flipped host (host.env and the environment both say writer host, role host), a fresh process runs the runbook's own HOST FENCE CHECK command and prints `{'on': True}`, and a soccer row there is PASS `host_fence`. In production the switch is off only by the cutover PR's source line: outside desk_policy, no tracked production Python file references the switch or a fence input, only the four verify/battery scripts reference a context manager, and no script that reaches one, by import or by a string its code uses, is imported or named on an export, chain, closing or deploy path (the parity harness that cutover-readiness runs in a scratch worktree excepted), in its Python files or in its units, timers, shell scripts and env files.
  - The runbook carries "The 2026-10 schedule" before section 0, with addendum 113's six dated items quoted verbatim and each date on its own row.
  - #580's in-process identity test, tests/test_desk_host_fence.py::test_the_switch_the_cutover_pr_turns_off_is_the_one_the_fence_reads, is referenced and not repeated.
- docs/specs/h2-cutover-runbook.md: a new section, "The 2026-10 schedule" (addendum 113), before section 0. It lists the plan's dates as the plan states them: Sun 10-18 → Thu 10-22 the five morning compares; Sun 10-18 the laptop dry run; Mon 10-19 evening the P8 rehearsal; by Wed 10-21 v1.5.0; Thu 10-22 the host's full day on the tag, the parity harness on it, and the evening `cutover-readiness`; Fri 10-23 morning the ruling; Mon 10-26 09:00–11:00 ET the cutover, with 10-30 as the fallback. Each step's date names its place on the page (the Fri 10-23 row is the architect's ruling, not a step, so its cell is empty), the frozen criteria are quoted, and the plan's dated items are quoted verbatim. No step is changed: the section adds 44 lines and the runbook's diff removes none (its other added lines, T9, are this PR's full-season part: changelog.d/587-fullseason-readiness.md). The Thu 10-22 evening row's "On this page" cell carries a note (Codex review on #587, verified against cutover_readiness.py): the readout section is labelled TERMINAL (host); on the laptop, `--receipts FILE` and `--fullseason-list FILE` name the host's files, or criteria (b) and (T9) read the laptop's own; which machine runs it is an open question for the architect (#587: the host-watch ledger entry's first question, the full-season entry's question 2). The row's "What" text, which paraphrases item 5 (quoted below the table), is unchanged.
- deploy/hosting/sp_cutover.py, closing.py, chains.py, the units and desk_policy.py are unchanged.

## 2026-10-17 (#584: desk-pass-units — ARCHITECT addendum 112 items 9 and 11, addendum 117 item 2; #181, #418)
- Addendum 117 item 2, verbatim: "#181 + #418 — the four: a. The stale "caution" text on the eight NHL rows is replaced by the pass text (reason as the Desk gives it); nothing else on those rows changes. b. Policy stays v1.1. This is a display defect, not a Desk-rule change; POLICY_VERSION moves only with #86. c. Venue rows: the same rule — a PASS venue row is 0 units / class pass. Every PASS, every engine. d. The golden's capture metadata is left as it is; the PR body lists the eight changed rows by match id with before/after, and says the metadata is untouched."
- src/walters/desk_policy.py, `_desk_call`: a PASS row ends with units 0 and class `pass`, every sport (#181, addendum 112 item 9). The pre-gate branch (NHL, `passAll`) let the sizing chain keep running, and its big-edge caution (edge >= 15pp) set 0.5 / `caution` on a PASS row and appended its reason and tag, a wart ported from the JS for parity.
  - Item 2(a): the big-edge caution no longer runs on a row that is already PASS (the pre-gate branch only). Those rows read 0 / `pass` and carry the pre-gate line as the Desk gives it: no "market-is-right caution" reason and no `big-edge caution half units` tag. Nothing else on them changes (their `edge ≥ floor` tag, any `strong tier` and `kalshi …` lines stay).
  - An NFL quarantine at an edge of 15pp or more is still a PLAY when the caution runs: its `shadow_units` keeps the caution's size and its tags keep the caution tag; its reasons were already only the QUARANTINE line. An MLB > 8pp quarantine never meets the caution (it is skipped for MLB under the quarantine rule), so its shadow is never sized or tagged by it.
  - Every other PASS path already ended at 0 / `pass` with its own reason and is untouched: S1 shadow league, kickoff clock, started, default rating, one-sided injuries, INTL no series / venue unknown, no reference, the pick-prob and edge floors, the thin-books reclass and the MLB kalshi-only suspension.
- src/walters/desk_policy.py, `desk_block`: item 2(c), every market-only (venue) PASS row carries `cls` `pass` beside its units 0. A VENUE row carries no `cls`, as before. The `venue` sub-block, the window card's venue block and every reader are unchanged: the Cockpit renders the venue table from `desk.venue`, the venue receipts' `desk_ok` reads no class, and venue rows are never parlay legs.
- Item 2(b): POLICY_VERSION stays v1.1. PLAY and LADDER sizing is unchanged. No switch: the golden is amended instead (below).
- tests/golden/desk_js_v1_1.json.gz: amended for exactly the eight rows, all NHL pre-gate PASS rows: 4 in "counts 0", 2 in "postseason 31", 2 in "fixtures loaded first". On each, `units` 0.5 -> 0 and `cls` caution -> pass (addendum 112 item 9), and the caution reason and tag are removed (item 2(a)): 32 leaf values. No other row, field or section moved (values, venue, parlays, the parlay fuzz and toFixed are identical in content). Item 2(d): the capture metadata (`captured_from`, `cockpit_sha256`, `now`, `browser_tz`) is untouched. The golden stores the venue engine's verdicts, not the desk block, so no venue row changed. Under the current policy (every rule on) five battery rows move; three of the eight have started.
- src/walters/desk_policy.py, `parlays_doc`: `desk_meta` carries `kalshi_leg_guard`, the same field `annotate()` writes into the `--desk` exports (#418).
- tools/cockpit.html: not changed. The Cockpit renders `desk.units`, `desk.cls`, tags and reasons from the file (`fileCall`) and computes none of them.
- docs/CLI.md: the `--desk` row gains #181's rule (both addenda) and the golden's amendment; the `desk-parlays` row lists its `desk_meta` fields, `kalshi_leg_guard` included. tests/test_desk_golden.py, scripts/desk_battery.py, scripts/desk_golden_capture.py, scripts/desk_parity_verify.py and scripts/cockpit_render_verify.py note the amendment.
- tests/test_desk_pass_units.py (14):
  - a pre-gate NHL PASS at 20pp and at exactly 15pp: units 0, class pass, no order, the reason is the pre-gate line alone and the tags `edge ≥ floor` alone (current policy and base_v11);
  - an NFL quarantine at 20pp keeps its 0.5u shadow and the caution tag (current policy and base_v11);
  - PASS paths in NHL, NFL (quarantine at 20pp, no reference, started), MLB (floor, > 8pp quarantine) and soccer (pick-prob floor, default rating): units 0, class pass;
  - the golden battery: no PASS call with units or a class other than pass, no PASS call with the caution reason, no pre-gate PASS with the caution tag (8 pre-gate rows at >= 15pp under base_v11, 5 under the current policy; the tag stays on 3 and 1 quarantine shadows);
  - venue PASS rows (the quote-age hold, below floor, single venue, books < 4, in-play, the CL stop, a shadow league): units 0, class pass; a VENUE row has no class (hold on and off);
  - PLAY sizing unchanged: NFL 1u play, NFL 16pp 0.5u caution (5 contracts), soccer LADDER 0.5u;
  - the parlays doc's `kalshi_leg_guard` equals an annotated export's, guard on and off.

## 2026-10-17 (#583: mlb-kalshi-window — #175, ARCHITECT addendum 112 item 8, addendum 117 item 1; Closes #175)
- deploy/hosting/chains.py: unchanged. The window's MLB Kalshi step stays `sync-kalshi --date-from {today} --date-to {tomorrow}`. Since #205 (2026-10-02), `--date-to D` reads the whole UTC day D (cli.py). Read from code, the step's window is our stored kickoffs from {today} 00:00Z up to {tomorrow}+1 day 00:00Z, which is the ruled end. It holds the 24 hours of every window run on {today}. The Issue's window (`--date-to` read as midnight, before #205) ended at {tomorrow} 00:00Z.
- docs/CLI.md: the `sync-kalshi` row says what `--date-from` / `--date-to` keep and where the window step's window ends.
- docs/specs/snapshot-retention.md: (F4) says #205 fixed the boundary it describes.
- tests:
  - test_hosting_pack.py: the window chain as sp_run resolves it on a UTC day D. The MLB Kalshi step is `--date-from D --date-to D+1`, every other step resolves to itself, and no other Kalshi step carries a date placeholder. Through the CLI, the step's window runs from D 00:00Z to D+2 00:00Z less a microsecond, past the 24 hours of the day's last window run.
  - test_kalshi_inplay_guard.py: a run at 23:05Z on D and a first pitch at 00:30Z on D+1. The step stores both legs; the Issue's window refuses them as outside the run's window.

## 2026-10-17 (#582: dedupe-orphans-isolation — #515, ARCHITECT addendum 112 item 3)
- tests/test_dedupe_orphans.py: each test that reads the OR1 world builds its own. A `world` fixture builds it fresh (any OR1 odds, matches, teams and competition dropped first) and drops it after. An `applied` fixture runs the apply test's own call (`md.orphans(CODE, prov, apply=True, now=NOW)`) on that world. The fixtures export and the apply summary read `applied`; the dry-run, the apply and the CLI dry-run read `world`. The module-shared world (`IDS`, `PROV`, `_shared`, `_world_once`) and the module cleanup are gone. **No behaviour change**: no production code moves, and every assertion is the one it was.
- Three tests depended on order, not one. The fixtures export (#515's) and the apply summary read the state the apply left, so both failed alone. The dry-run failed when it ran after the apply. Each now passes alone, in the file, in reverse order and in eight seeded shuffles. pytest-randomly is not installed (3.11 or 3.12), so the shuffles stand in for `-p randomly`.

## 2026-10-17 (#581: intl-tie-rejects — #330, ARCHITECT addendum 112 item 2, gate-class by label; Closes #330)
- src/walters/intl_elo.py `run()`: the log-loss criterion `crit_ll` is now `ll_model < ll_naive − 0.010`, unrounded, no tolerance, so a tie rejects (soccer-expansion-v1's F4 form, #326). It was `(ll_naive − ll_model) >= 0.010 − 1e-12`, which passed equality and anything within 1e-12 of it. One comparison: the walk, the bar, the bands and the verdict wording do not change. The module docstring quotes the ruling.
- Immaterial to the recorded verdicts (the run records' unrounded numbers, nothing re-run): intl-elo-v2 0.7889 against bar 1.0424 (0.2534 under it) and intl-elo-v1 0.8507 against bar 1.0431 (0.1924 under it) both pass the strict form, as recorded. No run record or registry entry is touched; the gate text (spec section 6, "A tie is a rejection.") is unchanged.
- The confirmation's criterion (`registry.record_confirmation`: `metric < reference`) was already strict and is unchanged.
- cli.py `intl-elo-backtest` docstring and the docs/CLI.md row: the criterion reads `log-loss < naive − 0.010` (unrounded; a tie rejects).
- tests/test_intl_elo.py (2): exact equality now rejects (the old comparison would have passed it); a model one ulp under the bar passes and one ulp over it fails; a model inside the old 1e-12 tolerance fails. Both recorded `crit_ll` values hold under the strict form.

## 2026-10-17 (#580: host-fence — ARCHITECT addendum 109 item 3, addendum 110 item 1, addendum 114 item 3; #410)
- src/walters/desk_policy.py: the host fence. On a machine whose role is not exactly `laptop`, every soccer model row is PASS, `pass_kind` `host_fence`:
  - role `host`: reason "host: ratings keyed to the laptop's team ids (#410); the cutover replaces this database" (addendum 109 item 3);
  - role unset (no source holds a value, or only an empty one): reason "host fence: role unknown (SP_EXPORTS_MIRROR_ROLE unset)" (addendum 110 item 1, ONE FLIP: "an unknown or missing role is FENCED, not open");
  - a value that is neither `host` nor `laptop`: reason "host fence: role '<the value as read, stripped>' is not host or laptop" (addendum 115 item 3b: "the wording is approved as Code wrote it").
  - It is checked first, before S1 and every other rule, so it overrides any PLAY, LADDER or other PASS kind. It is in NO_CALL_KINDS: units 0, no order, no exec block, no value shadow, no shadow units, never a parlay leg.
  - `rating_source`, `model_p` and the prediction block are unchanged; the row's model numbers stay in the file for the compare. INTL model rows (UNL, sport `intl`) are fenced with the soccer rows (addendum 115 item 3a); `HOST_FENCE_SPORTS` = SOCCER, INTL, and the one switch lifts both. MLB, NFL and market-only rows (the venue engine) are untouched under every role.
  - The role is the machine's `SP_EXPORTS_MIRROR_ROLE` (addendum 45 P1: host | laptop, no default), never `SP_WRITER_OF_RECORD`, which reads laptop on both machines until the cutover flips it (addendum 110 item 1, addendum 114 item 3). `role_reading()` / `machine_role()` read it, and the first source with a non-empty value decides: the machine's own host.env (`SP_HOST_ENV`, default `/etc/sports-predictor/host.env`; only the host has one), then the process environment (the units' EnvironmentFile, sp_run's `load_host_env`, config.py's `load_dotenv`), then the checkout's `.env` (`DOTENV`). Surrounding whitespace is stripped, as `closing.mirror_role()` strips it. A value that is neither host nor laptop decides too (unknown, fenced), never the next source's. A file that does not exist reads as empty and the next source decides. A host.env that exists but cannot be read makes the role unknown and nothing after it is read: fenced, reason `host fence: role unknown (host.env unreadable)` (ARCHITECT 2026-10-17 13:15 ET, addendum 116 item 2, law 4). An unreadable checkout `.env`, the last source, reads as empty.
  - Why host.env first (#410 review, P1): `closing.mirror_role()` reads the environment first, then host.env (`sp_common.setting`). A `closing-run` typed by hand on the host (the P8 rehearsal, under sudo) has no EnvironmentFile: it found `host` in host.env and signed its page `machine: host`, while its export step's environment had no role, or the laptop's role if the checkout's `.env` (a copy of the laptop's) carries it. That export ran the Desk unfenced, so a mis-keyed PLAY could reach the host pager and the window card. Reading host.env first fences that export, and any `cli.py` typed by hand on the host as `sp` or root (host.env is `root:sp 0640`). `closing.py` is not changed.
  - Why the `.env` last (addendum 110 item 1: "The laptop's .env carries the role line (the morning block checks it every day), so the laptop is never caught by it."): `cli.py` imports config.py, whose `load_dotenv` puts the `.env`'s role in the environment, but a script that never imports config does not. Reading the `.env` itself gives every laptop entry point the same answer. `DOTENV` is config.py's own path, `PROJECT_ROOT / ".env"` (the directory holding config.py), read with python-dotenv as config.py reads it; sp_common's `REPO / ".env"` is the same file.
  - Every path that builds desk blocks reads the role through this one function: the `--desk` exports (export-predictions, export-nfl-predictions, export-fixtures, export-unl-predictions: `maybe_annotate`), `desk-parlays` and `desk-rescore` (they re-evaluate the rows), a closing run's export step (a `cli.py` child), and the scripts that call `desk_policy.annotate` or `evaluate`. The window card copies the export's desk block, and its venue verdict (market-only) is never fenced.
  - The switch is `HOST_FENCE_RULE`. "The cutover PR does the flip and turns the switch off in the same change; the fence reads the switch, never SP_WRITER_OF_RECORD" (addendum 114 item 3). `host_fence_rule_off()` is for comparison. `base_v11()` holds it off, so the frozen golden passes whatever the machine's role.
  - desk_meta gains `host_fence_rule` (the switch). The role itself is not written there: it would part every laptop/host desk file in the daily compare.
- src/walters/desk_policy.py `rescore` + cli.py `desk-rescore` (#580 review): the fence is on in both of desk-rescore's sides (`addendum_off()` holds it, as it holds the quarantine and the kalshi-only suspension), so a laptop soccer PLAY re-scored on a machine whose role is host or unknown read `units published 1 / v1.1 0 → addendum 0 · UNCHANGED`, with "no executable quote" and nothing naming the fence. It is now its own transition, `HOST FENCE`, never halved or unchanged: the line reads `exec — (not priced: <the fence's reason>)`, the row carries `pass_reason`, and the summary counts it on its own line ("N soccer / INTL PLAY(s) now PASS under the host fence (this machine's role is not laptop; #410) — not counted as halved"). On the laptop the line is unchanged.
- The window card copies each row's Desk call (`window.canonical_models`), so on the host, or under an unknown role, a fenced row reads PASS 0u on the card and on the pager's line.
- docs/CLI.md (the `--desk` row), docs/specs/hosting-h1.md (under addendum 36 item 3) and docs/specs/h2-cutover-runbook.md (section 0): the fence, its role read and its switch.
- tests/conftest.py: every test is pinned to role laptop (addendum 111 item 4): `SP_EXPORTS_MIRROR_ROLE=laptop` in the environment (a child process inherits it), with `SP_HOST_ENV` and `desk_policy.DOTENV` naming files that do not exist, so no test inherits the machine's role and none reads a real `.env`. A test that needs another role, or none, sets or deletes it. Before the first pin, `SP_EXPORTS_MIRROR_ROLE=host python3 -m pytest -q tests/` failed 11 soccer Desk tests (all read `host_fence`); the suite now passes with the role exported as host.
- scripts/soccer_injury_factor_receipt.py: `earlier_kinds` follows `_desk_call`'s order with the host fence first. Under role host a one-sided case now reads as reached by an earlier rule (`host_fence`) instead of dropping out of every bucket.
- docs/specs/h2-cutover-runbook.md: two checks. Before `flip`, `HOST_FENCE_RULE` prints `{'on': False}` (anything else: do not flip, return it to the architect). After the flip, the host's first PL `--desk` file reads `desk_meta.host_fence_rule: false`. The PL check leaves the desk block out, so nothing else in the cutover reads the switch.
- tests/test_desk_host_fence.py (40):
  - the three ruled cases: two mis-keyed clubs (both `model`, foreign league labels, a full-unit PLAY with an order line on the laptop) under role host are PASS `host_fence` with the ruled reason and the row's other fields unchanged; under role laptop every call is unchanged (a PLAY, a LADDER, a value shadow) and desk_meta is the same file on either machine; under role unset (deleted, empty, whitespace) every soccer model row is PASS `host_fence` with the role-unknown reason;
  - eight values that are neither host nor laptop are PASS `host_fence` naming the value; surrounding whitespace is stripped;
  - the `.env` alone saying laptop (no role in the environment, no host.env) leaves the row unchanged, its host or invalid value fences, and the environment comes before it; a host.env that exists but cannot be read (or is a directory) is PASS host_fence `host fence: role unknown (host.env unreadable)` whatever the environment and the `.env` say, and a host.env that does not exist falls through;
  - host.env first: with the role only in host.env, `closing.mirror_role()` and `machine_role()` both read host (a child process with the environment's role removed reads host too), and host.env's host beats the environment's laptop; a host.env with no role line or an empty one leaves the decision to the environment, its invalid value fences, and its own `laptop` wins over the environment's `host`;
  - the switch off leaves every row unchanged under every role (host, unset, empty, invalid, laptop, `.env` laptop, host.env host);
  - the switch the cutover PR turns off is the one the fence reads: `HOST_FENCE_RULE["on"] = False` alone lifts it under role host and role unknown; `SP_WRITER_OF_RECORD` (laptop, host or unset, in every source) and `sp_common.writer_of_record()` change nothing, and desk_policy's code names neither;
  - `DOTENV` is config.py's `PROJECT_ROOT / ".env"` and sp_common's `REPO / ".env"`, read in a fresh process;
  - under role host and an unknown role, the fence overrides a LADDER, a value shadow, `default_rating`, `shadow_league` and `started`, and no fenced row is a parlay leg; MLB and NFL model rows and a soccer market-only fixtures file read as under role laptop; the card's copy reads PASS 0u and the pager line shows PASS and no PLAY;
  - the golden battery passes under role host and role unset;
  - desk-rescore of a laptop soccer PLAY reads `host fence` (with the fence's reason) under role host, unset and an invalid value, `unchanged` under role laptop and with the switch off; the CLI line ends `HOST FENCE`, names the reason, prints no UNCHANGED and no "no executable quote", and the summary counts it on its own line (5 cases).
- tests/test_soccer_injuries_one_sided.py (1): under role host the receipt counts a one-sided case as reached by `host_fence` first.
  - INTL (addendum 115 item 3a): a UNL model row is PASS `host_fence` under role host, unset and an invalid value, a PLAY under role laptop, and a PLAY again with the switch off.

## 2026-10-17 (#579: migrate-guard — #524, ARCHITECT addendum 112 item 1)
- src/db/migrate_guard.py (new): `refuse_missing_db(engine)`, the migrations' one shared guard. With no DB file at the engine's configured path it prints `no database at <path>; a migration never creates one — law 5` and the migration exits 1, before its first connection: the connect hooks in src/db/database.py, which make a missing directory and a new WAL-mode file, never fire. The path is the engine's own URL (`DATABASE_URL`, default `sqlite:///./data/sports.db`), a relative one read against the working directory as SQLite reads it. An in-memory SQLite URL is refused too. A non-SQLite URL passes: there is no file, and connecting to a server never creates its database.
- All 21 top-level `migrate_*.py` call it as the first step of `main()`, right after `engine = get_engine()` (which makes no connection). Nothing else in any migration changes. migrate_kalshi_settled_markets.py's own check (#521, "no DB file at <path> — nothing to migrate …") is replaced by the shared one and its ruled words.
- docs/RELEASES.md: one line beside "Run those by hand, after a backup".
- Not changed: database.py's `do_connect` mkdir, which the app relies on for a first run (out of scope per #524).
- tests:
  - test_migrate_guard.py (new): every `migrate_*.py`, found by glob, run in its own process with DATABASE_URL on a missing file in a missing directory: exit 1, the ruled line alone on stdout, and nothing created (no file, no directory, no sidecar). A relative URL is read against the working directory. migrate_kalshi_ticker.py and migrate_kalshi_settled_markets.py still migrate an existing DB and exit 0.
  - test_kalshi_history.py: the #521 guard test asserts the shared guard's words.
  - test_odds_source_updated_at.py: `test_migration_refuses_without_the_tables` passed because the migration created its empty DB (#524's shape). It now opens the empty DB first, so the test still reaches the missing-tables refusal.

## 2026-10-17 (#577: void-redated — ARCHITECT addendum 106 item 4, addendum 107 item A2, amended by addendum 109 item 2; addendum 114 items 1, 2, 4; addendum 115 items 4-5; #574, sibling #568; closes #578)
- The rulings of 11:00 and 11:30 ET, verbatim:
  - Addendum 114 item 1: "A parlay ticket with a leg void as re-dated: the leg is a PUSH — removed from the ticket, the ticket re-priced on its remaining legs and settled when they are all graded; a one-leg remainder settles as a single; the void leg stays on the ticket record labelled "void: re-dated", units unchanged on the record. The re-dated game's fresh closing row is never substituted into the ticket: it is a different call made at a different time. A ticket settles once (the bug the review found stays fixed); a ticket never stays open waiting for a game that moved. Test: a three-leg ticket with one re-dated leg settles as a two-leg ticket when those two grade."
  - Addendum 114 item 2: "Calls graded before this change on a game later re-dated stay graded, labelled "legacy join" in the exports — confirmed. Nothing is re-graded retroactively; the record says why those rows differ from the rule."
  - Addendum 114 item 4: "The back-to-back-days bug the build turned up (the ±1-day name join grading a call against the wrong game) is a finding in its own right: an Issue with the example, closed by #577, and a BACKLOG line naming how many graded rows the match-id pairing changes when it lands (the receipt from the exports before/after). If that number is not zero, bring it to me before #577 goes ready."
  - Addendum 115 item 4: "#577 parlays: a ticket whose every leg moved settles as a push — accepted; that is the reading of "never stays open waiting for a game that moved"."
  - Addendum 115 item 5: "The 14-day mirror receipt for #578 (main's Cockpit vs #577's on the same files, graded rows that differ): the right receipt. The mirror is read-only data for Code and nothing from it goes into the public repo beyond counts and match ids."
- #578, the back-to-back-days finding (addendum 114 item 4): this PR closes it (Closes #578 in the PR body). A call with a match id is graded on its own game's row only, never on the neighbouring day's.
- Receipt (addendum 114 item 4): 0 graded row(s) change between main's Cockpit and #577's on the laptop mirror's last 14 days (2026-10-04 to 2026-10-17); 43 calls captured on each side, 37 graded, 0 void, 6 open, 0 legacy join, 0 id mismatch, the same under three load orders; one graded call, match 50542, main pairs with the same teams' previous-day game, match 50512, when that day's Desk files load before its results (same result and return, a different close reference); match ids: none.
- src/walters/redated.py (new): the rule in one place. `redated_label(recorded start, current utc_date)` returns "void: re-dated <old> → <new>" (UTC, `YYYY-MM-DD HH:MMZ`) when the two differ by more than `desk_policy.DESK_CLOCK_DRIFT` (1h). Exactly 1h is not void; a start with no clock, missing or unparseable, is not compared.
  - Addendum 109 item 2 Q2: when the recorded start is the provider's placeholder (`src/ingestion/placeholder.py` `is_placeholder_kickoff`, 04:00:00Z, imported) and it moved more than 1h, the label is `PLACEHOLDER_LABEL`, "void: placeholder kickoff". One void state, two labels; an unmoved placeholder is graded as before. `void_counts` gives every count line its text, `re-dated N · placeholder kickoff M`.
  - `closing_starts` reads `exports/closing_*.json` (never `host/`) into each match's closing rows by match id (the run's start, the row's `utc_date`). An unreadable file is counted, never fatal.
  - `void_label`: a match is void when it has closing rows, none within the rule of its current start (the fresh closing on the new date is the graded row), and its latest is re-dated.
  - `label_rows` gives a results row the key `redated` (either label), never `status` or `void` (the Cockpit's intake would read those as a called-off game and refund the fresh call).
- tools/cockpit.html (repo copy; the live Cockpit is the published artifact): `gradeLedger` compares a call's kickoff with its matched result's date (`redatedLabel`, `REDATED_DRIFT_MS` = 1h, the same text as the Python rule). More than 1h apart: the call gets `void_redated` (the label), status `void` and no result. The fresh call at the new start is graded as before; a date with no clock is not compared.
  - Match id (addendum 109 item 2): `normalize` keeps each file row's `match_id`, `baseCall` stores it on every call beside the kickoff (null when the row had none), and the ledger JSON export carries both. `outcomesFromDoc` keeps each result's `match_id`.
  - `findOutcome`: a call with a match id pairs with the result row of that id only (one row; several are ambiguous and leave it open). A call whose id is in no loaded row stays open. A call without one is paired by the ±1-day team join as before, and `gradeLedger` gives it `legacy_join`. The re-dated check applies to both, so a game moved three days is void by id.
  - A match id is machine-local and reusable (the host and the laptop number matches apart; the Cockpit claims from either machine's files), so the row of the call's id must also name the call's home and away teams (`normTeam`). A row carrying the id for another game, of any sport, never grades or voids the call: it stays open and gets `id_mismatch`, listed in the ledger (`#idMismatch`) and counted in the intake note (`id mismatch N (match id on another game: counted, never graded)`). A later pairing that verifies grades it and clears the flag.
  - "legacy join" is shown: the ledger lists the graded legacy calls (`#legacyJoin`, folded under its count) and marks the void ones, and the intake note (`legacy join N`) and the P&L block (`Legacy join: N call(s)`) count them.
  - Legacy join, a label (addendum 114 item 2): `labelLegacy`, on every read of the ledger (`loadLedger`), gives `legacy_join` to every call without a match id that a pairing reached (a result, or void as re-dated), whenever it was graded; the ledger views and the ledger JSON export carry it. A call graded before this change is never revisited ("nothing is re-graded retroactively"): its status, result and returns are untouched; a stored flag is never removed; an open call with no result is not labelled. `importLedgerDoc` labels the incoming rows the same way, so an export from before the label is not counted "updated" by it.
  - The placeholder: `isPlaceholderKickoff` mirrors `is_placeholder_kickoff` (parity checked in the Playwright script); `redatedLabel` returns `PLACEHOLDER_LABEL` for a placeholder kickoff that moved. The intake note and the P&L block read `void: re-dated N · placeholder kickoff M` (`voidCounts`).
  - Out of every tally: `settledBets` / `agg` / the tables / equity / P&L read status `graded`; the CLV series, the n/30 counters (`gradedCount`), `ledgerSummary` and the early-execution count (`earlyMarkerLine`, the n/50 revisit) skip `void_redated` explicitly. One exception (addendum 115 item 4): a ticket whose every leg moved is a settled push carried by its void legs (`ticket_result` "push"); `settledBets` counts it (n, staked, returned) and `earlyMarkerLine` counts it once when executed early, as a pushed straight is. The P&L block's Void line, the void list's header and the intake note name the exception (`out of every line above, except a ticket whose every leg moved: counted there once, as a push; the fresh call on the new date is its own call, graded, never a leg of the old ticket`).
  - Parlay push (addendum 114 item 1; addendum 115 item 4): a leg void as re-dated, either label, is removed from its ticket (`pushedLeg`, replacing `settledVoidLeg`): never reopened by a re-log, and never graded at a later intake once paired by its match id or once its ticket has settled. A legacy leg (no match id: the ±1-day team join) on an open ticket is checked again at each intake, as a straight is: its void may be the same teams' game of the neighbouring day (#578, LCS-style back to back), not a move, and its own game's row within the hour of its kickoff grades it (the ticket never waits for it: a void leg is out of the remaining legs). The void list marks such a leg `(no match id: checked again at each intake while its ticket is open)`. The ticket is re-priced on its remaining legs (only the winning legs multiply the stake, as a pushed or called-off leg already dropped out) and settles when every remaining leg has a result, or at once on a losing one (the ticket rule as it was). One remaining leg pays stake / its price, a single's return. Every leg moved: the ticket settles at once as a push, stake back, `ticket_result` "push" on its void legs (status and labels kept), counted by `settledBets` as a push (n, staked, returned; out of the hit rate). The void leg keeps its label, status and units and takes none of the ticket's fields; the remaining legs carry `ticket_legs` (1: a single; 0: every leg moved). A ticket settles once (`ticketSettled`: a leg graded or carrying `ticket_result`). A same-ticket re-log of a leg at a kickoff more than the hour from its recorded one never rewrites it (`movedLeg`): the moved game's fresh row is never substituted into the ticket. A later-day re-log of the ticket (the next day's Desk re-emits it as P-<day2>-<the same signature>; the other legs reprice into the stored ticket by position) keeps that leg's moved game too (`upsertCalls`, `movedFrom`), never a one-leg ticket of its own: on main and before this, it was added as a 0.25u "parlay" nobody issued, a second ticket in `settledBets`. Its stored leg is the one with the same game, pick and ticket signature and the same match id, or, a legacy leg, the one on the ticket a sibling leg of the same fresh ticket reprices into. A different match id (the series' next game of the matchup) is never read as moved and is added as before; a legacy leg cannot tell the two apart, and on an anchored ticket is kept either way. The void list says where each void leg's ticket stands.
  - The ledger lists each void call with its label; the P&L block and the results-intake note count them.
  - A void call is checked again at every intake: a result within the hour of its kickoff grades it and clears the label (a parlay leg: a legacy one, while its ticket is open). A re-log of the position (`upsertCalls`) reopens it without the label or the legacy flag; a parlay leg the legacy join already graded (its ticket waiting) keeps the flag, since nothing grades it again.
- Results exports: a row void by its closing rows keeps every field, gains `redated` and leaves every tally; `record.redated` counts them (either label).
  - `export.export_results` (record games / hits / `vs_close`, `totals_pulse`; new `exports_dir`, default `exports`), `nfl_predict.export_nfl_results` (season and pre-live records, read from `out_dir`), `intl_production.export_results` (read from `out_dir`).
  - `nfl_predict.grade_nfl` (new `exports_dir`) leaves the game out and names it under `── void: re-dated N · placeholder kickoff M`, so nfl-grade, the file and RESULTS.md state one record. A window whose games are all void still names them: the not-ok return carries `redated` / `redated_rows`, and RESULTS.md's NFL section reads `No graded games in window.` with the void line, as MLB and Soccer do.
  - `export.results_tally` (new `exports_dir`): the MLB, Soccer (PL) and NFL sections leave the game out and name it on a `- Void: re-dated N · placeholder kickoff M` line, printed only when a game is void.
  - cli.py: `export-results`, `export-nfl-results` and `export-intl-results` print `void: re-dated N · placeholder kickoff M (kept in the file, out of every tally above)` and one line per row. `export-nfl-results`' pre-live line takes its games from the pre-live record, and `--match` reads a void row `IN the file (void: re-dated, out of every record)` or `IN the file (void: placeholder kickoff, out of every record)`.
- The ledger ports: `ledger_fills.executed_positions` never reads a `void_redated` call. `k_receipt`: such a call is never eligible; `format_fills` prints `void: re-dated N · placeholder kickoff M` and names each call that would otherwise have been eligible (a void shadow or parlay leg was never in the reconciliation), and a fill matched to one is counted apart (`on a void call N`). Under it, `legacy join N of the eligible calls` (`reconcile()["legacy_join"]`). `scripts/value_shadow_receipt.py`: out of every total and the n/30, listed with its label on a `void: re-dated N · placeholder kickoff M` line, `void_redated` in the JSON line; a legacy-join row is marked `legacy join` and counted on its own line (`legacy_join` in the JSON line). Fills carry no match id, so the ports still fit a fill to its call by game, side and day.
- scripts/replay_inventory_probe.py: a game's closing is void when none of its closing rows' starts is within the rule and its latest is re-dated (a latest row not comparable is not void). A void game is listed with its label and left out of `closing` and `all_four`; each group prints `closing void (games left out of closing and all four): re-dated N · placeholder kickoff M`, and the JSON carries `closing_redated` per group and in total.
- scripts/cockpit_redated_verify.py (Playwright, 87 checks): 50548 called at 10-17 00:00Z and again at 10-18 21:00Z against a results row dated 10-18 21:00Z. The old call is void with the exact label and the fresh one graded. A value shadow and a parlay leg at the old start are void too. 50547, exactly 1h and a date-only result are graded; 61 minutes is void. Every tally counts only the graded calls, and the labels match `redated.py` word for word. These calls carry no match id: each is paired by the ±1-day join and shown "legacy join".
  - A series (#574 question 1, legacy calls): one day's result was the only match for the neighbouring day's open call (same teams, the ±1-day join) and graded it. That call is now void, and it is graded at the intake that holds its own result.
  - A ticket settles once: a leg voided at intake 1 (the ticket settles on its other leg) and matched to its own game at intake 2 stays void with its label; the ticket's return and result are unchanged, the note counts 0 graded, and a re-log (same day at a new kickoff, or a later day) is kept, never reopened. With the old and the fresh 50548 call both executed early, the early-execution count reads 1.
  - The Cockpit import (addendum 109 item 2): the 50548 export rows (old start, then new) loaded through `#predFile` become calls carrying `match_id` 50548 and their kickoff; the intake voids the old one and grades the fresh one by id; the downloaded ledger JSON carries both fields.
  - By match id: a game moved three days is void (the same call with no match id stays open in the ±1-day join); a series' two games are each graded on their own; a call whose id is in no loaded row stays open while a legacy call takes the same-teams row, flagged; a call recorded at 04:00Z whose game kicked off at 23:30Z is "void: placeholder kickoff" and an unmoved placeholder is graded. The placeholder test and the count line match the Python's.
  - A machine-local id: an NFL call whose id a loaded MLB row carries, and one whose id an NFL row of other teams carries (3h 05m apart), stay open, never graded or voided, counted and listed "id mismatch". Its own game's row under the id grades it although another file's row carries the same id, and the flag clears. A soccer call pairs by id with a PL fixtures row naming its teams (the two files name the sport apart). A parlay leg the legacy join graded, its ticket waiting, keeps "legacy join" and its result through a re-log that brings a match id.
  - The ruled ticket (addendum 114 item 1): legs A, B, C by match id, A is 50548 at its old start. A is void with the label, units 0.25 unchanged on the record; a same-ticket re-log of A at the moved kickoff, before the void or after it, is kept and never rewrites A, and a fresh call on A's game at the new start is its own call; the ticket stays open while C is open (B graded, waiting), a later row for A within the hour of its kickoff never undoes the push, and the ticket settles as a two-leg ticket priced on B and C (0.25 / 0.45 / 0.5) when they grade, once (a later intake with A's id at its old start and B and C reversed changes nothing). A later-day re-log of the ticket (P-2026-10-17-T3, A at 10-18 21:00Z with match id 50548, B and C at their kickoffs) reprices B and C and keeps A, nothing added, and `settledBets` still lists the one ticket; a legacy ticket the same (a sibling leg anchors it), while a fresh leg of a different match id (the series' next game) is added as before.
  - A two-leg ticket with one re-dated leg settles as a single on the other leg (`settleReturn`'s 0.25 / 0.6); a ticket whose every leg moved (a re-dated and a placeholder leg) settles as a push on its void legs, counted as a push (n 1, net 0, out of the hit rate); executed early, it is one early position (`Early executions: 1 position(s)`), and the P&L block's Void line names the exception; a later intake changes neither (addendum 115 item 4).
  - A legacy leg on an open ticket (#578): three legacy legs at 0.5; intake 1 holds only the same two teams' previous game, the ±1-day join's only match for leg A ("void: re-dated 2026-10-20 00:08Z → 2026-10-19 00:08Z", the ticket open, the void list marks it checked again); intake 2 holds A's own game on schedule and B and C, all wins: A is graded and the ticket settles on its three legs at 2.0 (the build before this fix kept A pushed and settled two legs at 1.0).
  - Graded before this change (addendum 114 item 2): a straight and an old ticket's legs, no match id and no flag, are labelled "legacy join" in the ledger list, the intake note, the P&L block and the downloaded ledger JSON, their status, result and returns unchanged although a loaded row disagrees; a call graded by id and an open call are not labelled; an import of those rows as stored before the label reads `0 updated`.
- scripts/cockpit_leg_audit_verify.py, scripts/cockpit_ledger_audit_verify.py: their never-deleted checks treat `legacy_join` as a mark, as they treat `tz_audit` (addendum 114 item 2: a label, never a stored field's change).
- scripts/cockpit_intl_verify.py: its results and fixtures rows carry the match id, as the exports write it (the call pairs by it).
- docs/CLI.md: the rows of `export-results`, `export-nfl-results`, `nfl-grade`, `export-intl-results`, `k-track-receipt` and `results-tally`.
- tests/test_void_redated.py (29): 50548 verbatim through `closing.closing_doc`, by match id (another match's closing at the new start never stands for it); the fresh closing makes it graded; 50547; exactly 1h; 61 minutes; date-only; a game moved three days (the rule and the MLB export); the placeholder (moved: its own label; unmoved or within the hold: graded; the NFL file, nfl-grade, the console and `--match`; the replay inventory); the Desk's constant read at call time; unreadable files and `host/`. Each surface (the MLB, NFL and INTL exports and their consoles, nfl-grade, RESULTS.md, the three ports, the replay inventory) leaves the row out and counts it; so does an NFL window whose only game is void, the `export-nfl-results` `--match` receipt and pre-live line, and the k-receipt, which never counts a void shadow or parlay leg. The ports count a placeholder void apart and a legacy join on its own line. An unmoved game's export is byte for byte the export with no closing file.
- tests/test_window_card.py: the card's row carries `match_id` and its kickoff. tests/test_value_side_and_qb_audit.py: the stubbed `grade_nfl` takes `exports_dir`.

## 2026-10-17 (#576: coverage — ARCHITECT addendum 107 item C7, amended by addendum 111 items 1-2; Closes #575)
- cli.py `coverage [--date YYYY-MM-DD]`, built in deploy/hosting/coverage_map.py: the day's coverage, read-only. The DB is opened mode=ro (a missing file is refused, never created); no row or export is written; no provider call. On a WAL file SQLite itself may leave its -wal/-shm sidecars, as for every `ro_connect` reader. It reads the DB, the roadmap and the registry, the watch's schedule inputs (chains.py, closing.py) and the watch's receipt log, plus the settings `closing._family_refusal` and `sp_run.active_from` read (SP_SKIP_FAMILIES, a chain's `active_from_env`), nothing else.
  - The day: `--date`, default today in US Eastern. A game belongs to the day by its US Eastern date (`closing.ny_date`). Void games (`closing.VOID`) are named and not counted.
  - One line per competition with games that day: the games; the status with where it was read; the stored prediction rows by model_version with their computed_at in ET (`latest …`, or `computed <earliest> to <latest>` when the rows differ, so an old row is never hidden behind a fresh one; the map keeps each game's own), and the games with none; the closing groups of the day.
  - The status, in the ruled order (addendum 111 item 2):
    - LIVE: a closing family covers the competition and the model its closing chain's predict step writes with resolves. For `predict --sport S` that is the one production row of S's model family in `model_versions` (`training.MODEL_FAMILIES`, as `_current_production_version` reads it). For `predict-nfl` it is `nfl_predict.MODEL_VERSION`. The line names it: `LIVE (closing family SOCCER; production soccer_elo_poisson v22)`. No production row, or more than one, is not LIVE: the reason stays on the line and the derivation goes on.
    - SHADOW: a roadmap lane names the competition in its new `competitions` field, and either the lane is confirming with its registry entry confirming, or a chain in chains.py runs a shadow export for the competition (one of the four cli commands whose rows carry engine `model_shadow`, in a chain whose steps name the competition). NHL qualifies by nhl-daily's `export-nhl-predictions`; UNL and PD by their confirming lanes; NCAA's declared lane has no shadow export scheduled. A chain outside its season gate on the day runs nothing (`sp_run.active_from`: its `active_from_env` setting, such as SP_NHL_ACTIVE_FROM, else chains.py's date; sp_run skips it before that date and fails it on a malformed setting), so it is no schedule that day and the line names the gate: `no shadow export scheduled for NHL (chains.py: nhl-daily inactive until <date> [<source>])`. The tag is the vN token of the shadow's id, or the full id where there is none.
    - MARKET-ONLY: the code's own sets, imported: `desk_policy.SHADOW_VENUE_COMPS` (the set `_refuse_shadow_league` refuses), `chains.EXPANSION_CODES`, `chains.KALSHI_CAPTURE_ONLY`, `export._MARKET_ONLY_REASON` (NHL, NCAA, UNL) and `cup_coeff.EXAM_COMPS` (CL, EFL, UEL; EL, the adapter's alias for UEL). Both SHADOW and MARKET-ONLY print `MARKET-ONLY · shadow v7` (NHL), `· shadow v2` (UNL), `· shadow v1` (PD).
    - UNKNOWN only when none applies, with every reason. A roadmap or registry that cannot be read judges no shadow, and the line says so.
  - The closing groups:
    - A run done (addendum 111 item 1) prints `T-35 HH:MM ET [match ids] done (run <run_id>, <exit>)`, the ruling's words. The run id, exit and covers are the receipt's own (`closing._attempts`: a refusal or a superseded run is no run). Where a start time has several runs, the latest success prints where there is one (`closing.closing_state`: a later failed run, such as an operator's re-run, never hides it); else the latest run.
    - A done start time is never printed as due. Where the watch still forms a group at it, the line says what the watch does with it, as the watch decides: `(attempt N of 3: the watch tries again)` only ahead of T-5 with no success and fewer than three attempts; `(inside T-5: no further attempt, the watch records a miss)` inside T-5 (`closing.due`'s inside, `closing.watch`); `(a successful closing: the watch runs it no more)` or `(3 attempts: …)` where `closing._under_lock` supersedes it. Then `; not in its covers: <ids>` names the group's games the run's covers do not hold.
    - Then the export file the run landed in, the receipt's own `closing_file`: `; closing file exports/<name>`. Where closing.py's write failed after the page went out (`closing_file_failed`, or an error in `closing_file`: the run is exit 0 and never run again), `; closing file NOT written (exports/<name>): receipted and notified, not run again`, closing.py's own words. Only the receipt is read, nothing under exports/.
    - Then the groups the watch will run: `closing.groups()` on `closing.due()`'s own inputs (the stored games plus the unpaged called-off ones, `with_called_off`, less the games a closing has finished with, `covered_ids`), over the family's games of the day at now. `started …` and `a closing finished with …` (a game whose run is no done line of the day) come first, then `T-35 HH:MM ET [match ids] → exports/closing_<FAMILY>_<start>.json`, marked `(due now)` from T-35 to T-5, or `inside T-5: no attempt, no file` for a miss.
    - A family this machine refuses (`_family_refusal`: SP_SKIP_FAMILIES, MLB on the host) prints `closing: refused here (…)`. Receipts that cannot be read print `closing: not shown (…)`.
  - Then the gaps in capitals: a LIVE competition with a game that has no row, `PL: 4 GAMES, 0 PREDICTION ROWS — soccer-prematch has not run`, or `MLB: 2 GAMES, 1 PREDICTION ROW, NONE FOR 50549`; none for a family this machine refuses. The hint names the chain whose predict step matches the closing chain's word for word (SOCCER soccer-prematch, MLB mlb-preslate, NFL nfl-predict); no chain found, no hint. Then one line naming the UNKNOWN competitions, for which no gap is judged. No gap is claimed for SHADOW or MARKET-ONLY competitions.
  - Exit 0 whatever the gaps; a `--date` that is not real, a DB that cannot be opened or read, or a DATABASE_URL that is not SQLite exits 2.
- docs/roadmap.json: each of the eight lanes gains `competitions`, as ruled (addendum 111 item 2): unl [UNL], pd [PD], leagues [SA, BL1, FL1, ELC], ncaa [NCAA], nhl [NHL], cups [CL, EFL, UEL], nfl-qb [NFL], mlb-pitchers [MLB]. No other byte of a lane changes: no date, no text, no moved line.
- src/roadmap.py: `competitions` is optional in the validation (`validate()` checks it by name; `OPTIONAL_LANE_KEYS` only lists it). Where a lane carries it, it is a non-empty list of competition codes, unpadded, each named once. The print does not show it, and the base check (dates and moved lines) is unchanged.
- docs/CLI.md: the `coverage` row, and the field on the `roadmap` row.
- tests/test_coverage_map.py (55 tests, throwaway DB, a scratch receipts file):
  - the spec's three: a day with rows, a day with a gap (the spec's example line word for word), and a market-only sport (NHL with its shadow v7, NCAA); also an old row shown beside fresh ones;
  - every status branch: LIVE from a closing family and its production row (PL v22) or its constant (NFL); a closing family without a live model (no production row, two, no table); SHADOW from a confirming lane (UNL, the both line; EL2, SHADOW alone); NHL `MARKET-ONLY · shadow v7` by nhl-daily's shadow export, and without it; NHL's shadow gone outside nhl-daily's season gate (SP_NHL_ACTIVE_FROM the day after, a malformed setting, a past day before chains.py's date) and kept on the gate's own day; NCAA MARKET-ONLY, and reported as a shadow were a chain to run its export; CL, EFL, UEL and SA, BL1, FL1, ELC MARKET-ONLY from the code's sets, read at run time; UNKNOWN for a code nothing names, a registry id the registry does not hold, and a lane that disagrees with its entry; an unreadable roadmap;
  - on the tracked files and code: the ruling's statuses word for word; the market-only sets pinned as the code's own; the shadow exports pinned to the cli and to every model_shadow module; the live model pinned to the predict path; the tag;
  - runs done: `done (run <run_id>, <exit>)` (refused, superseded, other-day and other-family receipts not counted); a failed attempt then a success prints the latest; a later failed run never hides a success; a done start time never printed as due, then three failed attempts; a failed run inside T-5 is a miss, never tried again; a start time the watch supersedes (three attempts, or a success) names the game its covers do not hold; a game added after a failed run is named on the line that says the watch tries again; the closing file named on a done line, and `NOT written` where closing.py's write failed (flagged, or an error alone); a game finished with by a run of the day before keeps its line, and a run with no covers still prints;
  - the closing groups and files on a day with two start times, started games leaving them, and the groups to run equal to `closing.due()`'s after a closing finished with part of a start time; a family this machine refuses; receipts that cannot be read;
  - the default date across the UTC midnight, and the 25-hour day of 2026-11-01;
  - no write transaction (every connection mode=ro, every statement a SELECT, the file's sha256 unchanged; on a WAL file only SQLite's own -wal/-shm sidecars, the -wal empty) and no network;
  - a missing DB is refused and not created; a DB that cannot be opened and a URL that is not SQLite are refused; a date that is not real is refused; the SELECTs run on the ORM's real schema;
  - the hint's derivation from chains.py, and the two predict commands pinned as the only cli writers of prediction rows.
- tests/test_roadmap.py: the eight lanes carry the ruled lists; the field is optional; a malformed list (not a list, empty, a code that is not text, blank or padded, a code twice) is refused and named.

## 2026-10-17 (#573: ncaa-range-note — #570, ARCHITECT addendum 106 item 3, addendum 107 item A1)
- src/adapters/api_american_football.py (NCAA and NFL): `list_matches` prints one line before the fetch when `--date-from` ≠ `--date-to`: `RANGE A..B is not supported by this provider: reading and writing the whole <season> listing` (`range_note`). The provider's `/games` takes one `date`, so a range has always read and written the whole season. **No behaviour change**: the same call is made and the same listing written.
- cli.py `sync-matches --match-ids`: both strict lines carry the same words when the adapter could not send the range. The `✗ STRICT` label reads `(<code> A..B: RANGE …)`, and the `✓` line ends `(RANGE …)`.
- src/ingestion/resync_diff.py: `resync-diff` marks its adapter read-only, so its note says `reading`, not `reading and writing`.
- docs/CLI.md: the `sync-matches` row says so.
- tests/test_range_note.py (4): the note's words and where it prints (a range only; a single day and a season read print nothing); the line comes before the fetch and the call is unchanged; the STRICT label through `sync-matches` (#570's faked-provider receipt); `resync-diff` says `reading`.

## 2026-10-17 (#572: kalshi-history-429 — ARCHITECT addendum 104 item 2)
- src/ingestion/kalshi_history.py (`kalshi-history`): a 429 is asked again in the run, after 2 s and then after 5 s (`RETRY_429_WAITS`), on any call: the cutoff, a list page or a candle call. Each retry is a call against `--max-calls`, and none is made past the cap. A third 429 counts the call failed, and the next run asks it again, as before. Nothing else is retried. The receipt prints `429 retries: N` on every run, after the no-candles breakdown.
- src/ingestion/kalshi_match.py: the two-rows refusal on a clock ticker with no game number. Rows hours apart (an MLB doubleheader) now read "two games of the pair that day; the clock does not separate them". Rows at one kickoff minute are one game stored twice (#569), so they keep "dedupe-matches has to merge them", and the line names them. Where both hold, the line says both. On a date-only ticker (a placeholder and a second row) the line still names the rows dedupe-matches has to merge. The reason, the refusal and every other line are unchanged.
- docs/CLI.md: the `kalshi-history` row says how a 429 is handled.
- tests:
  - test_kalshi_history.py (+9): a 429 then the answer, stored after a 2 s wait; two 429s, waits 2 s and 5 s; a third 429 counts failed and the next run stores it; a 429 at the cap is not asked again; a 503, 408 or 404 is asked once; the receipt line on a clean run, after the no-candles breakdown.
  - test_kalshi_matcher_day_rule.py: the doubleheader line; two rows at one minute keep the dedupe words; a doubleheader with one game stored twice names both.

## 2026-10-17 (#571: lineups-save-fix — #565, ARCHITECT addendum 104 item 4)
- src/ingestion/lineups_history.py (`sync-lineups-history`), #538's two round-2 findings (#565):
  - `--save` keeps an HTTP error answer's decoded body. The request wrapper keeps every answer's body as it arrives, whatever its status. The HTTPError branch saves it as `<fixture id>.http<status>.json` before the run stops (401, 403, a 429 after the adapter's own retry) or moves on (any other status). The name means it never replaces a lineup answer an earlier run kept as `<fixture id>.json`. A body that does not decode keeps nothing, as before.
  - `refreshed_at` is taken per fixture, just before its store. It is no longer once for the whole run, which left a 100-call run's last rows about 10 minutes early.
- docs/CLI.md: the two sentences that describe `--save` and the rows' time.
- tests/test_lineups_history.py (+3): a 500 body kept while the run moves on, and a 429 body kept before it stops (the adapter's one retry counted); a later run's 503 body kept beside an earlier run's lineup answer, never over it; two fixtures each carry their own `refreshed_at`.
- Ledger only, from the same day's rulings: addendum 103 item 1 (#568), addendum 103 item 3 (the NCAA resync answer on #399; #570) and addendum 105 (MLB twin rows, #569).

## 2026-10-16 (#566: web-ncaa-fence — ARCHITECT addendum 99 items 2(2) and 5, addendum 100 item 1; #560, #567)
- src/walters/ncaa_backtest.py: `v2_fence_view(code, season)` returns the withheld notice while the shown season is NCAA's 2026 and the ncaa-elo-v2 run is unrecorded, else None.
- src/web/routes/home.py + templates/league_dashboard.html: the league view (`/?league=NCAA`) withholds its 2026 league table until the run is recorded. The table's place reads "withheld until the ncaa-elo-v2 run is recorded" (the 2026 fence, addendum 86 item 3, Q2). Its single-game lists stay (the level ruling); every other league is unchanged.
- src/web/routes/matches.py + templates/match_detail.html (ARCHITECT 2026-10-16, addendum 100 item 1; #567, Codex's P1 on #566): an NCAA 2026 fixture's page reads the same notice while the run is unrecorded, through the same helper. The notice replaces each side's record (W-D-L, points), its form strip (the last-5 pills and the goals for/against totals) and the head-to-head aggregate line. The prediction narrative, which reads those tallies, is not built.
  - The fixture's own score, the two teams and the single-game lists (each side's recent games, the head-to-head meetings, each with its score) stay.
  - Any other league or season is unchanged.
- docs/RELEASES.md: the ritual's step 2 makes `logs/` first (`mkdir -p logs && python3 scripts/release_notes.py ...`). A fresh or cleaned checkout has no `logs/`, and the redirect failed before the script ran (#560, Codex on #558 round 2).
- tests/test_web_ncaa_fence.py (5):
  - the helper: NCAA 2026 alone, lifted by the recorded run;
  - the league view: the notice in the table's place, the single games kept, the table back once recorded;
  - the NCAA 2026 match page: record, form strip and head-to-head aggregate withheld, the teams, scores and single games kept, every figure back once recorded;
  - another league's match page, untouched;
  - the release step's `mkdir -p logs`.

## 2026-10-16 (#563: mlb-no-book-odds — ARCHITECT addendum 97 item 2; #550, #514)
- src/ingestion/service.py: `sync_odds_mlb` records on `SyncResult.no_book_odds` every game it leaves with no complete book, with the provider's answer for it. That covers the per-game fallback's games and a bulk-matched game stored with no complete book.
  - The answers (`NO_BOOK_ODDS_WHY`): "provider listed the game, no odds" (the ruling's words); no game in the provider's listing matched it; the games listing read failed; a doubleheader id already taken; a failed odds read; a started game; no complete book.
  - When the fallback never runs (an empty odds window, a failed window read, no key), the run's own answer goes on `no_book_odds_run` (`NO_BOOK_ODDS_RUN_WHY`).
  - The per-game log lines are unchanged.
- cli.py: `sync-odds --competition MLB` prints one plain `NO-BOOK-ODDS (MLB)` line just before its `✓ MLB odds` summary (inside a closing run's five-line step tail; the summary stays `sp_receipts`' key line), naming each such game: match id, the answer in brackets, the teams and the provider's game id. When the fallback never ran, the line is `NO-BOOK-ODDS (MLB): run [<answer>]`. No line is printed when the sync named no game and its odds window answered.
- deploy/hosting/closing.py:
  - `no_book_odds` reads the sync-odds step's line from its tail into the run (`books_why`). The step's receipt records it (`no_book_odds`).
  - `closing_doc` gives an MLB closing file's closing block `books`, one entry a row: `{match_id, n, why}`. `why` is null when the row shows books. When n is 0 it is the sync step's answer for the game, else its run-level answer, else "the sync step named no answer for the game" (law 4: never a guess).
  - The rows stay as the export gave them. Other families, and the backfill, write no `books`.
- src/walters/mlb_actionable.py + cli.py `mlb-actionable-receipt`: the postseason split carries "closing runs with no provider odds: N of M" (`closing_tally`, read-only). It reads the `exports/closing_MLB_*.json` files and each row's season and stage from the DB, with the games' count, the files with no odds and any unreadable file.
- docs/CLI.md: the rows of `sync-odds`, `closing-run` and `mlb-actionable-receipt`.
- tests/test_no_book_odds.py (12):
  - the sync's answers and its line, read back by the closing run;
  - a failed games listing, never read as the game not listed;
  - a bulk-matched game stored with no complete book, named;
  - an empty odds window: the run-level answer, given to every no-book row with no answer of its own; a failed window read and no key, each its own answer;
  - the fallback's failed odds read, doubleheader guard and one-sided board, each its own answer;
  - the CLI prints the line inside the step's five-line tail, with the summary still last (the receipts' key line);
  - the 10-15 shape through a closing run: match 104 listed with no odds, the books entry naming it, why null where books exist, the rows untouched, the step's receipt;
  - a no-book row the sync did not name;
  - only MLB, and the backfill unchanged;
  - the receipt's tally, and the command printing it in the postseason split.
- tests/test_closing_file.py: the MLB closing block now expects `books`.

## 2026-10-16 (#561: ncaa-2026-fence — ARCHITECT addendum 86 item 3 (Q2); addendum 96 item 1)
- src/walters/ncaa_backtest.py: the 2026 fence, in v1r's form.
  - `V2_FENCE` holds the ruling verbatim, with `V2_FENCE_RULING`, `V2_FENCED_RATE` and `v2_fence_refusal`.
  - `v2_run_recorded()` reads only the registry: ncaa-elo-v2's `run`; an absent entry reads as not recorded. The fence lifts with the recorded run, never by a flag.
  - `coverage_report(..., fenced_v2=None)` and `V1RStream.lines(..., fenced_v2=True)`: ncaa-cfbd-coverage prints no 2026 home win rate in either block. Counts, coverage, the census and the neutral counts stay; the #79 block's withheld line keeps its n.
  - `v2_fence_walk` and `FenceRefused`: the generic walks score whatever competition they are given. `run_backtest` (src/walters/backtest.py) and `run_soccer_backtest` (src/walters/soccer_backtest.py) therefore refuse NCAA with 2026 among their seasons. So do the commands that call them: `backtest`, `soccer-backtest` (its three `--candidate` modes included, checked before dispatch: Codex on #561), `dixon-coles-sweep` and `elo-coeff-sweep` (exit 2, naming the ruling). Found by the review before opening: the ruling's "no command prints an outcome figure of the 2026 season".
- cli.py:
  - `ncaa-audit` with 2026 among its seasons refuses, exit 2, naming the ruling, before anything is read. Its default seasons are 2025 alone until the run.
  - `resync-diff --competition NCAA` prints the home-rate line as withheld when the listing includes 2026 (no `--season`, a blank one, or 2026). n and the single-game samples stay. A blank `--season` now reads as none, so the 2025 fence covers it too.
- scripts/ncaa_source_probe.py: 2026's rate-and-margin lines print n and ncaa-elo-v2's withheld notice (`fenced_notice`). This holds for `--year 2026`, and for a `--from-file` whose records carry season 2026 under another `--year` (`fenced_year`).
- docs/roadmap.json: the ncaa lane's step 2 ("the declaration PR open, its checks green, nothing run") is done, receipt "#553 merged at 81ea7c0" (addendum 96 item 1).
- docs/specs/ncaa-elo-v2.md (Q2 built) and docs/CLI.md (the rows of the three NCAA commands, and of `backtest`, `soccer-backtest` and the two sweeps).
- tests/test_ncaa_2026_fence.py (6):
  - the ruling verbatim, and the registry-only switch;
  - coverage in both blocks;
  - ncaa-audit's refusal and its default seasons;
  - resync-diff, a blank `--season` included;
  - the probe's `main()` over saved records, by `--year` and by the records' season;
  - the generic walks' refusal.
- tests/test_ncaa_audit.py and tests/test_ncaa_v1r_fence.py: the tests that read 2026 now say which fence they exercise. The v1r coverage test checks each season's own line.
- tests/test_ncaa_elo_v2.py: the roadmap test reads step 2 done (#553 merged) and step 3 open.

## 2026-10-16 (#559: window-sync-continue — ARCHITECT addendum 84 item 2(b), #555)
- deploy/hosting/sp_run.py: `run_steps(..., continue_sync=, report=)`.
  - In a chain flagged `continue_on_sync_failure`, a failed step whose command starts `sync-` (`SYNC_PREFIX`) is receipted as now, marked `continued`, and the run goes on.
  - A failed card/export step still stops it.
  - The return is the first failed step's exit: non-zero when any step failed, so systemd's OnFailure notice fires as before.
  - Every chain's receipt adds `failed_steps` ([{step, command, exit}]) and `stopped_at` when a step failed.
  - The chain's last output lines name each failed step: `✗ step i/n exit=rc: <command> — <its last output line>`, plus `✗ stopped at step k/n` when a step ended the run. The failure page reads the journal's last 30 lines, so it names the failure even after later steps ran.
  - The `· sync step failed` line names the step and its command.
  - The window page post runs after a clean run, or when only sync steps failed and the card ran.
- deploy/hosting/chains.py: `CHAINS["window"]` carries `continue_on_sync_failure: True`, with the ruling quoted. No other chain does.
- docs/specs/hosting-h1.md: the `sp_run.py` row says so. The comments in chains.py and sp_window_page.py say when the page posts.
- tests/test_hosting_pack.py (4 new), on a fake step list:
  - two failed sync steps: the rest and the card run, the page posts, the exit is non-zero;
  - a failed card step: the chain ends and no page is posted;
  - only the window chain runs on;
  - the chain's last output lines name the failed sync step, its command and its last (redacted) line.
- #551's test fix is ported (tests/ledger_text.py): main at c546168 is red without it.

## 2026-10-16 (#558: releases-v1-4-0 — ARCHITECT addendum 88 items 1 and 3; Closes #557)
- docs/RELEASES.md, ritual step 3: the tag step now reads `git tag -a vX.Y.Z <sha> --cleanup=verbatim -F logs/release_notes_vX.Y.Z.txt`, from v1.5.0 on. git's default cleanup strips every line beginning with `#`.
- docs/RELEASES.md, ritual step 2: the notes are written to that file (`release_notes.py --to <sha> > logs/release_notes_vX.Y.Z.txt`), so step 3's `-F` reads the notes just generated (Codex on #558). Never tag from a file holding the script's `✗` line.
- docs/RELEASES.md, a new "Release record" section, one line per tag. Its first line is v1.4.0:
  - cut 2026-10-16 14:18:21Z, commit `684462e3d5078ff2c906db73362a220917bf1fcb`, tag object `253bacd00327446936cdb16ea37a76deafc20ff1`, release Issue #556;
  - the record of its tag message's dropped lines: the notes' header and all 105 `## ` section headings, 106 lines (#557).
- No code change. The tag does not move.

## 2026-10-16 (#553: ncaa-elo-v2 declared — ARCHITECT addendum 81 item 2, #79; nothing run)
- docs/registry/experiments.json: `ncaa-elo-v2` declared through `registry.declare`: status declared, run and verdict null.
  - D5 is the gate and D7 the confirmation window, both verbatim. The plan is v1r's numbers: 100, log_loss, 0.6931, beat the D4 baseline − 0.010.
  - v1's constants and the neutral rule.
  - `logistic_scale`: s = 279.14222651259433, frozen exactly as the fit printed it (ARCHITECT addendum 93), with `fit` = the training fingerprint a5568a48…f3ab47, regular games 2024 752 / 2025 762, log-likelihood −870.104578, b_2025 0.991330, the operator's block at head 4790737. The run refuses while s is null.
  - D9, D10 and D11 verbatim (`prior_reads_note`, `second_read`, `benchmark`).
  - Test set: "NCAA FBS 2026 regular season as it accrues (CFBD both-FBS labels; training and warm-up 2024 and 2025)".
- docs/specs/ncaa-elo-v2.md: item 1 and D1-D11 verbatim, the registry entry, the declared procedure of the fit of s, the parameterised gate, the second read, ten interpretations and the two questions, both RULED by addendum 86 item 3 (Q1: price only, update at 400; Q2: a 2026 fence, its own PR after this one merges).
- src/models/ncaa_elo.py: `NCAAEloV2`, which is NCAAEloV1 with the logistic scale s in the stated probability only. PRICE ONLY (addendum 86 item 3, Q1): it overrides `predict`, and the update keeps v1's expected score at /400, so its ratings are v1's at every s. At s = 400 it is v1 exactly.
- src/walters/ncaa_backtest.py:
  - `NeutralRuleElo(scale=)`: None keeps v1.
  - `Game.week`: CFBD's week once the 2023 ingest stores it; None until then.
  - `v1r_stream(seasons=)` and `load_v1r_streams`: one read, several streams.
- src/walters/ncaa_v1r_gate.py: the gate's machinery, parameterised by registry id (`Spec`, `Read`, `SPECS`, `spec_of`), as D6 orders.
  - **v1r is unchanged:** its tests pass unchanged, and a before/after capture of its pure outputs is byte-identical.
  - **v2:**
    - D4 is read over 2024 and 2025, and the 2026 'regular' games are scored.
    - The frozen s; the run refuses while it is not frozen.
    - The run needs 2024, 2025 and 2026 covered.
    - One fingerprint covers the 2024-2026 stream and the 2023 second-read stream, the week included.
    - The D10 second read: a cold start, scored from week 5, with its own weeks 1-4 baseline. It is NOT READ without 2023 coverage and INVALID under 500 or without its baseline, and it never refuses the run.
    - The combined verdict. The record's ids sidecar holds both reads' ids.
- src/walters/ncaa_scale_fit.py (new): D1's fit. Maximum likelihood over the 2024 and 2025 'regular' games, walking only those seasons.
  - The search: a grid of 100..1000 by 5, then golden-section to 1e-6. The bracket edge is flagged; a tie goes toward 400.
  - It prints the curve at 300..500 by 25, the fitted s exactly, b on 2025, the training fingerprint, and two checks against v1r's recorded run.
- cli.py: `ncaa-gate --id`, `ncaa-confirm --id` and `ncaa-fit-scale --id ncaa-elo-v2`. `ncaa-v1r-gate` and `ncaa-v1r-confirm` are unchanged.
- docs/roadmap.json, lane ncaa: step 1 done (addendum 81), state declared, registry_id ncaa-elo-v2.
- docs/CLI.md: the three commands.
- tests/test_ncaa_elo_v2.py: 40 tests, strengthened after an adversarial review before opening.
- #551's test fix is ported (tests/ledger_text.py): the spec and ledger verbatim test reads the entry through it.

## 2026-10-16 (#552: desk-clock-hold — ARCHITECT addendum 83 item 2, #529)
- src/walters/desk_policy.py: the Desk's kickoff-clock hold (#530) has its own threshold, `DESK_CLOCK_DRIFT = 1h`, and it is inclusive. A stored kickoff and a leg's ticker clock at or more than 60 minutes apart hold the row: PASS, units 0, no order, no value shadow, pass kind `kickoff_clock`.
  - The matcher's `kalshi_match.MAX_TICK_DRIFT` stays 2h for placement; the Desk no longer reads it.
  - The desk block's `kickoff_clock.max_drift_h` now reads 1.0.
  - desk_meta gains `kickoff_clock_hold_h`, the threshold in force.
  - Everything else in #530's rule is unchanged: the switch, the reason text, the order (after S1, before started), the closing file and the Cockpit tag.
  - tools/cockpit.html (repo copy): the comment beside the tag names the Desk's threshold. The Cockpit compares no clocks itself.
- Not changed here: the closing watch still fires at the stored kickoff time. The run time is a separate question for the replay spec (Tuesday 2026-10-20).
- tests/test_desk_kickoff_clock.py (26 tests). The ruling's three rows:
  - 50548 TB at CLE tonight (stored 20:00 ET vs the ticker's 18:00 ET: exactly the matcher's 2h, which #530 let through) is held;
  - 50546 (13:00 vs 18:00 ET) is held;
  - 50547 (20:00 vs 20:00 ET) is untouched.
  - The threshold: 60 minutes holds and 59 does not, either way round. Patching the matcher's constant moves nothing; patching the Desk's moves the hold.

## 2026-10-15 (#548: cutover-preflight — ARCHITECT addendum 79 item 4 and addendum 80 item 3, #495, #520)
- deploy/hosting/sp_cutover.py, the preflight:
  - **A listed timer that is not active refuses**, named on the refused line and on the receipt (`timers_listed_inactive`; [] on a pass). Addendum 79 item 4 supersedes #495's "It refuses nothing for it" (addendum 80 item 3, Q2).
  - **The preflight runs before runbook step 2 (addendum 80 item 3, Q1).** Past the pack, the data/ guard and the two timer reads, it stops when EVERY listed timer is inactive and no sp timer off the list is active (a run after step 2, which is not the preflight).
    - It prints `timers already stopped: run the preflight before step 2` and its receipt: exit 1 and `stopped`, never `refused`, and no ✗, REFUSED or FAIL line.
    - It runs no further check (no shot read, no verify), and `run` goes no further.
    - An sp timer active off the list is never hidden by the stop: addendum 57 item 8's refusal names it.
  - **The NHL shot GATE reads the PACK's DB, and refuses on it (addendum 80 item 3, Q3):** `<pack>/sports.db`, the laptop's DB that `install` puts in place. The host's live DB is read the same way and printed for the record; it never refuses.
    - Both are read by `sp_cutover.py shot-gate`, an internal command and never a step: `--pack <dir>` for the pack, nothing for the live DB.
    - It runs in a process of its own, as the service user under root (as install is). The app's sessions read through a connection of their own, sp_common's own read-only open. For the pack that is `copy_connect` (mode=ro and immutable, as sp_migrate opens the pack's copy); for the live DB it is `ro_connect` (mode=ro, never immutable, #340). No WAL pragma, no mkdir, nothing written. A missing DB is refused and never created; `init_db` is never called.
    - The counts are `nhl_shots.coverage()["gate_stream"]`, nhl-shot-coverage's own numbers. Each season also carries its first and last stream date.
    - Each season prints `the pack's NHL shot GATE stream <season>: w/n = x% [PASS|BELOW >= 95%]` with nhl-shot-coverage's own rule (the unrounded share). The host's lines read `for the record, never refuses: the host's live NHL shot GATE stream …`. No host line carries a fault mark, whether read, unread or empty.
    - A pack season below 95% refuses, named with its share. A pack read that fails or names no season refuses: never read as a pass.
  - **Below 95% on the host, the backfill's exact host command is printed and never run, labelled "optional before cutover; not a prerequisite":**
    - first, `cd <checkout>` and `nhl-shot-sync --start <the day before the first stream game> --end <the last> --dry-run`;
    - a STOP line;
    - then the write: the `.backup` (`sp_backup.py daily`, nhl-shot-sync's own docstring), the same sync without `--dry-run`, and `nhl-shot-coverage`.
  - **Each check prints its own line** (`·` passed, `✗` failed); the flag and writable lines say exactly what was read. Past the pack, the data/ guard and the two timer reads, the preflight refuses once, naming every failed check (joined with ` | `). `sp_migrate verify` runs only when they all pass. A single failure's text is unchanged.
  - Every receipt from the reads on carries `shot_gate_pack` and `shot_gate_host`: a pass, any refusal, verify FAIL, or "not read (dry run)".
  - The dry run reads neither (the scratch world holds no NHL games) and says so.
- docs/specs/h2-cutover-runbook.md: the preflight row names the new refusals, the record read and the stop after step 2.
- tests/test_h2_cutover.py:
  - The listed-but-inactive test now refuses and names the timer; a second test shows other units refuse nothing.
  - New tests (addendum 79 item 4): the laptop's numbers, the 95% boundary (1326 and 1327 of 1396), an unread gate, one refusal naming three failures, the dry run, the read's argv and parsing, `shot-gate` end to end on a throwaway NHL DB in a subprocess, the DB's bytes unchanged by the read, and the flag and writable lines.
  - Addendum 80 item 3:
    - the pack below 95% refuses;
    - #520's host numbers (0/1396, 0/1394) never refuse and print the optional backfill;
    - an unread host record never refuses;
    - every listed timer stopped prints the one line, with no fault mark and nothing else run;
    - one listed timer stopped is still the 79.4 refusal;
    - an off-list sp timer active is never hidden by the stop;
    - a refusal on another check keeps both reads;
    - the live read is mode=ro and never immutable: a row in the WAL is read (#340);
    - `shot-gate --pack` reads the pack's copy (a WAL-header copy too) and leaves it byte for byte, with nothing beside it;
    - a pack without a DB refuses on its own path, never reading the live DB, and creates nothing.

## 2026-10-15 (#538: sync-lineups-history, DRAFT — ARCHITECT addendum 74 item 1; addendum 71's Step B; #106)
- `python cli.py sync-lineups-history --competition CL|UEL|EFL|FAC --season YYYY [--since YYYY-MM-DD] [--dry-run] [--max-calls N] [--save DIR]` (src/ingestion/lineups_history.py).
  - For the FINISHED fixtures of one cup-season it stores each side's starting eleven and bench from `/fixtures/lineups`, read through the adapter's own `list_lineup_confirmed`, pace and parser.
  - Rows go in the existing `lineups` table with `kind` `history`. No column is added. Never `confirmed`: the live lineup factor reads every team's last confirmed starters across competitions.
  - Sides are mapped by provider id (merged ids included), never by name. Rows carry the ingest time only.
- Idempotent: a fixture holding both elevens is skipped with no call. Any other is asked, and each answered side's history rows are replaced. Other kinds are never touched. One session per fixture.
- A later nameless answer for a side never replaces an eleven stored from an earlier named answer (ARCHITECT 2026-10-16, addendum 98 item 1). The receipt counts such sides ("answered nameless, earlier eleven kept: N") and lists their fixture ids. Completeness still reads from the stored rows. A side with no stored rows that answers nameless stays unstored.
- The coverage receipt per competition-season: fixtures with both elevens / fixtures, then one / none (by why) / failed / not asked / no fixture id, rows, and calls with HTTP requests by status.
- `--max-calls` (default 100) stops cleanly between fixtures. A payload error or a 401/403/429 stops the run; other failures are listed and asked again next run.
- `--dry-run` reads mode=ro, prints the plan before any call, and writes nothing. `--save` keeps each answer whole, a quota or plan refusal included (its 200 body is kept before the adapter raises on it, Codex on #538), never under data/ (checked by resolved path and file identity, as `--out` is guarded on #433).
- `--since YYYY-MM-DD` (ARCHITECT 2026-10-16, addendum 83 item 5(b)) keeps only the fixtures on or after the date: the stored kickoff's UTC date, and a fixture with no kickoff is left out. Each left-out fixture is never asked and stays out of the coverage line. The receipt counts them and lists every one: match id, fixture id, date, teams. FAC 2025/26 is pulled `--since 2025-11-01`, the First Round Proper, because its preliminary rounds carry no lineup.
- The run list (addendum 83 item 5(a)): CL 2026/27, EFL 2026/27, CL 2025/26, UEL 2025/26, EFL 2025/26, FAC 2025/26.
- src/db/schema.py: the Lineup docstring names the `history` kind (comment only, no DDL). docs/CLI.md: the command's row.
- tests/test_lineups_history.py (25 new; 4 for `--since`, 1 for addendum 98) on a throwaway DB with the adapter's real parser.
  - Three run on the kept answers (tests/fixtures/lineups_history/, its README; addendum 83 item 5(c)): seven real /fixtures/lineups answers of 2026-10-16 13:19Z, byte for byte from laptop/lineups-payloads-1016 (df877e3). Six have lineups (CL 2025/26 x3, EFL 2026/27 x3); one is the empty FAC answer, kept deliberately. The other two FAC answers are dropped as duplicates.
  - The kept answers' keys; both elevens and every bench stored (246 rows), three null formations stored as null, six null positions; the empty answer counted as "none · an empty answer" with nothing written.
  - The synthetic payload stays only for the shapes no kept answer holds: nameless slots, short sides, an unmapped side, refusals and the cap.

## 2026-10-16 (#551: ledger-tests-after-compile — main's CI red on c546168, the v1.4.0 commit of ARCHITECT addendum 84)
- c546168 (the ledger compile) folded every fragment into CHANGELOG.md and BACKLOG.md and deleted the files.
  - Three tests read `docs/ledger/entries/2026-10-08-ncaa-v1r-declaration.md` directly, so CI's smoke job on c546168 failed: `test_ncaa_v1r_declaration::test_spec_and_ledger_quote_d1_to_d9_and_the_d5_note_verbatim` and two in `test_ncaa_v1r_fence`.
  - The tag ritual refuses unless CI on the commit is green.
- tests/ledger_text.py (new): `entry_text(name, heading)` reads an entry from its fragment while the file exists. After the compile it reads the entry's block in BACKLOG.md, found by its heading line (exactly once), up to the next entry or section heading.
  - The folded block is the fragment verbatim: checked on c546168 against the file as it stood at 87ea592.
- The three tests read the entry through it. What they assert is unchanged.
- tests/test_ledger_text.py: the fragment is read first; then the folded block, bounded by the next heading; a missing or doubled heading fails loudly.
  - A guard: no test reads `docs/ledger/entries` or `changelog.d` directly any more. The fragments' own checker is exempt.

## 2026-10-15 (#547: replay-inventory — ARCHITECT addendum 79 item 3, #75)
- scripts/replay_inventory_probe.py (new, read-only): what the DB can replay, per sport, for the graded games since 2026-09-20 (FINISHED with both scores; kickoff in [--since, --until)). Soccer is split by competition code; NCAA is sport NFL with code NCAA.
  - Per sport it prints:
    - **Stored predictions before kickoff:** the current row, the prediction_history rows, either, and current rows computed at or after kickoff. Versions per game are history rows before kickoff (min/median/max). It also counts the games with a prediction_outcomes row.
    - **Book history before kickoff:** games, those with a complete session, first and last capture age vs kickoff, and the earliest capture.
      - Read from odds_snapshots and the odds table: market 1X2, source not kalshi; NULL counts as book; the football-data-uk closes are left out.
      - Each table's share is printed, with its own sessions per game and complete games. Sessions are never added across the two tables, because one sync writes both. Before #167 (2026-10-01) the soccer, cup and NHL syncs appended every run to the odds table, so for those games it is the only book history.
    - **Kalshi snapshots before kickoff** (source kalshi), the same figures. A game whose legs are mismatched (addendum 37 item 3, `kalshi_legs.mismatched`) is never counted, and is printed apart.
    - **kalshi_settled_markets** rows.
    - **Closing files** in the laptop's exports/, by match id. Host copies under exports/host/ are counted, never matched, because their match ids are the host's own.
    - **All four.**
  - Sessions and completeness are read the way close.py reads each table. The outcomes are HOME and AWAY; soccer adds DRAW.
    - **odds_snapshots** (`close_from_snapshots`): a session is one captured_at; it is complete when it carries every outcome.
    - **The odds table** (`close_1x2`, the #207 contract): a session is a captured_at t and the rows in the 10 minutes before it, the latest per (bookmaker, selection, line). It is complete when ONE bookmaker quoted every outcome above 1.0. Books are never pooled (Codex on #547). A random-input check against `close_1x2` itself matched 4,000 of 4,000.
    - **Kalshi:** a session is one captured_at, complete when every leg is stored. That is a count of stored legs, not the Kalshi grading close.
  - The printed keys line names every key, the sport grouping included.
  - The header gives the schema's answer on versions:
    - `predictions` is current-only: every writer deletes the match's rows and inserts one.
    - `prediction_history` is append-only since #301 (2026-10-06, no backfill). The probe prints this DB's first history stamp.
    - No sport's count is assumed. The production INTL export appends UNL history with no predictions row (Codex on #547).
  - A missing table or column (older DB) is said, never assumed. The DB opens mode=ro; the fallback is the plain path with `query_only`, as #421 ruled ("no third way"). None is ever created.
- tests/test_replay_inventory_probe.py: 17 tests on throwaway SQLite files. They cover pre-#167 odds-table history, mismatched legs, an incomplete session, the query-only fallback, pooled books, the 10-minute window and UNL history.

## 2026-10-15 (#545: value-shadow-receipt — ARCHITECT addendum 79 item 2, #86; finding #544)
- scripts/value_shadow_receipt.py (new, read-only): every value shadow in a Cockpit ledger export (`bd_ledger_v1_<date>.json`, from "Export ledger (JSON)"), units only, no dollar figure.
  - **Per row:** the kickoff, sport, game, side, the edge at the call, the close, the result (won / lost / push / void / ungraded) and units (0.25u notional; net over the settled rows).
    - The edge at the call is the claim's: claim_model_p minus claim_market_p. Without a claim it is value_edge_pp, labelled "last log".
    - The close is `close_ref.q_close`. The game's score is not in the ledger: the call's graded result is.
  - **Totals** over all value shadows and over the rows with a close only: graded n, the record, units net.
  - **n/30** prints both Cockpit readings: the policy card's (every value shadow with a result) and the P&L block's (its settled rows, after the kickoff audit).
  - **Settlement follows the Cockpit's `settledBets`:**
    - The kickoff audit (`auditCall`, #178) is recomputed from the stored stamps, never read from the stored `tz_audit` mark: a ledger last saved before the mark existed carries none (Codex on #545). The port matches the Cockpit's own JS on 400 of 400 randomized cases.
    - A row the audit excludes is out of the net, and its settled record is printed apart.
    - A flagged row is re-settled at the audited price, rounded as the Cockpit's toFixed(4) rounds.
  - **Staked:** a truthy `staked` field, or the text "value shadow, staked" in any string of a call. A call of another type marked so is listed apart, with its own units, and kept out of the totals. Neither the repo Cockpit nor the live artifact has such a field today.
  - **A Kalshi fill on a shadow's side:** the Cockpit's own fill matcher (`src/walters/ledger_fills.py`) books it off-book as "matches a quarantine SHADOW". The receipt re-fits it to the value shadow and counts it on the row. Its prices and size are never printed.
  - A ledger with no value shadow prints "→ n=0 of 30". A file that is not a ledger export is refused.
  - The docstring carries the law-1 read of where `value_shadow_graded` comes from and why the closing runs read none (#544).
- scripts/value_shadow_fixture_capture.py (new): writes the test fixture through the Cockpit's own code. It drives tools/cockpit.html headless: logs, grades, and saves the "Export ledger (JSON)" text.
- tests/fixtures/value_shadow/bd_ledger_v1_cockpit.json: the kept ledger shape, 6 calls (5 value shadows: won, lost, push, ungraded, a soccer DRAW won; 3 with a close). Every kickoff is fixed at 2091-10-16 18:00 UTC, so a re-capture reproduces it (Codex on #545).
- tests/test_value_shadow_receipt.py: 22 tests.

## 2026-10-15 (#543: guard-desk-pick — ARCHITECT addendum 79 item 1, #537)
- scripts/soccer_injury_factor_receipt.py: a changed call is now graded on the Desk's own pick, not on the receipt's unrounded pick.
  - The Desk's pick is the one `desk_policy.normalize` takes from the export's 4-decimal probabilities: it walks HOME, DRAW, AWAY and moves only on a strictly greater value, so a tie goes to the first side.
  - `guard_calls` keeps the pick of the row the Desk's own run evaluated (`desk_pick`; None when the case is not evaluated). `guard_summary`'s `changed_graded` grades on it.
  - The instrument rules (`instrument()`) are kept; only the side passed to them changed. The edge and cohort lines keep the unrounded pick. The `--list` row names the Desk's pick where the two differ.
  - Two leading sides within 0.0001 of each other can round to the same value. On main, AWAY 0.50001 / DRAW 0.49997 on a draw graded "PLAY AWAY lost"; now it grades "PLAY DRAW won", the Desk's DRAW.
- tests/test_soccer_injuries_one_sided.py: 1 new test, that tie case run through `guard_calls`, `guard_summary` and the `--list` report. The summary unit test's row carries `desk_pick`.

## 2026-10-15 (#541: lineup-kind-guard, GATE-CLASS — ARCHITECT addendum 75 item 2, Q9)
- src/walters/training.py: the two whole-table lineup readers of the soccer pricing take `kind in ('projected', 'confirmed')` (`LIVE_LINEUP_KINDS`, sync-lineups' own kinds): `lineup_kind_by_match_team` and `starters_by_match_team`. A finished cup fixture's `history` rows (sync-lineups-history, #538) never reach a prediction, the report-only cup exam or the fix-v2 tuning. The recent-XI reader already reads `confirmed` only.
- src/web/routes/matches.py: the match page's lineup reads the same two kinds.
- On today's DB nothing changes: no `history` row exists until #538's first pull. The frozen receipt is the architect's block on the laptop (the PR body).
- Tests, each pinning one filter: it fails with that filter alone removed.
  - tests/test_cup_exam.py, the starters reader: the exam's rows are identical with and without a history eleven that, unguarded, reads as 11 missing regulars.
  - tests/test_cup_exam.py, the kind reader: a history eleven on a scheduled match leaves the stored lineup_kind None; unguarded it reads 'history'.
  - tests/test_lineup_kind_guard.py (2), the match page.

## 2026-10-15 (#540: probe-competition — ARCHITECT addendum 75 item 3(a))
- scripts/lineup_timing_probe.py takes `--competition CL|UEL|EL|EFL` (default CL): the stored competition code whose rows on the day are polled. The polls, the late rule and the summary are the same for each, and the header and the D0 lines name the code read.
- The Europa League is stored under UEL or EL (the adapter maps both; addendum 76 item 2). A day with no row under the code asked says how many rows the other code holds that day, so the operator re-runs with the right one. Nothing is read as the other code.
- tests/test_lineup_timing_probe.py: 6 new. A UEL row on the day is polled only under `--competition UEL` and CL stays the default; EL reads its own rows; the 0-rows line names the other Europa League code both ways (UEL→EL, EL→UEL) and says 0 when neither holds a row; a code outside the four is refused by the parser.

## 2026-10-15 (#539: cups-probe-steps — ARCHITECT addendum 75 item 3)
- docs/roadmap.json, the cups lane: two operator steps between Step A (CL, 10-20) and Step B (10-29). Step A, UEL is the timing probe on the UEL matchday, due 2026-10-22. Step A, EFL is the probe on the next EFL round with stored rows, its date named by the operator (2026-10-27 until named). Step A's probe step is done (#528 merged).
- CLAUDE.md, the cups paragraph: "CUP MODEL TRACK: reopened 2026-10-15 on a dated plan …; EFL/CL/UEL stay MARKET-ONLY until a PASS and its confirmation. The exam harness + fix-v2 machinery stay merged." This replaces "SUSPENDED … for the season". Nothing else in that paragraph changes.

## 2026-10-15 (#536: injury-guard-isolated — ARCHITECT addendum 74 item 3, #425)
- scripts/soccer_injury_factor_receipt.py: the one-sided-list guard, isolated. Measurement only: no rule, threshold or switch default changes.
  - Each case is given to the Desk as the predictions export built at the prediction's computed_at read it, and evaluated as of that moment: the stored 1X2 to 4 decimals; the book reference the export read then; the stored list counts and rating sources.
  - Since #167 `sync_odds` replaces a source's odds rows on every sync and appends the same `close_1x2` consensus to `odds_snapshots`. So the reference is the latest session by computed_at in either table: the later stamp wins, and the odds table wins a tie. An odds-table session read unpriced is no reference.
  - Where neither table has a session by then but the odds table holds a later one, the session read then may have been replaced. That case is counted as reference unknown and not evaluated (law 4).
  - A snapshot is the last priced session by then. An unpriced session that a later sync replaced leaves no trace, so there the receipt reads the priced snapshot before it where the export had none. The changed cases are split by where their reference was read (odds table / snapshot / none).
  - That reference is not the grading close. The edge and cohort lines keep the grading close; the Desk reads what it had.
  - `desk_policy.evaluate` runs with every switch as it stands, then again with the guard's own switch off (`injuries_one_sided_rule_off`).
  - Per case, both calls. The receipt counts the one-sided cases, the ones the guard held and what they read without it, the ones an earlier rule reached first (shadow league, kickoff clock, started, default rating) by kind, and the cases where only the guard changed the call (PLAY / LADDER / PASS).
  - A changed call is graded by its own instrument: a PLAY on its side; a LADDER on AWAY as X2 (a draw wins); a LADDER on a draw pick is not graded.
  - The counts are over the rows the receipt stands behind (#437), with the all-rows reference line marked. They say where each Desk reference was read from (odds table / snapshot / none). Cases not evaluated are counted by reason (no computed_at, reference unknown). `--list` shows both calls per row and the reference the Desk read.
  - No Kalshi quote is given. On a three-way soccer row the Desk takes no Kalshi-only reference, so a quote changes a call's units, never the call; the EPL tickers carry no clock.
- The log-loss lines are unchanged: they measure the injury factor (the cut kept against taken out), not the guard.
- tests/test_soccer_injuries_one_sided.py (3 new), on the receipt's own DB shape. The fixture has ten cases, stored the way `sync_odds` leaves them: held then LADDER read from a snapshot of a replaced session (changed, graded X2 on a draw); held then PLAY (changed); held then PASS noref (not changed); a non-guard PASS; a left-out row; default-rating and started cases reached before the guard; a replaced history read as unknown; and no odds at all read as no reference. A unit test covers the as-of reference rules, and another the summary (not-evaluated reasons, instrument grading, the export's 4-decimal probabilities).

## 2026-10-15 (#535: pitcher-neither-receipt — ARCHITECT addendum 74 item 2, #507)
- scripts/mlb_pitcher_probe.py (read-only): per season, the finished games with neither starter recorded.
  - Their date range and count by month (stored kickoff, UTC).
  - Their provenance: `matches.external_ids` keys, printed as read (mlb_stats_api = statsapi's sync-matches; api_baseball = the api-sports fallback).
  - The split as `cli.py sync-appearances` reads a game: no pitcher_appearances row for its statsapi id / rows but no starter / no statsapi id.
  - One sentence from the code: a re-run of `sync-appearances --season YYYY` writes rows for the first group where statsapi's boxscore answers, at most `--limit` games a run (default 2000, in no set order). It writes a starter only where the boxscore's per-game `gamesStarted` is 1. The second group is skipped unless `--refresh`.
  - `--refresh` makes every finished game with a statsapi id a target and deletes their rows, committed before any request. A game whose request fails or returns nothing is left with no rows, so the sentence says to take a .backup first. The third group is skipped either way, so for it a command is missing.
- tests/test_mlb_pitcher_probe.py: 1 new, on the throwaway DB (2025: four games with no row and one with a reliever row only; 2024: one game with no statsapi id).

## 2026-10-15 (#534: copy-verify-immutable — ARCHITECT addendum 73 item 4, #532)
- deploy/hosting/sp_common.py: `copy_connect(p)`, the immutable open of a copy nobody writes (`?mode=ro&immutable=1`).
  - `copy_integrity` opens through it, unchanged in behaviour.
  - `table_counts(..., copy=True)` reads a copy through it.
  - `ro_connect` stays mode=ro, so the live DB is never opened immutable (#340).
- deploy/hosting/closing.py `take_backup`: the `.partial` is checked with `copy_integrity`, and the finished copy is opened with `copy_connect`. Both were mode=ro.
- deploy/hosting/sp_migrate.py:
  - `pack` checks and counts the pack's copy through the immutable open.
  - `verify` does the same on the pack's own copy. With `install`'s override, the installed DB (the live one from then on) stays mode=ro.
- tests/test_hosting_pack.py (2 new), on a WAL source in a throwaway folder; both fail on main:
  - the closing backup leaves the `.db` and its `.sha256` and nothing beside them, and every read of the copies is immutable;
  - the pack folder holds no `-shm` / `-wal`, verify reads the pack immutable, and install reads the installed DB mode=ro.

## 2026-10-15 (#531: backup-partial-sidecars — ARCHITECT addendum 72 item 4, #517)
- deploy/hosting/sp_backup.py: the host's verify opens the `.partial` copy `?mode=ro&immutable=1`, through `sp_common.copy_integrity`, as pull_backup's has since #526.
  - Its own mode=ro open (`c.integrity` → `ro_connect`) made a 32768-byte `.partial-shm` and an empty `.partial-wal` beside a WAL copy on Linux. Nothing removed them; that is the host's 64 sidecars of 10-11..10-15.
  - A failed run removes every `*.partial*` in the folder. It used to remove the `.partial` only.
- deploy/hosting/pull_backup.py: a failed pull's cleanup glob takes `*.partial*` (it took `*.partial`).
- sp_prune is unchanged: it plans `sports_*.db` names only, and leaves `.partial*` files to the cleanup (a test pins it).
- tests/test_hosting_pack.py (4 new), each on a throwaway folder:
  - a WAL source's daily backup verifies through the immutable open and leaves the `.db` and its `.sha256` only;
  - a failed backup removes every `*.partial*` and nothing else;
  - a failed pull removes every `*.partial*`;
  - prune never plans a `.partial*`.
  - The first three fail on main.
- The 64 existing files on the host: removed in the operator's next host block, after this PR is on a tag (the host runs tags), never by hand before.

## 2026-10-15 (#530: kickoff-clock-hold — ARCHITECT addendum 72 item 1, #529)
- src/walters/desk_policy.py: a row whose stored kickoff and the Kalshi clock in a leg's own ticker disagree by more than `kalshi_match.MAX_TICK_DRIFT` (2h, the matcher's own threshold, read there) gets no Desk call. The rule's own switch is on.
  - The row is PASS: units 0, no order, no exec block, no value shadow, never a parlay leg.
  - Its pass kind is `kickoff_clock`, now in NO_CALL_KINDS. The reason names both clocks: "stored kickoff 2026-10-15 13:00 ET vs Kalshi's clock 18:00 ET: no call".
  - The clock is read with `kalshi_match.ticker_stamp`. A ticker shape without a clock is not compared, and a row with no ticker is unchanged.
  - The rule is checked after S1 and before the started rule.
  - The desk block carries `kickoff_clock`: both clocks in UTC and ET, the drift and the threshold. desk_meta carries `kickoff_clock_rule`.
  - The frozen battery runs with the rule off (`base_v11()`); `kickoff_clock_rule_off()` compares a file with and without it.
  - POLICY_VERSION stays v1.1, the file's convention since F1: no rule since has bumped it.
- The closing file holds each row as the export gave it (closing.closing_doc, addendum 40 item 2), so it carries the kind, the reason and both clocks. closing.py is unchanged.
- tools/cockpit.html (repo copy): the kind's tag reads "kickoff disputed" and its row is greyed, as for the other no-call kinds. The reason is rendered from the file.
- The file_unit_basis docstring's dollar example reads "$N" (addendum 68 item 6).
- tests/test_desk_kickoff_clock.py (23 tests), on the day's rows:
  - 50546 TB at CLE (13:00 vs 18:00 ET) is held;
  - 50547 MIL at LAD (20:00 vs 20:00 ET) is untouched;
  - the threshold is the matcher's (patched there, the rule follows);
  - the threshold itself does not hold, and two hours and one minute does, either way round;
  - a ticker shape without a clock, and a row with no ticker, are not compared;
  - any one leg past the threshold holds the row;
  - a value-bearing row loses its shadow;
  - the rule comes after S1 and before started;
  - the closing file carries the kind and both clocks, and the Cockpit carries the tag.

## 2026-10-15 (#528: lineup-timing-probe — ARCHITECT addendum 71 item 2, Step A, #106)
- scripts/lineup_timing_probe.py, read-only, writes nothing. For the day's CL fixtures with a stored row, it polls `APIFootballAdapter.list_lineup_confirmed` (the call sync-lineups uses, with the adapter's pace and parse) at T-120, T-90, T-75, T-60, T-45, T-30 and T-15.
  - Each poll prints the starters and the bench per side. Its minute is the minute the counted answer was asked for: after the adapter's pace and after its one retry of a 429.
  - A poll more than 5 minutes past its time (a late start, a laptop that slept) is printed as missed and never counted under its label.
  - Per fixture: the first poll with eleven starters per side, and the poll before it answered without them. Polls between those two that failed or were missed are named, because the lineup may have been readable at one of them. Also the keys the answer carries, and the polls answered, failed and missed.
  - The fixtures are then counted by that first poll. A fixture whose earlier polls were not all answered is counted apart.
  - Printed once: the keys the adapter reads, and the calls (calls, HTTP requests by status, failures).
  - Not polled, with the reason printed: a row with no fixture id, a kickoff that cannot be read, or a stored status the matcher counts as not a game (kalshi_match.NOT_GAMES).
  - The database is opened mode=ro (query_only where a copy refuses it, #421).
  - `--plan` prints the fixtures and their poll times and makes no call. `--date` is the day in UTC.
- tests/test_lineup_timing_probe.py (26 tests): a throwaway DB from the app's schema, the real adapter with its HTTP session stubbed (a real request fails the test), and a fake clock.

## 2026-10-15 (#527: cups-plan — ARCHITECT addendum 71 item 3, #106)
- docs/roadmap.json, lane cups: state blocked → declared, on addendum 71's plan.
  - The probe step done {2026-10-14, logs/lineup_history_probe_2026-10-14.txt}.
  - The ruling step done {2026-10-15, addendum 71}.
  - Steps A, B and C with their owners and dates:
    - Step A's probe written (code, 2026-10-19);
    - Step A run on the CL matchday, the laptop awake 10:30am to 3:00pm ET (operator, 2026-10-20; addendum 73 item 3);
    - Step B's ingest PR with its dry-run receipt (code, 2026-10-29);
    - Step C's declaration at cup_exam's frozen gate as it stood at the 2026-09-25 FAIL (mean error <= 8.0pp, <= 13 rows over 8pp, sign >= 80%; fix-v2's 14.76pp is the record to better, not the bar; addendum 73 item 2(b)), or, if Step A shows lineups only after T-45 for most fixtures, a post-lineup closing design or a written no (architect, 2026-11-05).
  - earliest_live 2027-02-16, the knockout play-offs' first leg (addendum 73 item 2(c) corrects addendum 71's 2027-01-20, league-phase Matchday 7). live_needs reads the same gate.
  - No moved line: a first earliest_live is not a move (addendum 61 item 4; ruled to govern by addendum 73 item 2(a)).
  - `python cli.py roadmap` prints overdue 0.
- tests/test_roadmap.py: the four tests that took the cups lane's old state from the real file now set it themselves.
  - Two of them now clear the done steps first.
  - The step-not-done rule is still tested on a blocked lane.
  - The base-line rewrite test now moves the lane's last step and reads the line it appends, wherever it lands.
  - The overdue-count and plural-tail tests clear the ncaa lane's done steps too, so the college declaration's done step (owed 2026-10-16) does not break them.

## 2026-10-14 (#526: backup-pull-verify-wal — ARCHITECT addendum 68 item 2, #517)
- deploy/hosting/pull_backup.py: the verify opens the pulled COPY with `?mode=ro&immutable=1`, through the new `sp_common.copy_integrity`.
  - The laptop's (macOS) SQLite cannot open a WAL-mode copy with no -shm beside it as mode=ro ("unable to open database file").
  - Immutable reads the copy as it is and creates nothing beside it.
  - The live DB is never opened immutable: `ro_connect` stays mode=ro (#340).
- Tests: tests/test_hosting_pack.py (1 new):
  - a WAL `.backup` copy with no sidecars verifies with integrity ok through the immutable path, and the folder is left as found (the final file and its .sha256);
  - `ro_connect` holds no immutable open.
  - On the old mode=ro verify it fails (Linux would leave the -shm and -wal).

## 2026-10-14 (#523: cockpit-fill-units — ARCHITECT addendum 67 item 3, #487)
- tools/cockpit.html (repo copy; the live Cockpit is republished on the operator's word after the architect's read): the B-track fills exposure reads units on the loaded files' own unit basis.
  - `fillUnitBasis` reads the order lines as `desk_policy.file_unit_basis` reads a file's, across every accepted loaded file: the prediction and fixtures rows, and a desk_parlays file's ticket legs (Codex on #523).
  - "1u = $N": a team-outcome's units are the entry cost of the contracts paying on it (qty × entry, fees left out) ÷ N.
  - "1u = N contracts": contracts ÷ N, with N from the file.
  - No unit basis in the loaded files: contracts only, labelled "contracts (no unit basis in file)", with no cap comparison. Loaded files that disagree on the basis are treated the same way, naming both.
- `FILL_UNIT_CONTRACTS=10` goes. The page holds no dollar figure of its own. A note in the file's header comment names the rule.
- scripts/cockpit_exposure_verify.py (Codex on #523) passes the basis a file with "1u = 10 contracts" declares, read by the page's own reader. It checks the table with no file loaded (contracts, labelled, no unit), with a file of 1u = 10 contracts (1.50u > 1.25u) and with a file of 1u = $5 (1.80u > 1.25u): 18/18 green. scripts/cockpit_maker_taker_verify.py: 26/26.
- Tests: tests/test_cockpit_fill_units.py (7; the page's functions under node):
  - the constant gone and no dollar figure held;
  - a dollar unit: $23.00 of entry over $20 is 1.15u, under the cap, and over $15 is 1.53u, over it;
  - a contracts unit, read from the file;
  - no basis: contracts and the label, never a unit;
  - two files that disagree.
  - a parlays file's ticket legs give the basis alone, and conflict with rows that disagree;
  - the page reads the rows and the parlays file at both call sites.

## 2026-10-14 (#522: mlb-pitcher-probe — ARCHITECT addendum 67 item 2; roadmap lane mlb-pitchers, #507)
- scripts/mlb_pitcher_probe.py: MLB pitcher coverage, read-only. It writes nothing and opens the database mode=ro, falling back to the plain path with query_only (#421).
  - D0: every table whose name or columns speak of a pitcher or a starter, with its columns, and the ones it reads: pitcher_appearances, then match_participants as a second read.
  - D1: per season (2024..2026), the MLB games by stored status; the finished games with a starter recorded for both sides, one side only, or neither (is_starter = 1, by match_id or by the statsapi id in source_game_id); and match_participants' starting pitchers by kind.
  - P1: ten finished games per season, evenly spaced by kickoff, through statsapi's /schedule?gamePk&hydrate=probablePitcher (the adapter's own call and pace). Per game: whether both probables are named, and the keys read.
  - P2: the next unplayed game (status SCHEDULED, after now; a cancelled, postponed or stale-orphan row is passed over, Codex on #522): whether the probables are named now, and every key of the answer that speaks of a time. It says so when the payload does not give the hour they appeared.
  - A row whose external_ids is not a JSON object carrying the id is one game with no id, never the end of the probe. A starter with no team id names no side (both Codex on #522).
  - Summary per season: starters recorded x/y · probables available on the sample z/10.
- Tests: tests/test_mlb_pitcher_probe.py (8), on a throwaway SQLite file built from the app's schema and a stubbed statsapi:
  - both / one / neither, with a starter found by source_game_id;
  - the ten-game sample and its count;
  - the payload that does not give the hour, and one that does;
  - a failed call printed and the probe going on;
  - nothing written and no database created.
  - P2 passing over cancelled, stale-orphan and postponed rows and malformed ids;
  - a starter with a null or empty team id counted under no side.

## 2026-10-14 (#521: kalshi-settled-history — ARCHITECT addendum 67 item 1, #519)
- `kalshi-history --series S [--since] [--until] [--dry-run] [--max-calls N]` (src/ingestion/kalshi_history.py): the Kalshi settled-market history ingest.
  - It reads the cutoff, then `/historical/markets` and `/markets?status=settled`, paged by cursor.
  - Each event is placed by the shared matcher on the stored games of its days. The live sync's in-play, no-price, spread and window refusals are not read for a settled market.
  - Each market's one-minute candles are read from kickoff − 6h to its close.
  - It stores one row per market in the new table `kalshi_settled_markets`: the last two-sided quote at or before kickoff, and its counts.
  - It writes that table and nothing else.
  - Refused markets are kept with match_id null and the reason in notes, and the refusals are listed by reason.
  - Each candle shape is read by its own keys (`KEYS`), and a null price is never filled.
  - A stored ticker is skipped, so a run resumes by the table. At the cap the run stops cleanly and prints where.
  - A list that does not reach its end (the cap, a failed page, a page with no list, a cursor that comes back) stores nothing.
  - The claims rule is read across events: two markets claiming one side of one game are both refused.
  - A series whose competition is not in the DB refuses before any call.
  - A candle window that starts at or after close_time asks nothing. A candle call refused for good (a 4xx other than 408/429) is stored with no quote; other failures store nothing and are asked again.
  - An unreadable timestamp is skipped, never a crash.
  - `--dry-run` reads and writes nothing.
- migrate_kalshi_settled_markets.py: creates the table and the one-row migration marker `kalshi_settled_markets_migration`, by Core SQL. Additive and idempotent; run after the daily .backup. With no DB file at the configured path it refuses and creates nothing (law 5).
  - A run without --dry-run writes only when the table AND the marker exist (Codex P2 on #521, the convention of ncaa_cfbd's marker from #333). The table is mapped, so any init_db() creates it; its existence does not prove the backed-up migration ran.
  - `drop_db()` (`init-db --force`) drops the marker with the mapped tables, as it drops the two CFBD markers. Otherwise a forced reset would leave the marker beside a recreated empty table.
- docs/CLI.md: the `kalshi-history` row.
- `KEYS` is enumerated from the probe's five kept files of 2026-10-14 (laptop/kalshi-payloads-1014; addendum 68 item 5).
  - No key of the receipt differs from the files.
  - settled_time's key is `settlement_ts`, which the receipt did not name.
- Two-sided is ruling 9's `0 < bid <= ask < 1` (#286): the kept files send an empty side at size zero, priced 0.00 (a bid) or 1.00 (an ask), and an empty side is not a quote. This reading is for the architect's read.
- A time's fraction of 4 or 5 digits, as the kept files send it, is read whole on Python 3.10 too.
- The --dry-run receipt prints each row's settled_time, and the count of rows with none.
- Tests: tests/test_kalshi_history.py (35), on tests/fixtures/kalshi_history/: the kept files trimmed (whole objects, the kept format; the cutoff file byte for byte).
  - Every key in `KEYS` is checked against every kept market and candle, and each shape's candles are read by their own keys only.
  - The MLB clock shape, which the kept NFL files do not carry, is written in the four tests that need it.
  - Covered: each shape read by its own keys into a stored row (the kept candles: 0.45/0.46 historical, 0.61/0.62 live, settled_time from settlement_ts), and the close leaf where open / high / low differ; a zero-volume minute two-sided, its null price stored as sent, and a one-sided minute never filled; an empty side or a crossed quote not a quote; a 4- or 5-digit fraction read whole; a tie's "scalar" kept null with the result as read; unmatched markets kept with their reason and no candle call; the cap stops the run, prints where, and the next run resumes on all of an event's legs; a list cut short stores nothing, even after the other list is read whole, and names the kept cursor; --dry-run writes nothing; a run writes its one table and nothing else; --since/--until; the command; the window on the stored kickoff, not the ticker clock; an unmatched clock market's candles on the ticker clock; the claims across events; a failed page; a cursor that comes back; an unread series and a competition not in the DB refused before any call; an unreadable timestamp; a window after close_time; a candle call refused for good or not (404, 400 / 429, 503, 408); a table init_db() made, with no marker or an empty one, refusing a run while --dry-run still reads; the migration writing its marker once; a forced reset (drop_db, and `init-db --force`) dropping the marker so a run refuses again; and the migration never creating a database.

## 2026-10-14 (#518: kalshi-pin-fenerbahce — ARCHITECT addendum 66 item 4)
- src/ingestion/kalshi_match.py: a pin, "Fenerbahce" (as Kalshi writes it) is the stored club "Fenerbahçe".
  - The pin's name is written with ç as U+00E7, the NFC form the host's window card prints.
  - Its norm tokens equal the stored name's, as the other pins' do. norm_tokens folds no accent, so "Fenerbahce" alone shares no word with the stored name. That is why the laptop's wide probe refused KXUCLGAME-26OCT14AVLFEN and -26OCT20FENSLA for no fit.
  - Nothing else in the matcher changes: one each, the best fit, a tie refused, a pinned name fitting its own team and no other.
- Tests: tests/test_kalshi_matcher_day_rule.py (5 new):
  - the pin's tokens equal the stored name's, and the two spellings share no word unpinned;
  - the true case: Fenerbahçe @ Aston Villa places on its game with the Tie as DRAW, and is refused for no fit without the pin;
  - a stored name with one word more (Fenerbahçe SK), or with ç decomposed (c + U+0327), is not the pin's team and is refused;
  - the club's own game against another side, with Aston Villa absent, is refused as today.

## 2026-10-14 (#516: win-rates-carry-the-line — ARCHITECT addendum 64 items 2 and 3, #510, #511)
- calibration: the overall hit rate carries the line against the close (`vs_close`) over the same games, against the grading close. `compute_calibration(with_vs_close=True)`; the command prints the line under the hit rate. The per-bin rates carry nothing ("a frequency per band is calibration, not a record").
- The web dashboard (/predictions): each model version's top-pick accuracy carries its line, in an "Against the close" column.
- ncaa-shadow-grade: the hit rate carries `vs_close`, per the shadow's own close (the odds table), printed under the summary.
- src/walters/vs_close.py: `outcome_row` and `block_from_outcomes` build a stored prediction's results row against the grading close. Calibration, the web route and the RESULTS.md MLB/PL sections use them; nothing is computed twice.
- RESULTS.md: the "Soccer (PL)" section reads PL rows and no other (the query filters by the competition it names).
- export-results: a competition code the database does not hold refuses, exit 2, naming the code (`UnknownCompetition`). It never falls back to every row, and nothing is written.
- Unchanged by the ruling:
  - the Cockpit's ledger hit rates, whose mean CLV is their line;
  - the frozen receipts and backtests.
- docs/CLI.md: a `calibration` row; the export-results, results-tally and ncaa-shadow-grade rows.
- Tests: tests/test_win_rates_carry_the_line.py (5); tests/test_ncaa_shadow.py's grade test reads the line. All six fail on main 84c26f4.

## 2026-10-13 (#513: record-vs-close — ARCHITECT addendum 63 items 3 and 4, #512, #507)
- src/walters/vs_close.py (new): the record against the close, one helper for every family. `block()` takes (model p, close p) of the outcome that happened, per decided game with a close. It returns the games, the model's log-loss, the close's, close minus model, its bootstrap 95% interval (10,000 resamples, seed 20261013, `random.Random`, the 250th and 9,750th sorted means) and the count of games the model beat the close (strictly lower log-loss). The block is a function of the set of games (sorted first) and carries no negative zero. `line()` prints it.
- NFL: `record.vs_close`, each `record.by_week[w].vs_close` and `pre_live.record.vs_close` in the results file. `grade_nfl` returns the same blocks, read as the file reads its rows. The receipt, nfl-grade and the RESULTS.md NFL section print each under its win rate.
- MLB and PL: `export_results` gains a `record` block: `games`, `hits` and `vs_close`, plus `kalshi_only_closes`. The export-results console and the RESULTS.md MLB and Soccer (PL) sections print the line.
- INTL: `record.vs_close` in the production results file, printed by export-intl-results. unl-shadow-grade carries `vs_close` on the same priced games and on each |model − close| bucket, prints it under the hits line and each bucket, and its RESULTS.md section prints it.
- NHL: nhl-shadow-grade returns `vs_close` per name, never pooled: v7, the goal-margin fallback, and the v1 reference. It covers decided games with a priced close and counts `undecided`. The console and RESULTS.md print one line per name.
- The shadow sections and the NHL file notes now read "against the close only" instead of "divergence only".
- tools/cockpit.html (the repo copy; republished only on the operator's word): the Ledger card shows each loaded results file's model record. It shows the win rate with its line, read from the file's record block and never recomputed.
- docs/roadmap.json: the mlb-pitchers lane (#507), addendum 63 item 4's text.
- docs/CLI.md: the rows of every command above.
- Tests: tests/test_vs_close.py (16) and tests/test_record_vs_close.py (10; one runs the Cockpit's line in node against the Python line). Additions to the NFL, UNL and NHL tests.

## 2026-10-13 (#509: nhl-shadow-fallback-name — ARCHITECT addendum 63 item 2, #508)
- src/walters/nhl_shadow.py: a walk that took the goal-margin fallback for any game is not v7. `shadow_name(fit_block)` reads the name from the fit block: no fit gives `nhl_elo_v1` (addendum 49, unchanged); a fit with `goal_margin_fallbacks` above 0 gives `nhl_elo_v7_goal_margin_fallback`; otherwise `nhl_elo_v7_xg_margin_no_na`. The name is on the header and on every row. The fit block is written as it is. A fallback file carries its own note and a `not_v7` line; `gate_verdict` is unchanged (v7's declaration includes the goal fallback).
- nhl-shadow-grade never pools a fallback file with a v7 file. The fallback has its own line: pick-vs-close, value-side, unpriced, unanchored. The file's fit block decides, so an older v7-named file whose walk took the fallback is graded there. `graded_by_name` counts each name's calls; the console and the RESULTS.md shadow section print it.
- cli.py: `export-nhl-predictions` prints `not_v7` as a `✗` line; `nhl-shadow-grade` prints the names graded and the fallback's line.
- docs/CLI.md (both rows); docs/specs/h2-cutover-runbook.md (the NHL post-check note).
- Tests: tests/test_nhl_shadow.py, 12 new cases (11 fail on main); three v7 cases moved to a fixture with xG for every game.

## 2026-10-13 (#506: roadmap-moved-lines-kept — ARCHITECT addendum 62 items 3 (#504) and 4)
- src/roadmap.py: the base check keeps the record. Every moved line the base holds is on the head, word for word, and in the base's order; the head only appends. A line changed or removed, or out of the base's order, fails the PR, naming the lane and the line. A lane only one side holds needs nothing from this (#504).
- docs/roadmap.json: lane nfl-qb, step 1 (the quarterback data probe) done on 2026-10-13, receipt "PR #489 merged at 7e6e88c". No date moves; the print reads the operator's run, due 2026-10-23, as the lane's next step.
- docs/CLI.md, docs/LEDGER.md and CLAUDE.md say so. Tests: tests/test_roadmap.py 125 (9 new cases).

## 2026-10-13 (#505: cl-venue-stop — ARCHITECT addendum 61 item 3, #498)
- src/walters/desk_policy.py: CL makes no venue call. `SKEW_TEST_VENUE_COMPS = ("CL",)` stops `venue_edge` right after UNL's stop, with the ruled reason "three-way soccer — no venue call before the skew test is read (CL)", on the window card and in a CL fixtures file. Its own switch, `SKEW_TEST_VENUE_RULE`, is off only under `base_v11()`, for the frozen pre-F1c golden battery's CL rows, as every rule that postdates it is.
- src/walters/venue.py: `KALSHI_FEE_M["KXUCLGAME"] = (1.0, 1.0)` ("It costs a fill. It prices no call."). CL stays out of `KALSHI_SERIES_BY_COMPETITION`.
- tools/cockpit.html (the repo copy; republished only on the operator's word): the charter's "cups when priced" waits on the skew-test ruling, and the stop is named in the charter and the PASS-reason list.
- Tests: tests/test_cl_venue_stop.py (9); tests/test_cl_kalshi.py's two CL tests now read the stop and the fee entry.

## 2026-10-13 (#503: roadmap-base-check — ARCHITECT addendum 60 item 3 (#490); addendum 61 items 4 and 5 (#492, #494))
- src/roadmap.py `check_moves` / `check_base`, run as `python scripts/ledger.py check-roadmap --base origin/<base>` in CI's `fragments` job after check-fragments.
  - A PR's `docs/roadmap.json` is read against the file where it branched (the merge-base).
  - For each lane both sides hold, a moved `earliest_live` and a moved `due` (on a step with the same `what`) each need a moved line the head adds: `which` the step's what or `earliest_live`, `was` the base's date, `now` the head's.
  - A cleared earliest_live needs its line with `now` null. A first date set, and a lane or step only one side holds, need nothing.
  - It fails naming the lane and the date, and never writes the file.
- Validation:
  - within a lane no two steps share a `what`;
  - a moved line's `now` may be null where `which` is `earliest_live`;
  - a milestone with no `due_on` key is refused, named (#494).
- The print: "in 1 day", "OVERDUE 1 day", "(+1 more step overdue)".
- Tests: tests/test_roadmap.py 116 (37 new cases; 79 on main). One moved line records one move (Codex on #503). Open for a ruling: #504 (a base moved line rewritten or deleted).
- Ledger: the records of addendum 61 items 1, 2, 6 and 7: merging by the called head (#502), the four calls, #500 and #501 closed on their ruling, #493 waiting on the count.

## 2026-10-13 (#499: kalshi-cl-series — ARCHITECT addendum 58)
- src/adapters/kalshi.py: CL reads Kalshi through KXUCLGAME, wired since 2026-10-13 ("wired as PL is: the soccer path, three legs, the same spread guard, the same placement"; CL stays market-only, with no model and no call). `SOCCER_GAME_SERIES` gains `"CL": "KXUCLGAME"`, pinned: no discovery call. `kalshi-replay` reads it with the other soccer series; `sync-kalshi-soccer --competition CL` stores what `kalshi_match.place` places.
- deploy/hosting/chains.py: `WINDOW_KALSHI` syncs CL as it syncs UNL. The host takes it with the tag that carries it (item 3); no CL sync goes into the operator's block before the architect has read one replay console with CL in it.
- docs/CLI.md: the `sync-kalshi-soccer` and `kalshi-replay` rows say CL is wired and since when. src/walters/venue.py: the stale "no UCL series is wired" comment is corrected (comment only; no fee entry added).
- Tests: tests/test_cl_kalshi.py (27): the Arsenal event's three legs on Lille @ Arsenal (HOME ARS, AWAY LIL, DRAW TIE); a CL event whose two names fit no stored game refused for no fit (3); the same spread guard; the receipt's 18 name pairs; the replay plan; the window chain; no venue series for CL; the sync storing three legs; a CL row with Kalshi legs makes no venue call today (quote-age hold). Open question #498 (needs-ruling): whether "no call" covers venue-edge once that hold lifts, and the KXUCLGAME fee entry.

## 2026-10-13 (#497: kalshi-history-probe — ARCHITECT addendum 60 item 7; finding #496)
- scripts/kalshi_history_probe.py: the read-only probe of Kalshi's price history for settled markets.
  - It uses the adapter's own base, pace (no pause) and page size (200), through `KalshiAdapter._get`, and records every call with its status.
  - Q0: the historical cutoff.
  - Q1: for each series in kalshi-replay's `series_plan`, the historical and live settled market lists, paged by cursor to their end: markets, events, first and last close, events by month.
  - Q2: three events per series (first, middle, last), with one-minute candlesticks for the six hours before each market's close (counts; the first, every thirtieth and the last).
  - Q3: every call made, in order, with its status; each one refused with its body whole.
  - It keeps one raw payload of each kind under logs/. `--out` writes JSON and is refused under data/, as the configured database or one of its sidecars wherever it lives (a hard link or symlink included), and as any existing SQLite file. Nothing printed is cut. Nothing is ingested.
- Tests: tests/test_kalshi_history_probe.py (17), offline.

## 2026-10-13 (#489: nfl-qb-probe — ARCHITECT addendum 59 item 5(h); lane nfl-qb, #427)
- scripts/nfl_qb_probe.py: the read-only quarterback probe, for the NFL seasons 2023 to 2026. It follows scripts/lineup_history_probe.py.
  - Ids come from the adapter's own mapping: `_CODE_TO_LEAGUE["NFL"]` and `DIRECT_BASE` from src/adapters/api_american_football.py; QB position names from qb_audit.QB_POSITIONS.
  - Q0 /status. Q1 /leagues coverage per season, verbatim.
  - Q2 per season: three finished games (first, middle, last) through /games/statistics/players. It prints the raw shape, the groups, the passing players with every stat name and value, every key or stat name that says "start" (or that none does), and the most attempts, labelled OUR READ.
  - Q3 the next unplayed game: /games?id, /games/statistics/players and both rosters' quarterbacks, verbatim.
  - A per-season summary at the end.
  - It never stops on an error, writes nothing, opens no database, and never prints the key. The operator runs it and pastes the whole output to the architect.
- Addendum 60 item 5 (#491 into #489): "A probe's receipt cuts nothing." Nothing the probe prints is sliced (a "start" value, an error body, a raw shape, a team block of another shape).
  - Every "start" field is printed with whose it is: team, group, and the player entry's id and name.
  - Q3 counts only entries that name a player, and prints the others whole.
  - A group, entry, status or stage of an unexpected shape is reported and never drops a game.
  - A year sent as digits is that year in Q1.
  - The most attempts are taken by attempts alone.
- Tests: tests/test_nfl_qb_probe.py (27), offline.

## 2026-10-13 (#488: model-roadmap — ARCHITECT addendum 59 items 5 and 6; Issue #486)
- docs/roadmap.json: the model roadmap, the first content of addendum 59 item 5(g) word for word. There are seven lanes: unl #220, pd #322, ncaa #79, leagues #322, nhl #105, cups #106 and nfl-qb #427. Each lane carries its state, its dated steps (owner architect, operator, code or calendar; `done` null or `{date, receipt}`), earliest_live, live_needs, vs_close, and a `moved` list (`{moved_on, which, was, now, why, ruling}`). The file is tracked and never under data/, and it changes only in a PR that quotes the ruling for the change.
- src/roadmap.py + `python cli.py roadmap [--today YYYY-MM-DD]`: read-only, with no database and no network.
  - Per lane, in the file's order: title, Issue, state, earliest live and the record against the close, then its next step with `in N days`, `today` or `OVERDUE N days`.
  - Then the ledger milestones that have a due_on, and a last line `overdue: N`.
  - It exits 0 whatever is overdue. A file that does not validate exits 2 and names the entry.
  - The ruled validation runs in code and as a test on the real file.
- CLAUDE.md, Queue section: the model lanes come first; the dates live in docs/roadmap.json and `python cli.py roadmap` prints them; no date moves a bar (5(c), quoted). docs/CLI.md: the `roadmap` row.
- .github/ledger/taxonomy.json (item 6): "Cutover ~Oct 8" due_on 2026-10-08 -> 2026-10-30; "Executable-edge ruling (2 wks of ladders)" 2026-10-13 -> 2026-10-20. The operator changes the same two on GitHub by hand.
- docs/LEDGER.md: the milestone table carries the two moved dates.
- Tests: tests/test_roadmap.py (79). A date is real only as YYYY-MM-DD (an ISO week such as 2026-W01-1, or a basic-format string, is refused). A taxonomy of the wrong shape, a lone-surrogate text field and JSON nested past the parser's depth each exit 2. The print uses 5(e)'s forms verbatim ("in N days", "OVERDUE N days", N = 1 included). Each validation rule, each of the six parts and each moved date has a test that fails when the rule is removed.

## 2026-10-13 (#483: cutover-active-timers — ARCHITECT addendum 57 item 8; #481)
- deploy/hosting/sp_cutover.py: the preflight reads the sp timers active on the host (`systemctl list-units --type=timer --state=active --no-legend --plain 'sp-*'`). An active `sp-*.timer` not on the timers list refuses the preflight, before anything is paused, and the refusal names each one with the list's path (receipt `timers_off_list`). Every active sp timer is kept whatever its name: one the list's name pattern cannot carry (`sp-x@y.timer`, an underscore) refuses and is named like any other, and the refusal says the list cannot carry it as built. A listing that cannot be read refuses. The list is never written. The preflight receipt carries `timers_active`. The dry run's stand-in reports its scratch list's timers as the active ones, so the dry run's scratch list stays as it is.
- docs/specs/h2-cutover-runbook.md: the preflight row names the read and the refusal.
- Tests: tests/test_h2_cutover.py (26). The host's shape of 2026-10-13 (two active timers off the list) refuses and names both; an active templated or underscored sp timer refuses and is named, never dropped; the list corrected by hand passes; an inactive listed timer, a service and a non-sp timer refuse nothing; an unreadable listing refuses; the dry run passes. `_real()` defaults to the fake runner, so no test calls the real systemctl.

## 2026-10-13 (#482: kalshi-matcher-pins — ARCHITECT addendum 57 item 6; lane #479)
- src/ingestion/kalshi_match.py: the matcher's pins. Penn is Pennsylvania; University at Albany is UAlbany; LIU is Long Island University; PSG is Paris Saint Germain; Stade Rennais is Rennes; M´gladbach (U+00B4) is Borussia Mönchengladbach. A pin (`PINS`) reads one of the event's two names whole, as the module takes it (the market's yes_sub_title, stripped), never a word of a name: Penn St. is not Penn. The fit's scoring (`side_score`, `_distinct_score`, through `_as_scored`; `_best_fits` is the one fit place() and the out-of-step pre-pass share) reads each name through the pins; which name is home comes back as the event's own name. Nothing else changes: one each, the best fit, a pair tie refused.
- Addendum 59 item 2 (#484): a pin fits its own team and no other. A pinned name scores against a team only where the team's stored name has the same words as the pin's name under norm_tokens, no more and no fewer (`_as_scored`, read by `side_score` and `_distinct_score`); against every other team it scores nothing, whatever word they share (PSG does not fit Paris FC, M´gladbach does not fit Borussia Dortmund, LIU does not fit Rhode Island). Against its own team it scores what the pin's name scored on 8c51f89 (1 to 3 per name; the twelve events' fits on their own games total 2 to 4, as on 8c51f89). An event's name that is not pinned is read as before; one each, the best fit and the refused tie do not change. `_best_fits` passes the event's own names to the fit.
- Tests: tests/test_kalshi_matcher_day_rule.py (104): the twelve events of the 2026-10-13 console, each placed with its pin and refused for no fit without it; Penn St. fits Penn State and not Pennsylvania; a pinned name with no game of its pair is refused as today, with the pinned team on the day against another side (Princeton @ Pennsylvania, alone and with Columbia @ Dartmouth; Lyon @ Paris Saint Germain), so one name alone never places a game. Addendum 59 item 2: the twelve events score on their own games what the head gave them; Bayern Munich / M´gladbach on a lone Bayern München @ Borussia Dortmund row, Lyon / PSG on a lone Lyon @ Paris FC row and Brown / LIU on a lone Brown @ Rhode Island row are refused for no fit with the pins on; a stored name one word more or one word fewer than the pin's name is refused; a pinned name scores nothing through a word of its raw Kalshi name (Stade Rennais against Stade Brestois 29, University at Albany against Long Island University); a stored name that differs from the pin's only in punctuation or case is the pin's own team (Paris Saint-Germain, long island university, BORUSSIA MÖNCHENGLADBACH); an unpinned name is read as before (Paris FC on a lone Lyon @ Paris Saint Germain row, limitation #485).

## 2026-10-12 (#477: kalshi-out-of-step — ARCHITECT addendum 54 item 6, addendum 55 item 3; finding #476, lane #478)
- src/ingestion/kalshi_match.py: on a series whose ticker carries a clock time, the events of the same two names are read together (`behind_out_of_step`, before any event is placed; every market read, priced or not). An event with no game number is out of step when no game of its two teams is on its date (the pair place() would choose; no fit is no game; a row that is not a game is not one), or when its date is before the run's day (US Eastern). Every event of the same names dated after the earliest one out of step, with or without a game number, is refused as "behind an event of the same two names out of step", and its line names that event and why, only where the market would otherwise take its place on a game (addendum 55 item 3); a market refused for a reason of its own keeps that reason, with no behind line. The event out of step keeps its own reason. A date-only series is outside the rule. place()'s names and best-fit code moved into `_names` / `_best_fits` (no behaviour change).
- Tests: tests/test_kalshi_matcher_day_rule.py (48): every later event held, not only the next; the earliest of two events out of step named; the same two names across a venue flip; a numbered event never out of step itself; today's seven open events (four legs as main, nothing behind, the later events under their own reasons); the next day's row not stored with a third event after it; the ruling's seven ALCS shapes (the receipt's Friday, the Saturday after, the evening of the rainout, a normal day, the next day's row not yet stored, yesterday's event still open (priced and unpriced), a numbered event behind) and a date-only series outside the rule; #474's tests unchanged.

## 2026-10-12 (#475: kalshi-matcher-switch — ARCHITECT addendum 50 item 6(b), addendum 51 item 7, addendum 53 item 4, addendum 54 items 3-4; called on the morning replay console, not before)
- src/ingestion/kalshi_sync.py: both sync paths (sync_kalshi_mlb for MLB/NFL/NHL/NCAA, sync_kalshi_soccer) place with kalshi_match.place. Games: the stored rows of the series' own competition on the events' days (stored_games; 6(c) rows are not games). The console prints the refusals by reason and the module's lines. The summary keys are as before, plus `refused` by reason. The old three-gate matchers and MAX_START_DRIFT are removed. The shared path finds its competition from venue.KALSHI_SERIES_BY_COMPETITION (series_competition) and refuses a series the map does not name once. `sport` is kept for the callers and read nowhere.
- src/ingestion/kalshi_replay.py: the two-way series come from the same map (shared_series). Each series is stamped after its own fetch, to the microsecond as a sync stores captured_at (Codex on #475), and replayed at that time (#470 item 3). Main's newest legs are read at or before that fetch (#470 item 2). Games are loaded with the syncs' stored_games.
- src/ingestion/kalshi_match.py: a time-tie refusal prints Kalshi's clock and occurrence and each passing game's id and ET kickoff (addendum 51 item 4). No rule changes.
- The alarm (addendum 54 item 3), both paths: it prints when no market is placed although markets were read and a game of the competition that has not started is inside the run's window; a game outside the window, one that has started and a row that is not a game do not count. The summary carries `alarm`. The shared path whose competition is not in the database answers not ok, "competition X not in DB" (item 4(b)). cli sync-kalshi-ncaa / sync-kalshi-nhl print the sync's reason, as sync-kalshi-nfl does (item 4(a)). docs/CLI.md: the five sync rows say where a market is placed; a kalshi-replay row (item 4(c)).
- Tests: tests/test_kalshi_matcher_day_rule.py (50 on this PR; 64 with #477's merged from main). The replay tests' raw INSERT carries the capture time as ISO text. The clock-ticker heading is reworded (addendum 53). tests/test_k1_kalshi_quotes.py and tests/test_unl_kalshi_discovery.py fixtures carry real-form dated event tickers in place of `EV1`. changelog.d/461's test count is corrected.

## 2026-10-12 (#474: kalshi-clock-ticker-date — ARCHITECT addendum 52; finding #473)
- src/ingestion/kalshi_match.py: on a clock ticker with no game number, the event's game is the pair's one game whose stored kickoff, read in US Eastern, falls on the ticker's own date; nothing else is read there (not the clock, not occurrence_datetime, not a day either side). Two games on that date refuse as two rows, naming them; none refuses under a reason of its own ("no game of the pair on the ticker's date") with a line giving the ticker date, its clock and our kickoffs of the pair in ET; a clock more than two hours from the chosen game's kickoff prints a line with both times, whether or not the market is placed. A numbered event (G1/G2) keeps the clock alone (addendum 51 item 3, lane #472). occurrence_datetime places nothing and refuses nothing on any series. The sync paths are unchanged (the switch PR).
- Tests: tests/test_kalshi_matcher_day_rule.py (34): the NLCS and ALCS events of 2026-10-12 on today's shapes, the missing row, two rows on the date, main's gate on the same rows; the 8h40 clock test now expects placement and the line.

## 2026-10-12 (#469: lineups-every-id — #467, Codex on #465)
- src/ingestion/service.py `sync_lineups`: a lineup row's team is found by every provider id a team row answers to (`team_merge.source_ids`: its own id first, then the ids a merge recorded), so a merged row's recorded id no longer loses that side's lineup after the match's lineups are wiped.
- Tests: tests/test_team_merge.py (18 with this one: a lineup carrying a merged row's recorded id is kept).
- docs/CLI.md: a `merge-teams` row (`--pair KEPT:MERGED`, `--backup`). changelog.d/465-merge-teams.md: the test count corrected (17 at #465's head; it said 11). Addendum 51 item 6.

## 2026-10-12 (#468: nhl-shadow-v7-line — ARCHITECT addendum 50 item 3, #466)
- src/walters/nhl_shadow.py `grade`: the v7 line counts a row that names v7 from a file whose fit was made, and no other row; a row that names the reference counts on the reference line by its own number (the v1-era files of 2026-09-30 to 10-02 name v1 and carry no reference block: they leave the v7 line). A row kept off the v7 line says why on its line (`not graded: no xG fit` / `not graded: not a v7 row`), never "no anchor" when it has one; RESULTS.md's NHL section names how many calls are off the v7 line and why. `grade()` returns `not_v7`.
- Tests: tests/test_nhl_shadow.py (a v1-era row on the reference line by its own number; a no-fit row with a book anchor).

## 2026-10-12 (#465: merge-teams — ARCHITECT addendum 44 item 3; Hawai'i, #426, #358)
- cli `merge-teams` + src/ingestion/team_merge.py (new): one program is one team row. Dry run by default; `--apply` only with `--backup` taken just before (dedupe-matches' check, on the teams count). A candidate pair: names equal once unescaped and reduced to letters and digits without case, the same sport, no stored game between the two, no day (UTC or US Eastern) holding a game of each; anything else is listed and left. The lower id keeps its row; every reference read from the live DB is re-pointed; the other row's provider ids are recorded on it (`<source>_also`, `merged_from`); the emptied row is deleted. A unique-table conflict or a reference the command does not know refuses the pair, naming the table. The dry run counts stored team names carrying an HTML entity, by sport.
- Addendum 50 item 5: `--apply` takes the pairs it merges (`--pair KEPT:MERGED`, as the dry run prints each candidate) and merges those and no other; a named pair that is not a candidate when the apply reads the database is refused with its reason; `--apply` without a pair is refused. A `competition_teams` membership of the other row in a competition and season the kept row is in too is one membership: dropped, not re-pointed, and counted by the dry run; every other unique-table conflict refuses the pair.
- A listing carrying either id finds the kept row: `service._find_team_by_source`, `refresh_by_id`, `resync_diff` and dedupe-matches read every provider id on a row (`team_merge.source_ids`).
- src/adapters/api_american_football.py: provider team names are unescaped where read.
- Tests: tests/test_team_merge.py (17 at #465's head; the count corrected by #469, addendum 51 item 6).

## 2026-10-12 (#464: nhl-shadow-names-its-model — ARCHITECT addendum 49, #463)
- src/walters/nhl_shadow.py: a shadow names the model it ran. Where the xG fit cannot be made (`live_xg` answers `xg_model` "unavailable (...)"), the file and its rows carry `nhl_elo_v1` and v1's verdict and number and no other model, and the file carries `v7_unavailable` with the reason. With the fit made, the file is unchanged (byte for byte against main). The grade reads each file's fit block, not its name (`fit_made`): a no-fit file is never counted on the v7 line, its reference line still counts, and RESULTS.md's NHL section says how many such calls it holds. This covers the ten host files of 2026-10-03 on.
- cli `export-nhl-predictions`: a line when v7 was not available.
- docs/specs/h2-cutover-runbook.md step 5: the ruled NHL shadow post-check (the first host nhl-daily after the flip prints the fit on the laptop's count of attempts and no fallback beyond games without shots).
- Tests: tests/test_nhl_shadow.py (the no-fit file and rows; rows unchanged with the fit; the grade never counts a no-fit file as v7 and keeps its reference line).

## 2026-10-12 (#462: closing-export-path-refusal — ARCHITECT addendum 44 item 8, #442 ruled)
- deploy/hosting/closing.py: a run whose export path (`logs/<run_id>.<slate>`) already exists does not start. The check runs under the lock with the run's own start, before the schedule read, the backup and every step, and is refused like any other refusal (exit 2, receipted, notified on a watch). The dry run says it would refuse. R6's move out of exports/ never replaces a file already at its logs/ name (`export_move_error`). Two runs of one family entering in one UTC second share a run id; the second no longer overwrites the first's kept export.
- Tests: tests/test_closing_runs.py (#442: the same-second refusal keeps the first export and runs no step; a run one second later has its own path; the move keeps a taken name). test_real_step_runner_against_a_fake_cli's second run moves one second later.

## 2026-10-12 (#461: kalshi-matcher-day-rule — the matcher's first PR: the module, its tests and a read-only replay; ARCHITECT addendum 37 item 2, addendum 44 item 1, addendum 50 item 6)
- src/ingestion/kalshi_match.py (new, pure): the ruled placement. The event's two names come from its own markets (sibling `yes_sub_title`s; the "A vs B" title is the fallback). They must fit a game one each ("St." = State), among the stored games of the series' own competition on the event's day: the ticker's date read in US Eastern, a day either side. A best fit shared by two pairs is refused. Inside the one pair, a date-only ticker takes its own date before a day off; two stored rows on the date are refused under their own reason, naming the ids dedupe-matches has to merge; a date that cannot separate the pair's games refuses, printing the ticker date and our ET kickoffs. A clock ticker keeps the time gate as built and the G1/G2 suffix. Then the run's window decides. Two markets claiming one side are both refused. Every refusal is counted by its reason, and each refused market's reason is kept. Addendum 50 6(c): a cancelled, postponed or stale-orphan row is not a game.
- cli `kalshi-replay` + src/ingestion/kalshi_replay.py (new, addendum 50 6(b)): fetches each series' open markets once (MLB, NFL, NHL, NCAA, each soccer series that resolves), keeps them in logs/kalshi_replay_<stamp>.json, places them with the new module on the stored games through a mode=ro session, and stores nothing. Per series it prints what the new module places and refuses, by reason, beside the legs main stored at its last sync, then every leg that differs. `--from-file` replays a kept file; `--series` narrows.
- The two sync paths are unchanged (the switch is its own PR, called on the replay's console).
- Tests: tests/test_kalshi_matcher_day_rule.py (29 at this PR's merge; 64 at the switch, #475, with #477 merged).

## 2026-10-12 (#457: closing-watch-before-tag — ARCHITECT addendum 47 items 6 and 7, addendum 48 items 5 and 6; Closes #453, #455, #459, #460)
- deploy/hosting/sp_receipts.py (`failed`, `key_line`): a closing miss, and a closing whose push failed after its page, count as failing (#453): "the mirror is what the compare and the Cockpit read, and it is short of that file until the next push." Rider (addendum 48 item 5, #459): a closing whose file was not written (`closing_file_failed`) counts as failing too, and its key line says `closing file NOT WRITTEN`.
- deploy/hosting/closing.py (`notify_failure`, new `page_operator`): a failure, a miss or a refusal that neither the screen nor the card topic took goes once through the operator topic (`NTFY_TOPIC`, as sp_notify's page), and the notification's receipt names the channel that took it (`channel`: card / screen / card+screen / operator / none). The watch's exit status does not change (7(a)).
- deploy/hosting/sp_notify.py (`held_behind`): for `sp-closing-watch.service`, by name, the unit's failure page goes out at most once in thirty minutes; every failure still writes its receipt, and a held-back one says so (`page_held_back`) and names the page it stands behind (`stands_behind`) (7(b)); only a delivered page holds the next back (Codex 4250381656).
- deploy/hosting/sp_cutover.py (preflight): refuses unless host.env itself says `SP_EXPORTS_MIRROR_ROLE=host`; prints, by name only, each setting whose value on the host changes when the pack's `.env` replaces the checkout's (only a setting to which host.env gives a value is left out, addendum 48 item 6 / #460 item 1; the list refuses nothing by itself), and receipts it as `env_changes` (7(c)); a pack with no env lists nothing, since install then leaves the checkout's .env (Codex 4250381661).
- docs: h2-cutover-runbook.md (section 0's role line; step 4's settings list and refusal row; step 5b's notes), CLI.md, the unit's comment. Tests: test_closing_runs.py (3), test_hosting_pack.py (1), test_h2_cutover.py (3); the cutover test's host.env stand-in carries the role.

## 2026-10-12 (#456: injuries-read-entries — ARCHITECT addendum 47 items 3 and 4; Closes #454, #451)
- src/adapters/api_american_football.py (`list_injuries`): an entry of the injuries read is told apart by its provider id. One id listed more than once is one entry, the first. Entries that share a name and differ in id are different players: each is kept and resolved by its own id (the roster's id join, then the position lookup), never by a name. "An entry with no id is resolved by name as today. It is not kept where an entry with an id has its name. Entries with no id that share a name are one entry, the first." (the fourth sentence as addendum 48 item 3 rewrote it; names compared as the roster join does, `qb_audit._norm`). Before, the read kept the first entry of a name and dropped the rest, so a quarterback listed second under a shared name was dropped. It replaces addendum 44 item 4's "a name the feed lists under two ids is ambiguous" (#440): the console line loses its ambiguous count, and the in-read memo goes (one id is one entry).
- src/walters/qb_audit.py (`roster_index`, `resolve_position`): only a roster row's `position` resolves a player, never `group` (#451). A name the roster holds more than once (by `_norm`: "Michael Carter" and "Michael Carter II" are one name) resolves nobody by name: `by_name` is unique-only, as `by_init` was, and both are counted over every roster row. `resolve_position(..., by_name=False)` resolves by id alone.
- Two rows of one name on one team are now possible in `injuries`; every reader of the table's `player_name` takes a list (nfl_predict qb_listed / positions_unresolved, the window's qb_news and digest, export, the web route). One downstream reader does key by name: the window card page (`deploy/hosting/sp_window_page.py`, QB news keyed `team_id|player`), so two same-name injured QBs on one team share one news item there. RULED a limitation (addendum 48 item 4, #458).
- `qb_audit.injury_entries` is the one place the entries are taken: the adapter's read and `nfl-qb-audit --live` (`audit_live`) both use it (Codex 4250343097). An entry whose name another entry of the read has, an id-less one included, is resolved by its own id alone (Codex 4250343104).
- docs/CLI.md: the sync-injuries row. Tests: tests/test_nfl_position_lookup.py (10 new, one for addendum 48 item 3: the six of the ruling and #451; the #440 test and the in-read memo test removed; the test-double receipt now asks the two ids of one name).

## 2026-10-12 (#449: host-closing-watch — ARCHITECT addendum 45, #405 and #408 ruled P1-P8; shipped HELD, C7 stands)
- deploy/hosting/closing.py: P1 the mirror push's role comes from `SP_EXPORTS_MIRROR_ROLE` (`push_mirror` and `install-push`); unset, or neither `host` nor `laptop`, refuses the run before any step (receipted, exit 2), refuses `install-push`, and preflight says so; no default. P2/P5 `preflight` and `test-page` take `--family`. P3 the watch's exit: 0 success, 2 a refusal, 3 (`NOTIFIED`) a failed run or a miss already receipted and notified, 1 what the process could not report itself. Every closing page, failure/miss notification and the test page end with `machine: host` or `machine: laptop`.
- deploy/hosting/systemd/sp-closing-watch.service + .timer (new, NOT enabled): `closing.py watch --family NFL --family SOCCER`, every minute of every hour (`OnCalendar=*-*-* *:*:00 UTC`, Persistent=false, AccuracySec=1s), `SuccessExitStatus=2 3`, `TimeoutStartSec=45min`, `OnFailure=sp-notify@closing-watch.service`. deploy/hosting/sp_notify.py: `unit_for("closing-watch")` → `sp-closing-watch.service`.
- deploy/hosting/sp_receipts.py: the table reads a closing line's `seconds` as its duration and has key lines for `closing` and `closing_miss` (no receipt changes shape).
- scripts/setup_closing_watch.sh: `--family` (repeatable; none = MLB, NFL, SOCCER) carried by the plist, the preflight, the test page and the closing words; `SP_EXPORTS_MIRROR_ROLE` is a required setting, and it must be `laptop` (`preflight --expect-role laptop`; Codex 4248790027: a laptop `.env` saying `host` would push into the mirror's host side). The runbook's host preflight passes `--expect-role host` (Codex 4248918614).
- docs: hosting-h1.md (H0-3 amended for this one timer, by name; T11's third list `HELD_FOR_CUTOVER`; H2 step 7 MLB after the flip), h2-cutover-runbook.md (section 0: the role setting, P8's rehearsal, P6, the unguarded hand run; section 1 step 5b the host step in P4's order and "was" restarting on the host; step 7 the MLB laptop duty; section 2 the "MLB laptop duty (addendum 45)" class; section 4 resolved), CLI.md, host.env.example.
- Tests: tests/test_closing_runs.py (role argv on both settings and refusal when unset or invalid; the watch's exit for success, refusal, failed run, miss, unreported failure and unhandled error; the page's last line on both roles; the setup script with `--family MLB`; the receipts table), tests/test_hosting_pack.py (the timer's own form and its H0-3 exemption by name, every other timer still H0-3; T11's held list).

## 2026-10-12 (#448: nfl-position-lookup — ARCHITECT addendum 44 item 4, THE POSITION LOOKUP; Closes #440)
- src/adapters/api_american_football.py: a listed injured player whose position the roster does not give is asked for by his provider id (`/players?id=`); only the answer's `position` field is taken. A name the injury feed lists under two ids is ambiguous: not asked, counted and listed (#440). A failed lookup (an exception, or a provider answer with errors) is recorded.
- src/ingestion/service.py + src/walters/player_positions.py: an answer that gives a position is kept in `player_position_answers` (one row per source and provider player id; position NOT NULL), read before each team's read and written after it, guarded by the table's existence. A kept position is used instead of a call. Addendum 46 item 2: an answer that gives none, an empty answer included, leaves the player unresolved and counted; it is not a failed read, it is not kept, and he is asked again at the next read. `SyncResult.position_lookups` sums the counts; a failed lookup is a failed read (`--strict`).
- The lookup runs for `--competition NFL` only (`cli.POSITION_LOOKUP_COMPS`; NCAA shares the adapter and makes none, Codex 4248625990); one id under two names is asked once in a read (Codex 4248626014). After a rate-limit answer no further lookup is made in the command; the ones not asked are failed reads under `--strict`, listed and not kept (Codex 4248901861).
- cli.py: `sync-injuries` prints `POSITION-LOOKUP (<COMP>): …` before the empty-answers line (which stays last), and the ambiguous and failed names.
- migrate_player_position_answers.py (new, additive, idempotent): creates `player_position_answers`. Before it runs, the lookup is still made and nothing is kept.
- docs/CLI.md: the sync-injuries row. Tests: tests/test_nfl_position_lookup.py (13); tests/test_closing_runs.py's A2 strict count now includes the failed lookups.

## 2026-10-12 (#447: mlb-actionable-splits-receipt — the declared toss-up splits, one run, filed as declared; Closes #354)
- `docs/receipts/mlb-actionable-2026-10-12T1214Z.md`: the operator's one run of the MLB actionable receipt with the #354 splits (by month of first pitch, by pick side) on the laptop at main 30b4d96, cherry-picked from `laptop/mlb-actionable-splits` 705196b with its blob unchanged (80806c6). Both splits reconcile with the parent (278 games, 163 wins). Read-only; no policy change (ARCHITECT 2026-10-12, addendum 44 item 6).

## 2026-10-11 (#439: cutover-pl-check-420 — #420 RULED (addendum 38) + #422 items 1-4 RULED (addendum 40 item 9) + addendum 41 items 4-5 (#443) + #441; Closes #420, #441, #443)
- deploy/hosting/compare_exports.py: `--ignore-keys` (keys left out at any depth, printed; it replaces the generic timestamp mask, so database timestamps and `match_id` are compared, `git_sha` reported on its own line) and `--require-predictions` (the count of rows with a prediction and its probabilities on each side; none, or nothing compared (a missing host file), is NO-COVERAGE). Both off by default.
- docs/specs/h2-cutover-runbook.md: the PL reference is written for the check on the laptop immediately before the pack, with `--start` / `--end`; the host exports with the same dates; the check leaves out desk, desk_meta, line_move and late_news_flag and exported_at (the file's write stamp, CONFIRMED by addendum 41 item 4), prints them and the predictions count; a check that does not pass ends the cutover for that day, the host stays paused (timers stopped, flag laptop, nothing resumed or restored) until the architect has read it; section 3 gains that case. hosting-h1.md H2 step 4 points to it.
- docs/specs/h2-cutover-runbook.md (#443 RULED, addendum 41 item 5): cutover morning step 1 uninstalls the laptop's closing watch with the CLV jobs and its receipt shows it gone (`launchctl list` reads `none loaded`); the rollback's launchd step and the preflight-refusal return reinstall it; after the flip the #405 ruling governs. hosting-h1.md H2 step 1 and Rollback the same.
- docs/specs/h2-cutover-runbook.md (#441, Codex on #439): step 3's reference export takes `--out exports/soccer_PL_<start>_to_<end>.json`, so a one-day window still writes the name step 4 copies.
- docs/CLI.md: the compare row. Tests: tests/test_compare_exports_pl_check.py.

## 2026-10-11 (#438: receipts-ro-419 — #419 + #421 (addendum 38 item 4) + #422 item 5; Closes #419, #421)
- `scripts/kalshi_leg_audit.py` (#419): every count straight from `odds_snapshots`, orphans (no match row) on their own line and never counted as tickered (`tickered` = tickered snapshots with a match row), `orphans=N` in the summary line of both database shapes; `--since` validated as `YYYY-MM-DD` (exit 2 otherwise); a graded query that fails is `NOT CHECKED` and exits 1; the IN list is chunked.
- `scripts/kalshi_leg_audit.py` and `scripts/soccer_rating_coverage.py` (#421 RULED): a copy that refuses mode=ro is opened on the plain path with `PRAGMA query_only = ON`, and the console says which form it used.
- `scripts/soccer_rating_coverage.py` (#422 item 5 RULED): the competition is looked up as soccer; a code with none, or more than one, refuses.
- docs/CLI.md: both rows. Tests: tests/test_kalshi_leg_audit.py, tests/test_soccer_rating_coverage.py.

## 2026-10-11 (#436: a40-probe-receipt — ARCHITECT addendum 40 items 4 (PROBE FIRST) and 7 (RECEIPT FIRST); Refs #432, #426)
- `scripts/nfl_injury_position_probe.py` (new, read-only): for the stored NFL injured players whose position did not resolve, the player id from the provider's own /injuries answer (by exact name; our rows store no id), then GET /players?id=: does the provider answer a position? For the operator's run; console on #432.
- `scripts/ncaa_hawaii_receipt.py` (new, read-only): our teams named like Hawai'i (ids, source ids, game counts), the three games, and the provider's answer for team 59 and team 901. For the operator's run; console on #426.
- Ledger: the addendum 40 item 7 FINDING (#426).
- docs/CLI.md: their rows. Tests: tests/test_a40_probe_and_receipt.py.
- Codex round 1: the probe's `--out` never aliases the database, its sidecars or data/; a provider errors envelope is a failed read (`provider error`), never "not in the feed"; a player left out by `--limit` has its console line; player objects are printed whole.

## 2026-10-11 (#435: soccer-injuries-one-sided — ARCHITECT addendum 40 item 6, A ONE-SIDED LIST GETS NO CALL; Closes #430, #437, finding #425)
- src/walters/export.py: soccer `input_quality.injuries` = {home, away}: {count, synced_at} (null where the team has no row); `injuries_synced_at` and the row's `injuries` block unchanged.
- src/walters/desk_policy.py: a soccer row with exactly one side's list empty is PASS, `pass_kind` `injuries_one_sided` (among NO_CALL_KINDS: no order, no exec, no value shadow), its reason naming the team; both empty or both listed unchanged. Own switch (`injuries_one_sided_rule_off()`), `desk_meta.injuries_one_sided_rule`. No probability changes.
- `scripts/soccer_injury_factor_receipt.py` (new, read-only): every graded PL prediction re-priced with the injury cut taken out of its expected goals; log loss both ways (all, by list-length difference, positive-edge cohort with how many keep +5pp).
- Ledger: the addendum 40 item 5 FINDING (#425) and the item 6 ruling.
- docs/CLI.md: the Desk row and the receipt row. Tests: tests/test_soccer_injuries_one_sided.py.
- Codex round 1: the receipt looks up the soccer `soccer_elo_poisson` row of a version only, and reads rho / max_goals as of each prediction (audited set-soccer-config edits walked back); a log-loss line over the rows the rebuild reproduces. `base_v11()` holds the one-sided rule off (frozen verify files).
- #437 RULED (addendum 41 item 2, rides this PR): every aggregate of the receipt over the rows it stands behind (the stored 1X2 rebuilt to 3 decimals and the factor's note agreeing with the cut taken back, a missing note included); a row failing either is left out of every aggregate, counted by reason and listed; the all-rows line stays, marked `ALL ROWS (reference)`. No cut is taken back from the note's rounded percentage.
- #437's third item RULED (addendum 42 item 2): a side whose stored expected goals sit at the model's 0.05 floor with a cut applied is a third reason a row is left out (counted under its own reason and listed).

## 2026-10-11 (#434: nfl-injury-unread — ARCHITECT addendum 40 item 4, AN EMPTY NFL INJURY LIST IS UNREAD; Closes #429, finding #424)
- src/walters/desk_policy.py: where either team's stored injury list is empty (`input_quality.injuries.<side>.count` 0), an NFL PLAY is sized as a QB-flagged one: half units, reason "injury list empty (<team>): QB rule unread → half units", tag `QB unread half units`. Quarantines, PASSes and shadows untouched; POLICY_VERSION v1.1. Own switch (`injury_empty_rule_off()`), `desk_meta.nfl_injury_list_empty_rule`.
- src/ingestion/service.py / cli.py: `SyncResult.empty_answers`; `sync-injuries` prints one `EMPTY-ANSWER (<COMP>): ...` line naming each team whose answer was empty; `--strict` does not fail on it.
- deploy/hosting/closing.py: the page's PLAY line says `injury list empty: <team>` beside B7's count; the receipt records `injury_lists_empty` (and each step's `empty_answers`); THE HOLD OF 2026-10-11, a second `CLOSING_HOLDS` row (NFL only): a PLAY tagged `QB-flagged half units` or `QB unread half units` says `QB: paste to the architect before placing`.
- Ledger: the addendum 40 item 3 FINDING (#424) and the item 4 ruling; the QB-term limitation is #427.
- docs/CLI.md: the Desk, sync-injuries and closing-run rows. Tests: tests/test_nfl_injury_unread.py.
- Codex round 1: `base_v11()` holds the rule off too (the frozen Cockpit verify files stay frozen); a strict failure ends with the `EMPTY-ANSWER` line, so the closing run's 5-line step tail keeps it.

## 2026-10-11 (#433: closing-file — ARCHITECT addendum 40 item 2, ONE CLOSING, ONE PAGE, ONE FILE; Closes #428, finding #423)
- deploy/hosting/closing.py: a closing run whose page went out writes `exports/closing_<FAMILY>_<start>.json` (the page's games only, each row as the export gave it, `count` the rows kept, a `closing` block: family, start, run_id, match_ids, called_off) after the phone accepted the page and before the push; a failed write is receipted and notified, never rerun. The run's export step writes `logs/<run id>.<slate name>` (`--out {export_out}`), so a closing run never writes, replaces or moves the slate file. The receipt records both files and their sha256 and `page.at`.
- deploy/hosting/chains.py: the three closing chains' export step takes `--out {export_out}`. cli.py / nfl_predict.py: `export-nfl-predictions --out PATH`.
- src/walters/venue_quote_age.py: `closing_` among the Desk export names.
- `scripts/closing_file_backfill.py` (new): rebuilds the closing files of past paged runs from the exports-mirror clone's history by the receipt's sha256 (run once, before the 2026-10-18 06:10Z squash). Never opens the database.
- Ledger: the addendum 40 item 1 FINDING (#423) and the item 2 ruling.
- docs/CLI.md: the closing-run, export-nfl-predictions and backfill rows. Tests: tests/test_closing_file.py; tests/test_closing_runs.py updated for the logs/ export.
- Codex round 1: `export-nfl-predictions --out` refuses a path under data/ or onto the configured database (law 5); a closing file already written for a family and start is never replaced (a manual rerun's write is refused, receipted and notified).
- Codex round 2: the `--out` guard also refuses the database's -wal/-shm/-journal sidecars and hard links to them (file identity).
- Codex round 4 (P1): the guard covers every database the process can mean: `DATABASE_URL`, config's `database_url` (the `./data/sports.db` default when the variable is unset) and the engine's own file.
- Codex (after the cap): the backfill never writes a closing file missing a paged game; such a run is INCOMPLETE, listed, nothing written.
- Addendum 41 item 3 (ARCHITECT 2026-10-11, THE FILE OF A SECOND PAGE): a start time paged a second time: the later page's file replaces the earlier, the earlier kept as `logs/<its run id>.<name>`, the later receipt names it (`closing_file.replaced`: file, sha256, run_id, kept_as); an earlier file that cannot be moved refuses the write (`closing_file_failed`) and stands. The backfill writes the later page's file and lists the earlier (`EARLIER`). This replaces Codex round 1's never-replace.

## 2026-10-11 (#417: addendum-36-seed — ARCHITECT addendum 36 items 1, 3 and 4; Refs #410)
- Ledger: the item 1 FINDING (the host's soccer model runs on default or other clubs' ratings) with its receipt, the BACKLOG entry for #410.
- docs/specs/hosting-h1.md B4: the item 3 amendment (the seeded ratings and team_to_league are the training database's state, not configuration; the host's soccer model rows are evidence of nothing until the cutover).
- docs/specs/h2-cutover-runbook.md: one check after `install` and before `flip`: the installed database's PL export equals the laptop's last file from that database, number for number (`compare_exports.py`, VERDICT: CLEAN).
- `scripts/soccer_rating_coverage.py` (new, read-only): per team of a competition and season, its id, name, production league rating or MISSING, and team_to_league; totals. Tests: tests/test_soccer_rating_coverage.py.

## 2026-10-11 (#416: kalshi-leg-audit — ARCHITECT addendum 37 items 1 and 4; Refs #413)
- `scripts/kalshi_leg_audit.py` (new, read-only): by series and capture day, the games whose ticketed legs name two events and the events whose legs sit on two games (match id, teams, kickoff, tickers, capture times); totals, first day per series, listed games with a graded prediction, and the count of untickered captures. For the operator's runs on both machines; consoles on #413.
- Ledger: the addendum 37 item 1 FINDING (BACKLOG entry for #413).
- docs/CLI.md: its row. Tests: tests/test_kalshi_leg_audit.py (a throwaway SQLite file).

## 2026-10-11 (#415: addendum-34-rulings — ledger only, ARCHITECT addendum 34 item 7)
- docs/ledger/entries/2026-10-11-addendum-34-rulings.md: the rulings of addendum 34 items 2 (#404: grade_nfl accepted as grading; the close-age line follows the field, none for the NHL / UNL shadow sections) and 3 (#340: mode=ro stands, never immutable). No code.

## 2026-10-11 (#414: kalshi-leg-guard — legs of two events are never a pair — ARCHITECT addendum 37 item 3; Refs #413)
- `src/walters/kalshi_legs.py` (new): the one helper. A game's current Kalshi legs (newest per side before kickoff) are read as a set only when their stored tickers name one event and that event's current legs sit on no other game; else the game is mismatched and its events are named. Works on a SQLAlchemy session or a raw sqlite3 connection; answers nothing before `migrate_kalshi_ticker.py`; legs with no ticker are read as before; nothing stored is touched.
- Readers guarded (a mismatched game's legs are dropped before anything is computed): export.py (`_collect_rows` for the MLB/soccer predictions exports, `_fixture_row` for fixtures / the window card / the shadow files), nfl_predict.py (export-nfl-predictions), window.py (venue gap), line_move.py (`line_move_for_match`), close.py (`grading_close`'s Kalshi-only close), clv_restate.py (`_close_for`), k_receipt.py (`ladders`), unl_ladders.py (`receipt`), mlb_odds_timing.py, cli.py `kalshi-disagreement`, deploy/hosting/closing.py (`price_captures`), scripts/kalshi_soccer_incomplete_receipt.py and scripts/kalshi_soccer_twoway_receipt.py.
- Export contract (additive): `kalshi.status` `mismatched` with `events`; `kalshi_legs` null; exec fields null; `input_quality.kalshi` `mismatched`; `counts.kalshi_mismatched`; `desk_meta.kalshi_leg_guard`.
- Tests: tests/test_kalshi_leg_guard.py.

## 2026-10-11 (#412: kalshi-event-probe — ARCHITECT addendum 37 item 2, Law 1 first)
- `scripts/kalshi_event_probe.py` (new, read-only, GET only, no key): per event ticker (default: the nine KXNCAAFGAME events of the addendum 37 receipt), the event object and its markets at any status, every time field verbatim, the ticker's date stamp as written; `--out` appends one JSON line per event. For the operator's laptop run; its console and file go in the matcher PR before item 2 is built.
- docs/CLI.md: its row. Tests: tests/test_kalshi_event_probe.py (fake fetch, no network).

## 2026-10-11 (#411: soccer-rating-source — a default rating is labelled and gets no call — ARCHITECT addendum 36 item 2; Refs #410)
- `_generate_predictions_soccer` (src/walters/training.py): every soccer prediction's `factor_breakdown` carries `home_rating_source` / `away_rating_source`: `model` when the team is in the production model's league rating table, `default` when it is not (EloState.get's starting rating). The report-only rows carry the same two keys. No probability changes.
- `export-predictions` (soccer, src/walters/export.py): `input_quality.rating_source` {`home`, `away`} beside `strengths_source`; null on a prediction written before the label. The window card's `model` block copies it (`rating_source`, src/walters/window.py).
- Desk (src/walters/desk_policy.py): a row whose `rating_source` reads `default` on either side is PASS, `pass_kind` `default_rating`, reason naming the team(s): units 0, no order, no exec block, no value shadow, never a parlay leg. Checked after the started rule. `desk_meta.default_rating_rule` = true; `default_rating_rule_off()` for comparison. A row without the label is unchanged; the Desk golden holds.
- CSV (`export-predictions --format csv`, soccer): `home_rating_source` and `away_rating_source` columns (Codex on #411).
- Tests: tests/test_soccer_rating_source.py.

## 2026-10-09 (#409: Codex sweep of #340 and #310, two deploy fixes)
- `sp_deploy`: a `git checkout` that exits nonzero after HEAD already moved to the target (a failing post-checkout hook) is now receipted at the target with `checkout_warning` and its new migrations printed; the receipt and the exit stay nonzero, since the hook may not have finished (Codex on #409). Before, it was receipted as a failed checkout with the old code "still" live, and a retry saw an empty range, so the migrations were never printed (Codex P1 4200879012 on #310).
- `sp_deploy._classify`: per-requirement options are read across the whole line. A `--config-settings` / `-C` after an environment marker (`pkg>=1; python_version >= "3.0" --config-settings=...`, which pip accepts) is refused like one before it; before, the marker split dropped it and the line counted as a plain specifier (Codex P2 4200879018 on #310).
- #340's two threads (4211712334, 4211712341) were already settled on main (0c87fe1, f53b611); nothing changed for them.

## 2026-10-09 (#407: odds source time stored and shown — ARCHITECT addendum 32 item 4, export contract + migration)
- Ruling (verbatim, item 4): "sync-odds-football stores the source's update time with what it writes: on every odds row, and on every book consensus snapshot it appends. Every export block that shows a capture time for those prices shows source_updated_at beside it, in the same form; where a session's rows differ, the oldest. The Desk does not read it. #91 and the quote-age rule stay exactly as built: every computed venue row is still held."
- Adapter: `NormalizedOdds.source_updated_at` (optional, default None). The american-football adapter's `list_odds` parses `response[].update` ("2026-10-08T02:15:10+00:00") to naive UTC. Absent, not a string, unparseable, or with no UTC offset: None, never guessed, never our clock. Hockey, soccer and MLB adapters untouched.
- Schema: nullable `source_updated_at` on `odds` and `odds_snapshots`, NOT mapped in the ORM (ARCHITECT addendum 35 item 2: the ORDER LINE convention): written by `database.write_source_times` and read by `database.attach_source_times` (guarded Core SQL, only when the column exists; per call, never cached). Migration `migrate_odds_source_updated_at.py`: additive, idempotent, receipt of rows that carry the field and rows that do not, per table and source. No backfill.
- Sync (`sync_odds_nfl`, sync-odds-football, NFL + NCAA): every odds row stores it; every book consensus snapshot stores the oldest of its 1X2 rows, and unknown when any row is unknown.
- Exports (named from the code): `src/walters/export.py` `_fixture_row` `market` block, 1X2 close and the dark spread-derived fallback (export-fixtures, the window card, the NHL/intl shadow rows that share the grammar); `src/walters/line_move.py` `line_move` book venue `from_source_updated_at` / `to_source_updated_at` (export-nfl-predictions, the window card); `src/walters/nfl_predict.py` export-nfl-results `graded.value_anchor_source_updated_at`. Contract text in docs/CLI.md.
- Not in this PR (per the ruling): the close's own source time on results rows (`close_at`, close.py), any rule that reads the field, any resume of the venue engine. The Desk does not read it; the Desk golden is unchanged.
- RUN ORDER (addendum 35 item 2): any order. Before the migration the sync writes its rows and snapshots and every export shows the field null; the migration is preceded by a `.backup` and run by hand.
- Tests: tests/test_odds_source_updated_at.py (adapter present / absent / unreadable; the sync and the exports on a database WITHOUT the columns (rows and snapshots written, null shown, nothing raises) and after the migration (the values); the export blocks; the ORM never names the columns; the migration run twice).

## 2026-10-09 (#406: odds payload probe gains soccer and MLB (addendum 32 item 5); addendum 32 items 2 and 3 recorded for #399)
- `scripts/odds_payload_probe.py --sport soccer --competition CODE --game ID` probes the request `sync-odds` makes for a soccer competition (`APIFootballAdapter.list_odds`, `/odds?fixture=`); `--sport mlb --season S` probes the call `sync-odds --competition MLB` makes (`APIBaseballClient.list_odds_window`, `/odds?league=1&season=S`), and `--game` / `--match-id` its per-game rollover fallback. Same refusals as nhl/ncaa; the read/drop listing is per adapter. Read-only: nothing is stored.
- Ledger: addendum 32 item 2 (the odds payload read: American football's `response[].update` is dropped by the adapter; hockey has no such field) and item 3 (the ruling on what `update` is) recorded for Issue #399, with the operator's receipts verbatim.

## 2026-10-09 (#405: the host and the closing runs (C7), an account from the code — ARCHITECT addendum 31 item 4)
- Docs only, nothing built: docs/ledger/entries/2026-10-09-host-closing-account.md accounts for closing-run / closing-watch on the host as they stand on main (mirror role, backup, page, lock, MLB, receipts, a timer unit, the laptop's watch), with a file and line for every point, and ends with a proposal for the architect's ruling.

## 2026-10-09 (#404: close_minutes_before_start on every results row with close_at, and its median / largest / n in results-tally — ARCHITECT addendum 31 item 3, #382 first half; export contract, additive)
- Ruling (verbatim): "Every results row that carries close_at also carries close_minutes_before_start: whole minutes, rounded down, from the close's capture to the stored start, and null where there is no close. It is the age of our capture, not of the quote (#348), and the field's doc line says so. results-tally prints, for each sport that reports a close, the median and the largest over its window, with n. Nothing is renamed and nothing is removed."
- `src/walters/close.py`: new `minutes_before_start(captured_at, start)` (whole minutes, floored; None when either time is missing). Both builders of `close_at`, `close_block` and `grading_close_block`, now emit `close_minutes_before_start` beside it (null when there is no close), so all three carriers get it: the results export (`export-results`, MLB / soccer), `export-nfl-results` and `export-intl-results`. Doc line in the builders' docstrings and docs/CLI.md: the age of OUR capture, not of the quote (#348).
- `results-tally`: each sport that reports a close (MLB, Soccer (PL), NFL) gets a RESULTS.md line with the median and largest `close_minutes_before_start` over its window, with n, and the console prints the same, one line per sport. MLB / soccer use the results rows' close (`grading_close_block`) over the rolling window; NFL uses `grade_nfl`'s live season-to-date rows (the same close as `close_block`), which now carries a `close_minutes_before_start` summary.
- Nothing renamed or removed: `clv`, `value_side_clv`, `close_at` and the rest of each row stand as they were. No export-contract golden pins the field set; none needed updating.
- Tests: `tests/test_close_minutes_before_start.py` (6, all failing on main): floor to whole minutes and null; both builders; every results carrier (MLB, soccer, NFL, INTL) carries it wherever `close_at` is; the kalshi_only close; results-tally's median / largest / n per sport, on an isolated throwaway DB.

## 2026-10-09 (#403: the declared MLB receipt built — toss-up splits by month and pick side, #354; ARCHITECT addendum 31 item 2)
- `mlb-actionable-receipt` extended, nothing else in it changed (the existing output is a byte-identical prefix of the new one on both test fixtures). New sections after the blend table: the regular season's toss-up row (included rows) split by the calendar month of the first pitch's date in America/New_York (`Match.utc_date`, naive UTC; a row with none is the `no first-pitch date` cell, always printed) and by pick side (HOME / AWAY). Each cell prints a tier row's columns and its wins, and the toss-up rows left out for want of a book close in that cell, by reason.
- Under each split: `Σ cells: games, wins · parent: games, wins · reconciled|DIFFERS`. On DIFFERS the command prints the receipt, refuses (exit 2) and writes no file.
- The postseason's toss-up rows: one line of their own, never pooled. The blend split unchanged (Q3).
- Tests: `tests/test_mlb_receipt_splits.py` (month split with an ET rollover game, pick-side split, no-date cell, postseason line, CLI output, refusal by an injected mismatch). Read-only; no threshold, no sizing.

## 2026-10-09 (#402: sync_odds --limit means the next N; Closes #387)
- `IngestionService.sync_odds` (soccer path) now orders its candidates by kickoff (`utc_date`), then `id`, before `--limit` is applied, so the limit prices the next N scheduled games instead of the first N in storage order. AMENDED (ARCHITECT addendum 33 item 2): "A named game is never dropped by the limit. With --match-ids every named game is priced and --limit does not apply. The order is kickoff, then id, in both modes." Until this PR the limit (CLI default 20) cut a named `--match-ids` list, silently.
- The window service's `sync-odds --limit <n>` (deploy/hosting/sp_run.py) now prices that competition's next n scheduled games; the premise in deploy/hosting/chains.py ("sync_odds takes the next N scheduled games") is now true. Neither file changed.
- Test: tests/test_sync_odds_next_n.py (three upcoming games stored out of kickoff order, limit 2: the two earliest are priced; fails on main) and `test_a_named_game_is_never_dropped_by_the_limit` (three named games, limit 2: all three asked, in kickoff order; fails on main).

## 2026-10-09 (#401: ncaa-placeholder-rekey — ARCHITECT addendum 30 items 3 and 4)
- `sync-matches` (NCAA only): a stored SCHEDULED row at the provider's 04:00Z placeholder kickoff holds its natural key against a real kickoff within 24 hours; an unknown incoming id for the same home/away pair re-keys that row (`rekeyed=`, old id kept in `<source>_prev` and the `<source>_rekeys` log) instead of creating a second row. AMENDED (addendum 33 item 1): the placeholder window is consulted only where the 12-hour rule would create a row (no candidate within 12 hours, same pair or swapped); there the same refusals apply among placeholder rows (stored id still listed, row already claimed in the run, more than one placeholder candidate, pair swapped). A doubled game's real-kickoff row is re-keyed by the 12-hour rule, as on main; the placeholder row is untouched. A row at a real kickoff keeps the 12-hour window. NFL unchanged.
- `src/ingestion/placeholder.py`: `is_placeholder_kickoff` / `placeholder_resolved` moved here from `scripts/ncaa_rekey_receipt.py`, which now imports them (one definition, shared; script behaviour unchanged).
- docs/CLI.md: the laptop morning chain reads NCAA by date (today..today+7, one day per call) and then runs `refresh-by-id`, as `ncaa-schedule` does on the host.

## 2026-10-09 (#400: ledger — the college provider re-issued its game ids (#399); a correction to addendum 21; two receipts; nothing built)
- Finding #399: the provider re-issued its 2026 college game ids on 2026-10-09. No live college row has a fresh book price tonight. The odds side waits on a read-only probe and a ruling.
- The architect's correction of addendum 21 item 1: on the host, the announced times arrived on second rows (27 pairings twice on 2026-10-09). Also posted on #377.
- Receipts: NFL's by-date listing before the install (added to the closing-runs entry, posted on #385). PL's missing close season is 2025/26 (added to #397's entry, posted on #397).

## 2026-10-09 (#398: ledger — the architect's read of the soccer value receipt; PL close finding; #390 item 8; nothing built)
- The architect's read of the soccer value receipt (#396), verbatim. It is not a policy and changes none: value shadows stay unstaked (#86).
- Finding #397: half of PL 2024/25 + 2025/26 has no stored fdcuk_close, so the receipt's PL page stands on one season. The page is not regenerated.
- #390 item 8, noted and not ruled: a moved game landing on a start time that already had its closing yields superseded receipts each tick, then a late miss with the wrong reason.

## 2026-10-09 (#396: soccer value receipt — the one run, filed as declared)
- `docs/receipts/soccer-value-sides-2026-10-09.md` and its PL reference page: the operator's one run of `soccer-value-receipt` on the laptop (main ed5ecbb), spliced from `laptop/soccer-value-receipt` e6e9233 byte for byte (ARCHITECT 2026-10-09, addendum 28 item 5; Issue #383). Reconciliation PASS in all five leagues. Read-only; not gate evidence and not a policy.

## 2026-10-09 (#395: sx-shadow-dropped-label — a dropped league's shadow row ends at its own outcome)
- `_status_label` (src/walters/soccer_expansion.py): a league whose own gate outcome is not PASS returns that outcome only. soccer_expansion_shadow rows for SA, BL1, FL1 and ELC now read "DROPPED — calibration", no longer "DROPPED — calibration · verdict PASS · confirmation open" (the PASS and the open confirmation are PD's). PD's label is unchanged: "PASS · verdict PASS · confirmation open". ARCHITECT addendum 24 item 5; Issue #391.
- Pin: tests/test_soccer_expansion.py::test_shadow_label_a_dropped_league_ends_at_its_own_outcome, on the registry's recorded run (fails on ed5ecbb). Labels only: no gate, threshold, verdict or prediction changes.
- Codex on #395: a league dropped before the run (F1, no per_league entry) reads "DROPPED before the run — <recorded reason>", never "?".

## 2026-10-09 (#394: closing runs, #390 items 6 and 7 — ARCHITECT addendum 28 item 2; references #390, does not close it)
- Rulings verbatim in `docs/ledger/entries/2026-10-09-closing-390-items-6-7.md`. Daily-class: no model, gate, threshold or Desk rule changes.
- Item 6 (RULED): `deploy/hosting/closing.py` `covered_ids`. A game is finished with only at the start its cover recorded (`covers[].start`). A finishing receipt (a success, or the last of three attempts) counts the game only while its stored start, re-read by match id (`stored_starts`, new), is still that start.
  - A game a successful run paged, whose stored start then moves, forms a group at its new start, and that group runs. So does a game paged as cancelled or postponed that is later stored as scheduled at another start.
  - On ed5ecbb, `covered_ids` was a set of match ids, so such a game got no closing and no miss.
- Item 7 (nit): `unpaged_called_off(fam, now)` is bounded to the window `schedule()` reads, [now - 6h, now + 6h) (`schedule_window`, `SCHEDULE_HOURS`, new). `with_called_off` takes the same `now`. Before this, a called-off game whose start time ended with one or two failed attempts stayed in the watch's games, and in `closing-watch --dry-run`, for good.
- Tests: `tests/test_closing_runs.py` `test_390_6_*` (2) and `test_390_7_*` (1), all three failing on ed5ecbb. One existing assertion changed only for the new signature: `unpaged_called_off("SOCCER", NOW + 1m)`.
- Not built: the note beside item 5 (not ruled).

## 2026-10-09 (#393: ncaa-elo-v1r verdict: FAIL on the spread test; 2025 retired as a college test season; ncaa-backtest closed; no college shadow)
- The one gate run is spliced from the operator's branch `laptop/ncaa-elo-v1r-run-record` (130b481) by cherry-pick, byte for byte: the registry entry's run, `docs/registry/ids/ncaa-elo-v1r.txt` (762 ids) and `docs/registry/ncaa-elo-v1r.started.json`.
  - Candidate NCAAEloV1, v1's constants untouched, on the CFBD both-FBS stream; run at 2026-10-09T16:18:32Z, no prior read.
- The verdict is recorded with the architect's ruling verbatim (addendum 24 item 1): FAIL.
  - (1) Margin passes: log-loss 0.559642 against a bar of 0.664889. (2) Level passes: gap 1.818pp against 5pp.
  - (3) Spread fails: slope b 1.420537, outside 0.80 to 1.20 (too timid). (4) Range passes: ratings 1121.1 to 1906.2.
  - Status `closed`, verdict recorded at 2026-10-09T17:49:27Z. No confirmation window, no cohort. College football stays market-only.
- `registry.RETIRED_TEST_SETS` retires "NCAA FBS 2025 regular season (CFBD both-FBS labels; warm-up 2024)"; the next candidate declares the NCAA FBS 2026 regular season as it accrues (>= 500 games).
- `ncaa-backtest` refuses, exit 2, naming addendum 24 item 2(c), with or without `--baselines-only`, for good. `GATE_STATUS` is `CLOSED` (ruling 2026-10-09).
- `export-ncaa-predictions` refuses, exit 2, naming addendum 24 item 2(d), while the registry records a non-PASS verdict for ncaa-elo-v1r. `ncaa-shadow-grade` is unchanged.
- The #368 test-season fence lifts by itself with the run record: the 2025 lines and `ncaa-audit` return (no code).

## 2026-10-09 (#392: closing runs, the #390 follow-up — ARCHITECT addendum 26 item 2; references #390, does not close it)
- Rulings verbatim in `docs/ledger/entries/2026-10-09-closing-390-followup.md`. Daily-class: no model, gate, threshold or Desk rule changes. It gates the watch's install, not #385's merge.
- (a) Codex 4232719331: `deploy/hosting/closing.py` `covered_ids`. A game is finished with at a start time only when a successful attempt for that start time covered it, or when the start time has had three attempts and the last of them covered it. An earlier attempt's covers no longer count on their own. Before this, one failed attempt followed by a retry that found the game moved closed the game for good at a start time it no longer had.
- (b) R6 moving the export: `last_calls` follows the receipts, not the files. The base is the newest closing receipt of the family that carries `last_calls`, with the calls that run paged laid over it when its page went out. An export that no closing run wrote, written after that run started, comes before it for the games it holds. With no such receipt, the files' calls stand, as before.
  - The closing receipt's `desk_rows` now carry `call_text` (the call on the page), and the receipt carries `run_start_wall` (the wall clock at the run's start, which file mtimes are compared with).
  - A paged receipt written before `call_text` existed falls back to its export, if that file is still in exports/ with the same bytes.
- Tests: `tests/test_closing_runs.py` `test_26_2a_*` (2) and `test_26_2b_*` (2). All four fail on f256cdd. No existing test changed.
- (c) #390 item 4 (addendum 25 item 3), built under addendum 26 item 2(c): a covered game the schedule read finds CANCELLED or POSTPONED gets a line of its own on the page.
  - `called_off` re-reads the stored status by match id right after the schedule read, in `leave_moved`, and the receipt records the games as `called_off`.
  - The game stays in `covers`. It is not checked as moved, gets no Desk row and is not counted as a PASS.
  - `page_text` writes `<game> · <STATUS>`, adding `was <call>` when the last call was a PLAY or a LADDER. That `was` makes the page high priority.
  - Tests: `test_25_3_*` (2), both failing on f256cdd.
- Codex 4233123800 (P1, #392), on (c): `schedule()` drops every CANCELLED and POSTPONED game. So if the attempt that found the game called off failed afterwards (a later step, or a page ntfy did not accept), the watch rebuilt that start time without the game, or, when it was the only game, formed no group at all. The game's line was then never paged.
  - The fix, in `closing.py`: `unpaged_called_off` and `with_called_off`. A game an attempt recorded in `called_off` stays a game of its start time, at the start it was covered at, until that start time has a successful attempt or three attempts.
  - `due`, `plan` and the run's covers read the schedule plus those games. The run's own checks (missing from export, started) still read `schedule()`.
  - Tests: `test_392_4233123800_*` (2), both failing on bc6e107.
- Not built: #390 item 3 (an MLB group across midnight in New York) and item 5 (reading (a)'s edge). Both stay open on #390.

## 2026-10-09 (#386: soccer-value-receipt — the declared read-only receipt of value sides against the close)
- New READ-ONLY command `soccer-value-receipt [--out PATH]` (ARCHITECT 2026-10-09, addendum 21 item 6, amended before any read by addendum 23 item 2; Issue #383). Not gate evidence and not a policy; the operator runs it and the receipt goes to docs/receipts by PR.
  - Reads soccer-expansion-v1's 3,445 scored ids from the registry's ids file and re-prices them with the gate's own walk at the run record's rho / elo_goal_coeff, against fdcuk_close de-vigged as `market_side` does.
  - Value outcome = the largest model p minus close p. Tables: league (PD, SA, BL1, FL1, ELC, pooled) x edge bucket (under 5pp, 5-10, 10-15, 15+, 5+ as one row) x value outcome is the top pick; the 5+ row by kind (home, draw, away).
  - Columns: n, mean model p, mean close p, hit rate, hit - close pp and flat-stake return at the close's fair price, each with a seeded percentile bootstrap 95% interval (the match resampled within the cell, seed 20261009, 10,000 resamples, the return interval from the same draws); a cell of fewer than two matches prints no interval.
  - Buckets hold their lower edge at the gate's tolerance (5.0 is in 5 to 10); under 5 is 0 to 5; ties go to the first of home, draw, away.
  - PL 2024/25 + 2025/26 on a page of their own (`<stem>-pl-reference.md`), pooled over its two seasons as each league is, for reference; PL's live read (#92) is not this.
- The receipt prints the declaration AS ISSUED, its withdrawn sentence ("which must reproduce the run record's cohorts: 79 of 212, 88 of 225, 115 of 266, 93 of 205, 137 of 373") struck through and marked `[WITHDRAWN, ARCHITECT 2026-10-09 addendum 23 (b)]`, not deleted; the amendment (a)-(e) verbatim beside it.
- Reconciliation (amendment (b)), before any table: under `market_side`'s own rule the walk reproduces, per league, the run record's n_priced, both log-losses (model and close) and the cohort's count, hits and mean edge (floats to 1e-9; also the scored ids and each league's n). If it does not, the receipt is written with the declaration, the amendment and the difference only (no table, no PL page) and the command exits 2.
- Refusals (exit 2, nothing written): no run record; ids file sha differs from the record. There is no check of the 5+ row against the run record's cohorts: addendum 23 (b) withdrew that sentence (a different selection), so the earlier cohort check, its banner and exit 3 are gone.
- Writes nothing to the DB; never under data/. docs/CLI.md row; tests/test_soccer_value_receipt.py (synthetic leagues, throwaway DB, TMP registry).
- Codex review of 7086c1e: refuses (exit 2, nothing written) when either requested PL season scores no rows, when the ids file is malformed, or when the run record has no ids_sha256; a failed reconciliation removes a PL page an earlier run left at the same --out.
- The receipt's head prints the architect's correction to (a) of the amendment (addendum 27 item 1) beside the amendment, verbatim, pinned by a test; the amendment stays as issued.

## 2026-10-09 (#385: closing runs for every model family, paged by T-30 — ARCHITECT addendum 21 item 3 + addendum 22; closes #380)
- Rulings verbatim in `docs/ledger/entries/2026-10-09-closing-runs-all-families.md`. Daily-class: no model, gate, threshold or Desk rule changes. Branched from #370's head (c533485), not yet on main.
- `deploy/hosting/mlb_closing.py` became `deploy/hosting/closing.py`, for the families MLB, NFL and SOCCER (PL) (C1). The commands are `python cli.py closing-run --family F [--start ISO] [--dry-run]` and `python cli.py closing-watch [--family F] [--dry-run]`. `mlb-closing-run` and `mlb-closing-watch` stay as aliases.
- C2, timing: the watch ticks every minute. A family's earliest unstarted start time not yet closed (by a success or three attempts) covers the games starting within 10 minutes after it. The run for that start time begins between T-35 and T-5 and never inside T-5. A start time first seen inside T-5 is a miss (`kind: closing_miss`), notified once. A run's summary and page hold its own games only. This replaces the 5–65 minute window and the 90-minute summary.
- C3, chains (`chains.py`): `nfl-closing` and `soccer-closing` are derived from `freshen:NFL` and `freshen:SOCCER`.
  - They open with the schedule read: ~~NFL `refresh-by-id --match-ids <the covered games>`~~ (SUPERSEDED by addendum 25 2(i): NFL takes the SOCCER form), SOCCER `sync-matches` one UTC day per call with `--match-ids` (addendum 23 A1).
  - `sync-injuries` runs with `--match-ids <the covered games> --strict` (Codex round 2; was `--kickoff-within-hours`).
  - The book sync runs with `--match-ids <the covered games>`.
  - The export runs with `--desk`.
  - `CLOSING_FAMILIES`. `sp_run.py` refuses these chains (`closing_only`) and refuses any closing chain's dry run.
- New opt-in CLI options; the defaults are unchanged:
  - `sync-injuries --strict`: exits 1 when a read it needed failed, listing each one (`SyncResult.failed_reads`).
  - `sync-odds --match-ids` (soccer).
  - `sync-odds-football --match-ids`.
- C4, every family gets: the started test, the export-completeness check, the price check against the run's start, the moved export, the mirror push, and the failed-run notification (screen and phone, best effort). 380.1: for MLB, every starter the export lists must have been refreshed (`match_participants.refreshed_at`) at or after the run's start. If not, the attempt fails as `stale starters` and is retried; a side with no listed starter is not stale and gets its own line on the page.
- C5/C6, the page: one page per run, sent through the ntfy card topic (`NTFY_CARD_TOPIC`) and shown on the laptop's screen. It lists, in order: header; PLAY/LADDER lines (order line, exec edge, hold, `was <earlier call>`); value and quarantine shadow lines ending `shadow, not staked`; the PASS count. Priority is high when the page carries a PLAY. No line is over 100 characters; longer entries continue on indented lines. An unset or whitespace `NTFY_CARD_TOPIC` refuses the run before its first step, and the value is never printed. A page ntfy does not accept fails the run (`page`), and the watch retries.
- 380.3, backup: a backup the run takes counts only when the copy, integrity check, open, sha256 and hash file all succeed. Otherwise the run fails as `backup` before the first step, and whatever it left is renamed `.failed-<stamp>`, never deleted.
- 380.4, the lock: the run decides under the chain lock, re-reading the clock and its receipts there. A run started by the watch waits for the lock until T-5 at the latest.
  - Once it holds the lock, a start time that already has a success or three attempts ends the run as `superseded`: neither an attempt nor a refusal, and nothing is posted.
  - If it gets the lock inside T-5, that is a miss, receipted and notified.
  - The attempt number and the run's start (for the price and starter checks) are both taken under the lock.
- 380.5, K6: `applied` is true only when the weight is not 0 and the market's probability differs from the probability entering the blend (`training.blend_applied`). The probabilities are untouched; the bit-identical K6 test still passes.
- Reading 7: a refusal on a watch-started run is receipted and notified once per start time and reason.
- `scripts/setup_mlb_closing_watch.sh` became `scripts/setup_closing_watch.sh`: one LaunchAgent, `com.sportspredictor.closingwatch`, every 60 s, replacing #370's MLB-only job. It reads settings from the checkout's `.env` or host.env only and refuses any setting found only in the shell, naming it. No value goes into the plist. The run's own refusal checks run under `env -i`. It sends one test page through the card topic and refuses to install if ntfy does not accept it. No host timer (C7).
- Receipts: `kind: closing` with `family`, `start`, `covers`, `attempt`, `run_start`, `queued_at`, `page`, `superseded`; and `kind: closing_miss`. They replace `mlb_closing` and `mlb_closing_miss`.
- Docs: `docs/CLI.md` rows and the "Closing runs (operator)" section. The #370 ledger entry's R2 quotation is restored as issued.
- Tests: `tests/test_closing_runs.py` (renamed from `test_mlb_closing_autopilot.py`), 62 tests, one per ruling, plus a dry-run test and five for Codex round 1. The 380.5 test is in `tests/test_mlb_kalshi_only_suspended.py`. `tests/test_hosting_pack.py`'s law-1 option check resolves the closing chains with their example values.
- Codex round 1 on #385, four fixes, each with a test that fails on 140d0ee:
  - `target moved` (P1; SUPERSEDED by addendum 23 C, below): after the steps, a covered game whose stored start (re-read by match id) is no longer the start it was covered at fails the run as `target moved`, naming each game with the target, its covered start and its stored start. It is an own-check failure: the export is moved into logs/, nothing is pushed, no call is paged. Reading (conservative): one moved game fails the run even when the others stayed. A game an attempt found moved is not counted as closed by that start time's later success or third attempt; its new start time is its own receipt key and closes at its own T-35.
  - `watch` (P1): each queued run in one tick reads `clock()` when it starts, so the time spent on earlier closings counts toward its T-5 and started checks and its T-minus. A test-supplied `now` still fixes the tick's time.
  - `sync-injuries --strict` (P2): with `--kickoff-within-hours`, a competition not in the DB now fails the read (exit 1, `✗ STRICT: ...`) instead of returning at the empty-window branch. The default and an empty window are unchanged.
  - `parse_utc` (P2): any explicit offset (`-04:00`, `+02:00`, `-0400`) converts to UTC; `Z`, naive and the stored `2026-10-08 23:05:00.000000` read as before.
- ARCHITECT addendum 23 item 3 (rulings verbatim in the ledger entry; the round-1 fixes above went up in 1c4f44e before this ruling arrived). Main merged in first (#370, #378, #381, #375).
  - A1, the schedule read is strict: SUPERSEDED for NFL by addendum 25 2(i), below: ~~`refresh-by-id --match-ids` (exactly the named games; exit 1 on any not found, refused, excluded, without an id, unresolved, still rate limited or not stored) opens `nfl-closing`~~; `sync-matches --match-ids` (exit 1 unless the provider's answer held every named game) opens `soccer-closing` and `mlb-closing`. Defaults unchanged.
  - A2: the american-football adapter records a failed or empty roster read (`last_roster_failure`); `sync-injuries --strict` fails on it. Default unchanged.
  - A5: for Kalshi with more than one leg, only the legs the Desk read for the row (the call's and a value shadow's exec block, the order line, every leg under a Kalshi reference) must be fresh; a stale unread leg is listed (`stale_legs_not_read`).
  - B1/B2: the page goes first (phone tried three times, ten seconds apart), then the mirror push; a failed push after the page is receipted (`push_failed`) and notified, never rerun. A screen notification not posted is recorded only (`failed: notify` is gone).
  - B3/B4/B7: a game whose last call (SUPERSEDED: "the last call" is now addendum 25 2(iii)'s, below) was PLAY/LADDER and is now PASS gets `<game> · PASS · was <call>` and makes the page high priority; every line but the head and the PASS count names its game; an NFL PLAY says `<n> injured, position unresolved`.
  - B5: the 2026-10-07 hold names MLB and NFL (`families`), not PL. B6: a miss is receipted and notified once per start time and reason.
  - C: a covered game the schedule read moved leaves the run (receipted, a new start time for the watch); a run left with none fails as `start moved`.
  - D1: `closing.py install-push`; the setup script makes one mirror push (label install) under `env -i` and refuses to install if it fails. D2: the VPN line is MLB's.
  - Codex round 2: `sync_match_stats` NameError (an undefined `match_ids`) removed; the closing injury read scoped by `sync-injuries --match-ids`; a lock error is a receipted failed attempt (`lock`); a family `SP_SKIP_FAMILIES` names is refused (receipted and notified once) instead of dropped by the watch.
  - Findings logged, nothing built (F): `sync_odds` `--limit` without ORDER BY; PL lineups no chain refreshes; the export's latest Kalshi snapshot per leg.
  - Tests: `tests/test_closing_runs.py` 78 (the round-1 moved tests updated to C), `tests/test_refresh_by_id.py` +3 (A1 and #378's UNRESOLVED note; SUPERSEDED by addendum 25 2(i): the refresh-by-id A1 test is gone, the sync-matches one moved to `tests/test_sync_matches_named.py`, the UNRESOLVED test stays).
- ARCHITECT addendum 25 item 2 (2026-10-09 12:45 ET; rulings verbatim in the ledger entry). Main had not moved (fbf0d1e). Addendum 24 itself was not relayed to the builder; its item 3 is applied as addendum 25 2(i) states it.
  - 2(i), A1 amended: `nfl-closing` opens with `sync-matches --competition NFL --season 2026` by date, one UTC day per call, each naming that day's covered games (`--match-ids {start_day_ids}` / `{end_day_ids}`), the SOCCER form (`chains._closing_from_freshen`, the `by_id` branch removed). `refresh-by-id --match-ids` and `named_failures` are removed: `src/ingestion/refresh_by_id.py` and `cli.py refresh_by_id_cmd` are what #378 merged; `tests/test_refresh_by_id.py` is #378's plus the UNRESOLVED test. The `sync-matches --match-ids` test moved to `tests/test_sync_matches_named.py`. Reading (a) now applies to NFL too.
  - 2(ii), Codex 4232307577: a covered game the schedule read moved leaves the run right after the read (`closing.leave_moved`, `schedule_reads`), before a later step can fail, so a failed attempt's `covers` never holds it and three failed attempts do not close its new start; also when the read itself fails. A run left with no game ends there as `start moved` (no further step, no export).
  - 2(ii), Codex 4232307584: `_order_leg` names a leg only by the ticker the order carries; an order with no ticker (a LADDER with no HOME ticker) read no leg, so its stale HOME snapshot is listed in `stale_legs_not_read`, not a failure.
  - 2(iii), the last call (reading 7 amended): "The last call of a game is the call the operator was last shown for it: its call on the last closing page that covered it or, when no page has covered it, its call in the newest export that no closing run wrote. An export a closing run wrote never supplies the last call of a game that run did not page. C5's was and B3 read this." Built: `closing.last_calls`. A closing receipt records `export_written` (file, sha256 of the export it wrote, whatever the outcome, before R6 moves it) and `last_calls` (the last call it found before its first step for every game of the family found, start no more than 24 hours before the run). The newest family file a closing receipt names is followed: that run's paged calls (page accepted) and, for every other game, its receipt's last calls; a file no receipt names keeps its own calls, and older files fill the games it lacks. C5's `was` and B3 read it.
  - Item 3 (postponed or cancelled covered games): ruled, built in the follow-up #390; nothing here.
  - Tests: `tests/test_closing_runs.py` 84: 6 new, all failing on 08026e2 as written, five of them on behaviour (the unfollowable-chain test pins today's behaviour and fails there only on the new receipt field); the NFL read tests updated to the by-date form; the all-moved test now expects no step after the read and no export.

## 2026-10-09 (#384: findings logged and a receipt declared, addendum 21 items 5 and 6; nothing built)
- Finding #382: the recorded close is our last capture, and it is old. NFL: median 111 minutes before kickoff, none inside 30. MLB: median 60. The `clv` field names are left as they are until a ruled contract change.
- #357 gains the 2024 count (178 games stored one day early). #376 gains two non-blocking notes.
- Declared before any read (#383): the soccer value receipt. Value sides of the soccer-expansion-v1 scored ids against the de-vigged fdcuk close, by league, edge bucket and top-pick, with a PL reference page. Read-only; not gate evidence.
- The declaration amended before any read (ARCHITECT 2026-10-09, addendum 23 item 2): what was known, the cohort sentence withdrawn (marked, not deleted) in favour of a market_side reconciliation, the bootstrap, bucket edges and ties, and how to read it. Addendum 23's merge calls recorded.
- Logged, nothing built (ARCHITECT 2026-10-09, addendum 25 item 3; #390): the closing page's line for a covered game the schedule read finds cancelled or postponed, ruled now and built in the follow-up.
- The architect's correction to (a) of the amendment (addendum 27 item 1): the known log-losses are per league over every priced match, not over the cohort. Quoted beside the amendment.
- Finding logged, nothing built (addendum 24 item 5, #391): a DROPPED league's soccer-expansion shadow rows carry PD's verdict and "confirmation open".

## 2026-10-09 (#381: soccer-expansion-v1 confirmation cohort spliced, 60 PD fixtures)
- The cohort frozen on the laptop is spliced from `laptop/soccer-expansion-v1-cohort` (716c56c) by cherry-pick, byte for byte: the registry entry's `confirmation_cohort` and `docs/registry/ids/soccer-expansion-v1.cohort.txt`.
  - 60 PD fixtures, 2026-10-09T19:00Z through 2026-11-22T16:00Z, frozen at 14:14:16Z, after the verdict (12:47:39Z).
- PD stays a shadow until CONFIRMED.

## 2026-10-09 (#379: soccer-expansion-v1 verdict: PASS, surviving set PD; confirmation window open)
- The one gate run is spliced from the operator's branch `laptop/soccer-expansion-v1-run-record` (35135c4) by cherry-pick, byte for byte: the registry entry's run, `docs/registry/ids/soccer-expansion-v1.txt` (3,445 ids) and `docs/registry/soccer-expansion-v1.started.json`.
  - Candidate production v22 (rho -0.1, elo_goal_coeff 0.0008), run at 2026-10-09T12:24:56Z, no prior read.
- The verdict is recorded with the architect's ruling verbatim (addendum 20).
  - PASS, surviving set PD (log-loss 1.0027 against 1.0506; every gated band held).
  - SA, BL1, FL1 and ELC beat their log-loss bars but are dropped on calibration; they stay in the shadow.
  - The closing market beat the candidate in all five leagues (reported, never gated).
  - Status `confirming`, verdict recorded at 2026-10-09T12:47:39Z. The confirmation is the first 60 PD league games kicking off after that time.
- Until CONFIRMED, PD is a shadow: never a Desk call, never an order line.

## 2026-10-09 (#378: NCAA kickoff freshness on the host: a daily forward-week sync, ARCHITECT addendum 19 item 3)
- Ruling and cause: verbatim in `docs/ledger/entries/2026-10-09-ncaa-host-kickoff-freshness.md`.
- New host chain `ncaa-schedule` (`deploy/hosting/chains.py`): `sync-matches --competition NCAA --season 2026 --date-from D --date-to D` for D = today .. today+7, single-day calls (the american-football adapter sends `date` only when from == to). Sync only: no Kalshi, no export, no model step. `NCAA_FORWARD_DAYS = 7`.
- New timer `sp-ncaa-schedule.timer`: every day, 10:35 and 22:35 UTC (outside the H0-3 reboot buffer). Twice a day, so one failed run still leaves every stored kickoff under a day old. Added to the runbook's T11 `TIMERS` list, with the install steps for a live host (`docs/specs/hosting-h1.md`).
- `sp_run.date_vars` gains `{today_plus1}`..`{today_plus7}` (`{today_plus3}` unchanged).
- `ncaa-market`, the window service and the adapter are unchanged.
- Docs: `docs/CLI.md` (NCAA kickoff freshness paragraph), `docs/specs/hosting-h1.md` (timer table, T11, live-host install).
- Test: `tests/test_hosting_pack.py::test_every_ncaa_kickoff_in_the_next_seven_days_is_refreshed_every_day`. For each weekday it resolves every chain whose timer fires that day and requires single-day NCAA syncs covering today..today+7. On the old chains it fails on Monday with all eight dates missing (no NCAA sync fires on Monday).
- Host action after the tag that carries it is deployed: install and enable the new timer (runbook), then run `sp_run.py ncaa-schedule` once.
- **Amended by ARCHITECT addendum 21 item 1 (2026-10-09): the refresh is by id.** The provider's listing no longer carries college games that have not started, but the games still answer by id. Ruling and receipts are verbatim in the ledger entry.
  - New command `refresh-by-id --competition NCAA --days 7` (`src/ingestion/refresh_by_id.py`). It takes every stored SCHEDULED game on the UTC dates today..today+7 and makes one `GET /games?id=` per game (the adapter's `get_game`). It applies kickoff, status (the adapter's map; unknown stays SCHEDULED) and score.
  - Rate limits follow the sync-odds-football rule: paced at `SP_ODDS_FOOTBALL_RPM`, deferred on `RateLimited` and retried after Retry-After for up to `ODDS_RETRY_ROUNDS` rounds, never dropped.
  - NOT FOUND is counted, listed and untouched. Other teams are REFUSED and lookup errors are UNRESOLVED; both are untouched. The step exits 1 on unresolved or still-limited games.
  - The receipt is printed (asked, unchanged, updated, each kickoff moved with both times, each not found) and appended to the receipts log as kind `refresh_by_id`.
  - `ncaa-schedule` keeps its eight listing reads and runs `refresh-by-id` last. The timer, the window service, `ncaa-market` and the adapter are unchanged.
  - Laptop: `docs/CLI.md` morning chain, Phase 1, runs `refresh-by-id --competition NCAA --days 7`.
  - Docs: `docs/CLI.md` (command row, NCAA kickoff paragraph, morning chain) and `docs/specs/hosting-h1.md` (timer table, install note).
  - Tests: `tests/test_refresh_by_id.py`. Its chain test fails on the pre-amendment chain, where the kickoff stays at 04:00Z, and passes now. Rate limit, not-found and receipt-count tests are alongside, plus `test_every_day_the_host_refreshes_ncaa_games_by_id`.

## 2026-10-08 (#375: ncaa-elo-v1r gate command (D3-D6, --preflight, reservation, one recorded run) and confirmation command (D7); not run)
- **`ncaa-v1r-gate`** (new; `src/walters/ncaa_v1r_gate.py`; ARCHITECT 2026-10-08, addendum 11 item 3, PR B). It follows the soccer-expansion-v1 pattern.
  - `--preflight` scores nothing. Per season it prints the stream by season_type, the neutral count, the coverage and the D4 baseline (D6).
  - The run's preconditions, each checked before the reservation (exit 2, nothing written): declared and unrun; `--architect-word` given; `--stream-fingerprint` given; 2024 and 2025 covered (L2 + L3, each missing season named); the loaded stream's fingerprint matches; the scored set numbers >= 500.
  - The reservation `docs/registry/ncaa-elo-v1r.started.json` is written after the #329 cross-ref guard, carries the word and the fingerprint, and precedes the first game scored.
  - Then the D3 walk: 2024 is update only; 2025 `regular` games are predicted, then updated; every other 2025 game is walked, never scored; no 2026 game is scored. Then the D5 verdict.
  - The run is recorded with its scored ids (`registry.record_run`).
- **`ncaa-v1r-confirm`** (new) follows the intl-elo-confirm pattern for D7.
  - `--freeze-cohort` freezes the first 100 eligible fixtures, through `registry.freeze_confirmation_cohort`, which runs the guard.
  - `--substitute` replaces cancelled fixtures only. A finished fixture without a label stays pending.
  - The read reuses the gate's replay. `--record --ruling` computes CONFIRMED iff log-loss <= 0.6931 and < the D4 baseline − 0.010 on the same games.
  - The command refuses unless 2024, 2025 and 2026 are covered.
- **One D5 implementation.** `ncaa_backtest.logistic_slope / level_gap / level_ok / slope_ok` are extracted from `scripts/ncaa_v1r_design_receipt.py`, which now imports them. Re-running the receipt after the extraction gave output byte-identical to before (Runtime line aside).
- `ncaa_backtest.coverage_misses` is shared by the shadow, the gate and the confirmation. The shadow's refusal text is unchanged.
- #79's `ncaa-backtest` is unchanged. Nothing was run against a real DB, and the registry entry is unchanged (still `declared`).
- Docs: docs/CLI.md has two new rows; docs/specs/ncaa-elo-v1r.md has a new section 8, "Commands".
- Tests: `tests/test_ncaa_v1r_gate.py` (synthetic only).
- **Codex on #375, round 1 (both verified and fixed).** A cancelled cohort fixture that still carries a current label is never scored: it stays pending, release due, until `--substitute` replaces it (D7). A `STALE_ORPHAN` row ("never a fixture") is never eligible, at the freeze or as a replacement. Two tests, each failing on the previous code.
- **Addendum 17 (ARCHITECT 2026-10-08 18:56 ET), PR B's four choices RULED and built.** Quoted verbatim in the spec (section 8) and the ledger entry.
  - Item 1: there is no `OPEN_ITEMS` gate (removed). `--preflight` ends with `STREAM FINGERPRINT <sha256>`: the 2024 and 2025 stream as the gate walks it, each game with match id, kickoff, label season, season_type, merged home and away ids, scores, neutral flag and label source. The run requires it as `--stream-fingerprint` and refuses, before the reservation, when the stream no longer matches. The fingerprint is recorded beside the word in the reservation and the run record.
  - Item 2: the scored set (2025 `regular` games, level scores already skipped) is counted before the reservation. Under 500 the run refuses and records nothing; it is no longer recorded as INVALID.
  - Items 3 and 4: the end of the walk and the pending confirmation fixture stand as built.
  - Tests: four new (no `OPEN_ITEMS`; a mismatched fingerprint and a scored set under 500 each refuse before the reservation with nothing written; the fingerprint is stable and moves with every field it carries), the two open-item tests removed, seven updated for the required fingerprint. Each new test fails on the previous code.
- **Addendum 21 item 4 (ARCHITECT 2026-10-09), #375's two readings RULED.** Quoted verbatim in the spec (section 8) and the ledger entry.
  - Reading (1), accepted: "What D6 seals is the scoring of the test season: a game priced by the candidate and compared with its result. Loading the stream to fingerprint it and to count the scored set scores nothing and prints no figure across games; the preflight makes the same load. The reservation is written before any game is scored." The stream read before the reservation stands as built.
  - Reading (2): "When 2024 has no non-neutral regular game, D4 is undefined and nothing can be scored: the run refuses before the reservation and records nothing, as it does under 500 games. It is not an INVALID run and the read is not spent." Built: the run refuses (exit 2) before the reservation when 2024 has no non-neutral `regular` game, and records nothing. The earlier path reserved and recorded an INVALID run with 0 scored ids. `run_gate` raises the same refusal as a backstop.
  - Test: `test_an_undefined_d4_baseline_refuses_before_the_reservation_and_records_nothing` (fails on the previous code, which recorded 0 scored ids).
- **Addendum 18 item 1:** the #365 declaration ledger entry marks its middle reading, "The stream still starts from our FINISHED, scored rows", WITHDRAWN, quoting the ruling.

## 2026-10-08 (#373: soccer-expansion-confirm, the soccer-expansion-v1 confirmation window on the intl-elo-confirm pattern)
- New command `soccer-expansion-confirm` (ARCHITECT 2026-10-08, addendum 11, item 4). Flags: `--freeze-cohort`, `--substitute`, `--record --ruling TEXT` and `--no-fetch`; no flag prints progress. Flags and refusals mirror `intl-elo-confirm`, and the writes go through the same registry functions.
- Refusals: it refuses unless the registry holds the run record, a PASS verdict and a non-empty surviving set.
- Cohort: the first 60 fixtures by (kickoff, id) of the surviving leagues. Each must be a regular-season round (F3; an unplaced label refuses a freeze or substitution it could precede), kick off after the verdict, and be neither a test-set id nor a stale orphan; any status counts. The cohort is frozen once, after the cross-ref guard (#329).
- Substitution: only unscoreable fixtures are released, using the intl predicate unchanged. A FT row still waiting for its score stays pending.
- The read: the gate's own walk (per league-season cold start, min_prior 40, F5 batching) at the run record's rho / elo_goal_coeff. It reports pooled log-loss vs the pooled naive − 0.010, with per-league lines (reported, not gated).
- Naive source: the run record's per-league 2023/24 `naive_freq`. Only when one is absent does `naive_for` recompute it, and it is labelled.
- `registry.record_confirmation` computes the outcome: bar 1.0986 inclusive, reference strict, so a tie fails.
- Docs: CLI.md row; spec section 5a.
- Tests: 17 new tests (`tests/test_soccer_expansion_confirm.py`, synthetic leagues, tmp registry).
- Review round 1 (Codex P1, verified): `run_soccer_backtest` gains the opt-in `score_90_extra_time` (default off, so the gate and every existing command are unchanged). The confirm read passes it: an AET/PEN row is scored AND walked on its stored 90-minute score; one without that score is left out of the walk. Progress prints such rows as a DATA NOTE. One new test.
- Review round 2 (Codex P1, verified): the opt-in is renamed `confirmation_scoring` (default off; the gate is unchanged). The walk now uses the substitution's ONE predicate (`soccer_expansion.unscoreable`, the intl rule): a released row such as AWD / WO without a 90' score is neither scored nor walked; a non-FT row with a 90' score walks on the 90' score. One new test. The test module now tears down its league rows, so test order no longer matters.
- **Addendum 16 item 1 (#373 READ):** awarded games (AWD / WO) are always released, whatever scores the row carries; a finished row with no raw status code is never released, is walked and scored as the gate walks it, and is listed; progress prints a per-league-season census by raw code and lists every row the walk left out (id, kickoff, teams, raw code, scores); a fixture with no season at or before the 60th or a replacement refuses the freeze or the substitution; a cohort fixture that becomes STALE_ORPHAN is released, reason STALE_ORPHAN. The read stays on the candidate as gated (Q1).

## 2026-10-08 (#371: NCAA CFBD v2 migration marker — ARCHITECT, addendum 13 item 1; Closes #367)
- `migrate_ncaa_cfbd_v2.py` now also creates the one-row marker table `ncaa_cfbd_v2_migration` (Core SQL, unmapped in the ORM, the `ncaa_cfbd_labels_migration` convention) and writes its row if missing, printing `+ Wrote` or `· Kept`. Additive and idempotent; nothing else in the script changed.
- The non-dry `ncaa-cfbd-labels` gate is now `ncaa_cfbd.v2_migrated()`: `ncaa_cfbd_labels.season_type`, `ncaa_cfbd_ingest_records` AND the marker row. An `init_db()`-created table and column no longer count. The refusal names the marker and says: take the .backup, then run `python migrate_ncaa_cfbd_v2.py`. A `--dry-run` needs none of it. Readers (`records_ready`, coverage, the shadow) are unchanged.
- `drop_db()` (`init-db --force`) drops `ncaa_cfbd_v2_migration` as well, like the labels marker.
- Operator: if `migrate_ncaa_cfbd_v2.py` ran before this PR (no marker), run it once more after the .backup. It finds both objects, keeps them, and writes only the marker.
- Tests: `tests/test_ncaa_cfbd_v2_marker.py` (4; all fail on main, pass here). Existing CFBD tests now run the v2 script before a non-dry ingest.

## 2026-10-08 (#370: MLB closing-run autopilot — ARCHITECT addendum 13 item 3, Q2; laptop only)
- Ruling: A1–A9 verbatim in `docs/ledger/entries/2026-10-08-mlb-closing-autopilot.md`. Stacks on #369 (Q3): the summary block shows its `kalshi_only_hold`.
- `chains.py`: `CHAINS["mlb-closing"]`, derived from `mlb-preslate`, never copied. Steps 1–9 are its own. Step 10 is its export plus `--date {today} --desk`, so the file carries the Desk's call. `{today}` is the first pitch's America/New_York date, because the export's default slate is the UTC date and would drop a 22:10 ET game run after 20:00 ET. The chain is marked `laptop_only`, and `sp_run.py` refuses it (exit 2, receipted). `mlb-preslate` and `freshen:MLB` are unchanged.
- New `deploy/hosting/mlb_closing.py`, exposed as `python cli.py mlb-closing-run` and `python cli.py mlb-closing-watch`.
  - `run`, under the chain lock. First a `.backup` dated today (NY) in the operator's backup folder (`SP_BACKUP_DIR`, else `~/backups`). If none exists, one is taken through the `.backup` API, integrity-checked, opened, and given a sha256 sidecar; it is never written under `data/`. Then the ten steps. The run stops at the first failure, and after a failure there is no export, push or notification. On success: a summary block per game with first pitch within 90 minutes, `exports_mirror.py push --role laptop --label closing`, and one macOS notification per game.
  - One `kind: mlb_closing` receipt line either way: first pitch, steps (exit and seconds), export, Desk rows, push, backup, attempt.
  - The run refuses when every game in its window has started.
  - `watch` decides from the stored schedule with no network: MLB games not started, first pitch 5–65 minutes away, no success receipt for that first-pitch time, fewer than three attempts. It runs only if the feed (`statsapi.mlb.com/api/v1/sports/1`) answers. If not, it posts "MLB feed unreachable: VPN on, Tailscale off", writes a `kind: mlb_closing_miss` receipt and retries on the next tick. It is silent otherwise, and while a chain holds the lock.
  - A7 hold: `CLOSING_HOLDS`, a one-row table (a PLAY with exec edge under 4.0pp, or unknown, gets "paste to the architect before placing" on its notification and order line). It places nothing and never opens Kalshi's trading API.
  - `--dry-run` on both commands touches nothing: no step, backup, receipt, push, notification or network.
- `scripts/setup_mlb_closing_watch.sh`: a LaunchAgent (`com.sportspredictor.mlbclosingwatch`, `StartInterval` 300, logs under `logs/`) on the `setup_clv_capture.sh` pattern. The operator installs it; `--uninstall` is the off switch.
- Docs: `docs/CLI.md` rows plus the "MLB closing autopilot (operator)" section.
- Tests: `tests/test_mlb_closing_autopilot.py`, 27 tests, synthetic, with a scratch schedule in a throwaway DB and the network blocked.
- Review round 1 (Codex on #370): a failed or timed-out mirror push fails the run (`failed: push`, no notification; the export stays on disk), so the watch retries within 3 attempts. An unstarted stored game within 90 minutes with no Desk row in the export fails the run (`failed: missing from export`, `missing` lists the match ids; no push, no notification). A `sync-kalshi` step that prints "✗ Kalshi sync failed:" or "Kalshi sync: <reason>" but exits 0 is a failed step (`detected_failure`); the shared command is unchanged. A laptop-only refusal (SP_SKIP_FAMILIES names MLB) now appends a refused `mlb_closing` receipt, except on `--dry-run`. 35 tests.
- Review round 2 (Codex on #370): each notification result is recorded in the receipt (`notifications`) and validated before exit 0; on macOS a notification osascript did not post (nonzero exit, timeout, exception) fails the run (`failed: notify`) and the watch retries; off macOS "not macOS" is not a failure. A run whose target first pitch passes before the steps finish fails (`failed: first pitch elapsed during the run`, `completed_at`; no push, no notification), and the watch never retries a started first pitch. The summary rows and the export-completeness check use the run START, so a game starting mid-run is not silently dropped. 41 tests.
- Merged main (#369 on main) into the branch first.
- Addendum 16 item 2 (ARCHITECT 2026-10-08, #370 READ), rulings verbatim in the ledger entry:
  - R1: one started test, taken when the steps have finished (stored status re-read: LIVE/FINISHED, or first pitch at or before that moment). A started game has no summary block or notification and is not required in the export. A started target fails the run (`target started`, which replaces `first pitch elapsed during the run`).
  - R2: the run checks its prices. For every summary game, the stored book rows (`odds`, the last 1X2 capture session before first pitch) and the Kalshi quote (`odds_snapshots` source `kalshi`, latest per side before first pitch) the export shows must be captured at or after the run's start. If not: `stale prices`, naming the game and both times; nothing pushed or notified. No shared command changes; the sync-kalshi marker table stays.
  - R3: the chain lock is held from the backup check until the receipt line is written.
  - R4: a malformed `--first-pitch` is a receipted refusal, exit 2.
  - R5: the backup folder is checked before anything else; under `data/` it refuses the run, receipted, whether or not a backup sits there.
  - R6: a run failing on stale prices, a game missing from the export or a started target moves its export to `logs/<run id>.<file>` (`export_moved_to`). A failed push or notification leaves it in place.
  - Failed-run notification: a watch-started run that does not succeed posts one notification (first pitch, what failed or why it refused, attempt n/3; the third says no further attempt). It is best effort and recorded in `failure_notification`. A manual run prints only.
  - M1: `SP_EXPORTS_MIRROR_REMOTE` unset is a receipted refusal (exit 2) before the first step, and `setup_mlb_closing_watch.sh` refuses to install.
  - M2: the setup script posts a test notification, says what should have appeared and where to allow it (System Settings → Notifications → Script Editor), and prints the two needs: the laptop awake, and VPN on with Tailscale off.
  - Backup folder and manual-run targeting: accepted as built.
  - Tests: one per ruling (R1–R6, failed-run notification, M1, M2) in `tests/test_mlb_closing_autopilot.py`; 52 tests.
- Addendum 18 item 2 (#369's K6 record): at `market_blend_w` 0 the record reads `applied` false, `enabled` true, and keeps the weight and market numbers. Probabilities untouched. One test (`tests/test_mlb_kalshi_only_suspended.py`).

## 2026-10-08 (#369: MLB kalshi-only suspended; the MLB blend record — ARCHITECT addendum 13 item 2, Q3)
- Ruling: K1–K6 verbatim in `docs/ledger/entries/2026-10-08-mlb-kalshi-only-suspended.md`.
- Desk (`desk_policy.desk_call`), K1: an MLB row the 2026-10-01 rule would call on the kalshi-only mid is PASS with no reference. `pass_kind` is `kalshi_only_suspended` (added to `NO_CALL_KINDS`), tag `kalshi-only suspended (MLB)`, reason "kalshi-only suspended for MLB: the model number is unblended without books (ARCHITECT 2026-10-07)". Units 0, shadow units 0, no order, no exec block, no value shadow, never a parlay leg. `reference`, `market_ref` and `edge_pp` are null.
- K3: such a row carries `kalshi_only_hold` {`mid`, `bid`, `ask`, `spread_c`, `raw_edge_pp`, `equal_footing_edge_pp`, `would_call`, `would_units`}. The raw edge is model pick p minus the pick side's mid (AWAY = 1 − mid), as the 2026-10-01 rule measured it; the equal-footing edge is half of it. The would-be call and units are the pre-K1 path's own output (`_desk_call`), not a copy of its logic. Nothing reads the block as a call.
- K4: NFL and PL are unchanged (tests compare their desk blocks with the suspension on and off). The Cockpit's kalshi-only review counter (`kalshiOnlyGraded`, also the ledger summary's `kalshi_only_graded`) no longer counts MLB rows.
- Switch `KALSHI_ONLY_MLB_SUSPENDED`, as the #328 quarantine has: off under `base_v11()` (the frozen golden, byte-unchanged; parity battery 14/14 green). Forced on inside `base_v11()`, 22 golden call rows would differ, so the switch is load-bearing. `addendum_off()` holds it on, as it holds the quarantine. `desk_meta.mlb_kalshi_only_suspended` records it. `kalshi_only_suspension_off()` exists for tests only.
- `desk-rescore`: a published MLB PLAY the suspension now holds reads `kalshi-only suspended`, never "halved".
- K6: MLB predict (`training._generate_predictions_mlb`) writes `factor_breakdown.market_blend` = {`applied`, `enabled`, `w`, `market_home`, `market_away`} on each prediction. It records the existing blend branch and changes nothing in it. The fixed fixture (`tests/mlb_blend_fixture.py`) gives bit-identical probabilities on origin/main and on this branch: six of six, blend on and off.
- #354 data: `mlb-actionable-receipt` rows carry `blend` (blended / model alone / not recorded), from `market_blend.applied` only. The receipt adds one read-only table, blend x tier for all stages. Rows predicted before K6 are "not recorded". #354's month and pick-side splits are not built here.
- Cockpit (repo copy only; the live page is republished only on the operator's word): the pass-kind tag "kalshi-only suspended", the row greyed, the summary count, the hold rendered as "hold (record only, not a call)", and the policy card text.
- Tests: `tests/test_mlb_kalshi_only_suspended.py`. `tests/test_mlb_big_edge_quarantine.py` now reads the kalshi-only shadow sizing with the suspension off, and asserts K1 with it on.
- Headless verifies (Playwright, not in CI), both green:
  - `scripts/cockpit_mlb_quarantine_verify.py` 11/11. The MLB kalshi-only row is never logged, and the slate shows the suspended PASS with its hold. The #328 kalshi-only mid check moves to an NFL row.
  - `scripts/cockpit_kalshi_only_verify.py` 15/15. The seeded ledger counts 4 NFL rows; 2 MLB rows are not counted.
- Codex P1 on #369, fixed: a pre-Q3 export with a published MLB kalshi-only PLAY crashed `desk-rescore` with a TypeError on the None edge. The rescore row now carries `hold_raw_edge_pp`, printed as "hold raw edge … (not a live edge)", and the formatter prints "—" for any None edge. Test: `test_desk_rescore_cli_prints_the_suspension_with_the_holds_raw_edge`.
- **Addendum 15 item 2 (ARCHITECT 2026-10-08, RULED): the rescore prices the row's own order.** `desk-rescore` now carries the exec cost and exec edge of the row's own `exec` block under the current Desk (one helper, `desk_policy.call_exec_block`, read by both `desk_block` and the rescore): the same size, and none where the Desk writes no exec block. A suspended row reads "exec — (not priced: no order under the suspension)" and keeps the hold's raw edge. This also fixes the sibling on main since #328: a quarantine shadow was priced at one unit on the rescore line and at its shadow size in its exec block (#374). Test: `test_desk_rescore_prices_each_row_at_its_own_exec_block_and_a_suspended_row_not_at_all` (suspended, half-size quarantine shadow, plain PLAY; the unit in contracts and in dollars).

## 2026-10-08 (#366: soccer-expansion-v1 closing-odds name pins; second preflight read)
- `team_aliases.TOKEN_SYNONYMS` gains five football-data entries (ARCHITECT 2026-10-08, addendum 12): bilbao -> athletic, espanol -> espanyol, m'gladbach -> mönchengladbach, hamburg -> hamburger, brest -> brestois. Nothing else in the matcher changes.
- The football-data closes ingest (`soccer_odds_history`) normalizes both names to Unicode NFC before scoring, so an NFD-stored Mönchengladbach still matches. The shared tokenizer is otherwise unchanged, because the Kalshi matchers run on it.
- Guard: ath, borussia and stade are never synonyms (pinned by a test).
- Tests cover the architect's hard cases, the NFD form, a re-run storing nothing, and a tie still refused.
- Ledger: the second soccer preflight read, and #363 (design-stage band-rule finding).

## 2026-10-08 (#365: ncaa-elo-v1r declared, not run; design receipt OK; the NCAA shadow walks the declared stream)
- **Design receipt (step (a)).** Adds `scripts/ncaa_v1r_design_receipt.py`, a seeded simulation of the ncaa-elo-v1r gate design (ARCHITECT addendum 11, item 3). It reads no stored game and opens no database.
  - Receipt: `docs/receipts/ncaa-v1r-design-2026-10-08.md`. Stop condition: OK.
  - Settings (110,140) / (150,170) / (190,210), the committed receipt (the round-1 re-run below): mean slope 0.985 / 1.160 / 1.335; band rule 29.5% / 31.0% / 24.0%; D5 (2)&(3) 87.0% / 59.5% / 15.5%. (The first run, superseded, read 87.5% / 26.5% in the first setting; also OK.)
  - 675 scored games per season.
  - Tests in `tests/test_ncaa_v1r_design_receipt.py`.
- **Declaration (step (b)).** `ncaa-elo-v1r` is in `docs/registry/experiments.json`, declared through `registry.declare`. It is not run (status declared, run null, verdict null).
  - test_set: "NCAA FBS 2025 regular season (CFBD both-FBS labels; warm-up 2024)".
  - gate: D5 verbatim. Confirmation window: D7 verbatim.
  - Plan: 100 games, log_loss, bar 0.6931, must beat the D4 baseline minus 0.010.
  - `neutral_site_rule`: no_home_advantage_at_neutral, with v1's untouched `constants`.
  - `prior_reads_note` names the VOID 2026-09-30 v1 run (D9).
  - `prior_reads_note` also carries the addendum 14 correction to D9 (#368): no candidate has been scored on the test set; one 2025 outcome figure (non-neutral home win rate 0.597, n 652) was read before the declaration.
  - The spec, `docs/specs/ncaa-elo-v1r.md`, quotes D1–D9 and the architect's D5 note verbatim.
- **Shadow (step (c)).** `export-ncaa-predictions` now walks D2's stream: current CFBD labels, seasons 2024, 2025 and 2026, kickoff then match id, postseason included.
  - Level scores are skipped, counted and listed.
  - Neutral games are priced and updated with home advantage 0. A label without a neutral flag is treated as non-neutral and counted.
  - It refuses unless 2024, 2025 and 2026 are all covered (D6), naming each season that misses.
  - Upcoming rows say which home advantage they applied and that the neutral flag is unknown before the game (D8).
  - One D1 wrapper, `ncaa_backtest.NeutralRuleElo`, is shared by the shadow and the design receipt.
  - The file's `fit` block reports games walked per season, the season_type census, the level-score list and the count of labels without a neutral flag.
- `ncaa-cfbd-coverage` always prints 2024, 2025 and 2026 and says whether the condition holds in all three.
- #79's all-division stream, gate and numbers are unchanged. NCAA stays market-only.
- The gate command, `--preflight`, the reservation and the confirmation command are PR B.
- Adds `tests/test_ncaa_v1r_declaration.py` and a D8 row test in `tests/test_ncaa_shadow.py`.
- **Codex on #365, round 1.** P1: the v1r stream reads every stored NCAA match that carries a label, whatever our local status or scores (`load_v1r_games`; D2: the scores come from the label), so it counts the same current labels the coverage fact does. P2: the design receipt's cross-conference round is now drawn uniformly over valid matchings by rejection sampling. Re-run receipt: (110,140) / (150,170) / (190,210): slope 0.985 / 1.160 / 1.335, band rule 29.5% / 31.0% / 24.0%, D5 (2)&(3) 87.0% / 59.5% / 15.5%. Stop condition still OK.
- Addendum 13 item 1: the classification-field ruling (both fields required with division fbs; the refusal writes a zero record; a dry run prints the refusal and joins nothing) is quoted in the CFBD labels spec and pinned by a dry-run test. The code landed with #362.
- **#368 (addendum 14 item 2): the test-season fence.** Until the registry records the ncaa-elo-v1r run, no command prints a 2025 outcome figure. `ncaa-cfbd-coverage` withholds the 2025 home win rate in both blocks (counts, coverage, census and neutral counts stay). `ncaa-backtest` and `ncaa-audit` refuse with exit 2, naming the ruling. `resync-diff --competition NCAA` withholds its home win rate line when the listing includes 2025. The D9 correction is quoted beside D9 in the spec, the ledger entry and the registry. Closes the #372 item (this fragment's summary figures).
- **Addendum 15 (#365 read).** The D9 correction in force (addendum 15 item 1(a), superseding addendum 14's) is quoted beside D9 in the spec, the ledger entry and `prior_reads_note`; it names every prior read of the 2025 home rate and margin and what was declared with them known. `scripts/ncaa_source_probe.py` closes the fence's one hole: for 2025, until the run is recorded, its two rate-and-margin lines print n and the withheld notice. Level-score entries stay listed (item 3, no change). The two section-6 readings are accepted as built (item 4).

## 2026-10-08 (#364: registry cross-ref guard — #329 RULED, parts 1 and 2)
- New shared guard `registry.cross_ref_guard(eid, no_fetch=False)`. It first fetches origin `laptop/*` (`+refs/heads/laptop/*:refs/remotes/origin/laptop/*`); a failed fetch refuses.
- It then scans every ref the clone knows (`refs/heads`, `refs/remotes`; symbolic refs skipped) for a cohort, a run record or a reservation of the experiment that this working tree does not hold identically. Each kind is compared on its ledger field and its file: `confirmation_cohort` + `ids/<eid>.cohort.txt`; `run` + `ids/<eid>.txt`; `<eid>.started.json`.
- A hit refuses (a `RegistryError`; the CLI exits 2) naming every ref and its full commit, plus the sha256 when the record carries one. Nothing is written.
- Callers: `registry.freeze_confirmation_cohort` (every cohort freeze; `intl-elo-confirm --freeze-cohort`) and `soccer_expansion.reserve` (the one-run reservation; `soccer-expansion-gate`). Both call the guard before any write.
- New `--no-fetch` flag on `intl-elo-confirm` (with `--freeze-cohort`) and `soccer-expansion-gate`. It skips the fetch only, and the receipt prints `other clones not checked`.
- Receipt (read-only, `--no-fetch`, this clone): intl-elo-v2 is refused on the VOID 2026-10-07 cohort (`origin/laptop/intl-elo-v2-cohort`, e697533, sha256 419872ed…) and on `laptop/intl-elo-v2-run-record`. soccer-expansion-v1 passes (453 refs scanned).
- Tests: `tests/test_registry_cross_ref_guard.py` (13, synthetic git repos under tmp_path). `tests/conftest.py` stubs the guard for every other test, so no test reads or fetches the real repo's refs.

## 2026-10-08 (#362: NCAA CFBD scope + join — ARCHITECT, addendum 10 item 3)
- Data lane: no model constant changed; #79's all-division stream and its acceptance numbers are unchanged; the ncaa-elo-v1r declaration is not written.
- J1: `ncaa-cfbd-labels` retries a first-pass-unmatched game within ±36h by the same name tiers. It joins (`join_via dateshift`, listed with both kickoffs and the offset) only on exactly one (match, orientation), a match the first pass did not join, and agreeing scores. A name fit whose scores disagree stays unmatched and is listed with both scores.
- J2: our team names are html-unescaped before normalization in the join and alias vetting. In the v1r stream and the shadow, ids whose unescaped names are identical are one team, keyed by the lowest id: a read-time mapping, with every group and changed name listed. `teams` is never written.
- J3: aliases pinned: App State -> Appalachian State, Massachusetts -> UMass, Buffalo -> Buffalo State, Rice -> Rice Owls.
- J4: `ncaa_cfbd_labels.season_type` (nullable; new `migrate_ncaa_cfbd_season_type.py`, additive and idempotent), filled from CFBD's `seasonType` as served and carried on `Game` as data only. The ingest refuses to write until the migration runs. Readers work before it.
- SCOPE:
  - The v1r stream (`ncaa_backtest.v1r_stream`, walked by the NCAA shadow) is the CFBD-labelled games only.
  - The 95% coverage condition is now labelled ÷ CFBD's completed both-FBS games per season (it divided by every all-division stream game). The ingest receipt prints it and lists every unlabelled game.
  - `ncaa-cfbd-coverage` and the shadow's precondition re-read it from the side table and the saved payload it names.
- Tests: `tests/test_ncaa_cfbd_scope_join.py` (21, synthetic fixtures). Spec: docs/specs/ncaa-cfbd-labels.md; docs/specs/ncaa-shadow.md and docs/CLI.md updated.
- Codex on #362:
  - Every non-dry ingest run persists its receipt per season in new `ncaa_cfbd_ingest_receipts` (new `migrate_ncaa_cfbd_ingest_receipts.py`), zero joins included.
  - Coverage and the shadow's precondition read the latest receipt, so a zero-join re-ingest reads 0/N.
  - The v1r stream and the shadow's FBS test admit only labels that receipt joined (`admitted_labels`); stale rows, e.g. from a `--division ''` run, are listed and never walked.
- ARCHITECT addendum 11 item 2 (2026-10-08): J5 and LABEL SET L1-L4 (verbatim in docs/specs/ncaa-cfbd-labels.md and the ledger entry). Substring-tier joins need agreeing scores (first pass and retry; a failed first-pass substring goes to the retry). Ingest records go in `ncaa_cfbd_ingest_records`, replacing ee4276a's receipt table. Coverage = the latest record. A label is current when its fetched_at equals the latest record's (the stream and the shadow's FBS team set read current labels only). A non-dry run needs division fbs. ONE migrate script, `migrate_ncaa_cfbd_v2.py`, replaces the two unmerged ones.
  - Codex P1 (on #365): with division fbs, a payload missing either classification field refuses (exit 2; zero-scope record) and `in_scope_reason` never admits a game without both fields.

## 2026-10-08 (#361: soccer-expansion-v1 first preflight read; ledger only)
- Ledger note, nothing built. The architect read the first `soccer-expansion-gate --preflight` (laptop, c3a3744).
- The PL backtest is identical before and after #326.
- F3 placements are confirmed for the test seasons.
- 2023/24 is stored for none of the five leagues, so the run would refuse today. The operator syncs it (teams, then matches) and ingests the football-data closes for the ten test league-seasons.
- The one run follows the architect's read of the second preflight, not before Friday morning.
- The 2023/24 backfill joins the soccer-refresh pot: Monday's refresh drift line is read with that in mind.

## 2026-10-08 (#356: shadow leagues are never a call — ARCHITECT addendum 9 item 1, S1)
- Ruling (verbatim): "Real, and not a merge blocker: it needs a manual predict plus export on a shadow league, which no chain and no operator block runs, and main has carried the same generic path all along. Fix today in its own small PR, both halves, keyed on the one set desk_policy.SHADOW_VENUE_COMPS. (a) predict and export-predictions refuse a competition in the set, exit 2, naming export-soccer-expansion-shadow. (b) desk_call returns PASS for a model row whose competition is in the set: reason 'shadow league: never a call until CONFIRMED', no order, no value shadow. A league leaves the set only in a reviewed PR after CONFIRMED, by ruling."
- CLI: `predict` and `export-predictions` refuse `--competition` PD / SA / BL1 / FL1 / ELC (any case) before any DB read. They exit 2 and name `export-soccer-expansion-shadow`. The set is imported from `desk_policy.SHADOW_VENUE_COMPS`; there is no second list.
- Desk (`desk_policy.desk_call`): a model row whose competition is in the set is PASS, `pass_kind` `shadow_league`, tag `shadow league`, reason `shadow league: never a call until CONFIRMED`. It has 0 units, no order, no exec block and no value shadow, and is never a parlay leg. The check runs before the started rule, so a started shadow-league row keeps this reason.
- No switch: no row of the frozen golden (`tests/golden/desk_js_v1_1.json.gz`) is in the set, so the golden is byte-unchanged and the battery passes as is.
- Cockpit (repo copy): `passKindTag` renders `shadow_league` as "shadow league", the row is greyed like `started`, and the summary counts it.
- Tests: `tests/test_shadow_league_no_call.py`.
- Not covered by the ruling (reported, unchanged): the web admin predict job and the match-page refresh still call `generate_predictions` without the check. `export-predictions` without `--competition` still lists the leagues' matches (no chain runs it). Any prediction row on them is PASS under (b).

## 2026-10-08 (#355: MLB actionable receipt read: no policy change)
- Ledger only. The architect read the MLB actionable receipt (operator console, run 2026-10-08T1336Z). The Desk keeps pMin 0 for MLB, and the prediction layer's actionable flag stays a label.
- Two findings, neither a policy: #352 (the toss-up tier beat the close in the three buckets with more than one game; the fourth populated bucket, 8 to 15pp, holds one game, a loss: ARCHITECT correction 2026-10-08, addendum 10) and #353 (Desk-reachable volume is about 4% of priced games).
- Follow-up receipt declared now, read-only, to run after Q3: the toss-up row split by calendar month and by pick side, plus Q3's blend split (#354).
- The receipt file is spliced from the operator's laptop/mlb-actionable-receipt branch, not retyped.

## 2026-10-08 (#350: sp_receipts reads every writer's backup shape)
- deploy/hosting/sp_receipts.py: new `backup_sha()` feeds the table's backup-sha column. It accepts the chain receipt's dict `backup` (sp_run.py), the file-name string `backup` of the migrations (sp_deploy.py) and cleanup (remove_allstar_rows.py) receipts, the cleanup's sibling `backup_sha256`, and the backup receipt's top-level `sha256`. A name with no sha shows empty. Any other shape shows empty and does not crash. Fixes the host crash `AttributeError: 'str' object has no attribute 'get'` (ARCHITECT 2026-10-08 addendum 8 item 3).
- tests/test_sp_receipts_backup_shape.py: a mixed receipts.jsonl (chain dict, migrations string, cleanup string+sha, odd list) renders end to end through `main(["--since","24h"])`. It fails on the old code with the host's exact error at line 89.
- Other receipts.jsonl readers checked (sp_cutover.py, cutover_readiness.py, sp_migrate.py, sp_common.py, scripts/h2_dry_run.py): none reads `backup`, so nothing else changed. No writer changes, and no receipt line is rewritten. Read-only tool; no prediction outputs changed.

## 2026-10-08 (#349: review stop rule in CLAUDE.md)
- CLAUDE.md: the REVIEW STOP RULE (ARCHITECT 2026-10-08, addendum 7 item 2), verbatim, under the review rules. Merge-readiness = green CI + every P1 fixed or ruled. P2s get one fix round. After round two, read-only P2s go to ONE follow-up Issue and money-path P2s are listed for the architect. Hard cap of three review rounds. A merge-from-main push needs green CI only. A policy change ships before its tooling.
- Sweep paragraph amended: after the cap, an open thread is answered with the PR's follow-up Issue number, not another fix round.
- Docs only; no code, no outputs changed.

## 2026-10-07 (#346: NCAA / NFL delineation — ARCHITECT, daily-class)
- `sync-odds-football`: the window line names each competition it covers, counted from the games in the window ("NCAA odds: 48 upcoming games · NFL odds: 12 upcoming games in window · paced at 280/min"), instead of "NFL odds: 60 upcoming games" for an NFL+NCAA window. The per-game lines ("no odds yet", "no provider id", "odds fetch") name the competition. The summary reads "Football odds: created=N across G games (NCAA a · NFL b)", from the games actually priced, instead of the hardcoded "(NFL+NCAA)". `sync_odds_nfl` returns `games_by_competition`.
- Export rows: every fixtures row (`export-fixtures`, and the window card through the shared `_fixture_row`) carries `competition` (the Competition code) and `family`: "NCAAF" for college, "NFL" for NFL, the upper-cased sport otherwise. A window-card college row keeps `sport: "nfl"` because sp_run's `FRESHEN_FAMILY` keys on (sport, competition); its `competition` (NCAA) and `family` (NCAAF) name it.
- `window-card`: the games count names each competition ("games 37 (MLB 5 · NCAA 20 · NFL 12)"). `capture-weather-nfl`: skipped games are counted per competition ("skipped=50 (NCAA 48 · NFL 2)").
- Labels only: no probability, policy, gate or grading logic changes.
- Codex on #346: the rate-limit lines (retry, still limited, deferred / recovered) name each competition; the repo Cockpit's window table renders `family` before `sport` ("NCAAF · NCAA"; older files keep the sport); the shadow clause is #344's (unmerged), not this PR's.
- Codex on #346: the odds summary names every competition in the window, priced of in-window ("NCAA 0/48 · NFL 0/12 priced/in window"), so a run that priced nothing still says which competitions it covered.

## 2026-10-07 (#344: NCAA shadow — ARCHITECT, addendum 6 item 1)
- New `export-ncaa-predictions` writes `exports/ncaa_shadow_<stamp>.json`: `ncaa_elo_v1r` (v1, constants untouched) for every FBS game in the next 36h.
  - Each row has `engine: model_shadow`, `competition: NCAA`, `family: NCAAF`, and `gate_verdict` "UNGATED — shadow only" until the registry records a verdict.
  - The fixtures market block sits beside the prediction.
  - It is never a call, never a venue input and never in the ledger.
- It REFUSES (exit 2) until `ncaa-elo-v1r` is declared with its `neutral_site_rule` and the CFBD side table covers 95% or more of the stream in both seasons.
- New `ncaa-shadow-grade` grades the last row before kickoff: results (hit rate, log-loss, Brier, on the CFBD score where labelled) and model-vs-close. It is labelled NOT gate evidence.
- Codex on #344: the declaration must also freeze `constants` = v1's untouched values; files are second-stamped and created exclusively; grading skips (and counts) an artifact row whose teams / kickoff / competition are not the match's; every grade line says NOT gate evidence.
- Not on any chain; spec docs/specs/ncaa-shadow.md (#343).

## 2026-10-07 (#342: sync-pitchers count line — ARCHITECT, daily-class)
- `sync-pitchers`: the per-date line counts this run's upcoming games with a probable over this run's upcoming games, and prints the date-wide count of games with a probable separately: `2/3 upcoming games with probable pitchers (4 date-wide, started games included)`. It used to print the batch size (every game on the date, started ones included) over the upcoming count, for example `4/3` at 21:59Z on 2026-10-07 (#341). This is a log line only; nothing written to the DB changes.

## 2026-10-07 (#340: venue-edge quote age — ARCHITECT, gate-class)
- Ruling (verbatim): "#91 means the age of the QUOTE. A fetch time is not a quote age; where the quote's own time is not known the age is UNKNOWN, and the ratified rule for unknown age is NO REFERENCE. From today the operator places no VENUE order on either machine's files. In code, from the next tag: venue-edge emits no call (PASS, noref, 'book quote age unknown: no reference') and the venue block keeps its numbers for the record. [...] The engine resumes only when a quote time is stored and #91 is applied to it, by ruling." Full text: docs/specs/venue-quote-age.md.
- Desk (`desk_policy`):
  - Every venue row the engine computes is now PASS / noref, reason `book quote age unknown: no reference`, with 0 units and no order.
  - The venue block keeps side, div, book, Kalshi and exec numbers, plus `quote_age_hold` (the engine's would-be verdict).
  - Rows that stop before the computation (no pair, UNL, in-play, #91 capture age, books < 4) keep their own reason.
  - The rule has its own switch, `QUOTE_AGE_RULE`. `base_v11()` turns it off, so the frozen golden is unchanged. `desk_meta.venue_quote_age_rule` records it.
  - The window card is held too. Parlays never had venue legs; a test now pins that.
- Cockpit: held venue rows render PASS · no reference with the file's numbers. The T-60 re-run hint is suppressed on them. Verify: `scripts/cockpit_venue_quote_age_verify.py` (11/11).
- `scripts/odds_payload_probe.py` (read-only): dumps every field of the NHL / NCAA odds response from the sync's own endpoint, the time-like keys, and the paths the adapter drops. From the code, the adapters read only bookmaker / bet / value / odd and stamp the fetch time; the repo holds no payload. Branch (2): no column. The staleness-test proposal (N unchanged captures) goes to a ruling.
- New `venue-calls-receipt` (step 3) and `quote-age-report` (step 4). Both are read-only, and `--out` refuses data/.
- Codex on #340 (five findings, verified and fixed):
  - Probe: an unsuccessful response (non-2xx, a non-JSON body, or a non-empty `errors` field, the adapters' own `_get` checks) is refused with exit 2, its reason and no verdict. A `--from-file` payload that carries errors is refused the same way.
  - Probe: every list element is scanned for key paths and time-like fields. `--max-items` now limits only the samples printed, so a timestamp found only in a late bookmaker / bet / value is reported.
  - Receipt: a re-logged ledger position anchors at its frozen `claim_at`. `upsertCalls()` overwrites the top-level `claim_as_of` / `captured_at` with the newest log, so those are not used. Later re-logs (`reprices`) are reported on the position and never counted as separate calls.
  - Receipt + report: export rows resolve by stable identity, because match_id is machine-local. A local match_id is used only once the DB row's teams and kickoff check out. Mirrored `exports/host/` files, and any mismatch, resolve by exact team names + kickoff ±12h. An ambiguous match is reported as unresolved, never guessed.
  - Report: only rows whose reference session is verified (file fair == capture at 4 dp) enter median / p90 / max. Mismatched and unverifiable rows are counted and listed as excluded, with the reason.
  - Probe: a missing provider key and every `--match-id` preflight failure are refusals too (exit 2, reason stated), not a bare exit 1.
  - Receipt: a MANUAL ledger claim (stamped at the click, never a file's `as_of`) merges onto its position by identity (sport, teams, kickoff, side): the latest file call at or before the click. No such file means it stays its own row and is never guessed onto a later file.
  - Both receipts refuse (exit 2) an `--exports-dir` that is missing, misspelled or a file, never reporting an empty audit. `venue-calls-receipt` refuses a ledger whose calls array has any non-object entry, as `k-track-receipt` does.
  - Report: a row decided at or after its kickoff is excluded by its timestamps, not only by `pass_kind == "started"`. Files older than the started-game rule (2026-10-06) carry no marker, and such a row would otherwise inflate both ages.
  - Probe: a missing, unreadable or truncated `--from-file` is a refusal (exit 2, reason, no verdict), not a traceback.
  - Probe: a transport failure (DNS, TLS, connection, timeout) is a refusal: exit 2, key-redacted reason, no verdict. Report: every excluded row is listed with its reason, never truncated at 50.
  - Report: an NFL snapshot is de-vigged by average-then-normalise (sync-odds-football), while the export's fair is per-book normalise-then-average (`close_1x2`), so the two differ at 4 dp whenever books' overrounds differ. A snapshot that mismatches is now re-derived from the same session's stored odds rows (same source and `captured_at`) with the export's formula before the row is called unverified. Still a mismatch, or no odds rows left for that session: excluded, with that reason.
  - Receipt: two files with the same call identity (teams, kickoff, side, `as_of`) are merged as copies only when their market numbers agree too (fair at 4 dp, capture time, books, book / Kalshi p, div). Otherwise each is listed as its own call, flagged CONFLICT, and never merged.
  - Receipt: an exact-time ledger claim among conflicting file rows attaches only to the row whose book p / Kalshi p / div it carries. If none or several fit, it attaches to none and both rows say LEDGER AMBIGUOUS. Report: same match + `as_of` with a different book fair keeps both rows, flagged as conflicting copies. A desk export with an unparseable `desk_meta.as_of` is refused, never skipped silently. Identity resolution is sport-scoped (NFL / NHL / MLB directly, other codes through their Competition); an unknown sport is unfiltered and says so.
  - A desk export with a non-object `fixtures` / `predictions` entry is refused, never skipped or a traceback. Report: mirrored host exports are listed but never measured, since this DB holds the laptop's captures and not the host's. Captures are compared with `desk_meta.as_of` at the second (its serialized precision), so a capture in the export's own second is the reference and its age floors at 0.
  - Receipt: a VENUE call that only host files hold gets verdict `HOST: NOT MEASURED`, never a MOVED / NEVER MOVED verdict from this DB's captures, and it is totalled separately. `--exports-dir exports/host` is recognised as the mirror itself. A `fixtures` / `predictions` value that is not a list is refused. Probe: an odds response with no bookmaker / bet / value objects is INCONCLUSIVE, never a no-time-field verdict. A camel-case `…Ts` key (`quoteTs`) is time-like; `bets` / `results` are not.
  - Report: when duplicate model rows are merged, a local copy makes the row local in whatever order the copies were found (for example `exports/laptop/` sorting after `host/`), so the row is measured rather than excluded as mirrored.
  - Receipt: a VENUE call whose reference is not the 1X2 consensus (an NCAA `spread_derived` fair) gets `NOT 1X2: NOT MEASURED`, totalled separately. It never gets an anchor or a movement verdict from the unrelated 1X2 sessions.
  - Receipt: a re-logged ledger claim carries the prices frozen at the claim (`claim_model_p`, plus `claim_market_p` where it is the Kalshi price). What the Cockpit did not freeze (div; Kalshi p behind an executable cost) is unknown and named, never the latest reprice. An unreadable export file (`fixtures_*`, `*predictions*`, `desk_parlays_*`, `window_*`) is refused rather than omitted; other broken JSON is only counted.
  - A document carrying `desk_meta` with a missing, null or empty `as_of` (or a non-object `desk_meta`) is refused, the same as an unparseable one. A ledger whose venue claim has a damaged `reprices` array is refused.
  - Receipt: re-logs are compared to the claim at full precision, so a same-second re-log is kept. A ledger-only NFL / NCAA claim has an unknown reference source (the ledger keeps no `fair_source`) and is `NOT 1X2: NOT MEASURED`. A present but unparseable `claim_at` refuses the ledger. A call whose anchor session's fair differs from the call's own gets `ANCHOR MISMATCH: NOT MEASURED`, never a movement verdict from a substitute session.
  - Receipt: only a manual claim (`claim_source` not `auto`) falls back to its position. An auto-claim whose exact export is gone stays its own row. Claim-time Kalshi p is decided by the frozen `claim_exec_cost` alone, so a legacy claim keeps `claim_market_p` after an executable re-log. A row whose `desk` is not an object is refused. Every re-log is listed.
  - Receipt: the claim's divergence is compared at 2 dp, its serialized precision. A VENUE file row with no parseable `market.captured_at` is `NO CAPTURE TIME: NOT MEASURED`, never anchored on a substitute capture. A legacy claim (no `claim_at`) with a damaged `claim_as_of` / `captured_at`, or a claim with no time at all, refuses the ledger. A file fair verifies only with the session's full outcome set.
  - Both receipts open the DB read-only (a `mode=ro` SQLite URI, with no connect hook, no WAL pragma and no commit). A missing DB file is refused, never created. A ledger claim anchors at full precision, since `claim_at` keeps milliseconds. A file call whose anchor's snapshot differs from the file is re-derived from that session's odds rows (the export's formula) before ANCHOR MISMATCH. A `fixtures_*` / `*predictions*` export without its rows key is refused.
  - Read-only open creates no WAL sidecars. With no `-wal` / `-shm` on disk (checkpointed), the DB opens `immutable`; with both present it opens `mode=ro`; with exactly one present it is refused. Files that differ only in `fair_source` are separate calls, never merged copies. Probe: a schema verdict needs `values[]` objects carrying both `value` and `odd`; anything less is INCONCLUSIVE.
  - Probe: the `--match-id` lookup opens the DB the same sidecar-safe way (immutable when checkpointed; refused with exactly one sidecar). A row whose `market` is not an object, or whose `fair_prob` is not an object of numbers, is refused at discovery rather than crashing while rounding.
  - A re-logged venue claim's claim-time Kalshi p is unknown. `snapshotCalls()` freezes the executable cost in `claim_market_p` and never sets `kalshi_exec_cost`, so that value cannot be read as Kalshi p; this supersedes the earlier legacy-claim rule. A file VENUE call with no fair is `NO FILE FAIR: NOT MEASURED`. An anchor verified by odds-row re-derivation keeps `file == anchor snapshot: NO` and prints the basis it was verified by. A malformed `market.selections` or a non-numeric VENUE field is refused at discovery. Probe: a verdict needs one `values[]` object with a non-empty value and an odd > 1.
  - Probe: a quote counts only by the adapter's own rules: the bet name is in `_MARKET_MAP` and the value normalises via `_normalize_selection`, for `--sport`'s adapter, or either adapter from a file. Non-numeric or unhashable `bookmaker_count` / `captured_at`, or non-numeric venue claim prices in the ledger, are refused. `export-predictions`' default names (`<sport>[_<COMP>]_<date>.json`) are required inputs, so an unreadable one refuses.
  - The read-only open is `mode=ro` again and never `immutable`, which supersedes the sidecar rule above. An immutable open skips SQLite's change detection, so a write or checkpoint by the app during a receipt could be missed or read torn. SQLite may create its own `-wal` / `-shm` sidecars for a WAL database, as every reader does; the database content is never written. Same for the probe's `--match-id` lookup. Age report: literal snapshot equality and odds-row re-derivation are counted apart (`file_rederived`), and mirrored rows are left out of the per-sport capture diagnostics. A default-named prediction export (`<sport>[_<COMP>]_<date>.json`) must carry `predictions`.
  - A non-string `market.fair_source` is refused at discovery, never left to raise an unhashable signature error.
  - Report: the reference source and its raw fair are part of copy identity, so two different `spread_derived` references for one game are both kept and flagged, never collapsed. Discovery refuses a non-string identity field (desk `engine` / `call` / `side` / `reference` / `pass_kind`, or a row's teams / kickoff / competition), never a traceback while hashing.
  - A default prediction export name with an underscore competition code (`soccer_UEFA_EURO_<date>.json`, `WCQ_EU`, `CNL_Q`) is a required input too; a `_results_` export still is not. A venue ledger claim with a non-string `sport` / `home` / `away` / `kickoff` / `pick` / `claim_source` refuses the ledger.
  - A desk row whose `match_id` is not an integer or null is refused at discovery (it is passed to the DB lookup). Probe: `quoteTS` / `oddsTS` are time-like; a scalar `response` / `bookmakers` / `bets` / `values` container holds no quotes (INCONCLUSIVE), never a traceback.
  - Probe: both schema verdicts need a usable quote. A time-like field in a response with no usable quote (a fixture date) is listed as unattributable, and the verdict is INCONCLUSIVE.
  - Desk exports under any `--out` name: an unreadable file whose text still carries desk blocks is refused, and a desk document with no `fixtures` / `predictions` / `tickets` is refused. An NFL / NCAA file row with no `market.fair_source` has an unknown reference: `NOT 1X2: NOT MEASURED` in the receipt, no 1X2 fair in the age report. Probe: a non-string bet name is no market, never a traceback.
- Evidence (ARCHITECT, addendum 5 II): LAD@ATL's nine-book MLB consensus (ATL 0.4302) was unchanged from the host's 14:05Z capture to the laptop's 21:59:58Z capture, two seconds before first pitch. Kalshi was also unchanged (0.42 / 0.43). Recorded in the spec as evidence for step (4); no code or policy change.
- Evidence (ARCHITECT, addendum 6 item 3): SJ@STL. The same five-book consensus (SJ 0.5265) at 14:56Z, 16:00Z and 22:09Z while Kalshi's SJ ask went 0.46 to 0.42. The laptop Desk at 22:09:27Z still printed VENUE 0.25u with an order, div 10.7pp, `stale_book_zone` true. `venue-calls-receipt` now prints each call's `stale_book_zone` as written and totals TRUE / false / unknown (ledger-only or not on file). A non-boolean value is refused at discovery.
  - Cockpit policy card: the VENUE-EDGE line states the hold (book quote age unknown: no reference; place no venue order) and gives the frozen rule only as what applies once the hold lifts. Verify 12/12.
  - A desk document with missing or non-string sport metadata (and rows without their own competition) is refused, never read as an out-of-scope sport. A generated export name whose JSON root is not an object is refused. A ledger re-log earlier than the frozen `claim_at` refuses the ledger. Probe `--match-id`: the match must be the asked league (NFL and NCAA share the provider id key), and its `external_ids` must be a JSON object.
  - Copies of one VENUE call that disagree on `stale_book_zone` keep both readings (CONFLICTING across copies, totalled apart), never whichever was read first. A legacy claim's logs earlier than its fallback claim time are listed apart, never as re-logs after the claim. Probe: `asOf` / `as_of` keys are time-like.
  - Report percentiles are nearest-rank with ties half-up (Python's ties-to-even `round()` alternated ranks). A ledger claim's divergence is compared with the Cockpit's `toFixed(2)` rule (`desk_policy.js_fixed`), so 6.125 matches its 6.13. 1X2 model-reference copies dedupe at 4 dp; the raw fair distinguishes spread references only.
  - A row the Desk annotates (a scheduled or status-less fixtures row; a predictions row with a probability) without its `desk` object refuses the export, never read as a non-call. Probe: `--from-file`, `--game` and `--match-id` are mutually exclusive (a conflict is refused), and a `--match-id`'s provider id must be a string or integer.
  - Damaged desk exports are refused however they broke: an unreadable file whose text carries a rows key (`fixtures` / `predictions`, so a prefix truncation before the first desk block is caught), Desk rows in a document with no `desk_meta`, and a Desk-annotated row whose `desk` lacks `engine` / `call`. Probe: a direct `--game` payload is checked against the league it names (`response[].league.id`: NHL 57, NCAA 2, from the adapters); another league is refused, and no league id prints LEAGUE UNVERIFIED on the verdict.
  - Every unreadable JSON under the exports dir refuses both receipts (an export may carry any `--out` name and break before any marker); this supersedes the name / marker sniffs above. A ledger-only claim is measured only when its frozen book p equals the anchor's side probability (else ANCHOR MISMATCH; no book p: LEDGER UNVERIFIED, both NOT MEASURED). Probe: `--from-file` with `--sport` is league-checked like a fetch, and a scalar `response` names no league.
  - Any export that parses as null, a scalar or `[]` is refused whatever its name (a non-empty list is another file kind). Probe: a `--match-id` fetch whose payload names another league is refused too.
  - A predictions row whose `prediction` is not an object (or null) refuses the export. A fixture VENUE call takes its row's own `competition` before the document's sport metadata.
  - A scalar `fixtures` / `predictions` container is refused before any row is read (no traceback). A document whose only sport source is an unknown `sport` (not soccer / nfl / mlb / nhl / ncaa / unl / intl) is refused. Probe: a numeric-string league id is read as that league; a malformed league id refuses.
  - A desk block's `engine` / `call` / `reference` must be desk_policy's own vocabulary (model_edge PLAY / PASS / LADDER; venue_edge VENUE / PASS; books / kalshi_only / null); a corrupted value refuses. A ledger claim whose frozen prices contradict its only candidate file call attaches to none, and the file row says so. Cockpit: a held row's kickoff cell gives no "re-run by" instruction (verify 13/13).
  - A desk block's `reference` is checked against its engine and call: a model PLAY / LADDER must carry books / kalshi_only, a VENUE block none. `--out` refuses a `.json` path under `--exports-dir` (discovery would refuse the text receipt as a damaged export). Probe: a quote-bearing response item with no league id leaves the payload LEAGUE UNVERIFIED.
  - The model-reference report resolves a row's sport with the same precedence discovery accepts (row competition, then the document's `competition_code` / `competition` / `sport`), so a PL document named only by `competition` keeps its rows. Probe: a price that is not a finite decimal above 1 (0, 1, NaN, Infinity) is no usable quote.
  - NaN / Infinity (which `json.load` accepts) are not receipt numbers. A ledger call whose `engine` is not model_edge / venue_edge refuses. A competition that contradicts its document's single-league sport (nfl + NFA) refuses. A generated-name export emptied to an object with no metadata or rows refuses. `--out` may not be the `--ledger` file.
  - An empty object `{}` under any name refuses (as null / scalar / `[]` already did). `--out` refuses the configured SQLite database file and its -wal / -shm / -journal sidecars, wherever DATABASE_URL points.
  - Discovery reads `.JSON` (any case) and an extension-less file that parses as a desk document (`--out exports/audit`); every other file is counted on the sources line as "other file(s) not read".
  - Discovery reads a desk document under any file name (`--out exports/audit.txt`); rows carrying even an empty `desk: {}` without `desk_meta` refuse; a subdirectory that cannot be scanned refuses. A ledger venue claim with an unparseable kickoff refuses. `--out` refuses a `.json` name under the exports dir in any case.
  - quote-age-report: an NFL predictions row's `market.selections` (the export's 1X2 close, unlabelled) keeps its fair; only the unlabelled `fair_prob` shape is treated as possibly spread-derived (P1: every books-backed NFL row was unmeasured). A file captured_at after the call's as_of leaves the call unmeasured. A VENUE call whose book_p is not its side's fair refuses; a row competition contradicting the document's competition_code refuses (soccer included). `--out` never names a discovered export, whatever its suffix.
  - A VENUE row's book_p / side fair is checked numeric before it is compared (refusal, never a traceback). A file of any name that begins as a JSON object but does not parse refuses as a damaged export.
  - A ledger venue claim whose `claim_source` is not "auto" or absent refuses. A document carrying both `fixtures` and `predictions` lists refuses. Probe: `--out` refuses the configured database file and its sidecars.
  - A timestamp whose offset overflows on UTC conversion is invalid (refusal, never a traceback); a VENUE side that is not a string refuses before any lookup. Probe: `--out` never replaces an existing desk export (generated name, a desk document, or a mirrored host copy).
  - `--out` naming a directory, or a path under an existing file, refuses before the scan (never an IsADirectoryError).
  - Probe: `--out` refuses a generated desk export name (or the host mirror) whether or not the file exists, and a path under an existing file.
  - Any row carrying a `desk` key (whatever its value) without `desk_meta` refuses the document.
  - Any file whose text parses as JSON, whatever its suffix, goes through the same damage checks as a `.json` export (an emptied `--out exports/audit.txt` refuses). A desk block whose engine is foreign to its row family (model_edge on a fixtures row, venue_edge on a predictions row) refuses.
  - A venue_edge block whose call contradicts its own `venue.eligible` (PASS + eligible, VENUE + not) refuses. A file that cannot be opened refuses; undecodable bytes that begin as a JSON object refuse, other binary files are counted. Probe: an empty payload `{}` is refused and never written.
  - `--out` (receipts and probe) compares file identity, not only the path: a hard link to the database, its sidecars, the `--ledger` file or a discovered export refuses.

## 2026-10-07 (#337: record — the v1.3.0 release gate (PASS) and the host's 2026-10-07 deploy / migration / intl history load)
- Ledger only: the architect's v1.3.0 RELEASE GATE ruling (compare_exports DIVERGENT, every line an allowed class, GATE: PASS, tag at the ledger-compile commit 0023368) and the host's RECORD of 2026-10-07 (deploy at 15:45Z, `migrate_prediction_history` via `sp_deploy --run-migrations`, the 2018+ international history loaded, `intl-daily` green on v1.3.0), both verbatim. The release Issue (docs/RELEASES.md step 4) follows.

## 2026-10-07 (#335: daily-class — NCAA midweek timer, mirror settings from .env, missing key refused, nhl_probe.jsonl ignored)
- `sp-ncaa-market.timer` gains Tue + Wed 16:00 UTC, so midweek FBS games get a host fixtures file. A changed timer is installed on the host by hand after the tag's deploy (`docs/specs/hosting-h1.md`).
- `sp_common.setting` reads the environment, then host.env, then the checkout's `.env` (the environment wins). `exports_mirror.py` reads REMOTE / KEY / ROLE / DIR / AUTHOR through it, so the laptop's `.env` carries them.
- `exports_mirror.py push` REFUSES (exit 2) an SSH remote whose key file does not exist, naming the path, before any git step. It never pushes keyless. `docs/specs/exports-mirror.md` corrects the laptop key name to the default `~/.ssh/sp_exports_deploy_key`.
- `.gitignore`: `/nhl_probe.jsonl` (the NHL probe's `--out` in the repo root).

## 2026-10-07 (#333: NCAA CFBD label lane — ARCHITECT, data lane)
- CollegeFootballData (CFBD) becomes the NCAA label source of record (ruling 2026-10-07, item 6). No model change; GATE #79 unchanged and still SUSPENDED-PENDING-DATA.
- New side table `ncaa_cfbd_labels` keyed by our match id: CFBD game id, orientation (same / swapped), neutral flag, both scores in OUR orientation, season, provenance (source, payload file, fetched_at, correction reason). Created by `migrate_ncaa_cfbd_labels.py` (run after the `.backup`). The matches table is never written.
- New `ncaa-cfbd-labels --year 2025 --year 2026 [--from-file] [--dry-run] [--save-dir] [--division] [--unmatched-names]` (`src/ingestion/ncaa_cfbd.py`):
  - fetches CFBD `/games` (`CFBD_API_KEY` from `.env`, never printed) and saves the raw payload under `exports/cfbd/` (gitignored);
  - joins each completed both-FBS game to our NCAA match (exact names before substring, either orientation; ambiguity refused);
  - upserts the side table and prints a per-season receipt, listing every score-corrected row with its reason and every refusal.
- Pinned alias map `src/ingestion/ncaa_cfbd_aliases.json`, shipped EMPTY. An alias never overrides an exact match; one whose target names 0 or more than 1 of our teams is refused. The operator fills it in a reviewed PR from `--unmatched-names`.
- The NCAA stream (`ncaa_backtest.load_games`) reads orientation, scores and neutral from the side table where a row exists, else the matches row. `ncaa-backtest` prints the uncovered share per season. Neutral is carried on the Game as data only.
- New read-only `ncaa-cfbd-coverage`: per season, stream games, covered, share, swapped, neutral, score-corrected, the non-neutral home rate, and whether the >= 95% condition holds (a computed fact; the gate's status does not change).
- The CFBD fetch / field discovery moved from `scripts/ncaa_source_probe.py` into `src/ingestion/ncaa_cfbd.py`; the probe imports them and keeps its own compare.
- `config.Settings.cfbd_api_key`; `CFBD_API_KEY` added to `.env.example` and to the hosting `SECRET_ENV` redaction list.
- Spec: `docs/specs/ncaa-cfbd-labels.md`. Tests: `tests/test_ncaa_cfbd_labels.py` (21, synthetic records only).
- Codex on #333 (fix 1): the ingest's guard now requires the migration marker `ncaa_cfbd_labels_migration` (written only by `migrate_ncaa_cfbd_labels.py`, unmapped in the ORM), not just the table, since any `init_db()` creates the table. A `--dry-run` still needs neither.
- Codex on #333 (fix 2): `--division ''` (all classifications) now omits the CFBD `classification` query parameter instead of sending `classification=fbs`; the probe shares `fetch` and gets the same fix.
- Codex on #333 (fix 3): the raw-payload save directory (`--save-dir`, and the probe's `--save`) must be under `exports/` when it is inside the repository; any other in-repo path is refused (real paths, symlinks resolved), `data/` stays refused, paths outside the repository are accepted. Only `data/` was refused before, so `--save-dir src/cfbd` would have written a licensed payload to a tracked path.
- Codex on #333 (fix 4): `drop_db()` (`init-db --force`) now also drops the unmapped marker `ncaa_cfbd_labels_migration`; `drop_all()` left it behind, so after a forced reset the guard read "migrated" for the empty side table `init_db()` recreated. The ingest refuses again until the migration is re-run.

## 2026-10-07 (#331: intl-elo-v2 confirmation cohort of record — the 2026-10-03 freeze spliced; ARCHITECT addendum 3 A)
- Spliced `laptop/intl-cohort-freeze` bf556b4 (cherry-picked, operator authorship kept): `docs/registry/experiments.json` intl-elo-v2 `confirmation_cohort` (n 60, sha256 `94416b7c…`, frozen_at 2026-10-03T12:01:42Z, eligible_stored 120, finished 7 / scheduled 53, UNL 41 / CNL 19, last kickoff 2026-11-11T21:00Z) and `docs/registry/ids/intl-elo-v2.cohort.txt`. Sidecar verified: 60 distinct ids, `registry._ids_sha` == the recorded sha; `registry.frozen_cohort` reads it back.
- The 2026-10-07 freeze (`laptop/intl-elo-v2-cohort` e697533, sha256 `419872ed…`) is VOID, kept on its branch as a record, never merged; #318 closed unmerged. It differs by one fixture: 48559 in place of 41643.
- The hourly comment sweep (a scheduled Claude Code routine, NOT repository code: nothing in this repo runs or enforces it) now reports any `laptop/*` registry write that is not on main after a day. A repo-side guard for `--freeze-cohort` is proposed for a ruling (#329).
- Ruling verbatim: "The intl-elo-v2 confirmation cohort was frozen ON TIME by the operator on 2026-10-03T12:01:42Z (branch laptop/intl-cohort-freeze, commit bf556b4: 60 fixtures, sha256 94416b7c…, 7 finished / 53 scheduled at freeze, 120 eligible stored, last kickoff 2026-11-11T21:00Z) and never spliced. The architect, not having read the laptop branches, ordered a second freeze on 2026-10-07 (laptop/intl-elo-v2-cohort, e697533, sha256 419872ed…), which differs in one fixture: 48559 (kickoff 2026-11-09T21:00Z, first stored by the 2026-10-07 sync) in place of 41643. A cohort is frozen once and never changes; a fixture listed after the freeze does not enter it. THE 2026-10-03 FREEZE IS THE COHORT OF RECORD. The 2026-10-07 freeze is VOID: a duplicate made in error, kept on its branch as a record, never merged. The addendum-1 text ('executed on 2026-10-07, after 59 of the 60 had been played') is withdrawn: it was wrong. The 59 labelled fixtures are common to both lists, so the read at 2026-10-07T14:17Z stands for the cohort of record: 59/60, log-loss 0.8400, naive 1.0364, reference 1.0264, bar 1.0986. Not a verdict. The 60th fixture is 41643, kickoff 2026-11-11T21:00Z; the record step is the operator's on 2026-11-12. Finding for the ledger: a registry write that lives only on an unmerged laptop branch is invisible to the next freeze, which is how a second one was accepted."

## 2026-10-07 (#328: MLB big-edge quarantine — ARCHITECT, gate-class)
- Desk (`src/walters/desk_policy.py`): an MLB row whose edge against its reference is above 8pp is QUARANTINED: PASS, units 0, `shadow_units` at the size it would have staked, reason naming the ruling, tag `quarantine > 8pp (shadow)`, no order. The edge is the Desk's own, so the book close and the kalshi-only mid quarantine alike; the postseason and kalshi-only multipliers size the shadow as they would have sized units. Exactly 8.00pp plays (float-noise tolerance). The MLB 15pp caution tier is superseded. `base_v11()` keeps the old behaviour for the frozen goldens; `desk_meta.mlb_quarantine_above_pp` records the threshold in force.
- Cockpit (`tools/cockpit.html`): a quarantine shadow is now the FILE's Desk call (PASS + shadow units + a `quarantine … (shadow)` tag), not only an NFL row with `quarantine: true`; the MLB legend line carries the rule. Without this the Cockpit would have shown MLB quarantines as plain PASSes and logged nothing. New `scripts/cockpit_mlb_quarantine_verify.py` (4/4).
- Ruling verbatim: "MLB BIG-EDGE QUARANTINE. Receipt: operator console 2026-10-07, calibration-market --sport mlb (since 2026-06-14; 1,397 scored, 1,364 with a close; edge = model top-pick probability minus the close's fair probability for the same side). Model above the close by more than 8pp: n=34, model 55.3%, won 20.6% (7 of 34). Above by 2 to 8pp (the >2 row less the >8 row): n=228, model 53.8%, won 55.3% (126). Within 2pp: n=609, 54.7% -> 55.8%. Below by more than 2pp: n=493, 55.8% -> 64.1%. The moderate band holds up; the big-edge band loses to the market's own price. RULED, effective with the 2026-10-07 slate: an MLB row whose edge against its reference is above 8pp is QUARANTINED: never a straight play, logged as a quarantine shadow at the size it would have staked (the NFL contract, at 8pp for MLB). The MLB 15pp caution tier is superseded. The 4pp floor and the rest of v1.1 stand. First review with the tier x edge receipt (item 2). Until the code lands the operator applies it by hand from the closing-run summary."
- Codex on #328: the quarantine shadow records the Desk's own reference (a kalshi-only mid, `reference: kalshi_only`), and the Card, the audit text and the ledger's `quarantine` flag read the file's Desk call (`rowQuar`), so an MLB quarantine shows its chip, border and reason. The verify is now 7/7.
- Codex on #328, round 2 (fixed):
  - (P1) `desk-rescore` held the quarantine constant: its "before" side now runs under `addendum_off()` (#87 + started off, MLB quarantine as it is) instead of `base_v11()`, so a pre-rule MLB >8pp PLAY is no longer counted "halved by #87"; a published PLAY the current Desk quarantines gets its own verdict `quarantined` and its own console/receipt line. `base_v11()` (the golden battery's policy) is unchanged.
  - (P1) Window card: `canonical_models()` ORs the row's Desk quarantine shadow (PASS, `shadow_units` > 0, a `quarantine … (shadow)` tag: the Cockpit's fileQuar) into `quarantine`, so an MLB >8pp row is flagged on the Next-24h card, in `receipts.quarantined` and in the pager's quarantine flips.
  - (P2) Cockpit Ask prompt: the house doctrine states the quarantine per sport (NFL/INTL divergence >= 15pp; MLB edge vs its reference > 8pp, ARCHITECT 2026-10-07; the MLB 15pp caution tier superseded), not "quarantine>=15pp".
  - (P3) Cockpit Card reasoning: the file's Desk reason is pushed raw (the final `esc(why.join(...))` escapes it once), so "> 8pp" no longer shows as "&gt;". The MLB-quarantine verify is now 9/9.

## 2026-10-07 (#326: soccer-expansion-v1 — ARCHITECT, gate-class declaration, NO run)
- soccer-expansion-v1 is DECLARED in the registry with its executable confirmation plan (#322). The spec is `docs/specs/soccer-expansion-v1.md` (the ruling verbatim, the operational definitions, findings F1–F6).
- `soccer-expansion-gate [--preflight]`:
  - the one run, per league, on PD/SA/BL1/FL1/ELC, test seasons 2024/25 + 2025/26;
  - refused unless declared and unrun, while F1–F6 are open, and before any scoring if a 2023/24 naive is missing or a test season would score nothing;
  - `--preflight` scores nothing.
- `soccer-backtest` refuses these leagues while the experiment is unrun.
- `export-soccer-expansion-shadow` (model_shadow, no Desk call, no prediction row) and `soccer-expansion-shadow-grade` (read-only).
- `soccer-prematch` / `soccer-morning-after` and the laptop routine add the five leagues' 2026/27 `sync-matches` / `sync-odds`, data only. Kalshi series PINNED (ARCHITECT 2026-10-07, addendum 2): PD KXLALIGAGAME, SA KXSERIEAGAME, BL1 KXBUNDESLIGAGAME, FL1 KXLIGUE1GAME, ELC KXEFLCHAMPIONSHIPGAME in `SOCCER_GAME_SERIES`; EL1 / EFL / CZE recorded, not wired (`SOCCER_SERIES_RESERVED`). Each league's `sync-kalshi-soccer` runs on `soccer-prematch` and the laptop routine as CAPTURE ONLY, not in the window chain; "A pinned series never makes a league live."
- Codex on #326:
  - the generic `backtest` walk (`src/walters/backtest.py run_backtest`) is sealed on these leagues too (`backtest --competition BL1` refuses, exit 2).
  - the seal is enforced in `run_soccer_backtest` (every path, the sweeps included);
  - the pre-scoring check refuses a test season the walk would score nothing in: the walk's own predicate (>= min_prior prior rows and both teams among them), from fixture order and team ids, no score read;
  - F5 (fixtures sharing a kickoff: the walk updates after each row) is an open finding for a ruling; the run refuses until it is ruled;
  - the run reserves the gate before its first read (an exclusive `docs/registry/soccer-expansion-v1.started.json`); an interrupted, failed or concurrent attempt is refused until ruled;
  - the run record keeps each league's calibration band rows;
  - F6 (a league with no gated calibration band passes the bands criterion vacuously) is an open finding for a ruling.
- Rulings on F1–F5 (ARCHITECT 2026-10-07, addendum 3, item B; quoted verbatim in spec section 7a). F6 is not ruled, so the run still refuses:
  - F1: a league without a complete stored 2023/24 regular season (a full double round-robin, every row finished with both scores) is dropped before the run, never read, and named with its reason (`dropped_before_run` in the verdict and the record). All five dropped refuses;
  - F2: no change; per league-season from a cold start, min_prior 40, the two test seasons pooled per league;
  - F3: only regular-season rounds are scored and walked, in the test seasons and the 2023/24 baseline. `placement()` maps `Match.stage` (api-football `league.round`, verbatim) to regular / playoff / unplaced. `--preflight` prints every label with its count and placement; an unplaced label refuses the run;
  - F4: TIES REJECT. `crit_ll` is now `ll_model < ll_naive − 0.010`, unrounded, no tolerance;
  - F5: `run_soccer_backtest` gains two opt-in arguments, both default off so every existing command reproduces its numbers: `stage_filter` and `batch_same_kickoff` (same-kickoff fixtures predicted from one pre-state). The gate passes both; `scoreable_count` mirrors the batched predicate.
  - the Desk's venue engine never calls PD / SA / BL1 / FL1 / ELC (`desk_policy.SHADOW_VENUE_COMPS`, pinned to the leagues): their Kalshi capture reaches the 24h window card, which spans every competition, so without this a gap there could print a VENUE line.
  - F6 ruled (2026-10-08): a league with no calibration band at >= 100 observations is DROPPED, "no gated band"; it never passes on log-loss alone (intl / NHL / NCAA gates unchanged). The registry operator correction (R1) has no machine-readable field to land in: it stays open and the run still refuses until directed.
  - R1 ruled (2026-10-08, addendum 8): no new field or schema. The entry gains `ratified` beside the byte-identical `gate` (the F1-F6 reading of record; F4: the gate's <= is read as strict). The addendum 7 operator sentence is withdrawn and kept quoted in spec 7b. `OPEN_FINDINGS` is empty.

## 2026-10-07 (#325: intl-golive-dark — ARCHITECT, gate-class, built DARK)
- Desk: `POLICY["INTL"]` = the SOCCER block with qNever (INTL DESK POLICY v0, #323). Nothing changes for anyone: only a production intl file reaches it.
  - Half units until 30 INTL calls are graded (`intl_graded` in the ledger summary; absent = 0).
  - UNL only: CNL rows are PASS `no_series`.
  - An unknown venue on a home-abroad side is PASS `venue_unknown`. The list stays empty until it is ruled by name.
  - The v1.1 goldens are unchanged.
- `export-intl-predictions`: the shadow's intl-elo-v2 rows re-shaped for the Desk.
  - Each row carries `market_divergence_pp` / `quarantine` (the NFL contract), `venue_flag` and `competition`.
  - It REFUSES and writes nothing until `registry.production_allowed("intl-elo-v2")`.
  - `export-unl-predictions` is unchanged.
- `intl-home-abroad-receipt` (read-only, `--out` to docs/receipts/):
  - per national team, listed-home games since 2022 with a known neutral_v3 and the share abroad;
  - venue-id coverage per current competition-season.
- `unl-shadow-grade` adds per row the result, the hit, model and book-close log-loss, the same-priced-games aggregate, and the |model − close| buckets (<4, 4-10, 10-15, >=15pp). Not to be run until this entry's BACKLOG fragment is merged.
- Codex on #325:
  - the Cockpit logs INTL quarantine shadows and emits `intl_graded` in the ledger summary;
  - `export-intl-predictions --desk`;
  - full team names in the home-abroad receipt;
  - `--hours 0` exports an empty window (only an omitted window falls back to the default);
  - new `scripts/cockpit_intl_verify.py`.
  - `export-intl-predictions` refuses and writes nothing when `prediction_history` is missing, or when the rows appended differ from the fixtures in the file (rolled back): the history is the only grading record of these calls.
  - KXUEFANLGAME fills now match INTL calls as well as UNL ones, in the Cockpit and in `ledger_fills.py` alike (they fell to the FUN book).
  - The 90-minute grading path was escalated; it is ruled in addendum 3, item C (below).
- ARCHITECT 2026-10-07 addendum 3, item C (verbatim): "INTL calls are graded on the 90-MINUTE result, never on a score that includes extra time or penalties. The results path for an INTL call reads the stored 90-minute score; where a game went beyond 90 minutes and no 90-minute score is stored, the call is left ungraded and listed, never graded on the later score. Before this merges, read the settlement rule from the KXUEFANLGAME payload itself (rules_primary) and quote it in the PR: if Kalshi settles on anything other than the result at the end of regulation, stop and return to the architect. Confirmed from your list: the gap is measured on the top-pick side; 'current season' is one with a scheduled or live fixture. Amended: the production INTL export writes no predictions row, but it DOES append to prediction_history on every export (model version, three probabilities, computed_at), as the K-track rule requires of every model sport."
  - New `export-intl-results`: production INTL calls graded on the 90-minute result only. A game past 90 minutes (AET / PEN) with no stored 90-minute score is listed as ungraded, with its reason.
  - The Cockpit grades an INTL call only from that file, never from a fixtures file's extra-time score.
  - `export-intl-predictions` appends to `prediction_history` on every export, through the shared append helper. It still writes no `predictions` row.
  - The KXUEFANLGAME settlement rule (rules_primary), read by the operator on the laptop on 2026-10-08 (five markets, two UNL games of 2026-10-06), settles "after 90 minutes plus stoppage time (does not include extra time or penalties)": the result at the end of regulation. Ruling C is met (ARCHITECT 2026-10-08, addendum 8, 2a). Verbatim in the PR body.
  - the production file is written to a temporary path inside the history transaction and published by an atomic rename only after the commit; a failed commit leaves no file and never overwrites an earlier one.
  - the temporary export file is removed by the helper itself if the history transaction fails on commit (the test now fails that transaction, not build()'s reads); the home-abroad receipt ends each team name with " | " so a long name never runs into the country.
  - Publication is now part of the history transaction. The JSON goes to a unique temporary file (mkstemp), and is published by `os.link` as the transaction's last step, never overwriting: an export for the same minute already on disk refuses. If the commit fails after publication, the published file is removed, so no prediction_history row outlives a failed publication. The Desk annotation uses the export's own `now` (`desk_meta.as_of` == `exported_at`); `maybe_annotate` takes an optional `now`, and the wall clock stays the default.
  - Ruled (2026-10-08, addendum 8, 2b): `export-intl-results` is the MODEL's record. It grades every exported production prediction of intl_elo_v2; a Desk PASS is a prediction without a bet, not a missing prediction. The file carries one header line (`record_scope`), every row names its competition, and history rows store no Desk call. The no-window `window.kind` is now `all_production_predictions`.

## 2026-10-07 (#324: mlb-actionable-receipt — ARCHITECT, read-only receipt)
- New read-only command `mlb-actionable-receipt` (#321). It reads graded MLB predictions that have a book close, season to date, with the postseason split out.
  - Rows: the prediction layer's tier (`classify_tier`) × the edge vs the close (<0, 0-4, 4-8, 8-15, >=15pp). ARCHITECT 2026-10-07 (addendum 3 D), verbatim: "Negative edges get their own bucket: <0, 0-4, 4-8, 8-15, >=15. Kalshi-only closes stay excluded and are counted on the receipt. Nothing else changes." This receipt is the review instrument for the MLB big-edge quarantine (#327).
  - Columns: n, mean model p, mean close fair p, hit rate, hit − close (pp) with a pinned-seed bootstrap 95% CI, and flat-stake ROI at the close fair price.
  - The header says the edge is against the CLOSE, a proxy for the Desk's T-60 reference.
  - Writes `docs/receipts/` via `--out`.
- No policy change.

## 2026-10-07 (#320: ncaa-tomorrow-kalshi-label — ARCHITECT, daily-class)
- `ncaa-market` chain: adds a single-day `sync-matches` for {tomorrow} after {yesterday} and {today}. Kickoffs at 8pm ET or later fall on the next UTC date (#319).
- Kalshi syncs: the discovery line names the series actually fetched (`KXNHLGAME`, `KXNCAAFGAME`, …) instead of "MLB" for every sport.

## 2026-10-06 (#316: evening-rulings-310 — ARCHITECT, ledger only)
- Records the 2026-10-06 evening rulings verbatim:
  - #310 merges at 99faed0 (follow-up ruling, amending e1a2146);
  - the requirements-install lane closes at that merge (later threads get the closed-lane reply unless they reproduce on the production layout);
  - staged virtualenv declined (#312);
  - #309 and #311 approved;
  - the follow-up approving #314 (with the architect's receipts), #315 and #316.
- No code change.

## 2026-10-06 (#315: mlb-pregame-null-scores — ARCHITECT, daily-class)
- MLB adapter (`src/adapters/mlb_stats_api.py`): when statsapi's coded state is S, P or PW, both scores are null.
  - statsapi sends a pre-game 0-0, which is not a score (law 4).
  - Live and final scores pass through unchanged.
- Test: `tests/test_mlb_pregame_scores.py`.

## 2026-10-06 (#314: desk-started-pass — ARCHITECT, gate-class)
- Desk: a model-sport row whose kickoff is at or before desk `as_of` is now PASS, units 0, `pass_kind` "started", reason "started - never a new call" (#313).
  - It carries no order, no value shadow and no exec block, and it is never a parlay leg.
  - An unknown kickoff is unchanged.
  - The rule has its own switch (`desk_policy.STARTED_RULE`). `base_v11()` turns it off, so the frozen golden holds (0 mismatches).
  - `desk_meta.started_rule` records the switch state.
- Cockpit: a started PASS is tagged "started", greyed like "no reference", and counted in the summary's pass split.
- Tests: `tests/test_desk_started_rule.py` (6). `scripts/cockpit_pass_class_verify.py` gains 3 started checks (19/19).

## 2026-10-06 (#311: kalshi-ed25519 — ARCHITECT)
- `scripts/kalshi_trade_api_probe.py` signs with Ed25519 keys as well as RSA, chosen by key type. Ed25519 signs `timestamp_ms + METHOD + path` directly; RSA stays RSA-PSS.
  - The key file may be PEM or a bare base64 PKCS#8 body (`MC4CAQAwBQYD…`).
  - Other key types are refused, and key material is never echoed.
  - The AUTH receipt names `key_type`.
  - Still read-only (GET only).

## 2026-10-06 (#310: deploy-pip-install — ARCHITECT)
- `sp_deploy` runs `venv/bin/pip install -r requirements.txt` when `requirements.txt` changed in the deploy range. It uses the target tag's file, runs before the checkout, and is printed and receipted (`deploy_requirements`). A failed install refuses the deploy, and the host stays on its release.
- Review fixes (Codex on #310): the install also runs when this host has no successful install receipt for the target's file (bootstrap). It runs in a temporary worktree of the target, so relative includes resolve. A target without `requirements.txt` installs nothing and says so. A failed install warns that the venv may be partially updated.
- Review fixes, round 2 (Codex on #310): an included-file change alone triggers the install. The install record (`requirements.installed`) survives receipt-log rotation. Worktree output is attached to a receipt only when the worktree failed.
- Review fixes, round 3 (Codex on #310): continued lines are joined before includes are parsed. Editable (`-e`) requirements refuse the deploy, because they would point into a deleted temporary tree. The install record names its destination venv or interpreter, so a recreated venv reinstalls.
- Review fixes, round 4 (Codex on #310): continuations concatenate as pip does. The install record lives inside the venv. Symlinked includes are followed. Local-path requirements are refused like editables.
- Review fixes, round 5 (Codex on #310): symlink blobs are not scanned as directives. Bare relative paths, archives and local `--find-links` count as local sources and are refused.
- Review fixes, round 6 (Codex on #310): an allowlist replaces the parsing heuristics. Only plain requirements files auto-install; anything else refuses with the reason and is installed by hand. Checkout blockers are preflighted before installing. A pip launcher that cannot run is a receipted failure.
- Review fixes, round 7 (Codex on #310): `--requirements-installed-by-hand` acknowledges a by-hand install, so a refused release can deploy. The preflight sees renamed destinations and ancestor collisions. A failed install-record write is a receipted refusal. The venv's Python version is part of the install identity.
- Review fixes, round 8 (Codex on #310): by-hand acknowledgements are per release (commit-bound). The dry run honours the flag. A tracked directory replaced by a file is not a blocker. A non-UTF-8 requirements file is a receipted refusal.
- Review fixes, round 9 (Codex on #310): an untracked file inside a tracked directory the target replaces blocks the checkout. Without a repo venv, the install record lives inside the running virtualenv.
- Review fixes, round 10 (Codex on #310): symlinked-directory children; a venv without pip installs via its own python; a failed pip run drops the record; system-site-packages is in the identity; a TMPDIR failure is receipted; per-requirement options are refused; a matching record satisfies a retry.
- Review fixes, round 11 (Codex on #310): empty untracked directories don't block. The by-hand dry run keeps the migration warnings. pip inputs set in the environment refuse auto-install. A failed record write drops the old record.

## 2026-10-06 (#309: desk-rescore-receipts — ARCHITECT rulings recorded)
- `desk-rescore` writes its receipt into `docs/receipts/` (default `desk-rescore-<UTC stamp>.md`; `--out` to name it). It never writes under `data/` and never overwrites: the file is created exclusively.
- Recorded rulings:
  - An edited copy of a migration is a new migration.
  - The migration-plan lane is closed (#305 at 00eac85).
  - The 10-06 K-track receipt stays as partial-window evidence. A FINAL receipt is re-run after 10-08 and committed beside it.

## 2026-10-06 (#307: unl-exploratory-17 — #286 ruling 1 recorded)
- `unl_ladders.EXPLORATORY_MATCH_IDS` pins the 17 exploratory UNL games by match id (31887, 31888, 31890–31904), as ruled. `unl-ladder-receipt --skew-test` no longer refuses on ruling 1.
- `docs/receipts/unl-exploratory-17.md` is spliced from the laptop (operator commit 9d30b5a).

## 2026-10-06 (#306: k-track-receipt-splice — #87 ruling evidence on file)
- `docs/receipts/k-track-2026-10-06.md` is spliced from the laptop (operator commit 687b0f1, ruling (g) on #303). It shows system_matched 3, UNKNOWN 1 (the GB side error), 3 composite NO fills off-book, and venue fee-clear 0/29 NFL · 0/32 NHL · 2/18 NCAA · 0/17 UNL.
- Effect receipt: `desk-rescore` on Sunday's four PLAYs, 0/4 halved (architect state sync).
- 1c-spread share as recorded (architect): MLB/NFL/NHL/UNL 85–99%, NCAA 82%, PL 72% (n=6). Cost model unchanged.

## 2026-10-06 (#305: sweep-migration-rename-age — post-merge Codex finding on #304)
- `sp_deploy` migration plan: a migration RENAMED from another migration inside the deploy range (migrate_temp.py → migrate_x.py) carries the source's age, not the rename commit's. It is now undetermined, never planned at the rename's position. On main, add temp, add y, then rename temp → x planned `run [y, x]`, reversing the real order.
- Review fixes (Codex on #305):
  - Renames are scanned with `-m`, so merge-result renames count.
  - Rename CHAINS through intermediate names (migrate_temp → holding.py → migrate_x) are followed.
  - The scan runs before ordering, so an ambiguous migration is listed once and never in the ordered part.
- Review fixes, round 2 (Codex on #305):
  - Moves no longer depend on git's similarity-based rename detection. A move that also rewrote the file (below `-M`'s 50% threshold) planned `run [y, x]`. Now any commit diff that deletes a migration, or a path carrying a migration's age, taints the paths it adds. A new migration added in a tainted diff is undetermined.
  - Taint follows time (topological order, oldest first). A later reuse of an intermediate name (`holding.py`) no longer reaches back and blocks a valid `[x, y]` plan.
- Review fix, round 3 (Codex on #305): taint only accumulates. A merge that replayed a side branch's `holding.py` (renamed from a migration) as a plain addition used to clear its taint, so a later `holding.py` → `migrate_x.py` planned `run [y, x]`.
- Review fixes, round 4 (Codex on #305):
  - A migration moved onto an existing placeholder path (`--no-renames`: D source + M destination) now carries the source's age. It had planned `run [y, x]`.
  - New migrations with identical content at the target, an unchanged copy of an in-range migration with the source kept, are undetermined. That case had planned `[temp, y, x]`, running one one-shot twice.
  - Recreating a deleted name stays tainted. This errs toward undetermined; the operator orders by hand.
- Review fixes, round 5 (Codex on #305): this replaces the per-path taint scan of rounds 2–4.
  - Any migration deletion in the range (merge parents included) makes every new migration undetermined.
  - A rewritten move of a pre-range migration, and a split copy-then-delete that had planned `run [y, x]`, are now undetermined.
  - The deploy prompt for undetermined migrations says to read each one's history and never re-run a rename or copy. It no longer implies that every listed name runs, and it warns when the range deletes a migration.
- Review fixes, round 6 (Codex on #305):
  - The migration-deletion warning prints on its own. A range that only deleted a migration used to say nothing.
  - The dry run previews undetermined migrations and the deletion warning.
  - An edited copy of a migration stays a new migration. Copying an existing migration and editing it is how new migrations are written, and #304 kept template-derived migrations new.
- Review fix, round 7 (Codex on #305): the deletion warning names the deleted migrations. It points to a range-wide `git log --no-renames --name-status`, never `--follow`, which misses a rewritten move. The plan and the deploy receipt carry `deleted_migrations`.

## 2026-10-06 (#304: post-merge-codex-sweep — post-merge Codex findings on #296 and #297)
- `sp_deploy` migration plan:
  - An UNCHANGED copy of an existing migration (`C100`) is reported with the renames and never planned as runnable. `-M` alone reported it as an addition. A new migration written from an old one's template stays new.
  - Only a migration's FIRST appearance groups it with a commit, so a merged branch's ordered migrations are no longer "added together" just because `log -m` re-lists them in the merge commit.
- `k-track-receipt --ledger` refuses an export whose `calls`, `fills` or `system_picks` is not a list of objects, instead of a traceback.
- The other two post-merge #297 findings (shared city words, the windowed unpriced count) are fixed on #299, which rewrites that code.
- Review fixes (Codex on #304):
  - A copy or rename is suppressed only when its SOURCE was a migration at `before`. A new migration identical to a shared non-migration template stays new.
  - Each migration counts at its LAST addition by an ordinary commit, so a re-added migration keeps its grouping. A merge commit counts only when no ordinary commit added the path.
- Review fixes (Codex on #304, round 2):
  - Copies are decided by CONTENT: a new migration whose file is identical to any migration at `before` is a copy, whichever identical source git would have named.
  - Only an addition carrying the released file's content counts, so a competing branch's different file under the same name never sets the order.
  - An explicit `"fills": null` is refused.
- Review fix (Codex on #304, round 3): when several ordinary additions carry the released file (identical files on two branches, or an identical re-add), the migration is undetermined and the operator orders it.
- Review fix (Codex on #304, round 4): **conservative ordering.** A migration counts only when exactly ONE ordinary commit added it, or none did and exactly ONE merge did. The chosen commits must form a strict ancestry chain, in topological order. Re-adds, competing or identical additions, several merge additions, one shared commit, and parallel branches are all undetermined, and the operator orders them.
- Review fix (Codex on #304, round 5): a merge commit counts as an addition exactly when NONE of its parents had the path (a merge-result addition or re-add). When a parent had it, `-m` is only re-listing that branch's addition. A merge re-add after an ordinary add is therefore a second addition, and undetermined.
- Review fix (Codex on #304, round 6): the addition log runs with `--no-renames`, so a file renamed INTO a migration name counts as an addition of that migration. A rename re-add is therefore a second addition, and undetermined.

## 2026-10-06 (#303: k-exec-addendum — #87 executable edge, Desk v1.1 addendum — ARCHITECT-RULE)
- **Cost = ask + taker fee** (`desk_policy.taker_cost_for`): the contract the order line buys, at its ask, plus 0.07·M·P(1−P) rounded to the nearest cent per fill. The maker cost is shown for reference only.
- **TAKE at the ask by default.** Join-bid applies only at a spread of 3c or more, in the order line, the exec block and the Cockpit's ledger join bid. The 2026-09-30 join-bid doctrine is superseded.
- **Sizing.** A PLAY gets full tier units only when its exec edge is at least 4pp. Otherwise, or with no executable quote, it gets HALF units. Quarantine, floors, tiers and ladders are unchanged.
- **Venue.** The 5pp fair threshold stands, AND the exec edge (book fair − cost) must clear 4pp. A venue call with no executable quote is PASS with no reference.
- **Parlays.** Ticket Π market = Π executable cost; a ticket with an unpriced leg is not offered (counted). Each ticket carries `fair_p`, each leg's `exec_cost`, and the independence-estimate label.
- New read-only `desk-rescore FILES…`: the published PLAYs, re-scored under the addendum at each file's own as_of, showing which would have been halved.
- `desk_meta.exec_addendum` stamps every file. The frozen pre-F1c golden still holds under `base_v11()`.
- New tests: `tests/test_desk_exec_addendum.py` and `scripts/cockpit_exec_addendum_verify.py`.
- Review fixes (Codex on #303):
  - The doctrine, the join price, the cost and the order now share one quote source (`side_quotes`: the contract the order line buys), so a three-way leg-priced pick no longer says "take" while its order joins.
  - There is one join price, bid + 1c at a spread of 3c or more, in both the exec block and the order line.
  - The Cockpit ledger records the file's executable cost and join price, and logs parlay legs at their executable cost (fair kept as `fair_p`), so tickets settle at the price that qualified them.
- **ARCHITECT RULINGS on (a)–(j), 2026-10-06:** (a)–(d) ratified; (e) ratified, to be revisited at the first 30 graded ladders; (f) #218 re-scoped; (g) the receipt file is committed from the laptop by the operator (pending; not in this PR); join at bid + 1c on spreads of 3c or more ratified.
  - **(h) applied:** each order is priced at its OWN contract count (`order_contracts`, as `order_line` writes it), and the 10-contract assumption ends. A 0.25u venue or parlay order is 2 contracts. A PLAY's gate prices the order it places if it clears (its tier units, × 0.5 when kalshi-only). A halved PLAY also reports its emitted order's cost (`order_cost`, `order_contracts`).
  - **(i) applied:** the venue engine backs the best side (largest fair divergence) among the sides that clear BOTH gates.
  - **(j):** unchanged. Parlay ladder legs stay straight-on-pick, and double-chance legs are a v1.2 candidate.
- Review fixes (Codex on #303, round 4):
  - Quote selection is `order_line`'s own: a ticketed side leg is the instrument (unpriceable without an ask), else NO on the opponent's ticketed leg.
  - The fill count is taken at the emitted limit (the join price at spreads of 3c or more).
  - The Cockpit ledger records a halved PLAY's `order_cost` and settles VENUE calls at their executable cost, keeping `kalshi_p` alongside.
  - Pre-addendum files keep their legacy join bid.
  - The receipt is marked pending from the laptop.
- Review fixes (Codex on #303, round 5):
  - The Cockpit's exec marker states only the gate ("exec gate clears / fails"), never a final size.
  - `desk.exec` is present whenever `side_quotes` prices the pick, including NO on the opponent's leg.
  - Value shadows log the file's executable cost.
  - `docs/CLI.md` documents the TAKE / join ≥ 3c limit.
  - `desk-rescore` applies the file's own unit basis and prints it.
- Review fixes (Codex on #303, round 6):
  - `maker_cost` is the join order's (bid + 1c) at the order's own count, and none when the doctrine takes.
  - Quarantine shadows log the file's exec cost.
  - Parlay legs keep their serialized `fair_p`.
  - `desk-parlays` documentation and CLI output describe executable pricing ("Π executable cost", Π fair, unpriced tickets excluded).
- Review fixes (Codex on #303, round 7):
  - A LADDER (which buys NO on HOME) carries no pick-leg exec block.
  - A parlay whose leg has no book reference has `fair_p` unavailable, never Π model.
  - A halved PLAY's maker reference is at the emitted order's count.
  - The Cockpit's Policy card states the #87 v1.1 doctrine: TAKE, executable sizing and the venue gate.
- Review fixes (Codex on #303, round 8):
  - Quarantine shadows' exec is priced at the shadow's size.
  - An explicit `market_p: null` on a parlay leg and an explicit `order_cost: null` (a refused resized order) stay unavailable in the Cockpit ledger. Only absent legacy fields fall back.

## 2026-10-06 (#301: prediction-history — every prediction write kept as a series, #87 K-track — ARCHITECT)
- New APPEND-ONLY `prediction_history` table: `match_id`, `model_version`, `computed_at`, the home/draw/away probabilities, and `recorded_at`.
  - Every `Prediction` insert, from any write path (`predict-nfl`, soccer and MLB predict), is appended at flush in the same transaction. A rolled-back run leaves no history.
  - `predictions` stays current-only (S13). The window chain's hourly re-predicts become a stored series, so model-vs-cost is evaluable per Kalshi capture.
- New `migrate_prediction_history.py`: additive and idempotent, with a receipt. There is no backfill, because overwritten predictions are gone.
  - Before it runs, predictions still write and the skipped history is logged as a warning.
- Chain receipts count `prediction_history`. The count is null until the migration runs.

## 2026-10-06 (#299: fill matcher — doubleheaders by the ticker's start time; three-way NO is composite — ARCHITECT)
- The Cockpit's fill matcher and its Python port (`src/walters/ledger_fills.py`) change together, with parity preserved (`scripts/ledger_fills_parity_verify.py` 30/30).
- **Doubleheaders:** the event ticker's HHMM is the scheduled start in US Eastern time (`KalshiAdapter.ticker_start`, M13; DST via Intl / zoneinfo). Among a fill's candidate calls, those within 3h of it count, nearest first. Without a time the old order stands, and an ambiguous attribution stays flagged. The Cockpit re-parses each stored ticker, so earlier imports gain the start time.
- **Three-way NO:** a NO on an EPL/UCL/FA Cup/UEFA NL HOME or AWAY leg is two outcomes, COMPOSITE. It is never matched to a single-side straight: with a candidate call it is booked off-book ("composite contract — never a straight"); a UNL single with no call stays in the fun book (ruled 2026-09-30). Its held contract stays known for the closing fair. A two-way NO still means the opposite team.
- Tests: `tests/test_fill_matcher_lane.py`; `k-track-receipt` lists composite fills.
- Review fixes (Codex on #299):
  - When the ticker carries team codes, they decide which game a fill fits. One shared title word ("United", "City") no longer stands for team identity.
  - The receipt's unpriced-position count is scoped to the window.
- Review fix (Codex on #299, round 2): a composite NO matches a real LADDER call whose pick is the opposite side. The desk order line executes an AWAY ladder as NO on HOME (X2), so executed ladders reconcile and carry their CLV. A straight still never matches a composite.
- Review fix (Codex on #299, round 3): ticker codes that do not prefix the team name (JAX for Jacksonville Jaguars, BHA for Brighton and Hove Albion) now match through a strict two-team title fallback. Both title teams must fit, on different sides, by whole-word subset. A shared "United" and Man City vs Man United still do not match.
- MATCHER BUG (ARCHITECT 2026-10-06): the ticker suffix names the side. A fill whose resolved role differs from the call's pick is off-book ("side disagrees") and is never matched. KXNFLGAME-26OCT04GBTB-GB yes (Green Bay, AWAY) had been system_matched to a HOME (Tampa Bay) call because "Green Bay" and "Tampa Bay" share the word "Bay". With a ticker role, agreement is role == pick; without one, it is a whole-name subset. Applies to both logged calls and stored predictions. Regression uses the exact fill; parity is 34/34. Reclassified on the operator's ledger, system-matched becomes 3 fills.
- Review fix (Codex on #299, round 4): the ticker's start time now picks the GAME first (the nearest start; tied starts stay together and are flagged), and only then is the pick checked. A disagreeing exact-time game no longer hands the fill to a later game. Parity: 36/36.
- Sweep fix (post-merge Codex on #297): ticker codes must fit both sides AND at least one strongly (by initials or name prefix). Two weak two-letter-initials fits are a same-city collision, not identity: a Giants–Rams fill no longer fits a Jets–Chargers call. Legacy titles without codes now need two different sides. Parity: 38/38.
- Review fix (Codex on #299, round 5): the strict-title fallback also holds the CONTRACT's team (the title's "X wins" team) on the ticker's side of the call. A call with the same teams but home and away reversed never fits. Parity: 40/40.
- Review fixes (Codex on #299, round 6):
  - NO on the TIE of a three-way market is composite (HOME-or-AWAY, `no_on_role` DRAW).
  - A WEAK code fit (only the first two letters prefix the initials) must be confirmed by a title team whose every word is a prefix of the side's name. A strong opponent no longer vouches for it: NYGSEA does not fit Jets–Seahawks. A code that fully prefixes the initials (KC, SF) stays identity.
  - Legacy "A vs B Winner?" titles orient through the other code fitting the call's opposite side.
  - Parity: 46/46.
- Review fixes (Codex on #299, round 7):
  - Title teams are now BOUND TO SIDES. "X wins — Y" puts X on the contract's side. A legacy "A vs B Winner?" title is AWAY vs HOME, per the repo's own fixtures, e.g. BUFKC = "Buffalo vs Kansas City".
  - A weak code is confirmed only by its own side's title team, so a reversed Giants/Jets game never fits.
  - A legacy title orients two non-prefix codes (UGAUNC).
  - Parity: 50/50.
- Review fix (Codex on #299, round 8): the Cockpit flags tied attributions with every candidate (`ambiguous_calls`) on the straight and ladder paths, as the port does. Parity now compares that field: 52/52, and 49/52 on the old Cockpit.

## 2026-10-06 (#298: Desk fee-clear marker — an exact 4.00pp edge clears — ARCHITECT)
- `desk_policy.exec_block`'s `fee_clears` and the Cockpit's "fee-clears?" marker compare with a 1e-9 tolerance (`FEE_CLEAR_EPS`). Before, (0.35 − 0.31)·100 = 3.9999999999999982 read as a miss. Same tolerance as `k-track-receipt`.
- Golden: no edge within 1e-6 of 4pp in `tests/golden/desk_js_v1_1.json.gz`; unchanged, still 15/15. Test: `tests/test_desk_fee_clear_boundary.py`.

## 2026-10-06 (#297: k-track-receipt — the #87 executable-edge receipt, with #75's call-to-fill reconciliation — ARCHITECT)
- New READ-ONLY `k-track-receipt`:
  - **Ladders:** every pre-kickoff Kalshi ladder captured 2026-09-23 → end of 10-07, by sport: spreads, two-sidedness (0 < bid ≤ ask < 1), and the fee-clear rate at taker and maker cost (the Desk's K2 4pp rule; `venue.kalshi_exec` costs), versus the live model's pick and versus the venue engine's book reference, never pooled.
  - **Fills** (`--ledger` reads the Cockpit's ledger export): executed-position CLV and fee-adjusted edge, plus #75's call-to-fill reconciliation, exactly one disposition per eligible call.
- `src/walters/ledger_fills.py` ports the Cockpit's fill classification and executedPositions line for line. `scripts/ledger_fills_parity_verify.py` runs the Cockpit's JS and the port on one ledger: 24/24.
- Tests: `tests/test_k_track_receipt.py`.
- Review fixes (Codex on #297):
  - The predictions table keeps the current row only (upsert). A capture taken before a re-prediction therefore has no model reference: it is reported as "captured before the current prediction was written: no history kept", never silently dropped and never a look-ahead.
  - One-sided and incomplete ladders count as not evaluable on each basis, and their two-sided legs' spreads stay in the distribution.
  - The call window compares full kickoff timestamps.
  - Each reconciled fill prints its ledger id.
- Review fixes (Codex on #297, round 2):
  - The funnel's "cost recorded" reads the recorded-cost fields for every call, MATCHED included.
  - A fill that more than one real call fits (an MLB doubleheader: same teams, same day) keeps the Cockpit's attribution for parity, but is flagged and listed as AMBIGUOUS, never silent. Fixing the matcher itself means using the ticker's start time in the Cockpit and the port together.
- Review fixes (Codex on #297, round 3):
  - Executed-position CLV is restricted to the window's calls, the same cohort as the reconciliation. Positions outside it are counted and excluded.
  - An exact 4.00pp edge clears despite binary-float drift (1e-9 tolerance; `desk_policy`'s fee-clear has the same comparison and is raised separately).
  - A NO on a three-way family's HOME/AWAY leg (two outcomes) keeps the Cockpit's attribution for parity but is flagged COMPOSITE NO and listed.

## 2026-10-06 (#296: host receipts carry the running release; deploy prints the exact migration command — ARCHITECT)
- `sp_common._git` passes `safe.directory` for the checkout. The host checkout is root-installed and the units run as `sp`, so git refused it ("dubious ownership"), `running_release()` returned None, and no receipt carried a release (cutover-readiness criterion (b)). A receipt whose release is still null now carries `release_error` with git's own message.
- `sp_deploy` prints, for each new migration, the exact by-hand command: as `sp`, with host.env loaded, `sp_backup.py daily &&` the migration.
- Tests: `test_running_release_reads_a_checkout_owned_by_another_user`, `test_a_null_release_carries_its_reason`, `test_deploy_prints_the_exact_migration_command`.
- Review fixes (Codex on #296):
  - The migration command runs the new migrations in the order they were added (commit order, oldest first) as one chained `&&` command. Git's alphabetical path order put `migrate_score_90.py` before `migrate_status_raw.py`, which it needs.
  - A rollback or other non-forward deploy prints no runnable migrations. It lists the skipped ones, and modified migrations are listed separately.
  - Test: `test_deploy_migration_plan_orders_by_commit_and_skips_rollbacks`.
- Review fixes (Codex on #296, round 2):
  - The printed command runs `sp_deploy.py --run-migrations m1 m2 …`. It holds ONE DB lock across the daily backup and every migration, runs them in order, stops at the first failure, and receipts each step. A chained `sp_backup.py daily && migrate…` released the lock in between.
  - A migration added in a merge result counts as new (absent at the old head, present at the target).
  - An ancestry check that errors refuses the plan instead of reading as a rollback.
  - An explicit release on a receipt (sp_cutover's dry run) no longer also carries `release_error`.
- Review fix (Codex on #296, round 3): the migration plan is computed before the checkout moves, inside the deploy lock. A planning failure refuses with production still on its current release, and a dry run shows the plan. Test: `test_deploy_plans_migrations_before_moving_the_checkout`.
- Review fixes (Codex on #296, round 4):
  - The printed command carries `--expect <target sha>`. `--run-migrations` refuses, before any backup, unless HEAD is still that release.
  - `--dry-run` with `--run-migrations` refuses.
  - A failed tag or branch lookup makes the release unreadable (null, with `release_error`), never a guessed `UNTAGGED@`/`BETA`.
- Review fixes (Codex on #296, round 5):
  - Migrations added together in one commit, or not placed by the history, have no determinable order. No runnable command is generated; the deploy names them and the exact `--expect … --run-migrations <ordered names>` form to run once the order is decided.
  - A renamed migration is reported (already ran under its old name), never runnable.
  - Migration files are validated under the DB lock.

## 2026-10-06 (#295: CLAUDE.md — quoted heredocs only for PR text — ARCHITECT)
- Standing rule recorded in CLAUDE.md: PR bodies, comments and commit messages are written through quoted heredocs (`<<'EOF'`) only. An unquoted heredoc runs every backticked span as a command; on 2026-10-06 one ran `nfl-grade`, which created an empty DB under the container's data/ (since removed) and blanked spans in #290's body (since repaired).

## 2026-10-06 (#294: UNL skew test v2 — the ten ratified definitions; cutoff moves to the ratification — ARCHITECT)
- `docs/specs/unl-venue-skew-test.md` is now v2. It records the 2026-10-06 ruling verbatim and states every definition. The freeze cutoff moves to `2026-10-06T14:35:31Z` (the ruling's relay on #286); anything inspected before it is exploratory.
- `unl-ladder-receipt` applies the ten definitions:
  - (1) the exploratory 17 are excluded by match id (`EXPLORATORY_MATCH_IDS`; `--skew-test` refuses until all 17 are recorded);
  - (2) book sessions use the venue engine's own rules: at least 4 books, captured no more than 3h before the Kalshi capture and never after it;
  - (5) only the latest capture counts;
  - (6) the receipt refuses without the ticker column;
  - (7) CANCELLED/POSTPONED/STALE_ORPHAN are excluded and listed;
  - (8) one event per board, with the event printed;
  - (9) two-sided means `0 < bid <= ask < 1`;
  - (10) only an exact tie on the favorite excludes a game.
- (4) `sync-kalshi-soccer --competition UNL` refuses any `--max-spread` but 0.10. Every soccer sync prints its max-spread.
- Tests: `test_the_ten_ratified_definitions`, `test_unl_sync_refuses_any_max_spread_but_the_frozen_one`.

## 2026-10-06 (#293: NFL grading — one record definition in nfl-grade and RESULTS.md — ARCHITECT)
- ARCHITECT 2026-10-06: `nfl-grade` and the RESULTS.md NFL section state the record the way the results file does (#290). Rows count from `live_since` onward. A tie is a PUSH, outside the hit denominator; it was a hit for an away pick. Pre-live rows sit under their own heading, never pooled.
- `grade_nfl` returns `games`/`decided`/`hits`/`pushes` and a `pre_live` tally. It skips unscored FINISHED rows (the #289 rule), and `days_back=None` means season to date. Log-loss keeps the gate's tie convention, averaged over live rows.
- RESULTS.md's NFL section reads the season to date, no longer a rolling 30 days. It prints `Sides: **H/D** · pushes P` and a pre-live sub-heading.
- RESULTS.md: a sport whose outcomes carry no log loss prints `Mean log-loss: — (n=0)` instead of raising ZeroDivisionError. The new test's shared-DB run surfaced this.
- Test: `test_nfl_grade_and_results_md_state_the_one_record_definition`.
- Review fix (Codex on #293): `nfl-grade` defaults to the season to date, the stated record. Before, the CLI called `grade_nfl()` with its 8-day default. `--days N` keeps the rolling read. Test: `test_nfl_grade_cli_defaults_to_the_season_record`.

## 2026-10-05 (#292: NFL prediction-set scope check expects bye weeks; Kalshi-only reference's first live fire recorded)
- `nfl_backtest.scope_line(per_week=True)`, used by `predict-nfl`'s prediction set: per week, teams = 2 × games = 32 − byes, each team once. A bye week (e.g. teams=30) no longer raises SCOPE ALERT. Duplicates, more than 32 teams, or non-NFL rows still do. Ratings and backtest keep the 32-team check. Test: `test_prediction_set_expects_32_minus_byes_per_week`.
- Recorded: the Kalshi-only reference fired live (NYY@TB 23:11Z, mid 0.475, spread 1c, +3.1pp → PASS below floor).

## 2026-10-05 (#291: `unl-ladder-receipt`: read-only per-game UNL ladder receipt + the frozen favorite-skew test — ARCHITECT #286)
- New CLI `unl-ladder-receipt` (`src/walters/unl_ladders.py`). Per UNL game after the freeze cutoff it shows the match, legs (bid/ask, spread, two-sided), capture time, series, book probability and favorite gap.
- The sample is the first 30 games qualifying under `docs/specs/unl-venue-skew-test.md`; exclusion reasons are listed. `--skew-test` runs the frozen bootstrap test once the sample is complete. `--out` writes to `docs/receipts/` and refuses `data/`. Read-only.
- Tests: `tests/test_unl_ladder_receipt.py` covers each exclusion reason, the three-leg normalized gap, a deterministic bootstrap (seed 20261005) and the CLI.
- Review fixes (Codex on #291): a leg without a stored ticker makes the series UNKNOWN (never certified by the other legs); an offset-bearing `--since` is normalized to naive UTC; a DB without UNL prints `REFUSED` instead of a KeyError; `--skew-test` refuses unless the frozen cutoff and n 30 are in force.
- Review fixes, round 2 (Codex on #291): a capture stamped exactly at the cutoff no longer qualifies (strictly after); `--n` must be at least 1; the CI keeps full precision, so the verdict and the printed bounds are the same numbers. Cancelled/postponed/stale fixtures in the cohort are escalated (frozen-definition change).
- Review fixes, round 3 (Codex on #291): the bootstrap receives UNROUNDED gaps (rounding is display-only); receipt timestamps keep seconds; the `data/` guard compares the RESOLVED target with the resolved project `data/`, so a symlink or a cwd inside `data/` cannot bypass it (the test uses a temporary stand-in, never the real `data/`).
- Review fix, round 4 (Codex on #291): a malformed `--since` is a Click usage error (exit 2), not a traceback.
- Review fix, round 5 (Codex on #291): the receipt prints every leg's book probability even when that Kalshi leg is missing. Escalated (frozen definitions): one event ticker across the three legs, boundary quotes (0.00/1.00) as one-sided, and the 4-decimal tie rule.
- Review fix, round 6 (Codex on #291): an explicitly empty `--since ""` is a usage error, not a silent fall-back to the frozen cutoff.
- Review fix, round 7 (Codex on #291): a refused receipt (e.g. no UNL competition) exits 2 and is never written to `--out`.

## 2026-10-05 (#290: NFL season record: ties are pushes; pre-live rows listed separately, never pooled — ARCHITECT)
- `export_nfl_results`: a tie is a PUSH (`result "T"`, `push: true`, `top_pick_hit: null`), out of the hit denominator and counted separately. Log loss keeps the frozen gate's tie convention.
- The season record starts at `live_since` 2026-09-22 (Week 3). Preseason and earlier rows sit under `pre_live` with their own record.
- `record` gains `live_since`, `decided` and `pushes`. Contract: `results`/`count` are live rows only.
- Test: `test_ties_are_pushes_and_pre_live_rows_are_never_pooled`.
- Review fixes (Codex on #290): the `export-nfl-results` receipt prints hits over DECIDED games with pushes shown separately (`W6 1/1 +1P`), prints the pre-live record on its own line, and `--match` finds pre-live rows ("IN the file (pre-live, not in the season record)"). The season-choice finding was already fixed via #289.

## 2026-10-05 (#289: NFL results export skips FINISHED rows with no scores instead of crashing — Codex on #278)
- `export_nfl_results`: the base query requires both scores. A FINISHED row with null scores made `home_score > away_score` raise `TypeError` and aborted the season-to-date file. Test: `test_a_finished_row_without_scores_is_skipped_not_a_crash` (fails on main, passes here).
- Escalated, unchanged: tie grading in the record and preseason predictions in the season record.
- Review fix (Codex on #289): the season is chosen from every FINISHED predicted game before unscored rows are dropped, so an unscored opener of a new season exports that season (empty) instead of republishing the previous one. Test: `test_an_unscored_opener_of_a_new_season_does_not_republish_the_old_season`.

## 2026-10-05 (#288: Kalshi-only grading close reads the Kalshi ML rows two-way syncs actually store — Codex on #278)
- `close.grading_close` and `clv_restate` filtered snapshots to `market == "1X2"`. Two-way Kalshi legs are stored as `"ML"`, so the ruled kalshi_only close never saw a real quote.
- New `kalshi_close_market_filter` (1X2, plus Kalshi ML). Book sessions stay 1X2-only, and `close_from_kalshi` accepts both markets.
- Tests: fixtures use `ML`, as real syncs do. A new regression test covers the grading close and the restate, with a non-Kalshi ML row that never becomes a book close. Both fail on main and pass here.

## 2026-10-05 (#287: UNL ladders — the 17 recorded as exploratory; the favorite-skew test frozen — ARCHITECT)
- Recorded: 17/18 two-sided, 1c spreads, median |book−Kalshi| 2.5pp (max 4.4pp), Kalshi sharper on favorites by 3–4pp. Ruled EXPLORATORY: they informed the hypothesis and do not count.
- Frozen `docs/specs/unl-venue-skew-test.md`: the mean signed gap (Kalshi − book) on the pre-game favorite over a FRESH 30 two-sided boards captured after 2026-10-05T17:00Z (series KXUEFANLGAME). STRUCTURAL if the bootstrap 95% CI excludes 0, in which case UNL stays ineligible unless a skew-adjusted rule is declared as a separate candidate. One-sided boards never count.
- UNL stays "never" for venue-edge. Tracked in #286.

## 2026-10-05 (#285: UNL Kalshi series pinned to KXUEFANLGAME; KXCONCACAFNLGAME reserved for CNL — ARCHITECT ruling)
- `src/adapters/kalshi.py`: UNL → `KXUEFANLGAME` in `SOCCER_GAME_SERIES`, the adapter default, so the window chain needs no `--series`. Discovery had refused on two candidates (KXUEFANLGAME, KXCONCACAFNLGAME).
- New `SOCCER_SERIES_RESERVED = {"CNL": "KXCONCACAFNLGAME"}` ("for later"): a CNL sync refuses and names the series until CNL is wired (#284).
- `SOCCER_SERIES_DISCOVERY` is now empty; the mechanism stays tested for a future unpinned competition.
- Tests: pin + reserve (no `/series` call for UNL), discovery exactly-one-or-refused on the 2026-10-05 listing, and a UNL sync storing a three-way set via "mapped" with both candidates listed. Docs: CLI.md.

## 2026-10-05 (#283: NCAA re-key receipt: post-backup rows count as accounted only on the keeper — Codex review on #279)
- `ncaa_rekey_receipt.py --reconstruct-merges`: a reference row created after the backup (rowid above the backup's max) is accounted only when it points at the keeper. A post-backup row still on the merged-away id (no FK enforcement) is flagged and the reconstruction reads REVIEW. Test: `test_post_backup_row_dangling_on_the_merged_id_is_review` (fails on main, passes here).

## 2026-10-05 (#282: PR-body lint: closing keywords only on declared closure lines — LEDGER rule 5 enforced)
- New `pr-body` check (`python scripts/ledger.py check-body`, body via `PR_BODY`). It rejects a closing keyword + Issue ref (close/fix/resolve forms, `#N`, `owner/repo#N` or an Issue URL) anywhere except a declared closure line starting `Closes #N`. It re-runs on description edits.
- Why: #273, #274 and #275 used negated closing phrases, and GitHub closed #85, #211 and #276 on merge. Their descriptions now read "Outstanding work remains on #N".
- Tests: `tests/test_ledger_pr_body.py`. The original descriptions are rejected; the corrected ones and real closure lines are accepted.

## 2026-10-05 (#281: Codex reviews are input under the fence — ARCHITECT ruling recorded)
- CLAUDE.md, Workflow: Codex review comments are handled like Anthony's. Trivia (verified correctness bugs in the PR's own code, nits) gets fix-and-reply. Anything policy/gate/ledger-semantic is escalated as `needs-ruling`. A Codex suggestion never changes a frozen threshold or a verdict. Docs only; no code.
- Tagging (ARCHITECT, amended): the only mention is the review-request phrase, posted once after a fix push. Thread replies never contain the handle in any formatting, because any other mention starts a Codex cloud task.
- Sweep (ARCHITECT): an unanswered Codex thread on a merged PR is a finding (the #278 miss, fixed in #288).

## 2026-10-05 (#280: the Desk's 2c spread cap applies to the Kalshi grading close; follow-up to #278)
- **Ruling (ARCHITECT 2026-10-05, on #278, verbatim):** "apply the SAME 2c spread cap to the grading close — a wide Kalshi mid is not a reference anywhere."
- #278 merged at its earlier head, before the cap commit landed; this carries it.
- `close.close_from_kalshi` uses the Desk's own `KALSHI_ONLY["maxSpreadC"]` (2c, the same cent rounding). When the LAST two-sided pre-kickoff quote is wider, there is no Kalshi close; an older, tighter quote is stale and never substituted.
- Regression: 2c → priced; 3c → none; last quote 10c after an earlier 1c → none.

## 2026-10-05 (#279: resync matches by natural key before creating (second re-key); dedupe skips absent tables / refuses a schema behind the code; reconstruction learns the ruled classes)
- **(A) Second re-key (ARCHITECT, verbatim):** "the provider re-keyed Abilene Christian@West Florida a SECOND time (24146 → 24111) after Saturday's dedupe … Make the resync match by natural key (home, away, kickoff ±12h) when the incoming id is unknown, before creating a row."
  - The hole: the natural-key fallback skipped a stored row whose own id was STILL in the listing (and one already re-keyed this run) as "a different game", then CREATED the new id: a twin. The 10-03 test pinned that creation.
  - Now an unknown id is created only when no live stored row holds its natural key. One free candidate is re-keyed. A candidate whose id is still listed (the provider serving both ids), already claimed this run, or ambiguous is REFUSED (skipped, receipted), never created.
  - An incoming id found in a row's `<source>_prev` history goes back to that row. Cancelled / stale_orphan rows are never candidates.
- **(B) dedupe `--apply` crash (ARCHITECT):** "no such table: intl_venue_resolved". The reference sweep now skips tables absent from the live DB (they hold no references) and names them. `dedupe-matches` / `--orphans` refuse a schema behind the code with the remedy (`python cli.py init-db`, additive, never --force; the transaction rolls back) instead of a traceback.
- **(C) #277 reconstruction 30/30, RULED ACCOUNTED (ARCHITECT).** The tool now knows the ruled classes:
  - **created after the backup:** a rowid above the backup's max;
  - **re-pointed:** a table keyed BY match_id has rowid == match_id, so the re-point moves the row to a new rowid with identical content; such rows are paired;
  - **placeholder kickoff:** 04:00Z → real kickoff within 24h.
  A clean merge carrying them reads ACCOUNTED; a replaced row, a gone row or any other shift still reads REVIEW. Also fixed: a rowid-alias key reported the match id under the column's own name and leaked it into the content.
- **Receipts:** pytest 703 passed / 1 skipped (+6: refuse-not-create on a still-listed id; second re-key after a dedupe (refused while both listed, re-keyed after, history id goes back); two new ids for one row; absent table skipped; schema refusal without a traceback; the three accounted classes).
- **Review fixes (Codex on #279):**
  - P1: a row created in the run joins the natural-key index, so two unseen ids for one fixture in one listing create once and refuse the second.
  - P2: only a missing table / column ("no such table/column", "has no column named") is refused as "behind the code"; a locked or read-only DB, disk I/O and other operational errors keep their own diagnostic.
  - P2: an empty backup table's max rowid is 0, so every current row in it is post-backup.
  - P2: the placeholder class requires the destination to be a REAL kickoff (not another 04:00Z) within 24h.
  - pytest 706 passed / 1 skipped (+3).

## 2026-10-05 (#278: NFL results season-to-date (Week 3 TNF dropped by the rolling window); Kalshi-only grading close; K-track first live fills recorded)
- **(1) K-track, first live datapoints (ARCHITECT, recorded verbatim):** "First system-matched fills: 4 · +$5.96; executed CLV n=4 mean −0.23pp, fee-adj −1.83pp, all taker — record as the K-track's first live datapoints." Recorded in the ledger entry; no code.
- **(2) NFL results window:** `nfl_NFL_results_2026-10-05` lacked match 15073 (GB–ATL, Week 3 TNF) that the 10-02 file had. Cause: a WINDOW, not a filter. `export_nfl_results` wrote a rolling 8 days (unchanged since the live era), and the game kicked off 2026-09-25 00:15Z. The 10-02 cutoff (~09-24) held it; the 10-05 cutoff (~09-27) did not. Fix: SEASON TO DATE by default, with the file carrying `window` and `record` (games, top-pick hits, by week), so a lifetime record reconciles from one file. `--days N` keeps a rolling window; `--match ID` prints a membership receipt.
- **(3) Kalshi-only grading close (ARCHITECT ruling, verbatim):** "when no book session exists pre-pitch and a two-sided Kalshi capture does, grade against the Kalshi mid, labelled reference=kalshi_only."
  - Built in `close.grading_close`: odds table → book-consensus snapshot → (only when NO pre-kickoff book capture exists in either) the mid of the last two-sided pre-kickoff Kalshi HOME quote. Two-way boards only. A book session that exists but cannot price stays unpriced.
  - Labelled everywhere: `closing_bookmaker = "kalshi_only"` on the stored grade (evaluate and its backfill, clv-restate); `close_reference` and `close_kalshi` (bid / ask / mid / spread) on results rows. `close-probe` prints the receipt.
  - The generic results export now reads THE grading close (it read the odds table alone, so MLB's replaced table left rows unpriced even where the ruled snapshot close priced them).
- **Receipts:** pytest 680 passed / 1 skipped (+6: Kalshi mid / in-play / one-sided / three-way; absent books → kalshi_only; incomplete book session stays unpriced; books win and say so; season-to-date keeps a 10-day-old game the rolling window drops).

## 2026-10-04 (#277: --audit-merges zero says only "no current nearby rows found"; --reconstruct-merges against the pre-apply backup; #270 review)
- **Review on #270 (Anthony, 2026-10-04):** replaying the previous algorithm (offsets −70h/−40h/0h/+40h; provider absent/error/absent/found) applies a merge, moves an odds reference and shifts the keeper's kickoff. The audit then printed "every merge stands" although the unresolved twin sat 80h from the mutated kickoff. "Limit that output to `no current nearby rows found`. … reconstruct the reported 30-merge cohort from the retained pre-apply backup and apply plan … Mark unavailable provenance `UNKNOWN`."
- **`scripts/ncaa_rekey_receipt.py --audit-merges`:** a zero now reads `no current nearby rows found`, plus a note that the audit sees the current table only.
- **`--reconstruct-merges --backup PRE.db [--plan FILE] [--expect N]`** (read-only; the macOS mode=ro fallback is reused and its form printed). For every orphan merge in the provenance log it prints:
  - the original connected twin group in the backup;
  - the merged row (by the logged ids, among rows gone since);
  - the keeper's pre → post kickoff, with a shift named;
  - every reference move per table referencing matches (pre counts on both rows vs post on the keeper);
  - any same-pair row near the PRE or the POST kickoff outside the group.
- `--plan` cross-checks the pasted apply output's `[merge]` lines. Rows with no provenance log, a keeper absent from the backup, or an unmatched merged row read UNKNOWN. The last line gives `merges n/N` and ACCOUNTED or REVIEW. Backup paths are not printed (sanitised).
- **Regression:** the boundary case (keeper kickoff +40h, twin 40h from the pre kickoff and 80h from the post one): the audit says only "no current nearby rows found", and the reconstruction names the shift, the twin near the pre kickoff and the odds move. pytest 675 passed / 1 skipped.
- **Review fix (2026-10-05, reproduced on `70acdbbf`):**
  - **Plan cross-check:** compares the keeper AND merged row ids and both provider ids against the reconstruction. A plan naming a different merged row, or a different provider id, prints `⚠ plan disagrees` → REVIEW. An UNKNOWN merged row leaves the plan unverifiable, counted.
  - **References:** checked by identity, not count. Every pre row (rowid + content) referencing the keeper or the merged row must end on the keeper unchanged. Rows on the keeper that were not in the backup are flagged. A replaced odds row with equal counts → REVIEW. A table without rowids reads identity UNKNOWN.
  - **Regressions:** both refusals return REVIEW; the clean baseline merge returns ACCOUNTED. pytest 677 passed / 1 skipped.

## 2026-10-04 (#275: intl-venue-resolve: venue-country normalization for the rows v3 left unknown; ARCHITECT lane 5, data lane)
- **Ruling (lane 5, 2026-10-04):** "Intl venue-country normalization for the 313 unmatched venues and the 57% unflagged rows. Data lane only; intl-elo-v2 stays frozen through its window."
- **`python cli.py intl-venue-resolve --from-dir <save> --venues-dir <dir> [--aliases FILE] [--plan]`**, for every `intl_match_venue` row with `neutral_v3` NULL:
  - route A `/venues?id=<id>` for venue ids outside the route-B catalog (the "unmatched venues"); one call per distinct id, `--max-calls` capped, saved as `venue_id_<id>.json` and replayed;
  - no venue id served: a UNIQUE city, then name, match against the saved `/venues` catalog; several countries = ambiguous, refused and counted;
  - country spelling: NFKD/casefold on both sides, plus an optional pinned `--aliases` JSON. None is built in (law 1). A neutral reading whose home-country spelling never appears as a venue country stays unknown ("alias needed"), and the receipt lists those spellings for a ruling.
- **Storage:** a NEW table `intl_venue_resolved` (created by `init_db`, additive; no migration) holding venue country, `country_source`, `neutral_resolved` and the reason a row stays unknown. `intl_match_venue` and intl-elo-v2's inputs are never touched (the frozen window holds).
- **Receipt:** the unknown-row reasons, route-A calls, outcomes per source, the unflagged share before → after, and the alias candidates.
- **Tests:** 4 new (plan, route A / city / name / ambiguity / spelling / home-unknown / unserved, v3 untouched, alias + replay with 0 calls, refusals, CLI plan). pytest 678 passed / 1 skipped.

## 2026-10-04 (#274: #211 B-track: fills-based exposure and cash-at-risk per team-outcome, beside the units cap; ARCHITECT lane 3)
- **Ruling (lane 3, 2026-10-04):** "#211 B-track: fills-based exposure and cash-at-risk per team-outcome, from the imported Kalshi CSV, beside the units-based cap." Diagnostic only: the 1.25u cap and sizing are unchanged (ARCHITECT 2026-10-01: "cap/sizing unchanged").
- **Cockpit `fillExposure(L)`:** every sport fill becomes a payoff over its game's outcomes. YES on X pays if X; NO on X pays on every other outcome. Soccer families settle three ways (TIE = the draw); the rest settle two ways. Per game it reports gross stake, fees, hedge offset (= the worst outcome's payout, so > 0 only when the contracts pay on EVERY outcome) and cash at risk (= gross + fees − hedge offset). Per team-outcome it reports contracts and ≈ units at 10 contracts per 1u, flagged when above the 1.25u cap-equivalent.
- A fill whose contract role the ticker does not decide is excluded and counted (law 4).
- Fills are realized positions, so this is the exposure as executed. The result does not depend on load order (keyed by game, summed).
- **Where:** a "B-track exposure — fills-based" table in the Ledger tab's Realized card (top 25 games by cash at risk), plus a headline line in the P&L text.
- **Receipts:** new `scripts/cockpit_exposure_verify.py` 13/13 (two-way hedge, NO contract, soccer tie unhedged, cap-equivalent flag, exclusion, reversed-order identity, render, P&L line); all other Cockpit verifies green; pytest 674 passed / 1 skipped.
- **Still open on #211 (not this lane):** desk load-order invariance (resolve by as_of) and the ticket-product "independence estimate" label.
- **Review fix (2026-10-05):** a game is now the FULL settlement event ticker before its outcome suffix (e.g. `KXMLBGAME-26SEP271305NYYBOS`). Before, family+date+teams collapsed two intraday MLB doubleheader events into one game with a false hedge offset. Opposite sides of different events never hedge. A ticker whose event part fails the game grammar is excluded and counted apart ("event identity ambiguous"). Regression: doubleheader = two events, zero cross-game hedge, downside 1.53 + 1.47 (the old grouping read a 3-contract hedge and 0 at risk); same-event hedge and soccer-tie checks still green. Verify 16/16.

## 2026-10-04 (#273: cutover-readiness: the ruled #85 criteria in one read-only readout; ARCHITECT lane 2)
- **Ruled criteria (2026-10-02, verbatim):** "cutover when (a) 5 consecutive morning compares show only explained classes, (b) the host has run a full day on a tag carrying #246 with desk calls emitted, (c) parity harness green on that tag — earliest Oct 8 stands."
- **`cli.py cutover-readiness`** (`deploy/hosting/cutover_readiness.py`) prints:
  - (a) the five-compare streak from the exports mirror, pairing laptop/<date> with host/<date> as the Action does: dates, verdicts, and the classes named per divergent line;
  - (b) the host tag, days on it, whether it carries #246 (`git merge-base --is-ancestor`), and desk calls emitted per chain (chain receipts' exports, read from the mirror);
  - (c) `scripts/desk_parity_verify.py` run on that tag in a scratch git worktree;
  - a `GO` / `NOT-YET — <each unmet>` line (exit 0/1), including the earliest date.
- **Conservative naming (law 4):** the tool machine-names only identical, capture timing (market / Kalshi / price fields and the Desk fields that follow them, on matched rows) and the guarded code-version skew. Rows or files on one side only and model fields are UNNAMED, and they break the streak unless `--named` names that date, which then prints as operator-named. GO is a readout, never the decision.
- **Receipts:** 7 new tests; a synthetic five-day mirror + host receipts read GO with the real parity run on v1.2.2 (14/14 GREEN); v1.1.0 does not carry #246, v1.2.0 and v1.2.2 do.
- **Review fix (2026-10-05, reproduced on `9757e76c`):**
  - **Chain completion:** a chain counts only when it COMPLETED: an explicit integer exit 0, nothing refused, and every counted step run. A missing exit is a failure, a season-gated skip completes nothing, and a full day needs at least one completed chain and none failed.
  - **One-sided dates:** a date only one writer pushed is pending only when it is today, by the declared clock. An older one is OVERDUE, and the streak reads 0, as it does when the newest common date is more than a day stale.
  - **Regressions:** missing exit and partial steps → no full day → NOT-YET; a host-only date the day before today → `(a) streak 0/5 (overdue one-sided …)` → NOT-YET; the same date as today → pending, streak 5/5. pytest 683 passed / 1 skipped.

## 2026-10-04 (#272: Desk ORDER LINE — copy-exact Kalshi orders on PLAY / VENUE / ticket rows; ARCHITECT 2026-10-04)
- **Ruling (verbatim):** "ORDER LINE on every Desk PLAY/VENUE/ticket row: the Kalshi market ticker (we already resolve it in sync-kalshi), side (YES/NO), limit price per doctrine (join bid; the ask when spread is 1c), and contract count for the row's units at a declared unit size (SP_UNIT_USD in env, default 10 contracts) — so placing an order is copy-exact, never a lookup. Parlay tickets list the legs the same way. Cockpit renders from the file; no policy change."
- **Storage:** `odds_snapshots.market_ticker` (new, additive; `migrate_kalshi_ticker.py`). `sync-kalshi-*` (shared MLB/NFL/NHL/NCAA and soccer paths) stores the ticker it already resolved per leg. The column is deliberately NOT mapped in the ORM (on SQLAlchemy 2.1 an ORM INSERT names every mapped column, deferred included, so a mapped column would break every snapshot insert before the migration). It is written and read by guarded Core SQL (`write_kalshi_tickers` / `read_kalshi_tickers`), so a deploy before the migration keeps working; the test covers both states. No backfill (the tickers were never stored).
- **Exports:** prediction / NFL / fixtures rows carry `kalshi_legs` {selection: ticker, bid, ask} from the latest pre-kickoff Kalshi snapshot per leg.
- **Desk:** `desk.order` {ticker, side, limit, limit_basis, contracts, unit, text, why} on PLAY / LADDER rows, eligible market-only VENUE rows and every `desk-parlays` leg. LADDER = BUY NO on HOME (mirrored prices); a two-way market falls back to NO on the opponent, a three-way never does; a DRAW ladder is refused. Join bid, the ask at ≤ 1c spread, no bid = refused. Contracts = floor(units × 10), or floor(units × SP_UNIT_USD / limit) when set. A refusal is a `why`, never a guess. Calls and units are unchanged (parity golden green).
- **Cockpit:** renders `desk.order.text` verbatim under the call (model table, venue table, parlay legs).
- **Receipts:** pytest 682 passed / 1 skipped; `scripts/desk_parity_verify.py` 14/14; new `scripts/cockpit_order_line_verify.py` 11/11; all 21 other Cockpit verifies green (`cockpit_pass_class_verify.py` now reads the call cell without the order element).

## 2026-10-04 (#271: UNL Kalshi series discovered and stored; published-Cockpit CSP noted, local launcher)
- **`sync-kalshi-soccer --competition UNL`:** the soccer sync knew only `KXEPLGAME`. UNL has Kalshi markets (operator fills exist) but no receipted ticker.
  - `KalshiAdapter.resolve_soccer_series` discovers the UNL series from Kalshi's own `/series` listing (keywords "nations league"; game-winner series only, i.e. tickers ending `GAME` like every wired series).
  - Exactly one match is required, else it refuses and lists the candidates (law 1: never a guessed ticker).
  - The legs are stored like PL's (Home/Away/Tie snapshots, same gates), so `export-fixtures --competition UNL` and the venue engine read UNL three-way sets.
  - `--series` pins the ticker once receipted, and the receipt line names how the series was resolved.
  - UNL is added to the window chain's Kalshi table; the CI pin now covers mapped plus discoverable series.
- **Published Cockpit:** its CSP blocks api.github.com, so "Load latest from host" fails there. `docs/specs/exports-mirror.md` says so, and the new `scripts/cockpit_local.py` serves a saved copy of the published artifact (or the repo copy, flagged) on 127.0.0.1, where the control works. The ledger is per origin: move it with Export/Import and keep the same port.
- tests/test_unl_kalshi_discovery.py (2): discovery exactly-one / refused (2 or 0) / override / unmapped; UNL legs stored as a three-way set with quotes (Kalshi mocked).

## 2026-10-03 (#270: dedupe-matches --orphans: incomplete lookup coverage leaves the whole candidate set UNRESOLVED)
- PR #266 review (Anthony) found two cases on `d14c3f83`. A failed date lookup plus one observed provider game still permitted a RELINK. One found twin plus an unresolved competing twin still permitted a MERGE.
- Now a twin whose provider lookup errors, or any day of the ±2d search that fails, leaves the candidate and every twin it was weighed against UNRESOLVED and untouched (no merge, no relink) until complete lookups establish uniqueness. The plan line names the gap.
- tests/test_dedupe_orphans.py (+1): both cases, dry-run and apply, with ids, rows and references unchanged. The test was verified to fail on the old code (it relinked).
- **Review 2 (Anthony):** overlapping candidate sets still bypassed uniqueness. Same-pair kickoffs at t−30h, t, t+30h and t+40h with provider states absent / error / absent / found merged in one insertion order and refused in another.
  - Uniqueness is now decided per connected component of the twin graph (same home+away, ≤48h, different ids). Every id in the set is looked up first, and any error leaves every candidate UNRESOLVED.
  - A merge happens only when the set is exactly one absent candidate plus one found twin; any larger or multi-live set is refused for review.
  - With no live id in the set, each candidate is searched at the provider, and one failed search day leaves the whole set unresolved.
  - Merges in which the live row keeps its id now log provenance too (`<source>_rekeys`).
  - `scripts/ncaa_rekey_receipt.py --audit-merges` is the provenance audit of the applied merges: re-keyed rows with another same-pair row still within 48h.
  - Regressions: both overlap scenarios across all 24 insertion orders, dry-run and apply, rows / ids / odds references unchanged, one identical plan for every order (fails on the previous code); the audit test.

## 2026-10-03 (#269: ledger: evening state sync — WAL cause confirmed, NCAA re-key residue cleared, v1.2.2 deployed, mirror host side live)
- Record only (no code). It captures the architect's evening receipts for #265 (zero-pair explanation + `--orphans` apply), #268 (WAL confirmed), #264 / #208 (published Cockpit + production tag), #261 (host mirror live, laptop pending) and #263 (what remains).

## 2026-10-03 (#268: HOTFIX: backup verify falls back to a plain read when the read-only URI open fails)
- **`_verify_backup`** (`dedupe-matches --apply`, `clv-restate --apply`) tries two open forms in order, and the receipt names the one that read the backup:
  1. the read-only URI (`Path.as_uri() + "?mode=ro"`, `integrity_check`);
  2. if that raises, a plain `sqlite3.connect(path)` with `PRAGMA query_only = ON` (no writes possible) and `quick_check`.
- On macOS an existing 248 MB backup refused the URI form with "unable to open database file". The success line now reads `opened via <form> (after: <URI error>) · integrity ok (<check>) · journal_mode <mode> · <table> n = live`. If both forms fail, the refusal lists both errors.
- tests/test_backup_verify.py (+3): a macOS-style absolute path whose URI open raises falls back and verifies (the backup bytes are unchanged); both forms failing names both; `query_only` blocks writes.

## 2026-10-03 (#267: exports mirror: the first push to an empty remote no longer reads "nothing changed"; keygen path)
- **`exports_mirror.py push`** judges "changed" against the REMOTE's tip, not the local HEAD.
  - On the host the remote was set in `host.env` before the deploy key worked, so the chain hook's pushes committed in the working clone and failed to push. The hand-run first push then compared against that local commit and printed "not pushed — nothing changed" over an empty remote.
  - Unpushed local commits are now pushed ("incl. N earlier unpushed commit(s)").
  - The clone's `origin` follows `host.env` if the remote changes.
- **Deploy key path:** `keygen` and `push` resolve the key the same way: `SP_EXPORTS_MIRROR_KEY`, else an installed `/etc/sports-predictor/exports_deploy_key`, else `~/.ssh/sp_exports_deploy_key` (writable by `sp`). `keygen --key PATH` is accepted. An unwritable target refuses and prints both routes (the `--key` route and the root step). `docs/specs/exports-mirror.md` step 2 is updated.
- tests/test_exports_mirror.py: first push after failed attempts (reproduced: "nothing changed" over an empty remote), first push of 18 files from a fresh clone, key resolution, keygen into a writable path, unwritable-dir refusal.

## 2026-10-03 (#266: dedupe-matches --orphans; the apply summary reports state, not just this run's merges)
- **Reporting fix:** a `dedupe-matches` apply that found nothing left to merge printed "merged 0" on a table where 962 rows had already been re-keyed in place.
  - Every summary now prints the STATE before and, on apply, after: rows, deleted, rows carrying `<source>_prev`, stale orphans, and re-keys by provenance.
  - A 0-pair run says the rows were already re-keyed, so nothing was missed.
  - Re-keys now log `<source>_rekeys` entries {from, to, via, at}. `via` is one of: dedupe-merge, orphan-merge, orphan-relink, sync.
- **`dedupe-matches --orphans`** (dry-run unless `--apply --backup`). Candidates are SCHEDULED rows with no score that are stale (kickoff more than 6h past) or have a twin (same home AND away within 48h, a different id). Each id is resolved at the provider (`GET /games?id=`):
  - found → untouched;
  - lookup error → UNRESOLVED;
  - NOT FOUND + one live twin → merged (the older row keeps the references);
  - NOT FOUND, no twin → a provider search of the row's date ±2d for the pair. If exactly one game is found and no row holds its id, the row is RELINKED in place; if none is found, it is marked `STALE_ORPHAN` (never deleted);
  - ambiguous, swapped, held-elsewhere or already-claimed cases → refused and reported.
- **New status `MatchStatus.STALE_ORPHAN`:**
  - `export-fixtures` excludes it (counted);
  - the odds / Kalshi `match_lookup` and NFL rest-days skip it;
  - a SQLite status CHECK constraint lacking it refuses the mark cleanly.
- **Adapter:** `APIAmericanFootballAdapter.get_game(id)` (`/games?id=`), with the listing parse factored into `_parse_games` (behaviour unchanged).
- tests/test_dedupe_orphans.py (6).

## 2026-10-03 (#265: NCAA re-key receipt: why `dedupe-matches --apply` found 0 pairs)
- **`scripts/ncaa_rekey_receipt.py`** (read-only; opens the DB with `mode=ro`, writes nothing). It prints:
  - rows re-keyed in place, and the source-id classes (22xxx old vs 23xxx/24xxx new);
  - the natural-key clusters under `find_pairs`' own rules: mergeable / SAME id / missing id / 3+ rows, so a 0 is explained rather than assumed;
  - rows with no twin, with stale SCHEDULED orphans counted;
  - export-window rows vs distinct games, flagging duplicates still in the window;
  - per-id rows (ext ids, `_prev`, status, odds and snapshot counts);
  - `--game "Away@Home"` rows, with `--resolve` looking each row's id up at the provider (GET `/games?id=`, `/odds?game=`; the key is never printed).
- tests/test_ncaa_rekey_receipt.py (1).

## 2026-10-03 (#264: P0-3 follow-up, refs #208: fee-adjusted edge only from a recorded opening fee)
- **Cockpit `executedPositions()`** (PR #259 review 2, Anthony): the fee-adjusted edge requires `open_fee` on EVERY fill of the position (a recorded zero counts).
  - It no longer substitutes the combined/total `fees` for a missing opening fee and no longer defaults it to zero.
  - Without it the fee-adjusted edge is unavailable (null); entry-price CLV stays.
  - Positions are tagged `open_fee` / `missing` / `combined_only`, and the P&L prints both exclusion counts.
  - Opening and closing fees stay recorded separately at import (a re-import fills them in on older rows); nothing splits a combined figure.
- `scripts/cockpit_clv_verify.py` 19/19: missing-fee, combined-fee, recorded-zero and mixed-fill regressions with exclusion counts. Stored series and sizing unchanged.

## 2026-10-03 (#263: PRIORITY: backup verify opens Windows/space paths; names the failed check; sync-odds-football paced + 429 retry)
- **`dedupe-matches --apply` and `clv-restate --apply`** now share `_verify_backup`. It opens the backup with `Path.as_uri() + "?mode=ro"`; the old `f"file:{path}?mode=ro"` failed with "unable to open database file" on a Windows absolute path or any path with a space, `#` or `?`. It expands `~` and refuses only paths inside this project's `data/`. Every refusal names its check and the path it tried. `sp_common.ro_connect` and the k0 probe use the same safe open.
- **`sync-odds-football`** paces its per-game odds calls below the provider limit (`SP_ODDS_FOOTBALL_RPM`, default 280/min). A game still rate limited after the adapter's own retry (new `RateLimited`) is deferred and retried after the window (`Retry-After`, else 60s), for up to 2 rounds, never dropped. Odds are stamped at fetch time. The receipt counts rate-limited / recovered games.
- tests: test_backup_verify (6, a real `.backup` file under "my backups #1/"), test_odds_football_throttle (2).

## 2026-10-03 (#262: auto-claim includes parlay tickets; #208 segment scope ruled)
- `tools/cockpit.html`: loading the desk files auto-claims parlay tickets too, each at the `desk_parlays` file's as_of (whole ticket or nothing; a leg started at as_of skips the ticket). The idempotency key includes `parlay_id`, so a leg shared by two tickets is claimed once per ticket. `scripts/cockpit_autoclaim_verify.py` 13/13 (+2); the leg_audit verify counts the auto-claimed ticket legs.

## 2026-10-03 (#261: F2.5 exports mirror — the host pushes exports/ after every chain step; the laptop pushes at the end of the morning chain; compare Action; Cockpit "Load latest from host")
- `deploy/hosting/exports_mirror.py` (`push --role host|laptop`, `squash`, `keygen`): writes `<role>/<date>/<file>` plus `<role>/latest/<kind>.json`, keeps 14 days, and also ships `tools/compare_exports.py` and the compare Action into the mirror. Copies only. A push race retries from the remote's tip.
- `sp_run`: the mirror push runs after every chain step. It is non-fatal, takes at most 90 s and is receipted; it is off until `SP_EXPORTS_MIRROR_REMOTE` is set. New `sp-exports-squash.timer` (Sun 06:10 UTC), on the T11 list.
- `deploy/exports-mirror/compare.yml`: the commit status `compare_exports` (clean / DIVERGENT / pending) for the newest date both writers pushed.
- Cockpit: "Load latest from host". It uses a fine-grained read-only token kept in localStorage and fetches `host/latest/*.json` into the same load path (F1c refusal intact); upload handling is refactored into `loadDocs`.
- `docs/specs/exports-mirror.md` covers the operator setup. tests/test_exports_mirror.py (5); `scripts/cockpit_mirror_verify.py` (6).
- Review fix (Anthony): the shipped `tools/compare_exports.py` imported `sp_common.py`, which the mirror never shipped (`ModuleNotFoundError` in the Action). It is now standalone: it falls back to `SP_WRITER_OF_RECORD` from the environment. Its exits are 0 CLEAN / 1 DIVERGENT / 2 ERROR (bad arguments, a missing side directory, a crash), and it ends on a `VERDICT:` line. The Action posts `error` ("not a data verdict") unless the exit code AND the VERDICT line agree. Regression: a fresh clone of the mirror, with no PYTHONPATH, runs the shipped CLI and the Action's own step script → CLEAN, DIVERGENT, ERROR (tests/test_exports_mirror.py now has 6 tests).
- Review fix 2 (Anthony): a zero-file comparison is never CLEAN. Exit 3 = NO-COVERAGE ("VERDICT: NO-COVERAGE (0 compared) — not a data verdict"); the Action posts `error` "NO COVERAGE · <date>". Every run prints a `coverage:` line: JSON compared, one-side-only, outside the window, and files the glob left out (e.g. Markdown). Regressions on the shipped tree in a clean checkout: Markdown-only dated folders and empty folders → exit 3 / state=error (tests/test_exports_mirror.py now has 7 tests).

## 2026-10-03 (#260: Kalshi trade-API probe — read-only, no orders)
- `scripts/kalshi_trade_api_probe.py`: on the host it answers REACH (prod + demo `/exchange/status`), AUTH (RSA-PSS-signed key; `/portfolio/balance`), ORDERS (`/portfolio/orders` keys) and FILLS (`/portfolio/fills`: `is_taker`, fee fields). GET only by construction; no order is placed or cancelled. `cryptography>=41.0.0` added to requirements.txt (ruled: the signing dependency is real). tests/test_kalshi_trade_probe.py (3; the signing test skips where `cryptography` is unusable).

## 2026-10-03 (#259, closes #208 — P0-3: "model-close divergence" rename; entry-price CLV and fee-adjusted closing edge on executed positions)
- **Rename (labels and docs; stored series and keys kept):** the per-game metric stored as `clv` (model p − close fair on the pick) is now labelled "model-close divergence" in RESULTS.md, the NHL/UNL shadow grades and sections, `nfl-grade`, `clv-restate`, the web predictions page, the Cockpit shadow card and `docs/CLI.md`.
- **Exports:** results exports (`export-results`, `export-nfl-results`) carry `graded.close_fair` per side plus `close_at` / `close_books` / `close_source`, from `close.close_block` (the ruled `close_1x2`).
- **Cockpit (`close_ref`, version "p0-3 v2"; review fix):** graded straight/ladder positions gain a REFERENCE block = {q_close, fair by role, ref_move_claim = q_close − claim ref, ref_move_relog = q_close − re-log ref, quoted_edge_relog = q_close − quoted taker cost}. A ladder uses pick + DRAW. There is no complement guess and no block without a close. These are labelled reference movement, not CLV. Legacy `clv_v2` ("p0-3 v1") blocks are kept as stored, never rewritten and never read.
- **P&L block:**
  - EXECUTED-POSITION CLV comes ONLY from matched Kalshi fills. Per position, qty-weighted: the held contract's closing fair minus the fill entry (a NO is priced as 1 − the NO'd side), and that less the charged fee per contract. It is broken out by sport.
  - Calls with no matched fill are excluded and counted, as are fills whose held contract cannot be priced at the close.
  - REFERENCE MOVEMENT (claim → close, re-log → close, quoted taker edge) is printed separately, under its own label.
  - Every series reports n / mean / median / positive share / 90% bootstrap CI clustered by day.
- **Review regression (Anthony, PR #259):** q 0.65, re-log 0.60, matched fill at 0.70 → reference movement +5pp, executed entry CLV −5pp (v1 read +5pp as "exec CLV"). Separately, a graded call with no fill → not an executed position. Sizing unchanged.
- tests/test_close_block_208.py (2); `scripts/cockpit_clv_verify.py` (15); three tests updated for the new labels.

## 2026-10-03 (#258: Cockpit AUTO-CLAIM — loading a desk file claims its calls at the file's as_of)
- `tools/cockpit.html`: loading a `--desk` prediction or fixtures file logs its PLAY / LADDER, VENUE, quarantine-shadow and value-shadow calls as claims automatically. The claim is stamped at the file's `desk_meta.as_of`, and the kickoff test also reads it. Claims are idempotent on (match, pick, call type, engine, as_of) via `L.meta.auto_claims`, and a file older than the ledger never reprices a position. Parlay tickets stay on the button, now "Re-log at T-60". Fixtures rows now carry their file's as_of (bug found by the new verify).
- `scripts/cockpit_autoclaim_verify.py` (11 checks): two Braves PLAYs and Thursday's Pitt@VT VENUE claimed; PASS and started-at-as_of rows not claimed; idempotent reload; newer file reprices, older never does. Four verifies adjusted (render-comparison loads now claim). Desk golden unchanged.

## 2026-10-03 (#257: NCAA duplicate rows — the resync re-keys instead of duplicating; dedupe-matches; export prefers the finished row)
- `IngestionService.sync_matches` (american-football family): a source-id miss falls back to the natural key: same competition, same home and away team, kickoff within 12h, and the stored id absent from the listing. The stored row is UPDATED and takes the new id; the old id is kept as `<source>_prev`. Ambiguous candidates or a home/away-swapped pair are refused and receipted, never created. `SyncResult` reports `rekeyed` / `rekey_refused`.
- `python cli.py dedupe-matches --competition NCAA [--apply --backup PATH]`: the receipt of how each duplicate pair differs. Apply merges the newer row into the older, referenced one: references are re-pointed, the empty row is deleted, and conflicts are refused.
- `export-fixtures` carries one row per fixture, preferring the finished one, and counts `duplicates_suppressed`.
- tests/test_ncaa_rekey_dedupe.py (5).

## 2026-10-02 (#256: NCAA market chain syncs results before the export; closes #254)
- `ncaa-market` (host `sp-ncaa-market`, Thu / Fri / Sat) now runs `sync-matches --competition NCAA --season 2026` for yesterday and today as single-day calls, before `sync-kalshi-ncaa` and `export-fixtures`. Games finished since the last run (Thursday's slate before Friday's export) leave the window instead of reading SCHEDULED.
- The laptop routine is documented in `docs/CLI.md` (Market-only competitions); `docs/specs/hosting-h1.md` timer table updated. tests/test_hosting_pack.py (+1).

## 2026-10-02 (#255, refs #254: NCAA kickoff +24h finding — read-only receipt script)
- `scripts/kickoff_receipt.py` (read-only), for each match:
  - the STORED row: utc_date, status, external ids;
  - the PROVIDER's raw date block and timestamp (`/games?id=`, one GET; `--no-provider` skips it);
  - every EXPORT carrying the match: as_of, row utc, the Desk's reason, and the in-play test recomputed on that file's own inputs.
- tests/test_kickoff_receipt.py (1). No pipeline change until the receipt says which side is wrong.

## 2026-10-02 (#253: nhl-v7 ledger annotation; AET/PEN release ratified)
- `docs/registry/experiments.json`: nhl-v7 gains `ledger_count_at_record: 6` and a one-line `ledger_count_note`. Its run record's `prior_read_count: 5` stays as written (ARCHITECT: never rewrite a run record; the live count is the ledger's). `docs/REGISTRY.md` records the doctrine. tests/test_nhl_v6_record.py (+1).
- Ratified, no code change: AET/PEN rows without a stored 90-minute score are unscoreable and released from the intl-elo-v2 cohort, as built in #252.

## 2026-10-02 (#252: intl-elo-v2 cohort — UNSCOREABLE fixtures are released, raw code as reason)
- ARCHITECT 2026-10-02: "AWD/WO (forfeit, walkover) games are RELEASED and substituted exactly like cancelled/abandoned — unscoreable is the criterion, not the status label; record the raw code as reason."
- A cohort fixture is released when it can never be scored: cancelled (CANC / ABD), or finished under a non-FT code without a 90-minute score (AWD / WO, and AET / PEN missing the split). A FT row still waiting for its score stays pending.
- `registry.substitute_cohort_fixture` requires evidence of a cancelled or finished fixture marked unscoreable, and the raw code as the reason. Replacements are never unscoreable themselves. `intl-elo-confirm --substitute` writes the substitutions. tests: registry, intl shadow.

## 2026-10-02 (#251: intl-elo-v2 run record spliced; PASS recorded — confirmation window open)
- `docs/registry/`: the laptop's intl-elo-v2 run (392 scored ids, the same ids as v1, sha256 verified; log-loss 0.7889 vs bar 1.0424; RPS 0.153 vs 0.237; fit c×1.5, K×2.0; neutral rule v3) is spliced. Its prior reads are recomputed against main's ledger: intl-elo-v1, so 2 reads counting this one, as ruled.
- Verdict PASS recorded verbatim. Status is `confirming`, and production is refused until a CONFIRMED read. The declared limitations are recorded: grid-edge pick, 13.7% v3 neutral share, 57% unflagged venues. tests/test_intl_elo_v2.py (+1).

## 2026-10-02 (#250, closes #91 RULED: a venue-edge book capture older than 3h at decision time is NO reference)
- `desk_policy.venue_edge`: when the row's `market.captured_at` is more than 3h (`VENUE["maxBookAgeH"]`) before the Desk's as-of, the row is PASS / `noref` ("books captured X.Xh ago > 3h — no reference"). It is excluded, not stale-flagged: no side, no divergence, `stale_book_zone` false. This is the same class as absent books. The Next-24h card (`window_venue`) obeys the same rule.
- Exactly 3h and fresher are judged as before. Review on #250: a capture AFTER the decision time is unavailable, giving PASS / `noref`. An UNKNOWN age (missing or unparseable `captured_at`) also gives PASS / `noref` under law 4. Ratified by the architect (2026-10-02): "UNKNOWN capture age = NO REFERENCE — ratified, no longer provisional."
- tests/test_venue_stale_books_91.py (6) pins >3h, exactly 3h, missing, malformed, future and at-decision captures.
- The desk golden is unchanged (810/810). The battery's fixtures now carry a fresh capture time; the deleted JS never read it. The Cockpit verify fixtures do the same.

## 2026-10-02 (#249, closes #130: the export's `kalshi_exec_cost` alias is RETIRED)
- **Announcement (ruling (1) on #129):** exports no longer write `kalshi_exec_cost`. `venue.kalshi_exec` and `KALSHI_EXEC_NULL` drop it; the taker cost is `exec_cost_taker` (with `exec_cost_maker`, and the `_away` pair on two-way rows). Condition met: the published Cockpit was republished twice after #88 (the #178 republish and the post-F1c republish).
- The pre-split fallback goes from the Python Desk (`desk_policy`, `kExec.cost`) and from `tools/cockpit.html`. The LEDGER's own `kalshi_exec_cost` / `_maker` fields on call records are not the alias and keep their taker/maker meaning.
- Receipts and verify scripts read `exec_cost_taker`. The desk golden battery maps its pre-split rows (alias only) to `exec_cost_taker`, which is equivalent under the deleted JS's `exec_cost_taker ?? kalshi_exec_cost`: all 810 frozen calls still match row for row.

## 2026-10-02 (#248: UNL shadow engine — intl-elo-v2 greyed in its confirmation window; daily intl chain)
- `export-unl-predictions`: intl-elo-v2 three-way rows for scheduled competitive internationals (36h), `engine: model_shadow`, labelled "PASS — confirmation n/60"; multipliers read from the registry run record; refuses until the run record + PASS are spliced. Never a Desk call, never in the Prediction table.
- `unl-shadow-grade` (top pick vs the three-way close) and a RESULTS.md shadow section; `intl-elo-confirm [--record --ruling]` scores the declared window (first 60 competitive after the verdict) predict-then-update vs naive − 0.010.
- Host chain `intl-daily` (07:20 UTC, `sp-intl-daily.timer`): `intl-sync --since {today}` → `intl-venue-sync` → `export-unl-predictions`. `intl-sync` keeps friendlies of senior sides already stored (incremental sync). Cockpit shadow card shows three-way picks ("Draw") and each model's gate label. tests/test_intl_shadow.py (7), test_intl_history (+1).
- Review on #248: the confirmation COHORT is the first 60 eligible FIXTURE ids whatever their status (never chosen from results), frozen once in the registry (`intl-elo-confirm --freeze-cohort`, `registry.freeze_confirmation_cohort`, sidecar `<id>.cohort.txt` + sha256). `record_confirmation` refuses any scored set that is not exactly the frozen cohort; a pending or unscoreable fixture leaves the read incomplete, never replaced by game 61. tests: registry (+2), intl shadow (reproduction of the review's case).
- ARCHITECT 2026-10-02 (2): a CANCELLED or ABANDONED cohort fixture is RELEASED. It is replaced by the next eligible fixture after the cohort (61st, 62nd …) and recorded as a substitution with its reason and evidence (`registry.substitute_cohort_fixture`, `intl-elo-confirm --substitute`). A postponed, scheduled or unplayed fixture is never swapped. The frozen file never changes; the effective cohort applies the substitutions, and `record_confirmation` reads against it. tests: registry (+1), intl shadow (+1).

## 2026-10-02 (#247: nhl-v8 + intl-elo-v1 run records and FAIL verdicts in the registry)
- The laptop run records of nhl-v8 (0.6963; 1,394 ids) and intl-elo-v1 (FAIL on calibration; 392 ids) are spliced with their ids files (sha verified) and FAIL verdicts recorded verbatim. NHL 2025: 8 reads, retired (a ninth declaration is refused). intl test set: 1 read.

## 2026-10-02 (#246: NHL shadow engine switches to v7, v1 as reference)
- `export-nhl-predictions`: the shadow rows are `nhl_elo_v7_xg_margin_no_na` ("FAILED 0.6885 vs 0.6866"), each with a `reference` block carrying `nhl_elo_v1`'s probability; the fit receipt counts xG updates vs goal fallbacks. `nhl-shadow-grade` / RESULTS.md show v1's pick-vs-close beside v7's.
- `nhl-daily`: `nhl-shot-sync` (yesterday..today, the NHL's free API) runs before the shadow export so live games carry xG. tests/test_nhl_shadow.py updated (+1).

## 2026-10-02 (#244: intl-venue-sync — fix the crash on /venues payloads with None fields)
- `src/ingestion/intl_venues.py`: the law-1 key receipt counts keys (`Counter.update(v.keys())`), not dict values, which crashed on a None field and would have summed numeric ones. Regression test on a real-shaped payload. A re-run with the same `--venues-dir` replays the saved responses.

## 2026-10-02 (#243: per-PR ledger fragments — CHANGELOG/BACKLOG are compiled, never edited by a PR)
- `python scripts/ledger.py compile [--commit] [--dry-run]` folds `changelog.d/<PR>-<slug>.md` and `docs/ledger/entries/<date>-<slug>.md` into CHANGELOG.md / BACKLOG.md newest first, deletes them, and commits the fold alone; `ledger.py pending` counts what is uncompiled.
- CI `fragments` job: a PR that edits CHANGELOG.md / BACKLOG.md (except a pure compile) or lacks its fragments fails. The tag ritual compiles before the release notes; `sp_deploy` reports uncompiled fragments in the deployed tag (read-only). tests/test_ledger_fragments.py (6). Retires the merge-up ritual.

## 2026-10-02 (#220: intl-elo-v2 declared — train-only fit + neutral rule v3)
- `docs/specs/intl-elo-v2.md` + registry `intl-elo-v2`: (a) c multiplier and global K multiplier fitted on the training stream only (48-pair declared grid); (b) neutral v3 (venue country ≠ home country). Same bar/bands/test set; train-only attribution printed.
- `python cli.py intl-venue-sync` (route B; new table `intl_match_venue`) and `intl-elo-backtest --candidate v2`. tests/test_intl_elo_v2.py (5). intl-elo-v1 FAIL is recorded once its laptop run record is spliced.

## 2026-10-02 (#153: NHL v8 declared — train-only fit of scale and k; the 2025 test set retired after it)
- `nhl-backtest --candidate v8`: v7's xG + Elo with the logistic divisor and k fitted by maximum likelihood on 2024 only over the declared grid (56 pairs; tie → (400, 6)); chosen and printed before any 2025 read. Registry `nhl-v8` declared; doc `docs/specs/nhl-xg-v8.md`.
- Doctrine: `registry.RETIRED_TEST_SETS` — after v8 the NHL 2025 test set refuses any declaration or run; later NHL candidates declare 2026-27 (≥ 600 games). `docs/REGISTRY.md` updated. (v6/v7 FAIL records: #239.)

## 2026-10-02 (#153: nhl-v7 run record + FAIL verdict in the registry)
- The laptop's v7 run record (1,394 scored ids, sha verified; the same set as v6) is spliced with `docs/registry/ids/nhl-v7.txt`; FAIL recorded verbatim. NHL 2025: 7 prior reads. v7's stored prior_read_count (5) is kept as written.

## 2026-10-02 (#153: nhl-v6 run record + FAIL verdict in the registry)
- The laptop's v6 run record (1,394 scored ids, sha verified) is spliced into `docs/registry/experiments.json` with `docs/registry/ids/nhl-v6.txt`; the FAIL verdict is recorded verbatim (status closed). NHL 2025: 6 prior reads. tests/test_nhl_v6_record.py.

## 2026-10-02 (#220/#240: intl-elo-v1 known limitation declared)
- `docs/specs/intl-elo-v1.md` and the registry entry carry the declared limitation (neutral-venue play-offs/finals priced with the home edge; v2's 10% check vacuous under the HOME ruling). The fix, v3 (venue country), is for the next candidate.

## 2026-10-02 (#220: intl-elo-v1 preflight rulings — v2 check gated, v3 pre-declared)
- `intl-elo-backtest`: v2's RULE CHECK printed on the same home-and-away denominator and gated at 10% (a breach refuses); a city hosted only by this competitive match is HOME (ruled); `rule_check_v1/v2` recorded with the run. Gap games update ratings (pinned by a test).
- intl-neutral-v3 (venue country ≠ home country) pre-declared; `scripts/intl_venue_route_probe.py` reports its cheapest route from the saved responses with zero calls.

## 2026-10-02 (#153: NHL v6 FAIL; v7 declared — the xG `na` level removed)
- v6 ruled FAIL (0.6886 vs 0.6866; calibration FAIL; shot information +0.0023). The verdict is recorded once the laptop's run record is committed.
- `docs/specs/nhl-xg-v7.md` + registry `nhl-v7`: v6 with the xG model's `na` shot-type level removed (a label leak: missing shot type occurs on ~0.3% of goals); untyped events take the baseline level. Same bar, splits, gate and confirmation plan. `nhl-backtest --candidate v7` (one recorded run). tests/test_nhl_xg_v7.py (4); the nhl-v6 repo test accepts the coming run record.

## 2026-10-02 (#153: NHL shot coverage receipt — both denominators, thresholds on the gate stream)
- `nhl-shot-coverage` / the `nhl-shot-sync` receipt report all finished games (preseason included; not judged) AND the v6 gate stream (nhl-backtest's own stream). P1/P6 thresholds apply to the gate stream (ruled 2026-10-02). Regression test with the ruling's numbers. v6 may run.

## 2026-10-02 (#234 rulings: CNL_Q K 40; intl-neutral-v2 leave-one-out)
- `intl_elo`: CNL_Q is Nations League class (K 40). v2 host-city sets are built from home-and-away competitions only, with each match left out of its own set; the "hosted only this match" count is printed. Doc, registry and tests updated (still unrun).

## 2026-10-02 (#220 lane 2: intl-elo-v1 RATIFIED; harness built, not run)
- `docs/specs/intl-elo-v1.md` RATIFIED (draws S=0.5 with max(margin,1); no regression; unknown venue +100; RULE CHECK 10% with the pre-declared intl-neutral-v2; naive symmetric at neutral). Registry entry carries `ratified`; still unrun.
- `python cli.py intl-elo-backtest [--preflight]` (`src/walters/intl_elo.py`): registry refusal before any data load; walk-forward Elo with the soccer Elo→Poisson three-way; naive − 0.010 + bands; RPS; one recorded run. Refuses while CNL_Q's K class is unruled (#234). tests/test_intl_elo.py (11).

## 2026-10-02 (#230: CONCACAF Nations League codes — intl-sync refused on id 808)
- Adapter codes `CNL` (536, CONCACAF Nations League) and `CNL_Q` (808, its 2018 qualification), ruled. The ingest codes both by name; the provisional, never-written `CONCACAF_NL` is renamed `CNL`. `intl-inventory` includes both. A regression test reproduces the refusal.

## 2026-10-02 (#220 lane 2: international Elo v1 declared — frozen, not run, awaiting ratification)
- `docs/specs/intl-elo-v1.md`: the frozen pre-commitment (H +100 / 0 at derived-neutral; K 20/40/50/60 by class; ln(|margin|+1) with our Elos' 2.2 gap factor; the soccer Elo→Poisson draw mapping with ρ −0.10; train 2018–2024-08, test UNL 2024/25 + WCQ_EU 2025-26; bar = naive − 0.010; bands; RPS). Five RATIFY items, including the draw update (ln(0+1) = 0 would freeze ratings on every draw).
- Registry: `intl-elo-v1` declared (unrun, 0 prior reads) with a 60-game executable confirmation plan. tests/test_intl_elo_declaration.py.

## 2026-10-02 (#230: national-team history ingest — UNL lane reopened, data-ready)
- `python cli.py intl-sync` (`src/ingestion/intl_history.py`): the ruled set from 2018 (WCQ all confederations, Euro + qualifiers, Nations League, friendlies). Leagues are discovered by name and coded by name (new: WCQ_IC, UEFA_EURO_Q, CONCACAF_NL); an adapter-id clash or unmapped name is refused. `/fixtures` + `/teams` per competition-season; `--max-calls`, `--dry-run`, `--save` / `--from-dir`; never touches data/.
- Senior-team filter: a fixture is kept only when both teams play in UNL / WCQ_* / UEFA_EURO / UEFA_EURO_Q; exclusions are printed.
- New table `match_neutral_derived`: `neutral_derived` under the stated rule (venue city vs the home team's ground city, same competition-season; NULL when unknown), with both cities kept. Never a provider fact.
- `python cli.py intl-coverage`: the per-competition-season receipt with the rule's home-and-away sanity check. tests/test_intl_history.py (5).

## 2026-10-02 (#228: national-team source probe — read-only; UNL lane #220 SUSPENDED-PENDING-DATA)
- `scripts/intl_source_probe.py`: can API-Football serve national-team history 2018-present (WCQ all confederations, Euro + qualifiers, Nations League, friendlies)? League ids are discovered by name and cross-checked against the adapter; a coverage receipt per competition-season (scored, 90-minute, venue shares, neutral keys detected, never inferred); `--plan` cost in calls; `--max-calls` budget refusal; `--save` / `--from-dir` replay; never touches data/.
- tests/test_intl_source_probe.py (5, synthetic replay; the API is never reached).

## 2026-10-02 (#153: NHL v6 declaration RATIFIED — the update direction follows the xG margin)
- `NHLEloV6.update`: the result term is the sign of xG_home − xG_away (1 / 0; an exact tie moves nothing); the magnitude is |xG margin| through the same ln(margin + 1); the mov gap is taken from the xG winner. The actual result only scores the prediction. Games without xG fall back to v1 on goals (counted).
- `docs/specs/nhl-xg-v6.md` is marked RATIFIED with the ruling quoted; the confirmation window is ratified. The registry entry `nhl-v6` is updated before any run (still `declared`, unrun).
- New test: a home team that wins on goals but loses on xG moves DOWN.

## 2026-10-02 (#153 part 2: NHL v6 declared — frozen, not run)
- `docs/specs/nhl-xg-v6.md`: the frozen declaration under the corrected manifest (#210), awaiting ratification. The event code is eligibility/target only; shot type is a nullable feature; rules R1–R7 (blocked, shootout, side, situation, empty net, coordinates, orientation); fit on 2023-24 only; v6 = v1 with the margin input = |xG_home − xG_away|; rolling team xG is reported only; same gate; a proposed confirmation window.
- `src/models/nhl_xg.py` (rules, IRLS logistic fit with window assertion, game xG, rolling team xG) and `NHLEloV6` (`src/models/nhl_elo.py`).
- `nhl-backtest --candidate v6`: refused unless the registry holds `nhl-v6` and it has not run (the refusal comes before any data load); asserts the fit ended before the first train game; reports v1 beside v6, shot information, RPS and the exclusions; records the ONE run in the registry.
- Registry: `nhl-v6` declared (status declared; 5 prior reads of NHL 2025 shown). tests/test_nhl_xg_v6.py: 7 tests, including the no-same-game-leakage proof.

## 2026-10-02 (#212 review fix: the confirmation is executable and cannot be recorded early)
- `declare()` requires a structured `confirmation_plan` {n_games, metric, bar, must_beat_reference, reference} (`check_plan`).
- `record_confirmation(eid, scored_ids, result, ruling)` executes the plan and computes CONFIRMED/NOT_CONFIRMED (metric <= bar and, when required, strictly below the reference; a tie fails). The scored ids are stored in a `<id>.confirm.txt` sidecar with sha256, and the result is kept.
- It refuses: no PASS; fewer games than planned; any game starting before the verdict; any game from the scored test set; a missing metric or reference.
- `production_allowed()` also requires a complete confirmation record. Regression tests: immediate confirmation fails (fails on the old code: 3 failed).

## 2026-10-02 (#220: UNL lane step 1 — national-team results inventory)
- `src/walters/intl_inventory.py` + `python cli.py intl-inventory` (read-only). For UNL, WC, UEFA_EURO, WCQ_* and FRIENDLIES_INT, per competition and season: finished+scored matches, date span, teams, raw home/draw/away shares and venue completeness. Also each UNL team's prior international results before its first UNL match.
- No neutral site is inferred (law 4). tests/test_intl_inventory.py.

## 2026-10-02 (#176: NCAA source probe — read-only, row-level)
- `scripts/ncaa_source_probe.py`: CollegeFootballData (CFBD) `/games` by year, FBS by default. Field names are discovered from the first record and printed; a missing required field refuses the run.
- Each completed game is joined to OUR NCAA matches through the shared matcher (ambiguity refused), in the source's orientation, else swapped. It compares labels and scores (in our orientation); neutral games are counted separately and never relabel ours.
- It reports the source's home rate and margin (non-neutral / neutral), ours on the same joined games, the join rate, swapped / score-mismatch / unmatched samples and the access receipt (HTTP status, rate-limit headers).
- Key from `CFBD_API_KEY` (.env, never printed); `--from-file` for offline re-runs; refuses `--save` under data/; writes nothing. tests/test_ncaa_source_probe.py: 3 tests.

## 2026-10-02 (#191: F1c — the Cockpit renders desk files only; the in-browser policy is deleted)
- **Golden first** (a separate commit, before any deletion): `scripts/desk_golden_capture.py` drove the pre-F1c `tools/cockpit.html` (sha256 37250ba4…, = main) on the seeded battery (clock and counts pinned, America/New_York), the 600-slate parlay fuzz and the toFixed sample, writing `tests/golden/desk_js_v1_1.json.gz`. `tests/test_desk_golden.py` and `scripts/desk_parity_verify.py` check the Python Desk against it row for row with no browser (14/14).
- **`tools/cockpit.html`:**
  - Deleted: `computeCall`, `valueSide`, `venueEdge`, `kalshiOnlyRef`, the parlay builder, `execFacts`/`execEdgeHTML`/`deskCostFor`/`execEdgePP`, and the policy constants (POLICY, BASE_UNITS, the policy halves of VENUE/PASSCLASS/KALSHI_ONLY).
  - Prediction and fixtures files without `desk` blocks are **REFUSED whole**: "REFUSED n file(s) without desk blocks (…) — export with --desk". `model_shadow` and `desk_parlays` files keep their own paths.
  - Tickets come only from the `desk_parlays` file.
  - Kept: the ledger, fills, audits, rendering and the export-quote accessors the ledger capture reads.
- **The Next-24h card's venue verdict** is stamped by `window.py` as `desk_venue` via the new `desk_policy.window_venue`; the card renders it.
- **Verifies:** `cockpit_render_verify` is rewritten: rendered == the deleted JS's frozen outputs in all three scenarios, plus tamper, refusal, no-parlays and version-mismatch checks. 13 legacy-path verifies now load through `scripts/cockpit_desk_files.upload()` (the Python Desk with the page's own ledger-summary counts, plus the desk_parlays file). `cockpit_window_verify` stamps `desk_venue`. All 18 verifies are green.

## 2026-10-02 (#212: experiment registry + confirmation doctrine)
- `src/walters/registry.py` and the git-tracked ledger `docs/registry/experiments.json`. Each candidate goes through declare (before any run; the confirmation window is required), run (once per id; scored ids in a sidecar `docs/registry/ids/<id>.txt` with count and sha256; prior reads computed), verdict (verbatim), then confirmation. `production_allowed()` encodes the doctrine: a PASS is not production until a declared confirmation window closes CONFIRMED.
- Seeded with the pre-registry verdicts, unchanged: NHL v1–v5, S19, DC-fit, S14 stage 2 and cups fix-v2. Their ids are "not recorded" and are never reconstructed. NHL's 2025 test set shows 5 prior reads.
- `python cli.py registry [--id ID]` (read-only). docs/REGISTRY.md. tests/test_registry_212.py: 5 tests.

## 2026-10-02 (#153 part 1: NHL-xG shot-event ingest)
- New table `nhl_shot_events` (additive; `init_db` creates it). One row per shot-type play (shot on goal, missed, blocked, goal) from api-web play-by-play, 2023-24 onward. Raw values only: event type (stored for eligibility and target only, never a feature, per #210), nullable shot type, x/y, shooter, goalie in net (NULL = empty net or absent), situation code, period, time, zone, home defending side, and shooter side vs play-owner side.
- `src/ingestion/nhl_shots.py`: discovery-based parsing (law 1); links through the goalie-sync mapping, else the refusal-on-ambiguity matcher; upserts without deleting and never blanks a stored value on refetch; relinks unlinked rows; coverage receipt.
- CLI `nhl-shot-sync` and `nhl-shot-coverage`. The receipt reports P1–P6 against the probe's frozen FEEDABLE bars (95/95/90/95/90, plus every season).
- tests/test_nhl_shot_events.py: 3 tests.

## 2026-10-02 (MLB odds history: snapshot per sync, close = last pre-first-pitch session)
- `sync_odds_mlb` (bulk window and rollover fallback, via `_mlb_store_odds`):
  - A game at or after first pitch is never touched: no wipe, no insert. The pre-game session survives and no in-game price is stored.
  - A pre-game sync replaces the current board and APPENDS one book-consensus `OddsSnapshot` (1X2, `api_baseball`, `n_books` = complete books, #207 contract), as NFL's sync does.
  - The sync's log line counts snapshots and post-first-pitch games kept.
- Grading close (`close.grading_close`): the odds table's last pre-kickoff session under the contract; when it cannot price, the last COMPLETE pre-kickoff book-consensus snapshot session (`close_from_snapshots`; Kalshi, in-game and incomplete sessions never count). Used by evaluate, its M11b backfill (which re-grades NULL-CLV outcomes), clv-restate and the results-tally cohorts.
- `capture-odds` no longer writes its own pooled 1X2 snapshot (the sync writes it under the contract) and is bounded to games before first pitch (#174).
- New `close-probe --match ID` (read-only receipt). tests/test_mlb_odds_history.py: 5 tests, including the PHI@ATL shape re-graded from the snapshot.

## 2026-10-01 (#207: P0-2 the close contract)
- `close_1x2(rows, before, outcomes)` now requires the outcome set: binary HOME/AWAY or 3-way HOME/DRAW/AWAY. `outcomes_for(sport)` is the one mapping (soccer is 3-way, every other sport binary, as read from the adapters).
- A book counts only with a COMPLETE same-session set. Each complete book is de-vigged on its own, then the books are averaged. With no complete book the result is UNPRICED: `fair` is None and `missing` names each quoted book's absent legs. `books` counts complete books, `books_quoted` every book in the session. `priced(cl)` is the caller check.
- All 11 call sites pass the outcome set and check `priced`: evaluate CLV, the M11b backfill, the market blend, NFL export/grade (3 sites), nhl_shadow, miss_analysis, clv_restate (2 sites) and the sync_odds snapshot.
- results-tally reports the **verified-close** CLV cohort as the headline and the **retained-legacy** cohort on its own line, never pooled (`clv_restate.clv_cohort`, read-only).
- tests/test_close_contract_207.py: missing draw, one-sided, mismatched coverage, post-kickoff replacement, same-session completeness, per-book de-vig, cohorts, no pooled headline.
- **Exports (ARCHITECT-RULE 2026-10-01):** the MLB/soccer prediction export's market block and the fixtures export (incl. the window card's rows) use the same contract, so there is one definition.
  - `bookmaker_count` now means complete books; `bookmaker_count_quoted` is added.
  - `overround_pct` is the mean per-book booksum.
  - An unpriced close ships the no-1X2 shape plus an additive `close_unpriced` receipt. Fixtures receipts gain a `close_unpriced` count.
  - `scripts/export_close_compare.py BEFORE AFTER` is the read-only receipt for a real export of each kind.

## 2026-10-01 (#209: P1-1 legacy soccer improve refused)
- `training.improve(sport=SOCCER)` raises `LegacySoccerImproveRefused` before its first write (`evaluate_finished`). The message points to `soccer-backtest` (the chronological, market-scored gates) with `set-soccer-config`, and to `soccer-refresh`.
- `cli.py improve --sport soccer`, and the bare `improve` (whose default is soccer), print the refusal and exit 2. The admin web job returns "REFUSED: …". MLB is unchanged, including the host chain's `improve --sport mlb --hold-on-pass`.

## 2026-10-01 (#204 / #175: Kalshi in-play guard on OUR start time — merged in #205; record backfilled)
- `sync_kalshi_mlb` (the shared path for MLB, NFL, NHL and NCAA): the in-play guard now runs after matching and checks the matched game's `utc_date`, not the market's `occurrence_datetime`. A game with no start time on record is never treated as pre-game.
- Gate 1 (time) has two anchors: games within 5h of the occurrence OR within 2h of the ticker's ET start stamp (`KalshiAdapter.ticker_start`, the M13 parse). The fallback for a missing occurrence is kept.
- `sync-kalshi --date-to D` covers the whole UTC day D. The window's `--date-to {tomorrow}` had dropped first pitches after 00:00Z (#175).
- tests/test_kalshi_inplay_guard.py: 4 tests. Run against the old code, they reproduce "matched 0 / in-play 2" and the stored in-play leak.

## 2026-10-01 (#213: review hygiene)
- RESULTS.md is marked REGENERATED, NOT AUTHORITATIVE IN GIT: in the `results-tally` header (every regeneration), README, docs/CLI.md, and a banner on the stale committed copy (2026-09-17).
- #83 re-closed with an `ARCHITECT`-opening comment (S19 REJECT, 2026-09-30). #98's description is refreshed: #167 met its reopening condition in code, and it waits on a live PL receipt.

## 2026-10-01 (#206: P0-1 maker fee no longer double-counts the 25%)
- `venue.KALSHI_FEE_M`: game series (NFL/NHL/NCAAF/EPL) maker M changes from 0.25 to 1.0; MLB pre-live stays (0.5, 0.5). The maker discount is the 0.0175 rate (= ¼ × 0.07), applied once. Before: NFL maker, 100 contracts at 50c, cost $0.11. Published: $0.44.
- Cockpit `FEE_M_BY_FAMILY` (the fill classifier) gets the same fix, and the policy card text is corrected. `scripts/kalshi_fee_fill_receipt.py` reads the fixed table.
- Desk maker costs re-state through the export's `exec_cost_maker`: +0.2 to +0.3pp per contract on a 10-lot (NFL join 0.56: 0.561 → 0.564). K2 stays informational: no call, unit or tier effect.
- tests/test_kalshi_maker_fee_published_206.py (published-schedule fixtures: $0.44 and $1.75 per 100 at 50c; MLB taker $0.04–$0.88, maker $0.01–$0.22). Two older tests are re-derived by hand. Two Cockpit verifies get corrected synthetic fees and costs.

## 2026-10-01 (#201: seed-thread links recorded)
- The first `discussions` / `list` dispatch receipt is on #201. Discussions are enabled with six categories. The four seed threads are #197 and #198 (Q&A), #199 (Ideas) and #200 (Receipts).
- docs/LEDGER.md gains a table of the posted seed threads. The seed file's header points to it.
- The `list` call ran with the token's current scopes. `write:discussion` is added only if the first `post` or `reply` is refused.

## 2026-10-01 (#201: Discussions posting via the ledger workflow)
- `ledger.yml` + `scripts/ledger.py`: a workflow_dispatch mode
  `discussions`. `list` (the default) prints categories and thread links;
  `post` sends a `docs/discussions/` file to a named category; `reply`
  answers by thread number. It uses `LEDGER_PROJECT_TOKEN`, and nothing
  posts without a dispatch that names the file.
- `tests/test_ledger_discussions.py` (5).

## 2026-10-01 (#170: Discussions — Receipts category + S14 receipts post)
- `docs/LEDGER.md` adds the Receipts category. Discussions setup is all
  operator steps (Code has no Discussions tool).
- `docs/discussions/seed-2026-10-01.md`: four categories, and post 4 is the
  S14 residual receipt (+1.17 live vs +0.18 pooled).

## 2026-10-01 (#192: one injured QB = one news item)
- Card pager: a QB's injury status change pages ONCE per player, listing
  every game his team has in the window (new class `qb_news`). Half units
  per game are unchanged.
- B-track shadow logs `qb_shared_risk` (a QB flag spanning two or more live
  games), with no cap change. It appears in the `desk-parlays` CLI, the
  parlay card and the ledger tally.

## 2026-10-01 (#193 B-track cross-book rules, shadow; #192 QB finding)
- `desk_policy.b_track_shadow`: an exposure cap of 1.25u per team-outcome
  and ticket dedup, pre-committed and shadow only. `desk_parlays` reports
  what the rules would cut and the tickets v1.2 would build.
- Cockpit: the parlay card shows "exposure-capped N · deduped N" and marks
  the would-cut tickets. Logged legs carry `b_shadow_cut`. The ledger keeps
  a per-slate tally, and the P&L block gets the B-track shadow line (n/30
  slates, net of the would-cut tickets).
- `scripts/cockpit_btrack_verify.py` (8 checks). Finding #192 (QB flags
  counted per game, not per player).

## 2026-10-01 (card page content, F2 slice 1; #189 NCAA label)
- Card pager: every line and digest row reads "competition · away @ home ·
  kickoff ET · model pick prob (tier) · reference · edge · Desk call ·
  flags". Market-only rows say so. Each delta adds a "↳" line.
- New delta classes "model updated" and "call changed". The digest lists
  Desk calls first.
- NCAA games show "NCAA", not the "NFL" family (#189).
- `tests/test_card_page.py` (6).

## 2026-10-01 (#187: MLB start times — statsapi kept, card flags unconfirmed, audit)
- `mlb_apisports`: the api-sports fallback never overwrites a
  statsapi-sourced start time. Disagreements are receipted and stamped on
  the row.
- Window card / pager: MLB rows whose time statsapi has not confirmed show
  "⚠ time unconfirmed".
- `mlb-time-audit`: read-only statsapi vs api-sports postseason start-time
  comparison (laptop).

## 2026-10-01 (#151 F1b: the Cockpit renders desk calls from the file)
- `tools/cockpit.html`: rows from `--desk` exports are rendered from their
  `desk` blocks (calls, value shadows, venue, exec text); parlay tickets
  come only from a loaded `desk_parlays` file. The summary names the source
  and flags legacy rows or a policy-version mismatch. Legacy files without
  desk blocks still compute in the browser, labelled as such.
- `desk_policy`: unrounded desk numbers, `desk.venue` on every row, raw
  ticket edge.
- `scripts/cockpit_render_verify.py`: computed vs rendered identical
  (calls, shadows, venue, tickets, table text, ledger capture); the policy
  functions are never called in render mode. 16/16.

## 2026-10-01 (#183: parlay-leg audit in the Cockpit ledger)
- "Audit parlay legs (#183)" checks each logged parlay leg against the
  Desk call of its game in the export files loaded for the leg's day. A
  ticket with a leg that was not a play is flagged "leg not a play
  (#183)" and left out of the P&L. Nothing is deleted.
- `scripts/cockpit_leg_audit_verify.py`: 9 checks.

## 2026-10-01 (#151 F1: parlays ported; #183 parlay legs fixed)
- `tools/cockpit.html`: parlay legs come from the Desk's non-PASS calls.
  Before this, a fixtures file loaded ahead of a predictions file could
  build tickets from PASS rows (#183).
- `desk_policy.build_parlays` + `desk-parlays FILES…` write
  `exports/desk_parlays_<date>.json` (cross-sport tickets in one file).
- Parity verify: tickets row-for-row in every run, plus a 600-slate parlay
  fuzz (889 tickets identical). 31/31.
- #181 (NHL 0.5u on PASS) is parity-preserved until the v1.2 bump, as
  ruled.

## 2026-10-01 (#151 F1: the Desk's call in the export, off by default)
- `src/walters/desk_policy.py`: a Python port of the Cockpit Desk v1.1, the
  single source of truth once parity is proven. `--desk` (or
  `SP_DESK_CALLS=1`) on `export-predictions` / `export-nfl-predictions` /
  `export-fixtures` adds `desk` per row and `desk_meta` (as_of, counts).
  Off by default; with it off, files are unchanged.
- Cockpit: "Export ledger summary" writes `ledger_summary.json` (graded
  counts per rule), which the export reads when present; otherwise it
  counts 0, the cautious side.
- `scripts/desk_parity_verify.py`: JS vs Python row-for-row, with the clock
  and counts pinned (synthetic battery 16/16; real exports by argument).
- `tests/test_desk_policy.py` (8 tests). Finding #181 (NHL PASS rows can
  show 0.5u).

## 2026-10-01 (#178: ledger kickoff audit in the Cockpit)
- `tools/cockpit.html`: every position's claim, execution and reprices are
  checked against the true UTC kickoff. Post-kickoff prices are flagged
  "post-kickoff (tz bug)" and left out of the P&L, which falls back to the
  last pre-kickoff reprice or the claim, or excludes the position. Stored
  fields are never rewritten; flagged positions carry a `tz_audit` mark.
  The P&L block shows a one-line count.
- Reprice history is now logged per position (`reprices`); before this it
  was overwritten on each re-log.
- `scripts/cockpit_ledger_audit_verify.py`: 19 checks.

## 2026-10-01 (#178: Cockpit reads kickoff times as UTC)
- `tools/cockpit.html`: new `utcMs()` reads the exports' naive `utc_date`
  as UTC. The capture window, Kalshi-only T-60, the venue in-play check
  and KO / re-run-by were shifted by the viewer's UTC offset in any non-UTC
  browser. The live artifact needs republishing.
- `scripts/cockpit_utc_verify.py`: 28 checks across four timezones
  (main: 14/28; fixed: 28/28).

## 2026-10-01 (#163 verdicts, NCAA source finding, NHL 2024 Utah alias, H2 rehearsal)
- #163 soccer candidates, both REJECT, production unchanged: DC-FIT
  (−0.0003 out of sample); S14-STAGE2 (criterion (i): the +1.17 offset
  overshoots the pool's +0.18 residual to −0.99). No re-tune.
- NCAA: the provider's current 2025 labels match ours, so the fault is at
  the source. The gate stays SUSPENDED-PENDING-DATA and the banner now
  says so. The offseason alternative-source probe is #176.
- `nhl_goalies.NAME_ALIASES`: the 2024 doubled form "Utah Utah Hockey Club"
  maps to Utah Mammoth / Utah Hockey Club. Re-sync owed; the 2024 target
  is >= 90%.
- H2 dry run PASS recorded as the cutover rehearsal receipt.

## 2026-10-01 (#170: GitHub Discussions as the input channel)
- `docs/LEDGER.md`: the Discussions fence (threads are data, never rulings;
  adoption = ruling + Issue with `Source: Discussion #N`), the RFC rule
  (name the gate), and ledger rules 5 (`Refs #N` only) and 6 (ruling closes
  start with ARCHITECT).
- `docs/discussions/seed-2026-10-01.md`: three seed threads for the
  operator to post.

## 2026-10-01 (#82: snapshot retention design, for ruling)
- `docs/specs/snapshot-retention.md`: proposed retention for odds/Kalshi
  snapshots. Raw rows are kept 30 days; first captures and closes are kept
  forever; hourly rollups are kept beyond that. It includes a reader-by-reader
  impact check, a DDL sketch and safety design. Design only; no code
  deletes anything.

## 2026-10-01 (#166: H2-PREP — cutover orchestrator, dry run, runbook)
- `deploy/hosting/sp_cutover.py`: the ruled H2 sequence (preflight, pause,
  install, flip, resume, receipt), each step receipted and refusing on
  failure. `--dry-run --scratch DIR` runs it against a scratch copy.
- `scripts/h2_dry_run.py` proves the sequence on a scratch DB.
- `docs/specs/h2-cutover-runbook.md`: the operator steps, the
  fresh-fingerprint compare, the MLB doubleheader/postponed waivers and
  rollback.

## 2026-10-01 (audit rulings: NCAA gate suspended + resync-diff; NHL Utah alias + unlinked listing)
- `resync-diff` (read-only): compares the provider's current listing with
  our stored rows (labels, scores, home rate on both copies).
  `sync-matches` never rewrites home/away on existing rows, so a re-sync
  cannot repair labels and could flip stored results.
- `ncaa-backtest` announces the NCAA gate as SUSPENDED-PENDING-DATA; v1's
  verdict is void.
- NHL goalie mapping: "Utah Hockey Club" ↔ "Utah Mammoth" alias.
  `nhl-goalie-audit --list-ours` lists every one of our unlinked games with
  the nearest API game, its delta and a named cause.

## 2026-10-01 (#167 CORRECTION: the soccer/NHL "close" was an average of every capture)
- **Correction.** The general odds sync (soccer, cups, NHL) appended a full
  book set on every run. Every reader then de-vigged ALL of a match's rows
  at once, so the "closing price" behind soccer CLV, NFL grading's close,
  the NHL shadow close and the prediction export's market reference was a
  mean over every capture, not the close. **Soccer CLV figures published
  before 2026-10-01 are not closing-line value**; they are re-stated by
  `clv-restate --apply` and `results-tally`.
- The close is now ONE definition (`src/walters/close.py`): the last
  pre-kickoff capture session, latest row per book. In-game prices are
  never the close; MLB rollover games captured after first pitch become
  unpriced.
- The odds sync now replaces per match, stores the totals/spread line, and
  appends history to odds_snapshots.
- New: `odds-audit` (read-only receipt) and `clv-restate` (dry-run by
  default; `--apply` only with a verified backup).

## 2026-10-01 (#163: soccer candidates — Dixon-Coles rho fit, S14 Stage-2)
- `soccer-backtest --candidate dixon-coles-fit` (backtest-only): ρ fitted
  on PL 2023/24 only, frozen, gated against production's ρ on PL 2023/24 to
  2025/26 pooled.
- `soccer-backtest --candidate s14-totals` (backtest-only): +1.17 goals on
  uncertain-winner games. The verdict needs both the improve rule and S14's
  frozen Stage-2 criteria.
- Both are pre-committed, write nothing and change no production model.

## 2026-10-01 (#159/#160/#161: postseason sizing; kalshi-only reference; Desk kickoff + n/30)
- MLB prediction exports carry `stage` (`regular` / `postseason` from our
  statsapi gameType mapping; null when unknown) and `stage_raw`.
- Desk: postseason rows play at half units until 30 postseason calls are
  graded.
- Desk: KALSHI-ONLY provisional reference (ruled). Model sports with no
  books at T-60, a two-sided Kalshi market (spread ≤ 2c) and a series in
  the fee table use the Kalshi mid as the reference, are flagged
  "kalshi-only", and size at 0.5 ×. The ledger records
  `reference: kalshi_only`. Review at 30 graded calls.
- Desk rows show the kickoff and "re-run by" (T-60). The policy card shows
  "graded n/30" for value shadows, postseason and kalshi-only calls.
- Finding logged: NHL venue gaps ≤ 3.2pp over 18 games; threshold unchanged.

## 2026-10-01 (#157: morning chain in two network phases; compare_exports --since)
- `docs/CLI.md`: the laptop morning chain runs in two phases. Phase 1 runs
  the statsapi steps under the VPN. Then quit the VPN and bring Tailscale
  up. Phase 2 runs the host pull/compare under Tailscale.
- `compare_exports.py --since N` (default 3) compares only exports dated
  within the last N UTC days, plus undated files, so settled exhibits stop
  re-printing. The skipped count is printed, and `--since 0` compares
  everything.

## 2026-09-30 (#155: MLB postseason night-game odds coverage)
- `python cli.py mlb-odds-timing --start D [--end D] [--only-missing]`
  (read-only): shows when api-sports first priced each MLB game, from our
  odds_snapshots. It flags UTC-rollover and night starts and gives each
  game a verdict: PRICED_PRE_START, PRICED_ONLY_AFTER_START or
  NO_BOOKS_CAPTURED. It is the receipt for the finding that postseason
  night games got no books.

## 2026-09-30 (#148: release model — main = BETA, production = tags)
- `deploy/hosting/sp_deploy.py` deploys the latest `vX.Y.Z` tag (detached)
  or an exact `--tag`. It never pulls `main` and refuses when no tag exists.
- Every receipts line carries `release` (`v1.0.0` / `BETA main@sha` /
  `UNTAGGED@sha`). Boot, chain and `sp_receipts.py` output print it.
- `scripts/release_notes.py`: the CHANGELOG slice since the previous tag.
- Ledger: `release` label and a per-release milestone (`v1.0.0`).
  `docs/RELEASES.md` holds the promotion ritual and the hotfix path.
- Fixed #149: the deploy read a host-rewritten RESULTS.md as `ESULTS.md`
  and refused.

## 2026-09-30 (#79: NCAA data audit)
- `python cli.py ncaa-audit` (read-only; `--season`, `--limit`) — the audit
  the architect ordered before any NCAA v2 (v1 verdict PROVISIONAL: log-loss
  PASS, calibration FAIL, 2025 home rate 0.489 implausible vs 2026's 0.708).
  Over the gate's stream WITHOUT its exclusions, per season: home rate by
  verbatim stage and by UTC month, repeated/reversed pairings with dates,
  two labelled HEURISTICS (home side had fewer prior-season games; home rate
  when both sides are "established" >= 8 games vs not), an inventory of
  every stored field that could indicate a neutral site or division, and a
  suspects list. Infers nothing; writes nothing. Module
  `src/walters/ncaa_audit.py`; tests `tests/test_ncaa_audit.py`.

## 2026-09-30 (gate verdicts; NHL shot-quality probe + unlinked-games audit)
- Verdicts logged: S19 REJECT (+0.0005 vs 0.0050, #83 closed); NHL v5 FAIL
  (0.6912 vs 0.6866; goalie information −0.0003 = the goalie floor; NHL
  stays market-only, reopening now needs xG-class shot data); NCAA v1
  provisional pending a data audit.
- `scripts/nhl_pbp_probe.py`: read-only probe of NHL play-by-play shot
  events (location, type, shooter, situation), 2023-24 onward.
- `nhl-goalie-audit`: why NHL games are unlinked (UTC-boundary offsets and
  more), with an opt-in `nhl-goalie-sync --tolerance-hours`.

## 2026-09-30 (#138: plain soccer-backtest evaluates production params)
- `soccer-backtest` (plain report) now uses production's `elo_goal_coeff`
  (0.0008) as well as its `dixon_coles_rho`; it used the default 0.0023.
  **Historical plain-report numbers shift**: runs before this change are
  not comparable. The S19 gate verdict was already on production params
  and is unaffected.
- The #137 / #140 / #141 / #139 pre-commitments are ratified (BACKLOG).

## 2026-09-30 (#79 NCAA v1: frozen gate + Elo candidate)
- `python cli.py ncaa-backtest` — the NCAA v1 gate, frozen before any run:
  train 2025, test = the finished 2026 games at run time (n and date range
  printed), pre/postseason excluded. Pass = log-loss <= the 2025 home-rate
  baseline − 0.010, every 10pp band with n >= 100 within ±5pp, final
  ratings 1000-2000; fewer than 500 test games = INVALID. `--baselines-only`
  prints the bar before any candidate is scored.
- Candidate `ncaa_elo_v1` (src/models/ncaa_elo.py): plain Elo, MOV + season
  regression, constants fixed a priori (k 24, home 55, mov_base 2.2,
  regression 0.25, default 1500), no selection. Read-only: nothing is
  written, no export changes; NCAA stays market-only until the architect
  rules on a verdict.

## 2026-09-30 (S19 + S20: soccer time-decay candidate, RPS reported)
- S20 (#84): the soccer backtest reports the Ranked Probability Score
  (H<D<A ordered) beside log-loss: `soccer-backtest` (calibration and
  model-vs-close blocks), an RPS column in `dixon-coles-sweep` and
  `elo-coeff-sweep`, and both arms of the S19 comparison. It is reported
  only and is in no acceptance criterion.
- S19 (#83): `soccer-backtest --candidate time-decay` scores production
  and a time-decay candidate on the same matches. The candidate weights
  the attack/defense fit by 0.5^(age_days/365); the 365-day half-life
  (Dixon & Coles 1997, ~373 days) was frozen before any run. The existing
  gate decides: candidate log-loss better by >= 0.0050, ties reject.
  It is evaluated on PL 2023/24 + 2024/25 + 2025/26, pooled. Backtest-only:
  nothing is written and production (v22) is unchanged. The frozen
  half-life, the evaluation set and four more choices wait on architect
  ratification.
- FINDING: plain `soccer-backtest` scores at the default elo_goal_coeff
  (0.0023), not production's 0.0008. It is left unchanged here; the S19
  comparison uses production's value.

## 2026-09-30 (#89: NO-side exec cost for away picks)
- On two-way markets (NFL/NHL/NCAA/MLB) the exports now carry the AWAY side's
  Kalshi cost: the NO side of the home contract (NO ask = 1 − home bid, NO
  bid = 1 − home ask), taker and maker, with the same per-fill fee as the home
  side (`away_bid`, `away_ask`, `exec_cost_taker_away`, `exec_cost_maker_away`).
- Soccer (1X2) away fields stay null: NO on HOME is draw-or-away, not an away bet.
- The Desk prices an AWAY pick from it ("… maker (join 0.xx, NO side)") and
  the ledger records those costs; pre-#89 exports and soccer still show
  "exec —". Informational only: no call, unit or tier change.

## 2026-09-30 (NHL-GOALIE: NHL API goalie ingest + v5 candidate)
- New `nhl_goalie_appearances` table and `nhl-goalie-sync`: per-game goalie
  appearances (starter flag, shots / saves / goals against) from
  api-web.nhle.com, mapped to our NHL matches, 2023-24 onward.
  `nhl-goalie-coverage` is the receipt.
- `nhl-backtest --candidate v5`: v1 + each starter's shrunk, decayed save%
  over league average as an Elo adjustment, through the frozen NHL gate.
  Constants are fixed a priori and await ratification before the run.

## 2026-09-30 (#88 re-fit: Kalshi fee rounding is fitted, not assumed)
- The per-fill ceiling failed its receipt (253/629 legs; the misses sat 1¢
  below it). `scripts/kalshi_fee_fill_receipt.py` now scores ceil /
  nearest / floor / banker's over every multi-contract leg (shards priced
  0.00 excluded), prints each rule's rate, and adopts one only at >= 95%;
  otherwise it prints the residuals.
- ADOPTED: Kalshi rounds each fill's fee to the NEAREST cent (542/548 =
  98.9%; ceil 45.3%, floor 54.7%). Exec costs move down by at most 0.1¢
  per contract (NFL 0.55/0.58: taker 0.597, maker 0.561).

## 2026-09-30 (Desk: PASS reasons in two classes)
- A Desk PASS is now tagged "no reference" (no two-sided reference, or too
  few books: greyed, with a "re-run at T-60" hint) or "below floor" (a real
  edge measured and declined). Presentation only: no call, unit or policy
  change. The summary splits the pass count.

## 2026-09-30 (#88 ruled: Kalshi fees round per fill)
- Fees are modelled as one ceiling per FILL of N contracts; the Desk
  assumes N = 10 (provisional until the B-track sizes units). Exec costs
  now carry fractions of a cent (NFL 0.55/0.58: taker 0.598, maker 0.562)
  and the Cockpit shows them to 3 decimals.
- `scripts/kalshi_fee_fill_receipt.py --csv` reproduces multi-contract
  fill fees from the Kalshi CSV (the receipt: five to the cent).
- DEPRECATION: the export's `kalshi_exec_cost` (= `exec_cost_taker`) is
  retired two Cockpit republishes from now (architect 2026-09-30). Read
  `exec_cost_taker` / `exec_cost_maker`.

## 2026-09-30 (#93 ruled: Kalshi maker and taker costs)
- Exports carry `exec_cost_taker` and `exec_cost_maker` (the ruled fee
  multipliers: game series taker M=1 / maker M=0.25, MLB pre-live M=0.5).
  `kalshi_exec_cost` stays as the taker alias.
- The Desk's exec edge and "fee-clears?" use the maker cost by default,
  with the taker cost as the fallback. Calls and units are unchanged.
- The ledger records both costs; imported fills are classified maker /
  taker from their fee, with an alarm for MLB fills at the live rate
  (doctrine: MLB is never executed live).

## 2026-09-30 (NHL-API-PROBE: the H2 goalie-source probe)
- `scripts/nhl_api_probe.py` is read-only. It probes api-web.nhle.com
  (schedule, boxscore goalie stats, roster, pre-game starter and lead time,
  2023–2025 depth) and MoneyPuck's projected-starters CSV, then prints
  FEEDABLE / NOT per need and the H2 reopening line.
- Run it on the laptop and on the host (the datacenter-IP receipt).

## 2026-09-30 (NHL shadow: the failed v1 as a greyed reference model)
- `export-nhl-predictions` writes the FAILED `nhl_elo_v1` for every NHL
  game in the next 36h. Every row is stamped `engine: model_shadow` and
  `gate_verdict: FAILED 0.6909 vs 0.6866`. Nothing is written to the DB.
- The Cockpit shows them greyed under "Reference model — failed gate".
  They never become a Desk call, a venue input or a ledger entry, and the
  window card ignores them.
- `nhl-shadow-grade` and a RESULTS.md shadow section report live CLV only
  (pick-vs-close, value-side). The `nhl-daily` host chain gains the export.

## 2026-09-30 (CORRECTION: soccer Kalshi read as two-way in the fixtures export, window card and line-move)
- CORRECTION, not a feature (#117). On soccer rows the window card's Kalshi
  home price was H/(H+A) even with the TIE leg present. So its venue gap
  and STALE-BOOK? flag compared a two-way number with a three-way book fair.
- A soccer set missing a leg was also labelled two-sided in the fixtures
  export (cups, UNL).
- Soccer now reads P(home) over HOME + DRAW + AWAY. A set missing a leg is
  "partial": no Kalshi price, exec fields, venue gap or Kalshi line-move.
  The Cockpit reads Kalshi-only 1X2 fixtures three-way.
- NFL, NCAA, NHL and MLB are unchanged. Receipt:
  `scripts/kalshi_soccer_twoway_receipt.py`.

## 2026-09-30 (ledger: auto-close reads "Closes #N" lines only)
- The ledger bot matched a closing keyword anywhere in a PR description,
  so a prose mention ("…which closes #111…") closed #111 under the wrong
  PR's name.
- It now reads only lines that start with the keyword (optionally after
  "Ledger:" or a list marker), such as "Closes #1, #2 and #3".

## 2026-09-30 (CORRECTION: soccer Kalshi sets missing a leg were normalized as two-way)
- CORRECTION, not a feature (#113). A soccer prediction row whose Kalshi
  capture lacked a leg (usually the TIE) was normalized over HOME + AWAY
  and marked two-sided, so its exported Kalshi `prob` was inflated.
- Such rows now ship `normalized: false`, `prob: null`, `missing_legs`,
  `input_quality.kalshi: "partial"` and null Kalshi cost fields. Complete
  1X2 sets and MLB rows are unchanged.
- The before/after receipt is `scripts/kalshi_soccer_incomplete_receipt.py`.

## 2026-09-30 (ledger: the bot closes a merged PR's "Closes #N" itself)
- GitHub did not register the `Closes #N` links of Claude-opened PRs, so
  merged work left its Issues open. The ledger bot now closes them on
  merge (Done), keeps a limitation open unless the PR says "Resolves
  limitation", and can replay an already-merged PR (`close-merged`).

## 2026-09-30 (Cockpit: the fun book; Kalshi quotes on MLB/soccer exports)
- The fills importer has a "fun" book: NHL and UNL singles with no
  system call, MVE combos, and non-sport markets. "Off-book other" is
  retired; the REALIZED table and the Copy P&L block print every book.
- MLB and soccer prediction exports gain `kalshi_bid` / `kalshi_ask` /
  `kalshi_exec_cost` (HOME contract, two-sided only; additive), so the
  Desk's exec-edge and join-bid columns work for baseball and soccer.

## 2026-09-30 (Cockpit fills: side from the ticker suffix; a fourth book; no default order)
- The Kalshi fills importer resolves the side from the ticker suffix first
  (`KX{FAM}GAME-{date}{AWAY}{HOME}-{SIDE}`, TIE = draw) and the title second
  ("{Team} wins — {Team}"). Stored fills are re-derived at classification,
  so the 33 "side not resolvable" fills re-classify.
- A fourth book, "system-pick, unlogged": fills that match a stored
  prediction (harvested from results exports) when no ledger call exists.
- The Open calls table shows "—" instead of a default "limit 0.59" on rows
  without a Kalshi ladder.

## 2026-09-29 (the ledger: Issues = state, BACKLOG = history, one Project board = order)
- A fixed label taxonomy (track: / class: / sport: / size: plus
  needs-ruling / needs-operator) and six dated or condition-bound
  milestones, in `.github/ledger/taxonomy.json`.
- `scripts/ledger.py` + the `ledger` workflow:
  - an idempotent bootstrap (labels, milestones, the backfill Issues,
    the board in queue order);
  - an Issue label lint (comments, never blocks);
  - PR title prefix -> track label;
  - `Closes #N` -> In progress / Done;
  - limitations close only with "Resolves limitation"; no closing by
    hand without a PR or a quoted ruling.
- The backfill manifest covers the queue, the open rulings, the
  operator actions and every known limitation, each linked to its
  BACKLOG commit + line.
- CLAUDE.md's queue is now a pointer to the board; `docs/LEDGER.md`
  holds the rules and the six views.

## 2026-09-29 (MLB PHASE A rulings)
- The four PHASE A rulings are logged:
  - empty stage on host-created rows is ratified;
  - the three-status map stands (the observed vocabulary was FT / CANC /
    NS);
  - MLB market-only rows on the host window card are accepted;
  - the doubleheader game-2 difference is waived in the compare
    ("apisports doubleheader gap"). The runbook carries the compare
    line.

## 2026-09-29 (MLB PHASE A: api-sports fallback for host MLB history; PHASE B closed negative)
- `sync-matches` / `sync-teams --competition MLB` use api-sports Baseball
  wherever `SP_SKIP_FAMILIES` names MLB (the DO host); the laptop keeps
  statsapi. Gate met: 100.0% score parity.
- Stage is never read from the provider's `week`: created rows carry
  stage NULL, and paired statsapi rows keep theirs. Status mapping is
  conservative, and a finished row is never downgraded.
- Known limitation, receipted every run: doubleheader game 2 is absent
  from api-sports. Existing rows are marked "apisports-unavailable",
  never fabricated.
- Host chain `mlb-history` + `sp-mlb-history.timer` (10:30 UTC): sync
  only, no MLB predictions on the host.
- PHASE B verdict logged: api-sports Baseball has no pitcher, bullpen
  or umpire feed. MLB predictions stay on the laptop.

## 2026-09-29 (MLB PHASE B probe: pitchers / bullpen / umpires from api-sports?)
- `scripts/mlb_phase_b_probe.py` is read-only. It classifies candidate
  api-sports Baseball endpoints and flags pitcher / bullpen / umpire
  fields, with a verdict per need.
- To be run on the laptop. The receipt is pending.

## 2026-09-29 (MLB-PROBE verdict + follow-up)
- Architect verdict logged: api-sports Baseball is GREEN for MLB
  schedule/results and AMBER for predictions (no pitcher, umpire or
  bullpen data).
- The probe fix: our DB stores status "finished" (lowercase), so score
  parity was never computed.
- It now prints score parity against the 99.5% PHASE A gate, a sample of
  disagreements, and every unpaired finished game with a doubleheader /
  UTC-boundary suspect read.

## 2026-09-29 (cosmetics lane C: utcnow sweep, MVE combo fills, ntfy topic validation)
- `datetime.utcnow()` / `utcfromtimestamp()` are replaced everywhere by
  `src/timeutil.py` helpers. These are built on `now(timezone.utc)` and
  stay naive UTC, so there is no behavior change.
- The fills importer classifies Kalshi MVE combos by leg content:
  sports legs → off-book sports parlays.
- An ntfy topic containing whitespace is refused at startup: chains fail
  loudly and never page the wrong topic.

## 2026-09-29 (late-news follow-on: T-90 injuries in the imminent tier, quarantine-class line moves)
- The window service's imminent tier syncs injuries for the NFL/soccer
  games kicking off within 2h. The sync is scoped per team, and the
  T-90 check now compares injury content.
- Line-move pages ignore quiet hours and go out at high priority.
- `late-news?` is also on the MLB and soccer prediction exports.
- Known limits logged: soccer line-move is Kalshi-only; MLB follows
  capture cadence.

## 2026-09-29 (MLB-PROBE: api-sports Baseball vs statsapi, read-only)
- `scripts/mlb_apisports_probe.py` reports coverage vs our 2025/2026
  MLB matches, ID mapping via the odds join, status vocabulary and
  postseason game types. No wiring.
- To be run on the laptop. The receipt is pending.

## 2026-09-29 (hosting: bootstrap catch-up — laptop completeness sweep)
- `bootstrap.py catch-up --reference <host fingerprint>`: for each
  competition-season where the laptop counts fewer games, it runs
  sync-teams then sync-matches.
- Dry run by default. `--apply` backs up first, receipts each season
  before and after, and stops at the first failure.

## 2026-09-29 (K-track: Kalshi fee schedule receipt; K2 join bid + order type/fill)
- Fee schedule receipt (July 2026 schedule): taker 0.07 is confirmed.
  Maker is 0.0175 × M, with M = 0 unless the series is listed.
  - The game-series maker multiplier is NOT verified: the PDF is
    unreadable from the build environment.
  - Kalshi rounds to the centicent per order, so our per-contract cent
    rounding overstates the fee (logged; unchanged pending a ruling).
- Desk: join bid (bid + 1¢) beside exec cost. A 1¢ spread shows
  "joining = taking".
- Positions record order type (limit/market) and fill price.

## 2026-09-29 (Cockpit K2: executable-edge display)
- The Desk shows exec edge = model − Kalshi (ask + fee) beside the fair
  edge, with "fee-clears?" at ≥ 4pp. It is informational only: no
  sizing, tier or call change.
- Positions record the Kalshi exec cost at claim and at execution.

## 2026-09-29 (MNF QB verdict; line-move alarm; T-60 closing-freshen doctrine)
- QB audit verdict logged: the cause was sync timing plus provider
  latency. The Chicago starter was absent from the provider's report at
  both pre-game syncs. The detection code is exonerated.
- New line-move alarm:
  - inside T-3h, a ≥ 6pp net move on book or Kalshi (stored snapshots,
    no provider calls) marks the row `late-news?` in the window card
    and the NFL export;
  - it pages on the card topic and triggers `freshen:<family>`.
- CLI.md doctrine: the game-day T-60 closing freshen is mandatory for
  model sports while the laptop is writer of record.
- The host-journal receipt for Monday's T-90 check is pending, to be run
  on the host (commands in the PR).

## 2026-09-29 (#63 rulings: value-side anchor timestamp on every grade)
- The architect ratified all four #63 decisions: all-sport scope, the
  earliest pre-kickoff book anchor, tagged quarantine shadows, and
  snapshot growth deferred to pruning.
- `nfl-grade` value-side lines now show the anchor and prediction
  timestamps, and flag an anchor that came after the prediction.
- `export-nfl-results` rows carry the value-side fields and anchor
  timestamp (additive).

## 2026-09-29 (Week 4 MNF rulings: value-side shadow, value-side CLV, QB feed audit)
- Cockpit: the Desk evaluates edge on every side. A value side that is
  not the top pick and clears 4pp logs a `value_shadow` at 0.25u
  notional.
  - It is graded like quarantine shadows and never staked.
  - It has its own counterfactual line, with promotion review at 30
    graded (policy v1.2 candidate).
- `nfl-grade` and RESULTS.md print value-side-vs-close beside
  pick-vs-close.
  - `sync-odds-football` now appends a book-consensus snapshot on every
    sync, which serves as the anchor.
  - Games without one are counted as unanchored.
- NFL QB detection: positions resolve by id, then name, then a unique
  initial+surname. QB/Quarterback both count. Still-listed players are
  no longer dropped by the 14-day filter.
- The export gains `positions_unresolved`.
- New read-only `nfl-qb-audit` (with `--live` for the H1/H2/H3 verdict).
  The receipt on MNF data must run on the host/laptop.

## 2026-09-28 (hosting: sp_run transient-step retry)
- sp_run retries a step that fails TRANSIENTLY (connection errors,
  timeouts, HTTP 5xx/429) twice, 15s then 45s. The receipt says
  `retried N`.
- A step still failing pages as before. Other 4xx and exceptions in our
  own code never retry.

## 2026-09-28 (Cockpit: execution-timing rule, policy v1.1 addendum)
- Positions carry claim_at (frozen claim price) and executed_at (default:
  last freshen before kickoff; or an explicit, recorded "Execute now").
- Grading settles at the execution price, with a claim-price counterfactual.
  The P&L block gains a "claim vs exec" column and an EXECUTION TIMING
  section. No sizing changes.

## 2026-09-28 (hosting: ncaa-market Thursday run)
- sp-ncaa-market adds Thu 16:00 UTC (Thursday-night slates' fixtures
  file). On the host: re-run install.sh after the pull.

## 2026-09-28 (hosting: exhibit 1 fixes — injuries, keyed comparator, SHA-stamped exports)
- nfl-predict syncs NFL injuries first (chain gap); a CI guard audits every
  prediction chain (MLB exempt: no injury source).
- compare_exports keys game rows on (kickoff, home, away), not match_id,
  and names unmatched rows.
- Every JSON export carries its producing `git_sha`. "Code-version skew"
  is an explained class only when both SHAs are present and named.
- Exhibit 1's divergence log is recorded in the runbook.

## 2026-09-28 (hosting: nhl-daily single-day syncs)
- nhl-daily syncs yesterday/today/tomorrow as three single-day calls that
  the hockey adapter honours, instead of one silent whole-season pull.

## 2026-09-28 (hosting: NHL opening-day gate + season gates as config)
- nhl-daily activates 2026-09-29 (2026-27 opening day; was the 2025-derived
  2026-10-07).
- Season gates are configurable per chain (`SP_NHL_ACTIVE_FROM` in
  host.env; malformed fails loudly). Every run prints and receipts
  `active from <date> [<source>]`.

## 2026-09-28 (hosting: P4 Tailscale SSH status)
- Tailscale SSH is enabled server-side (`sudo tailscale set --ssh=true`
  returned silently). The invalid `tailscale status --json | grep -i ssh`
  receipt is dropped. Client-side verification is pending (Mac MagicDNS);
  the tailnet-IP door is the proven standard, and the P4 receipt uses it.

## 2026-09-28 (exports: current-slate windowing)
- Prediction exports default to the current slate: kickoffs in the next
  36h for NFL and soccer. MLB keeps its one 08:00-UTC slate-day (ruling:
  it plays daily). Use
  `--week` (NFL) / `--days N` for the full look-ahead. Explicit dates keep
  their slate-day meaning. Generation is unchanged; only the file's rows
  are scoped.
- A `window:` receipt line is printed. freshen:SOCCER now uses the 36h
  default (a one-slate closing file).

## 2026-09-28 (hosting: H1b day one + runbook field amendments)
- H1b parallel week started 2026-09-28 13:45 UTC: 12 host timers,
  SP_PARALLEL_MODE=full, MLB timers off by ruling. The earliest cutover
  decision is after 2026-10-05 13:45 UTC (criterion 1: 7/7 days).
- Runbook P4: sp gets NOPASSWD sudo + Tailscale SSH (receipt-gated) before
  root is sealed. The console is emergency-only after P4. Mac VPN clients
  conflict with Tailscale (quit them before tailnet steps).

## 2026-09-28 (hosting: pull-exports lane)
- `deploy/hosting/pull_exports.py`: the laptop pulls the host's exports/
  over the tailnet into exports/host/ (never its own exports/). The host
  comes from SP_HOST_ADDR. Newest-wins, idempotent, all-or-nothing on an
  unreachable host, receipted (pulled / unchanged / newest window_24h.json).
- `scripts/setup_export_pull.sh`: optional hourly launchd job at :10.
- Docs: CLI.md hosting table, runbook T12b (laptop pulls; push is H2).

## 2026-09-28 (Cockpit: ledger doubling fix)
- Root cause: re-logging a multi-day file on a later day re-captured every
  call under a new log_date key (reproduced: 12 → 24). Import ledger merged
  by stored id. The Kalshi CSV import only re-rendered the doubled totals.
- The ledger key is enforced on every write path; import merges by
  recomputed key. Unit of account = the POSITION (ratified): a re-log on a
  later day reprices that position in place, never a second row.
- New "Dedupe ledger" repair (reports how many it removed) + a stored-
  duplicates warning on the Ledger tab.
- Capture only before kickoff (multi-week files no longer log played
  games); "Copy ledger (JSON)" with a text-box fallback + "Import pasted".
- scripts/cockpit_ledger_verify.py: 21/21 (import twice → identical totals).

## 2026-09-27 (window service: freshen chains + proximity tiers)
- freshen:NFL / freshen:MLB / freshen:SOCCER defined; the window service
  triggers them on T-90 news (chain lock, one per family per hour, MLB
  never on the host), then rebuilds the card.
- Proximity tiers: far (>6h) schedule check only, near (2-6h) + odds and
  Kalshi, imminent (<2h) + T-90 detection; receipt counts steps skipped.

## 2026-09-27 (window service: Next-24h card + delta pages)
- Hourly `window` chain (sp-window.timer, enabled on H1b day 1): single-day
  match syncs, window-scoped odds + Kalshi, then `window-card` →
  exports/window_24h.json. No model runs; model fields copied from the
  canonical exports.
- Delta pages to a second ntfy topic (NTFY_CARD_TOPIC), quiet hours
  00-07 ET except quarantine flips, one 08:00 ET digest.
- Quota line on every chain receipt.
- Cockpit "Next 24h" tab (headless receipt 12/12).

## 2026-09-27 (H1a CERTIFIED PASS)
- Host bootstrap certified: compare clean, no waivers. The laptop was the
  side short 67 UEL 2024/25 games (clubs never team-synced), now fixed.
- Law recorded: sync-teams before sync-matches for every new
  competition-season (CLAUDE.md, CLI.md).
- compare rows label each count laptop / host.

## 2026-09-27 (fingerprint receipts + hardening)
- bootstrap explain / explain-diff: the counting predicate, the same rows
  counted four ways, and every uncounted row's status/status_raw/stage/
  external_ids, diffed laptop vs host.
- Fingerprint groups by competition_id (LEFT JOIN, orphans labelled),
  self-checks against raw COUNT(*); compare sums duplicate status entries.
- remove_allstar_rows dry-run prints the NFL teams with the fewest games.

## 2026-09-27 (host Pro Bowl cleanup, authorized)
- deploy/hosting/remove_allstar_rows.py: host-only, receipted removal of
  pre-exclusion Pro Bowl rows (dry-run default; --apply backs up first,
  cascades through declared FKs in one transaction, prints post-counts).
- Event backups (_precleanup_, _prerefresh_) never count as the daily.
- Waiver policy: real provider drift only; UEL 2024/25 needs none.

## 2026-09-27 (H1a compare rulings: Pro Bowl exclusion, waivers, EL1/EL2 refresh)
- NFL adapter excludes Pro Bowl / all-star games and teams, printing each
  excluded row.
- bootstrap compare --waive COMP:SEASON:reason: row still printed as
  WAIVED, recorded in the receipt.
- Monday soccer-refresh (chain + routine doc) syncs EL1/EL2 2026/27 first.
- Fingerprints embed the producing bootstrap.py git blob SHA; compare
  refuses version-mismatched or unstamped fingerprints (the UEL 269 vs 202
  delta was version skew, not data).

## 2026-09-27 (bootstrap --skip-family: MLB Stats API blocks datacenter ASNs)
- bootstrap.py --skip-family MLB: MLB sync-teams/sync-matches receipted
  SKIPPED-ASN, numbering unchanged (resume --from 8); compare reports the
  family N/A-host.
- Runbook: MLB is a laptop duty; host MLB timers off; post-cutover egress
  is an H2-era decision.

## 2026-09-27 (Hosting H1 phasing: fresh bootstrap first)
- Runbook re-ordered: H1a fresh bootstrap (host syncs its own DB;
  acceptance = BACKLOG fingerprints reproduced), H1b independent parallel
  week, H2 cutover = the one .backup migration (why it can't be skipped).
- deploy/hosting/bootstrap.py: fingerprint / plan / run / compare.
- compare_exports: divergence classes = capture timing + provider
  pagination.
- Model registry seed (ratified): production model_versions rows seeded
  at bootstrap (config only; books stay empty); compare verifies model
  identity; the four model-bearing timers enable with the rest.
- Cutover criterion 3 amended before day 1: "capture timing or explained
  provider pagination, each explained".

## 2026-09-27 (Hosting H0 final four; FOUND SAFETY GAP logged)
- Paging via ntfy.sh (NTFY_TOPIC in .env); held PASS pages and logs.
- Backups: DO weekly on + nightly laptop pull (deploy/hosting/pull_backup.py,
  scripts/setup_backup_pull.sh); host retention 14 dailies, prune
  report-only until the first manual prune is reviewed.
- CLV captures confirmed on America/New_York; NCAA timer enabled.
- On the record: improve auto-promoted on PASS (masked by 36 rejections);
  closed by hold-on-pass + ratify-candidate.

## 2026-09-27 (Hosting H1: systemd pack + runbook, inert until provisioning)
- deploy/hosting/: chain definitions (CI-checked against cli.py), sp_run
  receipts writer, .backup/prune/notify/boot-receipt/deploy scripts,
  migration pack/verify/install, parallel-week export diff, 21 systemd
  unit/timer files, install.sh (enables nothing).
- docs/specs/hosting-h1.md: provisioning runbook (BROWSER/TERMINAL),
  frozen cutover criteria, H0 rulings record, 4 open items.
- H0-5 guard: `improve --hold-on-pass` holds a PASS and pages;
  `ratify-candidate` promotes on explicit ratification. Default unchanged.
- CLI.md: pre-slate `sync-umpires --today`; improve/ratify rows.

## 2026-09-27 (Cockpit: Kalshi fills import, two-book accounting)
- Ledger tab: "Import Kalshi CSV" -> REALIZED section (system-matched /
  off-book sports / off-book other; staked, fees, pre-fee, net, avg fill,
  fees % of loss) + plausible-match review list; in the Copy P&L block.
- CSV mapping verified on the real Kalshi export header; trailing-30-day
  avg fill + fee per $ staked (ledger-level).
- scripts/cockpit_fills_verify.py (20/20, real header).

## 2026-09-27 (K1: Kalshi bid/ask stored; executable-cost fields)
- odds_snapshots.yes_bid / yes_ask filled by every Kalshi sync going
  forward. Run `python migrate_kalshi_quotes.py` after merge, before any
  chain.
- NFL predictions + fixtures exports add kalshi_bid, kalshi_ask,
  kalshi_exec_cost (ask + fee; fee formula ARCHITECT-VERIFY) —
  informational until the executable-edge ruling.

## 2026-09-27 (K0: Kalshi storage receipt)
- `scripts/k0_kalshi_storage_probe.py`: read-only probe of what a stored
  Kalshi snapshot holds. Code read: only a derived prob (bid/ask mid,
  single side, or last price) — bid/ask are not persisted.

## 2026-09-27 (cosmetics batch)
- nfl-backtest verdict text for the live era (provenance/regression);
  stale rehearsal docstrings updated.
- export-nfl-results no longer writes the fossil `"rehearsal": true`.
- docs/CLI.md: sync-matches options, sync-kalshi-ncaa, daily backup,
  NFL LIVE section, full Kalshi series list. .env.example: football and
  hockey API keys. api_hockey docstring matches its actual key fallback.

## 2026-09-27 (U2: NFL export "why" fields)
- NFL predictions export adds elo_home, elo_away, elo_gap,
  home_adv_applied, rest_days_home, rest_days_away. Additive only.
- export-nfl-predictions warns (ELO DRIFT) when an NFL game finished
  after the predictions were written; silent otherwise.

## 2026-09-26 (Cockpit v0.4 — P&L / self-grading organ, policy v1.1)
- tools/cockpit.html: Ledger tab (localStorage bd_ledger_v1, export/
  import), "Log today's calls", venue-edge engine (shadow, 0.25u),
  results/fixtures grading intake, by-engine reports, equity + quarantine
  counterfactual, per-rule attribution, Copy P&L block, non-claims.
- docs/specs/cockpit-v04-pnl-organ.md (spec, verbatim).
- scripts/cockpit_v04_verify.py: headless capture -> grade -> report
  check (24/24).
- Venue-edge charter narrowed (ruling): market-only family only (NHL,
  NCAA, cups when priced); model sports (NFL etc.) emit model_edge only.
- venue.py: doc line — fixtures' kalshi.prob is the raw stored value.

## 2026-09-26 (NFL export: STALE-BOOK? venue flag)
- NFL predictions export adds kalshi_prob, venue_gap_pp and venue_flag
  ("STALE-BOOK?" when |book fair - Kalshi| >= 8pp). Warning only —
  quarantine unchanged. export-nfl-predictions prints the flagged games.
- Logged: vetted verdicts (NFL FAIL, NCAA INSUFFICIENT-REF) and the
  stale-at-source football moneyline finding.

## 2026-09-26 (full-loop ruling logged: venue-edge engine)
- Docs only. Architect ruling: a second recommendation engine
  (venue_edge: book fair vs Kalshi, |div| >= 5.0pp, fixed 0.25u, shadow)
  beside model_edge; ledger reports by engine; policy -> v1.1. Build
  held for the v0.4 spec.

## 2026-09-26 (spread-fallback check vetted; fallback dark)
- `spread-fallback-check`: per-row ML_books + capture timestamps/gap;
  verdict on the vetted set only (ML_books >= 4, gap <= 24h; same 3.0pp
  bar); UNRELIABLE-REF rows printed; INSUFFICIENT-REF when vetted n < 10.
- Spread fallback gated DARK (`FALLBACK_LIVE = False`): exports carry
  1X2-sourced fair prices only until a vetted PASS.
- Logged: lane 6 closed (scope clean, gate 0.6361 PASS), score-90 HOLD,
  quarantine ruling ratified as built, #27 lands as a draft.

## 2026-09-26 (hosting H0 draft, for review)
- Docs only. `docs/specs/hosting-h0.md`: VPS candidates, Tailscale-only
  posture, systemd unit inventory from the CLI.md chains, `.backup`-API
  migration runbook (checksums, 7-day parallel run), receipts-log
  format, CLI.md/cli.py discrepancies, ARCHITECT-RULE open questions.
  Draft for architect review — not a decision; nothing deployed.

## 2026-09-26 (spread->win-prob fallback, american football)
- NFL/NCAA games with no 1X2 consensus but posted spreads now get a
  spread-derived fair (normal margin; median book home line; sigma
  frozen a-priori NFL 13.45 / NCAA 16.5). Additive export field
  `fair_source` ("1X2" | "spread_derived") on every market block, plus
  `consensus_home_spread` / `spread_sigma` on derived blocks. NFL
  quarantine/divergence unchanged (1X2 only). Receipt command:
  `python cli.py spread-fallback-check --competition NFL|NCAA`.
  Acceptance receipt pending Anthony's real run; bar 3.0pp frozen
  before results.

## 2026-09-26 (data/ created at connect time)
- Importing the package no longer creates an empty data/ directory; the
  SQLite directory is created on first connection instead.

## 2026-09-26 (sync-odds-football rename)
- `sync-odds-nfl` renamed `sync-odds-football` (covers NFL + NCAA); the
  old name remains an alias — no chain changes needed.

## 2026-09-26 (NCAA book-market finding logged)
- Docs only. College books post spreads, not moneylines: 12/116 book
  consensus vs Kalshi 99/116 — Kalshi-primary confirmed. Queued:
  spread->win-prob fallback (K-track, after Cockpit v0.4, architect
  spec); `sync-odds-nfl` -> `sync-odds-football` rename (next daily batch).

## 2026-09-26 (NFL model paths scoped to competition NFL)
- Ratings, backtest pot, prediction set, export and grading now select
  Competition.code == "NFL" explicitly (NCAA shares Sport.NFL).
  predict-nfl and nfl-backtest print a scope line (teams, games,
  competitions) with a SCOPE ALERT on contamination.

## 2026-09-26 (H2 goalie probe verdict: NEGATIVE)
- Docs only. The hockey provider has no goalie/lineup/player endpoints
  (only /games/events answers). H2 reopens only via an external data
  source; NHL market-only indefinitely. Bounded authorization closed.

## 2026-09-26 (migrate_score_90 invariant revised)
- Receipt prints breaching rows verbatim + the AET/PEN stage table.
  Revised law: FT 90'==score; AET/PEN 90'<=stored per side; level at
  90' only for single-match ties (stage-based). No column changes —
  re-run `python migrate_score_90.py` after merge.

## 2026-09-26 (H2 probe fix; morning findings logged)
- `scripts/h2_goalie_probe.py`: prints one raw /games object verbatim
  first; date/timestamp parsing tolerant of the hockey string shape
  (fixes the `_game_ids` crash).
- BACKLOG: architect findings — NHL 20-25% past-regulation (status_raw
  splits); lineup probe GREEN (XI from ~2015, minutes from ~2018).

## 2026-09-26 (soccer ET flag + 90-minute score)
- Football adapter stores status_raw (FT/AET/PEN) and score.fulltime in
  new matches.home_score_90 / away_score_90. Storage only — scores and
  results unchanged. Run `python migrate_score_90.py` after merge
  (receipt includes the 90-minute invariants).

## 2026-09-26 (lineup-history probe)
- `scripts/lineup_history_probe.py`: read-only probe of API-Football's
  per-match lineup history — declared coverage per season plus spot
  checks (lineups + per-player minutes). No DB access, no wiring.
  Anthony runs it and pastes the output to the architect.

## 2026-09-26 (H2 goalie/lineup probe)
- `scripts/h2_goalie_probe.py`: read-only probe of the hockey provider
  for starting-goalie / lineup data — endpoints, fields, historical
  depth, pre-game availability. No DB access, no wiring. Anthony runs
  it and pastes the output to the architect.

## 2026-09-26 (NHL raw status storage)
- matches.status_raw: the provider's status code kept verbatim; the
  hockey adapter stores FT/AOT/AP (OT/SO wins distinguishable). Run
  `python migrate_status_raw.py` after merge, then a full NHL sync.

## 2026-09-26 (mission declared)
- CLAUDE.md: Mission section (architect, verbatim) at the top; queue
  re-ranked — Cockpit v0.4 P&L/self-grading at the head, K-track
  (Kalshi-executable edge accounting) and B-track (bankroll doctrine)
  opened behind it; closed items moved to a record list. Docs only.

## 2026-09-25 (NHL Phase 2 closed; market-only launch wiring)
- nhl_elo_v4 FAIL ratified (0.6907). Ledger v1 0.6909 / v2 0.6921 /
  v3 0.6952 / v4 0.6907 — schedule-only floor ~0.691 vs bar 0.6866.
  NHL model track suspended; Oct 7 launch is market-only.
- `export-fixtures`: Kalshi presence, latest pre-kickoff book consensus,
  printed odds-label receipt; NHL-ready. Cockpit: fixtures header +
  Kalshi fixed. Docs: NHL daily market-only chain.

## 2026-09-25 (NHL candidate v4 — last schedule-only; cup track suspended)
- nhl_elo_v3 FAIL ratified (0.6952). `nhl-backtest --candidate v4`: v1
  form, 12-point shrink grid (k 3-6 x home adv 35/40/45), v3 selection,
  2025 once. If it fails: no v5, Oct 7 market-only, track suspends
  pending the H2 goalie probe.
- Cup fix-v2 re-exam FAIL (14.76pp; inversion cleared): cup model
  track SUSPENDED for the season (rotation information floor); EFL/CL/
  UEL market-only; machinery stays merged.
- CLAUDE.md production state + queue status updated.

## 2026-09-25 (cup fix-v2 — gate-class)
- Cup re-exam FAIL ratified (sign inversion 2/5, mean 18.11pp).
- Cup elo_goal_coeff by context (same-/cross-league), tuned on prior
  cup matches with the exam's seasons excluded; `cup-exam` tunes then
  prices (`--cup-coeffs base` reproduces the old exam). League pricing
  untouched; nothing persisted.
- CLAUDE.md: market-is-a-reference doctrine; queue tail S19-S20, H2,
  data items (football 90'/ET flag, NHL OT/SO); S18 retired as
  already-shipped; deep-research disposition logged.

## 2026-09-25 (NHL candidate v3 — gate-class)
- nhl_elo_v2 FAIL ratified (2025 0.6921, upper bands overconfident).
- `nhl-backtest --candidate v3`: params selected by walk-forward
  validation inside 2024 (60% fit / 40% validation), full-2024 refit,
  2025 scored once; grid extended downward/center only. Gate unchanged.
- Standing fallback logged: no pass by Oct 6 -> NHL opens Oct 7
  market-only.

## 2026-09-25 (cup fix — gate-class)
- Cup/intl pricing: attack/defense from each team's domestic
  league-season fit (as-of-date), blended toward the cup fit by n/(n+5);
  every fit leave-self-out, strictly before kickoff.
- Ruling B: unrated / no-domestic-league cup fixtures are market-only
  (never priced); the exam reports them separately, outside INVALID.
- elo_goal_coeff unchanged (0.0008). League pricing untouched.
- Coverage floor: fewer than 45 scored fixtures = exam INVALID
  (architect amendment).

## 2026-09-25 (NHL candidate v2 — gate-class)
- nhl_elo_v1 FAIL ratified (0.6909 vs <= 0.6866); bar unchanged.
- `nhl-backtest --candidate v2`: frozen 720-point grid tuned on
  2024-internal sequential loss only, then 2025 scored once. v2 = v1 +
  rest days (back-to-back emphasis) from the existing schedule.

## 2026-09-25 (cup pricing hypothesis check)
- `cup-exam --detail` adds strength-fit receipts: per-side fit n,
  attack/defense, promoted-prior flag, self-in-fit, pool/backfill,
  summary. No pricing change.
- BACKLOG: code receipts for the cup strength window and the
  elo_goal_coeff under-dispersion; architect ruling B (out-of-pot =
  market-only) logged.

## 2026-09-25 (NHL Phase 2 — gate, then Elo v1; gate-class)
- `python cli.py nhl-backtest`: frozen NHL gate (train 2024, test 2025,
  preseason excluded by stage/date, OT/SO-inclusive home win), both
  baselines, three acceptance criteria, verdict. Writes nothing.
- nhl_elo_v1: MOV + per-team season regression; parameters a priori,
  home advantage from the 2024 home rate.

## 2026-09-25 (cup exam diagnostics)
- Cup exam verdict FAIL (mean |Δ_H| 13.86pp, sign 60%): cups stay locked.
- `cup-exam --detail`: per-row Elo/league/bonus inputs, |Δ_H| splits
  by pot membership and tier, default-Elo team count. No pricing change.

## 2026-09-25 (cup acceptance exam — gate-class)
- `_generate_predictions_soccer(include_finished=True)`: report-only
  pricing of finished fixtures; returns rows, writes nothing.
- `python cli.py cup-exam`: scores production pricing against
  exports/cup_answer_key.csv on the frozen bar (±8pp MAE, <=13 over
  8pp, EFL round-2 sign check); necessary-not-sufficient semantics.
- Removed superseded tools/betting_desk.html and
  tools/predictions_card.html (cockpit.html is the live surface).
- BACKLOG: architect's stale-entry disposition logged verbatim.

## 2026-09-25 (security warm-up — first Claude Code PR)
- Web UI: cross-site (CSRF) check on all state-changing requests;
  Host allowlist against DNS rebinding; Tailwind pre-built and
  htmx/Chart.js vendored — the UI loads no third-party scripts.
- tools/cockpit.html: escapes file- and model-supplied text (XSS).
- tests/ + pytest in CI; CLAUDE.md workflow: Claude Code works
  branch + PR only, Anthony merges.

## 2026-09-25 (working arrangement v2)
- CLAUDE.md shipped: Claude Code onboarded as repo executor; chat
  remains architect. Tarball era closes.

## 2026-09-25 (NCAA)
- NCAA wired into the american-football adapter (league map, both
  competitions listed, per-code resolution); cli routes NCAA; data +
  market-only doctrine.

## 2026-09-24 (cockpit)
- Card + Desk merged into one tabbed cockpit artifact (same URL);
  per-game signal expanders; tools/cockpit.html supersedes both files.

## 2026-09-24 (predictions card)
- Predictions Card artifact: sport-aware model viewer over the exports
  (bars, edges, quarantine, QB, gaps) — the post-GPT cockpit's second
  organ; in-repo copy versioned.

## 2026-09-24 (SDLC)
- Community standards shipped (CONTRIBUTING = the laws, CoC, SECURITY,
  MIT LICENSE, issue/PR templates) + CI (parse + import smoke on every
  push). PR doctrine: direct-to-main daily; branch+PR for gate-class.

## 2026-09-24 (H-track 1c)
- sync-kalshi-nhl (third sport on the shared matcher); export success
  string updated to LIVE format.

## 2026-09-23 (NHL Phase 1)
- api_hockey adapter shipped (cloned from american-football; id 57,
  AOT/ASO handling, preseason captured); registry, sport router, and
  --seasons wired. Backfill block issued.

## 2026-09-23 (H-track)
- NHL Phase 0 probe shipped: read-only plan/id/season-format recon with
  famous-club receipts.

## 2026-09-23 (cup exam prep)
- scripts/extract_cup_key.py: read-only answer-key extractor for the
  cup acceptance exam; report-only pricing mode scoped for next session.

## 2026-09-23 (perf)
- Match-sync O(n^2) fixed: per-sync prefetch cache replaces per-row JSON
  full scans; morning chains move to 2-day sync windows (full-season
  weekly).

## 2026-09-23
- H-track opened: NHL onboarding planned on the NFL playbook (phased,
  gate-first, preseason-as-shakedown); sequenced behind the cup
  acceptance exam.

## 2026-09-22
- **NFL LIVE (Week 3 ratified):** rehearsal flag dropped; per-row
  market_divergence_pp + quarantine field (>=15pp) implements the
  contract rule structurally.

## 2026-09-21 (rebuild)
- DB destroyed by packaging incident; restored from 09-17 backup and
  fully rebuilt same morning. v22 re-promoted on the full 16,546-match
  / 24-competition pot (spread 101%, documented drift override).
  Packaging + backup laws now in force.

## 2026-09-21 (desk v0.3)
- Betting Desk v0.3: multi-sport multi-file intake, cross-sport parlay
  builder (correlation-screened, positive-edge, 0.25u), audit expanded
  to per-game notes + parlay critique + prediction-layer signals
  feedback.

## 2026-09-21
- Engine-level SQLite pragmas (WAL + synchronous=NORMAL + busy_timeout)
  on every connection — fixes the morning-lag regression from db-tune's
  per-connection NORMAL.

## 2026-09-20 (desk v0.2)
- Betting Desk v0.2: sport-aware ladder (no DC on 2-way boards),
  monotone sizing, near-floor tempering, correlation flag — both day-1
  NFL defects fixed by the desk's own audit arm; now versioned in-repo
  (tools/betting_desk.html).

## 2026-09-20 (shadow day 1)
- First divergence report: slate-shape convergence; three structural B1
  requirements identified (input freshness, consensus quality,
  two-stage clearance); app-side injury-recency flag queued.

## 2026-09-20 (B1)
- Betting Desk artifact shipped: browser-local policy engine + Claude
  audit over daily exports — the B1 shadow vehicle.

## 2026-09-20 (B-track)
- B-track opened: native betting layer design committed (policy-as-code,
  shadow-vs-GPT migration path, audits-as-requirements). Sequenced after
  cup acceptance + U1 unless platform deadlines force it.

## 2026-09-20 (db)
- `db-tune`: WAL mode, ANALYZE, composite indexes, optional VACUUM,
  probe timing — first response to season-scale DB lag; snapshot
  pruning/rollup queued as the structural fix.

## 2026-09-20
- API-Football request spacing now env-configurable (API_FOOTBALL_RPM;
  default 10/min): the 2:04-per-odds-sync metronome was the free-tier
  pace hardcoded — paid plans can cut the European sweep's odds legs
  from ~12 minutes to ~30 seconds. 429 backoff unchanged as safety net.

## 2026-09-19 (feeder backfill)
- Nine feeder leagues backfilled: ~7,988 matches, zero skips. Monday
  refresh pot ~20,600 across 24 competitions.

## 2026-09-19 (feeders)
- Nine CL/UEL feeder leagues wired data-only (NED POR BEL SCO TUR AUT
  SUI GRE CZE) with strength priors; Nordic calendar-year leagues
  deferred pending season-string support.

## 2026-09-19 (backfill)
- Expansion backfill complete: 4,468 matches / 4 leagues, zero skips;
  ELC activated. 15 competitions, 5 countries.

## 2026-09-19 (expansion)
- Coverage expansion decided: La Liga, Serie A, Bundesliga, Ligue 1 +
  ELC activation — no code needed (pre-wired); backfill plan issued,
  refresh held to Monday as one gated transition, shadow-matchweek
  doctrine applies.

## 2026-09-19 (v22)
- **v22 promoted** — first soccer model change since v18: per-team
  regression, 8,137-match pot (pyramid/Euro/WC), spread guard passed
  99%; Southampton drift justified (50 ELC matches entered) with a
  documented one-time --max-drift override. Refresh reopened.

## 2026-09-19 (later)
- Compression CONVICTED by the probe (interleaved "2026"/"2026/27"
  season strings firing six tail regressions; pyramid exonerated) and
  FIXED: per-team season regression in elo.train (NFL semantics).

## 2026-09-19
- `scripts/compression_probe.py`: instrumented double-train (pot A/B)
  with inline regression markers — locates the Elo collapse empirically.
- U1 (per-sport daily cards + unified page) committed as next dedicated
  build session.

## 2026-09-17
- `capture-weather-nfl` (N1 phase 1): 32-stadium map keyed by home team,
  roofed handling, Open-Meteo capture into GameWeather — tracking only.
- S14 Stage-1: flat +1.0 uncertain-bucket totals correction selected
  counterfactually (direction 39%->52% in-sample); Stage-2 out-of-sample
  acceptance frozen pre-results.
- Cap-variant verdicts: all four declined (caps cost log-loss; shrink
  degraded the weakest band) — v1 unchanged; bonus finding: the >0.80
  zone was under-confident on 2025 (0.800 stated / 0.833 realized).
- `nfl-backtest-caps`: R-track cap/shrink variant harness (acceptance
  frozen pre-results); untestable asks (road-inversion, divisional)
  declined with reasons. Matched-zero sentinel extended to the shared
  MLB/NFL Kalshi path.

## 2026-09-16
- S14 verdict: soccer totals under-projection is bucket-shaped
  (uncertain-winner games +1.17 goals, confident +0.08, n=46) — fix
  hypothesis queued for Stage-1 backtest. CLI.md corrected:
  totals-check/calibration-series are MLB-only.

## 2026-09-15
- Hotfix: results-tally join corrected (outcomes link via prediction_id
  → Prediction → Match, not match_id) — caught on first run.
- **`results-tally`** → `RESULTS.md`: rolling 30-day per-sport record
  (sides, log-loss, CLV), auto-generated, linked from README; joins the
  morning rhythm.
- **`export-nfl-results`**: graded NFL results file in the standard
  consumer shape (rehearsal-flagged) — NFL joins the results-file rhythm.
- Week 1 NFL final: 9/16, log-loss 0.6755 (both max-conviction rows
  lost); MW4 soccer: 5/10, giant edges split — Forest won, Hull and
  Everton missed by draw (cohort 6/12, four misses-by-draw).

## 2026-09-14
- NFL Week 1 graded via `nfl-grade` (first live read): 9/15 sides,
  log-loss 0.6441 vs 0.6361 backtest — performance transferred live.
- **`docs/CLI.md`**: full CLI catalog (~55 commands with options),
  organized by workflow, plus the required-services matrix (providers,
  endpoints, env vars, subscription notes) and local component
  requirements. README links it as the primary interface reference.
- **README rewritten** to current four-sport reality; this CHANGELOG seeded.
- **`nfl-grade`**: grades NFL predictions vs finished games and banked
  closing consensus (sides, log-loss, CLV) — read-only, feeds the Week-2
  rehearsal decision.
- **Kalshi soccer hardening**: matched-zero sentinel (loud warning when
  games and markets are both present but nothing matches) and an in-play
  guard keyed on our own kickoff time at capture.
- **GitHub repo live** (this repo): pre-push security scan clean; tarball →
  extract → commit → push workflow established.

## 2026-09-13
- **Kalshi soccer matcher fixed** after an upstream title-format change
  ("A vs B Winner?" → "A wins") silently blinded it for two matchweeks:
  pairing now derived structurally from sibling legs sharing an
  event_ticker, old title parse kept as fallback. Matched 36/36 on return.
- NFL Week-1 game-day file: full model-vs-market comparison (15 priced
  games), Kalshi NFL board matched 28 legs / 14 games two-sided.

## 2026-09-10 → 09-12
- **NFL tier thresholds frozen** pre-results (strong ≥0.68, lean ≥0.57).
- Injury position enrichment: provider's injuries feed carries no
  positions; adapter now joins the team roster by player id (QB status
  live end-to-end).
- MW4 false alarm resolved on the record: two probe-falsified theories;
  file shipped; lesson logged (verify before withholding).

## 2026-09-09
- **NFL phase 2 in one day, gate-first**: backtest gate frozen before any
  model code; v1 Elo (margin-of-victory, per-team season regression)
  passed decisively (0.6361 vs 0.6911 baseline, all bands ≤7pp);
  prediction path + rehearsal-format export built; Week-1 shakedown run
  internally. `sync-odds-nfl` closed the book-capture gap.
- Kalshi sync parameterized (sport + series) — one matcher serves MLB and
  NFL; `sync-kalshi-nfl` added.

## 2026-09-05 → 09-08
- **NFL phase 1**: full data wiring from zero — adapter
  (api-american-football), registry/CLI routing, 3-season backfill
  (989 games), status inference (score-presence beats status-absence),
  spread-sign preservation, season-format hardening.
- **`export-fixtures`**: market-only files for gated competitions
  (matches + odds tables only; `contains_predictions: false`). First live
  consumption by the downstream layer same week.
- EFL Trophy consciously excluded (training-pot contamination); FA Cup
  sync deferred to its trigger rounds; CL ruled data-only behind the cup
  acceptance gate.
- Elo compression diagnosis narrowed: v19/v20 rejections deterministic;
  rating-spread guard added to the soccer gate.

## 2026-08-28 → 09-04
- S17: results export includes draw in top-pick labeling (+ assertion).
- M12: per-match skip warnings aggregated to one summary line.
- Doubleheader guard in the MLB odds fallback (nearest-time + claimed-id).
- EL→UEL competition normalization; pyramid (ELC/EL1/EL2) + CL/UEL
  history backfilled for the cup project.
- Aug-31 quality review: run_shrink_frac=0.35 confirmed on 509 games;
  starter-cap and bullpen-swing ledgers closed clean; M15/M16 tracking
  opened with pre-committed reads.

## 2026-08-11 → 08-27 (from the earlier phase)
- MLB production model v2 shipped behind the daily improve gate; CLV
  lifecycle automated (overnight closer backfill).
- Soccer v18 production through PL matchweeks; thermometer/pick-edge
  ledgers established.
- EFL Cup round-2 dress rehearsal caught the cup-path defects (league
  bonus misfire); S16 doctrine: no cup predictions until acceptance.
- Kalshi integration (MLB + soccer) with refuse-safe matching.
