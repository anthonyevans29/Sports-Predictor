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
   and the host deploys a git tag (docs/RELEASES.md). Backups are
   `.backup`-API only, daily, plus before any refresh.
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
- **A change to the stored schema ships with a NEW migration file in the same PR** (ARCHITECT 2026-11-12 10:55 ET,
  addendum 354 item 2(a), #950, verbatim): "FROM NOW ON a change to the stored schema ships with a NEW one-shot
  `migrate_<what>.py` in the same PR — it may do no more than call the idempotent migration that applies the change
  — because the plan already lists, orders and prints new migration files, and a rule the deploy can see is worth
  more than a rule a person must remember." The stored schema is a table, a column, an index or a trigger in
  `src/db/schema.py`.
  - **Make the file's content its own.** Name the PR and the change in its docstring. `sp_deploy` treats a new file
    whose content equals an existing migration's as a copy that already ran, and never runs it. It treats two
    identical new files in one range as undetermined.
  - **What the deploy says when the rule is missed:** on a forward deploy where `src/db/schema.py` changed and the
    plan lists no new migration, the dry run and the deploy print one `!` line, with no command (354 item 2(b)).
    The plan cannot know which migration covers the change, so the PRs are read before the DB is used.
  - **CI refuses a PR that misses it** (ARCHITECT 2026-11-12 14:25 ET, addendum 358 item 2, scope B: "a NEW TABLE
    ships with its migrate file too"): `scripts/schema_ddl_check.py` compiles `src/db/schema.py` at the PR's base and
    head into an in-memory SQLite and compares every table, index and trigger (whitespace collapsed, `VARCHAR(n)`
    lengths dropped). An object changed or added, on an existing table or a new one, with no new top-level
    `migrate_*.py` in the PR, refuses. A comment-only edit, or a change SQLite compiles the same, never trips it. An
    object removed from the metadata is printed as information (the live DB keeps it). The base is compiled at the
    merge base, so a PR behind its base is not asked for the base's own later changes. "New" is read as the deploy's
    plan reads it: a byte copy of a migration already on the base, a renamed migration, two new files with the same
    content, and every new file when any migration is deleted anywhere in the PR's history (lineage unknown) do not
    count, since the plan runs none of them. Editing an existing migration does not count either. Run it locally with
    `python scripts/schema_ddl_check.py --base origin/main`: the working tree is compiled, and its uncommitted
    migration files (staged, unstaged or untracked) count.
  - **Its stated limits** (358 item 2): it sees only what `Base.metadata` compiles, so **DDL outside
    `Base.metadata`** (raw SQL in a migration or anywhere else) is not seen; and **a data change that needs a backfill
    with no DDL change** is not seen. Both stay the author's to name in the PR, with the deploy's `!` line behind them.
    Every table is declared in `src/db/schema.py` (a test pins it), since the check compiles only what that module
    registers; a difference only in whitespace or a `VARCHAR(n)` inside a SQL string literal is normalised away.
