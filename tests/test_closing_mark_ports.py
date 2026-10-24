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


# ---- R16/R17: closing_positions, the port of the Cockpit's closingPositions ---------------------------------------
# ARCHITECT 2026-10-20, addendum 146 item 1(iv), verbatim: "R16 the ledger stores the page's ORDERED size and limit
# beside the FILLED size and entry; R17 each position carries entry minus the closing ask on its pick (true CLV, in
# cents) and the P&L view sums it beside the P&L". The sign CORRECTED (addendum 148 item 1(b)): "ask minus entry, + =
# bought below the close, the direction the page's existing CLV lines already use". Addendum 148 item 1(c)-(i), each
# default accepted. The cases are tests/test_cockpit_closing_marks.py's R17 cases (its R17_JS builders), through the
# port: the same numbers.

R17_U = "1u = 10 contracts (SP_UNIT_USD unset)"
R17_START = "2026-10-19T17:00:00Z"
R17_KEY = "model_edge|straight|HOME"
MISSING = object()


def _tk(h, side="HOME"):
    """R17_JS's TICK: the ticker the matcher parses for "<h> Visitors @ <h>" on 2026-10-19."""
    a, c = h[0] + "V", h[:3].upper()
    return f"KXNFLGAME-26OCT19{a}{c}-{a if side == 'AWAY' else c}"


def _legs(h, b, a):
    return {"HOME": {"ticker": _tk(h), "bid": b, "ask": a},
            "AWAY": {"ticker": _tk(h, "AWAY"), "bid": round(1 - a, 2), "ask": round(1 - b, 2)}}


def _o(ticker, side, limit, contracts):
    return {"ticker": ticker, "side": side, "limit": limit, "contracts": contracts, "unit": R17_U}


def _g(h, **o):
    """R17_JS's G: a stored game as putPage keeps it (legs at 52/53c, the PLAY's order YES 0.53 x 10); a key set to
    MISSING is left out (a page stored before R16/R17)."""
    g = {"sport": "NFL", "home": h, "away": h + " Visitors", "kickoff": "2026-10-19T17:00:00", "calls": [R17_KEY],
         "text": f"PLAY {h} 1u", "run_id": "20261019T162500Z-nfl", "as_of": "2026-10-19T16:25:00Z",
         "file": "closing_NFL_2026-10-19T1700Z.json", "legs": _legs(h, 0.52, 0.53),
         "orders": {R17_KEY: _o(_tk(h), "YES", 0.53, 10)}, **o}
    return {k: v for k, v in g.items() if v is not MISSING}


def _mk(h, **o):
    """R17_JS's T_mk (tests/test_cockpit_closing_marks.py T_BASE): an open NFL straight HOME claim of 2026-10-19."""
    c = {"id": f"c-{h}", "log_date": "2026-10-19", "sport": "NFL", "three_way": False, "status": "open", "tier": "lean",
         "engine": "model_edge", "call_type": "straight", "pick": "HOME", "units": 1, "model_p": 0.6, "market_p": 0.52,
         "kickoff": "2026-10-19T17:00:00", "claim_at": "2026-10-19T12:00:00.000Z", "home": h, "away": h + " Visitors",
         "game": f"{h} Visitors @ {h}", **o}
    return c


def _f(i, ticker, side, qty, entry):
    return {"id": i, "ticker": ticker, "side": side, "qty": qty, "entry": entry, "title": ""}


def _r17(calls, fills, games=(), more=()):
    """A ledger whose stored pages are `games` (one record, the 17:00Z start) and the records `more`; its positions."""
    cl = {}
    for start, gs in ((R17_START, games), *more):
        if gs:
            cl[f"NFL|{start}"] = {"family": "NFL", "start": start, "pages": {},
                                  "games": {f"{g['sport']}|{g['home']}|{g['away']}|{g['kickoff']}": g for g in gs}}
    L = {"meta": {"closings": cl}, "calls": calls, "fills": fills}
    return L, P.closing_positions(L)


def _r4(x):
    return None if x is None else round(x, 4)


