# docs/ — the index

Every file under `docs/` (`git ls-files docs`), one line each: what it is, its kind, and the lane or Issue it serves
(ARCHITECT 2026-11-06, addendum 276 item 3, PR B). Each description is read from the file's own head. The lane or
Issue comes from the file itself, from docs/roadmap.json, or from the commit that added it
(`git log --diff-filter=A -- <path>`). An Issue number appears only where the file or that commit names one. This
index describes and decides nothing (addendum 276 item 2(b)). Rules live in CLAUDE.md and CONTRIBUTING.md; status
lives in CLAUDE.md "Current production state".

Kinds: **live runbook** (steps or a reference read today); **spec** (a declaration, design, contract or rule set);
**record** (a receipt, a run record or a ruling's record, not edited for style: addendum 276 item 2(d)); **archive**
(a note that is not current; addendum 276 item 2(e)).

## docs/

- `docs/README.md`: this index. **live runbook**. Addendum 276 item 3 (PR B).
- `docs/CLI.md`: the CLI reference (`python cli.py <command>`), with the scripts and the laptop-side hosting tools. **live runbook**. Every lane; the commands are cli.py's.
- `docs/LEDGER.md`: the ledger's rules (Issues = state, BACKLOG.md = history, one Project board = order; per-PR fragments). **spec**. The ledger (ruled 2026-09-29).
- `docs/REGISTRY.md`: the experiment registry and the confirmation doctrine (declare, run, verdict, cohort, confirmation; retired test sets). **spec**. #212.
- `docs/RELEASES.md`: the release model (`main` = BETA, the latest `vX.Y.Z` tag = PRODUCTION; `deploy/hosting/sp_deploy.py`). **live runbook**. #148 (ruled 2026-09-30).
- `docs/roadmap.json`: the model lanes with their steps, due dates, earliest-live dates and moved lines. **spec**; changed only in a PR that quotes the ruling (its own `ruled` field), read by `python cli.py roadmap`, checked by `python scripts/ledger.py check-roadmap`. #486 (addendum 59 item 5).
- `docs/pl_weekly_routine.md`: the PL weekly routine (S5): Friday, Saturday and the morning-after chains. **live runbook** for its chains: `deploy/hosting/chains.py` (lines 4 and 121) names it as the soccer chains' source; its "STEP ZERO" (lines 9-14) pulls `main`, since work arrives by branch + PR (CLAUDE.md "Workflow"; corrected by addendum 286 item 2(b)), and the export is read in the Cockpit (addendum 276 item 1). PL; soccer-expansion-v1's data lines (ARCHITECT 2026-10-07).
- `docs/bucket2_tracking_plan.md`: the MLB "Bucket 2" tracking plan of 2026-06-29 (log umpire, weather, bullpen and starter data; nothing feeds the model). **archive**, by its status line. Its items 1-4 are recorded as built in BACKLOG.md's three 2026-06-29 "Bucket 2 tracking" entries.
- `docs/historical_backfill_assessment.md`: the 2026-07-06 feasibility assessment of an MLB 2025 backfill, by retrievability tier. **archive**, by its status line. Tier 1 is cited by docs/roadmap.json (lane mlb-pitchers, #507) and `scripts/mlb_pitcher_asof_receipt.py`; its tier-3 odds line is superseded for Kalshi-listed games by finding #496 (addendum 60 item 7).

## docs/archive/

- `docs/archive/bucket2_data_research.md`: the MLB "Bucket 2" data-sourcing research of 2026-06-29 (per data point: the feed, access, build size). **archive**, moved by `git mv` (addendum 276 item 2(e); no tracked file named its old path, `git grep`). Written 2026-06-29 (its title); superseded by `docs/bucket2_tracking_plan.md`, the same date and the same seven items, whose item 2 adds the finding that weather was display-only (`src/web/weather.py`), never a model input.

## docs/specs/

- `docs/specs/availability-record.md`: the availability record: two append-only tables, the writer, the read path, `availability`, and the nflverse depth-chart feed (section 9). **spec**. Lane availability-record (#830), addendum 252.
- `docs/specs/cockpit-v04-pnl-organ.md`: Cockpit v0.4, the P&L / self-grading organ, committed verbatim from the 2026-09-26 rulings (policy version v1.1). **spec**. PR #30; rulings on #61 (commit 2026-09-28).
- `docs/specs/desk-policy-v1.2.md`: Desk policy v1.2 (the unit is a fraction of the pool) and the early-entry arm (addendum 283). **spec**. #732 (addendum 179).
- `docs/specs/exports-mirror.md`: the exports mirror (F2.5): host and laptop push `exports/` to a private repo, the compare Action, the Cockpit's "Load latest from host", the bulletins subtree. **spec**. Lane F2.5 (ARCHITECT 2026-10-03); #826, #852, #858.
- `docs/specs/h2-cutover-runbook.md`: the H2 cutover runbook (the one `.backup` migration). **record**: its status line reads "CUTOVER DONE 2026-10-26 13:45:11Z" (addendum 168 item 1); its laptop routine (addendum 169 item 4) is the one README.md cites. Hosting H2; #707.
- `docs/specs/hosting-h0.md`: the H0 draft for an always-on host. **record**: its status line reads "RULED — see `docs/specs/hosting-h1.md`" (2026-09-27). Hosting H0.
- `docs/specs/hosting-h1.md`: the H1 unit pack and Anthony's provisioning runbook (systemd units, receipts writer, T-steps, T11's enable list). **live runbook**. Hosting H1.
- `docs/specs/intl-elo-v1.md`: international Elo v1, the frozen pre-commitment and its declared limitation. **spec**. #220 lane 2; registry `intl-elo-v1` (closed, FAIL).
- `docs/specs/intl-elo-v2.md`: international Elo v2, the frozen declaration. **spec**. #220; registry `intl-elo-v2`; roadmap lane unl.
- `docs/specs/mlb-pitchers-v1.md`: mlb-pitchers-v1, the pitcher-layer test: the ruling, the harness, the operator's sequence. **spec**. Lane mlb-pitchers (#507), addendum 190; registry `mlb-pitchers-v1` (closed, REJECT, addendum 266).
- `docs/specs/ncaa-cfbd-labels.md`: the NCAA CFBD label lane (data lane), with the pregame neutral flag (addendum 236 item 3(1)). **spec**. #176 probe read; gate #79.
- `docs/specs/ncaa-elo-v1r.md`: ncaa-elo-v1r, the declaration. **spec**. Lane ncaa (#79), addendum 11 item 3; registry `ncaa-elo-v1r` (closed, FAIL).
- `docs/specs/ncaa-elo-v2.md`: ncaa-elo-v2, the declaration. **spec**. Lane ncaa (#79), addendum 81 item 2; registry `ncaa-elo-v2`.
- `docs/specs/ncaa-shadow.md`: the NCAA shadow (`export-ncaa-predictions`, `ncaa-shadow-grade`) and the confirmation machinery's rulings. **spec**. Addendum 6 item 1; lane ncaa (#79).
- `docs/specs/nfl-qb-term.md`: the NFL quarterback term's design packet, a proposal for the 11-02 ruling, not a declaration. **spec**. Lane nfl-qb (#427), addendum 162 item 3.
- `docs/specs/nfl-rehearsal-arm.md`: nfl-elo-v2's rehearsal arm, the export contract (`src/walters/nfl_rehearsal.py`). **spec**. Lane nfl-v2 (#783), addenda 230 item 1(a), 247, 251 item 3.
- `docs/specs/nhl-xg-v6.md`: NHL-xG v6, the frozen declaration. **spec**. #153; registry `nhl-v6` (closed, FAIL).
- `docs/specs/nhl-xg-v7.md`: NHL-xG v7, the frozen declaration (v6 with the label leak removed). **spec**. #153; registry `nhl-v7` (closed, FAIL).
- `docs/specs/nhl-xg-v8.md`: NHL-xG v8, the frozen declaration, the last candidate on the 2025 test season. **spec**. #153; registry `nhl-v8` (closed, FAIL).
- `docs/specs/pl-availability-v1.md`: pl-availability-v1, the PL availability candidate. **spec**. Lane pl-availability (#754), addendum 198; registry `pl-availability-v1`.
- `docs/specs/snapshot-retention.md`: snapshot retention, a ruled design; its status line says nothing in it is built. **spec**. #82.
- `docs/specs/soccer-expansion-v1.md`: soccer-expansion-v1, the declaration (the production soccer model on PD, SA, BL1, FL1, ELC). **spec**. Roadmap lane pd (#322); registry `soccer-expansion-v1`.
- `docs/specs/soccer-parity-acceptance.md`: soccer backtest/production acceptance: one parity test and five pins. **spec**. Addenda 230 item 1(e), 248 item 2(a), 249 item 1, 251 item 2, 253 item 2; #788.
- `docs/specs/soccer-v23.md`: soccer-v23, the design of v22's joint log-linear successor; not declared, not run. **spec**. Lane soccer-v23 (#656), with #789.
- `docs/specs/unl-venue-skew-test.md`: UNL venue eligibility, the favorite-skew test (v2, ratified 2026-10-06). **spec**. #286.
- `docs/specs/venue-quote-age.md`: venue edge, the quote age (a fetch time is not a quote age). **spec**. #91 (addendum 4 E, ARCHITECT 2026-10-07).

## docs/receipts/

Each file is the kept output of one run (the commit that added it names the run).

- `docs/receipts/home-abroad-2026-10-23.md`: the INTL home-abroad receipt, run 2026-10-23T17:09:58Z, written by `python cli.py intl-home-abroad-receipt`. **record**. ARCHITECT 2026-10-07 item 4(c); addendum 160 items 1 and 4.
- `docs/receipts/k-track-2026-10-06.md`: the K-track receipt (ladders, fee-clear reads), written by `python cli.py k-track-receipt`; dollar figures redacted by #817. **record**. #87 (#75 folded in); #813.
- `docs/receipts/mlb-actionable-2026-10-08T1336Z.md`: the MLB actionable receipt, run 2026-10-08T1336Z, written by `python cli.py mlb-actionable-receipt`. **record**. ARCHITECT 2026-10-07 item 2 (no policy change).
- `docs/receipts/mlb-actionable-2026-10-12T1214Z.md`: the MLB actionable receipt with the declared toss-up splits, run 2026-10-12T1214Z, written by `python cli.py mlb-actionable-receipt`. **record**. #354; addendum 44 item 6.
- `docs/receipts/ncaa-v1r-design-2026-10-08.md`: the ncaa-elo-v1r gate design receipt (seeded simulation), written by `scripts/ncaa_v1r_design_receipt.py`. **record**. Lane ncaa (#79), addendum 11 item 3.
- `docs/receipts/soccer-value-sides-2026-10-09.md`: soccer value sides against the close on soccer-expansion-v1's scored ids, written by `python cli.py soccer-value-receipt`. **record**. #383; addenda 21 item 6, 23 item 2, 28 item 5.
- `docs/receipts/soccer-value-sides-2026-10-09-pl-reference.md`: the PL reference page of the same receipt (PL 2024/25 + 2025/26). **record**. #383.
- `docs/receipts/unl-exploratory-17.md`: the UNL ladder receipt for the first 17 games, recorded as exploratory, written by `python cli.py unl-ladder-receipt`. **record**. `docs/specs/unl-venue-skew-test.md` v2.

## docs/registry/

Generated by the registry module `src/walters/registry.py` and the gate commands that call it (docs/REGISTRY.md); a
run's files arrive on `main` as the laptop wrote them (each one's adding commit says so). Never edited for style
(addendum 276 item 2(d)).

- `docs/registry/experiments.json`: the experiment registry, one entry per candidate (declaration, run, verdict, cohort, confirmation). **record**; `declare()`, `record_run()` and `freeze_confirmation_cohort()` write it, and a verdict lands in a commit that quotes the ruling (13faddc6, 9394c9c4). #212.
- `docs/registry/ids/intl-elo-v1.txt`: intl-elo-v1's scored match ids, written by `record_run()` from `python cli.py intl-elo-backtest`. **record**. #220.
- `docs/registry/ids/intl-elo-v2.txt`: intl-elo-v2's scored match ids, written by `record_run()` from `python cli.py intl-elo-backtest`. **record**. #220.
- `docs/registry/ids/intl-elo-v2.cohort.txt`: intl-elo-v2's frozen confirmation cohort (60 fixtures), written by `python cli.py intl-elo-confirm --freeze-cohort`. **record**. #220.
- `docs/registry/ids/mlb-pitchers-v1.txt`: mlb-pitchers-v1's scored ids, written by `python cli.py mlb-pitchers-gate`. **record**. #507.
- `docs/registry/ids/mlb-pitchers-v1.cohort.txt`: mlb-pitchers-v1's frozen test cohort, written by the freeze (`src/walters/mlb_pitchers_gate.py` `freeze`). **record**. #507.
- `docs/registry/ids/ncaa-elo-v1r.txt`: ncaa-elo-v1r's scored ids, written by `python cli.py ncaa-v1r-gate`. **record**. #79.
- `docs/registry/ids/nfl-elo-v2.txt`: nfl-elo-v2's scored ids, written by `python cli.py nfl-v2-gate`. **record**. Lane nfl-v2 (#783).
- `docs/registry/ids/nhl-v6.txt`: nhl-v6's scored ids, written by `record_run()` from `python cli.py nhl-backtest`. **record**. #153.
- `docs/registry/ids/nhl-v7.txt`: nhl-v7's scored ids, written by `record_run()` from `python cli.py nhl-backtest`. **record**. #153.
- `docs/registry/ids/nhl-v8.txt`: nhl-v8's scored ids, written by `record_run()` from `python cli.py nhl-backtest`. **record**. #153.
- `docs/registry/ids/soccer-expansion-v1.txt`: soccer-expansion-v1's scored ids, written by `python cli.py soccer-expansion-gate`. **record**. Lane pd (#322).
- `docs/registry/ids/soccer-expansion-v1.cohort.txt`: soccer-expansion-v1's frozen confirmation cohort (60 PD fixtures), written by `python cli.py soccer-expansion-confirm --freeze-cohort`. **record**. Lane pd (#322).
- `docs/registry/mlb-pitchers-v1.started.json`: mlb-pitchers-v1's run reservation, written by `python cli.py mlb-pitchers-gate`. **record**. #507.
- `docs/registry/ncaa-elo-v1r.started.json`: ncaa-elo-v1r's run reservation, written by `python cli.py ncaa-v1r-gate`. **record**. #79.
- `docs/registry/nfl-elo-v2.started.json`: nfl-elo-v2's run reservation, written by `python cli.py nfl-v2-gate`. **record**. Lane nfl-v2 (#783).
- `docs/registry/soccer-expansion-v1.started.json`: soccer-expansion-v1's run reservation, written by `python cli.py soccer-expansion-gate`. **record**. Lane pd (#322).

## docs/ledger/

`docs/ledger/entries/` holds the per-PR BACKLOG fragments (ARCHITECT-RULE 2026-10-02). A PR adds one by hand;
`python scripts/ledger.py compile --commit` folds every entry into BACKLOG.md, newest first, and deletes it
(docs/ledger/entries/README.md). The list below is the folder at this PR's head, so it shortens at each compile.

- `docs/ledger/entries/README.md`: the folder's rules (one entry per PR, its changelog.d twin, the compile). **spec**. ARCHITECT-RULE 2026-10-02.
- `docs/ledger/entries/2026-11-04-230-1d-soccer-v23-design.md`: BUILT, soccer-v23's design PR. **record**. Addenda 248 item 2(b), 230 item 1(d); #656, #789, #788.
- `docs/ledger/entries/2026-11-04-244-4a-nhl-shadow-git-sha.md`: BUILT, five exports carry `git_sha`. **record**. Addenda 244 item 4(a), 249 item 2; #823.
- `docs/ledger/entries/2026-11-04-252-availability-record-schema.md`: LANE OPENED, the availability record's schema PR. **record**. Addendum 252; lane availability-record.
- `docs/ledger/entries/2026-11-05-252-3a-nflverse-feed.md`: BUILT, the nflverse depth-chart feed. **record**. Addenda 252 item 3(a), 258 item 2(1), 259 item 2.
- `docs/ledger/entries/2026-11-05-256-cups-step-c-no.md`: RECORDED, cups Step C closes as a written no with one bounded probe. **record**. Addendum 256; lane cups.
- `docs/ledger/entries/2026-11-05-261-1a-basketball-probe.md`: BUILT, the basketball source probe and lane basketball-market-only. **record**. Addenda 261 item 1(a), 264 item 4; #839.
- `docs/ledger/entries/2026-11-05-261-2b-tennis-probe.md`: BUILT, the tennis provider probe and lane tennis-market-only. **record**. Addenda 261 item 2(b), 264 item 4; #838.
- `docs/ledger/entries/2026-11-06-250-4-bulletins-mirror-subtree.md`: BUILT, the exports mirror's bulletins subtree. **record**. Addenda 250 item 4, 267 item 4(a); #826.
- `docs/ledger/entries/2026-11-06-264-3-soccer-v23-s11-followup.md`: soccer-v23's section 11 follow-up. **record**. Addenda 263, 264 item 3; lane soccer-v23.
- `docs/ledger/entries/2026-11-06-265-nfl-v2-verdict-record.md`: VERDICT, nfl_elo_v2's one run FAILED the phase-2 gate. **record**. Addendum 265; lane nfl-v2.
- `docs/ledger/entries/2026-11-06-266-mlb-pitchers-verdict-record.md`: VERDICT, mlb-pitchers-v1's one run REJECTED. **record**. Addendum 266; lane mlb-pitchers.
- `docs/ledger/entries/2026-11-06-269-274-records-tennis-basketball.md`: RECORDED, the tennis and basketball probe steps done. **record**. Addenda 269-274; #838, #839.
- `docs/ledger/entries/2026-11-06-271-3-basketball-wiring.md`: BUILT, the NBA's market-only wiring. **record**. Addenda 271 items 2-3, 261 items 0 and 1(b), 272 items 3-5; #839.
- `docs/ledger/entries/2026-11-06-276-a-readme-truth.md`: RECORDED, the repo truth pass, PR A (README.md). **record**. Addendum 276 items 2-3; #866.
- `docs/ledger/entries/2026-11-07-276-b-docs-index.md`: RECORDED, the repo truth pass, PR B (this index, the archive, CLI.md's Cockpit sentence). **record**. Addendum 276 items 2-3.
- `docs/ledger/entries/2026-11-07-276-c-scripts-index.md`: RECORDED, the repo truth pass, PR C (scripts/README.md, the two routine lines). **record**. Addendum 276 item 3; addendum 286 item 2(b).
- `docs/ledger/entries/2026-11-07-284-1a-nflverse-real-rows.md`: BUILT, the nflverse real-row tests (#869). **record**. Addenda 284 item 1(a), 286 item 1; #830.
- `docs/ledger/entries/2026-11-07-279-3a-nhl-source-probe.md`: BUILT, the NHL source probe. **record**. Addendum 279 items 3(a) and 5; lane nhl (#105).
- `docs/ledger/entries/2026-11-07-280-281-records.md`: RECORDED, the 280 hotfix, the main ruleset, roadmap done-marks. **record**. Addenda 278, 281 item 4, 282 items 1 and 5.
- `docs/ledger/entries/2026-11-07-280-py310-hotfix.md`: HOTFIX, main imports on Python 3.10; CI's 3.10 job. **record**. Addendum 280 item 2.
- `docs/ledger/entries/2026-11-07-283-4-early-entry-arm-ledger.md`: BUILT, the early-entry arm's ledger attribution (#864). **record**. Addenda 283 item 4, 286 item 3; #862.
- `docs/ledger/entries/2026-11-07-283-arm-policy-text.md`: POLICY, the early-entry arm declared. **record**. Addendum 283.
- `docs/ledger/entries/2026-11-07-284-1b-tennis-wiring.md`: BUILT, the tennis market-only wiring (#868). **record**. Addenda 284 item 1(b), 261 items 0 and 2(c), 269 items 1-3; #838.
- `docs/ledger/entries/2026-11-07-287-records.md`: RECORDED, the tennis wiring step done early and the undated step, the odds-payloads line, the ledger-480 records, the scripts index's re-run owed. **record**. Addenda 286 items 4(b) and 4(f), 287 items 2 and 3; #838, #871, #873.
- `docs/ledger/entries/2026-11-07-852-mirror-top-level-links.md`: BUILT, the exports mirror's top-level link refusal. **record**. Addendum 277 item 1; #852.

## docs/discussions/

- `docs/discussions/seed-2026-10-01.md`: the four Discussions seed threads, posted 2026-10-01 as Discussions #197, #198, #199 and #200 (links in docs/LEDGER.md). **record**. #170; `scripts/ledger.py`'s workflow_dispatch mode `discussions` posts a thread from a file in this folder (`DISCUSSIONS_DIR`).
