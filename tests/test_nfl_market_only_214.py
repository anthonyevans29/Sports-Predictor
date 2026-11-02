"""NFL MARKET-ONLY (ARCHITECT 2026-11-02 10:15 ET, addendum 214 items 2, 4(a) and 6).

Item 4(a), verbatim: "THE POLICY PR, small: the NFL family's Desk engine reads market-only — every NFL row's call is PASS
with the reason "nfl_elo_v1 uncertified (addendum 214): market-only until the confirmation read"; units 0; the model's
probabilities, divergence and quarantine fields stay on the page labelled uncertified (the confirmation's record);
shadow_units as today; the Cockpit shows the state as it shows NHL's. Tests pin: no NFL PLAY can be produced."

Pins: (1) a row that is a PLAY without the rule (edge over the floor, two-sided, no quarantine) is PASS, units 0, the
reason exactly the ruled text; (2) QB-flagged, empty-injury-list, big-edge, quarantined, started and no-reference rows are
PASS 0 with the same reason; (3) no NFL PLAY or units through the kalshi-only reference, a parlay leg or the venue engine;
(4) NHL, MLB and soccer rows are unchanged; (5) every shadow field of an NFL row is what it is without the rule (the
code main runs), the chain's call held for the record; (6) the Cockpit renders the kind, the hold, the NHL-style policy
line, the summary count and the Card's UNCERTIFIED state; (7) the NFL closing and slate pages carry no PLAY (the
closing page's one exception, addendum 217 item 4: the labelled "would-be PLAY (uncertified, unstaked)" record line,
never a call or an order); (8) the frozen golden battery changes only its NFL calls. The ruled reason is written out here, not imported, so the file runs
against main and fails there.
"""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from src.walters import desk_policy as dp
from src.walters.venue import kalshi_exec
from tests.test_closing_runs import box  # noqa: F401,E402  (the closing-run frame's fixture: the page tests below)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
MS = float((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))
REASON = "nfl_elo_v1 uncertified (addendum 214): market-only until the confirmation read"      # item 4(a), verbatim
PRE_GATE = "pre-gate sport: no production model — market display only"
STAKED = ("PLAY", "LADDER", "VENUE")
WOULD_BE = "would-be PLAY (uncertified, unstaked)"      # addendum 217 item 4, verbatim: the page's record-only line


def _rule_off():
    """The Desk as main runs it (this PR's switch off). On main itself the switch does not exist: nothing to turn off."""
    off = getattr(dp, "nfl_market_only_rule_off", None)
    if off is None:
        from contextlib import nullcontext
        return nullcontext()
    return off()


def at(minutes):
    return (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


def pred(home, p_home, fair_h, comp="NFL", *, when=300, books=9, bid=0.54, ask=0.55, **kw):
    """A two-way predictions row with Kalshi legs (no clock in the ticker) and the K-track quotes."""
    s = {"NFL": "KXNFLGAME", "MLB": "KXMLBGAME", "NHL": "KXNHLGAME"}[comp]
    r = {"home_team": home, "away_team": f"{home} away", "utc_date": at(when), "competition": comp,
         "stage": "regular",
         "kalshi_legs": {"HOME": {"ticker": f"{s}-26NOV02{home.upper()}-H", "bid": bid, "ask": ask},
                         "AWAY": {"ticker": f"{s}-26NOV02{home.upper()}-A", "bid": round(1 - ask, 2),
                                  "ask": round(1 - bid, 2)}},
         "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                        "tier": "lean"},
         "market": ({"bookmaker_count": books, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}}
                    if fair_h is not None else {"bookmaker_count": 0}),
         "input_quality": {"injuries": {"home": {"count": 2, "qb_listed": []}, "away": {"count": 3, "qb_listed": []}}}}
    r.update(kalshi_exec(bid, ask, comp, two_way=True))
    r.update(kw)
    return r


def soccer(home, probs, fair, **kw):
    r = {"home_team": home, "away_team": f"{home} away", "utc_date": at(300), "competition": "PL",
         "prediction": {"probabilities": dict(zip(("home_win", "draw", "away_win"), probs)), "tier": "lean"},
         "market": {"bookmaker_count": 8, "fair_prob": dict(zip(("HOME", "DRAW", "AWAY"), fair))}}
    r.update(kw)
    return r


