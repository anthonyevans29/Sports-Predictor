"""
Cockpit EXECUTION-TIMING headless verification (policy v1.1 addendum, 2026-09-28).

A position carries claim_at (first prediction; claim price FROZEN) and
executed_at (default = the last freshen before kickoff; or an explicit,
recorded operator-early execution that locks). Checks, over SYNTHETIC files:
- first Log stamps claim_at / claim_market_p and execution "close_default";
- a later-day re-log with moved prices keeps the claim, moves the default
  execution to the new price, and does NOT move an operator-early execution;
- "Execute now" records operator_early with its inputs (edge, QB listed) and
  flags a QB-listed execution as outside the doctrine's input-stable condition;
- grading settles at the EXECUTION price and books the claim-price
  counterfactual; the P&L block carries the "claim vs exec" column and the
  EXECUTION TIMING section; a pre-rule position is labelled, never backfilled.

    python3 scripts/cockpit_timing_verify.py

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cockpit_desk_files as cdf  # noqa: E402  (F1c: the Cockpit renders desk files only)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.now(timezone.utc).replace(microsecond=0)
ISO = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S")
D1 = ISO(NOW + timedelta(days=1))
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def nfl(home, away, p, fair, qbs=()):
    return {"home_team": home, "away_team": away, "utc_date": D1,
            "prediction": {"home_win_prob": p, "away_win_prob": round(1 - p, 4), "tier": "lean"},
            "market": {"bookmaker_count": 7, "fair_prob": {"HOME": fair, "AWAY": round(1 - fair, 4)}},
            "market_divergence_pp": round((p - fair) * 100, 1), "quarantine": False,
            "input_quality": {"book_odds": 7, "injuries": {"home": {"qb_listed": list(qbs)},
                                                            "away": {"qb_listed": []}}}}


def doc(eagles_fair, bears_fair):
    return {"sport": "nfl", "rehearsal": False, "predictions": [
        nfl("Philadelphia Eagles", "Dallas Cowboys", 0.64, eagles_fair),                    # default: execute at close
        nfl("Chicago Bears", "Detroit Lions", 0.66, bears_fair),                            # operator executes EARLY
        nfl("Miami Dolphins", "New York Jets", 0.65, 0.56, qbs=("T. Tagovailoa",)),         # early on a QB-listed game, 9pp
    ]}


RESULTS = {"sport": "nfl", "results": [
    {"home_team": h, "away_team": a, "date": D1[:10], "actual": {"home_score": 24, "away_score": 17}}
    for h, a in (("Philadelphia Eagles", "Dallas Cowboys"), ("Chicago Bears", "Detroit Lions"),
                 ("Miami Dolphins", "New York Jets"))]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-timing-")
    files = {"day1.json": doc(0.58, 0.60), "day2.json": doc(0.56, 0.55), "results.json": RESULTS}
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
        pos = lambda: {c["game"]: c for c in ledger()["calls"] if c["call_type"] == "straight"}

        def load(name):
            page.evaluate("document.getElementById('summary').textContent=''")
            cdf.upload(page, os.path.join(tmp, name))
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
            page.click("#tabDesk")

        print("CLAIM (day 1)")
        load("day1.json")
        page.click("#logBtn")
        P = pos()
        e1 = P["Dallas Cowboys @ Philadelphia Eagles"]
        check("claim stamped at first capture (claim_at, claim price frozen, model p)",
              bool(e1.get("claim_at")) and e1["claim_market_p"] == 0.58 and e1["claim_model_p"] == 0.64, str({k: e1.get(k) for k in ("claim_at", "claim_market_p")}))
        check("execution defaults to close_default at the capture price",
              e1["exec_mode"] == "close_default" and e1["exec_market_p"] == 0.58)

        print("OPERATOR EARLY EXECUTION")
        page.click("#tabLedger")
        page.click(f"button.execBtn[data-id='{P['Detroit Lions @ Chicago Bears']['id']}']")
        n1 = page.inner_text("#ledgerNote")
        b1 = pos()["Detroit Lions @ Chicago Bears"]
        check("Execute now → operator_early at the current price, inputs recorded",
              b1["exec_mode"] == "operator_early" and b1["exec_market_p"] == 0.60
              and b1["early_inputs"] == {"edge_pp": 6.0, "qb_listed": [], "quarantine": False,
                                         "marker_pp": 8, "below_marker": True}, n1)
        check("ruling (1): 6pp early execution flagged below the provisional 8pp marker (not blocked)",
              "below the provisional 8pp marker (recorded, not enforced)" in n1)
        check("input-stable early execution is not flagged", "outside the doctrine" not in n1)
        page.click(f"button.execBtn[data-id='{P['New York Jets @ Miami Dolphins']['id']}']")
        n2 = page.inner_text("#ledgerNote")
        check("early execution on a QB-listed game is RECORDED AS SUCH",
              "QB listed: T. Tagovailoa" in n2 and "outside the doctrine's input-stable condition" in n2, n2)
        check("9pp early execution is NOT below the marker",
              "below the provisional" not in n2
              and pos()["New York Jets @ Miami Dolphins"]["early_inputs"]["below_marker"] is False)
        rows = page.inner_text("#openList")
        check("open list shows claim + execution (early / at close)", "early 0.600" in rows and "at close 0.580" in rows)

        print("FRESHEN (day 2, prices moved)")
        page.evaluate("localDate=(d)=>{d=d||new Date(Date.now()+86400000);"
                      "return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}")
        load("day2.json")
        page.click("#logBtn")
        P2 = pos()
        e2, b2 = P2["Dallas Cowboys @ Philadelphia Eagles"], P2["Detroit Lions @ Chicago Bears"]
        check("claim unchanged by the freshen (0.58 frozen)", e2["claim_market_p"] == 0.58 and e2["claim_at"] == e1["claim_at"])
        check("default execution follows the last freshen (0.58 → 0.56, executed_at moved)",
              e2["exec_market_p"] == 0.56 and e2["executed_at"] > e1["executed_at"], f"{e1['executed_at']} → {e2['executed_at']}")
        check("operator-early execution is LOCKED (stays 0.60) while price context updates (0.55)",
              b2["exec_market_p"] == 0.60 and b2["market_p"] == 0.55 and b2["exec_mode"] == "operator_early")

        print("GRADE + P&L BLOCK")
        # a pre-rule graded position (no claim) — must be labelled, never backfilled
        L = ledger()
        L["calls"].append({"id": "legacy-1", "log_date": "2026-09-20", "sport": "NFL", "game": "A @ B", "home": "B",
                           "away": "A", "kickoff": "2026-09-21T17:00:00", "status": "graded", "result": "win",
                           "pick": "HOME", "tier": "lean", "engine": "model_edge", "call_type": "straight",
                           "units": 1, "model_p": 0.6, "market_p": 0.5, "units_returned": 2.0,
                           "graded_date": "2026-09-22", "rules": []})
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", L)
        page.set_input_files("#resultsFile", os.path.join(tmp, "results.json"))
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('graded')")
        G = pos()
        eg, bg = G["Dallas Cowboys @ Philadelphia Eagles"], G["Detroit Lions @ Chicago Bears"]
        u = eg["units"]
        check("default: settled at the EXECUTION price (1/0.56), claim counterfactual at 1/0.58",
              abs(eg["units_returned"] - u / 0.56) < 1e-3 and abs(eg["claim_units_returned"] - u / 0.58) < 1e-3,
              f"{eg['units_returned']} vs claim {eg['claim_units_returned']}")
        check("early: settled at the locked 0.60 (not the 0.55 close)",
              abs(bg["units_returned"] - bg["units"] / 0.60) < 1e-3)
        block = page.inner_text("#pnlBlock")
        print(block)
        real, seen = [], set()                       # one bet per straight, one per parlay TICKET
        for c in ledger()["calls"]:
            if c["status"] != "graded" or c["call_type"] == "quarantine_shadow":
                continue
            if c["call_type"] == "parlay_leg":
                if c["parlay_id"] in seen:
                    continue
                seen.add(c["parlay_id"])
            real.append(c)
        known = [c for c in real if c.get("claim_units_returned") is not None]
        delta = sum(c["units_returned"] - c["claim_units_returned"] for c in known)
        check("P&L block: 'claim vs exec' column on the engine lines",
              "claim vs exec" in block and f"{'+' if delta >= 0 else ''}{delta:.2f}/{len(known)}" in block,
              f"expected {delta:+.2f}/{len(known)}")
        check("P&L block: EXECUTION TIMING section with both modes",
              "EXECUTION TIMING" in block and "close_default" in block and "operator_early" in block)
        check("P&L block: early-execution tally with marker + 50-position revisit",
              "Early executions: 2 position(s) · below the provisional 8pp marker: 1 · "
              "threshold revisit at 50 executed positions (2/50)" in block)
        check("pre-rule position labelled, never backfilled",
              "Claim unknown (logged before the rule): 1 settled bet(s) excluded" in block)
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
