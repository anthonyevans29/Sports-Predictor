"""ARCHITECT 2026-10-06 (#87 K-track, prediction_history lane): "no prediction history is kept, so model-vs-cost
can't be evaluated per capture ... append (match, model_version, p, computed_at) on every predict run; the window
chain's hourly re-predicts become a stored series." `predictions` stays current-only (S13); every insert is
appended to prediction_history in the same transaction."""
import logging
from datetime import timedelta

import pytest
from sqlalchemy import select

import src.db.database as D
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Prediction, PredictionHistory, Sport, Team
from src.timeutil import utc_now_naive


def _nfl_match(tag, days=2):
    with session_scope() as s:
        c = s.query(Competition).filter_by(code="NFL").one_or_none()
        if c is None:
            c = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="US", type="LEAGUE")
            s.add(c)
            s.flush()
        h, a = Team(sport=Sport.NFL, name=f"Hist {tag} H"), Team(sport=Sport.NFL, name=f"Hist {tag} A")
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.NFL, competition_id=c.id, season="2093", matchday=1,
                  utc_date=utc_now_naive() + timedelta(days=days), status=MatchStatus.SCHEDULED,
                  home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        return m.id


def _history(mid):
    with session_scope() as s:
        return [(r.model_version, r.home_win_prob, r.draw_prob, r.away_win_prob, r.computed_at)
                for r in s.execute(select(PredictionHistory).where(PredictionHistory.match_id == mid)
                                   .order_by(PredictionHistory.id)).scalars()]


def test_every_predict_run_appends_while_predictions_stay_current_only():
    init_db()
    mid = _nfl_match("run")
    from src.walters.nfl_predict import predict_nfl
    predict_nfl(days_ahead=8)
    predict_nfl(days_ahead=8)                                       # the window chain's hourly re-predict
    with session_scope() as s:
        live = s.execute(select(Prediction).where(Prediction.match_id == mid)).scalars().all()
        assert len(live) == 1                                       # S13 unchanged: one current row
        cur = (live[0].model_version, live[0].home_win_prob, live[0].draw_prob, live[0].away_win_prob,
               live[0].computed_at)
    h = _history(mid)
    assert len(h) == 2                                              # both runs kept, as a series
    assert h[-1] == cur                                             # the last entry IS the current prediction
    assert h[0][4] <= h[1][4]


def test_any_write_path_appends_and_a_rollback_leaves_no_history():
    init_db()
    mid = _nfl_match("raw")
    with session_scope() as s:                                      # soccer/MLB write the same way (s.add)
        s.add(Prediction(match_id=mid, model_version="soccer_elo_poisson v22", home_win_prob=0.5, draw_prob=0.25,
                         away_win_prob=0.25))
    assert [x[:4] for x in _history(mid)] == [("soccer_elo_poisson v22", 0.5, 0.25, 0.25)]
    with pytest.raises(RuntimeError):
        with session_scope() as s:
            s.add(Prediction(match_id=mid, model_version="dry", home_win_prob=0.6, away_win_prob=0.4))
            s.flush()
            raise RuntimeError("chain failed")
    assert len(_history(mid)) == 1                                  # same transaction: rolled back together


def test_before_the_migration_predictions_still_write_and_history_is_skipped_loudly(monkeypatch, caplog):
    init_db()
    mid = _nfl_match("nomig")
    monkeypatch.setattr(D, "has_prediction_history", lambda conn: False)
    with caplog.at_level(logging.WARNING):
        with session_scope() as s:
            s.add(Prediction(match_id=mid, model_version="nfl_elo_v1", home_win_prob=0.55, away_win_prob=0.45))
    with session_scope() as s:
        assert s.execute(select(Prediction).where(Prediction.match_id == mid)).scalars().one()
    assert _history(mid) == []
    assert "migrate_prediction_history.py" in caplog.text


def test_migration_is_idempotent_and_prints_a_receipt(capsys):
    init_db()
    import migrate_prediction_history as M
    assert M.main() == 0
    assert M.main() == 0
    out = capsys.readouterr().out
    assert "prediction_history already exists" in out and "prediction_history:" in out


def test_migration_creates_the_table_on_a_db_without_it(tmp_path, monkeypatch, capsys):
    from sqlalchemy import create_engine, inspect
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    Base.metadata.create_all(eng, tables=[t for n, t in Base.metadata.tables.items() if n != "prediction_history"])
    assert not inspect(eng).has_table("prediction_history")
    import migrate_prediction_history as M
    monkeypatch.setattr(M, "get_engine", lambda: eng)
    assert M.main() == 0
    assert inspect(eng).has_table("prediction_history")
    assert "+ Creating prediction_history" in capsys.readouterr().out
