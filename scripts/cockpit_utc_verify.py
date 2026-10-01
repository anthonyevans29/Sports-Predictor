"""
Cockpit KICKOFF PARSING headless verification (#178, 2026-10-01). Exports
write utc_date as NAIVE UTC; the Cockpit must read it as UTC in EVERY browser
timezone. Runs the same SYNTHETIC files under UTC, America/New_York,
America/Los_Angeles and Asia/Tokyo and checks, per timezone:
- ledger capture window: a game that kicked off 2h ago is NOT captured, a
  game 30 min ahead IS (snapshotCalls / lastCapture.started);
- Kalshi-only reference: kickoff 30 min ahead = inside [T-60, T) -> eligible
  (PLAY 0.5u); kickoff 3h ahead -> "before T-60"; kickoff 30 min ago ->
  never a reference ("in-play");
- venue engine: a market-only fixture that kicked off 1h ago -> "in-play — never";
- koLine prints the kickoff and T-60 on the VIEWER's local clock.

    python3 scripts/cockpit_utc_verify.py [path/to/cockpit.html]

Writes nothing to the repo; no DB. Needs Playwright + Chromium.
"""
import functools
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
TZS = ("UTC", "America/New_York", "America/Los_Angeles", "Asia/Tokyo")
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def naive(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")          # what export.py writes: isoformat() of naive UTC


def row(home, away, p_home, *, when, fair_h=None, bid=None, ask=None):
    mk = {"bookmaker_count": 9 if fair_h is not None else 0}
    if fair_h is not None:
        mk["fair_prob"] = {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}
    return {"home_team": home, "away_team": away, "utc_date": naive(when), "competition": "MLB",
            "stage": "regular", "prediction": {"probabilities": {"home_win": p_home, "draw": None,
                                                                 "away_win": round(1 - p_home, 4)}, "tier": "lean"},
            "market": mk, "kalshi_bid": bid, "kalshi_ask": ask,
            "input_quality": {"book_odds": mk["bookmaker_count"]}}


SOON, AGO = NOW + timedelta(minutes=30), NOW - timedelta(hours=2)
MLB = {"sport": "mlb", "rehearsal": False, "predictions": [
    row("New York Yankees", "Boston Red Sox", 0.65, when=SOON, fair_h=0.56),           # books, ahead: captured
    row("Los Angeles Dodgers", "San Francisco Giants", 0.65, when=AGO, fair_h=0.56),   # books, started: refused
    row("Atlanta Braves", "Miami Marlins", 0.65, when=SOON, bid=0.55, ask=0.57),       # kalshi-only eligible
    row("Houston Astros", "Texas Rangers", 0.65, when=NOW + timedelta(hours=3), bid=0.55, ask=0.57),
    row("Seattle Mariners", "Oakland Athletics", 0.65, when=NOW - timedelta(minutes=30), bid=0.55, ask=0.57),
]}
FIX = {"competition_code": "NHL", "sport": "nhl", "contains_predictions": False, "fixtures": [
    {"home_team": "Boston Bruins", "away_team": "Toronto Maple Leafs", "status": "scheduled",
     "utc_date": naive(NOW - timedelta(hours=1)),
     "market": {"bookmaker_count": 9, "fair_prob": {"HOME": 0.60, "AWAY": 0.40}},
     "kalshi": {"status": "two_sided", "prob": {"HOME": 0.50, "AWAY": 0.50}}},
]}


def run_tz(browser, url, files, tz):
    print(f"\n[{tz}]")
    ctx = browser.new_context(timezone_id=tz)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.evaluate("localStorage.clear()")
    page.goto(url)
    page.set_input_files("#predFile", files)
    page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
    page.click("#tabDesk")
    calls = {c["home"]: c for c in page.evaluate(
        "deskCalls.map(x=>({home:x.r.home,call:x.call,units:x.units,ko:x.kalOnly,pk:x.passKind}))")}
    reason = lambda name: page.evaluate(f"""(()=>{{const tr=Array.from(document.querySelectorAll('#slate tbody tr'))
        .find(tr=>tr.children[0].textContent.includes({json.dumps(name)})); return tr?tr.children[7].textContent:null}})()""")
    cap = page.evaluate("""(()=>{const c=snapshotCalls(); return {homes:c.map(x=>x.home), started:lastCapture.started}})()""")
    check("capture: 30-min-ahead game captured, 2h-ago game refused as started",
          "New York Yankees" in cap["homes"] and "Los Angeles Dodgers" not in cap["homes"] and cap["started"] >= 1,
          json.dumps(cap))
    at = calls["Atlanta Braves"]
    check("kalshi-only: kickoff +30 min is inside [T-60, T) → PLAY 0.5u", at["call"] == "PLAY" and at["ko"]
          and at["units"] == 0.5, json.dumps(at))
    check("kalshi-only: kickoff +3h → 'before T-60'", "before T-60" in (reason("Houston Astros") or ""),
          reason("Houston Astros"))
    se = calls["Seattle Mariners"]
    check("kalshi-only: kickoff −30 min → never a reference (in-play)", not se["ko"] and se["call"] == "PASS"
          and "in-play" in (reason("Seattle Mariners") or ""), reason("Seattle Mariners"))
    venue = page.evaluate("deskVenue.map(x=>[x.r.home,x.v.reason])")
    vb = dict(venue).get("Boston Bruins")
    check("venue: fixture kicked off 1h ago → 'in-play — never'", vb == "in-play — never", str(vb))
    loc = SOON.astimezone(ZoneInfo(tz))
    want = f"KO {loc:%H:%M} · re-run by {(loc - timedelta(minutes=60)):%H:%M}"
    ko = page.evaluate("""(()=>{const tr=Array.from(document.querySelectorAll('#slate tbody tr'))
        .find(tr=>tr.children[0].textContent.includes('New York Yankees')); return tr.querySelector('.ko').textContent})()""")
    check(f"koLine on the local clock: '{want}'", ko == want, ko)
    check("no page errors", not errors, "; ".join(errors))
    ctx.close()


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "tools", "cockpit.html")
    tmp = tempfile.mkdtemp(prefix="cockpit-utc-")
    shutil.copy(src, os.path.join(tmp, "cockpit.html"))
    files = []
    for n, d in {"mlb.json": MLB, "fixtures.json": FIX}.items():
        files.append(os.path.join(tmp, n))
        with open(files[-1], "w") as f:
            json.dump(d, f)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=tmp))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html"
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        for tz in TZS:
            run_tz(browser, url, files, tz)
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
