**2026-10-11 — FINDING + AUDIT (ARCHITECT 2026-10-10 08:27 ET, addendum 37 items 1 and 4; Issue #413): the shared Kalshi matcher puts markets on the wrong game; the read-only leg audit.**
- **Header (verbatim):**
  > ARCHITECT · 2026-10-10 08:27 ET · addendum 37 · FINDING: the shared Kalshi matcher puts markets on the wrong game.
  > Three rulings: the event's two teams place a market; legs of two events are never a pair; an audit. Behind 33, 36.2
  > CORRECTED 2026-10-11 07:08 ET: receipt B, row 32810 only. That row's final is right; no separate addendum follows.
- **Finding, item 1 (verbatim):**
  > 1. FINDING: ON THE SHARED PATH ONE TEAM NAME PLACES A MARKET, AND MARKETS LAND ON OTHER GAMES. A BACKLOG entry and
  > an Issue (finding); nothing is built by this item. The receipt is at the end.
  > - What the files show. The laptop's college file of today 11:52Z (081d9fa): 4 games whose two legs come from two
  >   Kalshi events, and a fifth holding one leg of another game's event. The host's card of 12:10Z (v1.3.0): 7 such
  >   games and 6 events split across two games. The PL, expansion, UNL, NHL, NFL and MLB files: none.
  > - From the code. Every market's title now reads "<Team> wins" (the consoles' sample lines: 'Stanford wins', 'Boston
  >   wins'), so title_teams (adapters/kalshi.py:200-211) answers None for every market, and gate 2 of the shared path
  >   runs on its fallback: the yes team alone (kalshi_sync.py:191-196). The soccer path was repaired for this on
  >   2026-09-13 (426-434, 456-457: the pair comes from the event's sibling markets). The shared path was not, and its
  >   sentinel never fired because the fallback kept matching.
  > - A tie between two games in view is still refused: I ran main's matcher on a throwaway database with both
  >   name-sharing games in view (ambiguous 2, nothing stored for either name). The wrong legs come when the market's
  >   own game is not in view. Two ways are receipted, and both reproduce on main's code:
  >   (a) The run's window. With no dates it is now-1d to now+2d (86-87). The run of 2026-10-08 21:56:38Z ended its
  >       window at 2026-10-10 21:56:38Z. Houston @ Kansas State 19:30Z, Florida A&M @ Alabama State 20:00Z and North
  >       Dakota @ Northern Iowa 21:00Z were inside it; Georgia @ Alabama 23:30Z, North Dakota State @ UNLV 23:00Z and
  >       Kansas @ Utah (02:15Z the next day, as stored then) were outside. That run wrote all three wrong legs:
  >       Alabama, North Dakota State and Kansas.
  >   (b) The time gate. Between the file of 10-09 22:09Z and today's, our kickoff for South Carolina State @
  >       Charleston Southern moved from 22:00Z to 16:00Z, and for Bethune-Cookman @ Alabama A&M from 23:00Z to
  >       17:00Z. Today's run stored South Carolina State's market on Coastal Carolina @ Marshall 23:00Z and Alabama
  >       A&M's on Georgia @ Alabama 23:30Z.
  > - Keep-first (307-310) then lets Kalshi's list order decide which of two markets a side keeps. In (b) the wrong
  >   market came first, and Coastal Carolina's own leg was dropped as a duplicate.
  > - The readers pair the newest snapshot of each side on its own (export.py:1122-1128, venue.py:229-241), and the
  >   block's captured_at is the newest leg's (export.py:1142). So a wrong leg written once stays. North Dakota's away
  >   leg has read 0.59/0.60 since Thursday, beside a home leg refreshed on every run, under today's capture time.
  > - No call of record is affected. College is market-only, and under the 2026-10-07 quote-age rule the venue engine
  >   emits no call. Without that rule the row is a call: the host's card (v1.3.0 predates the rule) shows Houston @
  >   Kansas State eligible, HOME, exec edge 39.0pp at 0.16, and its HOME leg is Kansas in Kansas @ Utah. The host's
  >   pager can also page a STALE-BOOK? flag or a line move built on such a leg.
  > - Not established: since when, and what it has done to the stored legs of MLB, NFL and NHL. Item 4 answers that.
- **Item 4 (verbatim):**
  > 4. A READ-ONLY AUDIT, small: scripts/kalshi_leg_audit.py [--since DATE]. Over the stored Kalshi snapshots that
  > carry a ticker, by series and by day: the games whose legs come from two events and the events whose legs sit on
  > two games, each with match id, teams, kickoff, tickers and capture times. Then the totals, the first day each
  > series shows one, and, of the games listed, those with a graded prediction. Captures from before the ticker
  > column cannot be checked: the receipt says how many those are. The operator runs it on both machines, and both
  > consoles go on the Issue. #308's final receipt waits for it, and no venue-edge call resumes before items 2 and 3
  > are on main and I have read both consoles.
- **Order, item 5 (verbatim):**
  > 5. ORDER. Addendum 33's two commits first, then addendum 36 item 2. Then items 2 and 3 here, as one PR or two: the
  > laptop writes these legs on every run, so I want them on main as soon as the review allows. Then item 4, the rest
  > of 36, 34 item 7 and 35. Not a tag blocker by itself.
- **Built (item 4):** `scripts/kalshi_leg_audit.py`. A day is the capture's UTC date; within one series and day, a TWO-EVENT GAME is a game whose legs captured that day name more than one event, a SPLIT EVENT an event whose legs captured that day sit on more than one game; the event is the ticker without its last segment (the rule of `src/walters/kalshi_legs.event_of`, #414), the series its first segment. Graded = a `predictions` row with a `prediction_outcomes` row. Untickered captures are counted, never checked; without the column nothing is checked and the console says so.
- **Where the rest stands:** item 2 (the matcher) waits for the Law 1 payload read on #412 (this container cannot reach Kalshi); item 3 (the guard) is #414.
- **Receipts:** tests/test_kalshi_leg_audit.py (4 tests): the receipt's North Dakota shape (a two-event game on 2026-10-08, the NDSUUNLV split on 2026-10-09), first day per series, the graded listed game, `--since`, clean and untickered games never listed, the no-column console, and the file byte-identical after a run.
