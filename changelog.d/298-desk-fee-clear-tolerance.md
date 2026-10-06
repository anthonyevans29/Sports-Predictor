## 2026-10-06 (#298: Desk fee-clear marker — an exact 4.00pp edge clears — ARCHITECT)
- `desk_policy.exec_block`'s `fee_clears` and the Cockpit's "fee-clears?" marker compare with a 1e-9 tolerance (`FEE_CLEAR_EPS`). Before, (0.35 − 0.31)·100 = 3.9999999999999982 read as a miss. Same tolerance as `k-track-receipt`.
- Golden: no edge within 1e-6 of 4pp in `tests/golden/desk_js_v1_1.json.gz`; unchanged, still 15/15. Test: `tests/test_desk_fee_clear_boundary.py`.
