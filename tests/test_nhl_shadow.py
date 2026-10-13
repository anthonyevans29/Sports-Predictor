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


@pytest.fixture
def fit_full(monkeypatch):
    """The fit was made and every decided game has an xG margin: no goal-margin fallback, so the file is v7. (With
    fit_ok this DB's games carry no shots, so every one falls back: addendum 63 item 2 names that file the fallback.)"""
    from src.walters import nhl_backtest as nb
    xg = {g.match_id: (float(g.home_score) + 0.25, float(g.away_score)) for g in nb.load_games()
          if g.match_id is not None and g.home_score is not None and g.away_score is not None}
    monkeypatch.setattr(sh, "live_xg", lambda: (dict(xg), dict(FIT_MADE)))


def test_export_stamps_every_row_and_prices_only_the_window(nhl, tmp_path, fit_full):
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
    model, ref, fit = sh.fit(nb.load_games(), NOW, xg=sh.live_xg()[0])
    fit.update(sh.live_xg()[1])
    g = nb.Game(nhl["home_team"], nhl["away_team"], "2032", NOW + timedelta(hours=7), 0, 0)
    assert r["prediction"]["home_win_prob"] == round(model.predict(g), 4)
    assert r["reference"] == {"model_version": "nhl_elo_v1", "gate_verdict": sh.REFERENCE_VERDICT,
                              "home_win_prob": round(ref.predict(g), 4)}
    assert doc["fit"] == fit and fit["home_advantage"] > 0   # from the train season's home rate
    assert fit["goal_margin_fallbacks"] == 0 and fit["xg_updates"] == fit["games_used"]   # every game on xG: v7
    assert r["market"]["fair_prob"]["HOME"] > 0.5            # the books' reference rides along


def test_no_prediction_rows_and_the_window_card_ignores_the_shadow(nhl, tmp_path):
    sh.export(now=NOW, out_dir=str(tmp_path))
    with session_scope() as s:
        n = s.execute(select(func.count(Prediction.id)).join(Match, Match.id == Prediction.match_id)
                      .where(Match.sport == Sport.NHL)).scalar()
    assert n == 0
    assert nhl["up"] not in window.canonical_models(tmp_path)


def test_grade_is_live_clv_only_from_the_last_call_before_puck_drop(nhl, tmp_path, fit_full):
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


def test_with_the_fit_available_the_rows_are_unchanged(nhl, tmp_path, fit_full):
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


# =================================================================== addendum 50 item 3 (#466): the v7 line ==

def _finish(nhl):
    with session_scope() as s:
        m = s.get(Match, nhl["up"])
        m.status, m.home_score, m.away_score = MatchStatus.FINISHED, 3, 2


def test_a_v1_era_row_is_never_on_the_v7_line_and_counts_on_the_reference_line_by_its_own_number(nhl, tmp_path,
                                                                                                    fit_ok):
    """ARCHITECT 2026-10-12: "The v7 line counts a row that names v7 from a file whose fit was made, and no other row.
    A row that names the reference counts on the reference line by its own number." The files of 2026-09-30 to 10-02
    name v1, carry no reference block and no xg_model: fit_made reads them as made."""
    _scheduled(nhl)
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path))
    for f in tmp_path.glob("nhl_shadow_*.json"):
        f.unlink()
    era = json.loads(json.dumps(doc))
    era["model_version"] = "nhl_elo_v1"
    era["fit"] = {k: v for k, v in era["fit"].items() if k != "xg_model"}
    row = era["predictions"][0]
    row["model_version"], row["gate_verdict"] = "nhl_elo_v1", sh.REFERENCE_VERDICT
    row.pop("reference")
    row["prediction"]["home_win_prob"] = 0.61
    (tmp_path / "nhl_shadow_2033-01-10_1200.json").write_text(json.dumps(era))
    _finish(nhl)
    try:
        r = sh.grade(days=10000, export_dir=str(tmp_path), now=NOW + timedelta(days=1))
        close = (1 / 1.8) / (1 / 1.8 + 1 / 2.1)
        assert r["graded"] == 1 and r["not_v7"] == 1 and r["no_fit"] == 0
        assert r["priced"] == 0 and r["mean_clv_pp"] is None and r["value_side_n"] == 0          # not on the v7 line
        assert r["reference_priced"] == 1 and r["reference_mean_clv_pp"] == round((0.61 - close) * 100, 2)
        assert "[names the reference: not v7, the reference line] v1_H=0.610" in r["lines"][0]
        assert "value=— (not graded: not a v7 row)" in r["lines"][0] and "ref v1_H=0.610" in r["lines"][0]
        md = sh.results_section(10000, export_dir=str(tmp_path))
        assert "(1 naming the reference (nhl_elo_v1): the reference line only, never v7)" in md
        assert md.count("— (no v7-fit call graded: 1 naming the reference (nhl_elo_v1))") == 2
    finally:
        _scheduled(nhl)


