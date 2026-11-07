# Exports mirror (F2.5)

**Ruled** (ARCHITECT 2026-10-03, verbatim): "EXPORTS MIRROR lane (F2.5): (1) a private repo
Sports-Predictor-exports; the HOST pushes exports/ after every chain step (push-only deploy key,
generated on the host; Anthony adds the public half in the repo's deploy keys). Layout: host/
<date>/<file>, plus host/latest/<kind>.json (newest per kind, rewritten each push). Retention 14
days of dated folders; weekly history squash so the repo stays small. Files stay on the host
too. (2) The LAPTOP pushes the same way to laptop/ (writer of record) at the end of the morning
chain — then compare_exports runs as a GitHub Action on push and posts the DIVERGENT/clean
verdict as a commit status; pull_exports over Tailscale becomes optional. (3) Cockpit: a "Load
latest from host" control that fetches host/latest/* via the GitHub API with a fine-grained
read-only token the operator pastes once (stored in the browser, never in a file). Desk files
only (F1c). Receipt: tonight's 16:00 nhl-daily run visible in the repo within a minute."

## Pieces (all in this repo)

| Piece | Where | What |
|---|---|---|
| Mirror script | `deploy/hosting/exports_mirror.py` | `push --role host\|laptop` · `squash` · `keygen` |
| Host hook | `deploy/hosting/sp_run.py` `mirror_after_step` | after EVERY chain step; non-fatal, ≤ 90 s, receipted (`kind: mirror`); off until `SP_EXPORTS_MIRROR_REMOTE` is set |
| Weekly squash | `sp-exports-squash.timer` (Sun 06:10 UTC) | one orphan commit, force-pushed; a no-op until configured |
| Verdict Action | `deploy/exports-mirror/compare.yml` | shipped into the mirror by every push as `.github/workflows/compare.yml`, with `tools/compare_exports.py` |
| Cockpit control | `tools/cockpit.html` "Load latest from host" | GitHub contents API → `host/latest/*.json` → the normal load path (F1c refuses files without desk blocks) |

Layout in the mirror: `host/<YYYY-MM-DD>/<file>` and `laptop/<YYYY-MM-DD>/<file>`, with the date
taken from the file's UTC mtime. Only top-level `exports/*.json|*.md` are mirrored; subfolders
(raw provider caches) are not, except the one kept subtree, `exports/bulletins/` (below). `host/latest/<kind>.json` and `laptop/latest/<kind>.json` hold the
newest file per kind (the name with its date/time stamp removed) and are rewritten each push.
Dated folders older than 14 days are deleted (their tracked contents, by `git rm`; addendum 277 item 1, below).
`exports/` itself is never modified.

The kept subtree (ARCHITECT 2026-11-04, addendum 250 item 4, the bulletins lane, #826, verbatim): "exports_mirror.py
gains ONE kept subtree: `exports/bulletins/**` is copied verbatim to `<role>/bulletins/**` (suffixes .md and .png there;
the top-level rule is unchanged), NEVER pruned by RETENTION_DAYS (the dated-folder rule applies to `<role>/<date>/` only;
the weekly squash keeps files, as it does today), and NO JSON is ever written under it, so the compare's `*.json` Action
glob never sees a bulletin and the compare is untouched (no new kind, no new mask, kind_of unchanged)." As built
(`exports_mirror.bulletin_plan`): every regular `.md` and `.png` file under `exports/bulletins/` goes to
`<role>/bulletins/<the same relative path>` (`<FAMILY>/<date>/` and `<FAMILY>/weeks/` kept as they are), byte for byte,
whatever its mtime (no retention window), and is copied again when its bytes change. It is never pruned: the prune reads
only `<role>/<YYYY-MM-DD>/` folders, so neither `<role>/bulletins/` nor a dated folder nested in it is ever deleted. A
bulletin removed from `exports/` stays in the mirror, as a dated copy whose source is gone stays until its folder expires
(the push copies; it never deletes a copy for a missing source). Never copied, and receipted (the push's result carries
`skipped`, path and reason, and its console line `bulletins: N skipped (<reason> <count> · …)`, the line the chain hooks'
mirror receipts keep): any other suffix (a `.json` above all, so no JSON is ever written under the subtree; an upper-case
`.PNG` too), a symlink anywhere (file or folder, the subtree's own root included: never followed, in or out of the
subtree), anything that is not a regular file, a `.git` path component (git cannot carry it), a folder that cannot be
read, a file the push cannot read when it copies it (no read permission, or gone since the plan: `unreadable: <error>`),
and a path git itself refuses (`git refused the path`; git decides, by `add --force --ignore-errors` over the bulletins the push
carries, not a list kept in the mirror: under core.protectNTFS, git's default, `.git`'s other spellings `GIT~1`, `.git.`, `.git `).
The destination is never followed either (Codex on #847): the mirror's own tree may already track a symlink, so before a
bulletin is read back or written, every component from `<role>/` down to the file is `lstat`'ed, and a bulletin is
skipped, receipted, when the path there holds a symlink (the role folder, `bulletins/`, a family or date folder, or the
file itself, a relative escape or an absolute link: `destination path has a symlink`), a component above the file that
is not a folder (`destination path has a non-folder`), or a file that is not a regular file (`destination not a regular
file`); what the mirror tracks there is left as it is (never unlinked, never written through), missing folders are made
only below real ones, and git's own check never walks a `<role>/` or `<role>/bulletins/` that is not a real folder. A
component the index holds as a submodule (a gitlink: git checks one out as an empty real folder, so an lstat never sees
it) is refused the same way (`destination path has a submodule`), git's own check never takes a `<role>/` or
`<role>/bulletins/` submodule as its pathspec (git's add exits 128 there), and it removes only the folders a refused
file's unlink emptied.
One bad bulletin is local to that file: a copy git refused is removed from the working clone (it is the push's own
planned copy), so it never jams a later push, and the top-level files and the other bulletins still go. No `exports/bulletins/`:
nothing happens. The compare is untouched: the Action picks the newest
`YYYY-MM-DD` folder both writers hold (`bulletins/` never matches), and the `*.json` glob finds nothing under
`<role>/bulletins/`. The renderer's own writer refusing a `.json` under the subtree comes with the renderer (step 1's
second PR).

What a push publishes (ARCHITECT 2026-11-06, addendum 277 item 1, R2-1 on #847, verbatim): "the mirror publishes ONLY
the paths its plan copied. The whole-tree `add -A` is main's mechanism, and it means any stray file in the clone — a
leftover of a killed run, a file another writer dropped there — goes to the mirror unplanned; the mirror is private, and
the Desk's privacy rules still say nothing leaves a machine that was not planned to. The fix is the add limited to
planned paths (never `git clean -fd`: the mirror deletes nothing it did not plan either); a leftover from a killed run is
then never published and the next run's receipt names it as untracked-and-skipped." As built: no whole-tree add. The
push stages, by name (the list goes to git on stdin, NUL-separated, as literal pathspecs), exactly the dated and latest
copies of the top-level plan, the bulletins it carried (minus the skipped and the refused),
`tools/compare_exports.py` and `.github/workflows/compare.yml`, with `git add --force`: the list is the plan, so no
ignore rule (a stray untracked `.gitignore`, or a `.git/info/exclude` entry) vetoes a planned path or makes the add
abort the push (core.protectNTFS still refuses a path; review of the fix). Its planned deletions go through `git rm` on tracked
paths only: the latest cleanup (a tracked `<role>/latest/` file no planned kind holds) and the prune (the tracked
contents of an expired `<role>/<YYYY-MM-DD>/` folder; `pruned` names the folders that held any). A planned path beyond a
symlink or inside a submodule is never staged (git refuses that pathspec, and the whole-tree add never carried it
either); the top-level rule never writes one (#852, below). Any other untracked file in the
working clone (a killed run's leftover whose source is gone, a file another writer dropped there: under `<role>/bulletins/`,
`<role>/`, `<role>/latest/`, an expired folder or the clone root) is not staged, so it never reaches the remote; it is
never deleted (no clean, no unlink); and every push names it, `untracked_skipped` (clone-relative paths) on the result
and `· untracked-and-skipped N (<first five paths>[, +K more])` on the console line, until the operator removes it. A
tracked file the plan does not write, edited in the clone by another writer between the sync and the add, is not staged
either (the remote keeps its tracked bytes); it is not untracked, so it is not on the receipt, and the next sync's
`reset --hard` puts the tracked bytes back, as on main. The weekly squash commits the index as the sync left it (the remote tip's tree), never a whole-tree add, and names the same
files on its result.

The top-level rule's destination (#852; ARCHITECT 2026-11-06, addendum 277 item 1, verbatim): "THE PRE-EXISTING HOLE
(main's top-level rule follows a tracked symlink out of the clone: the latest cleanup can unlink files OUTSIDE the clone,
the dated copy can write outside it, the prune can abort every push; a tracked submodule at <role> silently swallows the
day's files): NOT in #847, as Code says. RULED: a limitation Issue now (class the ledger's; the probe output quoted as
its receipt), and its OWN PR in the next free code slot — the review's fix as proposed (lstat every component as
_dest_refusal does; refuse a symlinked or submodule <role>, <role>/latest, <role>/<date>; receipt the skip; follow
nothing, unlink nothing through a link)." As built, by `_dest_refusal` itself (the bulletins' rule, not a copy of it):
every planned dated and latest copy's path is `lstat`'ed from `<role>/` down before it is read back or written, and a
symlink there (`<role>`, `<role>/latest`, `<role>/<date>` or the file itself, a relative escape or an absolute link:
`destination path has a symlink`), a component that is not a folder, a file that is not a regular file, or a component
the index holds as a submodule (`destination path has a submodule`) skips that copy: never written through, never
written into the submodule's folder, never staged. The latest cleanup never reads a `<role>/` or `<role>/latest/` that is
not a real folder and never removes a gitlink (a stale submodule entry there is skipped). The prune picks each expired
`<role>/<YYYY-MM-DD>` by its name, then `lstat`, never a stat through it, and `lstat`'s it again
(`_dest_refusal(..., folder=True)`): a symlinked one (whatever its target: a folder, a file, nothing, one whose stat
raises) or a submodule one is skipped, never followed, never unlinked, never removed, and the push goes on; inside a
real expired folder a submodule entry is skipped and the rest of its tracked contents go. Every skip is receipted:
`top_level_skipped` (role-relative path, reason) on the result and `· top-level: N skipped (<reason> <count> · …)` on
the console line, on every push it remains (the bulletins' own `skipped` is unchanged); the tracked link or submodule is
left as the mirror holds it, and the rest of the push (the other copies, the other expired folders, the bulletins, the
tools) proceeds.

The tools copy's destination (#858; ARCHITECT addendum 282 item 3, verbatim): "the tools copy (tools/compare_exports.py
and the workflow file written through a tracked link) is the same defect in the same module and is BUILT in #858 by the
same rule — each tool path through _dest_refusal, skipped and receipted, never written through". As built: each of
`tools/compare_exports.py` and `.github/workflows/compare.yml` is `lstat`'ed by `_dest_refusal` from the clone root down
before it is read back or written; a symlink at `tools/`, `.github/`, `.github/workflows/` or the file itself (a relative
escape or an absolute link: `destination path has a symlink`), a submodule the index holds there (`destination path has
a submodule`), a component that is not a folder or a file that is not a regular file skips that tool: never written
through, never written into the submodule's folder, never staged. Every skip is receipted: `tools_skipped`
(clone-relative path, reason) on the result and `· tools: N skipped (<reason> <count> · …)` on the console line, on
every push it remains; the tracked entry is left as the mirror holds it, and the other tool, the top-level copies and
the bulletins still go.

The Action compares the newest date that BOTH writers have pushed and posts commit status
`compare_exports`: success = clean, failure = DIVERGENT, pending = one side has not pushed that
date yet. The full report is in the run's step summary.

Machine state (#592 RULED, ARCHITECT 2026-10-18, addendum 128 item 3): "the compare treats kind `coverage` as "machine state": listed by presence on each side (one side, both sides, neither), never compared for content, never DIVERGENT, never counted toward or against criterion (a). Printed as its own line ("machine-state files: coverage laptop yes / host no")." The day's coverage
file travels as every kind does, dated and latest (`<role>/<date>/coverage_<date>.json` and
`<role>/latest/coverage.json`; option 3, the latest copy only, was declined: "the dated file is the day's
record"), and the compare never opens either copy. The Action compares the dated folders only, so it lists
the dated copy on that one line, never a verdict; the latest copy is the same kind and is listed the same way
when latest/ folders are compared by hand. The host's writer is the last step of `intl-daily`
(`coverage --json`, daily 07:20 UTC; #805, ARCHITECT 2026-11-03, addendum 225 item 5); before it deployed,
host/latest/coverage.json was the laptop's file of 2026-10-23. The Action runs the comparator the last push shipped (each push
copies its own machine's `compare_exports.py` into `tools/`), so the rule holds there only once both writers
run code that carries it.

## Operator setup (once)

1. **GitHub (Anthony):** create the PRIVATE repo `anthonyevans29/Sports-Predictor-exports`, empty.
2. **Host:** `sp` cannot write `/etc/sports-predictor`, so use one of these two:
   - **as sp (no root):** `sudo -u sp /opt/sports-predictor/venv/bin/python deploy/hosting/exports_mirror.py keygen`
     writes `~sp/.ssh/sp_exports_deploy_key` and prints the PUBLIC half. With `SP_EXPORTS_MIRROR_KEY` unset,
     the mirror falls back to that path. `--key PATH` puts it elsewhere; then set `SP_EXPORTS_MIRROR_KEY=PATH`
     in `host.env`.
   - **root step (key under /etc):**
     `sudo ssh-keygen -q -t ed25519 -N '' -C 'sp-exports-mirror (push-only)' -f /etc/sports-predictor/exports_deploy_key`
     then `sudo chown sp:sp /etc/sports-predictor/exports_deploy_key* && sudo chmod 600 /etc/sports-predictor/exports_deploy_key`.
     An installed `/etc` key is used when present.

   `keygen` aimed at an unwritable directory refuses and prints both routes.
3. **GitHub (Anthony):** repo → Settings → Deploy keys → add that public half with **write access**.
   It is a deploy key, so it reaches this repo only.
4. **Host `host.env`:**
   ```
   SP_EXPORTS_MIRROR_REMOTE=git@github.com:anthonyevans29/Sports-Predictor-exports.git
   SP_EXPORTS_MIRROR_ROLE=host
   ```
   Then, unless T11 already enabled and listed it (it is on the T11 list; a host that predates the list line
   does not hold it in `/etc/sports-predictor/timers.enabled`), the recipe ends with the timers.enabled line
   (ARCHITECT 2026-10-26, addendum 168 item 2):
   ```
   sudo systemctl enable --now sp-exports-squash.timer
   echo sp-exports-squash.timer | sudo tee -a /etc/sports-predictor/timers.enabled
   ```
   Setting the remote BEFORE the key works is harmless. The chain hook's pushes commit in the working
   clone and fail to push; the first push that can reach the remote sends those commits too
   ("incl. N earlier unpushed commit(s)"). The change test is against the remote's tip, never the local HEAD.
5. **Laptop:** its own deploy key the same way. `exports_mirror.py keygen` writes the DEFAULT
   `~/.ssh/sp_exports_deploy_key` (the laptop's key is at that default name; corrected by ARCHITECT
   2026-10-07, addendum 4 F). Add it with write access, then put the settings in the checkout's `.env`
   (read through `sp_common.setting`; the process environment wins):
   ```
   SP_EXPORTS_MIRROR_REMOTE=git@github.com:anthonyevans29/Sports-Predictor-exports.git
   SP_EXPORTS_MIRROR_ROLE=laptop
   # SP_EXPORTS_MIRROR_KEY only if the key is NOT at ~/.ssh/sp_exports_deploy_key
   ```
   and at the END of the morning chain:
   ```
   python deploy/hosting/exports_mirror.py push --role laptop --label morning
   ```
   An SSH remote whose key file does not exist is REFUSED with the path named (exit 2), never pushed
   keyless. An HTTPS remote does not use the key.
6. **Cockpit:** create a fine-grained token: repository access = only Sports-Predictor-exports,
   permission = Contents: Read-only. Paste it once into the Cockpit's mirror field. It is kept in
   that browser's localStorage, never in a file.

**Receipt (ruled):** after the deploy, tonight's 16:00 `nhl-daily` steps show as commits
`host: nhl-daily step N …` in the mirror within a minute, and the step receipts carry `kind: mirror, exit 0`.

**Published artifact: the CSP blocks api.github.com (confirmed by the architect, 2026-10-04).** In the
published Cockpit, "Load latest from host" fails ("Fetch failed"); the file picker still works there.
To use the control, run the Cockpit locally:

```
python scripts/cockpit_local.py --html ~/Downloads/cockpit.html   # a saved copy of the published artifact
```

It serves the page on `http://127.0.0.1:8765` (127.0.0.1 only, read-only), where the GitHub contents API is
reachable. Without `--html` it serves the repo copy `tools/cockpit.html`, which may lag the published one, and
says so.

**The ledger is per origin.** The local page has its own localStorage, so its own ledger and token. Move the
ledger with "Export ledger (JSON)" → "Import ledger", and keep the same `--port` so the local origin stays the
same between runs.
