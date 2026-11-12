# Releases — main is BETA, production is tags

Ruled by the architect on 2026-09-30.

| | Tracks | Moves when |
|---|---|---|
| **BETA** | `main`; the laptop tracks it | every merge. Fast iteration continues as now. |
| **PRODUCTION** | the latest `vX.Y.Z` tag; the host runs it | only when the architect's ruling cuts a tag |

The host never pulls `main` again.

`deploy/hosting/sp_deploy.py` fetches tags and checks out the latest
`vX.Y.Z` as a detached HEAD, or the exact `--tag` you pass for a rollback or
a pin. If origin has no release tag, the deploy refuses and the host stays
where it is. It never falls back to `main`.

## What names the running release
`sp_common.running_release()` returns one of these:

| Value | Meaning |
|---|---|
| `v1.0.0` | HEAD sits exactly on a release tag (production) |
| `BETA main@<sha>` | HEAD is on a branch |
| `UNTAGGED@<sha>` | HEAD is detached, not on any tag |
| null | git is unreadable (law 4) |

It shows up in four places:
- **Every receipts-log line** has a `release` field: boot, chain, step,
  backup, page and deploy.
- **The boot receipt** prints `running <tag>`.
- **Every chain's final line** prints `running <tag>`.
- **`sp_receipts.py`** prints the running release in its header. Chain,
  boot and deploy rows carry it in the key line.

## Promotion ritual
The ritual for every tag, v1.0.0 and hotfixes included, with no exceptions:

