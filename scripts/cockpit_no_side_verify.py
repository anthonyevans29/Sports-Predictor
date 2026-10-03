"""
Cockpit NO-SIDE exec cost headless verification (#89, architect 2026-09-30).
An AWAY pick on a TWO-WAY market is priced on the NO side of the home
contract: NO ask = 1 - home bid, NO bid = 1 - home ask, the same fee formula
per fill. The export rows are built by the REAL `venue.kalshi_exec`, so the
Python math and the Cockpit read are checked together. Checks, over SYNTHETIC
files:
- export: two-way rows carry away_bid / away_ask / exec_cost_taker_away /
  exec_cost_maker_away; a 1c spread has no NO-side maker price; soccer (1X2)
  away fields are null;
- Desk: an NFL AWAY pick renders the NO-side exec edge (maker basis, "NO side"
  labelled; taker basis on a 1c spread); a HOME pick is unchanged; a pre-#89
  export and a soccer AWAY pick still show "exec — (quotes are the home
  contract's)"; calls and units are identical with and without quotes;
- ledger: the AWAY call records the NO-side taker / maker costs and join bid
  at capture, claim and execution;
- policy card states the NO side (the old "home contract only" is gone).

    python3 scripts/cockpit_no_side_verify.py

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cockpit_desk_files as cdf  # noqa: E402  (F1c: the Cockpit renders desk files only)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
D1 = (NOW + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
CHECKS = []
AWAY_KEYS = ("away_bid", "away_ask", "exec_cost_taker_away", "exec_cost_maker_away")
ALL_K = ("kalshi_bid", "kalshi_ask", "exec_cost_taker", "exec_cost_maker") + AWAY_KEYS


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def nfl(home, away, p_home, fair_home, bid, ask):
    r = {"home_team": home, "away_team": away, "utc_date": D1, "competition": "NFL",
         "prediction": {"home_win_prob": p_home, "away_win_prob": round(1 - p_home, 4), "tier": "lean"},
         "market": {"bookmaker_count": 7, "fair_prob": {"HOME": fair_home, "AWAY": round(1 - fair_home, 4)}},
         "market_divergence_pp": round((p_home - fair_home) * 100, 1), "quarantine": False,
         "input_quality": {"book_odds": 7, "injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}}
    r.update(kalshi_exec(bid, ask, "NFL", two_way=True))     # NFL is two-way (as nfl_predict passes)
    return r


def main():
    print("EXPORT (venue.kalshi_exec, two-way vs 1X2)")
    dal = kalshi_exec(0.40, 0.43, "NFL", two_way=True)
    check("NFL home 0.40/0.43 -> NO 0.57/0.60: taker 0.617 (0.60 + 17c/10), maker 0.584 (join 0.58 + 4c/10, #206)",
          (dal["away_bid"], dal["away_ask"], dal["exec_cost_taker_away"], dal["exec_cost_maker_away"])
          == (0.57, 0.6, 0.617, 0.584), json.dumps({k: dal[k] for k in AWAY_KEYS}))
    one = kalshi_exec(0.41, 0.42, "NFL", two_way=True)
    check("1c spread (NO 0.58/0.59): no NO-side maker price, taker 0.607",
          one["exec_cost_maker_away"] is None and one["exec_cost_taker_away"] == 0.607,
          json.dumps({k: one[k] for k in AWAY_KEYS}))
    soc = kalshi_exec(0.47, 0.49, "PL")
    check("soccer 1X2: every away field null (NO on HOME = draw-or-away), home still priced",
          all(soc[k] is None for k in AWAY_KEYS) and soc["exec_cost_taker"] == 0.507)

    D = {"sport": "nfl", "rehearsal": False, "predictions": [
        nfl("Seattle Seahawks", "Los Angeles Rams", 0.62, 0.56, 0.55, 0.58),       # HOME pick (unchanged)
        nfl("Dallas Cowboys", "Philadelphia Eagles", 0.36, 0.42, 0.40, 0.43),      # AWAY pick: NO-side maker
        nfl("Chicago Bears", "Minnesota Vikings", 0.35, 0.41, 0.41, 0.42),         # AWAY pick: 1c spread
    ]}
    PRE = json.loads(json.dumps(D))          # a pre-#89 export: no away keys at all
    for r in PRE["predictions"]:
        for k in AWAY_KEYS:
            r.pop(k)
    NOQ = json.loads(json.dumps(D))
    for r in NOQ["predictions"]:
        for k in ALL_K:
            r[k] = None
    S = {"sport": "soccer", "predictions": [
        {"home_team": "Everton", "away_team": "Arsenal", "utc_date": D1, "competition": "PL",
         "prediction": {"probabilities": {"home_win": 0.22, "draw": 0.25, "away_win": 0.53}},
         "market": {"bookmaker_count": 8, "selections": {"HOME": {"fair_prob": 0.26}, "DRAW": {"fair_prob": 0.27},
                                                         "AWAY": {"fair_prob": 0.47}}},
         "input_quality": {"book_odds": 8, "kalshi": "three_way"},
         **kalshi_exec(0.25, 0.27, "PL", two_way=False)}]}

    tmp = tempfile.mkdtemp(prefix="cockpit-no-")
    for n, d in {"nfl.json": D, "pre.json": PRE, "noquotes.json": NOQ, "soccer.json": S}.items():
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
            return {r[0]: r for r in page.evaluate("""Array.from(document.querySelectorAll('#slate tbody tr'))
                .filter(tr=>!tr.classList.contains('vshadow'))
                .map(tr=>Array.from(tr.children).map(td=>td.textContent))""")}

        print("DESK (an AWAY pick is priced on the NO side)")
        load("noquotes.json")
        base = {k: (r[1], r[5], r[6]) for k, r in table().items()}
        # AUTO-CLAIM (2026-10-03): loading a desk file claims its calls; the no-quotes
        # file is a render comparison only, so its claims are cleared before the real file.
        page.evaluate("localStorage.removeItem('bd_ledger_v1')")
        load("nfl.json")
        rows = table()
        d = next(v for k, v in rows.items() if "Dallas" in k)
        check("AWAY pick: 'exec +5.6pp @ 0.584 maker (join 0.58, NO side) · fee-clears? · taker 0.617 (+2.3pp)'",
              d[4] == "+6.0pp" + "exec +5.6pp @ 0.584 maker (join 0.58, NO side) · fee-clears? · taker 0.617 (+2.3pp)",
              d[4])
        c = next(v for k, v in rows.items() if "Chicago" in k)
        check("AWAY 1c spread: taker basis, 'NO side', 'joining = taking'",
              "exec +4.3pp @ 0.607 taker (NO side) (spread 1¢ — joining = taking) · fee-clears?" in c[4], c[4])
        s = next(v for k, v in rows.items() if "Seattle" in k)
        check("HOME pick unchanged: 'exec +5.6pp @ 0.564 maker (join 0.56) · fee-clears? · taker 0.597 (+2.3pp)'",
              "exec +5.6pp @ 0.564 maker (join 0.56) · fee-clears? · taker 0.597 (+2.3pp)" in s[4]
              and "NO side" not in s[4], s[4])
        check("informational only: picks, calls and units identical with and without quotes",
              {k: (r[1], r[5], r[6]) for k, r in rows.items()} == base, str(base))
        pol = page.inner_text("#deskView")
        check("policy card: NO side stated, 'home contract only' gone",
              "priced on its NO side (1 − home bid/ask" in pol and "home contract only" not in pol)

        print("LEDGER (the AWAY call records the NO-side costs)")
        page.click("#logBtn")
        P = pos()
        dp = P["Philadelphia Eagles @ Dallas Cowboys"]
        check("AWAY call: pick AWAY, kalshi_exec_cost 0.617 (NO taker), maker 0.584, join bid 0.58",
              (dp["pick"], dp["kalshi_exec_cost"], dp["kalshi_exec_cost_maker"], dp["kalshi_join_bid"])
              == ("AWAY", 0.617, 0.584, 0.58),
              json.dumps({k: dp.get(k) for k in ("pick", "kalshi_exec_cost", "kalshi_exec_cost_maker", "kalshi_join_bid")}))
        check("claim + default execution carry the NO-side costs (0.617 / 0.584)",
              (dp["claim_exec_cost"], dp["claim_exec_cost_maker"], dp["exec_cost"], dp["exec_cost_maker"])
              == (0.617, 0.584, 0.617, 0.584))
        cp = P["Minnesota Vikings @ Chicago Bears"]
        check("AWAY 1c spread position: maker null, taker 0.607, join bid null",
              cp["kalshi_exec_cost_maker"] is None and cp["kalshi_exec_cost"] == 0.607 and cp["kalshi_join_bid"] is None)
        sp = P["Los Angeles Rams @ Seattle Seahawks"]
        check("HOME call unchanged (0.597 / 0.564)", (sp["kalshi_exec_cost"], sp["kalshi_exec_cost_maker"]) == (0.597, 0.564))

        print("NO AWAY FIELDS (pre-#89 export; soccer 1X2)")
        load("pre.json")
        pd = next(v for k, v in table().items() if "Dallas" in k)
        check("pre-#89 export: AWAY pick keeps 'exec — (quotes are the home contract's)'",
              "exec — (quotes are the home contract's)" in pd[4], pd[4])
        load("soccer.json")
        sr = next(v for k, v in table().items() if "Everton" in k)
        check("soccer AWAY pick: 'exec —', never NO-on-HOME as an away price",
              sr[1] == "Arsenal" and "exec — (quotes are the home contract's)" in sr[4], str(sr))
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