def annotate(sport, rows):
    doc = {"sport": sport, "predictions": [json.loads(json.dumps(r)) for r in rows]}
    dp.annotate(doc, now=NOW)
    return doc


def desk(sport, *rows):
    return {r["home_team"]: r["desk"] for r in annotate(sport, rows)["predictions"]}


# The NFL battery: one row per path the Desk's chain can take for an NFL row.
def nfl_rows():
    qb = {"injuries": {"home": {"count": 1, "qb_listed": ["J. Starter"]}, "away": {"count": 2, "qb_listed": []}}}
    empty = {"injuries": {"home": {"count": 0, "qb_listed": []}, "away": {"count": 2, "qb_listed": []}}}
    return [
        pred("Play", 0.64, 0.55),                                                  # edge 9pp: a PLAY without the rule
        pred("NearFloor", 0.594, 0.55),                                            # edge 4.4pp: near-floor half units
        pred("Qb", 0.64, 0.55, input_quality=qb),                                  # QB-flagged half units
        pred("InjEmpty", 0.64, 0.55, input_quality=empty),                         # QB unread half units
        pred("Big", 0.72, 0.55),                                                   # 17pp: big-edge caution
        pred("Quar", 0.75, 0.55, market_divergence_pp=20.0, quarantine=True),      # quarantine shadow
        pred("Value", 0.55, 0.60),                                                 # the pick HOME -5pp; AWAY +5pp value
        pred("Floor", 0.56, 0.55),                                                 # below the floor
        pred("NoRef", 0.62, None, when=600),                                       # no book, before T-60
        pred("KalOnly", 0.64, None, when=30),                                      # kalshi-only reference (mid 0.545)
        pred("Started", 0.64, 0.55, when=-30),                                     # started
        pred("StartedValue", 0.55, 0.60, when=-30),                                # started, an AWAY value edge
        pred("ExecHalf", 0.605, 0.55),                                             # exec-halved PLAY (order at 1u)
    ]


HOMES = [r["home_team"] for r in nfl_rows()]


@pytest.fixture
def both():
    """Per test (never module scope): conftest's autouse pins (the unit folder, UNIT_PIN, the refused Kalshi fetch, the
    role) are function-scoped, and a module fixture would annotate before them, reading the live pool on today's ET
    date (review P1 on this PR)."""
    with _rule_off():
        off = desk("nfl", *nfl_rows())
    on = desk("nfl", *nfl_rows())
    return off, on


# ------------------------------------------------------------------------------------------- (1) and (2) --

def test_a_row_that_plays_without_the_rule_is_pass_units_0_with_the_ruled_reason(both):
    off, on = both
    assert (off["Play"]["call"], off["Play"]["units"]) == ("PLAY", 1)          # the PLAY main makes on this row
    d = on["Play"]
    assert (d["call"], d["units"], d["cls"]) == ("PASS", 0, "pass")
    assert d["reasons"] == [REASON] and d["reason"] == REASON
    assert d["order"] is None and d["pass_kind"] == "market_only"


@pytest.mark.parametrize("home", HOMES)
def test_every_nfl_row_is_pass_units_0_with_the_ruled_reason(both, home):
    d = both[1][home]
    assert (d["engine"], d["call"], d["units"], d["cls"]) == ("model_edge", "PASS", 0, "pass")
    assert d["reasons"] == [REASON] and d["reason"] == REASON and d["order"] is None
    assert "ladder_exec" not in d


def test_the_qb_injury_big_edge_and_quarantine_rows_were_calls_or_shadows_without_the_rule(both):
    off, _ = both
    assert (off["Qb"]["call"], off["Qb"]["units"]) == ("PLAY", 0.5) and "QB-flagged half units" in off["Qb"]["tags"]
    assert (off["InjEmpty"]["call"], off["InjEmpty"]["units"]) == ("PLAY", 0.5)
    assert "QB unread half units" in off["InjEmpty"]["tags"]
    assert (off["Big"]["call"], off["Big"]["units"], off["Big"]["cls"]) == ("PLAY", 0.5, "caution")
    assert (off["Quar"]["call"], off["Quar"]["shadow_units"]) == ("PASS", 0.5)
    assert off["KalOnly"]["call"] == "PLAY" and off["KalOnly"]["reference"] == "kalshi_only"
    assert off["Started"]["pass_kind"] == "started" and off["NoRef"]["pass_kind"] == "noref"
    assert off["StartedValue"]["pass_kind"] == "started" and off["StartedValue"]["value_shadow"] is None
    x = off["ExecHalf"]
    assert (x["call"], x["units"]) == ("PLAY", 0.5) and x["exec"]["order_contracts"] == 5 and "order_cost" in x["exec"]


