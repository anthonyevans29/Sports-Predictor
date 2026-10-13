"""ARCHITECT 2026-10-13 (addendum 63 item 3), verbatim: "Every results export (NFL, MLB, PL, and the INTL and NHL
grades) carries, in its record block, over the decided games that have a close: the games, the model's log-loss, the
close's, the paired difference close minus model, its bootstrap 95% interval on the paired per-game differences
(10,000 resamples, a fixed seed), and the count of games the model beat the close. The Cockpit shows that line beside
the win rate. A win rate is never printed without it."

Each family on its own throwaway SQLite file (SessionLocal rebound under tmp_path), hand-computed."""
import json
import math
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.schema import Sport
from src.walters import vs_close as vc

FAIR_H = round((1 / 1.8) / (1 / 1.8 + 1 / 2.1), 4)          # two books at 1.8 / 2.1, de-vigged per book
FAIR_A = round((1 / 2.1) / (1 / 1.8 + 1 / 2.1), 4)


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    from src.db import database
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{tmp_path / 'iso.db'}", future=True)
    Base.metadata.create_all(eng)
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True,
                                     expire_on_commit=False))
    monkeypatch.chdir(tmp_path)
    yield
    eng.dispose()


def _comp(s, sport, code):
    from src.db.schema import Competition
    c = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
    s.add(c)
    s.flush()
    return c


def _game(s, c, sport, key, ko, hs, aw, p, *, priced=True, week=6, stage=None, three=None, season="2026",
          outcome=True, result="auto"):
    """One finished game with a prediction (p = home win; three = (h, d, a)) and, when priced, two complete books
    at 1.8 / 2.1 (three-way: 2.0 / 3.4 / 3.8) one hour before the start."""
    from src.db.schema import Match, MatchStatus, Odds, Prediction, PredictionOutcome, Result, Team
    h, a = Team(sport=sport, name=f"VC {key} H"), Team(sport=sport, name=f"VC {key} A")
    s.add_all([h, a])
    s.flush()
    m = Match(sport=sport, competition_id=c.id, season=season, matchday=week, stage=stage, utc_date=ko,
              status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=hs, away_score=aw)
    s.add(m)
    s.flush()
    if priced:
        sels = (("HOME", 2.0), ("DRAW", 3.4), ("AWAY", 3.8)) if three else (("HOME", 1.8), ("AWAY", 2.1))
        for bk in ("bk1", "bk2"):
            for sel, px in sels:
                s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                           captured_at=ko - timedelta(hours=1)))
    ph, pd, pa = three if three else (p, None, 1 - p)
    pr = Prediction(match_id=m.id, model_version="vc-probe", home_win_prob=ph, draw_prob=pd, away_win_prob=pa)
    s.add(pr)
    s.flush()
    if outcome:
        res = {"H": Result.HOME, "D": Result.DRAW, "A": Result.AWAY}["H" if hs > aw else "A" if aw > hs else "D"]
        probs = {"H": ph, "D": pd or 0.0, "A": pa}
        top = max(probs, key=probs.get)
        s.add(PredictionOutcome(prediction_id=pr.id, actual_result=None if result is None else res,
                                actual_home_score=hs, actual_away_score=aw,
                                top_pick_hit=top == res.value, log_loss=-math.log(probs[res.value])))
    return m.id


# ---- NFL: the file, the grade and RESULTS.md state one record --------------------------------------------------

def _nfl_world(now):
    from src.db.database import session_scope
    from src.walters.nfl_predict import NFL_LIVE_SINCE
    with session_scope() as s:
        c = _comp(s, Sport.NFL, "NFL")
        d = now - timedelta(days=2)
        _game(s, c, Sport.NFL, "hw", d, 27, 10, 0.70, outcome=False)                  # model ahead of the close
        _game(s, c, Sport.NFL, "aw", d + timedelta(hours=1), 10, 27, 0.65, outcome=False)   # the close ahead
        _game(s, c, Sport.NFL, "tie", d + timedelta(hours=2), 20, 20, 0.40, outcome=False)  # a push: not fed
        _game(s, c, Sport.NFL, "bare", d + timedelta(hours=3), 24, 3, 0.60, priced=False, outcome=False)
        _game(s, c, Sport.NFL, "pre", NFL_LIVE_SINCE - timedelta(days=9), 24, 3, 0.60, week=1, outcome=False)


