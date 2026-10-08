## 2026-10-08 (#PENDING: ncaa-elo-v1r gate design receipt; seeded simulation, no stored game)
- Adds `scripts/ncaa_v1r_design_receipt.py`, a seeded simulation of the ncaa-elo-v1r gate design (ARCHITECT addendum 11, item 3, PR A step (a)). It reads no stored game and opens no database.
- It uses the repo's NCAAEloV1 with its constants untouched (D1) and #79's band rule as coded (`ncaa_backtest.run_gate`, `crit_bands`). A thin wrapper prices and updates neutral games with home advantage 0.
- Receipt: `docs/receipts/ncaa-v1r-design-2026-10-08.md`. Settings (110,140) / (150,170) / (190,210): mean slope 1.000 / 1.158 / 1.337, band rule 26.5% / 32.0% / 27.5%, D5 (2)&(3) 87.5% / 65.0% / 14.5%. 675 scored games per season. Stop condition: OK.
- Adds `tests/test_ncaa_v1r_design_receipt.py`: a tiny run is deterministic and imports no DB module; the neutral wrapper restores the constant; the slope fit recovers b = 1 on calibrated data.
- No registry entry, spec or other PR A content: that waits on the architect's check.
