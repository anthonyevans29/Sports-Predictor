"""
Parity receipt for src/walters/ledger_fills.py (the K-track receipt's port of
the Cockpit's fill classification + executed-position CLV, #87, 2026-10-06).

Imports the synthetic Kalshi CSV of scripts/cockpit_fills_verify.py through the
Cockpit's own "Import Kalshi CSV" input, reads the stored ledger back, then runs
the COCKPIT's classifyFills / executedPositions in Chromium and the Python port
on the SAME ledger, field by field: book, call_id, backed_role, backed,
no_on_role, fee class; per position qty, entry CLV and fee-adj edge. One call is
graded with a close so the CLV path is exercised. Any difference is a FAIL.
Writes nothing to the repo; no DB. Needs Playwright + Chromium.
Run:  python3 scripts/ledger_fills_parity_verify.py
"""
import functools
import http.server
import os
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cockpit_fills_verify as F  # noqa: E402  (fixture: LEDGER, FILLS, HDR)
from src.walters import ledger_fills as P  # noqa: E402

CHECKS = []


def _fill(fid, ticker, side, title):
    return {"id": fid, "ticker": ticker, "side": side, "qty": 2, "entry": 0.5, "exit": 1.0, "staked": 1.0,
            "fees": 0.04, "open_fee": 0.04, "close_fee": 0, "pnl_pre": 1.0, "pnl_net": 0.96, "title": title}


