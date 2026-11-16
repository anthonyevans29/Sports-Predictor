"""ARCHITECT 2026-11-16 11:27 ET, addendum 408 item 5: THE TWO COST LINES (#955), BUILT IN ONE PR.

"(a) Line 1, the proposer's marked section: per name each event's ticker with the other name, and per top-score team
its team id and its provider id under --key ... (b) Line 2, the replay: after the counts by reason, one line per refusal
reason other than the window and play begun, listing that reason's event tickers from res.why ... (c) THE FENCE ...
nothing in place(), the loader, the resolver or any table file changes; kalshi_match.console_lines is unchanged, so no
sync's console changes; no placement and no refusal changes."

Every team id and provider id here is synthetic; the names are the real spellings of 353 item 2 and of 403 item 2(d).
"""
from __future__ import annotations

import hashlib
import inspect
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner

from src.ingestion import kalshi_match as km
from src.ingestion import kalshi_table as kt

ROOT = Path(__file__).resolve().parent.parent
KEY = "api_basketball"
Z = datetime.fromisoformat


def event(stamp, legs, series="KXNCAAMBGAME", bid="0.40", ask="0.42"):
    e = f"{series}-{stamp}"
    return [{"event_ticker": e, "ticker": f"{e}-{sfx}", "title": f"{name} wins", "yes_sub_title": name,
             "yes_bid_dollars": bid, "yes_ask_dollars": ask} for sfx, name in legs]


# ---- line 1: the proposer's marked section ---------------------------------------------------------------------------

def test_names_of_keeps_each_events_ticker_with_the_other_name_in_the_markets_order():
    mks = (event("26NOV15GBHAW", [("GB", "Green Bay"), ("HAW", "Hawai'i")])
           + event("26NOV17GBUWFL", [("GB", "Green Bay"), ("UWF", "West Florida")])
           + event("26NOV15ZZZ", [("Z", "Only One")]))                         # a pair that does not form: no name
    got = kt.names_of(mks)
    assert got == {"Green Bay": [("KXNCAAMBGAME-26NOV15GBHAW", "Hawai'i"), ("KXNCAAMBGAME-26NOV17GBUWFL", "West Florida")],
                   "Hawai'i": [("KXNCAAMBGAME-26NOV15GBHAW", "Green Bay")],
                   "West Florida": [("KXNCAAMBGAME-26NOV17GBUWFL", "Green Bay")]}


def test_propose_keeps_the_events_and_each_top_teams_ids_and_still_takes_a_bare_count():
    teams = [NS(id=16, name="Wisc. Green Bay", external_ids={KEY: "249"}),
             NS(id=17, name="Green Bay Phoenix", external_ids={}),                       # no id: '-' in the console
             NS(id=18, name="Hawaii", external_ids={KEY: "1933"})]
    names = {"Green Bay": [("KXNCAAMBGAME-26NOV17GBUWFL", "West Florida")]}
    (p,) = kt.propose(names, teams, KEY)
    assert p.events == 1 and p.seen == [("KXNCAAMBGAME-26NOV17GBUWFL", "West Florida")]
    assert p.top == 2.0 and p.top_teams == ["Green Bay Phoenix", "Wisc. Green Bay"]
    assert p.top_ids == [(17, "Green Bay Phoenix", None, None), (16, "Wisc. Green Bay", "249", None)]
    (q,) = kt.propose({"Green Bay": 3}, teams, KEY)                                    # the count form, unchanged
    assert q.events == 3 and q.seen == [] and q.marks == p.marks and q.top_teams == p.top_teams


def _kept(tmp_path, markets):
    p = tmp_path / "kept" / "kalshi_replay_20261116T130000Z.json"
    p.parent.mkdir()
    p.write_text(json.dumps({"kind": "kalshi_replay_markets", "fetched_at": "2026-11-16T13:00:00",
                             "series": {"KXNCAAMBGAME": {"series": "KXNCAAMBGAME", "competition": "NCAAMB",
                                                         "path": "shared", "markets": markets,
                                                         "fetched_at": "2026-11-16T13:00:01"}}}))
    return p


def _copy(tmp_path, teams, games):
    import sqlite3

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
        for i, n, pid in teams:
            s.add(Team(id=i, sport=Sport.BASKETBALL, name=n, external_ids=({KEY: pid} if pid else {})))
        s.flush()
        for k, (a, h) in enumerate(games):
            s.add(Match(sport=Sport.BASKETBALL, competition_id=comp.id, season="2026",
                        utc_date=Z("2026-11-16T00:00") + timedelta(hours=k), status=MatchStatus.SCHEDULED,
                        home_team_id=h, away_team_id=a, status_raw="NS"))
        s.commit()
    eng.dispose()
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.close()
    return path


