"""THE FIRST TABLE OF KXNCAAMBGAME, as data (ARCHITECT 2026-11-15, addendum 392 items 2 and 4).

392 item 2(d), verbatim: "RULED: the first table of KXNCAAMBGAME is the 253 lines of the attached file, name | key | id,
exactly as printed, less any of the three I strike. Its "ruled" field: "ARCHITECT 2026-11-15, addendum 392 item 2". No
line of your own, no name normalised, no order imposed beyond the file's."
392 item 4(b): "A test that every shipped table loads under the strict loader, and that this one holds the ruled lines,
by count and by the sha256 of the file."

What this file pins:
- every table the repo ships (kalshi_table.declared() on the real folder) loads under the strict loader;
- KXNCAAMBGAME's: its series and ruled field, 253 lines, every key api_basketball, 253 distinct names and ids, and the
  sha256 of the file's bytes (any change to any line, its order or the file's form changes it);
- the series under it, on the real folder: 353 item 2's sample (Alabama St. at San Jose St.) placed by the table on its
  own game; the lone half-fit of 356 item 4(a) refused for no fit; "UTSA" (one of the 60 marked names, not in the first
  table) refused under the reason naming it; and the real sync-kalshi-ncaamb path the same way, its teams found by their
  api_basketball ids. Team names and kickoffs are synthetic; the provider ids are the table's own.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner

from src.ingestion import kalshi_match as km
from src.ingestion import kalshi_table as kt

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "src" / "ingestion" / "kalshi_tables" / "KXNCAAMBGAME.json"
SHA256 = "960267320bdef6992cdb5ad310db985a38b09fea15e2ef7b21f6d875e061edd1"
RULED = "ARCHITECT 2026-11-15, addendum 392 item 2"
KEY = "api_basketball"
Z = datetime.fromisoformat
NOW = Z("2026-11-15T15:00")


def test_every_shipped_table_loads_under_the_strict_loader():
    decl = kt.declared()
    assert "KXNCAAMBGAME" in decl and decl["KXNCAAMBGAME"] == TABLE
    for series, path in decl.items():
        t = kt.load(path)
        assert t.series == series and t.lines


def test_kxncaambgame_holds_the_ruled_lines_by_count_and_by_the_files_sha256():
    assert hashlib.sha256(TABLE.read_bytes()).hexdigest() == SHA256
    t = kt.load(TABLE)
    assert t.sha256 == SHA256 and t.series == "KXNCAAMBGAME" and t.ruled == RULED
    assert len(t.lines) == 253
    assert {ln.key for ln in t.lines.values()} == {KEY}
    assert len({ln.id for ln in t.lines.values()}) == 253
    names = list(t.lines)
    assert names[0] == "Abilene Christian" and names[-1] == "Youngstown St."       # the file's order, kept
    # the three lines 392 item 2(c) reads again before PR two merges: here, as printed
    assert {n: t.lines[n].id for n in ("Charlotte", "Florida International", "Loyola Marymount")} == {
        "Charlotte": "3429", "Florida International": "5628", "Loyola Marymount": "3382"}
    # 392 item 3: the 60 marked names are not in the first table (three of them, as the 11-13 names read printed them)
    assert not {"UTSA", "Alabama A&M", "Penn"} & set(names)


def _team(i, name, pid):
    return NS(id=i, name=name, external_ids={KEY: pid})


def _game(gid, away, home, kick):
    return NS(id=gid, utc_date=kick, home_team=home, away_team=away, home_team_id=home.id, away_team_id=away.id,
              status="scheduled")


def _event(stamp, legs):
    e = f"KXNCAAMBGAME-{stamp}"
    return [{"event_ticker": e, "ticker": f"{e}-{sfx}", "title": f"{name} wins", "yes_sub_title": name,
             "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.42"} for sfx, name in legs]


SJSU = [("SJSU", "San Jose St."), ("ALST", "Alabama St.")]
ALABAMA, ALST, SJ, TXST, UTSA = (_team(1, "Alabama", "176"), _team(2, "Alabama State", "1807"),
                                 _team(3, "San Jose State", "2110"), _team(4, "Texas State", "247"),
                                 _team(5, "UTSA Roadrunners", "9999"))


def _place(markets, games):
    tables = {"KXNCAAMBGAME": kt.resolve(kt.load(TABLE), [ALABAMA, ALST, SJ, TXST, UTSA])}
    return km.place(markets, games, now=NOW, lo=NOW - timedelta(days=1), hi=NOW + timedelta(hours=48), tables=tables)


def test_353s_sample_is_placed_by_the_table_on_its_own_game_and_the_half_fit_is_refused():
    own = _game(9801, ALST, SJ, Z("2026-11-16T05:00"))
    half = _game(9811, ALABAMA, SJ, Z("2026-11-16T05:00"))
    res = _place(_event("26NOV15ALSTSJSU", SJSU), [half, own])
    assert {k: mk["ticker"].rsplit("-", 1)[1] for k, mk in res.placed.items()} == {(9801, "HOME"): "SJSU",
                                                                                  (9801, "AWAY"): "ALST"}
    res = _place(_event("26NOV15ALSTSJSU", SJSU), [half])
    assert res.placed == {} and res.refused == {km.NO_FIT: 2}


def test_a_marked_name_is_refused_under_the_reason_naming_it():
    res = _place(_event("26NOV15TXSTUTSA", [("UTSA", "UTSA"), ("TXST", "Texas St.")]),
                 [_game(9831, TXST, UTSA, Z("2026-11-16T01:00"))])
    assert res.placed == {} and res.refused == {"not in KXNCAAMBGAME's name table: UTSA": 2}


def test_a_run_that_does_not_read_the_shipped_table_places_nothing_of_the_series():
    res = km.place(_event("26NOV15ALSTSJSU", SJSU), [_game(9801, ALST, SJ, Z("2026-11-16T05:00"))], now=NOW,
                   lo=NOW - timedelta(days=1), hi=NOW + timedelta(hours=48))
    assert res.placed == {} and res.refused == {km.TABLE_UNREAD: 2}


# ---- the real sync path, on conftest's throwaway DB ------------------------------------------------------------------

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


def test_sync_kalshi_ncaamb_stores_by_the_shipped_table_and_refuses_a_marked_name(ncaamb_db, monkeypatch):
    import cli
    from src.adapters.kalshi import KalshiAdapter
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
    from src.ingestion import kalshi_sync
    markets = (_event("26NOV15ALSTSJSU", SJSU) + _event("26NOV15TXSTUTSA", [("UTSA", "UTSA"), ("TXST", "Texas St.")]))
    monkeypatch.setattr(KalshiAdapter, "status", lambda self: {"trading_active": True})
    monkeypatch.setattr(KalshiAdapter, "sports_filters", lambda self: {})
    monkeypatch.setattr(KalshiAdapter, "open_markets_for_series", lambda self, s: markets)
    monkeypatch.setattr(kalshi_sync, "utc_now_naive", lambda: NOW)
    with session_scope() as s:
        comp = Competition(sport=Sport.BASKETBALL, code="NCAAMB", name="NCAA Men's Basketball (Division I)",
                           area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        rows = {t.name: Team(sport=Sport.BASKETBALL, name=t.name, external_ids=dict(t.external_ids))
                for t in (ALST, SJ, TXST, UTSA)}
        s.add_all(rows.values())
        s.flush()
        for away, home, ko in (("Alabama State", "San Jose State", "2026-11-16T05:00"),
                               ("Texas State", "UTSA Roadrunners", "2026-11-16T01:00")):
            s.add(Match(sport=Sport.BASKETBALL, competition_id=comp.id, season="2026", utc_date=Z(ko),
                        status=MatchStatus.SCHEDULED, home_team_id=rows[home].id, away_team_id=rows[away].id,
                        status_raw="NS"))
        s.flush()
        own = s.query(Match).filter(Match.competition_id == comp.id, Match.utc_date == Z("2026-11-16T05:00")).one().id
    out = CliRunner().invoke(cli.cli, ["sync-kalshi-ncaamb"])
    assert out.exit_code == 0 and "✓ Kalshi NCAAMB: 2 prices stored" in out.output, out.output
    r = kalshi_sync.sync_kalshi_mlb(series_override="KXNCAAMBGAME")
    assert r["refused"] == {"not in KXNCAAMBGAME's name table: UTSA": 2}, r
    with session_scope() as s:
        legs = {(x.match_id, x.selection) for x in s.query(OddsSnapshot).filter(OddsSnapshot.source == "kalshi")}
    assert legs == {(own, "HOME"), (own, "AWAY")}