def test_r17_the_port_prices_the_held_contracts_closing_ask_with_the_ruled_sign():
    """(f) YES on the pick's leg its ask; NO on the opponent 1 − its bid, rounded to 4 dp as the page's
    +(1-leg.bid).toFixed(4) (against an AWAY bid of 0.43: 0.57, never 0.5700000000000001, in the K-track line too); a
    ladder's NO on HOME the same; a ticker the page does not quote counted, not priced. (b) a 55c fill against a 53c closing ask is -2.0c, a 53c fill against
    55c +2.0c, through the port and the K-track receipt's line; a blend at the close prints +0.0c, never -0.0c. (c)
    4@0.55 + 6@0.53 against 0.53 is -0.8c; one unpriced fill leaves the position unpriced (null)."""
    def D():
        return [_mk("Denver", exec_order=None)]
    L55, (y55,) = _r17(D(), [_f("a", _tk("Denver"), "yes", 10, 0.55)], [_g("Denver")])
    L53, (y53,) = _r17(D(), [_f("a", _tk("Denver"), "yes", 10, 0.53)], [_g("Denver", legs=_legs("Denver", 0.54, 0.55))])
    assert (y55["asks"], _r4(y55["clv_c"]), y55["quote"]) == ([0.53], -2.0, "priced")
    assert (y53["asks"], _r4(y53["clv_c"])) == ([0.55], 2.0)
    (k55,), (k53,) = K.closing_clv_lines(L55, {"c-Denver"}), K.closing_clv_lines(L53, {"c-Denver"})
    assert " · straight HOME · -2.0c · filled 10 @ 0.5500 (1 fill(s); closing ask 0.53) · " in k55
    assert " · straight HOME · +2.0c · filled 10 @ 0.5300 (1 fill(s); closing ask 0.55) · " in k53
    _, (no,) = _r17(D(), [_f("a", _tk("Denver", "AWAY"), "no", 10, 0.50)], [_g("Denver")])
    assert (no["asks"], _r4(no["clv_c"])) == ([0.53], 3.0)                  # 1 − the AWAY leg's bid 0.47
    Lno, (no43,) = _r17(D(), [_f("a", _tk("Denver", "AWAY"), "no", 10, 0.50)],
                        [_g("Denver", legs=_legs("Denver", 0.56, 0.57))])        # AWAY bid round(1 - 0.57, 2) = 0.43
    assert no43["asks"] == [0.57] and _r4(no43["clv_c"]) == 7.0             # 1 − 0.43 unrounded: 0.5700000000000001
    (kno,) = K.closing_clv_lines(Lno, {"c-Denver"})
    assert " · straight HOME · +7.0c · filled 10 @ 0.5000 (1 fill(s); closing ask 0.57) · " in kno
    ars = "KXEPLGAME-26OCT19CHEARS-ARS"
    lad = _mk("Arsenal", id="L", sport="SOCCER", away="Chelsea", game="Chelsea @ Arsenal", three_way=True,
              call_type="ladder", pick="AWAY", units=0.5, kickoff="2026-10-19T19:00:00")
    lg = {"sport": "SOCCER", "home": "Arsenal", "away": "Chelsea", "kickoff": "2026-10-19T19:00:00",
          "calls": ["model_edge|ladder|AWAY"], "text": "LADDER Chelsea 0.5u", "run_id": "R", "as_of": "2026-10-19T18:25:00Z",
          "file": "f", "legs": {"HOME": {"ticker": ars, "bid": 0.40, "ask": 0.41}},
          "orders": {"model_edge|ladder|AWAY": _o(ars, "NO", 0.60, 5)}}
    _, (ld,) = _r17([lad], [_f("a", ars, "no", 5, 0.58)], more=[("2026-10-19T19:00:00Z", [lg])])
    assert {k: v for k, v in ld.items() if k != "c"} == {
        "id": "L", "status": "open", "cover": "page", "page": "closing", "legacy": False,   # the page's order read
        "ordered": _o(ars, "NO", 0.6, 5), "filled": {"contracts": 5, "entry": 0.58, "fills": 1}, "asks": [0.6],
        "quote": "priced", "clv_c": ld["clv_c"], "above_limit_c": None, "above_fills": 0, "over_size": False,
        "partial": False}
    assert _r4(ld["clv_c"]) == 2.0
    _, (q,) = _r17(D(), [_f("a", _tk("Denver"), "yes", 4, 0.55), _f("b", _tk("Denver"), "yes", 6, 0.53)], [_g("Denver")])
    assert _r4(q["clv_c"]) == -0.8 and {**q["filled"], "entry": _r4(q["filled"]["entry"])} == {
        "contracts": 10, "entry": 0.538, "fills": 2}
    _, (one,) = _r17(D(), [_f("a", _tk("Denver"), "yes", 4, 0.55),
                           _f("b", "KXNFLGAME-26OCT191300DVDEN-DEN", "yes", 6, 0.53)], [_g("Denver")])
    assert (one["asks"], one["quote"], one["clv_c"]) == ([0.53, None], "unpriced", None)
    Loff, (off,) = _r17(D(), [_f("a", _tk("Denver"), "yes", 10, 0.55)],
                        [_g("Denver", legs={"HOME": {"ticker": "KXNFLGAME-26OCT11-DENH", "bid": 0.52, "ask": 0.53}})])
    assert (off["asks"], off["quote"], off["clv_c"]) == ([None], "unpriced", None)
    lc = {"HOME": {"ticker": f" {_tk('Denver').lower()} ", "bid": 0.52, "ask": 0.53}}   # the page's T: trimmed, upper
    _, (tc,) = _r17(D(), [_f("a", _tk("Denver"), "yes", 10, 0.55)], [_g("Denver", legs=lc)])
    assert (tc["asks"], tc["quote"]) == ([0.53], "priced")
    assert K.closing_clv_lines(Loff, {"c-Denver"}) == []                    # not priced: no line (the Cockpit counts it)
    # a blend at the close: 5@0.28 + 5@0.32 against a 30c ask is 0 in cents, -2.8e-15 in floating point; the Cockpit's
    # c1 rounds first, so the receipt prints +0.0c, never -0.0c (as the page's line, its zero clvLines' "+0.00pp")
    Lz, (z,) = _r17(D(), [_f("a", _tk("Denver"), "yes", 5, 0.28), _f("b", _tk("Denver"), "yes", 5, 0.32)],
                    [_g("Denver", legs=_legs("Denver", 0.29, 0.30))])
    assert z["quote"] == "priced" and -1e-9 < z["clv_c"] < 0
    (kz,) = K.closing_clv_lines(Lz, {"c-Denver"})
    assert " · straight HOME · +0.0c · filled 10 @ 0.3000 (2 fill(s); closing ask 0.3, 0.3) · " in kz and "-0.0c" not in kz


