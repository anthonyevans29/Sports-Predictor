"""THE SERIES FIELDS (ARCHITECT 2026-10-18 10:10 ET, addendum 130 item 2(b)), verbatim: "DATA NOW, so the 2027 rule has
it and so the reconciliation below has a receipt: the laptop's statsapi sync stores `seriesGameNumber`,
`gamesInSeries`, `seriesDescription` and `rescheduledFrom` on the match row (additive columns by the unmapped pattern,
like #588's; migration by hand after the backup). Code: one small PR, data only, no reader changes its behaviour."

The fixture is the ALCS 2026 set of addendum 130 item 1(a): "gamePk 849818 = our 50546, Game 3, Oct 15, Final 2-3.
gamePk 849816 = our 50550, played Oct 17 20:08 ET, Final Rays 7-3, now **Game 4 of 7**. gamePk 849817 = our 50548:
the Oct 16 game, POSTPONED, rescheduled to Oct 18 21:08Z, now **Game 5 of 7** (rescheduledFrom 2026-10-17T00:00Z)."
The entries are synthetic in the statsapi /schedule shape (no statsapi payload is kept under tests/fixtures; the
field names are the ruling's): Game 3's clock, which side scored 2 in Game 3, and the series description are
this file's.

Covers: the adapter reads each game's own four fields, None where the entry has none or gives a shape it does not
read; the ORM never names the columns; sync-matches stores them after the migration, each row from its own entry
(NULL for a regular-season game without them, NULL for a field a later entry drops, never another game's), and a game
listed twice keeps its last entry, the one its status and kickoff come from; before the migration the sync writes its
rows and nothing else (no backfill after it); the api-sports fallback writes none; no export, Desk, window card or
matcher output changes, and an existing export test runs unchanged on a DB whose every match row carries the fields;
the migration is additive, idempotent, receipted, and refuses with no table and with no database file."""
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine, inspect, select, text

REPO = Path(__file__).resolve().parents[1]
COLS = ("series_game_number", "games_in_series", "series_description", "rescheduled_from")
ALCS = "AL Championship Series"
TB, CLE, NYY, BOS = (139, "Tampa Bay Rays"), (114, "Cleveland Guardians"), (147, "New York Yankees"), \
    (111, "Boston Red Sox")
Z = datetime.fromisoformat                                                    # naive UTC


def game(pk, when, code, away, home, ar=None, hr=None, game_type="L", **series):
    """One statsapi /schedule game entry; `series` holds the entry's own seriesGameNumber / gamesInSeries /
    seriesDescription / rescheduledFrom (left out = the entry has none)."""
    return {"gamePk": pk, "gameDate": when, "season": "2026", "gameType": game_type,
            "status": {"codedGameState": code},
            "teams": {"away": {"team": {"id": away[0]}, "score": ar}, "home": {"team": {"id": home[0]}, "score": hr}},
            "venue": {"name": "Progressive Field"}, **series}


def g3():
    return game(849818, "2026-10-15T22:08:00Z", "F", TB, CLE, 2, 3, seriesGameNumber=3, gamesInSeries=7,
                seriesDescription=ALCS)


def g4():
    return game(849816, "2026-10-18T00:08:00Z", "F", TB, CLE, 7, 3, seriesGameNumber=4, gamesInSeries=7,
                seriesDescription=ALCS)


def g5(**over):
    s = {"seriesGameNumber": 5, "gamesInSeries": 7, "seriesDescription": ALCS, "rescheduledFrom": "2026-10-17T00:00:00Z"}
    s.update(over)
    return game(849817, "2026-10-18T21:08:00Z", "S", TB, CLE, **{k: v for k, v in s.items() if v is not None})


def g5_postponed():
    """849817 on its old date, as a postponed entry (a synthetic shape: a game listed on its old and new dates)."""
    return game(849817, "2026-10-17T00:00:00Z", "D", TB, CLE, seriesGameNumber=4, gamesInSeries=7,
                seriesDescription=ALCS)


def regular():
    return game(776001, "2026-09-27T17:05:00Z", "F", BOS, NYY, 2, 5, game_type="R")


def schedule(*games):
    return {"dates": [{"date": g["gameDate"][:10], "games": [g]} for g in games]}


# --------------------------------------------------- the adapter ----

