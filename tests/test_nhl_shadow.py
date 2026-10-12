"""NHL SHADOW (architect 2026-09-30; v7 from 2026-10-02): the best FAILED
candidate (v7) as a greyed reference model, v1 beside it. Pins:
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


FIT_MADE = {"xg_model": "2023-24 fit, 3 attempts, no na level", "games_with_xg": 0}
NO_FIT = {"xg_model": "unavailable (no eligible 2023-24 shot after the rules)"}


@pytest.fixture
def fit_ok(monkeypatch):
    """The fit was made (the laptop's case). This test DB holds no shots, which is the host's case (addendum 49)."""
    monkeypatch.setattr(sh, "live_xg", lambda: ({}, dict(FIT_MADE)))


@pytest.fixture
def no_fit(monkeypatch):
    monkeypatch.setattr(sh, "live_xg", lambda: ({}, dict(NO_FIT)))


def test_export_stamps_every_row_and_prices_only_the_window(nhl, tmp_path, fit_ok):
    path, doc = sh.export(now=NOW, out_dir=str(tmp_path))
    assert Path(path).name == "nhl_shadow_2033-01-10_1200.json"
    # ARCHITECT 2026-10-02: the engine switches to v7, labelled with its verdict; v1 rides as the reference
    assert (doc["engine"], doc["model_version"]) == ("model_shadow", "nhl_elo_v7_xg_margin_no_na")
    assert doc["gate_verdict"] == "FAILED 0.6885 vs 0.6866"
    assert doc["reference_model"] == {"model_version": "nhl_elo_v1",
                                      "gate_verdict": "FAILED 0.6909 vs 0.6866 (Phase 2 closed 2026-09-25)"}
    assert doc["contains_predictions"] is False and "REFERENCE MODEL — FAILED GATE" in doc["note"]
    rows = {r["match_id"]: r for r in doc["predictions"]}
    assert set(rows) == {nhl["up"]}                          # preseason and >36h never priced
    assert doc["skipped"] == {"preseason_stage": 1}
    r = rows[nhl["up"]]
    assert (r["engine"], r["model_version"], r["gate_verdict"]) == (doc["engine"], doc["model_version"], doc["gate_verdict"])
    # v7 and v1 exactly as gated: recompute independently
    from src.walters import nhl_backtest as nb
    model, ref, fit = sh.fit(nb.load_games(), NOW)
    g = nb.Game(nhl["home_team"], nhl["away_team"], "2032", NOW + timedelta(hours=7), 0, 0)
    assert r["prediction"]["home_win_prob"] == round(model.predict(g), 4)
    assert r["reference"] == {"model_version": "nhl_elo_v1", "gate_verdict": sh.REFERENCE_VERDICT,
                              "home_win_prob": round(ref.predict(g), 4)}
    assert doc["fit"] == fit and fit["home_advantage"] > 0   # from the train season's home rate
    assert fit["goal_margin_fallbacks"] == fit["games_used"] - fit["xg_updates"]   # no shots here: all fall back
    assert r["market"]["fair_prob"]["HOME"] > 0.5            # the books' reference rides along


def test_no_prediction_rows_and_the_window_card_ignores_the_shadow(nhl, tmp_path):
    sh.export(now=NOW, out_dir=str(tmp_path))
    with session_scope() as s:
        n = s.execute(select(func.count(Prediction.id)).join(Match, Match.id == Prediction.match_id)
                      .where(Match.sport == Sport.NHL)).scalar()
    assert n == 0
    assert nhl["up"] not in window.canonical_models(tmp_path)


def test_grade_is_live_clv_only_from_the_last_call_before_puck_drop(nhl, tmp_path, fit_ok):
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
    pr = doc["predictions"][0]["reference"]["home_win_prob"]                     # v1 beside it, same close
    assert r["reference_mean_clv_pp"] == round(((pr - close) if pr >= 0.5 else ((1 - pr) - (1 - close))) * 100, 2)
    assert "ref v1_H=" in r["lines"][0] and "v7_xg_margin_no_na_H=" in r["lines"][0]
    md = sh.results_section(10000, export_dir=str(tmp_path))
    assert md.startswith("## NHL — REFERENCE MODEL, FAILED GATE") and "Live model-close divergence only; not a record" in md
    assert "unanchored" in md and "Reference nhl_elo_v1" in md


def test_nhl_daily_chain_exports_the_shadow_and_never_predicts():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import chains
    steps = [st[0] for st in chains.CHAINS["nhl-daily"]["steps"]]
    assert steps[-1] == "export-nhl-predictions" and "export-fixtures" in steps
    assert steps[-2] == "nhl-shot-sync" and "nhl-shot-sync" in chains.UNMETERED   # v7's live xG, then the export
    assert not any(st.startswith(("predict", "evaluate", "improve")) for st in steps)
    assert "export-nhl-predictions" in chains.UNMETERED


def test_v7_with_xg_moves_on_the_xg_margin_and_without_it_equals_v1():
    """v7 = the frozen declaration: with an xG margin it updates on it; without
    stored shots it falls back to v1 on goals (so the reference and v7 agree)."""
    from src.walters import nhl_backtest as nb
    games = nb.load_games()
    m_no, r_no, _ = sh.fit(games, NOW, xg={})
    gx = [g for g in games if g.utc_date < NOW and g.season == "2032"]
    g = nb.Game(gx[0].home_id, gx[0].away_id, "2032", NOW + timedelta(hours=1), 0, 0)
    assert m_no.predict(g) == r_no.predict(g)
    flip = {gx[0].match_id: (0.5, 3.0)}                      # the home side won on goals but lost on xG
    m_xg, r_xg, rc = sh.fit(games, NOW, xg=flip)
    assert rc["xg_updates"] == 1 and m_xg.predict(g) < r_xg.predict(g)


# ===================================================================== addendum 49 (#463): a shadow names its model ==

def _scheduled(nhl):
    """The module's game back in the window (an earlier test grades it as finished)."""
    with session_scope() as s:
        m = s.get(Match, nhl["up"])
        m.status, m.home_score, m.away_score = MatchStatus.SCHEDULED, None, None


def test_with_the_fit_unavailable_the_file_and_rows_carry_the_reference_name_verdict_and_reason(nhl, tmp_path, no_fit):
    """ARCHITECT 2026-10-12: "Where the xG fit cannot be made, the file and its rows carry the reference model's name
    and verdict and no other, and the file says that v7 was not available and why." """
    _scheduled(nhl)
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path))
    assert (doc["model_version"], doc["gate_verdict"]) == (sh.REFERENCE_VERSION, sh.REFERENCE_VERDICT)
    assert doc["v7_unavailable"] == ("nhl_elo_v7_xg_margin_no_na was not available: the xG fit could not be made "
                                     "(unavailable (no eligible 2023-24 shot after the rules))")
    assert doc["fit"]["xg_model"] == NO_FIT["xg_model"] and "nhl_elo_v1" in doc["note"]
    r = doc["predictions"][0]
    assert (r["model_version"], r["gate_verdict"]) == (sh.REFERENCE_VERSION, sh.REFERENCE_VERDICT)
    assert r["prediction"]["home_win_prob"] == r["reference"]["home_win_prob"]          # v1's number, v1's name
    names = {v for row in doc["predictions"] for v in (row["model_version"], row["reference"]["model_version"])}
    assert names == {"nhl_elo_v1"} and sh.GATE_VERDICT not in json.dumps(doc["predictions"])
    assert doc["fit"]["goal_margin_fallbacks"] == doc["fit"]["games_used"]               # counted as today


