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

2026-09-30 (architect): side resolution from the ticker suffix first
(KX{FAM}GAME-{date}{AWAY}{HOME}-{SIDE}; TIE = draw) and Kalshi's real title
grammar "{Team} wins — {Team}" second; a LEGACY stored fill (the pre-fix
"title not 'A vs B'" shape) re-classifies without re-import; the fourth book
"system-pick, unlogged" from stored predictions (a results export) when no
ledger call exists; and the Open calls "—" instead of a default "limit 0.59".

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


# A fill AS THE PRE-FIX IMPORTER STORED IT (the architect's 33, 2026-09-30):
# Kalshi's real title grammar "{Team} wins — {Team}", backed null, note
# "title not 'A vs B'". The fix re-derives the side at classification.
LEGACY = {"id": "legacy-1", "ticker": "KXNFLGAME-26SEP28BUFKC-KC", "side": "yes", "qty": 2, "entry": 0.57,
          "exit": 1.0, "staked": 1.14, "fees": 0.04, "pnl_pre": 0.86, "pnl_net": 0.82,
          "opened": "2026-09-27T07:00:00-05:00", "closed": "2026-09-28T18:00:00-05:00",
          "title": "Kansas City wins — Buffalo", "kind": "sport", "family": "NFL", "sports": ["NFL"],
          "date": "2026-09-28", "teams": "BUFKC", "sideCode": "KC", "backed": None, "teams_title": None,
          "resolve_note": "title not 'A vs B'"}
LEDGER = {"meta": {"policy_version": "v1.1"}, "fills": [LEGACY], "calls": [
    call("c1", "NFL", "Kansas City Chiefs", "Buffalo Bills", "HOME"),
    call("c2", "NCAA", "Alabama", "Auburn", "HOME", engine="venue_edge", tier="shadow", units=0.25,
         kick="2026-09-27T19:30:00"),
    call("c3", "NFL", "Cleveland Browns", "Carolina Panthers", "HOME", ct="quarantine_shadow", units=0),
    dict(call("c4", "NFL", "Chicago Bears", "Green Bay Packers", "HOME", kick="2026-10-04T17:00:00"),
         log_date="2026-09-30"),                                                   # Week 5: no ladder yet
    dict(call("c5", "NFL", "Detroit Lions", "Minnesota Vikings", "AWAY", kick="2026-10-04T17:00:00"),
         log_date="2026-09-30", kalshi_join_bid=0.47),                             # has a join bid
]}
# A results export (the pre-ledger era's stored predictions): the model picked
# the Yankees (away) in NYY @ BOS on 09-27.
RESULTS = {"sport": "mlb", "results": [
    {"match_id": 9, "date": "2026-09-27T17:05:00", "home_team": "Boston Red Sox", "away_team": "New York Yankees",
     "predicted": {"top_pick": "away_win", "top_pick_prob": 0.56},
     "actual": {"home_score": 2, "away_score": 5, "result": "A"}}]}
# The REAL Kalshi export header, verbatim and in order (architect-confirmed
# 2026-09-27 from the YTD export), including the columns the importer ignores.
HDR = ("subtrader_id,type,quantity_fp,market_ticker,side,entry_price_dollars,exit_price_dollars,"
       "open_fees_dollars,close_fees_dollars,realized_pnl_without_fees_dollars,"
       "realized_pnl_with_fees_dollars,close_timestamp,open_timestamp,product,period_start,market_title")
