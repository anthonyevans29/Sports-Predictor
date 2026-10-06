## 2026-10-06 (#299: fill matcher — doubleheaders by the ticker's start time; three-way NO is composite — ARCHITECT)
- The Cockpit's fill matcher and its Python port (`src/walters/ledger_fills.py`) change together, with parity preserved (`scripts/ledger_fills_parity_verify.py` 30/30).
- **Doubleheaders:** the event ticker's HHMM is the scheduled start in US Eastern time (`KalshiAdapter.ticker_start`, M13; DST via Intl / zoneinfo). Among a fill's candidate calls, those within 3h of it count, nearest first. Without a time the old order stands, and an ambiguous attribution stays flagged. The Cockpit re-parses each stored ticker, so earlier imports gain the start time.
- **Three-way NO:** a NO on an EPL/UCL/FA Cup/UEFA NL HOME or AWAY leg is two outcomes, COMPOSITE. It is never matched to a single-side straight: with a candidate call it is booked off-book ("composite contract — never a straight"); a UNL single with no call stays in the fun book (ruled 2026-09-30). Its held contract stays known for the closing fair. A two-way NO still means the opposite team.
- Tests: `tests/test_fill_matcher_lane.py`; `k-track-receipt` lists composite fills.
- Review fixes (Codex on #299):
  - When the ticker carries team codes, they decide which game a fill fits. One shared title word ("United", "City") no longer stands for team identity.
  - The receipt's unpriced-position count is scoped to the window.
