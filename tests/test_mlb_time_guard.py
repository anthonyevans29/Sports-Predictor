"""MLB start-time guard (architect 2026-10-01, card finding: host PHI@ATL G3
14:00 ET vs statsapi 20:00 ET). The api-sports fallback never overwrites a
statsapi-sourced time; a disagreement is receipted and stamped; the card flags
"time unconfirmed" (disagreement, or an api-sports-only time); the read-only
mlb-time-audit compares the two feeds' postseason times."""
from datetime import datetime, timedelta

from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team
from src.ingestion import mlb_apisports as fb

U = datetime(2073, 10, 8, 0, 0)          # 20:00 ET
PH = U - timedelta(hours=6)             # an api-sports 14:00 ET placeholder


class FakeClient:
    requests_remaining = 9

    def __init__(self, teams, games):
        self.teams, self.games = teams, games

    def list_teams(self, season):
        return self.teams

    def _get(self, path, params=None):
        return {"response": self.games}


def g(gid, home, away, at, short="NS"):
    return {"id": gid, "date": at.strftime("%Y-%m-%dT%H:%M:%S+00:00"), "week": "Final",
            "status": {"short": short, "long": short},
            "teams": {"home": {"id": home[0], "name": home[1]}, "away": {"id": away[0], "name": away[1]}},
            "scores": {"home": {"total": None}, "away": {"total": None}}}


ATL, PHI, LAD, SDP = (71, "Atlanta Braves"), (72, "Philadelphia Phillies"), (73, "Los Angeles Dodgers"), (74, "San Diego Padres")


def _setup():
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.sport == Sport.MLB,
                                                   Competition.code == "MLB")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA",
                               type="LEAGUE", external_ids={"mlb_stats_api": "MLB"})
            s.add(comp)
            s.flush()
        t = {}
        for sid, name in ((921, "Atlanta Braves"), (922, "Philadelphia Phillies")):
            t[name] = Team(sport=Sport.MLB, name=name, external_ids={"mlb_stats_api": str(sid)})
            s.add(t[name])
        s.flush()
        m = Match(sport=Sport.MLB, competition_id=comp.id, season="2073", stage="D", utc_date=U,
                  status=MatchStatus.SCHEDULED, home_team_id=t["Atlanta Braves"].id,
                  away_team_id=t["Philadelphia Phillies"].id, external_ids={"mlb_stats_api": "777"})
        s.add(m)
        s.flush()
        return m.id


def test_statsapi_time_is_never_overwritten_and_the_conflict_is_receipted():
    mid = _setup()
    teams = [{"id": i, "name": n, "code": None} for i, n in (ATL, PHI, LAD, SDP)]
    games = [g(501, ATL, PHI, PH), g(502, LAD, SDP, U + timedelta(days=1))]     # 502: api-sports only
    r = fb.sync_matches(FakeClient(teams, games), "2073")
    assert r["linked_existing"] == 1 and r["time_kept_statsapi"] == 1
    assert r["time_conflicts"] == [{"match_id": mid, "game": "Philadelphia Phillies @ Atlanta Braves",
                                    "statsapi": U.isoformat(), "api_sports": PH.isoformat(), "delta_h": -6.0}]
    with session_scope() as s:
        m = s.get(Match, mid)
        assert m.utc_date == U                                           # statsapi's time stands
        assert m.external_ids[fb.TIME_KEY] == PH.isoformat()
        assert fb.time_unconfirmed(m) == "time unconfirmed (api-sports says 2073-10-07T18:00Z)"
        other = s.execute(select(Match).where(Match.season == "2073", Match.id != mid)).scalars().one()
        assert other.utc_date == U + timedelta(days=1)
        assert fb.time_unconfirmed(other) == "time unconfirmed (api-sports only)"
    # api-sports corrects itself → the stamp clears and the card stops flagging
    games[0] = g(501, ATL, PHI, U)
    r2 = fb.sync_matches(FakeClient(teams, games), "2073")
    assert r2["time_conflicts"] == []
    with session_scope() as s:
        m = s.get(Match, mid)
        assert fb.TIME_KEY not in m.external_ids and fb.time_unconfirmed(m) is None


