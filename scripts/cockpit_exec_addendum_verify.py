"""
Cockpit render verify for the #87 EXECUTABLE-EDGE v1.1 ADDENDUM (ARCHITECT-RULE 2026-10-06). Files are written
by the Python Desk WITH the addendum (cockpit_desk_files base=False) and loaded into the Cockpit, which only
renders them (F1c). Checks:
- a PLAY clearing exec >= 4pp renders "TAKE at the ask · ask + taker fee · exec ≥ 4pp: full units" at 1u;
- a PLAY whose fair edge clears but exec does not renders "half units" at 0.5u, and the auto-claim logs 0.5u;
- a PLAY with no executable quote is 0.5u, its reason says so;
- a 2c spread is TAKE (the ledger's kalshi_join_bid is null); a >= 3c spread renders "join";
- venue: fair >= 5pp but exec < 4pp is PASS with the exec reason; fair and exec both clear is VENUE 0.25u;
- parlay tickets show "Π executable cost", each leg's exec cost and the independence-estimate label.

    python3 scripts/cockpit_exec_addendum_verify.py

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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cockpit_desk_files as cdf  # noqa: E402
from src.walters import desk_policy as dp  # noqa: E402
from src.walters.venue import kalshi_exec  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.now(timezone.utc).replace(microsecond=0)
D1 = (NOW + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
SOON = (NOW + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%S")
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
    if ask is not None:
        r.update(kalshi_exec(bid, ask, "NFL", two_way=True))
    return r


NFL = {"sport": "nfl", "rehearsal": False, "predictions": [
    nfl("Buffalo Bills", "Miami Dolphins", 0.66, 0.60, bid=0.59, ask=0.60),       # exec 0.617: +4.3 -> full
    nfl("Green Bay Packers", "Detroit Lions", 0.66, 0.60, bid=0.62, ask=0.64),    # exec 0.656: +0.4 -> half, 2c
    nfl("Chicago Bears", "Minnesota Vikings", 0.66, 0.60),                        # no quote -> half
    nfl("Denver Broncos", "Las Vegas Raiders", 0.66, 0.60, bid=0.55, ask=0.59),   # 4c spread: join; exec +5.3
]}


def fx(home, away, fair_h, bid, ask):
    return {"home_team": home, "away_team": away, "utc_date": SOON, "status": "scheduled",
            "market": {"bookmaker_count": 5, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)},
                       "captured_at": (NOW - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S")},
            "kalshi": {"status": "two_sided", "prob": {"HOME": 0.52, "AWAY": 0.48}},
            "kalshi_legs": {"HOME": {"ticker": f"KXNHLGAME-X-{home[:3].upper()}", "bid": bid, "ask": ask}},
            **kalshi_exec(bid, ask, "NHL", two_way=True)}


NHL = {"competition": "NHL", "fixtures": [fx("Boston Bruins", "Toronto Maple Leafs", 0.60, 0.52, 0.53),
                                          fx("New York Rangers", "New Jersey Devils", 0.60, 0.56, 0.57)]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-exec-addendum-")
    paths = []
    for n, d in (("nfl.json", NFL), ("nhl.json", NHL)):
        paths.append(os.path.join(tmp, n))
        with open(paths[-1], "w") as f:
            json.dump(d, f)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                          functools.partial(Quiet, directory=os.path.join(ROOT, "tools")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html")
        cdf.upload(page, paths, base=False)
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        page.click("#tabDesk")
        rows = {r[0]: r for r in page.evaluate("""Array.from(document.querySelectorAll('#slate tbody tr'))
            .filter(tr=>!tr.classList.contains('vshadow')).map(tr=>Array.from(tr.children).map(td=>td.textContent))""")}
        get = lambda k: next(v for g, v in rows.items() if k in g)
        b, gb, chi, den = get("Buffalo"), get("Green Bay"), get("Chicago"), get("Denver")
        check("exec clears: 'TAKE at the ask · ask + taker fee · exec ≥ 4pp: full units', 1u",
              "exec +4.3pp @ 0.617 TAKE at the ask · ask + taker fee · exec ≥ 4pp: full units" in b[4]
              and b[6] == "1", f"{b[4]} | {b[6]}")
        check("fair clears, exec does not: 'exec < 4pp: half units', 0.5u, reason names the cost",
              "exec < 4pp: half units" in gb[4] and gb[6] == "0.5"
              and "exec edge 0.4pp < 4pp at ask + taker fee 0.656 → half units" in gb[7], f"{gb[4]} | {gb[6]}")
        check("no executable quote: 0.5u, reason says so",
              chi[6] == "0.5" and "no executable quote for the pick" in chi[7], f"{chi[6]} | {chi[7]}")
        check("4c spread: rendered as 'join 0.56 (spread ≥ 3¢)', full units at exec +5.3",
              "join 0.56 (spread ≥ 3¢)" in den[4] and den[6] == "1", den[4])
        led = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))") or {"calls": []}
        st = {c["game"]: c for c in led["calls"] if c.get("call_type") == "straight"}
        g = next((c for k, c in st.items() if "Green Bay" in k), None)
        check("auto-claim logs the half-unit PLAY at 0.5u, join bid null on a 2c spread (TAKE)",
              g is not None and g["units"] == 0.5 and g.get("kalshi_join_bid") is None,
              json.dumps({k: g.get(k) for k in ("units", "kalshi_join_bid")} if g else None))
        ven = page.evaluate("""Array.from(document.querySelectorAll('#venueTable tbody tr'))
            .map(tr=>Array.from(tr.children).map(td=>td.textContent))""")
        bos = next(v for v in ven if "Boston" in v[0])
        nyr = next(v for v in ven if "New York Rangers" in v[0])
        check("venue: fair +8.0 and exec +5.3 → VENUE 0.25u with a TAKE order",
              bos[5].startswith("VENUE 0.25u") and "@ 0.53" in bos[5] and "exec edge 5.3pp ≥ 4pp" in bos[6], bos)
        check("venue: fair +8.0 but exec +1.3 → PASS (below floor), exec reason shown",
              nyr[5].startswith("PASS") and "exec edge 1.3pp < 4pp at ask + taker fee 0.587" in nyr[6], nyr)
        par = page.evaluate("document.getElementById('parlayOut').textContent")
        check("parlays: Π executable cost, each leg's exec cost, the independence-estimate label",
              "Π executable cost" in par and "exec 0.617" in par and dp.PARLAY_LABEL in par, par[:300])
        browser.close()
    srv.shutdown()
    check("no page errors", not errors, "; ".join(errors))
    n = sum(CHECKS)
    print(f"\n{n}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if n == len(CHECKS) else ""))
    return 0 if n == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
