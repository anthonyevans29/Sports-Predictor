"""The certification receipt's NCAAMB phases (scripts/nba_certification_receipt.py --competition NCAAMB; ARCHITECT
2026-11-12, addendum 352 items 2-3: "(iv) HISTORY: the 2026-27 season ONLY"; "(v) TEAM IDS: the receipt's check is
enough AND it is a stop, in both phases: zero NCAAMB team ids equal to a stored NBA team id, printed as a count with
the ids if any; a non-zero count stops the load and comes to me").

SYNTHETIC payloads only (tests/test_basketball_wiring.py's shapes); the provider is never called; the stored phase
reads a copy built under tmp_path, never data/."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from scripts import nba_certification_receipt as R
from tests.test_basketball_wiring import T0, FakeProvider, adapter_with, game, league, team

NBA_SEASONS = ("2026-2027", "2025-2026", "2024-2025")


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("API_BASKETBALL_KEY", "synthetic-basketball")      # a synthetic value; nothing is called


class LeagueFake(FakeProvider):
    """FakeProvider's answers, /teams and /games keyed by (league, served season): the NBA (12) and NCAA (116)."""

    def __init__(self, teams, games, leagues=None, fail_nba_teams=None):
        super().__init__(leagues=leagues if leagues is not None else [
            league(12, "NBA", NBA_SEASONS), league(116, "NCAA", ("2026-2027", "2025-2026"))])
        self.by_league_teams, self.by_league_games, self.fail_nba_teams = teams, games, fail_nba_teams

    def __call__(self, path, params=None):
        p = dict(params or {})
        if path in ("teams", "games"):
            self.calls.append((path, p))
            if self.adapter is not None:
                self.adapter._requests_remaining = self.remaining - len(self.calls)
                self.adapter.calls += 1
            if path == "teams" and p.get("league") == 12 and p.get("season") == self.fail_nba_teams:
                raise RuntimeError("synthetic: the NBA's /teams read failed")
            if p.get("league") == 116 and getattr(self, "fail_ncaa", False):
                raise RuntimeError("synthetic: league 116's read failed")
            src = self.by_league_teams if path == "teams" else self.by_league_games
            return {"errors": [], "response": src.get((p.get("league"), p.get("season")), [])}
        return super().__call__(path, params)


def ncaa_game(gid, home, away, short="NS", long="Not Started"):
    g = game(gid, short, long, home, away, T0)
    g["league"] = {"id": 116, "name": "NCAA", "type": "League", "season": "2026-2027", "logo": "synthetic"}
    return g


def fake(ncaa_ids=(2001, 2002, 2003), nba_ids=(101, 102, 103), **kw):
    teams = {(116, "2026-2027"): [team(i) for i in ncaa_ids]}
    teams.update({(12, s): [team(i) for i in nba_ids] for s in NBA_SEASONS})
    games = {(116, "2026-2027"): [ncaa_game(1, ncaa_ids[0], ncaa_ids[1]), ncaa_game(2, ncaa_ids[1], ncaa_ids[2])]}
    return LeagueFake(teams, games, **kw)


def run(capsys, argv, f):
    code = R.main(list(argv), adapter=adapter_with(f))
    out = capsys.readouterr().out
    return code, out, json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])


def test_the_served_phase_reads_league_116_and_prints_a_zero_collision_count(capsys):
    """The clean served run: NCAAMB 2026 = provider 2026-2027 read on league 116 ("NCAA"), then the stop's count, 0,
    against the NBA's served /teams for the three seasons the NBA stores. Exit 0; the tail names NCAAMB."""
    f = fake()
    code, out, tail = run(capsys, ["--competition", "NCAAMB"], f)
    assert code == R.OK, out
    assert out.startswith("NCAAMB DATA CERTIFICATION RECEIPT · SERVED")
    assert "/leagues: league 116 'NCAA'" in out and '\nNCAAMB 2026 = provider "2026-2027"' in out
    assert ("TEAM IDS vs THE NBA (352 item 3(v), a stop): 3 NCAAMB team ids served (/teams 3 · /games sides not on "
            "/teams 0) · 3 NBA team ids served for 2026, 2025, 2024 · shared: 0") in out
    assert "STOP" not in out
    assert out.strip().splitlines()[-1].startswith("NCAAMB-CERTIFICATION-RECEIPT ")
    assert tail["exit"] == R.OK and tail["nba_collision"] == {"read": True, "ncaamb_ids": 3, "nba_ids": 3,
                                                             "shared": []}
    leagues = {(p.get("league"), p.get("season")) for path, p in f.calls if path == "teams"}
    assert leagues == {(116, "2026-2027"), *((12, s) for s in NBA_SEASONS)}
    assert not [p for path, p in f.calls if path == "games" and p.get("league") == 12]   # the NBA's games: never read


