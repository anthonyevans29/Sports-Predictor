"""THE TENNIS WIRING, the fixture and results half (ARCHITECT 2026-11-05, addendum 261 item 2(c); 2026-11-06, addendum
269 items 1-3, addendum 270 item 5; 2026-11-07, addendum 284 item 1(b); lane tennis-market-only, #838).

Kalshi's two tour series are the fixture source AND the results source: the adapter `kalshi_tennis` reads
KXATPMATCH / KXWTAMATCH /markets under open, closed and settled TO THE LAST PAGE (269 item 3(d)), one fixture per
event (players as teams, the full name as served on yes_sub_title: 269 item 3(a)), and the result map of 269 item 3(b):
'yes' / 'no' -> FINISHED with the winner, 'scalar' -> SETTLED_SCALAR with no winner and the fraction kept, '' -> not
settled. The United Cup, exact-score, doubles, Challenger and ITF series are out of scope.

Every market, ticker and player name here is SYNTHETIC (invented for the test; the series tickers and the status and
result words are the ones the stage-1 digest on #838 served). The throwaway DB only (tests/conftest.py); no network:
the HTTP layer is a fake."""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.adapters import kalshi_tennis as kt
from src.db.schema import MatchStatus, Result, Sport

ROOT = Path(__file__).resolve().parent.parent


def mk(event, sfx, name, *, status="active", result="", exp="", value="0.0000", series="KXATPMATCH"):
    """One SYNTHETIC market of `event` (its ticker suffix, its player), with the served fields the map reads."""
    e = f"{series}-{event}"
    return {"event_ticker": e, "ticker": f"{e}-{sfx}", "yes_sub_title": name, "status": status, "result": result,
            "expiration_value": exp, "settlement_value_dollars": value, "title": "Who wins?",
            "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.42", "rules_primary": f"If {name} wins ...",
            "rules_secondary": "SYNTHETIC rules text", "early_close_condition": "SYNTHETIC condition"}


def pair(event, a, b, **kw):
    ra, rb = kw.pop("results", ("", ""))
    ea, eb = kw.pop("exps", ("", ""))
    va, vb = kw.pop("values", ("0.0000", "0.0000"))
    return [mk(event, "AAA", a, result=ra, exp=ea, value=va, **kw), mk(event, "BBB", b, result=rb, exp=eb, value=vb, **kw)]


class FakeKalshi:
    """GET /markets by (series, status) -> pages; each page serves the next page's cursor, the last none. `cursors`
    overrides the cursor a page serves (a repeat, a loop). Every call is recorded."""

    def __init__(self, pages=None, cursors=None, status=None, series_rows=None):
        self.pages = pages or {}
        self.cursors = cursors or {}
        self.calls = []
        self.status = status or {"trading_active": True}
        self.series_rows = series_rows

    def __call__(self, path, params=None):
        params = dict(params or {})
        self.calls.append((path, params))
        if path == "exchange/status":
            return self.status
        if path == "series":
            return {"series": self.series_rows or []}
        assert path == "markets", path
        key = (params["series_ticker"], params["status"])
        pages = self.pages.get(key, [[]])
        i = int(params.get("cursor", "c0")[1:]) if params.get("cursor") else 0
        cur = self.cursors.get((key, i), f"c{i + 1}" if i + 1 < len(pages) else "")
        return {"markets": pages[i] if i < len(pages) else [], "cursor": cur}


# ---- the series: the two tour series and nothing else ------------------------------------------------------------------

def test_the_two_tour_series_only_and_every_out_of_scope_series_is_never_selected():
    """269 item 1 K1: "the market-only record is the two tour series and nothing else"; 284 item 1(b): "the United
    Cup, exact-score, doubles, Challenger and ITF series out of scope". A listing that names out-of-scope tickers (a
    United Cup event served under the ATP series key, by a fault) never becomes a fixture."""
    assert kt.SERIES == {"ATP": "KXATPMATCH", "WTA": "KXWTAMATCH"}
    assert not set(kt.SERIES.values()) & set(kt.OUT_OF_SCOPE)
    for s in ("KXUNITEDCUPMATCH", "KXATPEXACTMATCH", "KXWTAEXACTMATCH", "KXATPDOUBLES", "KXWTADOUBLES",
              "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXITFMATCH", "KXITFWMATCH"):
        assert s in kt.OUT_OF_SCOPE
    from src.walters import venue
    assert {c: s for c, s in venue.KALSHI_SERIES_BY_COMPETITION.items() if "MATCH" in s} == {
        "ATP": "KXATPMATCH", "WTA": "KXWTAMATCH"}
    stray = (pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely", series="KXUNITEDCUPMATCH")
             + pair("26DEC28CCCDDD", "Cal Mockton", "Dov Testerly", series="KXATPDOUBLES"))
    fake = FakeKalshi({("KXATPMATCH", "open"): [stray + pair("26DEC28EEEFFF", "Eli Sampleton", "Fay Dummer")]})
    a = kt.KalshiTennisAdapter(get=fake)
    lst = a.listing("ATP")
    assert [f.event for f in lst.fixtures] == ["KXATPMATCH-26DEC28EEEFFF"]
    assert lst.refused[kt.OUTSIDE_SERIES] == 4
    asked = {p["series_ticker"] for path, p in fake.calls if path == "markets"}
    assert asked == {"KXATPMATCH"}                                     # no other series is ever read
    with pytest.raises(kt.Refused):
        a.listing("KXUNITEDCUPMATCH")


