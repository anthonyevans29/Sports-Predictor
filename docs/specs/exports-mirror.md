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
(raw provider caches) are not. `host/latest/<kind>.json` and `laptop/latest/<kind>.json` hold the
newest file per kind (the name with its date/time stamp removed) and are rewritten each push.
Dated folders older than 14 days are deleted. `exports/` itself is never modified.

The Action compares the newest date that BOTH writers have pushed and posts commit status
`compare_exports`: success = clean, failure = DIVERGENT, pending = one side has not pushed that
date yet. The full report is in the run's step summary.

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
   Then `systemctl enable --now sp-exports-squash.timer` (it is on the T11 list).
   Setting the remote BEFORE the key works is harmless. The chain hook's pushes commit in the working
   clone and fail to push; the first push that can reach the remote sends those commits too
   ("incl. N earlier unpushed commit(s)"). The change test is against the remote's tip, never the local HEAD.
5. **Laptop:** its own deploy key the same way (`keygen --key ~/.ssh/sp_exports_laptop`, add it with
   write access), then at the END of the morning chain:
   ```
   SP_EXPORTS_MIRROR_REMOTE=git@github.com:anthonyevans29/Sports-Predictor-exports.git \
   SP_EXPORTS_MIRROR_KEY=~/.ssh/sp_exports_laptop python deploy/hosting/exports_mirror.py push --role laptop --label morning
   ```
6. **Cockpit:** create a fine-grained token: repository access = only Sports-Predictor-exports,
   permission = Contents: Read-only. Paste it once into the Cockpit's mirror field. It is kept in
   that browser's localStorage, never in a file.

**Receipt (ruled):** after the deploy, tonight's 16:00 `nhl-daily` steps show as commits
`host: nhl-daily step N …` in the mirror within a minute, and the step receipts carry `kind: mirror, exit 0`.

**Note:** the Cockpit is a published artifact. If its sandbox blocks requests to api.github.com,
the control reports "Fetch failed" and the file picker still works. The republish will show it.