def test_nfl_file_grade_and_results_md_carry_one_line(iso_db, tmp_path):
    from src.timeutil import utc_now_naive
    from src.walters.export import results_tally
    from src.walters.nfl_predict import export_nfl_results, grade_nfl
    now = utc_now_naive()
    _nfl_world(now)
    doc = json.load(open(export_nfl_results(out_dir=str(tmp_path / "x"))))
    want = vc.block([(0.70, FAIR_H), (0.35, FAIR_A)])
    rec = doc["record"]
    assert rec["vs_close"] == want
    assert want["games"] == 2 and want["model_beat_close"] == 1
    assert want["model_log_loss"] == round((-math.log(0.70) - math.log(0.35)) / 2, 4)
    assert want["close_log_loss"] == round((-math.log(FAIR_H) - math.log(FAIR_A)) / 2, 4)
    assert rec["by_week"]["6"]["vs_close"] == want                   # the week's win rate carries its own line
    assert doc["pre_live"]["record"]["vs_close"] == vc.block([(0.60, FAIR_H)])
    lines = []
    r = grade_nfl(days_back=None, progress=lines.append)
    assert r["vs_close"] == rec["vs_close"]                              # ONE RECORD DEFINITION (2026-10-06)
    assert r["pre_live"]["vs_close"] == doc["pre_live"]["record"]["vs_close"]
    i = next(k for k, x in enumerate(lines) if "── sides" in x)
    assert lines[i + 1] == f"  ── {vc.line(want)}"                     # beside the win rate
    assert any(x.startswith("  ── pre-live vs close: 1 game · ") for x in lines)
    out = tmp_path / "RESULTS.md"
    results_tally(days=30, out_path=str(out))
    txt = out.read_text()
    assert f"pushes 1 (ties: outside the hit denominator)\n- {vc.line(want)}\n" in txt
    assert f"- Sides: 1/1 · pushes 0\n- {vc.line(vc.block([(0.60, FAIR_H)]))}\n" in txt


def test_nfl_cli_prints_the_line_under_the_record_each_week_and_pre_live(iso_db, tmp_path):
    from click.testing import CliRunner

    import cli
    from src.timeutil import utc_now_naive
    _nfl_world(utc_now_naive())
    res = CliRunner().invoke(cli.cli, ["export-nfl-results"])
    assert res.exit_code == 0, res.output
    out = res.output.splitlines()
    i = next(k for k, x in enumerate(out) if x.startswith("window: "))
    assert out[i + 1].startswith("  vs close: 2 games · model ")
    assert any(x.startswith("  W6 2/3 +1P · vs close: 2 games · ") for x in out)
    j = next(k for k, x in enumerate(out) if x.startswith("pre-live (never pooled)"))
    assert out[j + 1].startswith("  vs close: 1 game · ") and "no interval under two games" in out[j + 1]


# ---- MLB and PL: the results export gains its record block -------------------------------------------------------

def test_mlb_results_file_has_a_record_block_with_the_line(iso_db):
    from src.db.database import session_scope
    from src.timeutil import utc_now_naive
    from src.walters.export import export_results
    now = utc_now_naive()
    with session_scope() as s:
        c = _comp(s, Sport.MLB, "MLB")
        d = now - timedelta(days=1)
        _game(s, c, Sport.MLB, "m1", d, 5, 2, 0.62)
        _game(s, c, Sport.MLB, "m2", d + timedelta(hours=1), 1, 4, 0.55, result=None)  # null result: the scores
        _game(s, c, Sport.MLB, "m3", d + timedelta(hours=2), 3, 2, 0.58, priced=False)  # no close: not fed
    doc = json.loads(export_results(sport=Sport.MLB, start_date=now - timedelta(days=3), end_date=now,
                                    competition_code="MLB"))
    rec = doc["record"]
    assert rec["games"] == doc["count"] == 3 and rec["hits"] == 2
    want = vc.block([(0.62, FAIR_H), (0.45, FAIR_A)])
    assert {k: v for k, v in rec["vs_close"].items() if k != "kalshi_only_closes"} == want
    assert rec["vs_close"]["kalshi_only_closes"] == 0                     # these rows carry the close's reference


def test_a_kalshi_only_close_is_counted_and_named_in_the_line():
    rows = [{"predicted": {"home_win_prob": 0.6, "away_win_prob": 0.4}, "actual": {"result": "H"},
             "graded": {"close_fair": {"HOME": 0.55, "AWAY": 0.45}, "close_reference": ref}}
            for ref in ("books", "kalshi_only", "kalshi_only")]
    b = vc.block_from_rows(rows)
    assert b["games"] == 3 and b["kalshi_only_closes"] == 2
    assert vc.line(b).endswith(" · 2 of the closes the Kalshi-only mid")