def test_a_no_fit_row_with_a_book_anchor_says_not_graded_never_no_anchor(nhl, tmp_path, no_fit):
    """#466: "value=— (no anchor)" was printed for a no-fit row whose game has a pre-kickoff book anchor."""
    from src.db.schema import OddsSnapshot
    _scheduled(nhl)
    sh.export(now=NOW, out_dir=str(tmp_path))
    with session_scope() as s:
        for sel, pr in (("HOME", 0.55), ("AWAY", 0.45)):
            s.add(OddsSnapshot(match_id=nhl["up"], market="1X2", selection=sel, devig_prob=pr, n_books=3,
                               captured_at=NOW - timedelta(hours=2), source="sh_books"))
    _finish(nhl)
    try:
        r = sh.grade(days=10000, export_dir=str(tmp_path), now=NOW + timedelta(days=1))
        assert r["no_fit"] == 1 and r["unanchored"] == 0
        assert "value=— (not graded: no xG fit)" in r["lines"][0] and "no anchor" not in r["lines"][0]
    finally:
        _scheduled(nhl)
        with session_scope() as s:
            s.query(OddsSnapshot).filter(OddsSnapshot.match_id == nhl["up"],
                                         OddsSnapshot.source == "sh_books").delete(synchronize_session=False)



# ============================================= addendum 63 item 2: a shadow that ran the fallback is not v7 ==

def test_a_walk_with_any_goal_margin_fallback_is_named_the_fallback_on_the_header_and_every_row(nhl, tmp_path,
                                                                                               fit_ok):
    """ARCHITECT 2026-10-13: "A shadow run whose fit took the goal-margin fallback for any game is not v7. Its
    model_version reads nhl_elo_v7_goal_margin_fallback, on the file's header and on every row, and the fit block
    stays as it is." This DB's games carry no shots: the fit is made and every game falls back."""
    from src.walters import nhl_backtest as nb
    _scheduled(nhl)
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path))
    model, ref, fit = sh.fit(nb.load_games(), NOW, xg={})
    fit.update(FIT_MADE)
    assert doc["fit"] == fit and fit["goal_margin_fallbacks"] > 0                 # the fit block as it is
    assert doc["model_version"] == "nhl_elo_v7_goal_margin_fallback" == sh.FALLBACK_VERSION
    assert all(r["model_version"] == sh.FALLBACK_VERSION for r in doc["predictions"]) and doc["predictions"]
    assert doc["not_v7"] == (f"the walk took the goal-margin fallback for {fit['goal_margin_fallbacks']} of "
                             f"{fit['games_used']} games: this file is nhl_elo_v7_goal_margin_fallback, not "
                             "nhl_elo_v7_xg_margin_no_na (ARCHITECT 2026-10-13, addendum 63 item 2)")
    assert doc["note"] == sh.NOTE_FALLBACK and "v7_unavailable" not in doc
    g = nb.Game(nhl["home_team"], nhl["away_team"], "2032", NOW + timedelta(hours=7), 0, 0)
    r = doc["predictions"][0]
    assert r["prediction"]["home_win_prob"] == round(model.predict(g), 4)          # the numbers the walk ran
    assert r["reference"]["model_version"] == "nhl_elo_v1"
    assert sh.MODEL_VERSION not in json.dumps(doc["predictions"])


