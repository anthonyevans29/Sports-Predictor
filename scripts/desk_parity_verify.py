"""
F1 / F1c ROW-FOR-ROW PARITY VERIFY (#151, #191).

Before F1c this drove the Cockpit's in-browser Desk and the Python port side
by side. F1c (ARCHITECT-RULE 2026-10-01) DELETED the in-browser policy:
"Keep the headless parity harness as a regression test against the deleted
JS's last known outputs." So this now checks the Python Desk
(src/walters/desk_policy.py) against the frozen JS outputs in
tests/golden/desk_js_v1_1.json.gz — the seeded battery (clock and counts
pinned), the 600-slate parlay fuzz and the toFixed sample — row for row,
every field, floats exact. No browser. tests/test_desk_golden.py runs the
same check in CI.

    python3 scripts/desk_parity_verify.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desk_battery as b  # noqa: E402


def main():
    g = b.load_golden()
    print(f"PARITY vs the frozen pre-F1c JS Desk · now {g['now']} · browser tz {g['browser_tz']} · "
          f"cockpit sha256 {g['cockpit_sha256'][:12]}…")
    res = b.check_against_golden(g)
    for label, n, bad in res:
        print(f"  {'PASS' if not bad and n else 'FAIL'}  {label}: {n} rows identical"
              + (f"  — {'; '.join(bad[:3])}" if bad else ""))
    ok = all(n and not bad for _, n, bad in res)
    print(f"\n{sum(1 for _, n, bad in res if n and not bad)}/{len(res)} checks passed"
          + (" — PARITY: ALL GREEN" if ok else " — PARITY FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