def test_a_shared_team_id_is_a_stop_with_the_ids_printed(capsys):
    """352 item 3(v): "a non-zero count stops the load and comes to me". One NCAAMB id equal to an NBA id -> exit 3,
    the count and the id (with the NBA's name for it) printed."""
    code, out, tail = run(capsys, ["--competition", "NCAAMB"], fake(ncaa_ids=(2001, 102, 2003)))
    assert code == R.STOP == 3, out
    assert "· shared: 1: 102 (NBA 'Synthetic Team 102')" in out
    assert "STOP: an NCAAMB team id equals an NBA team id; the load stops here and comes to the architect" in out
    assert tail["exit"] == R.STOP and tail["nba_collision"]["shared"] == ["102"]


def test_a_games_side_id_off_teams_that_equals_an_nba_id_is_a_stop(capsys):
    """The pre-PR review (P1): sync-matches looks a side up by sport, source and provider id with no competition
    scope (service._find_team_by_source, 352 item 3(v): not re-scoped), so a /games side that league 116's /teams
    does not list but that carries a stored NBA id would be LINKED to the NBA's row, not skipped. The served stop
    reads the /games side ids as well as the /teams ids; the INTEGRITY line no longer says such a side is skipped."""
    f = fake()
    f.by_league_games[(116, "2026-2027")].append(ncaa_game(3, 2001, 102))     # 102: an NBA id, not on 116's /teams
    code, out, tail = run(capsys, ["--competition", "NCAAMB"], f)
    assert code == R.STOP, out
    assert ("TEAM IDS vs THE NBA (352 item 3(v), a stop): 4 NCAAMB team ids served (/teams 3 · /games sides not on "
            "/teams 1) · 3 NBA team ids served for 2026, 2025, 2024 · shared: 1: 102 (NBA 'Synthetic Team 102')") in out
    assert "sync-matches would skip it" not in out
    assert ("a side not in this season's /teams (sync-matches links it to any stored basketball team carrying its "
            "provider id, else skips it): 1: 3") in out
    assert tail["nba_collision"]["shared"] == ["102"] and tail["nba_collision"]["ncaamb_ids"] == 4

def test_an_nba_read_that_fails_is_a_stop_never_a_pass(capsys):
    """The check is read, never assumed (#902): the NBA side unread is a stop, not a zero."""
    code, out, tail = run(capsys, ["--competition", "NCAAMB"], fake(fail_nba_teams="2025-2026"))
    assert code == R.STOP, out
    assert "STOP: the NBA's /teams for 2025 could not be read" in out and "shared: 0" not in out
    assert tail["nba_collision"] == {"read": False, "season": "2025"}


@pytest.mark.parametrize("served", [[], None, {"not": "a list"}, [{"team": {"name": "no id"}}, "junk"]],
                         ids=["empty", "null", "object", "no-id"])
def test_an_nba_teams_read_that_answers_no_ids_is_a_stop_never_a_pass(capsys, served):
    """Codex on #957 (P2): an NBA /teams answer of 200 with an empty, null or non-list response (or one with no
    readable id) read as "no NBA teams" and the stop could print shared: 0 over an NBA side it never had. An answer
    that yields no NBA team id is a STOP, as a failed read is (the check is read, never assumed: #902)."""
    f = fake()
    f.by_league_teams[(12, "2025-2026")] = served
    code, out, tail = run(capsys, ["--competition", "NCAAMB"], f)
    assert code == R.STOP, out
    assert "STOP: the NBA's /teams for 2025 answered no team id" in out and "shared: 0" not in out
    assert tail["nba_collision"] == {"read": False, "season": "2025"}

