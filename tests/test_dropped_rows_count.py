"""COUNT FIRST (ARCHITECT 2026-11-24, addendum 497 Q7 and item 2 step (0); addendum 502 Q7).

497 Q7, verbatim: "YES, COUNT FIRST. The rows an adapter drops before counting get a printed count with their causes in
the command's own output; no exit changes with it. It is the first PR." 502 Q7, verbatim: "YES. sync-odds' uncounted
drops and sync-odds-football's skips get a printed count first, with 497's step (0); no exit changes with it."

(A) the adapters' listings dropped before counting (sync-matches, sync-teams): one shared line, base.dropped_line, the
api_basketball line byte for byte; (B) sync-odds: SyncResult.odds_not_read and odds_not_read_line; (C)
sync-odds-football: the returned dict's not_priced and football_not_priced_line; (D) no new line can be read as one of
sp_run's count lines, a laptop-routine echo, a failure or an exception.

Every payload is SYNTHETIC; no provider is called (each adapter's _get, or its odds read, is replaced). Throwaway DB
only (tests/conftest.py); every row a test creates is removed after it."""
from __future__ import annotations

import io
import itertools
import re
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner

from src.adapters import base
from src.adapters.api_american_football import APIAmericanFootballAdapter, RateLimited
from src.adapters.api_baseball import APIBaseballClient
from src.adapters.api_basketball import APIBasketballAdapter
from src.adapters.api_hockey import APIHockeyAdapter
from src.adapters.mlb_stats_api import MLBStatsAPIAdapter
from src.adapters.normalized import NormalizedOdds
from src.db.database import init_db, session_scope
from src.db.schema import (Competition, CompetitionTeam, Match, MatchStatus, Odds, OddsSnapshot, Sport, Team)
from src.ingestion import service as svc
from src.ingestion.service import IngestionService, football_not_priced_line, odds_not_read_line
from src.timeutil import utc_now_naive

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import laptop_routine  # noqa: E402
import sp_run  # noqa: E402

_seq = itertools.count(1)
T0 = int(datetime(2026, 11, 5, 0, 30, tzinfo=timezone.utc).timestamp())


def _stub_get(adapter, data):
    adapter._get = lambda path, params=None: data
    return adapter


def _out(capsys):
    return capsys.readouterr().out


# ------------------------------------------------------------------------------------- (A) the shared line itself

def _basketball_line_before(what, dropped):
    """api_basketball._report_dropped's text as it stood at 3b63269b, copied, the reference for byte identity."""
    parts = " · ".join(f"{why} {len(ids)}" for why, ids in dropped.items())
    ids = [str(i) for v in dropped.values() for i in v if i is not None]
    return (f"api_basketball /{what}: {sum(len(v) for v in dropped.values())} listing(s) not read ({parts})"
            + (f": {', '.join(ids)}" if ids else ""))


@pytest.mark.parametrize("what,dropped", [
    ("games", {"not an object": [None], "no id": [None], "no team id": [22], "no readable kickoff": [13, 14]}),
    ("games", {"no readable kickoff": [13, 14]}),
    ("teams", {"not an object": [None]}),
    ("teams", {"no id or name": [None, 7]}),
])
def test_the_basketball_line_is_byte_identical_through_the_shared_helper(capsys, what, dropped):
    a = APIBasketballAdapter.__new__(APIBasketballAdapter)
    a._report_dropped(what, dropped)
    assert _out(capsys) == _basketball_line_before(what, dropped) + "\n"
    assert a.last_dropped is dropped
    assert base.dropped_line("api_basketball", what, dropped) == _basketball_line_before(what, dropped)


def test_nothing_dropped_prints_nothing_and_leaves_last_dropped_empty(capsys):
    a = APIBasketballAdapter.__new__(APIBasketballAdapter)
    a._report_dropped("games", {})
    assert _out(capsys) == "" and a.last_dropped == {}
    assert base.dropped_line("x", "games", {}) is None


# ------------------------------------------------------------------------------------- (A) mlb_stats_api /schedule

def _mlb_game(pk, home=1, away=2, date="2026-04-01T23:05:00Z"):
    return {"gamePk": pk, "gameDate": date, "season": "2026", "gameType": "R",
            "status": {"codedGameState": "S"},
            "teams": {"home": {"team": {"id": home}}, "away": {"team": {"id": away}}}}


