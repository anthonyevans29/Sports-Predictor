"""A ONE-SIDED INJURY LIST GETS NO CALL (ARCHITECT 2026-10-11, addendum 40 item 6, #430; finding #425):

"A soccer row says, for each side, how many names are listed and when that team's list was last written. Where one
side's list is empty and the other's is not, the row gets no Desk call and no value shadow: it is a PASS, and its
reason names the team. desk_meta says the rule is on. No probability changes."

The finding's row: 9226 Newcastle at Coventry, Coventry 8 names and Newcastle none, read LADDER Newcastle 0.5u at
an edge of +16.8pp; with no injury term on either side the edge is +10.7pp."""
import json
import math
from datetime import datetime, timedelta, timezone

import pytest

from src.db.database import init_db, session_scope
from src.db.schema import (Competition, Injury, Match, MatchStatus, ModelVersion, Odds, Prediction,
                           PredictionOutcome, Sport, Team)
from src.walters import desk_policy as dp
from src.walters.export import export_predictions
from src.walters.training import _generate_predictions_soccer

NOW = datetime(2091, 10, 12, 9, 0)


def row_9226(home_n=8, away_n=0):
    """Coventry (home) v Newcastle (away): the stored probabilities and the books of the finding's receipt."""
    r = {"match_id": 9226, "home_team": "Coventry City", "away_team": "Newcastle United", "competition": "PL",
         "utc_date": "2091-10-12T19:00:00",
         "prediction": {"probabilities": {"home_win": 0.170, "draw": 0.214, "away_win": 0.616}, "tier": "lean"},
         "market": {"bookmaker_count": 9, "selections": {"HOME": {"fair_prob": 0.300}, "DRAW": {"fair_prob": 0.252},
                                                         "AWAY": {"fair_prob": 0.448}}}}
    if home_n is not None:
        r["input_quality"] = {"injuries": {"home": {"count": home_n, "synced_at": "2091-10-09T22:10:14"},
                                           "away": {"count": away_n, "synced_at": None if away_n == 0 else
                                                    "2091-10-10T09:30:00"}}}
    return r


def desk(*rows):
    doc = dp.annotate({"sport": "soccer", "predictions": [json.loads(json.dumps(r)) for r in rows]},
                      now=NOW.replace(tzinfo=timezone.utc))
    return [p["desk"] for p in doc["predictions"]], doc


def test_the_9226_row_8_and_0_is_a_pass_naming_the_team():
    with dp.injuries_one_sided_rule_off():
        (ladder,), _ = desk(row_9226(8, 0))
    assert ladder["call"] == "LADDER"                                                   # the finding's call
    (d,), doc = desk(row_9226(8, 0))
    assert (d["call"], d["units"], d["pass_kind"]) == ("PASS", 0, "injuries_one_sided")
    assert d["reason"].startswith("injury list one-sided: Newcastle United lists no name, Coventry City lists 8")
    assert d["order"] is None and d["value_shadow"] is None and d["exec"] is None
    assert doc["desk_meta"]["injuries_one_sided_rule"] is True
    assert "injuries_one_sided" in dp.NO_CALL_KINDS


@pytest.mark.parametrize("h,a", [(6, 2), (0, 0), (None, None)])
def test_two_lists_both_empty_or_no_counts_are_unchanged(h, a):
    (on,), _ = desk(row_9226(h, a))
    with dp.injuries_one_sided_rule_off():
        (off,), _ = desk(row_9226(h, a))
    (bare,), _ = desk(row_9226(None, None))
    assert on == off == bare and on["pass_kind"] != "injuries_one_sided"


def test_the_empty_home_side_is_named_too_and_the_switch_off_restores_the_call():
    (d,), _ = desk(row_9226(0, 7))
    assert d["pass_kind"] == "injuries_one_sided" and "Coventry City lists no name, Newcastle United lists 7" in d["reason"]
    with dp.injuries_one_sided_rule_off():
        (off,), doc = desk(row_9226(0, 7))
    (none,), _ = desk(row_9226(None, None))
    assert off == none and doc["desk_meta"]["injuries_one_sided_rule"] is False


def test_another_sport_is_never_read():
    r = row_9226(8, 0)
    on = dp.annotate({"sport": "mlb", "predictions": [dict(r, competition="MLB")]}, now=NOW)["predictions"][0]["desk"]
    with dp.injuries_one_sided_rule_off():
        off = dp.annotate({"sport": "mlb", "predictions": [dict(r, competition="MLB")]},
                          now=NOW)["predictions"][0]["desk"]
    assert on == off


