**2026-10-09 — THE FIFTH LANE: STORE IT AND SHOW IT (ARCHITECT addendum 32 item 4): the provider's own odds time, `source_updated_at`, stored by sync-odds-football and shown beside every capture time of those prices; the Desk does not read it.**
- **Ruling (verbatim, item 3, RULED: WHAT update IS):** "response[].update is the provider's own time for a game's odds: one per game, neither our fetch time nor the fixture's. It is read as the newest that any quote in the answer can be; a quote may be older. It is stored and shown as source_updated_at and described in those words, never as the time of a quote. A row without it has an unknown source time, and unknown is never read as fresh."
- **Ruling (verbatim, item 4):** "sync-odds-football stores the source's update time with what it writes: on every odds row, and on every book consensus snapshot it appends. Every export block that shows a capture time for those prices shows source_updated_at beside it, in the same form; where a session's rows differ, the oldest. The Desk does not read it. #91 and the quote-age rule stay exactly as built: every computed venue row is still held."
- Stored: `NormalizedOdds.source_updated_at`; the american-football adapter parses `response[].update` to naive UTC (absent / unreadable / no offset = None, never guessed, never our clock). `odds` and `odds_snapshots` gain nullable `source_updated_at` via `migrate_odds_source_updated_at.py` (additive, idempotent, receipt; no backfill: the old rows' source times were never kept). `sync_odds_nfl` writes it on every odds row and on every book consensus snapshot (the oldest of the snapshot's rows; any unknown row makes it unknown, since unknown is never read as fresh).
- Shown, beside the capture time in the same form (export blocks named from the code): `src/walters/export.py` `_fixture_row` `market.captured_at` (1X2 close, and the dark spread-derived fallback) -> `market.source_updated_at` (export-fixtures, the window card); `src/walters/line_move.py` book venue `from_at` / `to_at` -> `from_source_updated_at` / `to_source_updated_at` (export-nfl-predictions, the window card); `src/walters/nfl_predict.py` export-nfl-results `graded.value_anchor_at` -> `value_anchor_source_updated_at`. The NFL predictions `market` block shows no capture time, so it carries none.
- Not in this lane: `close_at` on results rows (close.py, addendum 31 item 3); the closing-run receipt's `captured_at` (deploy/hosting/closing.py, bound tonight); the venue receipts; any rule that reads the field. Hockey / soccer / MLB stay null (no payload read, or no field).
- **Amended (ARCHITECT 2026-10-09 20:34 ET, addendum 35, verbatim):**
  > ARCHITECT · 2026-10-09 20:34 ET · addendum 35 · #407: READ in full. Reading 1 RULED the other way: the two columns
  > are not mapped. Readings 2 to 5 ACCEPTED. Still held, and behind addendum 33
  >
  > 1. #407 AT 92ef652: READ, every file, the tests included. It does what addendum 32 item 4 says. Readings 2, 3, 4 and
  > 5 are ACCEPTED as built: a row without a source time makes its whole session unknown; the form is that of the
  > capture time beside it; the value anchor carries the field; an update with no offset, or one that is not a
  > string, is unknown.
  >
  > 2. READING 1, RULED: THE COLUMNS ARE NOT MAPPED.
  > "odds.source_updated_at and odds_snapshots.source_updated_at follow the ORDER LINE note of 2026-10-04 in
  > schema.py: not mapped in the ORM, written and read by guarded Core SQL, and only when the column exists. A pull
  > or a deploy before the migration keeps working: nothing fails, nothing is written to the field, and every export
  > shows it null. The tests cover both states."
  > I am amending my own item 4. Its last bullet read "after this merge every pull needs the migration before any
  > chain runs", and you built to it. But these are the two tables every chain reads and writes. Mapped, a checkout
  > that has not migrated fails on every odds query, the Kalshi captures and the closing runs included, until someone
  > runs the script; and the release ritual checks the tag out first and runs migrations by hand afterwards, with
  > the timers live. The ticker column was kept out of the ORM on 2026-10-04 for exactly this. That note is the
  > convention for these two tables.
  > - The writer. After the flush, the game's odds rows and its consensus snapshot rows get the value by Core SQL, as
  >   write_kalshi_tickers does. The existence check is not cached, as has_kalshi_ticker is not.
  > - The readers. The three export blocks read it through one guarded helper. Before the migration it answers
  >   nothing and each block shows null. oldest_source_time keeps its rule. Setting the value as a plain attribute on
  >   the rows a block already holds would leave the readers as they are; that is yours to choose.
  > - NormalizedOdds keeps the field. The migration script, its receipt and "no backfill" stand as built.
  > - Tests, beside the ones you have: on a database without the two columns, sync-odds-football writes its rows and
  >   snapshots, the three exports run and show null, and nothing raises. Then the migration, and the same run shows
  >   the values.
  > - The PR body's run order becomes: any order. The migration is still preceded by a backup and run by hand.
  >
  > 3. THE HOLD stands, for its other reason: the PR changes sync-odds-football, a step of the NFL closing chain. It
  > is not merged before the first watch-started NFL closing run has been read. The rebase of addendum 34 item 5
  > still applies once #404 is on main.
  >
  > 4. ORDER. Addendum 33 first, then addendum 34 item 7, then this.
- **Built (addendum 35 item 2):** both columns unmapped (schema.py notes, as `market_ticker`); `src/db/database.py` `has_source_time(table)` (one PRAGMA per call, never cached), `write_source_times(session, table, pairs)` (Core SQL UPDATE after the flush; 0 and nothing written before the migration), `attach_source_times(session, rows)` (the one guarded reader: sets the plain attribute `source_updated_at` on the Odds / OddsSnapshot rows a block already holds, None before the migration), so `oldest_source_time` and the three blocks read as before. `sync_odds_nfl` flushes each game's rows and snapshots and writes the field by Core SQL. `NormalizedOdds.source_updated_at`, the migration, its receipt and "no backfill" stand.
- RUN ORDER (addendum 35 item 2): any order; the migration is preceded by a `.backup` and run by hand. HELD (addendum 35 item 3): not merged before the first watch-started NFL closing run has been read.
