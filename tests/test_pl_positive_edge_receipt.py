"""THE PL POSITIVE-EDGE RECEIPT (ARCHITECT addendum 162 item 2(a); #92): scripts/pl_positive_edge_receipt.py, files only.

The results files carry export_results' keys (src/walters/export.py: match_id, date, teams, predicted, actual, graded with
the grading close block of src/walters/close.py graded_block, "redated"); the closing files are written as a closing
run writes them (tests/test_void_redated.py write_closing, through closing.closing_doc / closing_name, family SOCCER),
each row a predictions-export row whose desk block is the real desk_policy.annotate's."""
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import scripts.pl_positive_edge_receipt as pe
from src.walters import desk_policy as dp
from tests.test_void_redated import write_closing

ROOT = Path(__file__).resolve().parents[1]
KO = "2026-10-24T14:00:00"
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
SOURCE = "close_1x2: last pre-kickoff capture session, complete books de-vigged then averaged (#167/#207)"


def result_row(mid, p=(0.45, 0.30, 0.25), fair=(0.40, 0.30, 0.30), hit=True, score=(2, 1), date=KO, **extra):
    """One results row as export_results writes it (home pick by default)."""
    ph, pd, pa = p
    top = max({"home_win": ph, "draw": pd, "away_win": pa}.items(), key=lambda kv: kv[1])[0]
    close = ({"close_fair": None, "close_at": None, "close_minutes_before_start": None, "close_books": 0,
              "close_source": SOURCE, "close_reference": None, "close_book_stamp_age_h": None} if fair is None else
             {"close_fair": {"HOME": fair[0], "DRAW": fair[1], "AWAY": fair[2]}, "close_at": "2026-10-24T13:40:00",
              "close_minutes_before_start": 20, "close_books": 9, "close_source": SOURCE, "close_reference": "books",
              "close_book_stamp_age_h": 0.4})
    r = {"match_id": mid, "date": date, "away_team": f"Away {mid}", "home_team": f"Home {mid}",
         "predicted": {"top_pick": top, "top_pick_prob": round(max(p), 4), "home_win_prob": ph, "draw_prob": pd,
                       "away_win_prob": pa, "projected_total": 2.6, "over_under_line": None, "over_prob": None},
         "actual": {"home_score": score[0], "away_score": score[1], "total_runs": sum(score),
                    "result": "H" if score[0] > score[1] else "A" if score[0] < score[1] else "D"},
         "graded": {"top_pick_hit": hit, "total_correct": None, "total_error": None, "log_loss": 0.8,
                    "brier_score": 0.5, "model_close_divergence": None, "clv": None, "closing_price": None, **close}}
    r.update(extra)
    return r


def write_results(ex: Path, day: str, rows, exported_at="2026-10-25T08:30:00Z") -> Path:
    ex.mkdir(parents=True, exist_ok=True)
    p = ex / f"soccer_PL_results_{day}.json"
    p.write_text(json.dumps({"exported_at": exported_at, "git_sha": "abc1234", "sport": "soccer",
                             "start_date": f"{day}T08:00:00", "end_date": f"{day}T08:00:00", "competition_code": "PL",
                             "count": len(rows), "record": {}, "totals_pulse": None, "results": rows}))
    return p


def pred_row(mid, p=(0.45, 0.30, 0.25), mkt=(0.40, 0.30, 0.30), inj=(1, 1), utc=KO, computed="2026-10-24T07:10:00"):
    """A soccer predictions-export row (src/walters/export.py _build_row's keys), with the real Desk's block."""
    r = {"match_id": mid, "utc_date": utc, "status": "scheduled", "competition": "PL", "season": "2026/27",
         "home_team": f"Home {mid}", "away_team": f"Away {mid}",
         "prediction": {"model_version": "soccer_elo_poisson_v22", "computed_at": computed,
                        "probabilities": {"home_win": p[0], "draw": p[1], "away_win": p[2]}, "top_pick": "home_win",
                        "top_pick_prob": p[0], "tier": "lean"},
         "market": {"bookmaker_count": 9, "selections": {k: {"fair_prob": v} for k, v in zip(("HOME", "DRAW", "AWAY"),
                                                                                            mkt)}},
         "injuries": {"home_count": inj[0], "away_count": inj[1], "home_names": [], "away_names": []},
         "input_quality": {"injuries": {"home": {"count": inj[0], "synced_at": "2026-10-23T22:00:00"},
                                        "away": {"count": inj[1], "synced_at": "2026-10-23T22:00:00"}}}}
    doc = dp.annotate({"sport": "soccer", "predictions": [r]}, now=NOW)
    return doc["predictions"][0]


