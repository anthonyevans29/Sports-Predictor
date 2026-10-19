"""The Kalshi matcher (ARCHITECT 2026-10-10 addendum 37 item 2; its day rule, addendum 44 item 1, 2026-10-12):
the event's two names fit a game of the series' own competition on the event's day, one each; the window and the
time gate choose only inside that one pair; two markets claiming one side are both refused; every refusal is
counted by its reason. The slate is receipt A/B of addendum 37 (KXNCAAFGAME, 2026-10-10), names in the "St." form
the receipt quotes; synthetic rows and a throwaway DB only."""
from datetime import datetime, timedelta
import json
from types import SimpleNamespace as NS
import unicodedata

import pytest
from sqlalchemy import select

from src.ingestion import kalshi_match as km

_TEAM_IDS: dict[str, int] = {}


def _team(name):
    return NS(id=_TEAM_IDS.setdefault(name, len(_TEAM_IDS) + 1), name=name)


def game(gid, away, home, kick):
    h, a = _team(home), _team(away)
    return NS(id=gid, utc_date=kick, home_team=h, away_team=a, home_team_id=h.id, away_team_id=a.id)


def event(stamp, legs, occ=None, series="KXNCAAFGAME", bid="0.40", ask="0.42"):
    """One Kalshi event: a market per (ticker suffix, yes_sub_title), each titled "<Team> wins" as today."""
    e = f"{series}-{stamp}"
    return [{"event_ticker": e, "ticker": f"{e}-{sfx}", "title": f"{name} wins", "yes_sub_title": name,
             "occurrence_datetime": occ, "yes_bid_dollars": bid, "yes_ask_dollars": ask} for sfx, name in legs]


def placed(res):
    """{(match_id, side): the market's ticker suffix}."""
    return {k: mk["ticker"].rsplit("-", 1)[1] for k, mk in res.placed.items()}


def run(markets, games, now, hours=48, **kw):
    return km.place(markets, games, now=now, lo=now - timedelta(days=1), hi=now + timedelta(hours=hours), **kw)


Z = lambda s: datetime.fromisoformat(s)                                      # noqa: E731  naive UTC

# --- the 2026-10-10 slate, as stored on the run of 2026-10-08 21:56:38Z (receipt B) ---
HOU_KSU = game(32747, "Houston", "Kansas State", Z("2026-10-10T19:30"))
KU_UTAH = game(32748, "Kansas", "Utah", Z("2026-10-11T02:15"))
FAMU_ALST = game(32810, "Florida A&M", "Alabama State", Z("2026-10-10T20:00"))
UGA_ALA = game(32738, "Georgia", "Alabama", Z("2026-10-10T23:30"))
UND_UNI = game(32812, "North Dakota", "Northern Iowa", Z("2026-10-10T21:00"))
NDSU_UNLV = game(32820, "North Dakota State", "UNLV", Z("2026-10-10T23:00"))
CCAR_MRSH = game(32772, "Coastal Carolina", "Marshall", Z("2026-10-10T23:00"))
SCST_CHSO = game(32817, "South Carolina State", "Charleston Southern", Z("2026-10-10T16:00"))   # moved from 22:00Z
BCU_AAMU = game(32823, "Bethune-Cookman", "Alabama A&M", Z("2026-10-10T17:00"))              # moved from 23:00Z

KUUTAH = event("26OCT10KUUTAH", [("KU", "Kansas"), ("UTAH", "Utah")], occ="2026-10-10T19:00:00Z")
HOUKSU = event("26OCT10HOUKSU", [("HOU", "Houston"), ("KSU", "Kansas St.")])
FAMUALST = event("26OCT10FAMUALST", [("FAMU", "Florida A&M"), ("ALST", "Alabama St.")])
UGAALA = event("26OCT10UGAALA", [("UGA", "Georgia"), ("ALA", "Alabama")], occ="2026-10-10T20:00:00Z")
UNDUNI = event("26OCT10UNDUNI", [("UND", "North Dakota"), ("UNI", "Northern Iowa")])
NDSUUNLV = event("26OCT10NDSUUNLV", [("NDSU", "North Dakota St."), ("UNLV", "UNLV")])
CCARMRSH = event("26OCT10CCARMRSH", [("CCAR", "Coastal Carolina"), ("MRSH", "Marshall")])
SCSTCHSO = event("26OCT10SCSTCHSO", [("SCST", "South Carolina St."), ("CHSO", "Charleston Southern")],
                 occ="2026-10-11T01:00:00Z")
COOKAAMU = event("26OCT10COOKAAMU", [("COOK", "Bethune-Cookman"), ("AAMU", "Alabama A&M")])


def test_famualst_is_placed_on_the_game_a_day_off_when_none_is_on_the_date():
    """The storm move: the row reads 2026-10-09 16:00Z (Friday 11:05 CT), the ticker still 26OCT10."""
    moved = game(32810, "Florida A&M", "Alabama State", Z("2026-10-09T16:00"))
    res = run(FAMUALST, [moved, UGA_ALA, BCU_AAMU], now=Z("2026-10-09T10:00"))
    assert placed(res) == {(32810, "AWAY"): "FAMU", (32810, "HOME"): "ALST"}, res.refused   # "St." read as State
    assert not res.refused


def test_ugaala_is_placed_although_occurrence_is_3h30_before_kickoff():
    """A date-only ticker: occurrence_datetime is an expected expiration; it places nothing and refuses nothing."""
    res = run(UGAALA, [UGA_ALA, FAMU_ALST, BCU_AAMU], now=Z("2026-10-10T11:52"))
    assert placed(res) == {(32738, "AWAY"): "UGA", (32738, "HOME"): "ALA"}, res.refused


def test_kuutah_is_placed_on_the_0215z_kickoff_more_than_5h_from_occurrence():
    """02:15Z on the 11th is 22:15 ET on the 10th: the ticker's own date. Occurrence 19:00Z is 7h15 away."""
    res = run(KUUTAH + HOUKSU, [HOU_KSU, KU_UTAH], now=Z("2026-10-10T11:52"))
    assert placed(res) == {(32748, "AWAY"): "KU", (32748, "HOME"): "UTAH",
                           (32747, "AWAY"): "HOU", (32747, "HOME"): "KSU"}, res.refused


@pytest.mark.parametrize("reverse", [False, True])
def test_case_a_the_run_window_never_sends_a_market_to_a_worse_fitting_game(reverse):
    """Run 2026-10-08 21:56:38Z, window to 10-10 21:56:38Z. Main wrote Kansas on Houston @ Kansas State, Alabama on
    Florida A&M @ Alabama State and North Dakota State on North Dakota @ Northern Iowa. Now the three events whose
    game is outside the window are refused under that reason, and each in-window game holds its own event only."""
    now = Z("2026-10-08T21:56:38")
    games = [HOU_KSU, KU_UTAH, FAMU_ALST, UGA_ALA, UND_UNI, NDSU_UNLV]
    markets = KUUTAH + UGAALA + NDSUUNLV + HOUKSU + FAMUALST + UNDUNI
    res = run(markets[::-1] if reverse else markets, games, now=now)
    assert placed(res) == {(32747, "AWAY"): "HOU", (32747, "HOME"): "KSU",
                           (32810, "AWAY"): "FAMU", (32810, "HOME"): "ALST",
                           (32812, "AWAY"): "UND", (32812, "HOME"): "UNI"}, res.refused
    assert res.refused == {km.OUTSIDE_WINDOW: 6}


@pytest.mark.parametrize("reverse", [False, True])
def test_case_b_a_moved_kickoff_never_sends_a_market_to_another_game(reverse):
    """Run 2026-10-10 11:52Z: South Carolina State @ Charleston Southern moved 22:00Z -> 16:00Z and Bethune-Cookman
    @ Alabama A&M 23:00Z -> 17:00Z. Main stored South Carolina State on Coastal Carolina @ Marshall (dropping
    Coastal Carolina's own leg as a duplicate) and Alabama A&M on Georgia @ Alabama. Now each event holds its game."""
    games = [CCAR_MRSH, SCST_CHSO, BCU_AAMU, UGA_ALA]
    markets = SCSTCHSO + CCARMRSH + COOKAAMU + UGAALA
    res = run(markets[::-1] if reverse else markets, games, now=Z("2026-10-10T11:52"))
    assert placed(res) == {(32817, "AWAY"): "SCST", (32817, "HOME"): "CHSO",
                           (32772, "AWAY"): "CCAR", (32772, "HOME"): "MRSH",
                           (32823, "AWAY"): "COOK", (32823, "HOME"): "AAMU",
                           (32738, "AWAY"): "UGA", (32738, "HOME"): "ALA"}, res.refused
    assert not res.refused


def test_the_five_games_of_receipt_a_each_hold_only_their_own_event():
    """The 2026-10-10 11:52Z file had five rows holding a leg of another game's event (32747 Kansas, 32810 Alabama,
    32812 North Dakota State, 32772 South Carolina State, 32738 Alabama A&M). The whole slate, today's kickoffs."""
    now = Z("2026-10-10T11:52")
    famu_moved = game(32810, "Florida A&M", "Alabama State", Z("2026-10-09T16:00"))
    games = [HOU_KSU, KU_UTAH, famu_moved, UGA_ALA, UND_UNI, NDSU_UNLV, CCAR_MRSH, SCST_CHSO, BCU_AAMU]
    markets = KUUTAH + HOUKSU + FAMUALST + UGAALA + UNDUNI + NDSUUNLV + CCARMRSH + SCSTCHSO + COOKAAMU
    res = run(markets, games, now=now)
    own = {32747: "26OCT10HOUKSU", 32748: "26OCT10KUUTAH", 32738: "26OCT10UGAALA", 32812: "26OCT10UNDUNI",
           32820: "26OCT10NDSUUNLV", 32772: "26OCT10CCARMRSH", 32817: "26OCT10SCSTCHSO", 32823: "26OCT10COOKAAMU"}
    assert {mid for mid, _ in res.placed} == set(own)
    for (mid, _side), mk in res.placed.items():
        assert mk["event_ticker"] == "KXNCAAFGAME-" + own[mid]
    assert res.refused == {km.IN_PLAY: 2}            # Florida A&M @ Alabama State was played on the 9th


def test_two_stored_rows_of_one_pair_on_the_date_refuse_the_event_and_name_the_rows():
    placeholder = game(40001, "South Carolina State", "Charleston Southern", Z("2026-10-10T22:00"))
    res = run(SCSTCHSO, [SCST_CHSO, placeholder], now=Z("2026-10-10T11:52"))
    assert not res.placed and res.refused == {km.TWO_ROWS: 2}
    assert any("32817" in ln and "40001" in ln and "dedupe-matches" in ln for ln in res.lines), res.lines


def test_the_own_date_takes_the_market_before_a_day_off_and_two_days_off_are_refused():
    sat = game(40011, "Kansas", "Utah", Z("2026-10-10T20:00"))
    sun = game(40012, "Kansas", "Utah", Z("2026-10-11T20:00"))
    fri = game(40013, "Kansas", "Utah", Z("2026-10-09T20:00"))
    res = run(KUUTAH, [sun, sat], now=Z("2026-10-08T12:00"), hours=96)
    assert placed(res) == {(40011, "AWAY"): "KU", (40011, "HOME"): "UTAH"}
    res = run(KUUTAH, [fri, sun], now=Z("2026-10-08T12:00"), hours=96)
    assert not res.placed and res.refused == {km.DATE_TIE: 2}
    assert any("2026-10-10" in ln and "ET" in ln and "40013" in ln and "40012" in ln for ln in res.lines), res.lines


