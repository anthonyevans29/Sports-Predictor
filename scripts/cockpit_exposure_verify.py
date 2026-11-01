"""
#211 B-TRACK FILLS EXPOSURE (ARCHITECT lane 3, 2026-10-04): "fills-based
exposure and cash-at-risk per team-outcome, from the imported Kalshi CSV,
beside the units-based cap". DIAGNOSTIC ONLY (cap and sizing unchanged).
A SYNTHETIC Kalshi CSV (the real export's header) imported through the
Ledger tab's file input. Checks:
- opposing two-way fills hedge: cash at risk = gross + fees − the smaller side;
- a NO contract pays on every other outcome (NO on the away = the home side);
- soccer settles three ways: a home + away pair is NOT hedged (the tie);
- a team-outcome above the 1.25u cap-equivalent is flagged, on the unit label a loaded Desk row's order line
  declares (#487, addendum 67 item 3: here "1u = 10 contracts", as a file exported with SP_UNIT_USD unset says);
  with no loaded row ordering a fill's ticker the table shows contracts, labelled, and no unit;
- THE STAMP, NOT A DATE (ARCHITECT 2026-11-01 08:45 ET, addendum 197 item 1): "a fill converts by the unit stamped
  on the Desk row whose order produced it, and by nothing else." Each fill is matched by its ticker to the loaded
  order rows; the latest row whose page time is before the fill's opened time (the closing row over the slate row)
  converts it by its own label; a v1.1 row converts only its own fills; a fill no loaded page carries the order of
  is contracts only, "no loaded page carries this order"; a page after the fill never matches;
- a fill whose contract role the ticker does not decide is excluded, counted;
- load-order invariance: the same fills in reverse order give the same result;
- an MLB doubleheader (two intraday event tickers, same teams and date) is TWO
  settlement events: opposite sides never hedge across them (#274 review);
- a fill whose event identity is ambiguous is excluded and counted apart;
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
    ("KXMLBGAME-26SEP271305NYYBOS-BOS", "yes", 3, 0.50, 0.03),  # doubleheader game 1: BOS
    ("KXMLBGAME-26SEP271905NYYBOS-NYY", "yes", 3, 0.48, 0.03),  # game 2: NYY -> NOT a hedge of game 1
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
        # the basis a desk file exported with SP_UNIT_USD unset declares (desk_policy.unit_size's label), stamped on a
        # loaded row's order line for each fill's ticker, paged before the fills opened (09-27 12:00Z; addendum 197
        # item 1: the row whose order produced the fill converts it). The page holds no unit of its own.
        opened = set(page.evaluate("loadLedger().fills.map(f=>f.opened)"))
        check("fixture: every fill opened at 2026-09-27T07:00:00-05:00 (12:00Z), after the rows' 06:00Z page",
              opened == {"2026-09-27T07:00:00-05:00"}, str(opened))
        TICKERS = json.dumps(sorted({t for t, *_ in FILLS}))
        ROWS = (f"{TICKERS}.map(t=>({{fileDesk:{{order:{{ticker:t,text:'BUY',unit:UNIT}}}},"
                "deskMeta:{policy_version:'v1.2',as_of:'2026-09-27T06:00:00Z'},exportedAt:'2026-09-27T06:00:00Z'}))")
        B10 = ("fillOrderIndex(((UNIT)=>" + ROWS + ")('1u = 10 contracts (SP_UNIT_USD unset)'),null)")
        x = page.evaluate(f"fillExposure(loadLedger(),{B10})")
        g = {gm["teams"]: gm for gm in x["games"] if gm["family"] != "MLB"}
        dh = [gm for gm in x["games"] if gm["family"] == "MLB"]
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
              x["excludedRole"] == 1 and "KCKC" not in g, json.dumps(x["summary"]))
        check("doubleheader: two settlement events (the full event ticker), zero cross-game hedge",
              sorted(gm["key"] for gm in dh) == ["KXMLBGAME-26SEP271305NYYBOS", "KXMLBGAME-26SEP271905NYYBOS"]
              and all(gm["hedge"] == 0 for gm in dh), json.dumps(dh))
        check("doubleheader downside: each game loses its own stake + fees (1.53 and 1.47; the old grouping read a 3-contract hedge, 0 at risk)",
              sorted(round(gm["cashAtRisk"], 4) for gm in dh) == [1.47, 1.53], json.dumps([gm["cashAtRisk"] for gm in dh]))
        s = x["summary"]
        check("summary: 6 games · 8 team-outcomes held · 1 over · 1 hedged game (same event only)",
              s["games"] == 6 and s["teamOutcomes"] == 8 and s["over"] == 1 and s["hedged"] == 1, json.dumps(s))
        amb = page.evaluate("""(()=>{const L=loadLedger();
            const f=L.fills.find(x=>String(x.ticker).startsWith('KXNFLGAME-26SEP28BUFKC-KC'));
            L.fills=[...L.fills,{...f,id:'amb-1',ticker:'KXNFLGAME-26SEP28-BUFKC-KC'}];
            return fillExposure(L,""" + B10 + """);})()""")
        check("ambiguous event identity: excluded and counted apart, the BUFKC event unchanged",
              amb["excludedEvent"] == 1 and next(gm for gm in amb["games"] if gm["teams"] == "BUFKC")["fills"] == 2,
              json.dumps([amb["excludedEvent"], amb["summary"]]))
        rev = page.evaluate(f"(()=>{{const L=loadLedger(); L.fills=L.fills.slice().reverse(); return fillExposure(L,{B10});}})()")
        check("load-order invariance: reversed fills give the identical result", rev == x)
        tbl = page.inner_text("#exposureTable") if page.query_selector("#exposureTable") else ""
        check("Ledger tab renders the exposure table; no desk file loaded: contracts, 'no loaded page carries this "
              "order', no unit (#487, addendum 197)",
              "BUFKC" in tbl and "contracts only: no loaded page carries this order" in tbl
              and "15 ct · if it lands" in tbl
              and "≈" not in tbl and "cash at risk" in tbl.lower(), tbl[:300])
        # loaded desk rows whose order lines name the fills' tickers and declare 1u = 10 contracts: the cap beside
        page.evaluate(f"rows=((UNIT)=>{ROWS})('1u = 10 contracts (SP_UNIT_USD unset)'); renderLedger()")
        tbl = page.inner_text("#exposureTable") if page.query_selector("#exposureTable") else ""
        check("with the rows' 1u = 10 contracts: 15 ct ≈ 1.50u > 1.25u", "1.50u > 1.25u" in tbl, tbl[:300])
        page.evaluate(f"rows=((UNIT)=>{ROWS})('1u = $5'); renderLedger()")
        tbl = page.inner_text("#exposureTable") if page.query_selector("#exposureTable") else ""
        check("with the rows' 1u = $5: 15 ct at 0.60 = 9.00 of entry ≈ 1.80u > 1.25u", "1.80u > 1.25u" in tbl,
              tbl[:300])
        # addendum 197 item 1 (synthetic rows): the closing row over the slate row; a v1.1 row converts only its own
        # fills; a page after the fill and an off-book ticker convert to nothing
        row = ("(t,unit,page,v)=>({fileDesk:{order:{ticker:t,text:'BUY',unit}},deskMeta:{policy_version:v,as_of:page},"
               "exportedAt:page})")
        page.evaluate(f"(()=>{{const r={row}; rows=["
                      "r('KXNFLGAME-26SEP28DALPHI-PHI','1u = $5','2026-09-27T06:00:00Z','v1.2'),"      # slate
                      "r('KXNFLGAME-26SEP28DALPHI-PHI','1u = $6','2026-09-27T11:00:00Z','v1.2'),"      # closing
                      "r('KXNFLGAME-26SEP28BUFKC-KC','1u = $50','2026-09-26T16:00:00Z','v1.1'),"       # a v1.1 row
                      "r('KXMLBGAME-26SEP271305NYYBOS-BOS','1u = $5','2026-09-27T13:00:00Z','v1.2')];"  # after the fill
                      " renderLedger();})()")
        tbl = page.inner_text("#exposureTable") if page.query_selector("#exposureTable") else ""
        check("addendum 197: the closing row (11:00Z, 1u = $6) stands over the slate row (06:00Z, 1u = $5): "
              "PHI 15 ct at 0.60 = 9.00 ≈ 1.50u > 1.25u",
              "1u = $6 (1 fill(s))" in tbl and "1.50u > 1.25u" in tbl and "1u = $5 (" not in tbl, tbl[:600])
        check("addendum 197: a v1.1 row converts its own fill only (KC 3 ct at 0.56 = 1.68 at 1u = $50 ≈ 0.03u); "
              "its BUF fill, no row's order, is contracts only",
              "1u = $50 (1 fill(s)) · contracts only: no loaded page carries this order (1 fill(s))" in tbl
              and "KC (home): 3 ct ≈ 0.03u" in tbl and "BUF (away): 2 ct · if it lands" in tbl, tbl[:600])
        check("addendum 197: a row paged after the fill opened never converts it (BOS: contracts only, labelled)",
              "contracts only: no loaded page carries this order before the fill opened (1 fill(s))" in tbl
              and "BOS (home): 3 ct · if it lands" in tbl, tbl[-600:])
        check("addendum 197: no date reaches a fill (no ET-day label anywhere)",
              "ET day" not in tbl and "no unit basis for" not in tbl, tbl[:300])
        x = page.evaluate("fillExposure(loadLedger(),fillOrderIndex(rows,fileParlays)).summary")
        check("addendum 197: summary counts 2 fills matched (labels 1u = $50, 1u = $6) and 6 in contracts only by why "
              "(unmatched 5, after the fill 1)",
              x["matchedFills"] == 2 and x["labels"] == ["1u = $50", "1u = $6"] and x["contractsOnlyFills"] == 6
              and x["contractsOnlyByKind"] == {"unmatched": 5, "after_fill": 1}, json.dumps(x))
        txt = "\n".join(page.evaluate("realizedLines(loadLedger())"))
        check("addendum 197: the P&L text's headline names the units by the Desk row whose order produced each fill",
              "units by the Desk row whose order produced each fill (addendum 197): 2 fill(s) matched (1u = $50; "
              "1u = $6), 6 fill(s) contracts only (no loaded page carries this order before the fill opened: 1; "
              "no loaded page carries this order: 5)" in txt, txt[-600:])
        page.evaluate("rows=[]; renderLedger()")
        txt = "\n".join(page.evaluate("realizedLines(loadLedger())"))
        check("P&L text carries the headline (diagnostic, cap/sizing unchanged)",
              "B-track fills exposure (diagnostic, cap/sizing unchanged)" in txt
              and "1 fill(s) excluded (contract role not decided by the ticker)" in txt,
              txt[-400:])
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    sys.exit(0 if all(CHECKS) else 1)


if __name__ == "__main__":
    main()