# --------------------------------------------------------------------------------------------------- (3) --

def test_no_nfl_play_through_the_kalshi_only_reference(both):
    d = both[1]["KalOnly"]
    assert (d["call"], d["units"], d["reference"]) == ("PASS", 0, "kalshi_only")    # the reference stays the record's
    assert d["market_only_hold"]["would_call"] == "PLAY"


def test_no_nfl_parlay_leg():
    nfl = {"sport": "nfl", "predictions": [pred("A", 0.70, 0.60), pred("B", 0.72, 0.62), pred("C", 0.71, 0.61)]}
    mlb = {"sport": "mlb", "predictions": [pred("M1", 0.62, 0.57, "MLB"), pred("M2", 0.63, 0.58, "MLB")]}
    with _rule_off():
        before = dp.parlays_doc([("nfl.json", json.loads(json.dumps(nfl))), ("mlb.json", json.loads(json.dumps(mlb)))],
                                now=NOW)
    assert any(l["sport"] == "NFL" for t in before["tickets"] for l in t["legs"])       # main: NFL legs
    doc = dp.parlays_doc([("nfl.json", nfl), ("mlb.json", mlb)], now=NOW)
    assert not any(l["sport"] == "NFL" for t in doc["tickets"] for l in t["legs"])
    assert doc["live_legs"] == 2                                                         # the two MLB PLAYs
    calls = dp.evaluate(nfl, MS)["calls"]
    assert calls and all(c["call"] == "PASS" and c["units"] == 0 for _, c in calls)
    assert dp.rank_parlays(calls) == [] and dp.qb_shared_risk(calls, []) == []


def fixture_row(home="Kansas City Chiefs", away="Buffalo Bills"):
    """A market-only NFL fixtures row the venue engine would call without its holds (books vs Kalshi 7.15pp)."""
    return {"home_team": home, "away_team": away, "status": "scheduled", "utc_date": at(240),
            "market": {"bookmaker_count": 5, "fair_prob": {"HOME": 0.4735, "AWAY": 0.5265},
                       "captured_at": (NOW - timedelta(minutes=30)).replace(tzinfo=None).isoformat()},
            "kalshi": {"status": "two_sided", "prob": {"HOME": 0.545, "AWAY": 0.455}},
            "kalshi_legs": {"HOME": {"ticker": "KXNFLGAME-26NOV02BUFKC-KC", "bid": 0.53, "ask": 0.55},
                            "AWAY": {"ticker": "KXNFLGAME-26NOV02BUFKC-BUF", "bid": 0.44, "ask": 0.46}}}


def test_no_nfl_venue_call_whatever_the_quote_age_hold_does():
    with dp.quote_age_rule_off():
        with _rule_off():
            was = dp.annotate({"competition_code": "NFL", "fixtures": [fixture_row()]}, now=NOW)["fixtures"][0]["desk"]
        assert (was["call"], was["units"]) == ("VENUE", 0.25)                         # main, with the hold lifted
        d = dp.annotate({"competition_code": "NFL", "fixtures": [fixture_row()]}, now=NOW)["fixtures"][0]["desk"]
        w = dp.window_venue({**fixture_row(), "competition": "NFL", "engine": "market_only"}, MS)
    assert (d["engine"], d["call"], d["units"], d["order"]) == ("venue_edge", "PASS", 0, None)
    assert d["reason"] == "NFL market-only (addendum 214): no units, no position — no venue call"
    assert w["eligible"] is False and w["reason"] == d["reason"]
    d = dp.annotate({"competition_code": "NFL", "fixtures": [fixture_row()]}, now=NOW)["fixtures"][0]["desk"]
    assert (d["call"], d["units"]) == ("PASS", 0)                                       # with every hold as it is


