"""#87 EXECUTABLE EDGE — v1.1 ADDENDUM (ARCHITECT-RULE 2026-10-06, effective next slate):
(1) cost = ask + taker fee (0.07·M·P(1−P), nearest cent per fill); (2) TAKE at the ask by default, join-bid only
at a spread >= 3c; (3) exec edge = model_p − cost: full tier units only at >= 4pp, else HALF; (4) venue: the 5pp
fair threshold stands AND exec edge >= 4pp; (5) parlay legs priced at executable cost, independence label.
Quarantine, floors and tiers are unchanged. The frozen pre-addendum golden still holds under base_v11()."""
import json
from datetime import datetime, timedelta, timezone

from src.walters import desk_policy as dp
from src.walters.venue import kalshi_exec

NOW = datetime(2026, 10, 11, 16, 0, tzinfo=timezone.utc)
NOW_MS = float((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))


def ko(minutes=45):
    return (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


def nfl(home, p_home, fair_h, bid=None, ask=None, legs=None, **kw):
    r = {"home_team": home, "away_team": f"{home} away", "utc_date": ko(), "competition": "NFL", "stage": "regular",
         "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                        "tier": "lean"},
         "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}}}
    r.update(kalshi_exec(bid, ask, "NFL", two_way=True) if ask is not None or bid is not None else {})
    if legs:
        r["kalshi_legs"] = legs
    r.update(kw)
    return r


def calls(*rows):
    ev = dp.evaluate({"sport": "nfl", "predictions": list(rows)}, NOW_MS)
    return {r["home"]: c for r, c in ev["calls"]}


def test_cost_is_ask_plus_taker_fee_per_fill():
    # NFL M=1: fee for a 10-contract fill at 0.55 = round(10·0.07·0.55·0.45·100)c = 17c -> 1.7c per contract
    r = dp.normalize({"sport": "nfl", "predictions": [nfl("KC", 0.62, 0.55, bid=0.54, ask=0.55)]})[0]
    assert dp.desk_cost_for(r, "HOME") == {"cost": 0.567, "basis": "taker"}
    assert abs(dp.exec_edge_pp(r, "HOME", 0.62) - 5.3) < 1e-9
    with dp.base_v11():
        assert dp.desk_cost_for(r, "HOME")["basis"] == "taker"          # 1c spread: no maker price either way


def test_play_sizing_full_half_and_unknown():
    c = calls(nfl("FULL", 0.62, 0.55, bid=0.54, ask=0.55),             # fair +7.0, exec +5.3 -> full
              nfl("HALF", 0.62, 0.55, bid=0.58, ask=0.59),             # fair +7.0, exec +1.3 -> half
              nfl("NOQ", 0.62, 0.55))                                  # no executable quote -> half
    assert (c["FULL"]["call"], c["FULL"]["units"]) == ("PLAY", 1) and "exec clears" in c["FULL"]["tags"]
    assert (c["HALF"]["call"], c["HALF"]["units"]) == ("PLAY", 0.5) and "exec < 4pp half units" in c["HALF"]["tags"]
    assert any("exec edge 1.3pp < 4pp at ask + taker fee 0.607" in x for x in c["HALF"]["reasons"])
    assert (c["NOQ"]["call"], c["NOQ"]["units"]) == ("PLAY", 0.5) and "exec unknown half units" in c["NOQ"]["tags"]
    with dp.base_v11():
        assert calls(nfl("HALF", 0.62, 0.55, bid=0.58, ask=0.59))["HALF"]["units"] == 1


def test_floors_tiers_and_quarantine_unchanged():
    c = calls(nfl("FLOOR", 0.57, 0.55, bid=0.40, ask=0.41),            # fair +2.0 < 4: PASS, exec irrelevant
              nfl("Q", 0.80, 0.55, bid=0.70, ask=0.71, quarantine=True, market_divergence_pp=25.0))
    assert c["FLOOR"]["call"] == "PASS" and c["FLOOR"]["passKind"] == "floor"
    assert not any("exec" in t for t in c["FLOOR"]["tags"])
    q = c["Q"]                                                        # quarantine: never a straight, shadow as before
    assert q["call"] == "PASS" and q["shadowUnits"] == 0.5 and not any("exec" in t for t in q["tags"])
    with dp.base_v11():
        assert calls(nfl("Q", 0.80, 0.55, bid=0.70, ask=0.71, quarantine=True,
                         market_divergence_pp=25.0))["Q"]["shadowUnits"] == 0.5


def test_ladders_are_not_resized_by_the_play_rule():
    row = {"home_team": "Everton", "away_team": "Fulham", "utc_date": ko(), "competition": "PL", "stage": "regular",
           "prediction": {"probabilities": {"home_win": 0.25, "draw": 0.25, "away_win": 0.50}, "tier": "lean"},
           "market": {"bookmaker_count": 9, "fair_prob": {"HOME": 0.45, "DRAW": 0.27, "AWAY": 0.28}}}
    c = dp.evaluate({"sport": "soccer", "predictions": [row]}, NOW_MS)["calls"][0][1]
    assert c["call"] == "LADDER" and c["units"] == 0.5 and not any("exec" in t for t in c["tags"])


def test_take_is_the_doctrine_and_join_only_at_three_cents():
    one = dp.normalize({"sport": "nfl", "predictions": [nfl("A", 0.6, 0.5, bid=0.54, ask=0.55)]})[0]
    two = dp.normalize({"sport": "nfl", "predictions": [nfl("B", 0.6, 0.5, bid=0.53, ask=0.55)]})[0]
    three = dp.normalize({"sport": "nfl", "predictions": [nfl("C", 0.6, 0.5, bid=0.52, ask=0.55)]})[0]
    assert dp.join_bid_for(one, "HOME") == {"price": None, "note": "spread 1¢ < 3¢ — TAKE at the ask"}
    assert dp.join_bid_for(two, "HOME") == {"price": None, "note": "spread 2¢ < 3¢ — TAKE at the ask"}
    assert dp.join_bid_for(three, "HOME") == {"price": 0.53}
    with dp.base_v11():
        assert dp.join_bid_for(two, "HOME") == {"price": 0.54}            # the superseded 09-30 doctrine
    blk = dp.exec_block(two, "HOME", 0.6)
    assert blk["doctrine"] == "take" and blk["basis"] == "taker" and blk["cost"] == blk["taker_cost"]
    assert dp.exec_block(three, "HOME", 0.6)["doctrine"] == "join"
    legs = lambda b, a: {"HOME": {"ticker": "KXNFLGAME-26OCT11AKC-KC", "bid": b, "ask": a}}
    o = dp.order_line({"src": {"kalshi_legs": legs(0.53, 0.55)}, "threeWay": False}, "HOME", 1)
    assert (o["limit"], o["limit_basis"], o["text"]) == (0.55, "take at the ask (spread 2c)",
                                                         "BUY YES KXNFLGAME-26OCT11AKC-KC @ 0.55 × 10")
    o = dp.order_line({"src": {"kalshi_legs": legs(0.50, 0.55)}, "threeWay": False}, "HOME", 1)
    assert (o["limit"], o["limit_basis"]) == (0.51, "join bid + 1c (spread 5c >= 3c)")
    o = dp.order_line({"src": {"kalshi_legs": legs(0.50, None)}, "threeWay": False}, "HOME", 1)
    assert o["text"] is None and "no ask to take" in o["why"]


def test_the_cost_is_the_leg_the_order_line_buys():
    # an AWAY pick on a two-way board with its own YES leg is costed at that leg's ask, as the order line buys it
    r = nfl("KC", 0.40, 0.48, bid=0.50, ask=0.52,
            legs={"HOME": {"ticker": "T-KC", "bid": 0.50, "ask": 0.52}, "AWAY": {"ticker": "T-BUF", "bid": 0.46,
                                                                              "ask": 0.47}})
    n = dp.normalize({"sport": "nfl", "predictions": [r]})[0]
    assert dp.taker_cost_for(n, "AWAY") == 0.487                        # 0.47 + round(17.437c)/10 = 0.47 + 0.017
    assert dp.order_line(n, "AWAY", 1)["text"].startswith("BUY YES T-BUF @ 0.47")


def _fixture(home, fair_h, legs=None, captured=30):
    f = {"home_team": home, "away_team": f"{home} away", "utc_date": ko(), "status": "scheduled",
         "market": {"bookmaker_count": 5, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)},
                    "captured_at": (NOW - timedelta(minutes=captured)).strftime("%Y-%m-%dT%H:%M:%S")},
         "kalshi": {"status": "two_sided", "prob": {"HOME": 0.52, "AWAY": 0.48}}}
    if legs:
        f["kalshi_legs"] = legs
    return f


