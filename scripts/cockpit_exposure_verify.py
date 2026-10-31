"""
#211 B-TRACK FILLS EXPOSURE (ARCHITECT lane 3, 2026-10-04): "fills-based
exposure and cash-at-risk per team-outcome, from the imported Kalshi CSV,
beside the units-based cap". DIAGNOSTIC ONLY (cap and sizing unchanged).
A SYNTHETIC Kalshi CSV (the real export's header) imported through the
Ledger tab's file input. Checks:
- opposing two-way fills hedge: cash at risk = gross + fees − the smaller side;
- a NO contract pays on every other outcome (NO on the away = the home side);
- soccer settles three ways: a home + away pair is NOT hedged (the tie);
- a team-outcome above the 1.25u cap-equivalent is flagged, on the unit basis a loaded file's order lines
  declare (#487, addendum 67 item 3: here "1u = 10 contracts", as a file exported with SP_UNIT_USD unset says);
  with no basis in the loaded files the table shows contracts, labelled, and no unit;
- Desk policy v1.2 (#740, addendum 182 item 6): each game's fills on the unit of the loaded file of the game's own
  ET day (desk_meta.unit), never another day's; an unread day is contracts only, "unit unread — no order"; a day no
  loaded file names is contracts only, labelled; two files of one day that differ are contracts only, both named;
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
        # the basis a desk file exported with SP_UNIT_USD unset declares (desk_policy.unit_size's label), read by the
        # page's own reader (#487, addendum 67 item 3): the page holds no unit of its own
        B10 = "fillDayBases([{fileDesk:{order:{unit:'1u = 10 contracts (SP_UNIT_USD unset)'}}}],null)"
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
        check("Ledger tab renders the exposure table; no desk file loaded: contracts, labelled, no unit (#487)",
              "BUFKC" in tbl and "contracts (no unit basis for 2026-09-28 in the loaded files)" in tbl.lower()
              and "15 ct · if it lands" in tbl
              and "≈" not in tbl and "cash at risk" in tbl.lower(), tbl[:300])
        # a loaded desk file whose order lines declare 1u = 10 contracts: the cap beside, on the file's basis
        page.evaluate("rows=[{fileDesk:{order:{text:'BUY', unit:'1u = 10 contracts (SP_UNIT_USD unset)'}}}]; renderLedger()")
        tbl = page.inner_text("#exposureTable") if page.query_selector("#exposureTable") else ""
        check("with a desk file's 1u = 10 contracts: 15 ct ≈ 1.50u > 1.25u", "1.50u > 1.25u" in tbl, tbl[:300])
        page.evaluate("rows=[{fileDesk:{order:{text:'BUY', unit:'1u = $5'}}}]; renderLedger()")
        tbl = page.inner_text("#exposureTable") if page.query_selector("#exposureTable") else ""
        check("with a desk file's 1u = $5: 15 ct at 0.60 = $9.00 of entry ≈ 1.80u > 1.25u", "1.80u > 1.25u" in tbl,
              tbl[:300])
        # v1.2 (#740): the unit of the file of each game's own ET day (synthetic desk_meta.unit blocks)
        meta = ("(d,label,state)=>({policy_version:'v1.2',unit:{state,et_date:d,label,why:null}})")
        page.evaluate(f"(()=>{{const m={meta}; rows=[{{fileDesk:{{order:{{text:'BUY',unit:'1u = $5'}}}},"
                      "deskMeta:m('2026-09-28','1u = $5','read')},{fileDesk:{order:{text:null,unit:'unit unread'}},"
                      "deskMeta:m('2026-09-27','unit unread','unread')},{fileDesk:{order:{text:'BUY',unit:'1u = $50'}}}];"
                      " renderLedger();})()")
        tbl = page.inner_text("#exposureTable") if page.query_selector("#exposureTable") else ""
        check("v1.2: a 09-28 file's 1u = $5 converts the 09-28 games (15 ct at 0.60 ≈ 1.80u > 1.25u)",
              "2026-09-28: 1u = $5" in tbl and "1.80u > 1.25u" in tbl, tbl[:400])
        check("v1.2: the unread 09-27 day's games are contracts only, 'unit unread — no order', no unit",
              tbl.count("2026-09-27: unit unread — no order (contracts only)") == 2
              and "BOS (home): 3 ct · if it lands" in tbl and "NYY (away): 3 ct · if it lands" in tbl, tbl[-400:])
        check("v1.2: the day no v1.2 file names takes the v1.1 file's order-line unit (10-04 at 1u = $50)",
              "2026-10-04: 1u = $50" in tbl, tbl[:400])
        page.evaluate(f"(()=>{{const m={meta}; rows=[{{deskMeta:m('2026-09-28','1u = $5','read')}},"
                      "{deskMeta:m('2026-09-28','1u = $6','read')}]; renderLedger();})()")
        tbl = page.inner_text("#exposureTable") if page.query_selector("#exposureTable") else ""
        check("v1.2: two files of 09-28 that differ: contracts only, both named; 10-04 has no file: contracts only",
              "the loaded files of 2026-09-28 differ on the unit: 1u = $5 vs 1u = $6" in tbl
              and "contracts (no unit basis for 2026-10-04 in the loaded files)" in tbl and "≈" not in tbl, tbl[:400])
        txt = "\n".join(page.evaluate("realizedLines(loadLedger())"))
        check("v1.2: the P&L text's headline names the units by the file's ET day",
              "units by the file's ET day: 2026-09-27 contracts (no unit basis for 2026-09-27" in txt
              and "the 1.25u cap-equivalent not read (no unit)" in txt, txt[-500:])
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
