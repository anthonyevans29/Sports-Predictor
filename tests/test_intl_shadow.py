"""UNL SHADOW (ARCHITECT 2026-10-02): intl-elo-v2 (PASS, confirmation window)
as a greyed three-way shadow. Pins: it refuses without the registry's run
record + PASS; its multipliers are READ from the record (never refit); rows are
engine model_shadow, labelled "PASS — confirmation n/60", three-way, never in
the Prediction table; grading is the top pick vs the three-way close; the
confirmation set is competitive, after the verdict, first n; the intl-daily
chain syncs incrementally, then the venue step, then the export. The real
ledger is never touched (the registry is monkeypatched)."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, IntlMatchVenue, Match, MatchStatus, Odds, Prediction, Sport, Team
from src.walters import intl_elo as ie
from src.walters import intl_shadow as us
from src.walters import registry as reg

VERDICT_AT = datetime(2096, 1, 1)
NOW = datetime(2096, 3, 10, 12, 0)
ENTRY = {"id": "intl-elo-v2", "status": "confirming",
         "run": {"result": {"fit_c_mult": 2.0, "fit_k_mult": 1.25}},
         "verdict": {"verdict": "PASS", "at": "2096-01-01T00:00:00Z"},
         "confirmation_plan": {"n_games": 3, "metric": "log_loss", "bar": 1.0986, "must_beat_reference": True,
                               "reference": "naive - 0.010"}}


@pytest.fixture(scope="module")
def world():
    init_db()
    with session_scope() as s:
        def comp(code):
            c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
            if c is None:
                c = Competition(sport=Sport.SOCCER, code=code, name=code, area="I", type="INTL")
                s.add(c)
                s.flush()
            return c
        unl, fr = comp("UNL"), comp("FRIENDLIES_INT")
        t = [Team(sport=Sport.SOCCER, name=f"US Probe {i}") for i in range(4)]
        s.add_all(t)
        s.flush()

        def m(c, h, a, when, hs=None, as_=None, status=MatchStatus.FINISHED, season="2095/96"):
            x = Match(sport=Sport.SOCCER, competition_id=c.id, season=season, utc_date=when, status=status,
                      status_raw="FT" if status == MatchStatus.FINISHED else None, home_team_id=t[h].id,
                      away_team_id=t[a].id, home_score=hs, away_score=as_)
            s.add(x)
            s.flush()
            return x.id
        m(unl, 0, 1, datetime(2019, 6, 1), 1, 1, season="2018/19")   # the training stream (2018..2024-08)
        tn = m(unl, 2, 3, datetime(2019, 6, 2), 2, 1, season="2018/19")
        s.add(IntlMatchVenue(match_id=tn, venue_id=2, venue_country="Elsewhere", home_country="Probeland",
                             neutral_v3=True, rule="r"))                    # naive needs a neutral train game
        ids = {"after1": m(unl, 0, 1, datetime(2096, 2, 1), 2, 0), "after2": m(unl, 2, 3, datetime(2096, 2, 2), 1, 1),
               "friendly": m(fr, 0, 2, datetime(2096, 2, 3), 0, 0), "after3": m(unl, 1, 3, datetime(2096, 2, 4), 0, 1),
               "after4": m(unl, 3, 0, datetime(2096, 2, 5), 1, 0),
               "up": m(unl, 0, 3, NOW + timedelta(hours=6), status=MatchStatus.SCHEDULED),
               "far": m(unl, 1, 2, NOW + timedelta(hours=60), status=MatchStatus.SCHEDULED)}
        s.add(IntlMatchVenue(match_id=ids["up"], venue_id=1, venue_country="Nowhere", home_country="Probeland",
                             neutral_v3=True, rule="r"))
        for bk in ("b1", "b2"):
            for sel, price in (("HOME", 2.0), ("DRAW", 3.4), ("AWAY", 3.8)):
                s.add(Odds(match_id=ids["after1"], source="t", bookmaker=bk, market="1X2", selection=sel,
                           price_decimal=price, captured_at=datetime(2096, 1, 31, 12)))
        ids["teams"] = [x.id for x in t]
    return ids


@pytest.fixture
def frozen_ok(monkeypatch):
    monkeypatch.setattr(reg, "get", lambda eid, path=None: ENTRY if eid == "intl-elo-v2" else None)


def test_refuses_without_run_record_or_pass(monkeypatch):
    monkeypatch.setattr(reg, "get", lambda eid, path=None: None)
    with pytest.raises(us.ShadowRefused, match="no run record"):
        us.frozen()
    monkeypatch.setattr(reg, "get", lambda eid, path=None: {**ENTRY, "verdict": None})
    with pytest.raises(us.ShadowRefused, match="no PASS"):
        us.frozen()


def test_multipliers_are_read_from_the_record(frozen_ok):
    e, c, k = us.frozen()
    assert (c, k) == (2.0, 1.25)


def test_confirmation_set_is_competitive_after_the_verdict_first_n(world, frozen_ok):
    g = lambda i, code, when: ie.Game(i, code, "x", when, 1, 2, 1, 0, False)  # noqa: E731
    games = [g(1, "UNL", datetime(2095, 12, 31)), g(2, "UNL", datetime(2096, 1, 2)),
             g(3, "FRIENDLIES_INT", datetime(2096, 1, 3)), g(4, "WCQ_EU", datetime(2096, 1, 4)),
             g(5, "UNL", datetime(2096, 1, 5)), g(6, "UNL", datetime(2096, 1, 6))]
    assert [x.id for x in us.confirmation_games(games, ENTRY)] == [2, 4, 5]    # n = 3; friendly and pre-verdict out


def test_export_rows_are_three_way_shadow_labelled_and_never_predictions(world, frozen_ok, tmp_path):
    path, doc = us.export(now=NOW, out_dir=str(tmp_path))
    assert Path(path).name == "unl_shadow_2096-03-10_1200.json"
    assert (doc["engine"], doc["model_version"], doc["contains_predictions"]) == ("model_shadow", "intl_elo_v2", False)
    assert doc["gate_verdict"] == "PASS — confirmation 3/3"                     # 4 played, capped at n
    rows = {r["match_id"]: r for r in doc["predictions"]}
    assert world["up"] in rows and world["far"] not in rows                     # the 36h window
    p = rows[world["up"]]["prediction"]
    assert p["home_win_prob"] + p["draw_prob"] + p["away_win_prob"] == pytest.approx(1.0, abs=1e-3)
    assert p["neutral_v3"] is True and p["home_adv_applied"] == 0.0             # v3 neutral -> no home term
    assert p["top_pick_prob"] == max(p["home_win_prob"], p["draw_prob"], p["away_win_prob"])
    assert rows[world["up"]]["gate_verdict"] == doc["gate_verdict"] and doc["fit"]["c_mult"] == 2.0
    with session_scope() as s:
        n = s.execute(select(func.count(Prediction.id)).where(Prediction.match_id.in_(list(rows)))).scalar()
    assert n == 0


def test_grade_is_top_pick_vs_the_three_way_close(world, frozen_ok, tmp_path):
    call = {"match_id": world["after1"], "utc_date": "2096-02-01T00:00:00",
            "prediction": {"top_pick": "home_win", "top_pick_prob": 0.55}}
    (tmp_path / "unl_shadow_2096-01-31_1200.json").write_text(json.dumps(
        {"engine": "model_shadow", "exported_at": "2096-01-31T12:00:00", "predictions": [call]}))
    r = us.grade(days=10_000, export_dir=str(tmp_path), now=NOW)
    inv = {k: 1 / v for k, v in {"HOME": 2.0, "DRAW": 3.4, "AWAY": 3.8}.items()}
    fair_h = inv["HOME"] / sum(inv.values())
    assert r["graded"] == 1 and r["priced"] == 1 and r["mean_clv_pp"] == round((0.55 - fair_h) * 100, 2)
    md = us.results_section(10_000, export_dir=str(tmp_path))
    assert md.startswith("## UNL — SHADOW, CONFIRMATION WINDOW") and "not a record" in md


def test_confirmation_read_scores_the_first_n_predict_then_update(world, frozen_ok):
    r = us.confirmation_read(now=NOW)
    assert r["n"] == 3 and r["n_games"] == 3 and r["first_game_at"] == "2096-02-01T00:00:00Z"
    assert set(r["scored_ids"]) == {world["after1"], world["after2"], world["after3"]}
    assert r["reference_log_loss"] == pytest.approx(r["naive_log_loss"] - 0.010)


def test_intl_daily_chain_and_cli_refusal(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import chains
    steps = chains.CHAINS["intl-daily"]["steps"]
    assert [s[0] for s in steps] == ["intl-sync", "intl-venue-sync", "export-unl-predictions"]
    assert steps[0][1:3] == ["--since", "{today}"] and "export-unl-predictions" in chains.UNMETERED
    from click.testing import CliRunner
    from cli import cli
    monkeypatch.setattr(reg, "get", lambda eid, path=None: None)
    out = CliRunner().invoke(cli, ["export-unl-predictions"])
    assert out.exit_code == 2 and "REFUSED" in out.output
