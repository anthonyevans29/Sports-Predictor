"""THE FIFTH LANE: STORE IT AND SHOW IT (ARCHITECT 2026-10-09, addendum 32 item 4).

RULED (item 3): "response[].update is the provider's own time for a game's odds: one per game, neither our
fetch time nor the fixture's. It is read as the newest that any quote in the answer can be; a quote may be
older. It is stored and shown as source_updated_at and described in those words, never as the time of a
quote. A row without it has an unknown source time, and unknown is never read as fresh."

Covers: the american-football adapter (present, absent, unreadable), sync-odds-football (odds rows and the
book consensus snapshots), every export block that shows a capture time for those prices (fixtures market
block 1X2 + spread-derived, the line-move book venue of the NFL export / window card, the NFL results
file's value anchor), and migrate_odds_source_updated_at.py run twice."""
import json
from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine, select, text

from src.adapters.normalized import NormalizedOdds
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, OddsSnapshot, Prediction, Sport, Team
from src.ingestion import service as svc
from src.timeutil import oldest_source_time, utc_now_naive

UPD = datetime(2026, 10, 8, 2, 15, 10)          # the receipt's "2026-10-08T02:15:10+00:00", naive UTC


# ------------------------------------------------------------ the adapter ----

def _payload(update=..., n_blocks=1):
    block = {"game": {"id": 23616}, "bookmakers": [
        {"id": 1, "name": "BookA", "bets": [{"name": "Home/Away", "values": [
            {"value": "Home", "odd": "1.80"}, {"value": "Away", "odd": "2.05"}]}]}]}
    if update is not ...:
        block["update"] = update
    return {"response": [dict(block) for _ in range(n_blocks)]}


def _adapter(monkeypatch, payload):
    from src.adapters.api_american_football import APIAmericanFootballAdapter
    ad = APIAmericanFootballAdapter.__new__(APIAmericanFootballAdapter)
    monkeypatch.setattr(ad, "_get", lambda path, params=None: payload, raising=False)
    return ad


def test_adapter_present_parses_update_to_naive_utc(monkeypatch):
    rows = _adapter(monkeypatch, _payload("2026-10-08T02:15:10+00:00")).list_odds("23616")
    assert len(rows) == 2 and {r.source_updated_at for r in rows} == {UPD}
    assert all(r.source_updated_at.tzinfo is None for r in rows)
    assert all(r.captured_at != UPD for r in rows)                  # our fetch stamp stays separate
    # an offset is converted to UTC, a trailing Z reads as UTC
    rows = _adapter(monkeypatch, _payload("2026-10-07T22:15:10-04:00")).list_odds("23616")
    assert {r.source_updated_at for r in rows} == {UPD}
    rows = _adapter(monkeypatch, _payload("2026-10-08T02:15:10Z")).list_odds("23616")
    assert {r.source_updated_at for r in rows} == {UPD}


def test_adapter_absent_is_none_never_our_clock(monkeypatch):
    rows = _adapter(monkeypatch, _payload()).list_odds("23616")
    assert len(rows) == 2 and all(r.source_updated_at is None for r in rows)
    rows = _adapter(monkeypatch, _payload(None)).list_odds("23616")
    assert all(r.source_updated_at is None for r in rows)


@pytest.mark.parametrize("raw", ["", "  ", "yesterday", "2026-13-45T99:00:00+00:00", 1791590400,
                                 {"date": "2026-10-08"}, "2026-10-08T02:15:10"])     # no offset: zone unknown
def test_adapter_unreadable_is_none(monkeypatch, raw):
    rows = _adapter(monkeypatch, _payload(raw)).list_odds("23616")
    assert len(rows) == 2 and all(r.source_updated_at is None for r in rows)


def test_normalized_odds_field_is_optional():
    o = NormalizedOdds(match_source_id="1", source="x", bookmaker="b", market="1X2", selection="HOME",
                       price_decimal=2.0, captured_at=UPD)
    assert o.source_updated_at is None


def test_hockey_adapter_untouched():
    import inspect
    from src.adapters import api_hockey
    assert "source_updated_at" not in inspect.getsource(api_hockey)


def test_oldest_source_time_unknown_is_never_fresh():
    a, b = NS(source_updated_at=UPD), NS(source_updated_at=UPD + timedelta(hours=1))
    assert oldest_source_time([b, a]) == UPD                         # rows differ: the oldest
    assert oldest_source_time([a, NS(source_updated_at=None)]) is None   # one unknown: unknown
    assert oldest_source_time([]) is None


# --------------------------------------------------------------- the sync ----

