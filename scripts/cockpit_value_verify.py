"""
Cockpit VALUE-SIDE SHADOW headless verification (policy v1.2 CANDIDATE,
architect 2026-09-29, after Week 4 MNF: model CHI 48.9 vs market 35.5 =
+13.4pp on the DOG; the top-pick-anchored Desk said PASS; CHI won 27-7).
Checks, over SYNTHETIC files:
- the MNF shape: top pick PHI is PASS (edge -13.4pp) AND a value_shadow row
  renders on the dog with the reason "value on dog: +13.4pp";
- no value shadow when the other side is under the 4pp floor, when the top
  pick itself carries the edge (2-way), or for a pre-gate sport (NHL);
- 3-way boards: a DRAW value side is labelled "value on draw";
- the value row never counts as correlated exposure and never becomes a parlay leg;
- Log writes a value_shadow (engine model_edge, units 0, shadow_units 0.25),
  a re-log does not duplicate it, and it has no "Execute now" button;
- grading settles it like a quarantine shadow (notional, at 1/market_p),
  keeps it OUT of the real P&L, and the P&L block carries its own
  "Value-side counterfactual" line with the 30-graded promotion counter.

    python3 scripts/cockpit_value_verify.py

Writes nothing to the repo; no DB. Needs Playwright + Chromium.
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
NOW = datetime.now(timezone.utc).replace(microsecond=0)
ISO = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S")
D1 = ISO(NOW + timedelta(days=1))
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def nfl(home, away, p_home, fair_home):
    return {"home_team": home, "away_team": away, "utc_date": D1,
            "prediction": {"home_win_prob": p_home, "away_win_prob": round(1 - p_home, 4), "tier": "lean"},
            "market": {"bookmaker_count": 7, "fair_prob": {"HOME": fair_home, "AWAY": round(1 - fair_home, 4)}},
            "market_divergence_pp": round((p_home - fair_home) * 100, 1), "quarantine": False,
            "input_quality": {"book_odds": 7, "injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}}


NFL_DOC = {"sport": "nfl", "rehearsal": False, "predictions": [
    nfl("Chicago Bears", "Philadelphia Eagles", 0.489, 0.355),    # MNF: value on the home dog
    nfl("Dallas Cowboys", "New York Giants", 0.46, 0.43),         # other side +3pp: under the floor
    nfl("Buffalo Bills", "Miami Dolphins", 0.66, 0.60),           # top pick carries the edge: normal PLAY
]}
SOCCER_DOC = {"sport": "soccer", "rehearsal": False, "predictions": [
    {"home_team": "Arsenal", "away_team": "Chelsea", "utc_date": D1,
     "prediction": {"probabilities": {"home_win": 0.45, "draw": 0.33, "away_win": 0.22}},
     "market": {"bookmaker_count": 9, "fair_prob": {"HOME": 0.47, "DRAW": 0.27, "AWAY": 0.26}}},
]}
NHL_DOC = {"sport": "nhl", "rehearsal": False, "predictions": [
    {"home_team": "Boston Bruins", "away_team": "Toronto Maple Leafs", "utc_date": D1,
     "prediction": {"home_win_prob": 0.45}, "market": {"bookmaker_count": 6, "fair_prob": {"HOME": 0.62, "AWAY": 0.38}}},
]}
RESULTS = {"sport": "nfl", "results": [
    {"home_team": "Chicago Bears", "away_team": "Philadelphia Eagles", "date": D1[:10],
     "actual": {"home_score": 27, "away_score": 7}},
    {"home_team": "Buffalo Bills", "away_team": "Miami Dolphins", "date": D1[:10],
     "actual": {"home_score": 20, "away_score": 17}}]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-value-")
    files = {"nfl.json": NFL_DOC, "soccer.json": SOCCER_DOC, "nhl.json": NHL_DOC, "results.json": RESULTS}
    for n, d in files.items():
        with open(os.path.join(tmp, n), "w") as f:
            json.dump(d, f)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.join(ROOT, "tools")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html")
        ledger = lambda: page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")

        def load(name):
            page.evaluate("document.getElementById('summary').textContent=''")
            page.set_input_files("#predFile", os.path.join(tmp, name))
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
            page.click("#tabDesk")

        def slate():
            return page.evaluate("""Array.from(document.querySelectorAll('#slate tbody tr')).map(tr=>({
                v:tr.classList.contains('vshadow'),cells:Array.from(tr.children).map(td=>td.textContent)}))""")

        print("DESK (NFL: the MNF shape)")
        load("nfl.json")
        rows = slate()
        main_rows = [r for r in rows if not r["v"]]
        vrows = [r for r in rows if r["v"]]
        mnf = next(r for r in main_rows if "Chicago Bears" in r["cells"][0])
        check("top pick (Philadelphia) is PASS: the top-pick-anchored edge is -13.4pp",
              "Philadelphia" in mnf["cells"][1] and mnf["cells"][5] == "PASSbelow floor" and mnf["cells"][4] == "-13.4pp", str(mnf["cells"][:6]))
        check("exactly one value-shadow row, on the dog (Chicago)", len(vrows) == 1 and vrows[0]["cells"][1] == "Chicago Bears",
              str([r["cells"][:2] for r in vrows]))
        v = vrows[0]["cells"]
        check("value row reason reads 'value on dog: +13.4pp' (model 48.9% vs market 35.5%)",
              "value on dog: +13.4pp" in v[7] and "model 48.9% vs market 35.5%" in v[7] and "NOT staked" in v[7], v[7])
        check("value row call is 'VALUE 0.25u (shadow)', no staked units", v[5] == "VALUE 0.25u (shadow)" and v[6] == "—")
        check("under-floor other side (+3pp) and a top-pick edge emit no value shadow",
              not any(("Dallas" in r["cells"][0] or "Buffalo" in r["cells"][0]) for r in vrows))
        summary = page.inner_text("#summary")
        check("summary counts the value shadow separately, not as a play",
              "1 play" in summary and "1 value shadow (not staked)" in summary and "correlated" not in summary, summary)
        par = page.evaluate("deskParlays.map(t=>t.legs.map(l=>l.home))")
        check("value row is never a parlay leg", all("Chicago Bears" not in legs for legs in par), str(par))

        print("LOG + RE-LOG")
        page.click("#logBtn")
        note = page.inner_text("#logNote")
        vs = [c for c in ledger()["calls"] if c["call_type"] == "value_shadow"]
        check("Log writes one value_shadow: engine model_edge, pick HOME (Chicago), units 0, shadow 0.25",
              len(vs) == 1 and vs[0]["engine"] == "model_edge" and vs[0]["pick"] == "HOME" and vs[0]["units"] == 0
              and vs[0]["shadow_units"] == 0.25 and vs[0]["value_role"] == "dog" and vs[0]["top_pick"] == "AWAY"
              and vs[0]["market_p"] == 0.355 and vs[0]["value_edge_pp"] == 13.4, json.dumps(vs[:1]))
        check("log note names the value shadow", "model_edge (value shadow) 1" in note, note)
        page.click("#logBtn")
        check("re-log does not duplicate the position",
              len([c for c in ledger()["calls"] if c["call_type"] == "value_shadow"]) == 1)
        page.click("#tabLedger")
        vid = vs[0]["id"]
        check("value shadow has no 'Execute now' button (shadows are not executable)",
              page.locator(f"button.execBtn[data-id='{vid}']").count() == 0)

        print("GRADE + P&L")
        real_before = page.evaluate("agg(settledBets(loadLedger()).filter(b=>!b.shadow))")
        page.set_input_files("#resultsFile", os.path.join(tmp, "results.json"))
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('graded')")
        g = next(c for c in ledger()["calls"] if c["call_type"] == "value_shadow")
        check("CHI 27-7: value shadow WIN settled at notional 0.25/0.355, units_returned 0",
              g["result"] == "win" and abs(g["shadow_returned"] - 0.25 / 0.355) < 1e-3 and g["units_returned"] == 0,
              f"{g['result']} {g.get('shadow_returned')} {g.get('units_returned')}")
        real = page.evaluate("agg(settledBets(loadLedger()).filter(b=>!b.shadow))")
        check("real P&L carries only the Buffalo straight (the shadow is never staked)",
              real["n"] == 1 and real_before["n"] == 0, str(real))
        page.click("#copyPnlBtn")
        block = page.inner_text("#pnlBlock")
        net = 0.25 / 0.355 - 0.25
        check("P&L block: own 'Value-side counterfactual' line with the 30-graded counter",
              f"Value-side counterfactual (v1.2 candidate shadow, NOT staked): n 1 · notional staked 0.25 · net +{net:.2f}" in block
              and "promotion review at 30 graded (1/30), version bump only" in block, block)
        check("quarantine counterfactual line unchanged (n 0 here)",
              "Quarantine counterfactual (shadow, NOT staked): n 0" in block)
        tables = page.inner_text("#ledgerTables")
        check("ledger tables: value-side counterfactual table by sport", "value-side counterfactual" in tables.lower() and "NFL" in tables)

        print("OTHER SPORTS")
        load("soccer.json")
        vrows = [r for r in slate() if r["v"]]
        check("3-way board: DRAW value side is labelled 'value on draw' (+6.0pp)",
              len(vrows) == 1 and vrows[0]["cells"][1] == "Draw" and "value on draw: +6.0pp" in vrows[0]["cells"][7],
              str([r["cells"] for r in vrows]))
        load("nhl.json")
        check("pre-gate sport (NHL, pass-all) emits no value shadow", not any(r["v"] for r in slate()))
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
