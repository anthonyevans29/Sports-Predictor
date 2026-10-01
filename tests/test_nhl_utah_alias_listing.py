"""NHL audit rulings (architect 2026-10-01): (1) alias "Utah Hockey Club" <->
"Utah Mammoth" in the goalie mapping; (2) list OUR unlinked games with the
nearest API game, its delta and a NAMED cause. Synthetic payloads only."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, NHLGoalieAppearance, Sport, Team
from src.ingestion import nhl_goalies as ngs


def side(abbrev, place, common):
    return {"abbrev": abbrev, "placeName": {"default": place}, "commonName": {"default": common}}


def test_team_names_carry_the_utah_alias_both_ways():
    assert ngs.team_names(side("UTA", "Utah", "Mammoth")) == ["Utah Mammoth", "Utah Hockey Club"]
    assert "Utah Mammoth" in ngs.team_names({"name": {"default": "Utah Hockey Club"}})
    assert ngs.team_names(side("BOS", "Boston", "Bruins")) == ["Boston Bruins"]   # others untouched


def test_team_names_map_the_2024_doubled_utah_token():
    # 2024-25 schedule: placeName "Utah" + commonName "Utah Hockey Club"
    assert ngs.team_names(side("UTA", "Utah", "Utah Hockey Club")) == [
        "Utah Utah Hockey Club", "Utah Mammoth", "Utah Hockey Club"]


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


def test_sync_links_utah_mammoth_to_our_utah_hockey_club():
    init_db()
    t = datetime(2036, 1, 11, 2, 0)
    with session_scope() as s:
        c = _comp(s)
        h, a = _team(s, "Utah Hockey Club"), _team(s, "Vegas Golden Knights")
        m = Match(sport=Sport.NHL, competition_id=c.id, season="2036", utc_date=t, status=MatchStatus.FINISHED,
                  home_team_id=h.id, away_team_id=a.id, home_score=2, away_score=1)
        s.add(m)
        s.flush()
        mid = m.id
    g = {"id": 7001, "startTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "gameType": 2,
         "homeTeam": side("UTA", "Utah", "Mammoth"), "awayTeam": side("VGK", "Vegas", "Golden Knights")}
    gl = lambda pid: {"playerId": pid, "name": {"default": f"G{pid}"}, "starter": True,
                      "saves": 20, "shotsAgainst": 22}
    box = {"playerByGameStats": {"homeTeam": {"goalies": [gl(81)]}, "awayTeam": {"goalies": [gl(82)]}}}

    def fetch(url):
        if "/schedule/" in url:
            return 200, ({"gameWeek": [{"games": [g]}]} if url.endswith("2036-01-10") else {"gameWeek": []})
        return 200, box
    r = ngs.sync(date(2036, 1, 10), date(2036, 1, 10), fetch=fetch, sleep=0, now=datetime(2036, 2, 1))
    assert r["counts"]["mapped_to_our_match"] == 1
    with session_scope() as s:
        assert set(s.execute(select(NHLGoalieAppearance.match_id)
                             .where(NHLGoalieAppearance.nhl_game_id == 7001)).scalars()) == {mid}


T = datetime(2037, 11, 2, 0, 30)


def O(i, t, h, a, season="2037"):
    return {"id": i, "t": t, "season": season, "stage": "", "home": h, "away": a,
            "hn": ngs._norm(h), "an": ngs._norm(a)}


def G(gid, t, home, away, gtype=2):
    return {"id": gid, "start": t, "game_type": gtype, "home_names": [home], "away_names": [away]}


def test_listing_names_every_cause():
    ours = [O(1, T, "Boston Bruins", "Toronto Maple Leafs"),            # API preseason
            O(2, T, "Ottawa Senators", "Montreal Canadiens"),           # same pair, within 12h, unsynced
            O(3, T, "Seattle Kraken", "Calgary Flames"),                # same pair at +20h
            O(4, T, "Dallas Stars", "St. Louis Blues"),                 # API game linked elsewhere
            O(5, T, "New Jersey Devils", "Buffalo Sabres"),             # only swapped
            O(6, T, "Winnipeg Jets", "Nashville Predators"),            # one team only
            O(7, T, "Anaheim Ducks", "San Jose Sharks"),                # nothing within 7 days
            O(8, T, "Detroit Red Wings", "Chicago Blackhawks"),         # linked -> not listed
            O(9, T, "Detroit Red Wings", "Chicago Blackhawks", season="2036")]  # other season -> not listed
    api = [G(11, T + timedelta(hours=1), "Boston Bruins", "Toronto Maple Leafs", gtype=1),
           G(12, T + timedelta(hours=2), "Ottawa Senators", "Montreal Canadiens"),
           G(13, T + timedelta(hours=20), "Seattle Kraken", "Calgary Flames"),
           G(14, T, "Dallas Stars", "St. Louis Blues"),
           G(15, T, "Buffalo Sabres", "New Jersey Devils"),
           G(16, T + timedelta(days=2), "Winnipeg Jets", "Minnesota Wild"),
           G(17, T + timedelta(days=9), "Anaheim Ducks", "San Jose Sharks"),
           G(18, T, "Detroit Red Wings", "Chicago Blackhawks")]
    links = {14: 99, 18: 8}
    rows = {r["match_id"]: r for r in ngs.list_unlinked_ours(api, ours, links, {"2037"})}
    assert set(rows) == {1, 2, 3, 4, 5, 6, 7}
    assert {k: v["cause"] for k, v in rows.items()} == {
        1: "api_preseason", 2: "api_game_not_synced", 3: "utc_offset_beyond_12h",
        4: "linked_to_other_match", 5: "home_away_swapped", 6: "one_team_only", 7: "no_api_game"}
    assert rows[3]["delta_h"] == 20.0 and rows[6]["delta_h"] == 48.0 and rows[7]["api"] is None
    assert rows[4]["api_linked_to"] == 99 and "game 11 type 1" in rows[1]["api"]
