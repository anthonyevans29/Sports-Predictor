"""ARCHITECT 2026-10-06 (fill matcher lane): the event ticker's start time (US Eastern, KalshiAdapter.ticker_start,
M13) tells an MLB doubleheader's two games apart; a three-way NO is COMPOSITE (two outcomes), never a single-side
straight. The Cockpit and the Python port change together (parity: scripts/ledger_fills_parity_verify.py)."""
from src.adapters.kalshi import KalshiAdapter
from src.walters import ledger_fills as P


def _call(cid, home, away, pick, kick, sport="MLB"):
    return {"id": cid, "log_date": kick[:10], "sport": sport, "game": f"{away} @ {home}", "home": home, "away": away,
            "kickoff": kick, "status": "open", "pick": pick, "tier": "lean", "engine": "model_edge",
            "call_type": "straight", "units": 1}


def _fill(fid, ticker, side, title):
    return {"id": fid, "ticker": ticker, "side": side, "qty": 2, "entry": 0.5, "title": title}


def test_ticker_start_is_eastern_time_and_agrees_with_the_adapter():
    for t in ("KXMLBGAME-26OCT012000PHIATL-PHI", "KXMLBGAME-26AUG242145CINSF-SF", "KXMLBGAME-26NOV031305NYYBOS-BOS"):
        assert P.parse_ticker(t)["start"] == KalshiAdapter.ticker_start({"ticker": t}).strftime("%Y-%m-%dT%H:%M:%S")
    assert P.parse_ticker("KXMLBGAME-26NOV031305NYYBOS-BOS")["start"] == "2026-11-03T18:05:00"   # EST after DST ends
    assert P.parse_ticker("KXEPLGAME-26SEP13ARSCHE-ARS")["start"] is None                    # no time: never guessed


def test_doubleheader_fills_match_their_own_game():
    L = {"calls": [_call("g1", "Boston Red Sox", "New York Yankees", "HOME", "2026-09-27T17:05:00"),
                   _call("g2", "Boston Red Sox", "New York Yankees", "HOME", "2026-09-27T23:05:00")],
         "fills": [_fill("a", "KXMLBGAME-26SEP271905NYYBOS-BOS", "yes", "Boston wins — New York Y"),
                   _fill("b", "KXMLBGAME-26SEP271305NYYBOS-BOS", "yes", "Boston wins — New York Y"),
                   _fill("c", "KXMLBGAME-26SEP27NYYBOS-BOS", "yes", "Boston wins — New York Y")]}
    by = {f["id"]: f for f in P.classify_fills(L)}
    assert by["a"]["call_id"] == "g2" and by["b"]["call_id"] == "g1"
    assert by["c"]["call_id"] == "g1" and by["c"]["ambiguous_calls"] == ["g1", "g2"]   # no time: still flagged


def test_three_way_no_is_composite_never_a_straight():
    L = {"calls": [_call("s", "Arsenal", "Chelsea", "AWAY", "2026-09-27T14:00:00", sport="SOCCER")],
         "fills": [_fill("n", "KXEPLGAME-26SEP27CHEARS-ARS", "no", "Arsenal wins — Chelsea"),
                   _fill("y", "KXEPLGAME-26SEP27CHEARS-CHE", "yes", "Chelsea wins — Arsenal")]}
    by = {f["id"]: f for f in P.classify_fills(L)}
    assert by["n"]["book"] == "off_book_sports" and by["n"]["composite"] and by["n"]["no_on_role"] == "HOME"
    assert by["y"]["book"] == "system_matched" and by["y"]["call_id"] == "s"
    two_way = {"calls": [_call("k", "Kansas City Chiefs", "Buffalo Bills", "HOME", "2026-09-28T17:00:00", "NFL")],
               "fills": [_fill("m", "KXNFLGAME-26SEP28BUFKC-BUF", "no", "Buffalo wins — Kansas City")]}
    (f,) = P.classify_fills(two_way)                        # a two-way NO still means the opposite team
    assert f["book"] == "system_matched" and f["call_id"] == "k" and not f["composite"]


def test_ticker_codes_decide_team_identity_not_one_shared_word():
    """Codex on #299 (P1, verified): 'Manchester United' and 'Newcastle United' share 'united', so a title fit
    let a fill on one game match a different call. With ticker codes present, the codes decide."""
    L = {"calls": [_call("other", "Newcastle United", "West Ham United", "HOME", "2026-09-27T14:00:00", "SOCCER"),
                   _call("right", "Manchester United", "Leeds United", "HOME", "2026-09-27T14:00:00", "SOCCER")],
         "fills": [_fill("u", "KXEPLGAME-26SEP27LEEMUN-MUN", "yes", "Manchester United wins — Leeds United")]}
    (f,) = P.classify_fills(L)
    assert f["book"] == "system_matched" and f["call_id"] == "right" and not f.get("ambiguous_calls")


def test_unpriced_count_is_scoped_to_the_window():
    """Codex on #299 (P2, verified): an out-of-window matched call whose held contract cannot be priced was
    counted in the windowed receipt's unpriced line."""
    from datetime import datetime

    from src.walters import k_receipt as K
    call = dict(_call("c", "Kansas City Chiefs", "Buffalo Bills", "HOME", "2095-11-02T17:00:00", "NFL"),
                status="graded", close_ref={"fair": {}})                  # no fair: not priceable
    fill = dict(_fill("f", "KXNFLGAME-95NOV02BUFKC-KC", "yes", "Kansas City wins — Buffalo"), qty=2, entry=0.5)
    txt = "\n".join(K.format_fills({"calls": [call], "fills": [fill]}, datetime(2095, 9, 23), datetime(2095, 10, 8)))
    assert "not priceable" not in txt