# ---- paging to the last page ---------------------------------------------------------------------------------------------

def test_a_multi_page_listing_is_read_to_its_last_page():
    """269 item 3(d): "the adapter pages to the last page always". Three pages under settled, each cursor followed;
    the last page serves none; every market of every page is read."""
    p1 = pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely")
    p2 = pair("26DEC28CCCDDD", "Cal Mockton", "Dov Testerly")
    p3 = pair("26DEC29EEEFFF", "Eli Sampleton", "Fay Dummer")
    fake = FakeKalshi({("KXATPMATCH", "settled"): [p1, p2, p3]})
    got, n = kt.read_all(fake, "KXATPMATCH", "settled")
    assert n == 3 and [m["ticker"] for m in got] == [m["ticker"] for m in p1 + p2 + p3]
    cursors = [p.get("cursor") for path, p in fake.calls]
    assert cursors == [None, "c1", "c2"]
    lst = kt.KalshiTennisAdapter(get=FakeKalshi({("KXATPMATCH", "settled"): [p1, p2, p3]})).listing("ATP")
    assert lst.pages == {"open": 1, "closed": 1, "settled": 3} and len(lst.fixtures) == 3


@pytest.mark.parametrize("cur", ["", None])
def test_a_missing_or_empty_cursor_is_the_last_page(cur):
    fake = FakeKalshi({("KXWTAMATCH", "open"): [pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely",
                                                     series="KXWTAMATCH"), []]},
                      cursors={(("KXWTAMATCH", "open"), 0): cur})
    got, n = kt.read_all(fake, "KXWTAMATCH", "open")
    assert n == 1 and len(got) == 2 and len(fake.calls) == 1


def test_a_repeated_cursor_is_refused_never_a_loop_never_a_partial_count():
    """A page serving a cursor already read would loop forever: REFUSED after two calls, nothing returned."""
    page = pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely")
    fake = FakeKalshi({("KXATPMATCH", "settled"): [page, page]},
                      cursors={(("KXATPMATCH", "settled"), 0): "c1", (("KXATPMATCH", "settled"), 1): "c1"})
    with pytest.raises(kt.Refused, match="cursor already read"):
        kt.read_all(fake, "KXATPMATCH", "settled")
    assert len(fake.calls) == 2


def test_a_cursor_left_at_the_page_bound_is_a_refusal():
    """A listing still serving a cursor at the bound: REFUSED (a cursor left is a refusal, never a partial count)."""
    fake = FakeKalshi({("KXATPMATCH", "settled"): [[mk("26DEC28AAABBB", f"X{i}", f"P{i}")] for i in range(10)]})
    with pytest.raises(kt.Refused, match="a cursor is still served"):
        kt.read_all(fake, "KXATPMATCH", "settled", max_pages=4)
    assert len(fake.calls) == 4


def test_an_answer_of_the_wrong_shape_is_refused():
    with pytest.raises(kt.Refused, match="not"):
        kt.read_all(lambda p, q: {"markets": "nope"}, "KXATPMATCH", "open")
    with pytest.raises(kt.Refused):
        kt.read_all(lambda p, q: ["not", "an", "object"], "KXATPMATCH", "open")


@pytest.mark.parametrize("body", [{"error": {"code": "SYNTHETIC", "message": "x"}}, {"cursor": ""}, {},
                                  {"markets": None, "cursor": ""}])
