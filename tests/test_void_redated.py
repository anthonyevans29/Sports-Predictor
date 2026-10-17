"""VOID: RE-DATED (ARCHITECT 2026-10-17 09:25 ET, addendum 106 item 4; addendum 107 item A2, #574), verbatim: "Grading,
the results exports and the replay inventory label a closing row whose recorded start differs from the match's current
utc_date by more than DESK_CLOCK_DRIFT as "void: re-dated <old start> → <new start>" and exclude it from every tally;
the fresh closing on the new date is the graded row. Test with 50548 verbatim (10-17 00:00Z → 10-18 21:00Z)."

The 50548 closing row is tests/test_desk_kickoff_clock.py's (Cleveland Guardians vs Tampa Bay Rays at
"2026-10-17T00:00:00"), written through closing.closing_doc / closing_name as a closing run writes it; the match now
stands at 2026-10-18 21:00 UTC (Sunday 5:00pm ET). The results exports each run on a throwaway SQLite file
(tests/test_record_vs_close.py's iso_db); the Cockpit's grading is checked by scripts/cockpit_redated_verify.py
(Playwright)."""
import copy
import importlib.util
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session

from src.db.schema import Sport
from src.walters import desk_policy as dp
from src.walters import redated as rd
from src.walters.vs_close import block_from_rows
from tests.test_desk_kickoff_clock import mil_lad, tb_cle_tonight
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

ROOT = Path(__file__).resolve().parents[1]
LABEL = "void: re-dated 2026-10-17 00:00Z → 2026-10-18 21:00Z"
OLD_START, NEW_START = datetime(2026, 10, 17, 0, 0), datetime(2026, 10, 18, 21, 0)
MIL_LAD_START = datetime(2026, 10, 16, 0, 0)                  # 50547: never moved


