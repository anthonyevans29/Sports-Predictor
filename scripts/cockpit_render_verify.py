"""
F1b/F1c RENDER-FROM-FILE headless verification (ARCHITECT 2026-10-01: "the
Cockpit RENDERS desk calls from the file and never recomputes policy; its
only overlay is the ledger"; F1c #191: desk-less files are REFUSED and the
in-browser policy is DELETED).

The golden battery (scripts/desk_battery.py: the seeded files, clock and
counts pinned) is annotated by the Python Desk (export --desk) plus its
desk_parlays file and loaded into a non-UTC browser. Checks, per scenario:
  - every Desk structure the Cockpit RENDERS (calls with their exec facts,
    value shadows, venue, parlay tickets) equals the DELETED JS Desk's last
    known outputs (tests/golden/desk_js_v1_1.json.gz) — rendered == computed;
  - the policy functions no longer exist in the page;
then: a tampered desk.call is shown as the file says; a legacy (desk-less)
file is REFUSED with "export with --desk" and nothing of it renders; no
parlays file -> no tickets, and the card says so; a policy-version mismatch
is flagged.

    python3 scripts/cockpit_render_verify.py

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

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cockpit_desk_files as cdf  # noqa: E402
import desk_battery as b  # noqa: E402

CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


STATE = """(()=>{
  const n=v=>(v===undefined?null:v);
  const ex=fx=>fx?{edge:n(fx.edge_pp),cost:n(fx.cost),basis:n(fx.basis),taker:n(fx.taker_cost),join:n(fx.join_price),
    note:n(fx.join_note)}:{edge:null,cost:null,basis:null,taker:null,join:null,note:null};
  return {
    calls: deskCalls.map(x=>({key:x.r.game+"|"+x.r.utc,call:x.call,units:x.units,cls:x.cls,edge:n(x.edge),tags:x.tags,
      reasons:x.reasons,shadowUnits:x.shadowUnits,passKind:n(x.passKind),mktRef:n(x.mktRef),kalOnly:x.kalOnly,
      exec:ex(x.r.fileDesk.exec)})),
    values: deskValue.map(({r,v})=>({key:r.game+"|"+r.utc,side:v.side,edge:v.edge,modelP:v.modelP,marketP:v.marketP,
      role:v.role,reason:v.reason,tags:v.tags,exec:ex(v.fileExec)})),
    venue: deskVenue.map(({r,v})=>({key:r.game+"|"+r.utc,eligible:v.eligible,side:n(v.side),divPP:n(v.divPP),
      bookP:n(v.bookP),kalP:n(v.kalP),kind:n(v.kind),reason:v.reason})),
    parlays: deskParlays.map(t=>({legs:t.legs.map(l=>l.game+"|"+l.utc+"|"+l.pick),sports:t.sports,pm:t.pm,pk:t.pk,edge:t.edge})),
    summary: document.getElementById("summary").textContent,
    policyFns: ["computeCall","valueSide","venueEdge","kalshiOnlyRef","execEdgeHTML","execFacts","deskCostFor","execEdgePP"].filter(f=>typeof window[f]==="function"),
  };})()"""


NO_EXEC = {"edge": None, "cost": None, "basis": None, "taker": None, "join": None, "note": None}


def display_rule(js, docs):
    """The frozen JS outputs with the DISPLAY rule applied to exec: the old
    Desk showed an exec line only when the HOME contract carried a cost, ask
    or maker price (execFacts null otherwise) — desk.exec mirrors exactly
    that (desk_policy.exec_block). Everything else is compared as frozen."""
    home_quoted = {}
    for d in docs.values():
        if d.get("predictions") is None or d.get("engine") == "model_shadow":
            continue                     # calls/values come from prediction files only
        for r in b.dp.normalize(d):
            k = r.get("kExec")
            home_quoted[f"{r['game']}|{r['utc']}"] = bool(k) and not (
                k["cost"] is None and k["ask"] is None and k["maker"] is None)
    out = json.loads(json.dumps(js))
    for part in ("calls", "values"):
        for row in out[part]:
            if not home_quoted.get(row["key"], False):
                row["exec"] = dict(NO_EXEC)
    return out


def main():
    g = b.load_golden()
    tmp = tempfile.mkdtemp(prefix="cockpit-render-")
    shutil.copy(os.path.join(b.ROOT, "tools", "cockpit.html"), os.path.join(tmp, "cockpit.html"))

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=tmp))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html"
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        errors = []

        def load(files, counts):
            page = browser.new_context(timezone_id="America/New_York").new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.clock.set_fixed_time(b.GOLDEN_NOW)
            page.goto(url)
            page.evaluate(f"localStorage.setItem('bd_ledger_v1', {json.dumps(json.dumps(b.seeded_ledger(counts)))})")
            page.goto(url)
            d = tempfile.mkdtemp(dir=tmp)
            page.set_input_files("#predFile", cdf.write(d, files))
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
            return page, page.evaluate(STATE)

        for sc in g["scenarios"]:
            docs = b.scenario_docs(sc["seed"], b.GOLDEN_NOW, sc["reversed"])
            files = cdf.desk_files(docs, b.GOLDEN_NOW, sc["counts"])
            page, S = load(files, sc["counts"])
            print(f"[{sc['label']}]")
            check("the in-browser policy functions are gone", S["policyFns"] == [], json.dumps(S["policyFns"]))
            want = display_rule(sc["js"], docs)
            for k in ("calls", "values", "venue", "parlays"):
                bad = b.golden_diffs(want[k], S[k])
                check(f"rendered {k} == the deleted JS's frozen outputs ({len(S[k])} rows)", not bad and len(S[k]) > 0,
                      "; ".join(bad[:2]))
            page.context.close()

        sc = g["scenarios"][0]
        docs = b.scenario_docs(sc["seed"], b.GOLDEN_NOW, False)
        files = cdf.desk_files(docs, b.GOLDEN_NOW, sc["counts"])
        # tamper: the file says PLAY 0.75u on a row the policy PASSes -> shown as the file says
        t = json.loads(json.dumps(files))
        row = next(p for p in t["mlb.json"]["predictions"] if p["desk"]["call"] == "PASS")
        row["desk"].update(call="PLAY", units=0.75, cls="play", pass_kind=None, reasons=["TAMPERED"], tags=[])
        page, T = load(t, sc["counts"])
        hit = next((c for c in T["calls"] if c["reasons"] == ["TAMPERED"]), None)
        check("tampered desk.call is RENDERED as the file says (PLAY 0.75u) — nothing recomputes it",
              hit is not None and hit["call"] == "PLAY" and hit["units"] == 0.75, json.dumps(hit)[:200])
        page.context.close()
        # a legacy (desk-less) file beside desk files: REFUSED whole, the message says why
        mixed = {**files, "legacy_nfl.json": docs["nfl.json"]}
        page, M = load(mixed, sc["counts"])
        check("legacy file REFUSED: 'export with --desk', none of its rows rendered",
              "REFUSED 1 file(s) without desk blocks (legacy_nfl.json) — export with --desk" in M["summary"]
              and len(M["calls"]) == len(sc["js"]["calls"]), M["summary"][-160:])
        page.context.close()
        page = browser.new_context(timezone_id="America/New_York").new_page()
        page.clock.set_fixed_time(b.GOLDEN_NOW)
        page.goto(url)
        page.set_input_files("#predFile", cdf.write(tempfile.mkdtemp(dir=tmp), {"legacy_mlb.json": docs["mlb.json"]}))
        page.wait_for_function("document.getElementById('summary').textContent.includes('REFUSED')")
        s_only = page.inner_text("#summary")
        check("a legacy-only load renders 0 rows and says 'export with --desk'",
              "0 rows" in s_only and "export with --desk" in s_only, s_only[:200])
        page.context.close()
        # no parlays file -> no tickets, the card says so (never built in the browser)
        nop = {k: v for k, v in files.items() if k != "desk_parlays.json"}
        page, N = load(nop, sc["counts"])
        note = page.inner_text("#parlayOut")
        check("no desk_parlays file: 0 tickets, card says so", N["parlays"] == [] and "no desk_parlays file loaded" in note,
              note[:120])
        page.context.close()
        # policy-version mismatch flagged
        vm = json.loads(json.dumps(files))
        vm["nfl.json"]["desk_meta"]["policy_version"] = "v9.9"
        page, V = load(vm, sc["counts"])
        check("file policy version ≠ Cockpit: flagged", "file policy v9.9 ≠ Cockpit v1.1" in V["summary"], V["summary"][-160:])
        page.context.close()
        check("no page errors", not errors, "; ".join(errors[:3]))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
