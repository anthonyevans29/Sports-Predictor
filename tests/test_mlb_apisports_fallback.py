"""MLB PHASE A (architect 2026-09-29): the api-sports Baseball fallback for MLB
sync-matches/results, on a fake provider and the throwaway test DB. Pins:
engagement by SP_SKIP_FAMILIES; stage never from the provider's `week`;
conservative status mapping; exhibitions never ingested; idempotence; no
FINISHED downgrade; doubleheader game 2 marked, never fabricated; a statsapi
team is stamped, never renamed; ambiguity is held, never guessed."""
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Result, Sport, Team
from src.ingestion import mlb_apisports as fb

T = datetime(2031, 7, 4, 17, 5)


class FakeClient:
    requests_remaining = 99

    def __init__(self, teams, games):
        self.teams, self.games, self.calls = teams, games, []

    def list_teams(self, season):
        self.calls.append(("teams", season))
        return self.teams

    def _get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        return {"response": self.games}


def g(gid, home, away, at, short="FT", hr=5, ar=3, week="Regular Season"):
    return {"id": gid, "date": at.strftime("%Y-%m-%dT%H:%M:%S+00:00"), "week": week,
            "status": {"short": short, "long": short},
            "teams": {"home": {"id": home[0], "name": home[1]}, "away": {"id": away[0], "name": away[1]}},
            "scores": {"home": {"total": hr}, "away": {"total": ar}}}


@pytest.fixture(scope="module", autouse=True)
def mlb_comp():
    init_db()
    with session_scope() as s:
        if s.execute(select(Competition).where(Competition.sport == Sport.MLB,
                                               Competition.code == "MLB")).scalars().first() is None:
            s.add(Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA",
                              type="LEAGUE", external_ids={"mlb_stats_api": "MLB"}))


def _rows(season):
    with session_scope() as s:
        return {m.external_ids.get(fb.SOURCE) or f"ours{m.id}": {
            "id": m.id, "status": m.status, "stage": m.stage, "raw": m.status_raw,
            "score": (m.away_score, m.home_score), "ftr": m.full_time_result,
            "note": (m.external_ids or {}).get(fb.NOTE_KEY)}
            for m in s.execute(select(Match).join(Competition).where(
                Competition.code == "MLB", Match.season == season)).scalars()}


def test_engagement_is_sp_skip_families_naming_mlb_only():
    assert fb.fallback_engaged("MLB", {"SP_SKIP_FAMILIES": "NFL, mlb"})
    assert not fb.fallback_engaged("MLB", {"SP_SKIP_FAMILIES": "NFL"})
    assert not fb.fallback_engaged("MLB", {})
    assert not fb.fallback_engaged("MLB_SPRING", {"SP_SKIP_FAMILIES": "MLB"})
    assert not fb.fallback_engaged("NHL", {"SP_SKIP_FAMILIES": "MLB"})


YAN, BOS, LAD, SDP = (1, "New York Yankees"), (2, "Boston Red Sox"), (3, "Los Angeles Dodgers"), (4, "San Diego Padres")
AL, NL = (90, "American League"), (91, "National League")


def test_host_shape_creates_history_conservatively_and_is_idempotent():
    teams = [{"id": i, "name": n, "code": None} for i, n in (YAN, BOS, LAD, SDP, AL, NL)]
    games = [g(11, YAN, BOS, T),                                                  # regular final
             g(12, LAD, SDP, T + timedelta(days=95), hr=4, ar=2, week="Final"),   # WC or WS: stage stays NULL
             g(13, YAN, BOS, T + timedelta(days=1), short="NS", hr=None, ar=None),
             g(14, LAD, SDP, T + timedelta(days=2), short="POST", hr=None, ar=None),
             g(15, BOS, YAN, T + timedelta(days=3), short="INTR", hr=2, ar=1),    # unmapped: stays scheduled
             g(16, BOS, YAN, T + timedelta(days=4), hr=None, ar=None),            # FT without totals
             g(17, AL, NL, T + timedelta(days=10)),                              # all-star: never
             g(18, YAN, LAD, T - timedelta(days=100), week="Spring Training")]   # exhibition: never
    cl = FakeClient(teams, games)
    r = fb.sync_matches(cl, "2031")
    assert cl.calls[:2] == [("teams", 2031), ("games", {"league": 1, "season": 2031})]   # teams first, ONE /games
    assert r["teams"]["created"] == 4 and r["teams"]["non_club_skipped"] == ["American League", "National League"]
    assert r["created"] == 6 and r["exhibition_skipped"] == 2 and r["stage_null_created"] == 6
    assert r["finished"] == 2 and r["unmapped_status"] == {"NS": 1, "INTR": 1}
    assert r["known_limitation"].startswith("doubleheader game 2 is absent")
    rows = _rows("2031")
    assert {k for k in rows} == {"11", "12", "13", "14", "15", "16"}
    assert all(v["stage"] is None for v in rows.values())                         # never the provider's week
    assert rows["11"]["status"] == MatchStatus.FINISHED and rows["11"]["score"] == (3, 5)
    assert rows["11"]["ftr"] == Result.HOME and rows["12"]["ftr"] == Result.HOME
    assert rows["14"]["status"] == MatchStatus.POSTPONED
    assert rows["15"]["status"] == MatchStatus.SCHEDULED and rows["15"]["raw"] == "INTR"
    assert rows["16"]["status"] == MatchStatus.SCHEDULED and rows["16"]["score"] == (None, None)
    # idempotent re-run; and a FINISHED row is never downgraded by a later listing
    games[0] = g(11, YAN, BOS, T, short="NS", hr=None, ar=None)
    r2 = fb.sync_matches(FakeClient(teams, games), "2031")
    assert r2["created"] == 0 and r2["teams"]["created"] == 0 and r2["downgrade_refused"] == 1
    assert _rows("2031")["11"]["status"] == MatchStatus.FINISHED
    # a date window filters locally (still one provider call)
    r3 = fb.sync_matches(FakeClient(teams, games), "2031", "2031-07-05", "2031-07-05")
    assert r3["updated"] == 1 and r3["created"] == 0