def test_r17_the_port_counts_no_page_ambiguous_and_no_quote_and_never_prices_them():
    """No stored page: the slate's order (exec_order), or none (legacy: claimed before R16 stored one). Two covering
    pages (two starts within the hour): ambiguous, neither page's order nor quote read (law 4). (i) a page stored
    before this build, its legs and orders keys absent: "no closing quote stored", its order the slate's."""
    sl, f = _o(_tk("Denver"), "YES", 0.52, 10), [_f("a", _tk("Denver"), "yes", 10, 0.55)]
    _, (s,) = _r17([_mk("Denver", exec_order=sl)], f)
    assert (s["cover"], s["page"], s["quote"], s["clv_c"], s["ordered"]) == ("none", "slate", "no_page", None, sl)
    assert (s["above_limit_c"], s["above_fills"], s["legacy"]) == (3.0, 1, False)   # R16 reads the slate's limit
    _, (lg,) = _r17([_mk("Denver")], f)
    assert (lg["page"], lg["legacy"], lg["ordered"], lg["quote"]) == (None, True, None, "no_page")
    _, (two,) = _r17([_mk("Denver", exec_order=sl)], f, [_g("Denver")],
                     [("2026-10-19T17:30:00Z", [_g("Denver", kickoff="2026-10-19T17:30:00")])])
    assert (two["cover"], two["page"], two["ordered"], two["quote"], two["clv_c"], two["legacy"]) == \
        ("ambiguous", None, None, "ambiguous", None, False)
    _, (nq,) = _r17([_mk("Denver", exec_order=sl)], f, [_g("Denver", legs=MISSING, orders=MISSING)])
    assert (nq["cover"], nq["quote"], nq["page"], nq["clv_c"]) == ("page", "no_quote", "slate", None)
    _, (nl,) = _r17([_mk("Denver", exec_order=sl)], f, [_g("Denver", legs=None, orders={})])   # as putPage stores it
    assert {k: v for k, v in nl.items() if k != "c"} == {k: v for k, v in nq.items() if k != "c"}
    # JavaScript truthiness, as the page reads them: an empty legs object is a quote with no contract on it (counted
    # "on a contract the page does not quote", never "no closing quote stored"), and an empty order object is read
    for c in (_mk("Denver", exec_order=sl), _mk("Denver")):                 # with and without an exec_order key
        _, (em,) = _r17([c], f, [_g("Denver", legs={}, orders={R17_KEY: {}})])
        assert (em["quote"], em["page"], em["ordered"], em["legacy"], em["above_fills"]) == \
            ("unpriced", "closing", {}, False, 0)


