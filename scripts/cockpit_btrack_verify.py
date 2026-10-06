"""
B-TRACK SHADOW headless verification (ARCHITECT 2026-10-01, pre-committed,
shadow until the v1.2 bump): (1) exposure cap 1.25u per team-outcome across
straights + parlay legs; (2) ticket dedup. A SYNTHETIC slate (three 1u Desk
straights that the parlays share), annotated + desk-parlays'd by Python, loaded
into a non-UTC browser. Checks:
- the Desk's parlay card says "B-track shadow (not applied): exposure-capped N
  · deduped N" and marks the would-cut tickets; ALL tickets still render
  (nothing applied);
- Log: the would-cut tickets' legs carry b_shadow_cut, the others don't; the
  slate's counts land in ledger meta (keyed by the file's as_of; a re-log does
  not double-count);
- the P&L block line: "exposure-capped N · deduped N over S/30 slate(s) ·
  would-cut tickets settled n, net ±x u".

    python3 scripts/cockpit_btrack_verify.py

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

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.walters import desk_policy as dp  # noqa: E402

CHECKS = []
NOW = datetime.now(timezone.utc).replace(microsecond=0)
KO = (NOW + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S")


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def row(home, p, fair, comp="MLB"):
    r = {"home_team": home, "away_team": f"{home} Aw", "utc_date": KO, "stage": "regular",
         "prediction": {"probabilities": {"home_win": p, "draw": None, "away_win": round(1 - p, 4)}, "tier": "lean"},
         "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair, "AWAY": round(1 - fair, 4)}}}
    if comp:
        r["competition"] = comp
    return r


def main():
    docs = {"mlb.json": {"sport": "mlb", "predictions": [row("Ahome", 0.62, 0.55), row("Bhome", 0.63, 0.55)]},
            "nfl.json": {"sport": "nfl", "predictions": [row("Chome", 0.64, 0.55, comp=None)]}}
    with dp.base_v11():          # pre-addendum fixture: no exec quotes (#87 v1.1 prices legs at executable cost)
        ann = {n: dp.annotate(json.loads(json.dumps(d)), now=NOW) for n, d in docs.items()}
        par = dp.parlays_doc(list(ann.items()), now=NOW)
    b = par["b_track_shadow"]
    print(f"slate: straights {[p['desk']['units'] for d in ann.values() for p in d['predictions']]} · "
          f"tickets {len(par['tickets'])} · shadow capped {b['exposure_capped']} deduped {b['deduped']}")
    check("Python shadow cuts something on this slate (the cap bites), nothing applied",
          b["exposure_capped"] >= 1 and not b["applied"] and len(par["tickets"]) == 3, json.dumps(b["cuts"])[:200])
    tmp = tempfile.mkdtemp(prefix="cockpit-btrack-")
    shutil.copy(os.path.join(ROOT, "tools", "cockpit.html"), os.path.join(tmp, "cockpit.html"))
    paths = []
    for n, d in {**ann, "desk_parlays.json": par}.items():
        paths.append(os.path.join(tmp, n))
        with open(paths[-1], "w") as f:
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
        page = browser.new_context(timezone_id="America/Chicago").new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.clock.set_fixed_time(NOW)
        page.goto(url)
        page.evaluate("localStorage.clear()")
        page.goto(url)
        page.set_input_files("#predFile", paths)
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        card = page.inner_text("#parlayOut")
        check("parlay card: 'B-track shadow (not applied): exposure-capped N · deduped N'",
              f"B-track shadow (not applied): exposure-capped {b['exposure_capped']} · deduped {b['deduped']}" in card,
              card[:200])
        marks = card.count("B-track shadow: would be")
        check("all 3 tickets still render; the would-cut ones are marked",
              card.count("Ticket ") == 3 and marks == b["exposure_capped"] + b["deduped"], f"marks {marks}")
        page.evaluate("document.getElementById('logBtn').click()")
        L = page.evaluate("loadLedger()")
        legs = [c for c in L["calls"] if c["call_type"] == "parlay_leg"]
        cut_pids = {c["parlay_id"] for c in legs if c.get("b_shadow_cut")}
        want = sum(1 for t in par["tickets"] if t["b_shadow"])
        check("Log: legs of the would-cut tickets carry b_shadow_cut, the others don't",
              len(cut_pids) == want and all((c.get("b_shadow_cut") is not None) == (c["parlay_id"] in cut_pids)
                                            for c in legs), f"{len(cut_pids)} cut ticket(s) of {len({c['parlay_id'] for c in legs})}")
        meta = (L.get("meta") or {}).get("b_shadow") or {}
        asof = par["desk_meta"]["as_of"]
        check("ledger meta: the slate's shadow counts, keyed by the file's as_of",
              list(meta) == [asof] and meta[asof]["capped"] == b["exposure_capped"]
              and meta[asof]["deduped"] == b["deduped"], json.dumps(meta)[:200])
        page.evaluate("document.getElementById('logBtn').click()")                                                    # re-log: no double count
        meta2 = (page.evaluate("loadLedger()").get("meta") or {}).get("b_shadow") or {}
        check("re-log of the same slate does not double-count", len(meta2) == 1, json.dumps(list(meta2)))
        # settle every ticket as a win at its stored legs → the would-cut net is reported
        page.evaluate("""(()=>{const L=loadLedger(); for(const c of L.calls){ if(c.call_type!=="parlay_leg") continue;
            c.status="graded"; c.result="win"; c.ticket_result="win"; c.units_returned=1; c.graded_date="2026-10-01"; }
            saveLedger(L);})()""")
        pnl = page.evaluate("pnlBlock(loadLedger())")
        line = next((ln for ln in pnl.splitlines() if ln.startswith("B-track shadow")), "")
        check("P&L block: 'exposure-capped N · deduped N over 1/30 slate(s) · would-cut tickets settled n, net'",
              f"exposure-capped {b['exposure_capped']} · deduped {b['deduped']} over 1/30 slate(s)" in line
              and f"would-cut tickets settled {want}, net +{want * 0.75:.2f}u" in line, line)
        check("no page errors", not errors, "; ".join(errors[:3]))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
