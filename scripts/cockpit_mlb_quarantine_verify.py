"""
Cockpit MLB BIG-EDGE QUARANTINE headless verification (ARCHITECT 2026-10-07).

Over a SYNTHETIC MLB production file annotated by the Python Desk:
- an MLB row more than 8pp above its book reference is logged as a quarantine SHADOW (units 0, shadow_units at the
  size it would have staked), as NFL's divergence quarantines are, although the export's `quarantine` field is false
  (the Desk's own edge decides);
- a +6pp MLB row is still logged as a straight;
- an NFL divergence quarantine is still logged as a shadow (unchanged);
- Q3 (ARCHITECT 2026-10-08): an MLB row on a kalshi-only reference is PASS "kalshi-only suspended", never logged
  (no shadow units), its hold rendered for the record; an NFL kalshi-only quarantine shadow still records the mid.

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
K45 = (datetime.now(timezone.utc) + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%S")   # inside T-60
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
    row("Moderate", "MLB", 0.61, 0.55),                       # +6pp -> straight
    # no book market, Kalshi two-sided 0.49/0.50 inside T-60: the kalshi-only mid 0.495 is the reference, +10.5pp
    {**row("Kalonly", "MLB", 0.60, 0.5), "utc_date": K45, "market": {"bookmaker_count": 0},
     "kalshi_bid": 0.49, "kalshi_ask": 0.50}]}
NFL = {"sport": "nfl", "rehearsal": False, "predictions": [
    row("Divergent", "NFL", 0.80, 0.55, quarantine=True, market_divergence_pp=25.0,
        input_quality={"injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}),
    # Q3 K4: NFL keeps the kalshi-only reference; a divergence-quarantined row on it is a shadow at the mid
    {**row("NflKalonly", "NFL", 0.60, 0.5, quarantine=True, market_divergence_pp=20.0,
           input_quality={"injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}),
     "utc_date": K45, "market": {"bookmaker_count": 0}, "kalshi_bid": 0.49, "kalshi_ask": 0.50}]}


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
        k = by.get("NflKalonly")
        check("kalshi-only quarantine shadow records the Desk's mid and reference (Codex on #328; NFL since Q3)",
              k is not None and k["call_type"] == "quarantine_shadow" and abs((k.get("market_p") or 0) - 0.495) < 1e-9
              and k.get("reference") == "kalshi_only" and k.get("venue_hint") == "kalshi",
              json.dumps(k)[:220] if k else "absent")
        check("Q3 K1: the MLB kalshi-only row is never logged (no call, no shadow units)", "Kalonly" not in by,
              json.dumps(by.get("Kalonly"))[:160])
        ko = page.evaluate("""[...document.querySelectorAll('#slate tbody tr')].filter(tr=>tr.children[0].dataset.game
            &&tr.children[0].dataset.game.includes('Kalonly @')||tr.textContent.includes('Kalonly B @ Kalonly'))
            .map(tr=>({cls:tr.className,t:tr.textContent}))""")
        kt = ko[0]["t"] if ko else ""
        check("Q3 K1/K3: the slate shows PASS 'kalshi-only suspended', greyed, with the hold for the record",
              bool(ko) and ko[0]["cls"] == "noref" and "PASSkalshi-only suspended" in kt
              and "kalshi-only suspended for MLB: the model number is unblended without books" in kt
              and "hold (record only, not a call): mid 0.495 (bid 0.49 / ask 0.50, spread 1c)" in kt
              and "raw edge +10.5pp · on equal footing +5.2pp" in kt and "the 2026-10-01 rule: PASS 0u" in kt, " ".join(kt.split())[:600] or "absent")
        check("ledger quarantine flag set from the file's Desk call", q is not None and q.get("quarantine") is True,
              str(q.get("quarantine")) if q else "absent")
        page.click("#tabCard") if page.query_selector("#tabCard") else None
        card = page.evaluate("(()=>{renderCard();return [...document.querySelectorAll('.game')].map(g=>({q:g.classList.contains('quar'),t:g.textContent}))})()")
        bg = [c for c in card if "Bigedge" in c["t"]]
        check("Card shows the MLB quarantine (chip + border) from the file's Desk call (Codex on #328)",
              bool(bg) and bg[0]["q"] and "QUARANTINE +11pp" in bg[0]["t"] and "MLB big-edge quarantine" in bg[0]["t"],
              (bg[0]["t"][:200] if bg else f"{len(card)} cards"))
        check("Card's reasoning shows the Desk reason escaped once ('> 8pp', never '&gt;') (Codex on #328)",
              bool(bg) and "pp > 8pp vs the book close" in bg[0]["t"] and "&gt;" not in bg[0]["t"],
              (bg[0]["t"][-240:] if bg else "absent"))
        src = open(os.path.join(ROOT, "tools", "cockpit.html"), encoding="utf-8").read()
        check("Ask prompt states the quarantine per sport (NFL/INTL >=15pp; MLB >8pp, ARCHITECT 2026-10-07)",
              "NFL/INTL divergence >=15pp; MLB edge vs its reference >8pp" in src
              and "quarantine>=15pp never" not in src)
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
