# H2 cutover runbook: the ONE `.backup` migration (H2-PREP)

**Status: PREP ONLY.** This page is the operator sequence for the H2
cutover and for checking it afterwards. **The cutover itself needs an
architect ruling on the frozen parallel-week criteria** (H0-18,
`hosting-h1.md` "Cutover criteria"). Nothing on this page, and nothing in
`sp_cutover.py` or `h2_dry_run.py`, triggers the cutover or decides it.
Ties and partial passes are rejections; they extend the parallel week.

Source of truth for the steps: `hosting-h1.md` "## H2" (cutover morning,
steps 1 to 7). This runbook executes those steps through
`deploy/hosting/sp_cutover.py` with one receipt per step.

Labels follow hosting-h1.md: **TERMINAL (laptop)**, **TERMINAL (host)**.

---

## 0. Before the ruling day

- **Dry run (any day, no host needed).** TERMINAL (laptop), from the repo
  root with the venv active:
  ```
  python scripts/h2_dry_run.py
  ```
  It builds a small SQLite in a temp dir, packs it with `sp_migrate.py
  pack`, runs the whole host sequence with `sp_cutover.py run --dry-run
  --scratch <tmp>/host` (systemctl recorded, never run), then runs the
  fresh-fingerprint compare on the scratch exports.
  - Receipt: six `receipt {...}` lines (preflight, pause, install, flip,
    resume, receipt), `DRY-RUN PASS`, `CLEAN (1 compared)` and
    `H2 DRY RUN: PASS`.
  - It never touches `data/`, the real DB, `.env`, host.env or systemd.
    It refuses a work dir under `data/` (law 5).
- **Open prerequisite (hosting-h1.md H2 step 7):** the H2-era decision on
  how MLB reaches the host after cutover (statsapi ASN block). Settle it
  before the cutover; cutover must not strand MLB.
