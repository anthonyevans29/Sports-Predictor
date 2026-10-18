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
    known outputs (tests/golden/desk_js_v1_1.json.gz) — rendered == computed
    (one amendment by ruling, #181, addendum 112 item 9 + addendum 117
    item 2: the golden's eight pre-gate NHL PASS rows read units 0 / cls
    "pass" where the JS wrote 0.5 / "caution", without the big-edge caution
    reason and tag; nothing else moved, the capture metadata untouched);
  - the policy functions no longer exist in the page;
then: a tampered desk.call is shown as the file says; a legacy (desk-less)
file is REFUSED with "export with --desk" and nothing of it renders; no
parlays file -> no tickets, and the card says so; a policy-version mismatch
is flagged; the Ledger card shows exactly the line "exports read no ledger
summary; postseason rows are sized at half until v1.2" (#544, ARCHITECT
2026-10-18, addendum 125 item 4).

TODAY (ARCHITECT 2026-10-18, addendum 125 item 2(c), #589): "scripts/
cockpit_render_verify.py extended to load the file and assert the tiles'
counts equal the file's". A coverage_v1 file is written by the REAL command,
`python cli.py coverage --json`, on a SCRATCH database (scripts/
cockpit_coverage_file.py: the ORM's schema in a temporary folder; never
data/), then loaded through the file picker:
  - the Today tab: one tile per competition, in the file's order; each tile's
    games count and status label equal the file's; the gaps lines equal the
    file's `gaps`; the ETAs strip has one line per roadmap lane with the file's
    ETA ("no ETA" included); a group to run carries a countdown that moves with
    the page clock, a done group none; the page title is "Cockpit";
  - a coverage file loaded after a slate leaves the slate as it was (rows, the
    Desk table, the summary), and a slate loaded after a coverage file leaves
    the tiles as they were;
  - a status the file adds later ("POT", label "POT (training data only)")
    renders as its label; markup in a file string is shown as text, never run;
    a file whose roadmap is null shows its reason;
  - a slate and a coverage file in ONE load: null entries in a tile's lists
    (rows, groups) and in the roadmap are labelled "not read" and the slate
    loads; a damaged coverage file (a null competition entry) shows its error
    in the Today summary, no tile, and the slate picked with it still loads;
  - a file whose groups are all done (`--all-done`: every closing group
    receipted): each tile shows the file's own `closing_tail` ("none left to
    run"), never derived in the page.

    python3 scripts/cockpit_render_verify.py

Writes nothing to the repo; the scratch DB lives in a temporary folder.
Needs Playwright + Chromium.
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
import cockpit_coverage_file as ccf  # noqa: E402
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


LEDGER_CARD_LINE = "exports read no ledger summary; postseason rows are sized at half until v1.2"   # #544, verbatim

NO_EXEC = {"edge": None, "cost": None, "basis": None, "taker": None, "join": None, "note": None}

TODAY = """(()=>{
  const q=(el,s)=>el.querySelector(s);
  return {
    shown: !document.getElementById("todayView").hidden,
    summary: document.getElementById("todaySummary").textContent,
    tiles: [...document.querySelectorAll("#todayTiles .tile")].map(t=>({code:t.dataset.code,status:t.dataset.status,
      games:+q(t,".tgames").dataset.games,gamesText:q(t,".tgames").textContent,label:q(t,".slabel").textContent,
      groups:[...t.querySelectorAll(".grp")].map(g=>({state:g.dataset.state,
        countdown:q(g,".countdown")?q(g,".countdown").textContent:null})),
      tail:q(t,".ctail")?q(t,".ctail").textContent:null})),
    unread: [...document.querySelectorAll("#todayView .unread")].map(e=>e.textContent),
    gaps: [...document.querySelectorAll("#todayGaps .gapline")].map(e=>e.textContent),
    gapsText: document.getElementById("todayGaps").textContent,
    etas: [...document.querySelectorAll("#todayEtas .eta")].map(e=>({lane:e.dataset.lane,eta:q(e,".etav").textContent})),
    etasText: document.getElementById("todayEtas").textContent,
    rows: rows.length, calls: deskCalls.length, slateRows: document.querySelectorAll("#slate tbody tr").length,
    deskSummary: document.getElementById("summary").textContent, title: document.title,
    pwned: window.__pwned===1,
  };})()"""


def _cd_seconds(text):
    """'T-35 in 1h 05m 07s' -> 3907; None when not a countdown."""
    import re
    m = re.fullmatch(r"T-35 in (\d+)h (\d\d)m (\d\d)s", text or "")
    return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) if m else None