def test_mlb_stats_api_counts_each_cause_with_its_game_pk(capsys):
    good = _mlb_game(900)
    no_team = _mlb_game(901, away=None)
    bad_date = _mlb_game(902, date="not a date")
    no_date = _mlb_game(903)
    no_date.pop("gameDate")
    no_pk = _mlb_game(None, home=0)
    no_pk.pop("gamePk")
    data = {"dates": [{"games": [good, no_team]}, {"games": [bad_date, no_date, no_pk]}]}
    a = _stub_get(MLBStatsAPIAdapter(), data)
    got = a.list_matches("MLB", "2026")
    assert [m.source_id for m in got] == ["900"]
    assert got[0] == a._parse_game(good, "MLB")                        # the good row exactly as parsed before
    assert a.last_dropped == {"no team id": [901, None], "unreadable date": [902, 903]}
    assert _out(capsys) == ("mlb_stats_api /schedule: 4 listing(s) not read (no team id 2 · unreadable date 2): "
                            "901, 902, 903\n")


def test_mlb_stats_api_a_clean_answer_prints_nothing(capsys):
    a = _stub_get(MLBStatsAPIAdapter(), {"dates": [{"games": [_mlb_game(900)]}]})
    a.last_dropped = {"stale": [1]}
    assert len(a.list_matches("MLB", "2026")) == 1
    assert a.last_dropped == {} and _out(capsys) == ""


# ------------------------------------------------------------------------------------- (A) api_hockey

def _hockey_game(gid, home=10, away=11, ts=T0, date=None):
    return {"game": {"id": gid, "date": {"timestamp": ts, "date": date}, "status": {"short": "NS"}},
            "teams": {"home": {"id": home}, "away": {"id": away}}, "scores": {"home": None, "away": None}}


def test_api_hockey_games_counts_each_cause(capsys):
    games = [_hockey_game(500), _hockey_game(501, ts=None, date=None), _hockey_game(None),
             _hockey_game(503, away=None)]
    a = _stub_get(APIHockeyAdapter(), {"response": games})
    got = a.list_matches("NHL", "2026")
    assert [m.source_id for m in got] == ["500"]
    assert got[0].utc_date == datetime(2026, 11, 5, 0, 30)
    assert a.last_dropped == {"no kickoff date": [501], "no game id": [None], "no team id": [503]}
    assert _out(capsys) == ("api_hockey /games: 3 listing(s) not read (no kickoff date 1 · no game id 1 · "
                            "no team id 1): 501, 503\n")
    a2 = _stub_get(APIHockeyAdapter(), {"response": [_hockey_game(500)]})
    a2.list_matches("NHL", "2026")
    assert a2.last_dropped == {} and _out(capsys) == ""


def test_api_hockey_teams_counts_each_cause(capsys):
    teams = [{"id": 1, "name": "Synthetic A"}, {"team": {"id": None, "name": "Synthetic B"}}, {"id": 3, "name": ""}]
    a = _stub_get(APIHockeyAdapter(), {"response": teams})
    assert [t.source_id for t in a.list_teams("NHL", "2026")] == ["1"]
    assert a.last_dropped == {"no team id": [None], "no team name": [3]}
    assert _out(capsys) == "api_hockey /teams: 2 listing(s) not read (no team id 1 · no team name 1): 3\n"
    a2 = _stub_get(APIHockeyAdapter(), {"response": teams[:1]})
    a2.list_teams("NHL", "2026")
    assert a2.last_dropped == {} and _out(capsys) == ""


# ------------------------------------------------------------------------------------- (A) api_american_football

def _af_game(gid, home=20, away=21, ts=T0, date=None, home_name="Synthetic Home", week="Week 3"):
    return {"game": {"id": gid, "date": {"timestamp": ts, "date": date}, "status": {"short": "NS"}, "week": week,
                     "stage": "Regular Season"},
            "teams": {"home": {"id": home, "name": home_name}, "away": {"id": away, "name": "Synthetic Away"}},
            "scores": {"home": {"total": None}, "away": {"total": None}}}


def test_api_american_football_games_counts_each_cause_and_keeps_the_exhibition_line(capsys):
    games = [_af_game(600), _af_game(601, ts=None), _af_game(None), _af_game(603, home=None),
             _af_game(604, home_name="AFC")]
    a = _stub_get(APIAmericanFootballAdapter(), {"response": games})
    got = a.list_matches("NFL", "2026")
    assert [m.source_id for m in got] == ["600"]
    assert a.last_dropped == {"no kickoff date": [601], "no game id": [None], "no team id": [603],
                              "non-competitive": [604]}
    out = _out(capsys).splitlines()
    assert out == [
        "  excluded non-competitive game: id=604 2026-11-05 'AFC' v 'Synthetic Away' "
        "(week='Week 3', stage='Regular Season'; all-star side 'AFC')",                # the per-row line, as before
        "api_american_football /games: 4 listing(s) not read (no kickoff date 1 · no game id 1 · no team id 1 · "
        "non-competitive 1): 601, 603, 604",
    ]


