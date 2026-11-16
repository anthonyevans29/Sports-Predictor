"""THE TABLE OF KXNCAAFGAME, as data (ARCHITECT 2026-11-16, addendum 412 items 2 and 3).

412 item 2, verbatim in part: "RULED: THE TABLE OF KXNCAAFGAME IS THESE 264 LINES, in the file sent with this addendum
(ruled_1116_KXNCAAFGAME_table_lines.txt, 267 lines with its three header lines, sha256
f46a631747a4134d8754c777166163e6badcced415f32431b9d3b925a36a2c75). The data of each line are its name, its key and its
id; the rest of the line is my reading and stays out of the table."
412 item 3(a): "src/ingestion/kalshi_tables/KXNCAAFGAME.json, in KXNCAAMBGAME.json's own form: the series, "ruled":
"ARCHITECT 2026-11-16, addendum 412 item 2", and the 264 lines in name order, each name, key api_american_football and
id as a string, copied from the file and from nowhere else. A test pinned to the count and to the file's sha256".

What this file pins:
- KXNCAAFGAME's table loads under the strict loader: its series, its ruled field, 264 lines in name order, every key
  api_american_football, 264 distinct ids, and the sha256 of the file's bytes;
- the lines 412 item 2(c) names, as ruled (Buffalo, the two Miamis, St. Thomas, Grambling St., Southern University,
  Nicholls St., Louisiana-Monroe, Tennessee-Martin, San Jose St., LIU, Penn, University at Albany, Texas, Texas A&M);
- 412 item 3(d), on synthetic rows carrying the table's own provider ids: the event KXNCAAFGAME-26NOV28GTUGA, with no
  Georgia v Georgia Tech game stored and Louisiana Tech at Georgia Southern on the day, is placed by the scorer on that
  game and refused under the table for no fit.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from src.ingestion import kalshi_match as km
from src.ingestion import kalshi_table as kt

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "src" / "ingestion" / "kalshi_tables" / "KXNCAAFGAME.json"
SHA256 = "0698c81d7c05e1c4fdcf30d7a09f95f9e34ba5812e077139a3e93dd7fc0b903e"
RULED = "ARCHITECT 2026-11-16, addendum 412 item 2"
KEY = "api_american_football"
Z = datetime.fromisoformat


def test_kxncaafgame_holds_the_ruled_lines_by_count_and_by_the_files_sha256():
    assert hashlib.sha256(TABLE.read_bytes()).hexdigest() == SHA256
    t = kt.load(TABLE)
    assert t.sha256 == SHA256 and t.series == "KXNCAAFGAME" and t.ruled == RULED
    assert len(t.lines) == 264 and kt.declared()["KXNCAAFGAME"] == TABLE
    names = list(t.lines)
    assert names == sorted(names) and names[0] == "Abilene Christian" and names[-1] == "Yale"
    assert {ln.key for ln in t.lines.values()} == {KEY}
    assert len({ln.id for ln in t.lines.values()}) == 264
    assert all(isinstance(ln.id, str) and ln.id.isdigit() for ln in t.lines.values())


def test_the_lines_412_names_are_as_ruled():
    t = kt.load(TABLE)
    ruled = {"Buffalo": "141", "Miami (FL)": "123", "Miami (OH)": "130", "St. Thomas": "895", "Grambling St.": "185",
             "Southern University": "232", "Nicholls St.": "164", "Louisiana-Monroe": "196", "Tennessee-Martin": "247",
             "San Jose St.": "90", "LIU": "76", "Penn": "324", "University at Albany": "730", "Texas": "195",
             "Texas A&M": "111", "Georgia": "109", "Georgia Tech": "208", "Georgia Southern": "166",
             "Louisiana Tech": "84"}
    assert {n: t.lines[n].id for n in ruled} == ruled


def _team(i, name, pid):
    return NS(id=i, name=name, external_ids={KEY: pid})


GT, UGA, LATECH, GASO = (_team(1531, "Georgia Tech", "208"), _team(1434, "Georgia", "109"),
                         _team(1409, "Louisiana Tech", "84"), _team(1489, "Georgia Southern", "166"))


def _event(stamp, legs):
    e = f"KXNCAAFGAME-{stamp}"
    return [{"event_ticker": e, "ticker": f"{e}-{sfx}", "title": f"{name} wins", "yes_sub_title": name,
             "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.42"} for sfx, name in legs]


def test_412_3_d_the_scorer_places_gtuga_on_the_half_fit_and_the_table_refuses_it():
    """412 item 3(d): no Georgia v Georgia Tech game is stored. By side_score "Georgia Tech" half-fits Louisiana Tech
    and "Georgia" half-fits Georgia Southern, so the scorer places the event on Louisiana Tech at Georgia Southern
    (match 33592's shape, 2026-11-28). Under the table the two names are teams 1531 and 1434, and no stored game is
    between them: refused for no fit."""
    now = Z("2026-11-27T12:00")
    ev = _event("26NOV28GTUGA", [("GT", "Georgia Tech"), ("UGA", "Georgia")])
    half = NS(id=33592, utc_date=Z("2026-11-28T17:00"), home_team=GASO, away_team=LATECH,
              home_team_id=GASO.id, away_team_id=LATECH.id, status="scheduled")
    assert km.side_score("Georgia Tech", "Louisiana Tech") == 1.0 and km.side_score("Georgia", "Georgia Southern") == 1.0
    window = dict(now=now, lo=now - timedelta(days=1), hi=now + timedelta(days=2))
    scorer = km.place(ev, [half], **window, tables={})
    if "KXNCAAFGAME" in kt.declared():
        assert scorer.placed == {} and scorer.refused == {km.TABLE_UNREAD: 2}   # a run that skips the table: nothing
    tables = {"KXNCAAFGAME": kt.resolve(kt.load(TABLE), [GT, UGA, LATECH, GASO])}
    res = km.place(ev, [half], **window, tables=tables)
    assert res.placed == {} and res.refused == {km.NO_FIT: 2}, res.refused


@pytest.fixture
def no_tables(tmp_path, monkeypatch):
    d = tmp_path / "none"
    d.mkdir()
    monkeypatch.setattr(kt, "TABLE_DIR", d)


def test_412_3_d_with_no_table_the_scorer_places_gtuga_on_louisiana_tech_at_georgia_southern(no_tables):
    """The same event on main WITHOUT the table: the scorer's fit, the wrong game (#955's namesake case)."""
    now = Z("2026-11-27T12:00")
    ev = _event("26NOV28GTUGA", [("GT", "Georgia Tech"), ("UGA", "Georgia")])
    half = NS(id=33592, utc_date=Z("2026-11-28T17:00"), home_team=GASO, away_team=LATECH,
              home_team_id=GASO.id, away_team_id=LATECH.id, status="scheduled")
    res = km.place(ev, [half], now=now, lo=now - timedelta(days=1), hi=now + timedelta(days=2))
    assert {k: mk["ticker"].rsplit("-", 1)[1] for k, mk in res.placed.items()} == {(33592, "HOME"): "UGA",
                                                                                  (33592, "AWAY"): "GT"}
