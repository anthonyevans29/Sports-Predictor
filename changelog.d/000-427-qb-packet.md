## 2026-10-27 (#000: 427-qb-packet — the NFL quarterback term's design packet for the 11-02 ruling, and #627's receipt; read-only)
- docs/specs/nfl-qb-term.md (ARCHITECT 2026-10-23, addendum 162 item 3(a)): a PROPOSAL, not a declaration.
  - The measure: ANY/A per game (NY/A without sack yards where the line sends none), season-centred, with a prior-games estimate shrunk hard (k = 400 dropbacks, half-life 16 games, a replacement prior from first-100-dropback quarterbacks).
  - The term, relative to Elo: today's starter minus the quarterback level the team's rating was built on, so there is no double count.
  - Applied to the forecast only: v1's ratings and constants are unchanged, and β is the one fitted figure.
  - The identity rule: the previous game's most-attempts quarterback unless our injury read names him out, with #627's stamp problem named.
  - A proposed gate for the architect to freeze: 2024 fit, 2025 scored, −0.0050 vs v1, calibration, and the 2026 confirmation.
- scripts/nfl_qb_coverage.py: the coverage the packet asks for, per season and game type (games listed / finished / with passing lines for both teams; every field's presence; the roster join), read-only, every answer kept under logs/nfl_qb_payloads/ (never data/), resumable, --max-calls capped.
- scripts/nfl_injury_receipt.py (#627; addendum 162 item 3(c)): per NFL closing, the empty injury lists by cause (FEED / OUR READ / UNKNOWN from the closing receipt's empty answers), the join failures, the observation age; --live reads every team's injuries now (raw / taken / retained / unresolved, no position lookup). Opens no database.
- Tests: tests/test_nfl_qb_coverage.py, tests/test_nfl_injury_receipt.py (fake provider, throwaway files). No bar moves; nothing is fitted, run or scored.
