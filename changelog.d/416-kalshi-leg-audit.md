## 2026-10-11 (#416: kalshi-leg-audit — ARCHITECT addendum 37 items 1 and 4; Refs #413)
- `scripts/kalshi_leg_audit.py` (new, read-only): by series and capture day, the games whose ticketed legs name two events and the events whose legs sit on two games (match id, teams, kickoff, tickers, capture times); totals, first day per series, listed games with a graded prediction, and the count of untickered captures. For the operator's runs on both machines; consoles on #413.
- Ledger: the addendum 37 item 1 FINDING (BACKLOG entry for #413).
- docs/CLI.md: its row. Tests: tests/test_kalshi_leg_audit.py (a throwaway SQLite file).