def test_an_answer_with_no_markets_list_mid_listing_is_refused_never_an_empty_last_page(body):
    """Review P2 (269 item 3(d): "a cursor left is a refusal, never a partial count"): page 1 serves a market and a
    cursor; page 2 is an error body (or serves no 'markets' list at all). That is REFUSED, never read as an empty last
    page that would end the read 'complete' with page 1's markets only."""
    answers = [{"markets": [{"ticker": "KXATPMATCH-26DEC28AAABBB-AAA"}], "cursor": "c1"}, body]
    with pytest.raises(kt.Refused, match="market set is incomplete"):
        kt.read_all(lambda p, q: answers.pop(0), "KXATPMATCH", "settled")
    assert answers == []


# ---- the fixture: players as teams, the yes_sub_title matcher --------------------------------------------------------

def test_an_event_is_a_fixture_of_its_two_players_named_by_yes_sub_title_never_the_title():
    """269 item 1 K2: "THE MATCHER KEYS ON THE MARKET'S yes_sub_title, NEVER THE EVENT TITLE". The two players are the
    full names as served; home is the name that sorts first (ours: tennis has no home), stable whatever order the
    markets are served in."""
    ev = pair("26DEC28AAABBB", "Zed Synthwood", "Ana Fakely")
    for order in (ev, ev[::-1]):
        for m in order:
            m["title"] = "Somebody vs Somebody Else"                 # never read
        fx = kt.build("ATP", order).fixtures[0]
        assert (fx.home, fx.away, fx.day) == ("Ana Fakely", "Zed Synthwood", date(2026, 12, 28))


@pytest.mark.parametrize("names,why", [
    (("Ana Synthwood", "Ana Synthwood"), kt.NOT_TWO_PLAYERS),         # both markets name one player
    (("ANA SYNTHWOOD", "Ana Synthwood"), kt.NOT_TWO_PLAYERS),         # letter case only: one player (238 item 2(b))
    (("Ana Synthwood", ""), kt.NOT_TWO_PLAYERS),                      # a market naming nobody
    (("Ana Synthwood",), kt.NOT_TWO_MARKETS),
    (("Ana Synthwood", "Bea Fakely", "Cal Mockton"), kt.NOT_TWO_MARKETS),
])
def test_an_event_not_naming_two_players_is_refused_by_its_sentinel_never_guessed(names, why):
    mks = [mk("26DEC28AAABBB", f"S{i}", n) for i, n in enumerate(names)]
    lst = kt.build("ATP", mks)
    assert lst.fixtures == [] and lst.refused == {why: 1} and lst.refused_events == {"KXATPMATCH-26DEC28AAABBB": why}


