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
        _fixture("OK", 0.60, {"HOME": {"ticker": "T1", "bid": 0.52, "ask": 0.53}}),   # fair +8.0, exec +5.5 (2 contracts)
        _fixture("FEE", 0.60, {"HOME": {"ticker": "T2", "bid": 0.56, "ask": 0.57}}),  # fair +8.0, exec +1.5
        _fixture("NOQ", 0.60)]}                                                       # no executable quote
    ven = {r["home"]: v for r, v in dp.evaluate(doc, NOW_MS)["venue"]}
    # (h): a 0.25u venue order is 2 contracts: fee round(2·0.07·0.53·0.47·100)c = 3c -> 1.5c per contract
    assert ven["OK"]["eligible"] and abs(ven["OK"]["execPP"] - 5.5) < 1e-9 and ven["OK"]["execCost"] == 0.545
    assert not ven["FEE"]["eligible"] and ven["FEE"]["kind"] == "floor" and "exec edge 1.5pp < 4pp" in ven["FEE"]["reason"]
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
    assert not v["eligible"] and v["kind"] == "floor" and abs(v["exec_pp"] - 1.5) < 1e-9
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


def test_h_each_order_is_priced_at_its_own_contract_count(monkeypatch):
    """(h) RULED 2026-10-06: the fee is per fill of the order's OWN contract count; the 10-contract assumption ended.
    At a 0.55 ask (NFL M=1): 10 contracts -> 17c/10 = 1.7c; 2 contracts (0.25u) -> 3c/2 = 1.5c; SP_UNIT_USD=20 ->
    floor(20/0.55) = 36 contracts -> round(62.37c) = 62c/36."""
    n = dp.normalize({"sport": "nfl", "predictions": [nfl("A", 0.62, 0.55, bid=0.54, ask=0.55)]})[0]
    assert dp.taker_cost_for(n, "HOME", 1) == 0.567 and dp.taker_cost_for(n, "HOME", 0.25) == 0.565
    monkeypatch.setenv("SP_UNIT_USD", "20")
    assert dp.order_contracts(1, 0.55) == 36 and dp.taker_cost_for(n, "HOME", 1) == round(0.55 + 0.62 / 36, 4)
    monkeypatch.delenv("SP_UNIT_USD")
    assert dp.taker_cost_for(n, "HOME", 0.05) is None                 # under one contract: no order, no cost
    # a halved PLAY: the gate priced the 1u order; the emitted 0.5u order (5 contracts) is reported beside it
    doc = {"sport": "nfl", "predictions": [nfl("HALF", 0.62, 0.55, bid=0.58, ask=0.59)]}
    dp.annotate(doc, now=NOW)
    x = doc["predictions"][0]["desk"]["exec"]
    assert doc["predictions"][0]["desk"]["units"] == 0.5 and x["contracts"] == 10 and x["order_contracts"] == 5
    assert x["cost"] == 0.607 and x["order_cost"] == 0.606          # 5 × 0.07·0.59·0.41 = 8.47c -> 8c / 5 = 1.6c


