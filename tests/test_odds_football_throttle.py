"""ARCHITECT 2026-10-03: sync-odds-football hit the provider's 300/min limit on 431 games (60 unpriced).
Calls are paced below the limit, and a game that still meets a 429 is DEFERRED and retried after the
window — never dropped; odds are stamped at fetch time."""
from datetime import timedelta

import pytest

from src.adapters.api_american_football import RateLimited
from src.adapters.normalized import NormalizedOdds
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, Sport, Team
from src.ingestion import service as svc
from src.timeutil import utc_now_naive


@pytest.fixture
def games():
    init_db()
    with session_scope() as s:
        from sqlalchemy import select
        c = s.execute(select(Competition).where(Competition.code == "THR")).scalar_one_or_none()
        if c is None:
            c = Competition(sport=Sport.NFL, code="THR", name="THR", area="US", type="LEAGUE")
            s.add(c)
        ts = [Team(sport=Sport.NFL, name=f"THR {i}") for i in range(8)]
        s.add_all(ts)
        s.flush()
        ids = []
        for i in range(4):
            m = Match(sport=Sport.NFL, competition_id=c.id, season="2026", status=MatchStatus.SCHEDULED,
                      utc_date=utc_now_naive() + timedelta(days=2, minutes=i), home_team_id=ts[2 * i].id,
                      away_team_id=ts[2 * i + 1].id, external_ids={"api_american_football": f"thr{i}"})
            s.add(m)
            s.flush()
            ids.append(m.id)
    yield ids
    with session_scope() as s:
        s.query(Odds).filter(Odds.match_id.in_(ids)).delete(synchronize_session=False)
        from src.db.schema import OddsSnapshot
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)


def test_paced_and_429_deferred_then_recovered(games, monkeypatch):
    calls, sleeps, t = [], [], [0.0]
    limited = {"thr1": 1, "thr3": 1}                      # one 429 each, then fine

    def list_odds(self, gid):
        calls.append(gid)
        if gid.startswith("thr") and limited.get(gid):
            limited[gid] -= 1
            raise RateLimited("odds", 61)
        return [NormalizedOdds(source="api_american_football", match_source_id=gid, market="1X2", selection=sel,
                               bookmaker="bk", price_decimal=px, captured_at=utc_now_naive()) for sel, px in (("HOME", 1.8), ("AWAY", 2.1))]
    monkeypatch.setattr("src.adapters.api_american_football.APIAmericanFootballAdapter.list_odds", list_odds)
    monkeypatch.setattr(svc, "_odds_sleep", lambda x: (sleeps.append(round(x, 3)), t.__setitem__(0, t[0] + x)))
    monkeypatch.setattr(svc, "_odds_clock", lambda: t[0])
    monkeypatch.setenv("SP_ODDS_FOOTBALL_RPM", "120")     # 0.5 s between calls
    r = svc.sync_odds_nfl()
    mine = [c for c in calls if c.startswith("thr")]
    assert mine == ["thr0", "thr1", "thr2", "thr3", "thr1", "thr3"]          # deferred, retried after the window
    assert 61 in sleeps and all(x <= 0.5 for x in sleeps if x != 61)        # paced; window waited once
    assert r["rate_limited"] >= 2 and r["recovered"] >= 2
    with session_scope() as s:
        priced = {m for (m,) in s.query(Odds.match_id).filter(Odds.match_id.in_(games)).distinct()}
    assert priced == set(games)                                             # nobody dropped


def test_still_limited_after_the_rounds_is_reported_not_silent(games, monkeypatch):
    msgs = []

    def list_odds(self, gid):
        if gid == "thr2":
            raise RateLimited("odds", 5)
        return []
    monkeypatch.setattr("src.adapters.api_american_football.APIAmericanFootballAdapter.list_odds", list_odds)
    monkeypatch.setattr(svc, "_odds_sleep", lambda x: None)
    svc.sync_odds_nfl(progress=msgs.append)
    assert any("still rate limited after 2 retry round(s): 1 game(s) unpriced" in m for m in msgs), msgs
