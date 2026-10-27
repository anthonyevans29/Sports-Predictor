## 2026-10-27 (#713: 712-qb-receipt-fixes — the QB receipts' field line, dropped finished games and failed live reads, before the receipts run; #712 items 1-3)
- scripts/nfl_qb_coverage.py:
  - Item 1: each season's F line lists every passing field any season of the run sends. A field missing for a whole season reads "on 0, ABSENT"; it used to be left off. A header line names the field universe.
  - Item 2: a listed row the provider marks finished (a short the adapter maps to FINISHED, or no status claim with both totals) but the adapter's parse drops is named under FINISHED BUT DROPPED and makes the season's gate line INCOMPLETE. An all-star exhibition is the adapter's own exclusion, counted on its own line and not in the gate.
- scripts/nfl_injury_receipt.py `--live`: a read counts as answered only when it is HTTP 200 with no errors (item 3). A non-200 answer with an empty errors object is FAILED, never an empty roster or list, and a failed read's rows are never measured (Codex on #713); a failed /teams read reads no team.
- docs/specs/nfl-qb-term.md section 7 says the same. Items 4 and 5 stay on #712 for the 11-02 declaration.
- Tests: tests/test_nfl_qb_coverage.py, tests/test_nfl_injury_receipt.py. No bar moves; read-only receipts, no model or export change.
