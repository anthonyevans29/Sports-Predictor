"""The Kalshi matcher (ARCHITECT 2026-10-10 addendum 37 item 2; its day rule, addendum 44 item 1, 2026-10-12):
the event's two names fit a game of the series' own competition on the event's day, one each; the window and the
time gate choose only inside that one pair; two markets claiming one side are both refused; every refusal is
counted by its reason. The slate is receipt A/B of addendum 37 (KXNCAAFGAME, 2026-10-10), names in the "St." form
the receipt quotes; synthetic rows and a throwaway DB only."""
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

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


# --- clock tickers (MLB): the time gate as built, inside the one pair ---

def test_an_mlb_clock_ticker_keeps_the_time_gate_and_prints_both_times():
    cin_sf = game(40041, "Cincinnati Reds", "San Francisco Giants", Z("2026-08-25T01:45"))
    mk = event("26AUG242145CINSF", [("CIN", "Cincinnati"), ("SF", "San Francisco")], series="KXMLBGAME",
               occ="2026-08-25T04:45:00Z")
    res = run(mk, [cin_sf], now=Z("2026-08-24T18:00"))
    assert placed(res) == {(40041, "AWAY"): "CIN", (40041, "HOME"): "SF"}
    moved = game(40042, "Cincinnati Reds", "San Francisco Giants", Z("2026-08-24T17:05"))   # 8h40 off
    res = run(mk, [moved], now=Z("2026-08-24T12:00"))
    assert not res.placed and res.refused == {km.TIME_GATE: 2}
    assert any("2026-08-24 21:45 ET" in ln and "2026-08-24 13:05 ET" in ln for ln in res.lines), res.lines


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


# --- the series' own competition, through the sync (throwaway DB) ---

def _db_game(comp_code, home, away, kick):
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == comp_code)).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code=comp_code, name=comp_code, area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        h, a = Team(sport=Sport.NFL, name=home), Team(sport=Sport.NFL, name=away)
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.NFL, competition_id=comp.id, season="2026", utc_date=kick,
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        return m.id


def _sync(monkeypatch, series, markets):
    from src.adapters.kalshi import KalshiAdapter
    from src.ingestion import kalshi_sync
    monkeypatch.setattr(KalshiAdapter, "status", lambda self: {"trading_active": True})
    monkeypatch.setattr(KalshiAdapter, "sports_filters", lambda self: {})
    monkeypatch.setattr(KalshiAdapter, "open_markets_for_series", lambda self, s: markets)
    lines = []
    r = kalshi_sync.sync_kalshi_mlb(series_override=series, progress=lines.append)
    return r, lines


def _kalshi_rows(mid):
    from src.db.database import session_scope
    from src.db.schema import OddsSnapshot
    with session_scope() as s:
        return {o.selection for o in s.execute(select(OddsSnapshot).where(
            OddsSnapshot.match_id == mid, OddsSnapshot.source == "kalshi")).scalars()}


def test_a_college_market_is_never_placed_on_an_nfl_game_and_the_reverse(monkeypatch):
    from src.db.database import init_db
    from src.timeutil import utc_now_naive
    init_db()
    kick = utc_now_naive().replace(second=0, microsecond=0) + timedelta(hours=20)
    stamp = km.et_day(kick).strftime("%y%b%d").upper()
    nfl = _db_game("NFL", "Kestrelo Hawks", "Pumaro Cats", kick)
    ncaa = _db_game("NCAA", "Quillon State", "Varrow Tech", kick)
    college = event(stamp + "DRPDRK", [("DRP", "Pumaro Cats"), ("DRK", "Kestrelo Hawks")])
    r, lines = _sync(monkeypatch, "KXNCAAFGAME", college)
    assert r["ok"] and r["competition"] == "NCAA" and r["stored"] == 0, r
    assert r["refused"] == {km.NO_FIT: 2} and any(km.NO_FIT in ln for ln in lines), lines
    pro = event(stamp + "DRTDRS", [("DRT", "Varrow Tech"), ("DRS", "Quillon State")], series="KXNFLGAME")
    r, _ = _sync(monkeypatch, "KXNFLGAME", pro)
    assert r["ok"] and r["competition"] == "NFL" and r["stored"] == 0 and r["refused"] == {km.NO_FIT: 2}, r
    assert _kalshi_rows(nfl) == set() and _kalshi_rows(ncaa) == set()
    r, _ = _sync(monkeypatch, "KXNCAAFGAME", event(stamp + "DRTDRS", [("DRT", "Varrow Tech"),
                                                                        ("DRS", "Quillon State")]))
    assert r["stored"] == 2 and _kalshi_rows(ncaa) == {"HOME", "AWAY"} and _kalshi_rows(nfl) == set(), r


def test_a_series_with_no_competition_is_refused(monkeypatch):
    r, _ = _sync(monkeypatch, "KXNOSUCHGAME", event("26OCT10AB", [("A", "Alpha"), ("B", "Beta")]))
    assert not r["ok"] and "names no competition" in r["reason"], r
