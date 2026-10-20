"""THE PAPER LANE's pure helpers (ARCHITECT 2026-10-20, addendum 146 item 5(a)): the board read from the stored
market, the two-way mid as the grading close forms it (close.close_from_kalshi, unchanged), the three-way legs' raw
mids under the same filters (display only, never a close), and the shadow's pick and value side against those mids."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from src.walters import close, paper

KO = datetime(2026, 10, 20, 23, 0)


def snap(sel, bid, ask, mins=30, market="ML", source="kalshi"):
    return SimpleNamespace(source=source, market=market, selection=sel, captured_at=KO - timedelta(minutes=mins),
                           yes_bid=bid, yes_ask=ask)


def test_the_board_is_read_from_the_stored_market():
    assert paper.board_of([snap("HOME", .5, .51), snap("AWAY", .49, .5)]) == "two-way"
    assert paper.board_of([snap(s, .3, .31, market="1X2") for s in ("HOME", "DRAW", "AWAY")]) == "three-way"
    assert paper.board_of([snap("HOME", .5, .51), snap("DRAW", .3, .31, market="1X2")]) == "mixed"
    assert paper.board_of([]) is None
    assert paper.board_of([snap("HOME", .5, .51, source="books")]) is None


@pytest.mark.parametrize("rows", [
    [snap("HOME", .54, .55), snap("AWAY", .45, .46)],
    [snap("HOME", .58, .61, 10), snap("HOME", .60, .61, 60)],          # the last is 3c wide: none, never the older
    [snap("HOME", .54, None)],                                         # bid only
    [snap("HOME", .54, .55, -5)],                                      # after kickoff
    [snap("HOME", .49, .51), snap("HOME", .40, .41, 90)],              # the newest, 2c: within the cap
])
def test_the_two_way_mid_is_the_grading_closes_own(rows):
    assert paper.two_way_mid(rows, KO) == close.close_from_kalshi(rows, KO, close.BINARY)


def test_a_legs_mid_is_close_from_kalshis_on_home_only_1x2_rows():
    rows = [snap("HOME", .44, .45, market="1X2"), snap("HOME", .40, .41, 90, market="1X2")]
    legs = paper.leg_mids(rows, KO)
    assert legs["HOME"]["mid"] == close.close_from_kalshi(rows, KO, close.BINARY)["fair"]["HOME"]
    assert legs["HOME"]["captured_at"] == KO - timedelta(minutes=30) and legs["HOME"]["spread_c"] == 1.0
    assert legs["DRAW"] is None and legs["AWAY"] is None


def test_three_way_legs_raw_mids_and_the_cap():
    rows = [snap("HOME", .44, .45, market="1X2"), snap("DRAW", .27, .30, market="1X2"),
            snap("DRAW", .27, .28, 60, market="1X2"), snap("AWAY", .28, .29, market="1X2"),
            snap("AWAY", .99, .99, 5, market="ML")]                    # an ML row is never a three-way leg
    legs = paper.leg_mids(rows, KO)
    assert legs["HOME"]["mid"] == pytest.approx(.445) and legs["AWAY"]["mid"] == pytest.approx(.285)
    assert legs["DRAW"] is None                                        # 3c wide: none, the 1c older one not taken


def test_shadow_view_pick_and_value_side():
    v = paper.shadow_view({"home_win_prob": .55, "away_win_prob": .45, "top_pick": "home_win"},
                          {"HOME": .60, "AWAY": .40})
    assert (v["pick"], round(v["pick_div_pp"], 1), v["value_side"], round(v["value_div_pp"], 1)) == \
        ("HOME", -5.0, "AWAY", 5.0)
    v = paper.shadow_view({"home_win_prob": .60, "away_win_prob": .40, "top_pick": "home_win"},
                          {"HOME": .60, "AWAY": .40})
    assert (v["value_side"], v["value_why"], v["pick_div_pp"]) == (None, "no side above its mid", 0.0)   # exact tie
    v = paper.shadow_view({"home_win_prob": .55, "away_win_prob": .45, "top_pick": "home_win"}, None)
    assert (v["pick"], v["pick_p"], v["pick_div_pp"], v["value_side"], v["value_why"]) == \
        ("HOME", .55, None, None, "no mid")


def test_shadow_view_three_way_is_judged_only_with_all_three_legs():
    pred = {"home_win_prob": .40, "draw_prob": .30, "away_win_prob": .30, "top_pick": "home_win"}
    v = paper.shadow_view(pred, {"HOME": .44, "DRAW": None, "AWAY": .25})     # the board's DRAW leg has no mid
    assert (v["value_side"], v["value_why"], round(v["pick_div_pp"], 1)) == (None, "a leg has no mid", -4.0)
    v = paper.shadow_view(pred, {"HOME": .44, "DRAW": .27, "AWAY": .25})
    assert (v["value_side"], round(v["value_div_pp"], 1)) == ("AWAY", 5.0)
    v = paper.shadow_view(pred, {"HOME": .44, "DRAW": .25, "AWAY": .25})
    assert (v["value_side"], v["value_why"]) == (None, "two sides tie above their mids")


def test_a_prediction_of_another_shape_than_the_board_is_never_judged():
    """A two-way prediction (no draw_prob) on a three-way board is never judged on two of its three legs, priced or
    not; a three-way prediction on a two-way board neither. Neither carries a divergence (a two-way p against a raw
    three-way mid is not comparable)."""
    two = {"home_win_prob": .5, "away_win_prob": .5, "top_pick": "home_win"}
    for legs in ({"HOME": .405, "DRAW": .295, "AWAY": .305}, {"HOME": .405, "DRAW": None, "AWAY": .305}):
        v = paper.shadow_view(two, legs)
        assert (v["pick"], v["pick_div_pp"], v["value_side"], v["value_div_pp"], v["value_why"]) == \
            ("HOME", None, None, None, "a two-way prediction on a three-way board"), legs
    v = paper.shadow_view({"home_win_prob": .5, "draw_prob": .2, "away_win_prob": .3, "top_pick": "home_win"},
                          {"HOME": .45, "AWAY": .55})
    assert (v["pick_div_pp"], v["value_side"], v["value_why"]) == (None, None, "a three-way prediction on a two-way board")
    assert paper.board_differs(v["value_why"]) and not paper.board_differs("a leg has no mid")
    assert not paper.board_differs(None)


@pytest.mark.parametrize("home_p,side,why,div", [
    (0.5454, None, "no side above its mid by 0.05pp or more, the printed precision", 0.04),
    (0.5455, "HOME", None, 0.05), (0.546, "HOME", None, 0.1)],
    ids=["0.04pp-prints-0.0", "0.05pp-prints-0.1", "0.1pp"])
def test_the_value_side_is_judged_at_the_printed_precision(home_p, side, why, div):
    """nhl_shadow rounds to 4 dp: against a 0.545 mid, home .5454 is +0.04pp, which prints +0.0pp, so it is no value
    side (said so); .5455 is +0.05pp (prints +0.1pp) and is one. The divergences are rounded to 9 decimals, so the
    printed figure is the judged one."""
    v = paper.shadow_view({"home_win_prob": home_p, "away_win_prob": round(1 - home_p, 4), "top_pick": "home_win"},
                          {"HOME": .545, "AWAY": .455})
    assert (v["value_side"], v["value_why"], round(v["pick_div_pp"], 9)) == (side, why, div)
    if side:
        assert f"{v['value_div_pp']:+.1f}" == f"{v['pick_div_pp']:+.1f}" == f"{div:+.1f}" != "+0.0"


def test_the_rulings_and_the_label():
    assert paper.PAPER_LABEL == "PAPER, never a call" and paper.CLOSE_RECORD_COMPS == ("NHL", "NCAA", "CL")
    assert paper.RULING_5A.startswith("(a) coverage's SLATE line for a market-only competition carries, per game, ")
    assert paper.RULING_5B.endswith("(roadmap: \"no college candidate has been scored against a close\").")


def test_a_leg_reads_only_a_sane_two_sided_quote_within_the_cap():
    """close_from_kalshi's own sanity tests per leg: a crossed quote (bid above ask), bid 0 / ask 0 and bid 1 / ask 1
    are no mid; a 2c-wide leg is within the cap (the cap is > 2c, not >= 2c)."""
    for bad in ((.46, .45), (0.0, 0.0), (1.0, 1.0)):
        assert paper.leg_mids([snap("HOME", *bad, market="1X2")], KO)["HOME"] is None, bad
    legs = paper.leg_mids([snap("DRAW", .27, .29, market="1X2")], KO)
    assert legs["DRAW"]["mid"] == pytest.approx(.28) and legs["DRAW"]["spread_c"] == 2.0


def test_a_leg_never_reads_a_quote_from_kickoff_on():
    """R21 on a three-way board: an in-play quote is never the leg's; the last one before kickoff is."""
    legs = paper.leg_mids([snap("HOME", .44, .45, market="1X2"), snap("HOME", .80, .81, -5, market="1X2"),
                           snap("HOME", .70, .71, 0, market="1X2")], KO)
    assert legs["HOME"]["mid"] == pytest.approx(.445) and legs["HOME"]["captured_at"] == KO - timedelta(minutes=30)


