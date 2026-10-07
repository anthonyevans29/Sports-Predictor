"""ARCHITECT 2026-10-07 addendum 3, item C (on #323/#325):
"INTL calls are graded on the 90-MINUTE result, never on a score that includes extra time or penalties. The results
path for an INTL call reads the stored 90-minute score; where a game went beyond 90 minutes and no 90-minute score
is stored, the call is left ungraded and listed, never graded on the later score. ... Amended: the production INTL
export writes no predictions row, but it DOES append to prediction_history on every export (model version, three
probabilities, computed_at), as the K-track rule requires of every model sport."

Synthetic DB rows only (year 2098, probe names); the registry is monkeypatched; exports land in tmp_path."""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.db.database import append_prediction_history, init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Prediction, PredictionHistory, Sport, Team
from src.walters import intl_production as ip

NOW = datetime(2098, 6, 1, 12, 0)


@pytest.fixture(scope="module")
def world():
    init_db()
    with session_scope() as s:
        c = s.execute(select(Competition).where(Competition.code == "UNL")).scalar_one_or_none()
        if c is None:
            c = Competition(sport=Sport.SOCCER, code="UNL", name="UNL", area="I", type="INTL")
            s.add(c)
            s.flush()
        t = [Team(sport=Sport.SOCCER, name=f"Ninety Probe {i}") for i in range(2)]
        s.add_all(t)
        s.flush()

        def m(day, raw, status=MatchStatus.FINISHED, s90=None, sc=None):
            g = Match(sport=Sport.SOCCER, competition_id=c.id, season="2097/98", utc_date=datetime(2098, 5, day, 19),
                      status=status, status_raw=raw, home_team_id=t[0].id, away_team_id=t[1].id,
                      home_score_90=s90[0] if s90 else None, away_score_90=s90[1] if s90 else None,
                      home_score=sc[0] if sc else None, away_score=sc[1] if sc else None)
            s.add(g)
            s.flush()
            return g.id
        ids = {
            "reg": m(1, "FT", s90=(2, 0), sc=(2, 0)),         # regulation result: H
            "ft": m(2, "FT", sc=(0, 1)),                      # FT, no score_90 column yet: the FT score is the 90'
            "aet90": m(3, "AET", s90=(1, 1), sc=(2, 1)),      # beyond 90 WITH a stored 90' score: graded D
            "pen": m(4, "PEN", sc=(1, 1)),                    # beyond 90, no 90' score: ungraded + listed
            "aet": m(5, "AET", sc=(3, 2)),                    # beyond 90, no 90' score: ungraded + listed
            "next": m(28, None, status=MatchStatus.SCHEDULED, sc=None),
        }
        names = (t[0].name, t[1].name)
    return ids, names


def _history(ids, extra=()):
    rows = [{"match_id": ids[k], "model_version": ip.MODEL_VERSION, "computed_at": datetime(2098, 5, d, 10),
             "home_win_prob": .5, "draw_prob": .3, "away_win_prob": .2}
            for k, d in (("reg", 1), ("ft", 2), ("aet90", 3), ("pen", 4), ("aet", 5))]
    with session_scope() as s:
        append_prediction_history(s.connection(), rows + list(extra))


