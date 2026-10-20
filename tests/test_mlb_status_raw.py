"""STATUS_RAW ON THE STATSAPI PATH (ARCHITECT 2026-10-20, addendum 146 item 3(b); #568), verbatim: "The statsapi adapter
stores codedGameState verbatim in status_raw on every row it writes, as the api-football, api-hockey and api-sports
paths do (NormalizedMatch.status_raw). Receipt: the ALCS rows' status_raw after one sync."

The adapter reads the code before its "S" default (as api_hockey and api_football read theirs): a code the entry does
not give, or gives as anything but a non-blank text, is None, never "S"; the mapped status and the pre-game score
nulling are unchanged. The sync stores it on a row it creates and writes it on a row it updates; an entry without one
keeps the stored code (service.py: "never blank a stored code with an absent one"). The entries are synthetic in the
/schedule shape (tests/test_match_series_fields.py's game(); no statsapi payload is kept under tests/fixtures)."""
import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine, text

from tests.test_match_series_fields import ALCS, CLE, TB, _adapter, _alcs_rows, g3, g4, g5, game, schedule


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A throwaway DB of its own, as tests/test_match_series_fields.py's (not migrated: status_raw is a mapped
    column)."""
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


def _parsed(status):
    """The NormalizedMatch _parse_game makes of one entry whose status block is `status`."""
    g = game(849818, "2026-10-15T22:08:00Z", "F", TB, CLE, 2, 3)
    g["status"] = status
    return _adapter()._parse_game(g, "MLB")


def test_every_mapped_code_is_stored_verbatim_and_the_status_is_unchanged():
    from src.adapters.mlb_stats_api import _STATUS_MAP
    for code, status in _STATUS_MAP.items():
        nm = _parsed({"codedGameState": code})
        assert (nm.status_raw, nm.status) == (code, status), code


def test_an_unmapped_code_is_stored_verbatim_and_stays_scheduled():
    nm = _parsed({"codedGameState": "XQ", "detailedState": "Something new"})
    assert (nm.status_raw, nm.status.name) == ("XQ", "SCHEDULED")                   # law 4: the code kept, unmapped


@pytest.mark.parametrize("status", [{}, {"detailedState": "Final"}, {"codedGameState": ""},
                                    {"codedGameState": "  "}, {"codedGameState": 5}, {"codedGameState": None}],
                         ids=["no-block-key", "no-code", "empty", "blank", "a-number", "null"])
def test_a_code_not_given_as_text_is_none_never_s(status):
    nm = _parsed(status)
    assert nm.status_raw is None and nm.status.name == "SCHEDULED"


def test_a_missing_status_block_is_none():
    g = game(849818, "2026-10-15T22:08:00Z", "F", TB, CLE, 2, 3)
    del g["status"]
    nm = _adapter()._parse_game(g, "MLB")
    assert (nm.status_raw, nm.status.name, nm.home_score) == (None, "SCHEDULED", None)    # the "S" default, as before


@pytest.mark.parametrize("code", ["S", "P", "PW"])
def test_a_pregame_code_still_nulls_the_scores(code):
    nm = _parsed({"codedGameState": code})
    assert (nm.status_raw, nm.home_score, nm.away_score) == (code, None, None)


def test_a_final_keeps_its_scores_and_code():
    nm = _parsed({"codedGameState": "F"})
    assert (nm.status_raw, nm.status.name, nm.home_score, nm.away_score) == ("F", "FINISHED", 3, 2)


# --------------------------------------------------------------------------------------------- the sync ----

def _sync(monkeypatch, payload):
    import cli
    a = _adapter(payload)
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: a)
    r = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "MLB", "--date-from", "2026-10-12",
                                     "--date-to", "2026-10-21"])
    assert r.exit_code == 0, r.output


def _raw(eng):
    """{gamePk: (status, status_raw)}, by raw SQL."""
    with eng.connect() as c:
        return {str(pk).strip('"'): (st, raw) for pk, st, raw in c.execute(text(
            "SELECT json_extract(external_ids, '$.mlb_stats_api'), status, status_raw FROM matches"))}


def test_the_alcs_rows_status_raw_after_one_sync(fresh_db, monkeypatch):
    """The ruled receipt's shape: 50546 / 50550 / 50548 stored before (status_raw NULL, as every statsapi row is
    today), one sync lists them, each gets its own code; a row the sync does not list keeps NULL (50555's case: the
    provider dropped it, so no sync ever writes it)."""
    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus
    comp_id = _alcs_rows()
    with session_scope() as s:
        m = s.get(Match, 50546)
        s.add(Match(id=50555, sport=m.sport, competition_id=comp_id, season="2026", stage="L",
                    utc_date=m.utc_date.replace(day=21), status=MatchStatus.SCHEDULED, home_team_id=m.away_team_id,
                    away_team_id=m.home_team_id, external_ids={"mlb_stats_api": "849814"}))
    assert {v[1] for v in _raw(fresh_db).values()} == {None}
    _sync(monkeypatch, schedule(g3(), g4(), g5()))
    assert _raw(fresh_db) == {"849818": ("FINISHED", "F"), "849816": ("FINISHED", "F"),
                              "849817": ("SCHEDULED", "S"), "849814": ("SCHEDULED", None)}


def test_a_created_row_stores_the_code_and_an_update_writes_the_new_one(fresh_db, monkeypatch):
    _alcs_rows()
    _sync(monkeypatch, schedule(game(776002, "2026-10-21T00:08:00Z", "P", TB, CLE, seriesGameNumber=7,
                                     gamesInSeries=7, seriesDescription=ALCS)))
    assert _raw(fresh_db)["776002"] == ("SCHEDULED", "P")                             # created
    _sync(monkeypatch, schedule(game(776002, "2026-10-21T00:08:00Z", "I", TB, CLE, 1, 0)))
    assert _raw(fresh_db)["776002"] == ("LIVE", "I")                                  # updated
    gone = game(776002, "2026-10-21T00:08:00Z", "F", TB, CLE, 4, 2)
    gone["status"] = {"detailedState": "Final"}                                       # the entry gives no code
    _sync(monkeypatch, schedule(gone))
    assert _raw(fresh_db)["776002"] == ("SCHEDULED", "I")                             # the stored code kept
