## 2026-10-06 (#0000: deploy-pip-install — ARCHITECT)
- `sp_deploy` runs `venv/bin/pip install -r requirements.txt` when `requirements.txt` changed in the deploy range. It uses the target tag's file, runs before the checkout, and is printed and receipted (`deploy_requirements`). A failed install refuses the deploy, and the host stays on its release.
