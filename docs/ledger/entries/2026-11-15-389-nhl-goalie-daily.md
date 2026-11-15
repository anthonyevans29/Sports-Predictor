**2026-11-15 — Addendum 389: #1016 merge-ready; the NHL goalie gap read; the daily goalie step ruled and built; the backfills are the architect's; the shot sync's silent exit opened as a finding (#1018).**
- **Addendum 389 (ARCHITECT 2026-11-15 09:50 ET), verbatim:**

  > ARCHITECT 2026-11-15 09:50 ET (14:50Z, read from the clock) — addendum 389, for DEV 1 (Lane A). DEV 2 reads item 6 only.
  > Paste exactly. Record it in BACKLOG as usual.
  >
  > 1. #1016 — READ, MERGE-READY at 49723eff.
  >    Tests only (4 files, +20/-2): the two results-tally tests freeze export.utc_now_naive where their
  >    renderings compare. CI green on the head (smoke, smoke-py310, fragments, closing-refs), clean against
  >    main 08554df9, 0 open review threads. It merges by my block today. Nothing more is asked of it.
  >
  > 2. THE NHL GOALIE GAP — your five lines are accepted as the facts. What I read myself on main 08554df9:
  >    (a) src/ingestion/nhl_goalies.py http_json returns (0, None) on a network failure and (code, None) on
  >        an HTTP error; sync() only counts them (schedule_http_<code>, boxscore_http_<code>); the command
  >        exits 0 whatever the counts say.
  >    (b) nhl-shot-sync keys its games through the goalie-sync mapping and falls back to the matcher for a
  >        game with no goalie link (its own docstring). So the mapping belongs BEFORE the shot sync.
  >    (c) nhl-daily holds no nhl-goalie-sync step; UNMETERED holds nhl-shot-sync and not nhl-goalie-sync;
  >        the chain's date placeholders hold no day earlier than {yesterday}.
  >
  > 3. RULING — build the daily step. One small PR, lane A.
  >    (a) THE STEP: ["nhl-goalie-sync", "--start", "{yesterday}", "--end", "{today}"] in nhl-daily, after
  >        export-fixtures and before nhl-shot-sync.
  >    (b) UNMETERED gains "nhl-goalie-sync", beside nhl-shot-sync, with the same reason (api-web.nhle.com,
  >        the NHL's free API, never api-sports). tests/test_hosting_pack.py follows.
  >    (c) nhl-daily's go_on names it: a failed goalie step is receipted and paged as a sync-step failure and
  >        stops nothing after it. Its go_on_why cites this item.
  >    (d) A FAILURE THAT READS AS ONE: nhl-goalie-sync exits non-zero when any schedule or boxscore request
  >        of the run answered other than 200. It still prints its counts line and its coverage lines first,
  >        and what it parsed is still written (the upsert is unchanged). No flag: it holds for a hand run and
  >        for --dry-run as for the chain. You pick the exit code the repo's other syncs use for a provider
  >        failure and name it in the PR body.
  >    (e) A REFUSAL IS NOT A FAILURE: REFUSED games and "not in our DB" stay counted and printed, exit 0.
  >        No tolerance changes, no refusal becomes a guess.
  >    (f) If the provider answers other than 200 for a kind of game that is not a failure (a postponed game,
  >        say), STOP and tell me which kind, with the count. Do not allow-list a code on your own.
  >    (g) No new placeholder, no wider window in this PR. A game whose request fails on both of its two days
  >        is caught by the page, and the catch-up is a hand run by my block.
  >    (h) CLASS: a deploy script and a command's exit, so the stop rule's money-path side applies: P2s left
  >        after round two are listed for me. The PR body names the command and its arguments (198 item 6(i));
  >        it ships no block.
  >    (i) TAG: it rides the first tag cut after it merges. If it is merged before v1.6.9's fold, that is
  >        v1.6.9; I do not hold v1.6.9 for it.
  >
  > 4. THE BACKFILLS — mine, by block, both.
  >    (a) LAPTOP, today: an OPERATOR ONLY block (a one-off write outside the routine). A named pre-run
  >        backup, then your dry run for 2026-10-01 .. 2026-11-15 to a file, then a mechanical stop if any
  >        request answered other than 200 or boxscore_calls is 0 or above 500, then the same command without
  >        --dry-run, then the day's backup again and nhl-goalie-coverage --db on that copy. The operator
  >        relays the console to you: it is the 45-day receipt for your PR body (refusals, unmatched games,
  >        request counts), and it runs on main as it stands, so its exit is still 0 by design.
  >    (b) LAPTOP, from tomorrow: the two-day goalie sync joins my morning block after the NHL export. Nothing
  >        for you to ship.
  >    (c) HOST: after the tag that carries item 3, by my OPERATOR ONLY block: one hand run from 2026-10-01,
  >        then the coverage read on a backup copy. Not before.
  >
  > 5. A FINDING FOR THE LEDGER, yours to open: nhl-shot-sync, LIVE on the host's nhl-daily, has the same
  >    silent form (pbp_http_<code> is counted, the exit is 0), and on a {yesterday, today} window a game
  >    whose request fails on both days is never asked again. ONE Issue (class finding, sport nhl). In
  >    it, state what the host's receipts keep of that step's printed counts line, since that decides whether
  >    I can read from the receipts if it has ever happened. NO FIX YET: that step has no go_on, so an honest
  >    exit there would stop the shadow steps behind it, and that is its own ruling. It is not part of item
  >    3's PR.
  >
  > 6. DEV 2 — for your information only: this season's goalie appearances will exist on the laptop from
  >    today's backfill and on the host from the tag after v1.6.9 at the latest. The ceiling test's cohort is
  >    the retired 2025 season and does not wait on this. Nothing here changes your queue: matcher PR one is
  >    next.
  >
  > Nothing in this addendum moves a bar, a date or a held timer.

- **Item 3, what landed (this PR):**
  - `nhl-goalie-sync` exits 1 (`nhl_goalies.PROVIDER_FAILURE_EXIT`) when any schedule or boxscore request answered other than 200. 1 is the exit the repo's other syncs use for a failed provider read: sync-matches' strict read, availability-nflverse's `failed`, availability-nhl-observe's failed schedule read.
  - The line is printed last, after the counts and coverage lines, so the step receipt's five-line tail and the page carry it. Refusals and games not in our DB stay exit 0. No code is allow-listed.
  - On nhl-daily: the step sits between export-fixtures and nhl-shot-sync. It is UNMETERED, and `go_on` (`chains.NHL_GOALIE_GO_ON`) names it.
  - From the pre-push review: an answer cut short or malformed (`http.client.HTTPException`) counts as code 0 through the goalie sync's own fetch (`sync_fetch`), not a traceback. A failed boxscore is counted only as a failed request, never also as a refusal. `http_json` and the shot sync are untouched (#1018).
  - **The 45-day receipt (390 item 4(a)), the laptop on main 7506e550:** window 2026-10-01 .. 2026-11-15; schedule_calls 7 (all 200), games_found 322, skipped_not_finished 5, boxscore_calls 317 (all 200), both_starters 317, mapped_to_our_match 317, rows_written 1268; nothing refused, nothing not in our DB; exit 0. No code other than 200 came back, so 3(f)'s stop has nothing to report.
- **Item 5:** opened as #1018 (track:ops, class:finding, sport:nhl, size:S).
  - The host's receipts never hold the shot sync's counts line. A step receipt keeps its last five lines, which are always the end of the coverage block, and `marks` reads only the sync-teams and sync-matches family of lines. The journal holds the full output, for as far back as the host's journald keeps it.
  - Read for #1018 and stated there: the window asks for a game that starts after 10:00Z on ONE run only, not two. Those are the US afternoon and early-evening starts. The same holds for the new goalie step, where 3(d)'s exit and 3(c)'s page make that one failure visible.
- **Next:** 4(a) is the architect's laptop block. Its console is the 45-day receipt for the PR body, and 3(f)'s stop applies to any code other than 200 it shows.
