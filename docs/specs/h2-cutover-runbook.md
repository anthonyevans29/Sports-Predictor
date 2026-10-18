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

## The 2026-10 schedule

ARCHITECT 2026-10-17 10:55 ET, addendum 113, "THE CUTOVER PLAN: the laptop's producer duties move to the host;
target Monday 2026-10-26, fallback 10-30". These are the plan's dates as it states them. They date the steps on this
page and change none of them: each step is done as sections 0 to 3 write it. The frozen criteria are unchanged
(ARCHITECT 2026-10-02, verbatim): "cutover when (a) 5 consecutive morning compares show only explained classes, (b)
the host has run a full day on a tag carrying #246 with desk calls emitted, (c) parity harness green on that tag."

| When (addendum 113) | What | On this page |
|---|---|---|
| Sun 10-18 → Thu 10-22 | the five morning compares: criterion (a) | section 0, Readiness readout (a) |
| Sun 10-18 | the dry run on the laptop (any mode, no host); receipt to the architect | section 0, Dry run |
| Mon 10-19 evening | the P8 rehearsal on the host (Tailscale): one `closing-run --family NFL` by hand | section 0, The host closing-watch rehearsal |
| by Wed 10-21 | v1.5.0, the release ritual as docs/RELEASES.md | section 0, Host on a release tag |
| Thu 10-22 | the host runs on v1.5.0: criterion (b)'s full day with desk calls; the parity harness on that tag: criterion (c) | section 0, Readiness readout (b), (c) |
| Thu 10-22 evening | `cli.py cutover-readiness` on the HOST, over ssh in the Thursday evening block (addendum 128 item 1(a); addendum 113 item 5 said the laptop); its GO / NOT-YET lines pasted to the architect | section 0, Readiness readout, TERMINAL (host): (b) and (T9) read the host's own receipts and list, run without `--receipts` or `--fullseason-list` (pass `--named FILE` when a day is operator-named). The laptop form (`--receipts FILE --fullseason-list FILE`) is for the architect's dry reads only. |
| Fri 10-23 morning | the architect's ruling: cutover Monday 10-26, or named reasons and the 10-30 fallback | |
| Mon 10-26, 09:00–11:00 ET (fallback 10-30) | the cutover: section 1, step by step, each step's receipt pasted before the next | section 1 |

The plan's dated items (addendum 113, "WHAT STILL HAS TO HAPPEN, DATED"), verbatim:

> 1. Sun 10-18 → Thu 10-22: the five morning compares. Each morning's Tailscale block already runs compare_exports;
> a day counts when every divergent line is identical / capture timing / code-version skew, or operator-named with
> evidence in the --named file. Sunday's is the first with both machines on tagged-or-newer code paths. I read each
> one in the morning page; a day that needs a BACKLOG entry is a day lost from the streak.
> 2. Sun 10-18 (laptop, any mode, no host): the dry run — `sp_cutover.py run --dry-run --scratch <DIR>` on a scratch
> pack (runbook section 0). Receipt to me. Block from me tomorrow.
> 3. Mon 10-19 evening (host, Tailscale): the P8 rehearsal — one host `closing-run --family NFL --start <the MNF start
> the laptop's watch paged>`; its page is a second page, the operator acts on the laptop's; I read the receipt and
> duration. Block from me Monday.
> 4. By Wed 10-21: v1.5.0. The tag carries this week's merges — the host fence (#410), the void-re-dated rule (#574),
> the coverage command (#576), the migration guard (#524) and whatever else is in by Tuesday night. Release ritual as
> docs/RELEASES.md (--cleanup=verbatim). The host runs Thursday 10-22 on it: that is criterion (b)'s full day with desk
> calls; the parity harness runs on that tag Thursday: criterion (c).
> 5. Thu 10-22 evening: `cli.py cutover-readiness` on the laptop; its GO / NOT-YET lines pasted to me. Fri 10-23
> morning: my ruling — cutover Monday 10-26, or named reasons and the 10-30 fallback.
> 6. Mon 10-26 morning, 09:00–11:00 ET (no soccer that day; NFL only in the evening; the host's 13:05Z window tick is
> the first one to run on the new database): the runbook's section 1, step by step, labelled TERMINAL (laptop) /
> TERMINAL (host), each step's receipt pasted before the next. Backup first on both machines. The laptop's watch
> uninstalled at step 1; the host's watch is already a timer. After `receipt`: the laptop is the console — blocks,
> Cockpit, MLB closings only (its DB is written by the MLB chains and nothing else, per the ruling).

Which machine runs item 5's readout (ARCHITECT 2026-10-18, addendum 128 item 1(a)), verbatim:

> (a) WHICH MACHINE RUNS `cutover-readiness`: the HOST, over ssh in the Thursday evening block, so (b) and (T9)
> read the host's own receipts and list; the laptop form (`--receipts FILE --fullseason-list FILE`) is for my dry
> reads only and is labelled as such on the page.

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
- **MLB after the flip (RULED 2026-10-12, addendum 45 item 4; it no longer holds the cutover):** "MLB stays a
  laptop duty to the season's last game. After the flip the laptop's database is written by the MLB chains, the
  MLB capture jobs and the MLB watch, and by nothing else, and it is the record for MLB predictions and for
  nothing else. How MLB reaches the host is decided before Opening Day 2027; it no longer holds the cutover."
  The 2027 decision is Issue #97. The steps are section 1 step 7.
- **The laptop's role setting (addendum 45 P1), before the pull that carries it:** the laptop's `.env` holds
  `SP_EXPORTS_MIRROR_ROLE=laptop` (host.env holds `host`). A closing run on a machine without it, or with
  anything but `host` or `laptop`, is refused before any step, and the setup script's preflight says so.
  **The cutover's preflight checks the host's (addendum 47 item 7(c)):** it refuses unless host.env itself says
  `SP_EXPORTS_MIRROR_ROLE=host`. `install --replace` copies the pack's `.env` (the laptop's, role `laptop`) over the
  checkout's, and only host.env's own line keeps the host pushing as `host`.