def test_api_american_football_a_clean_answer_prints_nothing(capsys):
    a = _stub_get(APIAmericanFootballAdapter(), {"response": [_af_game(600)]})
    a.list_matches("NFL", "2026")
    assert a.last_dropped == {} and _out(capsys) == ""


def test_get_game_prints_nothing_new_and_parse_games_keeps_its_output(capsys):
    """_parse_games is shared by get_game (refresh-by-id, dedupe-matches --orphans): the count is list_matches' own."""
    a = _stub_get(APIAmericanFootballAdapter(), {"response": [_af_game(601, ts=None)]})
    assert a.get_game("601", "NFL") == (True, None)
    assert _out(capsys) == "" and a.last_dropped == {}
    rows = {"response": [_af_game(600), _af_game(603, home=None)]}
    assert a._parse_games(rows, "NFL", "2026") == a._parse_games(rows, "NFL", "2026", dropped={})


def test_api_american_football_teams_counts_each_cause(capsys):
    teams = [{"id": 1, "name": "Synthetic A"}, {"id": None, "name": "Synthetic B"}, {"id": 3, "name": ""},
             {"team": {"id": 4, "name": "NFC"}}]
    a = _stub_get(APIAmericanFootballAdapter(), {"response": teams})
    assert [t.source_id for t in a.list_teams("NFL", "2026")] == ["1"]
    assert a.last_dropped == {"no team id": [None], "no team name": [3], "non-competitive": [4]}
    assert _out(capsys).splitlines() == [
        "  excluded non-competitive team: id=4 'NFC' (all-star side 'NFC')",
        "api_american_football /teams: 3 listing(s) not read (no team id 1 · no team name 1 · non-competitive 1): 3, 4",
    ]


# ------------------------------------------------------------------------------------- (A) api_baseball client

def test_api_baseball_teams_counts_each_cause(capsys):
    c = _stub_get(APIBaseballClient("synthetic"), {"response": [{"id": 1, "name": "Synthetic A"},
                                                                {"id": None, "name": "B"}, {"id": 3, "name": None}]})
    assert c.list_teams(season=2026) == [{"id": 1, "name": "Synthetic A", "code": None}]
    assert c.last_dropped == {"no team id": [None], "no team name": [3]}
    assert _out(capsys) == "api_baseball /teams: 2 listing(s) not read (no team id 1 · no team name 1): 3\n"
    c2 = _stub_get(APIBaseballClient("synthetic"), {"response": [{"id": 1, "name": "Synthetic A"}]})
    c2.list_teams(season=2026)
    assert c2.last_dropped == {} and _out(capsys) == ""


def _odds_block(gid, date="2026-11-05T00:30:00+00:00", home="Synthetic H", away="Synthetic A"):
    return {"game": {"id": gid, "date": date, "teams": {"home": {"name": home}, "away": {"name": away}}},
            "bookmakers": [{"name": "bk", "bets": [{"name": "Home/Away", "values": [
                {"value": "Home", "odd": "1.80"}, {"value": "Away", "odd": "2.05"}]}]}]}


def test_api_baseball_odds_reads_record_the_whole_games_they_drop(capsys):
    blocks = [_odds_block(700), _odds_block(None), _odds_block(702, date="bad"), _odds_block(703, date=None),
              _odds_block(704, away="")]
    c = _stub_get(APIBaseballClient("synthetic"), {"response": blocks})
    rows = c.list_odds_window(season=2026)
    assert {r.api_baseball_game_id for r in rows} == {700} and len(rows) == 2
    assert c.last_dropped == {"no game id": [None], "unreadable date": [702, 703], "no team name": [704]}
    assert rows == list(c._parse_game_odds(blocks[0]))                  # the rows are the same with or without it
    assert c.list_odds_for_game(season=2026, game_id=700) == rows      # the per-game read records its own
    assert c.last_dropped == {"no game id": [None], "unreadable date": [702, 703], "no team name": [704]}
    assert _out(capsys) == ""                                           # carried by sync_odds_mlb, not printed here
    c2 = _stub_get(APIBaseballClient("synthetic"), {"response": blocks[:1]})
    c2.list_odds_window(season=2026)
    assert c2.last_dropped == {}


# ------------------------------------------------------------------------------------- (A) the MLB api-sports fallback

