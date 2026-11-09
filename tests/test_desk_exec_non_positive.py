"""A NON-POSITIVE EXEC EDGE IS A PASS (ARCHITECT 2026-11-09 10:05 ET, addendum 305 item 1, RULED; money path; a
tightening of the #87 v1.1 addendum's item 3, fewer calls never more).

Item 1, verbatim: "(3) exec edge = model_p − cost; a PLAY gets full tier units only at exec edge >= 4pp, else HALF
units; an exec edge <= 0 is a PASS (pass_kind `exec_non_positive`; the reason names the all-in cost and the model's
price): the Desk never buys above its own price." "The same rule on every path that emits a call or a would-be call:
the slate and closing pages, the would-be record (#446, the NFL market-only rows), the arm's settlement reading [...].
Value shadows are unstaked and keep their own exec block as a record; they are not calls."

Item 2(c), the pins: exec exactly 0 -> PASS; exec -0.2 -> PASS with the kind; exec +0.1 -> half units (unchanged);
exec +4 -> full (unchanged); the golden battery unchanged with the addendum OFF. Plus: the would-be record of an NFL
market-only row at exec <= 0 is no would-be PLAY; the closing page's Desk row reads the PASS and carries no order; the
current Desk's battery changes only half-unit PLAYs at exec <= 0. The kind and the reason are written out here, not
imported, so the file runs against main and fails there."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

from src.walters import desk_policy as dp
from src.walters import exec_cohorts as xc
from tests.test_nfl_market_only_214 import pred

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)            # test_nfl_market_only_214's clock (pred's kickoffs)
MS = float((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))
KIND = "exec_non_positive"                                          # item 1, verbatim
RULING = "the Desk never buys above its own price; addendum 305"


def _off():
    """The Desk before addendum 305 (its switch off). On main the switch does not exist: nothing to turn off."""
    off = getattr(dp, "exec_non_positive_rule_off", None)
    if off is None:
        from contextlib import nullcontext
        return nullcontext()
    return off()


def cost_at(row, units=1):
    """The all-in cost (ask + taker fee) of the pick's order at `units`, as the Desk prices it (#87 v1.1 (1), (h))."""
    r = dp.normalize({"sport": row["competition"].lower(), "predictions": [row]})[0]
    return dp.desk_cost_for(r, "HOME", units)["cost"]


def at_exec(home, delta, comp="NFL", ask=0.55, **kw):
    """A two-way row whose HOME pick's exec edge at a 1u order is `delta` (probability points): model p = cost + delta.
    The fair edge is 6pp (over the floor and its near-floor band, under the big-edge and MLB quarantine lines), so the
    tier gives full units and only the exec rule sizes the row."""
    base = pred(home, 0.60, 0.54, comp=comp, bid=round(ask - 0.01, 2), ask=ask, **kw)
    p = round(cost_at(base) + delta, 4)
    return pred(home, p, round(p - 0.06, 4), comp=comp, bid=round(ask - 0.01, 2), ask=ask, **kw), p


def calls(*rows, sport="nfl"):
    ev = dp.evaluate({"sport": sport, "predictions": [json.loads(json.dumps(r)) for r in rows]}, MS)
    return {r["home"]: (r, c) for r, c in ev["calls"]}


@pytest.fixture
def chain(nfl_market_only_off):
    """The Desk chain on NFL rows with addendum 214 off (as tests/test_desk_exec_addendum.py runs it)."""
    yield


# ----------------------------------------------------------------------------------------- item 2(c), the four --

def test_exec_exactly_zero_is_a_pass(chain):
    row, p = at_exec("Zero", 0.0)
    r, c = calls(row)["Zero"]
    assert dp.exec_edge_pp(r, "HOME", r["prob"], 1) == 0.0                 # exactly 0: the ruled "<= 0"
    assert (c["call"], c["units"], c["cls"], c["passKind"]) == ("PASS", 0, "pass", KIND)
    with _off():                                                            # before 305: a half-unit PLAY
        _, b = calls(row)["Zero"]
    assert (b["call"], b["units"], b["passKind"]) == ("PLAY", 0.5, None) and "exec < 4pp half units" in b["tags"]


