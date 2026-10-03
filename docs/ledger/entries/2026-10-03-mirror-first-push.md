**2026-10-03 — Exports mirror first push (ARCHITECT): "not pushed — nothing changed" over an empty remote; keygen path for `sp`.**
- **Ruling (verbatim):** "exports_mirror.py push on the HOST (remote set via host.env, key installed, repo empty, 18 files in exports/) prints "not pushed — nothing changed" on first run, with and without --role host --exports … --label. The empty-remote / first-push case is misdetected (change test against an absent baseline?). Also: keygen writes to /etc/sports-predictor which sp can't write — accept a path or document the root step. Fix + a first-push regression; small PR."
- **Root cause:**
  - A truly fresh clone always stages the shipped tools and workflow, so "nothing changed" required an existing local commit.
  - With `SP_EXPORTS_MIRROR_REMOTE` set before the key worked, `sp_run.mirror_after_step` ran pushes after chain steps. Each committed in `logs/exports-mirror` and failed to push (non-fatal, receipted).
  - The change test (`git diff --cached --quiet`) compared against that local HEAD. On an empty remote with no tip to reset to, the hand run found nothing staged.
  - The regression reproduces this exactly: the second hook push already read "nothing changed" before the fix.
- **Fix:** staged changes OR local commits the remote lacks (all commits when the remote has no branch) trigger the push. `origin` is re-pointed to `host.env`'s remote.
- **Keygen:** a shared `key_path()` resolution (env, then an installed /etc key, then `~/.ssh/sp_exports_deploy_key`); `--key PATH`; an unwritable target refuses with both routes. The spec step is updated.
- **Operator:** after merge and deploy, run `push` once by hand. It should print `pushed … incl. N earlier unpushed commit(s)`.
