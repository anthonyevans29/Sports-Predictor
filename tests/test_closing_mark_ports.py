"""#431 R7 + R13 (ARCHITECT 2026-10-20, addendum 145 item 3(b)): the Python ports follow the Cockpit's NOT EXECUTED
mark as they follow void_redated. R7: "matchFill prefers an unmarked call of the same game and side;
ledger_fills.match_fill moves with it." R13: "value_shadow_receipt.py, k_receipt.py and ledger_fills.py follow the
mark as they follow void_redated — those receipts are what I read, so parity ships with the mark." R10 keeps a marked
call "in executedPositions and clvLines, the claim-against-close read".

The mark is the Cockpit's contract (markClosings, tools/cockpit.html): c["not_executed"] = {"flag", "closing":
{family, start, run_id, as_of, file}, "closing_call": {text, calls}}; the ports read closing.family, closing.start
and closing_call.text, a missing key printing "?", and never crash on a mark of another shape."""
import copy
import json

from src.walters import desk_policy
from src.walters import k_receipt as K
from src.walters import ledger_fills as P
from tests.test_k_track_receipt import HI, LO, _ledger
from tests.test_value_shadow_receipt import call, kept, run

# the contract shape, as markClosings writes it: deterministic, no clock field
MARK = {"flag": "not executed (#431)",
        "closing": {"family": "NFL", "start": "2095-09-28T17:00:00Z", "run_id": "20950928T162500Z-nfl",
                    "as_of": "2095-09-28T16:25:00Z", "file": "closing_NFL_2095-09-28T1700Z.json"},
        "closing_call": {"text": "VENUE Kansas City Chiefs 1u", "calls": ["venue_edge|straight|HOME"]}}
VOID = "void: re-dated 2095-09-28 17:00Z → 2095-09-29 17:00Z"
NE_LINE = ("  not executed: {} (#431: the closing page did not repeat them; out of the reconciliation, kept in the CLV "
           "above)")
VS_NE_LINE = ("not executed: {} (#431: the closing page did not repeat them; out of every total and the n/30; marked, "
              "never deleted)")


def _pair():
    """c1 (graded, a close, the fill's call today) marked; an unmarked venue call on the same game and side after it:
    the closing page's own call, executed."""
    L = _ledger()
    L["calls"][0]["not_executed"] = copy.deepcopy(MARK)
    v = {**L["calls"][0], "id": "v1", "engine": "venue_edge", "tier": "venue"}
    del v["not_executed"]
    L["calls"].append(v)
    return L


def test_the_mark_is_the_cockpits_contract_shape_and_reads_back_whole():
    c = {"not_executed": copy.deepcopy(MARK)}
    assert set(MARK) == {"flag", "closing", "closing_call"}
    assert set(MARK["closing"]) == {"family", "start", "run_id", "as_of", "file"}
    assert set(MARK["closing_call"]) == {"text", "calls"}
    assert P.not_executed_closing(c) == "closing NFL 2095-09-28T17:00:00Z: VENUE Kansas City Chiefs 1u"
    assert json.loads(json.dumps(c)) == c                                      # a JSON round trip changes nothing


def test_a_mark_of_another_shape_reads_question_marks_and_never_crashes():
    for m in (True, "not executed", {"flag": "not executed (#431)"},
              {"closing": "NFL|2095-09-28T17:00:00Z", "closing_call": "PASS"},          # an earlier draft's shape
              {"closing": {"family": "NFL"}, "closing_call": {"calls": []}},
              {"closing": {"family": None, "start": ""}, "closing_call": {"text": None}}):
        line = P.not_executed_closing({"not_executed": m})
        assert line.startswith("closing ") and "?" in line
    assert P.not_executed_closing({"not_executed": "x"}) == "closing ? ?: ?"
    assert P.not_executed_closing({"not_executed": {"closing": {"family": "NFL"}}}) == "closing NFL ?: ?"
    L = _ledger()
    L["calls"][0]["not_executed"] = {"closing": "NFL|2095-09-28T17:00:00Z", "closing_call": "PASS"}
    txt = K.format_fills(L, LO, HI)
    assert "- NOT EXECUTED NFL Buffalo Bills @ Kansas City Chiefs · straight HOME · closing ? ?: ?" in txt
    V = kept()
    call(V, "Chicago Bears")["not_executed"] = True
    out, _ = run(V)
    i = out.index(VS_NE_LINE.format(1))
    assert out[i + 1].endswith(" · NOT EXECUTED · closing ? ?: ?")


# ---- R7: the fill goes to the unmarked call ------------------------------------------------------------------------

