# changelog.d — per-PR CHANGELOG fragments

ARCHITECT-RULE 2026-10-02: a PR never edits `CHANGELOG.md`. It adds
`changelog.d/<PR>-<slug>.md` holding **one** section in today's format:

```
## 2026-10-02 (#123: what shipped)
- ...
```

`<PR>` is the PR's own number: rename the file once the PR exists (CI checks
it). Its BACKLOG twin goes in `docs/ledger/entries/<YYYY-MM-DD>-<slug>.md`.
`python scripts/ledger.py compile --commit` folds every fragment into
`CHANGELOG.md` (newest first) in its own commit, during the tag ritual
(docs/RELEASES.md), and deletes them. Rules: docs/LEDGER.md.
