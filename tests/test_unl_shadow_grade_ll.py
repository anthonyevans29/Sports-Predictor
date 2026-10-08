"""ARCHITECT 2026-10-07 item 4 (d): unl-shadow-grade adds, per row, the result,
the hit, the model's three-way log-loss and the book close's; model vs close
log-loss over the SAME priced games only; the split by |model − close| on the
top-pick side (<4, 4-10, 10-15, >=15pp; 4 -> 4-10, 10 -> 10-15, 15 -> >=15).
Hand-computed example below. Read-only; the exports live in tmp_path."""
import json
import math
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, Sport, Team
from src.walters import intl_shadow as us

NOW = datetime(2097, 6, 1)


@pytest.fixture(scope="module")
def world():
    init_db()
    with session_scope() as s:
        c = s.execute(select(Competition).where(Competition.code == "UNL")).scalar_one_or_none()
        if c is None:
            c = Competition(sport=Sport.SOCCER, code="UNL", name="UNL", area="I", type="INTL")
            s.add(c)
            s.flush()
        t = [Team(sport=Sport.SOCCER, name=f"LL Probe {i}") for i in range(2)]
        s.add_all(t)
        s.flush()

        def m(day, raw, s90=None, sc=None, prices=None):
            g = Match(sport=Sport.SOCCER, competition_id=c.id, season="2096/97", utc_date=datetime(2097, 5, day),
                      status=MatchStatus.FINISHED, status_raw=raw, home_team_id=t[0].id, away_team_id=t[1].id,
                      home_score_90=s90[0] if s90 else None, away_score_90=s90[1] if s90 else None,
                      home_score=sc[0] if sc else None, away_score=sc[1] if sc else None)
            s.add(g)
            s.flush()
            for sel, px in (prices or {}).items():
                s.add(Odds(match_id=g.id, source="t", bookmaker="bk", market="1X2", selection=sel,
                           price_decimal=px, captured_at=datetime(2097, 5, day) - timedelta(hours=1)))
            return g.id
        ids = {
            "g1": m(1, "FT", s90=(2, 0), prices={"HOME": 2.0, "DRAW": 3.5, "AWAY": 4.0}),   # priced, H, hit
            "g2": m(2, "FT", sc=(1, 1)),                                                     # unpriced, D (FT score)
            "g3": m(3, "FT", s90=(0, 1), prices={"HOME": 2.0, "DRAW": 4.0, "AWAY": 4.0}),   # priced, A, miss
            "g4": m(4, "AET", sc=(2, 1), prices={"HOME": 2.0, "DRAW": 4.0, "AWAY": 4.0}),   # priced, no 90' result
        }
    return ids


def _export(tmp_path, world):
    def call(mid, day, ph, pd, pa):
        top = max((("home_win", ph), ("draw", pd), ("away_win", pa)), key=lambda x: x[1])
        return {"match_id": mid, "utc_date": f"2097-05-{day:02d}T00:00:00",
                "prediction": {"home_win_prob": ph, "draw_prob": pd, "away_win_prob": pa,
                               "top_pick": top[0], "top_pick_prob": top[1]}}
    preds = [call(world["g1"], 1, 0.5, 0.3, 0.2), call(world["g2"], 2, 0.25, 0.3, 0.45),
             call(world["g3"], 3, 0.2, 0.45, 0.35), call(world["g4"], 4, 0.5, 0.3, 0.2)]
    (tmp_path / "unl_shadow_2097-04-30_1200.json").write_text(json.dumps(
        {"engine": "model_shadow", "exported_at": "2097-04-30T12:00:00", "predictions": preds}))


