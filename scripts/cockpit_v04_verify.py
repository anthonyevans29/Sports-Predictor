"""
Cockpit v0.4 headless verification (2026-09-26) — capture -> grade -> report.

Drives tools/cockpit.html in headless Chromium (Playwright) over SYNTHETIC
export files, then re-grades every logged call INDEPENDENTLY in Python and
compares. Covers: straight win, soccer draw vs side-pick (loss), ladder/DC
won by the draw, NFL quarantine shadow (units 0, notional counterfactual),
a voided parlay leg dropped from its ticket, venue-edge calls (NCAA fixtures
+ NFL), UNL / single-venue / thin-books / in-play exclusions, idempotent
re-logging, an unmatched call staying open, and the Ledger outputs
(by-engine tables, equity SVG, P&L block, per-rule attribution).

Writes nothing to the repo; no DB. Needs Playwright + Chromium
(pre-installed in the cloud container; locally: pip install playwright).

Run:  python3 scripts/cockpit_v04_verify.py
"""
import functools
import http.server
import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KICK = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
PAST = KICK - timedelta(days=3)
K = KICK.strftime("%Y-%m-%dT%H:%M:%S")
P = PAST.strftime("%Y-%m-%dT%H:%M:%S")
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def soccer_row(home, away, probs, fair):
    return {"home_team": home, "away_team": away, "utc_date": K,
            "prediction": {"probabilities": {"home_win": probs[0], "draw": probs[1], "away_win": probs[2]},
                           "tier": "lean"},
            "market": {"bookmaker_count": 6, "selections": {
                "HOME": {"fair_prob": fair[0]}, "DRAW": {"fair_prob": fair[1]}, "AWAY": {"fair_prob": fair[2]}}},
            "input_quality": {"book_odds": 6}}


def nfl_row(home, away, p_home, fair_h, kal, quarantine=False):
    div = round((p_home - fair_h) * 100, 1)
    return {"home_team": home, "away_team": away, "utc_date": K,
            "prediction": {"home_win_prob": p_home, "away_win_prob": 1 - p_home, "tier": "lean"},
            "market": {"bookmaker_count": 7, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)},
                       "fair_source": "1X2"},
            "market_divergence_pp": div, "quarantine": quarantine,
            "kalshi_prob": kal, "venue_gap_pp": round(abs(fair_h - kal) * 100, 1),
            "input_quality": {"book_odds": 7, "injuries": {"home": {"count": 0, "qb_listed": []},
                                                            "away": {"count": 0, "qb_listed": []}}}}


def fixture(home, away, books, fair, kal, when=K, status="scheduled", hs=None, as_=None):
    return {"home_team": home, "away_team": away, "utc_date": when, "status": status,
            "home_score": hs, "away_score": as_,
            "market": ({"bookmaker_count": books, "fair_prob": {"HOME": fair[0], "AWAY": fair[1]},
                        "fair_source": "1X2"} if books else None),
            "kalshi": ({"status": "two_sided", "prob": {"HOME": kal[0], "AWAY": kal[1]}} if kal else None),
            "input_quality": {"book_odds": books, "kalshi": "two_sided" if kal else "absent"}}


