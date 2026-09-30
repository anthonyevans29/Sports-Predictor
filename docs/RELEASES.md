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
2. **Draft the release notes.** They are the CHANGELOG slice since the
   previous tag:
   ```
   python3 scripts/release_notes.py --to <sha>
   ```
   This is read-only. A section whose body changed since the previous tag
   is listed as AMENDED.
3. **The architect rules the tag.** Anthony cuts it and pushes it:
   ```
   git tag -a vX.Y.Z <sha> -m "<notes>"
   git push origin vX.Y.Z
   ```
   Claude Code never cuts or pushes a tag.
4. **The ledger records the release.** Open an Issue labelled `release`
   (plus track:H, class:lane, sport:all, size:S) on the per-release
   milestone `vX.Y.Z`. Paste the notes and the compare verdict into it.
5. **Deploy on the host:**
   ```
   sudo -u sp venv/bin/python deploy/hosting/sp_deploy.py
   ```
   The deploy receipt names the from and to releases and any new
   `migrate_*.py` files. Run those by hand, after a backup.

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
