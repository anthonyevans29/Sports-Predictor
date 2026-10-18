# #594 reconciliation read: notes on block_594_reconcile.txt (round 4)

Ruling: ARCHITECT addendum 130 item 2(e): "Reconciliation read FIRST (read-only: every row and export that read a Kalshi leg of 50548/50550 since Friday 23:25Z), then ONE reviewed command re-points the four leg rows by ticker ... the results file for 10-17 is re-exported after. Not today."

The block only reads. The re-point, the 10-17 re-export and any clv-restate are not in it. The ruled cutoff stays the default; anything wider is labelled beyond the window; scope questions are surfaced, never decided.

## How to run it (round 4: a file, not a paste)

The block is 134 KB. That is too long to paste comfortably and over GitHub's comment limit, so it is delivered as a file:

- **Run it as a file.** Save it anywhere, `cd` to the checkout root, then run `bash <path>/block_594_reconcile.txt 2>&1 | tee ~/rec594_<UTC stamp>.txt`. The file's first line says so. That line is a `:` no-op with a quoted string, so it is safe to paste too.
- **Settings** go before `bash` (`REC594_PY=./venv/bin/python bash ...`), or are exported before a paste. They are `REC594_PY`, `REC594_CUT`, `REC594_FOUR`, `REC594_LEDGER` and `REC594_STRICT`.
- **The block's own tee runs only when its output is a terminal** (`[ -t 1 ]`: pasted, or run with `bash` and no tee). Then the console is also kept as `~/rec594_<stamp>.txt`, and the first console line names the file.
  - Run as above, the output is a pipe. The block writes no file of its own and says so on its first console line, so the operator's tee file is the only one.
  - Round 3 always tee'd to `~/rec594_<same stamp>.txt` itself. With the operator's own tee stamped the same second, two `tee` processes would have truncated and written the same file.
- **It can still be pasted whole** into bash or zsh at the checkout root:
  - no comment lines, no tab characters, no shell glob;
  - no `!` that history expansion could take: the only ones stand before `=` or a space;
  - three quoted heredocs (`<<'EOF'`, per the CLAUDE.md 2026-10-06 rule), none inside `$( )`.
- **The end of the console** is `END #594 reconciliation read (read-only). The whole console, from the first line to this one, is the receipt (the tee file holds it).`

## Round 4: the 11 round-3 findings and what changed

| Finding | Change |
|---|---|
| R1 P2, the weekly mirror squash dates every unchanged file in [F14]/[F0] by the squash commit | `git_info` now knows the re-commits: every commit whose subject starts `weekly squash` (the subject `exports_mirror.squash` writes), every root commit that is not the oldest commit reachable through `--all --reflog`, and every shallow-boundary commit. When a file's last commit is one of them, the file is dated by the earliest commit reachable through `--all --reflog` that wrote the same blob at the same path. If there is none, it is dated by the document's own `exported_at` or `desk_meta.as_of`, when that is at or before the squash. Otherwise it is `undatable (squashed)`: the squash time is an upper bound on its date, so it is listed in every pass whose window starts at or before that bound. For the 10-18 06:10Z squash that is both passes, never silently inside the window. [F15] applies the same rule to blobs: a squash entry whose bytes an earlier commit wrote is counted as a re-commit and not as a write in the window. [F5] and [F12] go through the same dating. |
| R2 P2, [F16] fill and CSV times lose their UTC offset | A new `iso_epoch` reads times with `fromisoformat`, with Z read as `+00:00` and the offset honoured, and converts to UTC before labelling. `TS_IN` gains the offset group. Every FILL, REPRICE and CSV line prints the raw text beside the UTC time. A fill or CSV time with neither Z nor an offset is `no reliable time` and is never read as UTC. App-written times stay naive UTC, as the app and the DB write them. |
| R2 P2, [Z1] can certify a read during which another process committed | A `-wal` created during the read counts as the block's own only when it is 0 bytes, since a read-only connection writes no WAL frame. Otherwise Z1 prints `another process committed N bytes of WAL frames during the read: paste again (or run the file again)` and does not mark the run its own. A `-wal` that existed before and changed size is named with both sizes. |
| R1 P3, [F16] ignores close_ref and graded_date | `close_ref.close_at` (cockpit.html:1319, set at grading :1337, :1358) and `graded_date` (:1357, a date read as its 00:00Z) join `latest_of`. A call whose `close_ref.close_at` is at or after the ruled cutoff also prints `its close_ref.close_at ... is inside the ruled window: the grade read a close from the window ([C2], [F4])`. |
| R1 P3, [F10] counts any TB@CLE block as a pair block and runs on into the trailer | The header's `[match N]` decides. A block is a pair block only for 50548/50550. Another game's block is printed only when a line in it carries a ticker of either event or a pair id, and it is labelled `another game (match N)`. A header with no `[match N]` falls back to the team match and is labelled `pair block by team`. A block ends at a blank line, the next `── ` header, or a line starting `--- `, `=== `, `· `, `✓ ` or `✗ ` (the run's page, closing-file, mirror and status lines: closing.py:1792-1803, 1847-1853, 1949). The count line separates the four kinds. |
| R1 P3, parts D and F are hard-wired to python3 | One interpreter now serves parts D, C and F: `REC594_PY`, else `./venv/bin/python`, else `./.venv/bin/python`, else `python3`. It is checked with `command -v` plus a Python 3.8 probe. Parts D and F run it with `-I` (stdlib only) and part C with `-B`. With no usable interpreter, all 45 sections (D0-D13, C0-C6, W0, F0-F18, PRE, Z1, Z2) print a header and `count: absent (no usable interpreter ...)`. |
| R1 P3 and R2 P3, the header promises labels that D7-D9 and C4/C4F lack | Labels were added to D7 (`first_at`/`last_at` per capture group: inside / BEFORE / spans), D8 (`ruled_window` per row, and per game "N captured before the ruled cutoff" beside the kalshi_only verdict) and D9 (`computed_at`). In part C they were added to C4/C4F's moved rows, the what-if current legs, every close summary (`ruled_window` of the close's `captured_at`), every close leg (C2, C4, C6), C3's stored `evaluated_at`, D0's four and its 23:24-23:28 list, and F9's stale legs. The header sentence now names exactly what is labelled, and what carries no read time: D1 (kickoffs), D12 (counts), C1 (current tickers), C5 (game start times; the closing files are dated in [F3]), and the lines of F5 and F7 (dated by their file). |
| R2 P3, k-track-receipt is an id-less reader treated as console only | `k-track` joins `ID_LESS`, so [F12] lists its receipts by name. Z2 has its own row: `cli.py:1802-1842; src/walters/k_receipt.py:149-168, 218-243`. Its `--out` writes a receipt anywhere whose LADDERS part aggregates per sport and names no game, and its default window ends 2026-10-08 (`k_receipt.py:31-32`). MANUAL 5 now names `k-track-receipt` (with any `--out` file outside docs/receipts), `mlb-odds-timing` (cli.py:3685) and `scripts/kalshi_leg_audit.py`. |
| R1 P3 and R2 P3, citations | cutover-readiness is cited `cutover_readiness.py:36-40` (which machine) and `:85-94`, with `CAPTURE_ROW_FIELDS` at `:88`, in the Z2 row, in MANUAL 2 and below. The STANCE line now reads "opened mode=ro as ro_connect does (deploy/hosting/sp_common.py:260-263), plus PRAGMA query_only=ON added by this block". `ro_connect` itself runs no PRAGMA. |