def test_r17_the_port_reads_the_1c_shape_and_every_case_of_the_line_as_the_page_does():
    """The page's line test, case for case: where each order was read ((e): closing, slate, outside any page; a
    stored closing order wins over a different slate order), why one is not priced, and R16's flags ((g): two fills 2c
    above their page's limit, one partial, one over size; a position's largest excess, the fills counted, not the
    positions). The numbers by hand: tests/test_cockpit_closing_marks.py's 1(c) test."""
    def sl(h, lim, n):
        return _o(_tk(h), "YES", lim, n)
    # Denver's slate order (0.50 x 12) differs from its stored closing order (0.53 x 10): (e) reads the closing one
    # (the slate's would read 5.0c above and partial). Fresno: two fills above the 0.53 limit by 1.0c and 3.0c (its
    # max 3.0c, 2 fills; clv (5x(.53-.54) + 5x(.53-.56))/10 x100 = -2.0); Gilroy: one fill 1.0c above (clv -1.0)
    calls = [_mk("Denver", status="graded", result="win", exec_order=sl("Denver", 0.50, 12)),
             _mk("Buffalo", exec_order=None),
             _mk("Miami", exec_order=sl("Miami", 0.50, 10)), _mk("Dallas", exec_order=None),
             _mk("Newark", exec_order=None), _mk("Tampa", exec_order=None),
             _mk("Albany", exec_order=sl("Albany", 0.60, 3)), _mk("Lowell"), _mk("Camden", exec_order=None),
             _mk("Fresno", exec_order=None), _mk("Gilroy", exec_order=None)]
    fills = [_f("1", _tk("Denver"), "yes", 10, 0.55), _f("2", _tk("Buffalo"), "yes", 6, 0.55),
             _f("3", _tk("Miami"), "yes", 12, 0.50), _f("4", _tk("Dallas"), "yes", 5, 0.39),
             _f("5", _tk("Newark"), "yes", 10, 0.55), _f("6", _tk("Tampa"), "yes", 10, 0.70),
             _f("7", _tk("Albany"), "yes", 3, 0.60), _f("8", _tk("Lowell"), "yes", 10, 0.50),
             _f("9", "KXNFLGAME-26OCT191300CVCAM-CAM", "yes", 10, 0.45),
             _f("10", _tk("Fresno"), "yes", 5, 0.54), _f("11", _tk("Fresno"), "yes", 5, 0.56),
             _f("12", _tk("Gilroy"), "yes", 10, 0.54)]
    games = [_g("Denver"), _g("Buffalo"), _g("Miami", legs=_legs("Miami", 0.49, 0.50), orders={}),
             _g("Dallas", legs=_legs("Dallas", 0.40, 0.41), orders={}), _g("Newark"),
             _g("Tampa", legs=None, orders={R17_KEY: _o(_tk("Tampa"), "YES", 0.70, 10)}),
             _g("Camden", orders={R17_KEY: _o(_tk("Camden"), "YES", 0.45, 10)}), _g("Fresno"), _g("Gilroy")]
    L, ps = _r17(calls, fills, games, [("2026-10-19T17:30:00Z", [_g("Newark", kickoff="2026-10-19T17:30:00")])])
    by = {p["c"]["home"]: [p["page"], p["quote"], _r4(p["clv_c"]), _r4(p["above_limit_c"]), p["above_fills"],
                           p["over_size"], p["partial"]] for p in ps}
    assert by == {"Denver": ["closing", "priced", -2.0, 2.0, 1, False, False],       # tests/test_cockpit_closing_marks
                  "Buffalo": ["closing", "priced", -2.0, 2.0, 1, False, True],       # .py's expected values, verbatim
                  "Miami": ["slate", "priced", 0.0, None, 0, True, False],
                  "Dallas": [None, "priced", 2.0, None, 0, False, False],
                  "Newark": [None, "ambiguous", None, None, 0, False, False],
                  "Tampa": ["closing", "no_quote", None, None, 0, False, False],
                  "Albany": ["slate", "no_page", None, None, 0, False, False],
                  "Lowell": [None, "no_page", None, None, 0, False, False],
                  "Camden": ["closing", "unpriced", None, None, 0, False, False],
                  "Fresno": ["closing", "priced", -2.0, 3.0, 2, False, False],
                  "Gilroy": ["closing", "priced", -1.0, 1.0, 1, False, False]}
    assert [p["c"]["home"] for p in ps if p["legacy"]] == ["Lowell"]
    assert [p["status"] for p in ps].count("graded") == 1 and sum(p["filled"]["fills"] for p in ps) == 12
    assert next(p for p in ps if p["c"]["home"] == "Denver")["ordered"] == _o(_tk("Denver"), "YES", 0.53, 10)
    # the page's line numbers, from the port: K = 1 + 1 + 2 + 1 = 5 fills above (4 positions), max of the
    # positions' maxima [2.0, 2.0, 3.0, 1.0] = 3.0
    assert sum(p["above_fills"] for p in ps) == 5 and max(p["above_limit_c"] for p in ps if p["above_fills"]) == 3.0
    (kf,) = [x for x in K.closing_clv_lines(L, set()) if " Fresno Visitors @ Fresno " in x]
    assert " · straight HOME · -2.0c · filled 10 @ 0.5500 (2 fill(s); closing ask 0.53, 0.53) · ordered 10 @ 0.53 YES" \
        " (the closing page) · R16: 2 fill(s) above the limit (max +3.0c) · outside the window" in kf