def today_checks(browser, url, tmp, errors, load, slate_files, counts):
    """Addendum 125 item 2(c): the Today tab against a coverage_v1 file the real command wrote on a scratch DB."""
    from datetime import datetime, timedelta, timezone
    cov = ccf.make(tempfile.mkdtemp(dir=tmp))
    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    doc = cov["doc"] or {}
    print("[today: coverage --json on a scratch DB]")
    check("`coverage --json` on the scratch DB: exit 0, kind coverage_v1",
          cov["rc"] == 0 and doc.get("kind") == "coverage_v1", (cov["console"].strip().splitlines() or [""])[-1][:200])
    comps = doc.get("competitions") or []

    def fresh(clock=None):
        page = browser.new_context(timezone_id="America/New_York").new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        if clock:
            page.clock.install(time=clock)
        page.goto(url)
        return page

    def put(page, paths):
        page.set_input_files("#predFile", paths)
        page.wait_for_function("document.getElementById('todaySummary').textContent.startsWith('COVERAGE')")
        return page.evaluate(TODAY)

    page = fresh(t0)
    T = put(page, [cov["path"]])
    check("a coverage file alone opens the Today tab; the page title is \"Cockpit\"",
          T["shown"] and T["title"] == "Cockpit", f"{T['shown']} {T['title']!r}")
    check(f"tiles == the file's competitions, in its order ({len(comps)})",
          [t["code"] for t in T["tiles"]] == [x["code"] for x in comps] and len(comps) >= 4,
          json.dumps([t["code"] for t in T["tiles"]]))
    check("each tile's games count == len(games) in the file",
          [t["games"] for t in T["tiles"]] == [len(x["games"]) for x in comps]
          and all(t["gamesText"] == f"{len(x['games'])} game{'' if len(x['games']) == 1 else 's'}"
                  for t, x in zip(T["tiles"], comps)),
          json.dumps([(t["code"], t["games"], t["gamesText"]) for t in T["tiles"]]))
    check("each tile's status label == the file's status_label, word for word (LIVE, MARKET-ONLY · shadow v7, ...)",
          [t["label"] for t in T["tiles"]] == [x["status_label"] for x in comps],
          json.dumps([t["label"] for t in T["tiles"]]))
    check(f"the gaps lines == the file's gaps ({len(doc.get('gaps') or [])})",
          T["gaps"] == doc.get("gaps") and len(T["gaps"]) >= 2, json.dumps(T["gaps"])[:240])
    lanes = doc.get("roadmap") or []
    check(f"the ETAs strip: one line per roadmap lane, the file's ETA ({len(lanes)} lanes, "
          f"{sum(1 for ln in lanes if ln['eta'] == 'no ETA')} 'no ETA')",
          [(e["lane"], e["eta"]) for e in T["etas"]] == [(ln["lane"], ln["eta"]) for ln in lanes]
          and any(ln["eta"] == "no ETA" for ln in lanes), json.dumps(T["etas"])[:240])
    groups = [g for t in T["tiles"] for g in t["groups"]]
    ahead = [g for g in groups if g["state"] not in ("done", "started")]
    done = [g for g in groups if g["state"] == "done"]
    check("a group to run shows a live countdown to its T-35; a done group shows none",
          ahead and all(_cd_seconds(g["countdown"]) for g in ahead) and done
          and all(g["countdown"] is None for g in done), json.dumps(groups)[:240])
    page.clock.pause_at(t0 + timedelta(minutes=1))               # the page's clock held, then moved by hand
    left = lambda S: [_cd_seconds(g["countdown"]) for t in S["tiles"] for g in t["groups"]  # noqa: E731
                      if g["state"] not in ("done", "started")]
    a = left(page.evaluate(TODAY))
    page.clock.run_for(61000)
    z = left(page.evaluate(TODAY))
    check("the countdowns move with the page clock (61 s later, 61 s less)",
          a and len(a) == len(z) and all(x is not None and y is not None and x - y == 61 for x, y in zip(a, z)),
          f"{a} -> {z}")
    page.context.close()

    # a slate, then the coverage file alone: the slate is never reset
    page, S = load(slate_files, counts)
    before = page.evaluate(TODAY)
    T = put(page, [cov["path"]])
    check("coverage loaded after a slate: the slate is untouched (rows, Desk calls, table rows, summary)",
          (T["rows"], T["calls"], T["slateRows"], T["deskSummary"]) == (before["rows"], before["calls"],
                                                                       before["slateRows"], before["deskSummary"])
          and before["rows"] > 0 and len(T["tiles"]) == len(comps),
          f"rows {before['rows']}->{T['rows']} · calls {before['calls']}->{T['calls']}")
    page.context.close()

    # the coverage file, then a slate: the tiles are never reset
    page = fresh()
    page.clock.set_fixed_time(b.GOLDEN_NOW)
    page.goto(url)
    page.evaluate(f"localStorage.setItem('bd_ledger_v1', {json.dumps(json.dumps(b.seeded_ledger(counts)))})")
    page.goto(url)
    first = put(page, [cov["path"]])
    page.set_input_files("#predFile", cdf.write(tempfile.mkdtemp(dir=tmp), slate_files))
    page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
    T = page.evaluate(TODAY)
    check("a slate loaded after the coverage file: the tiles, gaps and ETAs are untouched, the slate loads",
          (T["tiles"], T["gaps"], T["etas"], T["summary"]) == (first["tiles"], first["gaps"], first["etas"],
                                                              first["summary"]) and T["rows"] > 0,
          f"tiles {len(first['tiles'])}->{len(T['tiles'])} · rows {T['rows']}")
    page.context.close()

    # a slate and a coverage file in ONE load (#589 review): the coverage path never stops the slate path
    slate = before

    def one_load(cov_doc, name):
        page = browser.new_context(timezone_id="America/New_York").new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.clock.set_fixed_time(b.GOLDEN_NOW)
        page.goto(url)
        page.evaluate(f"localStorage.setItem('bd_ledger_v1', {json.dumps(json.dumps(b.seeded_ledger(counts)))})")
        page.goto(url)
        page.set_input_files("#predFile", cdf.write(tempfile.mkdtemp(dir=tmp), {**slate_files, name: cov_doc}))
        try:
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')", timeout=15000)
        except Exception:  # noqa: BLE001 — the slate never loaded: the check below says so
            pass
        return page, page.evaluate(TODAY)

    nulls = json.loads(json.dumps(doc))
    tgt = next(x for x in nulls["competitions"] if x.get("groups") and x.get("rows"))
    tgt["rows"].insert(0, None)
    tgt["groups"].append(None)
    nulls["roadmap"] = list(nulls.get("roadmap") or []) + [None]
    page, T = one_load(nulls, "coverage_nulls.json")
    check("a slate and a coverage file with null list entries (rows, groups, roadmap) in ONE load: the slate loads, "
          "every tile renders, each null entry labelled 'not read'",
          (T["rows"], T["calls"], T["slateRows"]) == (slate["rows"], slate["calls"], slate["slateRows"])
          and [t["code"] for t in T["tiles"]] == [x["code"] for x in comps] and T["summary"].startswith("COVERAGE")
          and len(T["unread"]) == 3 and all("not read" in u for u in T["unread"]),
          f"rows {T['rows']}/{slate['rows']} · tiles {len(T['tiles'])} · {T['summary'][:80]!r} · {T['unread']}")
    page.context.close()
    broken = json.loads(json.dumps(doc))
    broken["competitions"] = [None] + broken["competitions"]
    page, T = one_load(broken, "coverage_broken.json")
    check("a slate and a damaged coverage file (competitions[0] null) in ONE load: the slate loads; the Today summary "
          "shows the error, no tile",
          (T["rows"], T["calls"], T["slateRows"]) == (slate["rows"], slate["calls"], slate["slateRows"])
          and "coverage_broken.json not rendered" in T["summary"] and "competitions[0]" in T["summary"]
          and T["tiles"] == [], f"rows {T['rows']}/{slate['rows']} · {T['summary'][:200]!r}")
    page.context.close()

    # every closing group done: the file's closing_tail ("none left to run") on the tile, not derived by the page
    done_all = ccf.make(tempfile.mkdtemp(dir=tmp), all_done=True)
    dd = done_all["doc"] or {}
    dcomps = dd.get("competitions") or []
    page = fresh(datetime.now(timezone.utc))
    T = put(page, [done_all["path"]])
    tails = [(x["code"], x.get("closing_tail")) for x in dcomps]
    check("a file whose groups are all done: each tile shows the file's closing_tail ('none left to run' on PL and "
          "NFL), as the file gives it",
          done_all["rc"] == 0 and [(t["code"], t["tail"]) for t in T["tiles"]] == tails
          and dict(tails).get("PL") == dict(tails).get("NFL") == "none left to run"
          and all(g["state"] == "done" for t in T["tiles"] for g in t["groups"]),
          json.dumps([(t["code"], t["tail"]) for t in T["tiles"]]))
    page.context.close()

    # a status the file adds later, markup in a file string, a roadmap the command could not read
    odd = json.loads(json.dumps(doc))
    pot = json.loads(json.dumps(comps[-1]))
    pot.update(code="SA", status="POT", status_label="POT (training data only)",
               status_from="<img src=x onerror=\"window.__pwned=1\">")
    odd["competitions"].append(pot)
    odd["gaps"] = odd["gaps"] + ["<b>X</b>: 1 GAME, 0 PREDICTION ROWS"]
    odd["roadmap"], odd["roadmap_unread"] = None, "the roadmap cannot be read: docs/roadmap.json: lane 1: no title"
    p = os.path.join(tempfile.mkdtemp(dir=tmp), "coverage_odd.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(odd, f)
    page = fresh(datetime.now(timezone.utc))
    T = put(page, [p])
    last = T["tiles"][-1] if T["tiles"] else {}
    check("a status the file adds later renders as its label (POT (training data only)), uncomputed",
          (last.get("code"), last.get("status"), last.get("label")) == ("SA", "POT", "POT (training data only)"),
          json.dumps(last)[:200])
    check("markup in a file string is shown as text, never run",
          not T["pwned"] and T["gaps"][-1] == "<b>X</b>: 1 GAME, 0 PREDICTION ROWS", T["gaps"][-1:])
    check("roadmap null: the ETAs strip shows the file's reason, no lane guessed",
          T["etas"] == [] and "roadmap not read: the roadmap cannot be read" in T["etasText"], T["etasText"][:160])
    page.context.close()
    return cov


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
        # #544 (ARCHITECT 2026-10-18, addendum 125 item 4): the Ledger card shows the one line, exactly
        page.click("#tabLedger")
        card_line = page.evaluate("""(()=>{const c=document.querySelector('#ledgerView > .card');
          const el=c&&c.querySelector('#ledgerExportsLine');
          return el?{text:el.textContent,shown:!!el.offsetParent}:null;})()""")
        check("Ledger card shows 'exports read no ledger summary; postseason rows are sized at half until v1.2'",
              card_line is not None and card_line["shown"]
              and card_line["text"] == LEDGER_CARD_LINE, json.dumps(card_line))
        page.context.close()
        today_checks(browser, url, tmp, errors, load, files, sc["counts"])
        check("no page errors", not errors, "; ".join(errors[:3]))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
