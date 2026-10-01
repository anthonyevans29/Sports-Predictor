"""
Cockpit POSTSEASON SIZING + KICKOFF headless verification (architect
2026-10-01). Checks, over SYNTHETIC MLB files:
- a PLAY row the export marks stage="postseason" plays at HALF units with the
  reason "postseason → half units until 30 graded (n/30)" and its tag, while
  fewer than 30 postseason calls are graded in the ledger;
- regular-season rows are untouched; stage null is labelled "stage unknown"
  and NOT halved; an older export with no stage key is untouched and unlabelled;
- with 30 graded postseason calls in the ledger the halving lifts;
- the policy card shows "graded n/30" for postseason and for value shadows;
- every Desk row shows "KO HH:MM · re-run by HH:MM" (T-60, local) while
  ahead, "started" after kickoff;
- the correlation note still reads team names (the KO line never leaks in);
- a logged call records its stage.

    python3 scripts/cockpit_postseason_verify.py

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
KICK = (datetime.now(timezone.utc) + timedelta(days=1)).replace(second=0, microsecond=0)
PAST = KICK - timedelta(days=3)
K = KICK.strftime("%Y-%m-%dT%H:%M:%S")
P = PAST.strftime("%Y-%m-%dT%H:%M:%S")
CHECKS = []
ABSENT = object()


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def mlb(home, away, p_home, fair_h, stage=ABSENT, when=K):
    row = {"home_team": home, "away_team": away, "utc_date": when,
           "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                          "tier": "lean"},
           "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}},
           "input_quality": {"book_odds": 9}}
    if stage is not ABSENT:
        row["stage"] = stage
    return row


NEW = {"sport": "mlb", "rehearsal": False, "predictions": [
    mlb("New York Yankees", "Boston Red Sox", 0.62, 0.55, "postseason"),     # 7pp PLAY -> half (postseason)
    mlb("Atlanta Braves", "Miami Marlins", 0.62, 0.55, "regular"),           # 7pp PLAY -> 1u
    mlb("San Diego Padres", "Chicago Cubs", 0.62, 0.55, None),               # stage unknown -> labelled, 1u
    mlb("Houston Astros", "Texas Rangers", 0.62, 0.55, "postseason", P),     # kicked off -> "started"
    mlb("Seattle Mariners", "New York Yankees", 0.62, 0.55, "postseason"),   # Yankees twice -> correlation note
]}
OLD = {"sport": "mlb", "rehearsal": False, "predictions": [
    mlb("Detroit Tigers", "Cleveland Guardians", 0.62, 0.55),                # pre-stage export: untouched
]}


def ledger(n_post, n_value):
    calls = []
    for i in range(n_post):
        calls.append({"log_date": "2026-10-01", "sport": "MLB", "game": f"A{i} @ H{i}", "home": f"H{i}",
                      "away": f"A{i}", "pick": "HOME", "engine": "model_edge", "call_type": "straight",
                      "units": 0.5, "status": "graded", "result": "win", "stage": "postseason",
                      "model_p": 0.6, "market_p": 0.55, "rules": []})
    for i in range(n_value):
        calls.append({"log_date": "2026-10-01", "sport": "NFL", "game": f"V{i} @ W{i}", "home": f"W{i}",
                      "away": f"V{i}", "pick": "AWAY", "engine": "model_edge", "call_type": "value_shadow",
                      "units": 0, "shadow_units": 0.25, "status": "graded", "result": "loss",
                      "model_p": 0.4, "market_p": 0.35, "rules": []})
    return {"meta": {"policy_version": "v1.1"}, "calls": calls}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-post-")
    for n, d in {"mlb_new.json": NEW, "mlb_old.json": OLD}.items():
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

        def open_with(led):
            page.goto(url)
            page.evaluate(f"localStorage.setItem('bd_ledger_v1', {json.dumps(json.dumps(led))})")
            page.goto(url)

        def load(*names):
            page.evaluate("document.getElementById('summary').textContent=''")
            page.set_input_files("#predFile", [os.path.join(tmp, n) for n in names])
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
            page.click("#tabDesk")

        def calls():
            return {c["home"]: c for c in page.evaluate(
                "deskCalls.map(x=>({home:x.r.home,call:x.call,units:x.units,tags:x.tags}))")}

        def cells(name):
            return page.evaluate(f"""(()=>{{const tr=Array.from(document.querySelectorAll('#slate tbody tr'))
                .find(tr=>!tr.classList.contains('vshadow')&&tr.children[0].textContent.includes({json.dumps(name)}));
                return tr?Array.from(tr.children).map(td=>td.textContent):null}})()""")

        print("BELOW 30 GRADED (ledger: 3 postseason, 7 value shadows)")
        open_with(ledger(3, 7))
        load("mlb_new.json", "mlb_old.json")
        c = calls()
        ny = c["New York Yankees"]
        check("postseason PLAY → 0.5u with the tag", ny["call"] == "PLAY" and ny["units"] == 0.5
              and "postseason half units" in ny["tags"], json.dumps(ny))
        check("reason names the counter", "postseason → half units until 30 graded (3/30)" in cells("New York Yankees")[7],
              cells("New York Yankees")[7])
        check("regular season untouched (1u)", c["Atlanta Braves"]["units"] == 1, json.dumps(c["Atlanta Braves"]))
        sd = c["San Diego Padres"]
        check("stage null: 1u, labelled 'stage unknown'", sd["units"] == 1
              and "stage unknown — postseason caution not applied" in cells("San Diego Padres")[7], json.dumps(sd))
        det = c["Detroit Tigers"]
        check("older export (no stage key): 1u, no stage label", det["units"] == 1
              and "stage" not in cells("Detroit Tigers")[7], cells("Detroit Tigers")[7])
        card = page.inner_text("#psProgress") + " | " + page.inner_text("#vsProgress")
        check("policy card: postseason 3/30 · value shadows 7/30", card == "graded 3/30 | graded 7/30", card)
        ko = cells("New York Yankees")[0]
        exp_ko = page.evaluate(f"hm(Date.parse('{K}Z'))")
        exp_rr = page.evaluate(f"hm(Date.parse('{K}Z')-3600e3)")
        check("KO line: kickoff + re-run by T-60 (local)", f"KO {exp_ko} · re-run by {exp_rr}" in ko, ko)
        check("kicked-off row: 'started', no re-run", "· started" in cells("Houston Astros")[0]
              and "re-run by" not in cells("Houston Astros")[0], cells("Houston Astros")[0])
        summ = page.inner_text("#summary")
        check("correlation note reads clean team names", "correlated exposure: New York Yankees×2" in summ, summ)
        logged = page.evaluate("snapshotCalls().filter(x=>x.home==='New York Yankees'&&x.call_type==='straight').map(x=>[x.stage,x.units])")
        check("logged call records stage + halved units", logged == [["postseason", 0.5]], json.dumps(logged))

        print("AT 30 GRADED")
        open_with(ledger(30, 0))
        load("mlb_new.json")
        c = calls()
        check("halving lifts at 30 graded postseason calls", c["New York Yankees"]["units"] == 1
              and "postseason half units" not in c["New York Yankees"]["tags"], json.dumps(c["New York Yankees"]))
        check("policy card: 30/30 — review due", page.inner_text("#psProgress") == "graded 30/30 — review due",
              page.inner_text("#psProgress"))
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