def test_pl_results_file_reads_the_draw_leg(iso_db):
    from src.db.database import session_scope
    from src.timeutil import utc_now_naive
    from src.walters.export import export_results
    now = utc_now_naive()
    with session_scope() as s:
        c = _comp(s, Sport.SOCCER, "PL")
        _game(s, c, Sport.SOCCER, "d", now - timedelta(days=1), 1, 1, None, three=(0.45, 0.30, 0.25),
              season="2026/27")
    doc = json.loads(export_results(sport=Sport.SOCCER, start_date=now - timedelta(days=3), end_date=now,
                                    competition_code="PL"))
    imp = [1 / 2.0, 1 / 3.4, 1 / 3.8]
    fair_d = round(imp[1] / sum(imp), 4)
    rec = doc["record"]
    assert rec["games"] == 1 and rec["hits"] == 0
    assert {k: v for k, v in rec["vs_close"].items() if k != "kalshi_only_closes"} == vc.block([(0.30, fair_d)])


def test_results_md_mlb_and_soccer_sections_print_the_line_under_sides(iso_db, tmp_path):
    from src.db.database import session_scope
    from src.timeutil import utc_now_naive
    from src.walters.export import results_tally
    now = utc_now_naive()
    with session_scope() as s:
        c = _comp(s, Sport.MLB, "MLB")
        _game(s, c, Sport.MLB, "t1", now - timedelta(days=1), 5, 2, 0.62)
        _game(s, c, Sport.MLB, "t2", now - timedelta(days=1, hours=-1), 1, 4, 0.55)
    out = tmp_path / "RESULTS.md"
    results_tally(days=30, out_path=str(out))
    txt = out.read_text()
    b = vc.block_from_rows([
        {"predicted": {"home_win_prob": 0.62, "away_win_prob": 0.38}, "actual": {"result": "H"},
         "graded": {"close_fair": {"HOME": FAIR_H, "AWAY": FAIR_A}, "close_reference": "books"}},
        {"predicted": {"home_win_prob": 0.55, "away_win_prob": 0.45}, "actual": {"result": "A"},
         "graded": {"close_fair": {"HOME": FAIR_H, "AWAY": FAIR_A}, "close_reference": "books"}}])
    assert f"## MLB\n\n- Sides: **1/2** (50.0%)\n- {vc.line(b)}\n" in txt
    assert "## Soccer (PL)\n\nNo graded games in window." in txt


def test_the_mlb_cli_prints_the_line_under_the_top_pick_record(iso_db, tmp_path):
    from click.testing import CliRunner

    import cli
    from src.db.database import session_scope
    day = datetime(2026, 9, 20)
    with session_scope() as s:
        c = _comp(s, Sport.MLB, "MLB")
        _game(s, c, Sport.MLB, "c1", day.replace(hour=23), 5, 2, 0.62)
    res = CliRunner().invoke(cli.cli, ["export-results", "--sport", "mlb", "--competition", "MLB", "--date",
                                       "2026-09-20", "--out", str(tmp_path / "m.json")])
    assert res.exit_code == 0, res.output
    out = res.output.splitlines()
    i = next(k for k, x in enumerate(out) if "top-pick 1/1" in x)
    want = f"  {vc.line(json.load(open(tmp_path / 'm.json'))['record']['vs_close'])}"
    assert want in out[i:i + 4] and "vs close: 1 game · " in want       # under the record (rich may wrap it)


# ---- INTL: the production file and the shadow grade --------------------------------------------------------------

def test_intl_production_record_carries_the_line(iso_db):
    from src.db.database import append_prediction_history, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Odds, Team
    from src.walters import intl_production as ip
    ko = datetime(2098, 5, 1, 19)
    with session_scope() as s:
        c = Competition(sport=Sport.SOCCER, code="UNL", name="UNL", area="I", type="INTL")
        t = [Team(sport=Sport.SOCCER, name=f"VC Intl {i}") for i in range(4)]
        s.add_all([c, *t])
        s.flush()
        priced = Match(sport=Sport.SOCCER, competition_id=c.id, season="2097/98", utc_date=ko,
                       status=MatchStatus.FINISHED, status_raw="FT", home_team_id=t[0].id, away_team_id=t[1].id,
                       home_score_90=1, away_score_90=1, home_score=1, away_score=1)
        bare = Match(sport=Sport.SOCCER, competition_id=c.id, season="2097/98", utc_date=ko + timedelta(days=1),
                     status=MatchStatus.FINISHED, status_raw="FT", home_team_id=t[2].id, away_team_id=t[3].id,
                     home_score_90=2, away_score_90=0, home_score=2, away_score=0)
        s.add_all([priced, bare])
        s.flush()
        for sel, px in (("HOME", 2.0), ("DRAW", 3.4), ("AWAY", 3.8)):
            s.add(Odds(match_id=priced.id, bookmaker="bk", market="1X2", selection=sel, price_decimal=px,
                       captured_at=ko - timedelta(hours=1)))
        append_prediction_history(s.connection(), [
            {"match_id": m.id, "model_version": ip.MODEL_VERSION, "computed_at": m.utc_date - timedelta(hours=9),
             "home_win_prob": .5, "draw_prob": .3, "away_win_prob": .2} for m in (priced, bare)])
    path, doc = ip.export_results(now=datetime(2098, 6, 1))
    imp = [1 / 2.0, 1 / 3.4, 1 / 3.8]
    assert doc["record"]["games"] == 2
    assert doc["record"]["vs_close"] == vc.block([(0.3, round(imp[1] / sum(imp), 4))])
    assert json.load(open(path))["record"]["vs_close"] == doc["record"]["vs_close"]


