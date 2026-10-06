**2026-10-06 — sp_deploy installs requirements when requirements.txt changed in the deploy range (ARCHITECT).**
- **Ruling (verbatim):** "(1) sp_deploy must install requirements when requirements.txt changed in the deploy range (print and run `venv/bin/pip install -r requirements.txt`, receipted) — the host lacked `cryptography` after v1.2.3."
- **Built:** when `requirements.txt` is in the range's diff, the deploy prints and runs `venv/bin/pip install -r requirements.txt`. It falls back to the running interpreter's `-m pip` when there is no venv.
  - It installs the TARGET tag's file, read with `git show`, BEFORE the checkout moves.
  - A `deploy_requirements` receipt records the exit and the command. The `deploy` receipt carries `requirements_installed`.
  - A failed install refuses the deploy (receipted, exit 1), and the host stays on its release, never on new code without its dependencies.
  - The dry run names the install it would run.
- **Receipts:** `test_deploy_installs_requirements_when_they_changed` covers four cases: an unchanged range (no install), a dry run (named only), a failed install (refused, HEAD unchanged) and a successful one (the target's file, before the checkout, receipted). The test fails on main. `pytest`: 823 passed, 1 skipped.
