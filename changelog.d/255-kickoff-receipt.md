## 2026-10-02 (#255, refs #254: NCAA kickoff +24h finding — read-only receipt script)
- `scripts/kickoff_receipt.py` (read-only), for each match:
  - the STORED row: utc_date, status, external ids;
  - the PROVIDER's raw date block and timestamp (`/games?id=`, one GET; `--no-provider` skips it);
  - every EXPORT carrying the match: as_of, row utc, the Desk's reason, and the in-play test recomputed on that file's own inputs.
- tests/test_kickoff_receipt.py (1). No pipeline change until the receipt says which side is wrong.
