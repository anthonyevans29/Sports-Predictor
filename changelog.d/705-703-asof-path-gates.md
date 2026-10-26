## 2026-10-26 (#705: 703-asof-path-gates — the as-of pitcher receipt's live path stands only on a pregame identity and complete ERAs)
- scripts/mlb_pitcher_asof_receipt.py, the P line (#703, #702's round-2 Codex P2s; ARCHITECT 2026-10-26 17:00 ET: "#703's fixes before the receipt's first run"):
  - A listed identity refreshed after the kickoff, or with no time, is counted as "identity not established pregame", never as a path.
  - A starter or bullpen component whose ERA is incomplete (an earned_runs NULL in the season, or in a recent window of 10 IP or more) is counted as "not reconstructable", never as a blend or a fallback.
  - The summary adds "the live path reconstructed (identity by kickoff, ERAs complete) x/y".
- Tests: tests/test_mlb_pitcher_asof_receipt.py (a post-kickoff identity; a prior earned_runs NULL under a pregame starter). No bar moves; the run is the operator's, after the #569 dedupe.
