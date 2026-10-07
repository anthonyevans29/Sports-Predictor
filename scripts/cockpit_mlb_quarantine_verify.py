"""
Cockpit MLB BIG-EDGE QUARANTINE headless verification (ARCHITECT 2026-10-07).

Over a SYNTHETIC MLB production file annotated by the Python Desk:
- an MLB row more than 8pp above its book reference is logged as a quarantine SHADOW (units 0, shadow_units at the
  size it would have staked), as NFL's divergence quarantines are, although the export's `quarantine` field is false
  (the Desk's own edge decides);
- a +6pp MLB row is still logged as a straight;
- an NFL divergence quarantine is still logged as a shadow (unchanged).

    python3 scripts/cockpit_mlb_quarantine_verify.py

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
K = (datetime.now(timezone.utc) + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S")
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def row(home, comp, p, fair, **kw):
    r = {"home_team": home, "away_team": f"{home} B", "utc_date": K, "competition": comp, "stage": "regular",
         "prediction": {"probabilities": {"home_win": p, "draw": None, "away_win": round(1 - p, 4)}, "tier": "lean"},
         "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair, "AWAY": round(1 - fair, 4)}},
         "quarantine": False}
    r.update(kw)
    return r


MLB = {"sport": "mlb", "rehearsal": False, "predictions": [
    row("Bigedge", "MLB", 0.66, 0.55),                        # +11pp -> quarantine shadow
    row("Moderate", "MLB", 0.61, 0.55)]}                      # +6pp -> straight
NFL = {"sport": "nfl", "rehearsal": False, "predictions": [
    row("Divergent", "NFL", 0.80, 0.55, quarantine=True, market_divergence_pp=25.0,
        input_quality={"injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}})]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-mlbq-")
    paths = []
    for name, doc in (("mlb_predictions.json", MLB), ("nfl_predictions.json", NFL)):
        paths.append(os.path.join(tmp, name))
        with open(paths[-1], "w") as f:
            json.dump(doc, f)

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
        cdf.upload(page, paths, parlays=False, base=False)
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        page.click("#tabDesk")
        page.click("#logBtn")
        L = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        by = {c["home"]: c for c in L["calls"]}
        q = by.get("Bigedge")
        check("MLB > 8pp logged as a quarantine shadow (units 0, shadow 1u) with the export's quarantine false",
              q is not None and q["call_type"] == "quarantine_shadow" and q["units"] == 0 and q["shadow_units"] == 1,
              json.dumps(q)[:180] if q else "absent")
        m = by.get("Moderate")
        check("MLB +6pp still logged as a straight", m is not None and m["call_type"] == "straight",
              json.dumps(m)[:160] if m else "absent")
        n = by.get("Divergent")
        check("NFL divergence quarantine still logged as a shadow (unchanged)",
              n is not None and n["call_type"] == "quarantine_shadow" and n["units"] == 0,
              json.dumps(n)[:160] if n else "absent")
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
