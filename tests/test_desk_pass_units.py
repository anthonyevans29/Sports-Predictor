"""#181 and #418 (ARCHITECT 2026-10-17 10:40 ET, addendum 112 items 9 and 11, RULED; 16:55 ET, addendum 117 item 2).

Item 9, verbatim: "#181 — Desk v1.1 NHL (pre-gate) PASS rows with edge ≥ 15pp carry units 0.5 / class caution (display
wart). RULED: a PASS row carries units 0 and class pass, every sport; golden updated for exactly those rows and the diff
pasted in the PR."

Item 11, verbatim: "#418 — desk-parlays desk_meta carries kalshi_leg_guard. RULED: yes, the same field the --desk
exports carry; test."

Addendum 117 item 2, verbatim: "#181 + #418 — the four:
 a. The stale "caution" text on the eight NHL rows is replaced by the pass text (reason as the Desk gives it); nothing
    else on those rows changes.
 b. Policy stays v1.1. This is a display defect, not a Desk-rule change; POLICY_VERSION moves only with #86.
 c. Venue rows: the same rule — a PASS venue row is 0 units / class pass. Every PASS, every engine.
 d. The golden's capture metadata is left as it is; the PR body lists the eight changed rows by match id with
    before/after, and says the metadata is untouched."
"""
import os
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import pytest

from src.walters import desk_policy as dp
from src.walters import kalshi_legs as kl
from src.walters import venue_quote_age as vqa
from src.walters.venue import kalshi_exec

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import desk_battery as b  # noqa: E402

NOW = datetime(2026, 10, 17, 17, 0, tzinfo=timezone.utc)
PRE_GATE = "pre-gate sport: no production model — market display only"
CAUTION_REASON = "edge ≥ 15pp → market-is-right caution (cohort: big edges historically anti-predictive)"
CAUTION_TAG = "big-edge caution half units"
POLICIES = [pytest.param(nullcontext, id="current"), pytest.param(dp.base_v11, id="base_v11")]


def at(minutes):
    return (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


def pred(home, p_home, fair_h, comp, *, when=30, books=9, **kw):
    """A two-way predictions row with Kalshi legs (no clock in the ticker) and the K-track quotes."""
    s = dp.KALSHI_ONLY["series"].get(comp) or {"NHL": "KXNHLGAME"}.get(comp, "KXTEST")
    r = {"home_team": home, "away_team": f"{home} away", "utc_date": at(when), "competition": comp,
         "stage": "regular",
         "kalshi_legs": {"HOME": {"ticker": f"{s}-26OCT17{home.upper()}-H", "bid": 0.54, "ask": 0.55},
                         "AWAY": {"ticker": f"{s}-26OCT17{home.upper()}-A", "bid": 0.44, "ask": 0.45}},
         "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                        "tier": "lean"},
         "market": ({"bookmaker_count": books, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}}
                    if fair_h is not None else {"bookmaker_count": 0})}
    r.update(kalshi_exec(0.54, 0.55, comp, two_way=True))
    r.update(kw)
    return r


def soccer(home, probs, fair, **kw):
    r = {"home_team": home, "away_team": f"{home} away", "utc_date": at(300), "competition": "PL",
         "prediction": {"probabilities": dict(zip(("home_win", "draw", "away_win"), probs))},
         "market": {"bookmaker_count": 8, "fair_prob": dict(zip(("HOME", "DRAW", "AWAY"), fair))}}
    r.update(kw)
    return r


def desk(sport, *rows):
    doc = {"sport": sport, "predictions": list(rows)}
    dp.annotate(doc, now=NOW)
    return {r["home_team"]: r["desk"] for r in doc["predictions"]}


@pytest.mark.parametrize("policy", POLICIES)
def test_a_pre_gate_pass_with_an_edge_of_15pp_or_more_carries_units_0_and_class_pass(policy):
    with policy():
        d = desk("nhl", pred("Bruins", 0.75, 0.55, "NHL"), pred("Edge15", 0.65, 0.50, "NHL"))
    for k, edge in (("Bruins", 20.0), ("Edge15", 15.0)):
        assert (d[k]["call"], d[k]["units"], d[k]["cls"]) == ("PASS", 0, "pass")          # was 0.5 / caution
        assert abs(d[k]["edge_pp"] - edge) < 1e-9 and d[k]["pass_kind"] is None
        assert d[k]["order"] is None and d[k]["shadow_units"] == 0 and d[k]["value_shadow"] is None
        # addendum 117 item 2(a): the caution's reason and tag are gone (were: the caution line after the pre-gate line,
        # and its tag); the row carries the pre-gate line as the Desk gives it, and its "edge ≥ floor" tag stays
        assert d[k]["reasons"] == [PRE_GATE] and d[k]["reason"] == PRE_GATE
        assert d[k]["tags"] == ["edge ≥ floor"]
        assert not any("caution" in x for x in d[k]["reasons"] + d[k]["tags"])


