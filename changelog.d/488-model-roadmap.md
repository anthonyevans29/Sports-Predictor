## 2026-10-13 (#488: model-roadmap — ARCHITECT addendum 59 items 5 and 6; Issue #486)
- docs/roadmap.json: the model roadmap, the first content of addendum 59 item 5(g) word for word. There are seven lanes: unl #220, pd #322, ncaa #79, leagues #322, nhl #105, cups #106 and nfl-qb #427. Each lane carries its state, its dated steps (owner architect, operator, code or calendar; `done` null or `{date, receipt}`), earliest_live, live_needs, vs_close, and a `moved` list (`{moved_on, which, was, now, why, ruling}`). The file is tracked and never under data/, and it changes only in a PR that quotes the ruling for the change.
- src/roadmap.py + `python cli.py roadmap [--today YYYY-MM-DD]`: read-only, with no database and no network.
  - Per lane, in the file's order: title, Issue, state, earliest live and the record against the close, then its next step with `in N days`, `today` or `OVERDUE N days`.
  - Then the ledger milestones that have a due_on, and a last line `overdue: N`.
  - It exits 0 whatever is overdue. A file that does not validate exits 2 and names the entry.
  - The ruled validation runs in code and as a test on the real file.
- CLAUDE.md, Queue section: the model lanes come first; the dates live in docs/roadmap.json and `python cli.py roadmap` prints them; no date moves a bar (5(c), quoted). docs/CLI.md: the `roadmap` row.
- .github/ledger/taxonomy.json (item 6): "Cutover ~Oct 8" due_on 2026-10-08 -> 2026-10-30; "Executable-edge ruling (2 wks of ladders)" 2026-10-13 -> 2026-10-20. The operator changes the same two on GitHub by hand.
- Tests: tests/test_roadmap.py (35).