def test_graded_on_the_90_minute_result_only_and_beyond_90_listed(world, tmp_path):
    ids, _ = world
    _history(ids, extra=[
        # after kickoff: never the call (the last row BEFORE kickoff is)
        {"match_id": ids["reg"], "model_version": ip.MODEL_VERSION, "computed_at": datetime(2098, 5, 1, 20),
         "home_win_prob": .1, "draw_prob": .1, "away_win_prob": .8},
        # another model version: not an INTL production call
        {"match_id": ids["aet"], "model_version": "other", "computed_at": datetime(2098, 5, 5, 11),
         "home_win_prob": .2, "draw_prob": .2, "away_win_prob": .6}])
    path, doc = ip.export_results(now=NOW, out_dir=str(tmp_path))
    assert path.endswith("intl_INTL_results_2098-06-01.json") and json.loads(open(path).read())["sport"] == "intl"
    by = {r["match_id"]: r for r in doc["results"]}
    un = {r["match_id"]: r for r in doc["ungraded"]}
    mine = set(ids.values())
    assert set(by) & mine == {ids["reg"], ids["ft"], ids["aet90"]}
    assert set(un) & mine == {ids["pen"], ids["aet"]}               # listed, never graded on the later score
    # regulation result
    r = by[ids["reg"]]
    assert r["actual"] == {"home_score": 2, "away_score": 0, "result": "H", "score_basis": "score_90",
                           "status_raw": "FT"}
    assert r["predicted"]["top_pick"] == "home_win" and r["graded"]["top_pick_hit"] is True
    assert r["graded"]["log_loss"] == round(-__import__("math").log(.5), 4)
    # a FT row without the score_90 column: its FT score is the 90-minute score
    r = by[ids["ft"]]
    assert (r["actual"]["result"], r["actual"]["score_basis"], r["graded"]["top_pick_hit"]) == ("A", "FT score", False)
    # AET with a stored 90-minute score: graded on 1-1 (a DRAW), not on the 2-1 after extra time
    r = by[ids["aet90"]]
    assert (r["actual"]["home_score"], r["actual"]["away_score"], r["actual"]["result"]) == (1, 1, "D")
    assert r["actual"]["after_extra_time"] == {"home_score": 2, "away_score": 1}
    assert r["graded"]["top_pick_hit"] is False and r["graded"]["push"] is False
    # beyond 90 with no 90-minute score: ungraded, with the reason
    assert un[ids["pen"]]["reason"].startswith("went beyond 90 minutes (PEN) and no 90-minute score is stored")
    assert un[ids["aet"]]["status_raw"] == "AET" and "never graded on the later score" in un[ids["aet"]]["reason"]
    assert "actual" not in un[ids["aet"]] and "graded" not in un[ids["aet"]]
    assert doc["record"]["ungraded"] == len(doc["ungraded"]) and doc["count"] == len(doc["results"])


def test_ungraded_reason_vocabulary():
    class M:
        def __init__(self, raw):
            self.status_raw = raw
    assert ip.ungraded_reason(M("aet")).startswith("went beyond 90 minutes (AET)")
    assert ip.ungraded_reason(M("FT")) == "finished FT, score not stored yet"
    assert ip.ungraded_reason(M("AWD")) == "no 90-minute score stored (status_raw AWD): not graded"
    assert ip.ungraded_reason(M(None)) == "no 90-minute score stored (status_raw NULL): not graded"


def test_every_export_appends_history_and_writes_no_prediction(world, monkeypatch, tmp_path):
    from src.walters import intl_shadow as us
    ids, (home, away) = world
    mid = ids["next"]
    monkeypatch.setattr(ip, "allowed", lambda: (True, "confirmation CONFIRMED"))
    ko = "2098-05-28T19:00:00"
    sh = {"match_id": mid, "utc_date": ko, "home_team": home, "away_team": away, "engine": "model_shadow",
          "gate_verdict": "x", "model_version": "intl_elo_v2", "market": None,
          "prediction": {"home_win_prob": .45, "draw_prob": .3, "away_win_prob": .25, "top_pick": "home_win",
                         "top_pick_prob": .45, "neutral_v3": False}}
    at = [datetime(2098, 5, 27, 8), datetime(2098, 5, 27, 9)]
    for t in at:
        monkeypatch.setattr(us, "build_rows", lambda now, hours, t=t: {"rows": [sh], "fit": {}, "now": t})
        _, doc = ip.export(out_dir=str(tmp_path))
        assert doc["prediction_history_appended"] == 1
    with session_scope() as s:
        h = list(s.execute(select(PredictionHistory).where(PredictionHistory.match_id == mid)
                           .order_by(PredictionHistory.computed_at)).scalars())
        assert [(x.model_version, x.computed_at, x.home_win_prob, x.draw_prob, x.away_win_prob) for x in h] == [
            ("intl_elo_v2", t, .45, .3, .25) for t in at]
        assert s.execute(select(func.count(Prediction.id)).where(Prediction.match_id == mid)).scalar() == 0
    assert len(list(tmp_path.glob("intl_predictions_*.json"))) == 2


def test_results_command_lists_the_ungraded(world, monkeypatch, tmp_path):
    from click.testing import CliRunner
    import cli
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ip, "export_results", lambda days=None: ("exports/x.json", {
        "window": {"kind": "all_production_calls"}, "record": {"games": 1, "hits": 0, "decided": 1, "ungraded": 1},
        "ungraded": [{"match_id": 9, "home_team": "H", "away_team": "A", "utc_date": "2098-05-04T19:00:00",
                      "reason": "went beyond 90 minutes (PEN) and no 90-minute score is stored: never graded on "
                                "the later score"}]}))
    out = CliRunner().invoke(cli.cli, ["export-intl-results"]).output
    assert "ungraded 1" in out and "UNGRADED match 9 A @ H 2098-05-04: went beyond 90 minutes (PEN)" in out
