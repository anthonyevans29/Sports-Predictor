# Changelog

Human-readable record of what shipped, newest first. Deep detail and the
reasoning behind each change live in `BACKLOG.md`; this file is the summary.
Every drop adds an entry going forward.

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