def _adapter(payload=None):
    from src.adapters.mlb_stats_api import MLBStatsAPIAdapter
    a = MLBStatsAPIAdapter.__new__(MLBStatsAPIAdapter)
    a.calls = []
    a._get = lambda path, params=None: (a.calls.append((path, params)), payload)[1]
    return a


def test_the_adapter_reads_each_games_own_fields():
    out = {m.source_id: m.series for m in _adapter(schedule(g3(), g4(), g5(), regular())).list_matches("MLB", "2026")}
    assert out == {
        "849818": {"series_game_number": 3, "games_in_series": 7, "series_description": ALCS, "rescheduled_from": None},
        "849816": {"series_game_number": 4, "games_in_series": 7, "series_description": ALCS, "rescheduled_from": None},
        "849817": {"series_game_number": 5, "games_in_series": 7, "series_description": ALCS,
                   "rescheduled_from": "2026-10-17T00:00:00Z"},
        "776001": {"series_game_number": None, "games_in_series": None, "series_description": None,
                   "rescheduled_from": None},
    }


def test_a_shape_it_does_not_read_is_none_never_guessed():
    from src.adapters.mlb_stats_api import series_fields
    assert series_fields({"seriesGameNumber": "5", "gamesInSeries": " 7 ", "seriesDescription": "  World Series ",
                          "rescheduledFrom": "2026-10-16T20:00:00-04:00"}) == {
        "series_game_number": 5, "games_in_series": 7, "series_description": "World Series",
        "rescheduled_from": "2026-10-17T00:00:00Z"}                       # an offset is read as its UTC time
    assert series_fields({"rescheduledFrom": "2026-10-17T00:00Z"})["rescheduled_from"] == "2026-10-17T00:00:00Z"
    for bad in ({"seriesGameNumber": True, "gamesInSeries": 7.0, "seriesDescription": "   ",
                 "rescheduledFrom": "2026-10-17T00:00:00"},               # no zone: not read as UTC
                {"seriesGameNumber": "٤", "gamesInSeries": "seven", "seriesDescription": 4,
                 "rescheduledFrom": "Oct 17"},
                {"seriesGameNumber": None, "gamesInSeries": [], "seriesDescription": None, "rescheduledFrom": 17},
                {}):
        assert series_fields(bad) == dict.fromkeys(COLS), bad


def test_only_the_statsapi_adapter_carries_series_fields():
    """Every other adapter's NormalizedMatch leaves `series` None: nothing is written for its rows."""
    from src.adapters.normalized import NormalizedMatch
    from src.db.schema import MatchStatus, Sport
    nm = NormalizedMatch(sport=Sport.SOCCER, competition_code="PL", season="2026/27", utc_date=Z("2026-10-18T14:00"),
                         status=MatchStatus.SCHEDULED, home_team_source_id="1", away_team_source_id="2",
                         source="api_football", source_id="9")
    assert nm.series is None


def test_the_orm_never_names_the_columns(tmp_path):
    """The ORDER LINE convention: unmapped, so a matches INSERT and SELECT work on a DB without the columns."""
    from sqlalchemy.orm import Session

    from src.db.schema import Base, Competition, Match, MatchStatus, Sport, Team
    assert not set(COLS) & set(Match.__table__.columns.keys())
    eng = create_engine(f"sqlite:///{tmp_path / 'pre.db'}")
    Base.metadata.create_all(eng)
    assert not set(COLS) & {c["name"] for c in inspect(eng).get_columns("matches")}
    with Session(eng) as s:
        c = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="USA", type="LEAGUE")
        h, a = Team(sport=Sport.MLB, name="H"), Team(sport=Sport.MLB, name="A")
        s.add_all([c, h, a])
        s.flush()
        s.add(Match(sport=Sport.MLB, competition_id=c.id, season="2026", utc_date=Z("2026-10-18T21:08"),
                    status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id))
        s.commit()
        assert s.query(Match).count() == 1
    eng.dispose()


# --------------------------------------------------- the sync ----

