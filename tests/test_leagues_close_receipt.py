"""Addendum 155 item 4(a) and addendum 156 item 1: the leagues' close receipt (paper.leagues_season and
scripts/leagues_close_receipt.py) on a throwaway SQLite file (tests/test_record_vs_close.py iso_db)."""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from src.db.schema import MatchStatus, Sport
from src.walters import paper
from tests.test_close_record_paper import _kal
from tests.test_close_record_three_way import A, KIND3
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

pytestmark = pytest.mark.usefixtures("iso_db")

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("leagues_close_receipt", ROOT / "scripts" / "leagues_close_receipt.py")
lr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lr)

SEASON = "2026/27"
DECLARED = date(2026, 11, 6)
NOW = datetime(2026, 10, 23, 12, 0)
KO = datetime(2026, 10, 18, 14, 0)


def _comps():
    from src.db.database import session_scope
    from src.db.schema import Competition
    with session_scope() as s:
        for code in paper.LEAGUES:
            s.add(Competition(sport=Sport.SOCCER, code=code, name=code, area="X", type="LEAGUE"))


def _game(mid, code, ko, status=MatchStatus.SCHEDULED, hs90=None, aw90=None, season=SEASON):
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Team
    with session_scope() as s:
        c = s.query(Competition).filter_by(code=code).one()
        h, a = Team(sport=c.sport, name=f"H{mid}"), Team(sport=c.sport, name=f"A{mid}")
        s.add_all([h, a])
        s.flush()
        fin = status == MatchStatus.FINISHED
        s.add(Match(id=mid, sport=c.sport, competition_id=c.id, season=season, utc_date=ko, status=status,
                    home_team_id=h.id, away_team_id=a.id, home_score=hs90 if fin else None,
                    away_score=aw90 if fin else None, home_score_90=hs90, away_score_90=aw90,
                    status_raw="FT" if fin else None))


def _legs(mid, quotes, at):
    for sel, (bid, ask) in quotes.items():
        _kal(mid, sel, bid, ask, at, market="1X2")


def test_finished_games_are_scored_as_the_close_record_scores_a_three_way_competition():
    """SA 801: 2-1 after 90, close A (HOME .4527 the favourite, a hit): log-loss -ln(.4527) = 0.7925. 802: finished,
    no capture (unpriced: no capture). The line is close_record_line's own, the unpriced line by cause."""
    _comps()
    _game(801, "SA", KO, MatchStatus.FINISHED, 2, 1)
    _legs(801, A, KO - timedelta(minutes=30))
    _game(802, "SA", KO + timedelta(hours=3), MatchStatus.FINISHED, 0, 0)
    r = paper.leagues_season(("SA",), SEASON, DECLARED, now=NOW)["SA"]
    assert r["record"]["n"] == 1 and r["record"]["finished"] == 2 and r["record"]["unpriced_none"] == 1
    line = paper.close_record_line("SA", r["record"])
    assert line.startswith(f"- SA · {KIND3} · close log-loss 0.7925 · favourite 1/1 (100.0%) · draw favourite 0 · n=1")


def test_games_to_come_are_read_for_the_capture_they_hold_and_not_games_are_left_out():
    _comps()
    soon = NOW + timedelta(days=2)
    _game(811, "BL1", soon)
    _legs(811, A, NOW - timedelta(hours=1))                                  # a full capture: forms a close now
    _game(812, "BL1", soon)
    _legs(812, {"HOME": (0.45, 0.46), "AWAY": (0.27, 0.28)}, NOW - timedelta(hours=1))   # a leg missing
    _game(813, "BL1", soon)                                                  # no capture
    _game(814, "BL1", soon, MatchStatus.POSTPONED)                           # not a game: left out
    c = paper.leagues_season(("BL1",), SEASON, DECLARED, now=NOW)["BL1"]["to_come"]
    assert c == {"n": 3, "close": 1, "unpriced_incomplete": 1, "unpriced_cap": 0, "unpriced_none": 1,
                 "unpriced_other": 0}
    assert lr.come_line("BL1", c) == ("  - BL1 · to come 3 · a capture forming a close now 1 · no close: last capture "
                                      "incomplete 1 · no capture 1")


