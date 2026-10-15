"""THE VALUE-SHADOW RECEIPT (ARCHITECT 2026-10-15, addendum 79 item 2; #86): every value shadow a Cockpit ledger export
holds, per row and in totals, units only. The kept ledger shape is tests/fixtures/value_shadow/bd_ledger_v1_cockpit.json,
written by the Cockpit's own code (scripts/value_shadow_fixture_capture.py: tools/cockpit.html in headless Chromium
logged and graded the shadows and the file is its "Export ledger (JSON)" text)."""
import copy
import json
from pathlib import Path

import pytest

import scripts.value_shadow_receipt as vsr

FIXTURE = Path(__file__).parent / "fixtures" / "value_shadow" / "bd_ledger_v1_cockpit.json"


def kept():
    return json.loads(FIXTURE.read_text())


def run(L, name="bd_ledger_v1_test.json"):
    out = []
    res = vsr.report(L, name, echo=out.append)
    return out, res


def call(L, home):
    return next(c for c in L["calls"] if c.get("call_type") == "value_shadow" and c["home"] == home)


def test_the_kept_ledger_is_the_cockpits_own_shape():
    L = kept()
    assert set(L) == {"meta", "calls", "system_picks"} and L["meta"]["policy_version"] == "v1.1"
    vs = [c for c in L["calls"] if c["call_type"] == "value_shadow"]
    assert len(vs) == 5 and all(c["engine"] == "model_edge" and c["units"] == 0 and c["shadow_units"] == 0.25
                                for c in vs)
    assert {c["status"] for c in vs} == {"graded", "open"} and not any("staked" in c for c in vs)
    assert vsr.refusal(L) is None


def test_every_value_shadow_per_row_and_the_totals_on_the_kept_ledger():
    out, res = run(kept())
    assert out[0].startswith("VALUE-SHADOW RECEIPT (ARCHITECT 2026-10-15, addendum 79 item 2; #86)")
    assert out[1] == ("ledger: bd_ledger_v1_test.json · calls 6 · meta.policy_version v1.1 (the Cockpit rewrites it "
                      "on every load)")
    assert out[2].startswith('keys: value shadow = call_type "value_shadow"')
    rows = [o for o in out if o.startswith("  2")]
    assert len(rows) == 5                                             # the Buffalo straight is not a shadow
    day = rows[0][2:18]
    assert rows[0] == f"  {day} · SOCCER · Chelsea @ Arsenal · DRAW · edge +6.0pp (claim) · close 0.280 · won · 0.25u, net +0.6759u"
    assert (f"  {day} · NFL · Dallas Cowboys @ New York Giants · AWAY (Dallas Cowboys) · edge +8.0pp (claim) · no close"
            " · lost · 0.25u, net -0.2500u") in rows
    assert (f"  {day} · NFL · Los Angeles Rams @ Seattle Seahawks · HOME (Seattle Seahawks) · edge +7.0pp (claim) · "
            "close 0.415 · push · 0.25u, net +0.0000u") in rows
    assert (f"  {day} · NFL · Minnesota Vikings @ Green Bay Packers · HOME (Green Bay Packers) · edge +7.0pp (claim) · "
            "no close · ungraded · 0.25u") in rows
    assert (f"  {day} · NFL · Philadelphia Eagles @ Chicago Bears · HOME (Chicago Bears) · edge +13.4pp (claim) · "
            "close 0.372 · won · 0.25u, net +0.4542u") in rows
    assert ("  all value shadows: n 5 · graded 4 · record won 2 · lost 1 · push 1 · void 0 · ungraded 1 · units net "
            "+0.8801u over 4 settled (notional 1u)") in out
    assert ("  the rows with a close only: n 3 · graded 3 · record won 2 · lost 0 · push 1 · void 0 · ungraded 0 · "
            "units net +1.1301u over 3 settled (notional 0.75u)") in out
    assert "  staked: 0 (a staked field 0 · the label 0) · marked but not a value_shadow call: 0" in out
    assert out[-2] == ("n/30 (the Cockpit's counter: every value shadow with a result, push and void included): "
                       "4 of 30")
    js = json.loads(out[-1].removeprefix("VALUE-SHADOW-RECEIPT "))
    assert js["n_of_30"] == "4 of 30" and js["all"]["units_net"] == 0.8801 and js["with_close"]["n"] == 3
    assert res["all"]["record"] == {"won": 2, "lost": 1, "push": 1, "void": 0}
    assert not any("$" in o for o in out)                             # no dollar figure anywhere


def test_the_edge_at_the_call_is_the_claims_and_a_relog_does_not_move_it():
    L = kept()
    c = call(L, "Chicago Bears")
    c["value_edge_pp"], c["model_p"], c["market_p"] = 9.9, 0.45, 0.351     # a later re-log before kickoff
    assert vsr.row(c)["edge_pp"] == pytest.approx(13.4) and vsr.row(c)["edge_basis"] == "claim"
    del c["claim_model_p"], c["claim_market_p"]                         # logged before the timing rule
    assert (vsr.row(c)["edge_pp"], vsr.row(c)["edge_basis"]) == (9.9, "last log")
    c.pop("value_edge_pp")
    assert vsr.edge_at_call(c) == (None, "none")


