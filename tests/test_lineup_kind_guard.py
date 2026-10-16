"""Q9 (ARCHITECT 2026-10-15, addendum 75 item 2): the match page reads the lineup kinds sync-lineups writes
(training.LIVE_LINEUP_KINDS); a finished cup fixture's 'history' rows (sync-lineups-history, #538) never show as its
lineup. On the throwaway test DB."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Lineup, Match, MatchStatus, Sport, Team
from src.web.app import app

HOST = "127.0.0.1:8000"


@pytest.fixture
def client():
    return TestClient(app, base_url=f"http://{HOST}", client=("127.0.0.1", 50000))


def _fixture(kinds):
    """A finished cup fixture whose home side holds one starter per kind given, named after the kind."""
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code=f"QG{len(kinds)}", name="Q9 Cup", area="X", type="CUP")
        h, a = Team(sport=Sport.SOCCER, name="Q9 Home"), Team(sport=Sport.SOCCER, name="Q9 Away")
        s.add_all([comp, h, a])
        s.flush()
        m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2091/92", utc_date=datetime(2091, 9, 1, 19),
                  status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=1, away_score=0)
        s.add(m)
        s.flush()
        s.add_all(Lineup(match_id=m.id, team_id=h.id, kind=k, is_starter=True, player_name=f"Player{k.title()}")
                  for k in kinds)
        return m.id


def test_the_match_page_shows_the_confirmed_lineup_and_never_a_history_row(client):
    mid = _fixture(["confirmed", "history"])
    html = client.get(f"/matches/{mid}").text
    assert "PlayerConfirmed" in html and "PlayerHistory" not in html


def test_history_rows_alone_show_no_lineup(client):
    mid = _fixture(["history"])
    r = client.get(f"/matches/{mid}")
    assert r.status_code == 200 and "PlayerHistory" not in r.text