def run(ex, **kw):
    """The results-files path (--source exports); the database path is tested below on a throwaway DB."""
    out = []
    res = pe.report(ex, echo=out.append, **{"source": "exports", **kw})
    return "\n".join(out), res


def member(res, mid):
    return next(m for m in res["members"] if m["match_id"] == mid)


def test_exactly_five_points_is_in_and_just_below_is_out(tmp_path):
    write_results(tmp_path, "2026-10-24", [result_row(1, p=(0.45, 0.30, 0.25), fair=(0.40, 0.30, 0.30)),
                                           result_row(2, p=(0.4499, 0.30, 0.2501), fair=(0.40, 0.30, 0.30))])
    text, res = run(tmp_path)
    assert (0.45 - 0.40) * 100 < 5                                   # the float trap the rounding guards against
    assert [m["match_id"] for m in res["members"]] == [1] and member(res, 1)["gap_pp"] == 5.0
    assert [x["match_id"] for x in res["below"]] == [2] and res["graded"] == 2
    assert "gap +5.00pp" in text and ">= +5pp (--min-gap-pp; the ruled line, not a knob)" in text


def test_an_unpriced_close_is_counted_and_named_never_in_the_cohort(tmp_path):
    write_results(tmp_path, "2026-10-24", [result_row(3, p=(0.70, 0.20, 0.10), fair=None)])
    text, res = run(tmp_path)
    assert not res["members"] and [x["match_id"] for x in res["no_close"]] == [3]
    assert "no close 1" in text and "no close: match 3 2026-10-24 14:00 Away 3 @ Home 3: close_fair null" in text


def test_a_kalshi_close_is_not_the_book_close(tmp_path):
    r = result_row(4, p=(0.70, 0.20, 0.10), fair=(0.50, 0.25, 0.25))
    r["graded"]["close_reference"] = "kalshi_only"
    write_results(tmp_path, "2026-10-24", [r])
    text, res = run(tmp_path)
    assert not res["members"] and "close not the book close: match 4" in text


def test_a_stale_stamp_is_counted_and_printed(tmp_path):
    r = result_row(5, p=(0.60, 0.20, 0.20), fair=(0.50, 0.25, 0.25))
    r["graded"].update(close_book_stamp_age_h=30.5,
                       close_stale_unswitched="three-way board: the rule names a two-sided Kalshi mid; none is derived")
    write_results(tmp_path, "2026-10-24", [r])
    text, res = run(tmp_path)
    assert [m["match_id"] for m in res["members"]] == [5]
    assert "book stamp 30.5h before the start (stale: over 24h)" in text and "unswitched: three-way board" in text
    assert "captured 20 min before the start" in text and "close stamp 2026-10-24T13:40:00" in text


def test_a_redated_row_is_left_out_and_counted(tmp_path):
    lab = "void: re-dated 2026-10-24 14:00Z → 2026-10-26 20:00Z"
    write_results(tmp_path, "2026-10-26", [result_row(6, p=(0.70, 0.2, 0.1), fair=(0.5, 0.25, 0.25),
                                                      date="2026-10-26T20:00:00", redated=lab),
                                           result_row(7, p=(0.70, 0.2, 0.1), fair=(0.5, 0.25, 0.25),
                                                      date="2026-10-26T20:00:00")])
    write_closing(tmp_path, datetime(2026, 10, 24, 13, 15), [pred_row(7, utc=KO)], fam="SOCCER")
    text, res = run(tmp_path)
    assert not res["members"] and {x["match_id"] for x in res["void"]} == {6, 7}
    assert f"void: match 6 2026-10-26 20:00 Away 6 @ Home 6: {lab} (by the results export)" in text
    assert "void: match 7 2026-10-26 20:00 Away 7 @ Home 7: void: re-dated 2026-10-24 14:00Z → 2026-10-26 20:00Z " \
           "(by the closing files on disk)" in text
    assert "void 2 (re-dated 2 · placeholder kickoff 0)" in text