def test_an_event_with_one_market_never_places_it():
    """One name alone never places a market (main placed it on the yes team's game: the yes-team fallback)."""
    res = run(KUUTAH[:1], [KU_UTAH], now=Z("2026-10-10T11:52"))
    assert not res.placed and res.refused == {km.NO_PAIR: 1}


def test_two_events_claiming_one_side_of_one_game_are_both_refused():
    twin = event("26OCT10UTAHKU", [("KU", "Kansas"), ("UTAH", "Utah")])
    res = run(KUUTAH + twin, [KU_UTAH], now=Z("2026-10-10T11:52"))
    assert not res.placed and res.refused == {km.TWO_CLAIMS: 4}


def test_a_best_fit_shared_by_two_pairs_is_refused():
    a = game(40021, "Boston College", "Syracuse", Z("2026-10-10T20:00"))
    b = game(40022, "Boston University", "Syracuse Tech", Z("2026-10-10T20:00"))
    res = run(event("26OCT10BOSSYR", [("BOS", "Boston"), ("SYR", "Syracuse")]), [a, b], now=Z("2026-10-10T11:52"))
    # "Syracuse" fits both homes once, "Boston" both aways once: two pairs share the best fit
    assert not res.placed and res.refused == {km.PAIR_TIE: 2}


def test_one_each_a_derby_event_never_lands_on_a_game_of_one_of_its_teams():
    """Main's s1/s2 were each a max over both sides: "Manchester City" and "Manchester United" both fit Manchester
    City v Arsenal (City twice). One each: home with one name and away with the other."""
    derby = event("26OCT10MCIMUN", [("MCI", "Manchester City"), ("MUN", "Manchester United"), ("TIE", "Tie")],
                  series="KXEPLGAME")
    city_ars = game(40031, "Arsenal", "Manchester City", Z("2026-10-10T14:00"))
    tie = lambda m: m["yes_sub_title"] == "Tie"                          # noqa: E731
    res = run(derby, [city_ars], now=Z("2026-10-10T08:00"), is_tie=tie)
    assert not res.placed and res.refused == {km.NO_FIT: 3}
    the_derby = game(40032, "Manchester United", "Manchester City", Z("2026-10-10T16:30"))
    res = run(derby, [city_ars, the_derby], now=Z("2026-10-10T08:00"), is_tie=tie)
    assert placed(res) == {(40032, "HOME"): "MCI", (40032, "AWAY"): "MUN", (40032, "DRAW"): "TIE"}


# --- clock tickers (MLB): the ticker's own date gives the game; a game number is admitted by its clock ---

def test_an_mlb_clock_ticker_takes_the_game_on_its_own_date_and_prints_a_far_clock():
    """Addendum 52 item 4: on a clock ticker with no game number, the ticker's own date is the gate. A kickoff 8h40
    from the clock on the same date was refused by main's gate; it is now placed, with the line giving both times."""
    cin_sf = game(40041, "Cincinnati Reds", "San Francisco Giants", Z("2026-08-25T01:45"))
    mk = event("26AUG242145CINSF", [("CIN", "Cincinnati"), ("SF", "San Francisco")], series="KXMLBGAME",
               occ="2026-08-25T04:45:00Z")
    res = run(mk, [cin_sf], now=Z("2026-08-24T18:00"))
    assert placed(res) == {(40041, "AWAY"): "CIN", (40041, "HOME"): "SF"} and not res.lines
    moved = game(40042, "Cincinnati Reds", "San Francisco Giants", Z("2026-08-24T17:05"))   # 8h40 off, same date
    res = run(mk, [moved], now=Z("2026-08-24T12:00"))
    assert placed(res) == {(40042, "AWAY"): "CIN", (40042, "HOME"): "SF"} and not res.refused
    assert res.lines == ["  ! KXMLBGAME-26AUG242145CINSF: Kalshi's clock 2026-08-24 21:45 ET is 8.7h from our kickoff "
                         "2026-08-24 13:05 ET (match 40042); the ticker's date gives the game"]


# --- addendum 52: the NLCS game of 2026-10-12, on today's shapes ---

LADMIL = event("26OCT122000LADMIL", [("MIL", "Milwaukee"), ("LAD", "Los Angeles D")], series="KXMLBGAME",
               occ="2026-10-13T03:00:00Z")
CLETB = event("26OCT122000CLETB", [("TB", "Tampa Bay"), ("CLE", "Cleveland")], series="KXMLBGAME",
              occ="2026-10-13T03:00:00Z")


def _nlcs():
    today = game(50542, "Los Angeles Dodgers", "Milwaukee Brewers", Z("2026-10-12T21:00"))   # 5:00pm ET
    last_night = game(50530, "Los Angeles Dodgers", "Milwaukee Brewers", Z("2026-10-12T00:00"))   # 8pm ET 10-11
    last_night.status = "finished"
    alcs = game(50543, "Cleveland Guardians", "Tampa Bay Rays", Z("2026-10-13T00:00"))          # 8:00pm ET
    return today, last_night, alcs


def test_the_nlcs_event_takes_the_game_on_its_date_though_the_clock_is_three_hours_off():
    """KXMLBGAME-26OCT122000LADMIL: Kalshi's clock 8:00pm ET, occurrence the clock plus three hours, our first pitch
    5:00pm ET. Main's gate wants 2h of the clock or 5h of occurrence (3h and 6h here) and matched nothing."""
    today, last_night, alcs = _nlcs()
    res = run(LADMIL, [last_night, today, alcs], now=Z("2026-10-12T20:27"))
    assert placed(res) == {(50542, "HOME"): "MIL", (50542, "AWAY"): "LAD"}, res.refused   # Milwaukee at home
    assert res.lines == ["  ! KXMLBGAME-26OCT122000LADMIL: Kalshi's clock 2026-10-12 20:00 ET is 3.0h from our "
                         "kickoff 2026-10-12 17:00 ET (match 50542); the ticker's date gives the game"]
    # the console prints it though nothing is refused (Codex on #474)
    assert km.console_lines(res) == ["  refused: none"] + res.lines


def test_the_alcs_event_on_its_own_row_prints_no_line():
    today, last_night, alcs = _nlcs()
    res = run(CLETB, [last_night, today, alcs], now=Z("2026-10-12T20:27"))
    assert placed(res) == {(50543, "HOME"): "TB", (50543, "AWAY"): "CLE"} and not res.lines and not res.refused


def test_no_game_of_the_pair_on_the_date_refuses_and_places_nothing_on_the_days_either_side():
    """The 21:00 row taken away, the pair's games of the day before and the day after beside it."""
    _, last_night, _ = _nlcs()
    tomorrow = game(50550, "Milwaukee Brewers", "Los Angeles Dodgers", Z("2026-10-14T00:00"))   # 8pm ET 10-13
    res = run(LADMIL, [last_night, tomorrow], now=Z("2026-10-12T12:00"), hours=72)
    assert not res.placed and res.refused == {km.NO_GAME_ON_DATE: 2}
    assert res.lines == ["  ✗ KXMLBGAME-26OCT122000LADMIL: ticker date 2026-10-12, clock 2026-10-12 20:00 ET; no game "
                         "of the pair on that date; our kickoffs 50530 2026-10-11 20:00 ET; 50550 2026-10-13 20:00 ET: "
                         "refused"]


def test_two_games_of_the_pair_on_the_date_with_no_game_number_are_two_rows():
    today, _, _ = _nlcs()
    second = game(50599, "Los Angeles Dodgers", "Milwaukee Brewers", Z("2026-10-13T00:00"))   # 8pm ET, same date
    res = run(LADMIL, [today, second], now=Z("2026-10-12T12:00"))
    assert not res.placed and res.refused == {km.TWO_ROWS: 2}
    assert res.lines == ["  ✗ KXMLBGAME-26OCT122000LADMIL: 2 stored rows of one pair on 2026-10-12 (ids 50542, 50599): "
                         "refused; two games of the pair that day; the clock does not separate them"]


def test_two_rows_at_one_kickoff_minute_are_one_game_twice_and_keep_the_dedupe_words():
    """Addendum 104 item 2 gives the doubleheader words for "two rows hours apart"; rows at one kickoff minute are one
    game stored twice (addendum 105, #569) and keep the dedupe words. The refusal and its reason do not change."""
    today, _, _ = _nlcs()
    twin = game(50598, "Los Angeles Dodgers", "Milwaukee Brewers", Z("2026-10-12T21:00"))   # the same minute
    res = run(LADMIL, [today, twin], now=Z("2026-10-12T12:00"))
    assert not res.placed and res.refused == {km.TWO_ROWS: 2}
    assert res.lines == ["  ✗ KXMLBGAME-26OCT122000LADMIL: 2 stored rows of one pair on 2026-10-12 (ids 50542, 50598): "
                         "refused; rows 50542, 50598 share one kickoff minute: dedupe-matches has to merge them"]


def test_a_doubleheader_with_one_game_stored_twice_names_both():
    today, _, _ = _nlcs()
    twin = game(50598, "Los Angeles Dodgers", "Milwaukee Brewers", Z("2026-10-12T21:00"))
    night = game(50599, "Los Angeles Dodgers", "Milwaukee Brewers", Z("2026-10-13T00:00"))   # 8pm ET, same date
    res = run(LADMIL, [today, twin, night], now=Z("2026-10-12T12:00"))
    assert not res.placed and res.refused == {km.TWO_ROWS: 2}
    assert res.lines == ["  ✗ KXMLBGAME-26OCT122000LADMIL: 3 stored rows of one pair on 2026-10-12 (ids 50542, 50598, "
                         "50599): refused; two games of the pair that day; the clock does not separate them; rows "
                         "50542, 50598 share one kickoff minute: dedupe-matches has to merge them"]


CLEKC_G2 = event("25JUL26CLEKCG2", [("CLE", "Cleveland"), ("KC", "Kansas City")], series="KXMLBGAME")


def test_a_doubleheader_on_a_date_only_ticker_with_a_game_number_suggests_no_merge():
    """ARCHITECT 2026-10-19, addendum 136 item 3: "the suffix "dedupe-matches has to merge them" printed on true
    doubleheaders — e.g. `KXMLBGAME-25JUL26CLEKCG2: 2 stored rows of one pair on 2025-07-26 (ids 8242, 8243)` where
    the kickoffs are 14:40 and 19:15 ET. The suffix belongs ONLY where rows share a kickoff minute [...] A doubleheader
    reads "two games of the pair that day; the G1/G2 suffix is not read (#478)" and no merge is suggested." The
    refusal and its reason do not change; rows at one minute keep the dedupe words, named beside it."""
    g1 = game(8242, "Cleveland Guardians", "Kansas City Royals", Z("2025-07-26T18:40"))   # 14:40 ET
    g2 = game(8243, "Cleveland Guardians", "Kansas City Royals", Z("2025-07-26T23:15"))   # 19:15 ET
    res = run(CLEKC_G2, [g1, g2], now=Z("2025-07-26T12:00"))
    assert not res.placed and res.refused == {km.TWO_ROWS: 2}
    assert res.lines == ["  ✗ KXMLBGAME-25JUL26CLEKCG2: 2 stored rows of one pair on 2025-07-26 (ids 8242, 8243): "
                         "refused; two games of the pair that day; the G1/G2 suffix is not read (#478)"]
    twin = game(8244, "Cleveland Guardians", "Kansas City Royals", Z("2025-07-26T23:15"))  # 8243 stored twice
    res = run(CLEKC_G2, [g1, g2, twin], now=Z("2025-07-26T12:00"))
    assert res.lines == ["  ✗ KXMLBGAME-25JUL26CLEKCG2: 3 stored rows of one pair on 2025-07-26 (ids 8242, 8243, "
                         "8244): refused; two games of the pair that day; the G1/G2 suffix is not read (#478); rows "
                         "8243, 8244 share one kickoff minute: dedupe-matches has to merge them"]
    res = run(CLEKC_G2, [g2, twin], now=Z("2025-07-26T12:00"))
    assert res.lines[0].endswith("refused; rows 8243, 8244 share one kickoff minute: dedupe-matches has to merge them")
    # a date-only ticker with no game number keeps the dedupe words, as built (the college placeholder case above)
    plain = event("25JUL26CLEKC", [("CLE", "Cleveland"), ("KC", "Kansas City")], series="KXMLBGAME")
    assert run(plain, [g1, g2], now=Z("2025-07-26T12:00")).lines[0].endswith("refused; dedupe-matches has to merge them")