def test_no_nfl_row_carries_a_staked_call_or_units_anywhere(both):
    for home, d in both[1].items():
        assert d["call"] not in STAKED and d["units"] == 0 and d["order"] is None, home
        assert d["venue"]["eligible"] is False, home


# --------------------------------------------------------------------------------------------------- (4) --

def test_nhl_mlb_and_soccer_rows_are_unchanged():
    def run():
        return {**desk("nhl", pred("Bruins", 0.75, 0.55, "NHL"), pred("NhlSmall", 0.61, 0.55, "NHL")),
                **desk("mlb", pred("MlbPlay", 0.62, 0.57, "MLB"), pred("MlbBig", 0.67, 0.55, "MLB")),
                **desk("soccer", soccer("SocPlay", (0.60, 0.22, 0.18), (0.52, 0.26, 0.22)))}
    with _rule_off():
        off = run()
    on = run()
    assert on == off
    assert on["Bruins"]["reasons"] == [PRE_GATE] and on["Bruins"]["call"] == "PASS"     # NHL's text, unchanged
    assert (on["MlbPlay"]["call"], on["SocPlay"]["call"]) == ("PLAY", "PLAY")            # a PLAY stays a PLAY
    assert on["MlbBig"]["call"] == "PASS" and on["MlbBig"]["shadow_units"] > 0           # the MLB quarantine stands
    assert not any("market_only_hold" in d for d in on.values())


# --------------------------------------------------------------------------------------------------- (5) --

SHADOW_FIELDS = ("edge_pp", "model_p", "market_ref", "reference", "tier", "pick", "shadow_units", "exec",
                 "value_shadow", "venue")


@pytest.mark.parametrize("home", HOMES)
def test_every_shadow_field_is_what_main_writes_and_the_chain_call_is_held(both, home):
    off, on = both
    a, b = off[home], on[home]
    for k in SHADOW_FIELDS:
        assert b[k] == a[k], (home, k)
    assert b["tags"] == a["tags"] + ["market-only: nfl_elo_v1 uncertified (addendum 214)"]
    h = b["market_only_hold"]
    assert (h["would_call"], h["would_units"], h["would_cls"], h["would_pass_kind"]) == (
        a["call"], a["units"], a["cls"], a["pass_kind"])
    assert h["would_reasons"] == a["reasons"] and h["would_reason"] == a["reason"] and h["staked"] is False
    assert h["certification"] == "uncertified"


def test_the_shadows_go_on(both):
    off, on = both
    assert dp.is_quarantine_shadow({"call": on["Quar"]["call"], "shadowUnits": on["Quar"]["shadow_units"],
                                    "tags": on["Quar"]["tags"]})
    from deploy.hosting import closing
    from src.walters.window import desk_quarantined
    assert closing.is_quarantine_shadow(on["Quar"]) and desk_quarantined(on["Quar"])
    v = on["Value"]["value_shadow"]
    assert v is not None and v["side"] == "AWAY" and v["staked"] is False and v["units"] == 0.25
    assert on["Started"]["value_shadow"] is None and on["Started"]["exec"] is None       # as main: no decision
    assert on["StartedValue"]["value_shadow"] is None and on["StartedValue"]["exec"] is None   # never a started shadow
    x = on["ExecHalf"]["exec"]                                       # priced as the chain sized it (0.5u: 5 contracts)
    assert x["order_contracts"] == 5 and x["order_cost"] == both[0]["ExecHalf"]["exec"]["order_cost"]
    assert on["Play"]["exec"] is not None and on["Play"]["exec"]["fee_clears"] is True   # the record's exec edge


def test_desk_meta_says_the_rule_is_on_and_the_golden_runs_without_it():
    doc = annotate("nfl", [pred("Play", 0.64, 0.55)])
    assert doc["desk_meta"]["nfl_market_only_rule"] is True
    assert doc["desk_meta"]["policy_version"] == "v1.2"                       # not bumped: the architect's question
    with dp.base_v11():
        d = desk("nfl", pred("Play", 0.64, 0.55))["Play"]
    assert d["call"] == "PLAY"


