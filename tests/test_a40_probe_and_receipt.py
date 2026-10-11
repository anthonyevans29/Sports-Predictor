"""Addendum 40 (ARCHITECT 2026-10-11): the item-4 PROBE (#432, does the provider answer a position by player id?)
and the item-7 RECEIPT (#426, Hawai'i under two provider team ids). Both read-only; the provider is faked; the
database is the throwaway test file."""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Injury, Match, MatchStatus, Sport, Team
import scripts.ncaa_hawaii_receipt as hr
import scripts.nfl_injury_position_probe as pp


def _db() -> Path:
    return Path(os.environ["DATABASE_URL"].replace("sqlite:///", ""))


@pytest.fixture(scope="module")
def world():
    init_db()
    with session_scope() as s:
        nfl = Competition(sport=Sport.NFL, code="A40NFL", name="A40 NFL", area="US", type="LEAGUE")
        ncaa = Competition(sport=Sport.NFL, code="A40NCAA", name="A40 NCAA", area="US", type="LEAGUE")
        s.add_all([nfl, ncaa])
        bal = Team(sport=Sport.NFL, name="A40 Baltimore", external_ids={"api_american_football": "5"})
        no = Team(sport=Sport.NFL, name="A40 New Orleans", external_ids={})
        haw = Team(sport=Sport.NFL, name="A40 Hawai'i", external_ids={"api_american_football": "901"})
        haw2 = Team(sport=Sport.NFL, name="A40 Hawai&#x27;i", external_ids={"api_american_football": "59"})
        wyo = Team(sport=Sport.NFL, name="A40 Wyoming", external_ids={"api_american_football": "77"})
        s.add_all([bal, no, haw, haw2, wyo])
        s.flush()
        s.add(Match(sport=Sport.NFL, competition_id=nfl.id, season="2026", utc_date=datetime(2091, 10, 11, 23, 45),
                    status=MatchStatus.SCHEDULED, home_team_id=no.id, away_team_id=bal.id))
        g = Match(sport=Sport.NFL, competition_id=ncaa.id, season="2026", utc_date=datetime(2091, 9, 6, 2, 0),
                  status=MatchStatus.FINISHED, home_team_id=wyo.id, away_team_id=haw.id, external_ids={
                      "api_american_football": "4001"})
        s.add(g)
        for name, pos, tid in (("Skylar Thompson", None, bal.id), ("Gone Player", "", bal.id),
                               ("Known Back", "RB", bal.id), ("Derek Carr", None, no.id)):
            s.add(Injury(team_id=tid, player_name=name, player_position=pos, source="api_american_football"))
        s.flush()
        return {"bal": bal.id, "no": no.id, "haw": haw.id, "haw2": haw2.id, "game": g.id}


def test_the_probe_asks_by_the_feeds_id_and_says_what_the_provider_answered(world, capsys):
    con, form = pp.open_read(_db())
    items = pp.unresolved(con, "A40", competition="A40NFL")
    con.close()
    assert form == "mode=ro URI"
    assert [(x["team"], x["player_name"]) for x in items] == [
        ("A40 Baltimore", "Gone Player"), ("A40 Baltimore", "Skylar Thompson"), ("A40 New Orleans", "Derek Carr")]
    calls = []

    def fetch(path, params):
        calls.append((path, params))
        if path == "injuries":
            return {"response": [{"player": {"id": 11, "name": "Skylar Thompson"}}]}
        return {"results": 1, "response": [{"id": 11, "name": "Skylar Thompson", "position": "QB", "group": "Offense"}]}
    out = []
    res = pp.probe(items, "KEY", fetch=fetch, echo=out.append)
    assert calls == [("injuries", {"team": "5"}), ("players", {"id": 11})]                 # GET only, by id
    v = {r["player_name"]: r["verdict"] for r in res["results"]}
    assert v == {"Skylar Thompson": "answers a position", "Gone Player": "not in the feed now (no id)",
                 "Derek Carr": "no provider team id"}
    assert res["calls"] == 2 and not any("KEY" in o for o in out)                          # the key never printed


