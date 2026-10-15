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
from src.db.schema import (Competition, Injury, Match, MatchStatus, ModelVersion, Odds, OddsSnapshot, Prediction,
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


def test_codex_rho_is_read_as_of_the_prediction_and_only_from_the_soccer_model_row():
    """Codex on #435: (1) ModelVersion.version is unique only with sport and family, so the lookup is scoped to
    soccer / soccer_elo_poisson; (2) set-soccer-config edits rho in place, so an earlier prediction reads the value
    before every later audited edit."""
    import scripts.soccer_injury_factor_receipt as rc
    params = {"poisson": {"dixon_coles_rho": -0.10, "max_goals": 10},
              "manual_config_edits": [{"ts": "2091-09-01T00:00:00", "field": "poisson.dixon_coles_rho",
                                       "from": "(default)", "to": -0.05},
                                      {"ts": "2091-09-20T00:00:00", "field": "poisson.dixon_coles_rho",
                                       "from": -0.05, "to": -0.10}]}
    assert rc.poisson_as_of(params, datetime(2091, 10, 1)) == (-0.10, 10)
    assert rc.poisson_as_of(params, datetime(2091, 9, 10)) == (-0.05, 10)
    assert rc.poisson_as_of(params, datetime(2091, 8, 1)) == (0.0, 10)                 # before both: the default
    init_db()
    with session_scope() as s:
        s.add(ModelVersion(sport=Sport.MLB, model_family="mlb_poisson", version="v-shared", status="production",
                           parameters={}))
        s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v-shared",
                           status="retired", parameters={"poisson": {"dixon_coles_rho": -0.10, "max_goals": 10}}))
        comp = Competition(sport=Sport.SOCCER, code="RSV", name="Shared Version League", area="X", type="LEAGUE")
        s.add(comp)
        h, a = Team(sport=Sport.SOCCER, name="RSV H"), Team(sport=Sport.SOCCER, name="RSV A")
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2091/92", utc_date=datetime(2091, 10, 1, 15),
                  status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=1, away_score=1)
        s.add(m)
        s.flush()
        p = rc.one_x_two(1.3, 1.1, -0.10, 10)
        pr = Prediction(match_id=m.id, model_version="v-shared", home_win_prob=p["HOME"], draw_prob=p["DRAW"],
                        away_win_prob=p["AWAY"], expected_home_score=1.3, expected_away_score=1.1,
                        computed_at=datetime(2091, 9, 30), factor_breakdown={"home_injuries_count": 2,
                                                                             "away_injuries_count": 2})
        s.add(pr)
        s.flush()
        s.add(PredictionOutcome(prediction_id=pr.id))
    with session_scope() as s:
        (x,), _ = rc.rows(s, "RSV")
    assert x["model_params_found"] and x["reproduces"]                                 # the soccer row's rho -0.10


def test_base_v11_holds_the_one_sided_rule_off():
    with dp.base_v11():
        (d,), doc = desk(row_9226(8, 0))
    assert d["call"] == "LADDER" and doc["desk_meta"]["injuries_one_sided_rule"] is False
    assert dp.INJURIES_ONE_SIDED_RULE["on"] is True