@pytest.mark.parametrize("policy", POLICIES)
def test_a_quarantine_shadow_keeps_the_cautions_size_and_tag(policy):
    """A row the quarantine turns PASS is still a PLAY when the caution runs: its shadow is sized by it (0.5u) and keeps
    its tag; its reasons were already only the QUARANTINE line. Unchanged by addendum 117."""
    with policy():
        q = desk("nfl", pred("NflQuar", 0.75, 0.55, "NFL", market_divergence_pp=20.0, quarantine=True))["NflQuar"]
    assert (q["call"], q["units"], q["cls"], q["shadow_units"]) == ("PASS", 0, "pass", 0.5)
    assert q["tags"] == ["edge ≥ floor", CAUTION_TAG, "quarantine ≥ 15pp (shadow)"]
    assert q["reasons"] == ["QUARANTINE 20pp — contract: never a straight play"]


@pytest.mark.parametrize("policy", POLICIES)
def test_every_pass_path_in_every_sport_carries_units_0_and_class_pass(policy):
    with policy():
        nhl = desk("nhl", pred("NhlSmall", 0.61, 0.55, "NHL"))                              # pre-gate, 6pp
        nfl = desk("nfl", pred("NflQuar", 0.75, 0.55, "NFL", market_divergence_pp=20.0, quarantine=True),
                   pred("NflNoRef", 0.62, None, "NFL", when=600),                          # no book, before T-60
                   pred("NflStarted", 0.62, 0.55, "NFL", when=-30))
        mlb = desk("mlb", pred("MlbFloor", 0.57, 0.55, "MLB"), pred("MlbBig", 0.67, 0.55, "MLB"))
        soc = desk("soccer", soccer("SocPMin", (0.25, 0.30, 0.45), (0.20, 0.30, 0.50)),
                   soccer("SocDefault", (0.60, 0.25, 0.15), (0.50, 0.28, 0.22),
                          input_quality={"rating_source": {"home": "default", "away": "model"}}))
    rows = {**nhl, **nfl, **mlb, **soc}
    for k, d in rows.items():
        if d["call"] == "PASS":
            assert (d["units"], d["cls"]) == (0, "pass"), (k, d["units"], d["cls"], d["reasons"])
    assert rows["NflQuar"]["call"] == "PASS" and rows["NflQuar"]["shadow_units"] == 0.5     # the shadow keeps its size
    assert rows["NflNoRef"]["pass_kind"] == "noref" and rows["MlbFloor"]["pass_kind"] == "floor"
    assert rows["SocPMin"]["pass_kind"] == "floor"
    if policy is nullcontext:                                                               # rules off in base_v11
        assert rows["NflStarted"]["pass_kind"] == "started"
        assert rows["MlbBig"]["call"] == "PASS" and rows["MlbBig"]["shadow_units"] > 0      # MLB > 8pp quarantine
    assert rows["SocDefault"]["pass_kind"] == "default_rating"


@pytest.mark.parametrize("policy", POLICIES)
def test_the_battery_has_no_pass_row_with_units_a_class_or_the_caution_text_other_than_pass(policy):
    """Every seeded scenario of the golden battery: no PASS call carries units or a non-pass class, and no pre-gate PASS
    carries the caution's reason or tag. Under base_v11 the golden's eight pre-gate rows (edge ≥ 15pp) are among them.
    The caution tag stays only on quarantine shadows (sized by it; reasons = the QUARANTINE line)."""
    pre_gate_big = quarantine_caution = 0
    with policy():
        for _, seed, counts, rev in b.SCENARIOS:
            for doc in b.scenario_docs(seed, b.GOLDEN_NOW, rev).values():
                for r, c in dp.evaluate(doc, b.now_ms(b.GOLDEN_NOW), counts)["calls"]:
                    if c["call"] != "PASS":
                        continue
                    assert (c["units"], c["cls"]) == (0, "pass"), (r["game"], c)
                    assert CAUTION_REASON not in c["reasons"], (r["game"], c)
                    if c["reasons"][:1] == [PRE_GATE]:
                        assert CAUTION_TAG not in c["tags"], (r["game"], c)
                        pre_gate_big += c["edge"] >= 15
                    elif CAUTION_TAG in c["tags"]:
                        assert c["shadowUnits"] > 0 and c["reasons"][0].startswith("QUARANTINE"), (r["game"], c)
                        quarantine_caution += 1
    assert pre_gate_big == (8 if policy is dp.base_v11 else 5)       # current policy: three of the eight have started
    assert quarantine_caution == (3 if policy is dp.base_v11 else 1)


