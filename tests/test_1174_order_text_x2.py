"""#1174 (ARCHITECT 2026-11-27, addendum 581 item 1): the bulletins' guard, ORDER_TEXT, exempts the ONE upper-case token
X2, the Desk's own name for the double chance, and gains a cents-then-count arm (F with D'). Pins both ways as the plan
(#1174, comment 7225829271) lists them, the three more 581 item 1(d) names, and the KNOWN PASS of 581 item 1(c).

Before this, the pattern's (?i) covered its standing-alone arm, so "(X2)" in a LADDER reason refused every bulletin of
a slate or a closing that held a LADDER call (579 item 2). The guard stays fail-closed: every other count still refuses.
"""
import sys
from pathlib import Path

import pytest

from src import privacy_patterns as pv
from src.walters import desk_policy as dp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import bulletin as b  # noqa: E402

from tests.test_bulletin import closing_file, files_under, repo, soccer_doc  # noqa: E402,F401


def offence(text):
    return pv.bulletin_offence(f"edge below the floor · {text}")


# The Desk's own words for the double chance (desk_policy.py: the LADDER reason, the order's and the ladder's why, the
# ladder leg): they pass.
DESK_WORDS = [
    "edge ≥ 20pp on away/draw (3-way) → double-chance (X2), half units",
    "edge ≥ 20pp on away/draw (3-way) → double-chance (1X/X2), half units",
    "NO on HOME (X2 = not home)",
    "double chance for a draw pick is 1X or X2 — no single contract; write it by hand",
    "double chance for a draw pick is 1X or X2: no single contract to price",
    "(X2)", "(1X/X2)", "X2 = not home", "1X or X2",
]


@pytest.mark.parametrize("text", DESK_WORDS)
def test_the_desks_double_chance_words_pass(text):
    assert offence(text) is None


# Every other count refuses, in either case, alone, after a price, before "at", or after a price in cents.
REFUSED = [
    "x3", "x2", "X3", "X12", "X22", "X20", "Ｘ3", "Ｘ３",          # standing alone; the lower-case two refuses (581 1(d))
    "fill X3 today", "fill x3 today",
    "@ 0.45 X2", "@ 45c X2",                                    # the upper-case two after an at-sign and a price
    "X2 at 45c", "X2 @ 45c",                                    # ... and before "at" / "@"
    "45c X2", "45c X3", "45c x 3", "45cX3", "45 c x 2",         # D': a price in cents then a count
    "@ 0.45 x 3", "x 3 at 45c", "@ 45c x 3",                    # the pins already on main stay
]


@pytest.mark.parametrize("text", REFUSED)
def test_every_other_count_refuses_as_order_text(text):
    assert offence(text) == "order_text"


def test_the_desks_own_order_line_refuses_under_the_fix():
    """The Desk's order text (desk_policy.order_line's shape: the BUY lead and the multiplication sign) is untouched:
    those two arms carry no exemption."""
    for line in ("BUY NO KXTESTGAME-26NOV28ABCDEF-ABC @ 45c × 3", "BUY YES KXTESTGAME-26NOV28ABCDEF-DEF @ 0.45 × 2",
                 "BUY NO KXTESTGAME-26NOV28ABCDEF-ABC @ 45c × 2 (X2 = not home)"):
        assert offence(line) == "order_text"


def test_the_known_pass_is_written_down():
    """581 item 1(c), ACCEPTED AND WRITTEN DOWN: an upper-case count of exactly two with no BUY lead, no
    multiplication sign, no at-sign, no "at" and no cents letter passes. The Desk's own order line never has that
    shape. This pin keeps the gap written and never silent: if a later change closes it, change this pin by ruling."""
    assert offence("0.45 X2") is None                           # KNOWN PASS (581 item 1(c))


def test_a_ladder_reason_no_longer_refuses_the_bulletin(repo):
    """End to end: a soccer row whose Desk reason carries the LADDER's double-chance words writes its bulletin (before
    #1174 the run left with 2, pattern order_text, nothing written)."""
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = DESK_WORDS[0]
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    assert files_under(repo / "exports" / "bulletins") != []


def test_an_order_count_in_a_reason_still_refuses_the_bulletin(repo):
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = "edge below the floor · 45c X2"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    assert files_under(repo / "exports" / "bulletins") == []


def test_the_pattern_keeps_its_case_insensitive_head():
    """Only the standing-alone arm's one token is exempt: the pattern's flag is unchanged."""
    import re
    assert pv.ORDER_TEXT.flags & re.IGNORECASE
    assert dp is not None                                       # the Desk is imported, not changed, by this PR