def test_time_audit_pairs_feeds_and_reads_the_placeholder_signature():
    stats = fb.statsapi_rows({"dates": [{"games": [
        {"gamePk": 1, "gameDate": "2073-10-08T00:00:00Z", "gameType": "D",
         "status": {"startTimeTBD": False, "detailedState": "Scheduled"},
         "teams": {"home": {"team": {"name": "Atlanta Braves"}}, "away": {"team": {"name": "Philadelphia Phillies"}}}},
        {"gamePk": 2, "gameDate": "2073-10-09T00:07:00Z", "gameType": "D",
         "status": {"startTimeTBD": True, "detailedState": "Scheduled"},
         "teams": {"home": {"team": {"name": "Los Angeles Dodgers"}}, "away": {"team": {"name": "San Diego Padres"}}}},
        {"gamePk": 3, "gameDate": "2073-10-10T23:00:00Z", "gameType": "L",
         "status": {"startTimeTBD": False, "detailedState": "Scheduled"},
         "teams": {"home": {"team": {"name": "Atlanta Braves"}}, "away": {"team": {"name": "Los Angeles Dodgers"}}}},
    ]}]})
    prov = fb.provider_rows([g(501, ATL, PHI, PH), g(502, LAD, SDP, datetime(2073, 10, 8, 18, 0)),
                             g(503, ATL, LAD, datetime(2073, 10, 10, 23, 0))])
    r = fb.time_audit(stats, prov)
    assert (r["paired"], r["exact"], r["mismatched"], r["mismatched_tbd"], r["tbd_total"]) == (3, 1, 2, 1, 1)
    assert r["placeholder_times_utc"] == {"18:00": 2}
    assert [x["delta_h"] for x in r["rows"]] == [-6.0, -6.12, 0.0]


def test_card_carries_the_time_flag_and_the_pager_shows_it(tmp_path):
    import importlib, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    page = importlib.import_module("sp_window_page")
    from src.walters.window import build_card
    with session_scope() as s:                       # a recorded disagreement on the statsapi row
        m = s.execute(select(Match).where(Match.season == "2073", Match.stage == "D")).scalars().one()
        m.external_ids = {**m.external_ids, fb.TIME_KEY: PH.isoformat()}
    card = build_card(now=U - timedelta(hours=8), hours=24, export_dir=str(tmp_path))
    row = next(r for r in card["fixtures"] if r["home_team"] == "Atlanta Braves" and r["utc_date"].startswith("2073"))
    assert row["time_flag"] == "time unconfirmed (api-sports says 2073-10-07T18:00Z)"
    assert card["receipts"]["time_unconfirmed"] >= 1
    snap = page.snapshot({"fixtures": [dict(row, time_flag="time unconfirmed (api-sports only)")]})
    g0 = next(iter(snap.values()))
    assert "⚠ time unconfirmed" in page.digest(snap)
    assert page.line({"cls": "new_priced", "id": "1", "g": g0}).split("\n")[0].endswith("· ⚠ time unconfirmed")


def test_cli_time_audit_prints_receipt(monkeypatch):
    from click.testing import CliRunner
    import cli
    from src.adapters import api_baseball, mlb_stats_api
    monkeypatch.setattr(api_baseball.APIBaseballClient, "from_env",
                        classmethod(lambda cls: FakeClient([], [g(501, ATL, PHI, PH)])))
    monkeypatch.setattr(mlb_stats_api.MLBStatsAPIAdapter, "_get", lambda self, path, params=None: {"dates": [{"games": [
        {"gamePk": 1, "gameDate": "2073-10-08T00:00:00Z", "gameType": "D", "status": {"startTimeTBD": True},
         "teams": {"home": {"team": {"name": "Atlanta Braves"}}, "away": {"team": {"name": "Philadelphia Phillies"}}}}]}]})
    out = CliRunner().invoke(cli.cli, ["mlb-time-audit", "--season", "2073"]).output
    assert "MISMATCHED 1 (statsapi TBD among them 1" in out and "(-6.00h" in out and "MLB-TIME-AUDIT " in out, out