def test_a_match_in_two_results_files_is_deduped_newest_wins(tmp_path):
    write_results(tmp_path, "2026-10-24", [result_row(8, p=(0.60, 0.2, 0.2), fair=(0.5, 0.25, 0.25), hit=False,
                                                      score=(0, 1))], exported_at="2026-10-25T08:30:00Z")
    write_results(tmp_path, "2026-10-24b", [result_row(8, p=(0.60, 0.2, 0.2), fair=(0.5, 0.25, 0.25), hit=True,
                                                       score=(2, 0))], exported_at="2026-10-26T08:30:00Z")
    text, res = run(tmp_path)
    assert res["results"]["rows_read"] == 2 and len(res["results"]["rows"]) == 1
    assert res["results"]["dupes"] == [(8, "soccer_PL_results_2026-10-24b.json", "soccer_PL_results_2026-10-24.json")]
    m = member(res, 8)
    assert m["hit"] is True and m["score"] == (2, 0) and m["file"] == "soccer_PL_results_2026-10-24b.json"
    assert "duplicate copies dropped 1" in text and "match 8: kept soccer_PL_results_2026-10-24b.json, dropped " \
                                                   "soccer_PL_results_2026-10-24.json" in text


def test_the_desks_final_call_is_the_newest_closing_runs_and_the_guard_is_printed(tmp_path):
    write_results(tmp_path, "2026-10-24", [result_row(9, p=(0.55, 0.25, 0.20), fair=(0.48, 0.27, 0.25))])
    old = pred_row(9, p=(0.55, 0.25, 0.20), mkt=(0.50, 0.27, 0.23), inj=(3, 2), computed="2026-10-24T05:00:00")
    new = pred_row(9, p=(0.55, 0.25, 0.20), mkt=(0.50, 0.27, 0.23), inj=(3, 0), computed="2026-10-24T07:10:00")
    assert (old["desk"]["call"], new["desk"]["call"], new["desk"]["pass_kind"]) == ("PLAY", "PASS", "injuries_one_sided")
    write_closing(tmp_path, datetime(2026, 10, 24, 12, 0), [old], fam="SOCCER")
    write_closing(tmp_path, datetime(2026, 10, 24, 13, 15), [new], fam="SOCCER")
    text, res = run(tmp_path)
    m = member(res, 9)
    assert m["call"] == "PASS" and m["run"] == datetime(2026, 10, 24, 13, 15)
    assert m["computed_at"] == "2026-10-24T07:10:00" and (m["inj"]["home"], m["inj"]["away"]) == (3, 0)
    assert "the Desk's final call: PASS (injuries_one_sided) · closing run 2026-10-24 13:15Z" in text
    assert ("injuries home 3 / away 0 (input_quality.injuries) · one-sided guard: fires (Away 9 lists no name, Home 9 "
            "lists 3) (rule on in code; the Desk at the run: PASS injuries_one_sided)") in text
    assert "prediction stamp 2026-10-24T07:10:00 (model soccer_elo_poisson_v22)" in text
    assert res["by_call"] == {"PASS": {"n": 1, "hits": 1}}
    assert "PLAY 0 (hits 0) · LADDER 0 (hits 0) · PASS 1 (hits 1)" in text


def test_a_guard_that_does_not_fire_reads_so(tmp_path):
    write_results(tmp_path, "2026-10-24", [result_row(10, p=(0.55, 0.25, 0.20), fair=(0.48, 0.27, 0.25))])
    write_closing(tmp_path, datetime(2026, 10, 24, 13, 15),
                  [pred_row(10, p=(0.55, 0.25, 0.20), mkt=(0.50, 0.27, 0.23), inj=(3, 2))], fam="SOCCER")
    text, res = run(tmp_path)
    assert member(res, 10)["call"] == "PLAY"
    assert "one-sided guard: does not fire (rule on in code; the Desk at the run: not a one-sided PASS)" in text


