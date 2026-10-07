"""
Cockpit render verify for VENUE-EDGE: QUOTE AGE (ARCHITECT 2026-10-07, addendum 4 E): "venue-edge emits no call
(PASS, noref, 'book quote age unknown: no reference') and the venue block keeps its numbers for the record."
The Cockpit renders file blocks only (F1c); files are written by the Python Desk WITH the hold (the export's
default). Checks:
- the ruling's row (San Jose @ St. Louis, books .5265 vs Kalshi .455 on AWAY, 5 books) renders PASS · "no
  reference", greyed, with the file's numbers (book .527, Kalshi .455, +7.1pp) and the exact reason;
- no order line on it, and no "re-run at T-60" hint (a re-run cannot clear the hold — the one Cockpit change);
- a below-floor computed row is held the same way; a pre-computation no-reference row (books 3 < 4) keeps its own
  reason AND its re-run hint (unchanged);
- the auto-claim logs NO venue_edge call (the ledger holds no claim from a held row);
- the Next-24h card shows the held NHL pair as "market-only", never "VENUE 0.25u (shadow)";
- control: the same row written with the hold OFF still renders "VENUE 0.25u" with its order (rendering is the
  file's, not the Cockpit's).

    python3 scripts/cockpit_venue_quote_age_verify.py

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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REASON = "book quote age unknown: no reference"
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def iso(h):
    return (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=h)).replace(microsecond=0).isoformat()


def fx(home, away, fair, kal, books=5, legs=None):
    f = {"home_team": home, "away_team": away, "utc_date": iso(5), "status": "scheduled",
         "market": {"bookmaker_count": books, "fair_prob": {"HOME": fair[0], "AWAY": fair[1]}, "fair_source": "1X2",
                    "captured_at": iso(-0.5)},                                    # fresh capture (#91 passes)
         "kalshi": {"status": "two_sided", "prob": {"HOME": kal[0], "AWAY": kal[1]}},
         "input_quality": {"book_odds": books, "kalshi": "two_sided"}}
    if legs:
        f["kalshi_legs"] = legs
    return f


SJ_LEGS = {"HOME": {"ticker": "KXNHLGAME-26OCT08SJSTL-STL", "bid": 0.53, "ask": 0.55},
           "AWAY": {"ticker": "KXNHLGAME-26OCT08SJSTL-SJ", "bid": 0.44, "ask": 0.46}}
NHL = {"competition_code": "NHL", "fixtures": [
    fx("St. Louis Blues", "San Jose Sharks", (0.4735, 0.5265), (0.545, 0.455), legs=SJ_LEGS),   # the ruling's row
    fx("Boston Bruins", "Toronto Maple Leafs", (0.55, 0.45), (0.54, 0.46),
       legs={"HOME": {"ticker": "T-BOS", "bid": 0.53, "ask": 0.54}}),                          # +1pp: below floor
    fx("Detroit Red Wings", "Ottawa Senators", (0.60, 0.40), (0.50, 0.50), books=3),          # books 3 < 4
]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-quote-age-")
    held_dir, ctl_dir = os.path.join(tmp, "held"), os.path.join(tmp, "control")
    os.makedirs(held_dir)
    os.makedirs(ctl_dir)
    for d in (held_dir, ctl_dir):
        with open(os.path.join(d, "fixtures_NHL.json"), "w") as f:
            json.dump(NHL, f)
    now_ms = float((datetime.now(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))
    card = {"exported_at": iso(0) + "Z", "window": {"from": iso(0) + "Z", "to": iso(24) + "Z", "hours": 24},
            "receipts": {"with_model": 0, "quarantined": 0, "stale_flags": 0}, "fixtures": []}
    for f in NHL["fixtures"][:1]:
        r = {**json.loads(json.dumps(f)), "match_id": 1, "sport": "nhl", "competition": "NHL", "model": None,
             "edge_pp": None, "tier": None, "quarantine": False, "venue_flag": None, "kalshi_home_norm": 0.545,
             "engine": "market_only"}
        r["desk_venue"] = dp.window_venue(r, now_ms)                              # what window.py stamps (hold on)
        card["fixtures"].append(r)
    card_path = os.path.join(tmp, "window_24h.json")
    with open(card_path, "w") as f:
        json.dump(card, f)

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

        def load(path):
            page.evaluate("document.getElementById('summary').textContent=''")
            cdf.upload(page, [path], base=False)                                  # the export's policy (hold ON)
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
            page.click("#tabDesk")

        def venue_rows():
            return page.evaluate("""Array.from(document.querySelectorAll('#venueTable tbody tr')).map(tr=>({
                cells:Array.from(tr.children).map(td=>{const c=td.cloneNode(true);c.querySelectorAll('.order').forEach(e=>e.remove());return c.textContent;}),
                order:Array.from(tr.querySelectorAll('.order')).map(e=>e.textContent).join(''),
                noref:tr.classList.contains('noref')}))""")

        def row(rs, name):
            return next(r for r in rs if name in r["cells"][0])

        ledger = lambda: page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1')||'{\"calls\":[]}').calls")  # noqa: E731

        print("HELD (hold on: the export's default)")
        load(os.path.join(held_dir, "fixtures_NHL.json"))
        rs = venue_rows()
        sj = row(rs, "St. Louis")
        check("the ruling's row: PASS · 'no reference', greyed",
              sj["cells"][5] == "PASSno reference" and sj["noref"], json.dumps(sj))
        check("its numbers are the file's: side San Jose, book 0.526 (toFixed of .5265), Kalshi 0.455, +7.1pp",
              sj["cells"][1] == "San Jose Sharks" and sj["cells"][2] == "0.526" and sj["cells"][3] == "0.455"
              and sj["cells"][4] == "+7.1pp", json.dumps(sj["cells"]))
        check("reason exactly the ruling's, no re-run hint", sj["cells"][6] == REASON, sj["cells"][6])
        check("no order line", sj["order"] == "", sj["order"])
        bo = row(rs, "Boston")
        check("below-floor computed row is held the same way (numbers kept: +1.0pp)",
              bo["cells"][5] == "PASSno reference" and bo["cells"][6] == REASON and bo["cells"][4] == "+1.0pp",
              json.dumps(bo["cells"]))
        de = row(rs, "Detroit")
        check("books 3 < 4 keeps its own reason and its re-run hint (unchanged)",
              "books 3 < 4" in de["cells"][6] and "re-run at T-60" in de["cells"][6] and de["noref"],
              json.dumps(de["cells"]))
        dv = page.evaluate("deskVenue.map(x=>[x.r.home,x.v.eligible,x.v.held])")
        check("deskVenue: nothing eligible; the two computed rows marked held",
              dv == [["St. Louis Blues", False, True], ["Boston Bruins", False, True], ["Detroit Red Wings", False, False]],
              json.dumps(dv))
        led = ledger()
        check("auto-claim logged NO venue_edge call", not [c for c in led if c.get("engine") == "venue_edge"],
              json.dumps(led)[:300])

        print("NEXT 24H CARD (desk_venue stamped with the hold on)")
        page.click("#tabNext")
        page.set_input_files("#windowFile", card_path)
        page.wait_for_function("!document.getElementById('nextTable').hidden")
        wr = page.eval_on_selector_all("#nextTable tbody tr", "trs => trs.map(t => [...t.children].map(td => td.innerText))")
        check("held NHL pair reads market-only, never VENUE", wr and wr[0][9] == "market-only", str(wr))

        print("CONTROL (hold off: the Cockpit renders whatever the file says)")
        page.evaluate("localStorage.clear()")
        page.reload()
        with dp.quote_age_rule_off():
            load(os.path.join(ctl_dir, "fixtures_NHL.json"))
        sj = row(venue_rows(), "St. Louis")
        check("same row from a pre-ruling file: VENUE 0.25u with its order",
              sj["cells"][5] == "VENUE 0.25u" and "BUY YES KXNHLGAME-26OCT08SJSTL-SJ" in sj["order"], json.dumps(sj))
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