def test_venue_needs_five_fair_and_four_executable():
    doc = {"competition": "NHL", "fixtures": [
        _fixture("OK", 0.60, {"HOME": {"ticker": "T1", "bid": 0.52, "ask": 0.53}}),   # fair +8.0, exec +5.3
        _fixture("FEE", 0.60, {"HOME": {"ticker": "T2", "bid": 0.56, "ask": 0.57}}),  # fair +8.0, exec +1.3
        _fixture("NOQ", 0.60)]}                                                       # no executable quote
    ven = {r["home"]: v for r, v in dp.evaluate(doc, NOW_MS)["venue"]}
    assert ven["OK"]["eligible"] and abs(ven["OK"]["execPP"] - 5.3) < 1e-9 and ven["OK"]["execCost"] == 0.547
    assert not ven["FEE"]["eligible"] and ven["FEE"]["kind"] == "floor" and "exec edge 1.3pp < 4pp" in ven["FEE"]["reason"]
    assert not ven["NOQ"]["eligible"] and ven["NOQ"]["kind"] == "noref"
    dp.annotate(doc, now=NOW)
    d = {f["home_team"]: f["desk"] for f in doc["fixtures"]}
    assert (d["OK"]["call"], d["OK"]["units"]) == ("VENUE", 0.25) and d["OK"]["venue"]["exec_pp"] is not None
    assert d["OK"]["order"]["limit_basis"] == "take at the ask (spread 1c)"
    assert (d["FEE"]["call"], d["NOQ"]["call"]) == ("PASS", "PASS")
    with dp.base_v11():
        assert all(v["eligible"] for _, v in dp.evaluate(doc, NOW_MS)["venue"])


