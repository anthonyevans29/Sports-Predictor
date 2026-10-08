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


def test_same_city_codes_never_stand_for_a_different_game():
    """Codex (post-merge on #297): a Giants–Rams fill must not fit a same-day Jets–Chargers call. NYG ~ "New York
    Jets" and LAR ~ "Los Angeles Chargers" each fit only by two-letter initials (weak); KC's weak fit still
    counts when the other code fits strongly."""
    jets = _call("nyj", "Los Angeles Chargers", "New York Jets", "AWAY", "2026-10-11T17:00:00", sport="NFL")
    f = P.classify_fills({"calls": [jets], "fills": [
        _fill("g", "KXNFLGAME-26OCT11NYGLAR-NYG", "yes", "New York G wins — Los Angeles R")]})[0]
    assert f.get("call_id") is None and f["category"] == "no logged call for this game"
    kc = _call("kc", "Kansas City Chiefs", "Buffalo Bills", "HOME", "2026-10-11T17:00:00", sport="NFL")
    assert P.classify_fills({"calls": [kc], "fills": [
        _fill("k", "KXNFLGAME-26OCT11BUFKC-KC", "yes", "Kansas City wins — Buffalo")]})[0]["call_id"] == "kc"


def test_title_fallback_keeps_home_and_away_orientation():
    """Codex on #299: a call with the same teams REVERSED (NYY home) fails the codes but passed the unordered
    title fallback, and the role check then matched a BOS-HOME fill to the Yankees' HOME pick."""
    rev = _call("rev", "New York Yankees", "Boston Red Sox", "HOME", "2026-09-27T17:05:00")
    f = P.classify_fills({"calls": [rev], "fills": [
        _fill("b", "KXMLBGAME-26SEP271305NYYBOS-BOS", "yes", "Boston wins — New York Yankees")]})[0]
    assert f.get("call_id") is None
    nfl = {"calls": [_call("j", "Jacksonville Jaguars", "Tennessee Titans", "HOME", "2026-10-04T17:00:00", "NFL")],
           "fills": [_fill("a", "KXNFLGAME-26OCT04TENJAX-JAX", "yes", "Jacksonville wins — Tennessee")]}
    assert P.classify_fills(nfl)[0]["call_id"] == "j"                  # the right orientation still matches


def test_codex_round_6_no_tie_weak_codes_and_legacy_titles():
    """Codex on #299, round 6 (verified): (1) NO on the TIE of a three-way market is HOME-or-AWAY: composite, with
    no_on_role DRAW; (2) one weak code is not confirmed by a strong opponent: NYGSEA must not fit a Jets–Seahawks
    call when the title says "New York G" (while KC and "Man City" stay confirmed); (3) a legacy "A vs B Winner?"
    title has no "X wins" name: orientation comes from the other code fitting the call's opposite side."""
    tie = P.classify_fills({"calls": [_call("s", "Arsenal", "Chelsea", "HOME", "2026-09-27T14:00:00", sport="SOCCER")],
                            "fills": [_fill("t", "KXEPLGAME-26SEP27CHEARS-TIE", "no", "Tie — Chelsea vs Arsenal")]})[0]
    assert tie["composite"] is True and tie["no_on_role"] == "DRAW" and tie["book"] == "off_book_sports"
    assert "composite" in tie["category"]
    jets = _call("nyj", "Seattle Seahawks", "New York Jets", "AWAY", "2026-10-11T17:00:00", sport="NFL")
    g = P.classify_fills({"calls": [jets], "fills": [
        _fill("g", "KXNFLGAME-26OCT11NYGSEA-NYG", "yes", "New York G wins — Seattle")]})[0]
    assert g.get("call_id") is None
    mci = _call("m", "Manchester City", "Arsenal", "HOME", "2026-10-04T14:00:00", sport="SOCCER")
    assert P.classify_fills({"calls": [mci], "fills": [
        _fill("c", "KXEPLGAME-26OCT04ARSMCI-MCI", "yes", "Man City wins — Arsenal")]})[0]["call_id"] == "m"
    jax = _call("j", "Jacksonville Jaguars", "Tennessee Titans", "HOME", "2026-10-04T17:00:00", "NFL")
    leg = P.classify_fills({"calls": [jax], "fills": [
        _fill("l", "KXNFLGAME-26OCT04TENJAX-JAX", "yes", "Tennessee vs Jacksonville Winner?")]})[0]
    assert leg["call_id"] == "j"


def test_codex_round_7_legacy_two_non_prefix_codes_and_same_side_confirmation():
    """Codex on #299, round 7 (verified): (1) UGAUNC with "Georgia vs North Carolina Winner?" — both codes non-prefix
    — orients by the legacy AWAY-vs-HOME title order; (2) a weak code is confirmed only by the title team on its
    OWN side: NYGNYJ-NYJ "New York Jets wins — New York Giants" never fits the reversed Giants-home call."""
    uga = _call("u", "North Carolina Tar Heels", "Georgia Bulldogs", "HOME", "2026-10-10T19:00:00", sport="NCAA")
    f = P.classify_fills({"calls": [uga], "fills": [
        _fill("a", "KXNCAAFGAME-26OCT10UGAUNC-UNC", "yes", "Georgia vs North Carolina Winner?")]})[0]
    assert f["call_id"] == "u"
    rev = _call("r", "New York Giants", "New York Jets", "HOME", "2026-10-11T17:00:00", sport="NFL")
    g = P.classify_fills({"calls": [rev], "fills": [
        _fill("b", "KXNFLGAME-26OCT11NYGNYJ-NYJ", "yes", "New York Jets wins — New York Giants")]})[0]
    assert g.get("call_id") is None


def test_uefanl_fill_matches_an_intl_call_and_still_a_unl_one():
    """Codex on #325: the production INTL ledger calls store sport "INTL"; a KXUEFANLGAME fill must reach them
    (matching rejects on sport first, so INTL executions fell to the market-only FUN book). UNL calls still match,
    and a UEFANL fill with no call is still a FUN "UNL single". Parity: scripts/ledger_fills_parity_verify.py."""
    assert P.parse_ticker("KXUEFANLGAME-26OCT10ENGSCO-ENG")["sports"] == ["UNL", "INTL"]
    L = {"calls": [_call("i", "Scotland", "England", "AWAY", "2026-10-10T18:45:00", sport="INTL"),
                   _call("u", "France", "Germany", "HOME", "2026-10-13T18:45:00", sport="UNL")],
         "fills": [_fill("fi", "KXUEFANLGAME-26OCT10ENGSCO-ENG", "yes", "England wins — Scotland"),
                   _fill("fu", "KXUEFANLGAME-26OCT13GERFRA-FRA", "yes", "France wins — Germany"),
                   _fill("ff", "KXUEFANLGAME-26OCT20ITANED-NED", "yes", "Netherlands wins — Italy")]}
    by = {f["id"]: f for f in P.classify_fills(L)}
    assert (by["fi"]["book"], by["fi"]["call_id"]) == ("system_matched", "i")
    assert (by["fu"]["book"], by["fu"]["call_id"]) == ("system_matched", "u")
    assert by["ff"]["book"] == "fun" and by["ff"]["category"].startswith("UNL single")