def test_the_marked_section_prints_each_events_ticker_and_each_top_teams_ids(tmp_path):
    import cli
    teams = [(16, "Wisc. Green Bay", "249"), (17, "Green Bay Phoenix", None), (18, "Hawaii", "1933"),
             (19, "West Florida Argonauts", "3339"), (3, "Alabama State", "1807"), (4, "San Jose State", "2110")]
    markets = (event("26NOV15ALSTSJSU", [("SJSU", "San Jose St."), ("ALST", "Alabama St.")])
               + event("26NOV17GBUWFL", [("GB", "Green Bay"), ("UWF", "West Florida")]))
    kept, copy = _kept(tmp_path, markets), _copy(tmp_path, teams, [(16, 19), (3, 4), (17, 18)])
    before = hashlib.sha256(copy.read_bytes()).hexdigest()
    r = CliRunner().invoke(cli.cli, ["kalshi-table-propose", "--series", "KXNCAAMBGAME", "--from-file", str(kept),
                                     "--key", KEY, "--db", str(copy)])
    assert r.exit_code == 0, r.output
    out = r.output
    hand_at, prop_at = out.index("--- MARKED FOR HAND READING (2)"), out.index("--- PROPOSED (2)")
    hand = out[hand_at:prop_at]
    assert "teams (team id, api_basketball id); then each event's ticker v the other name" in hand
    assert ("  Green Bay | 1 | no whole read | - | 2: Green Bay Phoenix (team 17, api_basketball -) ; Wisc. Green Bay "
            "(team 16, api_basketball 249)\n      events: KXNCAAMBGAME-26NOV17GBUWFL v West Florida\n") in hand, hand
    assert "      events: KXNCAAMBGAME-26NOV17GBUWFL v Green Bay\n" in hand                    # West Florida's
    # the PROPOSED section is as it was: name | events | team | our team id | provider id, no event line
    assert out[prop_at:].splitlines()[1:] == ["  Alabama St. | 1 | Alabama State | 3 | 1807",
                                              "  San Jose St. | 1 | San Jose State | 4 | 2110"]
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == before


# ---- line 2: the replay names the events under each reason other than the window and play begun ----------------------

def test_refused_events_lines_names_each_reasons_events_and_leaves_the_window_and_play_unnamed():
    from src.ingestion import kalshi_replay as kr
    res = km.Result()
    res.why = {"KXNCAAMBGAME-26NOV14UNCGCOR-UNCG": km.NO_FIT, "KXNCAAMBGAME-26NOV14UNCGCOR-COR": km.NO_FIT,
               "KXNCAAMBGAME-26NOV14ULLUNCW-ULL": km.NO_FIT, "KXNCAAMBGAME-26NOV14ULLUNCW-UNCW": km.NO_FIT,
               "KXNCAAMBGAME-26NOV18AAAA-A": km.OUTSIDE_WINDOW, "KXNCAAMBGAME-26NOV16BBBB-B": km.IN_PLAY,
               "KXNCAAMBGAME-26NOV16CCCC-C": km.NO_PRICE}
    mks = [{"ticker": t, "event_ticker": t.rsplit("-", 1)[0]} for t in res.why]
    assert kr.refused_events_lines(res, mks) == [
        "  the events refused, by reason (not the window, not play begun; \"in part\": the event placed other legs):",
        f"    {km.NO_FIT} (2): KXNCAAMBGAME-26NOV14ULLUNCW, KXNCAAMBGAME-26NOV14UNCGCOR",
        f"    {km.NO_PRICE} (1): KXNCAAMBGAME-26NOV16CCCC"]
    only = km.Result()
    only.why = {"KXNCAAMBGAME-26NOV18AAAA-A": km.OUTSIDE_WINDOW, "KXNCAAMBGAME-26NOV16BBBB-B": km.IN_PLAY}
    assert kr.refused_events_lines(only, []) == []                         # nothing to name: no line at all


@pytest.fixture
def scratch(tmp_path, monkeypatch):
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


def _seed(eng, home, away, kick):
    from sqlalchemy.orm import Session

    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with Session(eng) as s:
        comp = s.query(Competition).filter_by(code="NCAA").one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        h, a = Team(sport=Sport.NFL, name=home), Team(sport=Sport.NFL, name=away)
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.NFL, competition_id=comp.id, season="2026", utc_date=kick,
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.commit()
        return m.id


def test_the_replay_prints_the_counts_as_before_then_the_events_refused_for_a_reason_of_their_own(scratch):
    """On a series with no table (the scorer's), so the console lines of the matcher are compared one for one:
    km.console_lines(res) prints exactly as before, and the events line comes after it, naming the NO_FIT event and
    not the event outside the window."""
    from src.ingestion import kalshi_replay as kr
    now = Z("2026-10-10T11:52")
    _seed(scratch, "Utah", "Kansas", Z("2026-10-11T02:15"))
    _seed(scratch, "Iowa", "Ohio", Z("2026-10-14T23:00"))                          # 26OCT14: outside the 2-day window
    mks = (event("26OCT10KUUTAH", [("KU", "Kansas"), ("UTAH", "Utah")], series="KXNCAAFGAME")
           + event("26OCT10CHIGB", [("CHI", "Chicago"), ("GB", "Green Bay")], series="KXNCAAFGAME")
           + event("26OCT14OHIOIOWA", [("OHIO", "Ohio"), ("IOWA", "Iowa")], series="KXNCAAFGAME"))
    payload = {"fetched_at": now.isoformat(), "series": {"KXNCAAFGAME": {
        "series": "KXNCAAFGAME", "competition": "NCAA", "path": "shared", "markets": mks}}}
    lines = []
    r = kr.replay(payload, progress=lines.append)["KXNCAAFGAME"]
    assert r["placed"] == 2 and r["refused"] == {km.NO_FIT: 2, km.OUTSIDE_WINDOW: 2}, r
    i = lines.index("  refused, by reason:")
    assert lines[i:i + 3] == ["  refused, by reason:", f"       2  {km.NO_FIT}", f"       2  {km.OUTSIDE_WINDOW}"]
    j = lines.index('  the events refused, by reason (not the window, not play begun; "in part": the event placed other '
                    'legs):')
    assert j > i and lines[j + 1] == f"    {km.NO_FIT} (1): KXNCAAFGAME-26OCT10CHIGB"
    assert not any("26OCT14OHIOIOWA" in ln for ln in lines[j:j + 3])