@pytest.fixture
def games():
    init_db()
    with session_scope() as s:
        c = s.execute(select(Competition).where(Competition.code == "SUA")).scalar_one_or_none()
        if c is None:
            c = Competition(sport=Sport.NFL, code="SUA", name="SUA", area="US", type="LEAGUE")
            s.add(c)
        ts = [Team(sport=Sport.NFL, name=f"SUA {i}") for i in range(4)]
        s.add_all(ts)
        s.flush()
        ids = []
        for i in range(2):
            m = Match(sport=Sport.NFL, competition_id=c.id, season="2026", status=MatchStatus.SCHEDULED,
                      utc_date=utc_now_naive() + timedelta(days=2, minutes=i), home_team_id=ts[2 * i].id,
                      away_team_id=ts[2 * i + 1].id, external_ids={"api_american_football": f"sua{i}"})
            s.add(m)
            s.flush()
            ids.append(m.id)
    yield ids
    with session_scope() as s:
        s.query(Odds).filter(Odds.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)


def test_sync_stores_it_on_every_row_and_snapshot(games, monkeypatch):
    older = UPD - timedelta(minutes=30)
    per_game = {
        "sua0": [("bk1", "HOME", 1.8, UPD), ("bk1", "AWAY", 2.1, UPD),
                 ("bk2", "HOME", 1.85, older), ("bk2", "AWAY", 2.0, older)],     # rows differ: the oldest
        "sua1": [("bk1", "HOME", 1.8, None), ("bk1", "AWAY", 2.1, None)],         # absent: unknown
    }

    def list_odds(self, gid):
        return [NormalizedOdds(source="api_american_football", match_source_id=gid, market="1X2", selection=sel,
                               bookmaker=bk, price_decimal=px, captured_at=utc_now_naive(), source_updated_at=u)
                for bk, sel, px, u in per_game[gid]]
    monkeypatch.setattr("src.adapters.api_american_football.APIAmericanFootballAdapter.list_odds", list_odds)
    monkeypatch.setattr(svc, "_odds_sleep", lambda x: None)
    r = svc.sync_odds_nfl(match_ids=set(games))
    assert r["games"] == 2 and r["snapshots"] == 4
    g0, g1 = games
    with session_scope() as s:
        o0 = {(o.bookmaker, o.selection): o.source_updated_at
              for o in s.execute(select(Odds).where(Odds.match_id == g0)).scalars()}
        assert o0 == {("bk1", "HOME"): UPD, ("bk1", "AWAY"): UPD, ("bk2", "HOME"): older, ("bk2", "AWAY"): older}
        assert all(o.source_updated_at is None
                   for o in s.execute(select(Odds).where(Odds.match_id == g1)).scalars())
        s0 = list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == g0)).scalars())
        assert len(s0) == 2 and {x.source_updated_at for x in s0} == {older}
        assert all(x.captured_at != older for x in s0)               # the capture stamp is our fetch time
        s1 = list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == g1)).scalars())
        assert len(s1) == 2 and all(x.source_updated_at is None for x in s1)


# ------------------------------------------------------------ the exports ----

def _fixture_game(s, tag, rows, ko):
    c = s.execute(select(Competition).where(Competition.code == "SUAX")).scalar_one_or_none()
    if c is None:
        c = Competition(sport=Sport.NFL, code="SUAX", name="SUAX", area="US", type="LEAGUE")
        s.add(c)
    h, a = Team(sport=Sport.NFL, name=f"SUAX {tag} H"), Team(sport=Sport.NFL, name=f"SUAX {tag} A")
    s.add_all([h, a])
    s.flush()
    m = Match(sport=Sport.NFL, competition_id=c.id, season="2026", status=MatchStatus.SCHEDULED,
              utc_date=ko, home_team_id=h.id, away_team_id=a.id, external_ids={"suax": tag})
    s.add(m)
    s.flush()
    for bk, mkt, sel, px, line, at, u in rows:
        s.add(Odds(match_id=m.id, bookmaker=bk, market=mkt, selection=sel, price_decimal=px, line=line,
                   source="api_american_football", captured_at=at, source_updated_at=u))
    s.flush()
    return m