def test_rescore_names_a_published_nfl_play_as_market_only():
    with _rule_off():
        doc = annotate("nfl", [pred("Play", 0.64, 0.55)])
    assert doc["predictions"][0]["desk"]["call"] == "PLAY"
    (x,) = dp.rescore(doc)
    assert (x["addendum_call"], x["addendum_units"], x["verdict"], x["pass_reason"]) == (
        "PASS", 0, "nfl market-only", REASON)


def test_the_export_carries_the_uncertified_label(tmp_path):
    from src.db.database import init_db
    from src.walters.nfl_predict import export_nfl_predictions
    init_db()
    doc = json.loads(open(export_nfl_predictions(out_dir=str(tmp_path), desk=False)).read())
    assert doc["certification"].startswith("uncertified (addendum 214)")
    assert doc["note"].startswith("UNCERTIFIED (addendum 214)") and "LIVE: gate-passed" not in doc["note"]
    assert "CONTRACT RULE: rows whose market_divergence_pp has an absolute value of 15 or more carry quarantine=true" \
        in doc["note"]                                                       # addendum 208's clause stays verbatim
    for k in ("model_version", "contains_predictions", "rehearsal", "live_since", "predictions"):
        assert k in doc                                                      # additive: nothing renamed or removed


# --------------------------------------------------------------------------------------------------- (6) --

def _cockpit():
    return open(os.path.join(ROOT, "tools", "cockpit.html"), encoding="utf-8").read()


def _fn(html, name):
    m = re.search(r"^function " + name + r"\(.*?^\}", html, re.S | re.M)
    assert m, name
    return m.group(0)


def test_the_cockpit_shows_nfl_as_it_shows_nhl():
    html = _cockpit()
    assert re.search(r"<b>NHL</b> — PASS all <span[^>]*>\(pre-gate: no production model\)</span>", html)
    assert re.search(r"<b>NFL</b> — PASS all <span[^>]*>\(market-only since 2026-11-02, addendum 214: nfl_elo_v1 "
                     r"uncertified until the confirmation read\)</span>", html)
    assert 'k==="market_only"' in _fn(html, "passKindTag")
    pol = _fn(html, "policy")
    assert "mktOnlyHoldHTML(r.fileDesk.market_only_hold)" in pol and 'passKind==="market_only"' in pol
    assert 'reasons.join(" · ")' in pol                                     # the ruled reason, rendered from the file


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_cockpit_renders_the_file_call_reason_kind_and_hold_in_node(tmp_path, both):
    html = _cockpit()
    d = both[1]["Qb"]
    js = "\n".join([_fn(html, "esc"), _fn(html, "passKindTag"), _fn(html, "mktOnlyHoldHTML"), _fn(html, "fileCall"),
                    f"const r={{fileDesk:{json.dumps(d)}}};",
                    "const c=fileCall(r);",
                    "console.log(JSON.stringify([c.call,c.units,c.reasons.join(' · '),c.passKind,"
                    "passKindTag(c.passKind),mktOnlyHoldHTML(r.fileDesk.market_only_hold),mktOnlyHoldHTML(null)]));"])
    f = tmp_path / "m.js"
    f.write_text(js)
    out = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    assert out[:4] == ["PASS", 0, REASON, "market_only"]
    assert out[4] == '<span class="passkind">market-only · uncertified</span>'
    assert out[5].startswith('<div class="note">hold (record only, not a call; uncertified): the chain&#39;s call PLAY 0.5u')\
        or out[5].startswith('<div class="note">hold (record only, not a call; uncertified): the chain\'s call PLAY 0.5u')
    assert "QB-flagged (J. Starter) → half units" in out[5] and out[6] == ""


# ------------------------------------------------------------------- the pages, rule ON (review P2 on this PR) --
# What the operator reads and places from: the closing page and the slate page, on the closing-run frame
# (tests/test_closing_runs.py's box: a scratch schedule, every step, page and push faked, the network blocked), with the
# production default (the rule on). Item 2: the MNF page is "read for the record and NOT PLACED".

