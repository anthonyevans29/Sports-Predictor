"""
F1b RENDER-FROM-FILE headless verification (ARCHITECT 2026-10-01: "the
Cockpit RENDERS desk calls from the file and never recomputes policy; its
only overlay is the ledger").

The SAME synthetic slate (desk_parity_verify's seeded battery: MLB, NFL,
soccer, NHL, a model_shadow file, four fixtures files) is loaded twice into a
non-UTC browser with the clock and graded counts pinned:
  A. legacy files (no desk blocks) → the Cockpit COMPUTES the Desk;
  B. the files annotated by Python (export --desk) + the desk_parlays file →
     the Cockpit RENDERS the Desk.
Checks: every Desk structure (calls, value shadows, venue, parlay tickets),
the Desk / venue / parlay table text and the ledger capture (snapshotCalls)
are identical A vs B; in B the policy functions (computeCall, valueSide,
venueEdge, kalshiOnlyRef) are NEVER called; a tampered desk.call in the file
is shown as the file says (rendered, not recomputed); a missing parlays file
shows no tickets and says so; legacy rows beside desk rows and a
policy-version mismatch are flagged in the summary.

    python3 scripts/cockpit_render_verify.py

Writes nothing to the repo; no DB. Needs Playwright + Chromium.
"""
import functools
import http.server
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from src.walters import desk_policy as dp  # noqa: E402
import desk_parity_verify as pv  # noqa: E402

CHECKS = []
NOW = datetime.now(timezone.utc).replace(microsecond=0)
COUNTS = {"postseason_graded": 7, "value_shadow_graded": 2, "kalshi_only_graded": 1}


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


SPY = """(()=>{window.__calls={computeCall:0,valueSide:0,venueEdge:0,kalshiOnlyRef:0};
  for(const n of Object.keys(window.__calls)){const f=window[n]; window[n]=function(){window.__calls[n]++; return f.apply(this,arguments);};}})()"""

STATE = """(()=>{
  const n=v=>(v===undefined?null:v);
  const txt=sel=>Array.from(document.querySelectorAll(sel+" tbody tr")).map(tr=>tr.innerText);
  return {
    calls: deskCalls.map(x=>({key:x.r.game+"|"+x.r.utc,call:x.call,units:x.units,cls:x.cls,edge:n(x.edge),tags:x.tags,
      reasons:x.reasons,shadowUnits:x.shadowUnits,passKind:n(x.passKind),mktRef:n(x.mktRef),kalOnly:x.kalOnly})),
    values: deskValue.map(({r,v})=>({key:r.game+"|"+r.utc,side:v.side,edge:v.edge,modelP:v.modelP,marketP:v.marketP,
      role:v.role,reason:v.reason,tags:v.tags})),
    venue: deskVenue.map(({r,v})=>({key:r.game+"|"+r.utc,eligible:v.eligible,side:n(v.side),divPP:n(v.divPP),
      bookP:n(v.bookP),kalP:n(v.kalP),kind:n(v.kind),reason:v.reason})),
    parlays: deskParlays.map(t=>({legs:t.legs.map(l=>l.game+"|"+l.utc+"|"+l.pick),sports:t.sports,pm:t.pm,pk:t.pk,edge:t.edge})),
    slate: txt("#slate"), venueTable: txt("#venueTable"),
    parlayText: Array.from(document.querySelectorAll("#parlayOut > div[style]")).map(d=>d.innerText),
    capture: snapshotCalls(), summary: document.getElementById("summary").textContent,
    spy: window.__calls,
  };})()"""


def serve(tmp):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=tmp))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def write(tmp, docs):
    paths = []
    for n, d in docs.items():
        paths.append(os.path.join(tmp, n))
        with open(paths[-1], "w") as f:
            json.dump(d, f)
    return paths