def fx(home, *, fair=(0.4735, 0.5265), kal=(0.545, 0.455), books=5, kickoff_min=240):
    """A market-only fixtures row (the venue engine's input): books vs Kalshi, captured 30 minutes before NOW."""
    f = {"home_team": home, "away_team": f"{home} away", "status": "scheduled", "utc_date": at(kickoff_min),
         "market": {"bookmaker_count": books, "fair_prob": {"HOME": fair[0], "AWAY": fair[1]},
                    "captured_at": at(-30)},
         "kalshi": {"status": "two_sided", "prob": {"HOME": kal[0], "AWAY": kal[1]}} if kal else None,
         "kalshi_legs": {"HOME": {"ticker": f"KXNHLGAME-26OCT17{home.upper()}-H", "bid": 0.53, "ask": 0.55},
                         "AWAY": {"ticker": f"KXNHLGAME-26OCT17{home.upper()}-A", "bid": 0.44, "ask": 0.46}}}
    return f


def venue_desk(*rows, code="NHL"):
    doc = dp.annotate({"competition_code": code, "fixtures": list(rows)}, now=NOW)
    return {f["home_team"]: f["desk"] for f in doc["fixtures"]}


@pytest.mark.parametrize("hold", [True, False])
def test_a_pass_venue_row_carries_units_0_and_class_pass_and_a_venue_row_no_class(hold, monkeypatch):
    """Addendum 117 item 2(c): every PASS venue row (the quote-age hold, below floor, single venue, books < 4, in-play)
    reads units 0 / cls pass; a VENUE row carries no cls, as it never did. The venue sub-block is unchanged."""
    rows = (fx("Held"), fx("Floor", fair=(0.55, 0.45), kal=(0.54, 0.46)), fx("Single", kal=None),
            fx("Thin", books=3), fx("InPlay", kickoff_min=-10))
    with (nullcontext() if hold else dp.quote_age_rule_off()):
        d = venue_desk(*rows)
    for k in ("Floor", "Single", "Thin", "InPlay") + (("Held",) if hold else ()):
        assert (d[k]["engine"], d[k]["call"], d[k]["units"], d[k]["cls"]) == ("venue_edge", "PASS", 0, "pass"), k
        assert d[k]["order"] is None and "cls" not in d[k]["venue"]
        assert list(d[k])[:4] == ["engine", "call", "units", "cls"]
        assert vqa.desk_ok(d[k])                          # the venue receipts read the block unchanged
    if not hold:
        v = d["Held"]
        assert (v["call"], v["units"], v["pass_kind"]) == ("VENUE", 0.25, None) and "cls" not in v
        assert v["order"]["text"].startswith("BUY YES KXNHLGAME-26OCT17HELD-A") and vqa.desk_ok(v)
    assert d["Single"]["reason"] == "single venue — no pair" and d["InPlay"]["reason"] == "in-play — never"


def test_a_venue_pass_row_before_the_engine_carries_class_pass_too():
    """The stops before the computation (CL skew test, a shadow league) are PASS venue rows: the same rule."""
    assert (venue_desk(fx("Cl"), code="CL")["Cl"]["cls"], venue_desk(fx("Pd"), code="PD")["Pd"]["cls"]) == ("pass",) * 2


def test_a_play_rows_sizing_is_unchanged(monkeypatch):
    d = desk("nfl", pred("Play1u", 0.62, 0.55, "NFL"), pred("Big16", 0.71, 0.55, "NFL"))
    assert (d["Play1u"]["call"], d["Play1u"]["units"], d["Play1u"]["cls"]) == ("PLAY", 1, "play")
    # the same big-edge caution on a PLAY row still halves it and marks it caution
    assert (d["Big16"]["call"], d["Big16"]["units"], d["Big16"]["cls"]) == ("PLAY", 0.5, "caution")
    assert "big-edge caution half units" in d["Big16"]["tags"] and d["Big16"]["order"]["contracts"] == 5
    s = desk("soccer", soccer("Ladder", (0.20, 0.25, 0.55), (0.35, 0.25, 0.40)))["Ladder"]
    assert (s["call"], s["units"], s["cls"]) == ("LADDER", 0.5, "caution")      # 15pp ≥ soccer's 10pp caution


@pytest.mark.parametrize("on", [True, False])
def test_the_parlays_doc_carries_the_kalshi_leg_guard_as_the_desk_exports_do(monkeypatch, on):
    monkeypatch.setitem(kl.GUARD, "on", on)
    named = [("nfl.json", {"sport": "nfl", "predictions": [pred("Chiefs", 0.64, 0.55, "NFL")]})]
    export = {"sport": "nfl", "predictions": [pred("Chiefs", 0.64, 0.55, "NFL")]}
    dp.annotate(export, now=NOW)
    meta = dp.parlays_doc(named, now=NOW)["desk_meta"]
    assert meta["kalshi_leg_guard"] is export["desk_meta"]["kalshi_leg_guard"] is on