def test_r17_the_port_keeps_open_and_graded_marked_or_not_and_never_a_shadow_a_ticket_a_void_or_a_manual_fill():
    """(d) every filled straight, VENUE or LADDER position matched to a call, open included, marked or not; a shadow,
    a ticket leg (R5), a void (re-dated) call and a manual Record fill ((h), Issue #634) are not positions; a fill with
    qty 0 or with no entry is not read."""
    f = [_f(h, _tk(h), "yes", 10, 0.55) for h in ("Denver", "Buffalo", "Miami", "Dallas", "Newark", "Tampa")]
    calls = [_mk("Denver", status="graded", result="win"), _mk("Buffalo", not_executed=copy.deepcopy(MARK)),
             _mk("Miami", engine="venue_edge", tier="shadow"),
             _mk("Dallas", call_type="quarantine_shadow", units=0, shadow_units=0.5),
             _mk("Newark", call_type="parlay_leg", parlay_id="P-2026-10-19-X", units=0.25),
             _mk("Tampa", void_redated="re-dated", status="void"),
             _mk("Albany", order_type="limit", fill_price=0.55, fill_recorded_at="2026-10-19T13:00:00.000Z"),
             # the filters read the call's kind and its void label, never only whether matchFill handed it a fill: a
             # value shadow carrying units (matchFill takes any non-quarantine call with units) and a void label on a
             # graded row are still no positions
             _mk("Reno", call_type="value_shadow", units=0.25), _mk("Provo", void_redated="re-dated", status="graded")]
    f += [_f(h, _tk(h), "yes", 10, 0.55) for h in ("Reno", "Provo")]
    # a fill with qty 0 and one with no entry (set in the ledger directly, not through the CSV import): not read
    f += [_f("Denver-q0", _tk("Denver"), "yes", 0, 0.40), _f("Denver-null", _tk("Denver"), "yes", 5, None)]
    by = {x["id"]: x.get("call_id") for x in P.classify_fills({"calls": calls, "fills": f})}
    assert (by["Reno"], by["Provo"], by["Denver-q0"], by["Denver-null"]) == ("c-Reno", "c-Provo", "c-Denver", "c-Denver")
    _, ps = _r17(calls, f, [_g(h) for h in ("Denver", "Buffalo", "Miami", "Dallas", "Newark", "Tampa", "Albany", "Reno",
                                            "Provo")])
    assert [(p["c"]["home"], p["status"]) for p in ps] == [("Denver", "graded"), ("Buffalo", "open"), ("Miami", "open")]
    assert ps[0]["filled"] == {"contracts": 10, "entry": 0.55, "fills": 1} and ps[0]["asks"] == [0.53]