def test_main_s_gate_matched_none_of_the_nlcs_markets():
    """The receipt the ruling asks for: main's time gate (2h of the clock or 5h of occurrence) admits no game."""
    from datetime import timedelta
    today, last_night, alcs = _nlcs()
    clock, occ = km.ticker_stamp(LADMIL[0])[1], km.occurrence(LADMIL[0])
    admitted = [g.id for g in (today, last_night, alcs) if abs(g.utc_date - clock) <= timedelta(hours=2)
                or abs(g.utc_date - occ) <= timedelta(hours=5)]
    assert admitted == [50543]                       # only the ALCS game, which the names then refuse


# --- addendum 54 item 6: an event out of step (finding #476), on the ALCS shapes ---

def alcs(stamp, **kw):
    """An ALCS event in Cleveland: Tampa Bay at Cleveland."""
    return event(stamp, [("TB", "Tampa Bay"), ("CLE", "Cleveland")], series="KXMLBGAME", **kw)


E15, E16, E17 = alcs("26OCT151800TBCLE"), alcs("26OCT161800TBCLE"), alcs("26OCT171800TBCLE")   # Games 3, 4, 5


def _alcs_rows(g3_kick, g3_status=None, g4_kick=Z("2026-10-17T22:00"), g5_kick=None):
    """Game 3 rained out of Thursday 2026-10-15 (6pm ET); Game 4 moved to Saturday; Game 5 to Sunday."""
    g3 = game(60003, "Tampa Bay Rays", "Cleveland Guardians", g3_kick)
    if g3_status:
        g3.status = g3_status
    rows = [g3, game(60004, "Tampa Bay Rays", "Cleveland Guardians", g4_kick)]
    if g5_kick:
        rows.append(game(60005, "Tampa Bay Rays", "Cleveland Guardians", g5_kick))
    return rows


def test_the_receipt_s_friday_refuses_the_next_event_behind_the_rained_out_one():
    """The run is Friday 11am ET. Game 3 is played Friday 6pm ET; Game 4 moved to Saturday. 26OCT15 is refused for
    no game on its date, 26OCT16 behind it; nothing on the moved row (main and the switch put 26OCT16 on it)."""
    rows = _alcs_rows(Z("2026-10-16T22:00"))
    res = run(E15 + E16, rows, now=Z("2026-10-16T15:00"))
    assert not res.placed and res.refused == {km.NO_GAME_ON_DATE: 2, km.BEHIND: 2}
    assert res.lines[-1] == ("  ✗ KXMLBGAME-26OCT161800TBCLE: refused behind KXMLBGAME-26OCT151800TBCLE, out of step: "
                             "no game of its two teams on its date 2026-10-15 and its date 2026-10-15 is before the "
                             "day of the run 2026-10-16")
    assert placed(run(E16, rows, now=Z("2026-10-16T15:00"))) == {(60003, "HOME"): "CLE", (60003, "AWAY"): "TB"}  # alone


def test_the_saturday_after_refuses_game_5_s_event_behind_game_4_s():
    """Game 3 finished and its event gone; 26OCT16 open with the finished game on its date: in play, and out of step
    (its date before the run's). Game 5's event is refused behind it; nothing on Game 4's row."""
    rows = _alcs_rows(Z("2026-10-16T22:00"), "finished", g5_kick=Z("2026-10-18T22:00"))
    res = run(E16 + E17, rows, now=Z("2026-10-17T15:00"))
    assert not res.placed and res.refused == {km.IN_PLAY: 2, km.BEHIND: 2}
    assert res.lines == ["  ✗ KXMLBGAME-26OCT171800TBCLE: refused behind KXMLBGAME-26OCT161800TBCLE, out of step: "
                         "its date 2026-10-16 is before the day of the run 2026-10-17"]


def test_the_evening_of_the_rainout_the_postponed_row_is_not_a_game():
    """Game 3's row postponed and still on Thursday: not a game, so 26OCT15 is out of step (no game on its date) and
    26OCT16 is refused behind it."""
    rows = _alcs_rows(Z("2026-10-15T22:00"), "postponed", g4_kick=Z("2026-10-16T22:00"))
    res = run(E15 + E16, rows, now=Z("2026-10-16T03:00"))                       # Thursday 11pm ET
    assert not res.placed and res.refused == {km.NO_GAME_ON_DATE: 2, km.BEHIND: 2}
    assert res.lines[-1] == ("  ✗ KXMLBGAME-26OCT161800TBCLE: refused behind KXMLBGAME-26OCT151800TBCLE, out of step: "
                             "no game of its two teams on its date 2026-10-15")


def test_a_normal_day_has_nothing_out_of_step():
    """Today's shapes (#474): the NLCS and ALCS events of 2026-10-12 and tomorrow's ALCS event with its row."""
    today, last_night, alcs_today = _nlcs()
    tomorrow = game(50560, "Cleveland Guardians", "Tampa Bay Rays", Z("2026-10-14T00:00"))     # 8pm ET 10-13
    cletb13 = event("26OCT132000CLETB", [("TB", "Tampa Bay"), ("CLE", "Cleveland")], series="KXMLBGAME")
    res = run(LADMIL + CLETB + cletb13, [last_night, today, alcs_today, tomorrow], now=Z("2026-10-12T20:27"))
    assert km.BEHIND not in res.refused and not res.refused
    assert set(placed(res)) == {(50542, "HOME"), (50542, "AWAY"), (50543, "HOME"), (50543, "AWAY"),
                                (50560, "HOME"), (50560, "AWAY")}


def test_the_next_day_s_row_not_yet_stored_refuses_tomorrow_s_event_as_today():
    _, _, alcs_today = _nlcs()
    cletb13 = event("26OCT132000CLETB", [("TB", "Tampa Bay"), ("CLE", "Cleveland")], series="KXMLBGAME")
    res = run(CLETB + cletb13, [alcs_today], now=Z("2026-10-12T20:27"))
    assert placed(res) == {(50543, "HOME"): "TB", (50543, "AWAY"): "CLE"}
    assert res.refused == {km.NO_GAME_ON_DATE: 2} and km.BEHIND not in res.refused


def test_yesterday_s_event_still_open_holds_today_s_behind_it_and_another_pair_is_placed():
    _, _, alcs_yday = _nlcs()
    alcs_yday.status = "finished"
    alcs_tonight = game(50560, "Cleveland Guardians", "Tampa Bay Rays", Z("2026-10-14T00:00"))  # 8pm ET 10-13
    nlcs = game(50561, "Los Angeles Dodgers", "Milwaukee Brewers", Z("2026-10-13T21:00"))       # 5pm ET 10-13
    cletb13 = event("26OCT132000CLETB", [("TB", "Tampa Bay"), ("CLE", "Cleveland")], series="KXMLBGAME")
    ladmil13 = event("26OCT131700LADMIL", [("MIL", "Milwaukee"), ("LAD", "Los Angeles D")], series="KXMLBGAME")
    rows = [alcs_yday, alcs_tonight, nlcs]
    res = run(CLETB + cletb13 + ladmil13, rows, now=Z("2026-10-13T15:00"))
    assert placed(res) == {(50561, "HOME"): "MIL", (50561, "AWAY"): "LAD"}
    assert res.refused == {km.IN_PLAY: 2, km.BEHIND: 2}
    assert res.lines == ["  ✗ KXMLBGAME-26OCT132000CLETB: refused behind KXMLBGAME-26OCT122000CLETB, out of step: "
                         "its date 2026-10-12 is before the day of the run 2026-10-13"]
    # it counts whether or not its markets carry a price
    unpriced = event("26OCT122000CLETB", [("TB", "Tampa Bay"), ("CLE", "Cleveland")], series="KXMLBGAME",
                     bid=None, ask=None)
    res = run(unpriced + cletb13, rows, now=Z("2026-10-13T15:00"))
    assert not res.placed and res.refused == {km.NO_PRICE: 2, km.BEHIND: 2}


def test_a_numbered_event_dated_after_an_event_out_of_step_is_refused_behind_it():
    _, _, alcs_yday = _nlcs()
    alcs_yday.status = "finished"
    g2 = game(50562, "Cleveland Guardians", "Tampa Bay Rays", Z("2026-10-13T17:05"))           # 1:05pm ET 10-13
    numbered = event("26OCT131305CLETBG2", [("TB", "Tampa Bay"), ("CLE", "Cleveland")], series="KXMLBGAME")
    assert set(placed(run(numbered, [alcs_yday, g2], now=Z("2026-10-13T12:00")))) == {(50562, "HOME"),
                                                                                      (50562, "AWAY")}   # alone
    res = run(CLETB + numbered, [alcs_yday, g2], now=Z("2026-10-13T12:00"))
    assert not res.placed and res.refused == {km.IN_PLAY: 2, km.BEHIND: 2}
    assert res.lines == ["  ✗ KXMLBGAME-26OCT131305CLETBG2: refused behind KXMLBGAME-26OCT122000CLETB, out of step: "
                         "its date 2026-10-12 is before the day of the run 2026-10-13"]


def test_today_s_seven_events_place_four_legs_and_leave_the_later_events_to_their_own_reasons():
    """Addendum 55 item 3: the seven open events of 2026-10-12 (#473) on the rows as stored at 4:27pm. Tomorrow's rows
    are not stored, so 26OCT132000CLETB and 26OCT142000MILLAD are out of step; the three events after them could not
    have been placed and keep their own reasons, with no line of the behind kind."""
    today, last_night, alcs_today = _nlcs()
    mil_lad = [("MIL", "Milwaukee"), ("LAD", "Los Angeles D")]
    tb_cle = [("TB", "Tampa Bay"), ("CLE", "Cleveland")]
    seven = (LADMIL + CLETB + event("26OCT132000CLETB", tb_cle, series="KXMLBGAME")
             + event("26OCT142000MILLAD", mil_lad, series="KXMLBGAME")
             + event("26OCT152000MILLAD", mil_lad, series="KXMLBGAME") + alcs("26OCT151800TBCLE")
             + alcs("26OCT161800TBCLE"))
    res = run(seven, [last_night, today, alcs_today], now=Z("2026-10-12T20:27"))
    assert placed(res) == {(50542, "HOME"): "MIL", (50542, "AWAY"): "LAD", (50543, "HOME"): "TB",
                           (50543, "AWAY"): "CLE"}                                   # the same four legs as main
    assert res.refused == {km.NO_GAME_ON_DATE: 2, km.NO_FIT: 8} and km.BEHIND not in res.refused
    assert not any("refused behind" in ln for ln in res.lines), res.lines
    by_event = {}
    for m in seven:
        by_event.setdefault(km.event_of(m), []).append(m)
    behind = km.behind_out_of_step(by_event, [last_night, today, alcs_today], now=Z("2026-10-12T20:27"),
                                   is_tie=lambda m: False, implied_prob=lambda m: 0.5)
    assert set(behind) == {"KXMLBGAME-26OCT152000MILLAD", "KXMLBGAME-26OCT151800TBCLE",
                           "KXMLBGAME-26OCT161800TBCLE"}                 # behind, but none would have been placed


