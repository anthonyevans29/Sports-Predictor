"""#387 (ARCHITECT addendum 31 item 1): "sync_odds orders its candidates by
kickoff, then id, before the limit is applied, so that the limit means the
next N. --match-ids is unchanged." Throwaway DB, fake adapter, private code."""
from datetime import datetime, timedelta

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team

NOW = datetime(2039, 5, 1, 12, 0)


class RecordingOddsAdapter:
    source_name = "fakeodds"

    def __init__(self):
        self.asked = []

    def list_odds(self, source_id):
        self.asked.append(source_id)
        return []                       # nothing priced into the DB; the ask is the receipt


def test_limit_prices_the_next_n_by_kickoff(monkeypatch):
    from src.ingestion import service as svc
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code="SNN1", name="SNN1", area="X", type="LEAGUE")
        h, a = Team(sport=Sport.SOCCER, name="SNN1 H"), Team(sport=Sport.SOCCER, name="SNN1 A")
        s.add_all([comp, h, a])
        s.flush()
        # stored OUT of kickoff order: the latest game gets the lowest id
        for gid, hours in (("late", 30), ("mid", 6), ("early", 2)):
            s.add(Match(sport=Sport.SOCCER, competition_id=comp.id, season="2038/39",
                        utc_date=NOW + timedelta(hours=hours), status=MatchStatus.SCHEDULED,
                        home_team_id=h.id, away_team_id=a.id, external_ids={"fakeodds": gid}))
            s.flush()
    monkeypatch.setattr(svc, "utc_now_naive", lambda: NOW)
    ad = RecordingOddsAdapter()
    svc.IngestionService(ad).sync_odds("SNN1", limit=2)
    assert ad.asked == ["early", "mid"]          # the two earliest kickoffs, in kickoff order