@pytest.mark.parametrize("empty", ["teams", "games", "both"])
def test_a_season_that_answers_no_teams_or_no_games_certifies_nothing(capsys, empty):
    """Codex on #957, round 2 (P2): league 116 answering 200 with an empty /teams or /games read as a season read, so
    the stop compared what little it had and could exit 0 over a load that would store nothing. A season with no
    team or no game is FAILED (1): nothing to certify; with no other season read, the stop is NOT RUN."""
    f = fake()
    if empty in ("teams", "both"):
        f.by_league_teams[(116, "2026-2027")] = []
    if empty in ("games", "both"):
        f.by_league_games[(116, "2026-2027")] = []
    code, out, tail = run(capsys, ["--competition", "NCAAMB"], f)
    assert code == R.FAILED, out
    assert "FAILED: the provider answered" in out and "nothing to certify" in out
    assert "NOT RUN: no NCAAMB season was read" in out and "shared: 0" not in out
    assert tail["seasons"]["2026"]["empty"] is True and tail["nba_collision"]["read"] is False
    assert not [p for path, p in f.calls if p.get("league") == 12]

def test_no_ncaamb_season_read_runs_no_nba_read_and_keeps_the_seasons_exit(capsys):
    """The second pre-PR review (P2): with no NCAAMB season read (league 116 serving no 2026 season, or its /teams
    failing), the stop compared nothing against three NBA reads and printed a clean "shared: 0" (and an NBA read
    failing too turned a FAILED into a STOP). Now the check is NOT RUN: no league-12 call, its line says why, the
    tail records it unread, and the exit is the season's own (REFUSED 2, FAILED 1)."""
    f = fake(leagues=[league(12, "NBA", NBA_SEASONS), league(116, "NCAA", ("2025-2026",))])
    code, out, tail = run(capsys, ["--competition", "NCAAMB"], f)
    assert code == R.REFUSED, out
    assert "TEAM IDS vs THE NBA (352 item 3(v), a stop): NOT RUN: no NCAAMB season was read" in out
    assert "shared: 0" not in out and not [p for path, p in f.calls if p.get("league") == 12]
    assert tail["nba_collision"] == {"read": False, "reason": "no NCAAMB season read"}
    f = fake(fail_nba_teams="2026-2027")
    f.by_league_teams.pop((116, "2026-2027"))
    f.fail_ncaa = True
    code, out, tail = run(capsys, ["--competition", "NCAAMB"], f)
    assert code == R.FAILED, out
    assert "NOT RUN: no NCAAMB season was read" in out and "STOP" not in out


def test_the_stop_compares_ids_as_the_sync_does_as_strings(capsys):
    """The sync keys a side by str(provider id) (api_basketball; service._find_team_by_source), so an id served as
    102 in one listing and "102" in another is one team to the sync, and one shared id to the stop."""
    f = fake()
    g = ncaa_game(3, 2001, "102")
    f.by_league_games[(116, "2026-2027")].append(g)
    code, out, tail = run(capsys, ["--competition", "NCAAMB"], f)
    assert code == R.STOP, out
    assert "shared: 1: 102 (NBA 'Synthetic Team 102')" in out and tail["nba_collision"]["shared"] == ["102"]

def test_a_season_other_than_2026_is_refused_before_any_call(capsys):
    """352 item 3(iv): "HISTORY: the 2026-27 season ONLY". --season 2025 (alone or beside 2026) is refused, nothing
    read; the NBA keeps its three seasons."""
    for argv in (["--competition", "NCAAMB", "--season", "2025"],
                 ["--competition", "NCAAMB", "--season", "2026", "--season", "2025"]):
        f = fake()
        code, out, tail = run(capsys, argv, f)
        assert code == R.REFUSED, out
        assert "REFUSED: NCAAMB season(s) 2025: the 2026 season only (addendum 352 item 3(iv)" in out
        assert f.calls == [] and tail["refused"] == "season not ruled"
    assert R.SEASONS_BY_COMPETITION["NBA"] == ("2026", "2025", "2024")