def test_the_next_day_s_row_not_stored_with_a_third_event_after_it():
    """The third event is refused for its own reason (no game of the competition on its day fits it), no behind line."""
    _, _, alcs_today = _nlcs()
    tb_cle = [("TB", "Tampa Bay"), ("CLE", "Cleveland")]
    res = run(CLETB + event("26OCT132000CLETB", tb_cle, series="KXMLBGAME")
              + event("26OCT142000CLETB", tb_cle, series="KXMLBGAME"), [alcs_today], now=Z("2026-10-12T20:27"))
    assert placed(res) == {(50543, "HOME"): "TB", (50543, "AWAY"): "CLE"}
    assert res.refused == {km.NO_GAME_ON_DATE: 2, km.NO_FIT: 2}
    assert not any("refused behind" in ln for ln in res.lines), res.lines


def test_the_receipt_s_friday_holds_every_later_event_not_only_the_next():
    """Game 5's event, open too, would take Game 4's moved Saturday row: it is behind 26OCT15 as well."""
    rows = _alcs_rows(Z("2026-10-16T22:00"))
    res = run(E15 + E16 + E17, rows, now=Z("2026-10-16T15:00"))
    assert not res.placed and res.refused == {km.NO_GAME_ON_DATE: 2, km.BEHIND: 4}
    assert [ln.split(":")[0] for ln in res.lines if "refused behind" in ln] == [
        "  ✗ KXMLBGAME-26OCT161800TBCLE", "  ✗ KXMLBGAME-26OCT171800TBCLE"]


def test_the_line_names_the_earliest_of_two_events_out_of_step_and_why_that_one_is():
    """The Saturday after, with Game 3's event not yet settled: 26OCT15 and 26OCT16 are both out of step; Game 5's
    line names 26OCT15 and its own reasons. 26OCT16 keeps its own reason, in play (addendum 55 item 3)."""
    rows = _alcs_rows(Z("2026-10-16T22:00"), "finished", g5_kick=Z("2026-10-18T22:00"))
    res = run(E15 + E16 + E17, rows, now=Z("2026-10-17T15:00"))
    assert not res.placed and res.refused == {km.NO_GAME_ON_DATE: 2, km.IN_PLAY: 2, km.BEHIND: 2}
    assert [ln for ln in res.lines if "refused behind" in ln] == [
        "  ✗ KXMLBGAME-26OCT171800TBCLE: refused behind KXMLBGAME-26OCT151800TBCLE, out of step: no game of its two "
        "teams on its date 2026-10-15 and its date 2026-10-15 is before the day of the run 2026-10-17"]


def test_the_same_two_names_in_the_other_order_are_one_pair_across_the_venue_flip():
    """Yesterday's 26OCT122000CLETB (Tampa Bay, Cleveland) still open; today's game in Cleveland lists its names the
    other way round. By names, not by their order: today's event is behind."""
    _, _, alcs_yday = _nlcs()
    alcs_yday.status = "finished"
    at_cle = game(60013, "Tampa Bay Rays", "Cleveland Guardians", Z("2026-10-13T22:00"))
    flipped = event("26OCT131800TBCLE", [("CLE", "Cleveland"), ("TB", "Tampa Bay")], series="KXMLBGAME")
    assert set(placed(run(flipped, [alcs_yday, at_cle], now=Z("2026-10-13T15:00")))) == {(60013, "HOME"),
                                                                                          (60013, "AWAY")}  # alone
    res = run(CLETB + flipped, [alcs_yday, at_cle], now=Z("2026-10-13T15:00"))
    assert not res.placed and res.refused == {km.IN_PLAY: 2, km.BEHIND: 2}


def test_a_numbered_event_is_never_out_of_step_itself():
    """Yesterday's G2 event still open beside today's event of the pair: only an event with no game number is out of
    step, so today's is placed (the G2 keeps its own reason)."""
    g2_yday = game(50570, "Cleveland Guardians", "Tampa Bay Rays", Z("2026-10-12T21:05"))       # 5:05pm ET 10-12
    g2_yday.status = "finished"
    tonight = game(50560, "Cleveland Guardians", "Tampa Bay Rays", Z("2026-10-14T00:00"))       # 8pm ET 10-13
    g2_ev = event("26OCT121705CLETBG2", [("TB", "Tampa Bay"), ("CLE", "Cleveland")], series="KXMLBGAME")
    cletb13 = event("26OCT132000CLETB", [("TB", "Tampa Bay"), ("CLE", "Cleveland")], series="KXMLBGAME")
    res = run(g2_ev + cletb13, [g2_yday, tonight], now=Z("2026-10-13T15:00"))
    assert placed(res) == {(50560, "HOME"): "TB", (50560, "AWAY"): "CLE"}
    assert res.refused == {km.IN_PLAY: 2} and km.BEHIND not in res.refused


def test_a_date_only_series_is_outside_the_rule():
    """There a moved game is followed a day either side (two events on one game are both refused already): an older
    event of the pair with no game near its date, and dated before the run's day, holds nothing behind it."""
    sat = game(60100, "Houston", "Kansas State", Z("2026-10-17T19:30"))
    old_ev = event("26OCT14HOUKSU", [("HOU", "Houston"), ("KSU", "Kansas St.")])
    sat_ev = event("26OCT17HOUKSU", [("HOU", "Houston"), ("KSU", "Kansas St.")])
    res = run(old_ev + sat_ev, [sat], now=Z("2026-10-17T12:00"))
    assert placed(res) == {(60100, "HOME"): "KSU", (60100, "AWAY"): "HOU"}
    assert res.refused == {km.NO_FIT: 2} and km.BEHIND not in res.refused


def test_an_mlb_doubleheader_takes_its_g1_g2_suffix_inside_the_pair():
    g1 = game(40051, "St. Louis Cardinals", "Chicago Cubs", Z("2026-09-12T17:05"))
    g2 = game(40052, "St. Louis Cardinals", "Chicago Cubs", Z("2026-09-12T23:05"))
    occ = "2026-09-12T20:00:00Z"                       # within 5h of both: the time gate passes both games
    legs = [("STL", "St. Louis"), ("CHC", "Chicago C")]
    m1 = event("26SEP121305STLCHCG1", legs, series="KXMLBGAME", occ=occ)
    m2 = event("26SEP121905STLCHCG2", legs, series="KXMLBGAME", occ=occ)
    res = run(m2 + m1, [g1, g2], now=Z("2026-09-12T12:00"))
    assert placed(res) == {(40051, "AWAY"): "STL", (40051, "HOME"): "CHC",
                           (40052, "AWAY"): "STL", (40052, "HOME"): "CHC"}
    assert {mk["event_ticker"][-2:] for (mid, _), mk in res.placed.items() if mid == 40051} == {"G1"}


def test_the_ticker_stamp_reads_date_and_clock_in_us_eastern():
    assert km.ticker_stamp({"ticker": "KXMLBGAME-26OCT012000PHIATL-PHI"}) == (
        datetime(2026, 10, 1).date(), datetime(2026, 10, 2, 0, 0))
    assert km.ticker_stamp({"event_ticker": "KXNCAAFGAME-26OCT10KUUTAH"}) == (datetime(2026, 10, 10).date(), None)
    assert km.ticker_stamp({"ticker": "K-H", "event_ticker": "EV1"}) == (None, None)
    res = run([{"ticker": "K-H", "event_ticker": "EV1", "yes_sub_title": "Kansas", "yes_bid_dollars": "0.4",
                "yes_ask_dollars": "0.42"},
               {"ticker": "K-A", "event_ticker": "EV1", "yes_sub_title": "Utah", "yes_bid_dollars": "0.5",
                "yes_ask_dollars": "0.52"}], [KU_UTAH], now=Z("2026-10-10T11:52"))
    assert not res.placed and res.refused == {km.NO_DATE: 2}


# --- addendum 50 6(c): rows that are not games ---

@pytest.mark.parametrize("status", ["stale_orphan", "postponed", "cancelled"])
def test_a_row_that_is_not_a_game_takes_no_market_and_is_not_a_row_of_the_pair(status):
    """"A row whose status is cancelled, postponed or stale orphan is not a game for the matcher: it takes no market
    and is not counted among the rows of a pair." Beside its live twin on the date it no longer refuses the event."""
    live = game(40061, "South Carolina State", "Charleston Southern", Z("2026-10-10T16:00"))
    stale = game(40062, "South Carolina State", "Charleston Southern", Z("2026-10-10T22:00"))
    stale.status = status
    res = run(SCSTCHSO, [stale, live], now=Z("2026-10-10T11:52"))
    assert placed(res) == {(40061, "AWAY"): "SCST", (40061, "HOME"): "CHSO"} and not res.refused
    res = run(SCSTCHSO, [stale], now=Z("2026-10-10T11:52"))
    assert not res.placed and res.refused == {km.NO_FIT: 2}


def test_a_started_or_finished_row_stays_a_game_and_its_markets_are_refused_in_play():
    played = game(40063, "South Carolina State", "Charleston Southern", Z("2026-10-10T16:00"))
    played.status = "finished"
    res = run(SCSTCHSO, [played], now=Z("2026-10-10T19:00"))
    assert not res.placed and res.refused == {km.IN_PLAY: 2}
    assert res.why == {mk["ticker"]: km.IN_PLAY for mk in SCSTCHSO}                 # each market's own reason


# --- the read-only replay (addendum 50 6(b)), on a scratch database ---