def test_no_closing_row_is_named(tmp_path):
    write_results(tmp_path, "2026-10-24", [result_row(11, p=(0.60, 0.2, 0.2), fair=(0.5, 0.25, 0.25), hit=False,
                                                      score=(1, 1))])
    other = pred_row(11)
    other["home_team"] = "Someone Else"                   # the id is machine-local: another game's row is not this one
    write_closing(tmp_path, datetime(2026, 10, 24, 13, 15), [other], fam="SOCCER")
    write_results(tmp_path, "2026-10-23", [result_row(12, p=(0.60, 0.2, 0.2), fair=(0.5, 0.25, 0.25),
                                                      date="2026-10-23T14:00:00")], exported_at="2026-10-24T08:30:00Z")
    text, res = run(tmp_path)
    assert member(res, 11)["call"] == "no closing row (teams differ)" and member(res, 12)["call"] == "no closing row"
    assert "prediction stamp not in the closing files" in text and "injuries: not in the closing files" in text
    assert "result miss · score 1-1 (result D)" in text
    assert "no closing row 1 (hits 1)" in text and "no closing row (teams differ) 1 (hits 0)" in text


def test_the_script_writes_nothing_and_never_opens_the_db(tmp_path):
    write_results(tmp_path, "2026-10-24", [result_row(13, p=(0.60, 0.2, 0.2), fair=(0.5, 0.25, 0.25))])
    write_closing(tmp_path, datetime(2026, 10, 24, 13, 15), [pred_row(13)], fam="SOCCER")
    work = tmp_path / "cwd"
    work.mkdir()
    snap = lambda: {q: q.read_bytes() if q.is_file() else None for q in tmp_path.rglob("*")}   # noqa: E731
    before = snap()
    code = ("import runpy, sys; sys.argv = ['x', '--exports', sys.argv[1], '--source', 'exports']\n"
            "try:\n    runpy.run_path(%r, run_name='__main__')\n"
            "except SystemExit as e:\n    assert not e.code, e.code\n"
            "assert 'src.db.database' not in sys.modules, 'the DB module was imported'\n"
            % str(ROOT / "scripts" / "pl_positive_edge_receipt.py"))
    p = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=work, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "COHORT (1 rows, by date)" in p.stdout and "PL-POSITIVE-EDGE-RECEIPT " in p.stdout
    assert snap() == before                                # nothing written, nothing changed, the cwd empty


def test_a_file_that_is_not_pl_soccer_is_named_and_not_read(tmp_path):
    p = write_results(tmp_path, "2026-10-24", [result_row(14, p=(0.60, 0.2, 0.2), fair=(0.5, 0.25, 0.25))])
    doc = json.loads(p.read_text())
    doc["competition_code"] = "ELC"
    p.write_text(json.dumps(doc))
    (tmp_path / "soccer_PL_results_2026-10-25.json").write_text("{not json")
    text, res = run(tmp_path)
    assert not res["results"]["rows"] and res["results"]["not_pl"] == [p.name]
    assert "not PL soccer 1: soccer_PL_results_2026-10-24.json" in text
    assert "unreadable 1: soccer_PL_results_2026-10-25.json" in text


# ---- addendum 163 item 1: the table, the cells, the injury split, the n=60 line -----------------------------------

