## 2026-10-02 (#220: intl-elo-v2 declared — train-only fit + neutral rule v3)
- `docs/specs/intl-elo-v2.md` + registry `intl-elo-v2`: (a) c multiplier and global K multiplier fitted on the training stream only (48-pair declared grid); (b) neutral v3 (venue country ≠ home country). Same bar/bands/test set; train-only attribution printed.
- `python cli.py intl-venue-sync` (route B; new table `intl_match_venue`) and `intl-elo-backtest --candidate v2`. tests/test_intl_elo_v2.py (5). intl-elo-v1 FAIL is recorded once its laptop run record is spliced.
