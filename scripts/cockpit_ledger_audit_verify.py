"""
Cockpit LEDGER KICKOFF AUDIT headless verification (ARCHITECT 2026-10-01,
#178 follow-on). Seeds a SYNTHETIC ledger and checks:
- a clean position (claim + execution before the true UTC kickoff) is
  untouched;
- execution after kickoff, claim before -> flagged "post-kickoff (tz bug)",
  P&L recomputed at the CLAIM price; the claim counterfactual stays;
- a logged reprice history -> the LAST PRE-KICKOFF reprice is used;
- claim after kickoff (no pre-kickoff price) -> excluded from the P&L,
  counted, never deleted;
- legacy (no claim_at) captured after kickoff -> excluded;
- no parseable kickoff -> never flagged (law 4: unknown stays unknown);
- an operator_early execution before kickoff with later post-kickoff
  reprices -> flagged, priced at the (pre-kickoff) execution;
- a parlay with one post-kickoff leg -> the ticket is recomputed at the
  audited leg prices; a value shadow likewise at notional units;
- the P&L block carries the one-line count; the totals show it;
- saving marks tz_audit on flagged positions and changes NO stored field;
  the call count is unchanged;
- stampTiming appends every capture to `reprices` (going forward).

    python3 scripts/cockpit_ledger_audit_verify.py

Writes nothing to the repo; no DB. Needs Playwright + Chromium.
"""
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKS = []
KO = "2026-09-29T23:05:00"                 # naive UTC, as every export writes it
PRE, PRE2, POST = "2026-09-29T21:00:00.000Z", "2026-09-29T22:30:00.000Z", "2026-09-30T01:40:00.000Z"


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def call(i, **kw):
    c = {"id": f"c{i}", "log_date": "2026-09-29", "sport": "MLB", "game": f"A{i} @ H{i}", "home": f"H{i}",
         "away": f"A{i}", "kickoff": KO, "pick": "HOME", "engine": "model_edge", "call_type": "straight",
         "units": 1, "status": "graded", "result": "win", "tier": "lean", "rules": [], "graded_date": "2026-09-30",
         "exec_mode": "close_default"}
    c.update(kw)
    return c


def straight(i, claim_at, claim_p, exec_at, exec_p, **kw):
    return call(i, claim_at=claim_at, claim_market_p=claim_p, executed_at=exec_at, exec_market_p=exec_p,
                market_p=exec_p, units_returned=round(1 / exec_p, 4), claim_units_returned=round(1 / claim_p, 4),
                **kw)


LEDGER = {"meta": {"policy_version": "v1.1"}, "calls": [
    straight(1, PRE, 0.50, PRE2, 0.52),                                        # clean
    straight(2, PRE, 0.50, POST, 0.60),                                        # exec post -> claim .50
    straight(3, PRE, 0.50, POST, 0.60, reprices=[{"at": PRE, "market_p": 0.50}, {"at": PRE2, "market_p": 0.55},
                                                 {"at": POST, "market_p": 0.60}]),   # -> last pre .55
    straight(4, POST, 0.60, POST, 0.60),                                       # claim post -> excluded
    call(5, captured_at=POST, market_p=0.60, units_returned=round(1 / 0.6, 4), exec_mode=None),  # legacy post
    straight(6, PRE, 0.50, POST, 0.60, kickoff=None),                          # no kickoff -> unknown
    straight(7, PRE, 0.50, PRE2, 0.52, exec_mode="operator_early",
             reprices=[{"at": PRE, "market_p": 0.5}, {"at": POST, "market_p": 0.6}]),   # early, pre -> .52
    # parlay: two legs, leg b executed after kickoff (claim .40 pre)
    call(8, call_type="parlay_leg", parlay_id="P-2026-09-29-x", units=0.25, claim_at=PRE, claim_market_p=0.50,
         executed_at=PRE2, exec_market_p=0.50, units_returned=round(0.25 / 0.5 / 0.5, 4), ticket_result="win",
         claim_units_returned=round(0.25 / 0.5 / 0.4, 4)),
    call(9, call_type="parlay_leg", parlay_id="P-2026-09-29-x", units=0.25, claim_at=PRE, claim_market_p=0.40,
         executed_at=POST, exec_market_p=0.50, units_returned=round(0.25 / 0.5 / 0.5, 4), ticket_result="win",
         claim_units_returned=round(0.25 / 0.5 / 0.4, 4)),
    # value shadow, executed after kickoff, claim .30 pre
    call(10, call_type="value_shadow", units=0, shadow_units=0.25, claim_at=PRE, claim_market_p=0.30,
         executed_at=POST, exec_market_p=0.40, market_p=0.40, shadow_returned=round(0.25 / 0.4, 4),
         claim_shadow_returned=round(0.25 / 0.3, 4)),
    call(11, status="open", result=None, claim_at=PRE, claim_market_p=0.5, executed_at=POST, exec_market_p=0.6,
         market_p=0.6, kickoff="2099-01-01T00:00:00"),                        # open, future KO: clean
]}


