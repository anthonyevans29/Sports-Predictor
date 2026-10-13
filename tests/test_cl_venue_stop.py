"""CL makes no venue call (ARCHITECT 2026-10-13 13:11 ET, addendum 61 item 3, #498).

(1), verbatim: "'No call' in addendum 58 covers the venue engine. CL is a three-way Kalshi soccer market, as UNL is,
and it stays out of venue-edge on UNL's ground (INTL policy v0, rule 5): until the skew test (#286) is read and I rule
on it. Its stop reads 'three-way soccer — no venue call before the skew test is read (CL)'. The charter's 'cups when
priced' waits on that same ruling."
(2), verbatim: "KXUCLGAME carries (1.0, 1.0) in KALSHI_FEE_M, as the fee schedule ruling (#93) names UCL. It costs a
fill. It prices no call."
"The stop goes into desk_policy's engine and into the Cockpit's mirror of it, with their tests."
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from src.walters import desk_policy as dp
from src.walters import venue

STOP = "three-way soccer — no venue call before the skew test is read (CL)"
NOW = datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)
MS = NOW.timestamp() * 1000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def card_row(comp="CL", ko_h=3, ask=True):
    """A window-card row that, in a venue-eligible competition, the engine would measure: ten fresh books, a two-sided
    Kalshi block 7pp under the books on HOME, and an executable ask."""
    ko = (NOW + timedelta(hours=ko_h)).strftime("%Y-%m-%dT%H:%M:%S")
    row = {"engine": "market_only", "competition": comp, "utc_date": ko, "status": "scheduled",
           "home_team": "Arsenal", "away_team": "Lille",
           "market": {"bookmaker_count": 10, "fair_prob": {"HOME": 0.62, "AWAY": 0.16, "DRAW": 0.22},
                      "captured_at": (NOW - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S")},
           "kalshi": {"status": "two_sided", "prob": {"HOME": 0.55, "AWAY": 0.20, "DRAW": 0.25}}}
    if ask:
        row["kalshi_legs"] = {"HOME": {"ticker": "KXUCLGAME-26OCT13ARSLIL-ARS", "bid": 0.54, "ask": 0.55},
                              "AWAY": {"ticker": "KXUCLGAME-26OCT13ARSLIL-LIL", "bid": 0.19, "ask": 0.20},
                              "DRAW": {"ticker": "KXUCLGAME-26OCT13ARSLIL-TIE", "bid": 0.24, "ask": 0.25}}
    return row


def test_the_window_card_cl_row_stops_with_the_ruled_reason():
    v = dp.window_venue(card_row(), MS)
    assert (v["eligible"], v["reason"], v["side"]) == (False, STOP, None), v
    assert "quote_age_hold" not in v                       # the stop comes before the computation: nothing is held


def test_the_stop_does_not_lift_with_the_quote_age_hold():
    """'until the skew test (#286) is read and I rule on it': lifting the quote-age hold does not lift this stop."""
    with dp.quote_age_rule_off():
        v = dp.window_venue(card_row(), MS)
    assert (v["eligible"], v["reason"]) == (False, STOP)


def test_a_live_league_with_the_same_numbers_is_unchanged():
    pl = dp.window_venue(card_row("PL"), MS)
    assert pl["reason"] != STOP and pl["side"] == "HOME"         # measured (and held by the quote-age rule today)
    assert dp.window_venue(card_row("UNL"), MS)["reason"] == "single venue — no pair (UNL)"


def test_the_stop_comes_before_in_play_as_unl_does():
    assert dp.window_venue(card_row(ko_h=-1), MS)["reason"] == STOP


def test_a_cl_fixtures_file_row_passes_with_no_order():
    doc = {"competition_code": "CL", "fixtures": [card_row()]}
    dp.annotate(doc, now=NOW)
    d = doc["fixtures"][0]["desk"]
    assert d["call"] == "PASS" and d["order"] is None and d["reason"] == STOP, d


def test_the_stop_is_keyed_on_the_ruled_set():
    assert dp.SKEW_TEST_VENUE_COMPS == ("CL",)
    assert dp.SKEW_TEST_VENUE_REASON.format("CL") == STOP


def test_kxuclgame_carries_its_ruled_fee_and_prices_no_call():
    """(2): "It costs a fill. It prices no call." """
    assert venue.KALSHI_FEE_M["KXUCLGAME"] == (1.0, 1.0)
    assert "CL" not in venue.KALSHI_SERIES_BY_COMPETITION
    import importlib.util
    spec = importlib.util.spec_from_file_location("fills", os.path.join(ROOT, "scripts", "kalshi_fee_fill_receipt.py"))
    receipt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(receipt)
    series, cands = receipt.candidates("KXUCLGAME-26OCT13ARSLIL-ARS")        # a fill is costed by its series' M
    assert series == "KXUCLGAME" and [(lab, m) for lab, _rate, m in cands] == [("taker", 1.0), ("maker", 1.0)]


def test_the_cockpit_mirror_states_the_stop_and_the_charter_wait():
    html = open(os.path.join(ROOT, "tools", "cockpit.html"), encoding="utf-8").read()
    assert "cups when priced: that waits on the skew-test ruling, ARCHITECT 2026-10-13" in html
    assert "CL (three-way soccer) none before the skew test is read" in html
    assert STOP in html                                    # the PASS-reason class list names the stop's text
    assert "UCL:[1,1]" in html                             # the Cockpit's fills table already costs UCL at the ruled M


def test_the_stop_is_on_by_default_and_off_only_for_the_frozen_battery():
    """The frozen pre-F1c golden carries CL fixture rows the JS engine measured; it runs with the stop off
    (base_v11()), as it does with every rule that postdates it. Every other caller has it on."""
    assert dp.SKEW_TEST_VENUE_RULE["on"] is True
    with dp.base_v11():
        assert dp.SKEW_TEST_VENUE_RULE["on"] is False
        assert dp.window_venue(card_row(), MS)["reason"] != STOP
    assert dp.SKEW_TEST_VENUE_RULE["on"] is True
    with dp.addendum_off():                                     # desk-rescore's "before" side keeps it on
        assert dp.window_venue(card_row(), MS)["reason"] == STOP
