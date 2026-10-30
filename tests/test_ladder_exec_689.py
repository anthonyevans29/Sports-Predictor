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
    monkeypatch.setattr(dp, "UNIT_PIN", dp.LEGACY_CONTRACTS_BASIS)   # 1u = 10 contracts (conftest's pin, stated)


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


def test_a_sub_cent_quote_is_normalized_as_the_order_line_does():
    """Codex on #714: a HOME yes bid of 0.445 is a 0.45 yes bid in the order line, so the NO ask is 0.55, not 0.555."""
    d = desk_of(ladder_row(legs={"HOME": {"ticker": "T-EVE", "bid": 0.445, "ask": 0.4549}}))
    assert d["order"]["text"].startswith("BUY NO T-EVE @ 0.55 ")
    lx = d["ladder_exec"]
    assert (lx["bid"], lx["ask"]) == (0.55, 0.55) and lx["cost"] == round(0.55 + kalshi_fee(0.55, 1.0, n=5), 4)


def test_a_priced_leg_without_a_model_draw_says_why():
    """Codex on #714: a row with no draw probability prices the leg but has no model draw + away, so no edge, and
    says so (results-tally then names the cause, never "no ladder_exec block")."""
    r = dp.normalize({"sport": "soccer", "predictions": [ladder_row()]})[0]
    r["probsAll"] = {**r["probsAll"], "DRAW": None}
    lx = dp.ladder_exec_block(r, {"call": "LADDER", "units": 0.5})
    assert lx["cost"] is not None and lx["edge_pp"] is None and lx["model_p"] is None
    assert lx["why"] == "no model probability for draw + away (the row carries no draw probability): no edge"


def test_an_unread_day_labels_the_ladder_exec_count_the_fees_basis(monkeypatch):
    """Addendum 179 item 4 (#732): an unread day carries no order line; the ladder exec's count is then the reference
    fill the fee is priced at, labelled so, never an order."""
    monkeypatch.setattr(dp, "UNIT_PIN", dp.unit_unread(dp.UNIT_UNREAD_TEXT))
    d = desk_of(ladder_row())
    assert d["call"] == "LADDER" and d["order"]["text"] is None and d["order"]["why"] == dp.UNIT_UNREAD_TEXT
    assert d["ladder_exec"]["contracts"] == 5 and d["ladder_exec"]["contracts_basis"] == dp.UNIT_REFERENCE_FILL_TEXT
    monkeypatch.setattr(dp, "UNIT_PIN", dp.LEGACY_CONTRACTS_BASIS)
    assert "contracts_basis" not in desk_of(ladder_row())["ladder_exec"]
