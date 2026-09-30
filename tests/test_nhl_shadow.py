"""NHL SHADOW (architect 2026-09-30): the FAILED nhl_elo_v1 as a greyed
reference model. Pins:
- every row is stamped (model_version, gate_verdict, engine model_shadow);
- the model is v1 as gated (the 2024 home rate, walk-forward);
- preseason is never priced;
- nothing is written to the Prediction table;
- the window card never reads the shadow file as a model;
- grading is live CLV only, from the artifacts (the last call before puck
  drop), into a RESULTS.md shadow section;
- the nhl-daily chain gains the export step, and no predict step."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, Prediction, Sport, Team
from src.walters import nhl_shadow as sh
from src.walters import window

NOW = datetime(2033, 1, 10, 12, 0)


@pytest.fixture(scope="module")
def nhl():
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.sport == Sport.NHL,
                                                   Competition.code == "NHL")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.NHL, code="NHL", name="NHL", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        t = [Team(sport=Sport.NHL, name=f"SH Team {i}", external_ids={"sh": str(i)}) for i in range(4)]
        s.add_all(t)
        s.flush()

        def game(h, a, at, season, hs=None, as_=None, status=MatchStatus.FINISHED, stage=None):
            m = Match(sport=Sport.NHL, competition_id=comp.id, season=season, utc_date=at, status=status,
                      home_team_id=t[h].id, away_team_id=t[a].id, home_score=hs, away_score=as_, stage=stage)
            s.add(m)
            s.flush()
            return m.id
        for i in range(6):                                   # 2024 train season: home wins 4/6
            game(i % 2, 2 + i % 2, datetime(2024, 11, 1 + i, 0, 0), "2024",
                 3 if i < 4 else 1, 1 if i < 4 else 2)
        game(0, 1, datetime(2032, 12, 1), "2032", 5, 1)      # a later decided game moves ratings
        up = game(0, 2, NOW + timedelta(hours=7), "2032", status=MatchStatus.SCHEDULED)
        pre = game(1, 3, NOW + timedelta(hours=8), "2032", status=MatchStatus.SCHEDULED, stage="Pre Season")
        far = game(2, 3, NOW + timedelta(hours=40), "2032", status=MatchStatus.SCHEDULED)   # outside 36h
        for bk in ("b1", "b2"):
            for sel, price in (("HOME", 1.8), ("AWAY", 2.1)):
                s.add(Odds(match_id=up, source="t", bookmaker=bk, market="1X2", selection=sel,
                           price_decimal=price, captured_at=NOW))
        ids = {"up": up, "pre": pre, "far": far, "home_team": t[0].id, "away_team": t[2].id}
    return ids


def test_export_stamps_every_row_and_prices_only_the_window(nhl, tmp_path):
    path, doc = sh.export(now=NOW, out_dir=str(tmp_path))
    assert Path(path).name == "nhl_shadow_2033-01-10_1200.json"
    assert (doc["engine"], doc["model_version"]) == ("model_shadow", "nhl_elo_v1")
    assert doc["gate_verdict"] == "FAILED 0.6909 vs 0.6866 (Phase 2 closed 2026-09-25)"
    assert doc["contains_predictions"] is False and "REFERENCE MODEL — FAILED GATE" in doc["note"]
    rows = {r["match_id"]: r for r in doc["predictions"]}
    assert set(rows) == {nhl["up"]}                          # preseason and >36h never priced
    assert doc["skipped"] == {"preseason_stage": 1}
    r = rows[nhl["up"]]
    assert (r["engine"], r["model_version"], r["gate_verdict"]) == (doc["engine"], doc["model_version"], doc["gate_verdict"])
    # v1 exactly as gated: recompute independently
    from src.walters import nhl_backtest as nb
    model, fit = sh.fit(nb.load_games(), NOW)
    g = nb.Game(nhl["home_team"], nhl["away_team"], "2032", NOW + timedelta(hours=7), 0, 0)
    assert r["prediction"]["home_win_prob"] == round(model.predict(g), 4)
    assert doc["fit"] == fit and fit["home_advantage"] > 0   # from the train season's home rate
    assert r["market"]["fair_prob"]["HOME"] > 0.5            # the books' reference rides along


def test_no_prediction_rows_and_the_window_card_ignores_the_shadow(nhl, tmp_path):
    sh.export(now=NOW, out_dir=str(tmp_path))
    with session_scope() as s:
        n = s.execute(select(func.count(Prediction.id)).join(Match, Match.id == Prediction.match_id)
                      .where(Match.sport == Sport.NHL)).scalar()
    assert n == 0
    assert nhl["up"] not in window.canonical_models(tmp_path)


def test_grade_is_live_clv_only_from_the_last_call_before_puck_drop(nhl, tmp_path):
    early = NOW - timedelta(hours=10)
    sh.export(now=early, out_dir=str(tmp_path))                     # an older call
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path))              # the last call before puck drop
    late = json.loads(json.dumps(doc))                              # a file written AFTER puck drop never counts
    late["exported_at"] = (NOW + timedelta(hours=8)).isoformat()
    late["predictions"][0]["prediction"]["home_win_prob"] = 0.01
    (tmp_path / "nhl_shadow_late.json").write_text(json.dumps(late))
    calls = sh.last_calls(str(tmp_path))
    assert calls[nhl["up"]]["exported_at"] == NOW.isoformat()
    with session_scope() as s:
        m = s.get(Match, nhl["up"])
        m.status, m.home_score, m.away_score = MatchStatus.FINISHED, 3, 2
    r = sh.grade(days=10000, export_dir=str(tmp_path), now=NOW + timedelta(days=1))
    assert r["graded"] == 1 and r["priced"] == 1 and r["unanchored"] == 1 and r["value_side_n"] == 0
    p = doc["predictions"][0]["prediction"]["home_win_prob"]
    close = (1 / 1.8) / (1 / 1.8 + 1 / 2.1)
    want = (p - close) if p >= 0.5 else ((1 - p) - (1 - close))
    assert r["mean_clv_pp"] == round(want * 100, 2)
    assert set(r) >= {"mean_clv_pp", "mean_value_side_clv_pp"} and "hits" not in r and "logloss" not in r
    md = sh.results_section(10000, export_dir=str(tmp_path))
    assert md.startswith("## NHL — REFERENCE MODEL, FAILED GATE") and "Live CLV only; not a record" in md
    assert "unanchored" in md


def test_nhl_daily_chain_exports_the_shadow_and_never_predicts():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import chains
    steps = [st[0] for st in chains.CHAINS["nhl-daily"]["steps"]]
    assert steps[-1] == "export-nhl-predictions" and "export-fixtures" in steps
    assert not any(st.startswith(("predict", "evaluate", "improve")) for st in steps)
    assert "export-nhl-predictions" in chains.UNMETERED