EXTRA = {"calls": [
    F.call("dh1", "MLB", "Boston Red Sox", "New York Yankees", "HOME", kick="2026-09-27T17:05:00"),   # 13:05 ET
    F.call("dh2", "MLB", "Boston Red Sox", "New York Yankees", "HOME", kick="2026-09-27T23:05:00"),   # 19:05 ET
    F.call("epl", "SOCCER", "Arsenal", "Chelsea", "AWAY", kick="2026-09-27T14:00:00"),
    F.call("lad", "SOCCER", "Everton", "Fulham", "AWAY", ct="ladder", kick="2026-09-27T14:00:00"),
    F.call("tbh", "NFL", "Tampa Bay Buccaneers", "Green Bay Packers", "HOME", kick="2026-10-04T17:00:00"),
    F.call("ng1", "MLB", "Boston Red Sox", "New York Yankees", "AWAY", kick="2026-09-29T17:05:00"),   # 13:05 ET
    F.call("ng2", "MLB", "Boston Red Sox", "New York Yankees", "HOME", kick="2026-09-29T19:45:00"),   # 15:45 ET
    F.call("nyj", "NFL", "Los Angeles Chargers", "New York Jets", "AWAY", kick="2026-10-11T17:00:00"),
    F.call("rev", "MLB", "New York Yankees", "Boston Red Sox", "HOME", kick="2026-10-20T17:05:00"),  # reversed
    F.call("nyj2", "NFL", "Seattle Seahawks", "New York Jets", "AWAY", kick="2026-10-25T17:00:00"),
    F.call("jax", "NFL", "Jacksonville Jaguars", "Tennessee Titans", "HOME", kick="2026-11-01T17:00:00"),
    F.call("unc", "NCAA", "North Carolina Tar Heels", "Georgia Bulldogs", "HOME", kick="2026-11-07T19:00:00"),
    F.call("nyr", "NFL", "New York Giants", "New York Jets", "HOME", kick="2026-11-08T17:00:00"),   # Giants home
    F.call("lg1", "SOCCER", "Everton", "Fulham", "AWAY", ct="ladder", kick="2026-11-14T14:00:00"),
    F.call("lg2", "SOCCER", "Everton", "Fulham", "AWAY", ct="ladder", kick="2026-11-14T14:00:00"),  # tied ladders
], "fills": [
    _fill("x-dh2", "KXMLBGAME-26SEP271905NYYBOS-BOS", "yes", "Boston wins — New York Y"),  # game 2, not game 1
    _fill("x-dh1", "KXMLBGAME-26SEP271305NYYBOS-BOS", "yes", "Boston wins — New York Y"),
    _fill("x-3no", "KXEPLGAME-26SEP27CHEARS-ARS", "no", "Arsenal wins — Chelsea"),          # NO on ARS: composite
    _fill("x-lad", "KXEPLGAME-26SEP27FULEVE-EVE", "no", "Everton wins — Fulham"),          # the ladder's NO HOME
    _fill("x-gb", "KXNFLGAME-26OCT04GBTB-GB", "yes", "Green Bay wins — Tampa Bay"),        # side != pick (HOME)
    _fill("x-ng", "KXMLBGAME-26SEP291305NYYBOS-BOS", "yes", "Boston wins — New York Y"),   # game 1 disagrees
    _fill("x-nyg", "KXNFLGAME-26OCT11NYGLAR-NYG", "yes", "New York G wins — Los Angeles R"),  # not Jets–Chargers
    _fill("x-rev", "KXMLBGAME-26OCT201305NYYBOS-BOS", "yes", "Boston wins — New York Yankees"),  # BOS home
    _fill("x-tie", "KXEPLGAME-26SEP27CHEARS-TIE", "no", "Tie — Chelsea vs Arsenal"),               # NO TIE: composite
    _fill("x-nygs", "KXNFLGAME-26OCT25NYGSEA-NYG", "yes", "New York G wins — Seattle"),           # weak NYG unconfirmed
    _fill("x-jax", "KXNFLGAME-26NOV01TENJAX-JAX", "yes", "Tennessee vs Jacksonville Winner?"),    # legacy title
    _fill("x-unc", "KXNCAAFGAME-26NOV07UGAUNC-UNC", "yes", "Georgia vs North Carolina Winner?"),  # 2 non-prefix codes
    _fill("x-nyj", "KXNFLGAME-26NOV08NYGNYJ-NYJ", "yes", "New York Jets wins — New York Giants"),  # NYJ home: reversed
    _fill("x-lg", "KXEPLGAME-26NOV14FULEVE-EVE", "no", "Everton wins — Fulham"),           # two tied ladder calls
]}
FIELDS = ("book", "call_id", "backed_role", "backed", "no_on_role", "fee_class_open", "fee_class_close",
          "ambiguous_calls")


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def main():
    tmp = tempfile.mkdtemp(prefix="ledger-parity-")
    csv_path = os.path.join(tmp, "Kalshi-Fills.csv")
    with open(csv_path, "w") as f:
        f.write(F.HDR + "\n")
        for t, sd, q, en, ex, of, cf, net, pre, title in F.FILLS:
            f.write(f'sub-1,trade,{q:.2f},{t},{sd},{en:.8f},{ex:.8f},{of:.8f},{cf:.8f},{pre:.8f},{net:.8f},'
                    f'2026-09-28T18:00:00-05:00,2026-09-27T07:00:00-05:00,predictions,2026-09-01,"{title}"\n')

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                          functools.partial(Quiet, directory=os.path.join(ROOT, "tools")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html")
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", F.LEDGER)
        page.click("#tabLedger")
        page.set_input_files("#kalshiCsvFile", csv_path)
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('Kalshi CSV')")
        # fill matcher lane (2026-10-06): an MLB doubleheader told apart by the ticker's ET start time, and a
        # three-way NO (composite, two outcomes) that must never match a single-side straight
        page.evaluate("""(x) => { const L = loadLedger(); L.calls.push(...x.calls); L.fills.push(...x.fills);
            localStorage.setItem('bd_ledger_v1', JSON.stringify(L)); }""", EXTRA)
        # grade c1 (KC home, picked HOME) with a close, so executedPositions has positions
        page.evaluate("""() => { const L = loadLedger();
            const c = L.calls.find(x => x.id === 'c1');
            Object.assign(c, {status: 'graded', result: 'win', graded_date: '2026-09-28',
              close_ref: {version: 'p0-3 v2', q_close: 0.62, fair: {HOME: 0.62, AWAY: 0.38}}});
            localStorage.setItem('bd_ledger_v1', JSON.stringify(L)); }""")
        L = page.evaluate("loadLedger()")
        js = page.evaluate("classifyFills(loadLedger())")
        jpos = page.evaluate("executedPositions(loadLedger()).pos.map(p => ({id: p.c.id, clv: p.clv, "
                             "fee_adj: p.fee_adj, fee_status: p.fee_status}))")
        browser.close()
    srv.shutdown()
    check("no page errors", not errors, "; ".join(errors))
    py = P.classify_fills(L)
    check(f"same fill count ({len(js)})", len(js) == len(py), f"js {len(js)} py {len(py)}")
    for a, b in zip(js, py):
        diff = {k: (a.get(k), b.get(k)) for k in FIELDS if a.get(k) != b.get(k)}
        check(f"{a.get('ticker')} {a.get('side')} qty {a.get('qty')} → {a.get('book')}"
              + (f" ({a.get('call_id')})" if a.get("call_id") else ""), not diff, str(diff))
    by = {f.get("id"): f for f in py}
    check("doubleheader: the 19:05 ET fill matches game 2 (dh2)", by["x-dh2"].get("call_id") == "dh2"
          and next(f for f in js if f.get("id") == "x-dh2").get("call_id") == "dh2")
    check("doubleheader: the 13:05 ET fill matches game 1 (dh1)", by["x-dh1"].get("call_id") == "dh1")
    check("three-way NO is composite, never system_matched", by["x-3no"].get("book") == "off_book_sports"
          and "composite" in (by["x-3no"].get("category") or ""))
    check("composite NO on HOME matches the AWAY ladder call", by["x-lad"].get("call_id") == "lad"
          and next(f for f in js if f.get("id") == "x-lad").get("call_id") == "lad")
    check("GB/TB: a GB (AWAY) fill never matches a TB (HOME) call (shared 'Bay')",
          by["x-gb"].get("book") == "off_book_sports" and not by["x-gb"].get("call_id")
          and next(f for f in js if f.get("id") == "x-gb").get("book") == "off_book_sports")
    check("the timed game first: a 13:05 fill whose game picked AWAY is never handed to the 15:45 HOME call",
          not by["x-ng"].get("call_id") and not next(f for f in js if f.get("id") == "x-ng").get("call_id"))
    check("same-city codes: a Giants–Rams fill never fits the Jets–Chargers call",
          not by["x-nyg"].get("call_id") and not next(f for f in js if f.get("id") == "x-nyg").get("call_id"))
    check("orientation: a BOS-home fill never fits the reversed NYY-home call",
          not by["x-rev"].get("call_id") and not next(f for f in js if f.get("id") == "x-rev").get("call_id"))
    jsby = {f.get("id"): f for f in js}
    check("NO on a three-way TIE is composite (no_on_role DRAW)", all(
        x["x-tie"].get("composite") and x["x-tie"].get("no_on_role") == "DRAW" for x in (by, jsby)))
    check("a weak NYG code is not confirmed by a strong opponent: no Jets match",
          not by["x-nygs"].get("call_id") and not jsby["x-nygs"].get("call_id"))
    check("legacy 'A vs B Winner?' title with a non-prefix code still matches (opposite code orients)",
          by["x-jax"].get("call_id") == "jax" == jsby["x-jax"].get("call_id"))
    check("legacy AWAY-vs-HOME title orients two non-prefix codes (UGAUNC)",
          by["x-unc"].get("call_id") == "unc" == jsby["x-unc"].get("call_id"))
    check("weak codes are confirmed by their OWN side's title team: the reversed Giants-home call never fits",
          not by["x-nyj"].get("call_id") and not jsby["x-nyj"].get("call_id"))
    check("tied ladder calls are flagged with every candidate, Cockpit and port alike",
          by["x-lg"].get("ambiguous_calls") == ["lg1", "lg2"] == jsby["x-lg"].get("ambiguous_calls"))
    ppos = P.executed_positions(L)["pos"]
    check(f"executed positions: js {len(jpos)} py {len(ppos)}", len(jpos) == len(ppos) and len(jpos) > 0)
    pmap = {p["c"]["id"]: p for p in ppos}
    for jp in jpos:
        pp = pmap.get(jp["id"])
        ok = pp is not None and abs(pp["clv"] - jp["clv"]) < 1e-12 and pp["fee_status"] == jp["fee_status"] and (
            (pp["fee_adj"] is None and jp["fee_adj"] is None)
            or (pp["fee_adj"] is not None and jp["fee_adj"] is not None and abs(pp["fee_adj"] - jp["fee_adj"]) < 1e-12))
        fa = "—" if jp["fee_adj"] is None else f"{jp['fee_adj'] * 100:+.4f}pp"
        check(f"position {jp['id']}: entry CLV {jp['clv'] * 100:+.4f}pp · fee-adj {fa}",
              ok, "" if ok else f"py {pp and (pp['clv'], pp['fee_adj'], pp['fee_status'])}")
    n = sum(CHECKS)
    print(f"\n{n}/{len(CHECKS)} checks passed")
    return 0 if n == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