def table_world(tmp_path):
    """Four members, hand-computable: (pick, model p, close fair, hit, injuries on the closing row)
    1 home 0.60 / 0.50 hit  (+10pp; 3 and 2: both list, the guard quiet)        return +1
    2 home 0.52 / 0.40 miss (+12pp exactly: in the cell; 3 and 0: the guard fires) return -1
    3 home 0.5199 / 0.40 miss (+11.99pp: out of the cell; 0 and 0: neither)     return -1
    4 draw 0.40 / 0.25 hit  (+15pp; no closing row)                              return +3
    and the mirror: 5 at exactly -5pp (in, a hit), 6 at -4.99pp (out)."""
    write_results(tmp_path, "2026-10-24", [
        result_row(1, p=(0.60, 0.20, 0.20), fair=(0.50, 0.25, 0.25), hit=True),
        result_row(2, p=(0.52, 0.24, 0.24), fair=(0.40, 0.30, 0.30), hit=False, score=(0, 1)),
        result_row(3, p=(0.5199, 0.24, 0.2401), fair=(0.40, 0.30, 0.30), hit=False, score=(0, 2)),
        result_row(4, p=(0.30, 0.40, 0.30), fair=(0.40, 0.25, 0.35), hit=True, score=(1, 1)),
        result_row(5, p=(0.40, 0.30, 0.30), fair=(0.45, 0.30, 0.25), hit=True),
        result_row(6, p=(0.4001, 0.30, 0.2999), fair=(0.45, 0.30, 0.25), hit=False, score=(0, 0))])
    write_closing(tmp_path, datetime(2026, 10, 24, 13, 15),
                  [pred_row(1, inj=(3, 2)), pred_row(2, inj=(3, 0)), pred_row(3, inj=(0, 0))], fam="SOCCER")
    return run(tmp_path)


def test_the_close_implied_rate_its_half_width_and_the_model_mean(tmp_path):
    text, res = table_world(tmp_path)
    t = res["table"]
    assert (t["n"], t["hits"], t["rate"]) == (4, 2, 0.5)
    assert abs(t["implied"] - (0.50 + 0.40 + 0.40 + 0.25) / 4) < 1e-12                       # 0.3875
    hw = 1.96 * math.sqrt(0.5 * 0.5 + 0.4 * 0.6 + 0.4 * 0.6 + 0.25 * 0.75) / 4 * 100           # 46.94pp
    assert abs(t["implied_hw_pp"] - hw) < 1e-9 and round(hw, 1) == 46.9
    assert abs(t["model"] - (0.60 + 0.52 + 0.5199 + 0.40) / 4) < 1e-12                        # 0.509975
    assert ("n 4 · hits 2 (50.0%) · close-implied 38.8% (±46.9pp at 95%: ±1.96 x sqrt(sum p(1-p)) / n, p = each "
            "row's close fair for the pick) · the model's own mean probability 51.0%") in text


def test_the_per_unit_return_at_the_close_fair_price(tmp_path):
    text, res = table_world(tmp_path)
    t = res["table"]
    assert t["ret"] == 0.5 and t["priced"] == 4 and t["unpriced"] == 0              # (+1 - 1 - 1 + 3) / 4
    assert abs(t["ret_hw"] - 1.96 * math.sqrt(11 / 3) / 2) < 1e-12                  # sample sd sqrt(11/3)
    assert ("hypothetical return at the close's fair price +50.0% per unit, interval ±187.7 points (approximate, "
            "95%: a hit 1/p_close - 1, a miss -1; ±1.96 x sd / sqrt(n) of the per-unit returns, sample sd) over 4 "
            "rows, before spread and fee") in text


def test_a_two_member_return_by_hand():
    two = pe.stats([{"p": 0.6, "q": 0.5, "hit": True}, {"p": 0.4, "q": 0.25, "hit": False}])
    assert two["ret"] == 0.0                                                       # (+1 - 1) / 2
    assert abs(two["ret_hw"] - 1.96) < 1e-12                                       # 1.96 x sqrt(2) / sqrt(2)
    one = pe.stats([{"p": 0.6, "q": 0.25, "hit": True}])
    assert one["ret"] == 3.0 and one["ret_hw"] is None                             # no sd under 2 rows
    assert pe.stats([])["implied"] is None


def test_the_mirror_set_at_exactly_minus_five(tmp_path):
    text, res = table_world(tmp_path)
    assert [x["match_id"] for x in res["mirror"]] == [5] and 6 in {x["match_id"] for x in res["below"]}
    m = res["mirror_table"]
    assert (m["n"], m["hits"], m["implied"], m["model"]) == (1, 1, 0.45, 0.40)
    assert "the mirror set (gap <= -5pp: the pick at least 5pp BELOW the close): n 1 · hits 1 (100.0%)" in text


