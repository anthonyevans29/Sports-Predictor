"""
Cockpit P0-3 CLV SEMANTICS headless verification (#208, ARCHITECT 2026-10-01):
"rename the stored/graded metric "model-close divergence" everywhere it
appears; add entry-price CLV = q_close − entry on executed ledger positions
(claim and exec), and fee-adjusted closing edge; P&L block gains both.
Existing series kept."

v2 (PR #259 review, Anthony): executed-position CLV comes from the MATCHED
FILL's entry for the HELD contract; claim / re-log movement is reference
movement, labelled apart; calls with no matched fill are not executed.

Over SYNTHETIC files: a Log, a later re-log (claim frozen, exec moves), then
a results file carrying graded.close_fair:
- each graded straight carries close_ref "p0-3 v2" {q_close, fair,
  ref_move_claim, ref_move_relog, quoted_edge_relog} from the PICK's own close;
- a position graded before its close arrived gains close_ref when it does;
- a results row with no close leaves the position without close_ref
  (unavailable, never inferred); a stored legacy clv_v2 is never rewritten;
- REGRESSION sign reversal: q 0.65, re-log 0.60, matched fill at 0.70 ->
  reference movement +5pp, executed entry CLV −5pp;
- REGRESSION no fill: graded calls without a matched fill are excluded from
  the executed series (n 0, counted as excluded);
- a NO fill is priced as the contract held (1 − the NO'd side's close);
- no existing ledger field changes (units_returned, claim prices).

    python3 scripts/cockpit_clv_verify.py

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
import cockpit_desk_files as cdf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.now(timezone.utc).replace(microsecond=0)
D1 = (NOW + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def nfl(home, away, p, fair, ask=None):
    r = {"home_team": home, "away_team": away, "utc_date": D1,
         "prediction": {"home_win_prob": p, "away_win_prob": round(1 - p, 4), "tier": "lean"},
         "market": {"bookmaker_count": 7, "fair_prob": {"HOME": fair, "AWAY": round(1 - fair, 4)}},
         "market_divergence_pp": round((p - fair) * 100, 1), "quarantine": False,
         "input_quality": {"book_odds": 7, "injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}}
    if ask is not None:
        r.update(kalshi_bid=round(ask - 0.02, 2), kalshi_ask=ask, exec_cost_taker=round(ask + 0.017, 3))
    return r


def doc(eagles_fair):
    return {"sport": "nfl", "rehearsal": False, "predictions": [
        nfl("Philadelphia Eagles", "Dallas Cowboys", 0.64, eagles_fair, ask=0.58),   # PLAY with a quote
        nfl("Chicago Bears", "Detroit Lions", 0.66, 0.60),                           # PLAY, no quote
        nfl("Miami Dolphins", "New York Jets", 0.65, 0.58)]}                         # PLAY, its close missing


def results(close):
    rows = []
    for h, a, cf in (("Philadelphia Eagles", "Dallas Cowboys", {"HOME": 0.62, "AWAY": 0.38}),
                     ("Chicago Bears", "Detroit Lions", {"HOME": 0.57, "AWAY": 0.43}),
                     ("Miami Dolphins", "New York Jets", None)):
        g = {"close_fair": cf if close else None, "close_at": D1, "close_source": "close_1x2"} if close else {}
        rows.append({"home_team": h, "away_team": a, "date": D1[:10],
                     "actual": {"home_score": 24, "away_score": 17}, "graded": g})
    return {"sport": "nfl", "results": rows}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-clv-")
    files = {"day1.json": doc(0.58), "day2.json": doc(0.60), "res_noclose.json": results(False),
             "res_close.json": results(True)}
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
        ledger = lambda: page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")  # noqa: E731
        pos = lambda: {c["game"]: c for c in ledger()["calls"] if c["call_type"] == "straight"}  # noqa: E731

        def load(name):
            page.evaluate("document.getElementById('summary').textContent=''")
            cdf.upload(page, os.path.join(tmp, name))
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
            page.click("#tabDesk")
            page.click("#logBtn")

        load("day1.json")
        load("day2.json")                                   # re-log: claim 0.58 frozen, exec moves to 0.60
        print("GRADED BEFORE THE CLOSE ARRIVES")
        page.set_input_files("#resultsFile", os.path.join(tmp, "res_noclose.json"))
        page.wait_for_function("""(()=>{const L=JSON.parse(localStorage.getItem('bd_ledger_v1'));
            return L.calls.filter(c=>c.call_type==='straight').every(c=>c.status==='graded');})()""")
        P = pos()
        e = P["Dallas Cowboys @ Philadelphia Eagles"]
        check("graded, no close in the file -> no clv_v2 (unavailable, never inferred)",
              e["status"] == "graded" and "clv_v2" not in e, json.dumps({k: e.get(k) for k in ("status", "clv_v2")}))
        before = {g: (c["units_returned"], c["claim_market_p"], c["exec_market_p"]) for g, c in P.items()}

        print("CLOSE ARRIVES (results export with graded.close_fair)")
        legacy = {"version": "p0-3 v1", "q_close": 0.5, "clv_exec": 0.99}         # a v1 block already stored
        page.evaluate("""(lg)=>{const L=loadLedger(); L.calls.find(c=>c.game.includes('Eagles')).clv_v2=lg;
            saveLedger(L);}""", legacy)
        page.set_input_files("#resultsFile", os.path.join(tmp, "res_close.json"))
        page.wait_for_function("""(()=>{const L=JSON.parse(localStorage.getItem('bd_ledger_v1'));
            return L.calls.some(c=>c.close_ref);})()""")
        P = pos()
        v = P["Dallas Cowboys @ Philadelphia Eagles"]["close_ref"]
        check("q_close = the pick's own close (0.62); claim ref move +0.04; re-log ref move +0.02",
              (v["q_close"], v["ref_move_claim"], v["ref_move_relog"]) == (0.62, 0.04, 0.02)
              and v["fair"] == {"HOME": 0.62, "AWAY": 0.38} and v["version"] == "p0-3 v2", json.dumps(v))
        check("quoted taker edge @ re-log = q_close − quoted cost (0.62 − 0.597 = +0.023); no 'clv' field",
              v["quoted_edge_relog"] == 0.023 and not any(k.startswith("clv") for k in v), json.dumps(v))
        check("legacy clv_v2 (p0-3 v1) kept exactly as stored, never rewritten",
              P["Dallas Cowboys @ Philadelphia Eagles"].get("clv_v2") == legacy)
        b = P["Detroit Lions @ Chicago Bears"]["close_ref"]
        check("no side-specific quote -> quoted edge null; ref move still computed (0.57 − 0.60 = −0.03)",
              b["quoted_edge_relog"] is None and b["ref_move_relog"] == -0.03, json.dumps(b))
        check("a row with no close keeps no close_ref", "close_ref" not in P["New York Jets @ Miami Dolphins"])
        check("existing series kept: units_returned and claim/exec prices unchanged",
              {g: (c["units_returned"], c["claim_market_p"], c["exec_market_p"]) for g, c in P.items()} == before)

        print("P&L BLOCK")
        pnl = page.evaluate("pnlBlock(loadLedger())")
        sec = pnl[pnl.index("EXECUTED-POSITION CLV"):].split("\n")[:10]
        check("REGRESSION no fill: graded calls without a matched fill are NOT executed positions",
              any("entry-price CLV" in s and "n 0" in s for s in sec)
              and any("2 graded call(s) with a close · 0 executed (matched fill) · 2 without matched execution"
                      in s for s in sec), "\n".join(sec))
        check("reference movement printed apart, labelled not-CLV: claim +0.50pp mean, re-log −0.50pp, quoted n 1",
              any("REFERENCE MOVEMENT (not CLV" in s for s in sec)
              and any("claim ref → close" in s and "n   2" in s and "mean +0.50pp" in s for s in sec)
              and any("re-log ref → close" in s and "mean -0.50pp" in s for s in sec)
              and any("quoted taker edge @ re-log" in s and "n   1" in s for s in sec), "\n".join(sec))
        stub = """(fills)=>{const L=loadLedger(); const id=g=>L.calls.find(c=>c.game.includes(g)).id;
            const keep=classifyFills; classifyFills=()=>fills.map(f=>({book:'system_matched',...f,call_id:id(f.g)}));
            const out={lines:clvLines(L),ex:executedPositions(L)}; classifyFills=keep; return out;}"""
        r = page.evaluate(stub, [{"g": "Eagles", "qty": 10, "entry": 0.58, "open_fee": 0.17, "backed_role": "HOME"}])
        real = [s for s in r["lines"] if "fee-adj edge" in s][0]
        check("one matched fill: entry CLV 0.62 − 0.58 = +4.00pp; fee-adj − 0.17/10 = +2.30pp; Bears excluded",
              any("entry-price CLV" in s and "n   1" in s and "mean +4.00pp" in s for s in r["lines"])
              and "n   1" in real and "mean +2.30pp" in real
              and any("1 executed (matched fill) · 1 without matched execution" in s for s in r["lines"]),
              "\n".join(r["lines"][:4]))
        rev = page.evaluate("""(fills)=>{const L=loadLedger(); const c=L.calls.find(x=>x.game.includes('Eagles'));
            c.close_ref=clvBlock({...c,claim_market_p:0.60,exec_market_p:0.60},{close:{fair:{HOME:0.65,AWAY:0.35}}});
            const keep=classifyFills; classifyFills=()=>fills.map(f=>({book:'system_matched',...f,call_id:c.id}));
            const ex=executedPositions(L); classifyFills=keep; return {ref:c.close_ref,ex};}""",
            [{"qty": 10, "entry": 0.70, "open_fee": 0, "backed_role": "HOME"}])
        check("REGRESSION sign reversal: q 0.65, re-log 0.60, fill 0.70 -> ref move +5pp, executed entry CLV −5pp",
              rev["ref"]["ref_move_relog"] == 0.05 and len(rev["ex"]["pos"]) == 1
              and round(rev["ex"]["pos"][0]["clv"], 4) == -0.05, json.dumps(rev))
        r = page.evaluate(stub, [{"g": "Eagles", "qty": 4, "entry": 0.60, "open_fee": 0, "backed_role": "HOME"},
                                 {"g": "Eagles", "qty": 6, "entry": 0.30, "open_fee": 0, "backed_role": "HOME",
                                  "no_on_role": "AWAY"},
                                 {"g": "Bears", "qty": 5, "entry": 0.50, "open_fee": 0, "backed_role": None}])
        p0 = r["ex"]["pos"]
        check("held contract priced as held: YES 0.62−0.60, NO-on-away (1−0.38)−0.30, qty-weighted = +20.0pp;"
              " an unpriceable held contract is excluded and counted",
              len(p0) == 1 and round(p0[0]["clv"], 4) == round((4 * 0.02 + 6 * 0.32) / 10, 4)
              and r["ex"]["unpriced"] == 1, json.dumps(r["ex"]))
        ci = page.evaluate("clusterCI([{v:0.01,day:'a'},{v:0.03,day:'a'},{v:-0.02,day:'b'},{v:0.05,day:'c'}])")
        ci2 = page.evaluate("clusterCI([{v:0.01,day:'a'},{v:0.03,day:'a'},{v:-0.02,day:'b'},{v:0.05,day:'c'}])")
        check("day-clustered 90% bootstrap CI: bounded by the day means, reproducible (seeded)",
              ci == ci2 and -0.02 <= ci[0] <= ci[1] <= 0.05, json.dumps(ci))
        check("the stored per-game metric is named model-close divergence in the block",
              "model-close divergence" in pnl)
        check("no page errors", not errors, "; ".join(errors[:3]))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
