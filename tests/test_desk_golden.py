"""F1c (#191) REGRESSION: the Python Desk (src/walters/desk_policy.py) against
the DELETED in-browser Desk's last known outputs, frozen in
tests/golden/desk_js_v1_1.json.gz (scripts/desk_golden_capture.py, pre-F1c
cockpit.html; clock and counts pinned, non-UTC browser). Row for row, every
field, floats exact. No browser."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import desk_battery as b  # noqa: E402

RESULTS = b.check_against_golden()


@pytest.mark.parametrize("label,n,bad", RESULTS, ids=[r[0] for r in RESULTS])
def test_python_desk_matches_the_frozen_js(label, n, bad):
    assert n > 0 and not bad, "; ".join(bad[:3])


def test_golden_is_the_pre_f1c_capture():
    g = b.load_golden()
    assert g["now"] == "2026-10-02T16:00:00Z" and g["browser_tz"] == "America/New_York"
    assert [s["seed"] for s in g["scenarios"]] == [151, 152, 153]
    assert sum(len(s["js"]["calls"]) for s in g["scenarios"]) == 810 and len(g["to_fixed"]) == 1508