def test_r17_the_k_receipt_prints_one_line_per_priced_position_after_the_clv_block_never_on_a_pinned_line():
    """ONE line per priced position, after the executed-position CLV block's last line and before the reconciliation;
    the lines the other tests pin keep their places (the legacy-join and not-executed pair). The page's order with
    R16's flags; a position outside the reconciliation's cohort printed and labelled; one not priced prints nothing."""
    KC, BUF = "KXNFLGAME-95SEP28BUFKC-KC", "KXNFLGAME-95SEP28BUFKC-BUF"
    L = _ledger()
    c1 = L["calls"][0]

    def game(c, kick, legs=True):
        return {"sport": "NFL", "home": c["home"], "away": c["away"], "kickoff": kick, "calls": [R17_KEY],
                "text": "PLAY", "run_id": "R", "as_of": kick[:10] + "T16:25:00Z", "file": "f",
                "legs": {"HOME": {"ticker": KC if kick.startswith("2095-09") else KC.replace("SEP28", "OCT12"),
                                  "bid": 0.61, "ask": 0.62}, "AWAY": {"ticker": BUF, "bid": 0.38, "ask": 0.39}}
                if legs else None, "orders": {R17_KEY: _o(KC, "YES", 0.57, 12)}}
    L["meta"]["closings"] = {"NFL|2095-09-28T17:00:00Z": {"family": "NFL", "start": "2095-09-28T17:00:00Z",
                                                          "pages": {}, "games": {"a": game(c1, "2095-09-28T17:00:00")}}}
    txt = K.format_fills(L, LO, HI)
    want = ("- CLOSING CLV (#431 R17, close − entry; + = beat the close) NFL Buffalo Bills @ Kansas City Chiefs · "
            "2095-09-28 · straight HOME · +4.0c · filled 10 @ 0.5800 (1 fill(s); closing ask 0.62) · ordered 12 @ 0.57 "
            "YES (the closing page) · R16: 1 fill(s) above the limit (max +1.0c) · partial")
    i = txt.index(want)
    assert txt[i - 1].startswith("  mean entry CLV +4.00pp (n 1)") and txt[i + 1].startswith("CALL-TO-FILL")
    assert [x for x in txt if x.startswith("- CLOSING CLV")] == [want]
    j = next(n for n, x in enumerate(txt) if x.startswith("  legacy join 0 of the eligible calls"))
    assert txt[j + 1] == NE_LINE.format(0)                                   # the pinned pair keeps its place
    base = K.format_fills(_ledger(), LO, HI)
    assert [x for x in txt if not x.startswith("- CLOSING CLV")] == base     # one line added, no other line changed
    # c5 (kickoff 2095-10-12) outside the window: printed, labelled; a page with no legs: not priced, no line
    c5 = L["calls"][4]
    L["fills"].append(dict(L["fills"][0], id="f5", ticker=KC.replace("SEP28", "OCT12")))
    c5.update(home=c1["home"], away=c1["away"], game=c1["game"])
    L["meta"]["closings"]["NFL|2095-10-12T17:00:00Z"] = {
        "family": "NFL", "start": "2095-10-12T17:00:00Z", "pages": {},
        "games": {"b": game(c5, "2095-10-12T17:00:00")}}
    txt5 = [x for x in K.format_fills(L, LO, HI) if x.startswith("- CLOSING CLV")]
    assert len(txt5) == 2 and txt5[0] == want and txt5[1].endswith(" · outside the window")
    L["meta"]["closings"]["NFL|2095-10-12T17:00:00Z"]["games"]["b"]["legs"] = None
    assert [x for x in K.format_fills(L, LO, HI) if x.startswith("- CLOSING CLV")] == [want]


