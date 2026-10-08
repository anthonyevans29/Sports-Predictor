"""MLB BIG-EDGE QUARANTINE (ARCHITECT 2026-10-07, GATE-CLASS, effective with the 2026-10-07 slate):
"an MLB row whose edge against its reference is above 8pp is QUARANTINED: never a straight play, logged as a
quarantine shadow at the size it would have staked (the NFL contract, at 8pp for MLB). The MLB 15pp caution tier is
superseded. The 4pp floor and the rest of v1.1 stand."
The edge is the Desk's own, so the book and the kalshi-only reference quarantine alike; the postseason and
kalshi-only multipliers size shadow_units as they would have sized units. base_v11() keeps the frozen golden."""
from datetime import datetime, timedelta, timezone

from src.walters import desk_policy as dp

NOW = datetime(2026, 10, 7, 18, 0, tzinfo=timezone.utc)
NOW_MS = float((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))


def row(home, p_home, *, fair_h=None, bid=None, ask=None, when=30, stage="regular", comp="MLB", **kw):
    mk = {"bookmaker_count": 9 if fair_h is not None else 0}
    if fair_h is not None:
        mk["fair_prob"] = {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}
    r = {"home_team": home, "away_team": f"{home} away", "utc_date": (NOW + timedelta(minutes=when)).strftime(
            "%Y-%m-%dT%H:%M:%S"), "competition": comp, "stage": stage,
         "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                        "tier": "lean"},
         "market": mk, "kalshi_bid": bid, "kalshi_ask": ask}
    r.update(kw)
    return r


def calls(*rows, sport="mlb", counts=None):
    ev = dp.evaluate({"sport": sport, "predictions": list(rows)}, NOW_MS, counts)
    return {r["home"]: c for r, c in ev["calls"]}


def test_exactly_8pp_plays_and_above_8pp_quarantines():
    c = calls(row("Eight", 0.58, fair_h=0.50),                    # 7.999…: plays
              row("EightNoise", 0.63, fair_h=0.55),               # 8.000000000000007: exactly 8.00 plays
              row("EightOne", 0.581, fair_h=0.50))                # 8.1: quarantined
    assert c["Eight"]["call"] == "PLAY" and c["EightNoise"]["call"] == "PLAY"
    q = c["EightOne"]
    assert (q["call"], q["units"], q["shadowUnits"]) == ("PASS", 0, 1)
    assert q["tags"][-1] == "quarantine > 8pp (shadow)" and q["passKind"] is None      # tags accumulate, as NFL
    assert q["reasons"] == ["QUARANTINE edge 8.1pp > 8pp vs the book close — MLB big-edge quarantine, "
                            "ARCHITECT 2026-10-07: never a straight play (shadow at 1u)"]


def test_the_15pp_caution_tier_is_superseded_shadow_at_full_size():
    q = calls(row("Huge", 0.72, fair_h=0.55))["Huge"]             # +17pp: was caution half, now a 1u shadow
    assert (q["call"], q["shadowUnits"]) == ("PASS", 1) and not any("caution" in t for t in q["tags"])


def test_multipliers_size_the_shadow_as_they_would_have_sized_units():
    rows = (row("Post", 0.70, fair_h=0.55, stage="postseason"),                 # postseason half (0/30)
            row("KO", 0.60, bid=0.49, ask=0.50),                               # kalshi-only mid 0.495: +10.5pp
            row("KOPost", 0.60, bid=0.49, ask=0.50, stage="postseason"),       # 0.5 × 0.5
            row("PostDone", 0.70, fair_h=0.55, stage="postseason"))
    # the kalshi-only sizing is the 2026-10-01 path: since Q3 (ARCHITECT 2026-10-08) an MLB row on a kalshi-only
    # reference is PASS with no shadow units, so the multiplier is read with the suspension off
    with dp.kalshi_only_suspension_off():
        c = calls(*rows, counts=None)
    assert (c["Post"]["call"], c["Post"]["shadowUnits"]) == ("PASS", 0.5)
    assert (c["KO"]["call"], c["KO"]["shadowUnits"], c["KO"]["kalOnly"]) == ("PASS", 0.5, True)
    assert "vs the kalshi-only mid" in c["KO"]["reasons"][0]
    assert (c["KOPost"]["call"], c["KOPost"]["shadowUnits"]) == ("PASS", 0.25)
    q3 = calls(*rows, counts=None)                                             # Q3 K1: no shadow units at all
    assert (q3["KO"]["call"], q3["KO"]["shadowUnits"], q3["KO"]["passKind"]) == ("PASS", 0, "kalshi_only_suspended")
    assert q3["Post"] == c["Post"]                                             # a book row is untouched
    full = calls(row("PostDone", 0.70, fair_h=0.55, stage="postseason"), counts={"postseason_graded": 30})
    assert full["PostDone"]["shadowUnits"] == 1