def test_an_event_with_no_date_in_its_ticker_is_refused():
    mks = [dict(m, event_ticker="KXATPMATCH-NODATE", ticker=f"KXATPMATCH-NODATE-{i}")
           for i, m in enumerate(pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely"))]
    assert kt.build("ATP", mks).refused == {kt.NO_DATE: 1}


def test_players_are_teams_keyed_by_tour_and_name_with_no_alias_table_yet():
    """261 item 2(a): "sport TENNIS, external_ids kind player"; 261 item 2(c): "an alias table built only from
    receipts" (none yet: ALIASES is empty)."""
    assert kt.ALIASES == {}
    assert kt.player_id("ATP", "Ana Synthwood") == kt.player_id("ATP", "ANA SYNTHWOOD") == "ATP|ana synthwood"
    assert kt.player_id("ATP", "Ana Synthwood") != kt.player_id("WTA", "Ana Synthwood")
    a = kt.KalshiTennisAdapter(get=FakeKalshi({("KXATPMATCH", "open"): [pair("26DEC28AAABBB", "Ana Synthwood",
                                                                             "Bea Fakely")]}))
    teams = a.list_teams("ATP", "2026")
    assert {(t.sport, t.name, t.source, t.source_id) for t in teams} == {
        (Sport.TENNIS, "Ana Synthwood", "kalshi_tennis", "ATP|ana synthwood"),
        (Sport.TENNIS, "Bea Fakely", "kalshi_tennis", "ATP|bea fakely")}
    assert a.list_teams("ATP", "2027") == []
    comps = a.list_competitions(Sport.TENNIS)
    assert [(c.code, c.name, c.source_id, c.sport) for c in comps] == [
        ("ATP", "ATP Tennis Match", "KXATPMATCH", Sport.TENNIS), ("WTA", "WTA Tennis Match", "KXWTAMATCH", Sport.TENNIS)]
    assert a.list_competitions(Sport.SOCCER) == [] and a.get_match_stats("x") == []


def test_the_kickoff_is_the_first_instant_of_the_tickers_date_anywhere():
    """Law 4 (no served start time read): 00:00 at UTC+14 of the ticker's date = the day before at 10:00 UTC, so the
    in-play gate stops captures before any match dated that day could start."""
    assert kt.kickoff_utc(date(2026, 12, 28)) == datetime(2026, 12, 27, 10, 0)
    assert kt.EARLIEST_OFFSET.total_seconds() == 14 * 3600


# ---- the result map (269 item 3(b)) -----------------------------------------------------------------------------------

def test_the_contract_terms_are_not_invented_and_sit_before_the_status_map():
    """269 item 3(c): the clause is QUOTED on the PR "BEFORE the status map", from the venue's own text. No record holds
    it, so the adapter carries a TODO-for-receipt marker and its source, and no quote (never invented wording); the
    marker comes before the map in the module."""
    assert kt.CONTRACT_TERMS_QUOTE is None and "contract_terms_url" in kt.CONTRACT_TERMS_SOURCE
    src = (ROOT / "src" / "adapters" / "kalshi_tennis.py").read_text()
    assert src.index("TODO-FOR-RECEIPT") < src.index("THE STATUS MAP (269 item 3(b))") < src.index("def settle(")
    assert src.index("CONTRACT_TERMS_QUOTE") < src.index("RESULT_WORDS = ")


def test_the_result_words_are_exactly_the_four_served():
    assert kt.RESULT_WORDS == ("yes", "no", "scalar", "")
    assert kt.STATUS_WORDS == ("active", "closed", "finalized")


def F(results, exps=("", ""), values=("0.0000", "0.0000"), status="finalized", names=("Ana Synthwood", "Bea Fakely")):
    return pair("26DEC28AAABBB", *names, results=results, exps=exps, values=values, status=status)


def test_yes_no_is_finished_with_the_winner_named_by_expiration_value():
    """'yes' / 'no' → the winner = expiration_value, the loser the other market's player."""
    st = kt.settle(F(("no", "yes"), exps=("Bea Fakely", "Bea Fakely"), values=("0.0000", "1.0000")))
    assert (st.status, st.winner, st.status_raw, st.why) == (MatchStatus.FINISHED, "Bea Fakely", "finalized", None)
    assert st.served["KXATPMATCH-26DEC28AAABBB-BBB"] == {"result": "yes", "settlement_value_dollars": "1.0000",
                                                         "expiration_value": "Bea Fakely"}
    # letter case alone never refuses (addendum 238 item 2(b)): the receipt serves an upper-case expiration_value
    up = kt.settle(F(("yes", "no"), exps=("ANA SYNTHWOOD", "ANA SYNTHWOOD")))
    assert (up.status, up.winner) == (MatchStatus.FINISHED, "Ana Synthwood")


def test_scalar_is_its_own_status_never_a_winner_the_fraction_kept():
    st = kt.settle(F(("scalar", "scalar"), values=("0.3300", "0.6700")))
    assert (st.status, st.winner) == (MatchStatus.SETTLED_SCALAR, None)
    assert {k: v["settlement_value_dollars"] for k, v in st.served.items()} == {
        "KXATPMATCH-26DEC28AAABBB-AAA": "0.3300", "KXATPMATCH-26DEC28AAABBB-BBB": "0.6700"}


def test_empty_is_not_settled_and_stays_scheduled():
    for status in ("active", "closed"):
        st = kt.settle(F(("", ""), status=status))
        assert (st.status, st.winner, st.why, st.status_raw, st.served) == (MatchStatus.SCHEDULED, None, None, status, {})


@pytest.mark.parametrize("results,exps,status,why", [
    (("yes", "yes"), ("Ana Synthwood", "Ana Synthwood"), "finalized", kt.DISAGREE),
    (("no", "no"), ("", ""), "finalized", kt.DISAGREE),
    (("yes", "scalar"), ("Ana Synthwood", ""), "finalized", kt.DISAGREE),
    (("yes", ""), ("Ana Synthwood", ""), "finalized", kt.DISAGREE),
    (("yes", "no"), ("Bea Fakely", "Bea Fakely"), "finalized", kt.WINNER_MISMATCH),     # names the other player
    (("yes", "no"), ("Cal Mockton", "Cal Mockton"), "finalized", kt.WINNER_MISMATCH),   # names neither
    (("yes", "no"), ("", ""), "finalized", kt.WINNER_MISMATCH),                          # names nobody
    (("yes", "no"), ("Ana Synthwood", "Ana Synthwood"), "closed", kt.NOT_FINALIZED),
    (("scalar", "scalar"), ("", ""), "settled", kt.NOT_FINALIZED),                       # a word not served
    (("void", "void"), ("", ""), "finalized", kt.UNMAPPED_RESULT),
])
def test_anything_else_stays_scheduled_labelled_never_a_winner(results, exps, status, why):
    st = kt.settle(F(results, exps=exps, status=status))
    assert (st.status, st.winner, st.why) == (MatchStatus.SCHEDULED, None, why)


def test_a_result_key_not_served_is_not_read_as_empty():
    mks = F(("", ""), status="active")
    for m in mks:
        del m["result"]
    assert kt.settle(mks).why == kt.RESULT_ABSENT


def test_list_matches_maps_the_winner_side_keeps_scores_null_and_filters_by_the_ticker_day():
    """FINISHED: full_time_result is the winner's side; scores None (NULL AND LABELLED, 269 item 2); the season the
    ticker's year (int-style); the window and the season filter on the ticker's day."""
    rows = (pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely", results=("no", "yes"),
                 exps=("Bea Fakely", "Bea Fakely"), status="finalized")
            + pair("26DEC29CCCDDD", "Cal Mockton", "Dov Testerly", results=("scalar", "scalar"),
                   values=("0.2500", "0.7500"), status="finalized")
            + pair("27JAN02EEEFFF", "Eli Sampleton", "Fay Dummer"))
    a = kt.KalshiTennisAdapter(get=FakeKalshi({("KXATPMATCH", "settled"): [rows]}))
    ms = {m.source_id: m for m in a.list_matches("ATP", None, "2026-12-27", "2027-01-03")}
    m1 = ms["KXATPMATCH-26DEC28AAABBB"]
    assert (m1.status, m1.full_time_result, m1.home_score, m1.away_score, m1.season) == (
        MatchStatus.FINISHED, Result.AWAY, None, None, "2026")          # Bea Fakely sorts after Ana Synthwood: AWAY
    assert (m1.home_team_source_id, m1.away_team_source_id) == ("ATP|ana synthwood", "ATP|bea fakely")
    assert m1.utc_date == datetime(2026, 12, 27, 10, 0) and m1.sport == Sport.TENNIS and m1.source == "kalshi_tennis"
    m2 = ms["KXATPMATCH-26DEC29CCCDDD"]
    assert (m2.status, m2.full_time_result) == (MatchStatus.SETTLED_SCALAR, None) and len(m2.settlement) == 2
    assert ms["KXATPMATCH-27JAN02EEEFFF"].season == "2027" and ms["KXATPMATCH-27JAN02EEEFFF"].settlement is None
    assert [m.source_id for m in a.list_matches("ATP", "2027", "2026-12-27", "2027-01-03")] == ["KXATPMATCH-27JAN02EEEFFF"]
    assert [m.source_id for m in a.list_matches("ATP", None, "2026-12-29", "2026-12-29")] == ["KXATPMATCH-26DEC29CCCDDD"]
    # one read serves every call on the instance
    assert sum(1 for path, _ in a._http.calls if path == "markets") == 3


def test_a_market_read_under_two_statuses_is_taken_from_the_later_read():
    """Read in the order open, closed, settled: a market that moved between two reads is the later one."""
    early = pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely")
    late = pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely", results=("yes", "no"),
                exps=("Ana Synthwood", "Ana Synthwood"), status="finalized")
    a = kt.KalshiTennisAdapter(get=FakeKalshi({("KXATPMATCH", "open"): [early], ("KXATPMATCH", "settled"): [late]}))
    fx = a.listing("ATP").fixtures
    assert len(fx) == 1 and fx[0].settlement.status == MatchStatus.FINISHED


