## 2026-10-05 (#282: PR-body lint: closing keywords only on declared closure lines — LEDGER rule 5 enforced)
- New `pr-body` check (`python scripts/ledger.py check-body`, body via `PR_BODY`). It rejects a closing keyword + Issue ref (close/fix/resolve forms, `#N`, `owner/repo#N` or an Issue URL) anywhere except a declared closure line starting `Closes #N`. It re-runs on description edits.
- Why: #273, #274 and #275 used negated closing phrases, and GitHub closed #85, #211 and #276 on merge. Their descriptions now read "Outstanding work remains on #N".
- Tests: `tests/test_ledger_pr_body.py`. The original descriptions are rejected; the corrected ones and real closure lines are accepted.
