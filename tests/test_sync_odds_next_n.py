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


def _store_three(code):
    """Three upcoming games stored OUT of kickoff order: the latest gets the lowest id."""
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code=code, name=code, area="X", type="LEAGUE")
        h, a = Team(sport=Sport.SOCCER, name=f"{code} H"), Team(sport=Sport.SOCCER, name=f"{code} A")
        s.add_all([comp, h, a])
        s.flush()
        ids = {}
        for gid, hours in (("late", 30), ("mid", 6), ("early", 2)):
            s.add(Match(sport=Sport.SOCCER, competition_id=comp.id, season="2038/39",
                        utc_date=NOW + timedelta(hours=hours), status=MatchStatus.SCHEDULED,
                        home_team_id=h.id, away_team_id=a.id, external_ids={"fakeodds": f"{code}-{gid}"}))
            s.flush()
        for m in s.query(Match).filter(Match.competition_id == comp.id):
            ids[m.external_ids["fakeodds"].split("-", 1)[1]] = m.id
    return ids


def test_limit_prices_the_next_n_by_kickoff(monkeypatch):
    from src.ingestion import service as svc
    _store_three("SNN1")
    monkeypatch.setattr(svc, "utc_now_naive", lambda: NOW)
    ad = RecordingOddsAdapter()
    svc.IngestionService(ad).sync_odds("SNN1", limit=2)
    assert ad.asked == ["SNN1-early", "SNN1-mid"]   # the two earliest kickoffs, in kickoff order


def test_match_ids_selection_is_unchanged(monkeypatch):
    """--match-ids is unchanged: a named list longer than the limit keeps main's
    selection (storage order), not the kickoff order (Codex on #402)."""
    from src.ingestion import service as svc
    ids = _store_three("SNN2")
    monkeypatch.setattr(svc, "utc_now_naive", lambda: NOW)
    ad = RecordingOddsAdapter()
    svc.IngestionService(ad).sync_odds("SNN2", limit=2, match_ids=set(ids.values()))
    assert ad.asked == ["SNN2-late", "SNN2-mid"]
