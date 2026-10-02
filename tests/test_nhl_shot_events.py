"""NHL-xG lane (1) INGEST (#153; corrected manifest #210): nhl_shot_events
from api-web play-by-play, keyed to our matches via the goalie-sync mapping
(else the refusal-on-ambiguity matcher). Synthetic payloads shaped like the
probe's GREEN read (#143); the API is never reached. Raw values only: the
event type is stored for ELIGIBILITY + TARGET (never a feature), shot type
is nullable, empty-net / blocked / orientation / missing-coordinate inputs
are stored raw for the pre-committed v6 rules."""
from datetime import date, datetime, timedelta

from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, NHLGoalieAppearance, NHLShotEvent, Sport, Team
from src.ingestion import nhl_shots as nsh

T1 = datetime(2034, 11, 3, 0, 0)


def side(abbrev, place, common, tid):
    return {"id": tid, "abbrev": abbrev, "placeName": {"default": place}, "commonName": {"default": common}}


def sched(*games):
    return {"gameWeek": [{"date": "x", "games": list(games)}]}


def sgame(gid, start, home, away, gtype=2):
    return {"id": gid, "startTimeUTC": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "gameType": gtype,
            "homeTeam": home, "awayTeam": away}


def play(eid, typ, period=1, t="05:10", owner=1, x=-60.0, y=10.0, shot_type="wrist", shooter=101,
         goalie=202, sit="1551", defending="left", key_shooter="shootingPlayerId"):
    d = {"eventOwnerTeamId": owner, "zoneCode": "O"}
    if x is not None:
        d["xCoord"] = x
    if y is not None:
        d["yCoord"] = y
    if shot_type is not None:
        d["shotType"] = shot_type
    if shooter is not None:
        d[key_shooter] = shooter
    if goalie is not None:
        d["goalieInNetId"] = goalie
    return {"eventId": eid, "typeDescKey": typ, "typeCode": 506, "timeInPeriod": t,
            "periodDescriptor": {"number": period, "periodType": "REG"},
            "situationCode": sit, "homeTeamDefendingSide": defending, "details": d}


def pbp(*plays):
    return {"id": 9001, "homeTeam": {"id": 1, "abbrev": "WPJ"}, "awayTeam": {"id": 2, "abbrev": "NSH"},
            "rosterSpots": [{"playerId": 101, "teamId": 1}, {"playerId": 102, "teamId": 2},
                            {"playerId": 201, "teamId": 1}, {"playerId": 202, "teamId": 2}],
            "plays": [{"eventId": 1, "typeDescKey": "faceoff", "details": {}}] + list(plays)}


def test_read_events_raw_values_and_receipt():
    rows, rec = nsh.read_events(pbp(
        play(10, "shot-on-goal"),
        play(11, "goal", shooter=None, key_shooter="scoringPlayerId", t="12:34"),
        play(12, "goal", shooter=102, key_shooter="scoringPlayerId", owner=2, goalie=None, sit="1560"),  # empty net
        play(13, "blocked-shot", owner=2, shot_type=None),             # owner = blocking team by convention
        play(14, "missed-shot", x=None, y=None),                        # missing coordinates kept NULL
    ))
    by = {r["event_id"]: r for r in rows}
    assert set(by) == {10, 11, 12, 13, 14}                              # the faceoff is not a shot event
    assert by[10]["side"] == "home" and by[10]["owner_side"] == "home" and by[10]["x"] == -60.0
    assert by[10]["period"] == 1 and by[10]["period_type"] == "REG" and by[10]["time_in_period_s"] == 310
    assert by[12]["goalie_id"] is None and by[12]["situation_code"] == "1560" and by[12]["side"] == "away"
    assert by[13]["shot_type"] is None and by[13]["side"] == "home" and by[13]["owner_side"] == "away"
    assert by[14]["x"] is None and by[14]["y"] is None
    assert by[10]["home_defending_side"] == "left"
    assert rec["teams_found"] and rec["roster_players"] == 4
    assert rec["keys_used"]["x<-xCoord"] == 4 and rec["keys_used"]["type<-typeDescKey"] == 5