def test_exec_minus_point_two_is_a_pass_with_the_kind_and_the_reason_naming_cost_and_model_price(chain):
    row, p = at_exec("Bears", -0.002)                                       # Sunday's Bears: exec -0.2pp
    r, c = calls(row)["Bears"]
    cost = dp.desk_cost_for(r, "HOME", 1)["cost"]
    assert abs(dp.exec_edge_pp(r, "HOME", p, 1) + 0.2) < 1e-9
    assert (c["call"], c["units"], c["cls"], c["passKind"], c["shadowUnits"]) == ("PASS", 0, "pass", KIND, 0)
    assert c["reasons"] == [f"exec edge -0.2pp ≤ 0: ask + taker fee {cost:.3f} at or above the model's {p:.3f} → PASS "
                            f"({RULING})"]
    assert c["tags"] == ["exec ≤ 0 pass"]                                   # nothing sized: no sizing tag stays
    assert c["execUnits"] == 1                                              # priced at the order it would have placed


def test_exec_plus_point_one_stays_half_units(chain):
    row, _ = at_exec("Thin", 0.001)
    _, c = calls(row)["Thin"]
    assert (c["call"], c["units"], c["passKind"]) == ("PLAY", 0.5, None)
    assert "exec < 4pp half units" in c["tags"] and any("exec edge 0.1pp < 4pp" in x for x in c["reasons"])
    with _off():
        _, b = calls(row)["Thin"]
    assert b == c                                                           # unchanged by 305


def test_exec_plus_four_stays_full_units(chain):
    row, _ = at_exec("Clear", 0.04)
    _, c = calls(row)["Clear"]
    assert (c["call"], c["units"], c["passKind"]) == ("PLAY", 1, None) and "exec clears" in c["tags"]
    with _off():
        _, b = calls(row)["Clear"]
    assert b == c


def test_no_executable_quote_stays_half_units(chain):
    """v1.1's conservative unknown (no ask) is not a non-positive edge: half units, as ruled."""
    row = pred("NoQ", 0.62, 0.56)
    for k in ("kalshi_bid", "kalshi_ask", "exec_cost_taker", "exec_cost_maker", "kalshi_legs"):
        row.pop(k, None)
    _, c = calls(row)["NoQ"]
    assert (c["call"], c["units"]) == ("PLAY", 0.5) and "exec unknown half units" in c["tags"]


def test_mlb_reads_the_same_rule(chain):
    row, p = at_exec("Mets", -0.01, comp="MLB")
    r, c = calls(row, sport="mlb")["Mets"]
    assert (c["call"], c["units"], c["passKind"]) == ("PASS", 0, KIND)
    assert c["reasons"][0].startswith("exec edge -1.0pp ≤ 0: ask + taker fee ")


def test_a_quarantine_shadow_and_a_value_shadow_are_untouched(chain):
    """Not calls (item 1): a quarantined row keeps its shadow; a value shadow keeps its own exec block."""
    q, _ = at_exec("Quar", -0.01, market_divergence_pp=20.0, quarantine=True)
    _, c = calls(q)["Quar"]
    with _off():
        _, b = calls(q)["Quar"]
    assert c == b and c["shadowUnits"] > 0 and c["passKind"] is None
    row, _ = at_exec("Val", -0.01)
    on = {r["home_team"]: r["desk"] for r in _annotate("nfl", [row])["predictions"]}
    with _off():
        off = {r["home_team"]: r["desk"] for r in _annotate("nfl", [row])["predictions"]}
    assert on["Val"]["value_shadow"] == off["Val"]["value_shadow"]


# ------------------------------------------------------------------------------------- the desk block / pages --

def _annotate(sport, rows):
    doc = {"sport": sport, "predictions": [json.loads(json.dumps(r)) for r in rows]}
    dp.annotate(doc, now=NOW)
    return doc