@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A scratch SQLite with the schema and the ticker column; the replay's read-only session opens it mode=ro."""
    import contextlib

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from src.db.schema import Base
    from src.walters import venue_quote_age as vqa
    path = tmp_path / "replay.db"
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR"))

    @contextlib.contextmanager
    def ro():
        e = create_engine(f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true", connect_args={"uri": True})
        ss = Session(e)
        try:
            yield ss
        finally:
            ss.rollback()
            ss.close()
            e.dispose()
    monkeypatch.setattr(vqa, "readonly_session", ro)
    yield eng
    eng.dispose()


def _seed(eng, comp_code, home, away, kick, sport="NFL"):
    from sqlalchemy.orm import Session

    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with Session(eng) as s:
        comp = s.query(Competition).filter_by(code=comp_code).one_or_none()
        if comp is None:
            comp = Competition(sport=Sport[sport], code=comp_code, name=comp_code, area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        h, a = Team(sport=Sport[sport], name=home), Team(sport=Sport[sport], name=away)
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport[sport], competition_id=comp.id, season="2026", utc_date=kick,
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.commit()
        return m.id


def _main_leg(eng, mid, sel, ticker, at, market="ML"):
    from sqlalchemy import text
    with eng.begin() as c:
        c.execute(text("INSERT INTO odds_snapshots (match_id, market, selection, devig_prob, n_books, captured_at, "
                       "source, market_ticker) VALUES (:m, :mk, :s, 0.5, 1, :at, 'kalshi', :t)"),
                  {"m": mid, "mk": market, "s": sel, "t": ticker,
                   "at": at.isoformat(" ", timespec="microseconds")})   # ISO text, as the ORM writes it


def _payload(now, **series):
    comps = {"KXNCAAFGAME": "NCAA", "KXNFLGAME": "NFL", "KXMLBGAME": "MLB", "KXNHLGAME": "NHL"}
    return {"fetched_at": now.isoformat(), "series": {
        k: {"series": k, "competition": comps[k], "path": "shared", "markets": v} for k, v in series.items()}}


def test_the_replay_places_on_the_series_own_competition_compares_with_main_and_stores_nothing(scratch):
    from sqlalchemy import text

    from src.ingestion import kalshi_replay as kr
    now = Z("2026-10-10T11:52")
    ku = _seed(scratch, "NCAA", "Utah", "Kansas", Z("2026-10-11T02:15"))
    hou = _seed(scratch, "NCAA", "Kansas State", "Houston", Z("2026-10-10T19:30"))
    pro = _seed(scratch, "NFL", "Green Bay Packers", "Chicago Bears", Z("2026-10-10T17:00"))
    t = "KXNCAAFGAME-26OCT10KUUTAH"
    _main_leg(scratch, hou, "HOME", f"{t}-KU", Z("2026-10-10T11:40"))                     # main's wrong leg
    _main_leg(scratch, ku, "AWAY", f"{t}-UTAH", Z("2026-10-10T11:40"))                    # main's leg on the wrong side
    _main_leg(scratch, hou, "AWAY", "KXNCAAFGAME-26OCT10HOUKSU-HOU", Z("2026-10-10T11:40"))  # not in the markets now
    _main_leg(scratch, ku, "HOME", "OLD-TICKER", Z("2026-10-09T11:40"))                   # an older sync: not read
    before = scratch.connect().execute(text("SELECT COUNT(*) FROM odds_snapshots")).scalar()
    lines = []
    out = kr.replay(_payload(now, KXNCAAFGAME=KUUTAH), progress=lines.append)
    r = out["KXNCAAFGAME"]
    assert r["placed"] == 2 and r["main_legs"] == 3 and r["main_at"] == Z("2026-10-10T11:40")
    assert sorted(d.split(":", 1)[1].split("·")[0].strip() for d in r["differ"]) == [
        "on another game or side", "on another game or side", "stored by main and refused now"]
    assert any(f"{t}-KU: on another game or side · main {hou} Houston @ Kansas State HOME · new {ku} Kansas @ Utah "
               "AWAY" in ln for ln in lines), lines
    assert any("not in the open markets now" in ln for ln in lines)
    assert scratch.connect().execute(text("SELECT COUNT(*) FROM odds_snapshots")).scalar() == before   # nothing stored
    # a college market never lands on the NFL game, and the reverse
    nfl = kr.replay(_payload(now, KXNFLGAME=event("26OCT10CHIGB", [("CHI", "Chicago"), ("GB", "Green Bay")],
                                                  series="KXNFLGAME")), progress=lambda _: None)["KXNFLGAME"]
    assert nfl["placed"] == 2 and nfl["games"] == 1 and pro
    col = kr.replay(_payload(now, KXNCAAFGAME=event("26OCT10CHIGB", [("CHI", "Chicago"), ("GB", "Green Bay")])),
                    progress=lambda _: None)["KXNCAAFGAME"]
    assert col["placed"] == 0 and col["refused"] == {km.NO_FIT: 2}


def test_fetch_keeps_the_markets_under_logs_and_reads_every_series(tmp_path, monkeypatch):
    from src.adapters.kalshi import KalshiAdapter
    from src.ingestion import kalshi_replay as kr
    monkeypatch.setattr(kr, "REPO", tmp_path)
    monkeypatch.setattr(KalshiAdapter, "__init__", lambda self: None)
    asked = []
    monkeypatch.setattr(KalshiAdapter, "open_markets_for_series", lambda self, s: asked.append(s) or KUUTAH)
    payload = kr.fetch(progress=lambda _: None)
    assert set(asked[:4]) == {"KXMLBGAME", "KXNFLGAME", "KXNHLGAME", "KXNCAAFGAME"}
    assert set(asked[4:]) == set(KalshiAdapter.SOCCER_GAME_SERIES.values())          # each soccer series resolved
    kept = tmp_path / payload["kept_at"]
    assert kept.parent == tmp_path / "logs" and json.loads(kept.read_text())["series"]["KXNCAAFGAME"]["markets"] == KUUTAH
    assert payload["series"]["KXEPLGAME"]["path"] == "soccer" and payload["series"]["KXEPLGAME"]["competition"] == "PL"
    assert all(v.get("fetched_at") for v in payload["series"].values())           # each series stamped (#470 item 3)


def test_each_series_fetch_time_keeps_its_microseconds(tmp_path, monkeypatch):
    """Codex on #475: a sync's captured_at keeps microseconds; a fetch time cut to the second would put a capture made
    earlier in the same second after the fetch, and the replay would not read it."""
    from src import timeutil
    from src.adapters.kalshi import KalshiAdapter
    from src.ingestion import kalshi_replay as kr
    monkeypatch.setattr(kr, "REPO", tmp_path)
    monkeypatch.setattr(KalshiAdapter, "__init__", lambda self: None)
    monkeypatch.setattr(KalshiAdapter, "open_markets_for_series", lambda self, s: KUUTAH)
    monkeypatch.setattr(timeutil, "utc_now_naive", lambda: datetime(2026, 10, 10, 11, 52, 0, 800000))
    payload = kr.fetch(only=["KXNCAAFGAME"], progress=lambda _: None)
    assert payload["series"]["KXNCAAFGAME"]["fetched_at"] == "2026-10-10T11:52:00.800000"


def test_the_command_replays_a_kept_file_read_only(scratch, tmp_path):
    from click.testing import CliRunner

    import cli
    _seed(scratch, "NCAA", "Utah", "Kansas", Z("2026-10-11T02:15"))
    f = tmp_path / "kalshi_replay_20261010T115200Z.json"
    f.write_text(json.dumps(_payload(Z("2026-10-10T11:52"), KXNCAAFGAME=KUUTAH)))
    r = CliRunner().invoke(cli.cli, ["kalshi-replay", "--from-file", str(f)])
    assert r.exit_code == 0, r.output
    assert "read-only, nothing stored" in r.output and "== KXNCAAFGAME (NCAA, shared path)" in r.output
    assert "new: placed 2 · refused 0" in r.output and "legs that differ: 2" in r.output


# --- Codex on #461 (round 1) ---

def test_a_g2_market_is_not_placed_on_g1_when_g2_is_not_stored():
    """P1: the 5h occurrence window admitted G1 for a G2 market when G2 was missing; a suffix admits by the clock."""
    g1 = game(40071, "St. Louis Cardinals", "Chicago Cubs", Z("2026-09-12T17:05"))
    legs = [("STL", "St. Louis"), ("CHC", "Chicago C")]
    m2 = event("26SEP121905STLCHCG2", legs, series="KXMLBGAME", occ="2026-09-12T20:00:00Z")   # G2 at 23:05Z
    res = run(m2, [g1], now=Z("2026-09-12T12:00"))
    assert not res.placed and res.refused == {km.TIME_GATE: 2}
    m1 = event("26SEP121305STLCHCG1", legs, series="KXMLBGAME", occ="2026-09-12T20:00:00Z")
    assert set(placed(run(m1, [g1], now=Z("2026-09-12T12:00")))) == {(40071, "AWAY"), (40071, "HOME")}


def test_a_clock_field_that_is_no_time_is_unparseable_and_refused():
    """P2: '2460' kept the date and went down the date-only branch."""
    assert km.ticker_stamp({"event_ticker": "KXMLBGAME-26OCT012460PHIATL"}) == (None, None)
    g = game(40072, "Philadelphia Phillies", "Atlanta Braves", Z("2026-10-02T00:00"))
    res = run(event("26OCT012460PHIATL", [("PHI", "Philadelphia"), ("ATL", "Atlanta")], series="KXMLBGAME"), [g],
              now=Z("2026-10-01T12:00"))
    assert not res.placed and res.refused == {km.NO_DATE: 2}


def test_the_replay_plan_reads_discoverable_soccer_competitions_and_lists_the_unresolved(monkeypatch):
    """P2: a competition configured for discovery is read as sync-kalshi-soccer reads it; unresolved is listed."""
    from src.adapters.kalshi import KalshiAdapter
    from src.ingestion import kalshi_replay as kr
    monkeypatch.setattr(KalshiAdapter, "__init__", lambda self: None)
    monkeypatch.setattr(KalshiAdapter, "SOCCER_SERIES_DISCOVERY", {"XA": ["x"], "XB": ["y"]})
    real = KalshiAdapter.resolve_soccer_series

    def resolve(self, code, override=None):
        return {"XA": ("KXXAGAME", "discovered"), "XB": (None, "2 game series match: refused")}.get(code) or \
            real(self, code, override)
    monkeypatch.setattr(KalshiAdapter, "resolve_soccer_series", resolve)
    plan = {p["competition"]: p for p in kr.series_plan(KalshiAdapter())}
    assert plan["XA"]["series"] == "KXXAGAME" and plan["XA"]["path"] == "soccer"
    assert plan["XB"]["unresolved"] == "2 game series match: refused"
    assert {"PL", "UNL", "MLB", "NCAA"} <= set(plan)


def test_the_replay_names_main_s_newest_legs_with_their_age_and_flags_an_old_capture(scratch):
    """P2: a sync that stored nothing leaves no row; the newest legs are named with their age, an old one flagged."""
    from src.ingestion import kalshi_replay as kr
    now = Z("2026-10-10T11:52")
    ku = _seed(scratch, "NCAA", "Utah", "Kansas", Z("2026-10-11T02:15"))
    _main_leg(scratch, ku, "AWAY", "KXNCAAFGAME-26OCT10KUUTAH-KU", Z("2026-10-09T11:40"))     # yesterday's run
    lines = []
    r = kr.replay(_payload(now, KXNCAAFGAME=KUUTAH), progress=lines.append)["KXNCAAFGAME"]
    assert round(r["main_age_h"], 1) == 24.2
    assert any("captured 2026-10-09T11:40:00 (24.2h before these markets were fetched)" in ln for ln in lines), lines
    assert any(ln.startswith("  ⚠ main's newest legs are 24.2h old") for ln in lines)


# --- the switch (addendum 50 6(b)): both sync paths place with this module; what rides it (addendum 51 item 7) ---

def test_both_sync_paths_place_with_the_one_module():
    import inspect

    from src.ingestion import kalshi_sync
    src = inspect.getsource(kalshi_sync)
    assert src.count("km.place(") == 2 and "MAX_START_DRIFT" not in src and "side_score" not in src


def test_one_map_of_series_to_competition_for_the_syncs_and_the_replay():
    """Addendum 51 item 7: the replay's series read venue.KALSHI_SERIES_BY_COMPETITION, as the syncs do."""
    from src.adapters.kalshi import KalshiAdapter
    from src.ingestion import kalshi_replay as kr
    from src.ingestion.kalshi_sync import series_competition
    from src.walters.venue import KALSHI_SERIES_BY_COMPETITION
    assert kr.shared_series() == {"KXNFLGAME": "NFL", "KXNHLGAME": "NHL", "KXNCAAFGAME": "NCAA", "KXMLBGAME": "MLB"}
    assert all(series_competition(s) == c for s, c in kr.shared_series().items())
    assert series_competition(KalshiAdapter.GAME_SERIES[0]) == "MLB" and series_competition("KXNOSUCHGAME") is None
    # a competition in both maps has one series
    assert all(KalshiAdapter.SOCCER_GAME_SERIES[c] == s for c, s in KALSHI_SERIES_BY_COMPETITION.items()
               if c in KalshiAdapter.SOCCER_GAME_SERIES)


def _mlb_row(home, away, kick, status=None):
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "MLB")).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="USA", type="LEAGUE")
            s.add(comp)
        teams = []
        for name in (home, away):
            t = s.execute(select(Team).where(Team.name == name)).scalars().first()
            if t is None:
                t = Team(sport=Sport.MLB, name=name)
                s.add(t)
            teams.append(t)
        s.flush()
        m = Match(sport=Sport.MLB, competition_id=comp.id, season="2091", utc_date=kick,
                  status=status or MatchStatus.SCHEDULED, home_team_id=teams[0].id, away_team_id=teams[1].id)
        s.add(m)
        s.flush()
        return m.id