def test_read_events_refuses_a_payload_without_plays():
    assert nsh.read_events({"id": 1})[0] is None


def test_sync_links_via_goalie_mapping_upserts_and_reports_feedable(tmp_path):
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.sport == Sport.NHL, Competition.code == "NHL")
                         ).scalar_one_or_none() or Competition(sport=Sport.NHL, code="NHL", name="NHL",
                                                               area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        h, a = Team(sport=Sport.NHL, name="Winnipeg Jets"), Team(sport=Sport.NHL, name="Nashville Predators")
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.NHL, competition_id=comp.id, season="2077", utc_date=T1, status=MatchStatus.FINISHED,
                  home_team_id=h.id, away_team_id=a.id, home_score=3, away_score=1)
        s.add(m)
        s.flush()
        mid = m.id
        s.add(NHLGoalieAppearance(nhl_game_id=9001, match_id=mid, goalie_id=201, side="home",
                                  game_start=T1, game_type=2, is_starter=True))
    week = sched(sgame(9001, T1, side("WPJ", "Winnipeg", "Jets", 1), side("NSH", "Nashville", "Predators", 2)),
                 sgame(9002, T1, side("SEA", "Seattle", "Kraken", 3), side("VAN", "Vancouver", "Canucks", 4)))
    payloads = {9001: pbp(play(10, "shot-on-goal"), play(11, "goal", key_shooter="scoringPlayerId"),
                          play(13, "blocked-shot", owner=2, shot_type=None)),
                9002: pbp(play(20, "shot-on-goal"))}
    calls = []

    def fetch(url):
        calls.append(url)
        if "/schedule/" in url:
            return 200, week if url.endswith("2034-11-02") else {"gameWeek": []}
        return 200, payloads[int(url.split("/gamecenter/")[1].split("/")[0])]

    r = nsh.sync(date(2034, 11, 2), date(2034, 11, 8), fetch=fetch, sleep=0, now=datetime(2034, 12, 1))
    c = r["counts"]
    assert c["mapped_via_goalie_link"] == 1 and c["not_in_our_db"] == 1 and c["events_written"] == 4
    assert r["side_vs_owner"]["blocked-shot"] == {"disagree": 1}
    with session_scope() as s:
        ev = {(e.nhl_game_id, e.event_id): e for e in s.execute(select(NHLShotEvent).where(
            NHLShotEvent.nhl_game_id.in_([9001, 9002]))).scalars()}
        assert ev[(9001, 10)].match_id == mid and ev[(9002, 20)].match_id is None
        assert ev[(9001, 13)].shot_type is None
    # a refetch never blanks a stored value; a re-run skips stored games
    payloads[9001] = pbp(play(10, "shot-on-goal", x=None, y=None))
    r2 = nsh.sync(date(2034, 11, 2), date(2034, 11, 8), fetch=fetch, sleep=0, now=datetime(2034, 12, 1), refresh=True)
    assert r2["counts"]["events_written"] == 2
    with session_scope() as s:
        e = s.execute(select(NHLShotEvent).where(NHLShotEvent.nhl_game_id == 9001,
                                                 NHLShotEvent.event_id == 10)).scalar_one()
        assert (e.x, e.y) == (-60.0, 10.0)
    cov = nsh.coverage()
    assert cov["by_season"]["2077"] == {"finished": 1, "with_shots": 1, "events": 3, "goalie_linked_no_shots": 0}
    lines = nsh.feedable_lines(cov)
    assert any(l.startswith("P2 location x+y:") for l in lines) and any("P6 depth" in l for l in lines)
    out = CliRunner().invoke(__import__("cli").cli, ["nhl-shot-coverage"]).output
    assert "NHL-SHOT COVERAGE" in out and "2077: finished 1 · with shot events 1 (100.0%)" in out
