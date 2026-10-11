**2026-10-11 — RULING + BUILT (ARCHITECT 2026-10-10 08:27 ET, addendum 37 item 3; finding #413): legs of two events are never a pair.**
- **Ruling (verbatim):**
  > 3. RULED: LEGS OF TWO EVENTS ARE NEVER A PAIR.
  > "A game's Kalshi legs are read as a set only when their tickers name one event and that event's current legs sit
  > on no other game. Otherwise the row says mismatched and names the events, and nothing is computed from those
  > legs: no price, no normalized probability, no cost, no venue row, no line move, no close, no order line. Legs with
  > no stored ticker are read as before."
  > - Current legs: for each game and side, the newest stored leg before kickoff, as the readers take it today.
  > - In the exports: kalshi.status "mismatched" with the event tickers; kalshi_legs null; the exec fields null;
  >   input_quality.kalshi "mismatched"; desk_meta says the guard is on. An export contract change, so the PR template.
  > - One helper, used by every reader of stored legs. Enumerate the readers from the code and list them in the PR. I
  >   count at least: export.py (183-205, 709, 913, 1122-1142), venue.py (194, 229, 244), close.py close_from_kalshi,
  >   line_move.py _series, k_receipt.py (149-170), unl_ladders.py (112, 207), window.py (148), nfl_predict.py
  >   (221-276), mlb_odds_timing.py (98), closing.py price_captures and cli.py:5671.
  > - Nothing stored is deleted or rewritten. The wrong snapshots stay as history, and the guard is what stops them.
  > - Tests: today's five rows read mismatched and carry no number; a clean row is unchanged, the Desk golden included.
  > - Say in the PR how many rows of the laptop's current files it changes, by file. I expect the five, all college.
- **Built:** `src/walters/kalshi_legs.py`: `event_of` (the ticker without its last `-` segment), `judge` (pure), `current_tickers` / `homes_of` / `mismatched` (one SQLite query shape, run on a SQLAlchemy session or a sqlite3 connection), `guard_snaps` (for readers holding one game's ORM rows), `status_block`, `GUARD`. Before `migrate_kalshi_ticker.py` (`market_ticker` absent) it answers nothing.
- **Every reader of stored legs, from the code (rg `source == "kalshi"` / `source = 'kalshi'`), and what the guard does there:**
  - export.py `_collect_rows` (MLB / soccer `export-predictions`): legs dropped; `market.kalshi` = the mismatched block; exec null; `input_quality.kalshi` `mismatched`; so the Desk sees no Kalshi price, cost, venue or order.
  - export.py `_fixture_row` (export-fixtures, and through it the window card and the NHL / NCAA / INTL / expansion shadow files): `kalshi` = the mismatched block, `kalshi_legs` null, exec null, `input_quality.kalshi` `mismatched`, `counts.kalshi_mismatched`.
  - nfl_predict.py `export_nfl_predictions`: `guard_snaps`; `kalshi_prob` / exec / `kalshi_legs` / venue gap null; top-level `kalshi` block and `input_quality.kalshi` `mismatched` on that row only.
  - window.py `build_card`: the venue gap / STALE-BOOK? flag from guarded rows (none); the fixture row already says mismatched.
  - line_move.py `line_move_for_match` (`_series`): no Kalshi series from a mismatched game.
  - close.py `grading_close` and clv_restate.py `_close_for`: no Kalshi-only close from a mismatched game.
  - venue.py `kalshi_home_prob` / `latest_kalshi_by_selection` / `kalshi_legs`: pure over the rows their callers pass; every caller passes guarded rows.
  - k_receipt.py `ladders`, unl_ladders.py `receipt` (row reason `kalshi legs mismatched: …`), mlb_odds_timing.py (first Kalshi capture), cli.py `kalshi-disagreement`: mismatched games are not read.
  - deploy/hosting/closing.py `price_captures`: the Kalshi capture times of a mismatched game are none (the helper on the run's sqlite3 connection). Addendum 31's bound on closing.py is superseded here by addendum 37 item 3, which names `closing.py price_captures`.
  - scripts/kalshi_soccer_incomplete_receipt.py, scripts/kalshi_soccer_twoway_receipt.py: guarded the same way.
  - Not readers of legs: scripts/k0_kalshi_storage_probe.py (counts rows by market; reads no pair).
- **Readings:**
  1. "That event's current legs sit on no other game" reaches both games of a split event. In receipt A that makes eight rows mismatched, not five: the five, plus 32820 (North Dakota State @ UNLV, whose NDSUUNLV leg's event also sits on 32812), 32817 (South Carolina State @ Charleston Southern, SCSTCHSO also on 32772) and 32823 (Bethune-Cookman @ Alabama A&M, COOKAAMU also on 32738). Built as written; the three true games read mismatched until the wrong leg is no longer current on the other game.
  2. "Current" is computed by the helper from the stored rows (newest per game and side with `captured_at` before the stored kickoff, ties by id), not by each reader, so every reader judges on the same legs.
  3. Untickered legs name no event, so a game with one ticketed and one untickered leg is judged on the ticketed leg's event alone.
- **Rows changed in the laptop's current files:** not counted here (no file is reachable from this container). From the architect's receipt: fixtures_NCAA_2026-10-10.json, 8 by reading 1 (the five and their three partners); the PL, expansion, UNL, NHL, NFL and MLB files carry 0 split legs (receipt E), so 0.
- **Receipts:** tests/test_kalshi_leg_guard.py (10 tests): the receipt's five rows (and their three partners) read mismatched and carry no number in the fixtures row; a clean row and an untickered row unchanged; no venue price, no Kalshi line-move venue and no Kalshi-only close from a mismatched game; the closing run's capture read on a sqlite3 connection; the window card; before the migration nothing; nothing stored changed; `desk_meta.kalshi_leg_guard`. Four of them fail on main (fixtures row, venue/close, closing capture read, desk_meta). The Desk golden is unchanged.