def test_one_fallback_game_is_enough_and_none_is_v7(nhl, tmp_path, monkeypatch):
    from src.walters import nhl_backtest as nb
    games = [g for g in nb.load_games() if g.match_id is not None and g.home_score is not None]
    all_xg = {g.match_id: (float(g.home_score) + 0.25, float(g.away_score)) for g in games}
    one_short = dict(all_xg)
    one_short.pop(next(iter(one_short)))
    _scheduled(nhl)
    monkeypatch.setattr(sh, "live_xg", lambda: (dict(one_short), dict(FIT_MADE)))
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path))
    assert doc["fit"]["goal_margin_fallbacks"] == 1 and doc["model_version"] == sh.FALLBACK_VERSION
    monkeypatch.setattr(sh, "live_xg", lambda: (dict(all_xg), dict(FIT_MADE)))
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path / "v7"))
    assert doc["fit"]["goal_margin_fallbacks"] == 0 and doc["model_version"] == sh.MODEL_VERSION
    assert "not_v7" not in doc and doc["note"] == sh.NOTE


def test_the_no_fit_file_still_names_the_reference(nhl, tmp_path, no_fit):
    """Addendum 49 stands where the fit could not be made at all: v1's name and numbers."""
    _scheduled(nhl)
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path))
    assert doc["model_version"] == sh.REFERENCE_VERSION and "not_v7" not in doc


@pytest.mark.parametrize("fit, name", [
    ({"xg_model": "2023-24 fit", "goal_margin_fallbacks": 0}, "nhl_elo_v7_xg_margin_no_na"),
    ({"xg_model": "2023-24 fit", "goal_margin_fallbacks": 3}, "nhl_elo_v7_goal_margin_fallback"),
    ({"xg_model": "unavailable (x)", "goal_margin_fallbacks": 2879}, "nhl_elo_v1"),
    ({}, "nhl_elo_v7_xg_margin_no_na"), (None, "nhl_elo_v7_xg_margin_no_na"),
    ({"xg_model": "2023-24 fit", "goal_margin_fallbacks": True}, "nhl_elo_v7_xg_margin_no_na"),
])
def test_the_fit_block_decides_the_name(fit, name):
    assert sh.shadow_name(fit) == name


def _two_games(nhl):
    """A second game in the window beside the module's, with its own books."""
    with session_scope() as s:
        m0 = s.get(Match, nhl["up"])
        m = Match(sport=Sport.NHL, competition_id=m0.competition_id, season="2032", utc_date=NOW + timedelta(hours=7),
                  status=MatchStatus.SCHEDULED, home_team_id=nhl["away_team"], away_team_id=nhl["home_team"])
        s.add(m)
        s.flush()
        for bk in ("b1", "b2"):
            for sel, price in (("HOME", 2.2), ("AWAY", 1.7)):
                s.add(Odds(match_id=m.id, source="t", bookmaker=bk, market="1X2", selection=sel,
                           price_decimal=price, captured_at=NOW))
        return m.id


