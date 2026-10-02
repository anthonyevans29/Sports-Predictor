"""
The DESK BATTERY (F1c #191, ARCHITECT-RULE 2026-10-01): the seeded fuzz
battery, the Python Desk extractor and the comparison helper, browser-free.

The in-browser Desk policy was DELETED from the Cockpit in F1c. Its LAST
KNOWN OUTPUTS on this battery (clock and counts pinned, non-UTC browser) are
frozen in tests/golden/desk_js_v1_1.json.gz (captured by
scripts/desk_golden_capture.py against the pre-F1c cockpit.html, before the
deletion). tests/test_desk_golden.py and scripts/desk_parity_verify.py check
the Python Desk (src/walters/desk_policy.py) against them row for row.
"""
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.walters import desk_policy as dp  # noqa: E402

# The pinned clock of the frozen golden (any fixed instant; the battery's
# kickoffs are generated relative to it).
GOLDEN_NOW = datetime(2026, 10, 2, 16, 0, 0, tzinfo=timezone.utc)
GOLDEN_PATH = os.path.join(ROOT, "tests", "golden", "desk_js_v1_1.json.gz")
ZERO = {"postseason_graded": 0, "value_shadow_graded": 0, "kalshi_only_graded": 0}
SCENARIOS = [  # (label, seed, counts, reversed file order)
    ("synthetic battery, counts 0", 151, ZERO, False),
    ("synthetic battery, postseason 31 (full units)", 152,
     {"postseason_graded": 31, "value_shadow_graded": 4, "kalshi_only_graded": 2}, False),
    ("synthetic battery, fixtures loaded first", 153, ZERO, True),
]


def now_ms(now):
    return float((now - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))


def scenario_docs(seed, now, rev):
    docs = fuzz_docs(now, seed=seed)
    return dict(reversed(list(docs.items()))) if rev else docs


def parlay_scenarios(seed=183, n=600):
    rnd = random.Random(seed)
    teams = [f"T{i}" for i in range(9)]
    scen = []
    for _ in range(n):
        sl = []
        for j in range(rnd.randint(2, 9)):
            h, a2 = rnd.sample(teams, 2)
            sl.append({"r": {"home": h, "away": a2, "sport": rnd.choice(["MLB", "NFL", "SOCCER"]),
                             "game": f"{a2} @ {h}", "utc": f"2026-10-0{rnd.randint(1, 3)}T1{j}:00:00",
                             "pick": rnd.choice(["HOME", "AWAY", "DRAW"]),
                             "prob": round(rnd.uniform(0.3, 0.8), rnd.choice([2, 3, 6])),
                             "mkt": None if rnd.random() < 0.2 else round(rnd.uniform(0.3, 0.8), rnd.choice([2, 3]))},
                       "call": rnd.choice(["PLAY", "PLAY", "LADDER", "PASS"])})
        scen.append(sl)
    return scen


def py_parlays(scen):
    return [[{"legs": [f"{l['game']}|{l['utc']}|{l['pick']}" for l in t["legs"]], "sports": t["sports"],
              "pm": t["pm"], "pk": t["pk"], "edge": t["edge"]}
             for t in dp.build_parlays([(x["r"], {"call": x["call"]}) for x in sl])] for sl in scen]


def fixed_doubles(seed=7):
    rnd = random.Random(seed)
    return [rnd.uniform(-50, 50) for _ in range(1500)] + [0.125, 2.675, 1.005, 13.35, -0.04, 0.0, -0.0, 4.95]


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
            # Pre-split rows carried only the alias kalshi_exec_cost (retired, #130). The
            # deleted JS read exec_cost_taker ?? kalshi_exec_cost, so the alias's value lands
            # in exec_cost_taker when that is absent: same draws, same frozen outputs.
            q.setdefault("exec_cost_taker", round((ask or bid) + 0.011, 4))
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


def py_extract(docs_in_order, now_ms, counts):
    calls, values, venue, all_calls = [], [], [], []
    for doc in docs_in_order:
        ev = dp.evaluate(doc, now_ms, counts)
        key = lambda r: f"{r['game']}|{r['utc']}"

        def ex(r, side, p):
            dc, jb = dp.desk_cost_for(r, side), dp.join_bid_for(r, side)
            return {"edge": dp.exec_edge_pp(r, side, p), "cost": dc["cost"] if dc else None,
                    "basis": dc["basis"] if dc else None, "taker": dp.exec_cost_for(r, side),
                    "join": jb.get("price") if jb else None, "note": jb.get("note") if jb else None}
        all_calls += ev["calls"]
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
    parlays = [{"legs": [f"{l['game']}|{l['utc']}|{l['pick']}" for l in t["legs"]], "sports": t["sports"],
                "pm": t["pm"], "pk": t["pk"], "edge": t["edge"]} for t in dp.build_parlays(all_calls)]
    return {"calls": calls, "values": values, "venue": venue, "parlays": parlays}


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




def load_golden(path=None):
    import gzip
    import json
    with gzip.open(path or GOLDEN_PATH, "rt") as f:
        return json.load(f)


def golden_diffs(js_rows, py_rows):
    """Row-for-row: [] when identical, else readable mismatch lines."""
    bad = []
    if len(js_rows) != len(py_rows):
        bad.append(f"row count JS {len(js_rows)} vs Python {len(py_rows)}")
    for i, (a, b) in enumerate(zip(js_rows, py_rows)):
        if not same(a, b):
            diffs = [k for k in a if not same(a.get(k), b.get(k))]
            bad.append(f"row {i} {a.get('key')}: {', '.join(diffs)} — JS {[a.get(k) for k in diffs]} "
                       f"vs PY {[b.get(k) for k in diffs]}")
    return bad


def check_against_golden(golden=None):
    """Every frozen JS output vs the Python Desk now. Returns
    [(label, n_rows, mismatch_lines)]."""
    g = golden or load_golden()
    out = []
    for sc in g["scenarios"]:
        docs = scenario_docs(sc["seed"], GOLDEN_NOW, sc["reversed"])
        assert list(docs) == sc["files"], "battery drifted from the golden's file order"
        py = py_extract(list(docs.values()), now_ms(GOLDEN_NOW), sc["counts"])
        for part in ("calls", "values", "venue", "parlays"):
            out.append((f"{sc['label']} · {part}", len(sc["js"][part]), golden_diffs(sc["js"][part], py[part])))
    pf = py_parlays(parlay_scenarios())
    bad = [f"slate {i}" for i, (a, b) in enumerate(zip(g["parlay_fuzz"], pf)) if not same(a, b)]
    out.append(("parlay fuzz (600 slates)", sum(len(x) for x in g["parlay_fuzz"]), bad))
    xs = fixed_doubles()
    pfx = [[dp.js_fixed(x, d) for d in (1, 2, 3, 4)] for x in xs]
    out.append(("js_fixed == Number.toFixed", len(xs), [str(x) for x, a, b in zip(xs, g["to_fixed"], pfx) if a != b][:3]))
    return out
