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

1. **The day's laptop-vs-host compare passes.** The parallel week's
   comparator, `deploy/hosting/compare_exports.py`, becomes the release
   gate. Paste its verdict.
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
5. **Deploy on the host:**
   ```
   sudo -u sp venv/bin/python deploy/hosting/sp_deploy.py
   ```
   The deploy receipt names the from and to releases and any new
   `migrate_*.py` files. Run those by hand, after a backup.
   A migration with no DB file at the configured path refuses ("no database
   at <path>; a migration never creates one — law 5"), exit 1, and writes
   nothing (addendum 112 item 1, #524).

## Release record
One line per tag, from v1.4.0 on. Each release's Issue carries its notes and
its compare verdict.

| Tag | Cut (UTC) | Commit | Tag object | Release Issue |
|---|---|---|---|---|
| `v1.4.0` | 2026-10-16 14:18:21Z | `684462e3d5078ff2c906db73362a220917bf1fcb` | `253bacd00327446936cdb16ea37a76deafc20ff1` | #556 |
| `v1.5.0` | 2026-10-22 13:24:24Z | `d15b9981edfa74379dd01089f7de23db51353d45` | `358777b00f6d39de1a92f97052f3756d9b89e5c1` | #647 |

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
- **v1.5.0** (the operator's tag, addendum 152 item 4(b) and addendum 153
  item 3). The commit is the #645 merge: the ledger compile ffe4097 (43
  changelog sections, 47 ledger entries) over 1552e8c.
  - The first tag cut with `--cleanup=verbatim`. Its message keeps the
    header and all 43 `## ` section headings (44 lines beginning with `#`).
    It matches `python3 scripts/release_notes.py --to
    d15b9981edfa74379dd01089f7de23db51353d45` line for line, plus one
    trailing blank line. No AMENDED line.
  - #647 carries the notes (in four parts); the compare verdict and the
    host's deploy receipt follow there.

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
