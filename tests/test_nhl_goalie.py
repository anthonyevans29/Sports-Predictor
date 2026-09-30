"""NHL-GOALIE lane (architect 2026-09-30): (a) the api-web.nhle.com adapter +
nhl_goalie_appearances, (b) the v5 goalie term and its gate wiring. The API
is never reached here: payloads are synthetic, shaped like the ones the
NHL-API-PROBE found (#124), and parsing is discovery-based (law 1)."""
from datetime import date, datetime, timedelta

from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, NHLGoalieAppearance, Sport, Team
from src.ingestion import nhl_goalies as ngs
from src.models import nhl_goalie as ng
from src.models.nhl_elo import NHLEloConfig, NHLEloV1, NHLEloV5
from src.walters import nhl_backtest as nb


def side(abbrev, place, common):
    return {"abbrev": abbrev, "placeName": {"default": place}, "commonName": {"default": common}}


def sched(*games):
    return {"gameWeek": [{"date": "x", "games": list(games)}]}


def sgame(gid, start, home, away, gtype=2):
    return {"id": gid, "startTimeUTC": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "gameType": gtype,
            "homeTeam": home, "awayTeam": away}


def goalie(pid, name, starter, saves, shots, toi="60:00", decision=None):
    return {"playerId": pid, "name": {"default": name}, "starter": starter, "saves": saves,
            "shotsAgainst": shots, "goalsAgainst": shots - saves, "toi": toi, "decision": decision}


def box(home_goalies, away_goalies):
    return {"playerByGameStats": {"homeTeam": {"goalies": home_goalies, "forwards": []},
                                  "awayTeam": {"goalies": away_goalies, "forwards": []}}}


# --- (a) parsing -----------------------------------------------------------------

def test_schedule_games_found_by_discovery_and_names_accent_stripped():
    t = datetime(2031, 11, 3, 0, 0)
    gs = ngs.schedule_games(sched(sgame(7, t, side("MTL", "Montréal", "Canadiens"), side("BOS", "Boston", "Bruins"))))
    assert gs == [{"id": 7, "start": t, "game_type": 2, "home_names": ["Montreal Canadiens"],
                   "away_names": ["Boston Bruins"], "home_abbrev": "MTL", "away_abbrev": "BOS"}]


def test_boxscore_goalies_sided_starter_and_stats():
    rows, rc = ngs.boxscore_goalies(box([goalie(1, "A. Home", True, 28, 30, decision="W"),
                                         goalie(2, "B. Relief", False, 0, 0, toi="00:00")],
                                        [goalie(3, "C. Away", True, 25, 29, decision="L")]))
    assert [(r["side"], r["goalie_id"], r["is_starter"], r["saves"], r["shots_against"], r["goals_against"])
            for r in rows] == [("home", 1, True, 28, 30, 2), ("home", 2, False, 0, 0, 0), ("away", 3, True, 25, 29, 4)]
    assert rows[0]["toi_seconds"] == 3600 and rows[0]["decision"] == "W"
    assert rc["keys_used"]["starter"] == "starter" and rc["keys_used"]["shots_against"] == "shotsAgainst"


def test_combined_save_shots_string_and_missing_starter_flag_stays_null():
    g = {"playerId": 9, "name": {"default": "X"}, "saveShotsAgainst": "25/27"}
    r = ngs.goalie_rows(g)["row"]
    assert (r["saves"], r["shots_against"], r["goals_against"], r["is_starter"]) == (25, 27, 2, None)


def test_unsided_goalie_lists_are_refused():
    rows, rc = ngs.boxscore_goalies({"goalies": [goalie(1, "A", True, 20, 22)]})
    assert rows is None and rc["goalie_lists"] == ["goalies"]


# --- (a) sync end to end (fake API, throwaway DB) ----------------------------------

