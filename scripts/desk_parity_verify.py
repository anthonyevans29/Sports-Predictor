"""
F1 ROW-FOR-ROW PARITY VERIFY (#151; ARCHITECT 2026-10-01: "Row-for-row parity
verify with clock and counts pinned before any host chain emits desk calls").

The Cockpit's Desk (tools/cockpit.html, JS) and the Python port
(src/walters/desk_policy.py) read the SAME export files with the SAME pinned
clock and the SAME graded counts; every Desk output is compared field by
field, in row order:
  - calls (model rows): call, units, cls, edge, market reference, kalshi-only,
    pass class, tags, reasons (full text), shadow units;
  - exec (K2/#89/#93): desk cost + basis, exec edge, taker cost, join price;
  - value shadows: side, edge, model/market p, role, reason, tags;
  - venue (every row): eligible, side, divergence, book/Kalshi p, kind, reason;
  - the export path: annotate() writes desk.call/units/reason equal to the JS.
Floats must match EXACTLY (same IEEE arithmetic in the same order).

    python3 scripts/desk_parity_verify.py                       # synthetic battery + fuzz
    python3 scripts/desk_parity_verify.py exports/mlb_2026-10-01.json exports/nfl_predictions_2026-10-01.json \\
        --now 2026-10-01T16:00:00Z --ledger-summary exports/ledger_summary.json

With files: the REAL-EXPORT receipt (the ruled pre-cutover check). --now pins
the clock (default: each run's real now, printed); counts come from
--ledger-summary or --postseason/--value/--kalshi-only (default 0), and the
Cockpit's ledger is seeded with exactly that many graded calls. Writes nothing
to the repo; no DB. Needs Playwright + Chromium.
"""
import argparse
import functools
import http.server
import json
import math
import os
import random
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.walters import desk_policy as dp  # noqa: E402

CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


# ------------------------------------------------------------ fuzz battery --