def test_the_shared_sync_stores_what_the_module_places_and_prints_its_lines(monkeypatch):
    """The NLCS shape on the sync path: the ticker's own date gives the game though the clock is 3h off; a cancelled
    row of the pair on the date is not a game (6(c)); the far-clock line is printed on the sync's console."""
    from src.adapters.kalshi import KalshiAdapter
    from src.db.database import session_scope
    from src.db.schema import MatchStatus, OddsSnapshot
    from src.ingestion import kalshi_sync
    mid = _mlb_row("Marrow Mudhens", "Quillfort Quokkas", Z("2091-10-12T21:00"))             # 5:00pm ET
    gone = _mlb_row("Marrow Mudhens", "Quillfort Quokkas", Z("2091-10-12T23:00"), MatchStatus.CANCELLED)
    mks = event("91OCT122000QQMM", [("MM", "Marrow"), ("QQ", "Quillfort")], series="KXMLBGAME",
                occ="2091-10-13T03:00:00Z", bid="0.53", ask="0.55")
    monkeypatch.setattr(KalshiAdapter, "status", lambda self: {"trading_active": True})
    monkeypatch.setattr(KalshiAdapter, "sports_filters", lambda self: {})
    monkeypatch.setattr(KalshiAdapter, "game_series_markets", lambda self: mks)
    lines = []
    r = kalshi_sync.sync_kalshi_mlb(date_from=Z("2091-10-11T00:00"), date_to=Z("2091-10-14T00:00"),
                                    progress=lines.append)
    assert r["ok"] and r["stored"] == 2 and r["matched"] == 2 and r["unmatched"] == 0 and r["refused"] == {}, r
    assert "  refused: none" in lines
    assert any(ln.startswith("  ! KXMLBGAME-91OCT122000QQMM: Kalshi's clock 2091-10-12 20:00 ET is 3.0h from our "
                             f"kickoff 2091-10-12 17:00 ET (match {mid})") for ln in lines), lines
    with session_scope() as s:
        got = {o.selection: (o.devig_prob, o.market) for o in s.execute(select(OddsSnapshot).where(
            OddsSnapshot.match_id.in_([mid, gone]), OddsSnapshot.source == "kalshi")).scalars()
            if o.match_id == mid}
        assert s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == gone)).first() is None
    assert got == {"HOME": (0.54, "ML"), "AWAY": (0.54, "ML")}


def test_the_shared_sync_refuses_a_series_with_no_competition(monkeypatch):
    from src.adapters.kalshi import KalshiAdapter
    from src.ingestion import kalshi_sync
    monkeypatch.setattr(KalshiAdapter, "status", lambda self: {"trading_active": True})
    monkeypatch.setattr(KalshiAdapter, "sports_filters", lambda self: {})
    monkeypatch.setattr(KalshiAdapter, "open_markets_for_series", lambda self, s: KUUTAH)
    r = kalshi_sync.sync_kalshi_mlb(series_override="KXNOSUCHGAME")
    assert not r["ok"] and "no competition for KXNOSUCHGAME" in r["reason"]


def test_a_time_tie_prints_the_clock_occurrence_and_each_game_that_passed():
    """Addendum 51 item 4: a time-tie refusal prints its line, as the two-row refusal does."""
    g1 = game(40061, "St. Louis Cardinals", "Chicago Cubs", Z("2026-09-12T17:05"))
    g2 = game(40062, "St. Louis Cardinals", "Chicago Cubs", Z("2026-09-12T18:05"))
    res = run(event("26SEP121305STLCHCG3", [("STL", "St. Louis"), ("CHC", "Chicago C")], series="KXMLBGAME",
                    occ="2026-09-12T20:00:00Z"), [g1, g2], now=Z("2026-09-12T12:00"))
    assert not res.placed and res.refused == {km.TIME_TIE: 2}
    assert res.lines == ["  ✗ KXMLBGAME-26SEP121305STLCHCG3: time gate passes 2 games of the pair: Kalshi "
                         "2026-09-12 13:05 ET (occurrence 2026-09-12 16:00 ET); passed 40061 2026-09-12 13:05 ET; "
                         "40062 2026-09-12 14:05 ET: refused"]


def test_the_replay_reads_main_s_newest_legs_at_or_before_the_fetch(scratch):
    """#470 item 2: a --from-file replay after a later sync compares with the capture before its fetch."""
    from src.ingestion import kalshi_replay as kr
    now = Z("2026-10-10T11:52")
    ku = _seed(scratch, "NCAA", "Utah", "Kansas", Z("2026-10-11T02:15"))
    _main_leg(scratch, ku, "AWAY", "KXNCAAFGAME-26OCT10KUUTAH-KU", Z("2026-10-10T11:40"))
    _main_leg(scratch, ku, "HOME", "KXNCAAFGAME-26OCT10KUUTAH-UTAH", Z("2026-10-10T11:40"))
    _main_leg(scratch, ku, "AWAY", "KXNCAAFGAME-26OCT10KUUTAH-KU", Z("2026-10-10T15:00"))   # a sync after the fetch
    r = kr.replay(_payload(now, KXNCAAFGAME=KUUTAH), progress=lambda _: None)["KXNCAAFGAME"]
    assert r["main_at"] == Z("2026-10-10T11:40") and r["main_legs"] == 2 and r["differ"] == []
    assert round(r["main_age_h"], 1) == 0.2
    # a capture earlier in the same second as the fetch is before it (Codex on #475)
    sec = Z("2026-10-10T11:52:00.500000")
    _main_leg(scratch, ku, "AWAY", "KXNCAAFGAME-26OCT10KUUTAH-KU", sec)
    _main_leg(scratch, ku, "HOME", "KXNCAAFGAME-26OCT10KUUTAH-UTAH", sec)
    p = _payload(now, KXNCAAFGAME=KUUTAH)
    p["series"]["KXNCAAFGAME"]["fetched_at"] = "2026-10-10T11:52:00.800000"
    r = kr.replay(p, progress=lambda _: None)["KXNCAAFGAME"]
    assert r["main_at"] == sec and r["main_legs"] == 2


def test_the_replay_places_each_series_at_its_own_fetch_time(scratch):
    """#470 item 3: a game that starts between the run's first fetch and this series' fetch is in play here."""
    from src.ingestion import kalshi_replay as kr
    _seed(scratch, "NCAA", "Kansas State", "Houston", Z("2026-10-10T19:30"))
    p = _payload(Z("2026-10-10T19:20"), KXNCAAFGAME=HOUKSU)
    assert kr.replay(p, progress=lambda _: None)["KXNCAAFGAME"]["placed"] == 2
    p["series"]["KXNCAAFGAME"]["fetched_at"] = "2026-10-10T19:31:00"
    r = kr.replay(p, progress=lambda _: None)["KXNCAAFGAME"]
    assert r["placed"] == 0 and r["refused"] == {km.IN_PLAY: 2}


# --- addendum 54 item 3: the alarm; item 4(a)(b): the commands' refusals ---

NOW54 = Z("2026-10-13T15:00")                                                     # a Tuesday, 11:00 ET


def _a54_comp(code, sport):
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Sport
    init_db()
    with session_scope() as s:
        if s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none() is None:
            s.add(Competition(sport=Sport[sport], code=code, name=code, area="X", type="LEAGUE"))


def _a54_row(code, sport, home, away, kick, status=None):
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == code)).scalar_one()
        h, a = Team(sport=Sport[sport], name=home), Team(sport=Sport[sport], name=away)
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport[sport], competition_id=comp.id, season="2026", utc_date=kick,
                  status=status or MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        return m.id


def _a54_sync(monkeypatch, path, code, markets):
    """Run the shared or the soccer sync at NOW54 on fixed markets; returns (result, console lines)."""
    from src.adapters.kalshi import KalshiAdapter
    from src.ingestion import kalshi_sync
    from src.walters import venue
    series = f"KX{code}GAME"
    monkeypatch.setattr(kalshi_sync, "utc_now_naive", lambda: NOW54)
    monkeypatch.setattr(KalshiAdapter, "status", lambda self: {"trading_active": True})
    monkeypatch.setattr(KalshiAdapter, "sports_filters", lambda self: {})
    monkeypatch.setattr(KalshiAdapter, "open_markets_for_series", lambda self, s: markets)
    lines = []
    if path == "shared":
        monkeypatch.setitem(venue.KALSHI_SERIES_BY_COMPETITION, code, series)
        return kalshi_sync.sync_kalshi_mlb(series_override=series, progress=lines.append), lines
    return kalshi_sync.sync_kalshi_soccer(code, series_override=series, progress=lines.append), lines


def _alarmed(lines):
    return any("MATCHED ZERO" in ln for ln in lines)


@pytest.mark.parametrize("path,sport", [("shared", "NFL"), ("soccer", "SOCCER")])
def test_the_tuesday_shape_is_quiet(monkeypatch, path, sport):
    """Addendum 54 item 3's receipt: a date-only series on a Tuesday at 15:00Z, its two games more than two days out
    (the shared path's window) or past the soccer path's: refused as outside the window, and no alarm."""
    code = f"A54T{path[:2].upper()}"
    _a54_comp(code, sport)
    far = Z("2026-10-21T17:00") if path == "soccer" else Z("2026-10-18T17:00")   # Sunday; soccer: past its 7 days
    _a54_row(code, sport, f"Bram Bats {code}", f"Aard Ants {code}", far)
    _a54_row(code, sport, f"Dune Dogs {code}", f"Cove Cats {code}", far + timedelta(hours=3))
    day = f"{far:%y%b%d}".upper()
    mks = (event(f"{day}AABB", [("AA", f"Aard Ants {code}"), ("BB", f"Bram Bats {code}")], series=f"KX{code}GAME")
           + event(f"{day}CCDD", [("CC", f"Cove Cats {code}"), ("DD", f"Dune Dogs {code}")], series=f"KX{code}GAME"))
    r, lines = _a54_sync(monkeypatch, path, code, mks)
    assert r["ok"] and r["refused"] == {km.OUTSIDE_WINDOW: 4} and r["stored"] == 0, r
    assert not r["alarm"] and not _alarmed(lines), lines