def test_the_mlb_fallback_counts_a_provider_game_with_an_unreadable_date(monkeypatch, capsys):
    from src.ingestion import mlb_apisports as fb
    init_db()
    with session_scope() as s:
        if s.query(Competition).filter(Competition.sport == Sport.MLB, Competition.code == "MLB").first() is None:
            s.add(Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA", type="LEAGUE"))
    monkeypatch.setattr(fb, "sync_teams", lambda client, season: {"season": season})
    games = [{"id": 800, "date": "2031-04-01T23:05:00+00:00", "teams": {"home": {"name": "DRC Nowhere A"},
                                                                         "away": {"name": "DRC Nowhere B"}},
              "status": {"short": "NS"}, "scores": {}},
             {"id": 801, "date": "not a date", "teams": {}, "status": {}, "scores": {}},
             {"id": 802, "date": None, "teams": {}, "status": {}, "scores": {}},
             {"id": 803, "date": "2031-09-01T23:05:00+00:00", "teams": {}, "status": {}, "scores": {}}]
    client = NS(_get=lambda path, params=None: {"response": games})
    rec = fb.sync_matches(client, "2031", "2031-04-01", "2031-04-02")     # a season no other test stores
    out = _out(capsys).splitlines()
    assert out == ["api_baseball /games: 2 listing(s) not read (unreadable date 2): 801, 802"]   # 803: scope
    assert rec["provider_games"] == 4 and rec["team_missing"] == 1 and rec["created"] == 0    # the receipt as before


# ------------------------------------------------------------------------------------- (B) the line, pure

def test_odds_not_read_line_and_football_not_priced_line():
    assert odds_not_read_line({}) == "odds_not_read 0"
    assert odds_not_read_line({"no provider id": []}) == "odds_not_read 0"
    assert odds_not_read_line({"no provider id": [3, 4], "not stored": [9]}) == \
        "odds_not_read 3 (no provider id 2: 3, 4 · not stored 1: 9)"
    assert odds_not_read_line({"no game id": [None, None], "started": [5]}) == \
        "odds_not_read 3 (no game id 2 · started 1: 5)"
    assert football_not_priced_line({}) == "football_not_priced 0"
    assert football_not_priced_line({"no rows": [7]}) == "football_not_priced 1 (no rows 1: 7)"
    assert str(svc.SyncResult()) == "created=0 updated=0 skipped=0"     # __str__ unchanged
    assert svc.SyncResult().odds_not_read == {}


# ------------------------------------------------------------------------------------- (B) sync-odds (non-MLB)

FAKE = "fakeodds497"


class FakeOdds:
    source_name = FAKE

    def list_odds(self, source_id):
        ko = utc_now_naive()
        return [NormalizedOdds(match_source_id=source_id, source=FAKE, bookmaker="bk", market="1X2", selection=sel,
                               price_decimal=px, captured_at=ko) for sel, px in (("HOME", 1.5), ("DRAW", 4.0),
                                                                                  ("AWAY", 6.0))]


@pytest.fixture
def made():
    init_db()
    got = {"matches": [], "teams": [], "comps": []}
    yield got
    with session_scope() as s:
        mids = got["matches"]
        if mids:
            for model in (Odds, OddsSnapshot):
                s.query(model).filter(model.match_id.in_(mids)).delete(synchronize_session=False)
            s.query(Match).filter(Match.id.in_(mids)).delete(synchronize_session=False)
        if got["teams"]:
            s.query(CompetitionTeam).filter(CompetitionTeam.team_id.in_(got["teams"])).delete(
                synchronize_session=False)
            s.query(Team).filter(Team.id.in_(got["teams"])).delete(synchronize_session=False)
        if got["comps"]:
            s.query(Competition).filter(Competition.id.in_(got["comps"])).delete(synchronize_session=False)


def _comp(made, code, sport=Sport.SOCCER):
    with session_scope() as s:
        c = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(c)
        s.flush()
        made["comps"].append(c.id)
        return c.id


def _match(made, comp_id, sport=Sport.SOCCER, when=None, status=MatchStatus.SCHEDULED, season="2026", ext=None):
    with session_scope() as s:
        ts = [Team(sport=sport, name=f"DRC {next(_seq)} {utc_now_naive():%H%M%S%f}") for _ in range(2)]
        s.add_all(ts)
        s.flush()
        m = Match(sport=sport, competition_id=comp_id, season=season,
                  utc_date=when or utc_now_naive() + timedelta(days=2), status=status,
                  home_team_id=ts[0].id, away_team_id=ts[1].id, external_ids=ext)
        s.add(m)
        s.flush()
        made["matches"].append(m.id)
        made["teams"] += [t.id for t in ts]
        return m.id


def test_sync_odds_league_mode_counts_a_match_with_no_provider_id_before_the_limit(made):
    cid = _comp(made, "DRC1")
    bare = _match(made, cid, when=utc_now_naive() + timedelta(days=1))          # earliest: the limit would keep it
    priced = _match(made, cid, ext={FAKE: "g1"})
    res = IngestionService(FakeOdds()).sync_odds("DRC1", limit=1)
    assert res.created == 1 and res.odds_not_read == {"no provider id": [bare]}
    assert priced not in sum(res.odds_not_read.values(), [])


def test_sync_odds_match_ids_classifies_every_named_id_and_prints_before_the_summary(made, monkeypatch):
    import cli
    cid, other = _comp(made, "DRC2"), _comp(made, "DRC2X")
    now = utc_now_naive()
    priced = _match(made, cid, ext={FAKE: "g2"})
    no_id = _match(made, cid)
    elsewhere = _match(made, other, ext={FAKE: "g3"})
    off_season = _match(made, cid, season="2025", ext={FAKE: "g4"})
    finished = _match(made, cid, status=MatchStatus.FINISHED, ext={FAKE: "g5"})
    passed = _match(made, cid, when=now - timedelta(hours=3), ext={FAKE: "g6"})
    unnamed_bare = _match(made, cid)                                           # not named: never counted
    missing = 2_000_000_000
    named = [priced, no_id, elsewhere, off_season, finished, passed, missing]
    res = IngestionService(FakeOdds()).sync_odds("DRC2", season="2026", match_ids=set(named))
    assert res.created == 1
    assert res.odds_not_read == {"no provider id": [no_id], "not stored": [missing],
                                 "other competition": [elsewhere], "other season": [off_season],
                                 "not scheduled": [finished], "kickoff passed": [passed]}
    assert unnamed_bare not in sum(res.odds_not_read.values(), [])

    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: FakeOdds())
    out = CliRunner().invoke(cli.cli, ["sync-odds", "--competition", "DRC2", "--season", "2026",
                                       "--match-ids", ",".join(str(i) for i in named)])
    assert out.exit_code == 0, out.output
    lines = [x for x in out.output.splitlines() if x.strip()]
    assert lines[-1].startswith("✓ Odds (DRC2): created=1")               # the summary stays last
    assert lines[-2] == odds_not_read_line(res.odds_not_read)
    assert lines[-2].startswith("odds_not_read 6 (")
    assert lines[-3].startswith("orientation_mismatch_unpriced 0") and lines[-4].startswith("orientation_swapped 0")