## Code cited at main eae386b (#595 merged)

Every citation in the block and these notes is at main eae386b (`git show eae386b:<path>`):

- **`tools/cockpit.html`, repo copy.** CLAUDE.md says the live Cockpit is a separately published artifact, so the block says "repo copy" wherever it cites these lines.
  - localStorage ledger `:763-772`, `baseCall` `:901-905`, `stampTiming` `:916-932`, the ledger export `:1782-1787`;
  - the confirmed Kalshi CSV header list `:1884-1888` (`close_timestamp`, `open_timestamp`);
  - `importKalshiCSV` with the realized-P&L check `:2187-2192`; fills `opened`/`closed` copied raw from the CSV's `openTs`/`closeTs` columns `:2205-2208`;
  - round 4: `clvBlock` `close_at` `:1319`, `close_ref` set at grading `:1337` and `:1358`, `graded_date` `:1357`.
- **`deploy/hosting/cutover_readiness.py`** (#596).
  - The docstring at `:36-40` says which machine runs it: "the HOST, over ssh in the Thursday evening block ... The laptop form (--receipts FILE --fullseason-list FILE ...) is for the architect's dry reads only" (ARCHITECT addendum 128 item 1(a)).
  - The capture-timing sets are at `:85-94`, with `CAPTURE_ROW_FIELDS` at `:88`. Round 3 said `:34-38` and `:86`, which were wrong.
- **`deploy/hosting/sp_common.py`.**
  - `db_path` `:232-241`.
  - `ro_connect` `:260-263` opens `?mode=ro` only. The block adds `PRAGMA query_only=ON` itself.
  - The Apple failure note `:300-305`; `copy_connect` `:316-322`.
- **`deploy/hosting/exports_mirror.py`.**
  - `_sync_to_remote` `:170-175` (fetch, `checkout -B`, `reset --hard`) and `push` `:187-231` (copy2 at `:201`).
  - Round 4: `squash` `:234-244`. It makes an orphan commit `weekly squash <date> (history before this date dropped; files kept)`, runs `branch -M` and force-pushes.
  - The timer is `deploy/hosting/systemd/sp-exports-squash.timer:7`: `OnCalendar=Sun *-*-* 06:10:00 UTC`.
- **Writers of the squash fallback times.** `src/walters/export.py:85, 1061, 1344` write `exported_at` as naive UTC plus `Z`. `src/walters/desk_policy.py:1698, 1752` write `desk_meta.as_of` as `...Z`.
- **`deploy/hosting/closing.py`** (round 4, F10's block boundaries): `summary_block` `:1019-1039`, the summary and page `:1792-1803`, the closing-file and mirror lines `:1847-1853`, the run header `:1915` and the check line `:1949`.
- **k-track and the history readers** (round 4).
  - `cli.py:1802-1842` is `k-track-receipt`: `--out` at `:1807`, `K.ladders` at `:1841`.
  - `src/walters/k_receipt.py:31-32` is the default window, `:149-168` is `ladders` through `mismatched`, and `:218-243` is `format_ladders`, per sport.
  - `cli.py:3685` is `mlb-odds-timing`. `scripts/kalshi_leg_audit.py` is the read-only two-event audit.
- **Unchanged from round 3:** `compare_exports.py:88-90`, `coverage_map.py:22, 73, 104-109, 125, 282`, and the `cli.py`, `sp_migrate.py`, `sp_backup.py`, `pull_backup.py`, `kalshi_replay.py`, `replay_inventory_probe.py` and `mlb_actionable.py` lines as cited in the block.

Part C's imports (`src/walters/{close,kalshi_legs,clv_restate,redated}.py`, `src/db/schema.py`) are byte-identical between the harness clone (ba2efe5) and eae386b.

## The window, and what lies outside it

- **The ruled cutoff is the default.** It is 2026-10-16T23:25:59Z: "since Friday 23:25Z", with the second the Issue names. Every main-pass section uses it unless `REC594_CUT` is set.
- **`REC594_CUT=YYYY-MM-DDTHH:MM:SSZ` overrides it.** The header prints `OVERRIDE` with the direction.
  - **Wider (earlier):** every item dated before the ruled cutoff is labelled.
  - **Narrower (later):** items from the ruled cutoff on fall into the -pre pass, unlabelled, because they are inside the ruled window.
  - **Malformed:** the header says so, and the ruled cutoff is used.
- **The label.** An item dated before the ruled cutoff is labelled `before the ruled cutoff (outside addendum 130 2(e)'s window: for the architect)`. A table row carries a `ruled_window` column or field instead (`inside`, `BEFORE ...`, `spans the ruled cutoff`, `no time`). Labelled items are evidence for the architect's scope question, never folded silently into the window.
- **Where labels are printed (round 4: exactly what the console header says).**
  - Part D: D0 (first captures, the four, the 23:24-23:28 list), D2-D11 and D13.
  - Part C: C2-C4F and C6 (close summaries, close legs, moved rows, what-if legs, stored grades).
  - Part F: every section, by the item's date. F9 also labels its stale legs, F10 its run headers, and F16 its calls, reprices, fills and CSV lines.
  - Not labelled, because they carry no read time: D1 (kickoffs), D12 (counts), C1 (current tickers), C5 (game start times; the closing files are dated in [F3]), and the lines of F5 and F7 (dated by their file).
  - An undated item says so, for example `no time on the call`, or for a fill with no offset `no reliable time`.
- **How a file is dated.**
  - A git-tracked file whose bytes equal its HEAD blob is dated by its last commit. That covers the mirror clone's files, and `docs/receipts` and `RESULTS.md` in the checkout. Any other file is dated by its mtime.
  - The mirror's mtimes are checkout times: every push runs fetch, `checkout -B` and `reset --hard` (`exports_mirror.py:170-175`). A checkout or pull resets the mtimes of the checkout's tracked files the same way. The mtime is printed beside the commit date.
  - **After a squash (round 4).** The weekly squash re-commits every file at Sunday 06:10Z. The laptop clone picks it up at its next push, through fetch, `checkout -B` and `reset --hard`. A file whose last commit is a squash, root or shallow-boundary commit is dated in this order:
    1. by its first commit of the same bytes reachable through `--all --reflog`. The laptop's HEAD and origin reflogs keep the pre-squash history;
    2. else by its own `exported_at` or `desk_meta.as_of`;
    3. else it is `undatable (squashed)`, dated only at or before the earliest squash holding those bytes. It is then listed in every pass whose window starts at or before that, which is both passes for the 10-18 06:10Z squash.
  - A shallow boundary from September bounds its files before both windows, so they stay out of both, as before.
  - The blob check hashes the file in Python, as `blob <len>\0<bytes>`. Only `rev-parse`, `ls-tree` and `log` run, with no `git status`, so the index is never refreshed or written.
- **The -pre pass.** Part F reruns F0, F1-F4, F6, F8, F9, F11-F15, F17 and F18 as `[F*-pre]`. Its window runs from the first crossed capture over all time, computed in `[W0]` on a read-only open, up to the cutoff in use. When the window is empty, `[PRE]` says why in its count line.
- **Two sections cover all time.** F10 has no per-line time and labels any run header whose target start is before the cutoff. F16 labels each call by its latest time.

### D3 is expected to be non-empty

161800 legs sat on 50548 from Friday morning, before the 23:25Z sync. Under #594's ruling those legs belong to 50550, so they are crossed. The evidence:
- `docs/ledger/entries/2026-10-16-desk-clock-hold.md:1`, the ruling of 10-16 09:22 ET: "Today's 50548 (8pm vs 6pm) then holds". Its `:3` adds "the Kalshi ticker KXMLBGAME-26OCT161800TBCLE says 6:00pm ET ... the 7:25pm closing run is record-only".
- `changelog.d/552-desk-clock-hold.md:10`: "50548 TB at CLE tonight (stored 20:00 ET vs the ticker's 18:00 ET ...) is held".
- `tests/test_desk_kickoff_clock.py:53-55`: `tb_cle_tonight()` gives 50548 the ticker `KXMLBGAME-26OCT161800TBCLE`. This is a fixture of the morning state, not stored data.
- A possible third game: `BACKLOG.md:633` (#476) says the Friday 11am ET run stores the two 161800 legs on Game 3's row. `[D0]`, `[D5]`, `[D13] (d)` and `[C6]` list such rows, and `[F10]` prints Game 3's closing block when it carries an event ticker. The entry itself says "Not established: whether it has happened on stored legs."

The earlier legs still have readers after a four-row re-point:
- `mlb_odds_timing` takes `kalshi_first = min(captured_at)` (`src/walters/mlb_odds_timing.py:97-99`).
- `line_move` reads the whole capture series (`src/walters/line_move.py:106-117`).
- `scripts/kalshi_leg_audit.py` runs its two-event-day check.

The block lists those readers in the -pre passes, labelled, and their consoles in MANUAL 5. `[D13]` sorts every crossed row into classes. Whether rows (b) to (d) move is a scope question, and the block does not decide it.

## How the block runs, and why it is read-only

- **DB path.** The block resolves it as `deploy/hosting/sp_common.py:232-241` (`db_path`) does: `DATABASE_URL` from the environment, else the checkout `.env`, else `sqlite:///./data/sports.db` (`config.py:46`), relative to the checkout.
- **How the DB is opened.** Python's sqlite3 opens it by file URI `?mode=ro`, as `sp_common.ro_connect` does (`sp_common.py:260-263`). It then runs `PRAGMA query_only=ON`, which this block adds; `ro_connect` does not.
  - The open is never immutable: `sp_common.py:316-322` says "Never for the live DB (#340)".
  - Parts D, C and W0 each open and close it before `[Z1]`. D0, C0 and W0 each print the SQLite version, the `_sqlite3` module file and the interpreter they read with.
- **SQLite sidecars (law 5): the repo's existing stance, the default, FLAGGED FOR THE ARCHITECT.**
  - **What the block does.** It adopts the stance `deploy/hosting/coverage_map.py:108-109` documents for every ro_connect reader: "SQLite itself may leave its -wal/-shm sidecars beside a WAL file, as for every ro_connect reader". The morning `python cli.py coverage` line runs that reader daily. The block opens mode=ro and prints that sentence in its header. When a sidecar is missing beside a WAL DB, `open:` says SQLite may create it now.
  - **What Z1 reports (round 4, corrected).** A read-only connection never writes WAL frames, so a `-wal` that this block's own open creates is 0 bytes. Under WAL, another process's commit lands in the `-wal`, not in the DB file, so the DB's size and mtime alone prove nothing. Z1 therefore calls a change the block's own only when all three hold:
    - the changes are sidecars absent before and present after;
    - the created `-wal` is 0 bytes;
    - the DB's size and mtime are unchanged.

    It then reports "created by this block's own read-only open ... the -wal is 0 bytes". A created `-wal` with frames reads "another process committed N bytes of WAL frames during the read: paste again (or run the file again)". Any other change reads as another process writing, with the `-wal`'s before and after sizes when it changed.
  - **`REC594_STRICT=1` refuses instead.** With a WAL DB and a missing sidecar it opens nothing, creates nothing, and says how to read without it.
  - **`REC594_OPEN_ANYWAY` is gone.** It is no longer read, and the header says so if it is set.
  - **Why this matters on the laptop.** A clean close of an app connection deletes `-wal` and `-shm`, so a quiet laptop normally has neither. Under the default, a Linux-built SQLite creates both under data/. That is the law-5 tension the architect should rule on. The repo already accepts it for coverage and every ro_connect reader.
  - **Apple's SQLite fails instead** (`sp_common.py:300-305`: "unable to open database file"). The block prints the failure and names two options without taking either: run it while an app process holds the DB open, or read a fresh `.backup` copy opened as the repo opens copies (`sp_common.copy_connect`, `mode=ro&immutable=1`, `:316-322`), labelled a copy with its sha256.
- **The -shm.** Any WAL reader writes read-marks into the shared `-shm`, so its mtime moves on every read. `[Z1]` compares the `-shm` size only.
- **Before/after receipt.** `[Z1]` compares, before and after: the DB size and mtime, the `-wal` size and mtime, the `-shm` size, and the names in the DB's folder.
- **No cli.py command runs.**
- **The interpreter (round 4: one for parts D, C and F).**
  - The order is `REC594_PY`, else `./venv/bin/python` (the app's own: `scripts/setup_closing_watch.sh:32`, `scripts/setup_clv_capture.sh:17`), else `./.venv/bin/python`, else `python3`.
  - A shell check runs first: `command -v`, plus a probe that the interpreter is Python 3.8 or later.
  - Parts D and F use the standard library only and run under `-I`. Part C runs under `-B`, so no .pyc is written.
  - With no usable interpreter, all 45 sections print a header and `count: absent (no usable interpreter ...; set REC594_PY=... and run it again)`, so silence never means zero.
  - Part D's header and C0 print the interpreter chosen.
- **Part C imports the repo's read code.** It imports `src.db.schema`, `src.walters.close`, `kalshi_legs`, `clv_restate` and `redated`, all pure reads.
  - The engine is built from a creator that calls the same `open_ro()`. The Session runs `autoflush=False` and is rolled back and closed at the end.
  - `src.db.database` is never imported, and the block prints `False` as the receipt.
  - An interpreter without SQLAlchemy prints C0 `not run` and C1-C6 `absent`.
- **Dating rules.** DB times are compared as stored text, and `[D0]` prints the stored form. Receipts are dated on `ts`, git commits on `%ct` (epoch), and files as described above. Every section ends with `[TAG] count: ...`. A missing table or file prints `absent`; a failing section prints `ERROR` and `count: error`.
- **data/ is never read by the file part.** `under_data()` skips it, `.git` folders are skipped, and a SQLite file the sweep meets has only its 16-byte header read.
- **Overrides.**
  - `REC594_CUT`, `REC594_STRICT` and `REC594_PY`, as above.
  - `REC594_FOUR=<id,id,id,id>`: when the architect names the four, `[C4F]` previews exactly those ids. Ids that are not crossed rows of the pair are named in a WARNING.
  - `REC594_LEDGER`: a Cockpit ledger export.
  - `SP_RECEIPTS`, `SP_WINDOW_STATE`, `SP_EXPORTS_MIRROR_DIR` and `SP_BACKUP_DIR` are read the way `sp_common.setting` reads them: the environment, then host.env, then the checkout `.env`.

## Sections

Each entry gives what the section reads, the code it cites, and, where it matters, what a non-empty result means for the re-point. Round-4 changes are marked.

### Database (part D, stdlib, read-only URI)

**[D0] DB, open mode, sidecars, every crossed row, the four.**
- **Reads:**
  - the resolved path, header byte, sidecar stats, `query_only` and `journal_mode`, and the captured_at text form;
  - every crossed row over all time, as first and last capture per (match_id, ticker);
  - the first crossed capture;
  - THE FOUR: per ticker, the newest crossed row on the pair in the ruled second, with id, exact `captured_at`, bid, ask and (round 4) `ruled_window`;
  - the 23:24-23:28Z rows with their exact text and (round 4) `ruled_window`.
- **Code:** `sp_common.py:232-241, 260-263, 300-322`; `config.py:46`; `kalshi_sync.py:74, 146`; `src/db/database.py:192`.
- **If non-empty:** the four ids are what the reviewed command names. A `WARNING` means no row, or a tie, in the ruled second, and the architect names the ids.

**[D1] matches.** Unchanged. The mapping holds only if 50548 is gamePk 849817 and 50550 is gamePk 849816.

**[D2] Kalshi rows since the cutoff in use** / **[D3] the same before it.** Unchanged: three flags, `event_belongs_to`, `crossed` and `ruled_window`. A `crossed=False` row trips the addendum-37 guard on both games only while it is a CURRENT leg (`kalshi_legs.py:36-50, 95-114`), and `[D13] (e)` flags each such row.

**[D4] current legs (SQL)**, **[D5] games holding either event**, **[D6] kalshi_settled_markets:** unchanged, each with `ruled_window`.

**[D7] odds 1X2 (round 4: labelled).** Grouped by capture minute, with `first_at`, `last_at` and `ruled_window` per group (inside, wholly BEFORE, or spans the ruled cutoff). The count splits the groups the same way.

**[D8] book snapshots and kalshi_only reachability (round 4: labelled).**
- Each row carries `ruled_window`.
- Each game's line now says how many of its pre-kickoff odds rows and book snapshot rows were captured before the ruled cutoff.
- The verdict still counts every pre-kickoff capture, as `close.py` does, before the ruled cutoff too.

**[D9] predictions (round 4: labelled).** Each row carries `ruled_window` of `computed_at`.

**[D10] prediction_history** and **[D11] prediction_outcomes:** unchanged, labelled. `closing_bookmaker='kalshi_only'` on 50550 means its stored clv came from a crossed 172000-CLE HOME leg. Only `clv-restate --apply --backup` changes it (`clv_restate.py:203-206`).

**[D12] inventory:** unchanged.

**[D13] scope questions for the architect.** Unchanged. Every crossed row of either event is checked against the RULED cutoff, one line per row with its label:
- (a) the four;
- (b) crossed rows on the pair at or after the cutoff, beyond the four;
- (c) crossed rows on the pair before the cutoff;
- (d) crossed rows on OTHER games, each with `current leg: YES/no`, plus each other game's match, current legs and stored grade;
- (e) correctly placed rows since the cutoff, each with `current leg: YES/no`.

### Repo read code (part C)

**[C0] import receipt.** Prints the interpreter chosen (shared with D and F) and the SQLite library.

**[C1] guard now.** Unchanged.

**[C2] grading close now.**
- A `kalshi_only` close prints the newest two-sided pre-kickoff HOME leg or legs, with `priced_the_close` marking the row close.py keeps (`max()` at `close.py:189-198`, over the unordered query at `close.py:235-246`).
- Round 4: the close summary carries `ruled_window` of its `captured_at`, and each leg carries its own `ruled_window`.

**[C3] stored vs recomputed.** Round 4: the stored `evaluated_at` carries `ruled_window_evaluated_at`, and the recomputed close carries `ruled_window`.

**[C4] WHAT-IF A** (every crossed row of the pair re-pointed, in memory) and **[C4F] WHAT-IF B** (only the four).
- Round 4: every moved row, every what-if current leg and every close leg carries `ruled_window`. The count line says how many moved rows were captured before the ruled cutoff.
- In the harness, C4 moves ids 17, 18 and 19 (captured 10-16 13:00 and 23:25:58.999999) labelled BEFORE, beside ids 5 and 10 (inside).
- The tie and `REC594_FOUR` titles are unchanged.

**[C5] re-dated void.** Unchanged, and not labelled: these are game start times, and the closing files are dated in [F3].

**[C6] other games holding an event of the pair.** Unchanged. Its stored grades, close summary and close leg carry labels.

### Files (part F, stdlib)

**[W0] windows.** Unchanged.

**Matching** (unchanged):
- Rows sections print one compact JSON line per matching row. Laptop files match on match_id or ticker, host files (`/host/` in the path) on ticker only, and repeats show as `= same bytes as`.
- Text sweeps (F0, F9's page and tail text, F10, F12) match a line by id (laptop paths), by ticker, or by TEAM: `Rays` or `Guardians`, or both of `Tampa Bay`/`Tampa`/`TB` and `Cleveland`/`CLE` with MLB context in the file, receipt or run. A line that carries a date must carry one of 2026-10-16..19.
- The id pattern is decimal-safe: `0.50548` and `50548.5` do not match, while `match_id=50550,` and `50548.` do.

**[F0] sweep.** Every file in the window under exports/, logs/, docs/receipts/, RESULTS.md, the mirror clone, receipts, window state, `/tmp/sp_pack_*` and every pack a migrate receipt names.
- Round 4: mirror and checkout files are dated with the squash rule above. An undatable file prints `undatable (squashed), at or before <time>` in place of its date, and the count line gives the number.

**[F1]-[F4], [F6], [F8], [F13], [F17]:** unchanged. Their count lines add the squash counts.

**[F5] RESULTS.md:** dated by its last commit when clean. An undatable copy says so.

**[F7] window pager state:** unchanged.

**[F9] receipts.jsonl:** unchanged, except that the stale legs joined to the stored rows now carry `ruled_window` (round 4).

**[F10] closing_watch.log/.err (round 4).** All time. The header's `[match N]` decides what is printed:
- **Pair block:** the header names 50548 or 50550. The block is printed whole and labelled `pair block: match N`. That includes the `kalshi-only hold` line, which names no match.
- **Another game's block:** printed whole only when a line in it carries a ticker of either event or a pair id, labelled `another game (match N)`. Otherwise it is not printed, only counted.
- **A header with no `[match N]`:** the team match decides, labelled `pair block by team`.
- **The end of a block:** a blank line, the next `── ` header, or the run's page / closing-file / mirror / status lines (`--- `, `=== `, `· `, `✓ `, `✗ `).
- Lines outside blocks still match by id, ticker or team, marked `[matched by team]` when team-only. Each printed line comes after its run header.
- The count gives the four kinds.

**[F11] kalshi_replay payloads.** Unchanged.

**[F12] docs/receipts (round 4: k-track).**
- Files are matched by content (a game, an event or the team).
- Every receipt of an id-less reader is listed by name: `mlb-actionable`, `desk-rescore`, `venue`, `quote-age` and now `k-track` in the name.
- A k-track-receipt `--out` file's LADDERS part aggregates every Kalshi ladder per sport and names no game (`k_receipt.py:218-243`).
- A clean tracked receipt is dated by its last commit.

**[F14] mirror working tree (round 4).**
- Dated by its last commit, or after a squash by the squash rule above.
- In the round-4 harness (`mirror_sq`), F14 main prints only content first written after 23:25:59Z, plus the one undatable file. C1, C2 and C2h move to F14-pre, dated by their first commits and labelled, and C0 (10-15) falls before both windows.

**[F15] mirror git history (round 4).**
- It reads `git log --all --reflog --raw` once and filters each pass by `%ct`.
- A squash or root re-commit of bytes that an earlier commit wrote at the same path is not counted as a write in the window. The count line gives the number.
- A squash entry with no earlier writer is `undatable (squashed)` and is listed in every pass that starts at or before its squash.
- The main pass's commit list goes to MANUAL 1.

**[F16] Cockpit ledger and fills (round 4).**
- **Each CALL** is dated by the latest of `captured_at`, `claim_at`, `executed_at`, `reprices[].at`, `close_ref.close_at` and `graded_date` (a date, read as its 00:00Z). The line names the field(s) and their raw text beside the UTC time.
- **A call whose close_ref.close_at is inside the window** also prints `its close_ref.close_at ... is inside the ruled window: the grade read a close from the window ([C2], [F4])`.
- **Each REPRICE** prints its raw time, the UTC time and its own label.
- **FILL lines** are dated by the latest of `opened` and `closed`. **CSV lines** are dated by the latest timestamp in the line. Both read the Z or offset, and both print the raw text beside UTC. A time with neither is `no reliable time (no Z or offset in the text, not read as UTC)`, and a CSV line says how many such times it holds.
- **Each ledger file** is labelled by its mtime. The stale-ledger WARNINGs, the standing fresh-export line, and the open orders / positions / settlements line (MANUAL 3) are unchanged.

**[F18] backups and pack DBs.** Unchanged: listed by name, mtime, size and `.sha256` or MANIFEST hash, never opened. Reference points are laptop backups only.

**[PRE] the -pre pass:** F0, F1-F4, F6, F8, F9, F11-F15, F17 and F18 again, 15 sections.

### Closing sections

**[Z1] after.** The same signature as before, compared with the round-4 rule above.

**[Z2] readers with no stored output, or whose output names no match id.**
- **Round 4:**
  - The `k-track-receipt` row is its own, split from the `kalshi-disagreement, coverage` row.
  - The history-readers row names `mlb-odds-timing` (cli.py:3685) and `scripts/kalshi_leg_audit.py` as console only, with MANUAL 5.
  - The cutover-readiness row is re-cited `:36-40` and `:85-94` (CAPTURE_ROW_FIELDS at `:88`).
- **MANUAL 1 (compare_exports):** unchanged.
- **MANUAL 2 (cutover-readiness):** it runs on the HOST (`cutover_readiness.py:36-40` at main). Paste any HOST run since the cutoff, or the architect's laptop-form dry read, if one exists. A pass does not clear the crossing.
- **MANUAL 3 (Kalshi portfolio)** and **MANUAL 4 (host):** unchanged.
- **MANUAL 5 (consoles):** paste the scrollback of any run since the cutoff of `kalshi-replay`, `close-probe --match 50548|50550`, `scripts/replay_inventory_probe.py`, `kalshi-disagreement`, `mlb-actionable-receipt`, `venue-calls-receipt`, `quote-age-report`, and, new in round 4, `k-track-receipt` (with any `--out` file it wrote outside docs/receipts), `mlb-odds-timing` and `scripts/kalshi_leg_audit.py`.

## For the architect (surfaced, not decided)

1. **The sidecar stance (law 5).** The default opens mode=ro as every ro_connect reader does (`coverage_map.py:108-109`). On a quiet laptop that may create `-wal`/`-shm` under data/ (Linux-built SQLite), or fail (Apple SQLite). `REC594_STRICT=1` refuses instead. The block takes neither of the options it names for the Apple failure. This is the repo's existing stance, flagged here, not a new one.
2. **The (b) to (e) rows of `[D13]`, and the other games of `[C6]`:** which rows move. The ruling names four.
3. **A tie in the ruled second:** the architect names the four, and `REC594_FOUR` previews them.
4. **Host-side copies** ([F0]/[F13]/[F14]/[F15] host files, `~/sp-backups`): MANUAL 4.
5. **New in round 4: undatable mirror files after the squash.** A mirror file can have no reachable commit of its bytes before the squash (for example in a fresh re-clone, which has no pre-squash reflog) and no `exported_at` or `desk_meta.as_of`. Such a file is listed in both passes as `undatable (squashed)`, dated only at or before the squash. Whether it belongs inside the window is the architect's read.
6. **New in round 4: fills with no offset.** A Kalshi fill or CSV time with no Z or offset is `no reliable time`. It is not labelled before or inside, and the raw text is printed.

## Tested (scratch only), round 4

**The harness** is `.../rec594/vrun/x/v4`, with the reviewers' inputs untouched.
- `r4/root` and `r4/home` are `cp -a` copies of `v4/root` and `v4/home`, with mtimes kept. `r4/packs` links to `v4/packs`, so the migrate receipt's relative pack path resolves as it does from `v4/root`.
- Every run goes through `v4/scripts/run_x4.sh` unchanged. That runs the block as a file with `bash <file>`, as the new delivery does, or with `bash --norc -i < file`.
- The round-4 driver is `r4/scripts/run_r4_all.sh`. Outputs are `v4/out/r4_<label>.out` and `.harness`.
- **Round-4 decoys** (`r4/scripts/seed_r4.py`, writes only under `v4/r4`, prints an EXPECT line each):
  - fills and CSV lines at `-04:00` on 10-16 at 19:40 and 22:55 ET, a naive pair, and a `-04:00` pair wholly before the cutoff;
  - an untracked `docs/receipts/k-track-2026-10-17T1600Z.md` that names no game;
  - `r4/mirror_fresh`, a fresh clone of `mirror_sq` with no pre-squash reflog, plus a second squash at 10-18 13:00Z over two files that only it commits: one whose `exported_at` is 10-16 20:00Z and one at 10-17 15:00Z;
  - closing_watch.log: Game 3's block (`[match 50546]`) whose order line carries a 161800 ticker, and a header with no `[match N]`.
- `r4/scripts/z1_writer.py` waits for the block's own open to create the `-wal`, then commits and stays connected until the block has finished.

**Final pass.** Block sha256 `590b574b9aed7fa28b0f5f91753bfe98e5bac84f636ed2144aeb817ceeefa8d9`, 133,840 bytes.
- Every run exits 0, with no ERROR and no Traceback.
- No run prints `command not found` or `event not found`.
- **The DB and -wal.** Before and after the whole pass:
  - `x1.db`: sha256 `24a4a272f3b377c880f66439bd77fe06de4c6a0a481b7436cd48234bc91cafd8`, 569344 bytes, mtime 1792356503.603656.
  - `x1.db-wal`: sha256 `35c499d36653fe689c91403bde2e6005f4d4a68b4ce9860a35060e13b143b203`, 74192 bytes, mtime 1792356503.607624.
  - The `-shm` content (`67fed6ff...`) is unchanged; only its mtime moved.
- **No other writes.** Every DB-reading run's harness reports the DB, -wal, -journal and dir listing IDENTICAL, except the two WAL cases below. Nothing in the repo is newer than the pass marker outside `.git` and `.claude`, and there is no data/ anywhere.
- **`r4_m1_plain` (bash, a file):** 60 sections, 60 count lines.
  - **F10:** 14 lines.
    - the 50550 pair block;
    - Game 3's `[match 50546]` block, labelled `another game (match 50546)`;
    - the header with no match id, as `pair block by team`;
    - the page line `Tampa Bay Rays @ Cleveland Guardians PASS was PLAY`, `[matched by team]`.

    The 50551, 9001, 50553 and 50552 blocks are counted, not printed, and the v4 run's page, closing-file, mirror and check lines after the 50552 block are not printed. Round 3 printed 21 lines with "2 pair blocks".
  - **F12:** 6 files, including the k-track receipt by name.
  - **F16:**
    - `r4f_in` is dated `closed (raw 2026-10-16T22:55:03-04:00) = 2026-10-17T02:55:03Z`, no label.
    - `r4f_naive` reads `no reliable time ... opened 2026-10-16 19:40:12, closed 2026-10-16 22:55:03`.
    - `r4f_before` is dated `= 2026-10-16T23:20:00Z` and labelled before.
    - The `-04:00` CSV line reads `= 2026-10-17T02:55:03Z`, no label. The naive CSV line reads `no reliable time in the line | 2 time(s) with no Z or offset, not read as UTC`.
    - v4a is dated by `executed_at` 2026-10-17T00:05Z. v4b is dated by `graded_date (raw 2026-10-17) = 2026-10-17T00:00:00Z` with `its close_ref.close_at 2026-10-16T23:25:59.203319 is inside the ruled window`. Neither is labelled before.
  - **C4:** "9 rows re-pointed in memory (... 3 captured before the ruled cutoff)". D0's four read `ruled_window inside`, and its 23:24-23:28 list labels id 19 BEFORE.
  - **Z2:** 25 readers and 5 manual steps. **Z1:** unchanged.
  - Against round 3's `m1_plain`, F0, F17 and F18 give the same counts. F0 scans one file more: the k-track receipt.
- **`r4_m2_inter` (`bash --norc -i < file`):** its real count lines (lines starting `[TAG] count:`) are identical to the plain run's 60. The 2 extra pattern hits are bash -i's echo of input continuation lines (prefixed `> `), not output.
- **`r4_squash`** (`SP_EXPORTS_MIRROR_DIR=v4/mirror_sq`, the reviewer's squash replay):
  - **F14 main:** 7 rows in 6 files, each dated by its first commit or its last commit after the squash, plus `laptop/latest/uncommitted.json` as `undatable (squashed): ... at or before 2026-10-18T06:10:00Z`.
  - **F14-pre:** 4 rows in 4 files. `host/2026-10-16/window_24h.json` (C2h, first written 10-16 22:00Z), `closing_pre.json` (C2, 23:20Z) and `mlb_MLB_2026-10-16.json` (C1, 14:00Z) are each labelled before, plus the undatable file. C0 (10-15) is in neither pass.
  - **F0 and F0-pre** match: the C1/C2/C2h files with their first-commit dates, labelled, in F0-pre; the undatable file in both.
  - **F15 main:** "9 squash or root re-commits ... of bytes first written earlier, not counted as writes in this window". Round 3: F14 main had 11 rows in 10 files all dated 06:10Z, and F14-pre had 0.
- **`r4_squash_fresh`** (`SP_EXPORTS_MIRROR_DIR=v4/r4/mirror_fresh`):
  - **F14 main:** `laptop/2026-10-18/mlb_MLB_2026-10-18.json` by its first commit (`laptop: morning`, 12:00Z, reachable through origin's ref); `..._r4in.json` by its own `exported_at` 2026-10-17T15:00Z; 10 files `undatable (squashed), at or before 2026-10-18T06:10Z`, using the earlier squash's time as the bound, not the 13:00Z one.
  - **F14-pre:** `..._r4pre.json` by its `exported_at` 2026-10-16T20:00Z, labelled before, plus the same 10 undatable files.
- **`r4_bookrow`** (a 50550 odds row and a book snapshot at 10-16 12:00, predictions.computed_at 10-16 10:00):
  - D7's 10-16 group reads `BEFORE`, with "1 groups wholly before the ruled cutoff".
  - D8's row 23 reads `BEFORE`, and 50550's line reads "1 (1 captured before the ruled cutoff)". The verdict reads "no".
  - D9's row 2 reads `BEFORE`.
- **`r4_z1_writer`** (a WAL copy with no sidecars; the writer commits during the read and stays connected): the DB file's sha256, size and mtime are unchanged, and the `-wal` is 16512 bytes. `[Z1] count: 3 changed (another process committed 16512 bytes of WAL frames during the read: paste again, or run the file again)`.
- **`r4_nosc_default`** (the same copy, no writer): SQLite created the `-wal` (0 bytes) and `-shm`, and the DB is unchanged. `[Z1] count: 3 changed (only the sidecars this block's own mode=ro open created)`.
- **`r4_nosc_strict`:** refused, nothing created, `[Z1] count: unchanged`, 45 sections.
- **`r4_nopython3` and `r4_nopython3_i`** (PATH without python3, plain and `bash -i`): 45 headers and 45 `count: absent (no usable interpreter python3; ...)` lines, identical between the two, with no `command not found`. `r4_pymissing` (`REC594_PY=python-not-on-path`) is the same. Round 3: 8 count lines, and `python3: command not found` at three lines.
- **`r4_venv_nosqla`** (a `./venv/bin/python` without SQLAlchemy): parts D and F ran under `./venv/bin/python`, C0 printed `not run ... No module named 'sqlalchemy'`, C1-C6 printed `absent`, and the run had 60 count lines.
- **Delivery.**
  - The operator form (`bash <file> 2>&1 | tee ~/rec594_<stamp>.txt` from the checkout root) left exactly one file in that HOME, the operator's, with 60 count lines; the block wrote none.
  - The terminal form (`script` gives the block a tty, as a paste does) left the block's own `rec594_<stamp>.txt`, with 60 count lines.
- **Unchanged from round 3, rerun:** `r4_tie`, `r4_four_bad`, `r4_cutwide` (45: PRE empty, with the reason), `r4_cutnarrow`, `r4_cutbad`, `r4_cuteq`, `r4_strict_sc`, `r4_nourl` (45, absent, no data/ created), `r4_stale1`, `r4_stale2` and `r4_realwriters` (45).

**Mechanical checks** (`r3/check_block.py`, and `bash -n`):
- no tabs; no `!` except before `=` or a space; ASCII only;
- no single quote in REC594_LIB; no shell comment lines;
- three quoted heredocs, none in `$( )`;
- every Python part parses as Python 3.8.

The time parser was unit-checked separately (`r4/t_parse.py`): `-04:00`, `+0000`, `Z`, a 1-digit fraction, naive (UTC for app text, no reliable time for fills), a date, garbage and None.

**Not tested here:** zsh, macOS bash 3.2 and Apple's SQLite, none of which exist in this container. The zsh and bash 3.2 rules are followed by construction. The Apple failure text is the only branch no run reached.