# ---- routing, the schema, the bootstrap --------------------------------------------------------------------------------

def test_registry_sport_status_and_cli_routing():
    import cli
    from src.adapters.registry import get_adapter
    assert Sport.TENNIS.value == "tennis" and MatchStatus.SETTLED_SCALAR.value == "settled_scalar"
    assert isinstance(get_adapter(sport="tennis"), kt.KalshiTennisAdapter)
    assert cli._sport_for_competition("ATP") == cli._sport_for_competition("wta") == "tennis"
    assert cli._sport_for_competition("NBA") == "basketball"            # unchanged
    sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
    import closing
    assert "SETTLED_SCALAR" not in closing.VOID          # the market existed and settled: not void


def test_the_bootstrap_routes_tennis_last_and_plans_no_season_pull_only_the_capture():
    """addendum 270 item 5: "no backfill is scheduled": a reference holding tennis rows plans sync-competitions --sport
    tennis and the two Kalshi captures, never a season's sync-teams / sync-matches; catch-up lists the tennis rows as
    accruing, with no steps. A reference without tennis plans exactly what it planned before."""
    sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
    import bootstrap
    assert bootstrap.SPORT_CLI["TENNIS"] == "tennis" and bootstrap.FAMILY_ORDER[-1] == "TENNIS"
    g = lambda sport, comp, n=3: {"sport": sport, "comp": comp, "season": "2026", "status": "SCHEDULED", "n": n}
    plain = {"games": [g("NHL", "NHL")]}
    with_t = {"games": [g("NHL", "NHL"), g("TENNIS", "ATP"), g("TENNIS", "WTA")]}
    p0, p1 = bootstrap.plan(plain), bootstrap.plan(with_t)
    assert ["sync-competitions", "--sport", "tennis"] in p1
    assert not [st for st in p1 if st[0] in ("sync-teams", "sync-matches") and st[2] in ("ATP", "WTA")]
    # the day-one book step is the base adapter's no-op for tennis (kalshi_tennis reads no odds), as NBA's
    from src.adapters.base import DataAdapter
    assert kt.KalshiTennisAdapter.list_odds is DataAdapter.list_odds
    assert p1[-2:] == [["sync-kalshi-atp"], ["sync-kalshi-wta"]]
    assert [st for st in p1 if st not in (["sync-competitions", "--sport", "tennis"], ["sync-kalshi-atp"],
                                          ["sync-kalshi-wta"], ["sync-odds", "--competition", "ATP", "--season", "2026"],
                                          ["sync-odds", "--competition", "WTA", "--season", "2026"])] == p0
    cu = bootstrap.catch_up_plan({"games": []}, with_t)
    tennis = [r for r in cu["behind"] if r["sport"] == "TENNIS"]
    assert len(tennis) == 2 and all(r["accrues"] and r["steps"] == [] for r in tennis)
    assert not [st for st in cu["steps"] if "ATP" in st or "WTA" in st]