def test_the_desk_block_is_a_pass_with_no_order_and_keeps_its_exec_block_as_the_record(chain):
    row, p = at_exec("Bears", -0.002)
    doc = _annotate("nfl", [row])
    d = doc["predictions"][0]["desk"]
    assert (d["call"], d["units"], d["cls"], d["pass_kind"], d["order"]) == ("PASS", 0, "pass", KIND, None)
    assert d["exec"]["edge_pp"] <= 0 and d["exec"]["cost"] > p                 # the cost the reason names
    assert f"{d['exec']['cost']:.3f}" in d["reason"] and f"{p:.3f}" in d["reason"]
    assert doc["desk_meta"]["exec_non_positive_rule"] is True
    with _off():
        assert _annotate("nfl", [row])["desk_meta"]["exec_non_positive_rule"] is False


def test_the_closing_page_row_reads_the_pass(chain):
    import deploy.hosting.closing as closing
    a, _ = at_exec("Mets", -0.002, comp="MLB", match_id=1)
    b, _ = at_exec("Thin", 0.001, comp="MLB", match_id=2)
    doc = _annotate("mlb", [a, b])
    rows = {x["match_id"]: x for x in closing.desk_rows(doc, {1, 2}, NOW, fam="MLB")}
    assert (rows[1]["call"], rows[1]["call_text"], rows[1]["pass_kind"], rows[1]["order"]) == ("PASS", "PASS", KIND,
                                                                                               None)
    assert rows[1]["hold"] is None                                              # a PASS carries no PLAY hold
    assert rows[2]["call"] == "PLAY" and rows[2]["units"] == 0.5


def test_rescore_names_a_published_half_unit_play_as_exec_non_positive(chain):
    row, _ = at_exec("Bears", -0.002)
    doc = {"sport": "nfl", "predictions": [json.loads(json.dumps(row))]}
    with _off():
        dp.annotate(doc, now=NOW)                                               # Sunday's file: published before 305
    assert doc["predictions"][0]["desk"]["call"] == "PLAY"
    (x,) = dp.rescore(doc)
    assert (x["verdict"], x["addendum_call"], x["addendum_units"]) == ("exec non-positive", "PASS", 0)


# ------------------------------------------------------------------------------ the would-be record (#446) --

def test_the_would_be_record_reads_the_pass():
    """NFL market-only ON (production): the chain's own call is the record's would-be call. At exec <= 0 it is PASS
    exec_non_positive, so neither the closing page's would-be line nor exec_cohorts' would-be cohort sees a PLAY; at
    0 < exec < 4 the would-be half-unit PLAY stands."""
    import deploy.hosting.closing as closing
    neg, _ = at_exec("Bears", -0.002, match_id=1)
    thin, _ = at_exec("Thin", 0.001, match_id=2)
    doc = _annotate("nfl", [neg, thin])
    d = {r["home_team"]: (r, r["desk"]) for r in doc["predictions"]}
    for home in ("Bears", "Thin"):
        assert (d[home][1]["call"], d[home][1]["pass_kind"]) == ("PASS", "market_only")
    h = d["Bears"][1]["market_only_hold"]
    assert (h["would_call"], h["would_units"], h["would_pass_kind"]) == ("PASS", 0, KIND)
    assert h["would_reason"].startswith("exec edge -0.2pp ≤ 0: ask + taker fee ")
    cert = ("uncertified", "fixture")
    assert closing.would_be_for(*d["Bears"], "NFL", cert) is None and xc.would_be_play(d["Bears"][1]) is None
    w = closing.would_be_for(*d["Thin"], "NFL", cert)
    assert w and w["units"] == 0.5 and xc.would_be_play(d["Thin"][1])["would_call"] == "PLAY"
    rows = {x["match_id"]: x for x in closing.desk_rows(doc, {1, 2}, NOW, fam="NFL")}
    assert "would_be" not in rows[1] and rows[2]["would_be"]["units"] == 0.5


# ------------------------------------------------------------------------------------------ the golden battery --

def _battery():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import desk_battery as b
    return b