def fuzz_docs(now: datetime, seed: int = 151, n: int = 120) -> dict:
    rnd = random.Random(seed)
    ko = lambda: iso(now + timedelta(minutes=rnd.choice([-150, -30, -5, 5, 20, 45, 59, 61, 90, 240, 600])))
    pick = lambda *xs: rnd.choice(xs)
    r3 = lambda: round(rnd.uniform(0.05, 0.95), rnd.choice([2, 3, 4, 6]))

    def kal_quotes(p):
        if rnd.random() < 0.3:
            return {}
        bid = round(min(0.97, max(0.02, p + rnd.uniform(-0.12, 0.12))), 2)
        ask = round(bid + pick(0.01, 0.01, 0.02, 0.03, 0.05), 2) if rnd.random() < 0.85 else None
        q = {"kalshi_bid": bid if rnd.random() < 0.9 else None, "kalshi_ask": ask}
        if rnd.random() < 0.7:
            q["exec_cost_taker"] = round((ask or bid) + rnd.uniform(0.003, 0.02), 4)
        if rnd.random() < 0.5:
            q["exec_cost_maker"] = round(bid + 0.01 + rnd.uniform(0.001, 0.006), 4)
        if rnd.random() < 0.15:
            q["kalshi_exec_cost"] = round((ask or bid) + 0.011, 4)
        if rnd.random() < 0.4:
            q.update(away_bid=round(1 - (ask or 0.5), 2), away_ask=round(1 - bid, 2),
                     exec_cost_taker_away=round(1 - bid + 0.012, 4) if rnd.random() < 0.8 else None,
                     exec_cost_maker_away=round(1 - (ask or 0.5) + 0.016, 4) if rnd.random() < 0.6 else None)
        return q

    def two_way(i, comp, team):
        p = r3()
        row = {"home_team": f"{team} H{i}", "away_team": f"{team} A{i}", "utc_date": ko(), "competition": comp}
        if rnd.random() < 0.5:
            row["prediction"] = {"home_win_prob": p, "tier": pick("strong", "lean", None)}
        else:
            row["prediction"] = {"probabilities": {"home_win": p, "draw": None, "away_win": round(1 - p, 6)},
                                 "tier": pick("strong", "lean", "watch")}
        books = pick(0, 0, 1, 2, 3, 4, 6, 9, None)
        mk = {} if books is None else {"bookmaker_count": books}
        if books and rnd.random() < 0.9:
            fh = round(min(0.95, max(0.05, p + rnd.uniform(-0.2, 0.2))), 4)
            mk["fair_prob"] = {"HOME": fh, "AWAY": round(1 - fh, 4)} if rnd.random() < 0.92 else {"HOME": fh}
        row["market"] = mk
        st = rnd.random()
        if st < 0.25:
            row["stage"] = "postseason"
        elif st < 0.5:
            row["stage"] = "regular"
        elif st < 0.65:
            row["stage"] = None                                    # unknown (labelled)
        row["input_quality"] = {"kalshi": pick("two_sided", "absent", "one_sided", None)}
        row.update(kal_quotes(p))
        return row

    mlb = {"sport": "mlb", "rehearsal": False, "predictions": [two_way(i, "MLB", "MLB") for i in range(n)]}
    nfl_rows = []
    for i in range(n // 2):
        r = two_way(i, "NFL", "NFL")
        r.pop("competition")
        if rnd.random() < 0.6:
            r["kalshi_prob"] = round(rnd.uniform(0.1, 0.9), 4)
        div = round(rnd.uniform(-25, 25), 1)
        r["market_divergence_pp"] = div if rnd.random() < 0.8 else None
        r["quarantine"] = abs(div) >= 15
        if rnd.random() < 0.25:
            r["input_quality"]["injuries"] = {"home": {"qb_listed": [f"QB{i}"]}, "away": {"qb_listed": []}}
        nfl_rows.append(r)
    nfl = {"sport": "nfl", "rehearsal": False, "predictions": nfl_rows}
    soc_rows = []
    for i in range(n // 2):
        h, d = rnd.uniform(0.15, 0.7), rnd.uniform(0.15, 0.35)
        a = max(0.02, 1 - h - d)
        row = {"home_team": f"Club H{i}", "away_team": f"Club A{i}", "utc_date": ko(), "competition": "PL",
               "prediction": {"probabilities": {"home_win": round(h, 4), "draw": round(d, 4), "away_win": round(a, 4)},
                              "tier": pick("strong", "lean")}}
        fh, fd = round(rnd.uniform(0.15, 0.7), 4), round(rnd.uniform(0.18, 0.32), 4)
        fa = round(max(0.02, 1 - fh - fd), 4)
        books = pick(0, 2, 5, 8)
        if rnd.random() < 0.5:
            mk = {"bookmaker_count": books, "selections": {"HOME": {"fair_prob": fh}, "DRAW": {"fair_prob": fd},
                                                           "AWAY": {"fair_prob": fa} if rnd.random() < 0.9 else None}}
        else:
            mk = {"bookmaker_count": books, "fair_prob": {"HOME": fh, "DRAW": fd, "AWAY": fa}} if books else {}
        if rnd.random() < 0.4:
            mk["kalshi"] = {"normalized": True, "prob": {"HOME": fh + 0.02, "DRAW": fd, "AWAY": fa - 0.01}}
        row["market"] = mk
        row["input_quality"] = {"kalshi": pick("two_sided", "partial", None)}
        row.update(kal_quotes(h))
        soc_rows.append(row)
    soccer = {"sport": "soccer", "predictions": soc_rows}
    nhl = {"sport": "nhl", "predictions": [two_way(i, "NHL", "NHL") for i in range(n // 4)]}
    fixtures = []
    for code in ("NHL", "NCAA", "UNL", "CL"):
        fx = []
        for i in range(n // 4):
            fh = round(rnd.uniform(0.2, 0.8), 4)
            draw = code in ("UNL", "CL")
            fair = {"HOME": fh, "AWAY": round(1 - fh, 4)}
            if draw:
                fair = {"HOME": round(fh * 0.75, 4), "DRAW": 0.25, "AWAY": round((1 - fh) * 0.75, 4)}
            books = pick(0, 2, 3, 4, 7)
            kp = {k: round(max(0.01, v + rnd.uniform(-0.12, 0.12)), 4) for k, v in fair.items()}
            if rnd.random() < 0.15:
                kp.pop("DRAW" if draw else "AWAY", None)
            fx.append({"home_team": f"{code} H{i}", "away_team": f"{code} A{i}", "utc_date": ko(),
                       "status": pick("scheduled", "scheduled", "scheduled", "finished", None),
                       "market": {"bookmaker_count": books, "fair_prob": fair if books else {}},
                       "kalshi": {"status": pick("two_sided", "two_sided", "one_sided", "partial"), "prob": kp},
                       "input_quality": {"kalshi": "two_sided"}})
        fixtures.append({"competition_code": code, "contains_predictions": False, "fixtures": fx})
    shadow = {"engine": "model_shadow", "predictions": [two_way(0, "NHL", "SHADOW")]}
    docs = {"mlb.json": mlb, "nfl.json": nfl, "soccer.json": soccer, "nhl.json": nhl, "shadow.json": shadow}
    for f in fixtures:
        docs[f"fixtures_{f['competition_code']}.json"] = f
    return docs


# ------------------------------------------------------------------ harness --

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
   venue: deskVenue.map(({r,v})=>({key:r.game+"|"+r.utc,eligible:v.eligible,side:n(v.side),divPP:n(v.divPP),
     bookP:n(v.bookP),kalP:n(v.kalP),kind:n(v.kind),reason:v.reason})),
  };})()"""


def py_extract(docs_in_order, now_ms, counts):
    calls, values, venue = [], [], []
    for doc in docs_in_order:
        ev = dp.evaluate(doc, now_ms, counts)
        key = lambda r: f"{r['game']}|{r['utc']}"

        def ex(r, side, p):
            dc, jb = dp.desk_cost_for(r, side), dp.join_bid_for(r, side)
            return {"edge": dp.exec_edge_pp(r, side, p), "cost": dc["cost"] if dc else None,
                    "basis": dc["basis"] if dc else None, "taker": dp.exec_cost_for(r, side),
                    "join": jb.get("price") if jb else None, "note": jb.get("note") if jb else None}
        for r, c in ev["calls"]:
            calls.append({"key": key(r), "call": c["call"], "units": c["units"], "cls": c["cls"], "edge": c["edge"],
                          "tags": c["tags"], "reasons": c["reasons"], "shadowUnits": c["shadowUnits"],
                          "passKind": c["passKind"], "mktRef": c["mktRef"], "kalOnly": c["kalOnly"],
                          "exec": ex(r, r["pick"], r["prob"])})
        for r, v in ev["values"]:
            values.append({"key": key(r), "side": v["side"], "edge": v["edge"], "modelP": v["modelP"],
                           "marketP": v["marketP"], "role": v["role"], "reason": v["reason"], "tags": v["tags"],
                           "exec": ex(r, v["side"], v["modelP"])})
        for r, v in ev["venue"]:
            venue.append({"key": key(r), "eligible": v["eligible"], "side": v["side"], "divPP": v["divPP"],
                          "bookP": v["bookP"], "kalP": v["kalP"], "kind": v["kind"], "reason": v["reason"]})
    return {"calls": calls, "values": values, "venue": venue}


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is b
        if isinstance(a, bool) or isinstance(b, bool):
            return a == b
        return float(a) == float(b) or (math.isnan(float(a)) and math.isnan(float(b)))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def compare(label, js, py):
    bad = []
    if len(js) != len(py):
        bad.append(f"row count JS {len(js)} vs Python {len(py)}")
    for i, (a, b) in enumerate(zip(js, py)):
        if not same(a, b):
            diffs = [k for k in a if not same(a.get(k), b.get(k))]
            bad.append(f"row {i} {a.get('key')}: {', '.join(diffs)} — JS {[a.get(k) for k in diffs]} "
                       f"vs PY {[b.get(k) for k in diffs]}")
    check(f"{label}: {len(js)} rows identical (row order, every field)", not bad,
          "; ".join(bad[:3]) + (f" … (+{len(bad) - 3})" if len(bad) > 3 else ""))
    return not bad


def seeded_ledger(counts):
    calls, i = [], 0

    def add(**kw):
        nonlocal i
        i += 1
        c = {"id": f"seed{i}", "log_date": "2026-09-01", "sport": "MLB", "game": f"SA{i} @ SH{i}",
             "home": f"SH{i}", "away": f"SA{i}", "pick": "HOME", "engine": "model_edge", "call_type": "straight",
             "units": 0.5, "status": "graded", "result": "win", "rules": [], "model_p": 0.6, "market_p": 0.55}
        c.update(kw)
        calls.append(c)
    for _ in range(counts["postseason_graded"]):
        add(stage="postseason")
    for _ in range(counts["value_shadow_graded"]):
        add(call_type="value_shadow", units=0, shadow_units=0.25)
    for _ in range(counts["kalshi_only_graded"]):
        add(reference="kalshi_only", stage="regular")
    return {"meta": {"policy_version": "v1.1"}, "calls": calls}


def run(docs: dict, now: datetime, counts: dict, label: str):
    tmp = tempfile.mkdtemp(prefix="desk-parity-")
    shutil.copy(os.path.join(ROOT, "tools", "cockpit.html"), os.path.join(tmp, "cockpit.html"))
    paths = []
    for n, d in docs.items():
        paths.append(os.path.join(tmp, n))
        with open(paths[-1], "w") as f:
            json.dump(d, f)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=tmp))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html"
    now_ms = float((now - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))
    print(f"\n[{label}] now pinned {now:%Y-%m-%dT%H:%M:%SZ} · counts {counts} · files {len(docs)}")
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        ctx = browser.new_context(timezone_id="America/New_York")      # a non-UTC viewer (#178)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.clock.set_fixed_time(now)
        page.goto(url)
        page.evaluate(f"localStorage.setItem('bd_ledger_v1', {json.dumps(json.dumps(seeded_ledger(counts)))})")
        page.goto(url)
        jsn = page.evaluate("[postseasonGraded(),valueShadowGraded(),kalshiOnlyGraded(),Date.now()]")
        check("JS sees the pinned counts and clock",
              jsn[:3] == [counts["postseason_graded"], counts["value_shadow_graded"], counts["kalshi_only_graded"]]
              and jsn[3] == now_ms, json.dumps(jsn))
        summ = page.evaluate("ledgerSummary()")
        sp = os.path.join(tmp, "ledger_summary.json")
        with open(sp, "w") as f:
            json.dump(summ, f)
        rc, rsrc = dp.read_ledger_summary(sp)
        check("Cockpit ledger summary → Python reader round-trip", rc == counts and "generated" in rsrc,
              f"{rc} ({rsrc})")
        page.set_input_files("#predFile", paths)
        page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        js = page.evaluate(JS_EXTRACT)
        py = py_extract(list(docs.values()), now_ms, counts)
        ok = all([compare("calls", js["calls"], py["calls"]), compare("value shadows", js["values"], py["values"]),
                  compare("venue", js["venue"], py["venue"])])
        # the export path: annotate() → desk.call / units / reason equal the JS
        jc = {c["key"]: c for c in js["calls"]}
        bad = []
        for doc in docs.values():
            d = dp.annotate(json.loads(json.dumps(doc)), now=now, counts=counts)
            for row in d.get("predictions") or []:
                desk = row.get("desk")
                if not desk or desk["engine"] != "model_edge":
                    continue
                k = dp.normalize({"sport": d.get("sport"), "predictions": [row]})[0]
                j = jc.get(f"{k['game']}|{k['utc']}")
                if not j or (desk["call"], desk["units"], desk["reason"]) != (j["call"], j["units"], " · ".join(j["reasons"])):
                    bad.append(k["game"])
        check("export path: annotate() desk.call / units / reason == the Cockpit's", not bad, ", ".join(bad[:5]))
        # coverage receipt (what the battery exercised)
        from collections import Counter
        cov = Counter(f"{c['call']}/{c['passKind'] or '-'}" for c in py["calls"])
        tags = Counter(t for c in py["calls"] for t in c["tags"])
        vk = Counter("eligible" if v["eligible"] else (v["kind"] or "other") for v in py["venue"])
        print(f"  coverage: calls {dict(sorted(cov.items()))}")
        print(f"            tags {dict(sorted(tags.items()))}")
        print(f"            value shadows {len(py['values'])} · venue {dict(sorted(vk.items()))}")
        check("no page errors", not errors, "; ".join(errors))
        if label.startswith("synthetic"):
            # JS toFixed vs js_fixed on random doubles (the reasons' formatting)
            rnd = random.Random(7)
            xs = [rnd.uniform(-50, 50) for _ in range(1500)] + [0.125, 2.675, 1.005, 13.35, -0.04, 0.0, -0.0, 4.95]
            jf = page.evaluate("xs=>xs.map(x=>[x.toFixed(1),x.toFixed(2),x.toFixed(3),x.toFixed(4)])", xs)
            pf = [[dp.js_fixed(x, d) for d in (1, 2, 3, 4)] for x in xs]
            check(f"js_fixed == Number.toFixed on {len(xs)} doubles × 4 precisions", jf == pf,
                  str(next(((x, a, b) for x, a, b in zip(xs, jf, pf) if a != b), "")))
        browser.close()
    srv.shutdown()
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--now", default=None, help="pin the clock, ISO UTC (default: now)")
    ap.add_argument("--ledger-summary", default=None)
    ap.add_argument("--postseason", type=int, default=None)
    ap.add_argument("--value", type=int, default=None)
    ap.add_argument("--kalshi-only", type=int, default=None)
    a = ap.parse_args(argv)
    now = (datetime.fromisoformat(a.now.replace("Z", "+00:00")) if a.now
           else datetime.now(timezone.utc).replace(microsecond=0))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    counts, src = dp.read_ledger_summary(a.ledger_summary)
    for k, v in (("postseason_graded", a.postseason), ("value_shadow_graded", a.value),
                 ("kalshi_only_graded", a.kalshi_only)):
        if v is not None:
            counts[k], src = v, "command line"
    if a.files:
        docs = {}
        for p in a.files:
            with open(p) as f:
                docs[os.path.basename(p)] = json.load(f)
        print(f"REAL-EXPORT PARITY · counts from {src}")
        run(docs, now, counts, "real exports")
    else:
        run(fuzz_docs(now), now, {"postseason_graded": 0, "value_shadow_graded": 0, "kalshi_only_graded": 0},
            "synthetic battery, counts 0")
        run(fuzz_docs(now, seed=152), now, {"postseason_graded": 31, "value_shadow_graded": 4,
                                            "kalshi_only_graded": 2}, "synthetic battery, postseason 31 (full units)")
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — PARITY: ALL GREEN" if all(CHECKS) else " — PARITY FAILED"))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