# ---- the fence (408 item 5(c)) ----------------------------------------------------------------------------------------

def test_the_fence_console_lines_place_and_the_table_are_as_they_were():
    """kalshi_match.console_lines is the counts by reason and the matcher's lines, as before (no sync's console
    changes); the shipped table's bytes are 4abfb1db…4468103 (396 item 3; 408 item 5(d))."""
    res = km.Result()
    res.refused[km.NO_FIT] = 2
    res.lines.append("  ✗ a line")
    assert km.console_lines(res) == ["  refused, by reason:", f"       2  {km.NO_FIT}", "  ✗ a line"]
    assert "refused_events_lines" not in inspect.getsource(km)
    table = ROOT / "src" / "ingestion" / "kalshi_tables" / "KXNCAAMBGAME.json"
    assert hashlib.sha256(table.read_bytes()).hexdigest() == \
        "4abfb1db6f7d3590e2aec2cd90ac857a39526a2605e9c7fa37e3aeefe4468103"


def test_an_event_with_legs_placed_and_a_leg_refused_is_marked_in_part():
    """Pre-PR review (P2): place() refuses NO_PRICE, WIDE_SPREAD, YES_UNKNOWN, BEHIND and TWO_CLAIMS one market at a
    time, so an event can place two legs while a third is refused (a soccer Tie leg wider than the guard). The event is
    listed under its reason, as 408 item 5(b) rules, and marked "in part" so a placed event never reads as refused."""
    from src.ingestion import kalshi_replay as kr
    res = km.Result()
    ev = "KXEPLGAME-26NOV22ARSTOT"
    home, away, tie = (f"{ev}-ARS", f"{ev}-TOT", f"{ev}-TIE")
    res.placed = {(1, "HOME"): {"ticker": home, "event_ticker": ev}, (1, "AWAY"): {"ticker": away, "event_ticker": ev}}
    res.why = {tie: km.WIDE_SPREAD, "KXEPLGAME-26NOV22CHEMUN-TIE": km.WIDE_SPREAD}
    mks = [{"ticker": t, "event_ticker": t.rsplit("-", 1)[0]} for t in (home, away, tie, "KXEPLGAME-26NOV22CHEMUN-TIE")]
    assert kr.refused_events_lines(res, mks) == [
        "  the events refused, by reason (not the window, not play begun; \"in part\": the event placed other legs):",
        f"    {km.WIDE_SPREAD} (2): KXEPLGAME-26NOV22ARSTOT (in part), KXEPLGAME-26NOV22CHEMUN"]


def test_a_shared_or_several_provider_ids_are_printed_with_their_note_never_hidden():
    """Codex P2 on #1033: a top-score team whose provider id another stored team also holds keeps that id in the
    hand-reading aid, annotated, so the reader sees the ambiguity; a team with several ids lists them."""
    teams = [NS(id=16, name="Wisc. Green Bay", external_ids={KEY: "249"}),
             NS(id=20, name="Green Bay Old Row", external_ids={KEY: "900", f"{KEY}_also": ["249"]}),
             NS(id=21, name="Green Bay Two Ids", external_ids={f"{KEY}_also": ["301", "302"]}),
             NS(id=17, name="Green Bay Phoenix", external_ids={})]
    (p,) = kt.propose({"Green Bay": [("KXNCAAMBGAME-26NOV17GBUWFL", "West Florida")]}, teams, KEY)
    assert p.top_ids == [(20, "Green Bay Old Row", "900", None),
                         (17, "Green Bay Phoenix", None, None),
                         (21, "Green Bay Two Ids", None, "ids 301, 302"),
                         (16, "Wisc. Green Bay", "249", "also held by team 20")]
    assert kt.top_id_text(p.top_ids[3], KEY) == "Wisc. Green Bay (team 16, api_basketball 249, also held by team 20)"
    assert kt.top_id_text(p.top_ids[2], KEY) == "Green Bay Two Ids (team 21, api_basketball -, ids 301, 302)"
    assert kt.top_id_text(p.top_ids[1], KEY) == "Green Bay Phoenix (team 17, api_basketball -)"
