"""NFL model paths are hard-scoped to Competition.code == "NFL" (2026-09-26).

NCAA football lives under the same Sport.NFL family; before this, every NFL
model path filtered on sport only, so college games entered the ratings walk,
the backtest pot and the prediction set."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Prediction, Sport, Team


@pytest.fixture(scope="module")
def pot():
    init_db()
    now = datetime.utcnow()
    with session_scope() as s:
        # clean slate for the american-football family inside the shared test DB
        for m in s.execute(select(Match).where(Match.sport == Sport.NFL)).scalars():
            s.query(Prediction).filter(Prediction.match_id == m.id).delete()
            s.delete(m)
        s.flush()
        comps = {}
        for code in ("NFL", "NCAA"):
            c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
            if c is None:
                c = Competition(sport=Sport.NFL, code=code, name=code, area="USA", type="LEAGUE")
                s.add(c)
                s.flush()
            comps[code] = c
        nfl = [Team(sport=Sport.NFL, name=f"NFL-{i}", external_ids={"scope_test": f"n{i}"})
               for i in range(32)]
        ncaa = [Team(sport=Sport.NFL, name=f"NCAA-{i}", external_ids={"scope_test": f"c{i}"})
                for i in range(4)]
        s.add_all(nfl + ncaa)
        s.flush()

        def game(comp, h, a, season, when, status=MatchStatus.FINISHED, hs=24, as_=17, stage=None):
            s.add(Match(sport=Sport.NFL, competition_id=comps[comp].id, season=season,
                        stage=stage, utc_date=when, status=status,
                        home_team_id=h.id, away_team_id=a.id,
                        home_score=hs if status == MatchStatus.FINISHED else None,
                        away_score=as_ if status == MatchStatus.FINISHED else None))

        for season, base in (("2024", datetime(2024, 10, 1)), ("2025", datetime(2025, 10, 1))):
            for i in range(0, 32, 2):
                game("NFL", nfl[i], nfl[i + 1], season, base + timedelta(hours=i))
                game("NFL", nfl[i + 1], nfl[i], season, base + timedelta(days=7, hours=i), hs=10, as_=20)
            # college games in the SAME seasons: must never enter the pot
            game("NCAA", ncaa[0], ncaa[1], season, base, hs=56, as_=0)
            game("NCAA", ncaa[2], ncaa[3], season, base, hs=49, as_=3)
        game("NFL", nfl[0], nfl[1], "2025", base - timedelta(days=30), stage="Pre Season")
        game("NFL", nfl[0], nfl[2], "2026", now + timedelta(days=2), status=MatchStatus.SCHEDULED)
        game("NCAA", ncaa[0], ncaa[2], "2026", now + timedelta(days=2), status=MatchStatus.SCHEDULED)
        return {"nfl": [t.id for t in nfl], "ncaa": [t.id for t in ncaa]}


def test_ratings_walk_excludes_ncaa(pot):
    from src.walters.nfl_predict import _current_ratings
    lines = []
    st = _current_ratings(progress=lines.append)
    assert set(st.ratings) == set(pot["nfl"])
    assert not set(st.ratings) & set(pot["ncaa"])
    assert lines == ["scope[ratings]: teams=32, games=64, competitions={NFL}"]


def test_predict_nfl_writes_only_nfl_rows_and_prints_scope(pot):
    from src.walters.nfl_predict import predict_nfl
    lines = []
    assert predict_nfl(progress=lines.append) == 1
    assert lines[0] == "scope[ratings]: teams=32, games=64, competitions={NFL}"
    assert lines[1].startswith("scope[prediction set]: teams=2, games=1, competitions={NFL}")
    with session_scope() as s:
        preds = s.execute(select(Match).join(Prediction, Prediction.match_id == Match.id)
                          .where(Match.sport == Sport.NFL)).scalars().all()
        assert [m.competition.code for m in preds] == ["NFL"]


def test_backtest_pot_excludes_ncaa_and_prints_scope(pot):
    from src.walters.nfl_backtest import run_backtest
    lines = []
    r = run_backtest(progress=lines.append)
    assert lines[0] == "scope[nfl-backtest]: teams=32, games=64, competitions={NFL}"
    assert "warm-up 32 (2024), scored 32 (2025)" in lines[1]
    assert r["ok"] and r["scored_games"] == 32


def test_scope_line_raises_alert_on_contamination(pot):
    from src.walters.nfl_backtest import scope_line
    with session_scope() as s:
        mixed = s.execute(select(Match).where(Match.sport == Sport.NFL,
                                              Match.status == MatchStatus.FINISHED)).scalars().all()
        line = scope_line("probe", mixed)
    assert "competitions={NCAA, NFL}" in line and "SCOPE ALERT" in line