def test_floor_and_moderate_band_unchanged_and_other_sports_untouched():
    c = calls(row("Floor", 0.58, fair_h=0.56),                    # +2pp: PASS floor, as before
              row("Mid", 0.60, fair_h=0.54))                      # +6pp: a play, as before
    assert c["Floor"]["passKind"] == "floor" and c["Mid"]["call"] == "PLAY"
    nfl = row("KC", 0.66, fair_h=0.55, comp="NFL")                # +11pp NFL, not divergence-quarantined
    assert calls(nfl, sport="nfl")["KC"]["call"] == "PLAY"


def test_base_v11_keeps_the_old_behaviour_for_the_goldens():
    with dp.base_v11():
        c = calls(row("Nine", 0.65, fair_h=0.56), row("Huge", 0.72, fair_h=0.55))
    assert (c["Nine"]["call"], c["Nine"]["units"]) == ("PLAY", 1)
    assert (c["Huge"]["call"], c["Huge"]["units"], c["Huge"]["cls"]) == ("PLAY", 0.5, "caution")
    assert dp.MLB_QUARANTINE["on"] is True                         # restored on exit


def test_desk_block_is_a_quarantine_shadow_with_no_order():
    doc = {"sport": "mlb", "predictions": [row("Q", 0.66, fair_h=0.55, bid=0.53, ask=0.54)]}
    dp.annotate(doc, now=NOW)
    d = doc["predictions"][0]["desk"]
    assert (d["call"], d["units"], d["shadow_units"], d["order"]) == ("PASS", 0, 1, None)
    assert "quarantine > 8pp (shadow)" in d["tags"] and "MLB big-edge quarantine" in d["reason"]
    assert doc["desk_meta"]["mlb_quarantine_above_pp"] == 8.0
    with dp.base_v11():
        doc2 = {"sport": "mlb", "predictions": [row("Q", 0.66, fair_h=0.55)]}
        dp.annotate(doc2, now=NOW)
    assert doc2["desk_meta"]["mlb_quarantine_above_pp"] is None


def test_desk_rescore_holds_the_quarantine_constant_and_never_calls_it_halved(tmp_path):
    """Codex on #328 (P1): desk-rescore's "before" side ran under base_v11(), which also turned MLB_QUARANTINE
    off, so a pre-rule MLB >8pp PLAY that the current Desk quarantines read as "halved by #87". The before side
    now holds the quarantine policy constant (addendum_off); the quarantine transition is its own verdict/line."""
    import json

    from click.testing import CliRunner

    import cli
    doc = {"sport": "mlb", "predictions": [row("Big", 0.65, fair_h=0.56),               # +9pp: pre-rule PLAY 1u
                                           row("Mid", 0.62, fair_h=0.56)]}              # +6pp, no quote: #87 half
    with dp.base_v11():                                            # published before the 2026-10-07 rule
        dp.annotate(doc, now=NOW)
    assert [p["desk"]["call"] for p in doc["predictions"]] == ["PLAY", "PLAY"]
    rows = {x["game"].split(" @ ")[1]: x for x in dp.rescore(doc)}
    assert rows["Big"]["verdict"] == "quarantined" and rows["Big"]["addendum_call"] == "PASS"
    assert rows["Big"]["v11_units"] == rows["Big"]["addendum_units"] == 0      # same quarantine both sides
    assert (rows["Mid"]["verdict"], rows["Mid"]["v11_units"], rows["Mid"]["addendum_units"]) == ("halved", 1, 0.5)
    assert dp.MLB_QUARANTINE["on"] and dp.EXEC_RULES["on"] and dp.STARTED_RULE["on"]   # restored
    p = tmp_path / "mlb.json"
    p.write_text(json.dumps(doc))
    res = CliRunner().invoke(cli.cli, ["desk-rescore", str(p), "--out", str(tmp_path / "r.md")])
    assert res.exit_code == 0, res.output
    assert "2 PLAY(s) re-scored · 1 would have been halved" in res.output
    assert "1 PLAY(s) now QUARANTINED" in res.output and "QUARANTINED" in (tmp_path / "r.md").read_text()