@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A throwaway DB of its own (the shared test DB may be migrated by another test): the pattern of
    tests/test_kalshi_history.py."""
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    monkeypatch.delenv("SP_SKIP_FAMILIES", raising=False)                  # statsapi, the laptop's path
    db.init_db()
    yield eng
    eng.dispose()


def _migrate(capsys=None):
    import migrate_match_series_fields as mig
    assert mig.main() == 0
    return capsys.readouterr().out if capsys is not None else None


def _alcs_rows():
    """Our 50546 / 50548 / 50550 as stored before the sync: keyed by their gamePks, the receipt's ids."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with session_scope() as s:
        comp = Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA", type="LEAGUE")
        s.add(comp)
        t = {}
        for sid, name in (TB, CLE, NYY, BOS):
            t[sid] = Team(sport=Sport.MLB, name=name, external_ids={"mlb_stats_api": str(sid)})
            s.add(t[sid])
        s.flush()
        for mid, pk, when in ((50546, "849818", "2026-10-15T22:08"), (50548, "849817", "2026-10-17T00:00"),
                              (50550, "849816", "2026-10-17T00:08")):
            s.add(Match(id=mid, sport=Sport.MLB, competition_id=comp.id, season="2026", stage="L", utc_date=Z(when),
                        status=MatchStatus.SCHEDULED, home_team_id=t[CLE[0]].id, away_team_id=t[TB[0]].id,
                        external_ids={"mlb_stats_api": pk}))
        return comp.id


def _sync(monkeypatch, payload):
    import cli
    a = _adapter(payload)
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: a)
    r = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "MLB", "--date-from", "2026-09-27",
                                     "--date-to", "2026-10-19"])
    assert r.exit_code == 0, r.output
    assert a.calls and a.calls[0][0] == "schedule"
    return r.output


def _series(eng):
    """{gamePk: (series_game_number, games_in_series, series_description, rescheduled_from)}, by raw SQL."""
    with eng.connect() as c:
        return {str(pk).strip('"'): tuple(r) for pk, *r in c.execute(text(
            "SELECT json_extract(external_ids, '$.mlb_stats_api'), " + ", ".join(COLS) + " FROM matches"))}


def _row(gk):
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:
        m = next(m for m in s.execute(select(Match)).scalars() if (m.external_ids or {}).get("mlb_stats_api") == gk)
        return m.id, m.status.name, m.utc_date


def test_after_the_migration_the_sync_stores_each_games_own_fields(fresh_db, monkeypatch):
    _alcs_rows()
    _migrate()
    _sync(monkeypatch, schedule(g3(), g4(), g5(), regular()))
    assert _series(fresh_db) == {
        "849818": (3, 7, ALCS, None),
        "849816": (4, 7, ALCS, None),
        "849817": (5, 7, ALCS, "2026-10-17T00:00:00Z"),
        "776001": (None, None, None, None),                                   # a regular-season game without them
    }
    assert _row("849818")[0] == 50546 and _row("849816")[0] == 50550           # the receipt's rows, by gamePk
    assert _row("849817") == (50548, "SCHEDULED", Z("2026-10-18T21:08"))       # the rescheduled game, Game 5


def test_a_field_a_later_entry_drops_is_nulled_and_never_taken_from_another_game(fresh_db, monkeypatch):
    _alcs_rows()
    _migrate()
    _sync(monkeypatch, schedule(g3(), g4(), g5(), regular()))
    _sync(monkeypatch, schedule(g5(rescheduledFrom=None, gamesInSeries=None), regular()))   # only these two listed
    assert _series(fresh_db) == {
        "849818": (3, 7, ALCS, None),                                         # not listed: untouched
        "849816": (4, 7, ALCS, None),
        "849817": (5, None, ALCS, None),                                      # its own entry, NULL where it has none
        "776001": (None, None, None, None),
    }


@pytest.mark.parametrize("order", ["old date first", "new date first"])
def test_a_game_listed_twice_keeps_the_entry_its_status_and_kickoff_come_from(fresh_db, monkeypatch, order):
    _alcs_rows()
    _migrate()
    entries = [g5_postponed(), g5()] if order == "old date first" else [g5(), g5_postponed()]
    _sync(monkeypatch, schedule(*entries))
    if order == "old date first":
        assert _row("849817") == (50548, "SCHEDULED", Z("2026-10-18T21:08"))
        assert _series(fresh_db)["849817"] == (5, 7, ALCS, "2026-10-17T00:00:00Z")
    else:
        assert _row("849817") == (50548, "POSTPONED", Z("2026-10-17T00:00"))
        assert _series(fresh_db)["849817"] == (4, 7, ALCS, None)


