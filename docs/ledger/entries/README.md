# docs/ledger/entries — per-PR BACKLOG fragments

ARCHITECT-RULE 2026-10-02: a PR never edits `BACKLOG.md`. It adds
`docs/ledger/entries/<YYYY-MM-DD>-<slug>.md` holding **one** entry in today's
format:

```
**2026-10-02 — The ruling or finding, in one line.**
- **Ruling (verbatim):** "..."
- ...
```

Its CHANGELOG twin goes in `changelog.d/<PR>-<slug>.md`.
`python scripts/ledger.py compile --commit` folds every entry into
`BACKLOG.md` right after the `### MLB / baseball` anchor (newest first), in its
own commit, and deletes them. Rules: docs/LEDGER.md.
