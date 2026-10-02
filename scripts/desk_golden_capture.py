"""
F1c GOLDEN CAPTURE (#191, ARCHITECT-RULE 2026-10-01): "Keep the headless
parity harness as a regression test against the deleted JS's last known
outputs." Run ONCE against the PRE-F1c tools/cockpit.html (the last version
with the in-browser Desk policy), BEFORE the deletion: drives the JS Desk on
the seeded battery (scripts/desk_battery.py) with the clock and counts pinned
in a non-UTC browser, plus the 600-slate parlay fuzz and the toFixed sample,
and writes tests/golden/desk_js_v1_1.json. After F1c the JS no longer
exists; this script stays only as the record of how the golden was made.

    git show <pre-F1c commit>:tools/cockpit.html > /tmp/cockpit_pre_f1c.html
    python3 scripts/desk_golden_capture.py --cockpit /tmp/cockpit_pre_f1c.html
"""
import argparse
import functools
import hashlib
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desk_battery as b  # noqa: E402

JS_EXTRACT = """(()=>{
  const n=v=>(v===undefined?null:v);
  const ex=(r,side,p)=>{const dc=deskCostFor(r,side), jb=joinBidFor(r,side);
    return {edge:n(execEdgePP(r,side,p)),cost:dc?dc.cost:null,basis:dc?dc.basis:null,taker:n(execCostFor(r,side)),
      join:jb?n(jb.price):null,note:jb?n(jb.note):null};};
  return {
   calls: deskCalls.map(x=>({key:x.r.game+"|"+x.r.utc,call:x.call,units:x.units,cls:x.cls,edge:n(x.edge),
     tags:x.tags,reasons:x.reasons,shadowUnits:x.shadowUnits,passKind:n(x.passKind),mktRef:n(x.mktRef),
     kalOnly:x.kalOnly,exec:ex(x.r,x.r.pick,x.r.prob)})),
   values: deskValue.map(({r,v})=>({key:r.game+"|"+r.utc,side:v.side,edge:v.edge,modelP:v.modelP,marketP:v.marketP,
     role:v.role,reason:v.reason,tags:v.tags,exec:ex(r,v.side,v.modelP)})),
   parlays: deskParlays.map(t=>({legs:t.legs.map(l=>l.game+"|"+l.utc+"|"+l.pick),sports:t.sports,pm:t.pm,pk:t.pk,
     edge:t.edge})),
   venue: deskVenue.map(({r,v})=>({key:r.game+"|"+r.utc,eligible:v.eligible,side:n(v.side),divPP:n(v.divPP),
     bookP:n(v.bookP),kalP:n(v.kalP),kind:n(v.kind),reason:v.reason})),
  };})()"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cockpit", default=os.path.join(b.ROOT, "tools", "cockpit.html"))
    ap.add_argument("--out", default=b.GOLDEN_PATH)
    a = ap.parse_args()
    html = open(a.cockpit).read()
    if "function computeCall(" not in html:
        raise SystemExit("this cockpit.html has no in-browser Desk (post-F1c): capture from the pre-F1c version")
    tmp = tempfile.mkdtemp(prefix="desk-golden-")
    shutil.copy(a.cockpit, os.path.join(tmp, "cockpit.html"))

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *x):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=tmp))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html"
    golden = {"captured_from": "tools/cockpit.html (pre-F1c, in-browser Desk policy v1.1)",
              "cockpit_sha256": hashlib.sha256(html.encode()).hexdigest(),
              "now": b.GOLDEN_NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "browser_tz": "America/New_York",
              "scenarios": []}
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        for label, seed, counts, rev in b.SCENARIOS:
            docs = b.scenario_docs(seed, b.GOLDEN_NOW, rev)
            d = tempfile.mkdtemp(dir=tmp)
            paths = []
            for n, doc in docs.items():
                paths.append(os.path.join(d, n))
                json.dump(doc, open(paths[-1], "w"))
            page = browser.new_context(timezone_id="America/New_York").new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.clock.set_fixed_time(b.GOLDEN_NOW)
            page.goto(url)
            page.evaluate(f"localStorage.setItem('bd_ledger_v1', {json.dumps(json.dumps(b.seeded_ledger(counts)))})")
            page.goto(url)
            seen = page.evaluate("[postseasonGraded(),valueShadowGraded(),kalshiOnlyGraded(),Date.now()]")
            assert seen == [counts["postseason_graded"], counts["value_shadow_graded"], counts["kalshi_only_graded"],
                            b.now_ms(b.GOLDEN_NOW)], seen
            page.set_input_files("#predFile", paths)
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
            js = page.evaluate(JS_EXTRACT)
            assert not errors, errors
            golden["scenarios"].append({"label": label, "seed": seed, "counts": counts, "reversed": rev,
                                        "files": list(docs), "js": js})
            print(f"{label}: calls {len(js['calls'])} · values {len(js['values'])} · venue {len(js['venue'])} "
                  f"· parlays {len(js['parlays'])}")
            if seed == 151:
                scen = b.parlay_scenarios()
                golden["parlay_fuzz"] = page.evaluate(
                    """sc=>sc.map(s=>{deskCalls=s.map(x=>({r:x.r,call:x.call})); buildParlays();
                    return deskParlays.map(t=>({legs:t.legs.map(l=>l.game+"|"+l.utc+"|"+l.pick),sports:t.sports,pm:t.pm,pk:t.pk,edge:t.edge}));})""",
                    scen)
                xs = b.fixed_doubles()
                golden["to_fixed"] = page.evaluate("xs=>xs.map(x=>[x.toFixed(1),x.toFixed(2),x.toFixed(3),x.toFixed(4)])", xs)
                print(f"parlay fuzz: {sum(len(x) for x in golden['parlay_fuzz'])} tickets · toFixed {len(xs)}")
        browser.close()
    srv.shutdown()
    import gzip
    with gzip.open(a.out, "wt") as f:
        json.dump(golden, f, separators=(",", ":"))
    print(f"wrote {a.out} ({os.path.getsize(a.out) // 1024} KiB)")


if __name__ == "__main__":
    main()
