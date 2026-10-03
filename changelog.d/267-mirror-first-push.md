## 2026-10-03 (#267: exports mirror: the first push to an empty remote no longer reads "nothing changed"; keygen path)
- **`exports_mirror.py push`** judges "changed" against the REMOTE's tip, not the local HEAD.
  - On the host the remote was set in `host.env` before the deploy key worked, so the chain hook's pushes committed in the working clone and failed to push. The hand-run first push then compared against that local commit and printed "not pushed — nothing changed" over an empty remote.
  - Unpushed local commits are now pushed ("incl. N earlier unpushed commit(s)").
  - The clone's `origin` follows `host.env` if the remote changes.
- **Deploy key path:** `keygen` and `push` resolve the key the same way: `SP_EXPORTS_MIRROR_KEY`, else an installed `/etc/sports-predictor/exports_deploy_key`, else `~/.ssh/sp_exports_deploy_key` (writable by `sp`). `keygen --key PATH` is accepted. An unwritable target refuses and prints both routes (the `--key` route and the root step). `docs/specs/exports-mirror.md` step 2 is updated.
- tests/test_exports_mirror.py: first push after failed attempts (reproduced: "nothing changed" over an empty remote), first push of 18 files from a fresh clone, key resolution, keygen into a writable path, unwritable-dir refusal.
