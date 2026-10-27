"""#706 (ARCHITECT 2026-10-27 08:20 ET): "Both read the database read-only (prediction_outcomes, mode=ro) as the primary
source, the closing files beside, export files secondary; a receipt line says which source it read."

results-tally's MLB and PL sections and its NFL section read through database.readonly_scope (a mode=ro open of the file
the app's sessions are bound to), and each section carries a Source line. The PL positive-edge receipt's own tests are
in tests/test_pl_positive_edge_receipt.py."""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    from src.db import database
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{tmp_path / 'iso.db'}", future=True)
    Base.metadata.create_all(eng)
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True, expire_on_commit=False))
    monkeypatch.chdir(tmp_path)
    yield tmp_path / "iso.db"
    eng.dispose()


def test_readonly_scope_reads_the_bound_file_and_refuses_a_write(iso_db):
    from sqlalchemy.exc import OperationalError

    from src.db.database import readonly_scope
    before = iso_db.read_bytes()
    with readonly_scope() as s:
        assert s.execute(text("SELECT count(*) FROM matches")).scalar() == 0
        with pytest.raises(OperationalError, match="readonly"):
            s.execute(text("DELETE FROM matches"))
    assert iso_db.read_bytes() == before


def test_readonly_scope_refuses_a_missing_file_and_never_creates_it(tmp_path, monkeypatch):
    from src.db import database
    missing = tmp_path / "no" / "such.db"
    eng = create_engine(f"sqlite:///{missing}", future=True)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng, future=True))
    with pytest.raises(database.ReadOnlyRefused, match="no DB file"):
        with database.readonly_scope():
            pass
    assert not missing.exists() and not missing.parent.exists()


def test_results_tally_cli_exits_2_on_a_missing_db(tmp_path, monkeypatch):
    from click.testing import CliRunner

    import cli
    from src.db import database
    missing = tmp_path / "gone.db"
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=create_engine(f"sqlite:///{missing}", future=True), future=True))
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(cli.cli, ["results-tally"])
    assert r.exit_code == 2 and "REFUSED: no DB file" in r.output
    assert not missing.exists() and not (tmp_path / "RESULTS.md").exists()


def test_each_section_says_which_source_it_read(iso_db, monkeypatch):
    import math

    import src.walters.nfl_predict as nfp

    from src.db.database import session_scope
    from src.db.schema import (Competition, Match, MatchStatus, Prediction, PredictionOutcome, Result, Sport,
                               Team)
    from src.walters.export import results_tally
    from src.timeutil import utc_now_naive
    ko = utc_now_naive() - timedelta(days=2)
    with session_scope() as s:
        c = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="USA", type="LEAGUE")
        h, a = Team(sport=Sport.MLB, name="H"), Team(sport=Sport.MLB, name="A")
        s.add_all([c, h, a])
        s.flush()
        m = Match(sport=Sport.MLB, competition_id=c.id, season="2026", utc_date=ko, status=MatchStatus.FINISHED,
                  home_team_id=h.id, away_team_id=a.id, home_score=5, away_score=3)
        s.add(m)
        s.flush()
        p = Prediction(match_id=m.id, model_version="t", home_win_prob=0.6, away_win_prob=0.4)
        s.add(p)
        s.flush()
        s.add(PredictionOutcome(prediction_id=p.id, actual_result=Result.HOME, actual_home_score=5,
                                actual_away_score=3, top_pick_hit=True, log_loss=-math.log(0.6)))
    seen = []
    monkeypatch.setattr(nfp, "grade_nfl", lambda days_back=None, exports_dir="exports", readonly=False: seen.append(
        readonly) or {"ok": True, "games": 1, "decided": 1, "pushes": 0, "hits": 1, "logloss": 0.6, "mean_clv_pp": None,
                      "value_side_n": 0, "mean_value_side_clv_pp": None, "value_shadow_n": 0,
                      "mean_value_shadow_clv_pp": None})
    before = iso_db.read_bytes()
    out = iso_db.parent / "RESULTS.md"
    results_tally(days=30, out_path=str(out))
    txt = out.read_text()
    mlb = txt.split("## MLB", 1)[1].split("\n## ", 1)[0]
    pl = txt.split("## Soccer (PL)", 1)[1].split("\n## ", 1)[0]
    nfl = txt.split("## NFL (live since Week 3, 2026-09-22)", 1)[1].split("\n## ", 1)[0]
    assert "- Sides: **1/1**" in mlb
    for sec in (mlb, pl):                                       # PL: "No graded games in window." still says it
        assert "- Source: the database, read-only (mode=ro): prediction_outcomes of the matches from " in sec
        assert "(rolling 30 days); a game void by the closing files on disk left out; no export file read" in sec
    assert "No graded games in window." in pl
    assert seen == [True]                                       # the NFL section asks grade_nfl for the mode=ro read
    assert "- Source: the database, read-only (mode=ro): the NFL predictions joined to the finished games" in nfl
    assert "season to date from live_since, not the rolling window" in nfl
    assert iso_db.read_bytes() == before                         # results-tally wrote nothing to the database


def test_grade_nfl_readonly_opens_through_readonly_scope(iso_db, monkeypatch):
    from src.db import database
    from src.walters import nfl_predict
    seen = []
    real = database.readonly_scope

    def spy():
        seen.append(1)
        return real()
    monkeypatch.setattr(database, "readonly_scope", spy)
    nfl_predict.grade_nfl(readonly=True)
    assert seen == [1]
    nfl_predict.grade_nfl()                                      # the default keeps session_scope
    assert seen == [1]
