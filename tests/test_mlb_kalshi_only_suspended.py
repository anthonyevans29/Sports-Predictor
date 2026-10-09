"""Q3 — MLB KALSHI-ONLY SUSPENSION (ARCHITECT 2026-10-08, addendum 13 item 2, RULED):
"K1. An MLB row is never a call on a kalshi-only reference. Where the 2026-10-01 rule would have taken the Kalshi mid
as the reference, the row is PASS with no reference: units 0, no order, no shadow units. Reason on the row:
'kalshi-only suspended for MLB: the model number is unblended without books (ARCHITECT 2026-10-07)'.
K3. For the record such a row carries a kalshi_only_hold block: the mid, bid, ask and spread, the raw edge (model
number minus mid), the edge on equal footing (half the raw edge), and the call and units the 2026-10-01 rule would
have given. Nothing reads the block as a call.
K4. NFL and PL keep the kalshi-only reference exactly as ruled on 2026-10-01; their numbers are not blended with the
market. MLB rows no longer add to the 30-call review count.
K6. From this PR the predict step records on each MLB prediction whether the market blend was applied, with the
weight and the market number used. Nothing else about the prediction changes: the PR shows identical probabilities
before and after on the same inputs. The #354 receipt splits by that record: blended, model alone, not recorded.
Nothing is inferred for a row with no record."
Synthetic rows / throwaway DB only."""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from src.walters import desk_policy as dp

NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)
NOW_MS = float((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REASON = "kalshi-only suspended for MLB: the model number is unblended without books (ARCHITECT 2026-10-07)"
HOLD_KEYS = {"mid", "bid", "ask", "spread_c", "raw_edge_pp", "equal_footing_edge_pp", "would_call", "would_units"}


def row(home, p_home, *, fair_h=None, bid=0.49, ask=0.50, when=30, comp="MLB", series="KXMLBGAME"):
    """A two-way model row 30 minutes before first pitch. No book fair -> the 2026-10-01 rule's kalshi-only mid
    (bid/ask 0.49/0.50: mid 0.495, spread 1c). Ticketed legs so a call writes an order."""
    mk = {"bookmaker_count": 9 if fair_h is not None else 0}
    if fair_h is not None:
        mk["fair_prob"] = {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}
    r = {"home_team": home, "away_team": f"{home} away", "competition": comp, "stage": "regular",
         "utc_date": (NOW + timedelta(minutes=when)).strftime("%Y-%m-%dT%H:%M:%S"),
         "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                        "tier": "lean"},
         "market": mk, "kalshi_bid": bid, "kalshi_ask": ask,
         "kalshi_legs": {"HOME": {"ticker": f"{series}-26OCT08-{home}H", "bid": bid, "ask": ask},
                         "AWAY": {"ticker": f"{series}-26OCT08-{home}A", "bid": round(1 - ask, 2),
                                  "ask": round(1 - bid, 2)}}}
    return r


def desk(*rows, sport="mlb"):
    doc = {"sport": sport, "predictions": list(rows)}
    dp.annotate(doc, now=NOW)
    return {p["home_team"]: p["desk"] for p in doc["predictions"]}, doc


# ------------------------------------------------------------------------------------------------ K1 --

def test_k1_an_mlb_kalshi_only_row_is_pass_with_no_reference():
    with dp.kalshi_only_suspension_off():                       # the 2026-10-01 rule: a real call
        before, _ = desk(row("Play", 0.56))                     # +6.5pp vs mid 0.495
    b = before["Play"]
    assert b["call"] == "PLAY" and b["reference"] == "kalshi_only" and b["order"] is not None and b["units"] > 0
    after, doc = desk(row("Play", 0.56))
    d = after["Play"]
    assert (d["call"], d["units"], d["shadow_units"], d["pass_kind"]) == ("PASS", 0, 0, "kalshi_only_suspended")
    assert d["reason"] == REASON and d["reasons"] == [REASON]
    assert d["reference"] is None and d["market_ref"] is None and d["edge_pp"] is None
    assert d["order"] is None and d["exec"] is None and d["value_shadow"] is None
    assert "kalshi_only_suspended" in dp.NO_CALL_KINDS
    assert doc["desk_meta"]["mlb_kalshi_only_suspended"] is True


def test_k1_no_shadow_units_even_where_the_quarantine_would_have_shadowed():
    with dp.kalshi_only_suspension_off():
        q = desk(row("Big", 0.62))[0]["Big"]                    # +12.5pp vs the mid: a >8pp quarantine shadow
    assert (q["call"], q["shadow_units"], q["reference"]) == ("PASS", 0.5, "kalshi_only")
    d = desk(row("Big", 0.62))[0]["Big"]
    assert (d["call"], d["units"], d["shadow_units"], d["order"], d["exec"]) == ("PASS", 0, 0, None, None)
    assert not dp.is_quarantine_shadow({"call": d["call"], "shadowUnits": d["shadow_units"], "tags": d["tags"]})


def test_k1_a_suspended_row_is_never_a_parlay_leg():
    rows = [row("A", 0.56), row("B", 0.57)]
    nfl = [row("N1", 0.56, comp="NFL", series="KXNFLGAME"), row("N2", 0.57, comp="NFL", series="KXNFLGAME")]
    for r in nfl:
        r.pop("competition")
    files = [("mlb.json", {"sport": "mlb", "predictions": rows}), ("nfl.json", {"sport": "nfl", "predictions": nfl})]
    with dp.kalshi_only_suspension_off():
        assert dp.parlays_doc(json.loads(json.dumps(files)), now=NOW)["live_legs"] == 4
    p = dp.parlays_doc(files, now=NOW)
    assert p["live_legs"] == 2
    assert all(l["sport"] == "NFL" for t in p["tickets"] for l in t["legs"])


def test_k1_book_rows_and_started_rows_are_untouched():
    with dp.kalshi_only_suspension_off():
        before, _ = desk(row("Book", 0.60, fair_h=0.54), row("Started", 0.56, when=-5))
    after, _ = desk(row("Book", 0.60, fair_h=0.54), row("Started", 0.56, when=-5))
    assert after["Book"] == before["Book"] and after["Book"]["reference"] == "books"
    assert after["Started"] == before["Started"] and after["Started"]["pass_kind"] == "started"


# ------------------------------------------------------------------------------------------------ K3 --

@pytest.mark.parametrize("p_home,pick", [(0.56, "HOME"), (0.38, "AWAY"), (0.62, "HOME"), (0.52, "HOME")])
def test_k3_the_hold_records_the_reference_both_edges_and_the_would_be_call(p_home, pick):
    with dp.kalshi_only_suspension_off():
        was = desk(row("H", p_home))[0]["H"]
    d = desk(row("H", p_home))[0]["H"]
    h = d["kalshi_only_hold"]
    assert set(h) == HOLD_KEYS
    assert (h["mid"], h["bid"], h["ask"], h["spread_c"]) == ((0.49 + 0.50) / 2, 0.49, 0.50, 1)
    ref = h["mid"] if pick == "HOME" else 1 - h["mid"]          # the pick side's reference, as 2026-10-01
    model = p_home if pick == "HOME" else round(1 - p_home, 4)
    assert d["pick"] == pick and h["raw_edge_pp"] == (model - ref) * 100 == was["edge_pp"]
    assert h["equal_footing_edge_pp"] == h["raw_edge_pp"] / 2
    assert (h["would_call"], h["would_units"]) == (was["call"], was["units"])
    assert d["call"] == "PASS" and d["units"] == 0              # nothing reads the block as a call


def test_k3_the_would_be_call_covers_a_floor_pass_too():
    d = desk(row("Thin", 0.52))[0]["Thin"]                      # +2.5pp vs the mid: the 2026-10-01 rule PASSes
    assert (d["kalshi_only_hold"]["would_call"], d["kalshi_only_hold"]["would_units"]) == ("PASS", 0)
    assert d["pass_kind"] == "kalshi_only_suspended"


def test_k3_rows_with_no_kalshi_only_reference_carry_no_hold():
    d = desk(row("Wide", 0.60, bid=0.45, ask=0.50), row("Book", 0.60, fair_h=0.54))[0]   # 5c: no kalshi-only ref
    assert d["Wide"]["pass_kind"] == "noref" and "kalshi_only_hold" not in d["Wide"]
    assert "kalshi_only_hold" not in d["Book"]


# ------------------------------------------------------------------------------------------------ K4 --

def test_k4_nfl_keeps_the_kalshi_only_reference_exactly():
    def nfl():
        r = row("KC", 0.56, comp="NFL", series="KXNFLGAME")
        r.pop("competition")
        return r
    with dp.kalshi_only_suspension_off():
        before, _ = desk(nfl(), sport="nfl")
    after, _ = desk(nfl(), sport="nfl")
    assert after["KC"] == before["KC"]
    assert after["KC"]["call"] == "PLAY" and after["KC"]["reference"] == "kalshi_only" and after["KC"]["order"]


def test_k4_pl_rows_are_unchanged():
    def pl():
        return {"home_team": "PL H", "away_team": "PL A", "utc_date": (NOW + timedelta(minutes=30)).strftime(
                    "%Y-%m-%dT%H:%M:%S"), "competition": "PL",
                "prediction": {"probabilities": {"home_win": 0.55, "draw": 0.25, "away_win": 0.20}, "tier": "lean"},
                "market": {"bookmaker_count": 0}, "kalshi_bid": 0.49, "kalshi_ask": 0.50}
    with dp.kalshi_only_suspension_off():
        before, _ = desk(pl(), sport="soccer")
    after, _ = desk(pl(), sport="soccer")
    assert after == before and after["PL H"]["pass_kind"] != "kalshi_only_suspended"


def test_k4_the_suspension_is_mlb_only():
    assert dp.kalshi_only_suspended({"sport": "MLB"}) and not dp.kalshi_only_suspended({"sport": "NFL"})
    assert not dp.kalshi_only_suspended({"sport": "SOCCER"})


# ------------------------------------------------------------------------------- the switch / golden --

def test_base_v11_turns_the_suspension_off_and_restores_it():
    with dp.base_v11():
        assert dp.KALSHI_ONLY_MLB_SUSPENDED["on"] is False
        c = {r["home"]: c for r, c in dp.evaluate({"sport": "mlb", "predictions": [row("G", 0.56)]},
                                                  NOW_MS)["calls"]}
        assert c["G"]["kalOnly"] is True and "koHold" not in c["G"]
    assert dp.KALSHI_ONLY_MLB_SUSPENDED["on"] is True


def test_addendum_off_holds_the_suspension_as_it_holds_the_quarantine():
    with dp.addendum_off():
        assert dp.KALSHI_ONLY_MLB_SUSPENDED["on"] is True and dp.MLB_QUARANTINE["on"] is True


def test_desk_rescore_reports_the_suspension_never_as_halved():
    doc = {"sport": "mlb", "predictions": [row("Was", 0.56)]}
    with dp.kalshi_only_suspension_off():                       # a file published before Q3
        dp.annotate(doc, now=NOW)
    assert doc["predictions"][0]["desk"]["call"] == "PLAY"
    (x,) = dp.rescore(doc)
    assert x["verdict"] == "kalshi-only suspended" and x["addendum_call"] == "PASS"


def test_desk_rescore_cli_prints_the_suspension_with_the_holds_raw_edge(tmp_path):
    """Codex P1 on #369: a pre-Q3 export with a published MLB kalshi-only PLAY crashed desk-rescore (TypeError on a
    None edge). The row now carries the hold's raw edge, labelled as such, and a None edge prints as —."""
    from click.testing import CliRunner

    import cli
    doc = {"sport": "mlb", "predictions": [row("Was", 0.56)]}
    with dp.kalshi_only_suspension_off():                       # published before Q3: a real PLAY
        dp.annotate(doc, now=NOW)
    assert doc["predictions"][0]["desk"]["call"] == "PLAY"
    p = tmp_path / "mlb.json"
    p.write_text(json.dumps(doc))
    res = CliRunner().invoke(cli.cli, ["desk-rescore", str(p), "--out", str(tmp_path / "r.md")])
    assert res.exit_code == 0, (res.output, repr(res.exception))
    line = next(l for l in res.output.splitlines() if "Was away @ Was" in l)
    assert "fair — · hold raw edge +6.5pp (not a live edge)" in line and "KALSHI-ONLY SUSPENDED" in line
    assert "1 MLB PLAY(s) now PASS under the kalshi-only suspension" in res.output
    (x,) = dp.rescore(doc)
    assert x["fair_edge_pp"] is None and x["hold_raw_edge_pp"] == (0.56 - 0.495) * 100


# ------------------------------------------------------------------------- the Cockpit repo copy --

def _cockpit():
    return open(os.path.join(ROOT, "tools", "cockpit.html"), encoding="utf-8").read()


def _fn(html, name):
    m = re.search(r"^function " + name + r"\(.*?^\}", html, re.S | re.M) or \
        re.search(r"^function " + name + r"\([^\n]*\}$", html, re.M)
    assert m, name
    return m.group(0)


def test_cockpit_renders_the_pass_kind_and_the_hold():
    html = _cockpit()
    tag = _fn(html, "passKindTag")
    assert 'k==="kalshi_only_suspended"' in tag and "kalshi-only suspended" in tag
    pol = _fn(html, "policy")
    assert 'passKind==="kalshi_only_suspended"' in pol and "koHoldHTML(r.fileDesk.kalshi_only_hold)" in pol


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_cockpit_hold_render_and_the_30_call_count_run_in_node(tmp_path):
    html = _cockpit()
    hold = {"mid": 0.495, "bid": 0.49, "ask": 0.5, "spread_c": 1, "raw_edge_pp": 6.5, "equal_footing_edge_pp": 3.25,
            "would_call": "PLAY", "would_units": 0.5}
    ledger = {"calls": [{"result": "win", "reference": "kalshi_only", "sport": "MLB"},
                        {"result": "loss", "reference": "kalshi_only", "sport": "MLB"},
                        {"result": "win", "reference": "kalshi_only", "sport": "NFL"},
                        {"result": "win", "reference": "kalshi_only", "sport": "SOCCER"},
                        {"result": None, "reference": "kalshi_only", "sport": "NFL"},
                        {"result": "win", "reference": "books", "sport": "NFL"}]}
    js = "\n".join([_fn(html, "esc"), _fn(html, "koHoldHTML"), _fn(html, "gradedCount"), _fn(html, "kalshiOnlyGraded"),
                    f"function loadLedger(){{return {json.dumps(ledger)};}}",
                    f"console.log(JSON.stringify([koHoldHTML({json.dumps(hold)}), koHoldHTML(null), kalshiOnlyGraded()]));"])
    f = tmp_path / "k.js"
    f.write_text(js)
    out = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    assert out[0] == ('<div class="note">hold (record only, not a call): mid 0.495 (bid 0.49 / ask 0.50, spread 1c)'
                      ' · raw edge +6.5pp · on equal footing +3.3pp · the 2026-10-01 rule: PLAY 0.5u</div>')
    assert out[1] == ""
    assert out[2] == 2                                          # K4: NFL + PL only; the two graded MLB rows drop out


# ------------------------------------------------------------------------------------------------ K6 --

def _k6():
    import mlb_blend_fixture as F
    return F, F.run(F.V_ON), F.run(F.V_OFF)


def test_k6_the_blend_record_on_each_mlb_prediction():
    F, on, off = _k6()
    rec = on["BLEND"][2]["market_blend"]
    assert set(rec) == {"applied", "enabled", "w", "market_home", "market_away"}
    assert rec["applied"] is True and rec["enabled"] is True and rec["w"] == 0.5
    # the market number used: the de-vigged book close, averaged over the two complete books
    imp = [(1 / 1.62, 1 / 2.40), (1 / 1.65, 1 / 2.30)]
    mh = sum(h / (h + a) for h, a in imp) / 2
    assert rec["market_home"] == pytest.approx(mh, abs=1e-15)
    assert rec["market_away"] == pytest.approx(1 - mh, abs=1e-15)
    for g in ("NOBOOK", "UNPRICD"):                             # the model alone: enabled, not applied
        assert on[g][2]["market_blend"] == {"applied": False, "enabled": True, "w": None, "market_home": None,
                                            "market_away": None}
    for g in F.GAMES:                                           # blend disabled: recorded as not applied
        assert off[g][2]["market_blend"] == {"applied": False, "enabled": False, "w": None, "market_home": None,
                                             "market_away": None}


# The probabilities origin/main (50c4840) wrote on this fixture, before the K6 record existed (repr floats):
MAIN = {("on", "BLEND"): (0.5075558245824514, 0.4924441754175486),
        ("on", "NOBOOK"): (0.3440482239235226, 0.6559517760764775),
        ("on", "UNPRICD"): (0.44796826815960117, 0.5520317318403989),
        ("off", "BLEND"): (0.42546494597200657, 0.5745350540279934),
        ("off", "NOBOOK"): (0.3440482239235226, 0.6559517760764775),
        ("off", "UNPRICD"): (0.44796826815960117, 0.5520317318403989)}


def test_k6_identical_probabilities_before_and_after_the_record():
    F, on, off = _k6()
    for (v, g), (ph, pa) in MAIN.items():
        got = (on if v == "on" else off)[g]
        assert (got[0], got[1]) == (ph, pa), (v, g)              # bit-identical to origin/main
    # and the blend math itself: (1 - w) * model + w * market, renormalized, from the record's own numbers
    rec, pm = on["BLEND"][2]["market_blend"], off["BLEND"]
    h = (1 - rec["w"]) * pm[0] + rec["w"] * rec["market_home"]
    a = (1 - rec["w"]) * pm[1] + rec["w"] * rec["market_away"]
    assert (on["BLEND"][0], on["BLEND"][1]) == (h / (h + a), a / (h + a))


def test_k6_at_weight_0_the_record_reads_applied_false_and_keeps_the_numbers():
    """ADDENDUM 18 item 2 (ARCHITECT): "Applied means the market number moved the prediction. With market_blend_w
    at 0 the record reads applied false, enabled true, and keeps the weight and the market numbers. The
    probabilities are not touched by this fix." """
    import mlb_blend_fixture as F
    from src.db.database import session_scope
    from src.db.schema import ModelVersion, Sport
    from src.walters import mlb_actionable as MA

    F.build()
    with session_scope() as s:
        if s.query(ModelVersion).filter_by(version="k6-blend-w0").one_or_none() is None:
            s.add(ModelVersion(sport=Sport.MLB, model_family="mlb_pythag_negbin", version="k6-blend-w0",
                               status="candidate",
                               parameters={"baseball_config": {"market_blend_enabled": True, "market_blend_w": 0.0}}))
    zero, off, on = F.run("k6-blend-w0"), F.run(F.V_OFF), F.run(F.V_ON)
    rec = zero["BLEND"][2]["market_blend"]
    assert rec["applied"] is False and rec["enabled"] is True and rec["w"] == 0.0
    assert rec["market_home"] == on["BLEND"][2]["market_blend"]["market_home"]       # the market numbers kept
    assert rec["market_away"] == on["BLEND"][2]["market_blend"]["market_away"]
    assert MA.blend_of(zero["BLEND"][2]) == "model alone"
    # the probabilities: the w-0 blend is the model number (the same branch as before the fix, untouched)
    assert zero["BLEND"][0] == pytest.approx(off["BLEND"][0], abs=1e-12)
    assert zero["BLEND"][1] == pytest.approx(off["BLEND"][1], abs=1e-12)
    for g in ("NOBOOK", "UNPRICD"):                                                  # never priced: unchanged
        assert zero[g][2]["market_blend"] == {"applied": False, "enabled": True, "w": None, "market_home": None,
                                              "market_away": None}


def test_k6_the_actionable_receipt_splits_by_the_record_and_infers_nothing():
    from src.walters import mlb_actionable as MA
    assert MA.BLENDS == ("blended", "model alone", "not recorded")
    assert MA.blend_of({"market_blend": {"applied": True}}) == "blended"
    assert MA.blend_of({"market_blend": {"applied": False, "enabled": True}}) == "model alone"
    assert MA.blend_of({"market_blend": {"applied": False, "enabled": False}}) == "model alone"
    for fb in (None, {}, {"home_starter_known": True}, {"market_blend": None}, {"market_blend": {"enabled": True}}):
        assert MA.blend_of(fb) == "not recorded"
    close = {"fair": {"HOME": 0.5, "AWAY": 0.5}, "reference": "books", "source": "odds"}
    rows = [MA.grade_row(match_id=i, stage_raw="R", p_home=0.58, p_away=0.42, factor_breakdown=fb, hit=True,
                         close=close)
            for i, fb in enumerate([{"market_blend": {"applied": True}}, {"market_blend": {"applied": False}},
                                    {"market_blend": {"applied": False}}, {}])]
    res = MA.receipt(rows, b=50)
    assert [res["blend"][bl]["n"] for bl in MA.BLENDS] == [1, 2, 1]
    text = MA.format_receipt(res, season="2026", run_stamp="t")
    assert "## By market-blend record (Q3 K6, all stages) · blended 1 · model alone 2 · not recorded 1" in text


# ---------------------------------------------- addendum 15 item 2: "A cost is the cost of an order" --

@pytest.mark.parametrize("unit_usd", [None, "20"])            # the unit in contracts, and in dollars
def test_desk_rescore_prices_each_row_at_its_own_exec_block_and_a_suspended_row_not_at_all(
        tmp_path, monkeypatch, unit_usd):
    """ARCHITECT 2026-10-08, addendum 15 item 2 (RULED): "The desk-rescore line carries the exec cost and exec edge
    of the row's own exec block under the current Desk, at the file's as_of and counts: the same size, and none
    where the Desk writes no exec block. A suspended row is not priced." For every re-scored row exec_cost and
    exec_edge_pp equal exec.cost and exec.edge_pp of the same row annotated by the current Desk at the file's as_of
    and counts, and are None where exec is None. Cases: a suspended row, a half-size quarantine shadow (the sibling
    on main since #328: priced at one unit on the rescore line, at its shadow size in its exec block), a plain PLAY."""
    from click.testing import CliRunner

    import cli
    if unit_usd is None:
        monkeypatch.delenv("SP_UNIT_USD", raising=False)
    else:
        monkeypatch.setenv("SP_UNIT_USD", unit_usd)
    doc = {"sport": "mlb", "predictions": [
        row("Susp", 0.56),                                       # kalshi-only: suspended under Q3
        dict(row("Quar", 0.71, fair_h=0.56, bid=0.55, ask=0.56), stage="postseason"),   # +15pp: shadow 0.5u
        row("Play", 0.62, fair_h=0.56, bid=0.55, ask=0.56)]}     # +6pp on books: a plain PLAY
    with dp.base_v11():                                          # published before the quarantine and Q3
        dp.annotate(doc, now=NOW)
    assert [p["desk"]["call"] for p in doc["predictions"]] == ["PLAY", "PLAY", "PLAY"]
    rows = {x["game"].split(" @ ")[1]: x for x in dp.rescore(doc)}
    # the same rows, annotated by the current Desk at the file's as_of and counts
    cur = json.loads(json.dumps(doc))
    for p in cur["predictions"]:
        p.pop("desk")
    dp.annotate(cur, now=NOW, counts=doc["desk_meta"]["counts"])
    ex = {p["home_team"]: p["desk"]["exec"] for p in cur["predictions"]}
    assert ex["Susp"] is None and ex["Quar"] is not None and ex["Play"] is not None
    q = next(p["desk"] for p in cur["predictions"] if p["home_team"] == "Quar")
    assert (q["call"], q["shadow_units"]) == ("PASS", 0.5)      # the half-size shadow
    for home, x in rows.items():
        e = ex[home]
        assert x["exec_cost"] == (e["cost"] if e else None), home
        assert x["exec_edge_pp"] == (e["edge_pp"] if e else None), home
    assert rows["Susp"]["verdict"] == "kalshi-only suspended" and rows["Susp"]["hold_raw_edge_pp"] is not None
    assert rows["Quar"]["verdict"] == "quarantined"
    p = tmp_path / "mlb.json"
    p.write_text(json.dumps(doc))
    res = CliRunner().invoke(cli.cli, ["desk-rescore", str(p), "--out", str(tmp_path / "r.md")])
    assert res.exit_code == 0, (res.output, repr(res.exception))
    line = next(l for l in res.output.splitlines() if "Susp away @ Susp" in l)
    assert "exec — (not priced: no order under the suspension)" in line and "hold raw edge +6.5pp" in line
    qline = next(l for l in res.output.splitlines() if "Quar away @ Quar" in l)
    assert f"cost {ex['Quar']['cost']:.3f}" in qline and f"{ex['Quar']['edge_pp']:+.1f}pp" in qline