def test_the_golden_battery_is_unchanged_with_the_addendum_off_and_with_the_switch_forced_on():
    """The frozen golden runs under base_v11(), where the #87 addendum (EXEC_RULES) is off, so the branch never runs:
    the battery holds with 305's switch off (base_v11 turns it off) and with it forced on inside base_v11."""
    b = _battery()
    assert all(n > 0 and not bad for _, n, bad in b.check_against_golden())
    with dp.base_v11():
        assert dp.EXEC_NON_POSITIVE["on"] is False
        dp.EXEC_NON_POSITIVE["on"] = True
        try:
            assert all(n > 0 and not bad for _, n, bad in b._check(b.load_golden()))
        finally:
            dp.EXEC_NON_POSITIVE["on"] = False
    assert dp.EXEC_NON_POSITIVE["on"] is True


def test_the_current_desk_battery_changes_only_half_unit_plays_at_exec_non_positive():
    """Fewer calls, never more: on the seeded battery under the CURRENT Desk, every call 305 changes was a half-unit
    PLAY (the exec < 4pp tag) and is now PASS exec_non_positive with units 0 (an NFL row: its held chain call, under
    market-only); every value shadow, venue row and other call is byte-identical."""
    b = _battery()
    changed = 0
    for _, seed, counts, rev in b.SCENARIOS:
        docs = list(b.scenario_docs(seed, b.GOLDEN_NOW, rev).values())
        now_ms = b.now_ms(b.GOLDEN_NOW)
        on_calls = [c for d in docs for _, c in dp.evaluate(d, now_ms, counts)["calls"]]
        on = b.py_extract(docs, now_ms, counts)
        with _off():
            off_calls = [c for d in docs for _, c in dp.evaluate(d, now_ms, counts)["calls"]]
            off = b.py_extract(docs, now_ms, counts)
        assert b.same(on["values"], off["values"]) and b.same(on["venue"], off["venue"])
        for x, y in zip(off_calls, on_calls):
            if b.same(x, y):
                continue
            changed += 1
            was, now = x.get("mktOnlyHold") or x, y.get("mktOnlyHold") or y
            was_kind = was.get("pass_kind", was.get("passKind"))
            now_kind = now.get("pass_kind", now.get("passKind"))
            assert (was["call"], was["units"], was_kind) == ("PLAY", 0.5, None)
            assert (now["call"], now["units"], now_kind) == ("PASS", 0, KIND)
            assert "exec < 4pp half units" in x["tags"] and "exec ≤ 0 pass" in y["tags"]
    assert changed > 0                                     # the battery holds rows the rule turns PASS


# ------------------------------------------------------------------------------ the arm's settlement (283) --

def test_the_arm_reads_an_exec_non_positive_close_as_a_flip_exited_before_kickoff(chain, tmp_path):
    """Item 1: "the arm's settlement reading (a PASS at the close under 283 → exit pre-kickoff, as written)". The
    closing page's Desk block is the one this Desk writes for a row at exec <= 0 (PASS exec_non_positive, no order,
    its exec block kept); early_arm reads the page's call, so an early lot on that game is an arm flip, its sale before
    kickoff the pre-kickoff exit (test_early_arm's synthetic world: fictional clubs and ticker, invented figures)."""
    from src.walters import early_arm as ea
    from tests import test_early_arm as tea
    row, _ = at_exec("Bears", -0.002)
    desk = _annotate("nfl", [row])["predictions"][0]["desk"]
    assert (desk["call"], desk["pass_kind"], desk["order"]) == ("PASS", KIND, None)
    page = tea.row()
    page["desk"] = desk
    f = tea.entry(closed="2026-11-08T13:10:00Z", exit_=tea.EXIT_, close_fee=0.0101)    # sold before kickoff
    a, _, _ = tea.one(tmp_path, page, f)
    assert a["arm"] == ea.ARM_FLIP and a["closing_call"]["call"] == "PASS"
    assert a["flip_exit"] == "exited before kickoff" and not a["arm_breach"]
