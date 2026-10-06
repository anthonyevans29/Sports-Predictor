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
FIELDS = ("book", "call_id", "backed_role", "backed", "no_on_role", "fee_class_open", "fee_class_close")


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