- **Readiness readout (#85, ARCHITECT lane 2 2026-10-04).** TERMINAL (host),
  read-only:
  ```
  sudo -u sp venv/bin/python cli.py cutover-readiness
  ```
  It reads the exports mirror's working clone (`logs/exports-mirror`, or
  `--mirror DIR`), the host's receipts (`--receipts FILE` elsewhere) and
  runs the parity harness on the host's tag in a scratch git worktree.
  - **(a)** the compare streak: per date both writers pushed, newest first,
    the verdict and the classes named for each divergent line, until 5 in a
    row or the first break (a gap, no coverage, or an UNNAMED line). A date
    only one writer pushed is pending only when it is TODAY (the declared
    clock: the morning push may not have run yet); an older one is OVERDUE
    and the streak reads 0, as it does when the newest common date is more
    than a day old.
  - **(b)** the host's tag, days on it, `carries #246`, and desk calls per
    chain (chain receipts' exports, read from `host/<date>/` in the mirror).
    A full day = a UTC day wholly on the tag with at least one chain that
    COMPLETED (an explicit integer exit 0, nothing refused, every counted step
    run), none failed (a missing exit is a failure), desk rows emitted.
  - **(c)** `scripts/desk_parity_verify.py` on the tag's own code.
  - Last line: `GO — …` or `NOT-YET — <each unmet criterion>`. Exit 0 / 1.
  - The tool names only identical, capture timing (market / Kalshi / price
    fields and the Desk fields that follow them, on matched rows) and the
    comparator's guarded code-version skew. Rows or files on one side only
    (provider pagination, W1, W2) and model fields are UNNAMED: name them with
    `--named FILE` (`{"YYYY-MM-DD": "<class>: <evidence>"}`); such days print as
    operator-named. GO is a readout; the cutover is the architect's ruling.
- **Host on a release tag.** Production is a tagged release
  (docs/RELEASES.md). The host runs `sp_deploy.py` to the ruled tag before
  the cutover morning, so every cutover receipt names that tag.

## 1. Cutover morning (only after the ruling)

1. **TERMINAL (laptop)** (hosting-h1.md H2 step 1):
   - The backup line first, as every morning.
   - `bash scripts/setup_clv_capture.sh --uninstall`.
   - Run no chains.
   - Run any pending `migrate_*.py` named in the merge notes (after that
     backup), so the laptop DB is on the current schema.
2. **TERMINAL (host)** (H2 step 2): stop the host timers so nothing writes
   during the transfer:
   ```
   sudo systemctl stop $(cat /etc/sports-predictor/timers.enabled)
   systemctl list-timers 'sp-*' --no-pager      # receipt: none of the list is waiting
   ```
   `sp_cutover.py run` stops them again (idempotent) and receipts it.
3. **TERMINAL (laptop)** (H2 step 3): write the PL reference, then pack and transfer over the tailnet only.
   **The reference is written for the check (#422 RULED, ARCHITECT 2026-10-11, addendum 40 item 9):** "On the
   laptop, after the last sync and immediately before the pack: the PL predictions exported with --start and
   --end given, and the pack carries that file. The host exports with the same dates from the installed
   database." `<start>` / `<end>`: the PL games of the next round (calendar dates, `--end` inclusive); the same
   two dates go to the host in step 4. The file lands in `exports/`, which the pack carries.
   ```
   python cli.py export-predictions --sport soccer --competition PL --start <start> --end <end> --status scheduled
   #   → exports/soccer_PL_<start>_to_<end>.json   (paste its "✓ Wrote N predictions" line)
   python deploy/hosting/sp_migrate.py pack --out /tmp/sp_pack_$(date -u +%Y%m%dT%H%M)
   scp -r /tmp/sp_pack_<stamp> sp@sp-vps-1:/home/sp/      # tailnet only; no bucket/email/chat
   ```
   Receipt S1/R1: the db sha256, `integrity=ok`, a row count for every
   table, `absent:` for any manifest item that did not exist.
4. **TERMINAL (host)** (H2 steps 4 and 6), one step at a time, because the PL prediction check below
   (addendum 36 item 3) sits between `install` and `flip`. **Never `run` on cutover day:** `run` executes every
   step, `flip` and `resume` included, without stopping for the check.
   ```
   cd /opt/sports-predictor
   P=/home/sp/sp_pack_<stamp>
   sudo venv/bin/python deploy/hosting/sp_cutover.py preflight --pack $P
   sudo venv/bin/python deploy/hosting/sp_cutover.py pause --pack $P
   sudo venv/bin/python deploy/hosting/sp_cutover.py install --pack $P
   # the PL PREDICTION CHECK (below); flip only on its PASS
   sudo venv/bin/python deploy/hosting/sp_cutover.py flip --pack $P
   sudo venv/bin/python deploy/hosting/sp_cutover.py resume --pack $P
   sudo venv/bin/python deploy/hosting/sp_cutover.py receipt --pack $P
   ```
   - It runs as root (systemctl, and host.env is `root:sp 0640`). The steps
     that open the DB or the pack (verify, install) re-run as `sp`
     (`runuser -u sp`), so `data/sports.db`, `.env` and `exports/` stay
     sp-owned.
   - The cutover id is the pack directory name; every receipt carries it.
   - Steps and what each one refuses on:

     | Step | Does | Refuses on |
     |---|---|---|
     | preflight | `sp_migrate verify` (sha256, integrity, every table count); checks the pack's `DATABASE_URL` is relative; reads the timers list and host.env | missing pack; verify FAIL; an absolute `DATABASE_URL`; a missing or empty timers list, or a non-`sp-*.timer` name in it; host.env missing or not writable; `SP_WRITER_OF_RECORD` on more than one line or with a value other than `laptop`/`host`; any target under `data/` |
     | pause | `systemctl stop` on the list, then `is-active` for each timer; lists any `sp-chain@` still running | stop failed; any timer not `inactive` |
     | install | `sp_migrate install --replace` under the DB lock (waits for a running chain) | verify FAIL; S2 ≠ S1; any R2 ≠ R1; lock timeout |
     | flip | sets `SP_WRITER_OF_RECORD=host` in host.env (never touches `SP_PARALLEL_MODE`), line-preserving; keeps `host.env.pre-cutover-<ts>` beside it | ambiguous flag lines; any other key changed |
     | resume | `systemctl start` on the list; each `active`; `systemctl start sp-backup.service` | a timer not active; the backup failed or has no `integrity=ok` receipt |
     | receipt | a boot-receipt-style summary: running release, db sha (S2 = S1), R2 = R1, flag, timers, first backup | any earlier step without a successful receipt, or receipts out of order |

   - Receipt: paste the six `receipt {...}` lines and the `cutover receipt:` line (run one step at a
     time, `receipt` checks the earlier receipts of the same cutover id), plus the PL check's console.
   - **PL PREDICTION CHECK (ARCHITECT 2026-10-10, addendum 36 item 3; #410), after `install` and before `flip`:** "the host exports the PL predictions from the installed database, and the file equals the laptop's last file from that database, number for number." As ruled since:
     - **#420 (ARCHITECT 2026-10-11, addendum 38):** "In the cutover's PL check every field that is read from the database is compared, number for number. A field that is read off the clock is not compared: the Desk block, desk_meta, line_move and late_news_flag. The check prints the keys it left out, and a file with no predictions is still no coverage."
     - **#422 (ARCHITECT 2026-10-11, addendum 40 item 9):** "The reference is written for the check. [...] The check counts what it compared: at least one row with a prediction and its probabilities on each side, or it is no coverage. It prints the count. A check that does not pass ends the cutover for that day. The host stays paused: its timers stopped, the writer still the laptop, nothing resumed and nothing restored until I have read what the check showed. The laptop has lost nothing."

     The reference is the file step 3 wrote for the check, `soccer_PL_<start>_to_<end>.json`, carried by the pack (so a closing run's file name never enters the check). `install` copies the laptop's exports into `exports/`, so the host's file is written to a fresh, empty directory, never to `exports/`, and the reference is compared from its own directory. With the timers paused and the installed DB in place, on the host, with step 3's two dates:
     ```
     T=$(date -u +%Y%m%dT%H%M%SZ); F=soccer_PL_<start>_to_<end>.json
     mkdir /tmp/pl_ref_$T /tmp/pl_host_$T
     cp exports/$F /tmp/pl_ref_$T/                 # the reference step 3 wrote, as the pack carried it
     sudo -u sp venv/bin/python cli.py export-predictions --sport soccer --competition PL \
         --start <start> --end <end> --status scheduled --out /tmp/pl_host_$T/$F
     sudo -u sp venv/bin/python deploy/hosting/compare_exports.py /tmp/pl_ref_$T /tmp/pl_host_$T --since 0 \
         --ignore-keys desk,desk_meta,line_move,late_news_flag,exported_at --require-predictions
     ```
     With `--ignore-keys` the generic timestamp mask is OFF: every other key, database timestamps (`computed_at`, `captured_at`, `injuries_synced_at`) and `match_id` included, is compared; only `git_sha` (code, reported on its own line) is also left out. `exported_at` is the file's write stamp, read off the clock (PENDING the architect's confirmation on #439: it is not in the ruled list, and without it no two files ever compare clean). The console prints the keys left out (`left out of the comparison (--ignore-keys, read off the clock): desk, desk_meta, exported_at, late_news_flag, line_move`) and the count (`predictions compared (rows with a prediction and its probabilities): laptop N · host M`). Paste both lines and the verdict.
     **PASS:** `VERDICT: CLEAN`, one compared file, and N and M both at least 1. A missing host file, or no row with a prediction and its probabilities on either side, is `NO-COVERAGE`, never CLEAN.
     **Anything else ends the cutover for that day** (a number that differs, a row on one side only, NO-COVERAGE, an ERROR): do not run `flip` or `resume`, and restore nothing. The host stays paused (its timers stopped, `SP_WRITER_OF_RECORD=laptop`, the installed DB where `install` put it, the rehearsal DB still at `data/rehearsal_<ts>.db`) until the architect has read the console. The laptop has lost nothing: it is still the writer of record and its database is untouched. Section 3, "Not PASS at the PL check".
   - Steps can also run one at a time (`preflight`, `pause`, `install`,
     `flip`, `resume`, `receipt`) with the same `--pack`; `receipt` reads
     the earlier receipts of the same cutover id.
5. **Post checks. TERMINAL (host):**
   ```
   sudo -u sp venv/bin/python cli.py status
   sudo -u sp venv/bin/python deploy/hosting/sp_receipts.py --since 2h
   systemctl list-timers 'sp-*' --no-pager       # every listed timer has a next elapse
   ```
   Then, as hosting-h1.md H2 steps 4 and 5 rule: delete the rehearsal DB
   `data/rehearsal_<ts>.db` once the receipts are pasted, and delete the pack
   on both machines (`rm -rf`; it holds a DB copy and `.env`). Keep
   `host.env.pre-cutover-<ts>`; it holds no secrets and is the flag's
   rollback point.
6. **Fresh-fingerprint compare** (section 2), after the host's first chain.
7. **TERMINAL (laptop)** (H2 step 7): keep the last `.backup` file cold for
   30 days (the rollback point). The laptop's `data/sports.db` is not
   written again. The CLV launchd jobs stay uninstalled.

## 2. Fresh-fingerprint compare

The DB identity is already proven by install (S2 = S1, R2 = R1 on every
table). The compare proves the **pipeline**: the host, now running on the
laptop's history, produces what the laptop would have produced.

**When:** after the first host chain that writes exports after `resume`
(the hourly `sp-window` run at :05 at the latest).

**TERMINAL (laptop):**
```
venv/bin/python deploy/hosting/pull_exports.py
python deploy/hosting/compare_exports.py exports exports/host --since 1
```
`exports` holds the laptop's **last** exports: the laptop runs no chains
after the pack. `--since 1` limits the dated files to today (UTC); undated
files (`window_24h.json`, `fixtures_<comp>_<label>.json`) are always
compared.

**Expected classes** (every `✗` line carries exactly one of these, named in
the paste):

| Class | What it looks like | Allowed because |
|---|---|---|
| identical | `✓` | `exports/` traveled in the manifest; a file no host chain has rewritten yet is the laptop's file |
| capture timing | `fair_prob`, `market_divergence_pp`, `venue_gap_pp`, prices or Kalshi fields differ on matched rows | the host synced odds and Kalshi after the laptop's last sync |
| provider pagination | a row on one side only at a provider list/page boundary | the frozen criterion-3 class |
| code-version skew (guarded) | the comparator prints `code-version skew: laptop <sha> ≠ host <sha>` | only when both files carry `git_sha` and the line is printed; `NOT claimable` otherwise |
| WAIVER W1 | see below | ruled waiver |
| WAIVER W2 | see below | RATIFIED for MLB only (2026-10-01) |

**Not allowed:** model probabilities that differ on a matched row with no
new input on the host side (results, injuries, lineups). The host now
holds the laptop's DB, ratings and registry, so the model sides must agree.
Any line outside the table needs a BACKLOG entry and an Issue. It does not
roll anything back by itself; the architect rules.

### WAIVER W1: MLB doubleheader game 2 (`apisports doubleheader gap`)

- Source: Issue #96 (the dh-game2 known limitation), BACKLOG "MLB PHASE A
  BUILT" and ruling (4) on #73: a provider-difference class, waived with
  a receipt.
- Why: api-sports `/games` does not list doubleheader game 2 (13 games
  across 2025-2026). The host's MLB sync is the api-sports fallback, so the
  host never updates such a row. The rows inherited from the laptop are
  marked `external_ids.api_baseball_note = "apisports-unavailable"` and
  never fabricated.
- Allowed shapes, MLB only:
  - an MLB row on the laptop only, with the same date and the same teams
    as another game on both sides that day (the comparator keys a true
    doubleheader's second row as `... #2`);
  - a matched MLB doubleheader game-2 row whose status, score or kickoff
    lags on the host.
- Bound: the count of W1 rows equals that day's doubleheader game-2 count
  and nothing more (the same operator check as ruling (4)).
- Paste each one as `W1 doubleheader-game-2: <row key>`.

### WAIVER W2: MLB postponed games (RATIFIED 2026-10-01, MLB only)

Ruled: "Postponed-game waiver: ratified for MLB only (the api-sports class
we measured); any other sport needs its own receipt first." A postponed
game in any other sport is a plain divergence until its own receipt and
ruling exist.


- Why: a postponement reaches the two sides at different moments, and the
  providers report it differently: statsapi on the laptop; api-sports
  `POST` → `postponed` on the host (the three-status map ruled on #73).
  A rescheduled game moves its kickoff, and the comparator keys rows on
  (kickoff, home, away).
- Allowed shapes, MLB only:
  - the same home/away pair as `only on laptop` at the old kickoff and
    `only on host` at the new one;
  - a matched row whose `status` is `postponed` on one side and
    scheduled on the other.
- Evidence required per row: the game shows postponed or rescheduled at
  the provider (or in the DB's `status_raw`). Postponement is never
  assumed from absence alone (law 4). A game missing on one side with no
  postponement evidence is NOT W2.
- Paste each one as `W2 postponed: <row key> (<evidence>)`.

`compare_exports.py` has no `--waive` flag. The waivers are claimed in the
paste, line by line, like the explained classes. (`bootstrap.py compare
--waive` is the DB-fingerprint tool and is not used here.)

## 3. Rollback

**A refusal during `run`** prints `FAIL at <step>`. If the step came after
`pause`, it also prints `timers remain STOPPED`. Nothing resumes on its
own.

- **Refused at preflight:** nothing changed; the timers are as step 2
  left them. Fix the cause (for example, re-pack after a verify FAIL) and
  re-run `run`. To return to the parallel week instead:
  `sudo systemctl start $(cat /etc/sports-predictor/timers.enabled)`, then
  reinstall the laptop's CLV jobs. The laptop never stopped being the
  writer of record.
- **Refused at pause:** host DB and host.env are untouched. Fix it and
  re-run, or return to the parallel week as above.
- **Refused at install:** delete the pack on both machines and repeat from
  step 3 (hosting-h1.md H2 step 4: any `✗` means re-pack). Do not
  hand-move files in `data/`; a rehearsal DB moved aside stays as
  `data/rehearsal_<ts>.db` until the receipts are pasted.
- **Not PASS at the PL check** (between `install` and `flip`; #422 RULED, addendum 40 item 9): the cutover ends
  for that day. Run nothing further: no `flip`, no `resume`, no restore of the rehearsal DB, no timer start. The
  host stays paused (timers stopped, flag `laptop`, the installed DB in place, `data/rehearsal_<ts>.db` kept)
  until the architect has read what the check showed; what follows is the architect's ruling. The laptop is
  still the writer of record and has lost nothing.
- **Refused at flip or resume:** the DB is installed. Restore the flag
  from its kept copy if needed:
  `sudo cp -p /etc/sports-predictor/host.env.pre-cutover-<ts> /etc/sports-predictor/host.env`.
  Then fix the cause and re-run the single step (`flip`, `resume`,
  `receipt`) with the same `--pack`.

**After a PASS** (for example, an unexplained divergence in section 2),
rolling back is an architect ruling. It uses the same protocol in reverse
(hosting-h1.md H2 "Rollback"):
1. Stop the host timers.
2. Host: `sp_migrate.py pack`.
3. Transfer the pack to the laptop over the tailnet.
4. Laptop: `verify`, then `install --replace`.
5. Reinstall launchd (including the CLV jobs).

The laptop's 30-day cold `.backup` stays the last-resort rollback point.

## 4. Open (return to the architect)

- **RESOLVED 2026-10-01 — writer of record.** ARCHITECT-RULE: a REAL flag,
  `SP_WRITER_OF_RECORD=laptop|host`, lives in host.env AND in the laptop's
  `.env`. It is `laptop` until the flip; `sp_cutover.py flip` sets
  `host`. It is consumed by every receipt line (boot and chain included)
  and by `compare_exports` (which names the canonical side), and later by
  the feed header. No behavior is gated on it yet. `SP_PARALLEL_MODE` stays
  the H0-16 quota mode and is never touched by the flip. **After the flip,
  set the laptop's `.env` to `SP_WRITER_OF_RECORD=host` by hand**, so both
  sides agree.
- **RESOLVED 2026-10-01 — W2** is ratified for MLB only (see section 2).
- **MLB after cutover:** MLB predictions are a laptop duty (PHASE B
  negative). After cutover, MLB prediction files appear as
  `only on laptop` until the H2-era MLB decision lands. That is not a
  waiver; it is that open decision.
