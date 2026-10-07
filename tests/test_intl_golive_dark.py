"""INTERNATIONALS GO-LIVE READINESS, built DARK (ARCHITECT 2026-10-07, item 4 a + b).

INTL DESK POLICY v0: "(1) A new POLICY block INTL = the SOCCER block (eMin 4, eLad 10, eHair 10, pMin 0.50) with
qNever true ... (2) Half units until 30 INTL calls are graded. (3) A row is never a call when its venue flag is
unknown and its listed home side is on the home-abroad list ... (4) UNL only: CNL has no wired Kalshi series, so CNL
rows are predictions without a call. (5) UNL stays ineligible for venue-edge until the skew test (#286) is read."
The export refuses until registry.production_allowed("intl-elo-v2"); the v1.1 goldens are unchanged
(tests/test_desk_golden.py). The real ledger is never touched (the registry is monkeypatched)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from src.db.database import init_db, session_scope
from src.db.schema import Prediction
from src.walters import desk_policy as dp
from src.walters import intl_production as ip
from src.walters import registry as reg
from src.walters.venue import kalshi_exec

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
KO = (NOW + timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%S")


def row(home="Probeland", comp="UNL", p=(0.60, 0.22, 0.18), fair=(0.54, 0.26, 0.20), flag="home",
        ask=0.50, div=None):
    r = {"home_team": home, "away_team": f"{home} B", "utc_date": KO, "competition": comp, "venue_flag": flag,
         "prediction": {"probabilities": {"home_win": p[0], "draw": p[1], "away_win": p[2]}, "tier": None},
         "market": {"bookmaker_count": 8, "fair_prob": {"HOME": fair[0], "DRAW": fair[1], "AWAY": fair[2]},
                    "fair_source": "1X2"},
         "market_divergence_pp": ip.divergence_pp(p[0], {"fair_source": "1X2", "fair_prob": {"HOME": fair[0]}})
         if div is None else div}
    r["quarantine"] = r["market_divergence_pp"] is not None and abs(r["market_divergence_pp"]) >= 15
    r.update(kalshi_exec(ask - 0.01, ask, "UNL", two_way=False))
    return r


def desk(*rows, counts=None, sport="intl"):
    doc = {"sport": sport, "predictions": [json.loads(json.dumps(r)) for r in rows]}
    dp.annotate(doc, now=NOW, counts=counts)
    return [r["desk"] for r in doc["predictions"]], doc


def test_intl_block_is_the_soccer_block_with_qnever():
    assert dp.POLICY["INTL"] == {**dp.POLICY["SOCCER"], "qNever": True}
    assert dp.INTL["callComps"] == ("UNL",) and dp.INTL["halfUntilGraded"] == 30
    assert dp.INTL_HOME_ABROAD == frozenset()              # ruled BY NAME from receipt (c); nothing assumed


def test_unl_play_is_half_units_until_30_graded_then_full():
    (d,), doc = desk(row())
    assert (d["call"], d["units"]) == ("PLAY", 0.5) and "INTL → half units until 30 graded (0/30)" in d["reasons"]
    assert doc["desk_meta"]["counts"]["intl_graded"] == 0
    (d,), _ = desk(row(), counts={"intl_graded": 30})
    assert (d["call"], d["units"]) == ("PLAY", 1) and not any("INTL →" in x for x in d["reasons"])


def test_quarantine_at_15pp_is_shadow_only_as_in_the_nfl_contract():
    r = row(p=(0.70, 0.17, 0.13), fair=(0.54, 0.26, 0.20))     # div +16.0pp
    assert (r["market_divergence_pp"], r["quarantine"]) == (16.0, True)
    (d,), _ = desk(r, counts={"intl_graded": 30})
    assert d["call"] == "PASS" and d["units"] == 0 and d["shadow_units"] > 0 and d["order"] is None
    assert d["reason"].startswith("QUARANTINE 16pp")


def test_cnl_rows_are_predictions_without_a_call():
    (d,), _ = desk(row(comp="CNL"), counts={"intl_graded": 30})
    assert (d["call"], d["units"], d["pass_kind"]) == ("PASS", 0, "no_series")
    assert d["order"] is None and d["exec"] is None and d["value_shadow"] is None
    assert "no wired Kalshi series" in d["reason"]


def test_unknown_venue_and_home_abroad_side_is_never_a_call(monkeypatch):
    (d,), _ = desk(row(flag="unknown"), counts={"intl_graded": 30})
    assert d["call"] == "PLAY"                                 # the list is empty until ruled
    monkeypatch.setattr(dp, "INTL_HOME_ABROAD", frozenset({"Probeland"}))
    (u, k, other), _ = desk(row(flag="unknown"), row(flag="home"), row(home="Elsewhere", flag="unknown"),
                            counts={"intl_graded": 30})
    assert (u["call"], u["pass_kind"], u["order"], u["value_shadow"]) == ("PASS", "venue_unknown", None, None)
    assert k["call"] == "PLAY" and other["call"] == "PLAY"     # known venue / not on the list: unchanged
    r = row()
    r.pop("venue_flag")                                        # a missing flag counts as unknown (conservative)
    (m,), _ = desk(r, counts={"intl_graded": 30})
    assert m["pass_kind"] == "venue_unknown"


def test_pick_floor_is_the_soccer_pmin():
    (d,), _ = desk(row(p=(0.45, 0.30, 0.25), fair=(0.38, 0.32, 0.30)), counts={"intl_graded": 30})
    assert d["call"] == "PASS" and d["pass_kind"] == "floor" and "< 0.5" in d["reason"]


def test_unl_is_never_venue_eligible():
    (d,), _ = desk(row(), counts={"intl_graded": 30})
    assert d["venue"]["eligible"] is False
    fx = {"competition_code": "UNL", "fixtures": [{"home_team": "A", "away_team": "B", "utc_date": KO,
          "status": "scheduled", "market": {"bookmaker_count": 6, "fair_prob": {"HOME": .6, "DRAW": .2, "AWAY": .2},
                                            "captured_at": NOW.isoformat()},
          "kalshi": {"status": "two_sided", "prob": {"HOME": .5, "DRAW": .25, "AWAY": .25}}}]}
    dp.annotate(fx, now=NOW)
    assert fx["fixtures"][0]["desk"]["call"] == "PASS" and "(UNL)" in fx["fixtures"][0]["desk"]["reason"]


def test_other_sports_are_unchanged():
    nfl = {"home_team": "K", "away_team": "B", "utc_date": KO, "competition": "NFL", "stage": "regular",
           "prediction": {"probabilities": {"home_win": .62, "draw": None, "away_win": .38}, "tier": "lean"},
           "market": {"bookmaker_count": 9, "fair_prob": {"HOME": .55, "AWAY": .45}}}
    (d,), doc = desk(nfl, sport="nfl")
    assert "intl_graded" not in doc["desk_meta"]["counts"] and not any("INTL" in x for x in d["reasons"])


def test_ledger_summary_reads_the_optional_intl_count(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"kind": dp.SUMMARY_KIND, "counts": {"postseason_graded": 1, "value_shadow_graded": 0,
                                                                  "kalshi_only_graded": 0, "intl_graded": 12}}))
    assert dp.read_ledger_summary(str(p))[0]["intl_graded"] == 12
    p.write_text(json.dumps({"kind": dp.SUMMARY_KIND, "counts": {"postseason_graded": 1, "value_shadow_graded": 0,
                                                                  "kalshi_only_graded": 0}}))
    assert "intl_graded" not in dp.read_ledger_summary(str(p))[0]       # absent -> the Desk reads 0


def test_production_row_carries_the_nfl_divergence_contract():
    sh = {"match_id": 7, "utc_date": KO, "home_team": "A", "away_team": "B", "engine": "model_shadow",
          "gate_verdict": "PASS — confirmation 60/60", "model_version": "intl_elo_v2",
          "market": {"fair_prob": {"HOME": 0.224, "DRAW": 0.3, "AWAY": 0.476}, "fair_source": "1X2"},
          "prediction": {"home_win_prob": 0.549, "draw_prob": 0.25, "away_win_prob": 0.201, "top_pick": "home_win",
                         "top_pick_prob": 0.549, "neutral_v3": None}}
    r = ip.production_row(sh, "UNL")
    assert (r["market_divergence_pp"], r["quarantine"], r["venue_flag"]) == (32.5, True, "unknown")
    assert r["engine"] == "model_edge" and "gate_verdict" not in r and r["competition"] == "UNL"
    assert r["prediction"]["probabilities"] == {"home_win": 0.549, "draw": 0.25, "away_win": 0.201}
    assert ip.production_row({**sh, "market": None}, "CNL")["market_divergence_pp"] is None
    assert ip.VENUE_FLAG == {True: "neutral", False: "home", None: "unknown"}


def test_export_refuses_until_production_allowed_and_writes_nothing(monkeypatch, tmp_path):
    entry = {"id": "intl-elo-v2", "verdict": {"verdict": "PASS"}, "confirmation_window": "60 games"}
    monkeypatch.setattr(reg, "get", lambda eid, path=None: entry if eid == "intl-elo-v2" else None)
    with pytest.raises(ip.IntlRefused, match="not production-allowed .*confirmation window open"):
        ip.export(out_dir=str(tmp_path))
    entry["confirmation"] = {"outcome": "NOT_CONFIRMED", "n_scored": 60, "ids_sha256": "x", "result": {}}
    with pytest.raises(ip.IntlRefused, match="NOT_CONFIRMED"):
        ip.export(out_dir=str(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_confirmed_export_reshapes_the_shadow_and_writes_no_prediction(monkeypatch, tmp_path):
    from src.walters import intl_shadow as us
    init_db()
    entry = {"id": "intl-elo-v2", "verdict": {"verdict": "PASS"},
             "confirmation": {"outcome": "CONFIRMED", "n_scored": 60, "ids_sha256": "x", "result": {"ll": 0.8}}}
    monkeypatch.setattr(reg, "get", lambda eid, path=None: entry if eid == "intl-elo-v2" else None)
    sh = {"match_id": -1, "utc_date": KO, "home_team": "A", "away_team": "B", "engine": "model_shadow",
          "gate_verdict": "x", "model_version": "intl_elo_v2", "market": None,
          "prediction": {"home_win_prob": .5, "draw_prob": .3, "away_win_prob": .2, "top_pick": "home_win",
                         "top_pick_prob": .5, "neutral_v3": False}}
    monkeypatch.setattr(us, "build_rows", lambda now, hours: {"rows": [sh], "fit": {}, "now": NOW.replace(tzinfo=None)})
    path, doc = ip.export(out_dir=str(tmp_path), desk=True)
    assert (doc["sport"], doc["engine"], doc["production_allowed"]) == ("intl", "model_edge", "confirmation CONFIRMED")
    (r,) = doc["predictions"]
    assert r["venue_flag"] == "home" and r["desk"]["engine"] == "model_edge" and doc["desk_meta"]
    assert json.loads(open(path).read())["count"] == 1
    with session_scope() as s:
        assert s.execute(select(func.count(Prediction.id)).where(Prediction.match_id == -1)).scalar() == 0