def test_fixtures_market_block_shows_it_beside_captured_at():
    from src.walters.export import _fixture_row
    init_db()
    ko = utc_now_naive() + timedelta(days=1)
    at = ko - timedelta(hours=5)
    older = UPD - timedelta(hours=2)
    with session_scope() as s:
        m = _fixture_game(s, "a", [("bk1", "1X2", "HOME", 1.8, None, at, UPD),
                                   ("bk1", "1X2", "AWAY", 2.1, None, at, UPD),
                                   ("bk2", "1X2", "HOME", 1.9, None, at, older),
                                   ("bk2", "1X2", "AWAY", 2.0, None, at, older),
                                   # an earlier session never counts toward the last session's source time
                                   ("bk3", "1X2", "HOME", 1.9, None, at - timedelta(hours=6), older - timedelta(days=1)),
                                   ], ko)
        row = _fixture_row(s, m, "SUAX", Counter(), Counter())
        mk = row["market"]
        assert mk["captured_at"] == at.isoformat()
        assert mk["source_updated_at"] == older.isoformat()          # same form; the session's oldest
        assert list(mk).index("source_updated_at") == list(mk).index("captured_at") + 1   # beside it
        # unknown on one row of the session: unknown, never fresh
        m2 = _fixture_game(s, "b", [("bk1", "1X2", "HOME", 1.8, None, at, UPD),
                                    ("bk1", "1X2", "AWAY", 2.1, None, at, None)], ko)
        assert _fixture_row(s, m2, "SUAX", Counter(), Counter())["market"]["source_updated_at"] is None
        # Kalshi block: not sync-odds-football's prices, so no field there
        assert row["kalshi"] is None or "source_updated_at" not in row["kalshi"]
        s.rollback()


def test_fixtures_spread_derived_block_shows_it(monkeypatch):
    from src.walters import spread_fallback as fb
    from src.walters.export import _fixture_row
    init_db()
    monkeypatch.setattr(fb, "FALLBACK_LIVE", True)
    monkeypatch.setattr(fb, "sigma_for", lambda code: 13.5)
    ko = utc_now_naive() + timedelta(days=1)
    at = ko - timedelta(hours=5)
    older = UPD - timedelta(hours=3)
    with session_scope() as s:
        m = _fixture_game(s, "sp", [("bk1", "SPREADS", "HOME", 1.9, -3.5, at, UPD),
                                    ("bk1", "SPREADS", "AWAY", 1.9, 3.5, at, older)], ko)
        mk = _fixture_row(s, m, "SUAX", Counter(), Counter())["market"]
        assert mk["fair_source"] == fb.FAIR_SOURCE_SPREAD
        assert mk["captured_at"] == at.isoformat() and mk["source_updated_at"] == older.isoformat()
        s.rollback()


KO = datetime(2026, 10, 4, 17, 0)


def _snap(sel, p, at, u, source="api_american_football"):
    return NS(selection=sel, devig_prob=p, captured_at=at, source=source, market="1X2", source_updated_at=u)


def test_line_move_book_venue_shows_it_beside_from_at_and_to_at():
    from src.walters.line_move import line_move
    t0, t1 = KO - timedelta(hours=4), KO - timedelta(minutes=50)
    u0, u1 = UPD, UPD + timedelta(hours=40)
    snaps = [_snap("HOME", 0.49, t0, u0), _snap("AWAY", 0.51, t0, u0),
             _snap("HOME", 0.56, t1, u1), _snap("AWAY", 0.44, t1, None),     # one unknown: unknown
             _snap("HOME", 0.40, KO - timedelta(hours=2), None, source="kalshi"),
             _snap("AWAY", 0.60, KO - timedelta(hours=2), None, source="kalshi"),
             _snap("HOME", 0.50, KO - timedelta(minutes=30), None, source="kalshi"),
             _snap("AWAY", 0.50, KO - timedelta(minutes=30), None, source="kalshi")]
    lm = line_move(snaps, KO, KO - timedelta(minutes=30))
    b = lm["venues"]["book"]
    assert b["from_at"] == t0.isoformat() and b["from_source_updated_at"] == u0.isoformat()
    assert b["to_at"] == t1.isoformat() and b["to_source_updated_at"] is None
    assert "from_source_updated_at" not in lm["venues"]["kalshi"]       # Kalshi: not those prices
    # rows differ at one capture: the oldest
    snaps[3] = _snap("AWAY", 0.44, t1, u1 - timedelta(minutes=5))
    b = line_move(snaps, KO, KO - timedelta(minutes=30))["venues"]["book"]
    assert b["to_source_updated_at"] == (u1 - timedelta(minutes=5)).isoformat()