def test_the_grade_never_pools_a_fallback_file_with_a_v7_file_and_says_which_it_graded(nhl, tmp_path, fit_full):
    """ "nhl-shadow-grade never pools a fallback file with a v7 file: it grades each name on its own and says which it
    graded." Game A's last call is in a v7 file, game B's in a fallback file."""
    _scheduled(nhl)
    b = _two_games(nhl)
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path))
    for f in tmp_path.glob("nhl_shadow_*.json"):
        f.unlink()
    rows = {r["match_id"]: r for r in doc["predictions"]}
    v7 = {**doc, "predictions": [rows[nhl["up"]]]}
    fb = json.loads(json.dumps({**doc, "predictions": [rows[b]]}))
    fb["fit"] = {**fb["fit"], "goal_margin_fallbacks": 4}
    fb["model_version"] = fb["predictions"][0]["model_version"] = sh.FALLBACK_VERSION
    (tmp_path / "nhl_shadow_2033-01-10_1200.json").write_text(json.dumps(v7))
    (tmp_path / "nhl_shadow_2033-01-10_1201.json").write_text(json.dumps(fb))
    with session_scope() as s:
        for mid in (nhl["up"], b):
            m = s.get(Match, mid)
            m.status, m.home_score, m.away_score = MatchStatus.FINISHED, 3, 2
    try:
        r = sh.grade(days=10000, export_dir=str(tmp_path), now=NOW + timedelta(days=1))
        close_a, close_b = (1 / 1.8) / (1 / 1.8 + 1 / 2.1), (1 / 2.2) / (1 / 2.2 + 1 / 1.7)

        def clv(p, c):
            return (p - c) if p >= 0.5 else ((1 - p) - (1 - c))
        pa, pb = rows[nhl["up"]]["prediction"]["home_win_prob"], rows[b]["prediction"]["home_win_prob"]
        assert r["graded"] == 2 and r["priced"] == 1 and r["fallback"] == 1 and r["fallback_priced"] == 1
        assert r["mean_clv_pp"] == round(clv(pa, close_a) * 100, 2)                 # the v7 line: game A only
        assert r["fallback_mean_clv_pp"] == round(clv(pb, close_b) * 100, 2)        # the fallback line: game B only
        assert r["graded_by_name"] == {"nhl_elo_v7_xg_margin_no_na": 1, "nhl_elo_v7_goal_margin_fallback": 1,
                                       "nhl_elo_v1 (reference line only)": 0}
        assert r["reference_priced"] == 2                                            # v1 rides beside both
        tagged = [ln for ln in r["lines"] if "[goal-margin fallback: not v7, its own line]" in ln]
        assert len(tagged) == 1 and "v7_goal_margin_fallback_H=" in tagged[0]
        md = sh.results_section(10000, export_dir=str(tmp_path))
        assert ("- nhl_elo_v7_goal_margin_fallback (not v7: its own line, never pooled with v7; addendum 63 item 2), "
                f"1 graded: pick-vs-close {clv(pb, close_b) * 100:+.2f}pp (n=1 priced)") in md
        assert "(1 from walks with the goal-margin fallback (nhl_elo_v7_goal_margin_fallback): never v7; the " \
               "fallback on its own line below)" in md
        assert f"Mean pick-vs-close: {clv(pa, close_a) * 100:+.2f}pp (n=1 priced)" in md
    finally:
        with session_scope() as s:
            s.query(Odds).filter(Odds.match_id == b).delete(synchronize_session=False)
            s.query(Match).filter(Match.id == b).delete(synchronize_session=False)
        _scheduled(nhl)


def test_an_older_file_named_v7_whose_fit_block_counts_a_fallback_is_graded_on_the_fallback_line(nhl, tmp_path,
                                                                                                  fit_full):
    """The fit block decides, never the name (addendum 49): a file written before this ruling names v7 but its walk
    took the fallback; it is graded as the fallback, never as v7."""
    _scheduled(nhl)
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path))
    for f in tmp_path.glob("nhl_shadow_*.json"):
        f.unlink()
    old = json.loads(json.dumps(doc))
    old["fit"] = {**old["fit"], "goal_margin_fallbacks": 12}
    assert old["model_version"] == old["predictions"][0]["model_version"] == sh.MODEL_VERSION
    (tmp_path / "nhl_shadow_2033-01-10_1200.json").write_text(json.dumps(old))
    _finish(nhl)
    try:
        r = sh.grade(days=10000, export_dir=str(tmp_path), now=NOW + timedelta(days=1))
        assert r["priced"] == 0 and r["mean_clv_pp"] is None and r["value_side_n"] == 0      # never v7
        assert r["fallback"] == 1 and r["fallback_priced"] == 1 and r["not_v7"] == 1 and r["no_fit"] == 0
        assert "[goal-margin fallback: not v7, its own line] v7_goal_margin_fallback_H=" in r["lines"][0]
        md = sh.results_section(10000, export_dir=str(tmp_path))
        assert md.count("— (no v7-fit call graded: 1 from walks with the goal-margin fallback "
                        "(nhl_elo_v7_goal_margin_fallback))") == 2
    finally:
        _scheduled(nhl)


def test_the_cli_prints_the_fallback_on_export_and_grades_by_name(nhl, tmp_path, fit_ok, monkeypatch):
    from click.testing import CliRunner

    import cli
    _scheduled(nhl)
    monkeypatch.chdir(tmp_path)
    out = CliRunner().invoke(cli.cli, ["export-nhl-predictions"])
    assert out.exit_code == 0, out.output
    assert "model nhl_elo_v7_goal_margin_fallback" in out.output
    assert "✗ the walk took the goal-margin fallback for " in out.output
    out = CliRunner().invoke(cli.cli, ["nhl-shadow-grade", "--days", "10000"])
    assert out.exit_code == 0, out.output
    assert "── graded by name: nhl_elo_v7_xg_margin_no_na " in out.output