# ---- sync-matches end to end through the CLI (throwaway DB, fake HTTP) -------------------------------------------------

@pytest.fixture
def tennis_rows():
    """Removes every ATP / WTA / TENNIS row a test wrote (the throwaway DB is shared across the session)."""
    from src.db.database import init_db
    init_db()
    _clear_tennis()
    yield
    _clear_tennis()


def _clear_tennis():
    from src.db.database import session_scope
    from src.db.schema import Competition, CompetitionTeam, Match, OddsSnapshot, Team
    with session_scope() as s:
        comp_ids = [c.id for c in s.query(Competition).filter(Competition.code.in_(("ATP", "WTA")))]
        ids = [m.id for m in s.query(Match).filter(Match.competition_id.in_(comp_ids))]
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
        s.query(CompetitionTeam).filter(CompetitionTeam.competition_id.in_(comp_ids)).delete(synchronize_session=False)
        s.query(Team).filter(Team.sport == Sport.TENNIS).delete(synchronize_session=False)
        s.query(Competition).filter(Competition.code.in_(("ATP", "WTA"))).delete(synchronize_session=False)


def _fake_http(monkeypatch, fake):
    from src.adapters.kalshi import KalshiAdapter
    monkeypatch.setattr(KalshiAdapter, "_get", lambda self, path, params=None: fake(path, params))


SETTLED = (pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely", results=("no", "yes"),
                exps=("Bea Fakely", "Bea Fakely"), status="finalized")
           + pair("26DEC28CCCDDD", "Cal Mockton", "Dov Testerly", results=("scalar", "scalar"),
                  values=("0.4000", "0.6000"), status="finalized")
           + pair("26DEC01GGGHHH", "Gus Oldfield", "Hal Pastly", results=("yes", "no"),
                  exps=("Gus Oldfield", "Gus Oldfield"), status="finalized"))         # outside the window
OPEN = pair("26DEC29EEEFFF", "Eli Sampleton", "Ana Synthwood")