def main():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.join(ROOT, "tools")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html"
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        page = browser.new_context(timezone_id="America/New_York").new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.evaluate(f"localStorage.setItem('bd_ledger_v1', {json.dumps(json.dumps(LEDGER))})")
        page.goto(url)
        A = {c["id"]: c for c in page.evaluate("loadLedger().calls.map(c=>({id:c.id,...auditCall(c)}))")}
        bets = page.evaluate("settledBets(loadLedger()).map(b=>({...b}))")
        audit = page.evaluate("lastAudit")

        check("clean position: not flagged", not A["c1"]["flagged"], json.dumps(A["c1"]))
        check("exec after kickoff, claim before → flagged, priced at the claim (.50)",
              A["c2"]["flagged"] and A["c2"]["execPost"] and not A["c2"]["claimPost"] and A["c2"]["price"] == 0.5
              and A["c2"]["basis"] == "claim", json.dumps(A["c2"]))
        check("reprice history → the last PRE-kickoff reprice (.55)", A["c3"]["price"] == 0.55
              and A["c3"]["basis"] == "last pre-kickoff reprice" and A["c3"]["postReprices"] == 1, json.dumps(A["c3"]))
        check("claim after kickoff → excluded (no pre-kickoff price)", A["c4"]["excluded"] and A["c4"]["claimPost"],
              json.dumps(A["c4"]))
        check("legacy, captured after kickoff → excluded", A["c5"]["excluded"], json.dumps(A["c5"]))
        check("no kickoff → never flagged (unknown stays unknown)", not A["c6"]["checked"] and not A["c6"]["flagged"],
              json.dumps(A["c6"]))
        check("operator_early before kickoff + a post-kickoff reprice → flagged, priced at the execution (.52)",
              A["c7"]["flagged"] and not A["c7"]["execPost"] and A["c7"]["price"] == 0.52, json.dumps(A["c7"]))
        check("open position with a future kickoff: clean", not A["c11"]["flagged"], json.dumps(A["c11"]))

        real = [b for b in bets if not b["shadow"]]
        ret = sorted(round(b["returned"], 4) for b in real if b["call_type"] == "straight")
        want = sorted([round(1 / 0.52, 4), 2.0, round(1 / 0.55, 4), round(1 / 0.6, 4), round(1 / 0.52, 4)])
        check("straight P&L: c1 stored, c2 @ .50, c3 @ .55, c6 stored, c7 @ .52; c4/c5 out", ret == want,
              f"{ret} vs {want}")
        check("audited claim counterfactual kept where the claim was pre-kickoff",
              any(b["claimReturned"] == 2.0 and b["returned"] == 2.0 for b in real), "")
        par = [b for b in real if b["call_type"] == "parlay"]
        check("parlay recomputed at audited legs (.50 × claim .40): 0.25/.5/.4 = 1.25",
              len(par) == 1 and par[0]["returned"] == 1.25 and par[0]["tz"], json.dumps(par))
        sh = [b for b in bets if b["shadow"]]
        check("value shadow recomputed at the claim .30 (notional 0.25u → 0.8333)",
              len(sh) == 1 and sh[0]["returned"] == round(0.25 / 0.3, 4) and sh[0]["staked"] == 0.25, json.dumps(sh))
        check("counts: 7 flagged · 5 re-priced · 2 excluded",
              audit == {"flagged": 7, "fallback": 5, "excluded": 2, "legNotPlay": 0}, json.dumps(audit))
        pnl = page.evaluate("pnlBlock(loadLedger())")
        line = next((ln for ln in pnl.splitlines() if ln.startswith("Kickoff audit (#178)")), "")
        check("P&L block carries the one-line count", "7 settled position(s)" in line and "post-kickoff (tz bug)" in line
              and "5 re-priced" in line and "2 excluded" in line and "never deleted" in line, line)

        page.evaluate("renderLedger()")
        tot = page.inner_text("#tzAudit") if page.query_selector("#tzAudit") else ""
        check("ledger totals show the audit line", "Kickoff audit (#178)" in tot, tot)

        before = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1')).calls")
        page.evaluate("saveLedger(loadLedger())")
        after = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1')).calls")
        strip = lambda c: {k: v for k, v in c.items() if k != "tz_audit"}
        check("save: call count unchanged, every stored field unchanged (never deleted)",
              len(after) == len(before) and [strip(c) for c in after] == before, f"{len(before)} → {len(after)}")
        marks = {c["id"]: c.get("tz_audit") for c in after}
        check("save: tz_audit marks on the 7 flagged legs/positions only (parlay: per leg)",
              {k for k, v in marks.items() if v} == {"c2", "c3", "c4", "c5", "c7", "c9", "c10"}
              and marks["c4"]["excluded"] and marks["c2"]["flag"] == "post-kickoff (tz bug)", json.dumps(marks)[:300])
        rp = page.evaluate("""(()=>{const p=stampTiming({},{captured_at:'2026-10-01T10:00:00.000Z',market_p:.5,model_p:.6},true);
            stampTiming(p,{captured_at:'2026-10-01T11:00:00.000Z',market_p:.52,model_p:.6},false); return p.reprices})()""")
        check("stampTiming appends every capture to reprices", [x["market_p"] for x in rp] == [0.5, 0.52], json.dumps(rp))
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