@pytest.mark.parametrize("path,sport", [("shared", "NFL"), ("soccer", "SOCCER")])
def test_a_game_inside_the_window_with_its_event_refused_alarms(monkeypatch, path, sport):
    code = f"A54A{path[:2].upper()}"
    _a54_comp(code, sport)
    _a54_row(code, sport, f"Fox Fens {code}", f"Eel Elks {code}", Z("2026-10-14T23:00"))   # tomorrow, in the window
    own = event("26OCT14EEFF", [("EE", f"Eel Elks {code}"), ("FF", f"Fox Fens {code}")], series=f"KX{code}GAME",
                bid=None, ask=None)                                                         # its own event, unpriced
    unread = event("26OCT14XYZ", [("X", "Xeno"), ("Y", "Yuma")], series=f"KX{code}GAME")   # names read as no fit
    for mks, refused in ((own, {km.NO_PRICE: 2}), (unread, {km.NO_FIT: 2})):
        r, lines = _a54_sync(monkeypatch, path, code, mks)
        assert r["ok"] and r["stored"] == 0 and r["refused"] == refused, r
        assert r["alarm"] and any(ln.startswith("  ⚠ MATCHED ZERO with 2 markets read and 1 unstarted game(s) of the "
                                                "competition inside the run's window") for ln in lines), lines


@pytest.mark.parametrize("path,sport", [("shared", "NFL"), ("soccer", "SOCCER")])
def test_a_window_that_holds_only_a_started_game_is_quiet(monkeypatch, path, sport):
    """Nor a row that is not a game: a cancelled row inside the window does not count either."""
    from src.db.schema import MatchStatus
    code = f"A54S{path[:2].upper()}"
    _a54_comp(code, sport)
    _a54_row(code, sport, f"Gull Gnus {code}", f"Hare Hogs {code}", Z("2026-10-13T13:00"))       # started 2h ago
    _a54_row(code, sport, f"Ibis Imps {code}", f"Jay Jays {code}", Z("2026-10-14T23:00"), MatchStatus.CANCELLED)
    mks = event("26OCT13HHGG", [("HH", f"Hare Hogs {code}"), ("GG", f"Gull Gnus {code}")], series=f"KX{code}GAME")
    r, lines = _a54_sync(monkeypatch, path, code, mks)
    assert r["ok"] and r["stored"] == 0 and r["refused"] == {km.IN_PLAY: 2} and r["in_play"] == 2, r
    assert not r["alarm"] and not _alarmed(lines), lines


def test_the_shared_sync_with_its_competition_not_in_the_db_answers_as_the_soccer_path(monkeypatch):
    """Addendum 54 item 4(b): not ok, competition not in DB (it said '0 stored games' and refused all for no fit)."""
    _a54_comp("A54SEED", "NFL")                                                    # the schema exists
    r, lines = _a54_sync(monkeypatch, "shared", "A54NODB", KUUTAH)
    assert not r["ok"] and r["reason"] == "competition A54NODB not in DB", r
    assert not any("stored" in ln and "games on the events' days" in ln for ln in lines)


@pytest.mark.parametrize("cmd", ["sync-kalshi-ncaa", "sync-kalshi-nhl"])
def test_the_ncaa_and_nhl_commands_print_the_sync_s_reason(monkeypatch, cmd):
    """Addendum 54 item 4(a): they printed r.get('error'), so a refusal read 'None'."""
    from click.testing import CliRunner

    import cli
    from src.ingestion import kalshi_sync
    monkeypatch.setattr(kalshi_sync, "sync_kalshi_mlb", lambda **kw: {
        "ok": False, "reason": "no open markets in X (series ticker may have changed — check available series)",
        "sports_available": ["Hockey", "Football"]})
    out = CliRunner().invoke(cli.cli, [cmd]).output
    assert "no open markets in X" in out and "None" not in out and "Kalshi sports: Hockey, Football" in out, out


# --- addendum 57 item 6: the matcher's pins (lane #479), on the shapes of the morning's console ---

def _soccer(stamp, legs, series):
    """A soccer event: a market per name and the Tie leg."""
    return event(stamp, legs + [("TIE", "Tie")], series=series)


def _is_tie(m):
    return m["yes_sub_title"] == "Tie"


PIN_CASES = [
    # (event, its games, now, is_tie, {(match_id, side): ticker suffix})
    (lambda: event("26OCT16CLMBPENN", [("CLMB", "Columbia"), ("PENN", "Penn")]),
     lambda: [game(32835, "Columbia", "Pennsylvania", Z("2026-10-17T17:00"))], None,
     {(32835, "HOME"): "PENN", (32835, "AWAY"): "CLMB"}),
    (lambda: event("26OCT23YALEPENN", [("PENN", "Penn"), ("YALE", "Yale")]),
     lambda: [game(32901, "Yale", "Pennsylvania", Z("2026-10-24T17:00"))], None,
     {(32901, "HOME"): "PENN", (32901, "AWAY"): "YALE"}),
    (lambda: event("26OCT17ALBYSTON", [("STON", "Stony Brook"), ("ALBY", "University at Albany")]),
     lambda: [game(32902, "UAlbany", "Stony Brook", Z("2026-10-17T17:00"))], None,
     {(32902, "HOME"): "STON", (32902, "AWAY"): "ALBY"}),
    (lambda: event("26OCT24ALBYURI", [("URI", "Rhode Island"), ("ALBY", "University at Albany")]),
     lambda: [game(32903, "UAlbany", "Rhode Island", Z("2026-10-24T17:00"))], None,
     {(32903, "HOME"): "URI", (32903, "AWAY"): "ALBY"}),
    (lambda: event("26OCT17LIUWAG", [("LIU", "LIU"), ("WAG", "Wagner")]),
     lambda: [game(32904, "Long Island University", "Wagner", Z("2026-10-17T17:00"))], None,
     {(32904, "HOME"): "WAG", (32904, "AWAY"): "LIU"}),
    (lambda: event("26OCT24STNHLIU", [("LIU", "LIU"), ("STNH", "Stonehill")]),
     lambda: [game(32905, "Stonehill", "Long Island University", Z("2026-10-24T17:00"))], None,
     {(32905, "HOME"): "LIU", (32905, "AWAY"): "STNH"}),
    (lambda: _soccer("26OCT17RCSPSG", [("PSG", "PSG"), ("RCS", "Strasbourg Alsace")], "KXLIGUE1GAME"),
     lambda: [game(70001, "Paris Saint Germain", "Strasbourg", Z("2026-10-17T19:00"))], _is_tie,
     {(70001, "HOME"): "RCS", (70001, "AWAY"): "PSG", (70001, "DRAW"): "TIE"}),
    (lambda: _soccer("26OCT25PSGOL", [("OL", "Lyon"), ("PSG", "PSG")], "KXLIGUE1GAME"),
     lambda: [game(70002, "Lyon", "Paris Saint Germain", Z("2026-10-25T19:45"))], _is_tie,
     {(70002, "HOME"): "PSG", (70002, "AWAY"): "OL", (70002, "DRAW"): "TIE"}),
    (lambda: _soccer("26OCT18PARREN", [("PAR", "Paris FC"), ("REN", "Stade Rennais")], "KXLIGUE1GAME"),
     lambda: [game(70003, "Rennes", "Paris FC", Z("2026-10-18T13:00"))], _is_tie,
     {(70003, "HOME"): "PAR", (70003, "AWAY"): "REN", (70003, "DRAW"): "TIE"}),
    (lambda: _soccer("26OCT25RENRCS", [("REN", "Stade Rennais"), ("RCS", "Strasbourg Alsace")], "KXLIGUE1GAME"),
     lambda: [game(70004, "Strasbourg", "Rennes", Z("2026-10-25T15:00"))], _is_tie,
     {(70004, "HOME"): "REN", (70004, "AWAY"): "RCS", (70004, "DRAW"): "TIE"}),
    (lambda: _soccer("26OCT18BMGTSG", [("TSG", "Hoffenheim"), ("BMG", "M´gladbach")], "KXBUNDESLIGAGAME"),
     lambda: [game(70005, "TSG Hoffenheim", "Borussia Mönchengladbach", Z("2026-10-18T15:30"))], _is_tie,
     {(70005, "HOME"): "BMG", (70005, "AWAY"): "TSG", (70005, "DRAW"): "TIE"}),
    (lambda: _soccer("26OCT23VFBBMG", [("BMG", "M´gladbach"), ("VFB", "Stuttgart")], "KXBUNDESLIGAGAME"),
     lambda: [game(70006, "Borussia Mönchengladbach", "VfB Stuttgart", Z("2026-10-23T18:30"))], _is_tie,
     {(70006, "HOME"): "VFB", (70006, "AWAY"): "BMG", (70006, "DRAW"): "TIE"}),
]


@pytest.mark.parametrize("case", range(len(PIN_CASES)))
def test_each_refused_event_of_the_console_fits_its_game_with_its_pin(case, monkeypatch):
    mk, rows, is_tie, want = PIN_CASES[case]
    markets, games = mk(), rows()
    now = games[0].utc_date - timedelta(days=1)
    kw = {"is_tie": is_tie} if is_tie else {}
    res = km.place(markets, games, now=now, lo=now - timedelta(days=1), hi=now + timedelta(days=8), **kw)
    assert placed(res) == want and not res.refused, res.refused
    monkeypatch.setattr(km, "PINS", {})                        # without the pin: refused for no fit, as on main
    res = km.place(markets, games, now=now, lo=now - timedelta(days=1), hi=now + timedelta(days=8), **kw)
    assert not res.placed and res.refused == {km.NO_FIT: len(markets)}, res.refused


def test_a_pin_reads_a_name_whole_penn_st_is_not_penn():
    """Penn St. still fits Penn State, and does not fit Pennsylvania."""
    psu = game(70010, "Michigan", "Penn State", Z("2026-10-17T19:30"))
    upenn = game(70011, "Columbia", "Pennsylvania", Z("2026-10-17T17:00"))
    now = Z("2026-10-16T12:00")
    res = run(event("26OCT17MICHPSU", [("MICH", "Michigan"), ("PSU", "Penn St.")]), [psu, upenn], now=now)
    assert placed(res) == {(70010, "HOME"): "PSU", (70010, "AWAY"): "MICH"}
    res = run(event("26OCT17CLMBPSU", [("CLMB", "Columbia"), ("PSU", "Penn St.")]), [upenn], now=now)
    assert not res.placed and res.refused == {km.NO_FIT: 2}
    assert "Penn St." not in km.PINS and km.PINS["Penn"] == "Pennsylvania"


NO_PAIR_CASES = [
    # (event, the day's games, is_tie): the pinned team plays, against someone else; no game of the event's pair
    (lambda: event("26OCT16CLMBPENN", [("CLMB", "Columbia"), ("PENN", "Penn")]),
     lambda: [game(70012, "Princeton", "Pennsylvania", Z("2026-10-16T23:00"))], None),
    (lambda: event("26OCT16CLMBPENN", [("CLMB", "Columbia"), ("PENN", "Penn")]),
     lambda: [game(70012, "Princeton", "Pennsylvania", Z("2026-10-16T23:00")),
              game(70013, "Columbia", "Dartmouth", Z("2026-10-16T23:00"))], None),
    (lambda: _soccer("26OCT17RCSPSG", [("PSG", "PSG"), ("RCS", "Strasbourg Alsace")], "KXLIGUE1GAME"),
     lambda: [game(70014, "Lyon", "Paris Saint Germain", Z("2026-10-17T19:00"))], _is_tie),
]


