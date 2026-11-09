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
imported, so the file runs against main and fails there.

Addendum 309 item 1 (ARCHITECT 2026-11-09 12:50 ET, RULED), verbatim: "the exec_non_positive check reads TWO figures
and PASSES on either: (i) the gate's exec edge as #87 (h) prices it (the order the PLAY would place at tier size),
exactly as 890c4271 has it; (ii) the exec edge re-priced at the units the order will actually carry after EVERY sizing
rule has run (the 4pp halving, INTL half, postseason), computed with the same fee formula. Either ≤ 0 → PASS
exec_non_positive, the reason naming the figure that failed (its all-in cost and the model's price; both when both
fail). A tightening only [...]. The exec block stays the gate's figures (h, the record), with the final order's cost
added beside it as its own field (`exec.final_cost`, `exec.final_edge_pp`, `exec.final_units`)". Its tests are the
section "addendum 309" below; the 305 pins at a 0.55 ask whose half order costs a cent more per contract than the full
one (0.017 vs 0.018) read both figures, so the +0.1 pin sits at a 0.50 ask, where the two orders cost the same."""
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


def calls(*rows, sport="nfl", counts=None):
    ev = dp.evaluate({"sport": sport, "predictions": [json.loads(json.dumps(r)) for r in rows]}, MS, counts)
    return {r["home"]: (r, c) for r, c in ev["calls"]}


def gate_only(c):
    """A call without addendum 309's final-order record (execFinal), to compare with the call before 305."""
    return {k: v for k, v in c.items() if k != "execFinal"}


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
    # addendum 309 item 1: the half order this PLAY would place (0.5u) costs 0.568, so both figures fail and both are named
    assert dp.desk_cost_for(r, "HOME", 0.5)["cost"] == 0.568
    assert c["reasons"] == [f"exec edge -0.20pp at the gate's order (1u): ask + taker fee {cost:.3f}, and -0.30pp at the "
                            f"order placed (0.5u): ask + taker fee 0.568, both at or above the model's {p:.3f} → PASS "
                            f"({RULING})"]
    assert c["tags"] == ["exec ≤ 0 pass"]                                   # nothing sized: no sizing tag stays
    assert c["execUnits"] == 1                                              # priced at the order it would have placed


def test_exec_plus_point_one_stays_half_units(chain):
    row, _ = at_exec("Thin", 0.001, ask=0.50)                               # the 0.5u order costs the 1u order's
    _, c = calls(row)["Thin"]
    assert (c["call"], c["units"], c["passKind"]) == ("PLAY", 0.5, None)
    assert "exec < 4pp half units" in c["tags"] and any("exec edge 0.1pp < 4pp" in x for x in c["reasons"])
    with _off():
        _, b = calls(row)["Thin"]
    assert b == gate_only(c)                                                # unchanged by 305


def test_exec_plus_four_stays_full_units(chain):
    row, _ = at_exec("Clear", 0.04)
    _, c = calls(row)["Clear"]
    assert (c["call"], c["units"], c["passKind"]) == ("PLAY", 1, None) and "exec clears" in c["tags"]
    with _off():
        _, b = calls(row)["Clear"]
    assert b == gate_only(c)


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
    assert c["reasons"][0].startswith("exec edge -1.00pp at the gate's order (1u): ask + taker fee ")


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
    b, _ = at_exec("Thin", 0.001, comp="MLB", ask=0.50, match_id=2)
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
    thin, _ = at_exec("Thin", 0.001, ask=0.50, match_id=2)
    doc = _annotate("nfl", [neg, thin])
    d = {r["home_team"]: (r, r["desk"]) for r in doc["predictions"]}
    for home in ("Bears", "Thin"):
        assert (d[home][1]["call"], d[home][1]["pass_kind"]) == ("PASS", "market_only")
    h = d["Bears"][1]["market_only_hold"]
    assert (h["would_call"], h["would_units"], h["would_pass_kind"]) == ("PASS", 0, KIND)
    assert h["would_reason"].startswith("exec edge -0.20pp at the gate's order (1u): ask + taker fee ")
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
        on_calls = [gate_only(c) for d in docs for _, c in dp.evaluate(d, now_ms, counts)["calls"]]
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


