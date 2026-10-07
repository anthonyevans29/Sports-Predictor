"""ARCHITECT 2026-10-07 (daily-class): sync-pitchers printed "4/3 games with probable pitchers": the numerator
counted every game on the date's slate (the batch covers started games too), the denominator only this run's
upcoming games. Both now count the upcoming games; the slate total is printed apart."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchParticipant, MatchStatus, Sport, Team
from src.ingestion.service import IngestionService
from src.timeutil import utc_now_naive

SRC = "pitchers_test_src"
CODE = "SPC1"


@pytest.fixture(autouse=True, scope="module")
def _cleanup():
    yield
    with session_scope() as s:
        cids = [c.id for c in s.execute(select(Competition).where(Competition.code == CODE)).scalars()]
        mids = [m.id for m in s.execute(select(Match).where(Match.competition_id.in_(cids))).scalars()]
        s.query(MatchParticipant).filter(MatchParticipant.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(mids)).delete(synchronize_session=False)


class FakeAdapter:
    source_name = SRC

    def __init__(self, batch):
        self.batch = batch

    def get_probable_pitchers(self, source_id):
        return self.batch.get(str(source_id))

    def get_probable_pitchers_for_date(self, date_iso):
        return self.batch


def _p(n):
    return {"home": {"player_id": f"h{n}", "name": f"Home P{n}"}, "away": {"player_id": f"a{n}", "name": f"Away P{n}"}}


def test_the_count_is_upcoming_games_with_probables_over_upcoming_games():
    init_db()
    day = (utc_now_naive() + timedelta(days=2)).replace(hour=20, minute=0, second=0, microsecond=0)
    with session_scope() as s:
        c = Competition(sport=Sport.MLB, code=CODE, name=CODE, area="US", type="LEAGUE")
        s.add(c)
        s.flush()
        for i in range(3):
            h = Team(sport=Sport.MLB, name=f"{CODE} H{i}")
            a = Team(sport=Sport.MLB, name=f"{CODE} A{i}")
            s.add_all([h, a])
            s.flush()
            s.add(Match(sport=Sport.MLB, competition_id=c.id, season="2091", utc_date=day + timedelta(hours=i),
                        status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id,
                        external_ids={SRC: f"g{i}"}))
    # the date's slate: two of this run's three upcoming games, plus two already started (not in the run)
    batch = {"g0": _p(0), "g1": _p(1), "started1": _p(8), "started2": _p(9)}
    logs: list[str] = []
    r = IngestionService(FakeAdapter(batch)).sync_pitchers(CODE, "2091", on_log=logs.append)
    line = next(x for x in logs if "with probable pitchers" in x)
    assert "2/3 upcoming games with probable pitchers (4 on the date's slate)" in line, line
    assert r.created == 4 and r.skipped == 1