def test_the_desk_golden_holds_with_the_switch_on_and_off():
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import desk_battery as b
    assert all(n > 0 and not bad for _, n, bad in b.check_against_golden())
    with dp.injuries_one_sided_rule_off():
        assert all(n > 0 and not bad for _, n, bad in b.check_against_golden())


# ------------------------------------------------------------------------------- the export's per-side fields --

CODE, SEASON, MV = "IOS", "2091/92", "v-ios"
KICK = datetime(2091, 10, 20, 15, 0)


@pytest.fixture(scope="module")
def world():
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code=CODE, name="One Sided League", area="X", type="LEAGUE")
        s.add(comp)
        teams = [Team(sport=Sport.SOCCER, name=f"OS {n}") for n in ("Alpha", "Beta", "Gamma", "Delta")]
        s.add_all(teams)
        s.flush()
        a, b, g, d = (t.id for t in teams)
        t0 = datetime(2091, 8, 10, 15, 0)
        res = [(a, b, 2, 1), (g, d, 1, 1), (b, g, 0, 2), (d, a, 1, 3), (a, g, 1, 0), (b, d, 2, 2),
               (g, a, 1, 1), (d, b, 0, 1), (b, a, 1, 1), (d, g, 2, 1), (g, b, 3, 0), (a, d, 2, 0)]
        for i, (h, aw, hs, as_) in enumerate(res):
            s.add(Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON, utc_date=t0 + timedelta(days=4 * i),
                        status=MatchStatus.FINISHED, home_team_id=h, away_team_id=aw, home_score=hs, away_score=as_))
        one = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON, utc_date=KICK,
                    status=MatchStatus.SCHEDULED, home_team_id=a, away_team_id=b)
        two = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON, utc_date=KICK + timedelta(hours=2),
                    status=MatchStatus.SCHEDULED, home_team_id=g, away_team_id=d)
        s.add_all([one, two])
        stamp = datetime(2091, 10, 18, 22, 10, 14)
        for k in range(3):
            s.add(Injury(team_id=a, player_name=f"Alpha Out {k}", source="t", refreshed_at=stamp))
        s.add(Injury(team_id=g, player_name="Gamma Out", source="t", refreshed_at=stamp))
        s.add(Injury(team_id=d, player_name="Delta Out", source="t", refreshed_at=stamp + timedelta(hours=11)))
        s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version=MV, status="candidate",
                           parameters={"elo": {"league": {"ratings": {a: 1610.0, b: 1540.0, g: 1580.0, d: 1520.0}},
                                               "cup": {"ratings": {}}},
                                       "team_to_league": {a: CODE, b: CODE, g: CODE, d: CODE}, "contexts": {},
                                       "poisson": {}}))
        s.flush()
        return {"one": one.id, "two": two.id}


def test_the_export_says_each_sides_count_and_when_its_list_was_written(world):
    _generate_predictions_soccer(CODE, SEASON, model_version=MV)
    doc = json.loads(export_predictions(sport=Sport.SOCCER, start_date=KICK - timedelta(days=1),
                                        end_date=KICK + timedelta(days=1), competition_code=CODE,
                                        statuses=[MatchStatus.SCHEDULED], desk=True))
    rows = {r["match_id"]: r for r in doc["predictions"]}
    one, two = rows[world["one"]], rows[world["two"]]
    assert one["input_quality"]["injuries"] == {"home": {"count": 3, "synced_at": "2091-10-18T22:10:14"},
                                                "away": {"count": 0, "synced_at": None}}
    assert two["input_quality"]["injuries"] == {"home": {"count": 1, "synced_at": "2091-10-18T22:10:14"},
                                                "away": {"count": 1, "synced_at": "2091-10-19T09:10:14"}}
    assert one["input_quality"]["injuries_synced_at"] == "2091-10-18T22:10:14"          # unchanged, pair stamp
    assert one["injuries"]["home_count"] == 3 and one["injuries"]["away_count"] == 0     # unchanged block
    assert one["desk"]["pass_kind"] == "injuries_one_sided" and "OS Beta lists no name" in one["desk"]["reason"]
    assert two["desk"]["pass_kind"] != "injuries_one_sided"
    assert doc["desk_meta"]["injuries_one_sided_rule"] is True