# ticker, side, qty, entry, exit, open fee, close fee, net, pre, title
FILLS = [
    ("KXNFLGAME-26SEP28BUFKC-KC", "yes", 10, 0.55, 1.00, 0.18, 0.00, 4.32, 4.50, "Buffalo vs Kansas City Winner?"),   # matched model_edge
    ("KXNCAAFGAME-26SEP27AUBALA-ALA", "yes", 20, 0.49, 0.00, 0.35, 0.00, -10.15, -9.80, "Auburn vs Alabama Winner?"),  # matched venue_edge
    ("KXNFLGAME-26SEP28CARCLE-CLE", "yes", 10, 0.50, 0.00, 0.18, 0.00, -5.18, -5.00, "Carolina vs Cleveland Winner?"),  # shadow -> plausible
    ("KXNFLGAME-26SEP28BUFKC-BUF", "yes", 5, 0.45, 0.00, 0.09, 0.00, -2.34, -2.25, "Buffalo vs Kansas City Winner?"),   # side disagrees
    ("KXNFLGAME-26SEP28BUFKC-KC", "no", 4, 0.45, 0.00, 0.07, 0.00, -1.87, -1.80, "Buffalo vs Kansas City Winner?"),    # NO on KC = Buffalo
    ("KXMLBGAME-26SEP27NYYBOS-NYY", "yes", 8, 0.60, 1.00, 0.14, 0.00, 3.06, 3.20, "New York Y vs Boston Winner?"),    # no call -> off-book sports
    ("KXEPLGAME-26SEP27ARSCHE-TIE", "yes", 6, 0.25, 0.00, 0.08, 0.00, -1.58, -1.50, "Arsenal vs Chelsea Winner?"),    # tie leg, no call
    ("KXMVESPORTSMULTIGAMEEXTENDED-S2026ABC", "yes", 30, 0.10, 0.00, 0.19, 0.00, -3.19, -3.00, "Multi-game parlay"),  # parlay, legs not in title
    # MVE combos classified by LEG CONTENT (lane C, 2026-09-29)
    ("KXMVECROSSCATEGORY-S2026DEF", "yes", 20, 0.08, 0.00, 0.10, 0.00, -1.70, -1.60,
     "yes Buffalo,yes Kansas City,yes Over 44.5 points scored"),                                                    # all sports legs
    ("KXMVECROSSCATEGORY-S2026GHI", "yes", 10, 0.12, 0.00, 0.08, 0.00, -1.28, -1.20,
     "yes Buffalo,yes Fed rate above 4.25%"),                                                                        # mixed legs
    ("KXMVECROSSCATEGORY-S2026JKL", "yes", 10, 0.15, 0.00, 0.08, 0.00, -1.58, -1.50,
     "yes CPI above 3%,yes Fed rate above 4.25%"),                                                                   # non-sport legs
    ("KXFEDRATE-26OCT-T4.25", "yes", 50, 0.30, 0.00, 1.05, 0.00, -16.05, -15.00, "Fed rate above 4.25%?"),           # non-sport
    # Kalshi's REAL title grammar (2026-09-30): "{Team} wins — {Team}"; the ticker suffix decides the side
    ("KXNFLGAME-26SEP28BUFKC-KC", "yes", 3, 0.56, 1.00, 0.06, 0.00, 1.26, 1.32, "Kansas City wins — Buffalo"),    # matched c1
    ("KXNFLGAME-26SEP28CARCLE-CAR", "yes", 2, 0.50, 0.00, 0.04, 0.00, -1.04, -1.00, "Carolina wins — Cleveland"), # vs c3 (HOME): disagrees
    ("KXNFLGAME-26SEP28BUFKC-BUF", "no", 2, 0.44, 1.00, 0.04, 0.00, 1.08, 1.12, "Buffalo wins — Kansas City"),    # NO on BUF = KC: matched
    ("KXNHLGAME-26OCT01TORMTL-MTL", "yes", 4, 0.52, 0.00, 0.07, 0.00, -2.15, -2.08, "Montreal wins — Toronto"),   # no call, no prediction
    ("KXMLBGAME-26SEP27NYYBOS-BOS", "yes", 3, 0.45, 0.00, 0.05, 0.00, -1.40, -1.35, "Boston wins — New York Y"),  # stored pick disagrees
    ("KXNFLGAME-26SEP28BUFKC-KC", "yes", 1, 0.58, 1.00, 0.02, 0.00, 0.40, 0.42, ""),                             # no title: ticker + codes
]


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-fills-")
    csv_path = os.path.join(tmp, "Kalshi-Fills.csv")
    with open(csv_path, "w") as f:
        f.write(HDR + "\n")
        for t, sd, q, en, ex, of, cf, net, pre, title in FILLS:
            # values as seen in the real export: 8-decimal dollar strings, ISO -05:00 timestamps
            f.write(f'sub-1,trade,{q:.2f},{t},{sd},{en:.8f},{ex:.8f},{of:.8f},{cf:.8f},{pre:.8f},{net:.8f},'
                    f'2026-09-28T18:00:00-05:00,2026-09-27T07:00:00-05:00,predictions,2026-09-01,"{title}"\n')

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
        mapped = page.evaluate("mapHeaders(" + json.dumps(HDR.split(",")) + ")")
        want = {"ticker": "market_ticker", "side": "side", "qty": "quantity_fp", "entry": "entry_price_dollars",
                "exit": "exit_price_dollars", "openFee": "open_fees_dollars", "closeFee": "close_fees_dollars",
                "pnlPre": "realized_pnl_without_fees_dollars", "pnlNet": "realized_pnl_with_fees_dollars",
                "openTs": "open_timestamp", "closeTs": "close_timestamp", "title": "market_title"}
        got = {k: (HDR.split(",")[v] if v is not None else None) for k, v in mapped.items()}
        check("REAL export header: every field maps to exactly the right column", got == want,
              "; ".join(f"{k}->{got[k]}" for k in want if got[k] != want[k]))
        check("18 fills added; nothing reported missing", "18 fills added" in note and "not found" not in note)
        cls = page.evaluate("classifyFills(loadLedger())")
        by = {}
        for f in cls:                                   # first CSV occurrence per (ticker, side)
            if f["id"] != "legacy-1":
                by.setdefault((f["ticker"], f["side"]), f)
        tt = {(f["ticker"], f["side"], f["title"]): f for f in cls}
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
        # --- side resolution (architect 2026-09-30): ticker suffix first, title second ---
        lg = next(f for f in cls if f["id"] == "legacy-1")
        check("LEGACY stored fill ('title not A vs B') re-classifies without re-import -> system_matched c1",
              lg["book"] == "system_matched" and lg.get("call_id") == "c1" and lg["backed_role"] == "HOME"
              and lg["resolved_via"] == "ticker", f"{lg['book']} {lg.get('category')}")
        n1 = tt[("KXNFLGAME-26SEP28BUFKC-KC", "yes", "Kansas City wins — Buffalo")]
        check("real grammar 'Kansas City wins — Buffalo': suffix KC = HOME, named Kansas City -> matched",
              n1["book"] == "system_matched" and n1["backed"] == "Kansas City" and n1["backed_role"] == "HOME")
        n2 = by[("KXNFLGAME-26SEP28CARCLE-CAR", "yes")]
        check("suffix CAR = the AWAY code -> backs Carolina; the (shadow) call backs Cleveland -> disagrees",
              n2["backed_role"] == "AWAY" and n2["book"] == "off_book_sports" and "disagrees" in n2["category"])
        n3 = by[("KXNFLGAME-26SEP28BUFKC-BUF", "no")]
        check("NO on the away code BUF -> backs HOME (Kansas City) -> matched",
              n3["backed_role"] == "HOME" and n3["backed"] == "Kansas City" and n3["book"] == "system_matched")
        n4 = tt[("KXNFLGAME-26SEP28BUFKC-KC", "yes", "")]
        check("no title at all: the ticker role + {AWAY}{HOME} codes still match the call",
              n4["book"] == "system_matched" and n4["backed"] is None and n4["backed_role"] == "HOME")
        n5 = by[("KXNHLGAME-26OCT01TORMTL-MTL", "yes")]
        check("no call, no stored prediction -> off_book_sports 'no logged call'",
              n5["book"] == "off_book_sports" and n5["category"] == "no logged call for this game")
        check("nothing is 'side not resolvable' any more",
              not any("side not resolvable" in f.get("category", "") for f in cls))
        m0 = by[("KXMVESPORTSMULTIGAMEEXTENDED-S2026ABC", "yes")]
        check("MVE SPORTS family, legs not in the title -> off-book sports parlay (ticker family)",
              m0["book"] == "off_book_sports" and "legs not in title, ticker family SPORTS" in m0["category"], m0["category"])
        m1 = by[("KXMVECROSSCATEGORY-S2026DEF", "yes")]
        check("MVE combo, every leg sports (team names + 'points') -> off-book sports parlay, 3 legs",
              m1["book"] == "off_book_sports" and m1["category"] == "off-book sports parlay (MVE combo, 3 legs)", m1["category"])
        m2 = by[("KXMVECROSSCATEGORY-S2026GHI", "yes")]
        check("MVE combo, mixed legs -> off_book_other, labelled 1/2 sports",
              m2["book"] == "off_book_other" and m2["category"] == "MVE combo, mixed legs (1/2 sports)", m2["category"])
        m3 = by[("KXMVECROSSCATEGORY-S2026JKL", "yes")]
        check("MVE combo, non-sport legs -> off_book_other",
              m3["book"] == "off_book_other" and m3["category"] == "MVE combo, non-sport legs (2)", m3["category"])
        check("no MVE combo is ever system_matched",
              all(by[(t, "yes")]["book"] != "system_matched" for t in
                  ("KXMVESPORTSMULTIGAMEEXTENDED-S2026ABC", "KXMVECROSSCATEGORY-S2026DEF")))
        check("non-sport ticker -> off_book_other", by[("KXFEDRATE-26OCT-T4.25", "yes")]["category"].startswith("non-sport"))

        # independent three-book arithmetic
        books = {"system_matched": [], "system_pick_unlogged": [], "off_book_sports": [], "off_book_other": []}
        for f in cls:
            books[f["book"]].append(f)
        tot_net = sum(x[7] for x in FILLS) + LEGACY["pnl_net"]
        tot_fees = sum(x[5] + x[6] for x in FILLS) + LEGACY["fees"]
        tot_staked = sum(x[2] * x[3] for x in FILLS) + LEGACY["staked"]
        agg = page.evaluate("fillAgg(classifyFills(loadLedger()))")
        check("totals: net, fees, staked match the CSV", abs(agg["net"] - tot_net) < 1e-6
              and abs(agg["fees"] - tot_fees) < 1e-6 and abs(agg["staked"] - tot_staked) < 1e-6,
              f"net {agg['net']:.2f} fees {agg['fees']:.2f} staked {agg['staked']:.2f}")
        check("fees-as-%-of-loss = fees / |net|", abs(agg["feePct"] - tot_fees / -tot_net * 100) < 1e-6,
              f"{agg['feePct']:.1f}%")
        check("book sizes 6 / 0 / 10 / 3 before any stored predictions", [len(books[k]) for k in books] == [6, 0, 10, 3],
              str([len(books[k]) for k in books]))
        html = page.inner_text("#realized")
        check("REALIZED section renders the three books + plausible list",
              all(t in html for t in ("system-matched", "off-book sports", "off-book other", "fees =",
                                      "Unmatched-but-plausible — manual review (4)")))
        t30 = page.evaluate("(()=>{const fs=classifyFills(loadLedger());"
                            "return [trailing30(fs,Date.parse('2026-10-05T00:00:00Z')).length,"
                            "trailing30(fs,Date.parse('2026-11-30T00:00:00Z')).length]})()")
        check("trailing-30-day window by close time (19 in window, 0 two months later)", t30 == [19, 0], str(t30))
        block = page.inner_text("#pnlBlock")
        check("Copy P&L block carries the REALIZED section + trailing-30d line",
              "REALIZED (Kalshi fills" in block and "fees =" in block and "trailing 30d:" in block)
        page.evaluate("document.getElementById('kalshiCsvFile').value='';"
                      "document.getElementById('ledgerNote').textContent=''")
        page.set_input_files("#kalshiCsvFile", csv_path)
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('duplicates')")
        check("re-import is duplicate-safe", "0 fills added, 18 duplicates skipped" in page.inner_text("#ledgerNote"))
        L = page.evaluate("loadLedger()")
        check("fills live in the ledger (exported with it)", len(L.get("fills", [])) == 19 and len(L["calls"]) == 5)
        # --- (2) the pre-ledger era: STORED PREDICTIONS from a results export ---
        res_path = os.path.join(tmp, "mlb_results.json")
        with open(res_path, "w") as f:
            json.dump(RESULTS, f)
        page.set_input_files("#resultsFile", res_path)
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('stored predictions')")
        check("results intake harvests the stored predictions", "stored predictions: 1 read, 1 new" in
              page.inner_text("#ledgerNote"), page.inner_text("#ledgerNote")[:200])
        cls2 = page.evaluate("classifyFills(loadLedger())")
        b2 = {}
        for f in cls2:
            if f["id"] != "legacy-1":
                b2.setdefault((f["ticker"], f["side"]), f)
        y = b2[("KXMLBGAME-26SEP27NYYBOS-NYY", "yes")]
        check("NYY fill + the stored pick (Yankees) -> the FOURTH book 'system-pick, unlogged'",
              y["book"] == "system_pick_unlogged" and y["category"].startswith("system-pick, unlogged"), y["category"])
        bo = b2[("KXMLBGAME-26SEP27NYYBOS-BOS", "yes")]
        check("BOS fill vs the stored pick -> off-book, 'stored prediction exists but the side disagrees', plausible",
              bo["book"] == "off_book_sports" and bo.get("plausible") and "stored prediction" in bo["category"])
        check("never system_matched without a logged call", y.get("call_id") is None)
        sizes = [sum(1 for f in cls2 if f["book"] == k) for k in books]
        check("book sizes 6 / 1 / 9 / 3 after the harvest", sizes == [6, 1, 9, 3], str(sizes))
        check("the REALIZED table shows the fourth book", "system-pick, unlogged" in page.inner_text("#realized"))
        check("stored picks travel in the ledger (Export carries them)",
              len(page.evaluate("loadLedger()").get("system_picks", [])) == 1)
        # --- (3) Open calls: no default order on a row without a Kalshi ladder ---
        sel = page.evaluate("[...document.querySelectorAll('select.fillType')].map(x=>[x.dataset.id,x.value])")
        ph = page.evaluate("Object.fromEntries([...document.querySelectorAll('input.fillPx')].map(x=>[x.dataset.id,x.placeholder]))")
        check("Week 5 row without a ladder: order type '—' and price '—' (no 'limit 0.59' default)",
              dict(sel).get("c4") == "" and ph.get("c4") == "—", f"{sel} {ph}")
        check("a row with a stored join bid shows it as the price hint", ph.get("c5") == "0.47", str(ph))
        check("recording without choosing an order type is refused",
              page.evaluate("recordFill('c4','','0.50')") == "Order type must be limit or market.")
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
