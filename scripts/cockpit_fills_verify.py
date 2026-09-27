"""
Cockpit Kalshi-fills headless verification (2026-09-27) — two-book accounting.

Seeds a ledger with logged calls, imports a SYNTHETIC Kalshi fills CSV through
the Ledger tab's "Import Kalshi CSV" input, and checks: ticker grammar
(sport families, MVE parlays, non-sport), side resolution (incl. NO and the
tie leg), matching to calls (system_matched carrying engine/tier; a
quarantine-shadow match and a disagreeing side listed as plausible), the
three books' n / staked / fees / pre-fee / net, fees-as-%-of-loss, avg fill,
duplicate-safe re-import, the Copy P&L REALIZED section, and that the ledger
export carries the fills.

The CSV header names are a GUESS at Kalshi's export (the importer maps by
keyword and prints what it mapped) — ARCHITECT-VERIFY against a real header.
Writes nothing to the repo; no DB. Needs Playwright + Chromium.
Run:  python3 scripts/cockpit_fills_verify.py
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


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def call(cid, sport, home, away, pick, engine="model_edge", tier="lean", ct="straight", units=1, kick="2026-09-28T17:00:00"):
    return {"id": cid, "log_date": "2026-09-27", "sport": sport, "game": f"{away} @ {home}", "home": home,
            "away": away, "kickoff": kick, "three_way": sport == "SOCCER", "status": "open",
            "quarantine": ct == "quarantine_shadow", "pick": pick, "tier": tier, "engine": engine,
            "call_type": ct, "units": units, "model_p": 0.6, "market_p": 0.55, "venue_hint": "books", "rules": []}


LEDGER = {"meta": {"policy_version": "v1.1"}, "calls": [
    call("c1", "NFL", "Kansas City Chiefs", "Buffalo Bills", "HOME"),
    call("c2", "NCAA", "Alabama", "Auburn", "HOME", engine="venue_edge", tier="shadow", units=0.25,
         kick="2026-09-27T19:30:00"),
    call("c3", "NFL", "Cleveland Browns", "Carolina Panthers", "HOME", ct="quarantine_shadow", units=0),
]}
HDR = ("market_ticker,side,quantity_fp,entry_price_dollars,exit_price_dollars,open_fees_dollars,"
       "close_fees_dollars,realized_pnl_with_fees_dollars,realized_pnl_without_fees_dollars,"
       "open_ts,close_ts,market_title")
# ticker, side, qty, entry, exit, open fee, close fee, net, pre, title
FILLS = [
    ("KXNFLGAME-26SEP28BUFKC-KC", "yes", 10, 0.55, 1.00, 0.18, 0.00, 4.32, 4.50, "Buffalo vs Kansas City Winner?"),   # matched model_edge
    ("KXNCAAFGAME-26SEP27AUBALA-ALA", "yes", 20, 0.49, 0.00, 0.35, 0.00, -10.15, -9.80, "Auburn vs Alabama Winner?"),  # matched venue_edge
    ("KXNFLGAME-26SEP28CARCLE-CLE", "yes", 10, 0.50, 0.00, 0.18, 0.00, -5.18, -5.00, "Carolina vs Cleveland Winner?"),  # shadow -> plausible
    ("KXNFLGAME-26SEP28BUFKC-BUF", "yes", 5, 0.45, 0.00, 0.09, 0.00, -2.34, -2.25, "Buffalo vs Kansas City Winner?"),   # side disagrees
    ("KXNFLGAME-26SEP28BUFKC-KC", "no", 4, 0.45, 0.00, 0.07, 0.00, -1.87, -1.80, "Buffalo vs Kansas City Winner?"),    # NO on KC = Buffalo
    ("KXMLBGAME-26SEP27NYYBOS-NYY", "yes", 8, 0.60, 1.00, 0.14, 0.00, 3.06, 3.20, "New York Y vs Boston Winner?"),    # no call -> off-book sports
    ("KXEPLGAME-26SEP27ARSCHE-TIE", "yes", 6, 0.25, 0.00, 0.08, 0.00, -1.58, -1.50, "Arsenal vs Chelsea Winner?"),    # tie leg, no call
    ("KXMVESPORTSMULTIGAMEEXTENDED-S2026ABC", "yes", 30, 0.10, 0.00, 0.19, 0.00, -3.19, -3.00, "Multi-game parlay"),  # parlay
    ("KXFEDRATE-26OCT-T4.25", "yes", 50, 0.30, 0.00, 1.05, 0.00, -16.05, -15.00, "Fed rate above 4.25%?"),           # non-sport
]


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-fills-")
    csv_path = os.path.join(tmp, "Kalshi-Fills.csv")
    with open(csv_path, "w") as f:
        f.write(HDR + "\n")
        for t, sd, q, en, ex, of, cf, net, pre, title in FILLS:
            f.write(f'{t},{sd},{q},{en},{ex},{of},{cf},{net},{pre},2026-09-27T12:00:00Z,2026-09-28T23:00:00Z,"{title}"\n')

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
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", LEDGER)
        page.click("#tabLedger")
        page.set_input_files("#kalshiCsvFile", csv_path)
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('Kalshi CSV')")
        note = page.inner_text("#ledgerNote")
        print("   ", note[:220])
        check("9 fills added; all 11 columns mapped by keyword", "9 fills added" in note and "not found" not in note)
        cls = page.evaluate("classifyFills(loadLedger())")
        by = {(f["ticker"], f["side"]): f for f in cls}
        f1 = by[("KXNFLGAME-26SEP28BUFKC-KC", "yes")]
        check("KC yes -> system_matched model_edge (carries engine/tier)",
              f1["book"] == "system_matched" and f1["engine"] == "model_edge" and f1["tier"] == "lean")
        f2 = by[("KXNCAAFGAME-26SEP27AUBALA-ALA", "yes")]
        check("NCAA Alabama -> system_matched venue_edge", f2["book"] == "system_matched" and f2["engine"] == "venue_edge")
        f3 = by[("KXNFLGAME-26SEP28CARCLE-CLE", "yes")]
        check("Cleveland fill vs a quarantine SHADOW -> off-book, plausible",
              f3["book"] == "off_book_sports" and f3.get("plausible") and "SHADOW" in f3["category"])
        f4 = by[("KXNFLGAME-26SEP28BUFKC-BUF", "yes")]
        check("Buffalo yes (call backs KC) -> side disagrees, plausible",
              f4["book"] == "off_book_sports" and "disagrees" in f4["category"])
        f5 = by[("KXNFLGAME-26SEP28BUFKC-KC", "no")]
        check("NO on KC resolves to backing Buffalo", f5["backed"] == "Buffalo" and "disagrees" in f5["category"])
        f6 = by[("KXMLBGAME-26SEP27NYYBOS-NYY", "yes")]
        check("MLB fill with no logged call -> off_book_sports", f6["book"] == "off_book_sports" and not f6.get("plausible"))
        f7 = by[("KXEPLGAME-26SEP27ARSCHE-TIE", "yes")]
        check("EPL tie leg backs the Draw", f7["backed"] == "Draw" and f7["book"] == "off_book_sports")
        check("MVE multigame -> off_book_other (kalshi-native parlay)",
              by[("KXMVESPORTSMULTIGAMEEXTENDED-S2026ABC", "yes")]["book"] == "off_book_other"
              and "parlay" in by[("KXMVESPORTSMULTIGAMEEXTENDED-S2026ABC", "yes")]["category"])
        check("non-sport ticker -> off_book_other", by[("KXFEDRATE-26OCT-T4.25", "yes")]["category"].startswith("non-sport"))

        # independent three-book arithmetic
        books = {"system_matched": [], "off_book_sports": [], "off_book_other": []}
        for f in cls:
            books[f["book"]].append(f)
        tot_net = sum(x[7] for x in FILLS)
        tot_fees = sum(x[5] + x[6] for x in FILLS)
        tot_staked = sum(x[2] * x[3] for x in FILLS)
        agg = page.evaluate("fillAgg(classifyFills(loadLedger()))")
        check("totals: net, fees, staked match the CSV", abs(agg["net"] - tot_net) < 1e-6
              and abs(agg["fees"] - tot_fees) < 1e-6 and abs(agg["staked"] - tot_staked) < 1e-6,
              f"net {agg['net']:.2f} fees {agg['fees']:.2f} staked {agg['staked']:.2f}")
        check("fees-as-%-of-loss = fees / |net|", abs(agg["feePct"] - tot_fees / -tot_net * 100) < 1e-6,
              f"{agg['feePct']:.1f}%")
        check("book sizes 2 / 5 / 2", [len(books[k]) for k in books] == [2, 5, 2])
        html = page.inner_text("#realized")
        check("REALIZED section renders the three books + plausible list",
              all(t in html for t in ("system-matched", "off-book sports", "off-book other", "fees =",
                                      "Unmatched-but-plausible — manual review (3)")))
        block = page.inner_text("#pnlBlock")
        check("Copy P&L block carries the REALIZED section", "REALIZED (Kalshi fills" in block and "fees =" in block)
        page.evaluate("document.getElementById('kalshiCsvFile').value='';"
                      "document.getElementById('ledgerNote').textContent=''")
        page.set_input_files("#kalshiCsvFile", csv_path)
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('duplicates')")
        check("re-import is duplicate-safe", "0 fills added, 9 duplicates skipped" in page.inner_text("#ledgerNote"))
        L = page.evaluate("loadLedger()")
        check("fills live in the ledger (exported with it)", len(L.get("fills", [])) == 9 and len(L["calls"]) == 3)
        check("no page errors", not errors, "; ".join(errors))
        print("\n----- REALIZED lines in the P&L block -----")
        print("\n".join(line for line in block.splitlines() if line.strip() and
                        ("REALIZED" in line or line.startswith(("book", "system", "off-book", "TOTAL", "fees", "unmatched")))))
        browser.close()
    srv.shutdown()
    ok = all(CHECKS)
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed — {'ALL GREEN' if ok else 'FAILURES ABOVE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