def test_sync_odds_match_ids_on_a_competition_not_in_the_db_counts_every_named_id():
    res = IngestionService(FakeOdds()).sync_odds("DRC-NONE", match_ids={7, 3})
    assert res.odds_not_read == {"competition not in the DB": [3, 7]}
    assert odds_not_read_line(res.odds_not_read) == "odds_not_read 2 (competition not in the DB 2: 3, 7)"
    assert IngestionService(FakeOdds()).sync_odds("DRC-NONE").odds_not_read == {}


def test_sync_odds_prints_a_zero_line_when_every_game_is_read(made, monkeypatch):
    import cli
    cid = _comp(made, "DRC3")
    _match(made, cid, ext={FAKE: "g7"})
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: FakeOdds())
    out = CliRunner().invoke(cli.cli, ["sync-odds", "--competition", "DRC3"])
    assert out.exit_code == 0, out.output
    lines = [x for x in out.output.splitlines() if x.strip()]
    assert lines[-2:] == ["odds_not_read 0", "✓ Odds (DRC3): created=1 updated=0 skipped=0"]


# ------------------------------------------------------------------------------------- (B) sync-odds MLB

class FakeBaseball:
    """sync_odds_mlb's client: each read sets last_dropped as the real client does (a fresh dict per read)."""
    requests_remaining = 9

    def __init__(self, window, window_dropped, listing, per_game_dropped):
        self.window, self.window_dropped = window, window_dropped
        self.listing, self.per_game_dropped = listing, per_game_dropped
        self.last_dropped = {}

    def list_odds_window(self, season):
        self.last_dropped = dict(self.window_dropped)
        return self.window

    def list_games_on_date(self, season, date_str):
        return self.listing

    def list_odds_for_game(self, season, game_id):
        self.last_dropped = dict(self.per_game_dropped) if game_id == 7100 else {}
        return []