def test_the_cells_the_twelve_point_boundary_and_the_draw(tmp_path):
    text, res = table_world(tmp_path)
    assert pe.CELL_GAP_PP == 12.0 and pe.CELL_PICK == "draw" and pe.MIN_GAP_PP == 5.0
    assert res["cells"] == {"gap": {"n": 2, "hits": 1}, "draw": {"n": 1, "hits": 1}}       # 2 and 4; 4
    assert ("cells (the architect's cells from the 10-24 read, not knobs): gap >= +12pp (CELL_GAP_PP) n 2 (hits 1) · "
            "draw picks (CELL_PICK) n 1 (hits 1)") in text


def test_the_injury_split(tmp_path):
    text, res = table_world(tmp_path)
    sp = res["split"]
    assert sp["guard"] == {"fires": {"n": 1, "hits": 0}, "does not fire": {"n": 2, "hits": 1},
                           "no injury data / no closing row": {"n": 1, "hits": 1}}
    assert sp["presence"] == {"both sides list someone": {"n": 1, "hits": 1}, "one side lists none": {"n": 1, "hits": 0},
                              "neither lists anyone": {"n": 1, "hits": 0}, "unknown": {"n": 1, "hits": 1}}
    assert ("injury split, by the one-sided guard's state: fires 1 (hits 0) · does not fire 2 (hits 1) · no injury "
            "data / no closing row 1 (hits 1)") in text
    assert ("injury split, by injury presence: both sides list someone 1 (hits 1) · one side lists none 1 (hits 0) · "
            "neither lists anyone 1 (hits 0) · unknown 1 (hits 1)") in text


def test_the_n60_line_and_no_verdict(tmp_path):
    text, _ = table_world(tmp_path)
    assert ("- next read pre-registered at n=60 (ARCHITECT 2026-10-24, addendum 163 item 1): same definition, read "
            "once · the cohort now: n 4 of 60") in text
    assert pe.READ_AT_N == 60 and "VERDICT" not in text.upper().replace("NO VERDICT", "")


# ---- #706 (ARCHITECT 2026-10-27 08:20 ET): the database read-only as the primary source, the exports secondary -------

def db_world(tmp_path, monkeypatch):
    """A throwaway SQLite file the receipt opens mode=ro: PL 21 (an earlier and a later graded prediction; the later,
    away 0.55 at a 0.40 close, is the row), PL 22 (its one prediction marked dedupe_569: never a row), PL 23 (graded,
    home 0.62 at a 0.50 close: a hit), ELC 24 (not PL), PL 25 (before --since)."""
    import config
    import types
    from datetime import timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from src.db.schema import (Base, Competition, Match, MatchStatus, Odds, Prediction, PredictionOutcome, Result,
                               Sport, Team)
    db = tmp_path / "ro.db"
    eng = create_engine(f"sqlite:///{db}", future=True)
    Base.metadata.create_all(eng)
    ko = datetime(2026, 10, 24, 14, 0)
    with Session(eng) as s:
        pl = Competition(sport=Sport.SOCCER, code="PL", name="PL", area="ENG", type="LEAGUE")
        elc = Competition(sport=Sport.SOCCER, code="ELC", name="ELC", area="ENG", type="LEAGUE")
        s.add_all([pl, elc])
        s.flush()

        def game(mid, comp, at, hs, aw, fair, preds):
            h, a = Team(sport=Sport.SOCCER, name=f"Home {mid}"), Team(sport=Sport.SOCCER, name=f"Away {mid}")
            s.add_all([h, a])
            s.flush()
            s.add(Match(id=mid, sport=Sport.SOCCER, competition_id=comp.id, season="2026/27", utc_date=at,
                        status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=hs,
                        away_score=aw))
            s.flush()
            for bk in ("bk1", "bk2"):
                for sel, f in zip(("HOME", "DRAW", "AWAY"), fair):
                    s.add(Odds(match_id=mid, bookmaker=bk, market="1X2", selection=sel, price_decimal=round(1 / f, 4),
                               captured_at=at - timedelta(minutes=20)))
            res = Result.HOME if hs > aw else Result.AWAY if hs < aw else Result.DRAW
            for computed, (ph, pd, pa), fb in preds:
                pr = Prediction(match_id=mid, model_version="soccer_elo_poisson_v22", computed_at=computed,
                                home_win_prob=ph, draw_prob=pd, away_win_prob=pa, expected_home_score=1.4,
                                expected_away_score=1.1, factor_breakdown=fb)
                s.add(pr)
                s.flush()
                top = max((("H", ph), ("D", pd), ("A", pa)), key=lambda kv: kv[1])[0]
                s.add(PredictionOutcome(prediction_id=pr.id, actual_result=res, actual_home_score=hs,
                                        actual_away_score=aw, top_pick_hit=top == res.value, log_loss=0.9))
        early = ko - timedelta(days=1)
        game(21, pl, ko, 0, 1, (0.35, 0.25, 0.40), [(early, (0.50, 0.25, 0.25), None),
                                                    (ko - timedelta(hours=6), (0.25, 0.20, 0.55), None)])
        game(22, pl, ko, 1, 0, (0.40, 0.30, 0.30), [(early, (0.60, 0.20, 0.20), {"dedupe_569": {"twin": 9}})])
        game(23, pl, ko, 2, 0, (0.50, 0.25, 0.25), [(early, (0.62, 0.20, 0.18), None)])
        game(24, elc, ko, 2, 0, (0.40, 0.30, 0.30), [(early, (0.70, 0.15, 0.15), None)])
        game(25, pl, datetime(2026, 7, 20, 14, 0), 2, 0, (0.40, 0.30, 0.30), [(early, (0.70, 0.15, 0.15), None)])
        s.commit()
    eng.dispose()
    monkeypatch.setattr(config, "settings", types.SimpleNamespace(database_url=f"sqlite:///{db}"))
    # the exports, secondary: 21 with the EARLIER pick (home: they differ), 23 as the database has it, 26 files-only
    write_results(tmp_path, "2026-10-24", [result_row(21, p=(0.50, 0.25, 0.25), fair=(0.35, 0.25, 0.40), hit=False,
                                                      score=(0, 1)),
                                           result_row(23, p=(0.62, 0.20, 0.18), fair=(0.50, 0.25, 0.25)),
                                           result_row(26, p=(0.62, 0.20, 0.18), fair=(0.50, 0.25, 0.25))])
    return db


