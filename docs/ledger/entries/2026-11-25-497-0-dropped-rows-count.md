**2026-11-25 — 497 step (0), the dropped-rows count: the rows the adapters drop before counting, the games sync-odds does not read and the games sync-odds-football leaves unpriced each get a printed count with their causes in the command's own output; no exit, stored row, prediction, sp_run, stop rule or go_on changes (addenda 497 Q7 and item 2, 502 Q7; #1102).**
- **Ruling (497 Q7), verbatim:**

  >    Q7. YES, COUNT FIRST. The rows an adapter drops before counting get a printed count with their
  >        causes in the command's own output; no exit changes with it. It is the first PR.

- **Ruling (502 Q7), verbatim:**

  >    Q7. YES. sync-odds' uncounted drops and sync-odds-football's skips get a printed count first,
  >        with 497's step (0); no exit changes with it.

- **Ruling (497 item 2), verbatim, its sentence in its line context:**

  > 2. THE ORDER, yours with two changes: (0) the dropped-rows count of Q7; (1) dedupe-matches;
  >    (2) improve; (3) export-results, the mlb MLB call; (4) results-tally by Q8; (5) nhl-goalie-sync
  >    by Q6; (6) sync-teams NCAA; (7) the three Kalshi commands with Q3's throttle; (8) sync-matches
  >    LAST, and not before I have ruled, chain by chain, which chains go on past it. Each is its own
  >    money-path PR; none touches sp_run, a stop rule or a go_on.

- **What landed:**
  - One shared line for the adapters (src/adapters/base.py `dropped_line` / `report_dropped`), api_basketball's line byte for byte: `<source> /<what>: N listing(s) not read (reason n · reason n): id, id`, printed only when a row was dropped, with `last_dropped` (reason -> [provider ids]) kept on the adapter.
  - mlb_stats_api /schedule (no team id, unreadable date); api_hockey /games (no kickoff date, no game id, no team id) and /teams (no team id, no team name); api_american_football /games (the same three, plus non-competitive, whose own per-row line is kept) and /teams (no team id, no team name, non-competitive); api_baseball /teams (no team id, no team name); the MLB api-sports fallback's provider games with an unreadable date (api_baseball /games).
  - sync-odds: `SyncResult.odds_not_read` and `odds_not_read N (reason n: ids · ...)`, printed always before the summary: no provider id; with --match-ids each named id that is no candidate (not stored, other competition, other season, not scheduled, kickoff passed). MLB: the client's whole-game drops (no game id, unreadable date, no team name, by provider game id, once per game over the run) and the games at or after first pitch (started, by stored match id), not printed when no odds read was made; capture-odds prints the same line before its "odds synced:" line.
  - sync-odds-football: the returned dict's `not_priced` and `football_not_priced N (reason n: ids · ...)`, printed always before the summary: named, not in the window; no provider id; fetch error; still rate limited; no rows.
  - tests/test_dropped_rows_count.py (40): each cause on each adapter, the clean answer, the byte-identical basketball line, each sync-odds and sync-odds-football reason, an MLB game counted once over its two reads and not listed once priced, no line on a run that made no odds read, the line before the summary, exit 0, and no new line read by sp_run's count lines, SYNC_ECHO, the failure markers or the exception classifier.
- **Not in this PR:** kalshi_tennis's duplicate-ticker overwrite and its window/season filter; the MLB fallback's non-club and ambiguous team counts on sync-matches; api_football (no per-row drop: its parse aborts); every per-price parser drop (an unreadable price, an unmapped selection, a bet type not read, another totals line); sync-odds' --limit cut; every site the map lists as already counted.
- **Choices named for the architect:**
  - mlb_stats_api's line names its endpoint, `/schedule`, as basketball's names `/games` and `/teams`.
  - The MLB odds causes list two kinds of id under plain labels: no game id, unreadable date and no team name list provider game ids; started lists stored match ids.
  - The MLB client's drops count each game once over the run: the rollover's per-game read is a retry of the same game, and a game a later read returned rows for is taken off. A "no game id" drop has no id to match, so it counts once per read.
  - On MLB, a run with no key or a window read that raised made no odds read: it prints no odds_not_read line rather than a 0 nobody counted. An empty window was read, and its line counts that read's drops.
  - The adapters' line prints in every `list_matches` caller, not in sync-matches alone: dedupe-matches --orphans (497's step (1), its own PR) prints it in its per-day date search, and resync-diff prints it for MLB, NHL, NFL and NCAA. get_game (refresh-by-id) prints nothing new.
  - A named sync-odds id the filter leaves out for no cause the five labels name reads "not a candidate" (unreachable by the filter as written; never silent if it is reached).
  - sync-odds on a competition not in the DB returns before any read: its line reads `odds_not_read 0`, the named ids unclassified (the warning is the existing count).
  - capture-odds prints the line before "odds synced:"; its last line stays "✓ Captured".
  - On the MLB step the new line sits between NO-BOOK-ODDS and the summary, so NO-BOOK-ODDS is the third line from the end, inside the five-line tail.
- Nothing here moves a bar, a date or a held timer. Nothing changes a prediction output, an exit code or a stored value.