def test_437_every_aggregate_over_the_rows_the_receipt_stands_behind():
    """#437 RULED (ARCHITECT 2026-10-11, addendum 41 item 2): a row whose stored 1X2 is not rebuilt to 3 decimals, or
    whose factor note disagrees with the cut taken back (a missing note included), is left out of every aggregate,
    counted by reason and listed; the all-rows line stays, marked."""
    import scripts.soccer_injury_factor_receipt as rc

    def row(pid, *, reproduces=True, notes=("home missing 3 (-9% xG)",), counts=(3, 0), edge=8.0):
        fb = {"home_injuries_count": counts[0], "away_injuries_count": counts[1], "factor_notes": list(notes)}
        return {"prediction_id": pid, "match_id": pid, "game": f"A{pid} @ H{pid}", "kickoff": "2026-10-01T14:00:00",
                "model_version": "v", "counts": counts, "diff": abs(counts[0] - counts[1]), "result": "HOME",
                "stored": {"HOME": 0.5, "DRAW": 0.3, "AWAY": 0.2}, "bare": {"HOME": 0.55, "DRAW": 0.27, "AWAY": 0.18},
                "reproduces": reproduces, "model_params_found": True, "ll_stored": 1.0, "ll_bare": 2.0 if pid > 1 else 0.5,
                "pick": "HOME", "edge_pp": edge, "edge_bare_pp": edge, "note_mismatch": rc.note_mismatch(fb)}
    rs = [row(1), row(2, reproduces=False), row(3, notes=("home missing 3 (-15% xG)",)), row(4, notes=())]
    assert rs[2]["note_mismatch"] and rs[3]["note_mismatch"] == ["home: 3 name(s), no note"]
    sm = rc.summary(rs)
    assert sm["all"]["n"] == 1 and sm["all"]["ll_without_cut"] == 0.5                     # row 1 alone
    assert sm["all_rows_reference"]["n"] == 4                                               # the marked line stays
    assert sm["by_diff"]["3-5"]["n"] == 1 and sm["positive_edge"]["n"] == 1
    assert sm["left_out_rows"] == 3 and sm["left_out"] == {rc.LEFT_OUT[0]: 1, rc.LEFT_OUT[1]: 2, rc.LEFT_OUT[2]: 0}
    out = []
    rc.report(rs, {}, "PL", False, echo=out.append)
    assert sum(1 for o in out if o.lstrip().startswith("LEFT OUT ")) == 3                   # listed without --list
    assert any(o.lstrip().startswith("ALL ROWS (reference)") and "n    4" in o for o in out)
    assert any("left out of every aggregate (#437 RULED): 3 row(s)" in o for o in out)


def test_437_3_a_side_at_the_xg_floor_with_a_cut_is_left_out_under_its_own_reason():
    """#437's third item RULED (ARCHITECT 2026-10-11, addendum 42 item 2): a cut cannot be taken back from a floored
    number. A pre-cut xG of 0.055 cut 25% is stored as 0.05; the rebuild still reproduces (it uses the floored value),
    so only this reason catches it. A side at the floor with no cut, or a cut side above it, is not floored."""
    import scripts.soccer_injury_factor_receipt as rc
    assert rc.floored(0.05, 1.4, 9, 0) == ["home"]
    assert rc.floored(0.05, 1.4, 0, 3) == [] and rc.floored(0.06, 0.05, 2, 0) == []
    x = {"reproduces": True, "note_mismatch": [], "floored": ["home"]}
    assert rc.left_out(x) == [rc.LEFT_OUT[2]]
    p = rc.one_x_two(0.05, 1.4, -0.10, 10)
    assert rc.one_x_two(0.05 / (1 - rc.reduction(9)), 1.4, -0.10, 10)["HOME"] != p["HOME"]   # the bogus take-back


