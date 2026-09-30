"""
Cockpit MAKER / TAKER split headless verification (#93 ruling, architect
2026-09-30). The export rows are built by the REAL `venue.kalshi_exec`, so the
Python fee math and the Cockpit read are checked together. Checks, over
SYNTHETIC files:
- ruling (1): the export carries exec_cost_taker + exec_cost_maker (NFL taker
  M=1 / maker M=0.25; MLB pre-live M=0.5 for both); a 1c spread has no maker
  price; kalshi_exec_cost stays as the taker alias;
- ruling (2): the Desk's exec edge and "fee-clears?" use the MAKER cost by
  default, with the taker cost shown as the fallback; the taker cost is the
  basis when no maker price exists; calls and units are unchanged;
- the ledger records both costs at capture, claim and execution;
- ruling (3): imported fills are classified maker / taker from the CSV's fee
  vs the formula (MLB at the live rate = "taker_live", a doctrine alarm; tiny
  orders "ambiguous"; a mismatch "unknown"); a pre-split import gains the
  class when the same CSV is imported again;
- ruling (4): the policy card states "MLB is never executed live".

    python3 scripts/cockpit_maker_taker_verify.py

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
sys.path.insert(0, ROOT)
from src.walters.venue import kalshi_exec  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)
D1 = (NOW + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def nfl(home, away, p_home, fair_home, bid=None, ask=None):
    r = {"home_team": home, "away_team": away, "utc_date": D1, "competition": "NFL",
         "prediction": {"home_win_prob": p_home, "away_win_prob": round(1 - p_home, 4), "tier": "lean"},
         "market": {"bookmaker_count": 7, "fair_prob": {"HOME": fair_home, "AWAY": round(1 - fair_home, 4)}},
         "market_divergence_pp": round((p_home - fair_home) * 100, 1), "quarantine": False,
         "input_quality": {"book_odds": 7, "injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}}
    r.update(kalshi_exec(bid, ask, "NFL"))
    return r


def main():
    print("EXPORT (venue.kalshi_exec, ruling 1)")
    sea = kalshi_exec(0.55, 0.58, "NFL")
    check("NFL 0.55/0.58: taker 0.60 (0.58 + 2c at M=1), maker 0.57 (join 0.56 + 1c at M=0.25), alias = taker",
          (sea["exec_cost_taker"], sea["exec_cost_maker"], sea["kalshi_exec_cost"]) == (0.60, 0.57, 0.60), json.dumps(sea))
    mlb = kalshi_exec(0.55, 0.57, "MLB")
    check("MLB pre-live 0.55/0.57: M=0.5 both; taker 0.58, maker 0.57",
          (mlb["exec_cost_taker"], mlb["exec_cost_maker"], mlb["fee_m_taker"], mlb["fee_m_maker"]) == (0.58, 0.57, 0.5, 0.5),
          json.dumps(mlb))
    one = kalshi_exec(0.57, 0.58, "NFL")
    check("1c spread: no maker price (joining = taking)", one["exec_cost_maker"] is None and one["exec_cost_taker"] == 0.60)

    D = {"sport": "nfl", "rehearsal": False, "predictions": [
        nfl("Seattle Seahawks", "Los Angeles Rams", 0.62, 0.56, bid=0.55, ask=0.58),   # maker +5.0 clears, taker +2.0
        nfl("Buffalo Bills", "Miami Dolphins", 0.66, 0.60, bid=0.59, ask=0.60),        # 1c spread: taker basis
        nfl("Dallas Cowboys", "Philadelphia Eagles", 0.36, 0.42, bid=0.40, ask=0.43),  # AWAY pick
    ]}
    M = {"sport": "mlb", "predictions": [
        {"home_team": "New York Yankees", "away_team": "Boston Red Sox", "utc_date": D1, "competition": "MLB",
         "prediction": {"home_win_prob": 0.62, "draw_prob": None, "away_win_prob": 0.38},
         "market": {"bookmaker_count": 6, "selections": {"HOME": {"fair_prob": 0.56}, "AWAY": {"fair_prob": 0.44}}},
         **mlb}]}
    NOQ = json.loads(json.dumps(D))
    for r in NOQ["predictions"]:
        for k in ("kalshi_bid", "kalshi_ask", "exec_cost_taker", "exec_cost_maker", "kalshi_exec_cost"):
            r[k] = None

    # ticker, side, qty, entry, exit, open fee, close fee, pre, net, title — all settled (close fee 0)
    FILLS = [
        ("KXNFLGAME-26OCT04LARSEA-SEA", "yes", 10, 0.60, 1.00, 0.17, 0.00, 4.00, 3.83, "Los Angeles R vs Seattle Winner?"),  # taker
        ("KXNFLGAME-26OCT04MIABUF-BUF", "yes", 10, 0.60, 1.00, 0.02, 0.00, 4.00, 3.98, "Miami vs Buffalo Winner?"),         # maker
        ("KXMLBGAME-26OCT04BOSNYY-NYY", "yes", 10, 0.60, 1.00, 0.09, 0.00, 4.00, 3.91, "Boston vs New York Y Winner?"),     # MLB pre-live taker
        ("KXMLBGAME-26OCT03BOSNYY-NYY", "yes", 10, 0.60, 0.00, 0.17, 0.00, -6.00, -6.17, "Boston vs New York Y Winner?"),   # MLB live rate
        ("KXNFLGAME-26OCT04PHIDAL-DAL", "yes", 1, 0.95, 1.00, 0.01, 0.00, 0.05, 0.04, "Philadelphia vs Dallas Winner?"),     # tiny: ambiguous
        ("KXNFLGAME-26OCT05DETGB-GB", "yes", 10, 0.60, 1.00, 0.50, 0.00, 4.00, 3.50, "Detroit vs Green Bay Winner?"),       # no formula
        ("KXMVESPORTS-26OCT04-ABC", "yes", 10, 0.20, 0.00, 0.12, 0.00, -2.00, -2.12, "yes Seattle,yes Buffalo"),           # combo taker
    ]
    HDR = ("subtrader_id,type,quantity_fp,market_ticker,side,entry_price_dollars,exit_price_dollars,"
           "open_fees_dollars,close_fees_dollars,realized_pnl_without_fees_dollars,"
           "realized_pnl_with_fees_dollars,close_timestamp,open_timestamp,product,period_start,market_title")

    tmp = tempfile.mkdtemp(prefix="cockpit-mt-")
    for n, d in {"nfl.json": D, "noquotes.json": NOQ, "mlb.json": M}.items():
        with open(os.path.join(tmp, n), "w") as f:
            json.dump(d, f)
    csv_path = os.path.join(tmp, "Kalshi-Fills.csv")
    with open(csv_path, "w") as f:
        f.write(HDR + "\n")
        for t, sd, q, en, ex, of, cf, pre, net, title in FILLS:
            f.write(f'sub-1,trade,{q:.2f},{t},{sd},{en:.8f},{ex:.8f},{of:.8f},{cf:.8f},{pre:.8f},{net:.8f},'
                    f'2026-10-04T18:00:00-05:00,2026-10-04T07:00:00-05:00,predictions,2026-10-01,"{title}"\n')

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
            page.set_input_files("#predFile", os.path.join(tmp, name))
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
            page.click("#tabDesk")

        def table():
            return {r[0]: r for r in page.evaluate("""Array.from(document.querySelectorAll('#slate tbody tr'))
                .filter(tr=>!tr.classList.contains('vshadow'))
                .map(tr=>Array.from(tr.children).map(td=>td.textContent))""")}

        print("DESK (ruling 2: maker by default, taker as the fallback)")
        load("noquotes.json")
        base = {k: (r[5], r[6]) for k, r in table().items()}
        load("nfl.json")
        rows = table()
        s = next(v for k, v in rows.items() if "Seattle" in k)
        check("maker basis: 'exec +5.0pp @ 0.57 maker (join 0.56) · fee-clears? · taker 0.60 (+2.0pp)'",
              s[4] == "+6.0pp" + "exec +5.0pp @ 0.57 maker (join 0.56) · fee-clears? · taker 0.60 (+2.0pp)", s[4])
        b = next(v for k, v in rows.items() if "Buffalo" in k)
        check("1c spread: taker is the basis, labelled 'joining = taking'",
              "exec +4.0pp @ 0.62 taker (spread 1¢ — joining = taking) · fee-clears?" in b[4], b[4])
        d = next(v for k, v in rows.items() if "Dallas" in k)
        check("AWAY pick: 'exec —', never a derived price", "exec — (quotes are the home contract's)" in d[4], d[4])
        check("informational only: calls and units identical with and without quotes",
              {k: (r[5], r[6]) for k, r in rows.items()} == base, str(base))
        pol = page.inner_text("#deskView")
        check("policy card: maker default + the ruled multipliers + 'MLB is never executed live'",
              "MAKER cost" in pol and "maker M=0.25, MLB pre-live M=0.5" in pol and "MLB is never executed live" in pol)

        print("LEDGER (both costs recorded)")
        page.click("#logBtn")
        P = pos()
        sp = P["Los Angeles Rams @ Seattle Seahawks"]
        check("call records taker (kalshi_exec_cost 0.60) and maker (kalshi_exec_cost_maker 0.57)",
              sp["kalshi_exec_cost"] == 0.60 and sp["kalshi_exec_cost_maker"] == 0.57,
              json.dumps({k: sp.get(k) for k in ("kalshi_exec_cost", "kalshi_exec_cost_maker")}))
        check("claim + default execution carry both (claim 0.60/0.57, exec 0.60/0.57)",
              (sp["claim_exec_cost"], sp["claim_exec_cost_maker"], sp["exec_cost"], sp["exec_cost_maker"]) == (0.60, 0.57, 0.60, 0.57))
        bp = P["Miami Dolphins @ Buffalo Bills"]
        check("1c spread position: maker cost null (no maker price), taker 0.62",
              bp["kalshi_exec_cost_maker"] is None and bp["kalshi_exec_cost"] == 0.62)
        page.click("#tabLedger")
        page.click(f"button.execBtn[data-id='{sp['id']}']")
        e = pos()["Los Angeles Rams @ Seattle Seahawks"]
        check("operator-early execution locks both costs (0.60 / 0.57)", (e["exec_cost"], e["exec_cost_maker"]) == (0.60, 0.57))

        print("MLB (M=0.5 from the real export math)")
        load("mlb.json")
        nyy = next(v for k, v in table().items() if "Yankees" in k)
        check("MLB: 'exec +5.0pp @ 0.57 maker (join 0.56) · fee-clears? · taker 0.58 (+4.0pp)'",
              "exec +5.0pp @ 0.57 maker (join 0.56) · fee-clears? · taker 0.58 (+4.0pp)" in nyy[4], nyy[4])

        print("FILLS (ruling 3: maker/taker from the CSV fee vs the formula)")
        page.click("#tabLedger")
        page.set_input_files("#kalshiCsvFile", csv_path)
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('Kalshi CSV')")
        cls = page.evaluate("classifyFills(loadLedger()).map(f=>[f.ticker,f.fee_class_open,f.fee_class_close])")
        by = {t: (o, c) for t, o, c in cls}
        want = {"KXNFLGAME-26OCT04LARSEA-SEA": "taker", "KXNFLGAME-26OCT04MIABUF-BUF": "maker",
                "KXMLBGAME-26OCT04BOSNYY-NYY": "taker", "KXMLBGAME-26OCT03BOSNYY-NYY": "taker_live",
                "KXNFLGAME-26OCT04PHIDAL-DAL": "ambiguous", "KXNFLGAME-26OCT05DETGB-GB": "unknown",
                "KXMVESPORTS-26OCT04-ABC": "taker"}
        for t, w in want.items():
            check(f"{t}: open leg = {w}", by.get(t, (None,))[0] == w, str(by.get(t)))
        check("settled fills: no close-leg class (no close fee)", all(c is None for _, c in by.values()))
        real = page.inner_text("#realized")
        check("REALIZED card: fee-class line + the MLB live-rate doctrine alarm",
              "Fee class (open legs, fee vs formula — #93): maker 1 · taker 3 · taker_live 1 · ambiguous 1 · unknown 1" in real
              and "1 MLB fill(s) at the LIVE rate — doctrine: MLB is never executed live" in real, real[:400])
        txt = page.evaluate("realizedLines(loadLedger()).join('\\n')")
        check("text export carries the fee-class line", "fee class (open legs, fee vs formula): maker 1 · taker 3" in txt)

        print("PRE-SPLIT IMPORT (backfill on re-import)")
        page.evaluate("(()=>{const L=loadLedger(); L.fills.forEach(f=>{delete f.open_fee; delete f.close_fee;}); saveLedger(L);})()")
        pre = page.evaluate("classifyFills(loadLedger()).map(f=>f.fee_class_open)")
        check("a pre-split fill has no class (no per-leg fee stored)", all(x is None for x in pre), str(pre))
        n0 = len(ledger()["fills"])
        page.evaluate("document.getElementById('kalshiCsvFile').value='';"
                      "document.getElementById('ledgerNote').textContent=''")
        page.set_input_files("#kalshiCsvFile", csv_path)
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('Kalshi CSV')")
        post = page.evaluate("classifyFills(loadLedger()).map(f=>f.fee_class_open)")
        check("re-importing the same CSV adds no rows and restores every class",
              len(ledger()["fills"]) == n0 and post.count(None) == 0 and "taker_live" in post, str(post))
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
