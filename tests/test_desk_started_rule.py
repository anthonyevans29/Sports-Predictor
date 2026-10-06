"""A STARTED GAME IS NEVER A NEW CALL (#49 (b); ARCHITECT 2026-10-06, #313): a model-sport row whose kickoff is at or
before desk as_of is PASS / pass_kind "started", units 0, no order, no value shadow, never a parlay leg. An unknown
kickoff is unchanged (never guessed). Behind its own switch: the frozen golden holds with it off (base_v11), and
with it on only started rows change."""
from datetime import datetime, timedelta, timezone

from src.walters import desk_policy as dp
from src.walters.venue import kalshi_exec

NOW = datetime(2026, 10, 11, 17, 0, tzinfo=timezone.utc)
LEGS = {"HOME": {"ticker": "KXNFLGAME-26OCT11BUFKC-KC", "bid": 0.54, "ask": 0.55},
        "AWAY": {"ticker": "KXNFLGAME-26OCT11BUFKC-BUF", "bid": 0.44, "ask": 0.45}}


def nfl(home, kickoff, p_home=0.62, fair_h=0.55, p_alt=None):
    r = {"home_team": home, "away_team": f"{home} away", "utc_date": kickoff, "competition": "NFL",
         "stage": "regular", "kalshi_legs": LEGS,
         "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                        "tier": "lean"},
         "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}}}
    r.update(kalshi_exec(0.54, 0.55, "NFL", two_way=True))
    return r


def at(minutes):
    return (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


def desk(*rows):
    doc = {"sport": "nfl", "predictions": list(rows)}
    dp.annotate(doc, now=NOW)
    return {r["home_team"]: r["desk"] for r in doc["predictions"]}, doc


def test_a_started_row_with_a_clearing_edge_is_pass_started():
    d, doc = desk(nfl("KO", at(0)), nfl("LIVE", at(-60)))       # kickoff AT as_of, and an hour in
    for k in ("KO", "LIVE"):
        assert (d[k]["call"], d[k]["units"], d[k]["pass_kind"]) == ("PASS", 0, "started")
        assert d[k]["reason"] == "started - never a new call"
        assert d[k]["order"] is None and d[k]["value_shadow"] is None and d[k]["exec"] is None
    assert doc["desk_meta"]["started_rule"] is True


def test_the_same_row_one_minute_before_kickoff_is_unchanged():
    d, _ = desk(nfl("PRE", at(1)))
    assert (d["PRE"]["call"], d["PRE"]["units"], d["PRE"]["pass_kind"]) == ("PLAY", 1, None)
    assert d["PRE"]["order"]["text"].startswith("BUY YES KXNFLGAME-26OCT11BUFKC-KC")
    with dp.started_rule_off():                                  # and the started row, rule off, is what it was
        off, _ = desk(nfl("LIVE", at(-60)))
    assert off["LIVE"]["call"] == "PLAY"


def test_unknown_kickoff_is_never_guessed():
    d, _ = desk(nfl("NOKO", ""))
    assert d["NOKO"]["pass_kind"] != "started"


def test_parlays_skip_started_rows():
    rows = [nfl("A", at(-10), p_home=0.70), nfl("B", at(30), p_home=0.68), nfl("C", at(45), p_home=0.66)]
    doc = dp.parlays_doc([("nfl.json", {"sport": "nfl", "predictions": rows})], now=NOW)
    homes = {leg["game"].split(" @ ")[1] for t in doc["tickets"] for leg in t["legs"]}
    assert "A" not in homes and doc["live_legs"] == 2
    with dp.started_rule_off():
        assert dp.parlays_doc([("nfl.json", {"sport": "nfl", "predictions": rows})], now=NOW)["live_legs"] == 3


def test_value_shadow_is_not_built_for_a_started_row():
    # a big AWAY value edge on a started row: no shadow (and the same row pre-kickoff keeps it)
    row = lambda ko: nfl("V", ko, p_home=0.60, fair_h=0.80)
    pre, _ = desk(row(at(30)))
    live, _ = desk(row(at(-30)))
    assert pre["V"]["value_shadow"] is not None and live["V"]["value_shadow"] is None


def test_golden_battery_only_started_rows_change_with_the_rule_on():
    """The frozen golden holds with the rule off (tests/test_desk_golden.py). With it ON, the rows that change are
    exactly the started ones (listed in the PR): no other call row and no surviving value shadow moves."""
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import desk_battery as b
    g = b.load_golden()
    now_ms = b.now_ms(b.GOLDEN_NOW)
    with dp.base_v11():
        dp.STARTED_RULE["on"] = True
        try:
            for sc in g["scenarios"]:
                py = b.py_extract(list(b.scenario_docs(sc["seed"], b.GOLDEN_NOW, sc["reversed"]).values()),
                                  now_ms, sc["counts"])
                js_calls = {r["key"]: r for r in sc["js"]["calls"]}
                started = {r["key"] for r in py["calls"] if r.get("passKind") == "started"}
                assert started
                assert [r["key"] for r in py["calls"]
                        if r["key"] not in started and not b.same(js_calls.get(r["key"]), r)] == []
                js_vals = {r["key"]: r for r in sc["js"]["values"]}
                assert set(js_vals) - {r["key"] for r in py["values"]} <= started
                assert all(b.same(js_vals.get(r["key"]), r) for r in py["values"])
        finally:
            dp.STARTED_RULE["on"] = False