def test_sync_odds_mlb_counts_the_clients_drops_and_the_started_games(made, monkeypatch):
    import cli
    from src.adapters import api_baseball
    init_db()
    with session_scope() as s:
        comp = s.query(Competition).filter(Competition.sport == Sport.MLB, Competition.code == "MLB").first()
        if comp is None:
            comp = Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        cid = comp.id
    now = utc_now_naive()
    started = _match(made, cid, sport=Sport.MLB, when=now - timedelta(minutes=30))
    rollover = _match(made, cid, sport=Sport.MLB, when=now + timedelta(hours=2))
    with session_scope() as s:
        st, ro = s.get(Match, started), s.get(Match, rollover)
        st_names = (st.home_team.name, st.away_team.name)
        ro_names = (ro.home_team.name, ro.away_team.name)
    window = [NS(api_baseball_game_id=7000, home_team=st_names[0], away_team=st_names[1],
                 commence_time=now - timedelta(minutes=30), market="1X2", selection=sel, bookmaker="bk",
                 price_decimal=px, line=None) for sel, px in (("HOME", 1.8), ("AWAY", 2.05))]
    listing = [{"id": 7100, "date": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "teams": {"home": {"name": ro_names[0]}, "away": {"name": ro_names[1]}}}]
    fake = FakeBaseball(window, {"no game id": [None], "unreadable date": [7001]}, listing,
                        {"no team name": [7101]})
    monkeypatch.setattr(api_baseball.APIBaseballClient, "from_env", classmethod(lambda cls: fake))
    res = IngestionService(NS(source_name="mlb_stats_api")).sync_odds_mlb(season=2026)
    assert res.odds_not_read == {"no game id": [None], "unreadable date": [7001], "started": [started],
                                 "no team name": [7101]}
    assert str(res).startswith("created=0 updated=0")                    # the summary's counts as before

    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: NS(source_name="mlb_stats_api"))
    out = CliRunner().invoke(cli.cli, ["sync-odds", "--competition", "MLB", "--season", "2026"])
    assert out.exit_code == 0, out.output
    lines = [x for x in out.output.splitlines() if x.strip()]
    assert lines[-1].startswith("✓ MLB odds: ")
    assert lines[-2] == (f"odds_not_read 4 (no game id 1 · unreadable date 1: 7001 · started 1: {started} · "
                         f"no team name 1: 7101)")
    assert lines[-3].startswith("NO-BOOK-ODDS (MLB): ")                  # its own line, just above, as before


class FakeBaseballPerGame(FakeBaseball):
    """The same client, whose per-game read for 7100 can also answer rows (the game priced on the retry)."""

    def __init__(self, window, window_dropped, listing, per_game_dropped, per_game_rows=()):
        super().__init__(window, window_dropped, listing, per_game_dropped)
        self.per_game_rows = list(per_game_rows)

    def list_odds_for_game(self, season, game_id):
        super().list_odds_for_game(season, game_id)
        return list(self.per_game_rows) if game_id == 7100 else []


def _mlb_rollover_setup(made):
    """One started MLB game priced from the window (so the fallback is reached) and one game 2h out that the window
    did not price, listed by /games as provider game 7100."""
    init_db()
    with session_scope() as s:
        comp = s.query(Competition).filter(Competition.sport == Sport.MLB, Competition.code == "MLB").first()
        if comp is None:
            comp = Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        cid = comp.id
    now = utc_now_naive()
    started = _match(made, cid, sport=Sport.MLB, when=now - timedelta(minutes=30))
    rollover = _match(made, cid, sport=Sport.MLB, when=now + timedelta(hours=2))
    with session_scope() as s:
        st, ro = s.get(Match, started), s.get(Match, rollover)
        st_names = (st.home_team.name, st.away_team.name)
        ro_names = (ro.home_team.name, ro.away_team.name)

    def rows(gid, names, when):
        return [NS(api_baseball_game_id=gid, home_team=names[0], away_team=names[1], commence_time=when,
                   market="1X2", selection=sel, bookmaker="bk", price_decimal=px, line=None)
                for sel, px in (("HOME", 1.8), ("AWAY", 2.05))]
    window = rows(7000, st_names, now - timedelta(minutes=30))
    listing = [{"id": 7100, "date": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "teams": {"home": {"name": ro_names[0]}, "away": {"name": ro_names[1]}}}]
    return started, rollover, window, listing, rows(7100, ro_names, now + timedelta(hours=2))


def test_sync_odds_mlb_counts_a_game_both_reads_drop_once(made, monkeypatch):
    """The rollover's per-game read is a retry of the same game: a game the window read and its per-game read both
    drop is counted and listed once."""
    from src.adapters import api_baseball
    started, _, window, listing, _ = _mlb_rollover_setup(made)
    fake = FakeBaseballPerGame(window, {"unreadable date": [7100]}, listing, {"unreadable date": [7100]})
    monkeypatch.setattr(api_baseball.APIBaseballClient, "from_env", classmethod(lambda cls: fake))
    res = IngestionService(NS(source_name="mlb_stats_api")).sync_odds_mlb(season=2026)
    assert res.odds_not_read == {"unreadable date": [7100], "started": [started]}
    assert odds_not_read_line(res.odds_not_read) == f"odds_not_read 2 (unreadable date 1: 7100 · started 1: {started})"


