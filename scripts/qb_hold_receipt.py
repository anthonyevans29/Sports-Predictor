"""
THE QB HOLD, MEASURED (#446; ARCHITECT 2026-10-12 08:41 ET, addendum 44 item 9), READ-ONLY.

The ruling, verbatim (addendum 44 item 9): "Every NFL row the Desk calls PLAY with a QB flag or an unread list is kept
with what the page said, the price it named, the close, the result, and what was done about it. I read the receipt at
thirty such rows or at the season's end, whichever comes first. Nothing in the rule or the hold moves before that."

The build, verbatim (ARCHITECT 2026-11-02 08:30 ET, addendum 209 item 3): "the read-only receipt script of #446 is still
unbuilt and is the next ops item after today's PRs (Code: one PR, read-only, the rows from the closing and results
files, "what was done" from the ledger where a position exists, blank where none; no figure of the unit, no fill size
in the Issue)."

The would-be rows, verbatim (ARCHITECT 2026-11-02 11:20 ET, addendum 217 item 4): "#446's measurement keeps accruing on
paper — exec_cohorts and the closing page's hold check gain one cohort line for NFL while uncertified, "would-be PLAY
(uncertified, unstaked)", reading the record-only would-be call with the same QB-flag / unread-list classification,
never pooled with PLAY, never a position. #446's read at thirty rows counts those rows too, labelled."

The receipt's two questions, ruled, verbatim (ARCHITECT 2026-11-02 18:05 ET, addendum 223 item 5): "THE RECEIPT SCRIPT
PR (#446, 209 item 3) — its two questions, ruled: (a) "what was done" prints what the LEDGER holds, under the ledger's
own label for it (an operator fill prints as the ledger labels it; a would-be row with no ledger position stays blank);
the script reports and never relabels. It prints NO quantity, price, fee or P&L for any row, so a pasted console cannot
carry a fill size or let a reader infer the unit (209 item 3). (b) Results from the DB copy, as results-tally reads
them, STAYS — opened mode=ro + immutable=1 (198 item 6(ii)), the header naming the copy and the closing-file directory
as the two sources, a row whose game the copy lacks labelled "no result in this copy", never scored. It takes the slot
#800 freed."

Its three questions, ruled, verbatim (ARCHITECT 2026-11-03 07:55 ET, addendum 225 item 3): "#804 (the QB-hold receipt)
— its three questions: Q1 RULED by 2(a) above: a row the copy lacks ("no result in this copy"), a teams-differ row and a
void row each COUNT toward thirty as labelled, unscored rows, kept outside the W-L-P with their label (the change local
to collect(), as offered). Q2 CONFIRMED: "what was done" is the ledger's fills, never the Cockpit's claims (a claim is
what the page said). Q3 CONFIRMED as built: a would-be row's price line reads "none (PASS on the page)"; its exec edge
stays on the row. One push for Q1; CI green then my block. The count the script prints is the count; my "about fifteen"
was a read of the pages, not a rule."

Its follow-up's questions (#807), ruled, verbatim (ARCHITECT 2026-11-03 09:40 ET, addendum 231 item 2): "#807 — RULED:
(a) ITEM 3 FIRST, THE SOURCE AFTER THE CUTOVER: the same inversion as #688's (230 item 2(c)) — the receipt reads the
HOST's closing files (the mirror checkout's host/<date>/closing_NFL_*.json) with the HOST's backup copy via --db,
because match ids are machine-local and the host has been the writer of record since 10-26. The pre-cutover rows (the
hold's start 10-11 through 10-25) are the LAPTOP's closings with the laptop's database. So the receipt runs ONCE PER
MACHINE-ERA, two consoles posted together: the laptop run (its own exports/closing_NFL_*.json, its own DB, rows through
10-25) and the host run (--exports the mirror's host/ tree, --db the host's pulled backup, rows from 10-26); #446's
count toward thirty is the two counts' sum, stated on both consoles. The "host/ is never read" refusal of round 1 is
REMOVED: the header prints which directory and which copy were read, and my block pairs them; a run whose directory
and copy are different machines is the operator's error the header makes visible, not one the script can detect.
(b) ITEM 2 (the symlink into host/) dissolves with (a): host/ is a legitimate source when paired with the host's copy.
No refusal is built for it. (c) ITEM 1, "WHAT WAS DONE" ON UNSCORED ROWS: YES — positions() matches the ledger's fills
to EVERY row the receipt holds, scored or not (44 item 9 keeps "what was done" on every row; 225 item 3 made the
unscored rows rows of the count, so they carry it too); the label stays the ledger's; the LEDGER line drops "an
unscored row is not matched to fills". Local to positions(), as offered. One small PR for (a) and (c), read-only; then
my two blocks (the laptop run, the host run on Monday's pulled backup)."

Its follow-up's three questions (#810), ruled, verbatim (ARCHITECT 2026-11-03 11:10 ET, addendum 232 item 2): "#810
(#807) — RULED, one push, then my block: (a) THE SUM: each console prints ONE RUN'S count, labelled with its era and
its bound ("laptop era, runs through 2026-10-26T12:00:00Z: n of 30" / "host era, runs from 2026-10-26T12:00:00Z: m of
30"); `thirty_reached` is per run and is renamed to say so; the script takes NO other run's count as an input (an
input nobody verifies is not a receipt). The sum is my arithmetic on the two consoles, stated in my comment on #446.
(b) THE ERA BOUNDARY is the CLOSING RUN'S START INSTANT, in UTC: 2026-10-26T12:00:00Z (the cutover day; the first
closing the host wrote as writer of record was that evening's MNF; every earlier host closing was a P8 rehearsal).
`--through INSTANT` and `--from INSTANT` bound the run start, printed in the header; a run start exactly at the bound
belongs to the host era. KC@SEA (SNF 10-25 ET; the closing run started 2026-10-25 ~23:45Z) is the LAPTOP's row and
only the laptop's; the host's rehearsal closing of it is not a record and is excluded by the bound, not by hand. My
block passes the bounds. (c) THE HOST RUN'S SOURCE is the LAPTOP'S CUMULATIVE PULL, exports/host/ (pull_exports.py: a
flat directory, `find -maxdepth 1` of the host's exports/, rsync without --delete — nothing pulled is ever removed,
670 files today; the host's own exports/ is not pruned either: sp_prune.py is backups only), NOT the mirror checkout.
The mirror's 14-day retention is therefore not in the receipt's path and the timing note of item 3 falls away; it
stays as one line in the PR body for the record. The receipt reads a flat directory of closing_*.json OR a tree of
dated folders alike (never a latest/ folder), so the mirror checkout still works as a second source if ever needed.
The first host run is THIS WEEK on today's pulled backup, by my block, as soon as #810 merges; the laptop run the same
day."

The fill matching, a finding (#811), verbatim (ARCHITECT 2026-11-03 12:45 ET, addendum 233 item 1): "FINDING (ops; an
Issue, then a small read-only PR, the next slot after #413): THE RECEIPT MATCHED NONE OF THE LEDGER'S NFL FILLS. Both
runs read the Cockpit's export (bd_ledger_v1: calls 46, fills 931), found 8 NFL game fills, matched 0 to any of the 16
rows, and printed "what was done: not established" on every row — while the operator's Kalshi record of 11-02 (read by
me, never in the repo) holds Desk-call fills on at least one of those games (Baltimore @ Buffalo, 11-01, match 15149:
page PLAY HOME, QB-flagged). So the matcher's assumptions about the export's fill entries do not hold on the real file.
Code reads the Cockpit's own export function (tools/cockpit.html, "Export ledger (JSON)", the fills array: the real
keys for ticker, side, title, opened, closed, and whether the ticker is the market's or the event's, how a CSV-imported
fill carries its date) — law 1, from the code, not from a guess — then fixes `positions()` with a fixture in exactly
that shape with synthetic values; the test asserts the BUF-shaped case matches by event ticker and a CSV-imported fill
matches by the Cockpit's game matcher. If the code read leaves the shape ambiguous, the operator pastes ONE fill
entry's KEYS with every value redacted (never a quantity, price or fee) in the Issue. No fill figure enters the repo,
the Issue or the PR."

ONCE PER MACHINE-ERA (231 item 2(a); 232 item 2): match ids are machine-local, so a run reads ONE machine's closing
files with THAT machine's copy, and counts the rows of ONE era, bounded by the closing run's start instant in UTC
(232 item 2(b)). The laptop run: --exports the laptop's own exports/ (its closing_NFL_*.json), --db the laptop's
.backup copy, --through the era boundary (2026-10-26T12:00:00Z, the architect's block passes it). The host run:
--exports the laptop's cumulative pull of the host's exports, exports/host/ (deploy/hosting/pull_exports.py: a flat
directory, nothing pulled ever removed; 232 item 2(c)), --db the host's pulled backup, --from the era boundary. The
mirror checkout's host/ tree (host/<YYYY-MM-DD>/closing_NFL_*.json) is read the same way and stays a second source;
its 14-day retention is not in the receipt's path (232 item 2(c); a line for the record). The two consoles are posted
together; each console's COUNT is ONE run's count, labelled with its era and its bound (232 item 2(a)); the script
takes no other run's count as an input and adds none: the sum is the architect's arithmetic on the two consoles,
stated on #446 (232 item 2(a), which replaces 231 item 2(a)'s "the two counts' sum, stated on both consoles": no
console states a sum). The script cannot tell a machine: the SOURCES line prints the directory read
(resolved) and the copy read (resolved), and the architect's block pairs them; a directory and a copy of different
machines is the operator's error that line makes visible. host/ is read like any directory (round 1's refusal is
removed; a symlink into host/ is followed, 231 item 2(b)). The laptop run's own exports/ never reads its host/
subfolder (not a dated folder).

THE BOUND (232 item 2(b)): --from INSTANT and --through INSTANT bound the CLOSING RUN'S START (redated.closing_rows'
run start: the closing block's start, else the file name's stamp), each a UTC instant written YYYY-MM-DDTHH:MM:SSZ
in ASCII digits (nothing else is taken: a malformed instant is refused, exit 2, nothing read). --from is inclusive (start >= from),
--through exclusive (start < through): "a run start exactly at the bound belongs to the host era". Both bounds given
is a window (--from before --through, else refused: the window holds no instant). The bound applies to every closing
row BEFORE the one-row-per-game rule (and so before the void rule): a row of a run outside the bound is not read for
any game, not counted, and counted on the BOUND line (by run, by closing file, by closing row, and the NFL games left
with no row in the bound); a game of this receipt (a PLAY or would-be row on its newest run outside the bound) left
with no row in the bound is NAMED on its own line, "outside the bound (not counted)", so the exclusion is the
bound's and visible, never by hand. A closing row with NO run start (no closing block start, no stamp in the name)
cannot be placed in an era: a bounded run excludes it and names it on its own line, "run start unknown, outside every
bound", with its count (law 4: never guessed into an era); an unbounded run reads it as before. In a bounded run
the SOURCES line prints two spans, each labelled: the runs of every file read (before the bound) and the runs in the
bound. THE RUN'S LABEL
(232 item 2(a)): --through T only, "laptop era, runs through T"; --from F only, "host era, runs from F"; both, "window,
runs from F through T (no era: a window is neither era's run)"; neither, "unbounded run (no --from, no --through: no
era; not an era's count)". The label is the bound's, not a machine the script detects.

WHAT IT READS (each reading the conservative one, law 4; the keys are printed with the output):
- THE ROWS: the NFL closing files of the --exports directory (redated.closing_rows, the one reader:
  <exports>/closing_*.json, every file; and, for the mirror's layout (deploy/hosting/exports_mirror.py:
  <role>/<YYYY-MM-DD>/<file> plus <role>/latest/<kind>.json), the same glob in each dated folder
  <exports>/<YYYY-MM-DD>/, so --exports the mirror's host/ tree reads host/<date>/closing_NFL_*.json, 231 item 2(a);
  latest/ is never read, its files being copies of a dated folder's newest, which would read one run twice; no other
  subfolder is read; a file name found in more than one dated folder is counted on the SOURCES line, each copy read,
  the newest folder's copy the later of two equal runs; a flat directory, exports/host/ the laptop's pull, and a tree
  of dated folders, the mirror's, are read alike, 232 item 2(c)), the closing family NFL, the rows of the runs IN THE
  BOUND only (THE BOUND above). One row per game, exec_cohorts' rule (the void rule's selection): the newest
  run's row whose recorded start is within the Desk's clock drift (desk_policy.DESK_CLOCK_DRIFT) of the match's
  current start; with none within it, the newest run's row, void when redated.void_label says so.
- A PLAY ROW: desk.engine model_edge, desk.call PLAY, and one of the Desk's two QB tags on desk.tags
  (exec_cohorts.QB_TAGS: "QB-flagged half units", v1.1's QB rule; "QB unread half units", the empty-list rule of
  addendum 40 item 4).
- A WOULD-BE ROW (217 item 4): desk.call PASS with pass_kind market_only (addendum 214's NFL market-only rule), its
  record-only held call desk.market_only_hold.would_call PLAY, and one of the same two QB tags on desk.tags (the
  chain's tags ride the PASS row unchanged, desk_policy.nfl_market_only). Labelled "would-be PLAY (uncertified,
  unstaked)", on its own lines, never pooled with PLAY (every count and every JSON figure is per kind; only the count
  toward thirty adds the two, labelled), never a position of the Desk's.
- WHAT THE PAGE SAID: the call and the side (desk.pick, the team named), the QB tags as the Desk wrote them, and the
  Desk's own QB reasons (desk.reasons, or market_only_hold.would_reasons on a would-be row: the lines that begin
  "QB-flagged (" or "injury list empty ("), the exec edge (desk.exec.edge_pp) and the market reference
  (desk.market_ref). No unit figure is printed (209 item 3): the size is the tag's own words ("half units").
- THE PRICE IT NAMED: a PLAY's order limit (desk.order.limit, with its limit_basis). A would-be row's page named no
  price (it was PASS): the line says so and prints no other price (223 item 5: no price or fee for any row beyond the
  page's named price and the close; the record's exec cost, the ask plus the taker fee, is not printed). Never the
  order's contracts, its unit label or its text.
- THE CLOSE: the grading close, the results' own (close.grading_close_block on the match: the book close, the Kalshi
  mid where the rulings take one; its reference printed): the close's fair probability of the page's side. Unpriced is
  printed as such, never inferred.
- THE RESULT: from the database copy, as results-tally reads them (exec_cohorts.result_of: FINISHED with both scores
  decides; a level score is a push; CANCELLED / POSTPONED / STALE_ORPHAN void; anything else open), with the final
  score away-home (223 item 5(b): the results from the DB copy STAY). The header names the two sources: the copy read
  (--db) and the closing-file directory read (--exports), each resolved (231 item 2(a): the architect's block pairs
  them). No <sport>_results_<date>.json is opened.
- UNSCORED, COUNTED, LABELLED (225 item 3, by 225 item 2(a)): a row the hold touched counts toward thirty BEFORE the
  copy's checks; a row they leave out is kept outside the W-L-P, named beside the count by its cause, never scored
  (tallied per kind): a row whose game the copy lacks (its match id is not in the copy), labelled "no result in this
  copy" (223 item 5(b)); a row whose teams are not the copy's match (match ids are machine-local), "teams differ"; a
  void row, "re-dated void" (225 item 2(a)'s cause text), each with redated's own label (re-dated, or the placeholder
  kickoff: one void state, two labels, addendum 109 item 2 Q2; the UNSCORED line prints the head's split beside it,
  redated.void_counts: "re-dated N · placeholder kickoff M"). 225 item 2(a)'s fourth cause, non-taker basis, leaves no row out here: the receipt
  reads no cohort eligibility (no exec basis check), so a row of any basis is a scored row.
- WHAT WAS DONE (--ledger, the Cockpit's "Export ledger (JSON)" file, bd_ledger_v1_<date>.json): what the ledger holds
  on the row's game, under the ledger's own label for it (223 item 5(a)): the export's "fills" array, each entry
  printed under that key with its own field names (ticker, side, title, opened, closed) and its values as held,
  never relabelled (no "position", no side resolved to the page's). The same rule for a PLAY row and a would-be row.
  An entry is the row's game when its event ticker (the ticker less its last "-" part) is the event of the row's own
  order ticker or Kalshi legs; else when the Cockpit's game matcher fits it (src/walters/ledger_fills.py parse_ticker
  / side_fields, then game_fits on the row's teams, within a day of the ticker's date, the nearest start:
  ledger_fills._start_nearest); an entry that fits more than one row is ambiguous, counted, given to none (refusals
  stay refusals). Each entry prints on its own (a split or partial fill is its own entry); only the same entry, the
  same non-empty string id, is read once. NOTHING ELSE of an entry is printed: no quantity, price, fee, stake or P&L
  (qty, entry, exit, staked, fees, open_fee, close_fee, pnl_pre, pnl_net are never printed), and never its id (the
  CSV row it was imported from). A row with no entry is blank: "not established" (addendum 44 item 9 as addendum 46
  item 4 amended it, #446's first row: "What was done: blank, not established"). Without --ledger every row reads
  "not read (no --ledger)", never "not established". What was done is matched to EVERY row the receipt holds, scored
  or unscored (231 item 2(c)): an unscored row prints it at the end of its own line, under the same label, matched on
  the closing row's own teams, recorded start and Kalshi events (the game as the page named it: the copy lacks the
  match, or the copy's match is another game, or the game was re-dated); the LEDGER line's "of N" and the JSON's
  what_was_done count every row of the kind (its scored rows + its unscored rows: that kind's count toward thirty).
  THE ENTRY'S SHAPE, read from the Cockpit's code (#811; addendum 233 item 1, law 1): "Export ledger (JSON)" writes
  the stored ledger as held (loadLedger), and every fills entry is what importKalshiCSV stored (or an earlier export's
  entry merged as-is by id): {id (the CSV row's cells joined by U+241F: never printed), ticker (mapHeaders: the first
  header holding "ticker" but not "event", market_ticker on Kalshi's confirmed header, so the MARKET ticker with its
  -{SIDE} suffix, never the event's), side, the figures, opened / closed (Kalshi's open_timestamp / close_timestamp,
  raw strings, read by no matcher), title (market_title)} plus parseTicker's kind, family ("NFL"), sports, date (the
  ticker's own ET game date: a CSV-imported fill carries its date ONLY in its ticker), teams, sideCode, start (null
  without the ticker's HHMM, as the NFL game tickers the repo holds read) and sideFields' eight keys. The receipt
  re-parses the ticker as the Cockpit's classifyFills does (a stored kind or date is never trusted); positions()
  matches that shape by event ticker and by the game matcher (the tests pin both on the Cockpit's own entry), so the
  0 of 16 is not a key of the entry misread: what the real file's entries hold is open on #811. A Desk call's fill
  recorded through the Cockpit's Record-fill control lives on the CALL (order_type, fill_price), not in fills, and is
  not read (225 item 3 Q2: "the ledger's fills, never the Cockpit's claims").
- THE COUNT toward thirty: every row the hold touched, PLAY rows + would-be rows (217 item 4: counted too, labelled),
  each kind's count its scored rows + its unscored rows (225 item 3: "a row the copy lacks ("no result in this copy"),
  a teams-differ row and a void row each COUNT toward thirty as labelled, unscored rows, kept outside the W-L-P with
  their label"), beside it each kind's W-L-P / void / open (the scored rows only) and its unscored rows by cause. The
  printed count is the count (225 item 3: "The count the script prints is the count"). The one figure that adds the
  two kinds; every other count (rows with fills, not established, unscored) is printed and keyed per kind. A running
  count, never a verdict: the read is the architect's, at thirty rows or the season's end. It is ONE RUN'S count
  (232 item 2(a)), printed under the run's label (THE BOUND above: "laptop era, runs through T: n of 30" / "host era,
  runs from F: m of 30"); the JSON's this_run_thirty_reached is this run's count alone at thirty; #446's count toward
  thirty is the architect's sum of the two consoles, stated on #446, never an input or a figure of this script's.

Refusals (exit 2, nothing read, nothing written): --from or --through not a UTC instant YYYY-MM-DDTHH:MM:SSZ, or
--from not before --through (232 item 2(b)); --db missing, empty, under the repo's data/ (the checkout's, and the
main checkout's from a worktree; by path or identity: mlb_pitchers_gate.check_db; a data/ elsewhere is not refused),
the app's configured database, no file there (never created), a -wal / -shm / -journal file beside it (immutable=1
would ignore it: nfl_v2_gate.check_db's rule), or a copy that cannot be read as the schema the read needs; --exports
not a directory (a directory named host is read, by its own name or through a symlink: round 1's refusal is removed,
231 item 2(a) and (b)); --ledger unreadable, or not a bd_ledger_v1 export (no calls array; a call or a
fill that is not an object; fills not an array; a fill whose ticker, side, title, opened or closed is present and not
a string: the Cockpit's export writes each as the CSV's string or null, and the field is named, its value never
echoed). --db opens mode=ro&immutable=1 (mlb_pitchers_gate.readonly_session; addendum 198 item 6(ii)).
Writes nothing: no database row, no ledger, no file.

Last line: QB-HOLD-RECEIPT {json} (counts only; no unit, size or dollar figure).

    python3 scripts/qb_hold_receipt.py --db COPY --exports DIR [--from INSTANT] [--through INSTANT]
                                       [--ledger bd_ledger_v1_<date>.json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REFUSED = 2
FAMILY = "NFL"
READ_AT = 30
SIDECARS = ("-wal", "-shm", "-journal")      # nfl_v2_gate.check_db's rule: immutable=1 would ignore each of them
PLAY_LABEL = "PLAY (the Desk's call), QB-flagged or unread"
WOULD_LABEL = "would-be PLAY (uncertified, unstaked)"           # addendum 217 item 4, the label verbatim
NOT_ESTABLISHED = "not established"                            # addendum 46 item 4: blank where no position
NOT_READ = "not read (no --ledger)"
LEDGER_LABEL = "fills"                       # the bd_ledger_v1 export's own key for what it holds (223 item 5(a))
LEDGER_FIELDS = ("ticker", "side", "title", "opened", "closed")  # an entry's own field names; never a figure, never id
NO_RESULT = "no result in this copy"                           # addendum 223 item 5(b), the label verbatim
# the unscored rows' causes (225 item 3, by 225 item 2(a)): each counted toward thirty, labelled, never scored
UNSCORED_HEADS = (("no_result", NO_RESULT), ("teams", "teams differ"), ("void", "re-dated void"))
QB_REASON_HEADS = ("QB-flagged (", "injury list empty (")       # desk_policy's two QB reasons, as it writes them
ET = ZoneInfo("America/New_York")

RULING_44_9 = ("Every NFL row the Desk calls PLAY with a QB flag or an unread list is kept with what the page said, the "
               "price it named, the close, the result, and what was done about it. I read the receipt at thirty such "
               "rows or at the season's end, whichever comes first. Nothing in the rule or the hold moves before that.")
RULING_209_3 = ("the read-only receipt script of #446 is still unbuilt and is the next ops item after today's PRs (Code: "
                "one PR, read-only, the rows from the closing and results files, \"what was done\" from the ledger "
                "where a position exists, blank where none; no figure of the unit, no fill size in the Issue).")
RULING_217_4 = ("#446's measurement keeps accruing on paper — exec_cohorts and the closing page's hold check gain one "
                "cohort line for NFL while uncertified, \"would-be PLAY (uncertified, unstaked)\", reading the "
                "record-only would-be call with the same QB-flag / unread-list classification, never pooled with "
                "PLAY, never a position. #446's read at thirty rows counts those rows too, labelled.")
RULING_223_5 = ("THE RECEIPT SCRIPT PR (#446, 209 item 3) — its two questions, ruled: (a) \"what was done\" prints what "
                "the LEDGER holds, under the ledger's own label for it (an operator fill prints as the ledger labels it; "
                "a would-be row with no ledger position stays blank); the script reports and never relabels. It prints "
                "NO quantity, price, fee or P&L for any row, so a pasted console cannot carry a fill size or let a "
                "reader infer the unit (209 item 3). (b) Results from the DB copy, as results-tally reads them, STAYS — "
                "opened mode=ro + immutable=1 (198 item 6(ii)), the header naming the copy and the closing-file "
                "directory as the two sources, a row whose game the copy lacks labelled \"no result in this copy\", "
                "never scored. It takes the slot #800 freed.")
RULING_225_3 = ("#804 (the QB-hold receipt) — its three questions: Q1 RULED by 2(a) above: a row the copy lacks (\"no "
                "result in this copy\"), a teams-differ row and a void row each COUNT toward thirty as labelled, "
                "unscored rows, kept outside the W-L-P with their label (the change local to collect(), as offered). "
                "Q2 CONFIRMED: \"what was done\" is the ledger's fills, never the Cockpit's claims (a claim is what the"
                " page said). Q3 CONFIRMED as built: a would-be row's price line reads \"none (PASS on the page)\"; its"
                " exec edge stays on the row. One push for Q1; CI green then my block. The count the script prints is"
                " the count; my \"about fifteen\" was a read of the pages, not a rule.")
RULING_231_2 = ("#807 — RULED: (a) ITEM 3 FIRST, THE SOURCE AFTER THE CUTOVER: the same inversion as #688's (230 item "
                "2(c)) — the receipt reads the HOST's closing files (the mirror checkout's host/<date>/closing_NFL_*.json)"
                " with the HOST's backup copy via --db, because match ids are machine-local and the host has been the "
                "writer of record since 10-26. The pre-cutover rows (the hold's start 10-11 through 10-25) are the "
                "LAPTOP's closings with the laptop's database. So the receipt runs ONCE PER MACHINE-ERA, two consoles "
                "posted together: the laptop run (its own exports/closing_NFL_*.json, its own DB, rows through 10-25) "
                "and the host run (--exports the mirror's host/ tree, --db the host's pulled backup, rows from 10-26); "
                "#446's count toward thirty is the two counts' sum, stated on both consoles. The \"host/ is never "
                "read\" refusal of round 1 is REMOVED: the header prints which directory and which copy were read, and "
                "my block pairs them; a run whose directory and copy are different machines is the operator's error the "
                "header makes visible, not one the script can detect. (b) ITEM 2 (the symlink into host/) dissolves "
                "with (a): host/ is a legitimate source when paired with the host's copy. No refusal is built for it. "
                "(c) ITEM 1, \"WHAT WAS DONE\" ON UNSCORED ROWS: YES — positions() matches the ledger's fills to EVERY "
                "row the receipt holds, scored or not (44 item 9 keeps \"what was done\" on every row; 225 item 3 made "
                "the unscored rows rows of the count, so they carry it too); the label stays the ledger's; the LEDGER "
                "line drops \"an unscored row is not matched to fills\". Local to positions(), as offered. One small PR "
                "for (a) and (c), read-only; then my two blocks (the laptop run, the host run on Monday's pulled "
                "backup).")
RULING_232_2 = ("#810 (#807) — RULED, one push, then my block: (a) THE SUM: each console prints ONE RUN'S count, labelled "
                "with its era and its bound (\"laptop era, runs through 2026-10-26T12:00:00Z: n of 30\" / \"host era, runs "
                "from 2026-10-26T12:00:00Z: m of 30\"); `thirty_reached` is per run and is renamed to say so; the script "
                "takes NO other run's count as an input (an input nobody verifies is not a receipt). The sum is my "
                "arithmetic on the two consoles, stated in my comment on #446. (b) THE ERA BOUNDARY is the CLOSING RUN'S "
                "START INSTANT, in UTC: 2026-10-26T12:00:00Z (the cutover day; the first closing the host wrote as writer "
                "of record was that evening's MNF; every earlier host closing was a P8 rehearsal). `--through INSTANT` "
                "and `--from INSTANT` bound the run start, printed in the header; a run start exactly at the bound "
                "belongs to the host era. KC@SEA (SNF 10-25 ET; the closing run started 2026-10-25 ~23:45Z) is the "
                "LAPTOP's row and only the laptop's; the host's rehearsal closing of it is not a record and is excluded "
                "by the bound, not by hand. My block passes the bounds. (c) THE HOST RUN'S SOURCE is the LAPTOP'S "
                "CUMULATIVE PULL, exports/host/ (pull_exports.py: a flat directory, `find -maxdepth 1` of the host's "
                "exports/, rsync without --delete — nothing pulled is ever removed, 670 files today; the host's own "
                "exports/ is not pruned either: sp_prune.py is backups only), NOT the mirror checkout. The mirror's "
                "14-day retention is therefore not in the receipt's path and the timing note of item 3 falls away; it "
                "stays as one line in the PR body for the record. The receipt reads a flat directory of closing_*.json OR "
                "a tree of dated folders alike (never a latest/ folder), so the mirror checkout still works as a second "
                "source if ever needed. The first host run is THIS WEEK on today's pulled backup, by my block, as soon as "
                "#810 merges; the laptop run the same day.")
MACHINE_ERA = ("MACHINE-ERA (231 item 2(a); 232 item 2): one run per machine-era, the two consoles posted together — "
               "the laptop run (--exports its own exports/, --db its own copy, --through the era boundary) and the host "
               "run (--exports exports/host/, the laptop's cumulative pull of the host's exports, pull_exports.py, "
               "flat, nothing pulled ever removed; --db the host's pulled backup; --from the era boundary); the era "
               "boundary is the closing run's start instant in UTC, a run start exactly at it the host era's (232 item "
               "2(b)); this console's COUNT is ONE run's count, labelled with its era and its bound; the script takes "
               "no other run's count as an input and adds none: the sum is the architect's arithmetic on the two "
               "consoles, stated on #446 (232 item 2(a)); the SOURCES line names the directory and the copy read, and "
               "the architect's block pairs them (a directory and a copy of different machines is the operator's "
               "error, which the script cannot detect)")
INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")  # ASCII digits only   # a UTC instant, 2026-10-26T12:00:00Z (232 item 2(b))
OUTSIDE = "outside the bound (not counted)"
UNKNOWN = "run start unknown, outside every bound"
DATED = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"                       # the mirror's dated folder, <role>/<YYYY-MM-DD>/ (exports_mirror.plan)
KEYS = ("rows = the NFL closing files (<exports>/closing_*.json and each dated folder's <exports>/<YYYY-MM-DD>/"
        "closing_*.json, the mirror's layout; never latest/), the runs in the bound only (--from inclusive, --through "
        "exclusive, on the closing run's start, UTC; 232 item 2(b)), one per game (exec_cohorts' rule: the newest run's row within the Desk's clock "
        "drift of the match's current start) · PLAY = desk.call PLAY with a QB tag (exec_cohorts.QB_TAGS) · would-be "
        "= desk.call PASS, pass_kind market_only, market_only_hold.would_call PLAY, with a QB tag · price named = a "
        "PLAY's desk.order.limit; a would-be row names none · close = close.grading_close_block's fair for the page's "
        "side · result = the database copy, as results-tally reads it (exec_cohorts.result_of) · unscored = a row the "
        "copy's checks leave out, labelled by its cause (a game the copy lacks: \"no result in this copy\"; teams "
        "differ; re-dated void), never scored, outside the W-L-P, and COUNTED toward thirty (225 item 3) · what was done = what the ledger holds on the game (by event "
        "ticker, else the Cockpit's game matcher), under its own label: fills, each entry's ticker, side, title, "
        "opened, closed as held; never a quantity, price, fee or P&L; none: not established; matched to every row, "
        "scored or unscored (231 item 2(c); an unscored row on its closing row's own teams and start); an entry is the "
        "Cockpit's importKalshiCSV entry (ticker the market ticker, its date the ticker's own; #811) · count toward thirty = "
        "each kind's scored rows + its unscored rows; the printed count is the count (225 item 3) · every count is "
        "per kind; only the count toward thirty adds the two · the count is ONE run's, under the run's label (232 "
        "item 2(a)); #446's sum of the two runs is the architect's, on #446")


class Refused(Exception):
    """A refusal: printed as REFUSED, exit 2."""


# ------------------------------------------------------------------------------------------------- the ledger --

def read_ledger(path) -> dict:
    """The Cockpit's ledger export, or Refused: not readable, not JSON, or not a bd_ledger_v1 export (no calls array;
    a call or a fill that is not an object; fills present and not an array; a fill's LEDGER_FIELDS value present and
    not a string: the field named, the value never echoed)."""
    try:
        with open(path) as fh:
            L = json.load(fh)
    except (OSError, ValueError) as e:
        raise Refused(f"--ledger {path}: cannot read the ledger export ({type(e).__name__}); nothing read") from None
    if not isinstance(L, dict) or not isinstance(L.get("calls"), list):
        raise Refused(f"--ledger {path}: not a bd_ledger_v1 export (no calls array); nothing read")
    if any(not isinstance(c, dict) for c in L["calls"]):
        raise Refused(f"--ledger {path}: a call is not an object; nothing read")
    fills = L.get("fills", [])
    if fills is None:
        fills = []
    if not isinstance(fills, list) or any(not isinstance(f, dict) for f in fills):
        raise Refused(f"--ledger {path}: fills is not an array of objects; nothing read")
    for f in fills:          # the printable fields are the export's strings or null; a figure there is never printed
        for k in LEDGER_FIELDS:
            if f.get(k) is not None and not isinstance(f[k], str):
                raise Refused(f"--ledger {path}: a fill's {k} is not a string or null (the value is not printed); "
                              "nothing read")
    return {"calls": L["calls"], "fills": fills}


def _event(ticker) -> str | None:
    t = str(ticker or "").strip().upper()
    return t.rsplit("-", 1)[0] if "-" in t else None


def _row_events(row: dict, desk: dict) -> set:
    """The Kalshi events the row names: its order's ticker and its legs' tickers (the market less its side)."""
    out = set()
    order = desk.get("order") if isinstance(desk.get("order"), dict) else {}
    legs = row.get("kalshi_legs") if isinstance(row.get("kalshi_legs"), dict) else {}
    for t in [order.get("ticker")] + [(v or {}).get("ticker") for v in legs.values() if isinstance(v, dict)]:
        e = _event(t)
        if e:
            out.add(e)
    return out


def positions(L: dict, rows: list[dict]) -> dict:
    """`rows` is EVERY row the receipt holds, scored and unscored (231 item 2(c): "positions() matches the ledger's
    fills to EVERY row the receipt holds, scored or not"); each carries key, events, home, away and kickoff_iso (an
    unscored row: its closing row's own, or None where the row records no start, then matched by its events only).
    {row key: [{ticker, side, title, opened, closed}, ...] one per entry}: each fills entry on the row's game, its
    own field names and values as held (LEDGER_FIELDS; 223 item 5(a): never relabelled), "ambiguous": entries that fit
    more than one row, "nfl_fills": the NFL game entries read. Every entry stays its own (a split or partial fill whose
    printed fields match another's is still two entries); only the same entry (the same non-empty string id) is read
    once, and an entry with no id is never deduped. The id is read for that and printed nowhere. The matcher reads the
    ticker, side and title; nothing else of an entry is kept: no quantity, price, fee, P&L or id.
    The entry is the export's as the Cockpit's importKalshiCSV stored it (tools/cockpit.html; #811, addendum 233 item
    1): `ticker` the CSV's MARKET ticker (KX{FAM}GAME-{yyMONdd}[hhmm]{AWAY}{HOME}-{SIDE}), its date the ticker's own
    (`opened` / `closed` are Kalshi's raw strings, read by no matcher). An event ticker with no side or another NFL
    series is no sport market under the Cockpit's parseTicker, so it is not an NFL game entry (the Cockpit's parse is
    the rule)."""
    from src.walters import ledger_fills as lf
    found: dict = {}
    amb = nfl = 0
    seen: set = set()
    for f in L["fills"]:
        fid = f.get("id")
        if isinstance(fid, str) and fid:
            if fid in seen:
                continue
            seen.add(fid)
        fx = {**f, **lf.parse_ticker(f.get("ticker"))}
        if fx.get("kind") != "sport" or fx.get("family") != FAMILY:
            continue
        nfl += 1
        fx.update(lf.side_fields(fx, fx.get("title"), fx.get("side")))
        ev = _event(f.get("ticker"))
        cands = [r for r in rows if ev and ev in r["events"]]
        if not cands:
            near = [r for r in rows if lf.day_diff((r["kickoff_iso"] or "")[:10], fx.get("date")) <= 1
                    and lf.game_fits(fx, {"home": r["home"], "away": r["away"]})]
            cands = lf._start_nearest(fx, [{**r, "kickoff": r["kickoff_iso"]} for r in near])
        keys = list(dict.fromkeys(r["key"] for r in cands))
        if len(keys) > 1:
            amb += 1
            continue
        if not keys:
            continue
        found.setdefault(keys[0], []).append({k: f.get(k) for k in LEDGER_FIELDS})
    return {"by_row": found, "ambiguous": amb, "nfl_fills": nfl}


def done_text(ps: list[dict] | None, ledger_read: bool) -> str:
    """'what was done' (223 item 5(a)), the same rule for a PLAY row and a would-be row: what the ledger holds on the
    game, under its own label (LEDGER_LABEL, each entry's LEDGER_FIELDS as held, JSON), never relabelled; blank ("not
    established", 46 item 4) where it holds nothing; "not read (no --ledger)" without the file."""
    if not ledger_read:
        return NOT_READ
    if not ps:
        return NOT_ESTABLISHED
    return f"{LEDGER_LABEL}: " + "; ".join(json.dumps(p, ensure_ascii=False) for p in ps)


# --------------------------------------------------------------------------------------------------- the rows --

def classify(desk: dict) -> str | None:
    """"play", "would" or None (not a row of this receipt)."""
    from src.walters import desk_policy
    from src.walters.exec_cohorts import QB_TAGS
    tags = desk.get("tags") if isinstance(desk.get("tags"), list) else []
    if not {t for t in tags if isinstance(t, str)} & set(QB_TAGS):
        return None
    if desk.get("engine") != "model_edge":
        return None
    if desk.get("call") == "PLAY":
        return "play"
    hold = desk.get("market_only_hold") if isinstance(desk.get("market_only_hold"), dict) else {}
    if (desk.get("call") == "PASS" and desk.get("pass_kind") == desk_policy.NFL_MARKET_ONLY_KIND
            and hold.get("would_call") == "PLAY"):
        return "would"
    return None


def _num(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def parse_instant(text, flag) -> datetime:
    """A bound (232 item 2(b)): a UTC instant written YYYY-MM-DDTHH:MM:SSZ, as naive UTC (the run starts'
    redated.as_utc form), or Refused: nothing else is taken (no offset, no date alone, no space for the T)."""
    s = str(text)
    try:
        if not INSTANT.fullmatch(s):
            raise ValueError
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise Refused(f"{flag} {s!r}: not a UTC instant YYYY-MM-DDTHH:MM:SSZ (232 item 2(b)); nothing read") from None


def _z(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_label(lo: datetime | None, hi: datetime | None) -> tuple[str, str]:
    """(era, label) of the run (232 item 2(a)): the bound's, never a machine the script detects."""
    if lo is None and hi is None:
        return "unbounded", "unbounded run (no --from, no --through: no era; not an era's count)"
    if lo is None:
        return "laptop", f"laptop era, runs through {_z(hi)}"
    if hi is None:
        return "host", f"host era, runs from {_z(lo)}"
    return "window", f"window, runs from {_z(lo)} through {_z(hi)} (no era: a window is neither era's run)"


def in_bound(run: datetime | None, lo: datetime | None, hi: datetime | None) -> bool | None:
    """True / False on a known run start (--from inclusive, --through exclusive: a run start exactly at the bound is
    the host era's, 232 item 2(b)); None on an unknown run start under a bound (it cannot be placed in an era)."""
    if lo is None and hi is None:
        return True
    if run is None:
        return None
    return (lo is None or run >= lo) and (hi is None or run < hi)


def read_closings(exports_dir, lo: datetime | None = None, hi: datetime | None = None) -> dict:
    """redated.closing_rows (the one reader) on <exports_dir>, and on each dated folder <exports_dir>/<YYYY-MM-DD>/
    (the mirror's layout, deploy/hosting/exports_mirror.py: --exports the mirror's host/ tree reads
    host/<date>/closing_*.json, 231 item 2(a); a flat directory, exports/host/, is its top alone, 232 item 2(c));
    latest/ and any other subfolder are never read. The same shape as closing_rows' ("rows", "files", "unreadable",
    "runs"), merged: each match's entries IN THE BOUND (in_bound: lo inclusive, hi exclusive, on the run start) from
    every folder, oldest run first (equal runs keep the folder order, the newest dated folder last), plus "dated": the
    dated folders read, "repeated": the closing-file names found in more than one folder read (each copy read),
    "runs_in": the span of the run starts IN THE BOUND ("runs" is every file's, before the bound),
    "outside": {match id: entries} of a known run start outside the bound, "unknown": {match id: entries} with no run
    start under a bound, and "files_of": {match id: [file, ...]} beside "outside" / "unknown" (the folder-prefixed
    file of each entry, for the BOUND line's by-file count)."""
    from src.walters.redated import CLOSING_GLOB, closing_rows
    d = Path(exports_dir)
    dirs = [d] + sorted(p for p in d.iterdir() if p.is_dir() and re.fullmatch(DATED, p.name))
    rows: dict = {}
    out_rows: dict = {}
    unk_rows: dict = {}
    files, bad, runs, names = 0, [], [], {}
    for sub in dirs:
        cr = closing_rows(sub)
        files += cr["files"]
        pre = "" if sub == d else f"{sub.name}/"
        bad += [pre + n for n in cr["unreadable"]]
        if cr["runs"]:
            runs += list(cr["runs"])
        for n in (p.name for p in sub.glob(CLOSING_GLOB)):
            names[n] = names.get(n, 0) + 1
        for mid, v in cr["rows"].items():
            srcs = cr["exports"].get(mid) or [{}] * len(v)
            for e, src in zip(v, srcs):
                where = {True: rows, False: out_rows, None: unk_rows}[in_bound(e[0], lo, hi)]
                where.setdefault(mid, []).append((*e, pre + str(src.get("file"))))
    for bucket in (rows, out_rows, unk_rows):
        for v in bucket.values():
            v.sort(key=lambda x: (x[0] is not None, x[0] or datetime.min))
    return {"rows": {mid: [x[:3] for x in v] for mid, v in rows.items()}, "files": files, "unreadable": bad,
            "runs": (min(runs), max(runs)) if runs else None, "dated": len(dirs) - 1,
            "runs_in": (min(ins), max(ins)) if (ins := [x[0] for v in rows.values() for x in v if x[0] is not None])
            else None,
            "repeated": sorted(n for n, k in names.items() if k > 1),
            "outside": {mid: [x[:3] for x in v] for mid, v in out_rows.items()},
            "unknown": {mid: [x[:3] for x in v] for mid, v in unk_rows.items()},
            "files_of": {k: {mid: [x[3] for x in v] for mid, v in b.items()}
                         for k, b in (("outside", out_rows), ("unknown", unk_rows))}}


def excluded(cr: dict) -> dict:
    """The BOUND line's figures (232 item 2(b)): the NFL closing rows left out by the bound, by run (the distinct run
    starts), by closing file and by row, the NFL games left with no row in the bound, and the receipt's own games
    among those, NAMED: {"outside": {...}, "unknown": {...}}, each {"runs", "files", "rows", "games", "named":
    [{"kind", "text"}]} ("runs" None for unknown). A game named is one with no row in the bound whose newest entry
    of that bucket (outside: the newest known run; unknown: the newest file order) is an NFL row of this receipt
    (classify): a PLAY or a would-be row; a game with an outside entry is named under outside only."""
    res = {}
    for key in ("outside", "unknown"):
        ents = cr[key]
        nfl = {mid: [(e, f) for e, f in zip(v, cr["files_of"][key][mid]) if e[1] == FAMILY] for mid, v in ents.items()}
        nfl = {mid: v for mid, v in nfl.items() if v}
        games = [mid for mid in nfl if mid not in cr["rows"] and (key == "outside" or mid not in cr["outside"])]
        named = []
        for mid in sorted(games):
            run, _, row = nfl[mid][-1][0]
            desk = row.get("desk") if isinstance(row.get("desk"), dict) else {}
            kind = classify(desk)
            if kind is None:
                continue
            tag = WOULD_LABEL if kind == "would" else "PLAY"
            game = f"{row.get('away_team') or '?'} @ {row.get('home_team') or '?'}"
            when = f", run {run:%Y-%m-%d %H:%M}Z" if run is not None else ", run start unknown"
            named.append({"kind": kind, "text": f"match {mid} {game} ({tag}{when})"})
        res[key] = {"runs": len({e[0] for v in nfl.values() for e, _ in v}) if key == "outside" else None,
                    "files": len({f for v in nfl.values() for _, f in v}),
                    "rows": sum(len(v) for v in nfl.values()), "games": len(games), "named": named}
    return res


def collect(s, exports_dir, lo: datetime | None = None, hi: datetime | None = None) -> dict:
    """The receipt's rows from the closing files of the runs in the bound (read_closings; lo inclusive, hi exclusive,
    232 item 2(b)) and the database copy `s` (read-only; nothing written): "bound" (excluded()'s figures: what the
    bound left out, by run, file, row and game, the receipt's games among them named), "rows" (the scored rows), "unscored" (per kind, by cause, UNSCORED_HEADS: each {"text": named with its label, and
    the closing row's own key, events, home, away and kickoff_iso, the fields positions() matches on, 231 item 2(c)},
    never scored, kept outside the W-L-P) and "toward_thirty" (per kind: its scored rows + its unscored rows; 225 item
    3: a row the copy lacks, a teams-differ row and a void row each COUNT toward thirty as labelled, unscored rows)."""
    from src.db.schema import Match
    from src.walters.close import grading_close_block
    from src.walters.exec_cohorts import QB_TAGS, _within, result_of
    from src.walters.redated import as_utc, void_label

    cr = read_closings(exports_dir, lo, hi)
    rows = []
    unscored = {k: {key: [] for key, _ in UNSCORED_HEADS} for k in ("play", "would")}
    nfl_matches = 0
    for mid in sorted(cr["rows"]):
        entries = cr["rows"][mid]
        m = s.get(Match, mid)
        lab = None
        if m is None:
            e = entries[-1]
        else:
            near = _within(entries, m.utc_date)
            if near:
                e = near[-1]
            else:
                lab = void_label([(run, r.get("utc_date")) for run, _, r in entries], m.utc_date)
                e = entries[-1]
        if e[1] != FAMILY:
            continue
        nfl_matches += 1
        row = e[2]
        desk = row.get("desk") if isinstance(row.get("desk"), dict) else {}
        kind = classify(desk)
        if kind is None:
            continue
        game = f"{row.get('away_team') or '?'} @ {row.get('home_team') or '?'}"
        tag = WOULD_LABEL if kind == "would" else "PLAY"
        rko = as_utc(row.get("utc_date"))
        # an unscored row is matched to fills on the page's own game (231 item 2(c)): the closing row's teams and start
        page = {"key": mid, "home": row.get("home_team"), "away": row.get("away_team"),
                "kickoff_iso": rko.strftime("%Y-%m-%dT%H:%M:%S") if rko else None, "events": _row_events(row, desk)}
        if m is None:
            unscored[kind]["no_result"].append({**page, "text": f"match {mid} {game} ({tag})"})
            continue
        h = m.home_team.name if m.home_team else None
        a = m.away_team.name if m.away_team else None
        if (row.get("home_team"), row.get("away_team")) != (h, a):
            unscored[kind]["teams"].append({**page, "text": f"match {mid} {game} ({tag}; this database's match {mid} "
                                                            f"is {a or '?'} @ {h or '?'})"})
            continue
        if lab:
            unscored[kind]["void"].append({**page, "text": f"match {mid} {game} ({tag}): {lab}"})
            continue
        pick = desk.get("pick")
        hold = desk.get("market_only_hold") if isinstance(desk.get("market_only_hold"), dict) else {}
        reasons = hold.get("would_reasons") if kind == "would" else desk.get("reasons")
        reasons = [x for x in (reasons if isinstance(reasons, list) else [])
                   if isinstance(x, str) and x.startswith(QB_REASON_HEADS)]
        tags = [t for t in desk.get("tags") or [] if isinstance(t, str) and t in QB_TAGS]
        ex = desk.get("exec") if isinstance(desk.get("exec"), dict) else {}
        order = desk.get("order") if isinstance(desk.get("order"), dict) else {}
        cb = grading_close_block(s, m)
        fair = (cb.get("close_fair") or {}).get(pick) if pick in ("HOME", "AWAY") else None
        res = result_of(m, pick)
        ko = as_utc(m.utc_date)
        rows.append({
            "key": mid, "kind": kind, "match_id": mid, "home": h, "away": a, "pick": pick,
            "team": {"HOME": h, "AWAY": a}.get(pick), "kickoff_iso": ko.strftime("%Y-%m-%dT%H:%M:%S"),
            "kickoff_et": ko.replace(tzinfo=timezone.utc).astimezone(ET).strftime("%Y-%m-%d %H:%M ET"),
            "run": e[0], "tags": tags, "qb_reasons": reasons,
            "exec_edge_pp": _num(ex.get("edge_pp")), "market_ref": _num(desk.get("market_ref")),
            "limit": _num(order.get("limit")) if kind == "play" else None,
            "limit_basis": order.get("limit_basis") if kind == "play" else None,
            "close": _num(fair), "close_reference": cb.get("close_reference"), "close_books": cb.get("close_books"),
            "result": res, "score": (m.away_score, m.home_score), "events": _row_events(row, desk)})
    rows.sort(key=lambda r: (r["kickoff_iso"], r["match_id"]))
    toward = {k: sum(1 for r in rows if r["kind"] == k) + sum(len(v) for v in unscored[k].values())
              for k in ("play", "would")}
    return {"rows": rows, "unscored": unscored, "toward_thirty": toward, "files": cr["files"],
            "unreadable": cr["unreadable"], "runs": cr["runs"], "runs_in": cr["runs_in"], "nfl_matches": nfl_matches,
            "dated": cr["dated"],
            "repeated": cr["repeated"], "bound": excluded(cr)}


# -------------------------------------------------------------------------------------------------- the lines --

RESULT_TEXT = {"win": "won", "loss": "lost", "push": "push", "void": "void", "open": "open (not final)"}


def _f(x, nd=2) -> str:
    return "—" if x is None else f"{x:.{nd}f}"


def row_line(r: dict, done: str) -> str:
    side = f"{r['pick'] or '-'}" + (f" ({r['team']})" if r["team"] else "")
    if r["kind"] == "play":
        said = f"PLAY {side}"
        price = (f"limit {_f(r['limit'])} ({r['limit_basis'] or 'basis not written'})" if r["limit"] is not None
                 else "no order price on the page")
    else:
        said = f"PASS (market-only, addendum 214); {WOULD_LABEL}: {side}"
        price = "none (PASS on the page)"
    qb = " · ".join(r["tags"]) + (f" — {'; '.join(r['qb_reasons'])}" if r["qb_reasons"] else "")
    edge = "exec edge —" if r["exec_edge_pp"] is None else f"exec edge {r['exec_edge_pp']:+.1f}pp"
    close = (f"close {_f(r['close'], 3)} ({r['close_reference'] or 'books'})" if r["close"] is not None
             else f"close unpriced (books {r['close_books'] or 0})")
    a, h = r["score"]
    score = f" {a}-{h} (away-home)" if r["result"] in ("win", "loss", "push") and a is not None else ""
    return (f"- {r['kickoff_et']} · {r['away']} @ {r['home']} [match {r['match_id']}] · page: {said} · QB: {qb} · "
            f"{edge} · market ref {_f(r['market_ref'], 3)} · price named: {price} · {close} · result: "
            f"{RESULT_TEXT[r['result']]}{score} · what was done: {done}")


def _graded(rs: list[dict]) -> dict:
    return {k: sum(1 for r in rs if r["result"] == k) for k in ("win", "loss", "push", "void", "open")}


def count_line(n_play: int, n_would: int, g_play: dict, g_would: dict, u_play: dict | None = None,
               u_would: dict | None = None, label: str = run_label(None, None)[1]) -> str:
    """The count toward thirty, ONE RUN'S (232 item 2(a)), under the run's label (run_label: "laptop era, runs through
    T: n of 30" / "host era, runs from F: m of 30"): n_play / n_would are each kind's count (its scored rows + its
    unscored rows, 225 item 3); beside it each kind's record (g_*, the scored rows only) and its unscored rows by cause
    (u_*, {cause: n}). No other run's count is an input; the sum of the two runs is the architect's, on #446."""
    total = n_play + n_would
    tail = ("this run's count alone reaches thirty — for the architect's read (no verdict is computed here)"
            if total >= READ_AT else
            "this run's count; #446's count toward thirty is the architect's sum of the two runs' consoles, on #446 "
            "(232 item 2(a)); not read before thirty rows or the season's end (no verdict is computed here)")

    def rec(g, u):
        u = u or {}
        n = sum(u.get(key, 0) for key, _ in UNSCORED_HEADS)
        return (f"W-L-P {g['win']}-{g['loss']}-{g['push']}, void {g['void']}, open {g['open']}, unscored {n} ("
                + " · ".join(f"{head} {u.get(key, 0)}" for key, head in UNSCORED_HEADS) + ")")
    return (f"COUNT toward thirty, THIS RUN'S (#446; addendum 44 item 9, 209 item 3; would-be rows counted too, "
            f"labelled, 217 item 4; unscored rows counted too, labelled, outside the W-L-P, 225 item 3; one run's count, "
            f"232 item 2(a)): {label}: {total} of {READ_AT} (PLAY {n_play} + {WOULD_LABEL} {n_would}) — {tail} · "
            f"PLAY {rec(g_play, u_play)} · {WOULD_LABEL} {rec(g_would, u_would)}")


def bound_lines(lo: datetime | None, hi: datetime | None, bx: dict) -> list[str]:
    """The header's BOUND line, its named exclusions, and (a bounded run) the RUN START UNKNOWN line (232 item 2(b))."""
    _, label = run_label(lo, hi)
    head = (f"BOUND (232 item 2(b); the closing run's start instant, UTC; --from inclusive, --through exclusive: a run "
            f"start exactly at the bound is the host era's): this run: {label} · --from {_z(lo) if lo else '—'} · "
            f"--through {_z(hi) if hi else '—'}")
    if lo is None and hi is None:
        return [head + " · no bound: every run read, nothing excluded"]
    o, u = bx["outside"], bx["unknown"]
    lines = [head + f" · excluded by the bound (not counted, not read for any game): NFL closing rows {o['rows']}, "
                    f"from {o['runs']} run(s) (closing files {o['files']}), NFL games left with no row in the bound "
                    f"{o['games']}, of this receipt (named below) {len(o['named'])}"]
    lines += [f"  {OUTSIDE}: {x['text']}" for x in o["named"]]
    lines.append(f"{UNKNOWN.upper()} (232 item 2(b); law 4: a row with no run start is never placed in an era; not "
                 f"counted): NFL closing rows {u['rows']} (closing files {u['files']}), NFL games left with no row in "
                 f"the bound {u['games']}, of this receipt (named below) {len(u['named'])}")
    lines += [f"  {UNKNOWN} (not counted): {x['text']}" for x in u["named"]]
    return lines


def report(s, exports_dir, ledger: dict | None, db_text: str, ledger_text: str, echo=print,
           lo: datetime | None = None, hi: datetime | None = None) -> dict:
    from src.walters.redated import void_counts
    out = collect(s, exports_dir, lo, hi)
    era, this_run = run_label(lo, hi)
    rows = out["rows"]
    uo = out["unscored"]
    every = rows + [x for k in ("play", "would") for key, _ in UNSCORED_HEADS for x in uo[k][key]]  # 231 item 2(c)
    pos = positions(ledger, every) if ledger is not None else {"by_row": {}, "ambiguous": 0, "nfl_fills": 0}
    d = str(exports_dir).rstrip("/")
    resolved = Path(exports_dir).resolve()
    echo("QB-HOLD RECEIPT — every NFL row the Desk called PLAY with a QB flag or an unread list, and the would-be PLAY "
         "rows while NFL is uncertified (#446), read-only")
    echo(f"RULING (ARCHITECT 2026-10-12 08:41 ET, addendum 44 item 9, verbatim): \"{RULING_44_9}\"")
    echo(f"RULING (ARCHITECT 2026-11-02 08:30 ET, addendum 209 item 3, verbatim): \"{RULING_209_3}\"")
    echo(f"RULING (ARCHITECT 2026-11-02 11:20 ET, addendum 217 item 4, verbatim): \"{RULING_217_4}\"")
    echo(f"RULING (ARCHITECT 2026-11-02 18:05 ET, addendum 223 item 5, verbatim): \"{RULING_223_5}\"")
    echo(f"RULING (ARCHITECT 2026-11-03 07:55 ET, addendum 225 item 3, verbatim): \"{RULING_225_3}\"")
    echo(f"RULING (ARCHITECT 2026-11-03 09:40 ET, addendum 231 item 2, verbatim): \"{RULING_231_2}\"")
    echo(f"RULING (ARCHITECT 2026-11-03 11:10 ET, addendum 232 item 2, verbatim): \"{RULING_232_2}\"")
    def span(r):
        return f"{r[0]:%Y-%m-%d %H:%M}Z to {r[1]:%Y-%m-%d %H:%M}Z" if r else "—"
    runs = (f"runs {span(out['runs'])}" if lo is None and hi is None else      # a bounded run: both spans, labelled
            f"runs of every file read (before the bound) {span(out['runs'])}, runs in the bound {span(out['runs_in'])}")
    bad = (f" · unreadable {len(out['unreadable'])}: {', '.join(out['unreadable'])}" if out["unreadable"] else "")
    rep = (f" · names in more than one folder {len(out['repeated'])} (each copy read): {', '.join(out['repeated'])}"
           if out["repeated"] else "")
    echo(f"SOURCES (the two, 223 item 5(b); one machine's pair, 231 item 2(a)): the copy read {db_text} · the "
         f"closing-file directory read {resolved} (--exports {d}; closing_*.json there and in its dated folders "
         f"<YYYY-MM-DD>/ {out['dated']}, never latest/; redated.closing_rows): {out['files']} read, {runs}, NFL games "
         f"{out['nfl_matches']}{rep}{bad}")
    echo(MACHINE_ERA)
    for ln in bound_lines(lo, hi, out["bound"]):
        echo(ln)
    echo(f"WHAT WAS DONE FROM: {ledger_text}")
    echo(f"KEYS: {KEYS}")
    plays = [r for r in rows if r["kind"] == "play"]
    would = [r for r in rows if r["kind"] == "would"]
    ledger_read = ledger is not None
    for label, rs in ((PLAY_LABEL, plays), (WOULD_LABEL, would)):
        echo(f"{label} — {len(rs)} scored row{'s' if len(rs) != 1 else ''}, by kickoff")
        for r in rs:
            echo(row_line(r, done_text(pos["by_row"].get(r["key"]), ledger_read)))
    u_n = {k: {key: len(uo[k][key]) for key, _ in UNSCORED_HEADS} for k in ("play", "would")}
    def u_head(k, key, head):      # the void head carries redated's split: one void state, two labels (109 item 2 Q2)
        return f"{head} {u_n[k][key]}" + (f" ({void_counts(x['text'] for x in uo[k][key])})" if key == "void" else "")
    echo("UNSCORED (counted toward thirty, labelled, never scored, outside the W-L-P, 225 item 3; per kind, never "
         "pooled): " + "; ".join(f"{lab} — " + " · ".join(u_head(k, key, head) for key, head in UNSCORED_HEADS)
                                 for k, lab in (("play", "PLAY"), ("would", WOULD_LABEL))))
    for k in ("play", "would"):
        for key, head in UNSCORED_HEADS:
            for x in uo[k][key]:      # what was done on every row, scored or not (231 item 2(c)), the same label
                echo(f"  {head} (unscored, counted): {x['text']} · what was done: "
                     f"{done_text(pos['by_row'].get(x['key']), ledger_read)}")
    tw = out["toward_thirty"]
    # every row of the kind, scored + unscored (231 item 2(c)): the denominator is the kind's count toward thirty
    held = {k: sum(1 for r in rows if r["kind"] == k and pos["by_row"].get(r["key"]))
            + sum(1 for key, _ in UNSCORED_HEADS for x in uo[k][key] if pos["by_row"].get(x["key"]))
            for k in ("play", "would")}
    held_play, held_would = held["play"], held["would"]
    if ledger_read:
        echo(f"LEDGER: NFL game {LEDGER_LABEL} entries read {pos['nfl_fills']} · fitting more than one row (ambiguous, "
             f"given to none) {pos['ambiguous']} · PLAY rows (scored + unscored) with {LEDGER_LABEL} on the game "
             f"{held_play} of {tw['play']} · {WOULD_LABEL} rows (scored + unscored) with {LEDGER_LABEL} on the game "
             f"{held_would} of {tw['would']}")
    g_play, g_would = _graded(plays), _graded(would)
    echo(count_line(tw["play"], tw["would"], g_play, g_would, u_n["play"], u_n["would"], this_run))
    summary = {"exports": d, "exports_read": str(resolved), "dated_folders": out["dated"], "closing_files": out["files"], "unreadable": len(out["unreadable"]),
               "nfl_games": out["nfl_matches"], "play_rows": len(plays), "would_be_rows": len(would),
               "counted": {"play": tw["play"], "would_be": tw["would"]},
               "toward_thirty": tw["play"] + tw["would"], "read_at": READ_AT,
               "this_run_thirty_reached": tw["play"] + tw["would"] >= READ_AT, "play_record": g_play,
               "would_be_record": g_would, "ledger_read": ledger_read,
               "what_was_done": ({"play": {LEDGER_LABEL: held_play, "not_established": tw["play"] - held_play},
                                  "would_be": {LEDGER_LABEL: held_would, "not_established": tw["would"] - held_would}}
                                 if ledger_read else None),
               "ambiguous_fills": pos["ambiguous"] if ledger_read else None,
               "unscored": {"play": u_n["play"], "would_be": u_n["would"]},
               "run": {"era": era, "label": this_run, "from": _z(lo) if lo else None, "through": _z(hi) if hi else None},
               "excluded_by_bound": _bx_json(out["bound"]["outside"]) if (lo or hi) else None,
               "run_start_unknown": _bx_json(out["bound"]["unknown"]) if (lo or hi) else None}
    echo("QB-HOLD-RECEIPT " + json.dumps(summary, sort_keys=True))
    return {**out, "positions": pos, "summary": summary}


def _bx_json(b: dict) -> dict:
    return {"runs": b["runs"], "closing_files": b["files"], "nfl_closing_rows": b["rows"], "nfl_games": b["games"],
            "named": {"play": sum(1 for x in b["named"] if x["kind"] == "play"),
                      "would_be": sum(1 for x in b["named"] if x["kind"] == "would")}}


# ------------------------------------------------------------------------------------------------------- main --

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#446 (addendum 44 item 9; 209 item 3; 217 item 4; 232 item 2): the QB "
                                             "hold, measured, ONE run's count under its era's bound — read-only")
    ap.add_argument("--db", default=None, help="a .backup copy of the database outside the repo's data/, opened "
                                               "mode=ro&immutable=1 (required)")
    ap.add_argument("--exports", default="exports", help="the directory holding closing_*.json, at its top and in "
                                                         "its dated folders <YYYY-MM-DD>/ (a flat directory and the "
                                                         "mirror's tree alike; latest/ never read). Default exports. "
                                                         "One machine's pair with --db (231 item 2(a)): the laptop's "
                                                         "own exports/ with the laptop's copy (--through), or "
                                                         "exports/host/, the laptop's cumulative pull "
                                                         "(pull_exports.py), with the host's pulled backup (--from; "
                                                         "232 item 2(c)); the mirror's host/ tree a second source")
    ap.add_argument("--from", dest="from_", default=None, metavar="INSTANT",
                    help="bound the closing run's start, INCLUSIVE (start >= INSTANT), a UTC instant "
                         "YYYY-MM-DDTHH:MM:SSZ (232 item 2(b)): the host era's run, --from 2026-10-26T12:00:00Z; "
                         "the label 'host era, runs from INSTANT'")
    ap.add_argument("--through", default=None, metavar="INSTANT",
                    help="bound the closing run's start, EXCLUSIVE (start < INSTANT: a run start exactly at the bound "
                         "is the host era's), a UTC instant YYYY-MM-DDTHH:MM:SSZ (232 item 2(b)): the laptop era's "
                         "run, --through 2026-10-26T12:00:00Z; the label 'laptop era, runs through INSTANT'. Both "
                         "bounds: a window. A row with no run start is outside every bound (named, not counted)")
    ap.add_argument("--ledger", default=None, help="the Cockpit's Export ledger (JSON) file, bd_ledger_v1_<date>.json "
                                                   "(optional: without it 'what was done' reads not read)")
    a = ap.parse_args(argv)
    from src.walters import mlb_pitchers_gate as mp
    try:
        lo = parse_instant(a.from_, "--from") if a.from_ is not None else None
        hi = parse_instant(a.through, "--through") if a.through is not None else None
        if lo is not None and hi is not None and not lo < hi:
            raise Refused(f"--from {_z(lo)} is not before --through {_z(hi)}: the window holds no run start (232 item "
                          "2(b)); nothing read")
        path = mp.check_db(a.db)
        for sc in SIDECARS:
            if path.with_name(path.name + sc).exists():
                raise mp.GateRefused(f"--db {a.db} has a {sc} sidecar ({path.name + sc}): not a fresh .backup copy; "
                                     "immutable=1 would ignore it and read a stale file; take a fresh .backup copy")
        if not Path(a.exports).is_dir():
            raise Refused(f"--exports {a.exports}: not a directory; nothing read")
        ledger = read_ledger(a.ledger) if a.ledger else None
        mp.open_ro(path).close()
    except (mp.GateRefused, Refused) as err:
        print(f"REFUSED: {err}" + ("" if str(err).endswith("nothing read") else "; nothing read"))
        return REFUSED
    import sqlite3

    from sqlalchemy.exc import SQLAlchemyError
    db_text = (f"{path} (--db; a .backup copy, opened {mp.COPY_URI_QUERY.lstrip('?')}; the results, as results-tally "
               "reads them: exec_cohorts.result_of)")
    ledger_text = (f"ledger {a.ledger} (bd_ledger_v1: calls {len(ledger['calls'])}, fills {len(ledger['fills'])})"
                   if ledger is not None else "ledger not read (no --ledger): 'what was done' reads not read")
    lines: list[str] = []
    try:
        with mp.readonly_session(path) as s:
            report(s, a.exports, ledger, db_text, ledger_text, echo=lines.append, lo=lo, hi=hi)
    except (SQLAlchemyError, sqlite3.Error, LookupError) as err:   # a copy without the schema the read needs
        why = (str(err).strip().splitlines() or [""])[0]
        print(f"REFUSED: --db {path}: cannot be read as the schema the receipt needs ({type(err).__name__}: {why}); "
              "nothing read")
        return REFUSED
    for ln in lines:
        print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
