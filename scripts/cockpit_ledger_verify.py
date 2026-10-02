"""
Cockpit ledger integrity headless verification (ledger-doubling fix, 2026-09-28).

Incident: after Import Kalshi CSV on the republished Cockpit every ledger row
showed twice (model_edge 7->14, staked 5.50->11.00, shadows 2->4, open 10->20).
Drives tools/cockpit.html in headless Chromium over SYNTHETIC files and checks:
- capture: a game already past kickoff in a multi-week file is NOT captured;
  a week-2 game is; re-Log the same day and re-Log on a later day (the same
  file loaded again) add nothing;
- every write path holds the key: Import ledger twice, a self-duplicated
  import, Import Kalshi CSV twice, Import pasted -> identical totals;
- Dedupe ledger collapses a doubled ledger (same-key copies + later-day
  re-logs + a duplicate fill), reports how many it removed, restores the
  totals, and a second press finds none;
- clipboard-export fallback: with the clipboard refused, Copy ledger (JSON)
  puts the exact ledger in a selected text box; with it granted, it copies.

    python3 scripts/cockpit_ledger_verify.py              # tools/cockpit.html
    python3 scripts/cockpit_ledger_verify.py OLD.html     # e.g. reproduce on a prior version

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
ISO = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S")
D1, D2, W2, PAST = (ISO(NOW + timedelta(days=1)), ISO(NOW + timedelta(days=2)),
                    ISO(NOW + timedelta(days=8)), ISO(NOW - timedelta(days=2)))
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def nfl(home, away, p, fair, when, quarantine=False):
    return {"home_team": home, "away_team": away, "utc_date": when,
            "prediction": {"home_win_prob": p, "away_win_prob": round(1 - p, 4), "tier": "lean"},
            "market": {"bookmaker_count": 7, "fair_prob": {"HOME": fair, "AWAY": round(1 - fair, 4)}},
            "market_divergence_pp": round((p - fair) * 100, 1), "quarantine": quarantine,
            "input_quality": {"book_odds": 7, "injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}}


def soc(home, away, probs, fair, when):
    return {"home_team": home, "away_team": away, "utc_date": when,
            "prediction": {"probabilities": dict(zip(("home_win", "draw", "away_win"), probs)), "tier": "lean"},
            "market": {"bookmaker_count": 6, "selections": {k: {"fair_prob": v} for k, v in zip(("HOME", "DRAW", "AWAY"), fair)}}}


INPUTS = {   # a MULTI-WEEK file: one game already played, one next week
    "nfl_multiweek.json": {"sport": "nfl", "rehearsal": False, "predictions": [
        nfl("Kansas City Chiefs", "Buffalo Bills", 0.66, 0.60, PAST),                     # past kickoff
        nfl("Philadelphia Eagles", "Dallas Cowboys", 0.64, 0.58, D1),                     # PLAY
        nfl("Baltimore Ravens", "Pittsburgh Steelers", 0.63, 0.57, W2),                   # week 2 PLAY
        nfl("Detroit Lions", "Green Bay Packers", 0.80, 0.60, D1, quarantine=True),       # shadow
    ]},
    "soccer.json": {"sport": "soccer", "predictions": [
        soc("Arsenal", "Brentford", (0.62, 0.20, 0.18), (0.56, 0.25, 0.19), D1),         # PLAY
        soc("Wolves", "Chelsea", (0.20, 0.22, 0.58), (0.30, 0.26, 0.44), D2),             # LADDER
    ]},
}
RESULTS = {"results.json": {"sport": "nfl", "results": [
    {"home_team": "Philadelphia Eagles", "away_team": "Dallas Cowboys", "date": D1[:10],
     "actual": {"home_score": 24, "away_score": 17}},
    {"home_team": "Detroit Lions", "away_team": "Green Bay Packers", "date": D1[:10],
     "actual": {"home_score": 20, "away_score": 23}},
    {"home_team": "Arsenal", "away_team": "Brentford", "date": D1[:10],
     "actual": {"home_score": 2, "away_score": 0}}]}}
CSV = ("subtrader_id,type,quantity_fp,market_ticker,side,entry_price_dollars,exit_price_dollars,"
       "open_fees_dollars,close_fees_dollars,realized_pnl_without_fees_dollars,"
       "realized_pnl_with_fees_dollars,close_timestamp,open_timestamp,product,period_start,market_title\n"
       ",trade,10,KXNFLGAME-26SEP29DALPHI-PHI,yes,0.58,1.00,0.18,0.00,4.20,4.02,"
       "2026-09-29T20:00:00-05:00,2026-09-28T10:00:00-05:00,,,Dallas vs Philadelphia Winner?\n"
       ",trade,5,KXMVESPORTSMULTIGAMEEXTENDED-X,yes,0.20,0.00,0.05,0.00,-1.00,-1.05,"
       "2026-09-29T20:00:00-05:00,2026-09-28T10:00:00-05:00,,,parlay\n")


def main(html):
    tmp = tempfile.mkdtemp(prefix="cockpit-ledger-")
    for name, doc in {**INPUTS, **RESULTS}.items():
        with open(os.path.join(tmp, name), "w") as f:
            json.dump(doc, f)
    csv_path = os.path.join(tmp, "Kalshi-Fills.csv")
    with open(csv_path, "w") as f:
        f.write(CSV)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.dirname(html)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/{os.path.basename(html)}"

    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        ctx = browser.new_context()
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        ledger = lambda: page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        totals = lambda: page.inner_text("#ledgerTotals").split("\n")[0]
        has = lambda sel: page.evaluate(f"!!document.querySelector('{sel}')")

        def note_after(action, sel="#ledgerNote"):
            page.evaluate(f"document.querySelector('{sel}').textContent=''")
            action()
            page.wait_for_function(f"document.querySelector('{sel}').textContent.length>0")
            return page.inner_text(sel)

        cdf.upload(page, [os.path.join(tmp, n) for n in INPUTS])
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        page.click("#tabDesk")

        print("CAPTURE (multi-week file)")
        n1 = note_after(lambda: page.click("#logBtn"), "#logNote")
        C = ledger()["calls"]
        games = {c["game"] for c in C}
        print("   ", n1)
        check("past-kickoff game NOT captured (Bills @ Chiefs, kicked off 2 days ago)",
              "Buffalo Bills @ Kansas City Chiefs" not in games, str(sorted(games)))
        check("week-2 game captured (Steelers @ Ravens, +8 days)", "Pittsburgh Steelers @ Baltimore Ravens" in games)
        check("no parlay ticket carries a started leg",
              not [c for c in C if c["call_type"] == "parlay_leg" and "Chiefs" in c["game"]])
        base = len(C)
        page.click("#logBtn")
        check("re-Log same day adds nothing", len(ledger()["calls"]) == base, f"{base} -> {len(ledger()['calls'])}")
        # the incident path: the same file loaded again on a LATER local day,
        # prices moved overnight (Eagles book fair 0.58 -> 0.56)
        first = {c["game"]: c for c in C}["Dallas Cowboys @ Philadelphia Eagles"]
        moved = json.loads(json.dumps(INPUTS["nfl_multiweek.json"]))
        moved["predictions"][1]["market"]["fair_prob"] = {"HOME": 0.56, "AWAY": 0.44}
        with open(os.path.join(tmp, "nfl_multiweek_day2.json"), "w") as f:
            json.dump(moved, f)
        page.evaluate("document.getElementById('summary').textContent=''")
        cdf.upload(page, [os.path.join(tmp, "nfl_multiweek_day2.json"), os.path.join(tmp, "soccer.json")])
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        page.click("#tabDesk")
        page.evaluate("localDate=(d)=>{d=d||new Date(Date.now()+86400000);"
                      "return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}")
        n2 = note_after(lambda: page.click("#logBtn"), "#logNote")
        after = len(ledger()["calls"])
        print("   ", n2)
        check("re-Log on a LATER day adds nothing (no doubling)", after == base, f"calls {base} -> {after}")
        pos = {c["game"]: c for c in ledger()["calls"]}["Dallas Cowboys @ Philadelphia Eagles"]
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        check("ruling (a): the position is REPRICED in place (market_p 0.58 -> 0.56; id + first log_date kept)",
              pos["market_p"] == 0.56 and pos["id"] == first["id"] and pos["log_date"] == first["log_date"]
              and pos.get("last_logged") == tomorrow,
              f"market_p {first['market_p']} -> {pos['market_p']} · last_logged {pos.get('last_logged')}")
        page.evaluate("localDate=(d)=>{d=d||new Date();"
                      "return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}")

        print("GRADE + IMPORT PATHS")
        page.click("#tabLedger")
        page.set_input_files("#resultsFile", os.path.join(tmp, "results.json"))
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('graded')")
        T, L0 = totals(), ledger()
        print("    totals:", T)
        exp = os.path.join(tmp, "export.json")
        with open(exp, "w") as f:
            json.dump(L0, f)
        for i in (1, 2):
            n = note_after(lambda: page.set_input_files("#importLedgerFile", exp))
            check(f"Import ledger #{i}: identical totals + call count", totals() == T and len(ledger()["calls"]) == len(L0["calls"]),
                  f"{len(L0['calls'])} -> {len(ledger()['calls'])} · {n[:90]}")
        dup = dict(L0, calls=L0["calls"] + [dict(c, id="stale-" + str(i)) for i, c in enumerate(L0["calls"])])
        dup_path = os.path.join(tmp, "self_duplicated.json")
        with open(dup_path, "w") as f:
            json.dump(dup, f)
        n = note_after(lambda: page.set_input_files("#importLedgerFile", dup_path))
        check("Import of a self-duplicated ledger (same keys, stale ids): identical totals",
              totals() == T and len(ledger()["calls"]) == len(L0["calls"]), n[:120])
        fills = []
        for i in (1, 2):
            note_after(lambda: page.set_input_files("#kalshiCsvFile", csv_path))
            L = ledger()
            fills.append(len(L.get("fills") or []))
            check(f"Import Kalshi CSV #{i}: identical call totals", totals() == T and len(L["calls"]) == len(L0["calls"]),
                  f"calls {len(L['calls'])} · fills {fills[-1]}")
        check("Kalshi CSV twice: fills not doubled", fills == [2, 2], str(fills))
        T2, L1 = totals(), ledger()

        print("DEDUPE (repair a doubled ledger)")
        doubled = json.loads(json.dumps(L1))
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        relog = [dict(c, id=f"relog-{i}", log_date=tomorrow, status="open",
                      parlay_id=(c["parlay_id"].replace(c["log_date"], tomorrow) if c.get("parlay_id") else None))
                 for i, c in enumerate(L1["calls"])]
        for c in relog:
            for k in ("result", "units_returned", "shadow_returned", "graded_date", "ticket_result"):
                c.pop(k, None)
            if c.get("parlay_id") is None:
                c.pop("parlay_id")
        doubled["calls"] = L1["calls"] + relog + [dict(L1["calls"][0])]   # + one exact copy
        doubled["fills"] = L1["fills"] + [dict(L1["fills"][0])]
        want = len(relog) + 1 + 1
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", doubled)
        page.evaluate("renderLedger()")
        warn = page.inner_text("#ledgerTotals")
        check("doubled ledger: Ledger tab warns before repair", "duplicate(s) in the stored ledger" in warn, warn.split("\n")[-1][:110])
        if has("#dedupeBtn"):
            n = note_after(lambda: page.click("#dedupeBtn"))
            print("   ", n)
            check(f"Dedupe reports removed {want}", f"removed {want}" in n, n[:100])
            check("Dedupe restores the pre-incident totals + counts",
                  totals() == T2 and len(ledger()["calls"]) == len(L1["calls"]) and len(ledger()["fills"]) == 2,
                  f"{totals()[:80]}")
            check("graded history kept (graded count unchanged)",
                  sum(c["status"] == "graded" for c in ledger()["calls"]) == sum(c["status"] == "graded" for c in L1["calls"]))
            n = note_after(lambda: page.click("#dedupeBtn"))
            check("second Dedupe finds none", "no duplicates found" in n, n)
        else:
            check("Dedupe ledger action exists", False, "no #dedupeBtn")

        print("CLIPBOARD-EXPORT FALLBACK")
        if has("#copyLedgerBtn"):
            page.evaluate("() => { navigator.clipboard.writeText = () => Promise.reject(new Error('blocked by the embedding view')); }")
            n = note_after(lambda: page.click("#copyLedgerBtn"))
            box = page.input_value("#ledgerJson")
            check("clipboard refused -> ledger JSON in a visible, selected box",
                  page.is_visible("#ledgerJson") and json.loads(box) == ledger()
                  and page.evaluate("(()=>{const b=document.getElementById('ledgerJson');return b.selectionEnd-b.selectionStart===b.value.length})()"),
                  n)
            n = note_after(lambda: page.click("#importPastedBtn"))
            check("Import pasted (same JSON back): identical totals", totals() == T2 and len(ledger()["calls"]) == len(L1["calls"]), n[:100])
            page.reload()
            ctx.grant_permissions(["clipboard-read", "clipboard-write"])
            page.click("#tabLedger")
            n = note_after(lambda: page.click("#copyLedgerBtn"))
            got = page.evaluate("navigator.clipboard.readText()")
            check("clipboard granted -> copied, box stays hidden",
                  json.loads(got) == ledger() and not page.is_visible("#ledgerJson"), n)
        else:
            check("Copy ledger (JSON) action exists", False, "no #copyLedgerBtn")
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main(os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "tools", "cockpit.html")))