def test_sync_matches_writes_the_players_then_the_windows_events_with_the_ruled_map(monkeypatch, tennis_rows):
    import cli
    from sqlalchemy import text
    from src.db.database import session_scope
    fake = FakeKalshi({("KXATPMATCH", "settled"): [SETTLED[:4], SETTLED[4:]], ("KXATPMATCH", "open"): [OPEN]})
    _fake_http(monkeypatch, fake)
    run = CliRunner()
    res = run.invoke(cli.cli, ["sync-competitions", "--sport", "tennis"])
    assert res.exit_code == 0, res.output
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--season", "2026", "--date-from", "2026-12-27",
                               "--date-to", "2026-12-29"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "Players (ATP, as teams)" in res.output and "listing(s) of clubs not in the DB" not in res.output
    assert "pages {'open': 1, 'closed': 1, 'settled': 2}" in res.output and "4 events accepted" in res.output
    with session_scope() as s:
        comp = s.execute(text("SELECT sport, type, external_ids FROM competitions WHERE code = 'ATP'")).one()
        assert comp[0] == "TENNIS" and comp[1] == "LEAGUE" and '"kalshi_tennis": "KXATPMATCH"' in comp[2]
        got = {r[0]: r[1:] for r in s.execute(text(
            "SELECT json_extract(m.external_ids, '$.kalshi_tennis'), m.sport, m.season, m.status, m.status_raw, "
            "m.home_score, m.away_score, m.full_time_result, ht.name, at.name, m.utc_date, "
            "json_extract(m.external_ids, '$.kalshi_settlement') FROM matches m "
            "JOIN competitions c ON c.id = m.competition_id JOIN teams ht ON ht.id = m.home_team_id "
            "JOIN teams at ON at.id = m.away_team_id WHERE c.code = 'ATP'"))}
        players = s.execute(text("SELECT name, external_ids FROM teams WHERE sport = 'TENNIS' ORDER BY name")).all()
        linked = s.execute(text("SELECT COUNT(*) FROM competition_teams ct JOIN competitions c "
                                "ON c.id = ct.competition_id WHERE c.code = 'ATP' AND ct.season = '2026'")).scalar()
    assert set(got) == {"KXATPMATCH-26DEC28AAABBB", "KXATPMATCH-26DEC28CCCDDD", "KXATPMATCH-26DEC29EEEFFF"}
    a = got["KXATPMATCH-26DEC28AAABBB"]
    assert a[:9] == ("TENNIS", "2026", "FINISHED", "finalized", None, None, "AWAY", "Ana Synthwood", "Bea Fakely")
    assert str(a[9]).startswith("2026-12-27 10:00")
    assert json.loads(a[10])["KXATPMATCH-26DEC28AAABBB-BBB"]["result"] == "yes"
    c = got["KXATPMATCH-26DEC28CCCDDD"]
    assert c[:7] == ("TENNIS", "2026", "SETTLED_SCALAR", "finalized", None, None, None)
    assert {k: v["settlement_value_dollars"] for k, v in json.loads(c[10]).items()} == {
        "KXATPMATCH-26DEC28CCCDDD-AAA": "0.4000", "KXATPMATCH-26DEC28CCCDDD-BBB": "0.6000"}
    e = got["KXATPMATCH-26DEC29EEEFFF"]
    assert e[2:4] == ("SCHEDULED", "active") and e[6] is None and e[10] is None
    # the players of the window's events only (Gus Oldfield's event is outside it): one row per player
    assert [p[0] for p in players] == ["Ana Synthwood", "Bea Fakely", "Cal Mockton", "Dov Testerly", "Eli Sampleton"]
    assert json.loads(players[0][1]) == {"kalshi_tennis": "ATP|ana synthwood"} and linked == 5
    # a re-run is idempotent: no second row, no second player
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", "2026-12-27",
                               "--date-to", "2026-12-29"])
    assert res.exit_code == 0, res.output
    with session_scope() as s:
        assert s.execute(text("SELECT COUNT(*) FROM matches m JOIN competitions c ON c.id = m.competition_id "
                              "WHERE c.code = 'ATP'")).scalar() == 3
        assert s.execute(text("SELECT COUNT(*) FROM teams WHERE sport = 'TENNIS'")).scalar() == 5


@pytest.mark.parametrize("args,needle", [
    (["--season", "2026"], "--date-from and --date-to are required"),
    (["--seasons", "1"], "--seasons is refused"),
    (["--date-from", "2026-12-01", "--date-to", "2026-12-31"], "is 31 day(s); 1 to 7 are read"),
    (["--date-from", "2026-12-29", "--date-to", "2026-12-28"], "is 0 day(s)"),
    (["--date-from", "2026-12-28", "--date-to", "2026-12-28", "--season", "2026/27"], "--season is int-style"),
])
def test_a_tennis_sync_without_a_bounded_window_is_refused_before_any_call(monkeypatch, tennis_rows, args, needle):
    """addendum 270 item 5: "no model lane exists, so no backfill is scheduled": a season-wide or open-ended tennis
    sync is that backfill, so it is refused before any call; nothing is written."""
    import cli
    fake = FakeKalshi()
    _fake_http(monkeypatch, fake)
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "ATP", *args])
    assert res.exit_code == 2 and needle in res.output, res.output
    assert fake.calls == []