def test_the_60th_fixture_on_or_after_the_declaration_dates_step_c_and_fewer_than_60_dates_nothing():
    """156 item 1: the kickoff date of the 60th fixture scheduled on or after 2026-11-06, every game assumed to get a
    close; a postponed row and a game before the declaration are not counted. FL1 stores 60, one each 12 hours from 2026-11-06 20:00Z (the 60th at
    2026-12-06 08:00Z),
    ELC 61 from 2026-11-07 20:00Z (its 60th on 2026-12-07): the step's date is FL1's, ELC named; SA stores 59: no date."""
    _comps()
    start = datetime(2026, 11, 6, 20, 0)
    _game(900, "FL1", start - timedelta(days=1))                           # before the declaration: not counted
    _game(901, "FL1", start, MatchStatus.POSTPONED)                         # not a game: not counted
    for i in range(60):
        _game(1000 + i, "FL1", start + timedelta(days=0.5 * i))
        _game(2000 + i, "ELC", start + timedelta(days=1 + 0.5 * i))
    _game(2060, "ELC", start + timedelta(days=40))
    for i in range(59):
        _game(3000 + i, "SA", start + timedelta(days=i))
    res = paper.leagues_season(paper.LEAGUES, SEASON, DECLARED, now=NOW)
    assert res["FL1"]["projected"] == {"date": date(2026, 12, 6), "match_id": 1059} and res["FL1"]["from_declared"] == 60
    assert res["ELC"]["projected"]["date"] == date(2026, 12, 7) and res["SA"]["projected"] is None
    out = lr.lines(res, SEASON, DECLARED)
    assert out[-1] == ("STEP (c) (156 item 1): due 2026-12-06 (FL1, the earliest); the others: ELC 2026-12-07; "
                       "no date for SA, BL1 (fewer than 60 stored)")
    assert "  - SA · the 60th fixture on or after 2026-11-06: not stored (only 59 on or after it); no date" in out
    assert "- BL1 · no stored game of 2026/27; seasons stored: none" in out


def test_a_league_stored_under_another_season_string_names_the_seasons_it_holds():
    _comps()
    _game(950, "ELC", KO, season="2026-27")
    res = paper.leagues_season(("ELC",), SEASON, DECLARED, now=NOW)
    assert lr.lines(res, SEASON, DECLARED)[1] == "- ELC · no stored game of 2026/27; seasons stored: 2026-27"


def test_the_script_refuses_a_missing_database_and_never_creates_one(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'absent.db'}")
    with pytest.raises(SystemExit, match="never creates one"):
        lr.main([])
    assert not (tmp_path / "absent.db").exists()


def test_capture_quality_by_weekday_with_a_superseded_complete_capture():
    """158 item 2(b). SA 821 (Sat): one full capture at T-30, a qualifying close. 822 (Sat): a full capture at T-3h,
    then an incomplete one at T-30 (two legs): no close, SUPERSEDED (never substituted). 823 (Wed): no capture."""
    _comps()
    sat = datetime(2026, 10, 17, 14, 0)
    _game(821, "SA", sat, MatchStatus.FINISHED, 1, 0)
    _legs(821, A, sat - timedelta(minutes=30))
    _game(822, "SA", sat + timedelta(hours=2), MatchStatus.FINISHED, 0, 1)
    _legs(822, A, sat + timedelta(hours=2) - timedelta(hours=3))
    _legs(822, {"HOME": (0.45, 0.46), "AWAY": (0.27, 0.28)}, sat + timedelta(hours=2) - timedelta(minutes=30))
    _game(823, "SA", datetime(2026, 10, 21, 18, 45), MatchStatus.FINISHED, 2, 2)
    r = paper.leagues_season(("SA",), SEASON, DECLARED, now=NOW)["SA"]
    q = r["quality"]
    assert q["by_weekday"]["Sat"]["finished"] == 2 and q["by_weekday"]["Sat"]["n"] == 1
    assert q["by_weekday"]["Sat"]["unpriced_incomplete"] == 1 and q["by_weekday"]["Wed"]["unpriced_none"] == 1
    assert [(c["match_id"], c["why"]) for c in q["superseded"]] == [(822, "unpriced_incomplete")]
    lines = paper.quality_lines("SA", q)
    assert any(ln.startswith("    Sat: finished 2 · qualifying close 1 (50%) · missing 0 · incomplete 1") for ln in lines)
    assert any("controlling capture age median 0.5 h" in ln for ln in lines)
    assert "    superseded (a later capture forms no close where an older one would; never substituted): 1" in lines
    assert any(ln.startswith("      match 822 · kickoff Sat 2026-10-17 16:00Z") and "(incomplete)" in ln for ln in lines)


