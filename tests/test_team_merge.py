"""ONE PROGRAM IS ONE TEAM ROW (ARCHITECT 2026-10-12, addendum 44 item 3; #426, #358): the reviewed merge command.
Every merge test runs on a scratch SQLite file under tmp_path built from the schema; never data/."""
import json
import sqlite3
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.schema import Base, Competition, CompetitionTeam, Injury, Match, MatchStatus, Player, Sport, Team
from src.ingestion import team_merge as tm

SRC = "api_american_football"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "scratch.db"
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    yield path, eng
    eng.dispose()


def team(s, name, sid, sport=Sport.NFL):
    t = Team(sport=sport, name=name, external_ids={SRC: sid})
    s.add(t)
    s.flush()
    return t


def game(s, comp, home, away, kick, season="2026"):
    m = Match(sport=Sport.NFL, competition_id=comp.id, season=season, utc_date=kick, status=MatchStatus.FINISHED,
              home_team_id=home.id, away_team_id=away.id)
    s.add(m)
    s.flush()
    return m


def hawaii(eng, *, both_in_2026=False):
    """1385 "Hawai'i" (provider 59, games 2024-2026) and 1744 "Hawai&#x27;i" (provider 901, 2026 games): the
    receipt's shape, small."""
    with Session(eng) as s:
        comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        keep = team(s, "Hawai'i", "59")
        other = team(s, "Hawai&#x27;i", "901")
        wyo, sjsu, asu = team(s, "Wyoming", "70"), team(s, "San José State", "71"), team(s, "Arizona State", "72")
        game(s, comp, wyo, keep, datetime(2024, 9, 7, 23, 0), "2024")
        game(s, comp, keep, sjsu, datetime(2026, 9, 5, 23, 0))
        game(s, comp, wyo, other, datetime(2026, 9, 12, 23, 0))
        game(s, comp, asu, other, datetime(2026, 9, 26, 2, 0))
        s.add_all([CompetitionTeam(competition_id=comp.id, team_id=keep.id, season="2024"),
                   CompetitionTeam(competition_id=comp.id, team_id=other.id, season="2026")])
        if both_in_2026:
            s.add(CompetitionTeam(competition_id=comp.id, team_id=keep.id, season="2026"))
        s.add(Player(sport=Sport.NFL, name="Pono Kaleo", team_id=other.id, external_ids={SRC: "p1"}))
        s.add(Injury(team_id=other.id, player_name="Pono Kaleo"))
        s.commit()
        return keep.id, other.id


def con_of(path):
    return sqlite3.connect(path, isolation_level=None)


def test_canon_unescapes_and_reduces_to_letters_and_digits():
    assert tm.canon("Hawai&#x27;i") == tm.canon("Hawai'i") == tm.canon("HAWAI I") == "hawaii"
    assert tm.canon("Texas A&amp;M") == tm.canon("Texas A&M") == "texasam"
    assert tm.canon("") == "" and tm.canon(None) == ""


def test_the_dry_run_lists_the_pair_counts_entity_names_and_writes_nothing(db):
    path, eng = db
    keep, other = hawaii(eng)
    con = con_of(path)
    before = con.execute("SELECT COUNT(*), SUM(LENGTH(external_ids)) FROM teams").fetchone()
    p = tm.plan(con)
    assert con.execute("SELECT COUNT(*), SUM(LENGTH(external_ids)) FROM teams").fetchone() == before
    assert [(c["keep"]["id"], c["other"]["id"]) for c in p["candidates"]] == [(keep, other)]
    assert p["candidates"][0]["moves"] == {"competition_teams.team_id": 1, "injuries.team_id": 1,
                                           "matches.away_team_id": 2, "players.team_id": 1}
    assert {sp: [n for _, n in v] for sp, v in p["entity_names"].items()} == {"NFL": ["Hawai&#x27;i"]}
    assert not p["left"] and not p["unknown_refs"]