def test_the_receipt_lists_our_hawaii_teams_the_games_and_the_provider_answers(world):
    con, form = hr.open_read(_db())
    teams, games = hr.our_teams(con), hr.the_games(con, [world["game"], 999999])
    con.close()
    teams = [t for t in teams if t["name"].startswith("A40 ")]                          # the shared test file
    assert [(t["id"], t["name"], t["external_ids"]["api_american_football"]) for t in teams] == [
        (world["haw"], "A40 Hawai'i", "901"), (world["haw2"], "A40 Hawai&#x27;i", "59")]
    assert teams[0]["games"] == 1 and teams[0]["by_comp_season"] == [["A40NCAA", "2026", 1]] and teams[1]["games"] == 0
    g, missing = games
    assert g["away"] == {"id": world["haw"], "name": "A40 Hawai'i", "source_id": "901"} and missing == {"id": 999999,
                                                                                                    "stored": False}
    asked = []

    def fetch(path, params):
        asked.append((path, params))
        return {"results": 1, "response": [{"id": params["id"], "name": "Hawaii Rainbow Warriors"}]}
    provider = {pid: hr.get_json("teams", {"id": pid}, "KEY", fetch) for pid in hr.PROVIDER_TEAMS}
    out = []
    hr.report(teams, games, provider, echo=out.append)
    assert asked == [("teams", {"id": 59}), ("teams", {"id": 901})]
    last = json.loads(out[-1].split(" ", 1)[1])
    assert last["source_ids"] == ["59", "901"] and last["provider_asked"] == [59, 901] and last["games_stored"] == 1


@pytest.mark.parametrize("mod,table", [(pp, "injuries"), (hr, "teams")])
def test_a_copy_that_refuses_mode_ro_opens_query_only_and_a_write_fails(tmp_path, monkeypatch, mod, table):
    f = tmp_path / "copy.db"
    con = sqlite3.connect(f)
    con.execute(f"CREATE TABLE {table} (id INTEGER)")
    con.commit()
    con.close()
    real = sqlite3.connect

    def refuse_uri(path, *a, **k):
        if k.get("uri"):
            raise sqlite3.OperationalError("unable to open database file")
        return real(path, *a, **k)
    monkeypatch.setattr(mod.sqlite3, "connect", refuse_uri)
    c, form = mod.open_read(f)
    assert form == "plain path with PRAGMA query_only = ON (mode=ro refused)"
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        c.execute(f"INSERT INTO {table} VALUES (1)")
    c.close()


def test_codex_provider_errors_limit_lines_and_whole_objects(world):
    """Codex on #436: an errors envelope is a failed read (never "not in the feed"); a player left out by --limit
    has its own console line; a player object is printed whole."""
    con, _ = pp.open_read(_db())
    items = pp.unresolved(con, "A40", competition="A40NFL")
    con.close()
    out = []
    res = pp.probe(items, "KEY", fetch=lambda path, params: {"errors": {"requests": "limit reached"}, "response": []},
                   echo=out.append)
    v = {r["player_name"]: r["verdict"] for r in res["results"]}
    assert v["Skylar Thompson"] == v["Gone Player"] == "provider error (/injuries)"
    big = {"id": 11, "name": "Skylar Thompson", "position": "QB", "notes": "x" * 600}

    def fetch(path, params):
        if path == "injuries":
            return {"response": [{"player": {"id": 11, "name": "Skylar Thompson"}},
                                 {"player": {"id": 12, "name": "Gone Player"}}]}
        return {"results": 1, "response": [big]}
    out = []
    res = pp.probe(items, "KEY", limit=1, fetch=fetch, echo=out.append)
    assert any(o.strip() == json.dumps(big, sort_keys=True) for o in out)                # never cut
    assert any(o.endswith("not asked (--limit 1)") for o in out)


def test_codex_out_never_aliases_the_database_or_its_sidecars(tmp_path):
    db = tmp_path / "live.db"
    db.write_bytes(b"x")
    hard = tmp_path / "hard.jsonl"
    os.link(db, hard)
    for bad in (db, Path(str(db) + "-wal"), hard, pp.ROOT / "data" / "p.jsonl"):
        assert pp.out_refusal(str(bad), db), bad
    assert pp.out_refusal(str(tmp_path / "probe.jsonl"), db) is None
    assert pp.main(["--db", str(db), "--out", str(Path(str(db) + "-shm"))]) == 2 and db.read_bytes() == b"x"
