"""#689 (ARCHITECT 2026-10-26 12:05 ET): "a LADDER row's desk.exec is null by design, so the NO contract's probability
(model draw+away vs the market's), fee-inclusive cost and executable edge are not on the row [...] Build the exec block
for the ordered NO leg, informational: it changes no call, no units, no floor. results-tally's "left out: LADDER" line
then gains a priced-but-ungraded cohort line (notional, never pooled with PLAY)."

desk_policy.ladder_exec_block writes desk.ladder_exec on a LADDER row; desk.exec stays null; the golden's policy
(base_v11, the #87 addendum off) writes none. exec_cohorts prints the LADDER line."""
import copy
from datetime import datetime, timedelta, timezone

import pytest

from src.walters import desk_policy as dp
from src.walters.venue import kalshi_fee

NOW = datetime(2026, 10, 11, 16, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _contracts_per_unit(monkeypatch):
    monkeypatch.delenv("SP_UNIT_USD", raising=False)                 # 1u = 10 contracts


def ladder_row(probs=(0.25, 0.25, 0.50), legs=None):
    """Everton-Fulham as tests/test_desk_exec_addendum.py builds its LADDER: away +22pp on a three-way board."""
    return {"home_team": "Everton", "away_team": "Fulham", "utc_date": (NOW + timedelta(minutes=45)).isoformat(),
            "competition": "PL", "stage": "regular",
            "prediction": {"probabilities": dict(zip(("home_win", "draw", "away_win"), probs)), "tier": "lean"},
            "market": {"bookmaker_count": 9, "fair_prob": {"HOME": 0.45, "DRAW": 0.27, "AWAY": 0.28}},
            "kalshi_legs": legs if legs is not None else {"AWAY": {"ticker": "T-FUL", "bid": 0.28, "ask": 0.29},
                                                          "HOME": {"ticker": "T-EVE", "bid": 0.44, "ask": 0.45}}}


def desk_of(row):
    doc = {"sport": "soccer", "predictions": [copy.deepcopy(row)]}
    dp.annotate(doc, now=NOW)
    return doc["predictions"][0]["desk"]


def test_the_ordered_no_leg_is_priced_and_the_call_units_and_order_do_not_move(monkeypatch):
    d = desk_of(ladder_row())
    assert d["call"] == "LADDER" and d["units"] == 0.5 and d["exec"] is None           # desk.exec stays null
    assert d["order"]["text"] == "BUY NO T-EVE @ 0.56 × 5"
    lx = d["ladder_exec"]
    cost = round(0.56 + kalshi_fee(0.56, 1.0, n=5), 4)                                # NO ask = 1 - 0.44, 5 contracts
    assert lx["leg"] == "NO on HOME (X2 = not home)" and lx["ticker"] == "T-EVE"
    assert lx["model_p"] == pytest.approx(0.75) and lx["market_p"] == pytest.approx(0.55)   # draw + away
    assert (lx["bid"], lx["ask"], lx["contracts"], lx["basis"]) == (0.55, 0.56, 5, "taker")
    assert lx["cost"] == cost and lx["edge_pp"] == pytest.approx((0.75 - cost) * 100)
    assert lx["fee_clears"] is True and lx["informational"] is True and lx["why"] is None
    # informational: without the block, every other field of the desk is the same
    monkeypatch.setattr(dp, "ladder_exec_block", lambda r, c: None)
    assert {k: v for k, v in d.items() if k != "ladder_exec"} == desk_of(ladder_row())


def test_a_draw_pick_and_an_unticketed_home_leg_say_why_and_are_never_priced():
    draw = desk_of(ladder_row(probs=(0.25, 0.50, 0.25)))
    assert draw["call"] == "LADDER" and draw["ladder_exec"]["cost"] is None
    assert draw["ladder_exec"]["why"] == "double chance for a draw pick is 1X or X2: no single contract to price"
    bare = desk_of(ladder_row(legs={"AWAY": {"ticker": "T-FUL", "bid": 0.28, "ask": 0.29}}))
    assert bare["ladder_exec"]["why"] == "no Kalshi ticker on file for the HOME leg (ladder = NO on HOME)"
    assert bare["ladder_exec"]["cost"] is None and bare["ladder_exec"]["model_p"] == pytest.approx(0.75)
    nobid = desk_of(ladder_row(legs={"HOME": {"ticker": "T-EVE", "bid": None, "ask": 0.45}}))
    assert nobid["ladder_exec"]["why"] == "no NO ask to take (the HOME leg has no yes bid)"


def test_only_a_ladder_carries_it_and_the_goldens_policy_writes_none():
    play = desk_of(ladder_row(probs=(0.60, 0.20, 0.20)))
    assert play["call"] != "LADDER" and "ladder_exec" not in play
    with dp.base_v11():
        d = desk_of(ladder_row())
    assert d["call"] == "LADDER" and "ladder_exec" not in d