def test_i_venue_backs_the_best_side_that_clears_both_gates():
    """(i) RULED 2026-10-06: HOME leads on fair divergence (+8) but fails exec at its ask; DRAW (+6 fair) clears exec:
    the engine backs DRAW. With no side clearing both, the largest-divergence side is reported with its PASS reason."""
    f = {"home_team": "H", "away_team": "A", "utc_date": ko(), "status": "scheduled",
         "market": {"bookmaker_count": 5, "fair_prob": {"HOME": 0.50, "DRAW": 0.30, "AWAY": 0.20},
                    "captured_at": (NOW - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S")},
         "kalshi": {"status": "two_sided", "prob": {"HOME": 0.42, "DRAW": 0.24, "AWAY": 0.34}},
         "kalshi_legs": {"HOME": {"ticker": "TH", "bid": 0.47, "ask": 0.48},     # 0.50 − 0.495 = +0.5 exec
                         "DRAW": {"ticker": "TD", "bid": 0.22, "ask": 0.23}}}     # 0.30 − (0.23 + 0.01) = +6.0
    v = dp.evaluate({"competition": "UCL", "fixtures": [f]}, NOW_MS)["venue"][0][1]
    assert v["eligible"] and v["side"] == "DRAW" and abs(v["divPP"] - 6.0) < 1e-9
    f["kalshi_legs"]["DRAW"].update(bid=0.26, ask=0.27)                          # DRAW now fails exec too
    v = dp.evaluate({"competition": "UCL", "fixtures": [f]}, NOW_MS)["venue"][0][1]
    assert not v["eligible"] and v["side"] == "HOME" and "exec edge" in v["reason"]
    with dp.base_v11():
        assert dp.evaluate({"competition": "UCL", "fixtures": [f]}, NOW_MS)["venue"][0][1]["side"] == "HOME"


def test_codex_round_4_quote_selection_and_join_count_follow_the_order_line(monkeypatch):
    """Codex on #303: (1) a ticketed AWAY leg with no ask is the order's instrument, so it is UNPRICEABLE (never
    priced from NO on HOME, which order_line would not buy); (2) with SP_UNIT_USD and a >= 3c spread the order
    joins at bid + 1c, so the fill count is taken at the join limit, not the ask."""
    r = nfl("KC", 0.40, 0.48, bid=0.50, ask=0.52,
            legs={"HOME": {"ticker": "T-KC", "bid": 0.50, "ask": 0.52}, "AWAY": {"ticker": "T-BUF", "bid": 0.46,
                                                                              "ask": None}})
    n = dp.normalize({"sport": "nfl", "predictions": [r]})[0]
    assert dp.taker_cost_for(n, "AWAY", 1) is None and dp.order_line(n, "AWAY", 1)["text"] is None
    monkeypatch.setenv("SP_UNIT_USD", "20")
    j = dp.normalize({"sport": "nfl", "predictions": [nfl("J", 0.62, 0.50, bid=0.50, ask=0.55, legs={
        "HOME": {"ticker": "T-J", "bid": 0.50, "ask": 0.55}})]})[0]
    o = dp.order_line(j, "HOME", 1)
    assert (o["limit"], o["contracts"]) == (0.51, 39)                    # floor(20 / 0.51)
    fee39 = round(39 * 0.07 * 0.55 * 0.45 * 100) / 100                   # 67.6c -> 68c over the EMITTED 39
    assert dp.taker_cost_for(j, "HOME", 1) == round(0.55 + round(fee39 / 39, 6), 4)


def test_codex_round_5_exec_block_on_opponent_no_and_rescore_uses_the_files_units(monkeypatch):
    """Codex on #303: (1) an AWAY pick with no AWAY leg but a ticketed HOME leg is priced and ordered as NO on HOME,
    so desk.exec must be present even when the legacy K-track fields are empty; (2) desk-rescore applies the unit
    basis the FILE was produced under, never the caller's SP_UNIT_USD."""
    r = {"home_team": "KC", "away_team": "BUF", "utc_date": ko(), "competition": "NFL", "stage": "regular",
         "prediction": {"probabilities": {"home_win": 0.35, "draw": None, "away_win": 0.65}, "tier": "lean"},
         "market": {"bookmaker_count": 9, "fair_prob": {"HOME": 0.42, "AWAY": 0.58}},
         "kalshi_legs": {"HOME": {"ticker": "T-KC", "bid": 0.38, "ask": 0.39}}}
    n = dp.normalize({"sport": "nfl", "predictions": [r]})[0]
    blk = dp.exec_block(n, "AWAY", 0.65)
    assert blk is not None and blk["no_side"] and blk["cost"] == dp.taker_cost_for(n, "AWAY", 1)
    assert dp.order_line(n, "AWAY", 1)["text"].startswith("BUY NO T-KC @ 0.62")
    monkeypatch.setenv("SP_UNIT_USD", "20")
    doc = {"sport": "nfl", "predictions": [nfl("HALF", 0.62, 0.55, bid=0.58, ask=0.59, legs={
        "HOME": {"ticker": "T-H", "bid": 0.58, "ask": 0.59}})]}
    with dp.base_v11():
        dp.annotate(doc, now=NOW)                                       # produced under $20 units
    a = dp.rescore(doc)
    monkeypatch.delenv("SP_UNIT_USD")                                   # the caller's env differs
    b = dp.rescore(doc)
    assert a == b and a[0]["unit_basis"] == "1u = $20 (from the file)"


def test_codex_round_6_maker_cost_at_the_order_count_and_parlay_cli_wording(tmp_path):
    """Codex on #303: (1) maker_cost is the JOIN order's (bid + 1c) at the order's own contract count, not the legacy
    10-contract K-track figure: at a 0.53 join, 2 contracts (0.25u) -> 0.005, 10 -> 0.004 per contract; none when the
    doctrine takes; (2) desk-parlays prints "Π executable cost" with Π fair for executable-priced tickets."""
    from click.testing import CliRunner

    import cli
    n = dp.normalize({"sport": "nfl", "predictions": [nfl("J", 0.62, 0.50, bid=0.52, ask=0.56)]})[0]
    assert dp.maker_cost_at(n, "HOME", 1) == round(0.53 + 0.004, 4)        # round(10·0.0175·0.53·0.47·100)=4c /10
    assert dp.maker_cost_at(n, "HOME", 0.25) == round(0.53 + 0.005, 4)     # round(2·…)=1c /2
    t = dp.normalize({"sport": "nfl", "predictions": [nfl("T", 0.62, 0.50, bid=0.54, ask=0.55)]})[0]
    assert dp.maker_cost_at(t, "HOME", 1) is None                          # 1c spread: TAKE, no maker order
    rows = [nfl("A", 0.70, 0.60, bid=0.59, ask=0.60), nfl("B", 0.72, 0.62, bid=0.61, ask=0.62)]
    p = tmp_path / "nfl.json"
    p.write_text(json.dumps({"sport": "nfl", "predictions": rows}))
    res = CliRunner().invoke(cli.cli, ["desk-parlays", str(p), "--now", NOW.isoformat(), "--out", str(tmp_path / "o.json")])
    assert res.exit_code == 0, res.output
    assert "vs Π executable cost" in res.output and "(Π fair 0.372)" in res.output