def test_match_fill_prefers_the_unmarked_call_of_the_same_game_and_side_in_either_order():
    L = _pair()
    (f,) = P.classify_fills(L)
    assert f["call_id"] == "v1" and not f.get("ambiguous_calls")             # the tie lists the chosen group only
    L["calls"].reverse()
    (g,) = P.classify_fills(L)
    assert g["call_id"] == "v1" and not g.get("ambiguous_calls")             # order-free
    (p,) = P.executed_positions(L)["pos"]                                    # the executed call carries the CLV
    assert p["c"]["id"] == "v1" and abs(p["clv"] * 100 - 4.0) < 1e-9


def test_two_unmarked_calls_still_tie_and_a_marked_call_alone_keeps_its_fill_and_its_clv():
    L = _ledger()
    L["calls"].append({**L["calls"][0], "id": "v1", "engine": "venue_edge"})
    (f,) = P.classify_fills(L)
    assert f["call_id"] == "c1" and f["ambiguous_calls"] == ["c1", "v1"]     # unchanged
    M = _ledger()
    M["calls"][0]["not_executed"] = copy.deepcopy(MARK)
    (g,) = P.classify_fills(M)
    assert g["call_id"] == "c1"                                              # no unmarked candidate: the marked call
    (p,) = P.executed_positions(M)["pos"]                                    # R10: kept in executedPositions
    assert p["c"]["id"] == "c1" and abs(p["clv"] * 100 - 4.0) < 1e-9


# R7 x R2 (verify_ports #1): the drift cases of tests/test_cockpit_closing_marks.py, through the port
DRIFT_BASE = {"log_date": "2026-09-29", "sport": "MLB", "game": "New York Yankees @ Boston Red Sox",
              "home": "Boston Red Sox", "away": "New York Yankees", "status": "open", "pick": "HOME", "tier": "lean",
              "call_type": "straight", "units": 1}
DRIFT_FILL = {"id": "f", "ticker": "KXMLBGAME-26SEP291305NYYBOS-BOS", "side": "yes", "qty": 3, "entry": 0.55,
              "title": "Boston wins — New York Yankees"}                  # 13:05 ET = 17:05Z, YES on Boston (home)


def _drift(calls, fill=DRIFT_FILL):
    (f,) = P.classify_fills({"calls": calls, "fills": [fill]})
    return [f.get("call_id"), f.get("ambiguous_calls")]


def test_match_fill_prefers_the_unmarked_call_of_the_same_game_when_kickoffs_drift_within_the_hour():
    """R7 under R2: kickoffs within DESK_CLOCK_DRIFT (1 h, inclusive) are one game, so when every real call of the
    nearest start's group is marked, the unmarked side-agreeing call within the hour of it takes the fill (probe
    r7drift.py: the marked claim at 17:05Z, the unmarked call at 17:10Z, the fill went to the marked one). Either
    order; at exactly the hour; past it, another game; two unmarked calls within the hour still tie; the 3h
    doubleheader rule stands; the ladder too."""
    assert P.REDATED_DRIFT_S == desk_policy.DESK_CLOCK_DRIFT.total_seconds() == 3600
    m = {**DRIFT_BASE, "id": "m", "engine": "model_edge", "kickoff": "2026-09-29T17:05:00",
         "not_executed": copy.deepcopy(MARK)}

    def u(k, i="u"):
        return {**DRIFT_BASE, "id": i, "engine": "venue_edge", "kickoff": k}
    for k in ("2026-09-29T17:10:00", "2026-09-29T16:05:00", "2026-09-29T18:05:00", "2026-09-29T17:05:00"):
        assert _drift([m, u(k)]) == _drift([u(k), m]) == ["u", None], k
    assert _drift([m, u("2026-09-29T18:06:00")]) == _drift([u("2026-09-29T18:06:00"), m]) == ["m", None]
    assert _drift([m, u("2026-09-29T17:10:00", "u1"), u("2026-09-29T17:20:00", "u2")]) == ["u1", ["u1", "u2"]]
    # the 3h doubleheader rule stands: within the hour of the marked call, but past 3h of the ticker's start
    assert _drift([{**m, "kickoff": "2026-09-29T19:35:00"}, u("2026-09-29T20:20:00")]) == ["m", None]
    lb = {"log_date": "2026-10-19", "sport": "SOCCER", "game": "Chelsea @ Arsenal", "home": "Arsenal",
          "away": "Chelsea", "three_way": True, "status": "open", "pick": "AWAY", "tier": "lean",
          "engine": "model_edge", "call_type": "ladder", "units": 0.5}
    lm = {**lb, "id": "lm", "kickoff": "2026-10-19T19:00:00", "not_executed": copy.deepcopy(MARK)}
    lu = {**lb, "id": "lu", "kickoff": "2026-10-19T19:15:00"}
    fl = {"id": "n", "ticker": "KXEPLGAME-26OCT191500CHEARS-ARS", "side": "no", "qty": 2, "entry": 0.5,
          "title": "Arsenal wins — Chelsea"}                              # 15:00 ET = 19:00Z, NO on Arsenal
    assert _drift([lm, lu], fl) == _drift([lu, lm], fl) == ["lu", None]
    assert _drift([lm], fl) == ["lm", None]