def test_staked_shadows_are_read_by_a_field_or_the_label_and_another_call_so_marked_is_listed_apart():
    L = kept()
    call(L, "Chicago Bears")["staked"] = True
    call(L, "New York Giants")["note"] = "Value shadow, staked (small)"
    straight = next(c for c in L["calls"] if c["call_type"] == "straight")
    straight["rules"] = straight["rules"] + ["value shadow, staked"]
    out, res = run(L)
    assert res["staked"] == {"field": 1, "text": 1} and len(res["other_staked"]) == 1
    assert any(o.endswith("net +0.4542u · STAKED (a staked field)") for o in out)
    assert any(o.endswith("net -0.2500u · STAKED (the label)") for o in out)
    i = out.index('MARKED "value shadow, staked" BUT NOT call_type value_shadow (listed, kept out of the totals):')
    assert "Miami Dolphins @ Buffalo Bills" in out[i + 1] and out[i + 1].endswith("· call_type straight")
    assert "  staked: 2 (a staked field 1 · the label 1) · marked but not a value_shadow call: 1" in out
    assert res["all"]["n"] == 5 and res["all"]["units_net"] == 0.8801     # the straight stays out of the totals


def test_the_kickoff_audit_settles_as_the_cockpit_does():
    L = kept()
    call(L, "Chicago Bears")["tz_audit"] = {"flag": "x", "excluded": True}
    call(L, "Arsenal")["tz_audit"] = {"flag": "x", "excluded": False, "price_used": 0.25}
    out, res = run(L)
    a = res["all"]
    assert (a["graded"], a["settled"], a["audit_excluded"]) == (4, 3, 1)
    assert a["units_net"] == pytest.approx(round(0.25 / 0.25 - 0.25 - 0.25 + 0, 4))   # draw at 0.25; NYG lost; push
    assert any("Chicago Bears" in o and o.endswith("close 0.372 · won · 0.25u · kickoff audit: excluded") for o in out)
    assert any("Arsenal" in o and "net +0.7500u · kickoff audit: flagged" in o for o in out)
    assert "out of the P&L by the kickoff audit 1" in next(o for o in out if o.startswith("  all value shadows"))


def test_a_void_counts_graded_and_settles_its_stake_back():
    L = kept()
    c = call(L, "Green Bay Packers")
    c.update(status="graded", result="void", shadow_returned=0.25)
    _, res = run(L)
    assert res["all"]["record"]["void"] == 1 and res["all"]["graded"] == 5 and res["all"]["ungraded"] == 0
    assert res["all"]["units_net"] == 0.8801


def test_a_ledger_with_no_value_shadow_says_n_0_of_30():
    L = kept()
    L["calls"] = [c for c in L["calls"] if c["call_type"] != "value_shadow"]
    out, res = run(L)
    assert ('VALUE SHADOWS: none in this ledger (0 calls with call_type value_shadow, 0 marked "value shadow, staked") '
            "→ n=0 of 30") in out
    assert json.loads(out[-1].removeprefix("VALUE-SHADOW-RECEIPT "))["n_of_30"] == "0 of 30"
    out, _ = run({"meta": {}, "calls": []})
    assert any(o.endswith("→ n=0 of 30") for o in out)


@pytest.mark.parametrize("doc,why", [
    ([], "not a bd_ledger_v1 export (not a JSON object)"),
    ({"meta": {}}, "not a bd_ledger_v1 export (no calls array)"),
    ({"calls": [{"call_type": "value_shadow"}, "x"]}, "calls[1] is not an object (1 such)"),
])
def test_the_receipt_refuses_what_is_not_a_ledger_export(tmp_path, capsys, doc, why):
    p = tmp_path / "bd_ledger_v1_bad.json"
    p.write_text(json.dumps(doc))
    assert vsr.main(["--ledger", str(p)]) == 2
    assert capsys.readouterr().out.strip() == f"REFUSED: bd_ledger_v1_bad.json: {why}"


def test_the_cli_prints_the_receipt_and_writes_nothing(tmp_path, capsys):
    p = tmp_path / "bd_ledger_v1_2026-10-19.json"
    p.write_text(FIXTURE.read_text())
    before = sorted(x.name for x in tmp_path.iterdir())
    assert vsr.main(["--ledger", str(p)]) == 0
    out = capsys.readouterr().out
    assert "ledger: bd_ledger_v1_2026-10-19.json · calls 6" in out and "4 of 30" in out
    assert sorted(x.name for x in tmp_path.iterdir()) == before
    bad = tmp_path / "missing.json"
    assert vsr.main(["--ledger", str(bad)]) == 2 and "REFUSED:" in capsys.readouterr().out


def test_the_kept_fixture_is_not_mutated_by_the_receipt():
    L = kept()
    snap = copy.deepcopy(L)
    run(L)
    assert L == snap