def test_with_the_fit_available_the_rows_are_unchanged(nhl, tmp_path, fit_ok):
    _scheduled(nhl)
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path))
    assert "v7_unavailable" not in doc and doc["note"] == sh.NOTE
    r = doc["predictions"][0]
    assert (r["model_version"], r["gate_verdict"]) == (sh.MODEL_VERSION, sh.GATE_VERDICT)
    assert set(r) >= {"engine", "prediction", "reference", "market"}
    assert r["reference"]["model_version"] == "nhl_elo_v1"


def test_the_grade_never_counts_a_no_fit_file_as_v7_and_still_counts_its_reference_line(nhl, tmp_path, fit_ok):
    """"A file made without the fit is never graded as v7, whatever name it carries": the ten host files say v7
    in their rows; the grade reads the fit block."""
    _scheduled(nhl)
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path))
    for f in tmp_path.glob("nhl_shadow_*.json"):
        f.unlink()
    host = json.loads(json.dumps(doc))                                  # v7's name, no fit: the host's files
    host["fit"] = {**host["fit"], **NO_FIT, "xg_updates": 0}
    (tmp_path / "nhl_shadow_2033-01-10_1200.json").write_text(json.dumps(host))
    with session_scope() as s:
        m = s.get(Match, nhl["up"])
        m.status, m.home_score, m.away_score = MatchStatus.FINISHED, 3, 2
    try:
        r = sh.grade(days=10000, export_dir=str(tmp_path), now=NOW + timedelta(days=1))
        assert r["graded"] == 1 and r["no_fit"] == 1
        assert r["priced"] == 0 and r["mean_clv_pp"] is None and r["value_side_n"] == 0       # never v7
        close = (1 / 1.8) / (1 / 1.8 + 1 / 2.1)
        pr = doc["predictions"][0]["reference"]["home_win_prob"]
        assert r["reference_priced"] == 1 and r["reference_mean_clv_pp"] == round(
            ((pr - close) if pr >= 0.5 else ((1 - pr) - (1 - close))) * 100, 2)              # the reference counts
        assert "[no xG fit: not v7, the reference only]" in r["lines"][0]
        md = sh.results_section(10000, export_dir=str(tmp_path))
        assert "1 from files made without the xG fit: the reference line only, never v7" in md
        # Codex on #464: the empty v7 line names the reason, never "no stored close" / "unanchored"
        assert md.count("— (no v7-fit call graded: all 1 came from files made without the xG fit)") == 2
        assert "no stored close" not in md and "unanchored" not in md
    finally:
        with session_scope() as s:
            m = s.get(Match, nhl["up"])
            m.status, m.home_score, m.away_score = MatchStatus.SCHEDULED, None, None