def test_the_nfl_closing_page_has_no_play_line_and_keeps_the_shadow_lines(box):
    from tests.test_closing_runs import MACHINE, NOW as C_NOW, at, mc, runs
    assert all(p["desk"]["call"] == "PASS" and p["desk"]["units"] == 0 for p in box.docs["NFL"]["predictions"])
    assert mc.run("NFL", start=at(35), now=C_NOW) == 0
    pg = box.pages[-1]
    lines = pg["body"].splitlines()
    assert lines[0] == "NFL 13:00 ET · T-35m" and lines[-1] == MACHINE
    assert not any(" · PLAY " in x or "BUY YES" in x or "BUY NO" in x for x in lines), lines   # no placed call
    # nor its hold: the only PLAY on the page is addendum 217 item 4's labelled would-be line (the record, never a call)
    assert not any(re.search(r"\bPLAY\b", x) and WOULD_BE not in x for x in lines), lines
    assert lines == [                      # rule off, the same run pages "PLAY Buffalo 1u · BUY YES ..." (test_c5)
        "NFL 13:00 ET · T-35m",
        "Buffalo Visitors @ Buffalo · would-be PLAY (uncertified, unstaked) Buffalo 1u · exec +5.3pp",
        "  QB inputs clean · record only, not placed",
        "Tampa Visitors @ Tampa · value shadow Tampa Visitors 0.25u · edge +10.0pp · exec +7.5pp",
        "  shadow, not staked",
        "Newark Visitors @ Newark · quarantine shadow Newark 0.5u · edge +20.0pp · exec +18.2pp",
        "  shadow, not staked",
        "PASS: 4 games", MACHINE]
    assert pg["priority"] == "default"                                                 # no PLAY: never high
    assert all(d["call"] == "PASS" for d in runs("NFL")[-1]["desk_rows"])


def test_the_nfl_slate_page_reads_play_0(box, monkeypatch):
    from tests.test_slate_run import MACHINE, NFL_FILE, et, slate_pages, slates, the_day, tick
    the_day(box, monkeypatch)
    assert [p["desk"]["call"] for p in box.docs["NFL"]["predictions"]] == ["PASS", "PASS"]
    assert tick(et(7, 0)) == 0
    (s,) = slates()
    assert (s["rows"], s["calls"]) == (2, {"PLAY": 0, "PASS": 2})
    (pg,) = slate_pages(box)
    assert pg["body"] == f"SLATE NFL 2026-10-18: 2 rows · PLAY 0 · PASS 2 · {NFL_FILE}\n{MACHINE}"
    doc = json.loads((box.repo / NFL_FILE).read_text())
    assert [p["desk"]["pass_kind"] for p in doc["predictions"]] == ["market_only", "market_only"]
    assert doc["predictions"][0]["desk"]["market_only_hold"]["would_call"] == "PLAY"   # the record, never the page


# ----------------------------------------------------------- the frozen golden, rule ON (review nit on this PR) --