def _league_season(code, n_rounds=20):
    """A small league: 6 teams, a regular-season round every 3-4 days (three games at one kickoff per round, F5),
    plus two games of a non-regular stage the walk never reads (F3)."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Team
    with session_scope() as s:
        c = s.query(Competition).filter_by(code=code).one()
        teams = [Team(sport=c.sport, name=f"{code}{i}") for i in range(6)]
        s.add_all(teams)
        s.flush()
        ids = [t.id for t in teams]
        mid = 5000
        start = datetime(2026, 8, 15, 14, 0)
        for r in range(n_rounds):
            ko = start + timedelta(days=3 * r + (r % 2))
            rot = ids[r % 6:] + ids[:r % 6]
            for k in range(3):
                h, a = (rot[2 * k], rot[2 * k + 1]) if r % 2 == 0 else (rot[2 * k + 1], rot[2 * k])
                hs, as_ = (r + k) % 3, (r * 2 + k) % 4 // 2
                s.add(Match(id=mid, sport=c.sport, competition_id=c.id, season=SEASON, utc_date=ko,
                            status=MatchStatus.FINISHED, home_team_id=h, away_team_id=a, home_score=hs,
                            away_score=as_, stage=f"Regular Season - {r + 1}"))
                mid += 1
        for j in range(2):
            s.add(Match(id=mid + j, sport=c.sport, competition_id=c.id, season=SEASON,
                        utc_date=start + timedelta(days=20, hours=j), status=MatchStatus.FINISHED,
                        home_team_id=ids[j], away_team_id=ids[j + 2], home_score=3, away_score=0,
                        stage="Relegation Round"))


def test_the_prospective_path_equals_the_gate_walk_row_for_row_and_the_legacy_shadow_does_not():
    """158 item 2(a): the shadow's probabilities for this season's finished games equal the gate path's, row for row;
    the current shadow export's arithmetic (every stage, no batching) is reported apart, and here it differs."""
    from src.models.poisson import PoissonConfig
    from src.walters import leagues_candidate as lc
    _comps()
    _league_season("SA")
    cfg = PoissonConfig()
    p = lc.parity("SA", cfg.dixon_coles_rho, cfg.elo_goal_coeff, now=NOW)
    assert p["gate_scored"] > 0 and len(p["rows"]) == p["gate_scored"]
    assert p["unequal"] == 0 and p["max_diff"] <= lc.PARITY_TOL and not p["shadow_only"] and not p["gate_only"]
    assert p["legacy_unequal"] > 0                                   # the current shadow is not the walk
    assert p["finished_regular"] == 60 and p["not_regular"] == 2
    r0 = p["rows"][0]
    assert r0["candidate"] == lc.CANDIDATE and r0["prediction_stamp"] == NOW and r0["input_cutoff"] is not None
    lines = lc.parity_lines(p, rows=False)
    assert lines[0].startswith(f"SA {SEASON} · PARITY (158 item 2(a)) · finished regular-round 60 (other stages 2")
    assert "unequal 0" in lines[0] and "a finding: it is not the gate's walk" in lines[1]