def test_before_the_migration_the_sync_writes_its_rows_and_nothing_else(fresh_db, monkeypatch, capsys):
    from src.db.database import has_match_series
    _alcs_rows()
    assert not has_match_series()
    _sync(monkeypatch, schedule(g3(), g4(), g5(), regular()))                 # a pull before the migration
    assert not set(COLS) & {c["name"] for c in inspect(fresh_db).get_columns("matches")}
    assert _row("849817") == (50548, "SCHEDULED", Z("2026-10-18T21:08"))       # the sync itself, as before
    assert _row("776001")[1] == "FINISHED"
    out = _migrate(capsys)                                                    # no backfill: every row NULL
    assert _series(fresh_db) == dict.fromkeys(("849818", "849816", "849817", "776001"), (None,) * 4)
    assert "  MLB                   4        0         0        0        0        4" in out
    _sync(monkeypatch, schedule(g3(), g4(), g5(), regular()))                 # the next sync fills them
    assert _series(fresh_db)["849817"] == (5, 7, ALCS, "2026-10-17T00:00:00Z")


def test_the_api_sports_fallback_writes_none(fresh_db, monkeypatch):
    """The host's MLB path: a row it links and updates keeps what statsapi stored; a row it creates stays NULL."""
    from src.ingestion import mlb_apisports as fb
    _alcs_rows()
    _migrate()
    _sync(monkeypatch, schedule(g3(), g4(), g5()))

    class Client:
        requests_remaining = 9

        def list_teams(self, season):
            return [{"id": i, "name": n, "code": None} for i, n in ((1, TB[1]), (2, CLE[1]), (3, NYY[1]), (4, BOS[1]))]

        def _get(self, path, params=None):
            def gm(gid, home, away, at, short, hs, as_):
                return {"id": gid, "date": at, "week": "Regular Season", "status": {"short": short, "long": short},
                        "teams": {"home": {"id": home[0], "name": home[1]}, "away": {"id": away[0], "name": away[1]}},
                        "scores": {"home": {"total": hs}, "away": {"total": as_}}}
            return {"response": [gm(91, (2, CLE[1]), (1, TB[1]), "2026-10-18T00:08:00+00:00", "FT", 3, 7),   # 50550
                                 gm(92, (3, NYY[1]), (4, BOS[1]), "2026-09-20T17:05:00+00:00", "FT", 4, 1)]}  # new

    before = _series(fresh_db)
    r = fb.sync_matches(Client(), "2026")
    assert r["linked_existing"] == 1 and r["created"] == 1, r
    after = _series(fresh_db)
    assert {k: v for k, v in after.items() if k in before} == before
    with fresh_db.connect() as c:
        created = c.execute(text("SELECT " + ", ".join(COLS) + " FROM matches WHERE external_ids NOT LIKE "
                                 "'%mlb_stats_api%'")).all()
    assert created == [(None,) * 4]


# --------------------------------------------------- no reader changes ----

def _scrub(o):
    """The run's own clock and checkout leave the comparison: exported_at, git_sha, as_of, generated_at."""
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if k not in ("exported_at", "git_sha", "as_of", "generated_at")}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def _markets():
    def event(stamp, bid):
        e = f"KXMLBGAME-{stamp}TBCLE"
        return [{"event_ticker": e, "ticker": f"{e}-{sfx}", "title": f"{name} wins", "yes_sub_title": name,
                 "yes_bid_dollars": b, "yes_ask_dollars": f"{float(b) + 0.02:.2f}"}
                for sfx, name, b in (("TB", "Tampa Bay", bid), ("CLE", "Cleveland", f"{0.98 - float(bid):.2f}"))]
    return event("26OCT151800", "0.44") + event("26OCT161800", "0.52") + event("26OCT172000", "0.53")