def load(page, url, paths):
    page.goto(url)
    page.evaluate(f"localStorage.setItem('bd_ledger_v1', {json.dumps(json.dumps(pv.seeded_ledger(COUNTS)))})")
    page.goto(url)
    page.evaluate(SPY)
    page.set_input_files("#predFile", paths)
    page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
    return page.evaluate(STATE)


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-render-")
    shutil.copy(os.path.join(ROOT, "tools", "cockpit.html"), os.path.join(tmp, "cockpit.html"))
    srv = serve(tmp)
    url = f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html"
    legacy = pv.fuzz_docs(NOW, seed=1510)
    annotated = {n: dp.annotate(json.loads(json.dumps(d)), now=NOW, counts=COUNTS, counts_source="verify")
                 for n, d in legacy.items()}
    par = dp.parlays_doc(list(annotated.items()), now=NOW, counts=COUNTS, counts_source="verify")
    da, db = os.path.join(tmp, "a"), os.path.join(tmp, "b")
    os.makedirs(da)
    os.makedirs(db)
    pa = write(da, legacy)
    pb = write(db, {**annotated, "desk_parlays.json": par})
    print(f"now pinned {NOW:%Y-%m-%dT%H:%M:%SZ} · counts {COUNTS} · {len(legacy)} files · "
          f"{len(par['tickets'])} ticket(s) in desk_parlays")
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        ctx = browser.new_context(timezone_id="America/Los_Angeles")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.clock.set_fixed_time(NOW)
        A = load(page, url, pa)
        B = load(page, url, pb)
        check("A (legacy files): the browser computed the Desk",
              A["spy"]["computeCall"] > 0 and A["spy"]["venueEdge"] > 0 and "computed in browser" in A["summary"],
              json.dumps(A["spy"]))
        check("B (desk files): computeCall / valueSide / venueEdge / kalshiOnlyRef NEVER called",
              B["spy"] == {"computeCall": 0, "valueSide": 0, "venueEdge": 0, "kalshiOnlyRef": 0}, json.dumps(B["spy"]))
        check("B summary: 'desk: rendered from file (as of …)', no legacy warning",
              "desk: rendered from file (as of " + NOW.strftime("%Y-%m-%dT%H:%M:%SZ") in B["summary"]
              and "legacy" not in B["summary"], B["summary"][-160:])
        for k, label in (("calls", "Desk calls"), ("values", "value shadows"), ("venue", "venue verdicts"),
                         ("parlays", "parlay tickets")):
            check(f"{label}: {len(A[k])} identical computed vs rendered", pv.same(A[k], B[k]) and len(A[k]) > 0,
                  "" if pv.same(A[k], B[k]) else f"first diff {next((i for i, (x, y) in enumerate(zip(A[k], B[k])) if not pv.same(x, y)), 'len')}")
        check(f"Desk table text identical ({len(A['slate'])} rows incl. exec notes, KO lines)", A["slate"] == B["slate"],
              next((f"{x!r} vs {y!r}" for x, y in zip(A["slate"], B["slate"]) if x != y), "")[:300])
        check(f"venue table text identical ({len(A['venueTable'])} rows)", A["venueTable"] == B["venueTable"], "")
        check(f"parlay card tickets identical ({len(A['parlayText'])})", A["parlayText"] == B["parlayText"], "")
        # b_shadow_cut (B-track shadow, 2026-10-01) is a file-mode mark: the legacy path never computes it
        nocut = lambda cap: [{k: v for k, v in c.items() if k != "b_shadow_cut"} for c in cap]
        check(f"ledger capture identical ({len(A['capture'])} entries: straights, shadows, venue, parlay legs)",
              pv.same(nocut(A["capture"]), nocut(B["capture"])),
              next((json.dumps([x, y])[:300] for x, y in zip(A["capture"], B["capture"]) if not pv.same(x, y)), ""))
        strip = lambda s: re.sub(r" · desk: .*$", "", s)
        check("summary counts identical (desk-source note aside)", strip(A["summary"]) == strip(B["summary"]),
              f"{strip(A['summary'])[:120]} | {strip(B['summary'])[:120]}")

        # tamper: the file says PLAY 0.75u on a row the policy PASSes → the Cockpit shows the FILE
        t = json.loads(json.dumps(annotated))
        row = next(p for p in t["mlb.json"]["predictions"] if p["desk"]["call"] == "PASS")
        row["desk"].update(call="PLAY", units=0.75, cls="play", pass_kind=None, reasons=["TAMPERED"], tags=[])
        dt = os.path.join(tmp, "t")
        os.makedirs(dt)
        T = load(page, url, write(dt, {**t, "desk_parlays.json": par}))
        hit = next((c for c in T["calls"] if c["reasons"] == ["TAMPERED"]), None)
        check("tampered desk.call is RENDERED as the file says (PLAY 0.75u) — never recomputed",
              hit is not None and hit["call"] == "PLAY" and hit["units"] == 0.75 and T["spy"]["computeCall"] == 0,
              json.dumps(hit))
        # no parlays file → no tickets, and the card says why (tickets are never built here)
        dn = os.path.join(tmp, "n")
        os.makedirs(dn)
        N = load(page, url, write(dn, annotated))
        note = page.inner_text("#parlayOut")
        check("no desk_parlays file: 0 tickets, card says so (never built in the browser)",
              N["parlays"] == [] and "no desk_parlays file loaded" in note, note[:120])
        # mixed: one legacy file beside desk files → flagged; version mismatch → flagged
        mx = {**annotated, "mlb.json": legacy["mlb.json"]}
        mx["nfl.json"] = json.loads(json.dumps(mx["nfl.json"]))
        mx["nfl.json"]["desk_meta"]["policy_version"] = "v9.9"
        dm = os.path.join(tmp, "m")
        os.makedirs(dm)
        M = load(page, url, write(dm, {**mx, "desk_parlays.json": par}))
        check("mixed files: legacy rows flagged, version mismatch flagged",
              "row(s) from legacy files: Desk computed in browser" in M["summary"]
              and "file policy v9.9 ≠ Cockpit v1.1" in M["summary"], M["summary"][-220:])
        check("no page errors", not errors, "; ".join(errors[:3]))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
