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
   **Account data never enters the repo (ARCHITECT 2026-11-03, addendum
   236 item 2(d)):** no raw Kalshi CSV row, no account id, no fill figure,
   in any file — receipts carry tickers, sides and timestamps at most.
   CI's tests/test_no_raw_kalshi_rows.py (#813) fails on a raw row or the
   CSV header row in any tracked .md, .txt or .json outside tests/fixtures/,
   and on a dollar amount under docs/receipts/ or docs/ledger/ (addendum 238).
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
- Python 3.10 is the floor (the laptop); no PEP 701 f-strings (a replacement field never spans lines or reuses the
  enclosing quote); CI parses on 3.10. (ARCHITECT 2026-11-07, addendum 280 item 2(c).)
