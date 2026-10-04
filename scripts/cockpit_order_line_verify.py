"""
ORDER LINE (ARCHITECT 2026-10-04): every Desk PLAY / VENUE row and every
parlay-ticket leg carries `desk.order` from the file, and the Cockpit renders
it verbatim — "placing an order is copy-exact, never a lookup". The Cockpit
never computes an order. Checks, over SYNTHETIC files:
- a PLAY row shows the file's order text (ticker, side, limit, contracts);
- a PLAY row with no stored ticker shows the file's refusal reason, no line;
- a PASS row shows no order;
- an eligible VENUE row (market-only) shows the file's order text;
- every parlay-ticket leg shows its file order text;
- calls and units are unchanged by the order line (no policy change).

    python3 scripts/cockpit_order_line_verify.py

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
import cockpit_desk_files as cdf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KICK = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
K = KICK.strftime("%Y-%m-%dT%H:%M:%S")
CAP = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)).replace(microsecond=0).isoformat()
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def legs(code, home, away, h, a):
    return {"HOME": {"ticker": f"{code}-{home}" if home else None, "bid": h[0], "ask": h[1]},
            "AWAY": {"ticker": f"{code}-{away}" if away else None, "bid": a[0], "ask": a[1]}}


def nfl(home, away, p_home, fair_h, kl):
    return {"home_team": home, "away_team": away, "utc_date": K,
            "prediction": {"home_win_prob": p_home, "away_win_prob": round(1 - p_home, 4), "tier": "lean"},
            "market": {"bookmaker_count": 7, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)},
                       "fair_source": "1X2"},
            "quarantine": False, "market_divergence_pp": round((p_home - fair_h) * 100, 1),
            "kalshi_legs": kl,
            "input_quality": {"book_odds": 7, "injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}}


def fixture(home, away, fair, kal, kl):
    return {"home_team": home, "away_team": away, "utc_date": K, "status": "scheduled",
            "market": {"bookmaker_count": 6, "fair_prob": {"HOME": fair[0], "AWAY": fair[1]},
                       "fair_source": "1X2", "captured_at": CAP},
            "kalshi": {"status": "two_sided", "prob": {"HOME": kal[0], "AWAY": kal[1]}},
            "kalshi_legs": kl, "input_quality": {"book_odds": 6, "kalshi": "two_sided"}}


NFL = {"sport": "nfl", "rehearsal": False, "predictions": [
    nfl("Seattle Seahawks", "Los Angeles Rams", 0.64, 0.58,
        legs("KXNFLGAME-SEALAR", "SEA", "LAR", (0.57, 0.59), (0.41, 0.43))),      # PLAY, ticker on file
    nfl("Kansas City Chiefs", "Denver Broncos", 0.66, 0.59,
        legs("KXNFLGAME-KCDEN", "KC", "DEN", (0.60, 0.62), (0.38, 0.40))),        # PLAY, ticker on file
    nfl("Dallas Cowboys", "Philadelphia Eagles", 0.64, 0.58,
        legs("KXNFLGAME-DALPHI", None, None, (0.57, 0.59), (0.41, 0.43))),        # PLAY, no ticker stored
    nfl("Chicago Bears", "Minnesota Vikings", 0.58, 0.57,
        legs("KXNFLGAME-CHIMIN", "CHI", "MIN", (0.56, 0.58), (0.42, 0.44))),      # 1pp -> PASS
]}
NCAA = {"competition_code": "NCAA", "fixtures": [
    fixture("Ohio State", "Michigan", (0.60, 0.40), (0.52, 0.48),
            legs("KXNCAAFGAME-OSUMICH", "OSU", "MICH", (0.51, 0.52), (0.47, 0.49))),  # VENUE, 1c spread -> ask
]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-order-")
    for n, d in {"nfl.json": NFL, "fixtures_NCAA.json": NCAA}.items():
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
        cdf.upload(page, [os.path.join(tmp, n) for n in ("nfl.json", "fixtures_NCAA.json")])
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        page.click("#tabDesk")
        with open(os.path.join(tmp, "nfl.json")) as f:
            nfl_doc = json.load(f)
        with open(os.path.join(tmp, "fixtures_NCAA.json")) as f:
            ncaa_doc = json.load(f)
        with open(os.path.join(tmp, "desk_parlays.json")) as f:
            par_doc = json.load(f)
        file_order = {r["home_team"]: r["desk"].get("order") for r in nfl_doc["predictions"] + ncaa_doc["fixtures"]}

        def rows(table):
            return page.evaluate(f"""Array.from(document.querySelectorAll('#{table} tbody tr'))
                .filter(tr=>!tr.classList.contains('vshadow'))
                .map(tr=>({{name:tr.children[0].textContent,
                  line:(tr.querySelector('code.orderline')||{{}}).textContent||null,
                  note:(tr.querySelector('.note.order')||{{}}).textContent||null}}))""")

        def row(rs, name):
            return next(r for r in rs if name in r["name"])

        print("MODEL TABLE")
        rs = rows("slate")
        for team in ("Seattle", "Kansas City"):
            o = file_order[next(k for k in file_order if team in k)]
            r = row(rs, team)
            check(f"PLAY {team}: renders the file's order text verbatim",
                  o and o.get("text") and r["line"] == o["text"] and "BUY YES" in r["line"], json.dumps([r, o]))
        sea = row(rs, "Seattle")
        check("PLAY order: join bid, 10 contracts per 1u (default unit)",
              sea["line"] == "BUY YES KXNFLGAME-SEALAR-SEA @ 0.57 × 10", json.dumps(sea))
        dal = row(rs, "Dallas")
        check("PLAY with no stored ticker: the file's refusal, no order line",
              dal["line"] is None and dal["note"] and "no Kalshi ticker" in dal["note"], json.dumps(dal))
        chi = row(rs, "Chicago")
        check("PASS: no order", chi["line"] is None and chi["note"] is None, json.dumps(chi))
        calls = page.evaluate("deskCalls.map(x=>[x.r.home,x.call,x.units])")
        want = [[r["home_team"], r["desk"]["call"], r["desk"]["units"]] for r in nfl_doc["predictions"]]
        check("calls and units are the file's (no policy change)",
              all(c in [list(x) for x in calls] for c in want), json.dumps(calls))

        print("VENUE TABLE")
        vs = rows("venueTable")
        osu = row(vs, "Ohio State")
        o = file_order["Ohio State"]
        check("eligible VENUE (market-only): renders the file's order text",
              o and osu["line"] == o["text"], json.dumps([osu, o]))
        check("VENUE order: 1c spread takes the ask", osu["line"] == "BUY YES KXNCAAFGAME-OSUMICH-OSU @ 0.52 × 2",
              json.dumps(osu))

        print("PARLAY TICKETS")
        tix = par_doc.get("tickets") or []
        want = [l["order"]["text"] for t in tix for l in t["legs"] if (l.get("order") or {}).get("text")]
        shown = page.evaluate("Array.from(document.querySelectorAll('#parlayOut code.orderline')).map(e=>e.textContent)")
        check("at least one ticket built from the file", bool(tix), json.dumps(par_doc)[:300])
        check("every ticket leg shows its file order text", bool(want) and sorted(shown) == sorted(want),
              json.dumps([shown, want]))
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    sys.exit(0 if all(CHECKS) else 1)


if __name__ == "__main__":
    main()