INPUTS = {
    "soccer_preds.json": {"sport": "soccer", "predictions": [
        soccer_row("Arsenal", "Brentford", (0.62, 0.20, 0.18), (0.56, 0.25, 0.19)),   # s1 PLAY -> home win
        soccer_row("Fulham", "Everton", (0.59, 0.22, 0.19), (0.53, 0.27, 0.20)),      # s6 PLAY -> DRAW (side loses)
        soccer_row("Wolves", "Chelsea", (0.20, 0.22, 0.58), (0.30, 0.26, 0.44)),      # s2 LADDER -> DRAW (DC wins)
        soccer_row("Leeds", "Burnley", (0.60, 0.22, 0.18), (0.54, 0.26, 0.20)),       # s7 PLAY -> no result (open)
    ]},
    "nfl_preds.json": {"sport": "nfl", "rehearsal": False, "predictions": [
        nfl_row("Chiefs", "Bills", 0.66, 0.60, 0.61),                     # n3 PLAY -> CANCELLED (void)
        nfl_row("Browns", "Panthers", 0.75, 0.55, 0.50, quarantine=True), # n4 quarantine shadow (5pp venue gap)
        nfl_row("Jets", "Giants", 0.60, 0.72, 0.62),                       # n8 10pp book-Kalshi gap -> NO venue call
    ]},
    "fixtures_NCAA.json": {"competition_code": "NCAA", "fixtures": [
        fixture("Alabama", "Auburn", 5, (0.60, 0.40), (0.50, 0.52)),       # v1 venue: H div ~11pp -> call
        fixture("Ohio State", "Michigan", 5, (0.55, 0.45), (0.54, 0.46)),  # v2 div 1pp -> no call
        fixture("Texas", "Tennessee", 2, (0.70, 0.30), (0.40, 0.60)),      # v3 books 2 -> too thin
        fixture("Oregon", "USC", 6, (0.65, 0.35), None),                   # v4 no kalshi -> single venue
        fixture("Clemson", "Duke", 6, (0.70, 0.30), (0.40, 0.60), when=P), # v6 kickoff passed -> in-play never
    ]},
    "fixtures_UNL.json": {"competition_code": "UNL", "fixtures": [
        fixture("Spain", "France", 8, (0.60, 0.40), (0.40, 0.60)),         # v5 UNL -> excluded
    ]},
}
RESULTS = {
    "soccer_results.json": {"sport": "soccer", "results": [
        {"date": K, "home_team": "Arsenal", "away_team": "Brentford", "actual": {"home_score": 2, "away_score": 0, "result": "H"}},
        {"date": K, "home_team": "Fulham FC", "away_team": "Everton", "actual": {"home_score": 1, "away_score": 1, "result": "D"}},
        {"date": K, "home_team": "Wolves", "away_team": "Chelsea", "actual": {"home_score": 0, "away_score": 0, "result": "D"}},
    ]},
    "fixtures_NFL_finished.json": {"competition_code": "NFL", "fixtures": [
        fixture("Chiefs", "Bills", 7, (0.6, 0.4), None, status="cancelled"),
        fixture("Browns", "Panthers", 7, (0.55, 0.45), None, status="finished", hs=27, as_=13),
    ]},
    "fixtures_NCAA_finished.json": {"competition_code": "NCAA", "fixtures": [
        fixture("Alabama", "Auburn", 5, (0.6, 0.4), None, status="finished", hs=31, as_=10),
    ]},
}
# independent outcome table: (home, away) -> HOME / AWAY / DRAW / VOID
TRUTH = {("Arsenal", "Brentford"): "HOME", ("Fulham", "Everton"): "DRAW", ("Wolves", "Chelsea"): "DRAW",
         ("Chiefs", "Bills"): "VOID", ("Browns", "Panthers"): "HOME", ("Alabama", "Auburn"): "HOME"}


def expected_leg(c):
    o = TRUTH.get((c["home"], c["away"]))
    if o is None:
        return None
    if o == "VOID":
        return "void"
    if c["call_type"] == "ladder":
        return "win" if o in (c["pick"], "DRAW") else "loss"
    if o == c["pick"]:
        return "win"
    return "push" if (o == "DRAW" and not c["three_way"]) else "loss"