- **The host fence (ARCHITECT 2026-10-17, addendum 109 item 3; #410):** until the cutover, every soccer model row the host's Desk sees is PASS `host_fence` (the machine's `SP_EXPORTS_MIRROR_ROLE` is `host`, read from host.env first, then the environment, then the checkout's `.env`, so a run typed by hand, such as P8's `closing-run` below, is fenced as the timers' runs are; an unknown role is fenced too, addendum 110 item 1). "The fence lifts with the cutover (the ruling that cuts over names it)." The fence reads the switch `desk_policy.HOST_FENCE_RULE`, never `SP_WRITER_OF_RECORD`: "the cutover PR does the flip and turns the switch off in the same change" (addendum 114 item 3). The PL check below leaves the desk block out (`--ignore-keys desk,...`), so the fence does not touch it, and nothing else in the cutover reads the switch:
  - **Before `flip` (step 4, after `install`, the timers still paused), TERMINAL (host):** `sudo -u sp venv/bin/python -c "from src.walters.desk_policy import HOST_FENCE_RULE; print(HOST_FENCE_RULE)"` prints `{'on': False}` (the tag carries the cutover's PR). Anything else: do not `flip`, and return it to the architect; the writer of record would mark every PL row PASS `host_fence`.
  - **After the flip:** the host's first PL `--desk` file reads `desk_meta.host_fence_rule: false`; paste that line with the post-check receipts (step 5).
- **The host closing-watch rehearsal (ARCHITECT 2026-10-12, addendum 45 P8):** "One rehearsal before the cutover
  day, on my word, and not before the tag that carries P1 is on the host: a single closing-run by hand on the
  host, as sp, for one NFL or PL start time that the laptop's watch has already paged. Its page is a second page
  for that start, and the operator acts on the laptop's. I read its receipt and its duration before I rule the
  cutover." TERMINAL (host), only on that word, with that start time:
  ```
  sudo -u sp venv/bin/python cli.py closing-run --family NFL --start <ISO UTC start the laptop paged>
  sudo -u sp venv/bin/python deploy/hosting/sp_receipts.py --since 2h   # the closing line: exit, dur s, key line
  ```
  **A closing run started by hand on a machine that is not the writer of record is unguarded:** nothing in the
  code stops it, and nothing tells it the other machine already paged (each machine reads only its own
  receipts). P8's run is such a run, which is why its page is a second page and the laptop's is the one acted
  on. The page ends `machine: host`.
- **No timer moves (addendum 45 P6):** "In twelve days no chain held the lock, or waited for it, longer than seven
  minutes, and the watch allows thirty. A closing run meets the hourly chain only where its T-35 falls between
  five and twelve past the hour, a kickoff at about a quarter to, and then it waits for it. The units with no run
  in the read are read once they have run; they do not hold the enable."
- **T9: the weekly full-season list — "fullseason.list non-empty, dry run printed" (PRE-CUTOVER ITEM, binding;
  ARCHITECT 2026-10-18, addendum 122 item 3; #586).** The ruling, verbatim: "(a) T9 is a PRE-CUTOVER ITEM, binding:
  block_1018_t9_host.txt (Tailscale) generates the list from the host DB read-only, prints it, writes every line
  EXCEPT MLB, prints the file, then runs the chain's dry run (resolved commands only). MLB is excluded by ruling: MLB
  is a laptop duty to the season's last game; a host api-sports whole-season MLB write beside the laptop's statsapi
  rows is #569's twin-row shape. The chain's first real run is its own timer, Sun 10-25 06:00Z — the morning page
  that day carries its receipt, and Friday's cutover ruling is GO only conditional on it (an added condition; the
  frozen criteria are not loosened)."
  - Why: until 10-18 `/etc/sports-predictor/fullseason.list` on the host was the installed example (comment lines
    only), so `weekly-fullseason` refused ("lists no competitions") on 10-04, 10-11 and 10-18, paged each time
    (hosting-h1.md step T9 had never been run). block_1018_t9_host.txt's one run on 10-18 wrote its 26 lines
    (addendum 128 item 4). The host's first full-season resync is the chain's first real run (the close, below).
  - TERMINAL (host), Tailscale: the architect's block `block_1018_t9_host.txt`. It writes one host config file and
    opens the DB read-only. Receipt: paste its whole console: the generated list, the file as written (no MLB line),
    and the dry run, one `python cli.py sync-matches --competition <C> --season <S>` per line of the file
    (`sudo -u sp venv/bin/python deploy/hosting/sp_run.py weekly-fullseason --dry-run`, hosting-h1.md T10).
  - Run once: the block is NEVER re-run (ARCHITECT 2026-10-18, addendum 128 item 4, quoted at hosting-h1.md T9; a
    second run would double the lines). A list that needs regenerating comes as a fresh block from the architect
    that installs over the file (hosting-h1.md T9's form since #593).
  - The readout reads it: `cutover-readiness` prints `(T9) WEEKLY FULL-SEASON LIST` (below).
  - The close: the receipt of the chain's first real run, its own timer, Sun 10-25 06:00Z, on that morning's page.
- **Readiness readout (#85, ARCHITECT lane 2 2026-10-04).** TERMINAL (host),
  read-only, on the HOST, over ssh in the Thursday evening block (ARCHITECT 2026-10-18, addendum 128 item 1(a),
  verbatim: "WHICH MACHINE RUNS `cutover-readiness`: the HOST, over ssh in the Thursday evening block, so (b) and
  (T9) read the host's own receipts and list; the laptop form (`--receipts FILE --fullseason-list FILE`) is for my
  dry reads only and is labelled as such on the page."):
  ```
  sudo -u sp venv/bin/python cli.py cutover-readiness
  ```
  On the host, run it without `--receipts` or `--fullseason-list` (pass `--named FILE` when a day is
  operator-named): (b) reads the host's own receipts and (T9) the host's own list (the file
  host.env's `SP_FULLSEASON_LIST` names). It reads the exports mirror's working clone (`logs/exports-mirror`, or
  `--mirror DIR`) and runs the parity harness on the host's tag in a scratch git worktree.
  - **The laptop form, for the architect's dry reads only** (addendum 128 item 1(a)): TERMINAL (laptop),
    `python cli.py cutover-readiness --receipts FILE --fullseason-list FILE`, with the host's receipts and the
    host's list as the two FILEs. Without them (b) and (T9) read the laptop's own (`--receipts` defaults to this
    checkout's receipts, (T9) to this machine's `SP_FULLSEASON_LIST`). The Thursday evening readout is the host's.
  - **(a)** the compare streak: per date both writers pushed, newest first,
    the verdict and the classes named for each divergent line, until 5 in a
    row or the first break (a gap, no coverage, or an UNNAMED line). A date
    only one writer pushed is pending only when it is TODAY (the declared
    clock: the morning push may not have run yet); an older one is OVERDUE
    and the streak reads 0, as it does when the newest common date is more
    than a day old. A machine-state file (kind coverage, the day's
    `coverage --json` file) is listed by presence on its own line under the
    date and never counted toward or against (a) (ARCHITECT 2026-10-18,
    addendum 128 item 3).
  - **(b)** the host's tag, days on it, `carries #246`, and desk calls per
    chain (chain receipts' exports, read from `host/<date>/` in the mirror).
    A full day = a UTC day wholly on the tag with at least one chain that
    COMPLETED (an explicit integer exit 0, nothing refused, every counted step
    run), none failed (a missing exit is a failure), desk rows emitted.
  - **(c)** `scripts/desk_parity_verify.py` on the tag's own code.
  - **(T9)** an ADDED binding condition (ARCHITECT 2026-10-18, addendum 122 item 3(b); the frozen (a)-(c) are
    unchanged): the file `SP_FULLSEASON_LIST` names (host.env), or, in the laptop form (the architect's dry reads
    only), the host's file passed with `--fullseason-list FILE`, counted through the chain's own path
    (`sp_run.fullseason_resolve`: the parser, then the str.format `weekly-fullseason` fills its steps with).
    `fullseason list: N competitions — <CODE|SEASON> · …`, or `fullseason list: EMPTY → NOT-YET`. The setting not
    set (or `--fullseason-list` given an empty path), the file missing or unreadable, or a line the chain cannot
    parse or fill (no `|`, an empty code or season, a brace str.format cannot fill: the chain refuses each at resolve)
    are also NOT-YET, each with its reason (law 4). An MLB line on the list binds: NOT-YET, with the line named (MLB is excluded by ruling, addendum 122
    item 3(a)): it prints `⚠ MLB line(s) listed: <CODE|SEASON>, …` and the last line names it,
    `(T9) MLB line(s) on the list: MLB|2026`. ARCHITECT 2026-10-18, addendum 128 item 1(b), verbatim: "AN MLB LINE ON
    THE HOST'S LIST BINDS: NOT-YET, with the line named. The ruling excluded MLB; a list that carries it is wrong, and
    a readout that prints a warning and says GO is softer than the rule." MLB lines are named once the list parses:
    an UNPARSEABLE list is NOT-YET on its own and names no MLB line (the one parser refuses the file at its first bad
    line); fix the line, and the next run names them.
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
   - **The closing watch (#443 RULED, ARCHITECT 2026-10-11, addendum 41 item 5):** "Cutover morning, step 1: the
     laptop's closing watch is uninstalled with the CLV jobs (scripts/setup_closing_watch.sh --uninstall), and the
     step's receipt shows it gone." It starts a writing run by itself at T-35 of every start time: one between the
     reference and the pack leaves the reference older than the pack, one after the pack writes to a database the
     host does not have.
     ```
     bash scripts/setup_closing_watch.sh --uninstall
     launchctl list | grep -E 'com\.sportspredictor\.(closingwatch|mlbclosingwatch|captureodds)' || echo "none loaded"
     ```
     Receipt: paste both consoles; the second must read `none loaded`.
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
   two dates go to the host in step 4. The file lands in `exports/`, which the pack carries. The `--out` names the file in the two-date form even when
   `<start>` equals `<end>` (without it a one-day window writes `soccer_PL_<start>.json`, and step 4 would copy a
   stale file or none; Codex on #439, #441).
   ```
   python cli.py export-predictions --sport soccer --competition PL --start <start> --end <end> --status scheduled \
       --out exports/soccer_PL_<start>_to_<end>.json   # paste its "✓ Wrote N predictions" line
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
   # the HOST FENCE CHECK (section 0): HOST_FENCE_RULE prints {'on': False}; flip only then
   sudo venv/bin/python deploy/hosting/sp_cutover.py flip --pack $P
   sudo venv/bin/python deploy/hosting/sp_cutover.py resume --pack $P
   sudo venv/bin/python deploy/hosting/sp_cutover.py receipt --pack $P
   ```
   - **The settings list (ARCHITECT 2026-10-12, addendum 47 item 7(c)):** preflight prints, by name and never by
     value, each setting whose value on the host changes when the pack's `.env` replaces the checkout's (in the pack
     and not in the checkout's `.env`; in the checkout's `.env` and not in the pack; in both with different values).
     A setting to which host.env gives a value is left out, since host.env wins (an empty one, `NAME=`, falls back to the
     `.env` and stays on the list; addendum 48 item 6). "The list refuses nothing by itself. The cutover
     ruling names the settings it expects on it, and a name the ruling did not give stops the cutover before pause."
     The operator pastes the list with the preflight's receipt (`env_changes` in it, names only), and goes on to
     `pause` only when every name on it is one the ruling gave.
   - It runs as root (systemctl, and host.env is `root:sp 0640`). The steps
     that open the DB or the pack (verify, install) re-run as `sp`
     (`runuser -u sp`), so `data/sports.db`, `.env` and `exports/` stay
     sp-owned.
   - The cutover id is the pack directory name; every receipt carries it.
   - Steps and what each one refuses on:

     | Step | Does | Refuses on |
     |---|---|---|
     | preflight | `sp_migrate verify` (sha256, integrity, every table count); checks the pack's `DATABASE_URL` is relative; reads the timers list and host.env; reads the `sp-*` timers active on the host (`systemctl list-units --type=timer --state=active`, addendum 57 item 8) | missing pack; verify FAIL; an absolute `DATABASE_URL`; a missing or empty timers list, or a non-`sp-*.timer` name in it; an active `sp-*` timer that is not on the list, whatever its name, named in the refusal (the operator corrects the list by hand; the tool never writes it), or an active-timers listing that cannot be read; host.env missing or not writable; `SP_WRITER_OF_RECORD` on more than one line or with a value other than `laptop`/`host`; host.env not saying `SP_EXPORTS_MIRROR_ROLE=host` itself (addendum 47 item 7(c)); any target under `data/`; **addendum 79 item 4:** a listed timer that is not active (named); **addendum 80 item 3:** the PACK's NHL shot GATE streams (`<pack>/sports.db`, the laptop's DB that `install` puts in place) below 95% in any season they name (named with its share; read by `sp_cutover.py shot-gate --pack` as `sp`, nhl-shot-coverage's own numbers), or a pack GATE read that fails. Each check prints its own line and one refusal names every failed check. The host's live DB is read the same way and printed **for the record; it never refuses**. Below 95% there, the backfill's exact host command is printed (`nhl-shot-sync --start … --end … --dry-run` first), never run here, labelled "optional before cutover; not a prerequisite". **Every listed timer inactive and no sp timer off the list active** (a run after step 2, which is not the preflight): past the pack, data/ and timer-list reads, it stops with `timers already stopped: run the preflight before step 2` and its receipt (exit 1, `stopped`, never `refused`); no further check runs |
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
     With `--ignore-keys` the generic timestamp mask is OFF: every other key, database timestamps (`computed_at`, `captured_at`, `injuries_synced_at`) and `match_id` included, is compared; only `git_sha` (code, reported on its own line) is also left out. `exported_at` is left out by name with the other four (CONFIRMED, ARCHITECT 2026-10-11, addendum 41 item 4: "A stored time is a field read from the database, and the cutover's PL check compares it. The time the export was written is read off the clock: it is left out by name, with the other four. The daily compare keeps its timestamp mask."). The console prints the keys left out (`left out of the comparison (--ignore-keys, read off the clock): desk, desk_meta, exported_at, late_news_flag, line_move`) and the count (`predictions compared (rows with a prediction and its probabilities): laptop N · host M`). Paste both lines and the verdict.
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

   **NHL shadow post-check (ARCHITECT 2026-10-12, addendum 49 item 3; #463), read by the architect:** "After it
   the pack has brought the shots: the first nhl-daily on the host must print the fit made on the laptop's count of
   attempts, and no fallback beyond games that have no shots." Before the flip the host's shadow is known to differ
   (it has held no 2023-24 shot since 2026-10-03, and its files name v1). No shots are backfilled on the host
   before the flip; the pack carries them. Paste the `export-nhl-predictions` lines of that run (`v7 xG: 2023-24
   fit, <N> attempts` with N the laptop's count, and `goal fallbacks` no more than the games without shots), and
   no `✗ nhl_elo_v7_xg_margin_no_na was not available` line. (ARCHITECT 2026-10-13, addendum 63 item 2: a walk that
   took the goal-margin fallback for any game is not v7. Its file and rows read `nhl_elo_v7_goal_margin_fallback`, the
   run prints `✗ the walk took the goal-margin fallback for <n> of <N> games`, and nhl-shadow-grade grades it on its own
   line, never pooled with v7.)
5b. **TERMINAL (host): the host's closing watch (ARCHITECT 2026-10-12, addendum 45 P4; #405, #408 items 2 and 3).**
   "The runbook's host step, in this order: preflight for the two families, one test page as sp, the dry run,
   then install-push with the role host. Only when all four pass: install, daemon-reload, enable, and the line in
   timers.enabled. Their output is console evidence, pasted by the operator; nothing new writes a receipt."
   ```
   cd /opt/sports-predictor
   sudo -u sp venv/bin/python deploy/hosting/closing.py preflight --family NFL --family SOCCER --expect-role host
   sudo -u sp venv/bin/python deploy/hosting/closing.py test-page --family NFL --family SOCCER
   sudo -u sp venv/bin/python deploy/hosting/closing.py watch --family NFL --family SOCCER --dry-run
   sudo -u sp venv/bin/python deploy/hosting/closing.py install-push
   ```
   - Pass: preflight prints `✓ preflight: ... (NFL, SOCCER; role host)` (`--expect-role host` refuses any other role: a host pushing as `laptop` would write into the mirror's laptop side); the phone shows the test page
     "Test: the closing watch is installed (NFL, SOCCER). Pages arrive here by T-30." ending `machine: host`
     (the console says `accepted by ntfy`); the dry run lists the NFL and SOCCER start times; the install push
     prints `install push (exports mirror, host, label install): exit 0`.
   - Any one not passing: stop here; nothing is installed or enabled. Paste the consoles to the architect.
   - Only when all four pass:
     ```
     sudo install -m 0644 deploy/hosting/systemd/sp-closing-watch.service deploy/hosting/systemd/sp-closing-watch.timer /etc/systemd/system/
     sudo systemctl daemon-reload
     sudo systemctl enable --now sp-closing-watch.timer
     echo sp-closing-watch.timer | sudo tee -a /etc/sports-predictor/timers.enabled
     systemctl list-timers sp-closing-watch.timer --no-pager   # next elapse within the minute
     ```
   - The unit runs `closing.py watch --family NFL --family SOCCER` (P2: by name, never bare), every minute of
     every hour (P3: H0-3's one exemption, by name), bounded at 45 minutes. A failed run, a miss or a lock wait
     that ran out leaves exit 3 and a refusal exit 2: both already receipted and notified, both success to the
     unit. Its failure path (`sp-notify@closing-watch`) is for what the process could not report (#408 item 1),
     and that page goes out at most once in thirty minutes; every failure is still receipted, and a held-back one
     names the page it stands behind (addendum 47 item 7(b)). A failure, miss or refusal neither the screen (none
     on the host) nor the card topic took goes once through the operator topic, and its receipt names the channel
     that took it (addendum 47 item 7(a)).
     A reboot ends the tick that is running; the next tick retries (#408 item 4).
   - **"was" restarts on the host.** The host's first page computes each game's last call from the host's
     receipts and the host's `exports/` only; it does not use what the laptop last paged. The first host page
     for a game the laptop paged before the flip can lack its `was`, or show one from the file the pack carried.
6. **Fresh-fingerprint compare** (section 2), after the host's first chain.
7. **TERMINAL (laptop)** (H2 step 7): keep the last `.backup` file cold for
   30 days (the rollback point). **MLB after the flip (ARCHITECT 2026-10-12, addendum 45 item 4 and P5):** the
   laptop's database is written by the MLB chains, the MLB capture jobs and the MLB watch, and by nothing else,
   and it is the record for MLB predictions and for nothing else. "After the flip the laptop's watch covers MLB and
   nothing else, and only while an MLB game remains in the season: it is installed again, for MLB, once the host's
   timer is enabled and its first tick has been read." So, once step 5b's timer is enabled and its first tick read
   (`journalctl -u sp-closing-watch -n 20 --no-pager`), and only while an MLB game remains in the season:
   ```
   bash scripts/setup_clv_capture.sh                          # the CLV capture jobs: capture-odds --sport mlb only
   bash scripts/setup_closing_watch.sh --family MLB           # the closing watch for MLB and nothing else
   python cli.py closing-watch --family MLB --dry-run         # receipt: MLB start times only
   ```
   The setup script's consoles name MLB only (its preflight, its test page, its plist and its closing words).
   With no MLB game left in the season, nothing is reinstalled.

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
| MLB laptop duty (addendum 45) | after the flip, an MLB prediction file on the laptop only | ARCHITECT 2026-10-12, addendum 45 item 4: the laptop is the record for MLB predictions to the season's last game |

**Machine state is not a class (#592 RULED, ARCHITECT 2026-10-18, addendum 128 item 3):** "the compare treats kind `coverage` as "machine state": listed by presence on each side (one side, both sides, neither), never compared for content, never DIVERGENT, never counted toward or against criterion (a). Printed as its own line ("machine-state files: coverage laptop yes / host no")."
The day's `coverage_<date>.json` (and the latest copy `coverage.json`) is never a `·` or `✗` line, so
nothing is claimed for it in the paste; the comparator prints `machine-state files: coverage laptop
yes|no / host yes|no` on its own line, before the `coverage:` tally.

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
  reinstall the laptop's CLV jobs and its closing watch (`bash scripts/setup_closing_watch.sh`). The laptop never stopped being the
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
5. Reinstall launchd (including the CLV jobs and the closing watch, `bash scripts/setup_closing_watch.sh`;
   addendum 41 item 5: "The rollback's launchd step installs it again.").

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
- **RESOLVED 2026-10-12 — MLB after cutover** (addendum 45 item 4): MLB stays a laptop duty to the season's last
  game. After the flip, MLB prediction files appear as `only on laptop`, named in the paste as
  "MLB laptop duty (addendum 45)" (section 2). How MLB reaches the host is decided before Opening Day 2027
  (Issue #97); it no longer holds the cutover.