# ----------------------------------------------------------------------------------------------- the receipt --

def test_the_receipt_reprices_without_the_cut_and_reads_log_loss_both_ways(tmp_path):
    """The 9226 shape (8 and 0) graded: stored xG 0.76 / 1.822 at rho -0.10 (the architect's rebuild), re-priced
    with Coventry's -24% taken out. The stored 1X2 is rebuilt to 3 decimals; the books' edge on Newcastle is
    +16.8pp stored and +10.7pp without the cut (still >= +5pp)."""
    import scripts.soccer_injury_factor_receipt as rc
    init_db()
    hxg, axg = 0.76, 1.822
    p = rc.one_x_two(hxg, axg, -0.10, 10)
    assert round(p["AWAY"], 3) == 0.616
    bare = rc.one_x_two(hxg / 0.76, axg, -0.10, 10)
    assert round(bare["AWAY"], 3) == 0.556                                            # "no injury term": 0.556
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code="RIF", name="Receipt League", area="X", type="LEAGUE")
        s.add(comp)
        h, a = Team(sport=Sport.SOCCER, name="RIF Coventry"), Team(sport=Sport.SOCCER, name="RIF Newcastle")
        s.add_all([h, a])
        s.flush()
        ko = datetime(2091, 10, 13, 19, 0)
        m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2091/92", utc_date=ko,
                  status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=0, away_score=2)
        s.add(m)
        s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v-rif", status="retired",
                           parameters={"poisson": {"dixon_coles_rho": -0.10, "max_goals": 10}}))
        s.flush()
        pr = Prediction(match_id=m.id, model_version="v-rif", home_win_prob=p["HOME"], draw_prob=p["DRAW"],
                        away_win_prob=p["AWAY"], expected_home_score=hxg, expected_away_score=axg,
                        factor_breakdown={"home_injuries_count": 8, "away_injuries_count": 0,
                                          "factor_notes": ["home missing 8 (-24% xG)"]})
        s.add(pr)
        s.flush()
        s.add(PredictionOutcome(prediction_id=pr.id))
        fair = {"HOME": 0.300, "DRAW": 0.252, "AWAY": 0.448}
        for bk in ("b1", "b2"):
            for sel, f in fair.items():
                s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=1 / f,
                           captured_at=ko - timedelta(hours=1), source="t"))
    with session_scope() as s:
        rs, skipped = rc.rows(s, "RIF")
    (x,) = rs
    assert x["reproduces"] and x["counts"] == (8, 0) and x["diff"] == 8 and x["result"] == "AWAY"
    assert x["note_mismatch"] == [] and x["pick"] == "AWAY"
    assert round(x["edge_pp"], 1) == 16.8 and round(x["edge_bare_pp"], 1) == 10.8
    assert math.isclose(x["ll_stored"], -math.log(p["AWAY"])) and math.isclose(x["ll_bare"], -math.log(bare["AWAY"]))
    sm = rc.summary(rs)
    assert sm["by_diff"]["6+"]["n"] == 1 and sm["by_diff"]["0"]["n"] == 0
    assert sm["positive_edge"] == {"n": 1, "ll_stored": round(x["ll_stored"], 4),
                                   "ll_without_cut": round(x["ll_bare"], 4), "keep_5pp_without_cut": 1}
    out = []
    rc.report(rs, skipped, "RIF", True, echo=out.append)
    assert out[-1].startswith("SOCCER-INJURY-FACTOR ") and any("keep +5pp without the cut: 1/1" in o for o in out)


def test_the_receipts_fallback_connection_refuses_a_write(tmp_path):
    """#421's rule on this receipt: a copy that refuses mode=ro is opened on the plain path with query_only."""
    import sqlite3
    import scripts.soccer_injury_factor_receipt as rc
    from sqlalchemy import text
    f = tmp_path / "copy.db"
    con = sqlite3.connect(f)
    con.execute("CREATE TABLE predictions (id INTEGER)")
    con.commit()
    con.close()
    eng = rc.query_only_engine(f)
    with eng.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM predictions")).scalar() == 0
        with pytest.raises(Exception, match="readonly|read-only|query_only"):
            c.execute(text("INSERT INTO predictions VALUES (1)"))