def test_nfl_results_value_anchor_shows_it(tmp_path):
    from src.walters.nfl_predict import export_nfl_results
    init_db()
    ko = utc_now_naive().replace(microsecond=0) - timedelta(days=1)
    anchor_at = ko - timedelta(days=3)
    with session_scope() as s:
        c = s.execute(select(Competition).where(Competition.sport == Sport.NFL,
                                                Competition.code == "NFL")).scalars().first()
        if c is None:
            c = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="USA", type="LEAGUE")
            s.add(c)
            s.flush()
        rows = {}
        for tag, u in (("known", UPD), ("unknown", None)):
            h, a = Team(sport=Sport.NFL, name=f"SUAR {tag} Home"), Team(sport=Sport.NFL, name=f"SUAR {tag} Away")
            s.add_all([h, a])
            s.flush()
            m = Match(sport=Sport.NFL, competition_id=c.id, season="2026", utc_date=ko, status=MatchStatus.FINISHED,
                      home_team_id=h.id, away_team_id=a.id, home_score=27, away_score=7, external_ids={"suar": tag})
            s.add(m)
            s.flush()
            s.add(Prediction(match_id=m.id, model_version="t", home_win_prob=0.489, away_win_prob=0.511,
                             computed_at=ko - timedelta(days=2)))
            for sel, p in (("HOME", 0.355), ("AWAY", 0.645)):
                s.add(OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=p, n_books=5,
                                   captured_at=anchor_at, source="api_american_football", source_updated_at=u))
                s.add(Odds(match_id=m.id, bookmaker="bk", market="1X2", selection=sel, price_decimal=1 / p,
                           source="api_american_football", captured_at=ko - timedelta(hours=1)))
            rows[tag] = m.id
    try:
        path = export_nfl_results(days_back=3, out_dir=str(tmp_path))
    finally:
        # the shared throwaway DB: other modules export the NFL competition, so these games leave it.
        # The matches stay (a deleted id is reused, and prediction_history keys on it); their odds go.
        with session_scope() as s:
            ids = list(rows.values())
            for model in (Odds, OddsSnapshot):
                s.query(model).filter(model.match_id.in_(ids)).delete(synchronize_session=False)
            park = s.execute(select(Competition).where(Competition.code == "SUARX")).scalar_one_or_none()
            if park is None:
                park = Competition(sport=Sport.NFL, code="SUARX", name="SUARX", area="US", type="LEAGUE")
                s.add(park)
                s.flush()
            s.query(Match).filter(Match.id.in_(ids)).update({Match.competition_id: park.id},
                                                            synchronize_session=False)
    by = {x["match_id"]: x["graded"] for x in json.load(open(path))["results"]}
    g = by[rows["known"]]
    assert g["value_anchor_at"] == anchor_at.isoformat()
    assert g["value_anchor_source_updated_at"] == UPD.isoformat()
    assert by[rows["unknown"]]["value_anchor_source_updated_at"] is None
    # the close's own source time on results rows is NOT in this lane (addendum 32 item 4)
    assert not any("source" in k and "close" in k and "updated" in k for k in g)


# -------------------------------------------------------------- migration ----

def test_migration_is_additive_idempotent_and_receipts(tmp_path, monkeypatch, capsys):
    import migrate_odds_source_updated_at as mig
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:                                         # a pre-migration schema
        c.execute(text("CREATE TABLE odds (id INTEGER PRIMARY KEY, match_id INTEGER, source VARCHAR, "
                       "captured_at DATETIME)"))
        c.execute(text("CREATE TABLE odds_snapshots (id INTEGER PRIMARY KEY, match_id INTEGER, source VARCHAR, "
                       "captured_at DATETIME)"))
        c.execute(text("INSERT INTO odds VALUES (1, 7, 'api_american_football', '2026-10-09 22:07:00')"))
        c.execute(text("INSERT INTO odds VALUES (2, 8, 'api_hockey', '2026-10-09 22:07:00')"))
        c.execute(text("INSERT INTO odds_snapshots VALUES (1, 7, 'api_american_football', '2026-10-09 22:07:00')"))
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    assert mig.main() == 0
    out = capsys.readouterr().out
    assert "+ Adding odds.source_updated_at" in out and "+ Adding odds_snapshots.source_updated_at" in out
    assert "api_american_football" in out and "api_hockey" in out
    with eng.connect() as c:                                       # data kept, no backfill
        assert c.execute(text("SELECT id, source, source_updated_at FROM odds ORDER BY id")).all() == [
            (1, "api_american_football", None), (2, "api_hockey", None)]
    # a sync after migrating fills the field; the second run is a schema no-op and the receipt counts it
    with eng.begin() as c:
        c.execute(text("UPDATE odds SET source_updated_at = '2026-10-08 02:15:10' WHERE id = 1"))
    assert mig.main() == 0
    out = capsys.readouterr().out
    assert "already exists" in out and "+ Adding" not in out
    line = next(x for x in out.splitlines() if x.strip().startswith("odds ") and "api_american_football" in x)
    assert line.split()[2:5] == ["1", "1", "0"]                     # rows, with, without
    hockey = next(x for x in out.splitlines() if x.strip().startswith("odds ") and "api_hockey" in x)
    assert hockey.split()[2:5] == ["1", "0", "1"]
    with eng.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM odds")).scalar_one() == 2


def test_migration_refuses_without_the_tables(tmp_path, monkeypatch, capsys):
    import migrate_odds_source_updated_at as mig
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    assert mig.main() == 1
    assert "nothing to migrate" in capsys.readouterr().out
