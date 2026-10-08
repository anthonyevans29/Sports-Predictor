"""
Cockpit INTL headless verification (ARCHITECT 2026-10-07, INTL DESK POLICY v0; Codex on #325).

Over a SYNTHETIC intl production file (sport "intl", annotated by the Python Desk):
- a quarantined INTL row (|div| >= 15pp, qNever) is logged as a quarantine SHADOW (units 0), as NFL's are;
- a clearing UNL row is logged as a straight at HALF units (fewer than 30 INTL graded);
- a CNL row is never a call (PASS no_series) and logs nothing;
- the ledger summary carries intl_graded, which the Python Desk reads;
- (ARCHITECT 2026-10-07 addendum 3, item C) a fixtures file's score, which includes extra time, never grades an
  INTL call; the INTL results file (90-minute score) does; a game it lists as ungraded stays open.

    python3 scripts/cockpit_intl_verify.py

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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.walters.venue import kalshi_exec  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
K = (datetime.now(timezone.utc) + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S")
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def row(home, comp, p, fair):
    div = round((p[0] - fair[0]) * 100, 1)
    r = {"match_id": hash(home) % 10**6, "home_team": home, "away_team": f"{home} B", "utc_date": K,
         "competition": comp, "venue_flag": "home",
         "prediction": {"probabilities": {"home_win": p[0], "draw": p[1], "away_win": p[2]}, "tier": None},
         "market": {"bookmaker_count": 8, "fair_prob": {"HOME": fair[0], "DRAW": fair[1], "AWAY": fair[2]},
                    "fair_source": "1X2"},
         "market_divergence_pp": div, "quarantine": abs(div) >= 15}
    r.update(kalshi_exec(0.49, 0.50, "UNL", two_way=False))
    return r


DOC = {"sport": "intl", "engine": "model_edge", "model_version": "intl_elo_v2", "predictions": [
    row("Probeland", "UNL", (0.60, 0.22, 0.18), (0.54, 0.26, 0.20)),       # +6pp -> PLAY, half units
    row("Quarantia", "UNL", (0.70, 0.17, 0.13), (0.50, 0.28, 0.22)),       # +20pp -> quarantine shadow
    row("Concacafia", "CNL", (0.60, 0.22, 0.18), (0.54, 0.26, 0.20)),      # CNL -> no call
]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-intl-")
    with open(os.path.join(tmp, "intl_predictions.json"), "w") as f:
        json.dump(DOC, f)

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
        cdf.upload(page, [os.path.join(tmp, "intl_predictions.json")], parlays=False, base=False)
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        page.click("#tabDesk")
        page.click("#logBtn")
        L = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        calls = [c for c in L["calls"] if c.get("sport") == "INTL"]
        by = {c["home"]: c for c in calls}
        q = by.get("Quarantia")
        check("INTL quarantine logged as a shadow (units 0), as NFL's are",
              q is not None and q["call_type"] == "quarantine_shadow" and q["units"] == 0 and q["shadow_units"] > 0,
              json.dumps(q)[:160] if q else "absent")
        p = by.get("Probeland")
        check("clearing UNL row logged as a straight at half units (0/30 graded)",
              p is not None and p["call_type"] == "straight" and p["units"] == 0.5, json.dumps(p)[:160] if p else "absent")
        check("CNL row logs nothing (prediction without a call)", "Concacafia" not in by, str(sorted(by)))
        s = page.evaluate("ledgerSummary()")
        check("ledger summary carries intl_graded", s["counts"].get("intl_graded") == 0, json.dumps(s["counts"]))
        # ARCHITECT 2026-10-07 addendum 3, item C: graded on the 90-MINUTE result only. A UNL fixtures file whose
        # score includes extra time (2-1 AET) must NOT grade the INTL call; the INTL results file (1-1 at 90') does,
        # and a 90-minute draw loses a HOME pick (three-way).
        fx = {"competition_code": "UNL", "fixtures": [{"home_team": "Probeland", "away_team": "Probeland B",
              "utc_date": K, "status": "finished", "home_score": 2, "away_score": 1}]}
        res = {"sport": "intl", "results": [{"home_team": "Probeland", "away_team": "Probeland B", "utc_date": K,
               "predicted": {"top_pick": "home_win"},
               "actual": {"home_score": 1, "away_score": 1, "result": "D", "score_basis": "score_90",
                          "status_raw": "AET", "after_extra_time": {"home_score": 2, "away_score": 1}},
               "graded": {}}],
               "ungraded": [{"home_team": "Quarantia", "away_team": "Quarantia B", "utc_date": K,
                             "reason": "went beyond 90 minutes (PEN) and no 90-minute score is stored"}]}
        for name, d in (("unl_fixtures.json", fx), ("intl_results.json", res)):
            with open(os.path.join(tmp, name), "w") as f:
                json.dump(d, f)
        page.set_input_files("#resultsFile", [os.path.join(tmp, "unl_fixtures.json")])
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('finished results read')")
        L = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        p = {c["home"]: c for c in L["calls"] if c.get("sport") == "INTL"}.get("Probeland")
        check("a fixtures file's (extra-time) score never grades an INTL call",
              p is not None and p["status"] == "open" and not p.get("result"), json.dumps(p)[:160] if p else "absent")
        page.evaluate("document.getElementById('ledgerNote').textContent=''")
        page.set_input_files("#resultsFile", [os.path.join(tmp, "intl_results.json")])
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('finished results read')")
        L = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        by = {c["home"]: c for c in L["calls"] if c.get("sport") == "INTL"}
        p, q = by.get("Probeland"), by.get("Quarantia")
        check("the INTL results file grades on the 90-minute score (1-1: a HOME pick loses)",
              p is not None and p["status"] == "graded" and p["result"] == "loss", json.dumps(p)[:200] if p else "absent")
        check("a listed-ungraded INTL game stays open", q is not None and q["status"] == "open",
              json.dumps(q)[:160] if q else "absent")
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