# ------------------------------------------------------- addendum 309 item 1: the gate's order and the order placed --

FINAL = ("final_cost", "final_edge_pp", "final_units")


def gap_row(home="Gap", ask=0.55, p=0.5675, **kw):
    """The ruling's case: NFL at ask 0.55, model 0.5675, fair edge 6pp. The gate prices the 1u order (the fee rounded
    once per fill: 0.017 a contract, all-in 0.567, exec +0.05pp); the 4pp halving places a 0.5u order (0.018 a
    contract, all-in 0.568, exec -0.05pp)."""
    return pred(home, p, round(p - 0.06, 4), bid=round(ask - 0.01, 2), ask=ask, **kw)


def intl_row(home="Probeland", p=0.5675, ask=0.55, mid=115001):
    """A UNL model row (sport INTL) on the laptop, a PLAY: tests/test_desk_host_fence.py's intl_unl shape, the HOME
    pick at fair edge 6pp."""
    from src.walters import intl_production as ip
    from src.walters.venue import kalshi_exec
    probs, fair = (p, 0.25, round(0.75 - p, 4)), (round(p - 0.06, 4), 0.28, round(0.78 - p, 4))
    r = {"match_id": mid, "home_team": home, "away_team": f"{home} B", "utc_date": "2026-11-14T19:00:00",
         "competition": "UNL", "venue_flag": "home",
         "prediction": {"probabilities": {"home_win": probs[0], "draw": probs[1], "away_win": probs[2]}, "tier": None},
         "market": {"bookmaker_count": 8, "fair_prob": {"HOME": fair[0], "DRAW": fair[1], "AWAY": fair[2]},
                    "fair_source": "1X2"},
         "market_divergence_pp": ip.divergence_pp(probs[0], {"fair_source": "1X2", "fair_prob": {"HOME": fair[0]}})}
    r["quarantine"] = abs(r["market_divergence_pp"]) >= 15
    r.update(kalshi_exec(round(ask - 0.01, 2), ask, "UNL", two_way=False))
    return r


def test_309_gate_plus_final_minus_at_ask_0_55_is_a_pass_naming_the_final_order(chain):
    """The ruling's case: gate +0.05pp (1u), final -0.05pp (0.5u) → PASS exec_non_positive; the reason names the order
    placed (its all-in cost and the model's price)."""
    row = gap_row()
    r, c = calls(row)["Gap"]
    gate, final = dp.exec_edge_pp(r, "HOME", r["prob"], 1), dp.exec_edge_pp(r, "HOME", r["prob"], 0.5)
    assert abs(gate - 0.05) < 1e-9 and abs(final + 0.05) < 1e-9
    assert (dp.desk_cost_for(r, "HOME", 1)["cost"], dp.desk_cost_for(r, "HOME", 0.5)["cost"]) == (0.567, 0.568)
    assert (c["call"], c["units"], c["cls"], c["passKind"], c["shadowUnits"]) == ("PASS", 0, "pass", KIND, 0)
    assert c["reasons"] == [f"exec edge +0.05pp at the gate's order but -0.05pp at the order placed (0.5u): ask + "
                            f"taker fee 0.568 at or above the model's 0.5675 → PASS ({RULING})"]
    assert c["tags"] == ["exec ≤ 0 pass"] and c["execUnits"] == 1
    with _off():                                                            # before 305: a half-unit PLAY
        _, b = calls(row)["Gap"]
    assert (b["call"], b["units"], b["passKind"]) == ("PLAY", 0.5, None)
    d = _annotate("nfl", [row])["predictions"][0]["desk"]
    assert (d["call"], d["units"], d["pass_kind"], d["order"]) == ("PASS", 0, KIND, None)
    ex = d["exec"]                                                          # the gate's figures stay (h, the record)
    assert ex["cost"] == 0.567 and abs(ex["edge_pp"] - 0.05) < 1e-9
    assert (ex["final_cost"], ex["final_units"]) == (0.568, 0.5) and abs(ex["final_edge_pp"] + 0.05) < 1e-9


