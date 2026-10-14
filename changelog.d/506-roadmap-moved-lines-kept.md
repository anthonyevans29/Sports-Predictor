## 2026-10-13 (#506: roadmap-moved-lines-kept — ARCHITECT addendum 62 items 3 (#504) and 4)
- src/roadmap.py: the base check keeps the record. Every moved line the base holds is on the head, word for word, and in the base's order; the head only appends. A line changed or removed, or out of the base's order, fails the PR, naming the lane and the line. A lane only one side holds needs nothing from this (#504).
- docs/roadmap.json: lane nfl-qb, step 1 (the quarterback data probe) done on 2026-10-13, receipt "PR #489 merged at 7e6e88c". No date moves; the print reads the operator's run, due 2026-10-23, as the lane's next step.
- docs/CLI.md, docs/LEDGER.md and CLAUDE.md say so. Tests: tests/test_roadmap.py 125 (9 new cases).
