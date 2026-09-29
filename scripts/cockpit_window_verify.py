"""
Cockpit "Next 24h" tab headless verification (window service, 2026-09-27).

Loads a synthetic window card (the window_24h.json grammar: fixtures rows plus
model / edge_pp / tier / quarantine / venue_flag / engine) through the tab's
file input. Checks:
- rows render in card order with the model, book fair, Kalshi and edge text;
- flags (QUARANTINE, STALE-BOOK?);
- the venue column comes from the EXISTING venueEdge(): an eligible
  market-only pair shows "VENUE 0.25u (shadow)", a thin pair stays
  market-only, and a model row stays model_edge;
- a non-card JSON is refused with a message;
- tab switching hides the other views;
- no page errors.
Writes nothing to the repo; no DB. Needs Playwright + Chromium.
Run:  python3 scripts/cockpit_window_verify.py
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
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def ko(h):
    return (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=h)).replace(microsecond=0).isoformat()


def row(mid, sport, comp, home, away, h, fair, books, kal=None, kal_norm=None, model=None,
        edge=None, tier=None, quar=False, flag=None):
    return {"match_id": mid, "utc_date": ko(h), "status": "scheduled", "home_team": home,
            "away_team": away, "sport": sport, "competition": comp,
            "market": {"bookmaker_count": books, "fair_prob": fair, "fair_source": "1X2"},
            "kalshi": kal, "kalshi_home_norm": kal_norm, "model": model, "edge_pp": edge,
            "tier": tier, "quarantine": quar, "venue_flag": flag,
            "engine": "model_edge" if model else "market_only"}


CARD = {
    "exported_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
    "window": {"from": ko(0) + "Z", "to": ko(24) + "Z", "hours": 24},
    "receipts": {"with_model": 2, "quarantined": 1, "stale_flags": 1},
    "fixtures": [
        row(1, "nfl", "NFL", "Kansas City Chiefs", "Buffalo Bills", 2, {"HOME": 0.62, "AWAY": 0.38}, 6,
            kal={"status": "two_sided", "prob": {"HOME": 0.45, "AWAY": 0.55}}, kal_norm=0.45,
            model={"top_pick": "HOME", "top_pick_prob": 0.77, "tier": "strong"}, edge=15.0,
            tier="strong", quar=True, flag="STALE-BOOK?"),
        row(2, "nhl", "NHL", "Boston Bruins", "Toronto Maple Leafs", 5, {"HOME": 0.58, "AWAY": 0.42}, 5,
            kal={"status": "two_sided", "prob": {"HOME": 0.50, "AWAY": 0.50}}, kal_norm=0.50),
        row(3, "nfl", "NCAA", "Alabama", "Auburn", 7, {"HOME": 0.70, "AWAY": 0.30}, 2,
            kal={"status": "two_sided", "prob": {"HOME": 0.60, "AWAY": 0.40}}, kal_norm=0.60),
        row(4, "soccer", "PL", "Arsenal", "Chelsea", 9, {"HOME": 0.48, "DRAW": 0.27, "AWAY": 0.25}, 8,
            model={"top_pick": "HOME", "top_pick_prob": 0.55, "tier": "lean"}, edge=7.0, tier="lean"),
    ],
}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-window-")
    card_path, bad_path = os.path.join(tmp, "window_24h.json"), os.path.join(tmp, "not_a_card.json")
    with open(card_path, "w") as f:
        json.dump(CARD, f)
    with open(bad_path, "w") as f:
        json.dump({"predictions": []}, f)

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
        page.click("#tabNext")
        check("tab switch: Next 24h shown, Desk + Ledger hidden",
              page.is_visible("#nextView") and not page.is_visible("#deskView")
              and not page.is_visible("#ledgerView"))
        page.set_input_files("#windowFile", bad_path)
        page.wait_for_function("document.getElementById('nextSummary').textContent.includes('Could not read')")
        check("non-card JSON refused with a message", "not a window card" in page.inner_text("#nextSummary"))
        page.set_input_files("#windowFile", card_path)
        page.wait_for_function("!document.getElementById('nextTable').hidden")
        rows = page.eval_on_selector_all("#nextTable tbody tr",
                                         "trs => trs.map(t => [...t.children].map(td => td.innerText))")
        check("4 rows in card order", [r[2] for r in rows] == [
            "Buffalo Bills @ Kansas City Chiefs", "Toronto Maple Leafs @ Boston Bruins",
            "Auburn @ Alabama", "Chelsea @ Arsenal"], str([r[2] for r in rows]))
        nfl, nhl, ncaa, pl = rows
        check("NFL model row: model 77.0%, book fair 62.0%, Kalshi H 45.0%, edge +15.0pp",
              nfl[3] == "HOME 77.0%" and nfl[4] == "62.0%" and nfl[5] == "H 45.0%" and nfl[6] == "+15.0pp",
              str(nfl))
        check("NFL flags: QUARANTINE · STALE-BOOK?", nfl[8] == "QUARANTINE · STALE-BOOK?", nfl[8])
        check("NFL engine stays model_edge (charter: model sports never venue)", nfl[9] == "model_edge")
        check("NHL market-only pair >= 4 books, >= 5pp: VENUE 0.25u (shadow) via venueEdge()",
              nhl[9] == "VENUE 0.25u (shadow)", nhl[9])
        check("NCAA thin pair (2 books) stays market-only", ncaa[9] == "market-only", ncaa[9])
        check("PL model row: tier lean, edge +7.0pp, no flags",
              pl[7] == "lean" and pl[6] == "+7.0pp" and pl[8] == "—", str(pl))
        summ = page.inner_text("#nextSummary")
        check("summary carries counts", "4 games" in summ and "quarantined 1" in summ
              and "STALE-BOOK? 1" in summ, summ)
        page.click("#tabDesk")
        check("back to Desk: Next 24h hidden", page.is_visible("#deskView") and not page.is_visible("#nextView"))
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed")
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
