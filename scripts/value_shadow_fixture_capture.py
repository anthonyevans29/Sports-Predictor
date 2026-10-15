"""
VALUE-SHADOW LEDGER FIXTURE CAPTURE (ARCHITECT 2026-10-15, addendum 79 item 2: "tests on a kept ledger shape").

No real ledger export is kept anywhere the repo can read (the ledger lives in the operator's browser; exports/ is
gitignored). So the test fixture is written by the Cockpit's OWN code: this script drives tools/cockpit.html in
headless Chromium over synthetic desk files, logs the value shadows the files carry (auto-claim on load, then
"Re-log at T-60"), grades them from synthetic results files, and saves JSON.stringify(loadLedger(), null, 1): the
exact text the "Export ledger (JSON)" button downloads (bd_ledger_v1_<date>.json).

The ledger it writes: five value shadows, all kickoff 2091-10-16 18:00 UTC (fixed, and in the future: the Cockpit
captures a call only before kickoff):
  NFL  Philadelphia Eagles @ Chicago Bears   value HOME (dog)  · CHI 27-7   · won  · a close in the results file
  NFL  Dallas Cowboys @ New York Giants      value AWAY (dog)  · NYG 24-10  · lost · no close
  NFL  Los Angeles Rams @ Seattle Seahawks   value HOME (dog)  · 20-20      · push (a two-way tie) · a close
  NFL  Minnesota Vikings @ Green Bay Packers value HOME (dog)  · no result  · ungraded
  PL   Chelsea @ Arsenal                     value DRAW        · 1-1        · won  · a close
plus the real calls the same files make (the Buffalo straight, the top picks' PASSes are not logged).
The desk files are annotated as scripts/cockpit_desk_files.upload does by default, under desk_policy.base_v11()
(the frozen pre-addendum policy the Cockpit verifies use): the five value shadows read the same either way; only the
Buffalo straight's units would differ under today's rules.

    python3 scripts/value_shadow_fixture_capture.py [--out tests/fixtures/value_shadow/bd_ledger_v1_cockpit.json]

Writes only --out. No DB. Needs Playwright + Chromium.
"""
import argparse
import functools
import http.server
import json
import os
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cockpit_desk_files as cdf  # noqa: E402  (F1c: the Cockpit renders desk files only)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tests", "fixtures", "value_shadow", "bd_ledger_v1_cockpit.json")
D1 = "2091-10-16T18:00:00"     # a fixed kickoff in the future: re-running the capture reproduces the kept dates (Codex on
#                              #545); the Cockpit captures a call only before its kickoff


def nfl(home, away, p_home, fair_home):
    return {"home_team": home, "away_team": away, "utc_date": D1,
            "prediction": {"home_win_prob": p_home, "away_win_prob": round(1 - p_home, 4), "tier": "lean"},
            "market": {"bookmaker_count": 7, "fair_prob": {"HOME": fair_home, "AWAY": round(1 - fair_home, 4)}},
            "market_divergence_pp": round((p_home - fair_home) * 100, 1), "quarantine": False,
            "input_quality": {"book_odds": 7, "injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}}


NFL_DOC = {"sport": "nfl", "rehearsal": False, "predictions": [
    nfl("Chicago Bears", "Philadelphia Eagles", 0.489, 0.355),     # value on the home dog (+13.4pp)
    nfl("New York Giants", "Dallas Cowboys", 0.70, 0.78),          # value on the away dog (+8.0pp)
    nfl("Seattle Seahawks", "Los Angeles Rams", 0.47, 0.40),       # value on the home dog (+7.0pp)
    nfl("Green Bay Packers", "Minnesota Vikings", 0.45, 0.38),     # value on the home dog (+7.0pp), never graded
    nfl("Buffalo Bills", "Miami Dolphins", 0.66, 0.60),            # the top pick carries the edge: a real PLAY
]}
SOCCER_DOC = {"sport": "soccer", "rehearsal": False, "predictions": [
    {"home_team": "Arsenal", "away_team": "Chelsea", "utc_date": D1,
     "prediction": {"probabilities": {"home_win": 0.45, "draw": 0.33, "away_win": 0.22}},
     "market": {"bookmaker_count": 9, "fair_prob": {"HOME": 0.47, "DRAW": 0.27, "AWAY": 0.26}}},
]}


def result(home, away, hs, as_, close=None):
    r = {"home_team": home, "away_team": away, "date": D1[:10], "actual": {"home_score": hs, "away_score": as_}}
    if close:
        r["graded"] = {"close_fair": close, "close_at": D1, "close_source": "close_1x2"}
    return r


NFL_RESULTS = {"sport": "nfl", "results": [
    result("Chicago Bears", "Philadelphia Eagles", 27, 7, {"HOME": 0.372, "AWAY": 0.628}),
    result("New York Giants", "Dallas Cowboys", 24, 10),
    result("Seattle Seahawks", "Los Angeles Rams", 20, 20, {"HOME": 0.415, "AWAY": 0.585}),
    result("Buffalo Bills", "Miami Dolphins", 20, 17, {"HOME": 0.61, "AWAY": 0.39})]}
SOCCER_RESULTS = {"sport": "soccer", "results": [
    result("Arsenal", "Chelsea", 1, 1, {"HOME": 0.46, "DRAW": 0.28, "AWAY": 0.26})]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="write a value-shadow ledger fixture through the Cockpit's own code")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    tmp = tempfile.mkdtemp(prefix="cockpit-vs-fixture-")
    files = {"nfl.json": NFL_DOC, "soccer.json": SOCCER_DOC, "nfl_results.json": NFL_RESULTS,
             "soccer_results.json": SOCCER_RESULTS}
    for n, d in files.items():
        with open(os.path.join(tmp, n), "w") as f:
            json.dump(d, f)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.join(ROOT, "tools")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errors = []
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html")
        for name in ("nfl.json", "soccer.json"):
            page.evaluate("document.getElementById('summary').textContent=''")
            cdf.upload(page, os.path.join(tmp, name))
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
            page.click("#tabDesk")
            page.click("#logBtn")
        page.click("#tabLedger")
        for name in ("nfl_results.json", "soccer_results.json"):
            page.evaluate("document.getElementById('ledgerNote').textContent=''")
            page.set_input_files("#resultsFile", os.path.join(tmp, name))
            page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('graded')")
        text = page.evaluate("JSON.stringify(loadLedger(),null,1)")      # what "Export ledger (JSON)" downloads
        browser.close()
    srv.shutdown()
    if errors:
        print("page errors: " + "; ".join(errors))
        return 1
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        f.write(text)
    calls = json.loads(text)["calls"]
    vs = [c for c in calls if c.get("call_type") == "value_shadow"]
    print(f"wrote {a.out}: {len(calls)} calls, {len(vs)} value shadows "
          f"({sum(1 for c in vs if c.get('result'))} graded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