def _closing():
    spec = importlib.util.spec_from_file_location("closing", ROOT / "deploy" / "hosting" / "closing.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_closing(ex: Path, start: datetime, rows: list[dict], fam: str = "MLB") -> Path:
    """One closing file as a closing run writes it (addendum 40 item 2): the rows unchanged, the closing block."""
    cl = _closing()
    ex.mkdir(parents=True, exist_ok=True)
    doc = cl.closing_doc({"sport": fam.lower(), "predictions": rows}, fam, start, f"run-{start:%m%d%H%M}",
                         [r["match_id"] for r in rows], [])
    p = ex / cl.closing_name(fam, start)
    p.write_text(json.dumps(doc))
    return p


def fresh_50548() -> dict:
    return {**tb_cle_tonight(), "utc_date": "2026-10-18T21:00:00"}


# ---- the rule ---------------------------------------------------------------------------------------------------

def test_50548_verbatim_is_void_with_the_rulings_label():
    row = tb_cle_tonight()
    assert (row["match_id"], row["utc_date"], row["home_team"], row["away_team"]) == \
        (50548, "2026-10-17T00:00:00", "Cleveland Guardians", "Tampa Bay Rays")
    assert rd.redated_label(row["utc_date"], NEW_START) == LABEL
    assert rd.redated_label(row["utc_date"], "2026-10-18 21:00:00.000000") == LABEL     # the DB's stored text
    assert rd.redated_label("2026-10-17T00:00:00Z", "2026-10-18T17:00:00-04:00") == LABEL   # zones converted
    assert rd.redated_label(row["utc_date"], "2026-10-17T00:00:00") is None             # 50547's shape: no move


def test_more_than_the_hour_voids_and_exactly_the_hour_does_not():
    assert dp.DESK_CLOCK_DRIFT == timedelta(hours=1)
    assert rd.redated_label("2026-10-17T23:00:00", "2026-10-18T00:00:00") is None       # exactly 1h: not void
    assert rd.redated_label("2026-10-18T00:00:00", "2026-10-17T23:00:00") is None
    assert rd.redated_label("2026-10-17T23:00:00", "2026-10-18T00:01:00") == \
        "void: re-dated 2026-10-17 23:00Z → 2026-10-18 00:01Z"                          # 61 minutes: void
    assert rd.redated_label("2026-10-17T23:00:00", "2026-10-17T21:59:00") == \
        "void: re-dated 2026-10-17 23:00Z → 2026-10-17 21:59Z"                          # either way round
    assert rd.redated_label("2026-10-17T23:00:00", "2026-10-18T00:00:00.000001") is not None


def test_a_date_with_no_clock_or_nothing_is_not_compared():
    for a, b in (("2026-10-17", "2026-10-18T21:00:00"), ("2026-10-17T00:00:00", "2026-10-18"),
                 (None, NEW_START), ("2026-10-17T00:00:00", None), ("", NEW_START), ("not a date", NEW_START),
                 ("2026-10-17T25:00:00", NEW_START), (20261017, NEW_START)):
        assert rd.redated_label(a, b) is None, (a, b)


def test_the_rule_reads_the_desks_constant(monkeypatch):
    monkeypatch.setattr(dp, "DESK_CLOCK_DRIFT", timedelta(hours=2))
    assert rd.redated_label("2026-10-17T23:00:00", "2026-10-18T00:01:00") is None
    assert rd.redated_label(tb_cle_tonight()["utc_date"], NEW_START) == LABEL


# ---- the closing files --------------------------------------------------------------------------------------------

def test_the_fresh_closing_on_the_new_date_is_the_graded_row(tmp_path):
    ex = tmp_path / "exports"
    write_closing(ex, OLD_START, [tb_cle_tonight()])
    write_closing(ex, MIL_LAD_START, [mil_lad()])
    cs = rd.closing_starts(ex)
    assert cs["files"] == 2 and cs["unreadable"] == []
    assert cs["rows"][50548] == [(OLD_START, "2026-10-17T00:00:00")]          # the closing block's start
    assert rd.void_label(cs["rows"][50548], NEW_START) == LABEL
    assert rd.void_label(cs["rows"][50547], MIL_LAD_START) is None            # 50547 (no move): graded
    assert rd.void_label(cs["rows"].get(4242), NEW_START) is None             # no closing file names it
    write_closing(ex, NEW_START, [fresh_50548()])
    cs = rd.closing_starts(ex)
    assert [st for _, st in cs["rows"][50548]] == ["2026-10-17T00:00:00", "2026-10-18T21:00:00"]
    assert rd.void_label(cs["rows"][50548], NEW_START) is None                # the fresh closing is graded


def test_the_latest_closing_decides_and_a_start_not_compared_never_voids():
    old = [(datetime(2026, 10, 16), "2026-10-16T00:00:00"), (OLD_START, "2026-10-17T00:00:00")]
    assert rd.void_label(old, NEW_START) == LABEL                             # the latest of two re-dated rows
    assert rd.void_label(old + [(NEW_START, None)], NEW_START) is None        # the latest has no start: not compared
    assert rd.void_label(old, "2026-10-18") is None                           # the match's date has no clock
    assert rd.void_label([], NEW_START) is None


def test_unreadable_files_are_counted_and_the_hosts_copies_are_never_read(tmp_path):
    ex = tmp_path / "exports"
    write_closing(ex / "host", OLD_START, [tb_cle_tonight()])               # the host's match ids are its own
    (ex / "closing_MLB_bad.json").write_text("{not json")
    (ex / "closing_NFL_list.json").write_text("[1, 2]")
    cs = rd.closing_starts(ex)
    assert cs == {"rows": {}, "files": 0, "unreadable": ["closing_MLB_bad.json", "closing_NFL_list.json"]}
    assert rd.closing_starts(tmp_path / "none") == {"rows": {}, "files": 0, "unreadable": []}


def test_a_file_without_a_closing_block_start_sorts_by_its_name_stamp(tmp_path):
    ex = tmp_path / "exports"
    ex.mkdir()
    (ex / "closing_MLB_2026-10-18T2100Z.json").write_text(json.dumps({"predictions": [fresh_50548()]}))
    (ex / "closing_MLB_2026-10-17T0000Z.json").write_text(json.dumps({"predictions": [tb_cle_tonight()]}))
    assert [r for r, _ in rd.closing_starts(ex)["rows"][50548]] == [OLD_START, NEW_START]


# ---- the MLB results export, its console and RESULTS.md --------------------------------------------------------

def _game(s, c, sport, mid, home, away, ko, hs, aw, p, *, outcome=True, week=None, season="2026"):
    """One finished game with id `mid`, two complete books one hour before the start and a prediction (p = home)."""
    from src.db.schema import Match, MatchStatus, Odds, Prediction, PredictionOutcome, Result, Team
    h, a = Team(sport=sport, name=home), Team(sport=sport, name=away)
    s.add_all([h, a])
    s.flush()
    s.add(Match(id=mid, sport=sport, competition_id=c.id, season=season, matchday=week, utc_date=ko,
                status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=hs, away_score=aw))
    s.flush()
    for bk in ("bk1", "bk2"):
        for sel, px in (("HOME", 1.8), ("AWAY", 2.1)):
            s.add(Odds(match_id=mid, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                       captured_at=ko - timedelta(hours=1)))
    pr = Prediction(match_id=mid, model_version="vr-probe", home_win_prob=p, away_win_prob=1 - p,
                    expected_home_score=4.0, expected_away_score=3.0)
    s.add(pr)
    s.flush()
    if outcome:
        s.add(PredictionOutcome(prediction_id=pr.id, actual_result=Result.HOME if hs > aw else Result.AWAY,
                                actual_home_score=hs, actual_away_score=aw, top_pick_hit=(p >= 0.5) == (hs > aw),
                                log_loss=-math.log(p if hs > aw else 1 - p)))


def _comp(s, sport, code):
    from src.db.schema import Competition
    c = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
    s.add(c)
    s.flush()
    return c


def _mlb_world():
    from src.db.database import session_scope
    with session_scope() as s:
        c = _comp(s, Sport.MLB, "MLB")
        _game(s, c, Sport.MLB, 50548, "Cleveland Guardians", "Tampa Bay Rays", NEW_START, 5, 2, 0.61)
        _game(s, c, Sport.MLB, 50547, "Los Angeles Dodgers", "Milwaukee Brewers", MIL_LAD_START, 1, 4, 0.40)


def _mlb_export(ex=None):
    from src.walters.export import export_results
    kw = {} if ex is None else {"exports_dir": str(ex)}
    return json.loads(export_results(sport=Sport.MLB, start_date=datetime(2026, 10, 15),
                                     end_date=datetime(2026, 10, 19), competition_code="MLB", **kw))


def test_the_mlb_results_export_labels_the_row_keeps_it_and_tallies_only_the_rest(iso_db, tmp_path):
    _mlb_world()
    write_closing(tmp_path / "exports", OLD_START, [tb_cle_tonight()])       # the default exports dir (cwd)
    write_closing(tmp_path / "exports", MIL_LAD_START, [mil_lad()])
    doc = _mlb_export()
    rows = {r["match_id"]: r for r in doc["results"]}
    r = rows[50548]
    assert r["redated"] == LABEL and "redated" not in rows[50547]
    # the row keeps its result (the Cockpit grades the fresh call from it), never a key its intake reads as void
    assert r["date"] == "2026-10-18T21:00:00" and r["actual"]["result"] == "H" and r["graded"]["top_pick_hit"] is True
    assert not {"status", "void"} & set(r)
    rec = doc["record"]
    assert doc["count"] == 2 and rec["games"] == 1 and rec["hits"] == 1 and rec["redated"] == 1
    assert rec["vs_close"] == block_from_rows([rows[50547]]) and rec["vs_close"]["games"] == 1
    assert doc["totals_pulse"]["games"] == 1
    write_closing(tmp_path / "exports", NEW_START, [fresh_50548()])           # the fresh closing on the new date
    doc = _mlb_export()
    assert all("redated" not in x for x in doc["results"])
    assert (doc["record"]["games"], doc["record"]["hits"], doc["record"]["redated"]) == (2, 2, 0)


def test_unmoved_games_read_exactly_as_before(iso_db, tmp_path):
    _mlb_world()
    strip = lambda d: {k: v for k, v in d.items() if k not in ("exported_at", "git_sha")}      # noqa: E731
    before = _mlb_export(tmp_path / "none")
    write_closing(tmp_path / "ex", NEW_START, [fresh_50548()])
    write_closing(tmp_path / "ex", MIL_LAD_START, [mil_lad()])
    after = _mlb_export(tmp_path / "ex")
    assert strip(before) == strip(after) and before["record"]["redated"] == 0
    assert (before["record"]["games"], before["count"]) == (2, 2)


def test_export_results_prints_the_count_and_names_the_row(iso_db, tmp_path):
    from click.testing import CliRunner

    import cli
    _mlb_world()
    write_closing(tmp_path / "exports", OLD_START, [tb_cle_tonight()])
    res = CliRunner().invoke(cli.cli, ["export-results", "--sport", "mlb", "--competition", "MLB", "--date",
                                       "2026-10-18", "--out", str(tmp_path / "m.json")])
    assert res.exit_code == 0, res.output
    out = res.output.splitlines()
    assert any("top-pick 0/0" in x for x in out)                              # out of the record
    i = out.index("  void: re-dated 1 (kept in the file, out of every tally above)")
    assert out[i + 1] == f"    match 50548 Tampa Bay Rays @ Cleveland Guardians: {LABEL}"
    assert json.load(open(tmp_path / "m.json"))["results"][0]["redated"] == LABEL


def test_results_md_mlb_section_leaves_the_game_out_and_names_it(iso_db, tmp_path):
    from src.walters.export import results_tally
    _mlb_world()
    write_closing(tmp_path / "ex", OLD_START, [tb_cle_tonight()])
    out = tmp_path / "RESULTS.md"
    results_tally(days=36500, out_path=str(out), exports_dir=str(tmp_path / "ex"))
    txt = out.read_text()
    assert "## MLB\n\n- Sides: **1/1** (100.0%)\n- vs close: 1 game · " in txt
    assert (f"- Void: re-dated 1 (out of every line above): match 50548 Tampa Bay Rays @ Cleveland Guardians: "
            f"{LABEL}\n") in txt
    results_tally(days=36500, out_path=str(out), exports_dir=str(tmp_path / "none"))
    txt = out.read_text()
    assert "## MLB\n\n- Sides: **2/2** (100.0%)\n" in txt and "Void: re-dated" not in txt


# ---- NFL: the results file, nfl-grade and RESULTS.md state one record --------------------------------------------

FLEX = "void: re-dated 2026-10-18 17:00Z → 2026-10-18 20:25Z"


def _nfl_world(tmp_path):
    from src.db.database import session_scope
    with session_scope() as s:
        c = _comp(s, Sport.NFL, "NFL")
        _game(s, c, Sport.NFL, 70001, "Kansas City Chiefs", "Buffalo Bills", datetime(2026, 10, 18, 20, 25), 27, 10,
              0.70, outcome=False, week=7)                                   # flexed from 17:00Z
        _game(s, c, Sport.NFL, 70002, "Detroit Lions", "Minnesota Vikings", datetime(2026, 10, 18, 17, 0), 10, 27,
              0.65, outcome=False, week=7)                                   # no move: a miss
    row = lambda mid, h, a, utc: {"match_id": mid, "home_team": h, "away_team": a, "utc_date": utc}  # noqa: E731
    write_closing(tmp_path / "ex", datetime(2026, 10, 18, 17, 0),
                  [row(70001, "Kansas City Chiefs", "Buffalo Bills", "2026-10-18T17:00:00"),
                   row(70002, "Detroit Lions", "Minnesota Vikings", "2026-10-18T17:00:00")], fam="NFL")


def test_nfl_file_grade_and_results_md_leave_the_redated_game_out(iso_db, tmp_path):
    from src.walters.export import results_tally
    from src.walters.nfl_predict import export_nfl_results, grade_nfl
    _nfl_world(tmp_path)
    ex = str(tmp_path / "ex")
    doc = json.load(open(export_nfl_results(out_dir=ex)))
    rows = {r["match_id"]: r for r in doc["results"]}
    assert rows[70001]["redated"] == FLEX and "redated" not in rows[70002]
    assert rows[70001]["actual"]["result"] == "H" and not {"status", "void"} & set(rows[70001])
    rec = doc["record"]
    assert doc["count"] == 2 and (rec["games"], rec["decided"], rec["hits"], rec["redated"]) == (1, 1, 0, 1)
    assert rec["by_week"]["7"]["games"] == 1 and rec["vs_close"] == block_from_rows([rows[70002]])
    assert doc["pre_live"]["record"]["redated"] == 0
    lines = []
    g = grade_nfl(days_back=None, progress=lines.append, exports_dir=ex)
    assert (g["games"], g["decided"], g["hits"], g["redated"]) == (1, 1, 0, 1)   # ONE RECORD DEFINITION (2026-10-06)
    assert g["vs_close"] == rec["vs_close"]
    i = lines.index("  ── void: re-dated 1 (out of every line here)")
    assert lines[i + 1] == f"     match 70001 Buffalo Bills @ Kansas City Chiefs: {FLEX}"
    out = tmp_path / "RESULTS.md"
    results_tally(days=36500, out_path=str(out), exports_dir=ex)
    txt = out.read_text()
    assert "## NFL (live since Week 3, 2026-09-22)\n\n- Sides: **0/1** (0.0%) · pushes 0" in txt
    assert f"- Void: re-dated 1 (out of every line above): match 70001 Buffalo Bills @ Kansas City Chiefs: {FLEX}\n" in txt


def test_export_nfl_results_prints_the_count(iso_db, tmp_path):
    from click.testing import CliRunner

    import cli
    _nfl_world(tmp_path)
    (tmp_path / "ex").rename(tmp_path / "exports")                            # the command's own exports dir
    res = CliRunner().invoke(cli.cli, ["export-nfl-results"])
    assert res.exit_code == 0, res.output
    out = res.output.splitlines()
    i = out.index("  void: re-dated 1 (kept in the file, out of every tally above)")
    assert out[i + 1] == f"    match 70001 Buffalo Bills @ Kansas City Chiefs: {FLEX}"
    assert any(x.startswith("window: season_to_date season 2026") and "games 1 · top-pick hits 0/1" in x for x in out)


# ---- INTL ----------------------------------------------------------------------------------------------------------

def test_intl_results_leave_the_redated_game_out(iso_db, tmp_path):
    from src.db.database import append_prediction_history, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Team
    from src.walters import intl_production as ip
    ko = datetime(2098, 5, 1, 19)
    with session_scope() as s:
        c = Competition(sport=Sport.SOCCER, code="UNL", name="UNL", area="I", type="INTL")
        t = [Team(sport=Sport.SOCCER, name=f"VR Intl {i}") for i in range(4)]
        s.add_all([c, *t])
        s.flush()
        ms = [Match(id=81000 + i, sport=Sport.SOCCER, competition_id=c.id, season="2097/98",
                    utc_date=ko + timedelta(days=i), status=MatchStatus.FINISHED, status_raw="FT",
                    home_team_id=t[2 * i].id, away_team_id=t[2 * i + 1].id, home_score_90=1, away_score_90=0,
                    home_score=1, away_score=0) for i in range(2)]
        s.add_all(ms)
        s.flush()
        append_prediction_history(s.connection(), [
            {"match_id": m.id, "model_version": ip.MODEL_VERSION, "computed_at": m.utc_date - timedelta(hours=9),
             "home_win_prob": .5, "draw_prob": .3, "away_win_prob": .2} for m in ms])
    write_closing(tmp_path / "ex", ko - timedelta(days=1),
                  [{"match_id": 81000, "home_team": "VR Intl 0", "away_team": "VR Intl 1",
                    "utc_date": "2098-04-30T19:00:00"}], fam="INTL")
    path, doc = ip.export_results(now=datetime(2098, 6, 1), out_dir=str(tmp_path / "ex"))
    rows = {r["match_id"]: r for r in doc["results"]}
    assert rows[81000]["redated"] == "void: re-dated 2098-04-30 19:00Z → 2098-05-01 19:00Z"
    assert "redated" not in rows[81001] and doc["count"] == 2
    assert (doc["record"]["games"], doc["record"]["decided"], doc["record"]["hits"], doc["record"]["redated"]) == \
        (1, 1, 1, 1)
    assert json.load(open(path))["record"] == doc["record"]


# ---- the Python ports of the Cockpit's ledger ---------------------------------------------------------------------

def test_executed_positions_never_read_a_redated_call():
    from src.walters import ledger_fills as P
    from tests.test_k_track_receipt import _ledger
    L = _ledger()
    assert len(P.executed_positions(L)["pos"]) == 1
    L["calls"][0]["void_redated"] = LABEL
    assert P.executed_positions(L)["pos"] == []


def test_the_k_receipt_leaves_a_redated_call_out_and_counts_it():
    from src.walters import k_receipt as K
    from tests.test_k_track_receipt import HI, LO, _ledger
    L = _ledger()
    base = "\n".join(K.format_fills(L, LO, HI))
    assert "  void: re-dated 0 (out of the reconciliation and the CLV)" in base
    L["calls"].append({**L["calls"][1], "id": "c6", "game": "Bills @ Jets", "home": "New York Jets",
                       "away": "Buffalo Bills", "status": "void", "void_redated": FLEX})
    rec = K.reconcile(L, LO, HI)
    assert "c6" not in {r["call_id"] for r in rec["rows"]} and rec["funnel"]["eligible"] == 3
    txt = K.format_fills(L, LO, HI)
    i = txt.index("  void: re-dated 1 (out of the reconciliation and the CLV)")
    assert txt[i + 1] == f"- VOID NFL Bills @ Jets · straight HOME · {FLEX}"
    L["calls"][0]["void_redated"] = LABEL                   # the matched call itself: its fill is neither in nor out
    txt = "\n".join(K.format_fills(L, LO, HI))
    assert "system_matched in window: 0 (outside window 0; on a call void: re-dated 1) · qty 0" in txt
    assert "no executed positions" in txt


def test_the_value_shadow_receipt_leaves_a_redated_shadow_out_and_counts_it():
    import scripts.value_shadow_receipt as vsr
    from tests.test_value_shadow_receipt import call, kept, run
    out0, _ = run(kept())
    assert "void: re-dated 0 (out of every total and the n/30; the fresh call on the new date is the graded row)" in out0
    L = kept()
    c = call(L, "Green Bay Packers")                        # the kept ledger's open shadow
    c.update(status="void", void_redated=LABEL)
    out, res = run(L)
    assert ("  all value shadows: n 4 · graded 4 · record won 2 · lost 1 · push 1 · void 0 · ungraded 0 · units net "
            "+0.8801u over 4 settled (notional 1u)") in out
    i = out.index("void: re-dated 1 (out of every total and the n/30; the fresh call on the new date is the graded row)")
    assert out[i + 1].endswith(f" · NFL · Minnesota Vikings @ Green Bay Packers · HOME (Green Bay Packers) · edge "
                               f"+7.0pp (claim) · no close · {LABEL} · 0.25u")
    js = json.loads(out[-1].removeprefix("VALUE-SHADOW-RECEIPT "))
    assert js["void_redated"] == 1 and js["n_of_30"] == "4 of 30" and js["all"]["n"] == 4
    assert vsr.read(copy.deepcopy(L))["void_redated"][0]["outcome"] == LABEL


# ---- the replay inventory -------------------------------------------------------------------------------------------

def _replay_db(path: Path):
    from src.db.schema import (Base, Competition, Match, MatchStatus, OddsSnapshot, Prediction, Team)
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        c = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="X", type="LEAGUE")
        s.add(c)
        s.flush()
        for mid, home, away, ko in ((50548, "Cleveland Guardians", "Tampa Bay Rays", NEW_START),
                                    (50547, "Los Angeles Dodgers", "Milwaukee Brewers", MIL_LAD_START)):
            h, a = Team(sport=Sport.MLB, name=home), Team(sport=Sport.MLB, name=away)
            s.add_all([h, a])
            s.flush()
            s.add(Match(id=mid, sport=Sport.MLB, competition_id=c.id, season="2026", utc_date=ko,
                        status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=3, away_score=1))
            s.flush()
            s.execute(insert(Prediction.__table__).values(match_id=mid, model_version="v", home_win_prob=0.6,
                                                          away_win_prob=0.4, computed_at=ko - timedelta(hours=2)))
            for src, market in (("api_baseball", "1X2"), ("kalshi", "ML")):
                for sel in ("HOME", "AWAY"):
                    s.add(OddsSnapshot(match_id=mid, market=market, selection=sel, devig_prob=0.5, line=None,
                                       n_books=2, captured_at=ko - timedelta(hours=1), source=src))
        s.commit()
    eng.dispose()