def test_the_composite_ladder_branch_prefers_the_unmarked_ladder():
    lad = {"id": "lm", "log_date": "2026-09-27", "sport": "SOCCER", "game": "Chelsea @ Arsenal", "home": "Arsenal",
           "away": "Chelsea", "kickoff": "2026-09-27T14:00:00", "status": "open", "pick": "AWAY", "tier": "lean",
           "engine": "model_edge", "call_type": "ladder", "units": 1, "not_executed": copy.deepcopy(MARK)}
    un = {**lad, "id": "lu"}
    del un["not_executed"]
    fill = {"id": "n", "ticker": "KXEPLGAME-26SEP27CHEARS-ARS", "side": "no", "qty": 2, "entry": 0.5,
            "title": "Arsenal wins — Chelsea"}
    for calls in ([lad, un], [un, lad]):
        (f,) = P.classify_fills({"calls": calls, "fills": [fill]})
        assert f["call_id"] == "lu" and f["composite"] and not f.get("ambiguous_calls")
    (g,) = P.classify_fills({"calls": [lad], "fills": [fill]})
    assert g["call_id"] == "lm"                                              # the marked ladder alone keeps it


# ---- R13: the K-track receipt -------------------------------------------------------------------------------------

def test_the_k_receipt_leaves_a_marked_call_out_of_the_reconciliation_keeps_its_clv_and_counts_it():
    M = _ledger()
    M["calls"][0]["not_executed"] = copy.deepcopy(MARK)
    rec = K.reconcile(M, LO, HI)
    assert "c1" not in {r["call_id"] for r in rec["rows"]} and rec["funnel"]["eligible"] == 2
    assert rec["ledger"]["matched_not_executed"] == 1 and rec["ledger"]["matched_outside_window"] == 0
    assert [c["id"] for c in K.not_executed_calls(M, LO, HI)] == ["c1"]
    txt = K.format_fills(M, LO, HI)
    assert "  system_matched in window: 0 (outside window 0; on a not-executed call 1) · qty 0" in txt[1]
    assert ("- NFL Buffalo Bills @ Kansas City Chiefs · 2095-09-28 · pick HOME · qty 10 · entry CLV +4.00pp · "
            "fee-adj +2.30pp (open_fee) · NOT EXECUTED (#431)") in txt         # R10: still in the CLV rows
    assert ("  mean entry CLV +4.00pp (n 1) · mean fee-adj +2.30pp (n 1) · execution evidence, not evidence of edge "
            "(#75)") in txt
    assert not any("outside the window" in x for x in txt)
    j = txt.index("  legacy join 0 of the eligible calls (paired with its result by the Cockpit's ±1-day team join: "
                  "no match id, logged before the field; addendum 109 item 2)")
    assert txt[j + 1] == NE_LINE.format(1)                                   # after the legacy-join line
    assert txt[j + 2] == ("- NOT EXECUTED NFL Buffalo Bills @ Kansas City Chiefs · straight HOME · closing NFL "
                          "2095-09-28T17:00:00Z: VENUE Kansas City Chiefs 1u")
    assert "UNAVAILABLE 1 · UNATTEMPTED 0 · ATTEMPTED_UNFILLED 0 · MATCHED 0 · UNKNOWN 1" in "\n".join(txt)
    base = K.format_fills(_ledger(), LO, HI)
    assert NE_LINE.format(0) in base and not any(x.startswith("- NOT EXECUTED") for x in base)
    assert not any("NOT EXECUTED (#431)" in x for x in base)