def test_golden_battery_only_nfl_rows_change_with_the_rule_on():
    """The frozen golden holds with the rule off (tests/test_desk_golden.py, base_v11()). With it ON, as
    test_desk_started_rule's golden test does for its rule: every non-NFL call, value and venue row is the frozen JS
    exactly; every NFL call is PASS 0 with the ruled reason, its shadow fields (edge, shadow units, reference, exec) the
    frozen JS's; the NFL value and venue rows unchanged."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import desk_battery as b
    g = b.load_golden()
    now_ms = b.now_ms(b.GOLDEN_NOW)
    turned = 0
    with dp.base_v11():
        dp.NFL_MARKET_ONLY_RULE["on"] = True
        try:
            for sc in g["scenarios"]:
                docs = list(b.scenario_docs(sc["seed"], b.GOLDEN_NOW, sc["reversed"]).values())
                sport = {f"{r['game']}|{r['utc']}": r["sport"] for d in docs
                         for part in ("calls", "venue") for r, _ in dp.evaluate(d, now_ms, sc["counts"])[part]}
                py = b.py_extract(docs, now_ms, sc["counts"])
                pairs = list(zip(sc["js"]["calls"], py["calls"]))                    # row for row, as the golden
                assert len(sc["js"]["calls"]) == len(py["calls"]) and all(j["key"] == r["key"] for j, r in pairs)
                nfl = [(j, r) for j, r in pairs if sport[r["key"]] == "NFL"]
                assert nfl and len(nfl) < len(pairs)
                assert [r["key"] for j, r in pairs if sport[r["key"]] != "NFL" and not b.same(j, r)] == []
                for j, r in nfl:
                    turned += j["call"] != "PASS"
                    assert (r["call"], r["units"], r["cls"], r["reasons"], r["passKind"]) == (
                        "PASS", 0, "pass", [REASON], "market_only"), r["key"]
                    assert all(b.same(j[k], r[k]) for k in ("edge", "shadowUnits", "mktRef", "kalOnly", "exec")), r["key"]
                    assert r["tags"] == j["tags"] + ["market-only: nfl_elo_v1 uncertified (addendum 214)"], r["key"]
                for part in ("values", "venue"):
                    assert b.golden_diffs(sc["js"][part], py[part]) == [], part
        finally:
            dp.NFL_MARKET_ONLY_RULE["on"] = False
    assert turned > 0                                       # the battery holds NFL calls the rule turns PASS


def _node(tmp_path, *lines):
    f = tmp_path / "c.js"
    f.write_text("\n".join(lines))
    return json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_cockpit_summary_counts_market_only_rows_once(tmp_path):
    """The Desk summary's PASS breakdown (review nit on this PR): N market-only NFL rows read 'N market-only (NFL,
    uncertified)', never also as 'other'; the other kinds as before."""
    html = _cockpit()
    assert "passSummary({passes,passNoRef,passFloor,passStarted,passShadow,passKoSusp,passMktOnly})" in _fn(html,
                                                                                                           "policy")
    z = dict(passes=0, passNoRef=0, passFloor=0, passStarted=0, passShadow=0, passKoSusp=0, passMktOnly=0)
    cases = [z, {**z, "passes": 11, "passMktOnly": 11}, {**z, "passes": 5, "passNoRef": 1, "passMktOnly": 3},
             {**z, "passes": 5, "passNoRef": 3, "passFloor": 1}]
    out = _node(tmp_path, _fn(html, "passSummary"), f"console.log(JSON.stringify({json.dumps(cases)}.map(passSummary)));")
    assert out == ["", " (0 no reference · 0 below floor · 11 market-only (NFL, uncertified))",
                   " (1 no reference · 0 below floor · 3 market-only (NFL, uncertified) · 1 other)",
                   " (3 no reference · 1 below floor · 1 other)"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_cockpit_card_shows_nfl_uncertified_not_live(tmp_path, both):
    """4(a) "the Cockpit shows the state as it shows NHL's" on the Card view too (review P2 on this PR): a sport whose
    rows are PASS market_only, or whose file carries `certification`, is never LIVE; each game says uncertified shadow,
    not placed, with the file's reason; a live certified sport (MLB) and an internal one keep their chips."""
    html = _cockpit()
    card = _fn(html, "renderCard")
    assert "cardChip(rs)" in card and "cardUncertified(r)" in card and "cardUncertifiedWhy(r)" in card
    assert 'const live=rs.some(r=>r.live)' not in card
    for k in ("rehearsal===false", "cert:doc.certification??null"):
        assert k in html
    rows = [{"live": True, "fileDesk": both[1]["Qb"], "cert": None},                    # the Desk's block alone
            {"live": True, "fileDesk": None, "cert": "uncertified (addendum 214): ..."},  # the export's label alone
            {"live": True, "fileDesk": {"call": "PLAY", "units": 1, "pass_kind": None}, "cert": None},
            {"live": False, "fileDesk": {"call": "PASS", "units": 0, "pass_kind": "floor"}, "cert": None}]
    out = _node(tmp_path, _fn(html, "cardUncertified"), _fn(html, "cardUncertifiedWhy"), _fn(html, "cardChip"),
                f"const R={json.dumps(rows)};",
                "console.log(JSON.stringify([cardChip([R[0],R[2]]),cardChip([R[1]]),cardChip([R[2]]),cardChip([R[3]]),"
                "R.map(cardUncertified),cardUncertifiedWhy(R[0]),cardUncertifiedWhy(R[1])]));")
    assert out[:4] == ["UNCERTIFIED · market-only", "UNCERTIFIED · market-only", "LIVE", "internal"]
    assert out[4] == [True, True, False, False]
    assert out[5] == f"uncertified shadow, not placed: Desk PASS 0u — {REASON}"
    assert out[6] == "uncertified shadow, not placed: Desk PASS 0u — uncertified (addendum 214): ..."