def test_window_card_venue_uses_the_same_gate():
    row = {**_fixture("W", 0.60, {"HOME": {"ticker": "T", "bid": 0.56, "ask": 0.57}}), "competition": "NHL",
           "engine": "market_only"}
    v = dp.window_venue(row, NOW_MS)
    assert not v["eligible"] and v["kind"] == "floor" and abs(v["exec_pp"] - 1.3) < 1e-9
    row["kalshi_legs"]["HOME"].update(bid=0.52, ask=0.53)
    assert dp.window_venue(row, NOW_MS)["eligible"]


def test_parlay_legs_are_priced_at_executable_cost_with_the_independence_label():
    rows = [nfl("A", 0.70, 0.60, bid=0.59, ask=0.60), nfl("B", 0.72, 0.62, bid=0.61, ask=0.62),
            nfl("C", 0.70, 0.60)]                                                   # C: no executable quote
    doc = dp.parlays_doc([("nfl.json", {"sport": "nfl", "predictions": rows})], now=NOW)
    assert doc["pricing"]["unpriced_tickets"] == 3 and doc["pricing"]["label"] == dp.PARLAY_LABEL
    (t,) = doc["tickets"]                                                          # only A+B can be priced
    ca, cb = (l["exec_cost"] for l in t["legs"])
    assert t["market_p"] == ca * cb and abs(t["fair_p"] - 0.60 * 0.62) < 1e-12 and t["label"] == dp.PARLAY_LABEL
    assert t["market_basis"].startswith("executable") and abs(t["edge"] - (0.70 * 0.72 - ca * cb)) < 1e-12
    with dp.base_v11():
        assert len(dp.parlays_doc([("nfl.json", {"sport": "nfl", "predictions": rows})], now=NOW)["tickets"]) == 3


def test_desk_rescore_reports_which_published_plays_would_have_been_halved(tmp_path):
    from click.testing import CliRunner

    import cli
    doc = {"sport": "nfl", "predictions": [nfl("FULL", 0.62, 0.55, bid=0.54, ask=0.55),
                                           nfl("HALF", 0.62, 0.55, bid=0.58, ask=0.59),
                                           nfl("PASS", 0.56, 0.55, bid=0.58, ask=0.59)]}
    with dp.base_v11():                                            # Sunday's file: published before the addendum
        dp.annotate(doc, now=NOW)
    before = json.dumps(doc, sort_keys=True)
    rows = {x["game"].split(" @ ")[1]: x for x in dp.rescore(doc)}
    assert set(rows) == {"FULL", "HALF"}                           # PLAYs only
    assert (rows["FULL"]["verdict"], rows["HALF"]["verdict"]) == ("unchanged", "halved")
    assert rows["HALF"]["published_units"] == rows["HALF"]["v11_units"] == 1 and rows["HALF"]["addendum_units"] == 0.5
    assert json.dumps(doc, sort_keys=True) == before                # read-only
    p = tmp_path / "sunday.json"
    p.write_text(json.dumps(doc))
    res = CliRunner().invoke(cli.cli, ["desk-rescore", str(p)])
    assert res.exit_code == 0, res.output
    assert "2 PLAY(s) re-scored · 1 would have been halved" in res.output and "HALVED" in res.output


def test_doctrine_join_price_and_order_share_one_source_for_three_way_legs():
    """Codex on #303: a three-way AWAY/DRAW pick priced from its own leg showed doctrine "take" while the order
    joined; and the join price (bid + 1c) differed from the order's limit (bid). One source now."""
    row = {"home_team": "Everton", "away_team": "Fulham", "utc_date": ko(), "competition": "PL", "stage": "regular",
           "prediction": {"probabilities": {"home_win": 0.30, "draw": 0.25, "away_win": 0.45}, "tier": "lean"},
           "market": {"bookmaker_count": 9, "fair_prob": {"HOME": 0.40, "DRAW": 0.27, "AWAY": 0.33}},
           "kalshi_legs": {"AWAY": {"ticker": "KXEPLGAME-X-FUL", "bid": 0.30, "ask": 0.34}}}
    n = dp.normalize({"sport": "soccer", "predictions": [row]})[0]
    blk = dp.exec_block(n, "AWAY", 0.45)
    o = dp.order_line(n, "AWAY", 1)
    assert blk["doctrine"] == "join" and blk["join_price"] == 0.31 == o["limit"]
    assert o["text"].startswith("BUY YES KXEPLGAME-X-FUL @ 0.31")
