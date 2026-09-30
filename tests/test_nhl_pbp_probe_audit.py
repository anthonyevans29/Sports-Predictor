"""NHL follow-ons to the v5 FAIL (architect 2026-09-30): the read-only
play-by-play shot-quality probe, and the audit of unlinked goalie games
(UTC-boundary suspects) with the opt-in sync tolerance. Synthetic payloads
only; the API is never reached."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from scripts import nhl_pbp_probe as pp
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, NHLGoalieAppearance, Sport, Team
from src.ingestion import nhl_goalies as ngs


def side(abbrev, place, common):
    return {"abbrev": abbrev, "placeName": {"default": place}, "commonName": {"default": common}}


def sgame(gid, start, home, away, gtype=2):
    return {"id": gid, "startTimeUTC": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "gameType": gtype,
            "homeTeam": home, "awayTeam": away}


def box(hg, ag):
    g = lambda pid, sv, sh: {"playerId": pid, "name": {"default": f"G{pid}"}, "starter": True,
                             "saves": sv, "shotsAgainst": sh}
    return {"playerByGameStats": {"homeTeam": {"goalies": [g(hg, 25, 27)]}, "awayTeam": {"goalies": [g(ag, 30, 33)]}}}


# --- audit: pure classification ------------------------------------------------------

def O(i, t, h, a, season="2033"):
    return {"id": i, "t": t, "season": season, "stage": "", "home": h, "away": a,
            "hn": ngs._norm(h), "an": ngs._norm(a)}


def API(t, home, away, gid=1):
    return {"id": gid, "start": t, "game_type": 2, "home_names": [home], "away_names": [away]}


T = datetime(2033, 11, 2, 0, 30)


def test_classify_utc_boundary_swapped_mismatch_absent():
    ours = [O(1, T - timedelta(hours=18), "Boston Bruins", "Toronto Maple Leafs"),
            O(2, T, "Ottawa Senators", "Montreal Canadiens"),
            O(3, T + timedelta(hours=2), "Seattle Kraken", "Utah Hockey Club")]
    c = ngs.classify(API(T, "Boston Bruins", "Toronto Maple Leafs"), ours, set())
    assert (c["cause"], c["offset_h"], c["match_id"]) == ("utc_boundary", 18.0, 1)
    assert ngs.classify(API(T, "Montréal Canadiens", "Ottawa Senators"), ours, set())["cause"] == "home_away_swapped"
    assert ngs.classify(API(T, "Seattle Kraken", "Utah Mammoth"), ours, set())["cause"] == "name_mismatch"
    assert ngs.classify(API(T, "Vancouver Canucks", "Calgary Flames"), ours, set())["cause"] == "not_in_our_db"
    assert ngs.classify(API(T, "Ottawa Senators", "Montreal Canadiens"), ours, set())["cause"] == "unlinked_within_12h"


def test_classify_ambiguous_within_12h_is_refused():
    ours = [O(1, T, "Boston Bruins", "Toronto Maple Leafs"), O(2, T + timedelta(hours=3), "Boston Bruins",
                                                                  "Toronto Maple Leafs")]
    assert ngs.classify(API(T, "Boston Bruins", "Toronto Maple Leafs"), ours, set())["cause"] == "ambiguous_within_12h"


# --- audit + opt-in tolerance end to end (throwaway DB, fake API) -------------------

def _comp(s):
    c = s.execute(select(Competition).where(Competition.sport == Sport.NHL, Competition.code == "NHL")).scalar_one_or_none()
    if c is None:
        c = Competition(sport=Sport.NHL, code="NHL", name="NHL", area="USA", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


def _team(s, name):
    t = s.execute(select(Team).where(Team.sport == Sport.NHL, Team.name == name)).scalar_one_or_none()
    if t is None:
        t = Team(sport=Sport.NHL, name=name)
        s.add(t)
        s.flush()
    return t


def test_audit_finds_the_offset_and_tolerance_links_it():
    init_db()
    t_api = datetime(2034, 1, 11, 0, 0)
    with session_scope() as s:
        c = _comp(s)
        h, a = _team(s, "Winnipeg Jets"), _team(s, "Minnesota Wild")
        m = Match(sport=Sport.NHL, competition_id=c.id, season="2034", utc_date=t_api - timedelta(hours=15),
                  status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=3, away_score=1)
        s.add(m)
        s.flush()
        mid = m.id
    week = {"gameWeek": [{"games": [sgame(5001, t_api, side("WPG", "Winnipeg", "Jets"),
                                          side("MIN", "Minnesota", "Wild"))]}]}

    def fetch(url):
        if "/schedule/" in url:
            return 200, week if url.endswith("2034-01-10") else {"gameWeek": []}
        return 200, box(71, 72)

    # the default ±12h does not link it: stored with no match
    r = ngs.sync(date(2034, 1, 10), date(2034, 1, 10), fetch=fetch, sleep=0, now=datetime(2034, 2, 1))
    assert r["counts"]["not_in_our_db"] == 1
    a = ngs.audit(date(2034, 1, 10), date(2034, 1, 10), fetch=fetch, sleep=0, now=datetime(2034, 2, 1))
    assert a["api_unlinked_by_cause"] == {"utc_boundary": 1}
    assert a["offset_hours"] == {15: 1} and a["would_link_uniquely"] == {18: 1, 24: 1, 36: 1, 48: 1}
    assert a["ours_unlinked_by_season"]["2034"] == 1
    with session_scope() as s:                        # the audit wrote nothing
        assert s.execute(select(NHLGoalieAppearance.match_id).where(
            NHLGoalieAppearance.nhl_game_id == 5001)).scalars().all() == [None, None]
    # the operator widens the window after the audit: the stored rows get linked
    r2 = ngs.sync(date(2034, 1, 10), date(2034, 1, 10), fetch=fetch, sleep=0, now=datetime(2034, 2, 1),
                  tolerance_hours=18)
    assert r2["counts"]["mapped_to_our_match"] == 1
    with session_scope() as s:
        assert set(s.execute(select(NHLGoalieAppearance.match_id).where(
            NHLGoalieAppearance.nhl_game_id == 5001)).scalars()) == {mid}


# --- play-by-play probe -----------------------------------------------------------

def play(t, x=None, y=None, st=None, shooter=None, sit="1551"):
    d = {k: v for k, v in (("xCoord", x), ("yCoord", y), ("shotType", st), ("shootingPlayerId", shooter)) if v is not None}
    return {"eventId": 1, "typeDescKey": t, "typeCode": 506, "situationCode": sit, "details": d}


def pbp(n_shots=10, with_xy=True):
    plays = [play("faceoff")] + [play("shot-on-goal", 50 if with_xy else None, -10 if with_xy else None,
                                      "wrist", 8478402) for _ in range(n_shots)] + [play("goal", 80, 5, "snap", 8479318)]
    return {"id": 1, "plays": plays, "rosterSpots": []}


def test_read_game_finds_shots_and_fields_by_discovery():
    r = pp.read_game(pbp())
    assert r["plays"] == 12 and r["type_key"] == "typeDescKey" and r["shots"] == 11
    assert r["have"] == {"xy": 11, "shot_type": 11, "shooter": 11, "situation": 11}
    assert r["shot_types"] == {"shot-on-goal": 10, "goal": 1}
    assert "x<-xCoord" in r["keys_used"] and "shooter<-shootingPlayerId" in r["keys_used"]


def test_probe_green_and_not_met(capsys):
    now = datetime(2026, 9, 30, 12)

    def fetch_ok(url):
        if "/schedule/" in url:
            d = datetime.fromisoformat(url.rsplit("/", 1)[1])
            return 200, {"gameWeek": [{"games": [sgame(int(d.strftime("%Y%m%d")), d, side("A", "A", "A"),
                                                        side("B", "B", "B"))]}]}
        return 200, pbp()

    assert pp.main(["--per-season", "3", "--sleep", "0"], fetch=fetch_ok, now=now) == 0
    out = capsys.readouterr().out
    assert "P2 location: FEEDABLE" in out and "P6 depth: FEEDABLE" in out
    assert "REOPENING CONDITION (shot-quality data): GREEN" in out

    def fetch_noxy(url):
        return fetch_ok(url) if "/schedule/" in url else (200, pbp(with_xy=False))

    pp.main(["--per-season", "3", "--sleep", "0"], fetch=fetch_noxy, now=now)
    out = capsys.readouterr().out
    assert "P2 location: NOT" in out and "REOPENING CONDITION (shot-quality data): NOT MET" in out


def test_probe_refuses_data_dir(capsys):
    assert pp.main(["--out", "data/pbp.jsonl"]) == 1
    assert "REFUSED" in capsys.readouterr().out
