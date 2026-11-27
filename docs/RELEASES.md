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
      When the deploy instead prints "src/db/schema.py changed in this
      range and the plan lists no new migration" (ARCHITECT 2026-11-12,
      addendum 354 item 2(b), #950), it prints no command. Read the range's
      PRs for the migration that applies the change before the DB is used; a
      schema change ships with its own new `migrate_<what>.py`
      (CONTRIBUTING.md).
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
| `v1.6.8` | 2026-11-13 21:13:23Z | `b3c5fbcf0791ff9201136d57882b80d33f01a474` | `5a88468c646ae2198790da448b11d4ddf7befbe1` | #990 |
| `v1.6.9` | 2026-11-15 19:57:26Z | `482de3fdc4ee81ee532733975fd127999d6b7843` | `eb3becef4f5f24524cefa803923c463e416e908c` | #1027 |
| `v1.6.10` | 2026-11-21 12:57:39Z | `67f02dfc1bdcd30ab7860dd1cc5c78737908a1d8` | `a081dceded6b897f3f3623de16518bdd0acb9bdd` | #1061 |
| `v1.6.11` | 2026-11-25 14:54:00Z | `3b63269b5463ebddde57bf3781bf79caeca7ae54` | `4d4f00497517db7d332a08521f35343b65bfcd62` | #1138 |
| `v1.6.12` | 2026-11-27 17:41:07Z | `412003a7cb8d3e115ff11b316f0384978536f5b1` | `d86021de71bec0189b60efd82869f90f6fc67efd` | #1173 |

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
  - **After the tag** (the record follows the host the same day, ARCHITECT 2026-11-12 16:00 ET, addendum 360 item 5):
    - The nflverse feed's step is done on the 08:45Z availability-daily run, read by name (350 item 2; roadmap lane
      availability-record).
    - **`sp-availability-observe.timer` was ENABLED on the host at 15:23–15:25Z.** The architect's own block enabled it,
      not the deploy block (350 item 3). The NHL landing watch has collected since. Verbatim (ARCHITECT 2026-11-12 10:55
      ET, addendum 354 item 1, in part): "the operator enabled sp-availability-observe at 15:23–15:25Z by my block (both
      unit files identical to the tag; the dry run exit 0; the first tick at 15:25:02Z wrote observation #5, a MISSED
      row for a T-120 poll that was due before the watch existed; the timer set CLEAN at 21)". The host's timer set is
      21 from then on: the deploy's 20 plus this one.
    - **The first fixtures_NHL pair under v1.6.7's comparator is CLEAN.** Verbatim (ARCHITECT 2026-11-12 11:25 ET,
      addendum 355 item 2, as Release Issue #949's "After the tag" carries it): "First fixtures_NHL pair under v1.6.7's
      comparator, 2026-11-12: CLEAN — 24 rows compared in the window on each side, 0 diffs; 37 outside the window on
      each side, not compared; 420 host-only columns masked and counted; status `success` on the host's 16:00:38Z push
      (bc96d6e0), `pending` (awaiting host) on the laptop's 12:55Z push before it. First real compare verdict since MLB
      closed. It certifies the shared ingestion and fixture-row path on NHL, nothing about the market, the Desk or any
      model (335 item 4(a))." The read itself (355 item 1) is on #949.
    - The bulletin hooks (#916) run from this tag: the first hooked one is the 11-12 NFL closing (349 item 5).
  - **Carries:** git's `v1.6.6..v1.6.7` holds sixteen PRs: #913, #916, #918, #919, #922, #923, #925, #927, #929, #931,
    #933, #934, #935, #936, #938, #939 (89 commits with the fold commit, 68 files). Counted from `git log --merges
    v1.6.6..v1.6.7`: 21 merge commits, of which 16 are "Merge pull request #N"; sixteen CHANGELOG sections, one per
    PR.
  - **Not in the tag:** #942 (the `check_db` fence walking data/ by device and inode): its head moved during the window
    and it took the next one (349 item 1). It merged after the tag, with #948 (the three `intl-elo-confirm --db`
    nits, #940) (main 1e51c287). The next tag's span opens with these two.
  - **Release Issue:** #949 (ritual step 4), opened 2026-11-12 by ARCHITECT 2026-11-12 09:50 ET, addendum 349 item
    3: the notes line for line, the tag, 349 items 2 and 3 verbatim, and the deploy record of 350 item 1.
- **v1.6.8** (ARCHITECT, addendum 373, the tag ruling, as Release Issue #990 quotes it): no migration, and none was
  due. The commit is the #989 merge b3c5fbcf, the ledger compile afc17728 (32 changelog fragments, 32 ledger entries)
  over 1790723d (#988's merge), as v1.5.0's was the #645 merge. The tag was cut and pushed by the operator from the
  architect's block once CI read green on the tag's commit: tagger stamp 2026-11-13 21:13:23Z (16:13:23 -0500). The
  block's first run at 15:58 ET stopped on CI in progress and cut nothing (374 item 1). Verbatim (373 item 3):
  "THE RULING: v1.6.8 IS RULED ON b3c5fbcf0791ff9201136d57882b80d33f01a474. The commit is the #989 merge, the ledger
  compile afc17728 over 1790723d, as v1.5.0's was the #645 merge. The operator cuts and pushes it with my block once
  clause 1(a) reads green; the deploy follows by my block (no migration, requirements.txt unchanged, three unit files
  shipped and neither installed nor enabled). Then 371 item 5(c)'s order."
  - **Step 1 (373 item 1, verbatim):**
    - (a): "CI ON THE TAG'S COMMIT: b3c5fbcf0791ff9201136d57882b80d33f01a474 (the #989 merge, 15:54:40 ET); its two
      smoke jobs were still running when I wrote this, and the tag block refuses to cut until every check on that sha
      reads success or skipped. #989's own head afc17728 was green at the merge (seven checks success, one skipped)."
    - (b): "THE HOST'S RECEIPTS SINCE THE v1.6.7 TAG, read on the host at 19:47Z by my block: 727 lines (1,354 with the
      step rows), ONE failing row, named: the failure page of 11-13 06:00Z for sp-availability-observe.service,
      delivered — one run of 317 of the NHL landing watch exited 1 on a ReadTimeout of the league's schedule read at
      06:00:32Z. It is a provider read that timed out on a watch that stores what it sees and marks what it misses; no
      chain failed, no step failed, nothing of the release under test is at fault. Explained, and not a bar to the tag
      (v1.6.5 was ruled the same way on two explained rows). The timers 21 expected and 21 active, none missing or
      stray; no failed unit; the checkout clean on v1.6.7 (6792cefe); no reboot pending."
    - (c): "THE COMPARE: 2026-11-13 CLEAN, as 371 item 3 records it." That record, verbatim (371 item 3):
      "2026-11-13 CLEAN. fixtures_NHL, 21 rows each side, 0 differences; 45 rows outside the window each side; 362
      host-only columns; the host's push 5840a88 at 16:01:04Z, status success. My hand run of v1.6.7's own comparator
      on laptop/2026-11-13 against host/2026-11-13 agrees. Second CLEAN day of two."
  - **Step 2 (373 item 2, verbatim):** "#989 merged by exact head afc17728 (one commit, the compile on 1790723d). I
    re-ran scripts/ledger.py compile on 1790723d in a scratch worktree before the merge and got the tree
    69e65b0742bc57858a9191188c62e5ca08d20ccb, the PR head's own; the merge commit b3c5fbcf carries the same tree, 0
    fragments pending. The notes, written on the laptop from b3c5fbcf: 323 lines, 32 sections since v1.6.7, no AMENDED
    line, no ✗ line."
  - **The tag message:**
    - Stored (`git cat-file -p v1.6.8`): 323 lines and 83,500 bytes (its final newline included); 33 lines begin with `#` (the header and all 32
      `## ` section headings).
    - It is byte-identical to `python3 scripts/release_notes.py --to b3c5fbcf0791ff9201136d57882b80d33f01a474` (323
      lines, exit 0). `git for-each-ref --format='%(contents)'` prints one more newline, as on the earlier entries.
    - No AMENDED line. The one occurrence of the word quotes v1.6.7's record inside #951's section.
  - **The tag, verbatim (ARCHITECT, addendum 374 item 1):** "THE TAG (the ritual's step 3, the operator's console,
    16:13 ET): "CI on b3c5fbcf: fragments=skipped smoke-py310=success smoke=success"; "notes: 323 lines · 32 sections ·
    first line: # Release notes · b3c5fbcf0791ff9201136d57882b80d33f01a474 (b3c5fbcf) · since v1.6.7"; "PUSHED
    v1.6.8"; "tag object: 5a88468c646ae2198790da448b11d4ddf7befbe1 · points at:
    b3c5fbcf0791ff9201136d57882b80d33f01a474 · tagger: 2026-11-13 16:13:23 -0500". My own read of origin after it: the
    tag object 5a88468c, its commit b3c5fbcf (main's head), 32 sections in its message. The first run of the block at
    15:58 ET stopped on CI in progress and cut nothing; that is clause 1(a) of 373 doing its work."
  - **The deploy record, verbatim (ARCHITECT, addendum 374 item 2):** "THE DEPLOY (the operator's console, the host at
    2026-11-13T21:14Z, by my block): before, "release before: v1.6.7 · 6792cefe · reboot pending: no"; "DRY RUN: would
    deploy v1.6.7 -> v1.6.8 (b3c5fbcf)", dry run exit 0; "✓ deploy v1.6.7 -> v1.6.8 (b3c5fbcf, 83 files)"; "· shipped
    timers not in /etc/sports-predictor/timers.enabled: 3 on MLB_LAPTOP_ONLY (held off by T11) · 3 on TIMERS_BY_BLOCK
    (held off by T11)"; deploy exit 0; "after: v1.6.8 · b3c5fbcf0791ff9201136d57882b80d33f01a474". The receipt row: "|
    11-13 21:14 | sp-vps-1 | deploy | 0 |  | v1.6.7 -> v1.6.8 (b3c5fbcf) |  |". No migration ran and none was due.
    After: "timers.enabled 21 names · expected active 21 · active 21 · missing: none · stray: none";
    sp-tennis-daily.timer disabled; sp-ncaamb-daily.timer and sp-availability-graph.timer not-found (their unit files
    are in the checkout, 3 of 3, and none is in /etc/systemd/system: install.sh has not run for them and runs only in
    my enabling blocks); sp-availability-observe.timer active; git status empty; no failed unit."
  - **The state after it, verbatim (ARCHITECT, addendum 374 item 3):** "THE STATE, for both: production is v1.6.8 on
    b3c5fbcf; main is b3c5fbcf; the HELD LIST on the host is sp-tennis-daily.timer, sp-ncaamb-daily.timer,
    sp-availability-graph.timer. Nothing on the host has installed the graph engine's requirements, the probe's
    reader, or any NCAAMB row. The next three host steps are mine, each by its own block and none tonight: the graph
    engine's install and first run; the injury probe's report phase (structure-only console); the goalie agreement
    receipt on a host backup copy." PRODUCTION = v1.6.8.
  - **What changed for the host, read from git (`v1.6.7..v1.6.8`):**
    - `src/db/schema.py` and every `migrate_*.py` are unchanged, and so is `requirements.txt`.
    - Two side requirements files are new: `requirements-graph.txt` (#943) and `requirements-probe-pdf.txt` (#970).
      `sp_deploy` names neither and installs neither; the architect's blocks install them, by hash.
    - Three unit files are new, shipped and neither installed nor enabled: `sp-availability-graph.service` and
      `.timer` (#943), and `sp-ncaamb-daily.timer` (#957).
    - The held set after the deploy is unchanged: sp-tennis-daily, sp-ncaamb-daily and sp-availability-graph.
  - **Carries:** git's `v1.6.7..v1.6.8` holds 164 commits and 83 files. Of its 40 merge commits, 33 are "Merge pull
    request #N" on main's first parent: the 32 PRs the notes carry, one CHANGELOG section each, and the fold PR #989.
    The 32: #942, #943, #946, #948, #951, #952, #954, #957, #958, #961, #962, #963, #964, #966, #967, #968, #970, #971,
    #973, #974, #975, #976, #977, #978, #980, #981, #982, #983, #984, #985, #987, #988. #942 and #948 were v1.6.7's
    "Not in the tag". #943 and #946 merged after the v1.6.7 tag's commit and before #951 (371 item 5(a)).
  - **Release Issue:** #990 (ritual step 4), opened 2026-11-13 by ARCHITECT, addendum 374 item 4.
    - It carries 373 items 1–3 and 374 items 1–3 verbatim, the 32 from git, and the record line.
    - It also carries the notes in two comments. GitHub stores three of their characters differently, all in #981's
      section; the byte-identical copy is the tag.
- **v1.6.9** (ARCHITECT, addendum 400 item 3, the tag ruling, as Release Issue #1027 quotes it): no migration, and none was
  due. The commit is the #1025 merge 482de3fd, the ledger compile f6c8ba27 (22 changelog fragments, 23 ledger entries)
  over ff8042fe (#1022's merge), as v1.6.8's was the #989 merge. The tag was cut and pushed by the operator from the
  architect's block once CI read green on the tag's commit: tagger stamp 2026-11-15 19:57:26Z (14:57:26 -0500).
  Verbatim (400 item 3): "RULED: v1.6.9 IS CUT ON 482de3fd. The operator cuts and pushes it by my block (step 3), then
  deploys it on the host by my block. After the deploy, by my blocks and in this order, as 398 item 4 has it: the
  graph (unit reinstalled, one first run, the timer enabled only on ok), then the goalies (one hand run from
  2026-10-01, a backup first, then the coverage read on a backup copy)."
  - **Step 1:** (a) the compare, verbatim (395 item 3): "DEV 1 — THE DAY'S COMPARE, for v1.6.9's step 1 whenever the
    operator calls it: 2026-11-15, v1.6.8's own comparator (b3c5fbcf) on the mirror at 7ecb70b, laptop/2026-11-15
    against host/2026-11-15. VERDICT CLEAN. fixtures_NHL: rows laptop 21, host 21, diffs 0;
    42 rows a side outside the window; 363 host-only columns; code-version skew named (laptop e3f55ee2, host
    b3c5fbcf); 9 files expected one-sided; exit 0. The host's nhl-daily export landed at 16:00:40Z." (b) the host's
    receipts since the v1.6.8 tag, verbatim (399 item 1): "v1.6.9 STEP 1(b), THE HOST'S RECEIPTS SINCE THE v1.6.8 TAG
    — READ. By my block on the host at 2026-11-15T17:23Z: host on v1.6.8 (b3c5fbcf), up 12 h 53 min, no reboot
    pending; the window read 45 h. 1,253 chain and unit rows, 3 failing; with step rows 2,356, 9 failing. Every
    failing row, NAMED: (a) 11-14 13:08Z, the failure page for sp-availability-graph.service: the row 398 item 2(b)
    named before the read. The journal has that one start and that one failure (the --db fence refusing under the
    unit's sandbox; fixed on main by #996). The timer is disabled and inactive. (b) 11-15 15:06Z,
    sp-chain@window.service, exit 1, steps 16/22, and its failure page (delivered). NOT named before the read; read
    now by a second block (17:25Z). Its six failing steps are the two single-day sync-matches for UNL 2026/27, CNL
    2025/26 and FRIENDLIES_INT 2026, each answered by API-Football (src/adapters/api_football.py:252) with "Free plans
    do not have access to this season", each in 1.3 to 3.1 s, none retried. The SAME six commands exit 0 in every
    other window run of the day, the 14:05Z run before it and the 16:05Z and 17:05Z runs after it included. That
    answer appears in no other of the 18,795 receipt rows the file holds (from 11-01). The weekly full-season chain at
    06:00Z and every other soccer step of the day exit 0. READ AS: the provider treating the key as a free-plan key
    for about one minute. Not a defect of the code being tagged, and not of v1.6.8. The operator is checking the
    subscription's own page (the plan it shows, its renewal date, a payment attempted today). (c) The landing watch:
    482 runs finished, 0 failed, since the v1.6.8 deploy. (d) Timers: timers.enabled 21 names, 21 expected active, 21
    active, none missing, none stray. No failed unit. The checkout is clean. STEP 1(b) IS MET: every failing row is
    named. Step 1(a) was met by 395 item 3. Step 1(c) is the tag block's." (c) CI on the tag's commit, with step 1 met
    in full, verbatim (400 item 2): "STEP 1 IS MET IN FULL: (a) the day's compare CLEAN (395 item 3); (b) the host's
    receipts since the
    v1.6.8 tag, every failing row named (399 item 1); (c) CI green on 482de3fd (smoke and smoke-py310 success;
    fragments skipped), read at 13:24 ET, and read again by the tag block before it cuts."
  - **Step 2 (400 item 1, verbatim):** "THE FOLD IS IN (step 2). #1025 merged at f6c8ba27 by my block; main is
    482de3fdc4ee81ee532733975fd127999d6b7843, tree de6cbfff, the tree my own compile on ff8042fe gave. No fragment
    pending. The release notes were written on the merge commit: 361 lines, 22 sections, no AMENDED line, no failing
    line, as my preview on the fold's head read. Your span count is accepted: 22 PR merges and 3 merges of main into
    PR branches since b3c5fbcf."
  - **The tag message:**
    - Stored (`git cat-file -p v1.6.9`): 361 lines and 47,754 bytes (its final newline included); 23 lines begin with `#`
      (the header and all 22 `## ` section headings).
    - It is byte-identical to `python3 scripts/release_notes.py --to 482de3fdc4ee81ee532733975fd127999d6b7843` (361 lines,
      exit 0). `git for-each-ref --format='%(contents)'` prints one more newline, as on the earlier entries.
    - No AMENDED line. The one `✗` sits inside #1021's section and quotes the goalie step's own failure line.
  - **The tag, the deploy and the state after it, verbatim (ARCHITECT, addendum 402 item 1):** "v1.6.9 IS TAGGED AND
    DEPLOYED. (a) THE TAG (step 3), by my block, the operator's hand: CI read again on 482de3fd (smoke and smoke-py310
    success, fragments skipped); the notes file 361 lines, 22 sections, its first line naming the commit; git tag -a
    v1.6.9 --cleanup=verbatim -F the notes; pushed. Tag object eb3becef4f5f24524cefa803923c463e416e908c, pointing at
    482de3fdc4ee81ee532733975fd127999d6b7843, tagger time 2026-11-15 14:57:26 -0500 (19:57:26Z). (b) THE DEPLOY, by my
    block on the host at 2026-11-15T19:57Z: release before v1.6.8 (b3c5fbcf), no reboot pending; the dry run "would
    deploy v1.6.8 -> v1.6.9 (482de3fd)", exit 0; the deploy "v1.6.8 -> v1.6.9 (482de3fd, 47 files)", exit 0; HEAD is
    482de3fd; the deploy's receipt row at 11-15 19:57, exit 0. Shipped timers not in timers.enabled: 3 on
    MLB_LAPTOP_ONLY and 3 on TIMERS_BY_BLOCK, held off by T11, as before. (c) AFTER IT: timers.enabled 21 names, 21
    expected active, 21 active, none missing, none stray; sp-tennis-daily.timer disabled, sp-ncaamb-daily.timer not
    installed, sp-availability-graph.timer disabled; the landing watch's timer active; no failed unit; the checkout
    clean." PRODUCTION = v1.6.9.
  - **What changed for the host, read from git (`v1.6.8..v1.6.9`):**
    - `src/db/schema.py`, every `migrate_*.py`, `requirements.txt` and both side requirements files are unchanged.
    - Three deploy files changed: `deploy/hosting/chains.py` (#1021, the daily goalie step in nhl-daily, UNMETERED, its
      `go_on`), `deploy/hosting/exports_mirror.py` (#1000) and `deploy/hosting/systemd/sp-availability-graph.service`
      (#996, the unit's sandbox lines). No unit file was added: the pack ships 27 timers, as at v1.6.8.
    - The held set right after the deploy is unchanged: sp-tennis-daily, sp-ncaamb-daily and sp-availability-graph (402
      item 1(c)).
  - **After the deploy, by the architect's blocks (398 item 4; 402 item 3):**
    - The graph, 2026-11-15T20:01Z on v1.6.9 (ARCHITECT, addendum 404 item 1, verbatim in part): "THE GRAPH IS BUILT ON
      THE HOST IN ITS NODE SHAPE AND ITS TIMER IS ENABLED". The first run by the unit: systemctl start exit 0,
      Result=success, 247.7 s, 1,346,489 assertion nodes equal to the record's assertions; "ok": true, buffer_pool
      268435456, memory_limit 1610612736 (404 item 1(c)-(d)). sp-availability-graph.timer enabled, next run 2026-11-16
      10:20:00 UTC; 22 timers active, none missing, none stray (404 item 1(e)). "THE HELD LIST ON THE HOST IS NOW TWO:
      sp-tennis-daily.timer (installed, disabled) and sp-ncaamb-daily.timer (not installed)."
    - The goalie backfill, 2026-11-15T20:13Z to 20:18Z on v1.6.9 (ARCHITECT, addendum 405 item 1, verbatim in part):
      "THE HOST'S GOALIE BACKFILL RAN (389 item 4(c); 398 item 4(b))." The dry run and the real run for 2026-10-01 ..
      2026-11-15 each read schedule_calls 7 and boxscore_calls 317, all 200, nothing refused; rows_written 1268, exit 0,
      under the chains' own database lock. After it, on a backup copy: 18,066 appearance rows, 4,517 games, 325
      finished 2026-27 regular-season games with both starters, the same as the laptop (405 item 1(d)-(e)). A hand
      run, not under sp_run: it has no receipt row, and 405 and #1027's comment are its record (405 item 2). From
      2026-11-16 16:00Z nhl-daily's own step keeps it current.
    - "v1.6.9's DAY, CLOSED: tagged, deployed, the graph built and its timer on, the goalie record caught up on both
      machines, KXNCAAMBGAME's table of 313 lines on main and replayed." (405 item 4, verbatim in part.)
  - **Carries:** git's `v1.6.8..v1.6.9` holds 118 commits and 47 files. Of its 26 merge commits, 23 are "Merge pull
    request #N" on main's first parent: the 22 PRs the notes carry, one CHANGELOG section each, and the fold PR #1025;
    the other 3 merge main into PR branches (#1017's, #1004's, #1007's). The 22: #991, #993, #994, #996, #997, #998,
    #999, #1000, #1002, #1004, #1005, #1006, #1007, #1011, #1012, #1014, #1015, #1016, #1017, #1019, #1021, #1022. Not
    in the tag: #1023 (the 60 hand-ruled KXNCAAMBGAME lines), merged after the tag by the architect's block (400 item
    5; 402 item 4); it opens the next span.
  - **Release Issue:** #1027 (ritual step 4), opened 2026-11-15 by ARCHITECT, addendum 402 item 2. It was put on its
    milestone v1.6.9 on 2026-11-21, as a backfill: it had been opened with none (ARCHITECT, addendum 439 item 2(a)).
    - It carries 395 item 3, 399 item 1, 400 items 1-3 and 402 item 1 verbatim, what the release puts on the host as 402
      item 2 names it, the 22 from git, and the record line.
    - It also carries the notes in one comment; read back from GitHub, the comment is the tag message character for
      character, with the server's attribution footer after it. The byte-identical copy is the tag.
    - Addenda 404 (the graph's first run and its enable) and 405 (the goalie backfill) are each pasted verbatim in a
      comment of its own (402 item 3; each addendum's heading).
- **v1.6.10** (ARCHITECT, addendum 436 item 1, as Release Issue #1061 quotes it): no migration, and none was due. The
  commit is the #1060 merge 67f02dfc, as v1.6.9's was the #1025 merge: the ledger compile d824529b (17 changelog
  fragments, 20 ledger entries) over e65457ef (#1036's merge). Its tree e93c87c5 is the tree of the architect's own
  compile (435 item 3(a); 436 item 1(b)). The tag was ruled Friday 18:52 ET and cut by the operator Saturday (436 item
  1(c)); it is on origin, as Code fetched it. Its tagger stamp is 2026-11-21 12:57:39Z (07:57:39 -0500). Verbatim (436 item 1, its heading):
  "v1.6.10 IS PRODUCTION (the ritual, each step by my block)."
  - **Step 1 (436 item 1(a), verbatim):** "STEP 1. The host's receipts since the v1.6.9 tag, read Friday 12:55Z: 2,212
    lines (4,087 with the step rows), 0 failing; the landing watch 1,236 runs finished, 0 failed; the graph unit 6
    starts, 0 failed; timers 22 of 22; no failed unit; the checkout clean. The compare, by hand with 67f02dfc's
    comparator and --since 0: 2026-11-19 CLEAN (fixtures_NHL 26 rows each side, 0 diffs) and 2026-11-20 CLEAN (19 each,
    0 diffs); the code-version skew named on both."
  - **Step 2 (436 item 1(b), verbatim):** "STEP 2. The fold, #1060, merged at d824529b: main 67f02dfc, tree e93c87c5 (my
    own compile's); 17 changelog fragments and 20 ledger entries folded; the notes 170 lines, 17 sections, no AMENDED
    line, no failing line. CI green on 67f02dfc." The fold's ruling (435 item 3) is quoted whole in #1061.
  - **Step 3, the tag (436 item 1(c), verbatim):** "STEP 3. Ruled Friday 18:52 ET; cut by the operator Saturday:
    v1.6.10, tag object a081dceded6b897f3f3623de16518bdd0acb9bdd on 67f02dfc1bdcd30ab7860dd1cc5c78737908a1d8, tagger
    stamp 2026-11-21 07:57:39 -0500 (12:57:39Z), --cleanup=verbatim; the message keeps the header and all 17 section
    headings."
  - **The tag message:**
    - Stored (`git cat-file -p v1.6.10`): 170 lines and 18,735 bytes (its final newline included); 18 lines begin with `#`
      (the header and all 17 `## ` section headings).
    - It is byte-identical to `python3 scripts/release_notes.py --to 67f02dfc1bdcd30ab7860dd1cc5c78737908a1d8` (170
      lines, exit 0). `git for-each-ref --format='%(contents)'` prints one more newline, as on the earlier entries.
    - No AMENDED line and no `✗`. The one `FAILED` is inside #1039's section, where it quotes the probe's own
      `VERDICT FAILED` label.
  - **Step 5, the deploy and the state after it (436 item 1(d), verbatim):** "STEP 5. On the host at 12:58Z: v1.6.9 to
    v1.6.10 (67f02dfc, 27 files), exit 0; no migration, no unit file, requirements unchanged; timers 22 of 22, the two
    held units as they were; the college football table on the checkout reads the ruled sha256 0698c81d...; no failed
    unit; a clean checkout." PRODUCTION = v1.6.10.
  - **A gap, named (436 item 1(e), verbatim):** "A GAP, NAMED: the deploy block read the last 12 hours of receipts (592
    lines, 0 failing). I wrote it for Friday evening and it ran Saturday morning, so the receipts from Friday 12:55Z to
    Saturday 00:58Z were not read before the deploy. My next host read covers them, and I record what it finds."
  - **After the deploy, the gap closed (ARCHITECT 2026-11-21 08:15 ET, addendum 438 item 1, verbatim):** "THE
    POST-DEPLOY READ (436 item 1(e)'s gap, closed). The host at 13:13Z on v1.6.10 (67f02dfc): the receipts of the last
    25 hours, from before Friday's read, 1,258 lines (2,429 with the step rows), 0 failing; the landing watch 269 runs
    finished, 0 failed; the graph unit one start, 0 failed, its timer enabled and active; timers 22 of 22, none missing
    or stray; no failed unit; a clean checkout; no reboot pending. The host's first college football file on the tag
    (fixtures_NCAA_2026-11-21.json, exported 13:00:35Z, git_sha 67f02dfc, 148 rows, 125 with a Kalshi quote) places
    KXNCAAFGAME-26NOV21ARKTEX on Arkansas at Texas, ARK away and TEX home; Friday's file on v1.6.9 held no quote on that
    game. The table is doing on the host what the replay said it would."
  - **What changed for the host, read from git (`v1.6.9..v1.6.10`):**
    - `src/db/schema.py`, every `migrate_*.py`, `requirements.txt` and both side requirements files are unchanged.
    - No file under `deploy/` changed. The pack ships 27 timers, as at v1.6.9.
    - KXNCAAFGAME's name table (#1036), 264 lines, sha256 `0698c81d7c05e1c4fdcf30d7a09f95f9e34ba5812e077139a3e93dd7fc0b903e`:
      the Friday replay was ruled CLEAN and the table to the host in this tag (435 item 2).
    - KXNCAAMBGAME's 60 hand-ruled lines (#1023), 313 lines in all; the proposer's and the replay's lines (#1033); the
      graph rebuild's `peak` (#1031); the read-only `scripts/ncaa_listing_probe.py` (#1039), run by hand only.
  - **Carries:** git's `v1.6.9..v1.6.10` holds 76 commits and 27 files. Of its 22 merge commits, 18 are "Merge pull
    request #N" on main's first parent: the 17 PRs the notes carry, one CHANGELOG section each, and the fold PR #1060;
    the other 4 merge main into PR branches (two in #1036's, one in #1054's, one in #1023's). The 17: #1023, #1028,
    #1030, #1031, #1032, #1033, #1034, #1036, #1037, #1039, #1040, #1042, #1043, #1045, #1046, #1049, #1054. Not in the
    tag: #1056, #1059 and #1057, merged after the tag by the architect's block, each by its exact head (436 item 3);
    they open the next span.
  - **Release Issue:** #1061 (ritual step 4), opened 2026-11-21 by ARCHITECT, addendum 436 item 2, on the milestone
    v1.6.10 (addendum 439 item 2(a): the runbook's step 4 governs).
    - It carries 435 item 3 and 436 item 1 verbatim, what the release puts on the host, the 17 from git, and the record
      line.
    - It also carries the notes in one comment (7063157208). Read back from GitHub, the comment is the script's output
      character for character, with the server's attribution footer after it. The byte-identical copy is the tag.
    - Addendum 438 item 1 (the post-deploy read that closes 436 item 1(e)'s gap) is pasted verbatim in a comment of its
      own.
- **v1.6.11** (ARCHITECT 2026-11-25 09:41 ET, addendum 528 item 1): no migration, and none was due. The commit is the
  #1121 merge 3b63269b, as v1.6.10's was the #1060 merge: the ledger compile 1688ea48 (36 changelog fragments, 38
  ledger entries) over 9fcd5e8d (#1113's merge). Its tree 0dedefdb is the tree of the architect's own compile on
  9fcd5e8d (512 item 1(a); 514 item 1). The tag was cut by the operator's own hand from the architect's block and is on
  origin, as Code fetched it. Its tagger stamp is 2026-11-25 14:54:00Z (09:54:00 -0500). Verbatim (528 item 1, its
  heading): "v1.6.11 IS RULED: THE TAG IS CUT ON 3b63269b." **NOT DEPLOYED:** the deploy's day is left open until the
  architect gives it (528 item 3), and the host stays on v1.6.10 until his read after its own reboot (530 item 1(c)).
  PRODUCTION stays v1.6.10.
  - **Step 1 (528 item 1, verbatim):** "The three conditions are met: (a) CI is green on 3b63269b. (b) The compare of
    2026-11-24 is CLEAN (525 item 2). (c) THE HOST'S RECEIPTS SINCE THE v1.6.10 TAG, by the operator's block at 14:38Z:
    98 hours; 3,165 rows, 6,017 with the steps; 0 failing. The landing watch: 1,076 runs, none failed. The graph unit:
    none failed. Timers: 22 named, 22 active, none missing, none stray. No failed unit; the checkout is clean on
    v1.6.10. The operator has the tag block. It reads CI itself and refuses a tag that exists."
  - **Step 1(b), the compare (ARCHITECT 2026-11-25 08:09 ET, addendum 525 item 2, verbatim):** "THE DAY'S COMPARE
    (2026-11-24) IS CLEAN, by the repo's own tool on the mirror at 3b63269b: one paired kind compared, fixtures_NHL, 11
    rows a side in the window, no difference; twelve files one-sided as expected; the skew named is the laptop's
    498a9295 against the host's 67f02dfc. With CI green on 3b63269b that is two of the tag's three conditions. The third
    is the host's receipts since the v1.6.10 tag, by the operator's block this morning."
  - **Step 2, the fold (ARCHITECT 2026-11-24 17:07 ET, addendum 512 item 1, verbatim in part, to (b)):** "THE v1.6.11 FOLD, #1121, IS
    READ AT 1688ea48 AND IS MERGE-READY WHEN ITS CI IS GREEN. (a) It was cut from 9fcd5e8d, as expected. I ran the
    ledger compile on that main myself and got the fold's tree, 0dedefdb: BACKLOG.md, CHANGELOG.md and 74 deleted
    fragment files, 36 sections and 38 entries, nothing else. The review found nothing. (b) The release notes on the
    fold's commit, my preview: exit 0, 565 lines, 36 sections, no AMENDED line and no failing line." And its merge
    (ARCHITECT 2026-11-24 17:24 ET, addendum 514 item 1, verbatim): "THE FOLD IS MERGED. #1121 at 1688ea48 was merged
    by the operator's agent from my block at about 17:23 ET; the first run stopped rightly while CI was running. MAIN IS
    3b63269b, its tree the fold's, 0dedefdb, with no fragment pending. The release notes are written on the laptop:
    exit 0, 565 lines, 36 sections, no AMENDED line and no failing line, as my preview had them." #1121 merged
    2026-11-24T22:23:20Z. #1116 was not on main at 17:00 ET, so the fold did not carry it, and the fold's body says so
    (508 item 1(c); 512 item 2).
  - **Main held, then released (514 item 2 in part and 528 item 3 whole, verbatim):** "MAIN IS HELD AT 3b63269b UNTIL v1.6.11 IS CUT.
    Nothing merges and nobody pushes to main before the tag." Then: "MAIN IS RELEASED WHEN THE TAG IS ON GITHUB, and not
    a minute before. Then the five waiting PRs merge by my one block, which reads the tag first: #1116, #1115, #1117,
    #1124, #1126. DEV 1: the records PR follows #1116's merge; the release record names the tag's day and leaves the
    deploy's day open until I give it."
  - **Step 3, the tag, read from git:** tag object `4d4f00497517db7d332a08521f35343b65bfcd62` on
    `3b63269b5463ebddde57bf3781bf79caeca7ae54` (tree `0dedefdb24d121185a366788d6523fb3dfd47524`); tagger timestamp
    1795618440 -0500, which is 2026-11-25 09:54:00 -0500 (14:54:00Z), the tag's day 2026-11-25.
  - **The tag and the merges, read by the architect on GitHub (ARCHITECT 2026-11-25 10:11 ET, addendum 530 item 1(a)
    to (d), verbatim):** "(a) v1.6.11 is cut: the tag object 4d4f0049 points at 3b63269b, tagged 2026-11-25 09:54 ET by
    the operator's own hand, its message the notes file whole (565 lines, 36 sections). (b) By my block, after the tag:
    #1116 at 39f1cc21, #1115 at 14cc90be, #1117 at 2934ceea, #1124 at 6edc4515, #1126 at 1dd09e8d. MAIN IS 1dd09e8d AND
    IS NO LONGER HELD. (c) THE DEPLOY IS NOT TODAY (528): the host stays on v1.6.10 until my read after its own reboot.
    Nothing merged today is on the host, and no session writes as if it were. (d) The roadmap on main prints overdue:
    0."
  - **The tag message:**
    - Stored (`git cat-file -p v1.6.11`): 565 lines and 77,738 bytes (its final newline included); 37 lines begin with
      `#` (the header and all 36 `## ` section headings). Its first line reads "# Release notes ·
      3b63269b5463ebddde57bf3781bf79caeca7ae54 (3b63269b) · since v1.6.10".
    - It is byte-identical to `python3 scripts/release_notes.py --to 3b63269b5463ebddde57bf3781bf79caeca7ae54` (565
      lines, exit 0). `git for-each-ref --format='%(contents)'` prints one more newline, as on the earlier entries.
    - No AMENDED line, no `✗` and no `FAIL`.
  - **The deploy (528 item 2, verbatim):** "THE DEPLOY IS NOT TODAY. The same console reads "reboot pending: YES". My
    deploy block refuses on a pending reboot and I keep that refusal: one change at a time on the host. The host
    reboots itself at 04:30 UTC when a security upgrade asks (322 item 1). The deploy follows my read of the host after
    that reboot, on the day the operator chooses. NOTHING WAITS ON IT: main is released by the tag, not by the
    deploy." The deploy's day: open, until the architect gives it (528 item 3).
  - **What changed for the host, read from git (`v1.6.10..v1.6.11`):**
    - `src/db/schema.py`, every `migrate_*.py`, `requirements.txt` and both side requirements files are unchanged
      (514 item 3: "schema.py, requirements.txt and the unit files are unchanged and there is no migration").
    - Three deploy/hosting files changed, all three named as 514 item 3 rules: `deploy/hosting/laptop_routine.py`, new
      (#1096, the laptop's morning steps as one command; it runs on the laptop); `deploy/hosting/sp_window_page.py`
      (#1104, the window page carries the registry's certification for each model row); and
      `deploy/hosting/compare_exports.py` (#1064, with soccer-v23's dormant PASS shadow on the host's PL pages). No unit
      file was added or changed: the pack ships 27 timers, as at v1.6.10.
  - **Carries:** git's `v1.6.10..v1.6.11` holds 161 commits and 63 files. Of its 50 merge commits, 37 are "Merge pull
    request #N" on main's first parent: the 36 PRs the notes carry, one CHANGELOG section each, and the fold PR #1121.
    The other 13 merge into PR branches: main or another branch four times into #1096's, three times into #1086's,
    twice into #1075's and once each into #1085's, #1077's and #1056's; and fcbfff35 merges the laptop's PD
    substitution commit 371aca2c into #1088's (addendum 460 item 3). The 36: #1056, #1057, #1059, #1062, #1063, #1064,
    #1065, #1066, #1068, #1069, #1070, #1071, #1075, #1076, #1077, #1080, #1082, #1083, #1085, #1086, #1088, #1090,
    #1091, #1094, #1095, #1096, #1097, #1099, #1100, #1101, #1103, #1104, #1105, #1106, #1107, #1113. Not in the tag:
    #1116 (39f1cc21), #1115 (14cc90be), #1117 (2934ceea), #1124 (6edc4515) and #1126 (1dd09e8d), merged after the tag
    by the architect's one block, which read the tag first (528 item 3; 530 item 1(b)); they open the next span.
  - **The host's MLB hold, set after the tag and on v1.6.10 (ARCHITECT 2026-11-25 10:26 ET, addendum 531 item 1,
    verbatim in part):** "THE MLB SYNC HOLD ON THE HOST (522), by my OPERATOR block, 15:22Z, on v1.6.10." **The host
    holds MLB from 2026-11-25, lifted only by the architect's block with the plan's renewal before the 2027 season**
    (531 item 1(d), whose words are "the host holds MLB from 2026-11-25, lifted only by my block with the plan's renewal
    before the 2027 season (522 item 4)"; corrected by ARCHITECT 2026-11-25 13:42 ET, addendum 537 item 3 Q2, verbatim in part:
    "MY ERROR IN 531 item 1(d): the cite is 522 items 3(b) and 3(d), not item 4."; the lift as 522 item 3(b) rules it,
    "I lift it by block when the plan is back", and 522 item 3(d): "The plan must be back before the first 2027 game the
    live path prices"). It is not a file
    of the tag: one bare line naming MLB in the host's env file (531 item 1(a)), and "No timer, unit or chain changed"
    (531 item 1(c)). The hosting spec's section O carries it beside `SP_SYNC_HOLD`, with 531 item 1(a) to (c) whole.
  - **Release Issue:** #1138 (ritual step 4), opened 2026-11-25 on ARCHITECT 2026-11-25 13:42 ET, addendum 537 item 3
    Q3, on the milestone v1.6.11. Verbatim (537 item 3 Q3): "OPEN THE RELEASE ISSUE NOW. The tag exists; the Issue names
    the tag's day and says the deploy waits for the host's own reboot. The deploy's lines are added the day it runs."
    - It is "Release v1.6.11 (3b63269b)", labelled release, track:H, class:lane, sport:all and size:S, in the form of
      v1.6.10's #1061. It names the tag's day (cut 2026-11-25, 14:54:00Z) and says the deploy waits for the host's own
      reboot (528 item 2; 530 item 1(c)). The deploy's lines are added the day it runs.
    - It carries the notes in two comments (7171823071 and 7171823693). Read back from GitHub, each with the server's
      attribution footer after it, the two bodies joined by one blank line are the tag message character for character
      (77,642 characters, its final newline included).
- **v1.6.12** (ARCHITECT 2026-11-27 12:10 ET, addendum 578 item 2): no migration, and none was due. The commit is the
  #1171 merge 412003a7, as v1.6.11's was the #1121 merge: the ledger compile a152b22d (32 changelog fragments, 33
  ledger entries) over 6d511184 (#1170's merge). Its tree 5132fedc is the tree of the architect's own compile on
  6d511184 (577 item 1(a)). The tag was cut by the operator's own hand from the architect's block and is on origin, as
  Code fetched it. Its tagger stamp is 2026-11-27 17:41:07Z (12:41:07 -0500). ONE TAG AND ONE DEPLOY (565 item 2(d);
  573 item 4(f)): it carries the record of soccer-v23's one run and its REJECT (#1170) and every merge since v1.6.11,
  and the host went from v1.6.10 to v1.6.12 in one deploy; v1.6.11 was never deployed by itself. **DEPLOYED 2026-11-27
  18:25Z. PRODUCTION = v1.6.12** (580 item 2).
  - **Step 1, the tag's three conditions (577 item 2, verbatim):** "2. THE TAG's THREE CONDITIONS (docs/RELEASES.md),
    for v1.6.12: (a) THE HOST's RECEIPTS: read this morning by the operator's block (572 item 1(a)): 0 failing rows in
    the 47 hours since Wednesday's read, which itself held 0 over 98 hours; 22 timers, clean; no failed unit. (b) THE
    DAY's COMPARE (2026-11-26) IS CLEAN, by the repo's own tool on the mirror at main 6d511184: one paired kind
    compared, fixtures_NHL, 27 rows a side in the window, no difference; nine files one-sided as expected; the skew
    named is the laptop's 8de2a3ac against the host's 67f02dfc. (c) CI ON THE FOLD's MERGE COMMIT: the tag block reads
    it itself and stops if it is not green. Then ONE tag and ONE deploy, v1.6.10 to v1.6.12, by the operator's blocks,
    clear of 17:25Z to 17:45Z and 19:20Z to 19:45Z (572 item 2) beside the standing windows. DEV 1: the Release Issue
    at the tag, as you say."
  - **Step 2, the fold (577 item 1 and 578 item 1, verbatim):** "1. DEV 1 — THE FOLD, #1171, IS READ WHOLE AT a152b22d
    AND IS MERGE-READY. (a) I ran the compile on main 6d511184 myself: the same tree, 5132fedc, and pending reads 0
    after it. The diff is BACKLOG.md, CHANGELOG.md and 65 deleted fragments, 32 and 33. (b) Every check of the head is
    a success; no review thread. (c) The release notes on the fold's commit, by my own run: exit 0, 499 lines, 32
    sections, no AMENDED line and no failing line. They agree with yours. (d) Its merge block is with the operator;
    the block writes the notes file for the tag." Then: "1. THE FOLD, by the agent's block, read by me: #1171 merged
    at a152b22d; main is 412003a7cb8d3e115ff11b316f0384978536f5b1, its tree 5132fedc, the fold's; pending fragments 0
    and 0. The notes file for the tag, written on that commit: exit 0, 499 lines, 32 sections, no AMENDED line, no
    failing line; its first line names the commit." #1171 merged 2026-11-27T17:07:32Z.
  - **The tag ruled (578 item 2, verbatim):** "2. THE TAG v1.6.12 IS RULED, on 412003a7, by the operator's block
    (docs/RELEASES.md; 577 item 2): the host's receipts hold 0 failing rows; the day's compare, 2026-11-26, is CLEAN;
    and the block reads CI on 412003a7 itself and cuts nothing until every check is a success. It carries the 32
    sections since v1.6.11, soccer-v23's record of REJECT among them."
  - **Step 3, the tag, read from git:** tag object `d86021de71bec0189b60efd82869f90f6fc67efd` on
    `412003a7cb8d3e115ff11b316f0384978536f5b1` (tree `5132fedc2dfe2ebc458f8350e15ff5f123aa467b`); tagger timestamp
    1795801267 -0500, which is 2026-11-27 12:41:07 -0500 (17:41:07Z), the tag's day 2026-11-27.
  - **The tag message:**
    - Stored (`git cat-file -p v1.6.12`): 499 lines and 97,657 bytes (its final newline included); 33 lines begin with
      `#` (the header and all 32 `## ` section headings). Its first line reads "# Release notes ·
      412003a7cb8d3e115ff11b316f0384978536f5b1 (412003a7) · since v1.6.11".
    - It is byte-identical to `python3 scripts/release_notes.py --to 412003a7cb8d3e115ff11b316f0384978536f5b1` (499
      lines, exit 0). `git for-each-ref --format='%(contents)'` prints one more newline, as on the earlier entries.
    - No AMENDED line and no `FAIL`. Its one `✗` is quoted inside #1128's section ("starting with neither ✓ nor ✗"),
      not a failing line.
  - **Step 5, the deploy.** The first attempt (579 item 1, verbatim): "1. THE FIRST DEPLOY ATTEMPT, 18:02Z, by the
    operator's block: STOPPED, nothing deployed, as built. The host is on v1.6.10, clean, 22 timers, no reboot
    pending; the dry run named v1.6.12. The receipts of the last 12 hours hold ONE failing row: the bulletin run of
    17:31Z, exit 2." The exception (579 item 3, verbatim): "3. THE DEPLOY GOES AHEAD ON ONE NAMED EXCEPTION, MINE TO
    NAME. The rule that a failing row stops a deploy stands. This row is explained, it is the same on both versions,
    and the deploy neither mends nor worsens it. The second block deploys only if every failing row of the last 12
    hours is a bulletin run that left with 2, and the host's own receipts name the pattern order_text and no other.
    Any other failing row stops it as before." The second block (580 item 1, verbatim): "1. THE DEPLOY, the operator's
    second block, 18:25Z, read whole by me. (a) BEFORE: the host on v1.6.10 at 67f02dfc, up 1 day 13 hours, no reboot
    pending. The receipts of the last 12 hours: 689 lines, one failing row, the 17:31Z bulletin run that left with 2;
    no failing row of any other kind; the host's own receipts name the pattern order_text and no other for it. That is
    579's named exception and nothing more. (b) THE DRY RUN named v1.6.10 to v1.6.12 (412003a7) and left with 0. (c)
    THE DEPLOY left with 0: v1.6.10 to v1.6.12, 127 files; HEAD is 412003a7cb8d3e115ff11b316f0384978536f5b1, the tag's
    commit; its receipt row is in the log at 18:25Z. No migration, no requirements change. The line on shipped timers
    reads as it did before: 3 on MLB_LAPTOP_ONLY and 2 on TIMERS_BY_BLOCK, held off. (d) AFTER: timers.enabled 22
    names, 22 active, none missing, none stray; the tennis timer disabled and the college basketball one not
    installed, as held; both availability timers active; no failed unit; the checkout clean. (e) ON THE CHECKOUT: the
    registry's soccer-v23 entry reads closed, REJECT, 14:05:22Z; the MLB sync hold line stands, one line naming MLB;
    the second wave's script and the book-gap receipt are present for the next block." And (580 item 2, verbatim): "2.
    v1.6.12 IS PRODUCTION FROM 18:25Z. v22 is the live soccer model; the v23 shadow is dormant by its recorded REJECT.
    The first pages it writes are today's 19:25Z closings; I read them." install.sh was not run (579 item 5 Q2: "A
    comment-only difference in a unit file's /etc copy needs no reinstall"); step 5 above stands as written.
  - **What changed for the host, read from git (`v1.6.10..v1.6.12`, the deploy's span: 320 commits, 127 files):**
    `src/db/schema.py`, every `migrate_*.py` (27 at each end), `requirements.txt` and both side requirements files are
    unchanged. One unit file differs, `deploy/hosting/systemd/sp-closing-watch.service`, in comment lines alone
    (#1117); the pack ships 27 timers and 12 services at v1.6.10, v1.6.11 and v1.6.12. Under `deploy/hosting/`:
    `laptop_routine.py` new (#1096, the laptop's command); `closing.py` (#1117, #1131, #1136), `pull_backup.py`
    (#1154, #1159, laptop), `sp_run.py` (#1119, #1123, #1150), `sp_receipts.py` (#1117), `sp_window_page.py` (#1104)
    and `compare_exports.py` (#1064) changed. No setting is added that the host's env file must carry (578 item 3).
  - **Carries:** git's `v1.6.11..v1.6.12` holds 159 commits and 93 files. Of its 46 merge commits, 33 are "Merge pull
    request #N" on main's first parent: the 32 PRs the notes carry, one CHANGELOG section each, and the fold PR #1171.
    The other 13: twelve merge main into PR branches (three times into #1119's, twice into #1123's, once each into
    #1117's, #1145's, #1148's, #1150's, #1157's, #1161's and #1162's), and d0dc8425 merges
    laptop/soccer-v23-run-record (9e959a3c) into #1170's. The 32: #1115, #1116, #1117, #1119, #1123, #1124, #1126,
    #1128, #1129, #1131, #1134, #1136, #1137, #1139, #1143, #1144, #1145, #1148, #1150, #1151, #1153, #1154, #1156,
    #1157, #1159, #1160, #1161, #1162, #1165, #1167, #1168, #1170. Not in the tag: none.
  - **Release Issue:** #1173 (ritual step 4), opened 2026-11-27 at the tag on ARCHITECT 2026-11-27 12:10 ET, addendum
    578 item 4 ("DEV 1 — the Release Issue at the tag, its figures read again from git"), on the milestone v1.6.12,
    labelled release, track:H, class:lane, sport:all and size:S. Its notes are in two comments (7224731828 and
    7224732799), read back equal to the tag message with the server's attribution footer after each. The deploy's
    console is its comment 7225633042, and addendum 580 is placed whole there (7225628713). On 580 item 3's ruling,
    quoted verbatim, "v1.6.12 is live on the host from 2026-11-27T18:25Z and carries every merge of v1.6.10 and
    v1.6.11 (ARCHITECT, addendum 580)", #1061 (v1.6.10) and #1138 (v1.6.11) are closed.

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
