"""ARCHITECT 2026-11-15, addendum 387 item 3: THE MATCHER, RULED (B), THE REVIEWED NAME TABLE. PR one: the machinery.

"(a) a series DECLARES a table by having one; a declared series' name that is not in its table REFUSES its event under
a new counted reason that names the name; a series with no table is matched as today, to the last character. (b) A line
maps one Kalshi name to one team by the provider's key and id through Team.external_ids, so the laptop and the host
read one table; a line whose id is not among the stored teams of the series' competition refuses, and says so. (c) A
tabled name fits exactly one team; no line can loosen a fit, and the existing pins stand as they are. (d) ... the
proposer MARKS for hand reading, and never proposes, a name or a stored name carrying a mark the tokens drop (an
ampersand, a lone letter, parentheses, a dot other than State's), a name opening with Saint, St. or Mount, a whole read
on two or more teams, and a name with no whole read."

Every table here is written to a throwaway folder (tmp_path) that the test points kalshi_table.TABLE_DIR at; the repo's
own folder holds none (PR one is the machinery and no data). Team names are the real spellings of 353 item 2 and of the
2026-11-13 names read; every provider id is synthetic (9xxx).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner

from src.ingestion import kalshi_match as km
from src.ingestion import kalshi_table as kt

ROOT = Path(__file__).resolve().parent.parent
Z = datetime.fromisoformat
NOW = Z("2026-11-15T15:00")
KEY = "api_basketball"

TEAMS = {   # our team id -> (stored name, provider id)
    1: ("Alabama", "9001"), 2: ("Alabama A&M Bulldogs", "9002"), 3: ("Alabama State", "9003"),
    4: ("San Jose State", "9004"), 5: ("Texas State", "9005"), 6: ("UTSA", "9006"),
    7: ("Purdue Fort Wayne", "9007"), 8: ("Purdue", "9008"),
}


def team(tid):
    name, pid = TEAMS[tid]
    return NS(id=tid, name=name, external_ids={KEY: pid})


def game(gid, away, home, kick, status="scheduled"):
    h, a = team(home), team(away)
    return NS(id=gid, utc_date=kick, home_team=h, away_team=a, home_team_id=h.id, away_team_id=a.id, status=status)


def event(stamp, legs, series="KXNCAAMBGAME", bid="0.40", ask="0.42"):
    e = f"{series}-{stamp}"
    return [{"event_ticker": e, "ticker": f"{e}-{sfx}", "title": f"{name} wins", "yes_sub_title": name,
             "yes_bid_dollars": bid, "yes_ask_dollars": ask} for sfx, name in legs]


SJSU = [("SJSU", "San Jose St."), ("ALST", "Alabama St.")]
AAMU = [("SJSU", "San Jose St."), ("AAMU", "Alabama A&M")]


def write_table(folder: Path, series="KXNCAAMBGAME", lines=None, **over):
    lines = lines if lines is not None else [
        {"name": "Alabama St.", "key": KEY, "id": "9003"}, {"name": "San Jose St.", "key": KEY, "id": "9004"},
        {"name": "Alabama A&M", "key": KEY, "id": "9002"}, {"name": "Alabama", "key": KEY, "id": "9001"},
        {"name": "UTSA", "key": KEY, "id": "9006"}, {"name": "Texas St.", "key": KEY, "id": "9005"}]
    doc = {"series": series, "ruled": "ARCHITECT 2026-11-15, addendum 387 item 3 (a test table)", "lines": lines,
           **over}
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{series}.json"
    p.write_text(json.dumps(doc, indent=1))
    return p


@pytest.fixture
def tables_dir(tmp_path, monkeypatch):
    d = tmp_path / "kalshi_tables"
    d.mkdir()
    monkeypatch.setattr(kt, "TABLE_DIR", d)
    return d


def resolved(folder, series="KXNCAAMBGAME", teams=None):
    return {series: kt.resolve(kt.load(folder / f"{series}.json"), teams or [team(t) for t in TEAMS])}


def run(markets, games, tables=None):
    return km.place(markets, games, now=NOW, lo=NOW - timedelta(days=1), hi=NOW + timedelta(hours=48), tables=tables)


def placed(res):
    return {k: mk["ticker"].rsplit("-", 1)[1] for k, mk in res.placed.items()}


# ---- the repo holds no table (PR one: the machinery and no data) -----------------------------------------------------

def test_the_repo_declares_no_table_and_the_folder_says_how_one_is_declared():
    assert kt.TABLE_DIR == ROOT / "src" / "ingestion" / "kalshi_tables"
    assert kt.declared() == {}
    assert sorted(p.name for p in kt.TABLE_DIR.iterdir()) == ["README.md"]
    readme = (kt.TABLE_DIR / "README.md").read_text()
    assert "addendum 387 item 3" in readme and "holds no table yet" in readme


# ---- (a): a series with no table is matched as today -----------------------------------------------------------------

def test_a_series_with_no_table_is_matched_by_the_scorer_as_today_beside_a_declared_one(tables_dir):
    """KXNCAAFGAME has no table while KXNCAAMBGAME has one: its event is placed by the scorer exactly as with no table
    anywhere, the lone half-fit of 356 item 4(a) included (that is today's matcher, kept to the last character)."""
    write_table(tables_dir)
    ncaaf = event("26NOV15ALSTSJSU", SJSU, series="KXNCAAFGAME")
    half = [game(9811, 1, 4, Z("2026-11-16T05:00"))]          # Alabama at San Jose State: the scorer's half-fit
    with_tables = run(ncaaf, half, tables=resolved(tables_dir))
    for p in tables_dir.iterdir():
        p.unlink()
    assert kt.declared() == {}
    without = run(ncaaf, half)
    assert placed(with_tables) == placed(without) == {(9811, "HOME"): "SJSU", (9811, "AWAY"): "ALST"}
    assert with_tables.refused == without.refused and with_tables.lines == without.lines


# ---- a declared series: placed by its table alone --------------------------------------------------------------------

def test_with_no_table_the_scorer_places_356s_half_fit():
    """Today's matcher on 356 item 4(a)'s shape (the gap the table closes): Alabama State's own game not stored, one
    half-fit stored (Alabama at San Jose State) -> placed on the wrong game. Kept here so the next test's refusal reads
    against it."""
    res = run(event("26NOV15ALSTSJSU", SJSU), [game(9811, 1, 4, Z("2026-11-16T05:00"))])
    assert placed(res) == {(9811, "HOME"): "SJSU", (9811, "AWAY"): "ALST"}


def test_a_declared_series_places_on_the_names_own_teams_and_never_on_a_half_fit(tables_dir):
    """356 item 4(a)'s gap, closed: with Alabama State's own game NOT stored and one half-fit (Alabama at San Jose
    State) stored, the scorer places the event on the wrong game; the table refuses it for no fit. With the right game
    stored too, the table places it there, home and away by the teams' own ids."""
    write_table(tables_dir)
    ev = event("26NOV15ALSTSJSU", SJSU)
    wrong = game(9811, 1, 4, Z("2026-11-16T05:00"))
    res = run(ev, [wrong], resolved(tables_dir))
    assert res.placed == {} and res.refused == {km.NO_FIT: 2}, res.refused
    right = game(9813, 3, 4, Z("2026-11-16T05:00"))
    res = run(ev, [wrong, right], resolved(tables_dir))
    assert placed(res) == {(9813, "HOME"): "SJSU", (9813, "AWAY"): "ALST"} and not res.refused


def test_the_a_and_m_pair_is_two_teams_under_a_table(tables_dir):
    """The correction of #955: "Alabama A&M" reads WHOLE on "Alabama" under the tokens. Under its table line it is
    Alabama A&M's own id: it never fits the Crimson Tide's game, and it fits its own."""
    write_table(tables_dir)
    ev = event("26NOV15AAMUSJSU", AAMU)
    tide = game(9821, 1, 4, Z("2026-11-16T05:00"))
    assert km.side_score("Alabama A&M", "Alabama") == 1.0     # today's tokens: the A&M drops
    res = run(ev, [tide], resolved(tables_dir))
    assert res.placed == {} and res.refused == {km.NO_FIT: 2}
    own = game(9822, 2, 4, Z("2026-11-16T05:00"))
    assert placed(run(ev, [tide, own], resolved(tables_dir))) == {(9822, "HOME"): "SJSU", (9822, "AWAY"): "AAMU"}


def test_the_side_is_the_teams_own_whatever_order_the_names_come_in(tables_dir):
    write_table(tables_dir)
    ev = event("26NOV15TXSTUTSA", [("UTSA", "UTSA"), ("TXST", "Texas St.")])
    home_utsa = game(9831, 5, 6, Z("2026-11-16T01:00"))
    assert placed(run(ev, [home_utsa], resolved(tables_dir))) == {(9831, "HOME"): "UTSA", (9831, "AWAY"): "TXST"}
    home_txst = game(9832, 6, 5, Z("2026-11-16T01:00"))
    assert placed(run(ev, [home_txst], resolved(tables_dir))) == {(9832, "HOME"): "TXST", (9832, "AWAY"): "UTSA"}


def test_two_names_on_one_team_fit_no_game(tables_dir):
    write_table(tables_dir, lines=[{"name": "Alabama St.", "key": KEY, "id": "9003"},
                                   {"name": "Alabama State", "key": KEY, "id": "9003"}])
    ev = event("26NOV15ALSTALST", [("A", "Alabama St."), ("B", "Alabama State")])
    res = run(ev, [game(9841, 3, 4, Z("2026-11-16T05:00"))], resolved(tables_dir))
    assert res.placed == {} and res.refused == {km.NO_FIT: 2}


# ---- (a): a name not in the table refuses its event, the reason naming it ---------------------------------------------

def test_a_name_not_in_the_table_refuses_its_event_under_a_reason_that_names_it(tables_dir):
    """Purdue Fort Wayne's own game is stored and the scorer cannot read "IPFW" whole; with no line for it the event is
    refused, counted under the reason naming the name. A line for it would ADD a placement: one ruling, as a pin is
    (387 item 3(e)); the first table holds none."""
    write_table(tables_dir)
    ev = event("26NOV15IPFWSJSU", [("SJSU", "San Jose St."), ("IPFW", "IPFW")])
    res = run(ev, [game(9851, 7, 4, Z("2026-11-16T05:00"))], resolved(tables_dir))
    want = "not in KXNCAAMBGAME's name table: IPFW"
    assert km.not_in_table("KXNCAAMBGAME", ["IPFW"]) == want
    assert res.placed == {} and res.refused == {want: 2} and res.why == {mk["ticker"]: want for mk in ev}
    both = event("26NOV15ZZZYYY", [("Z", "Nowhere St."), ("Y", "Elsewhere")])
    res = run(both, [], resolved(tables_dir))
    assert res.refused == {"not in KXNCAAMBGAME's name table: Nowhere St. and Elsewhere": 2}


def test_a_pinned_name_is_read_through_a_declared_series_table_and_its_pin_stands_elsewhere(tables_dir):
    """(c): "the existing pins stand as they are": PINS is unchanged, and a series with no table still reads them. On
    a declared series a pinned name is a name like any other: in the table or refused."""
    assert km.PINS["Penn"] == "Pennsylvania" and len(km.PINS) == 7
    write_table(tables_dir)
    penn = [NS(id=50, name="Pennsylvania", external_ids={KEY: "9050"})]
    ev = event("26NOV15PENNSJSU", [("SJSU", "San Jose St."), ("PENN", "Penn")])
    g = NS(id=9861, utc_date=Z("2026-11-16T05:00"), home_team=team(4), away_team=penn[0], home_team_id=4,
           away_team_id=50, status="scheduled")
    res = run(ev, [g], resolved(tables_dir, teams=[team(t) for t in TEAMS] + penn))
    assert res.refused == {"not in KXNCAAMBGAME's name table: Penn": 2}
    ncaaf = event("26NOV15PENNSJSU", [("SJSU", "San Jose St."), ("PENN", "Penn")], series="KXNCAAFGAME")
    assert placed(run(ncaaf, [g], resolved(tables_dir))) == {(9861, "HOME"): "SJSU", (9861, "AWAY"): "PENN"}


# ---- (b): a line whose id is not one stored team refuses, and says so -------------------------------------------------

def test_a_line_whose_id_no_stored_team_holds_refuses_and_says_so(tables_dir):
    write_table(tables_dir, lines=[{"name": "Alabama St.", "key": KEY, "id": "9999"},
                                   {"name": "San Jose St.", "key": KEY, "id": "9004"}])
    ev = event("26NOV15ALSTSJSU", SJSU)
    res = run(ev, [game(9871, 3, 4, Z("2026-11-16T05:00"))], resolved(tables_dir))
    assert res.placed == {} and res.refused == {km.TABLE_LINE_UNRESOLVED: 2}
    assert res.lines == ["  ✗ KXNCAAMBGAME-26NOV15ALSTSJSU: KXNCAAMBGAME's line for 'Alabama St.': api_basketball "
                         "9999 is not among the stored teams of the series' competition: refused"]


def test_a_line_two_stored_teams_answer_to_refuses_and_a_merged_id_resolves():
    table = kt.Table("KXNCAAMBGAME", "r", {"A": kt.Line("A", KEY, "77"), "B": kt.Line("B", KEY, "88")}, "p", "s")
    teams = [NS(id=1, external_ids={KEY: "77"}), NS(id=2, external_ids={KEY: "5", f"{KEY}_also": ["77"]}),
             NS(id=3, external_ids={KEY: "6", f"{KEY}_also": ["88"]})]
    r = kt.resolve(table, teams)
    assert r.team_of == {"B": 3}                         # an id a merge recorded on a row answers to that row
    assert r.unresolved == {"A": "api_basketball 77 is held by 2 stored teams of the series' competition (ids 1, 2)"}


# ---- a declared table the run cannot use: every event of it refused, never the scorer ---------------------------------

@pytest.mark.parametrize("content,why", [
    ("{not json", "is not JSON"),
    (json.dumps({"series": "KXNCAAMBGAME", "ruled": "r", "lines": [], "extra": 1}), "the top level must hold"),
    (json.dumps({"series": "KXNCAAFGAME", "ruled": "r", "lines": []}), "is not its file's name"),
    (json.dumps({"series": "KXNCAAMBGAME", "ruled": " ", "lines": []}), "'ruled' must name"),
    (json.dumps({"series": "KXNCAAMBGAME", "ruled": "r", "lines": [{"name": "A", "key": KEY, "id": 9003}]}),
     "line 1's id must be a non-empty string"),
    (json.dumps({"series": "KXNCAAMBGAME", "ruled": "r", "lines": [{"name": "A ", "key": KEY, "id": "1"}]}),
     "line 1's name must be a non-empty string with no outer space"),
    (json.dumps({"series": "KXNCAAMBGAME", "ruled": "r", "lines": [{"name": "A", "key": KEY, "id": "1", "x": 2}]}),
     "line 1 must hold exactly"),
    (json.dumps({"series": "KXNCAAMBGAME", "ruled": "r", "lines": [{"name": "A", "key": KEY, "id": "1"},
                                                                    {"name": "A", "key": KEY, "id": "2"}]}),
     "has two lines"),
    (json.dumps({"series": "KXNCAAMBGAME", "ruled": "r", "lines": [{"name": "Utsa", "key": KEY, "id": "1"},
                                                                    {"name": "UTSA", "key": KEY, "id": "2"}]}),
     "differ only by case"),
    ('{"series": "KXNCAAMBGAME", "series": "KXNCAAMBGAME", "ruled": "r", "lines": []}', "appears twice"),
])
def test_a_table_that_is_not_a_table_refuses_every_event_of_its_series(tables_dir, content, why):
    (tables_dir / "KXNCAAMBGAME.json").write_text(content)
    with pytest.raises(kt.TableError, match=why):
        kt.load(tables_dir / "KXNCAAMBGAME.json")
    err = kt.tables_for(None, event("26NOV15ALSTSJSU", SJSU), [])["KXNCAAMBGAME"]
    assert isinstance(err, kt.TableError)
    ev = event("26NOV15ALSTSJSU", SJSU) + event("26NOV15TXSTUTSA", [("UTSA", "UTSA"), ("TXST", "Texas St.")])
    res = run(ev, [game(9881, 3, 4, Z("2026-11-16T05:00")), game(9882, 5, 6, Z("2026-11-16T01:00"))],
              {"KXNCAAMBGAME": err})
    assert res.placed == {} and res.refused == {km.TABLE_UNREADABLE: 4}
    assert len(res.lines) == 1 and res.lines[0].startswith("  ✗ KXNCAAMBGAME: its name table cannot be read (")


def test_a_caller_that_does_not_read_a_declared_table_places_nothing_of_its_series(tables_dir):
    """place() reads the folder itself, so no caller can leave a declared series to the scorer."""
    write_table(tables_dir)
    ev = event("26NOV15ALSTSJSU", SJSU)
    res = run(ev, [game(9891, 3, 4, Z("2026-11-16T05:00"))], tables=None)
    assert res.placed == {} and res.refused == {km.TABLE_UNREAD: 2}
    assert res.lines == ["  ✗ KXNCAAMBGAME: the series declares a name table (KXNCAAMBGAME.json) and this run did not "
                         "read it: every event of it refused"]


# ---- the out-of-step read uses the table too -------------------------------------------------------------------------

def test_the_out_of_step_read_of_a_declared_series_reads_the_names_teams_not_their_words(tables_dir):
    """A clock series (ticker 26NOV151900 ...): "out of step" is "no game of its two teams on its date". Under a table
    that is the two names' own teams: a word-fit game of another pair on the date does not keep the event in step."""
    series = "KXTESTCLOCK"
    write_table(tables_dir, series=series)
    tables = resolved(tables_dir, series)
    first = event("26NOV141900ALSTSJSU", SJSU, series=series)       # its own game is not stored: out of step
    later = event("26NOV161900ALSTSJSU", SJSU, series=series)
    by_event = {km.event_of(first[0]): first, km.event_of(later[0]): later}
    half = game(9901, 1, 4, Z("2026-11-15T00:00"))                   # Alabama at San Jose State, 11-14 ET
    own_later = game(9902, 3, 4, Z("2026-11-17T00:00"))
    scorer = km.behind_out_of_step(by_event, [half, own_later], now=NOW, is_tie=lambda m: False,
                                   implied_prob=lambda m: 0.4)
    team_of = {"Alabama St.": 3, "San Jose St.": 4}
    tabled = km.behind_out_of_step(by_event, [half, own_later], now=NOW, is_tie=lambda m: False,
                                   implied_prob=lambda m: 0.4,
                                   team_of_event=lambda ev, names: {n: team_of[n] for n in names})
    later_ev = km.event_of(later[0])
    assert "no game of its two teams" not in scorer.get(later_ev, "")       # the half-fit kept it in step
    assert "no game of its two teams on its date 2026-11-14" in tabled[later_ev]
    skipped = km.behind_out_of_step(by_event, [half, own_later], now=NOW, is_tie=lambda m: False,
                                    implied_prob=lambda m: 0.4, team_of_event=lambda ev, names: False)
    assert skipped == {}
    assert tables[series].team_of == {"Alabama St.": 3, "San Jose St.": 4, "Alabama A&M": 2, "Alabama": 1,
                                      "UTSA": 6, "Texas St.": 5}


# ---- tables_for: no declared series, no read --------------------------------------------------------------------------

def test_tables_for_reads_nothing_when_no_series_among_the_markets_is_declared(tables_dir, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the database was read with no declared series among the markets")
    monkeypatch.setattr(kt, "competition_teams", boom)
    assert kt.tables_for(None, event("26NOV15ALSTSJSU", SJSU), [1]) == {}
    write_table(tables_dir, series="KXNCAAFGAME")
    assert kt.tables_for(None, event("26NOV15ALSTSJSU", SJSU), [1]) == {}       # declared, but not among them


# ---- the history paths refuse a declared series (they fit names with the scorer outside place()) ----------------------

def test_the_history_paths_refuse_a_declared_series_and_pass_every_other(tables_dir):
    from src.ingestion import kalshi_history as kh
    kh.refuse_held_series("KXNCAAMBGAME")                                    # no table: passes, as before
    write_table(tables_dir)
    for f in (kh.refuse_held_series, kh.refuse_declared_series):
        with pytest.raises(ValueError, match=r"REFUSED: KXNCAAMBGAME declares a name table \(KXNCAAMBGAME\.json"):
            f("KXNCAAMBGAME")
    kh.refuse_held_series("KXNCAAFGAME")
    with pytest.raises(ValueError, match="declares a name table"):
        kh.list_chains("KXNCAAMBGAME")


# ---- the syncs: the shared path reads the table through Team.external_ids ---------------------------------------------

def _clear():
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, OddsSnapshot, Sport, Team
    with session_scope() as s:
        comp_ids = [c.id for c in s.query(Competition).filter(Competition.code == "NCAAMB")]
        ids = [m.id for m in s.query(Match).filter(Match.competition_id.in_(comp_ids))]
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
        s.query(Team).filter(Team.sport == Sport.BASKETBALL).delete(synchronize_session=False)
        s.query(Competition).filter(Competition.code == "NCAAMB").delete(synchronize_session=False)


@pytest.fixture
def ncaamb_db():
    from src.db.database import init_db
    init_db()
    _clear()
    yield
    _clear()


@pytest.fixture
def kalshi_fake(monkeypatch):
    from src.adapters.kalshi import KalshiAdapter
    box = {"markets": []}
    monkeypatch.setattr(KalshiAdapter, "status", lambda self: {"trading_active": True})
    monkeypatch.setattr(KalshiAdapter, "sports_filters", lambda self: {})
    monkeypatch.setattr(KalshiAdapter, "open_markets_for_series", lambda self, s: box["markets"])
    return box


def _store(s, games, provider_ids):
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    comp = Competition(sport=Sport.BASKETBALL, code="NCAAMB", name="NCAA Men's Basketball (Division I)", area="USA",
                       type="LEAGUE")
    s.add(comp)
    s.flush()
    teams = {}
    for away, home, ko in games:
        for nm in (away, home):
            if nm not in teams:
                teams[nm] = Team(sport=Sport.BASKETBALL, name=nm, external_ids={KEY: provider_ids[nm]})
                s.add(teams[nm])
        s.flush()
        s.add(Match(sport=Sport.BASKETBALL, competition_id=comp.id, season="2026", utc_date=ko,
                    status=MatchStatus.SCHEDULED, home_team_id=teams[home].id, away_team_id=teams[away].id,
                    status_raw="NS"))
    s.flush()
    return comp


def test_sync_kalshi_ncaamb_places_by_its_table_and_refuses_the_half_fit(ncaamb_db, kalshi_fake, tables_dir,
                                                                          monkeypatch):
    """The real sync path (sync-kalshi-ncaamb -> kalshi_sync.sync_kalshi_mlb -> place(tables=tables_for(...))): the
    table's lines are resolved through Team.external_ids on the stored teams, so the host and the laptop read one
    table whatever their row ids. Alabama State's game is stored and takes its markets; the event of "Alabama A&M",
    whose only stored game is the Crimson Tide's, is refused for no fit where the scorer would have placed it."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match, OddsSnapshot
    from src.ingestion import kalshi_sync
    monkeypatch.setattr(kalshi_sync, "utc_now_naive", lambda: NOW)
    pids = {"Alabama State": "9003", "San Jose State": "9004", "Alabama": "9001", "Texas State": "9005"}
    with session_scope() as s:
        comp = _store(s, [("Alabama State", "San Jose State", Z("2026-11-16T05:00")),
                          ("Alabama", "Texas State", Z("2026-11-16T03:00"))], pids)
        own = s.query(Match).filter(Match.competition_id == comp.id, Match.utc_date == Z("2026-11-16T05:00")).one().id
    write_table(tables_dir, lines=[{"name": "Alabama St.", "key": KEY, "id": "9003"},
                                   {"name": "San Jose St.", "key": KEY, "id": "9004"},
                                   {"name": "Alabama A&M", "key": KEY, "id": "9002"},
                                   {"name": "Texas St.", "key": KEY, "id": "9005"}])
    kalshi_fake["markets"] = (event("26NOV15ALSTSJSU", SJSU)
                              + event("26NOV15AAMUTXST", [("TXST", "Texas St."), ("AAMU", "Alabama A&M")]))
    out = CliRunner().invoke(cli.cli, ["sync-kalshi-ncaamb"])
    assert out.exit_code == 0, out.output
    assert "✓ Kalshi NCAAMB: 2 prices stored" in out.output, out.output
    assert "matched 2 · unmatched 2" in out.output, out.output
    said = []
    r = kalshi_sync.sync_kalshi_mlb(series_override="KXNCAAMBGAME", progress=said.append)
    assert r["refused"] == {km.TABLE_LINE_UNRESOLVED: 2}, r
    assert ("  ✗ KXNCAAMBGAME-26NOV15AAMUTXST: KXNCAAMBGAME's line for 'Alabama A&M': api_basketball 9002 is not "
            "among the stored teams of the series' competition: refused") in said, said
    with session_scope() as s:
        snaps = {(x.match_id, x.selection) for x in s.query(OddsSnapshot).filter(OddsSnapshot.source == "kalshi")}
    assert snaps == {(own, "HOME"), (own, "AWAY")}


# ---- the proposer (387 item 3(d)-(e)) --------------------------------------------------------------------------------

PROPOSER_TEAMS = [(1, "Alabama", "9001"), (2, "Alabama A&M Bulldogs", "9002"), (3, "Alabama State", "9003"),
                  (4, "San Jose State", "9004"), (9, "Texas", "9009"), (10, "Texas A&M", "9010"),
                  (11, "St. Bonaventure", "9011"), (12, "Miami (OH)", "9012"), (13, "Pennsylvania", "9013"),
                  (14, "Stephen F. Austin", "9014"), (15, "Hawai'i", "9015"), (16, "Green Bay Phoenix", "9016"),
                  (17, "UTSA", None)]


def _pteams():
    return [NS(id=i, name=n, external_ids=({KEY: p} if p else {})) for i, n, p in PROPOSER_TEAMS]


def test_the_proposer_marks_what_387_d_names_and_never_proposes_a_marked_name():
    names = {"Alabama St.": 1, "San Jose St.": 1, "Alabama A&M": 1, "Alabama": 1, "Texas": 2, "St. Bonaventure": 1,
             "Miami (OH)": 1, "Penn": 1, "Stephen F. Austin": 1, "Hawai'i": 1, "Green Bay": 1, "UTSA": 1}
    by = {p.name: p for p in kt.propose(names, _pteams(), KEY)}
    proposed = {n for n, p in by.items() if p.proposed}
    assert proposed == {"Alabama St.", "San Jose St.", "Alabama", "Hawai'i"}
    assert [w[:3] for w in by["Alabama St."].whole] == [(3, "Alabama State", "9003")]
    assert [w[:3] for w in by["Alabama"].whole] == [(1, "Alabama", "9001")]
    # "Alabama A&M" reads whole on the Crimson Tide alone (the A&M drops): marked, never proposed (the correction)
    assert [w[1] for w in by["Alabama A&M"].whole] == ["Alabama"]
    assert by["Alabama A&M"].marks == [f"{kt.MARK_DROPPED} (&, a lone letter)"]
    # "Texas": a whole read on Texas alone, but Texas A&M reads whole on "Texas" too: two teams, and a stored mark
    assert by["Texas"].marks == [f"{kt.MARK_DROPPED} (&, a lone letter)", kt.MARK_MANY]
    assert by["St. Bonaventure"].marks == [kt.MARK_SAINT]
    assert by["Miami (OH)"].marks == [f"{kt.MARK_DROPPED} (( ))"]
    assert by["Penn"].marks == [kt.MARK_NONE, f"{kt.MARK_PIN}: Pennsylvania"]
    assert by["Stephen F. Austin"].marks == [f"{kt.MARK_DROPPED} (a dot, a lone letter)"]
    assert by["Green Bay"].marks == [kt.MARK_NONE] and by["Green Bay"].top_teams == ["Green Bay Phoenix"]
    assert by["UTSA"].marks == [f"{kt.MARK_NO_ID}: no api_basketball id"]
    assert kt.dropped_marks("Alabama St.") == [] and kt.dropped_marks("Hawai'i") == []
    assert kt.dropped_marks("Nebraska O.") == ["a lone letter", "a dot"]


def _kept(tmp_path, markets, series="KXNCAAMBGAME"):
    p = tmp_path / "kept" / "kalshi_replay_20261115T130000Z.json"
    p.parent.mkdir()
    p.write_text(json.dumps({"kind": "kalshi_replay_markets", "fetched_at": "2026-11-15T13:00:00",
                             "series": {series: {"series": series, "competition": "NCAAMB", "path": "shared",
                                                 "markets": markets, "fetched_at": "2026-11-15T13:00:01"}}}))
    return p


def _copy(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from src.db.schema import Base, Competition, Match, MatchStatus, Sport, Team
    path = tmp_path / "copy" / "sports.db"
    path.parent.mkdir()
    eng = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        comp = Competition(sport=Sport.BASKETBALL, code="NCAAMB", name="NCAA Men's Basketball (Division I)",
                           area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        ts = {}
        for i, n, p in PROPOSER_TEAMS:
            ts[i] = Team(id=i, sport=Sport.BASKETBALL, name=n, external_ids=({KEY: p} if p else {}))
            s.add(ts[i])
        s.flush()
        for k, (a, h) in enumerate([(3, 4), (2, 1), (9, 10), (11, 12), (13, 14), (15, 16), (17, 4)]):
            s.add(Match(sport=Sport.BASKETBALL, competition_id=comp.id, season="2026",
                        utc_date=Z("2026-11-16T00:00") + timedelta(hours=k), status=MatchStatus.SCHEDULED,
                        home_team_id=ts[h].id, away_team_id=ts[a].id, status_raw="NS"))
        s.commit()
    eng.dispose()
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.close()
    return path


def test_the_proposer_command_prints_the_hand_lines_first_then_the_proposed_and_writes_nothing(tmp_path, tables_dir):
    import cli
    markets = (event("26NOV15ALSTSJSU", SJSU) + event("26NOV15AAMUALA", [("AAMU", "Alabama A&M"), ("ALA", "Alabama")])
               + event("26NOV15GBHAW", [("GB", "Green Bay"), ("HAW", "Hawai'i")]))
    kept, copy = _kept(tmp_path, markets), _copy(tmp_path)
    before = hashlib.sha256(copy.read_bytes()).hexdigest()
    r = CliRunner().invoke(cli.cli, ["kalshi-table-propose", "--series", "KXNCAAMBGAME", "--from-file", str(kept),
                                     "--key", KEY, "--db", str(copy)])
    assert r.exit_code == 0, r.output
    out = r.output
    assert out.startswith("KALSHI-TABLE-PROPOSE · KXNCAAMBGAME (competition NCAAMB) · markets kept at "
                          "2026-11-15T13:00:01")
    assert "mode=ro + immutable=1" in out and "read-only: nothing placed, nothing written, no table made" in out
    assert "6 names in 6 markets · 13 stored teams of NCAAMB · proposed 4 · marked for hand reading 2" in out
    assert "the series' table: none (the series is matched by the scorer)" in out
    hand_at, prop_at = out.index("--- MARKED FOR HAND READING (2)"), out.index("--- PROPOSED (4)")
    assert hand_at < prop_at
    assert "  Alabama A&M | 1 | a mark the tokens drop (&, a lone letter) | Alabama (team 1, api_basketball 9001)" \
        in out[hand_at:prop_at], out
    assert "  Green Bay | 1 | no whole read | - | 2: Green Bay Phoenix" in out[hand_at:prop_at]
    assert "  Alabama St. | 1 | Alabama State | 3 | 9003" in out[prop_at:]
    assert "  Hawai'i | 1 | Hawai'i | 15 | 9015" in out[prop_at:]
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in copy.parent.iterdir()) == ["sports.db"] and kt.declared() == {}


@pytest.mark.parametrize("case", ["sidecar", "no-series", "not-synced", "no-file"])
def test_the_proposer_refuses_and_reads_nothing(tmp_path, case):
    import cli
    kept, copy = _kept(tmp_path, event("26NOV15ALSTSJSU", SJSU)), _copy(tmp_path)
    args = ["--series", "KXNCAAMBGAME", "--from-file", str(kept), "--key", KEY, "--db", str(copy)]
    want = {"sidecar": "has a -wal sidecar", "no-series": "holds no markets of KXNCAAFGAME",
            "not-synced": "KXZZZGAME is not a series the syncs read", "no-file": "cannot be read as a kept markets file"}
    if case == "sidecar":
        copy.with_name("sports.db-wal").write_bytes(b"")
    elif case == "no-series":
        args[1] = "KXNCAAFGAME"
    elif case == "not-synced":
        args[1] = "KXZZZGAME"
    else:
        args[3] = str(tmp_path / "nowhere.json")
    r = CliRunner().invoke(cli.cli, ["kalshi-table-propose", *args])
    assert r.exit_code == 2 and "KALSHI-TABLE-PROPOSE REFUSED" in r.output and want[case] in r.output, r.output


def test_a_table_is_read_against_its_own_competitions_teams_only(ncaamb_db, tables_dir):
    """387 item 3(b): "a line whose id is not among the stored teams of the series' competition refuses". On a run that
    reads two competitions (comp_ids of both), a line whose id only a team of the OTHER competition holds is unresolved,
    never read against that team."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with session_scope() as s:
        comp = _store(s, [("Alabama State", "San Jose State", Z("2026-11-16T05:00"))],
                      {"Alabama State": "9003", "San Jose State": "9004"})
        other = Competition(sport=Sport.BASKETBALL, code="NBA", name="NBA", area="USA", type="LEAGUE")
        s.add(other)
        s.flush()
        a, b = (Team(sport=Sport.BASKETBALL, name=n, external_ids={KEY: p}) for n, p in (("Elsewhere", "9002"),
                                                                                        ("Nowhere", "9099")))
        s.add_all([a, b])
        s.flush()
        s.add(Match(sport=Sport.BASKETBALL, competition_id=other.id, season="2026", utc_date=Z("2026-11-16T05:00"),
                    status=MatchStatus.SCHEDULED, home_team_id=a.id, away_team_id=b.id, status_raw="NS"))
        s.flush()
        write_table(tables_dir)
        got = kt.tables_for(s, event("26NOV15ALSTSJSU", SJSU), [comp.id, other.id])["KXNCAAMBGAME"]
        assert set(got.team_of) == {"Alabama St.", "San Jose St."}
        assert got.unresolved["Alabama A&M"] == ("api_basketball 9002 is not among the stored teams of the series' "
                                                 "competition")
        assert kt.series_comp_ids(s, "KXNCAAMBGAME", [other.id]) == []
        assert kt.series_comp_ids(s, "KXNOTMAPPED", [other.id]) == [other.id]
        assert kt.series_comp_ids(s, "KXNOTMAPPED", [comp.id, other.id]) == []
        s.query(Match).filter(Match.competition_id == other.id).delete(synchronize_session=False)
        s.query(Competition).filter(Competition.id == other.id).delete(synchronize_session=False)