def test_the_database_is_the_primary_source_one_row_per_match_its_latest_prediction(tmp_path, monkeypatch):
    db = db_world(tmp_path, monkeypatch)
    before = db.read_bytes()
    out = []
    res = pe.report(tmp_path, echo=out.append, since="2026-08-01")
    text = "\n".join(out)
    r = res["results"]
    assert r["source"] == "db" and sorted(r["rows"]) == [21, 23]          # 22 marked, 24 ELC, 25 before --since
    assert r["rows_read"] == 3 and len(r["dupes"]) == 1                    # 21's earlier prediction not taken
    assert r["rows"][21][1]["predicted"]["top_pick"] == "away_win"
    assert r["check"] == {"both": 2, "db_only": 0, "exports_only": [26], "differ": [21]}
    assert "SOURCE: the database, read-only (mode=ro): prediction_outcomes of PL matches from 2026-08-01" in text
    assert "matches in both 2 · in the database only 0 · in the files only 1 (26) · top pick or hit differ 1 (21)" \
        in text
    assert {m["match_id"] for m in res["members"]} == {21, 23}            # +15pp and +12pp over the book close
    assert '"source": "db"' in text
    assert db.read_bytes() == before                                       # read-only: the file unchanged


def test_the_exports_source_reads_the_files_alone(tmp_path, monkeypatch):
    db_world(tmp_path, monkeypatch)
    text, res = run(tmp_path)
    assert res["results"]["source"] == "exports" and sorted(res["results"]["rows"]) == [21, 23, 26]
    assert "SOURCE: results files" in text and "the database not read" in text


def test_a_missing_db_file_is_refused_exit_2_never_created(tmp_path, monkeypatch, capsys):
    import config
    import types
    missing = tmp_path / "none.db"
    monkeypatch.setattr(config, "settings", types.SimpleNamespace(database_url=f"sqlite:///{missing}"))
    assert pe.main(["--exports", str(tmp_path)]) == 2
    assert "REFUSED: no DB file" in capsys.readouterr().out and not missing.exists()
