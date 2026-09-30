"""
Cockpit NHL SHADOW headless verification (architect 2026-09-30).

An engine "model_shadow" export (the FAILED nhl_elo_v1) renders greyed under
"Reference model — failed gate" and can never become a Desk call, a venue
input or a ledger entry. It is loaded beside a live NFL file, then the check
presses "Log today's calls".

    python3 scripts/cockpit_nhl_shadow_verify.py

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
D1 = (datetime.now(timezone.utc) + timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%S")
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


NFL = {"sport": "nfl", "rehearsal": False, "predictions": [
    {"home_team": "Buffalo Bills", "away_team": "Miami Dolphins", "utc_date": D1,
     "prediction": {"home_win_prob": 0.70, "away_win_prob": 0.30, "tier": "lean"},
     "market": {"bookmaker_count": 7, "fair_prob": {"HOME": 0.60, "AWAY": 0.40}},
     "market_divergence_pp": 10.0, "quarantine": False,
     "input_quality": {"book_odds": 7, "injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}}]}
GATE = "FAILED 0.6909 vs 0.6866 (Phase 2 closed 2026-09-25)"


def shadow_row(home, away, p, fair_h):
    return {"match_id": 1, "utc_date": D1, "home_team": home, "away_team": away, "status": "scheduled",
            "engine": "model_shadow", "model_version": "nhl_elo_v1", "gate_verdict": GATE,
            "market": {"bookmaker_count": 6, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}},
            "kalshi": {"status": "two_sided", "prob": {"HOME": 0.40, "AWAY": 0.60}},
            "prediction": {"home_win_prob": p, "away_win_prob": round(1 - p, 4),
                           "top_pick": "home_win" if p >= 0.5 else "away_win",
                           "top_pick_prob": max(p, round(1 - p, 4))}}


SHADOW = {"sport": "nhl", "engine": "model_shadow", "model_version": "nhl_elo_v1", "gate_verdict": GATE,
          "contains_predictions": False, "predictions": [
              shadow_row("Toronto Maple Leafs", "Montreal Canadiens", 0.72, 0.52),   # a +20pp "edge": must stay inert
              shadow_row("Boston Bruins", "New York Rangers", 0.45, 0.50)]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-nhlshadow-")
    for n, d in (("nfl.json", NFL), ("nhl_shadow.json", SHADOW)):
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
        page.set_input_files("#predFile", [os.path.join(tmp, "nfl.json"), os.path.join(tmp, "nhl_shadow.json")])
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        page.click("#tabDesk")
        card = page.evaluate("(()=>{const c=document.getElementById('shadowCard');"
                             "return {hidden:c.hidden,cls:c.className,text:c.innerText}})()")
        check("shadow card shown, greyed (.shadowref), titled 'Reference model — failed gate'",
              not card["hidden"] and "shadowref" in card["cls"] and "Reference model — failed gate" in card["text"])
        check("the card carries the model and the gate verdict", "nhl_elo_v1" in card["text"] and GATE in card["text"])
        check("both shadow games listed", "Montreal Canadiens @ Toronto Maple L" in card["text"]
              and "New York Rangers @ Boston Bruins" in card["text"])
        st = page.evaluate("({rows:rows.map(r=>r.sport),calls:deskCalls.map(c=>JSON.stringify(c)),"
                           "venue:deskVenue.map(v=>JSON.stringify(v)),value:deskValue.map(v=>JSON.stringify(v)),"
                           "shadow:shadowRows.length})")
        check("NHL never enters the Desk rows (policy / venue / ledger input)", st["rows"] == ["NFL"], str(st))
        nhl = ("Toronto", "Montreal", "Bruins", "Rangers")
        check("no NHL Desk call, venue call or value shadow (by game name)",
              len(st["calls"]) >= 1 and not any(t in x for x in st["calls"] + st["venue"] + st["value"] for t in nhl),
              f"calls {len(st['calls'])} · venue {len(st['venue'])} · value {len(st['value'])}")
        slate = page.inner_text("#slate")
        check("the Desk slate shows no NHL game", "Toronto" not in slate and "Boston Bruins" not in slate)
        page.click("#logBtn")
        L = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1')||'{\"calls\":[]}')")
        games = {c["game"] for c in L["calls"]}
        check("'Log today's calls' logs the NFL call and no NHL row",
              any("Buffalo" in g for g in games) and not any("Toronto" in g or "Bruins" in g for g in games), str(games))
        page.set_input_files("#predFile", os.path.join(tmp, "nhl_shadow.json"))
        page.wait_for_timeout(300)
        st2 = page.evaluate("({rows:rows.length,calls:deskCalls.length,shadow:shadowRows.length})")
        check("a shadow file alone: zero Desk rows and calls, the shadow card only",
              st2 == {"rows": 0, "calls": 0, "shadow": 2}, str(st2))
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    ok = all(CHECKS)
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed — {'ALL GREEN' if ok else 'FAILURES ABOVE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