def _outputs(tmp_path, comp_id):
    import json

    from src.db.database import session_scope
    from src.db.schema import Sport
    from src.ingestion import kalshi_match as km
    from src.ingestion.kalshi_sync import stored_games
    from src.walters.export import export_predictions, export_results
    from src.walters.window import build_card
    lo, hi = Z("2026-10-14T00:00"), Z("2026-10-20T00:00")
    preds = json.loads(export_predictions(sport=Sport.MLB, start_date=lo, end_date=hi, competition_code="MLB",
                                          desk=True))
    res = json.loads(export_results(sport=Sport.MLB, start_date=lo, end_date=hi, competition_code="MLB",
                                    exports_dir=str(tmp_path)))
    card = build_card(now=Z("2026-10-18T13:00"), export_dir=str(tmp_path))
    mks, now = _markets(), Z("2026-10-18T13:00")
    with session_scope() as s:
        r = km.place(mks, stored_games(s, [comp_id], mks), now=now, lo=now - timedelta(days=4),
                     hi=now + timedelta(days=2))
        placed = {k: mk["ticker"] for k, mk in r.placed.items()}
    assert preds["count"] == 3                                                # the three ALCS rows, each a call
    return _scrub(preds), _scrub(res), _scrub(card), (placed, dict(r.refused), r.lines, r.why)


def test_no_export_desk_card_or_matcher_output_changes(fresh_db, tmp_path):
    from src.db.database import session_scope, write_match_series
    from src.db.schema import OddsSnapshot, Prediction, PredictionOutcome, Result
    comp_id = _alcs_rows()
    with session_scope() as s:
        for mid, (h, a) in ((50546, (0.55, 0.45)), (50548, (0.505, 0.495)), (50550, (0.52, 0.48))):
            p = Prediction(match_id=mid, model_version="t", home_win_prob=h, draw_prob=None, away_win_prob=a)
            s.add(p)
            for sel, prob in (("HOME", h - 0.02), ("AWAY", a + 0.02)):
                s.add(OddsSnapshot(match_id=mid, market="1X2", selection=sel, devig_prob=prob, n_books=6,
                                   captured_at=Z("2026-10-14T12:00"), source="api_baseball"))
                s.add(OddsSnapshot(match_id=mid, market="ML", selection=sel, devig_prob=prob, n_books=1,
                                   captured_at=Z("2026-10-14T12:00"), source="kalshi", yes_bid=prob - 0.01,
                                   yes_ask=prob + 0.01))
            if mid == 50546:
                s.flush()
                s.add(PredictionOutcome(prediction_id=p.id, actual_result=Result.HOME, actual_home_score=3,
                                        actual_away_score=2, log_loss=0.6, brier_score=0.2, top_pick_hit=True))
    before = _outputs(tmp_path, comp_id)
    _migrate()
    with session_scope() as s:
        assert write_match_series(s, [(50546, {"series_game_number": 3, "games_in_series": 7,
                                               "series_description": ALCS}),
                                      (50550, {"series_game_number": 4, "games_in_series": 7,
                                               "series_description": ALCS}),
                                      (50548, {"series_game_number": 5, "games_in_series": 7,
                                               "series_description": ALCS,
                                               "rescheduled_from": "2026-10-17T00:00:00Z"})]) == 3
    assert _series(fresh_db)["849817"] == (5, 7, ALCS, "2026-10-17T00:00:00Z")
    assert _outputs(tmp_path, comp_id) == before


def test_an_existing_export_test_runs_unchanged_when_every_match_row_carries_the_fields(fresh_db):
    """tests/test_kalshi_exec_mlb_soccer.py's export test, unedited, on a migrated DB where a trigger gives every
    match row it inserts all four fields (so each row it exports carries them)."""
    import test_kalshi_exec_mlb_soccer as existing
    _migrate()
    with fresh_db.begin() as c:
        c.execute(text("CREATE TRIGGER series_on_every_row AFTER INSERT ON matches BEGIN UPDATE matches SET "
                       "series_game_number = 4, games_in_series = 7, series_description = 'AL Championship Series', "
                       "rescheduled_from = '2026-10-17T00:00:00Z' WHERE id = NEW.id; END"))
    existing.test_mlb_and_soccer_rows_carry_home_contract_exec_cost()
    with fresh_db.connect() as c:
        rows = c.execute(text("SELECT " + ", ".join(COLS) + " FROM matches")).all()
    assert len(rows) == 4 and set(rows) == {(4, 7, ALCS, "2026-10-17T00:00:00Z")}


# --------------------------------------------------- the migration ----

