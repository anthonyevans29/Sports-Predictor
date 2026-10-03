"""P0-2 CLOSE CONTRACT (#207, ARCHITECT 2026-10-01, external review): the
caller names the outcome set; a book counts only with a COMPLETE same-session
set; each complete book is de-vigged on its own, then averaged; no complete
book -> unpriced with a missing-leg receipt; quoted vs complete book counts.
Ruled tests: missing draw, one-sided, mismatched coverage, post-kickoff
replacement."""
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest

from src.db.schema import Sport
from src.walters.close import BINARY, THREE_WAY, close_1x2, outcomes_for, priced

KO = datetime(2041, 5, 1, 19, 0)
T = KO - timedelta(hours=1)


def r(book, sel, price, at=T):
    return NS(bookmaker=book, selection=sel, price_decimal=price, captured_at=at, market="1X2", line=None)


def test_outcome_set_per_sport():
    assert outcomes_for(Sport.SOCCER) == THREE_WAY
    for sp in (Sport.MLB, Sport.NFL, Sport.NHL):
        assert outcomes_for(sp) == BINARY


def test_missing_draw_book_is_quoted_not_complete():
    rows = [r("a", "HOME", 2.0), r("a", "DRAW", 3.4), r("a", "AWAY", 4.0),
            r("b", "HOME", 1.9), r("b", "AWAY", 3.8)]                       # b: no DRAW leg
    cl = close_1x2(rows, KO, THREE_WAY)
    assert (cl["books"], cl["books_quoted"]) == (1, 2)
    assert cl["missing"] == {"b": ["DRAW"]}
    imp = {"HOME": 1 / 2.0, "DRAW": 1 / 3.4, "AWAY": 1 / 4.0}
    assert cl["fair"]["HOME"] == pytest.approx(imp["HOME"] / sum(imp.values()))   # book a alone
    assert sum(cl["fair"].values()) == pytest.approx(1.0)
    assert cl["best"]["HOME"] == ("a", 2.0)                    # b's 1.9 is not a complete book's price


def test_missing_draw_everywhere_is_unpriced_with_receipt():
    rows = [r("a", "HOME", 2.0), r("a", "AWAY", 4.0), r("b", "HOME", 1.9), r("b", "AWAY", 3.8)]
    cl = close_1x2(rows, KO, THREE_WAY)
    assert not priced(cl) and cl["fair"] is None and cl["best"] == {}
    assert cl["missing"] == {"a": ["DRAW"], "b": ["DRAW"]} and (cl["books"], cl["books_quoted"]) == (0, 2)
    # the same rows ARE a complete binary board (a 2-way sport)
    assert priced(close_1x2(rows, KO, BINARY))


def test_one_sided_market_is_unpriced():
    rows = [r("a", "HOME", 1.8), r("b", "HOME", 1.85)]
    cl = close_1x2(rows, KO, BINARY)
    assert not priced(cl) and cl["missing"] == {"a": ["AWAY"], "b": ["AWAY"]}


def test_mismatched_coverage_devigs_per_book_then_averages():
    """Book a quotes HOME only, book b AWAY only: pooled selection averages
    would fabricate a two-sided price from two one-sided books."""
    cl = close_1x2([r("a", "HOME", 1.5), r("b", "AWAY", 2.0)], KO, BINARY)
    assert not priced(cl) and cl["missing"] == {"a": ["AWAY"], "b": ["HOME"]}
    # two complete books with different margins: the mean of per-book fair probs
    rows = [r("a", "HOME", 1.5), r("a", "AWAY", 2.4), r("b", "HOME", 1.8), r("b", "AWAY", 2.1)]
    cl = close_1x2(rows, KO, BINARY)
    fa = (1 / 1.5) / (1 / 1.5 + 1 / 2.4)
    fb = (1 / 1.8) / (1 / 1.8 + 1 / 2.1)
    assert cl["fair"]["HOME"] == pytest.approx((fa + fb) / 2)
    assert (cl["books"], cl["books_quoted"]) == (2, 2)


def test_post_kickoff_replacement_is_never_the_close():
    """A replace-on-sync source re-captured after kickoff: only in-game rows
    remain -> no pre-kickoff capture -> None (unpriced); a pre-kickoff
    session beside in-game rows -> the pre-kickoff session is the close."""
    live = KO + timedelta(minutes=20)
    assert close_1x2([r("a", "HOME", 1.2, live), r("a", "AWAY", 5.0, live)], KO, BINARY) is None
    cl = close_1x2([r("a", "HOME", 2.0), r("a", "AWAY", 1.9),
                    r("a", "HOME", 1.2, live), r("a", "AWAY", 5.0, live)], KO, BINARY)
    assert cl["fair"]["HOME"] == pytest.approx((1 / 2.0) / (1 / 2.0 + 1 / 1.9))
    assert cl["captured_at"] == T


def test_completeness_is_same_session():
    """A leg from an EARLIER session never completes a book in the last one."""
    early = KO - timedelta(days=1)
    rows = [r("a", "DRAW", 3.3, early), r("a", "HOME", 2.0), r("a", "AWAY", 4.0)]
    cl = close_1x2(rows, KO, THREE_WAY)
    assert not priced(cl) and cl["missing"] == {"a": ["DRAW"]}


def test_clv_cohorts_verified_vs_retained_legacy():
    from src.walters.clv_restate import clv_cohort
    m = NS(utc_date=KO, sport=Sport.SOCCER)
    pred = NS(home_win_prob=0.55, draw_prob=0.25, away_win_prob=0.20)
    rows = [r("a", "HOME", 2.0), r("a", "DRAW", 3.4), r("a", "AWAY", 4.0)]
    fair_h = close_1x2(rows, KO, THREE_WAY)["fair"]["HOME"]
    assert clv_cohort(NS(clv=0.55 - fair_h), pred, m, rows) == "verified"
    assert clv_cohort(NS(clv=0.55 - fair_h + 0.02), pred, m, rows) == "legacy"     # an older close's value
    no_draw = [r("a", "HOME", 2.0), r("a", "AWAY", 4.0)]
    assert clv_cohort(NS(clv=0.03), pred, m, no_draw) == "legacy"                  # contract cannot price it
    assert clv_cohort(NS(clv=None), pred, m, rows) is None


def test_results_tally_never_pools_the_cohorts(tmp_path):
    from src.db.database import init_db
    from src.walters.export import results_tally
    init_db()
    txt = open(results_tally(days=36500, out_path=str(tmp_path / "R.md"))).read()
    assert "Mean CLV:" not in txt and "Mean CLV, verified" not in txt   # pooled headline gone; P0-3 rename (#208)
    assert "CLOSE CONTRACT (#207)" in txt
    for line in txt.splitlines():
        if "Retained-legacy model-close divergence" in line:
            assert "not in the headline" in line