def test_ncaa_is_never_a_competition_the_receipt_takes(capsys):
    """NCAA is football (261 item 1(c): "competition code NCAAMB (never "NCAA", which is football)")."""
    with pytest.raises(SystemExit):
        R.main(["--competition", "NCAA"], adapter=adapter_with(fake()))
    capsys.readouterr()


# ---- the stored phase ------------------------------------------------------------------------------------------------

def _copy(tmp_path: Path, shared: bool) -> Path:
    """A stored NBA season and a stored NCAAMB one in a SQLite file under tmp_path (never data/). With `shared`, one
    NCAAMB game's home side is an NBA team row (what a shared provider id would have done to the sync)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from src.db.schema import Base, Competition, CompetitionTeam, Match, MatchStatus, Sport, Team
    path = tmp_path / "copy.db"
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        nba = Competition(sport=Sport.BASKETBALL, code="NBA", name="x", area="x", type="LEAGUE")
        col = Competition(sport=Sport.BASKETBALL, code="NCAAMB", name="y", area="y", type="LEAGUE")
        pros = [Team(sport=Sport.BASKETBALL, name=f"Synthetic Pro {i}", external_ids={"api_basketball": str(i)})
                for i in (101, 102)]
        colleges = [Team(sport=Sport.BASKETBALL, name=f"Synthetic College {i}",
                         external_ids={"api_basketball": str(i)}) for i in (2001, 2002)]
        s.add_all([nba, col, *pros, *colleges])
        s.flush()
        s.add_all([CompetitionTeam(competition_id=nba.id, team_id=t.id, season="2026") for t in pros])
        s.add_all([CompetitionTeam(competition_id=col.id, team_id=t.id, season="2026") for t in colleges])
        k = datetime(2026, 11, 16, 5, 0)
        s.add(Match(sport=Sport.BASKETBALL, competition_id=nba.id, season="2026", utc_date=k,
                    status=MatchStatus.SCHEDULED, status_raw="NS", home_team_id=pros[0].id, away_team_id=pros[1].id,
                    external_ids={"api_basketball": "901"}))
        s.add(Match(sport=Sport.BASKETBALL, competition_id=col.id, season="2026", utc_date=k,
                    status=MatchStatus.SCHEDULED, status_raw="NS",
                    home_team_id=(pros[0] if shared else colleges[0]).id, away_team_id=colleges[1].id,
                    external_ids={"api_basketball": "951"}))
        s.commit()
        pro_id = pros[0].id
    eng.dispose()
    return path, pro_id


def test_the_stored_phase_prints_a_zero_collision_count_on_a_clean_copy(tmp_path, capsys):
    path, _ = _copy(tmp_path, shared=False)
    code = R.main(["--competition", "NCAAMB", "--db", str(path)])
    out = capsys.readouterr().out
    assert code == R.OK, out
    assert "NCAAMB DATA CERTIFICATION RECEIPT · STORED" in out and "NCAAMB 2026 (stored): 1 rows · teams linked 2" in out
    assert "TEAM ROWS vs THE NBA (352 item 3(v), a stop): NCAAMB 2 team rows · NBA 2 · shared: 0" in out
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert tail["phase"] == "stored" and tail["nba_collision"] == {"ncaamb_rows": 2, "nba_rows": 2, "shared": []}


def test_an_ncaamb_game_on_an_nba_team_row_is_a_stop_on_the_copy(tmp_path, capsys):
    path, pro_id = _copy(tmp_path, shared=True)
    code = R.main(["--competition", "NCAAMB", "--db", str(path)])
    out = capsys.readouterr().out
    assert code == R.STOP, out
    assert f"shared: 1: team {pro_id} ('Synthetic Pro 101')" in out
    assert "STOP: an NCAAMB game is linked to an NBA team row; this comes to the architect" in out
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert tail["exit"] == R.STOP and tail["nba_collision"]["shared"] == [pro_id]


def test_the_nba_stored_phase_runs_no_collision_check(tmp_path, capsys):
    path, _ = _copy(tmp_path, shared=True)
    code = R.main(["--db", str(path)])
    out = capsys.readouterr().out
    assert code == R.OK, out
    assert "TEAM ROWS vs THE NBA" not in out and out.strip().splitlines()[-1].startswith("NBA-CERTIFICATION-RECEIPT ")
