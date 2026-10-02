"""#220 national-team source probe (read-only): league discovery by name (law
1; a target with no match is MISSING, women/youth never counted), the season
cut, the per-competition-season receipt (finished/scored/90-min/venue shares,
neutral keys detected not inferred), the --plan cost, the --max-calls and
data/ refusals, and the UNL-team join. Synthetic API-Football-shaped
responses replayed with --from-dir; the API is never reached."""
import json
import os
import sys
from datetime import datetime

from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import intl_source_probe as isp  # noqa: E402
from src.db.database import init_db, session_scope  # noqa: E402
from src.db.schema import Competition, Match, MatchStatus, Sport, Team  # noqa: E402


def league(lid, name, *years):
    return {"league": {"id": lid, "name": name, "type": "Cup"},
            "seasons": [{"year": y, "start": f"{y - 1}-09-01", "end": f"{y}-07-15"} for y in years]}


LEAGUES = [league(5, "UEFA Nations League", 2018, 2020, 2022), league(10, "Friendlies", 2016, 2019),
           league(32, "World Cup - Qualification Europe", 2018, 2022),
           league(4, "Euro Championship", 2020, 2024), league(960, "Euro Championship - Qualification", 2020),
           league(1, "World Cup", 2018, 2022), league(8, "World Cup - Women", 2019),
           league(9, "Copa America", 2021)]


def fx(fid, home, away, hg, ag, short="FT", venue=None, ft=True, extra=None):
    it = {"fixture": {"id": fid, "date": "2019-06-07T18:45:00+00:00", "status": {"short": short},
                      "venue": venue or {"id": None, "name": None, "city": None}},
          "teams": {"home": {"id": home}, "away": {"id": away}},
          "goals": {"home": hg, "away": ag},
          "score": {"fulltime": {"home": hg if ft else None, "away": ag if ft else None}}}
    it.update(extra or {})
    return it


def test_discover_by_name_cuts_seasons_and_drops_women():
    d = isp.discover(LEAGUES, datetime(2018, 1, 1).date())
    t = d["targets"]
    assert [(lid, [s["year"] for s in ss]) for lid, _, ss in t["NATIONS_LEAGUE"]] == [(5, [2018, 2020, 2022])]
    assert [s["year"] for s in t["FRIENDLIES"][0][2]] == [2019]          # 2016 ended before the cut
    assert t["EURO"][0][0] == 4 and t["EURO_Q"][0][0] == 960 and t["WCQ"][0][0] == 32
    assert 8 not in d["names"]                                            # women never counted
    assert [o[0] for o in d["others"]] == [9, 1]                          # offered, not fetched
    assert len(isp.plan(d)) == 3 + 1 + 2 + 2 + 1


def test_missing_target_is_reported_not_guessed():
    d = isp.discover([league(10, "Friendlies", 2019)], datetime(2018, 1, 1).date())
    assert d["targets"]["WCQ"] == [] and d["targets"]["EURO"] == []


def test_season_receipt_counts_and_detects_neutral_keys():
    r = isp.season_receipt([
        fx(1, 100, 200, 2, 1, venue={"id": 7, "name": "Stadion", "city": "Wien"}),
        fx(2, 200, 300, 1, 1, short="AET", ft=False, venue={"id": None, "name": "X", "city": None}),
        fx(3, 300, 100, None, None, short="FT"),                         # finished, no goals: not scored
        fx(4, 100, 300, None, None, short="PST"),
        fx(5, 400, 100, 0, 3, extra={"neutral": True})])
    assert (r["fixtures"], r["finished"], r["scored"], r["teams"]) == (5, 4, 3, 4)
    assert r["score_90"] == 2 / 3 and r["venue_id"] == 1 / 3 and r["venue_name"] == 2 / 3
    assert r["neutral_keys"] == ["neutral"] and r["status"] == {"FT": 3, "AET": 1, "PST": 1}
    assert isp.team_results({(5, 2019): [fx(1, 100, 200, 2, 1), fx(4, 100, 300, None, None, short="PST")]}) \
        == {"100": 1, "200": 1}


def _save(tmp_path, leagues, fixtures):
    json.dump({"response": {"subscription": {"plan": "Pro", "active": True},
                            "requests": {"current": 3, "limit_day": 7500}}}, open(tmp_path / "status.json", "w"))
    json.dump({"response": leagues}, open(tmp_path / "leagues.json", "w"))
    for (lid, year), rows in fixtures.items():
        json.dump({"response": rows}, open(tmp_path / f"fixtures_{lid}_{year}.json", "w"))


def test_replay_end_to_end_with_unl_join(tmp_path, capsys):
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "UNL")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.SOCCER, code="UNL", name="UEFA Nations League", area="World", type="CUP")
            s.add(comp)
            s.flush()
        a = Team(sport=Sport.SOCCER, name="Probe Nation A", external_ids={"api_football": "99001"})
        b = Team(sport=Sport.SOCCER, name="Probe Nation B", external_ids={})
        s.add_all([a, b])
        s.flush()
        s.add(Match(sport=Sport.SOCCER, competition_id=comp.id, season="2079/80", utc_date=datetime(2079, 9, 1),
                    status=MatchStatus.SCHEDULED, home_team_id=a.id, away_team_id=b.id))
    lg = [league(5, "UEFA Nations League", 2020), league(10, "Friendlies", 2019)]
    _save(tmp_path, lg, {(5, 2020): [fx(11, 99001, 99002, 1, 0)], (10, 2019): [fx(12, 99002, 99001, 2, 2)]})
    assert isp.main(["--from-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "plan 'Pro'" in out and "WCQ: MISSING" in out
    assert "TOTAL: 2 fixtures · 2 scored results · 2 competition-seasons" in out
    assert "NEUTRAL FLAG: NONE" in out
    assert "UNL -> 5: discovered as 'UEFA Nations League'" in out
    assert "OUR UNL TEAMS (" in out
    # the shared test DB may hold other UNL teams: compare against a zero-result pool
    with session_scope() as s:
        base = isp.unl_coverage(s, isp.team_results({}))["results_per_team"]
        got = isp.unl_coverage(s, isp.team_results({(10, 2019): [fx(12, 99002, 99001, 2, 2),
                                                                 fx(13, 99001, 99003, 1, 0)]}))["results_per_team"]
    assert got.get("1-9", 0) == base.get("1-9", 0) + 1 and got.get("0", 0) == base["0"] - 1   # A: 2 results
    assert base.get("no api_football id", 0) >= 1                                              # B: no id, never guessed


def test_plan_stops_before_fixtures_and_refusals(tmp_path, capsys):
    _save(tmp_path, LEAGUES, {})
    assert isp.main(["--from-dir", str(tmp_path), "--plan", "--no-db"]) == 0
    assert "COST: 9 fixture calls" in capsys.readouterr().out
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert isp.main(["--save", os.path.join(root, "data", "x"), "--no-db"]) == 2
