"""
Cockpit KALSHI-ONLY PROVISIONAL REFERENCE headless verification (policy v1.1
addendum, RULED architect 2026-10-01). Checks, over SYNTHETIC files:
- model sport, books ABSENT, inside T-60, Kalshi two-sided with spread <= 2c,
  series in the ruled fee table -> the Kalshi MID is the market reference,
  the row is flagged "kalshi-only" and plays at 0.5 x units (a REAL call);
- an AWAY pick is referenced at 1 - mid;
- before T-60, spread > 2c, Kalshi one-sided, a 3-way board: no reference
  (PASS "no reference", the reason names why);
- a measured edge below the floor on the Kalshi mid is "below floor";
- the multiplier composes with the postseason half (0.5 x 0.5 = 0.25u);
- rows with books are untouched (1u, reference books);
- pre-gate sports (NHL) are untouched;
- no value shadow is derived on a kalshi-only row (value-side unchanged);
- the ledger records reference="kalshi_only" and market_p = the mid;
- the policy card shows "graded n/30" for kalshi-only calls.

    python3 scripts/cockpit_kalshi_only_verify.py

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
import cockpit_desk_files as cdf  # noqa: E402  (F1c: the Cockpit renders desk files only)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.now(timezone.utc).replace(microsecond=0)
SOON = (NOW + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")       # inside T-60
LATER = (NOW + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")         # before T-60
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def row(home, away, p_home, *, comp="MLB", fair_h=None, bid=None, ask=None, when=SOON, stage="regular",
        draw=None):
    mk = {"bookmaker_count": 9 if fair_h is not None else 0}
    if fair_h is not None:
        mk["fair_prob"] = {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}
    probs = {"home_win": p_home, "draw": draw, "away_win": round(1 - p_home - (draw or 0), 4)}
    return {"home_team": home, "away_team": away, "utc_date": when, "competition": comp, "stage": stage,
            "prediction": {"probabilities": probs, "tier": "lean"}, "market": mk,
            "kalshi_bid": bid, "kalshi_ask": ask, "input_quality": {"book_odds": mk["bookmaker_count"]}}


MLB = {"sport": "mlb", "rehearsal": False, "predictions": [
    row("New York Yankees", "Boston Red Sox", 0.65, bid=0.55, ask=0.57),                 # mid .56, 9pp -> 0.5u
    row("San Diego Padres", "Chicago Cubs", 0.35, bid=0.44, ask=0.46),                   # AWAY .65 vs .55 -> 0.5u
    row("Atlanta Braves", "Miami Marlins", 0.65, bid=0.55, ask=0.57, when=LATER),        # before T-60 -> no ref
    row("Houston Astros", "Texas Rangers", 0.65, bid=0.54, ask=0.57),                    # spread 3c -> no ref
    row("Seattle Mariners", "Oakland Athletics", 0.65, bid=None, ask=0.57),              # one-sided -> no ref
    row("Detroit Tigers", "Cleveland Guardians", 0.65, bid=0.62, ask=0.64),              # mid .63, 2pp -> floor
    row("Philadelphia Phillies", "New York Mets", 0.65, bid=0.55, ask=0.57, stage="postseason"),  # 0.25u
    row("Los Angeles Dodgers", "San Francisco Giants", 0.65, fair_h=0.56, bid=0.55, ask=0.57),    # books: 1u
]}
SOCCER = {"sport": "soccer", "rehearsal": False, "predictions": [
    row("Arsenal", "Chelsea", 0.55, comp="PL", bid=0.40, ask=0.41, draw=0.25),           # 3-way -> no ref
]}
NHL = {"sport": "nhl", "rehearsal": False, "predictions": [
    row("Boston Bruins", "Toronto Maple Leafs", 0.65, comp="NHL", bid=0.55, ask=0.57),   # pre-gate: untouched
]}


def seeded(n, mlb=2):
    """n graded NFL kalshi-only calls, plus `mlb` graded MLB ones that no longer count (Q3 K4, ARCHITECT
    2026-10-08: "MLB rows no longer add to the 30-call review count")."""
    return {"meta": {"policy_version": "v1.1"}, "calls": [
        {"log_date": "2026-10-01", "sport": "NFL" if i < n else "MLB", "game": f"A{i} @ H{i}", "home": f"H{i}",
         "away": f"A{i}", "pick": "HOME", "engine": "model_edge", "call_type": "straight", "units": 0.5,
         "status": "graded", "result": "win", "reference": "kalshi_only", "model_p": 0.6, "market_p": 0.55,
         "rules": []}
        for i in range(n + mlb)]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-ko-")
    for n, d in {"mlb.json": MLB, "soccer.json": SOCCER, "nhl.json": NHL}.items():
        with open(os.path.join(tmp, n), "w") as f:
            json.dump(d, f)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.join(ROOT, "tools")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html"
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.evaluate(f"localStorage.setItem('bd_ledger_v1', {json.dumps(json.dumps(seeded(4)))})")
        page.goto(url)
        cdf.upload(page, [os.path.join(tmp, n) for n in ("mlb.json", "soccer.json", "nhl.json")])
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        page.click("#tabDesk")
        calls = {c["home"]: c for c in page.evaluate(
            "deskCalls.map(x=>({home:x.r.home,call:x.call,units:x.units,tags:x.tags,ref:x.mktRef,ko:x.kalOnly,pk:x.passKind}))")}

        def cells(name):
            return page.evaluate(f"""(()=>{{const tr=Array.from(document.querySelectorAll('#slate tbody tr'))
                .find(tr=>!tr.classList.contains('vshadow')&&tr.children[0].textContent.includes({json.dumps(name)}));
                return tr?Array.from(tr.children).map(td=>td.textContent):null}})()""")

        ny = calls["New York Yankees"]
        check("eligible: PLAY at 0.5u, flagged, reference = Kalshi mid .56",
              ny["call"] == "PLAY" and ny["units"] == 0.5 and ny["ko"] and abs(ny["ref"] - 0.56) < 1e-9
              and "kalshi-only half units" in ny["tags"], json.dumps(ny))
        c = cells("New York Yankees")
        check("market cell shows the mid + 'kalshi-only'; reason names bid/ask/spread",
              c[3].startswith("0.560") and "kalshi-only" in c[3]
              and "kalshi-only reference: mid 0.560 (bid 0.55 / ask 0.57, spread 2c)" in c[7], json.dumps(c))
        sd = calls["San Diego Padres"]
        check("AWAY pick referenced at 1 − mid (.55), 0.5u", sd["call"] == "PLAY" and sd["units"] == 0.5
              and abs(sd["ref"] - 0.55) < 1e-9, json.dumps(sd))
        for name, why in (("Atlanta Braves", "before T-60 — books may still post"),
                          ("Houston Astros", "Kalshi spread 3c > 2c"),
                          ("Seattle Mariners", "Kalshi not two-sided"),
                          ("Arsenal", "3-way board")):
            x = calls[name]
            check(f"{name}: PASS no reference, reason '{why}'", x["call"] == "PASS" and x["pk"] == "noref"
                  and not x["ko"] and why in cells(name)[7], cells(name)[7])
        de = calls["Detroit Tigers"]
        check("2pp on the Kalshi mid: PASS below floor (a measured decline)", de["call"] == "PASS"
              and de["pk"] == "floor" and de["ko"], json.dumps(de))
        ph = calls["Philadelphia Phillies"]
        check("postseason × kalshi-only = 0.25u", ph["units"] == 0.25
              and "postseason half units" in ph["tags"] and "kalshi-only half units" in ph["tags"], json.dumps(ph))
        la = calls["Los Angeles Dodgers"]
        check("books present: untouched (1u, no flag)", la["units"] == 1 and not la["ko"], json.dumps(la))
        bo = calls["Boston Bruins"]
        check("NHL pre-gate: untouched PASS, no kalshi-only reference", bo["call"] == "PASS" and not bo["ko"]
              and "kalshi-only" not in cells("Boston Bruins")[7], cells("Boston Bruins")[7])
        vs = page.evaluate("deskValue.map(x=>x.r.home)")
        check("no value shadow on kalshi-only rows (value-side unchanged)",
              not {"New York Yankees", "San Diego Padres", "Philadelphia Phillies"} & set(vs), json.dumps(vs))
        led = page.evaluate("""snapshotCalls().filter(x=>x.call_type==='straight')
            .map(x=>[x.home,x.reference,+x.market_p.toFixed(3),x.units])""")
        led = {h: (r, m, u) for h, r, m, u in led}
        check("ledger: reference=kalshi_only, market_p = mid, real units",
              led.get("New York Yankees") == ("kalshi_only", 0.56, 0.5)
              and led.get("San Diego Padres") == ("kalshi_only", 0.55, 0.5)
              and led.get("Los Angeles Dodgers") == ("books", 0.56, 1), json.dumps(led))
        check("policy card: kalshi-only graded 4/30 (NFL 4; the 2 MLB rows not counted, Q3 K4)", page.inner_text("#koProgress") == "graded 4/30",
              page.inner_text("#koProgress"))
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