# ---- the Cockpit reads the line as written and never prints the win rate without it -----------------------------

COCKPIT = Path(__file__).resolve().parents[1] / "tools" / "cockpit.html"


def _js_fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    depth, j = 0, src.index("{", i)
    for k in range(j, len(src)):
        depth += {"{": 1, "}": -1}.get(src[k], 0)
        if depth == 0:
            return src[i:k + 1]
    raise AssertionError(name)


def test_the_cockpit_shows_each_results_file_record_with_its_line():
    html = COCKPIT.read_text()
    assert 'id="modelRecord"' in html
    assert "recs=recs.concat(recordLines(doc,f.name))" in html
    assert '$("modelRecord").textContent=recs.join' in html
    body = _js_fn(html, "recordLines")
    assert "vsCloseLine(rec.vs_close)" in body and "vsCloseLine(pre.vs_close)" in body
    assert "Math.random" not in _js_fn(html, "vsCloseLine")             # read, never recomputed


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_cockpit_line_is_the_python_line_word_for_word(tmp_path):
    html = COCKPIT.read_text()
    blocks = [None, vc.block([]), vc.block([(0.6, 0.5)]), vc.block([(0.7, FAIR_H), (0.35, FAIR_A), (0.61, 0.6)]),
              {**vc.block([(0.6, 0.55), (0.4, 0.45)]), "kalshi_only_closes": 1},
              vc.block([(0.5, 0.50001), (0.5, 0.49999), (0.5, 0.5)]),                  # zeros, never "-0.0000"
              {"games": 46, "model_log_loss": 0.6104, "close_log_loss": 0.6419, "close_minus_model": 0.0315,
               "ci95": [-0.029, 0.091], "model_beat_close": 26, "resamples": 10_000, "seed": 20261013}]
    script = tmp_path / "t.js"
    script.write_text(_js_fn(html, "vsCloseLine") + "\n" + _js_fn(html, "recordLines") + "\n"
                      + f"const B={json.dumps(blocks)};\n"
                      + "console.log(JSON.stringify(B.map(vsCloseLine)));\n"
                      + "const doc={sport:'nfl',record:{games:3,decided:2,hits:1,pushes:1,vs_close:B[3]},"
                        "pre_live:{record:{games:1,decided:1,hits:1,pushes:0,vs_close:B[2]}}};\n"
                      + "console.log(JSON.stringify(recordLines(doc,'nfl_NFL_results_2026-10-13.json')));\n"
                      # a file exported before addendum 63 has a record and no line: its win rate is not shown
                      + "const old={sport:'nfl',record:{games:3,decided:2,hits:1,pushes:1},"
                        "pre_live:{record:{games:1,decided:1,hits:1,pushes:0}}};\n"
                      + "console.log(JSON.stringify(recordLines(old,'nfl_NFL_results_2026-10-12.json')));\n"
                      + "console.log(JSON.stringify(recordLines({sport:'mlb',competition_code:'MLB',"
                        "record:{games:1,hits:1,vs_close:B[2]}},'m.json').concat(recordLines({sport:'soccer',"
                        "competition_code:'PL',record:{games:1,hits:0,vs_close:B[2]}},'p.json'))));\n")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout.splitlines()
    got = json.loads(out[0])
    assert got[0] == "vs close: not in this file (exported before addendum 63)"
    assert got[1:] == [vc.line(b) for b in blocks[1:]]
    rec = json.loads(out[1])
    assert rec[0] == ("NFL model record · nfl_NFL_results_2026-10-13.json: top-pick hits 1/2 (50.0%) · pushes 1 · "
                      + vc.line(blocks[3]))
    assert rec[1] == "NFL pre-live (never pooled): hits 1/1 (100.0%) · " + vc.line(blocks[2])
    assert all(re.search(r"hits \d+/\d+", x) and " · vs close: " in x for x in rec)
    old = json.loads(out[2])
    assert old == ["NFL · nfl_NFL_results_2026-10-12.json: exported before addendum 63, no record against the close, "
                   "so no win rate is shown; re-export"]
    assert not any(re.search(r"hits \d", x) for x in old)                  # never a win rate without its line
    fams = json.loads(out[3])
    assert fams[0].startswith("MLB model record · m.json: top-pick hits 1/1 (100.0%) · vs close: 1 game")
    assert fams[1].startswith("SOCCER PL model record · p.json: top-pick hits 0/1 (0.0%) · vs close: 1 game")
