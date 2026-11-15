**2026-11-14 — #851: THE BULLETIN MIRROR'S TWO ROUND-TWO FINDINGS, FIXED FAIL-FIRST (ARCHITECT, addendum 381 item 3(v): "#851 with #881 if they touch the same module, else #851 alone").**
- **#851 alone:** #881 is in `src/walters/export.py`, a different module from `deploy/hosting/exports_mirror.py`.
- **R2-2:** a bulletin swapped after the plan for a symlink or a FIFO is skipped and receipted, never read through or blocked on.
- **R2-3:** a submodule is matched by its checkout folder's (st_dev, st_ino) as well as its text. So a case-folded family folder on the laptop's clone never swallows a bulletin silently.
- **Today:** neither had a trigger. Nothing writes `exports/bulletins/` before the renderer runs, and both need a hand-made oddity in the mirror's clone (277 item 1).
