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


def test_composite_no_matches_its_ladder_call_never_a_straight():
    """Codex on #299 (P1, verified): an AWAY ladder is executed as NO on HOME (desk order line: X2), which is the
    composite contract. It must match its ladder call (and carry its CLV), while a straight still never matches."""
    lad = dict(_call("lad", "Arsenal", "Chelsea", "AWAY", "2026-09-27T14:00:00", sport="SOCCER"), call_type="ladder")
    L = {"calls": [lad], "fills": [_fill("n", "KXEPLGAME-26SEP27CHEARS-ARS", "no", "Arsenal wins — Chelsea")]}
    (f,) = P.classify_fills(L)
    assert f["book"] == "system_matched" and f["call_id"] == "lad" and f["composite"]
    home_ladder = dict(lad, pick="HOME")                                   # NO on HOME is not a HOME position
    (g,) = P.classify_fills({"calls": [home_ladder], "fills": L["fills"]})
    assert g["book"] == "off_book_sports"
    graded = dict(lad, status="graded", close_ref={"fair": {"HOME": 0.45, "DRAW": 0.27, "AWAY": 0.28}})
    pos = P.executed_positions({"calls": [graded], "fills": [dict(L["fills"][0], qty=2, entry=0.5)]})["pos"]
    assert len(pos) == 1 and abs(pos[0]["clv"] - ((1 - 0.45) - 0.5)) < 1e-12             # held NO HOME at 0.55


def test_non_prefix_codes_match_through_a_strict_title_and_shared_words_still_do_not():
    """Codex on #299, round 3 (verified): JAX does not prefix 'Jacksonville Jaguars' (nor BHA 'Brighton and Hove
    Albion'), so codes-only rejected the right game. A strict two-team title fit (whole-word subsets on two
    different sides) now matches; one shared word, or Manchester City vs Manchester United, still does not."""
    nfl = {"calls": [_call("j", "Jacksonville Jaguars", "Tennessee Titans", "HOME", "2026-10-04T17:00:00", "NFL")],
           "fills": [_fill("a", "KXNFLGAME-26OCT04TENJAX-JAX", "yes", "Jacksonville wins — Tennessee")]}
    (f,) = P.classify_fills(nfl)
    assert f["book"] == "system_matched" and f["call_id"] == "j"
    epl = {"calls": [_call("b", "Brighton and Hove Albion", "Everton", "HOME", "2026-10-04T14:00:00", "SOCCER")],
           "fills": [_fill("c", "KXEPLGAME-26OCT04EVEBHA-BHA", "yes", "Brighton wins — Everton")]}
    (g,) = P.classify_fills(epl)
    assert g["book"] == "system_matched" and g["call_id"] == "b"
    city = {"calls": [_call("u", "Manchester United", "Arsenal", "HOME", "2026-10-04T14:00:00", "SOCCER")],
            "fills": [_fill("d", "KXEPLGAME-26OCT04ARSMCI-MCI", "yes", "Manchester City wins — Arsenal")]}
    (h,) = P.classify_fills(city)
    assert h["book"] != "system_matched"


def test_ticker_side_disagreeing_with_the_pick_is_never_matched_gb_tb_regression():
    """ARCHITECT 2026-10-06 (matcher bug): KXNFLGAME-26OCT04GBTB-GB yes (Green Bay, AWAY) was system_matched to
    a HOME (Tampa Bay) call because the names share "Bay". The ticker suffix names the side: off-book."""
    fill = _fill("gb", "KXNFLGAME-26OCT04GBTB-GB", "yes", "Green Bay wins — Tampa Bay")
    home = _call("tb", "Tampa Bay Buccaneers", "Green Bay Packers", "HOME", "2026-10-04T17:00:00", sport="NFL")
    f = P.classify_fills({"calls": [home], "fills": [fill]})[0]
    assert f["backed_role"] == "AWAY"
    assert f["book"] == "off_book_sports" and f.get("call_id") is None
    assert f["category"] == "logged call exists but the side disagrees"
    away = {**home, "id": "gbp", "pick": "AWAY"}                       # the same fill on a GB pick still matches
    assert P.classify_fills({"calls": [away], "fills": [fill]})[0]["call_id"] == "gbp"
    # the stored-prediction (pre-ledger) path uses the same rule
    pick = {"sport": "NFL", "date": "2026-10-04", "home": "Tampa Bay Buccaneers", "away": "Green Bay Packers",
            "pick": "HOME", "source": "results"}
    f = P.classify_fills({"calls": [], "fills": [fill], "system_picks": [pick]})[0]
    assert f["book"] == "off_book_sports" and "disagrees" in f["category"]
    # no ticker role (title only): whole-name subsets, so "Green Bay" never agrees with "Tampa Bay Buccaneers"
    assert not P.classify_fills({"calls": [home], "fills": [
        _fill("t", "KXNFLGAME-26OCT04XXYY-ZZ", "yes", "Green Bay vs Tampa Bay")]})[0].get("call_id")


def test_the_timed_game_is_resolved_before_its_pick_is_checked():
    """Codex on #299 (P1): a 13:05 ET HOME fill, game 1 (13:05) picked AWAY, game 2 (15:45) picked HOME. The fill
    belongs to game 1, whose pick disagrees: off-book, never handed to game 2."""
    L = {"calls": [_call("g1", "Boston Red Sox", "New York Yankees", "AWAY", "2026-09-27T17:05:00"),
                   _call("g2", "Boston Red Sox", "New York Yankees", "HOME", "2026-09-27T19:45:00")],
         "fills": [_fill("a", "KXMLBGAME-26SEP271305NYYBOS-BOS", "yes", "Boston wins — New York Y")]}
    f = P.classify_fills(L)[0]
    assert f["book"] == "off_book_sports" and f.get("call_id") is None and "disagrees" in f["category"]
