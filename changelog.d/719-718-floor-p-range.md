## 2026-10-27 (#719: 718-floor-p-range — the floor-blocked line reads a model_p only inside [0, pMin); #718)
- src/walters/exec_cohorts.py `floor_blocked`: a negative `model_p` (a malformed closing row) is never read into the floor-blocked line, beside the finite check of #717.
- Tests: tests/test_exec_cohorts.py (-0.1 out, 0.0 in). No bar moves; read-only line.