def test_the_k_receipt_lists_a_marked_call_that_is_also_void_as_void_only():
    L = _ledger()
    L["calls"].append({**L["calls"][1], "id": "c6", "game": "Bills @ Jets", "home": "New York Jets",
                       "away": "Buffalo Bills", "status": "void", "void_redated": VOID,
                       "not_executed": copy.deepcopy(MARK)})
    assert K.not_executed_calls(L, LO, HI) == []
    rec = K.reconcile(L, LO, HI)
    assert rec["funnel"]["eligible"] == 3 and rec["ledger"]["matched_not_executed"] == 0
    txt = K.format_fills(L, LO, HI)
    i = txt.index("  void: re-dated 1 · placeholder kickoff 0 (out of the reconciliation and the CLV)")
    assert txt[i + 1] == f"- VOID NFL Bills @ Jets · straight HOME · {VOID}"
    assert txt[i + 2].startswith("  legacy join 0 of the eligible calls")  # tests/test_void_redated.py's pin holds
    assert txt[i + 3] == NE_LINE.format(0)
    assert not any(x.startswith("- NOT EXECUTED") for x in txt)


# ---- R13: the value-shadow receipt --------------------------------------------------------------------------------

def _vs_mark():
    m = copy.deepcopy(MARK)
    m["closing"].update(start="2091-10-16T18:00:00Z", run_id="20911016T172500Z-nfl", as_of="2091-10-16T17:25:00Z",
                        file="closing_NFL_2091-10-16T1800Z.json")
    m["closing_call"] = {"text": "PASS", "calls": []}
    return m


def test_the_value_shadow_receipt_leaves_a_marked_shadow_out_of_the_totals_and_the_n30_on_the_kept_ledger():
    L = kept()
    c = call(L, "Chicago Bears")                                   # graded win, close 0.372, net +0.4542u
    c["not_executed"] = _vs_mark()
    out, res = run(L)
    assert ("  all value shadows: n 4 · graded 3 · record won 1 · lost 1 · push 1 · void 0 · ungraded 1 · "
            "units net +0.4259u over 3 settled (notional 0.75u)") in out
    assert ("  the rows with a close only: n 2 · graded 2 · record won 1 · lost 0 · push 1 · void 0 · "
            "ungraded 0 · units net +0.6759u over 2 settled (notional 0.5u)") in out
    assert not any("Chicago Bears" in o for o in out if o.startswith("  2") and "NOT EXECUTED" not in o)
    i = out.index(VS_NE_LINE.format(1))
    assert out[i - 1].startswith("legacy join 0 (")
    assert out[i + 1] == ("  2091-10-16 18:00 · NFL · Philadelphia Eagles @ Chicago Bears · HOME (Chicago Bears) · "
                          "edge +13.4pp (claim) · close 0.372 · won · 0.25u, net +0.4542u · NOT EXECUTED · "
                          "closing NFL 2091-10-16T18:00:00Z: PASS")                   # the claim's own numbers stay
    assert out[-2] == ("n/30: the policy card's counter (every value shadow with a result) 3 of 30 · the P&L block's "
                       "(its settled rows, the kickoff audit applied) 3 of 30")        # still the second-last line
    js = json.loads(out[-1].removeprefix("VALUE-SHADOW-RECEIPT "))
    assert js["not_executed"] == 1 and js["n_of_30"] == "3 of 30" and js["n_of_30_pnl"] == "3 of 30"
    assert js["all"]["units_net"] == 0.4259 and res["not_executed"][0]["id"] == c["id"]
    out0, _ = run(kept())
    assert VS_NE_LINE.format(0) in out0
    assert json.loads(out0[-1].removeprefix("VALUE-SHADOW-RECEIPT "))["not_executed"] == 0


def test_the_value_shadow_receipt_lists_a_marked_void_shadow_as_void_only_and_a_marked_staked_call_apart():
    L = kept()
    c = call(L, "Green Bay Packers")                               # the kept ledger's open shadow
    c.update(status="void", void_redated=VOID, not_executed=_vs_mark())
    out, _ = run(L)
    assert "void: re-dated 1 · placeholder kickoff 0" in "\n".join(out) and VS_NE_LINE.format(0) in out
    assert not any("NOT EXECUTED" in o for o in out)
    S = kept()
    st = next(x for x in S["calls"] if x["call_type"] == "straight")    # the Buffalo straight, staked by the label
    st.update(note="value shadow, staked", not_executed=_vs_mark())
    out, res = run(S)
    assert res["other_staked"] == [] and len(res["not_executed"]) == 1
    i = out.index(VS_NE_LINE.format(1))
    assert out[i + 1].endswith(" · NOT EXECUTED · closing NFL 2091-10-16T18:00:00Z: PASS · call_type straight")