def test_the_replay_inventory_counts_a_closing_only_at_the_games_own_start(tmp_path, capsys):
    import scripts.replay_inventory_probe as rip
    db, ex = tmp_path / "throwaway.db", tmp_path / "exports"
    _replay_db(db)
    write_closing(ex, OLD_START, [tb_cle_tonight()])
    write_closing(ex, MIL_LAD_START, [mil_lad()])

    def run():
        assert rip.main(["--db", str(db), "--exports", str(ex), "--since", "2026-10-10", "--until", "2026-10-20"]) == 0
        return capsys.readouterr().out.splitlines()
    out = run()
    i = out.index("MLB: graded 2")
    assert out[i + 6].endswith("/, by match id): 1 games")
    assert out[i + 7] == "  all four (a stored prediction + book history + kalshi history + a closing file): 1"
    assert out[i + 8] == "  closing void: re-dated (left out of closing and all four): 1 games"
    assert out[i + 9] == f"    match 50548: {LABEL}"
    js = json.loads(out[-1].removeprefix("REPLAY-INVENTORY "))
    assert js["closing_redated"] == 1
    assert (js["groups"]["MLB"]["closing"], js["groups"]["MLB"]["all_four"],
            js["groups"]["MLB"]["closing_redated"]) == (1, 1, 1)
    assert "redated" not in js["groups"]["MLB"]
    write_closing(ex, NEW_START, [fresh_50548()])                             # the fresh closing on the new date
    out = run()
    i = out.index("MLB: graded 2")
    assert out[i + 6].endswith("/, by match id): 2 games") and out[i + 7].endswith(": 2")
    assert out[i + 8] == "  closing void: re-dated (left out of closing and all four): 0 games"
    assert json.loads(out[-1].removeprefix("REPLAY-INVENTORY "))["closing_redated"] == 0


def test_the_rule_reads_the_files_a_closing_run_writes():
    from fnmatch import fnmatch
    cl = _closing()
    assert cl.CLOSING_FILE_DIR == "exports" and cl.closing_name("MLB", OLD_START) == "closing_MLB_2026-10-17T0000Z.json"
    assert fnmatch(cl.closing_name("SOCCER", NEW_START), rd.CLOSING_GLOB)