def _nhl_comp(s):
    comp = s.execute(select(Competition).where(Competition.sport == Sport.NHL, Competition.code == "NHL")).scalar_one_or_none()
    if comp is None:
        comp = Competition(sport=Sport.NHL, code="NHL", name="NHL", area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
    return comp


def _team(s, name):
    t = s.execute(select(Team).where(Team.sport == Sport.NHL, Team.name == name)).scalar_one_or_none()
    if t is None:
        t = Team(sport=Sport.NHL, name=name)
        s.add(t)
        s.flush()
    return t


def test_sync_maps_our_matches_writes_rows_and_reports_coverage():
    init_db()
    t1, t2 = datetime(2031, 11, 3, 0, 0), datetime(2031, 11, 5, 0, 30)
    with session_scope() as s:
        comp = _nhl_comp(s)
        mtl, bos = _team(s, "Montreal Canadiens"), _team(s, "Boston Bruins")
        m1 = Match(sport=Sport.NHL, competition_id=comp.id, season="2031", utc_date=t1 + timedelta(minutes=5),
                   status=MatchStatus.FINISHED, home_team_id=mtl.id, away_team_id=bos.id, home_score=3, away_score=2)
        s.add(m1)
        s.flush()
        m1_id = m1.id
    week = sched(sgame(101, t1, side("MTL", "Montréal", "Canadiens"), side("BOS", "Boston", "Bruins")),
                 sgame(102, t2, side("TOR", "Toronto", "Maple Leafs"), side("OTT", "Ottawa", "Senators")),
                 sgame(103, t2, side("TOR", "Toronto", "Maple Leafs"), side("OTT", "Ottawa", "Senators"), gtype=1),
                 sgame(104, t2 + timedelta(hours=2), side("VAN", "Vancouver", "Canucks"), side("SEA", "Seattle", "Kraken")))
    boxes = {101: box([goalie(11, "Home G", True, 30, 32)], [goalie(12, "Away G", True, 27, 30)]),
             102: box([goalie(13, "Tor G", True, 20, 21)], [goalie(14, "Ott G", True, 33, 36)]),
             104: {"goalies": []}}
    calls = []

    def fetch(url):
        calls.append(url)
        if "/schedule/" in url:
            return 200, week if url.endswith("2031-11-02") else {"gameWeek": []}
        gid = int(url.split("/gamecenter/")[1].split("/")[0])
        return 200, boxes[gid]

    r = ngs.sync(date(2031, 11, 2), date(2031, 11, 8), fetch=fetch, sleep=0, now=datetime(2031, 12, 1))
    c = r["counts"]
    assert c["games_found"] == 4 and c["skipped_game_type_1"] == 1
    assert c["mapped_to_our_match"] == 1 and c["not_in_our_db"] == 2
    assert c["both_starters"] == 2 and c["refused_unsided"] == 1 and c["rows_written"] == 4
    assert r["keys_used"]["starter"] == "starter"
    with session_scope() as s:
        rows = {(a.nhl_game_id, a.goalie_id): a for a in s.execute(select(NHLGoalieAppearance).where(
            NHLGoalieAppearance.nhl_game_id.in_([101, 102, 103, 104]))).scalars()}
        assert rows[(101, 11)].match_id == m1_id and rows[(101, 11)].side == "home"
        assert rows[(102, 13)].match_id is None                   # not in our DB: stored for goalie history
        assert rows[(101, 12)].team_abbrev == "BOS" and rows[(101, 12)].saves == 27
    cov = ngs.coverage()["by_season"]["2031"]
    assert cov == {"finished": 1, "linked": 1, "both_starters": 1}
    # idempotent: a second run fetches no boxscore for complete games and writes nothing new
    calls.clear()
    r2 = ngs.sync(date(2031, 11, 2), date(2031, 11, 8), fetch=fetch, sleep=0, now=datetime(2031, 12, 1))
    assert r2["counts"]["skipped_already_complete"] == 2
    assert not [u for u in calls if "/gamecenter/101/" in u or "/gamecenter/102/" in u]


def test_dry_run_writes_nothing():
    init_db()
    t = datetime(2032, 1, 10, 0, 0)
    week = sched(sgame(201, t, side("NJD", "New Jersey", "Devils"), side("NYR", "New York", "Rangers")))
    fetch = lambda url: (200, week) if "/schedule/2032-01-09" in url else \
        ((200, {"gameWeek": []}) if "/schedule/" in url else (200, box([goalie(21, "G", True, 20, 22)],
                                                                          [goalie(22, "H", True, 25, 26)])))
    r = ngs.sync(date(2032, 1, 9), date(2032, 1, 9), fetch=fetch, sleep=0, dry_run=True, now=datetime(2032, 2, 1))
    assert r["counts"]["rows_would_write"] == 2
    with session_scope() as s:
        assert not s.execute(select(NHLGoalieAppearance).where(NHLGoalieAppearance.nhl_game_id == 201)).first()


# --- (b) the goalie tracker ------------------------------------------------------

def A(day, gid, goalie_id, shots, saves, side="home"):
    return ng.Appearance(datetime(2024, 10, 1) + timedelta(days=day), gid, side, goalie_id, shots, saves)


def test_tracker_is_strictly_as_of():
    tr = ng.GoalieTracker([A(10, 1, 7, 30, 30)])            # a shutout at day 10
    tr.advance_to(datetime(2024, 10, 11, 3))                # the same game's clock (< 6h later): not visible
    assert tr.gsaa_rate(7, datetime(2024, 10, 11, 3)) == 0.0
    tr.advance_to(datetime(2024, 10, 12))
    assert tr.gsaa_rate(7, datetime(2024, 10, 12)) > 0.0


def test_tracker_shrinks_decays_and_signs():
    good = [A(i, 100 + i, 1, 30, 29) for i in range(0, 60, 2)]      # .967
    bad = [A(i + 1, 200 + i, 2, 30, 25, side="away") for i in range(0, 60, 2)]  # .833
    tr = ng.GoalieTracker(good + bad)
    t = datetime(2024, 10, 1) + timedelta(days=61)
    tr.advance_to(t)
    g, b = tr.gsaa_rate(1, t), tr.gsaa_rate(2, t)
    assert g > 0 > b
    raw_good = 29 / 30 - tr.league()[0]
    assert 0 < g < raw_good                                   # shrunk toward the league mean
    later = t + timedelta(days=ng.HALF_LIFE_DAYS * 3)
    assert abs(tr.gsaa_rate(1, later)) < abs(g)               # decays without new games
    assert tr.elo_adjustment(1, t) > 0 > tr.elo_adjustment(2, t)
    assert tr.elo_adjustment(None, t) == 0.0 and tr.elo_adjustment(999, t) == 0.0


def test_elo_per_goal_is_the_pythagorean_slope():
    tr = ng.GoalieTracker([])
    sv, spg, gpg = tr.league()
    assert (sv, spg, gpg) == (ng.BOOT_SV, ng.BOOT_SHOTS_PG, ng.BOOT_GOALS_PG)
    # one goal per game of prevention at 3.0 goals/game ~ 116 Elo points
    assert abs(ng.ELO_PER_LOGIT * ng.PYTH_EXP / gpg - 115.8) < 0.1


# --- (b) v5 ------------------------------------------------------------------------

def _game(day, h, a, hs, as_, hg=None, ag=None, season="2024"):
    return nb.Game(h, a, season, datetime(2024, 10, 1) + timedelta(days=day, hours=19), hs, as_,
                   home_goalie=hg, away_goalie=ag)


def test_v5_without_goalie_history_equals_v1():
    games = [_game(i, 1 + i % 3, 1 + (i + 1) % 3, 3, 2) for i in range(12)]
    v1, v5 = NHLEloV1(NHLEloConfig(home_advantage=30)), NHLEloV5(NHLEloConfig(home_advantage=30),
                                                                   tracker=ng.GoalieTracker([]))
    for g in games:
        assert abs(v1.predict(g) - v5.predict(g)) < 1e-12
        v1.update(g)
        v5.update(g)
    assert v5.unknown_starters == 24 and v5.priced == 12


def test_v5_prices_a_hot_starter_up_and_keeps_ratings_clean():
    hist = [A(i, 300 + i, 50, 30, 30) for i in range(0, 40, 2)]      # goalie 50: shutouts
    g = _game(45, 1, 2, 3, 2, hg=50, ag=None)
    v1 = NHLEloV1(NHLEloConfig(home_advantage=30))
    v5 = NHLEloV5(NHLEloConfig(home_advantage=30), tracker=ng.GoalieTracker(hist))
    assert v5.predict(g) > v1.predict(g)
    v5.update(g)
    # the home win was partly EXPECTED because of the goalie: a smaller rating gain than v1's
    v1.update(g)
    assert v5.rating(1) - 1500 < v1.rating(1) - 1500


def test_rps_binary_is_brier():
    assert abs(nb.rps_binary([(0.7, 1), (0.2, 0)]) - 0.065) < 1e-12        # ((0.3)^2 + (0.2)^2) / 2


def test_attach_goalies_and_the_v5_gate_report():
    init_db()
    with session_scope() as s:
        comp = _nhl_comp(s)
        teams = [_team(s, f"V5 Team {i}") for i in range(4)]
        mids = []
        gid = 900000
        for season, base in (("2024", datetime(2024, 10, 20)), ("2025", datetime(2025, 10, 20))):
            for i in range(24):
                h, a = teams[i % 4], teams[(i + 1) % 4]
                when = base + timedelta(days=i)
                m = Match(sport=Sport.NHL, competition_id=comp.id, season=season, utc_date=when,
                          status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id,
                          home_score=3 if i % 3 else 1, away_score=2)
                s.add(m)
                s.flush()
                mids.append(m.id)
                gid += 1
                for sd, goalie_id, saves in (("home", 7000 + i % 4, 28), ("away", 7100 + (i + 1) % 4, 26)):
                    s.add(NHLGoalieAppearance(nhl_game_id=gid, match_id=m.id, game_start=when, side=sd,
                                              goalie_id=goalie_id, is_starter=True, shots_against=30, saves=saves))
    games = nb.attach_goalies(nb.load_games())
    mine = [g for g in games if g.match_id in set(mids)]
    assert len(mine) == 48 and all(g.home_goalie is not None and g.away_goalie is not None for g in mine)
    assert nb.starter_coverage(mine) == (48, 48)
    out = CliRunner().invoke(__import__("cli").cli, ["nhl-backtest", "--candidate", "v5"]).output
    assert "GOALIE INPUTS" in out and "both starters known: train" in out
    assert "GOALIE INFORMATION (v1 − v5 log-loss):" in out and "RPS (two-outcome = Brier" in out
    assert "nhl_elo_v5" in out and "GATE VERDICT:" in out
    cov = CliRunner().invoke(__import__("cli").cli, ["nhl-goalie-coverage"]).output
    assert "NHL-GOALIE COVERAGE" in cov and "ALL: both starters identified on" in cov