def test_sync_odds_mlb_does_not_list_a_game_the_retry_priced(made, monkeypatch):
    """A game the window read dropped and the per-game read then priced was read: it is not listed."""
    from src.adapters import api_baseball
    started, rollover, window, listing, per_game = _mlb_rollover_setup(made)
    fake = FakeBaseballPerGame(window, {"unreadable date": [7100]}, listing, {}, per_game_rows=per_game)
    monkeypatch.setattr(api_baseball.APIBaseballClient, "from_env", classmethod(lambda cls: fake))
    res = IngestionService(NS(source_name="mlb_stats_api")).sync_odds_mlb(season=2026)
    assert res.updated == 1                                               # the rollover game was priced
    with session_scope() as s:
        assert s.query(Odds).filter(Odds.match_id == rollover).count() > 0
    assert res.odds_not_read == {"started": [started]}


@pytest.mark.parametrize("how", ["no_key", "window_failed"])
def test_sync_odds_mlb_prints_no_count_when_no_odds_read_was_made(monkeypatch, how):
    """Law 4: with no key, or a window read that raised, no odds read was made, so no odds_not_read line is printed
    (a 0 there would be a count nobody made); the summary stays last, the exit as before."""
    import cli
    from src.adapters import api_baseball

    class Raising(FakeBaseball):
        def __init__(self):
            super().__init__([], {}, [], {})

        def list_odds_window(self, season):
            raise api_baseball.APIBaseballError("boom")
    client = None if how == "no_key" else Raising()
    monkeypatch.setattr(api_baseball.APIBaseballClient, "from_env", classmethod(lambda cls: client))
    res = IngestionService(NS(source_name="mlb_stats_api")).sync_odds_mlb(season=2026)
    assert res.no_book_odds_run == how and res.odds_not_read == {}
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: NS(source_name="mlb_stats_api"))
    out = CliRunner().invoke(cli.cli, ["sync-odds", "--competition", "MLB", "--season", "2026"])
    assert out.exit_code == 0, out.output
    lines = [x for x in out.output.splitlines() if x.strip()]
    assert lines[-1].startswith("✓ MLB odds: ") and lines[-2].startswith("NO-BOOK-ODDS (MLB): run [")
    assert not any(x.startswith("odds_not_read") for x in lines)
    cap = CliRunner().invoke(cli.cli, ["capture-odds"])
    assert cap.exit_code == 0, cap.output
    assert not any(x.startswith("odds_not_read") for x in cap.output.splitlines())


def test_capture_odds_prints_the_line_before_its_odds_synced_line(monkeypatch):
    import cli
    monkeypatch.setattr(svc.IngestionService, "sync_odds_mlb",
                        lambda self, season: svc.SyncResult(odds_not_read={"started": [5]}))
    out = CliRunner().invoke(cli.cli, ["capture-odds"])
    assert out.exit_code == 0, out.output
    lines = [x for x in out.output.splitlines() if x.strip()]
    i = lines.index("odds_not_read 1 (started 1: 5)")
    assert lines[i + 1].startswith("odds synced: ") and lines[-1].startswith("✓ Captured ")


# ------------------------------------------------------------------------------------- (C) sync-odds-football

def test_sync_odds_football_counts_every_unpriced_game_and_prints_before_the_summary(made, monkeypatch):
    import cli
    cid = _comp(made, "DRC4", sport=Sport.NFL)
    good = _match(made, cid, sport=Sport.NFL, ext={"api_american_football": "drc-good"})
    no_id = _match(made, cid, sport=Sport.NFL)
    broken = _match(made, cid, sport=Sport.NFL, ext={"api_american_football": "drc-broken"})
    limited = _match(made, cid, sport=Sport.NFL, ext={"api_american_football": "drc-limited"})
    empty = _match(made, cid, sport=Sport.NFL, ext={"api_american_football": "drc-empty"})
    far = _match(made, cid, sport=Sport.NFL, when=utc_now_naive() + timedelta(days=20),
                 ext={"api_american_football": "drc-far"})
    missing = 2_000_000_001

    def list_odds(self, gid):
        if gid == "drc-broken":
            raise ValueError("synthetic provider hiccup")
        if gid == "drc-limited":
            raise RateLimited("odds", 5)
        if gid == "drc-empty":
            return []
        return [NormalizedOdds(source="api_american_football", match_source_id=gid, market="1X2", selection=sel,
                               bookmaker="bk", price_decimal=px, captured_at=utc_now_naive())
                for sel, px in (("HOME", 1.8), ("AWAY", 2.1))]
    monkeypatch.setattr("src.adapters.api_american_football.APIAmericanFootballAdapter.list_odds", list_odds)
    monkeypatch.setattr(svc, "_odds_sleep", lambda x: None)
    named = {good, no_id, broken, limited, empty, far, missing}
    msgs = []
    r = svc.sync_odds_nfl(progress=msgs.append, match_ids=named)
    assert r["not_priced"] == {"named, not in the window": sorted([far, missing]), "no provider id": [no_id],
                               "fetch error": [broken], "still rate limited": [limited], "no rows": [empty]}
    assert (r["created"], r["games"]) == (2, 1)
    assert {"created", "games", "snapshots", "rate_limited", "recovered", "games_by_competition",
            "window_by_competition", "orientation_swapped", "orientation_mismatch_unpriced"} <= set(r)
    assert any("still rate limited after 2 retry round(s): 1 game(s) unpriced" in m for m in msgs)   # as before

    out = CliRunner().invoke(cli.cli, ["sync-odds-football", "--match-ids", ",".join(str(i) for i in sorted(named))])
    assert out.exit_code == 0, out.output
    lines = [x for x in out.output.splitlines() if x.strip()]
    i = max(k for k, x in enumerate(lines) if x.startswith("✓ Football odds: created=2"))
    assert " ".join(lines[i:]).endswith("book-consensus snapshots appended=2")   # the summary (rich may wrap it) last
    far_ids = ", ".join(map(str, sorted([far, missing])))
    assert lines[i - 1] == (f"football_not_priced 6 (named, not in the window 2: {far_ids} · no provider id 1: {no_id}"
                            f" · fetch error 1: {broken} · still rate limited 1: {limited} · no rows 1: {empty})")
    assert lines[i - 2].startswith("orientation_mismatch_unpriced 0")