def test_a_paging_refusal_writes_nothing_and_exits_1(monkeypatch, tennis_rows):
    import cli
    from sqlalchemy import text
    from src.db.database import session_scope
    page = SETTLED[:2]
    fake = FakeKalshi({("KXATPMATCH", "settled"): [page, page]},
                      cursors={(("KXATPMATCH", "settled"), 0): "c1", (("KXATPMATCH", "settled"), 1): "c1"})
    _fake_http(monkeypatch, fake)
    run = CliRunner()
    assert run.invoke(cli.cli, ["sync-competitions", "--sport", "tennis"]).exit_code == 0
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", "2026-12-27",
                               "--date-to", "2026-12-29"])
    assert res.exit_code == 1 and "cursor already read" in res.output, res.output
    with session_scope() as s:
        assert s.execute(text("SELECT COUNT(*) FROM teams WHERE sport = 'TENNIS'")).scalar() == 0
        assert s.execute(text("SELECT COUNT(*) FROM matches WHERE sport = 'TENNIS'")).scalar() == 0


def test_a_stored_scheduled_row_settled_after_the_window_is_re_read_and_no_row_is_created(monkeypatch, tennis_rows):
    """Review P2 (late settlements): an event stored SCHEDULED that settles after the chain's next-day run has left
    the {yesterday}..{tomorrow} window. The next sync re-reads it from the SAME listing (no further call) and writes its
    settlement; an event of the same days never stored is NOT created (no backfill, addendum 270 item 5); a row older
    than TENNIS_MAX_WINDOW_DAYS before --date-from is not re-read."""
    import cli
    from sqlalchemy import text
    from src.db.database import session_scope
    open_now = (pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely", status="closed")
                + pair("26DEC10MMMNNN", "Max Oldrow", "Ned Oldrow", status="closed"))
    fake = FakeKalshi({("KXATPMATCH", "closed"): [open_now]})
    _fake_http(monkeypatch, fake)
    run = CliRunner()
    assert run.invoke(cli.cli, ["sync-competitions", "--sport", "tennis"]).exit_code == 0
    for lo, hi in (("2026-12-27", "2026-12-29"), ("2026-12-09", "2026-12-11")):
        res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", lo, "--date-to", hi])
        assert res.exit_code == 0, res.output

    def rows():
        with session_scope() as s:
            return dict(s.execute(text(
                "SELECT json_extract(m.external_ids, '$.kalshi_tennis'), m.status || '|' || "
                "COALESCE(m.full_time_result, '-') FROM matches m JOIN competitions c ON c.id = m.competition_id "
                "WHERE c.code = 'ATP'")).all())
    assert rows() == {"KXATPMATCH-26DEC28AAABBB": "SCHEDULED|-", "KXATPMATCH-26DEC10MMMNNN": "SCHEDULED|-"}
    # three days on: both events settle; an event of 12-28 never stored is now served too
    fake.pages = {("KXATPMATCH", "settled"): [
        pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely", results=("yes", "no"),
             exps=("Ana Synthwood", "Ana Synthwood"), status="finalized")
        + pair("26DEC10MMMNNN", "Max Oldrow", "Ned Oldrow", results=("yes", "no"),
               exps=("Max Oldrow", "Max Oldrow"), status="finalized")
        + pair("26DEC28PPPQQQ", "Pia Unstored", "Quin Unstored", results=("yes", "no"),
               exps=("Pia Unstored", "Pia Unstored"), status="finalized")]}
    calls = len(fake.calls)
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", "2026-12-31",
                               "--date-to", "2027-01-02"])
    assert res.exit_code == 0, res.output
    assert len(fake.calls) - calls == 3                        # one listing read (open, closed, settled), no more
    flat = " ".join(res.output.split())
    assert "ATP re-read (stored SCHEDULED rows dated 2026-12-24..2026-12-30, no new row): 1 re-read · 1 settled " \
           "since: KXATPMATCH-26DEC28AAABBB" in flat, flat
    assert rows() == {"KXATPMATCH-26DEC28AAABBB": "FINISHED|HOME", "KXATPMATCH-26DEC10MMMNNN": "SCHEDULED|-"}