def test_float_noise_never_makes_a_side_exceed_its_mid():
    """0.1 + 0.2 is 0.30000000000000004: rounded to 9 decimals before the comparison, it equals a 0.3 mid."""
    v = paper.shadow_view({"home_win_prob": 0.1 + 0.2, "away_win_prob": 0.7, "top_pick": "away_win"},
                          {"HOME": 0.3, "AWAY": 0.7})
    assert (v["value_side"], v["value_why"]) == (None, "no side above its mid")


@pytest.mark.parametrize("pred", [
    ["junk"], "n/a", {"home_win_prob": "0.6", "away_win_prob": .4, "top_pick": "home_win"},
    {"home_win_prob": float("nan"), "away_win_prob": .4, "top_pick": "home_win"},
    {"home_win_prob": True, "away_win_prob": .4, "top_pick": "home_win"},
    {"home_win_prob": .6, "away_win_prob": .4, "top_pick": ["home_win"]}],
    ids=["a-list", "text", "prob-text", "prob-nan", "prob-bool", "pick-a-list"])
def test_a_prediction_of_the_wrong_kind_is_unreadable_and_never_raises(pred):
    """Law 4: such a row is refused by coverage (unreadable), and shadow_view itself never raises on it: a value of the
    wrong kind reads as absent."""
    assert paper.unreadable(pred)
    if isinstance(pred, dict):
        v = paper.shadow_view(pred, {"HOME": .55, "AWAY": .45})
        assert v["pick"] is None or v["pick_p"] is None                  # nothing of the wrong kind is shown
    assert not paper.unreadable({"home_win_prob": .6, "away_win_prob": .4, "top_pick": "home_win"})
    assert not paper.unreadable({"home_win_prob": .6, "away_win_prob": .4})          # no pick: "carries no pick"