def test_the_receipt_isolates_the_guard_per_case_and_counts_the_calls_only_it_changed():
    """Addendum 74 item 3 (#425): for each case the Desk's call with the one-sided-list guard on and with its own switch
    off, as of the prediction's computed_at against the book reference an export built then read; the receipt counts
    the cases where only the guard changed the call. Ten graded cases on the receipt's own shape (stored xG 0.76 /
    1.822 at rho -0.10, AWAY 0.616; two books; computed 3h before kickoff). As sync_odds leaves them since #167: a
    sync REPLACES the odds rows and appends its consensus to odds_snapshots.
    0  8/0 a 4h sync at 0.448 (a snapshot now, source NULL as a legacy row), replaced by a 1h sync at 0.600, and a
       Kalshi row at 3h30 that never reads as books: held; LADDER (X2) off from the snapshot: changed, a draw: won
       (the grading close reads 0.600)
    1  6/2 a 4h sync at 0.448 (odds rows and its snapshot, the same session): LADDER either way, read from the odds
    2  8/0 books 0.600 at 4h: held; PASS noref off: not changed
    3  6/2 books 0.600: PASS noref either way (a PASS the guard did not make)
    4  8/0 books 0.448, no factor note: left out of every aggregate (counted in the all-rows line only)
    5  8/0 books 0.448, the home rating the default: default_rating either way (an earlier rule)
    6  0/5 books 0.448, computed 10 minutes after kickoff: started either way (an earlier rule)
    7  0/3 books 0.560: held; PLAY AWAY off: changed, a home win: lost
    8  0/3 odds rows only at 1h, no snapshot: the session read at computed_at may have been replaced: not evaluated
    9  0/3 no odds and no snapshot at all: no reference; held; PASS noref off: not changed"""
    import scripts.soccer_injury_factor_receipt as rc
    init_db()
    hxg, axg = 0.76, 1.822
    p = rc.one_x_two(hxg, axg, -0.10, 10)
    lad, flat, play = ({"HOME": 0.300, "DRAW": 0.252, "AWAY": 0.448}, {"HOME": 0.180, "DRAW": 0.220, "AWAY": 0.600},
                       {"HOME": 0.200, "DRAW": 0.240, "AWAY": 0.560})
    H4, H1, H3 = timedelta(hours=-4), timedelta(hours=-1), timedelta(hours=-3)
    cases = [  # counts, odds rows [(offset, fair)], snapshots [(offset, fair)], result, extra fb, computed_at, noted
        ((8, 0), [(H1, flat)], [(H4, lad), (H1, flat)], (1, 1), {}, H3, True),
        ((6, 2), [(H4, lad)], [(H4, lad)], (1, 0), {}, H3, True),
        ((8, 0), [(H4, flat)], [], (0, 1), {}, H3, True),
        ((6, 2), [(H4, flat)], [], (0, 1), {}, H3, True),
        ((8, 0), [(H4, lad)], [], (0, 2), {}, H3, False),
        ((8, 0), [(H4, lad)], [], (0, 2), {"home_rating_source": "default", "away_rating_source": "model"}, H3, True),
        ((0, 5), [(H4, lad)], [], (0, 2), {}, timedelta(minutes=10), True),
        ((0, 3), [(H4, play)], [], (1, 0), {}, H3, True),
        ((0, 3), [(H1, lad)], [], (0, 2), {}, H3, True),
        ((0, 3), [], [], (0, 2), {}, H3, True)]
    pids = []
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code="RIG", name="Guard League", area="X", type="LEAGUE")
        s.add(comp)
        s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v-rig", status="retired",
                           parameters={"poisson": {"dixon_coles_rho": -0.10, "max_goals": 10}}))
        s.flush()
        for i, ((hc, ac), books, snaps, (hs, as_), extra, at, noted) in enumerate(cases):
            h, a = Team(sport=Sport.SOCCER, name=f"RIG H{i}"), Team(sport=Sport.SOCCER, name=f"RIG A{i}")
            s.add_all([h, a])
            s.flush()
            ko = datetime(2091, 10, 13 + i, 19, 0)
            m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2091/92", utc_date=ko,
                      status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=hs, away_score=as_)
            s.add(m)
            s.flush()
            notes = [f"{side} missing {n} (-{int(rc.reduction(n) * 100)}% xG)" for side, n in (("home", hc), ("away", ac))
                     if n and noted]
            pr = Prediction(match_id=m.id, model_version="v-rig", home_win_prob=p["HOME"], draw_prob=p["DRAW"],
                            away_win_prob=p["AWAY"], expected_home_score=hxg, expected_away_score=axg,
                            computed_at=ko + at,
                            factor_breakdown={"home_injuries_count": hc, "away_injuries_count": ac,
                                              "factor_notes": notes, **extra})
            s.add(pr)
            s.flush()
            pids.append(pr.id)
            s.add(PredictionOutcome(prediction_id=pr.id))
            for off, fair in books:
                for bk in ("b1", "b2"):
                    for sel, f in fair.items():
                        s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=1 / f,
                                   captured_at=ko + off, source="t"))
            for off, fair in snaps:
                for sel, f in fair.items():
                    s.add(OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=f, line=None, n_books=2,
                                       captured_at=ko + off, source=None if i == 0 else "t"))   # Codex: NULL source
                if i == 0:                                       # a later Kalshi row by then never reads as books
                    s.add(OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=0.9, line=None,
                                       n_books=0, captured_at=ko + timedelta(hours=-3, minutes=-30), source="kalshi"))
    with session_scope() as s:
        rs, skipped = rc.rows(s, "RIG")
    by = {x["prediction_id"]: x for x in rs}
    held = {"call": "PASS", "units": 0, "pass_kind": "injuries_one_sided"}
    assert by[pids[0]]["desk_on"] == held and by[pids[0]]["desk_off"]["call"] == "LADDER"
    assert by[pids[0]]["desk_ref"] == {"books": 2, "captured_at": "2091-10-13T15:00:00", "from": "snapshot"}
    assert by[pids[0]]["edge_pp"] == pytest.approx((p["AWAY"] - 0.600) * 100)                  # the grading close
    assert by[pids[1]]["desk_on"] == by[pids[1]]["desk_off"] and by[pids[1]]["desk_on"]["call"] == "LADDER"
    assert by[pids[1]]["desk_ref"]["from"] == "odds"                                            # a tie: the odds table
    assert by[pids[2]]["desk_on"] == held and by[pids[2]]["desk_off"]["pass_kind"] == "noref"
    assert by[pids[3]]["desk_on"] == by[pids[3]]["desk_off"] == {"call": "PASS", "units": 0, "pass_kind": "noref"}
    assert rc.left_out(by[pids[4]]) and by[pids[4]]["desk_on"] == held and by[pids[4]]["desk_off"]["call"] == "LADDER"
    for i, kind in ((5, "default_rating"), (6, "started")):
        assert by[pids[i]]["desk_on"] == by[pids[i]]["desk_off"] == {"call": "PASS", "units": 0, "pass_kind": kind}
    assert by[pids[7]]["desk_on"] == held and by[pids[7]]["desk_off"]["call"] == "PLAY"
    assert by[pids[8]]["desk_on"] is None and by[pids[8]]["desk_skip"] == rc.UNKNOWN_REF
    assert by[pids[8]]["edge_pp"] == pytest.approx((p["AWAY"] - 0.448) * 100)                 # the close still prices
    assert by[pids[9]]["desk_ref"] is None and by[pids[9]]["desk_on"] == held
    assert by[pids[9]]["desk_off"]["pass_kind"] == "noref" and by[pids[9]]["edge_pp"] is None
    sm = rc.summary(rs)
    assert sm["guard"] == {"n": 8, "not_evaluated": {rc.UNKNOWN_REF: 1},
                           "reference": {"none": 1, "odds": 6, "snapshot": 1}, "one_sided": 6, "held": 4,
                           "one_sided_earlier": {"default_rating": 1, "started": 1},
                           "earlier": {"default_rating": 1, "started": 1},
                           "held_off": {"LADDER": 1, "PASS noref": 2, "PLAY": 1}, "changed_call": 2,
                           "changed_by_reference": {"odds": 1, "snapshot": 1},
                           "changed_graded": {"LADDER X2 won": 1, "PLAY AWAY lost": 1},
                           "changed_ids": [pids[0], pids[7]]}
    g = sm["guard"]
    assert g["one_sided"] == g["held"] + sum(g["one_sided_earlier"].values())
    ga = sm["guard_all_rows_reference"]
    assert (ga["n"], ga["one_sided"], ga["held"], ga["changed_call"]) == (9, 7, 5, 3)
    assert dp.INJURIES_ONE_SIDED_RULE["on"] is True                    # the switch default is untouched
    out = []
    rc.report(rs, skipped, "RIG", True, echo=out.append)
    assert any(o.startswith("THE ONE-SIDED-LIST GUARD, ISOLATED (addendum 74 item 3)") for o in out)
    assert (f"  over the rows the receipt stands behind: n 8 · the Desk's reference read from: none 1 · odds 6 · "
            f"snapshot 1 · not evaluated: {rc.UNKNOWN_REF} 1") in out
    assert "  reached by an earlier rule first (both runs alike): default_rating 1 · started 1" in out
    assert ("  one-sided lists (the guard's condition) 6: held by the guard 4 · reached by an earlier rule first 2 "
            "(default_rating 1 · started 1)") in out
    assert "  the guard held (PASS injuries_one_sided) 4 · with it off those read: LADDER 1 · PASS noref 2 · PLAY 1" in out
    assert (f"  cases where only the guard changed the call: 2/8 · their reference read from: odds 1 · snapshot 1 · "
            f"graded by the instrument: LADDER X2 won 1 · PLAY AWAY lost 1 · predictions {pids[0]}, {pids[7]}") in out
    assert any(o.startswith(f"  {pids[0]} ·") and o.endswith("PASS injuries_one_sided / LADDER · ref 2 books at "
                                                             "2091-10-13T15:00:00 (snapshot)") for o in out)
    assert any(o.startswith(f"  {pids[8]} ·") and o.endswith(f"not evaluated: {rc.UNKNOWN_REF}") for o in out)
    assert any(o.startswith(f"  {pids[9]} ·") and o.endswith("PASS injuries_one_sided / PASS noref · ref none")
               for o in out)
    assert '"guard": {"changed_by_reference": {"odds": 1, "snapshot": 1}, "changed_call": 2' in out[-1]