def test_migration_is_additive_idempotent_and_receipts(tmp_path, monkeypatch, capsys):
    import migrate_match_series_fields as mig
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    Base.metadata.create_all(eng)                                   # the pre-migration schema (columns unmapped)
    with eng.begin() as c:
        c.execute(text("INSERT INTO competitions (id, sport, code, name, area, type, external_ids) VALUES "
                       "(1, 'MLB', 'MLB', 'MLB', 'USA', 'LEAGUE', '{}'), (2, 'SOCCER', 'PL', 'PL', 'ENG', 'LEAGUE', '{}')"))
        c.execute(text("INSERT INTO matches (id, sport, competition_id, season, utc_date, status, home_team_id, "
                       "away_team_id, external_ids) VALUES "
                       "(50548, 'MLB', 1, '2026', '2026-10-18 21:08:00', 'SCHEDULED', 1, 2, '{}'), "
                       "(50550, 'MLB', 1, '2026', '2026-10-18 00:08:00', 'FINISHED', 1, 2, '{}'), "
                       "(7, 'SOCCER', 2, '2026/27', '2026-10-18 14:00:00', 'SCHEDULED', 3, 4, '{}')"))
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    assert mig.main() == 0
    out = capsys.readouterr().out
    assert [ln for ln in out.splitlines() if ln.startswith("+ ")] == [
        f"+ Adding matches.{c}..." for c in COLS]
    with eng.connect() as c:                                        # data kept, no backfill
        assert c.execute(text("SELECT id, status, " + ", ".join(COLS) + " FROM matches ORDER BY id")).all() == [
            (7, "SCHEDULED", None, None, None, None), (50548, "SCHEDULED", None, None, None, None),
            (50550, "FINISHED", None, None, None, None)]
    with eng.begin() as c:                                          # a statsapi sync after migrating fills them
        c.execute(text("UPDATE matches SET series_game_number = 5, games_in_series = 7, "
                       "series_description = 'AL Championship Series', rescheduled_from = '2026-10-17T00:00:00Z' "
                       "WHERE id = 50548"))
    assert mig.main() == 0                                          # the second run: a schema no-op
    out = capsys.readouterr().out
    assert [ln for ln in out.splitlines() if ln.startswith("· ")] == [
        f"· matches.{c} already exists." for c in COLS] and "+ Adding" not in out
    receipt = {ln.split()[0]: ln.split()[1:] for ln in out.splitlines() if ln.startswith("  ") and
               ln.split()[0] in ("MLB", "PL")}
    assert receipt == {"MLB": ["2", "1", "1", "1", "1", "1"], "PL": ["1", "0", "0", "0", "0", "1"]}
    with eng.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM matches")).scalar_one() == 3
    eng.dispose()


def test_a_partly_migrated_db_gets_the_rest(tmp_path, monkeypatch, capsys):
    import migrate_match_series_fields as mig
    from src.db.database import has_match_series
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{tmp_path / 'part.db'}")
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.execute(text("ALTER TABLE matches ADD COLUMN series_game_number INTEGER"))
    with eng.connect() as c:
        assert not has_match_series(c)                              # the writer needs all four
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    assert mig.main() == 0
    out = capsys.readouterr().out
    assert "· matches.series_game_number already exists." in out
    assert [ln for ln in out.splitlines() if ln.startswith("+ ")] == [f"+ Adding matches.{c}..." for c in COLS[1:]]
    with eng.connect() as c:
        assert has_match_series(c)
    eng.dispose()


def test_migration_refuses_without_the_table(tmp_path, monkeypatch, capsys):
    import migrate_match_series_fields as mig
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    eng.connect().close()                                           # an existing DB without the table
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    assert mig.main() == 1
    assert "nothing to migrate" in capsys.readouterr().out


def test_migration_refuses_when_the_database_file_is_absent(tmp_path):
    """The shared guard (#524, addendum 112 item 1), as tests/test_migrate_guard.py runs every migration: its own
    process, DATABASE_URL on a missing file in a missing directory; exit 1, the ruled line, nothing created."""
    missing = tmp_path / "nowhere" / "sports.db"
    r = subprocess.run([sys.executable, str(REPO / "migrate_match_series_fields.py")], cwd=str(REPO),
                       env={**os.environ, "DATABASE_URL": f"sqlite:///{missing}"}, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout == f"no database at {missing.resolve()}; a migration never creates one — law 5\n"
    assert list(tmp_path.iterdir()) == []
