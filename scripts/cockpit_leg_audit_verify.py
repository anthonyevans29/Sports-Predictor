"""
Cockpit PARLAY-LEG AUDIT headless verification (ARCHITECT 2026-10-01, #183).
Seeds a SYNTHETIC ledger of parlay tickets, loads a SYNTHETIC export of the
legs' day, presses "Audit parlay legs (#183)" and checks:
- a leg whose game was a PASS in the same-day export → leg_check not_play,
  its ticket flagged "leg not a play (#183)" and EXCLUDED from the P&L;
- a ticket whose legs were all plays → kept, marked play;
- a leg whose game is not in the loaded files, or whose export is from a
  different day than the leg's log_date → unchecked (law 4), ticket kept;
- the note and the P&L audit line carry the counts; nothing is deleted:
  every stored field is unchanged except the added leg_check marks.

    python3 scripts/cockpit_leg_audit_verify.py

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
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cockpit_desk_files as cdf  # noqa: E402  (F1c: the Cockpit renders desk files only)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = "America/New_York"
NOW = datetime.now(timezone.utc).replace(microsecond=0)
KO = (NOW + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%S")
TODAY = NOW.astimezone(ZoneInfo(TZ)).strftime("%Y-%m-%d")
OTHER_DAY = (NOW - timedelta(days=3)).astimezone(ZoneInfo(TZ)).strftime("%Y-%m-%d")
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def row(home, p, fair):
    return {"home_team": home, "away_team": f"{home} Aw", "utc_date": KO, "competition": "MLB", "stage": "regular",
            "prediction": {"probabilities": {"home_win": p, "draw": None, "away_win": round(1 - p, 4)}},
            "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair, "AWAY": round(1 - fair, 4)}}}


EXPORT = {"sport": "mlb", "exported_at": NOW.strftime("%Y-%m-%dT%H:%M:%S") + "Z", "predictions": [
    row("Apass", 0.50, 0.49), row("Bplay", 0.65, 0.56), row("Cplay", 0.66, 0.56), row("Dplay", 0.67, 0.56)]}


def leg(pid, home, log_date, n):
    return {"id": f"{pid}-{n}", "log_date": log_date, "sport": "MLB", "game": f"{home} Aw @ {home}", "home": home,
            "away": f"{home} Aw", "kickoff": KO, "pick": "HOME", "engine": "model_edge", "call_type": "parlay_leg",
            "parlay_id": pid, "units": 0.25, "status": "graded", "result": "win", "ticket_result": "win",
            "units_returned": 1.0, "graded_date": TODAY, "tier": "parlay", "rules": ["parlay 0.25u"],
            "captured_at": (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "model_p": 0.6, "market_p": 0.5}


LEDGER = {"meta": {"policy_version": "v1.1"}, "calls": [
    leg("P-T1", "Apass", TODAY, 1), leg("P-T1", "Bplay", TODAY, 2),        # leg A was a PASS → excluded
    leg("P-T2", "Cplay", TODAY, 1), leg("P-T2", "Dplay", TODAY, 2),        # all plays → kept
    leg("P-T3", "Zmissing", TODAY, 1), leg("P-T3", "Ymissing", TODAY, 2),  # not loaded → unchecked
    leg("P-T4", "Apass", OTHER_DAY, 1), leg("P-T4", "Xother", OTHER_DAY, 2),   # other day → unchecked
]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-legs-")
    path = os.path.join(tmp, "mlb.json")
    with open(path, "w") as f:
        json.dump(EXPORT, f)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.join(ROOT, "tools")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html"
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        page = browser.new_context(timezone_id=TZ).new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.evaluate(f"localStorage.setItem('bd_ledger_v1', {json.dumps(json.dumps(LEDGER))})")
        page.goto(url)
        page.click("#tabLedger")
        page.click("#legAuditBtn")
        check("no files loaded → refuses, asks for the day's exports",
              "Load the export files" in page.inner_text("#ledgerNote"), page.inner_text("#ledgerNote"))
        before = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1')).calls")
        cdf.upload(page, [path])
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        plays = page.evaluate("deskCalls.map(x=>[x.r.home,x.call])")
        check("the loaded export: Apass PASS, the others PLAY", dict(plays) == {
            "Apass": "PASS", "Bplay": "PLAY", "Cplay": "PLAY", "Dplay": "PLAY"}, json.dumps(plays))
        page.click("#tabLedger")
        page.click("#legAuditBtn")
        note = page.inner_text("#ledgerNote")
        # AUTO-CLAIM (2026-10-03, tickets included): the load also claimed the file's tickets, whose
        # legs the audit checks too (all PLAYs): 4 seeded + the auto-claimed legs.
        n_auto = page.evaluate("""JSON.parse(localStorage.getItem('bd_ledger_v1')).calls
            .filter(c=>c.call_type==='parlay_leg'&&c.claim_source==='auto').length""")
        check("note: 4 seeded + auto-claimed legs checked · 1 not a play → 1 ticket excluded · 4 unchecked",
              f"{4 + n_auto} leg(s) checked" in note and "1 leg not a play (#183) → 1 ticket(s) excluded" in note
              and "4 unchecked" in note and "never deleted" in note, note)
        # AUTO-CLAIM (2026-10-03): loading the export also claims its PLAYs (the file's
        # call at its as_of); the audit's guarantees are about the calls that were there.
        seeded = {c["id"] for c in before}
        allc = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1')).calls")
        after = [c for c in allc if c["id"] in seeded]
        claimed = sorted(c["home"] for c in allc if c["id"] not in seeded and c["call_type"] == "straight")
        legs = sorted({c["home"] for c in allc if c["id"] not in seeded and c["call_type"] == "parlay_leg"})
        check("auto-claim: the export's three PLAYs claimed (and its tickets, legs from PLAYs only), the PASS not",
              claimed == ["Bplay", "Cplay", "Dplay"] and set(legs) <= {"Bplay", "Cplay", "Dplay"},
              json.dumps({"straights": claimed, "ticket legs": legs}))
        lc = {c["id"]: (c.get("leg_check") or {}).get("status") for c in after}
        check("marks: A not_play, B/C/D play, T3/T4 unmarked",
              lc == {"P-T1-1": "not_play", "P-T1-2": "play", "P-T2-1": "play", "P-T2-2": "play",
                     "P-T3-1": None, "P-T3-2": None, "P-T4-1": None, "P-T4-2": None}, json.dumps(lc))
        strip = lambda c: {k: v for k, v in c.items() if k not in ("leg_check", "tz_audit")}
        check("never deleted: same calls, every stored field unchanged but the marks",
              len(after) == len(before) and [strip(c) for c in after] == [strip(c) for c in before],
              f"{len(before)} → {len(after)}")
        bets = page.evaluate("settledBets(loadLedger()).filter(b=>b.call_type==='parlay').length")
        la = page.evaluate("lastAudit")
        check("P&L: T1 excluded (3 of 4 tickets remain), legNotPlay = 1", bets == 3 and la["legNotPlay"] == 1,
              f"tickets {bets} · {json.dumps(la)}")
        pnl = page.evaluate("pnlBlock(loadLedger())")
        check("P&L block line carries the count",
              "Parlay tickets with a leg not a play (#183): 1 excluded." in pnl, "")
        page.evaluate("renderLedger()")
        check("ledger totals show the audit line", "leg not a play (#183): 1 excluded" in page.inner_text("#tzAudit"),
              page.inner_text("#tzAudit") if page.query_selector("#tzAudit") else "(none)")
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