def test_the_as_of_reference_reads_the_session_the_export_read_then():
    """The later session wins across the two tables (the odds table on a tie); an unpriced odds-table session read then
    is no reference even with an older snapshot; a later odds session alone is unknown; nothing at all is none."""
    from types import SimpleNamespace as N
    import scripts.soccer_injury_factor_receipt as rc
    ko, at = datetime(2091, 1, 1, 19), datetime(2091, 1, 1, 16)

    def book(t, bk, fair, sels=("HOME", "DRAW", "AWAY")):
        return [N(market="1X2", bookmaker=bk, selection=k, price_decimal=1 / fair[k], captured_at=t, line=None)
                for k in sels]

    def snap(t, fair):
        return [N(market="1X2", selection=k, devig_prob=v, n_books=3, captured_at=t, source="api_football")
                for k, v in fair.items()]
    f1, f2 = {"HOME": 0.5, "DRAW": 0.25, "AWAY": 0.25}, {"HOME": 0.123456, "DRAW": 0.3, "AWAY": 0.576544}
    t12, t14 = datetime(2091, 1, 1, 12), datetime(2091, 1, 1, 14)
    ref, src = rc.as_of_reference(book(t12, "b", f1), snap(t14, f2), at, ko)
    assert src == "snapshot" and ref == {"books": 3, "fair": {"HOME": 0.1235, "DRAW": 0.3, "AWAY": 0.5765},
                                         "captured_at": t14}
    assert rc.as_of_reference(book(t14, "b", f1), snap(t12, f2), at, ko)[1] == "odds"
    assert rc.as_of_reference(book(t14, "b", f1), snap(t14, f2), at, ko)[1] == "odds"
    assert rc.as_of_reference(book(t14, "b", f1, ("HOME", "AWAY")), snap(t12, f2), at, ko) == (None, "none")
    assert rc.as_of_reference(book(datetime(2091, 1, 1, 18), "b", f1), [], at, ko) == (None, "unknown")
    assert rc.as_of_reference([], [], at, ko) == (None, "none")
    assert rc.as_of_reference(book(datetime(2091, 1, 1, 20), "b", f1), [], at, ko) == (None, "none")  # after kickoff


