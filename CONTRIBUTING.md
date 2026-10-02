# Contributing

This project runs on laws earned from incidents. They are not optional.

## The laws
1. **Read before edit.** A regex or memory match is a hypothesis, not a
   read. Anchors, column names, and status vocabularies come from the
   actual file, schema, or provider payload — enumerated, never guessed.
2. **Receipts over claims.** Every sync prints counts; every model change
   faces a gate; every claim of "fixed" or "fast" is backed by a pasted
   console. Speed without receipts triggers a sanity audit.
3. **Gates decide, humans ratify.** Models promote only through frozen,
   pre-committed acceptance criteria (log-loss + calibration bands +
   spread/drift guards). Acceptance is written BEFORE results exist.
4. **Conservative unknowns.** Unmapped statuses stay SCHEDULED; missing
   data stays null and labeled; nothing is faked to look complete.
5. **The database never travels.** Packaging excludes `data/` and `.git`,
   verified per tarball. Backups are `.backup`-API only, daily, plus
   before any refresh.
6. **Track by artifact.** BACKLOG.md is the decision record; CHANGELOG.md
   the change record; incident entries name root cause and the law that
   changed. Findings without a log entry didn't happen. Every known
   limitation, finding and queued lane is also an Issue: Issues are the
   STATE ledger, BACKLOG.md the history, the Project board the order
   (docs/LEDGER.md).
   **Per-PR fragments (ARCHITECT-RULE 2026-10-02):** a PR never edits
   CHANGELOG.md or BACKLOG.md. It adds `changelog.d/<PR>-<slug>.md` (one
   `## YYYY-MM-DD (...)` section) and `docs/ledger/entries/<date>-<slug>.md`
   (one `**YYYY-MM-DD — ...**` entry); `python scripts/ledger.py compile
   --commit` folds them in date order in its own commit (the tag ritual,
   docs/RELEASES.md). CI fails a PR that edits the shared files or lacks a
   fragment.

## Workflow
- Daily/operational changes: direct commits to `main` with descriptive
  messages carrying receipts.
- **Gate-class changes** (model logic, training, acceptance criteria,
  export contracts): branch + pull request using the template — the PR
  carries the backtest verdicts and gate output before merge.
- CI must pass (parse + import smoke) on every push.
