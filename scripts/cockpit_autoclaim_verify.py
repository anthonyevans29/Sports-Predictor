"""
Cockpit AUTO-CLAIM headless verification (ARCHITECT 2026-10-03): "loading a
--desk file into the Cockpit logs its PLAY/VENUE/shadow calls as claims
automatically, idempotent on (match, pick, desk_meta.as_of); "Log today's
calls" becomes "re-log at T-60" only. The claim is the file's call at the
file's as_of — no human step. Receipt: the two Braves PLAYs and Thursday's VT
VENUE call would have been claimed."

Over SYNTHETIC desk files annotated by the Python Desk at their own as_of:
- the receipt cases: two Braves PLAYs from a file made BEFORE first pitch (one
  game already started when the file is loaded) and Thursday's Pitt@VT VENUE
  call from Thursday's NCAA file — all claimed, claim_at = the file's as_of;
- a PASS row and a row already started at as_of are not claimed;
- reloading the same file claims nothing (idempotent on match, pick, as_of);
- a NEWER file reprices (claim frozen); an OLDER file never reprices;
- the button reads "Re-log at T-60".

    python3 scripts/cockpit_autoclaim_verify.py

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
NOW = datetime.now(timezone.utc).replace(microsecond=0)
ISO = lambda dt: dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")  # noqa: E731
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def mlb(home, away, p_home, fair_h, when):
    return {"home_team": home, "away_team": away, "utc_date": ISO(when), "stage": "regular",
            "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                           "tier": "lean"},
            "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}},
            "input_quality": {"book_odds": 9}}


def ncaa(home, away, fair_h, kal_h, when, cap):
    return {"home_team": home, "away_team": away, "utc_date": ISO(when), "status": "scheduled",
            "market": {"bookmaker_count": 6, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)},
                       "fair_source": "1X2", "captured_at": ISO(cap)},
            "kalshi": {"status": "two_sided", "prob": {"HOME": kal_h, "AWAY": round(1 - kal_h, 4)}},
            "input_quality": {"book_odds": 6, "kalshi": "two_sided"}}


G1, G2 = NOW - timedelta(hours=2), NOW + timedelta(hours=20)          # Braves: G1 already started at load
AS_OF = NOW - timedelta(hours=5)                                       # the morning file, before first pitch
THU_KO, THU_AS_OF = NOW - timedelta(hours=30), NOW - timedelta(hours=33)


def mlb_doc(padres_fair):
    return {"sport": "mlb", "rehearsal": False, "predictions": [
        mlb("Atlanta Braves", "San Diego Padres", 0.62, 0.55, G1),                  # PLAY (started at load)
        mlb("San Diego Padres", "Atlanta Braves", 0.38, padres_fair, G2),           # PLAY on the Braves (away)
        mlb("New York Mets", "Miami Marlins", 0.52, 0.51, G2),                      # PASS
        mlb("Chicago Cubs", "St. Louis Cardinals", 0.66, 0.55, AS_OF - timedelta(hours=1))]}   # started at as_of


NCAA = {"competition_code": "NCAA", "contains_predictions": False, "fixtures": [
    ncaa("Virginia Tech", "Pittsburgh", 0.60, 0.536, THU_KO, THU_AS_OF - timedelta(minutes=30))]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-autoclaim-")
    files = {}
    for name, doc, at in (("mlb_morning.json", mlb_doc(0.45), AS_OF), ("ncaa_thu.json", NCAA, THU_AS_OF),
                          ("mlb_t60.json", mlb_doc(0.44), NOW - timedelta(hours=1)),
                          ("mlb_older.json", mlb_doc(0.47), AS_OF - timedelta(hours=2))):
        d = cdf.desk_files({name: doc}, at, parlays=False)[name]
        files[name] = os.path.join(tmp, name)
        with open(files[name], "w") as f:
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
        ledger = lambda: page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1')||'{\"calls\":[]}').calls")  # noqa: E731

        def load(name):
            page.evaluate("document.getElementById('summary').textContent=''")
            page.set_input_files("#predFile", files[name])
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
            return page.inner_text("#logNote")

        print("RECEIPT: the two Braves PLAYs (morning file, before first pitch)")
        note = load("mlb_morning.json")
        calls = ledger()
        braves = sorted((c["game"], c["pick"], c["claim_source"], c["claim_at"][:19]) for c in calls
                        if "Braves" in c["game"])
        check("both Braves PLAYs claimed with no click — G1 too, though it started before the load",
              len(braves) == 2 and all(b[2] == "auto" for b in braves), json.dumps(braves))
        check("claim_at = the file's as_of (the claim is the file's call at the file's as_of)",
              all(b[3] == ISO(AS_OF) for b in braves), json.dumps([b[3] for b in braves]))
        check("PASS row and the row already started at as_of are not claimed",
              not any("Mets" in c["game"] or "Cubs" in c["game"] for c in calls), json.dumps([c["game"] for c in calls]))
        check("note reports the auto-claim", note.startswith("Auto-claimed 2 call(s)") and "1 past kickoff" in note, note)

        print("RECEIPT: Thursday's Pitt@VT VENUE call (Thursday's NCAA file)")
        load("ncaa_thu.json")
        vt = [c for c in ledger() if "Virginia Tech" in c["game"]]
        check("VT VENUE claimed (venue_edge, 0.25u, Thursday's as_of)",
              len(vt) == 1 and vt[0]["engine"] == "venue_edge" and vt[0]["units"] == 0.25
              and vt[0]["claim_at"][:19] == ISO(THU_AS_OF), json.dumps(vt[0] if vt else None))

        print("IDEMPOTENT / NEWER / OLDER")
        n0 = len(ledger())
        note = load("mlb_morning.json")
        check("reloading the same file claims nothing", len(ledger()) == n0 and "Auto-claimed 0 call(s)" in note
              and "2 already claimed from this file" in note, note)
        load("mlb_t60.json")
        g2 = next(c for c in ledger() if c["kickoff"] == ISO(G2) and "Braves" in c["game"])
        check("a NEWER file reprices: claim frozen at the morning price (0.55), execution follows (0.56)",
              g2["claim_market_p"] == 0.55 and g2["exec_market_p"] == 0.56 and g2["claim_at"][:19] == ISO(AS_OF),
              json.dumps({k: g2.get(k) for k in ("claim_at", "claim_market_p", "exec_market_p", "executed_at")}))
        before = {c["id"]: (c.get("executed_at"), c.get("exec_market_p")) for c in ledger()}
        note = load("mlb_older.json")
        allc = ledger()
        after = {c["id"]: (c.get("executed_at"), c.get("exec_market_p")) for c in allc if c["id"] in before}
        check("an OLDER file never reprices an existing position", before == after and "older than the ledger" in note,
              note)
        check("...but claims what it alone made before kickoff (the Cubs row: started only after its as_of)",
              [c["game"] for c in allc if c["id"] not in before] == ["St. Louis Cardinals @ Chicago Cubs"],
              json.dumps([c["game"] for c in allc if c["id"] not in before]))

        print("BUTTON")
        check("the button reads 'Re-log at T-60'", page.inner_text("#logBtn") == "Re-log at T-60",
              page.inner_text("#logBtn"))
        check("no page errors", not errors, "; ".join(errors[:3]))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