def test_the_guard_block_reads_only_rows_that_carry_both_calls_and_grades_by_the_instrument():
    import scripts.soccer_injury_factor_receipt as rc
    on = {"call": "PASS", "units": 0, "pass_kind": "injuries_one_sided"}
    rs = [{"prediction_id": 1, "result": "HOME", "pick": "AWAY", "counts": (0, 4), "desk_on": on,
           "desk_off": {"call": "PLAY", "units": 1, "pass_kind": None}, "desk_ref": {"from": "snapshot"},
           "desk_pick": "AWAY"},
          {"prediction_id": 2, "result": "HOME", "pick": "HOME", "counts": (0, 4), "desk_on": None, "desk_off": None,
           "desk_skip": rc.NO_COMPUTED_AT},
          {"prediction_id": 3, "result": "HOME", "pick": "HOME", "counts": (3, 0)}]            # an older row: no calls
    assert rc.guard_summary(rs) == {"n": 1, "not_evaluated": {"no computed_at": 1, "no desk calls": 1},
                                    "reference": {"snapshot": 1}, "one_sided": 1, "held": 1, "one_sided_earlier": {},
                                    "earlier": {}, "held_off": {"PLAY": 1}, "changed_call": 1,
                                    "changed_by_reference": {"snapshot": 1}, "changed_graded": {"PLAY AWAY lost": 1}, "changed_ids": [1]}
    assert [rc.instrument("LADDER", "AWAY", r) for r in ("AWAY", "DRAW", "HOME")] == \
        ["LADDER X2 won", "LADDER X2 won", "LADDER X2 lost"]
    assert rc.instrument("LADDER", "DRAW", "DRAW") == "LADDER DRAW not graded"
    assert [rc.instrument("PLAY", "HOME", r) for r in ("HOME", "DRAW")] == ["PLAY HOME won", "PLAY HOME lost"]
    assert [rc.one_sided(c) for c in ((0, 0), (0, 2), (3, 0), (6, 2))] == [False, True, True, False]
    assert rc.desk_row(_match_stub(), "PL", {"HOME": 0.539951, "DRAW": None, "AWAY": 0.2}, None, 0, 1, {})[
        "prediction"]["probabilities"] == {"home_win": 0.54, "draw": None, "away_win": 0.2}      # the export's 4dp