def test_309_the_reverse_case_gate_non_positive_final_positive_is_a_pass_by_the_gate(chain):
    """Gate <= 0, final > 0 (at ask 0.60 the 0.5u order costs a tenth of a cent less a contract: 0.616 vs 0.617): PASS
    by read (i), the reason naming the gate's figure (its order, cost and the model's price); a negative gate edge never
    becomes a PLAY because the half order prices cheaper."""
    row = gap_row("Rev", ask=0.60, p=0.6165)
    r, c = calls(row)["Rev"]
    assert (dp.desk_cost_for(r, "HOME", 1)["cost"], dp.desk_cost_for(r, "HOME", 0.5)["cost"]) == (0.617, 0.616)
    assert dp.exec_edge_pp(r, "HOME", r["prob"], 1) < 0 < dp.exec_edge_pp(r, "HOME", r["prob"], 0.5)
    assert (c["call"], c["units"], c["passKind"]) == ("PASS", 0, KIND)
    assert c["reasons"] == [f"exec edge -0.05pp at the gate's order (1u): ask + taker fee 0.617 at or above the "
                            f"model's 0.6165 → PASS ({RULING})"]
    ex = _annotate("nfl", [row])["predictions"][0]["desk"]["exec"]
    assert ex["cost"] == 0.617 and ex["edge_pp"] < 0                       # the gate's figure, the one that failed
    assert (ex["final_cost"], ex["final_units"]) == (0.616, 0.5) and ex["final_edge_pp"] > 0


def test_309_intl_half_size(chain):
    """INTL halves after the gate (until 30 graded): the order placed is 0.5u. A row the gate clears (exec >= 4pp) is a
    half-unit PLAY whose final figures are the 0.5u order's; the ruling's 0.5675 row at ask 0.55 is a PASS by read
    (ii), named at the 0.5u order."""
    clear = intl_row("Clearland", p=0.62, mid=1)
    gap = intl_row("Gapland", mid=2)
    got = calls(clear, gap, sport="intl")
    r, c = got["Clearland"]
    assert (c["call"], c["units"], c["execUnits"]) == ("PLAY", 0.5, 1) and "intl half units" in c["tags"]
    assert "exec clears" in c["tags"]                                       # the 4pp line read at the gate's order
    assert c["execFinal"] == {"units": 0.5, "cost": dp.desk_cost_for(r, "HOME", 0.5)["cost"],
                              "edge_pp": dp.exec_edge_pp(r, "HOME", r["prob"], 0.5)}
    _, g = got["Gapland"]
    assert (g["call"], g["units"], g["passKind"]) == ("PASS", 0, KIND)
    assert g["reasons"] == [f"exec edge +0.05pp at the gate's order but -0.05pp at the order placed (0.5u): ask + "
                            f"taker fee 0.568 at or above the model's 0.5675 → PASS ({RULING})"]
    with _off():
        _, b = calls(clear, gap, sport="intl")["Gapland"]
    assert (b["call"], b["units"]) == ("PLAY", 0.5)
    _, done = calls(clear, sport="intl", counts={dp.INTL_COUNT_KEY: 30})["Clearland"]
    assert (done["call"], done["units"], done["execFinal"]["units"]) == ("PLAY", 1, 1)   # 30 graded: no INTL half