def ret(units, res, mp):
    return units / mp if res == "win" else units if res in ("push", "void") else 0.0


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-v04-")
    for name, doc in {**INPUTS, **RESULTS}.items():
        with open(os.path.join(tmp, name), "w") as f:
            json.dump(doc, f)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=os.path.join(ROOT, "tools"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html"

    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") and not os.path.isdir("/opt/pw-browsers/chromium") else None
        browser = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.set_input_files("#predFile", [os.path.join(tmp, n) for n in INPUTS])
        # the loader parses asynchronously, then switches to the Card tab — wait for it
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        page.click("#tabDesk")
        page.wait_for_selector("#venueCard:not([hidden])")

        print("CAPTURE")
        page.click("#logBtn")
        note1 = page.inner_text("#logNote")
        L = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        calls = L["calls"]
        by = lambda **kw: [c for c in calls if all(c.get(k) == v for k, v in kw.items())]
        check("policy_version stamped v1.1", L["meta"]["policy_version"] == "v1.1")
        check("model_edge straights = 4 (s1, s6, s7, n3)", len(by(engine="model_edge", call_type="straight")) == 4)
        check("ladder logged for the Wolves–Chelsea away edge", len(by(call_type="ladder")) == 1
              and by(call_type="ladder")[0]["pick"] == "AWAY")
        sh = by(call_type="quarantine_shadow")
        check("NFL quarantine PASS logged as shadow at units 0", len(sh) == 1 and sh[0]["units"] == 0
              and sh[0]["shadow_units"] == 0.5, f"shadow_units={sh and sh[0].get('shadow_units')}")
        ven = by(engine="venue_edge")
        vg = sorted(c["game"] for c in ven)
        check("venue_edge calls = NCAA Alabama only (market-only charter)", vg == ["Auburn @ Alabama"], str(vg))
        check("NFL row with a 10pp book-Kalshi gap emits NO venue call",
              not [c for c in ven if c["sport"] == "NFL"] and
              "model sport — model_edge only" in page.inner_text("#venueTable"))
        check("venue calls fixed 0.25u, tier shadow, hint kalshi",
              all(c["units"] == 0.25 and c["tier"] == "shadow" and c["venue_hint"] == "kalshi" for c in ven))
        legs = by(call_type="parlay_leg")
        check("parlay legs share parlay_id (model_edge only)", legs and all(c["engine"] == "model_edge" for c in legs)
              and len({c["parlay_id"] for c in legs}) >= 1, f"{len(legs)} legs / {len({c['parlay_id'] for c in legs})} tickets")
        vrows = page.inner_text("#venueTable")
        check("UNL excluded: 'single venue — no pair (UNL)'", "single venue — no pair (UNL)" in vrows)
        check("thin books, missing Kalshi, in-play labelled", "pair too thin" in vrows and
              "single venue — no pair" in vrows and "in-play — never" in vrows)
        slate = page.inner_text("#slate")
        check("quarantined NFL row displays PASS with no units", "QUARANTINE 20" in slate)
        n_before = len(calls)
        page.click("#logBtn")
        L2 = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        check("re-logging is idempotent (no duplicates)", len(L2["calls"]) == n_before,
              f"{n_before} -> {len(L2['calls'])}; {page.inner_text('#logNote')[:60]}")
        print("   ", note1)

        print("GRADE")
        page.click("#tabLedger")
        page.set_input_files("#resultsFile", [os.path.join(tmp, n) for n in RESULTS])
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('graded')")
        print("   ", page.inner_text("#ledgerNote"))
        L = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        calls = L["calls"]
        mism = []
        for c in calls:
            if c["call_type"] == "parlay_leg":
                continue
            exp = expected_leg(c)
            if exp is None:
                if c["status"] != "open":
                    mism.append(("should stay open", c["game"]))
                continue
            u = c["shadow_units"] if c["call_type"] == "quarantine_shadow" else c["units"]
            got = c["shadow_returned"] if c["call_type"] == "quarantine_shadow" else c["units_returned"]
            if c["result"] != exp or abs(got - ret(u, exp, c["market_p"])) > 1e-3:
                mism.append((c["game"], c["call_type"], c["result"], exp, got))
        check("every straight/ladder/venue/shadow graded exactly as the independent grader", not mism, str(mism))
        g = lambda game, ct, eng="model_edge": next(c for c in calls if c["game"] == game and c["call_type"] == ct and c["engine"] == eng)
        s6 = g("Everton @ Fulham", "straight")
        check("soccer draw vs side-pick = LOSS (name matched via normalization 'Fulham FC')",
              s6["result"] == "loss" and s6["units_returned"] == 0)
        lad = g("Chelsea @ Wolves", "ladder")
        check("ladder/DC won by the draw at fair odds 1/(fair A + fair D)",
              lad["result"] == "win" and abs(lad["units_returned"] - 0.5 / 0.70) < 1e-3, f"{lad['units_returned']}")
        n3 = g("Bills @ Chiefs", "straight")
        check("cancelled NFL game = void, stake returned", n3["result"] == "void" and n3["units_returned"] == 1)
        s7 = g("Burnley @ Leeds", "straight")
        check("unmatched call stays open and is listed", s7["status"] == "open" and "Burnley @ Leeds" in page.inner_text("#openList"))
        tickets = {}
        for c in calls:
            if c["call_type"] == "parlay_leg":
                tickets.setdefault(c["parlay_id"], []).append(c)
        tmis, void_ticket = [], False
        for pid, ls in tickets.items():
            res = [expected_leg(x) for x in ls]
            if any(r is None for r in res) and "loss" not in res:
                if ls[0]["status"] != "open":
                    tmis.append((pid, "settled early without a losing leg"))
                continue
            if "loss" in res:
                exp = 0.0
            else:
                live = [x for x, r in zip(ls, res) if r == "win"]
                exp = ls[0]["units"]
                for x in live:
                    exp /= x["market_p"]
            if "void" in res and "loss" not in res and "win" in res:
                void_ticket = True
            if abs(ls[0]["units_returned"] - exp) > 1e-3:
                tmis.append((pid, ls[0]["units_returned"], exp))
        check("parlay tickets settle as the independent grader (void legs dropped)", not tmis, str(tmis))
        print(f"    auto-ranked tickets: {len(tickets)} (void-leg+win ticket among them: {void_ticket})")
        # Deterministic void-leg case through the SAME intake: a crafted 2-leg
        # ticket (Chiefs–Bills cancelled + Arsenal home win) on a fresh ledger.
        crafted = {"meta": {"policy_version": "v1.1"}, "calls": [
            {"id": "t1", "log_date": KICK.strftime("%Y-%m-%d"), "sport": "NFL", "game": "Bills @ Chiefs",
             "home": "Chiefs", "away": "Bills", "kickoff": K, "three_way": False, "status": "open",
             "quarantine": False, "pick": "HOME", "tier": "parlay", "engine": "model_edge",
             "call_type": "parlay_leg", "parlay_id": "PX", "units": 0.25, "model_p": 0.66,
             "market_p": 0.60, "venue_hint": "books", "rules": ["parlay 0.25u"]},
            {"id": "t2", "log_date": KICK.strftime("%Y-%m-%d"), "sport": "SOCCER", "game": "Brentford @ Arsenal",
             "home": "Arsenal", "away": "Brentford", "kickoff": K, "three_way": True, "status": "open",
             "quarantine": False, "pick": "HOME", "tier": "parlay", "engine": "model_edge",
             "call_type": "parlay_leg", "parlay_id": "PX", "units": 0.25, "model_p": 0.62,
             "market_p": 0.56, "venue_hint": "books", "rules": ["parlay 0.25u"]}]}
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", crafted)
        page.evaluate("document.getElementById('ledgerNote').textContent='';"
                      "document.getElementById('resultsFile').value=''")
        page.set_input_files("#resultsFile", [os.path.join(tmp, n) for n in RESULTS])
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('graded')")
        C = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")["calls"]
        leg = {c["id"]: c for c in C}
        check("void leg drops from the ticket: pays 0.25 x (1/0.56) on the surviving win",
              leg["t1"]["result"] == "void" and leg["t2"]["result"] == "win"
              and abs(leg["t1"]["units_returned"] - 0.25 / 0.56) < 1e-3 and leg["t1"]["ticket_result"] == "win",
              f"returned {leg['t1']['units_returned']}")
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", L)   # restore
        page.evaluate("renderLedger()")

        print("REPORT")
        tables = page.inner_text("#ledgerTables")
        check("by-engine / sport / tier / call-type tables rendered",
              all(t in tables.lower() for t in ("by engine", "by sport", "by tier", "by call type", "venue_edge")))
        check("equity SVG with counterfactual line", page.locator("#equity svg polyline").count() == 2)
        rules = page.inner_text("#ruleTable")
        check("per-rule attribution incl. quarantine shadow + venue stale-book zone",
              "quarantine ≥ 15pp (shadow) [shadow]" in rules and "venue gap ≥ 8pp (STALE-BOOK? zone)" in rules)
        block = page.inner_text("#pnlBlock")
        check("P&L block: engines, counterfactual, sizing gate, non-claims",
              all(t in block for t in ("model_edge", "venue_edge", "Quarantine counterfactual",
                                       "/50 graded before any sizing proposal", "Non-claims")))
        check("non-claims footer present", "EV-realization proxy, not cash" in page.inner_text("#nonClaims"))
        check("no page errors", not errors, "; ".join(errors))
        shot = os.environ.get("COCKPIT_SHOT_DIR")      # optional: eyeball the layout
        if shot:
            page.set_viewport_size({"width": 900, "height": 1000})
            page.screenshot(path=os.path.join(shot, "ledger.png"), full_page=True)
            page.click("#tabDesk")
            page.screenshot(path=os.path.join(shot, "desk.png"), full_page=True)
        print("\n----- P&L block (as the operator would copy it) -----")
        print(block)
        browser.close()
    srv.shutdown()
    ok = all(CHECKS)
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed — {'ALL GREEN' if ok else 'FAILURES ABOVE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