STL, CHC, MIA, ATL = (21, "St.Louis Cardinals"), (22, "Chicago Cubs"), (23, "Miami Marlins"), (24, "Atlanta Braves")


def test_statsapi_rows_are_linked_stage_kept_dh_game2_marked_never_fabricated():
    U = datetime(2032, 7, 4, 17, 5)
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "MLB")).scalars().first()
        t = {}
        for sid, name in ((121, "St. Louis Cardinals"), (122, "Chicago Cubs"),
                          (123, "Miami Marlins"), (124, "Atlanta Braves")):
            t[name] = Team(sport=Sport.MLB, name=name, external_ids={"mlb_stats_api": str(sid)})
            s.add(t[name])
        s.flush()

        def m(pk, home, away, at, stage, status=MatchStatus.FINISHED, hs=5, as_=3):
            s.add(Match(sport=Sport.MLB, competition_id=comp.id, season="2032", stage=stage, utc_date=at,
                        status=status, home_team_id=t[home].id, away_team_id=t[away].id,
                        home_score=hs, away_score=as_, external_ids={"mlb_stats_api": pk}))
        m("g1", "St. Louis Cardinals", "Chicago Cubs", U, "F")                              # DH game 1
        m("g2", "St. Louis Cardinals", "Chicago Cubs", U + timedelta(hours=6), "F", hs=1, as_=2)   # DH game 2
        m("g3", "Miami Marlins", "Atlanta Braves", U, "R", status=MatchStatus.SCHEDULED, hs=None, as_=None)
    teams = [{"id": i, "name": n, "code": None} for i, n in (STL, CHC, MIA, ATL)]
    games = [g(31, STL, CHC, U + timedelta(minutes=10)),                     # game 2 absent (the limitation)
             g(32, MIA, ATL, U - timedelta(hours=2), short="NS", hr=None, ar=None),   # equidistant pair:
             g(33, MIA, ATL, U + timedelta(hours=2), short="NS", hr=None, ar=None)]   # AMBIGUOUS, held
    r = fb.sync_matches(FakeClient(teams, games), "2032")
    assert r["teams"]["stamped"] == 4 and r["teams"]["created"] == 0
    with session_scope() as s:
        names = {x.name for x in s.execute(select(Team).where(
            Team.external_ids["mlb_stats_api"].as_string().in_(["121", "122", "123", "124"]))).scalars()}
    assert "St. Louis Cardinals" in names and "St.Louis Cardinals" not in names       # stamped, never renamed
    assert r["linked_existing"] == 1 and r["created"] == 0 and r["ambiguous"] == 1
    assert r["held_near_unkeyed"] == 2                                               # never a duplicate
    assert [d["game"] for d in r["dh_marked"]] == ["Chicago Cubs @ St. Louis Cardinals"]
    rows = _rows("2032")
    assert rows["31"]["stage"] == "F" and rows["31"]["score"] == (3, 5)              # our stage kept
    game2 = [v for k, v in rows.items() if k.startswith("ours") and v["note"]]
    assert len(game2) == 1 and game2[0]["note"] == "apisports-unavailable"
    assert game2[0]["score"] == (2, 1) and game2[0]["status"] == MatchStatus.FINISHED  # untouched
    assert len(rows) == 3                                                            # nothing fabricated


def test_cli_routes_mlb_to_the_fallback_only_when_engaged(monkeypatch):
    import cli as climod
    from src.adapters import api_baseball
    teams = [{"id": i, "name": n, "code": None} for i, n in (YAN, BOS)]
    monkeypatch.setattr(api_baseball.APIBaseballClient, "from_env",
                        classmethod(lambda cls: FakeClient(teams, [g(41, YAN, BOS, T + timedelta(days=30))])))
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    out = CliRunner().invoke(climod.cli, ["sync-matches", "--competition", "MLB", "--season", "2031"])
    assert out.exit_code == 0, out.output
    assert "FALLBACK" in out.output and "MLB-FALLBACK-RECEIPT {" in out.output
    assert "KNOWN LIMITATION: doubleheader game 2" in out.output
    monkeypatch.setenv("SP_SKIP_FAMILIES", "NFL")
    called = []
    monkeypatch.setattr(climod, "_mlb_fallback_run", lambda *a, **k: called.append(a))
    monkeypatch.setattr(climod, "IngestionService", lambda adapter: type(
        "S", (), {"sync_matches": lambda self, *a, **k: "statsapi"})())
    assert CliRunner().invoke(climod.cli, ["sync-matches", "--competition", "MLB", "--season", "2031"]).exit_code == 0
    assert called == []


def test_mlb_history_chain_is_sync_only():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import chains
    steps = chains.CHAINS["mlb-history"]["steps"]
    assert [s[0] for s in steps] == ["sync-competitions", "sync-matches"]
    assert chains.CHAINS["mlb-history"]["backup"] == "daily"
    assert not any(s[0] in ("predict", "evaluate", "improve", "export-predictions") for s in steps)