def test_a_ledger_whose_only_value_shadow_is_marked_is_not_read_as_none():
    L = kept()
    keep = call(L, "Chicago Bears")
    keep["not_executed"] = _vs_mark()
    L["calls"] = [keep]
    out, res = run(L)
    assert not any(o.startswith("VALUE SHADOWS: none") for o in out)
    assert res["rows"] == [] and len(res["not_executed"]) == 1
    assert out[-2].startswith("n/30: the policy card's counter (every value shadow with a result) 0 of 30")


# ---- R13: the cross-language contract -----------------------------------------------------------------------------

def test_r13_the_mark_the_cockpit_writes_reads_back_whole_through_the_three_ports(tmp_path):
    """R13, the contract pinned across the two languages (SPEC_V2: "A cross-language test builds a mark through the
    Cockpit's own markClosings under node and feeds the ledger to the three ports"). The page's own loadDocs takes the
    morning slate, then its closing (Tampa at the books' price: the page calls no value shadow there); the stored
    ledger is dumped as the Export writes it and read by ledger_fills, k_receipt and value_shadow_receipt. Each port's
    line is exactly "closing {family} {start}: {text}" from the mark the page wrote, never a "?" (a key the port did not
    find, the shape drifted). A Kalshi fill on a marked claim keeps it an executed position (R10). Skipped without
    node (the page runs under it, as tests/test_cockpit_closing_marks.py)."""
    from datetime import datetime

    import scripts.value_shadow_receipt as vsr
    from tests.test_cockpit_closing_marks import CLOSING_NAME, DVDEN, SLATE_NAME, _node, closing, slate
    L = _node(tmp_path, r'''
await loadDocs([T_doc(SN,S)]); await loadDocs([T_doc(CN,C)]);
T_out(JSON.parse(T_stored()));''', S=slate(), C=closing(Tampa=0.70), SN=SLATE_NAME, CN=CLOSING_NAME)
    marked = [c for c in L["calls"] if c.get("not_executed")]
    assert sorted((c["home"], c["call_type"], c["pick"]) for c in marked) == [
        ("Dallas", "straight", "HOME"), ("Denver", "straight", "HOME"), ("Miami", "straight", "HOME"),
        ("Tampa", "value_shadow", "AWAY")]
    lines = {}
    for c in marked:
        m = c["not_executed"]
        assert set(m) == {"flag", "closing", "closing_call"} and m["flag"] == "not executed (#431)"
        assert set(m["closing"]) == {"family", "start", "run_id", "as_of", "file"}
        assert set(m["closing_call"]) == {"text", "calls"}
        want = f"closing {m['closing']['family']} {m['closing']['start']}: {m['closing_call']['text']}"
        assert "?" not in want and want.startswith("closing NFL 2026-10-19T17:00:00Z: ")
        assert P.not_executed_closing(c) == want                                 # ledger_fills
        lines[c["id"]] = want
    k = K.format_fills(L, datetime(2026, 10, 18), datetime(2026, 10, 21))      # k_receipt
    ks = [x for x in k if x.startswith("- NOT EXECUTED ")]
    assert k[k.index(ks[0]) - 1].startswith("  not executed: 3 (#431")
    assert sorted(ks) == sorted(f"- NOT EXECUTED {c['sport']} {c['game']} · {c['call_type']} {c['pick']} · "
                                f"{lines[c['id']]}" for c in marked if c["call_type"] == "straight")
    out = []                                                                   # value_shadow_receipt
    res = vsr.report(copy.deepcopy(L), "bd_ledger_v1_xlang.json", echo=out.append)
    (tampa,) = [c for c in marked if c["call_type"] == "value_shadow"]
    (vl,) = [o for o in out if o.endswith(" · NOT EXECUTED · " + lines[tampa["id"]])]
    assert "Tampa Visitors @ Tampa" in vl and [r["id"] for r in res["not_executed"]] == [tampa["id"]]
    assert not any("?" in o for o in out + k if "NOT EXECUTED" in o)
    # R10 through the port: a fill on the marked Denver claim, graded with a close, stays an executed position
    den = next(c for c in marked if c["home"] == "Denver")
    den.update(status="graded", result="win", units_returned=1.9, graded_date="2026-10-19",
               close_ref={"version": "p0-3 v2", "q_close": 0.55, "fair": {"HOME": 0.55, "AWAY": 0.45}})
    L["fills"] = [{"id": "F1", "ticker": DVDEN, "side": "yes", "qty": 10, "entry": 0.5, "title": "", "open_fee": 0.02}]
    (f,) = P.classify_fills(L)
    assert f["call_id"] == den["id"] and not f.get("ambiguous_calls")
    (p,) = P.executed_positions(L)["pos"]
    assert p["c"]["id"] == den["id"] and abs(p["clv"] * 100 - 5.0) < 1e-9