def test_309_postseason_half_is_priced_by_the_gate_and_the_final_check_alike(chain):
    """The postseason half runs before the gate, so the gate already prices the 0.5u order and the final order is the
    same order: the 0.5675 row at ask 0.55 fails both figures (each -0.05pp at 0.5u) and the reason names both."""
    row = gap_row("Post", stage="postseason")
    r, c = calls(row)["Post"]
    assert c["execUnits"] == 0.5 and (c["call"], c["units"], c["passKind"]) == ("PASS", 0, KIND)
    assert c["reasons"] == [f"exec edge -0.05pp at the gate's order (0.5u): ask + taker fee 0.568, and -0.05pp at the "
                            f"order placed (0.5u): ask + taker fee 0.568, both at or above the model's 0.5675 → PASS "
                            f"({RULING})"]
    ok = gap_row("PostOk", p=0.59, stage="postseason")
    _, c2 = calls(ok)["PostOk"]
    assert (c2["call"], c2["units"], c2["execUnits"], c2["execFinal"]["units"]) == ("PLAY", 0.5, 0.5, 0.5)
    assert c2["execFinal"]["edge_pp"] == dp.exec_edge_pp(dp.normalize({"sport": "nfl", "predictions": [ok]})[0],
                                                         "HOME", 0.59, 0.5)


def test_309_the_4pp_line_and_h_are_untouched(chain):
    """A +4pp row stays full (the 4pp line reads the gate's order); a half-unit row keeps the gate's figures at 1u and
    its emitted order's cost (order_cost) beside them; the final figures equal the order's. Every gate field of the exec
    block is the rule-off block's, byte for byte."""
    full, _ = at_exec("Clear", 0.04)
    half, _ = at_exec("Half", 0.02)
    on = {r["home_team"]: r["desk"] for r in _annotate("nfl", [full, half])["predictions"]}
    with _off():
        off = {r["home_team"]: r["desk"] for r in _annotate("nfl", [full, half])["predictions"]}
    for home in ("Clear", "Half"):
        assert {k: v for k, v in on[home]["exec"].items() if k not in FINAL} == off[home]["exec"]
        assert not any(k in off[home]["exec"] for k in FINAL)
        assert (on[home]["call"], on[home]["units"]) == (off[home]["call"], off[home]["units"])
    assert (on["Clear"]["units"], on["Clear"]["exec"]["final_units"]) == (1, 1)
    assert on["Clear"]["exec"]["final_edge_pp"] == on["Clear"]["exec"]["edge_pp"] >= 4
    h = on["Half"]["exec"]
    assert (on["Half"]["units"], h["final_units"], h["final_cost"]) == (0.5, 0.5, h["order_cost"])


def test_309_final_fields_ride_every_gated_row_and_only_those(chain):
    """Written for every PLAY that reaches the final check and on the PASS it causes; not on a quarantine shadow (never
    gated) nor with the rule off; the would-be record of an NFL market-only row carries them (its chain's own block)."""
    play, _ = at_exec("Play", 0.02)
    gap = gap_row()
    q, _ = at_exec("Quar", -0.01, market_divergence_pp=20.0, quarantine=True)
    d = {r["home_team"]: r["desk"] for r in _annotate("nfl", [play, gap, q])["predictions"]}
    assert all(k in d["Play"]["exec"] for k in FINAL) and all(k in d["Gap"]["exec"] for k in FINAL)
    assert d["Quar"]["exec"] is not None and not any(k in d["Quar"]["exec"] for k in FINAL)


def test_309_the_would_be_record_reads_the_final_order():
    """NFL market-only ON (production): the chain's own call at the ruling's case is PASS exec_non_positive (no would-be
    PLAY), and its exec block carries both figures."""
    import deploy.hosting.closing as closing
    doc = _annotate("nfl", [gap_row(match_id=1)])
    r = doc["predictions"][0]
    d = r["desk"]
    assert (d["call"], d["pass_kind"]) == ("PASS", "market_only")
    h = d["market_only_hold"]
    assert (h["would_call"], h["would_units"], h["would_pass_kind"]) == ("PASS", 0, KIND)
    assert h["would_reason"].startswith("exec edge +0.05pp at the gate's order but -0.05pp at the order placed (0.5u)")
    assert closing.would_be_for(r, d, "NFL", ("uncertified", "fixture")) is None and xc.would_be_play(d) is None
    assert (d["exec"]["final_units"], d["exec"]["final_cost"]) == (0.5, 0.568)
