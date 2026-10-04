"""
#211 B-TRACK FILLS EXPOSURE (ARCHITECT lane 3, 2026-10-04): "fills-based
exposure and cash-at-risk per team-outcome, from the imported Kalshi CSV,
beside the units-based cap". DIAGNOSTIC ONLY (cap and sizing unchanged).
A SYNTHETIC Kalshi CSV (the real export's header) imported through the
Ledger tab's file input. Checks:
- opposing two-way fills hedge: cash at risk = gross + fees − the smaller side;
- a NO contract pays on every other outcome (NO on the away = the home side);
- soccer settles three ways: a home + away pair is NOT hedged (the tie);
- a team-outcome above the 1.25u cap-equivalent (10 contracts per 1u) is flagged;
- a fill whose contract role the ticker does not decide is excluded, counted;
- load-order invariance: the same fills in reverse order give the same result;
- the Ledger tab renders the table and the P&L text carries the headline.

    python3 scripts/cockpit_exposure_verify.py

Writes nothing to the repo; no DB. Needs Playwright + Chromium.
"""
import functools
import http.server
import json
import os
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKS = []
HDR = ("subtrader_id,type,quantity_fp,market_ticker,side,entry_price_dollars,exit_price_dollars,"
       "open_fees_dollars,close_fees_dollars,realized_pnl_without_fees_dollars,"
       "realized_pnl_with_fees_dollars,close_timestamp,open_timestamp,product,period_start,market_title")
# ticker, side, qty, entry, open fee
FILLS = [
    ("KXNFLGAME-26SEP28BUFKC-KC", "yes", 3, 0.56, 0.06),       # KC (home) 3
    ("KXNFLGAME-26SEP28BUFKC-BUF", "yes", 2, 0.44, 0.04),      # BUF (away) 2 -> hedges 2
    ("KXNFLGAME-26SEP28CARCLE-CAR", "no", 4, 0.50, 0.05),      # NO on CAR (away) = CLE (home) 4
    ("KXNFLGAME-26SEP28DALPHI-PHI", "yes", 15, 0.60, 0.10),    # PHI (home, ticker suffix) 15 contracts = 1.5u > 1.25u
    ("KXEPLGAME-26OCT04ARSCHE-CHE", "yes", 5, 0.45, 0.06),     # soccer home 5
    ("KXEPLGAME-26OCT04ARSCHE-ARS", "yes", 5, 0.30, 0.05),     # soccer away 5 -> tie unhedged
    ("KXNFLGAME-26SEP28KCKC-KC", "yes", 1, 0.50, 0.01),        # role undecidable -> excluded
]


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def csv(rows):
    out = [HDR]
    for t, sd, q, en, of in rows:
        out.append(f'sub-1,trade,{q:.2f},{t},{sd},{en:.8f},0.00000000,{of:.8f},0.00000000,0.00000000,0.00000000,'
                   f'2026-09-28T18:00:00-05:00,2026-09-27T07:00:00-05:00,predictions,2026-09-01,""')
    return "\n".join(out) + "\n"


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-exposure-")
    path = os.path.join(tmp, "Kalshi-Fills.csv")
    with open(path, "w") as f:
        f.write(csv(FILLS))

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.join(ROOT, "tools")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html")
        page.click("#tabLedger")
        page.set_input_files("#kalshiCsvFile", path)
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('Kalshi CSV')")
        x = page.evaluate("fillExposure(loadLedger())")
        g = {gm["teams"]: gm for gm in x["games"]}
        oc = {t: {o["outcome"]: o for o in gm["outcomes"]} for t, gm in g.items()}

        def near(a, b):
            return abs(a - b) < 1e-6

        bk = g["BUFKC"]
        check("two-way opposing fills: hedge offset = the smaller side (2 contracts)", bk["hedge"] == 2, json.dumps(bk))
        check("cash at risk = gross + fees − hedge", near(bk["cashAtRisk"], 3 * 0.56 + 2 * 0.44 + 0.10 - 2),
              str(bk["cashAtRisk"]))
        check("per team-outcome contracts: KC (home) 3, BUF (away) 2",
              oc["BUFKC"]["HOME"]["contracts"] == 3 and oc["BUFKC"]["AWAY"]["contracts"] == 2)
        cc = g["CARCLE"]
        check("NO on the away team pays on the home outcome only (two-way)",
              oc["CARCLE"]["HOME"]["contracts"] == 4 and oc["CARCLE"]["AWAY"]["contracts"] == 0 and cc["hedge"] == 0,
              json.dumps(cc))
        dp = oc["DALPHI"]["HOME"]
        check("15 contracts = 1.50u at 10/1u: flagged over the 1.25u cap-equivalent",
              near(dp["units"], 1.5) and dp["over"], json.dumps(dp))
        check("3 contracts (0.30u) not flagged", not oc["BUFKC"]["HOME"]["over"])
        ac = g["ARSCHE"]
        check("soccer three-way: home 5 + away 5 is NOT hedged (the tie pays nothing)",
              ac["outs"] == ["HOME", "AWAY", "DRAW"] and ac["hedge"] == 0
              and near(ac["cashAtRisk"], 5 * 0.45 + 5 * 0.30 + 0.11), json.dumps(ac))
        check("undecidable contract role: excluded and counted (never guessed)",
              x["excluded"] == 1 and "KCKC" not in g, json.dumps(x["summary"]))
        s = x["summary"]
        check("summary: 4 games · 6 team-outcomes held · 1 over · 1 hedged game",
              s["games"] == 4 and s["teamOutcomes"] == 6 and s["over"] == 1 and s["hedged"] == 1, json.dumps(s))
        rev = page.evaluate("(()=>{const L=loadLedger(); L.fills=L.fills.slice().reverse(); return fillExposure(L);})()")
        check("load-order invariance: reversed fills give the identical result", rev == x)
        tbl = page.inner_text("#exposureTable") if page.query_selector("#exposureTable") else ""
        check("Ledger tab renders the exposure table (cash at risk, the cap beside)",
              "BUFKC" in tbl and "1.50u > 1.25u" in tbl and "cash at risk" in tbl.lower(), tbl[:300])
        txt = "\n".join(page.evaluate("realizedLines(loadLedger())"))
        check("P&L text carries the headline (diagnostic, cap/sizing unchanged)",
              "B-track fills exposure (diagnostic, cap/sizing unchanged)" in txt and "1 fill(s) excluded" in txt,
              txt[-400:])
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    sys.exit(0 if all(CHECKS) else 1)


if __name__ == "__main__":
    main()