def test_sync_odds_football_without_the_key_prints_as_before(monkeypatch):
    import cli
    monkeypatch.setattr(svc, "sync_odds_nfl", lambda progress=None: {"created": 3, "games": 2})
    out = CliRunner().invoke(cli.cli, ["sync-odds-football"])
    assert out.exit_code == 0 and "football_not_priced" not in out.output
    monkeypatch.setattr(svc, "sync_odds_nfl", lambda progress=None: {"created": 3, "games": 2, "not_priced": {}})
    out = CliRunner().invoke(cli.cli, ["sync-odds-football"])
    lines = [x for x in out.output.splitlines() if x.strip()]
    assert out.exit_code == 0 and lines[-2:] == ["football_not_priced 0", "✓ Football odds: created=3 across 2 games"]


# ------------------------------------------------------------------------------------- (D) the markers

NEW_LINES = [
    base.dropped_line("mlb_stats_api", "schedule", {"no team id": [901, None], "unreadable date": [902]}),
    base.dropped_line("api_hockey", "games", {"no kickoff date": [501], "no game id": [None], "no team id": [503]}),
    base.dropped_line("api_hockey", "teams", {"no team id": [None], "no team name": [3]}),
    base.dropped_line("api_american_football", "games", {"no kickoff date": [1], "no game id": [None],
                                                         "no team id": [2], "non-competitive": [3]}),
    base.dropped_line("api_american_football", "teams", {"no team id": [None], "no team name": [3],
                                                         "non-competitive": [4]}),
    base.dropped_line("api_baseball", "teams", {"no team id": [None], "no team name": [3]}),
    base.dropped_line("api_baseball", "games", {"unreadable date": [801, 802]}),
    odds_not_read_line({}),
    odds_not_read_line({"no provider id": [1], "not stored": [2], "other competition": [3], "other season": [4],
                        "not scheduled": [5], "kickoff passed": [6], "not a candidate": [7]}),
    odds_not_read_line({"no game id": [None], "unreadable date": [7001], "no team name": [7101], "started": [8]}),
    football_not_priced_line({}),
    football_not_priced_line({"named, not in the window": [1], "no provider id": [2], "fetch error": [3],
                              "still rate limited": [4], "no rows": [5]}),
]
FORBIDDEN = ("skipped", "failed", "STRICT", "REFUSED", "Error", "Exception", "orientation_", "provider_id_")
SP_RUN_LINES = (sp_run.TEAMS_LINE, sp_run.FALLBACK_TEAMS_LINE, sp_run.MATCHES_LINE, sp_run.SKIPPED_LISTINGS_LINE,
                sp_run.SCORES_BY_TEAM_LINE, sp_run.ODDS_SWAPPED_LINE, sp_run.ODDS_MISMATCH_LINE, sp_run.HELD_LINE)


@pytest.mark.parametrize("line", NEW_LINES)
def test_no_new_line_reads_as_a_count_line_an_echo_a_failure_or_an_exception(line):
    assert line and "\n" not in line
    assert not line.lstrip().startswith(("✓", "✗"))
    assert not any(w in line for w in FORBIDDEN), line
    assert not any(rx.match(line) or rx.search(line) for rx in SP_RUN_LINES), line
    assert not sp_run._EXC_LINE.match(line.strip()) and not sp_run._TRANSIENT.search(line), line
    assert not laptop_routine.SYNC_ECHO.search(line), line
    assert sp_run.sync_counts([line]) == {}
    assert sp_run.transient_class(1, [line]) is None
    assert not re.search(r"match \d+ \[", line)                          # closing.no_book_odds' own shape
