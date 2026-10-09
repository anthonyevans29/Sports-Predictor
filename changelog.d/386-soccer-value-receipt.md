## 2026-10-09 (#386: soccer-value-receipt — the declared read-only receipt of value sides against the close)
- New READ-ONLY command `soccer-value-receipt [--out PATH]` (ARCHITECT 2026-10-09, addendum 21 item 6; Issue #383). Not gate evidence and not a policy; the operator runs it and the receipt goes to docs/receipts by PR.
  - Reads soccer-expansion-v1's 3,445 scored ids from the registry's ids file and re-prices them with the gate's own walk at the run record's rho / elo_goal_coeff, against fdcuk_close de-vigged as `market_side` does.
  - Value outcome = the largest model p minus close p. Tables: league (PD, SA, BL1, FL1, ELC, pooled) x edge bucket (under 5pp, 5-10, 10-15, 15+, 5+ as one row) x value outcome is the top pick; the 5+ row by kind (home, draw, away).
  - Columns: n, mean model p, mean close p, hit rate, hit - close pp and flat-stake return at the close's fair price, each with a seeded bootstrap 95% interval (seed 20261009, 10,000 resamples).
  - PL 2024/25 + 2025/26 on a page of their own (`<stem>-pl-reference.md`), for reference; PL's live read (#92) is not this.
- Refusals (exit 2, nothing written): no run record; ids file sha differs from the record; the re-walk does not reproduce the run (scored ids, n_priced, model log-loss, each league's +5pp cohort).
- The declared cohort check: each league's 5+ row must reproduce the run record's cohort (79/212, 88/225, 115/266, 93/205, 137/373). A miss is written as a COHORT CHECK FAILED banner with the decomposition, exit 3: a finding for a ruling.
- Writes nothing to the DB; never under data/. docs/CLI.md row; tests/test_soccer_value_receipt.py (synthetic leagues, throwaway DB, TMP registry).
