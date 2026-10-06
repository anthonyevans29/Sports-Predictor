"""F1c (#191): the Next-24h card's venue verdict is computed by the Python
Desk (desk_policy.window_venue, stamped by window.py as desk_venue) — the
Cockpit only renders it."""
from datetime import datetime, timedelta, timezone

import pytest
from src.walters import desk_policy as dp


@pytest.fixture(autouse=True)
def _base_v11():
    """These cases pin v1.1 rules that the #87 addendum (2026-10-06) does not touch; their fixtures carry no
    executable quotes. The addendum and its interactions are tested in tests/test_desk_exec_addendum.py."""
    with dp.base_v11():
        yield

NOW = datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc)
MS = float((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))
KO = "2026-10-02T21:00:00"


def row(engine="market_only", comp="NHL", books=5, fair=None, kal=None, ko=KO):
    return {"engine": engine, "competition": comp, "utc_date": ko,
            "market": {"bookmaker_count": books, "fair_prob": fair or {"HOME": 0.58, "AWAY": 0.42},
                       "captured_at": "2026-10-02T15:30:00"},                     # fresh (#91)
            "kalshi": kal if kal is not None else {"status": "two_sided", "prob": {"HOME": 0.50, "AWAY": 0.50}}}


def test_eligible_pair_thin_pair_model_row_unl_and_in_play():
    v = dp.window_venue(row(), MS)
    assert v["eligible"] and v["side"] == "HOME" and abs(v["div_pp"] - 8.0) < 1e-9
    assert dp.window_venue(row(books=2), MS)["kind"] == "noref"
    assert dp.window_venue(row(engine="model_edge"), MS)["reason"].startswith("model sport")
    assert dp.window_venue(row(comp="UNL"), MS)["reason"] == "single venue — no pair (UNL)"
    assert dp.window_venue(row(ko="2026-10-02T15:00:00"), MS)["reason"] == "in-play — never"
    assert dp.window_venue(row(kal={"status": "partial", "prob": {"HOME": 0.5}}), MS)["kind"] == "noref"
