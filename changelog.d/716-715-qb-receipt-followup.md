## 2026-10-27 (#716: 715-qb-receipt-followup — the coverage receipt's field absence and gate read the passing data only; a malformed row is counted, never a traceback; #715)
- scripts/nfl_qb_coverage.py:
  - Item 1: only the games-list and statistics reads, a parse-dropped finished game or a malformed row make a season's field absence UNKNOWN or its gate line INCOMPLETE. A failed or capped roster read is listed and leaves the roster join partial, never the field line or the gate.
  - Item 2: a listed row not in the provider's shape (not an object, or a game, teams or home / away member that is not one) is counted under "(not the provider's row shape)", named, and makes the gate INCOMPLETE and an absence UNKNOWN. Before, it stopped the run with a traceback.
- docs/specs/nfl-qb-term.md section 7 says the same.
- Tests: tests/test_nfl_qb_coverage.py. No bar moves; read-only receipt.