def test_r17_the_ledger_the_cockpit_builds_under_node_prices_the_same_through_the_port(tmp_path):
    """The cross-language case: the page's own loadDocs takes the morning slate, then its closing (Buffalo quoted
    55/56c there, so its order differs from the slate's; Miami left off the page); the page stores the pages, the
    claims and their orders. A Dallas game stored before R17 (its legs key removed). Kalshi fills: YES on Buffalo and
    NO on its opponent (the closing page's order), a ticker the page does not quote on Denver (its order the slate's:
    the closing page PASSes it), Dallas, Miami (no stored page). The ledger the page exports is read by the port:
    every field of every position equal to the page's, and the K-track receipt's line carries the page's cents.
    Skipped without node (the page runs under it, as tests/test_cockpit_closing_marks.py)."""
    from tests.test_cockpit_closing_marks import CLOSING_NAME, SLATE_NAME, _node, closing, slate, tick
    S = slate(ticked=True)
    C = closing(ticked=True, quotes={"Buffalo": (0.55, 0.56)}, ids=[301, 307, 304, 302, 303])     # no Miami (306)
    fills = [{"id": "F1", "ticker": tick("Buffalo"), "side": "yes", "qty": 4, "entry": 0.57, "title": ""},
             {"id": "F2", "ticker": tick("Buffalo", "AWAY"), "side": "no", "qty": 6, "entry": 0.55, "title": ""},
             {"id": "F3", "ticker": "KXNFLGAME-26OCT191300DVDEN-DEN", "side": "yes", "qty": 5, "entry": 0.5, "title": ""},
             {"id": "F4", "ticker": tick("Dallas"), "side": "yes", "qty": 5, "entry": 0.6, "title": ""},
             {"id": "F5", "ticker": tick("Miami"), "side": "yes", "qty": 5, "entry": 0.57, "title": ""}]
    got = _node(tmp_path, r'''
await loadDocs([T_doc(SN,S)]); await loadDocs([T_doc(CN,C)]);
const L=loadLedger(), st=L.meta.closings["NFL|2026-10-19T17:00:00Z"];
delete Object.values(st.games).find(g=>g.home==="Dallas").legs;
L.fills=FILLS; saveLedger(L);
const M=loadLedger(), ps=closingPositions(M);
T_out({L:M,ps:ps.map(({c,...p})=>p),line:closingClvLine(M),
  c1:Object.fromEntries(ps.filter(p=>p.clv_c!=null).map(p=>{ const v=+p.clv_c.toFixed(1)||0; return [p.id,`${v>=0?"+":""}${v.toFixed(1)}c`]; }))});''',
                S=S, C=C, SN=SLATE_NAME, CN=CLOSING_NAME, FILLS=fills)
    L = json.loads(json.dumps(got["L"], indent=1))                              # as the Export writes it
    py = [{k: v for k, v in p.items() if k != "c"} for p in P.closing_positions(L)]
    assert py == got["ps"]                                                     # every field, exactly
    by = {p["c"]["home"]: p for p in P.closing_positions(L)}
    assert {h: (p["cover"], p["page"], p["quote"]) for h, p in by.items()} == {
        "Buffalo": ("page", "closing", "priced"), "Denver": ("page", "slate", "unpriced"),
        "Dallas": ("page", "slate", "no_quote"), "Miami": ("none", "slate", "no_page")}
    b = by["Buffalo"]
    assert b["asks"] == [0.56, 0.56] and _r4(b["clv_c"]) == 0.2                 # YES at its ask, NO at 1 − 0.44
    assert b["ordered"]["limit"] == 0.56 and b["above_limit_c"] == 1.0 and b["above_fills"] == 1
    assert b["ordered"] != b["c"]["claim_order"] and b["c"]["claim_order"]["limit"] != 0.56   # the closing page's, not
    for h in ("Denver", "Dallas", "Miami"):                                    # the slate's; theirs the slate's
        assert by[h]["ordered"] == by[h]["c"]["exec_order"] == by[h]["c"]["claim_order"] and by[h]["ordered"]["ticker"]
    assert got["line"].startswith("Closing CLV (close − entry; + = beat the close) (addendum 146 item 1(iv) R17, #431): "
                                  "4 position(s), 5 fill(s) · sum +0.2c · mean +0.2c per position · graded 0 · open 4")
    (k,) = K.closing_clv_lines(L, set())
    assert f" · straight HOME · {got['c1'][b['id']]} · filled 10 @ " in k and k.endswith(" · outside the window")