def test_log_loss_hand_computed_and_same_priced_restriction(world, tmp_path):
    _export(tmp_path, world)
    r = us.grade(days=10_000, export_dir=str(tmp_path), now=NOW)
    rows = {x["match_id"]: x for x in r["rows"]}
    assert (r["graded"], r["priced"], r["unpriced"], r["no_result"], r["priced_no_result"]) == (4, 3, 1, 1, 1)
    # g1: model H 0.5, single book 2.0/3.5/4.0 -> fair H = 0.5 / (0.5 + 1/3.5 + 0.25)
    fair_h = 0.5 / (0.5 + 1 / 3.5 + 0.25)
    g1 = rows[world["g1"]]
    assert (g1["result"], g1["hit"], g1["bucket"]) == ("H", True, "<4")
    assert g1["ll_model"] == pytest.approx(-math.log(0.5)) and g1["ll_close"] == pytest.approx(-math.log(fair_h))
    assert g1["div_pp"] == pytest.approx((0.5 - fair_h) * 100)
    # g2: unpriced -> model log-loss only, never in the same-priced aggregate
    g2 = rows[world["g2"]]
    assert (g2["result"], g2["hit"], g2["ll_close"]) == ("D", False, None)
    assert g2["ll_model"] == pytest.approx(-math.log(0.3))
    # g3: pick DRAW 0.45 vs close 0.25 -> +20pp (>=15); result A
    g3 = rows[world["g3"]]
    assert (g3["result"], g3["hit"], g3["bucket"]) == ("A", False, ">=15")
    assert g3["ll_model"] == pytest.approx(-math.log(0.35)) and g3["ll_close"] == pytest.approx(math.log(4))
    # g4: priced, AET without a 90-minute score -> no result, no log-loss
    g4 = rows[world["g4"]]
    assert (g4["result"], g4["hit"], g4["ll_model"], g4["ll_close"]) == (None, None, None, None)
    sp = r["same_priced"]
    assert (sp["n"], sp["hits"]) == (2, 1)
    assert sp["ll_model"] == pytest.approx((-math.log(0.5) - math.log(0.35)) / 2)
    assert sp["ll_close"] == pytest.approx((-math.log(fair_h) + math.log(4)) / 2)
    a = r["all_scored"]
    assert a["n"] == 3 and a["ll_model"] == pytest.approx((-math.log(0.5) - math.log(0.3) - math.log(0.35)) / 3)
    assert {k: v["n"] for k, v in r["buckets"].items()} == {"<4": 1, "4-10": 0, "10-15": 0, ">=15": 1}
    # the original summary keys are unchanged
    assert r["mean_clv_pp"] == round(((0.5 - fair_h) + 0.2 + (0.5 - 0.5)) / 3 * 100, 2)


def test_bucket_boundaries():
    b = us.div_bucket
    assert [b(x) for x in (0.0, 3.999, 4.0, 9.999, 10.0, 14.999, 15.0, 32.5)] == \
        ["<4", "<4", "4-10", "4-10", "10-15", "10-15", ">=15", ">=15"]
    assert [b(-x) for x in (4.0, 10.0, 15.0)] == ["4-10", "10-15", ">=15"]          # |model − close|
    assert b((0.55 - 0.51) * 100) == "4-10" and b((0.65 - 0.55) * 100) == "10-15"    # float noise at a boundary
    assert b((0.40 - 0.25) * 100) == ">=15"                                         # 15.000000000000002
    assert b((0.29 - 0.25) * 100) == "4-10" and b((0.35 - 0.25) * 100) == "10-15"   # 3.99999…, 9.99999…


def test_cli_prints_the_new_sections(world, tmp_path, monkeypatch):
    _export(tmp_path, world)
    real = us.grade
    monkeypatch.setattr(us, "grade", lambda days, progress=None: real(days=10_000, export_dir=str(tmp_path),
                                                                     now=NOW, progress=progress))
    from click.testing import CliRunner
    from cli import cli
    out = CliRunner().invoke(cli, ["unl-shadow-grade"])
    assert out.exit_code == 0, out.output
    assert "mean pick-vs-close" in out.output and "SAME priced games: n 2" in out.output
    assert ">=15: n   1" in out.output and "result H hit Y" in out.output