@pytest.mark.parametrize("case", range(len(NO_PAIR_CASES)))
def test_a_pinned_name_with_no_game_of_its_pair_is_refused_as_today(case, monkeypatch):
    """The pinned team's own game against another side is not the event's game: one name alone never places it."""
    mk, rows, is_tie = NO_PAIR_CASES[case]
    markets, games = mk(), rows()
    kw = {"is_tie": is_tie} if is_tie else {}
    res = run(markets, games, now=Z("2026-10-16T12:00"), **kw)
    assert not res.placed and res.refused == {km.NO_FIT: len(markets)}, res.refused
    monkeypatch.setattr(km, "PINS", {})                        # as today: main refuses it the same way
    res = run(markets, games, now=Z("2026-10-16T12:00"), **kw)
    assert not res.placed and res.refused == {km.NO_FIT: len(markets)}, res.refused


# --- addendum 59 item 2 (#484): a pin fits its own team and no other ---

HEAD_SCORES = [2, 2, 3, 3, 4, 4, 4, 4, 3, 2, 3, 3]          # fit() on #482's head (8c51f89), the pin's name in place


@pytest.mark.parametrize("case", range(len(PIN_CASES)))
def test_each_pinned_event_scores_on_its_own_game_what_the_head_gave_it(case):
    """"Against its own team it scores what the pin's name scores on #482's head": each event's fit on its own game
    is what 8c51f89 gave it (totals of 2 to 4 over the two names)."""
    mk, rows, is_tie, want = PIN_CASES[case]
    markets, g = mk(), rows()[0]
    names = km._names(markets, markets[0], is_tie or (lambda m: False))
    f = km.fit(tuple(names), g.home_team.name, g.away_team.name)
    home = next(sfx for (mid, side), sfx in want.items() if side == "HOME")
    assert f is not None and f[0] == HEAD_SCORES[case]
    assert f[1] == next(m["yes_sub_title"] for m in markets if m["ticker"].endswith("-" + home))


NAMESAKE_CASES = [
    # (event, the lone row: the opponent against the namesake the pin's name shares a word with); the head placed each
    (lambda: _soccer("26OCT18FCBBMG", [("FCB", "Bayern Munich"), ("BMG", "M´gladbach")], "KXBUNDESLIGAGAME"),
     lambda: [game(70020, "Bayern München", "Borussia Dortmund", Z("2026-10-18T16:30"))], _is_tie),
    (lambda: _soccer("26OCT25PSGOL", [("OL", "Lyon"), ("PSG", "PSG")], "KXLIGUE1GAME"),
     lambda: [game(70021, "Lyon", "Paris FC", Z("2026-10-25T19:45"))], _is_tie),
    (lambda: event("26OCT24BRWNLIU", [("BRWN", "Brown"), ("LIU", "LIU")]),
     lambda: [game(70022, "Brown", "Rhode Island", Z("2026-10-24T17:00"))], None),
]


@pytest.mark.parametrize("case", range(len(NAMESAKE_CASES)))
def test_a_pinned_name_never_fits_a_namesake_through_a_shared_word(case):
    """"PSG does not fit Paris FC, M´gladbach does not fit Borussia Dortmund, LIU does not fit Rhode Island": with
    the pins on, each event is refused for no fit on the lone row the head placed it on with a score of 2."""
    mk, rows, is_tie = NAMESAKE_CASES[case]
    markets, games = mk(), rows()
    pinned = next(m["yes_sub_title"] for m in markets if m["yes_sub_title"] in km.PINS)
    g = games[0]
    pin_tokens = km.norm_tokens(km.PINS[pinned])
    assert pin_tokens & (km.norm_tokens(g.home_team.name) | km.norm_tokens(g.away_team.name))   # a word is shared
    kw = {"is_tie": is_tie} if is_tie else {}
    now = g.utc_date - timedelta(days=1)
    res = km.place(markets, games, now=now, lo=now - timedelta(days=1), hi=now + timedelta(days=3), **kw)
    assert not res.placed and res.refused == {km.NO_FIT: len(markets)}, res.refused


@pytest.mark.parametrize("pinned, opponent, stored", [
    ("Penn", "Columbia", "Pennsylvania Quakers"),               # one word more than the pin's name
    ("LIU", "Wagner", "Long Island University Sharks"),         # one word more
    ("LIU", "Wagner", "Long Island"),                           # one word fewer
])
def test_a_pinned_name_needs_the_same_words_not_a_shared_one(pinned, opponent, stored):
    """"The same words under norm_tokens, no more and no fewer": a stored name one word off the pin's is another
    team, and the event is refused for no fit."""
    g = game(70023, opponent, stored, Z("2026-10-17T17:00"))
    res = run(event("26OCT17PINX", [("OPP", opponent), ("PIN", pinned)]), [g], now=Z("2026-10-16T12:00"))
    assert not res.placed and res.refused == {km.NO_FIT: 2}, res.refused


@pytest.mark.parametrize("pinned, other, opponent", [
    ("Stade Rennais", "Stade Brestois 29", "Lyon"),             # stade: a word of the raw Kalshi name
    ("University at Albany", "Long Island University", "Stony Brook"),   # university: likewise
])
def test_a_pinned_name_scores_nothing_through_a_word_of_its_raw_kalshi_name(pinned, other, opponent):
    """The pinned name is its pin against its own team and nothing against any other: the raw name's own words never
    fit either (Stade Rennais does not fit Stade Brestois 29 through stade)."""
    assert km.norm_tokens(pinned) & km.norm_tokens(other)
    assert km.side_score(pinned, other) == 0.0 and km._distinct_score(pinned, other, set()) == 0.0
    res = run(event("26OCT17PINRAW", [("OPP", opponent), ("PIN", pinned)]),
              [game(70025, opponent, other, Z("2026-10-17T17:00"))], now=Z("2026-10-16T12:00"))
    assert not res.placed and res.refused == {km.NO_FIT: 2}, res.refused


@pytest.mark.parametrize("pinned, stored, opponent, score", [
    ("PSG", "Paris Saint-Germain", "Lyon", 3.0),                 # a hyphen
    ("LIU", "long island university", "Wagner", 3.0),            # case
    ("M´gladbach", "BORUSSIA MÖNCHENGLADBACH", "VfB Stuttgart", 2.0),
])
def test_a_pinned_names_own_team_is_read_under_norm_tokens_not_as_a_string(pinned, stored, opponent, score):
    """"The same words under norm_tokens": a stored name that differs from the pin's only in punctuation or case is
    the pin's own team, placed with the score the pin's name has on it."""
    assert km.side_score(pinned, stored) == km.side_score(km.PINS[pinned], stored) == score
    res = run(event("26OCT17PINCASE", [("OPP", opponent), ("PIN", pinned)]),
              [game(70026, opponent, stored, Z("2026-10-17T17:00"))], now=Z("2026-10-16T12:00"))
    assert placed(res) == {(70026, "HOME"): "PIN", (70026, "AWAY"): "OPP"}, res.refused


def test_an_event_name_that_is_not_pinned_is_read_as_before():
    """"An event's name that is not pinned is read as before": Paris FC still fits a lone Lyon @ Paris Saint Germain
    row through paris, as on main (#484's receipt; logged as a limitation, addendum 59 item 3)."""
    res = run(_soccer("26OCT25PFCOL", [("OL", "Lyon"), ("PFC", "Paris FC")], "KXLIGUE1GAME"),
              [game(70024, "Lyon", "Paris Saint Germain", Z("2026-10-25T19:45"))], now=Z("2026-10-24T12:00"),
              is_tie=_is_tie)
    assert placed(res) == {(70024, "HOME"): "PFC", (70024, "AWAY"): "OL", (70024, "DRAW"): "TIE"}


# --- addendum 66 item 4 (2026-10-14): "the Kalshi name "Fenerbahce" pins to the stored club "Fenerbahçe"" ---

FEN = "Fenerbah\u00e7e"          # the stored club as the host's window card prints it, ç as U+00E7


def _avlfen():
    """KXUCLGAME-26OCT14AVLFEN, refused by the laptop's wide probe of 2026-10-14 for no fit ("stored names sharing a
    word: ['Aston Villa']"): Fenerbahçe @ Aston Villa, CL, 2026-10-14 19:00Z."""
    return _soccer("26OCT14AVLFEN", [("AVL", "Aston Villa"), ("FEN", "Fenerbahce")], "KXUCLGAME")


def test_fenerbahce_pins_to_the_stored_club_under_the_same_words():
    """The pin's norm tokens equal the stored name's (as the other pins'); unpinned, the two spellings share no word,
    since norm_tokens folds no accent."""
    assert km.PINS["Fenerbahce"] == FEN and unicodedata.normalize("NFC", FEN) == FEN
    assert km.norm_tokens(km.PINS["Fenerbahce"]) == km.norm_tokens(FEN) == {"fenerbah\u00e7e"}
    assert not km.norm_tokens("Fenerbahce") & km.norm_tokens(FEN)
    assert km.side_score("Fenerbahce", FEN) == km.side_score(FEN, FEN) == 1.0


def test_the_refused_cl_event_fits_its_game_with_the_pin(monkeypatch):
    """The true case: the probe's refused event places on its game, sides by the names, Tie as DRAW; without the pin
    it is refused for no fit, as on main."""
    markets, games = _avlfen(), [game(70030, FEN, "Aston Villa", Z("2026-10-14T19:00"))]
    res = run(markets, games, now=Z("2026-10-13T19:00"), is_tie=_is_tie)
    assert placed(res) == {(70030, "HOME"): "AVL", (70030, "AWAY"): "FEN", (70030, "DRAW"): "TIE"}, res.refused
    assert not res.refused
    monkeypatch.setattr(km, "PINS", {})
    res = run(markets, games, now=Z("2026-10-13T19:00"), is_tie=_is_tie)
    assert not res.placed and res.refused == {km.NO_FIT: 3}, res.refused


@pytest.mark.parametrize("stored", [
    FEN + " SK",                                            # one word more than the pin's name
    unicodedata.normalize("NFD", FEN),                      # ç decomposed (c + U+0327): another spelling, not the stored one
])
def test_fenerbahce_fits_only_the_stored_spelling(stored):
    """"A pin names one stored team": a stored name whose words differ from the pin's is not its team, and the event
    is refused for no fit."""
    assert km.norm_tokens(stored) != km.norm_tokens(FEN)
    assert km.side_score("Fenerbahce", stored) == 0.0 and km._distinct_score("Fenerbahce", stored, set()) == 0.0
    res = run(_avlfen(), [game(70031, stored, "Aston Villa", Z("2026-10-14T19:00"))], now=Z("2026-10-13T19:00"),
              is_tie=_is_tie)
    assert not res.placed and res.refused == {km.NO_FIT: 3}, res.refused


def test_fenerbahce_with_no_game_of_its_pair_is_refused_as_today(monkeypatch):
    """Namesake-free: the pinned club's own game against another side is not the event's game, and the pinned name
    scores nothing against the other clubs of the day."""
    games = [game(70032, FEN, "Galatasaray", Z("2026-10-14T19:00")),
             game(70033, "Aston Villa Women", "Chelsea", Z("2026-10-14T19:00"))]
    assert all(km.side_score("Fenerbahce", t) == 0.0 for t in ("Galatasaray", "Aston Villa Women", "Chelsea"))
    res = run(_avlfen(), games, now=Z("2026-10-13T19:00"), is_tie=_is_tie)
    assert not res.placed and res.refused == {km.NO_FIT: 3}, res.refused
    monkeypatch.setattr(km, "PINS", {})                        # as today: main refuses it the same way
    res = run(_avlfen(), games, now=Z("2026-10-13T19:00"), is_tie=_is_tie)
    assert not res.placed and res.refused == {km.NO_FIT: 3}, res.refused