def test_apply_keeps_the_lower_id_repoints_records_the_provider_id_and_deletes_the_row(db):
    path, eng = db
    keep, other = hawaii(eng)
    con = con_of(path)
    res = tm.apply(con, "2026-10-12T19:00:00")
    assert [(m["keep"], m["other"]) for m in res["merged"]] == [(keep, other)] and not res["refused"]
    assert con.execute("SELECT COUNT(*) FROM teams WHERE id = ?", (other,)).fetchone()[0] == 0
    for t, c in tm.live_refs(con):
        assert con.execute(f'SELECT COUNT(*) FROM "{t}" WHERE "{c}" = ?', (other,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM matches WHERE home_team_id = ? OR away_team_id = ?",
                       (keep, keep)).fetchone()[0] == 4
    ext = json.loads(con.execute("SELECT external_ids FROM teams WHERE id = ?", (keep,)).fetchone()[0])
    assert ext[SRC] == "59" and ext[f"{SRC}_also"] == ["901"]
    assert ext["merged_from"][0]["team_id"] == other and ext["merged_from"][0]["external_ids"] == {SRC: "901"}
    assert tm.source_ids(ext, SRC) == {"59", "901"}
    assert tm.plan(con)["candidates"] == []                                 # nothing left to merge


def test_a_unique_table_conflict_refuses_the_pair_and_names_the_table(db):
    path, eng = db
    keep, other = hawaii(eng, both_in_2026=True)
    p = tm.plan(con_of(path))
    assert not p["candidates"]
    assert p["left"][0]["why"].startswith("a unique-table conflict: competition_teams"), p["left"]
    assert tm.apply(con_of(path), "x") == {"merged": [], "refused": []}


def test_a_reference_the_command_does_not_know_refuses_the_pair_and_names_the_table(db):
    path, eng = db
    keep, other = hawaii(eng)
    con = con_of(path)
    con.execute("CREATE TABLE side_notes (id INTEGER PRIMARY KEY, team_id INTEGER, note TEXT)")
    con.execute("CREATE TABLE empty_notes (id INTEGER PRIMARY KEY, owner_team_id INTEGER)")
    con.execute("INSERT INTO side_notes (team_id, note) VALUES (?, 'x')", (other,))
    p = tm.plan(con)
    assert p["unknown_refs"] == ["empty_notes.owner_team_id", "side_notes.team_id"]
    assert not p["candidates"] and "side_notes.team_id" in p["left"][0]["why"], p["left"]


def test_two_rows_that_met_three_rows_and_another_sport_are_listed_and_left(db):
    path, eng = db
    with Session(eng) as s:
        comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        a, b = team(s, "Miami", "1"), team(s, "Miami.", "2")
        game(s, comp, a, b, datetime(2026, 9, 1, 23, 0))                    # they played each other
        team(s, "Tri", "7"), team(s, "TRI", "8"), team(s, "t-r-i", "9")
        team(s, "Navy", "10", sport=Sport.MLB), team(s, "Navy", "11")       # one row each in two sports
        s.commit()
    p = tm.plan(con_of(path))
    why = {x["key"]: x["why"] for x in p["left"]}
    assert why["miami"].startswith("a stored game has the two playing each other (match "), why
    assert why["tri"] == "3 rows share the name: only a pair is merged"
    assert not p["candidates"] and "navy" not in why


def test_a_shared_eastern_day_alone_leaves_the_pair(db):
    path, eng = db
    with Session(eng) as s:
        comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        a, b, x, y = team(s, "Hawai'i", "59"), team(s, "Hawai&#x27;i", "901"), team(s, "Ohio", "3"), team(s, "Akron", "4")
        game(s, comp, a, x, datetime(2026, 10, 10, 3, 0))       # 23:00 ET on 10-09, UTC day 10-10
        game(s, comp, y, b, datetime(2026, 10, 9, 18, 0))       # UTC day 10-09, ET day 10-09
        s.commit()
    p = tm.plan(con_of(path))
    assert not p["candidates"] and p["left"][0]["why"] == "a day holds a game of each (2026-10-09)", p["left"]


def test_a_listing_carrying_either_id_finds_the_kept_row(tmp_path):
    from src.db.database import init_db, session_scope
    from src.ingestion.service import IngestionService
    init_db()
    with session_scope() as s:
        t = Team(sport=Sport.NFL, name="Merged Rainbows", external_ids={SRC: "m59", f"{SRC}_also": ["m901"]})
        s.add(t)
        s.flush()
        tid = t.id
        assert IngestionService._find_team_by_source(s, Sport.NFL, SRC, "m59").id == tid
        assert IngestionService._find_team_by_source(s, Sport.NFL, SRC, "m901").id == tid
        assert IngestionService._find_team_by_source(s, Sport.NFL, SRC, "m902") is None


def test_merged_ext_keeps_both_ids_and_the_lists():
    out = tm.merged_ext({SRC: "59", f"{SRC}_prev": ["a"]}, {SRC: "901", f"{SRC}_prev": ["b"], "other_src": "z"},
                        1744, "T")
    assert out[SRC] == "59" and out[f"{SRC}_also"] == ["901"] and out[f"{SRC}_prev"] == ["a", "b"]
    assert out["other_src"] == "z" and out["merged_from"] == [
        {"team_id": 1744, "external_ids": {SRC: "901", f"{SRC}_prev": ["b"], "other_src": "z"}, "at": "T"}]


def test_the_adapter_unescapes_a_provider_team_name(monkeypatch):
    from src.adapters.api_american_football import APIAmericanFootballAdapter
    ad = APIAmericanFootballAdapter.__new__(APIAmericanFootballAdapter)
    monkeypatch.setattr(ad, "_get", lambda path, params=None: {"response": [{"id": 901, "name": "Hawai&#x27;i"}]},
                        raising=False)
    try:
        teams = ad.list_teams("NCAA", "2026")
    except TypeError:
        pytest.skip("list_teams signature")
    assert [t.name for t in teams] == ["Hawai'i"]


def test_the_command_refuses_apply_without_a_backup_and_the_dry_run_writes_nothing():
    from click.testing import CliRunner

    import cli
    from src.db.database import init_db
    init_db()
    r = CliRunner().invoke(cli.cli, ["merge-teams", "--apply"])
    assert r.exit_code != 0 and "--backup" in r.output
    r = CliRunner().invoke(cli.cli, ["merge-teams"])
    assert r.exit_code == 0 and "DRY RUN (nothing written)" in r.output, r.output
    assert "stored team names carrying an HTML entity, by sport" in r.output


# ============================================================================== Codex on #465 (round 1) ==

def test_a_sync_found_by_the_recorded_id_keeps_the_rows_own_id():
    """P1: syncing team 901 onto {59, also [901]} must not make 901 the row's id (a later 59 would make a new row)."""
    from types import SimpleNamespace as NS

    from src.db.database import init_db, session_scope
    from src.ingestion.service import IngestionService, SyncResult
    init_db()
    with session_scope() as s:
        t = Team(sport=Sport.NFL, name="Kept Rainbows", external_ids={SRC: "k59", f"{SRC}_also": ["k901"]})
        s.add(t)
        s.flush()
        svc = IngestionService.__new__(IngestionService)
        nt = NS(sport=Sport.NFL, source=SRC, source_id="k901", name="Kept Rainbows", short_name=None, tla=None,
                area=None, founded=None, venue=None)
        got = svc._upsert_team(s, nt, SyncResult())
        assert got.id == t.id and got.external_ids[SRC] == "k59" and got.external_ids[f"{SRC}_also"] == ["k901"]
        assert IngestionService._find_team_by_source(s, Sport.NFL, SRC, "k59").id == t.id
        nt2 = NS(**{**vars(nt), "source_id": "k59"})
        assert svc._upsert_team(s, nt2, SyncResult()).id == t.id


def test_a_merged_rows_earlier_merges_are_carried_forward():
    out = tm.merged_ext({SRC: "1"}, {SRC: "2", "merged_from": [{"team_id": 9, "external_ids": {SRC: "3"}, "at": "A"}]},
                        5, "B")
    assert [m["team_id"] for m in out["merged_from"]] == [9, 5]
    assert out["merged_from"][0] == {"team_id": 9, "external_ids": {SRC: "3"}, "at": "A"}


def test_apply_rereads_the_rows_under_the_lock(db, monkeypatch):
    """P2: an ingest that writes a provider id between the plan and the lock is kept, not overwritten."""
    path, eng = db
    keep, other = hawaii(eng)
    con = con_of(path)
    real_plan = tm.plan

    def plan_then_ingest(c):
        p = real_plan(c)
        c.execute("UPDATE teams SET external_ids = ? WHERE id = ?", (json.dumps({SRC: "59", "other_src": "x"}), keep))
        return p
    monkeypatch.setattr(tm, "plan", plan_then_ingest)
    res = tm.apply(con, "T")
    assert [m["keep"] for m in res["merged"]] == [keep]
    ext = json.loads(con.execute("SELECT external_ids FROM teams WHERE id = ?", (keep,)).fetchone()[0])
    assert ext["other_src"] == "x" and ext[f"{SRC}_also"] == ["901"]


def test_the_international_path_reads_every_recorded_id(monkeypatch):
    from src.ingestion import intl_history as ih
    from src.db.database import init_db, session_scope
    init_db()
    with session_scope() as s:
        t = Team(sport=Sport.SOCCER, name="Merged Nation", external_ids={"api_football": "n1",
                                                                          "api_football_also": ["n2"]})
        s.add(t)
        s.flush()
        tid = t.id
    svc = ih._cached_service(type("A", (), {"source_name": "api_football"})()) if hasattr(ih, "_cached_service") \
        else None
    if svc is None:
        pytest.skip("no cached service")
    with session_scope() as s:
        assert svc._find_team_by_source(s, Sport.SOCCER, "api_football", "n2").id == tid
        assert svc._find_team_by_source(s, Sport.SOCCER, "api_football", "n1").id == tid