def test_537_a_changed_call_is_graded_on_the_desks_own_pick_from_the_rounded_1x2():
    """#537 FIXED (addendum 79 item 1): the Desk picks from the export's 4-decimal probabilities, walking HOME, DRAW,
    AWAY and moving only on a strictly greater one (desk_policy.normalize). AWAY 0.50001 and DRAW 0.49997 sit within
    0.0001 of each other and both round to 0.5000: the Desk picks DRAW, while the unrounded pick (rows()'s, the edge
    lines') is AWAY. A draw: the guard's changed call, a PLAY with it off, is graded on the Desk's DRAW, a win."""
    from types import SimpleNamespace as N
    import scripts.soccer_injury_factor_receipt as rc
    stored = {"HOME": 0.00002, "DRAW": 0.49997, "AWAY": 0.50001}
    assert abs(stored["AWAY"] - stored["DRAW"]) < 1e-4 and rc.r4(stored["AWAY"]) == rc.r4(stored["DRAW"]) == 0.5
    assert max(rc.SIDES, key=lambda k: stored[k]) == "AWAY"                       # rows()'s unrounded pick
    fair = {"HOME": 0.10, "DRAW": 0.44, "AWAY": 0.46}                              # DRAW +6pp: a PLAY with the guard off
    odds = [N(market="1X2", bookmaker=bk, selection=k, price_decimal=1 / v, captured_at=datetime(2091, 1, 1, 15),
              line=None) for bk in ("b1", "b2") for k, v in fair.items()]
    g = rc.guard_calls(_match_stub(), "PL", stored, (odds, []), 0, 3, {}, datetime(2091, 1, 1, 16))
    assert g["desk_pick"] == "DRAW" and g["desk_ref"]["from"] == "odds"
    assert g["desk_on"]["pass_kind"] == dp.INJURIES_ONE_SIDED_KIND and g["desk_off"]["call"] == "PLAY"
    x = {"prediction_id": 1, "result": "DRAW", "pick": "AWAY", "counts": (0, 3), **g}
    s = rc.guard_summary([x])
    assert s["changed_call"] == 1 and s["changed_graded"] == {"PLAY DRAW won": 1}   # never "PLAY AWAY lost"
    assert rc.guard_calls(_match_stub(), "PL", stored, (odds, []), 0, 3, {}, None)["desk_pick"] is None
    ll = rc.ll(stored["DRAW"])                                  # the listing names the Desk's pick where it differs
    row = {**x, "match_id": 1, "game": "A @ H", "kickoff": "2091-01-01T19:00:00", "model_version": "v", "diff": 3,
           "stored": stored, "bare": stored, "reproduces": True, "model_params_found": True, "ll_stored": ll,
           "ll_bare": ll, "edge_pp": 4.0, "edge_bare_pp": 4.0, "note_mismatch": [], "floored": []}
    out = []
    rc.report([row], {"no injury counts": 0, "no expected goals": 0}, "PL", True, echo=out.append)
    assert any(o.endswith("· AWAY +4.0 / +4.0pp · PASS injuries_one_sided / PLAY (the Desk's pick DRAW) · ref 2 "
                          "books at 2091-01-01T15:00:00 (odds)") for o in out)
    assert any("graded by the instrument: PLAY DRAW won 1" in o for o in out)


def _match_stub():
    from types import SimpleNamespace as N
    return N(id=1, home_team=N(name="H"), away_team=N(name="A"), utc_date=datetime(2091, 1, 1, 19))