1. **CI green, the host's receipts clean, and the day's compare run and
   read** (ARCHITECT 2026-11-02 11:35 ET, addendum 218 item 1, #782; from the
   tag after v1.6.2), verbatim: "CI green on the tag's commit, the host's
   receipts since the last tag with no failing row (sp_receipts), AND the
   day's compare run and read — it certifies the machine-neutral files it
   can still see and names any divergence; an empty window is reported, not
   treated as a pass of anything it did not compare". The comparator is
   `deploy/hosting/compare_exports.py`; paste its verdict and the receipts'
   line. Through v1.6.2 step 1 read: "The day's laptop-vs-host compare
   passes. The parallel week's comparator, `deploy/hosting/compare_exports.py`,
   becomes the release gate. Paste its verdict." Since the cutover the laptop
   writes no production page, so that compare certified only the
   machine-neutral files (one on 2026-11-02; #782).
   A compare that compared no paired file with rows in its window (addendum
   335 item 4(c), below) reads `NOTHING-TO-COMPARE` (exit 3; the
   mirror's status pending) and is neither a pass nor a fail of step 1: the
   gap is named. ARCHITECT 2026-11-11,
   addendum 334 item 3, verbatim: "since MLB's close there is no kind both
   machines export on the same day, so the tag ritual's step 1 cannot pass or
   fail until spring", and of the tags until the off-season comparison is
   ruled: "Until then a tag's step 1 is recorded as 332 item 4 recorded
   v1.6.6's: the gap named, the tag ruled on CI and the PRs' own receipts."
   **The off-season comparison (ARCHITECT 2026-11-11 08:45 ET, addendum 335 item 4, #924), verbatim:** (a)
   "It certifies what step 1 exists for — that main on the laptop and the
   tag on the host turn the same provider answers into the same rows through the shared ingestion and
   `_fixture_row` path — and nothing about the market, the Desk or any model, which the release Issue says in
   those words." (f) "WHICH COMPARE IS THE DAY'S: a tag's step 1 reads the last COMPLETE day's folder (D-1 for a
   morning tag: the pair completes at the host's 16:0xZ push), by a hand run of the comparator pasted in the tag
   block as v1.6.3's was; the mirror's commit status is the daily signal, not the ritual's record." The hand run
   is `python3 deploy/hosting/compare_exports.py <mirror>/laptop/<D-1> <mirror>/host/<D-1> --since 0` from the
   tag's checkout (the paired kinds as declared; the verdict rule is 335 item 4(c) as 336 item 4 corrects it, in
   the comparator's docstring). D-1 is a complete day on the run's own UTC date, so a paired kind missing on a
   side reads DIVERGENT there (ARCHITECT 2026-11-11 09:35 ET, addendum 336 item 4(2), verbatim: "for any earlier
   date it is DIVERGENT ("paired kind missing on <role>"), which is what a tag's hand run on D-1 reads (335 item
   4(f))."); a run on D itself reads `awaiting <role>` until both machines have pushed. Until the laptop's block carries the NHL lines (from the day after #924's build merges), step 1
   stays as 334 item 3 records it, above.
   Until the host runs the tag that carries NOTHING-TO-COMPARE, its own
   pushes ship v1.6.6's comparator back into the mirror, so a zero-compared
   day still reads red on host-pushed commits: read the laptop-pushed commit's
   status, or run the comparator by hand.

2. **Compile the ledger fragments, then draft the release notes.** On `main`
   (Anthony's lane, or a PR whose only change is the fold):
   ```
   python3 scripts/ledger.py compile --commit
   ```
   This folds `changelog.d/` and `docs/ledger/entries/` into CHANGELOG.md /
   BACKLOG.md in date order, deletes them, and commits that alone
   (ARCHITECT-RULE 2026-10-02; docs/LEDGER.md). The notes are then the
   CHANGELOG slice since the previous tag, written to the notes file the
   tag step reads (`logs/` is gitignored):
   ```
   mkdir -p logs && python3 scripts/release_notes.py --to <sha> > logs/release_notes_vX.Y.Z.txt
   ```
   `mkdir -p logs` first: a fresh or cleaned checkout has no `logs/`, and the redirect fails before the script
   runs (#560). This is read-only. A section whose body changed since the previous tag
   is listed as AMENDED. The script exits non-zero when it cannot read
   CHANGELOG.md, and the file then holds only its `✗` line: never tag from
   such a file.
3. **The architect rules the tag.** Anthony cuts it and pushes it:
   ```
   git tag -a vX.Y.Z <sha> --cleanup=verbatim -F logs/release_notes_vX.Y.Z.txt
   git push origin vX.Y.Z
   ```
   Claude Code never cuts or pushes a tag.
   - `--cleanup=verbatim` is required from v1.5.0 on (ARCHITECT 2026-10-16,
     addendum 88 item 3; #557). Without it, git's default cleanup strips
     every line beginning with `#`. That is the notes' header and every
     `## ` section heading.
   - v1.4.0 was cut with `-F` alone and lost those lines (see the release
     record below). A tag never moves, so it stands as cut.
4. **The ledger records the release.** Open an Issue labelled `release`
   (plus track:H, class:lane, sport:all, size:S) on the per-release
   milestone `vX.Y.Z`. Paste the notes and the compare verdict into it.
5. **Deploy on the host** (ARCHITECT 2026-10-22, addendum 154 item 2), in two
   calls. The recommended first call is the dry run: it fetches, names the
   target and prints the plan, and changes nothing.
   ```
   sudo -u sp venv/bin/python deploy/hosting/sp_deploy.py --tag vX.Y.Z --dry-run
   ```
   1. The deploy: `sudo -u sp venv/bin/python deploy/hosting/sp_deploy.py
      [--tag vX.Y.Z]` (default: the latest tag). Its receipt names the from
      and to releases and any new `migrate_*.py` files.
   2. The migration command the deploy prints, verbatim. It runs as the
      service user with host.env loaded and holds one DB lock across the
      daily backup and every migration, in order.
   - Never pass `--run-migrations` to the deploy call itself. It runs ONLY
     the migrations (it returns before the checkout) and validates the names
     against the CURRENT checkout. On the old release a new file "is not a
     migrate_*.py file": refused, nothing changed (v1.5.0's first attempt,
     2026-10-22).
   - A migration with no DB file at the configured path refuses ("no database
     at <path>; a migration never creates one — law 5"), exit 1, and writes
     nothing (addendum 112 item 1, #524).
   - A new unit file (ARCHITECT 2026-11-09 09:55 ET, addendum 304 item 2, for
     the next tag on; v1.6.5's first timer block ran `enable` before `install.sh`),
     verbatim: "when the tag ships a new unit file, `sudo bash
     deploy/hosting/install.sh` (idempotent; enables nothing) before the
     enable".

## Release record
One line per tag, from v1.4.0 on. Each release's Issue carries its notes and
its compare verdict.

| Tag | Cut (UTC) | Commit | Tag object | Release Issue |
|---|---|---|---|---|
| `v1.4.0` | 2026-10-16 14:18:21Z | `684462e3d5078ff2c906db73362a220917bf1fcb` | `253bacd00327446936cdb16ea37a76deafc20ff1` | #556 |
| `v1.5.0` | 2026-10-22 13:24:24Z | `d15b9981edfa74379dd01089f7de23db51353d45` | `358777b00f6d39de1a92f97052f3756d9b89e5c1` | #647 |
| `v1.6.0` | 2026-10-26 12:07:29Z | `4c106f5097cd4a47817d6a5cf988b7b9f21c00e6` | `01fa5d615cb0c9142b94ef816d0eb6e6d7f6f5da` | #678 |
| `v1.6.1` | 2026-10-28 12:45:48Z | `23f86e3794a7c075eb7b668e980e2f41ee90ad8f` | `fd3fd51b0179b9fe97dc1b07f00843d69150bf15` | #777 (record backfilled 2026-11-02 (addendum 213 item 2)) |
| `v1.6.2` | 2026-11-02 14:14:20Z | `98181976f9f4c98c2c3f6e3c8e576e8082d6477f` | `db8fde9c6680b46e77f843b0a5c2e779295bc9dd` | #776 (step 1 as it stood) |
| `v1.6.3` | 2026-11-03 12:59:11Z | `0c88f5cc4e9332bade5efd2043def40ab37a5def` | `7312627b5b39fc5f38e71718edb9d9cbd3f7be00` | #806 (step 1 as rewritten, #782) |
| `v1.6.4` | 2026-11-05 13:03:31Z | `284c575847379d545408bf88bb3939041e253ad8` | `fbb6e46a9348d2430b61ab475c3b5faa84b10025` | #837 (step 1 as rewritten, #782) |
| `v1.6.5` | 2026-11-09 13:46:27Z | `5f9cf13dc935ed5fdaf220772e8e8ccfea06dfc4` | `dae246a9edf64e0ad953f75d7a0c08e145f62f62` | #898 (step 1 as rewritten, #782) |
| `v1.6.6` | 2026-11-10 20:11:06Z | `8aa27a89b3e0018e8ad229f321cab3e02acec212` | `0e7844aca0254cb6b17c383f0971166ef749ecab` | #917 |
| `v1.6.7` | 2026-11-12 15:19:06Z | `6792cefec6acc3f9254a97e2ba10fc530ce1f6eb` | `577e444a9d16f9d4979faa7d587a1ce2a1d15255` | #949 |

- **v1.4.0** (ARCHITECT 2026-10-16, addendum 87). The commit is the ledger
  compile over 53a0e83, the #551 merge over c546168.
  - Its tag message lost every line of the notes beginning with `#`
    (addendum 88 item 3; #557). Cut with `-F` and git's default cleanup,
    it lacks the header ("# Release notes · 684462e… · since v1.3.0") and
    all 105 `## ` section headings: 106 lines.
  - The section bodies are all there, but without their headings they run
    on with nothing between them.
  - The full notes are in #556: `python3 scripts/release_notes.py --to
    684462e3d5078ff2c906db73362a220917bf1fcb` (105 sections since v1.3.0,
    no AMENDED line).
- **v1.5.0** (ARCHITECT 2026-10-22, addendum 154 item 1). The commit is the
  #645 merge: the ledger compile ffe4097 (43 changelog sections, 47 ledger
  entries) over 1552e8c. The tag was cut by the operator.
  - **Compare:** day 4 of 5, ruled PASS for the release gate (09:30 ET). The
    tool read DIVERGENT on 3 files, every divergence in an allowed class:
    code-version skew (the host on v1.4.0, the laptop on ancestors of
    d15b998) and capture timing. There was no data or logic disagreement.
  - **The tag message:** the first tag cut with `--cleanup=verbatim`. It
    keeps the header and all 43 `## ` section headings (44 lines beginning
    with `#`; the v1.4.0 lesson closed). It matches `python3
    scripts/release_notes.py --to d15b9981edfa74379dd01089f7de23db51353d45`
    line for line, plus one trailing blank line. No AMENDED line.
  - **Deploy:** on the host at 13:40:09Z (v1.4.0 -> v1.5.0, 176 files, exit
    0). Both new migrations ran under one lock after backup
    `sports_2026-10-22_134012.db` (integrity ok): `migrate_injury_player_source_id.py`,
    then `migrate_match_series_fields.py`.
  - **Day 5:** ruled PASS (ARCHITECT 2026-10-23 08:30 ET, addendum 155 item
    9), with both sides on d15b998. The tool read DIVERGENT on 5 files, none
    a code-version skew. The classes were capture timing, the host's NFL
    cohort from its bootstrap, and the 37 NCAA placeholder rows of
    item 8: `sp-ncaa-schedule.timer` was never installed on the host. The
    operator installed it at 12:32Z. v1.5.0 is CONFIRMED as production; the
    host stays on the tag.
  - #647 carries the notes (in four parts) and addendum 154 item 1 verbatim.
- **v1.6.0** (ARCHITECT 2026-10-26, addendum 168 item 1): the cutover's tag. The commit is the ledger compile
  4c106f50 (17 changelog fragments, 19 ledger entries) over 9659224 (#671, the fence switch off, and #672). The tag was
  cut by the operator: tagger stamp 2026-10-26 12:07:29Z (08:07:29 ET); the architect's record reads 08:11 ET,
  the push after the clean-tree gate (below).
  - **Compare:** the day's compare at 07:30 ET read DIVERGENT on 9 files, every one named code-version skew;
    ruled PASS for the release gate. Host receipts over 24h: 0 failing.
  - **The tag message:** `--cleanup=verbatim`, the header and all 17 `## ` section headings kept (18 lines beginning
    with `#`). It matches `python3 scripts/release_notes.py --to 4c106f5097cd4a47817d6a5cf988b7b9f21c00e6` line
    for line, plus one trailing blank line. No AMENDED line.
  - **The release block's clean-tree gate:** the fold commit had been made on the laptop by an earlier run of the
    release block and not pushed; the gate caught it, the push followed and the block re-ran clean. Not a finding
    (addendum 168 item 1: "the gate worked").
  - **Deploy, with the timers stopped (addendum 167 item 3):** on the host at 13:43Z (v1.5.0 -> v1.6.0, 59 files),
    after `pause` (13:43:19Z, 16 timers stopped, no chain running) and before `install`. Why that order: v1.6.0
    carries #671 (the fence switch off), and a host on its old database must never run a fence-off tag with its
    timers live (addendum 167 item 2). The migration command ran as printed: backup `sports_2026-10-26_134323.db`
    (integrity ok), then `migrate_cup_lineup_observations.py`. The fence check printed `{'on': False}`.
  - **Every receipt from `install` on names v1.6.0** (addendum 167 item 3); the preflight's names v1.5.0. The
    cutover's receipt at 13:45:11Z: running v1.6.0, flag host.
  - #678 carries the notes and addendum 168 item 1 verbatim.
- **v1.6.1** (record backfilled 2026-11-02, ARCHITECT 2026-11-02 09:55 ET, addendum 213 item 2: the ritual's step 4
  was missed on 10-28). The commit is the ledger compile 23f86e37 (22 changelog fragments, 25 ledger entries) over
  7fb77030 (#717); the tag addendum 168's postscript named for #674 (the timers retirement). Tagger stamp
  2026-10-28 12:45:48Z (08:45:48 ET).
  - **The tag message:** the header and all 22 `## ` section headings kept (23 lines beginning with `#`). It matches
    `python3 scripts/release_notes.py --to 23f86e3794a7c075eb7b668e980e2f41ee90ad8f` line for line, plus one trailing
    blank line. No AMENDED line.
  - **Compare:** addendum 168's postscript line ("the tag v1.6.1 Wednesday morning after that day's compare"), quoted
    on #777. BACKLOG holds no separate line with that compare's own VERDICT.
  - **Deploy:** `sp_deploy.py --tag v1.6.1` on 10-28; its timers line read the new runbook with the old release's
    parser (addendum 174 item 4; fixed by #725).
  - #777 carries the notes and addendum 213 item 2 verbatim.
- **v1.6.2** (ARCHITECT 2026-11-02 09:30 ET, addendum 212 item 2(b)). The commit is the ledger compile 98181976
  (26 changelog fragments, 26 ledger entries) over 9eebd349 (#770); it carries #766, #767, #771, #773, #768 and #770.
  The tag was cut by the operator: tagger stamp 2026-11-02 14:14:20Z (09:14:20 ET).
  - **The tag message:** `--cleanup=verbatim`, the header and all 26 `## ` section headings kept (27 lines beginning
    with `#`). It matches `python3 scripts/release_notes.py --to 98181976f9f4c98c2c3f6e3c8e576e8082d6477f` line
    for line, plus one trailing blank line. No AMENDED line.
  - **Deploy:** "11-02 14:22Z deploy exit 0 v1.6.1 -> v1.6.2 (98181976)" (addendum 212).
  - **Compare (step 1 as it stood, addendum 218 item 1):** PASS (ARCHITECT 2026-11-02 08:50 ET, addendum 210
    item 1): one file compared, `mlb_all_scored.json`, 879 rows both sides, 0 diffs; five host-only files, each
    explained (the writer-of-record split; the operator's undated Kalshi trade-API probe). Verbatim on #776.
  - #776 carries the notes (two comments; they exceed one Issue body) and the deploy receipt.
- **v1.6.3** (ARCHITECT 2026-11-03 08:20 ET, addendum 228: "v1.6.3 is PRODUCTION"). The commit is the ledger
  compile 0c88f5cc (12 changelog fragments, 12 ledger entries) over 6f6b9dac (#801). The tag was cut by the operator:
  tagger stamp 2026-11-03 12:59:11Z (07:59:11 ET). Verbatim (228 item 1): "tag v1.6.3: annotated, tag object
  7312627b5b39fc5f38e71718edb9d9cbd3f7be00 on the fold commit 0c88f5cc4e9332bade5efd2043def40ab37a5def (the ledger
  fold of main 6f6b9dac: 12 changelog fragments and 12 ledger entries folded), cut 2026-11-03T12:59:11Z by the
  operator's block, 12 headings kept, notes = the CHANGELOG slice since v1.6.2; CI success on the commit."
  - **The tag message:** `--cleanup=verbatim`, the header and all 12 `## ` section headings kept (13 lines beginning
    with `#`). It matches `python3 scripts/release_notes.py --to 0c88f5cc4e9332bade5efd2043def40ab37a5def` line
    for line. No AMENDED line.
  - **Step 1 (rewritten, #782):** PASS, addendum 227, as 228 item 1 records it, verbatim: "step 1 (rewritten, #782):
    CI green on the commit; the host's receipts since the v1.6.2 deploy 550 rows, 0 failing; the compare of 11-03
    (--since 1) 1 file compared (mlb_all_scored.json, 879 rows, 0 diffs), 6 host-only files each in a known class
    (closing_NFL and nfl_NFL_results: writer of record; unl_shadow: intl-daily host-only; window_24h;
    kalshi_trade_probe.json; soccer_expansion_shadow_2026-11-03_095246.json: the export switch, host-only by 178 R6) —
    PASS, addendum 227."
  - **Deploy:** verbatim (228 item 1): "deploy: receipt "11-03 13:00 deploy exit 0 v1.6.2 -> v1.6.3 (0c88f5cc)", 80
    files, no migration, requirements unchanged, timer files unchanged (the 3 MLB_LAPTOP_ONLY timers held off by T11
    as before); running_release v1.6.3; the checkout carries nfl-elo-v1's entry, the four leagues' entries and the
    market-only reason."
  - **Carries:** git's `v1.6.2..v1.6.3` holds twelve PRs: #774, #775, #778, #779, #784, #785, #793, #796, #797, #799,
    #800, #801 (62 commits with the fold commit; 61 to 6f6b9dac). Addendum 228 item 1's list ("carries: #775, #778,
    #779, #784, #785, #793, #796, #797, #799, #800, #801 (61 commits since v1.6.2).") omits #774: it merged at
    cbe4698e on 2026-11-02 at 14:42Z, after v1.6.2's cut at 14:14:20Z, so git puts it in v1.6.3. The record keeps
    git's twelve; the architect has been told.
  - #806 carries the notes (in comments; they exceed one Issue body) and the deploy receipt.
- **v1.6.4** (ARCHITECT 2026-11-05 08:05 ET, addendum 255, the tag ruling; ARCHITECT 2026-11-05 09:30 ET, addendum 257
  item 1: "Production is v1.6.4"): a migration tag. The commit is the ledger compile 284c5758 (16 changelog fragments, 16
  ledger entries) over 87a5766b (#828). The tag was cut by the operator: tagger stamp 2026-11-05 13:03:31Z
  (08:03:31 ET); the ruling's header reads 08:05 ET. Verbatim (255 item 2): "RULING: v1.6.4 is CUT on 87a5766b (the fold commit on it), A
  MIGRATION TAG: the release block now; the deploy block in its window (09:15–10:50 ET or 11:15–12:15 ET, never
  :00–:10); its dry run must name exactly migrate_ncaa_cfbd_pregame.py and nothing else; the migration by the deploy's
  own printed command (backup, then the migration, one lock); the four markers read back. Then the CFBD hand-run block
  (the first host read; Sunday's chain repeats it). Then, and only then, #831 by my block when Code names its head."
  - **The tag message:** the header and all 16 `## ` section headings kept (17 lines beginning with `#`). It matches
    `python3 scripts/release_notes.py --to 284c575847379d545408bf88bb3939041e253ad8` line for line (332 lines). No
    AMENDED line.
  - **Step 1 (rewritten, #782):** PASS, addendum 255 item 1, its three clauses read from the Tailscale console of
    12:40Z: (a) the compare (--since 1, the laptop at 87a5766b, the host at v1.6.3), "ONE compared file,
    mlb_all_scored.json, 879 = 879 rows, 0 diffs", three host-only files each explained by its kind (window_24h.json,
    unl_shadow_2026-11-05_0720.json, kalshi_trade_probe.json), none a divergence; (b) the receipts since the v1.6.3
    deploy (48h), "every row exit 0", "No failing row; the release block's awk gate reads 0"; (c) the reads.
  - **Deploy, with its migration:** verbatim (257 item 1): "THE DEPLOY (receipts 14:15Z): v1.6.3 -> v1.6.4 (284c5758,
    76 files), the dry run naming exactly migrate_ncaa_cfbd_pregame.py; the migration by the deploy's printed command
    under one lock after the backup sports_2026-11-05_141512.db (integrity ok); four NCAA markers present; the registry
    on the host carries nfl-elo-v2 and the four leagues' entries; the rehearsal module present and dormant. Production
    is v1.6.4 (docs/RELEASES.md by Code's records PR, the deploy row as the receipt)." The deploy row is this record's
    receipt. git agrees: `git diff --stat v1.6.3 v1.6.4` reads 76 files changed, and the one new `migrate_*.py` among
    them is `migrate_ncaa_cfbd_pregame.py`.
  - **Carries:** git's `v1.6.3..v1.6.4` holds sixteen PRs: #802, #804, #808, #809, #810, #812, #814, #816, #817, #818,
    #819, #820, #822, #824, #825, #828 (83 commits with the fold commit; 82 to 87a5766b). Counted from `git log
    --merges --oneline v1.6.3..v1.6.4`: 25 merge commits, of which 16 are "Merge pull request #N" and 9 merge `main`
    into a branch; sixteen PRs, as the fold's sixteen fragments and the notes' sixteen sections.
  - **Release Issue:** #837 (ritual step 4), opened 2026-11-05 by ARCHITECT 2026-11-05 10:35 ET, addendum 260 item 1:
    the notes line for line, the tag, 255 item 1's verdict and receipts, the deploy and migration rows, 255 item 2
    verbatim. The deploy row of addendum 257 item 1 is the receipt this record carries.

- **v1.6.5** (ARCHITECT 2026-11-09 08:45 ET, addendum 300, the tag ruling, as Release Issue #898 quotes it; the form
  confirmed by addendum 301 item 4): a migration tag. The commit is the ledger compile 5f9cf13d (30 changelog
  fragments, 31 ledger entries) over 2336a77a (#888's merge). The tag was cut and pushed by the operator from the
  architect's block: tagger stamp 2026-11-09 13:46:27Z (08:46:27 ET). Verbatim (300 item 1, as #898 quotes it): "1.
  THE TAG: `v1.6.5` on 5f9cf13dc935ed5fdaf220772e8e8ccfea06dfc4, `--cleanup=verbatim -F logs/release_notes_v1.6.5.txt`
  (429 lines, 30 sections, 1 AMENDED line), cut and pushed by the operator from my block after CI is green on
  5f9cf13d. Claude Code never cuts or pushes a tag." Correction (addendum 301 item 3, as #898 quotes it): "the notes
  carry 0 AMENDED sections."
  - **The tag message:** 430 lines; 31 lines begin with `#` (the header and all 30 `## ` section headings). It matches
    `python3 scripts/release_notes.py --to 5f9cf13dc935ed5fdaf220772e8e8ccfea06dfc4` line for line (429 lines), apart
    from one trailing blank line in the tag message, as on v1.6.4. No AMENDED section (301 item 3).
  - **Step 1 (rewritten, #782):** addendum 300, as #898 quotes it: the compare, laptop/2026-11-09 vs host/2026-11-09,
    0 JSON compared, 7 on one side only, every one a machine-specific kind by design, "VERDICT DIVERGENT by the
    comparator's rule and REPORTED here as "nothing comparable today, nothing certified by it"" (addendum 218 item 1);
    the host's receipts since v1.6.4, 3,994 lines with 2 failing rows, both one step of one run (nhl-daily 11-05
    16:02Z, the exports-mirror push step refused once, the chain exit 0 steps 8/8), and 0 failing rows since 11-06.
  - **Deploy, with its migration:** THE DEPLOY RECORD, verbatim (ARCHITECT 2026-11-09 09:55 ET, addendum 304 item 2:
    "every figure from the operator's consoles of this morning, the host's receipts carrying them"). The deploy rows
    are this record's receipt. git agrees: `git diff --stat v1.6.4 v1.6.5` reads 126 files changed, and the one new
    `migrate_*.py` among them is `migrate_availability_record.py` (#831, #841).
    - "13:47Z deploy: v1.6.4 (284c5758) → v1.6.5 (5f9cf13d), 126 files; receipt row `deploy 0 · v1.6.4 -> v1.6.5
      (5f9cf13d)`; the deploy named one new migration and the three shipped timers not in timers.enabled."
    - "13:49Z the migration command, verbatim as printed, one lock: `backup:daily 0 · sports_2026-11-09_134946.db
      integrity=ok · f2c52596cf5d`; `migrations 0`; migrate_availability_record.py created availability_observations
      and availability_assertions, 7 triggers, 10 of 10 declared indexes, and wrote the marker
      availability_record_migration (migrated_at 2026-11-09 13:49:58Z)."
    - "14:12Z the availability 2025 read FIRST (T11's watermark rule): AVAILABILITY-NFLVERSE observation #1 ·
      complete · depth_charts_2025.csv · HTTP 200 · rows read 554,215 · loads 221 · rows asserted 554,215 · one
      partial team group (LAC, 2025-12-18, 8 of 72 rows) · payload sha256 f5a4aa3fa70150e8 · exit 0."
    - "14:14Z the NBA first load on the host (bootstrap order): sync-competitions basketball created 1; sync-teams
      NBA 2026 created 30; sync-matches NBA 2026 created 1,266 (orientation_reversed 0 · teams_mismatch_refused 0);
      sync-kalshi-nba KXNBAGAME 64 markets · matched 28 · 28 prices stored · unmatched 36 (outside the run's window) ·
      ambiguous 0 · in-play 0."
    - "14:16Z the unit files: `install.sh` installed 34 unit files (host.env untouched, nothing enabled by it); then
      `systemctl enable --now sp-nba-daily.timer sp-availability-daily.timer` exit 0; both active, next runs Tue
      06:47Z and Tue 08:45Z; sp-tennis-daily.timer installed, disabled, inactive; timers.enabled 20 names, no
      duplicate. MY MISS, recorded as such: my first timer block ran `enable` before `install.sh` ("Unit file
      sp-nba-daily.timer does not exist") and, reading the pipeline's exit from `tail`, appended the two names to
      timers.enabled anyway; the fix block put the units in place and enabled both; the file's end state is right.
      RELEASES.md step 5 gains one line for the next tag: "when the tag ships a new unit file, `sudo bash
      deploy/hosting/install.sh` (idempotent; enables nothing) before the enable"."
    - "The receipts since the deploy: 0 failing."
    - "The compare of the day, as 300 item 0 reads it; the one failing row since v1.6.4 explained there."
  - **Carries:** git's `v1.6.4..v1.6.5` holds twenty-nine PRs: #831, #832, #834, #836, #841, #842, #843, #846, #847,
    #848, #854, #856, #857, #858, #861, #863, #864, #866, #867, #868, #869, #870, #874, #877, #880, #884, #886, #887,
    #888 (207 commits with the fold commit). Counted from `git log --merges --oneline v1.6.4..v1.6.5`: 63 merge
    commits, of which 29 are "Merge pull request #N"; thirty CHANGELOG sections, one more than the PRs, because #846
    carries two (the nfl-elo-v2 and mlb-pitchers-v1 verdict records).
  - **Release Issue:** #898 (ritual step 4), opened 2026-11-09 by ARCHITECT 2026-11-09 08:45 ET, addendum 300 item 3:
    the notes line for line, the tag, the compare verdict and the receipts, addendum 300 item 1 verbatim. The deploy
    and migration rows join it from the deploy's console (step 5).
- **v1.6.6** (ARCHITECT 2026-11-10 15:00 ET, addendum 324, the tag ruling, as Release Issue #917 quotes it): not a
  migration tag. The commit is the ledger compile 8aa27a89 (11 changelog fragments, 12 ledger entries) over 97bc8c50
  (#914's merge). The tag was cut and pushed by the operator from the architect's block: tagger stamp 2026-11-10
  20:11:06Z (15:11:06 ET). Verbatim (324 item 2): "THE TAG: v1.6.6 on 8aa27a89, `--cleanup=verbatim -F
  logs/release_notes_v1.6.6.txt`, by the operator's block once CI is green on the fold commit (the block checks).
  Code opens the release Issue "Release v1.6.6 (8aa27a89)" on a v1.6.6 milestone with the eleven PRs, the deploy
  record appended from the operator's consoles as they come (the form of 304 item 2). Codex-free: a tag is not a PR."
  - **The tag message:** 152 lines; 12 lines begin with `#` (the header and all 11 `## ` section headings). It matches
    `python3 scripts/release_notes.py --to 8aa27a89b3e0018e8ad229f321cab3e02acec212` line for line (151 lines, exit 0),
    apart from one trailing blank line in the tag message, as on v1.6.4 and v1.6.5. The one AMENDED hit is a quoted
    phrase, not a section (324 item 1).
  - **Step 1 (ARCHITECT 2026-11-10 18:55 ET, addendum 332 item 4, verbatim):** "step 1 (the laptop-vs-host compare) on
    11-10: compare_exports DIVERGENT — 0 compared, 11 one-side-only — which certifies nothing on a Tuesday in MLB's
    off-season (no kind both machines export that day); the tag was ruled on the fold's green CI and the eleven PRs'
    own receipts (324 item 1), the compare's gap recorded, not waived".
  - **No migration; one requirements change:** `git diff --stat v1.6.5 v1.6.6` reads 60 files changed, and no file
    under `migrations/` changed. requirements.txt gains `matplotlib>=3.8` (#894), which `sp_deploy` installs by its own
    rule (324 item 1).
  - **The day, verbatim (ARCHITECT 2026-11-10 16:40 ET, addendum 331 item 4):** "v1.6.6 cut (8aa27a89, 15:11 ET) and
    deployed (20:26Z); the host OS upgraded and rebooted (17:05Z, kernel 6.8.0-149) with the effective
    unattended-upgrades config confirmed; #902 restored on both machines (the laptop 00:26Z, the host 20:57Z) with the
    hold lifted (21:13Z); eleven PRs folded into the tag and two more merged after it; the Cockpit at v39." The
    deploy's own receipt line (324 item 3(b): v1.6.5 → v1.6.6, matplotlib installed, no migration, timers untouched)
    joins #917 from the operator's console.
  - **After the deploy, in order (the architect's blocks, 324 item 3, each read on #917 and #902):**
    - the exposure read and the timer SET check, both clean (327 items 1-2);
    - the #902 remedy by the chain's own step and the dry run, clean (328 items 1-2);
    - the apply, read clean (329 items 1-2);
    - `sp-ncaa-market.timer` re-enabled at 21:13Z, whose `Persistent=true` catch-up run read clean (330, 331 item 3).
  - **Carries:** git's `v1.6.5..v1.6.6` holds eleven PRs: #894, #897, #900, #903, #904, #906, #909, #910, #911, #912,
    #914 (83 commits with the fold commit). Counted from `git log --merges v1.6.5..v1.6.6`: 15 merge commits, of
    which 11 are "Merge pull request #N"; eleven CHANGELOG sections, one per PR.
  - **Not in the tag:** #913 (the Cockpit's build stamp; the artifact is the deployable, republished as v39) and #916
    (the bulletin hooks, which ride v1.6.7) merged after it (main e5c9ea41). The next tag's span opens with these two
    (331 item 1).
  - **Release Issue:** #917 (ritual step 4), opened 2026-11-10 by ARCHITECT 2026-11-10 15:00 ET, addendum 324 item 2:
    the notes line for line, the tag, and 324 items 1 and 2 verbatim. The deploy rows join it from the operator's
    consoles.
- **v1.6.7** (ARCHITECT 2026-11-12 09:50 ET, addendum 349, the tag ruling, as Release Issue #949 quotes it): a
  migration tag whose migration the deploy's plan did not list (below). The commit is the ledger compile 6792cefe (16
  changelog fragments, 17 ledger entries) over 09259889 (#936's merge). The tag was cut and pushed by the operator from
  the architect's block once CI was green on the fold (smoke 14:45:35Z, smoke-py310 14:51:43Z): tagger stamp
  2026-11-12 15:19:06Z (10:19:06 ET). Verbatim (349 item 3, in part): "v1.6.7 IS RULED on 6792cefe: the tag by the
  operator's block once CI is green on the fold commit, `--cleanup=verbatim -F` the notes."
  - **The tag message:** 197 lines and 51,699 bytes as stored (`git cat-file -p v1.6.7`); 17 lines begin with `#` (the
    header and all 16 `## ` section headings). It is byte-identical to `python3 scripts/release_notes.py --to
    6792cefec6acc3f9254a97e2ba10fc530ce1f6eb` (197 lines, exit 0). `git for-each-ref --format='%(contents)'` prints
    one more newline, which is the trailing blank line the earlier entries name. No AMENDED line.
  - **Step 1 (349 item 3, verbatim):** "STEP 1 (the compare), recorded as 334 item 3 says: no paired file existed
    before today — the first fixtures_NHL pair is today's (the laptop's file is on the mirror at 90afdb5a, reading
    pending, awaiting host), so the tag is ruled on the fold's CI and the sixteen PRs' own receipts, the gap named;
    from the NEXT tag step 1 is a hand run on the last complete day's folder (335 item 4(f))."
  - **The migration, named by the block, not printed by the plan:** #933's poll key changes `src/db/schema.py` (the
    partial unique index `uq_avail_obs_source_endpoint_scheduled` and the insert trigger
    `trg_availability_observations_poll_guard`). `migrate_availability_record.py`, unchanged in the range, applies
    both, because it reads its triggers and indexes from `schema.py`. No `migrate_*.py` file was new or modified in
    `v1.6.6..v1.6.7`, so `sp_deploy`'s plan listed none and printed no command; the architect's deploy block named it
    (349 item 4). The plan's blind spot is #950. requirements.txt unchanged; two unit files added
    (`sp-availability-observe.service` and `.timer`, shipped disabled).
  - **The deploy record, verbatim (ARCHITECT 2026-11-12 10:35 ET, addendum 350 item 1, in part):** "`DRY RUN: would
    deploy v1.6.6 -> v1.6.7 (6792cefe)`, exit 0; `✓ deploy v1.6.6 -> v1.6.7 (6792cefe, 68 files)`, exit 0,
    requirements unchanged; its timers line names sp-availability-observe.timer and sp-tennis-daily.timer as shipped
    and not enabled (as ruled) and the three MLB_LAPTOP_ONLY. THE MIGRATION, by `sp_deploy.py --expect 6792cefe…
    --run-migrations migrate_availability_record.py` under one DB lock: `✓ backup sports_2026-11-12_152050.db
    integrity=ok`; exactly two created lines — `+ Created trigger trg_availability_observations_poll_guard`, `+
    Created index uq_avail_obs_source_endpoint_scheduled` — and 18 kept; 8 triggers, 11 of 11 declared indexes; the
    marker kept (migrated_at 2026-11-09 13:49:58); 4 observations and 1,332,030 assertions stored; exit 0. Receipts:
    deploy 0, backup:daily 0 (203a39adbaa3), migrations 0. After: the timer set CLEAN (20 expected, 20 active), the
    checkout clean. PRODUCTION = v1.6.7." The deploy ran 2026-11-12T15:20–15:21Z on sp-vps-1 (kernel 6.8.0-149, no
    reboot pending).
  - **After the deploy:** the nflverse feed's step done on the 08:45Z availability-daily run, read by name (350 item 2;
    roadmap lane availability-record). `sp-availability-observe.timer` stays disabled until its own block (350 item 3).
    The bulletin hooks (#916) run from this tag: the first hooked one is the 11-12 NFL closing (349 item 5).
  - **Carries:** git's `v1.6.6..v1.6.7` holds sixteen PRs: #913, #916, #918, #919, #922, #923, #925, #927, #929, #931,
    #933, #934, #935, #936, #938, #939 (89 commits with the fold commit, 68 files). Counted from `git log --merges
    v1.6.6..v1.6.7`: 21 merge commits, of which 16 are "Merge pull request #N"; sixteen CHANGELOG sections, one per
    PR.
  - **Not in the tag:** #942 (the `check_db` fence walking data/ by device and inode): its head moved during the window
    and it took the next one (349 item 1). It merged after the tag, with #948 (the three `intl-elo-confirm --db`
    nits, #940) (main 1e51c287). The next tag's span opens with these two.
  - **Release Issue:** #949 (ritual step 4), opened 2026-11-12 by ARCHITECT 2026-11-12 09:50 ET, addendum 349 item
    3: the notes line for line, the tag, 349 items 2 and 3 verbatim, and the deploy record of 350 item 1.

## Hotfix path
A hotfix gets a patch tag (`vX.Y.Z+1`) through the same ritual. There is no
direct-to-host path and no exceptions.

To cut the tag from a commit that is not on `main`'s tip, the fix still
lands on `main` first, via PR, and Anthony merges it. The tag then goes on
that merged commit.

## First pin: cutting v1.0.0
v1.0.0 is cut from current `main` once the host is pinned to it.

1. Merge the release-model PR.
2. Run the host's last `main`-style update, so the new `sp_deploy.py` is on
   disk:
   ```
   sudo -u sp git -C <checkout> fetch origin main
   sudo -u sp git -C <checkout> merge --ff-only origin/main
   ```
3. Run step 1 of the ritual, the compare.
4. The architect rules v1.0.0 and Anthony pushes the tag.
5. Run `sp_deploy.py`. The receipt reads `BETA main@<sha> -> v1.0.0`.
6. Check that every later receipt line carries `"release": "v1.0.0"`.
