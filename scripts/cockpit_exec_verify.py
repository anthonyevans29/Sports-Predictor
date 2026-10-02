"""
Cockpit K2 EXECUTABLE-EDGE DISPLAY headless verification (K-track, architect
2026-09-29). Checks, over SYNTHETIC files:
- a HOME pick with Kalshi quotes shows "exec +x.xpp @ cost" beside the fair
  edge, and "fee-clears?" only when exec edge >= 4pp;
- an AWAY pick with (home-contract) quotes and NO away fields (a pre-#89
  export) shows "exec —", never a derived price (the #89 NO-side path is
  checked in cockpit_no_side_verify.py);
- rows without quotes show nothing extra;
- calls, units and tiers are IDENTICAL with and without the quotes
  (informational only: no sizing / tier / call change);
- the ledger records exec cost at claim (claim_exec_cost) and at execution
  (exec_cost): the default execution follows the re-log, an operator-early
  execution locks it.

    python3 scripts/cockpit_exec_verify.py

Writes nothing to the repo; no DB. Needs Playwright + Chromium.
"""
import copy
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
D1 = (NOW + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def nfl(home, away, p_home, fair_home, ask=None, cost=None, bid=None):
    r = {"home_team": home, "away_team": away, "utc_date": D1,
         "prediction": {"home_win_prob": p_home, "away_win_prob": round(1 - p_home, 4), "tier": "lean"},
         "market": {"bookmaker_count": 7, "fair_prob": {"HOME": fair_home, "AWAY": round(1 - fair_home, 4)}},
         "market_divergence_pp": round((p_home - fair_home) * 100, 1), "quarantine": False,
         "input_quality": {"book_odds": 7, "injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}},
         "kalshi_bid": None, "kalshi_ask": None, "kalshi_exec_cost": None}
    if ask is not None:
        r.update(kalshi_bid=bid if bid is not None else round(ask - 0.01, 2), kalshi_ask=ask, kalshi_exec_cost=cost)
    return r


def doc(bills_cost):
    return {"sport": "nfl", "rehearsal": False, "predictions": [
        nfl("Buffalo Bills", "Miami Dolphins", 0.66, 0.60, ask=0.60, cost=bills_cost),   # HOME pick
        nfl("Green Bay Packers", "Detroit Lions", 0.62, 0.57, ask=0.58, cost=0.60),       # HOME pick, exec +2.0
        nfl("Dallas Cowboys", "Philadelphia Eagles", 0.36, 0.42, ask=0.41, cost=0.43),    # AWAY pick
        nfl("Chicago Bears", "Minnesota Vikings", 0.65, 0.58),                            # no quotes
        nfl("Denver Broncos", "Las Vegas Raiders", 0.62, 0.55, ask=0.54, cost=0.56, bid=0.50),  # 4¢ spread: join 0.51
    ]}


# An MLB prediction export row as export-predictions now writes it (architect
# 2026-09-30: MLB/soccer rows carry kalshi_bid/ask/exec_cost like NFL).
MLB = {"sport": "mlb", "predictions": [
    {"home_team": "New York Yankees", "away_team": "Boston Red Sox", "utc_date": D1, "competition": "MLB",
     "prediction": {"home_win_prob": 0.62, "draw_prob": None, "away_win_prob": 0.38},
     "market": {"bookmaker_count": 6, "selections": {"HOME": {"fair_prob": 0.56}, "AWAY": {"fair_prob": 0.44}}},
     "kalshi_bid": 0.55, "kalshi_ask": 0.57, "kalshi_exec_cost": 0.59}]}


def strip(d):
    d = copy.deepcopy(d)
    for r in d["predictions"]:
        r.update(kalshi_bid=None, kalshi_ask=None, kalshi_exec_cost=None)
    return d


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-exec-")
    files = {"day1.json": doc(0.62), "day2.json": doc(0.63), "noquotes.json": strip(doc(0.62)),
             "mlb.json": MLB}
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

        def table():
            return page.evaluate("""Array.from(document.querySelectorAll('#slate tbody tr'))
                .filter(tr=>!tr.classList.contains('vshadow'))
                .map(tr=>Array.from(tr.children).map(td=>td.textContent))""")

        print("DESK")
        load("noquotes.json")
        base = {r[0]: (r[5], r[6]) for r in table()}
        load("day1.json")
        rows = {r[0]: r for r in table()}
        bills = next(v for k, v in rows.items() if "Buffalo" in k)
        # These fixtures are PRE-SPLIT exports (kalshi_exec_cost only, no
        # exec_cost_maker): the Desk falls back to the taker cost and says so
        # (#93 split; the maker path is checked in cockpit_maker_taker_verify.py).
        check("HOME pick with quotes: fair edge + 'exec +4.0pp @ 0.620 taker' + 1¢ spread: joining = taking + fee-clears?",
              bills[4] == "+6.0pp" + "exec +4.0pp @ 0.620 taker (spread 1¢ — joining = taking) · fee-clears?", bills[4])
        gb = next(v for k, v in rows.items() if "Green Bay" in k)
        check("exec edge +2.0pp: shown, no fee-clears? marker",
              "exec +2.0pp @ 0.60" in gb[4] and "fee-clears?" not in gb[4], gb[4])
        dal = next(v for k, v in rows.items() if "Dallas" in k)
        # #89: these rows carry no away_* fields (pre-#89 shape), so the Desk
        # still derives nothing; the NO-side path is cockpit_no_side_verify.py.
        check("AWAY pick, pre-#89 export (no away fields): 'exec —', never a derived price",
              "exec — (quotes are the home contract's)" in dal[4], dal[4])
        den = next(v for k, v in rows.items() if "Denver" in k)
        check("pre-split export: join bid = bid + 1¢ (0.51) with its pre-fee edge, labelled as having no maker cost",
              "join 0.51 (+11.0pp pre-fee; no maker cost in this export)" in den[4], den[4])
        chi = next(v for k, v in rows.items() if "Chicago" in k)
        check("no quotes: nothing extra", chi[4] == "+7.0pp", chi[4])
        check("informational only: every call and unit identical with and without quotes",
              {k: (r[5], r[6]) for k, r in rows.items()} == base, str(base))

        print("LEDGER")
        page.click("#logBtn")
        P = pos()
        b1 = P["Miami Dolphins @ Buffalo Bills"]
        check("claim records exec cost at claim and at execution (0.62 / 0.62)",
              b1["claim_exec_cost"] == 0.62 and b1["exec_cost"] == 0.62, json.dumps({k: b1.get(k) for k in ("claim_exec_cost", "exec_cost")}))
        d1 = P["Philadelphia Eagles @ Dallas Cowboys"]
        check("AWAY position: exec cost null (not derived), labelled by absence",
              d1["kalshi_exec_cost"] is None and d1["claim_exec_cost"] is None)
        page.click("#tabLedger")
        gid = P["Detroit Lions @ Green Bay Packers"]["id"]
        page.click(f"button.execBtn[data-id='{gid}']")
        check("operator-early execution locks exec_cost at the current 0.60",
              pos()["Detroit Lions @ Green Bay Packers"]["exec_cost"] == 0.60)

        print("ORDER TYPE + FILL")
        did = P["Las Vegas Raiders @ Denver Broncos"]["id"]
        check("position records the join bid seen at capture (0.51)",
              P["Las Vegas Raiders @ Denver Broncos"]["kalshi_join_bid"] == 0.51)
        page.select_option(f"select.fillType[data-id='{did}']", "limit")
        page.fill(f"input.fillPx[data-id='{did}']", "0.99x")
        page.click(f"button.fillBtn[data-id='{did}']")
        check("a malformed fill price is refused, nothing recorded",
              "Fill price must be" in page.inner_text("#ledgerNote") and "order_type" not in pos()["Las Vegas Raiders @ Denver Broncos"])
        page.select_option(f"select.fillType[data-id='{did}']", "limit")
        page.fill(f"input.fillPx[data-id='{did}']", "51")
        page.click(f"button.fillBtn[data-id='{did}']")
        dp = pos()["Las Vegas Raiders @ Denver Broncos"]
        note = page.inner_text("#ledgerNote")
        check("limit fill @ 51¢ recorded as order_type limit / fill_price 0.51, note cites the join bid",
              dp["order_type"] == "limit" and dp["fill_price"] == 0.51 and "join bid at capture was 0.51" in note, note)
        page.select_option(f"select.fillType[data-id='{did}']", "market")
        page.fill(f"input.fillPx[data-id='{did}']", "0.54")
        page.click(f"button.fillBtn[data-id='{did}']")
        check("re-recording replaces the fill and says so (market @ 0.54, replaces limit @ 0.51)",
              pos()["Las Vegas Raiders @ Denver Broncos"]["order_type"] == "market"
              and "replaces limit @ 0.51" in page.inner_text("#ledgerNote"))
        check("open list shows the recorded order", "market @ 0.540" in page.inner_text("#openList"))
        rows_txt = page.inner_text("#openList")
        check("open list shows the recorded Kalshi cost ('k 0.620')", "k 0.620" in rows_txt)
        page.evaluate("localDate=(d)=>{d=d||new Date(Date.now()+86400000);"
                      "return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}")
        load("day2.json")
        page.click("#logBtn")
        P2 = pos()
        b2 = P2["Miami Dolphins @ Buffalo Bills"]
        check("re-log: claim exec cost frozen (0.62), default execution follows (0.63)",
              b2["claim_exec_cost"] == 0.62 and b2["exec_cost"] == 0.63, json.dumps({k: b2.get(k) for k in ("claim_exec_cost", "exec_cost")}))
        check("operator-early exec_cost stays locked (0.60) through the re-log",
              P2["Detroit Lions @ Green Bay Packers"]["exec_cost"] == 0.60)
        print("MLB (exports carry the K-track fields since 2026-09-30)")
        load("mlb.json")
        nyy = next(v for k, v in {r[0]: r for r in table()}.items() if "Yankees" in k)
        check("MLB HOME pick: exec edge + join bid render from the MLB export's fields",
              "exec +3.0pp @ 0.590 taker" in nyy[4] and "join 0.56" in nyy[4], nyy[4])
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
