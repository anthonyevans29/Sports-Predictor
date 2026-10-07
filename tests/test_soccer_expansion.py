"""soccer-expansion-v1 (ARCHITECT 2026-10-07, GATE-CLASS; declared, NOT run). Pins: the registry declaration and its
executable confirmation plan; the one-run command refuses unless declared and unrun, while the spec's findings are
open, and on a missing 2023/24 naive or test season (before any league is scored); the dropped-league rule and the
named surviving set; the market side-report is reported, never gated; soccer-backtest refuses these leagues while the
experiment is unrun; shadow rows are engine model_shadow, carry no desk call and write no prediction. The real
ledger is never touched (the registry is monkeypatched)."""
import json
import random
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import func, select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Prediction, Sport, Team
from src.walters import desk_policy as dp
from src.walters import registry as reg
from src.walters import soccer_expansion as sx

DECLARED = {"id": sx.EID, "status": "declared", "run": None, "test_set": "x"}


def results(n, good: bool, seed=1, start=0):
    """n synthetic scored matches; good=True: confident and right; False: confident and wrong."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        y = rng.choice("HDA")
        # good: the 0.70 side wins 70% of the time (calibrated); bad: it never wins
        right = good and (i % 10) < 7
        hit = y if right else {"H": "A", "D": "H", "A": "H"}[y]
        p = {k: 0.15 for k in "HDA"}
        p[hit] = 0.70
        out.append({"match_id": start + i, "p_home": p["H"], "p_draw": p["D"], "p_away": p["A"], "actual": y})
    return out


NAIVE = {"H": 0.45, "D": 0.27, "A": 0.28, "n": 380}


def test_registry_declares_it_with_an_executable_plan():
    e = reg.get(sx.EID)
    assert e and e["status"] == "declared" and e["run"] is None
    assert e["declaration"] == "docs/specs/soccer-expansion-v1.md"
    assert reg.check_plan(e["confirmation_plan"]) == {"n_games": 60, "metric": "log_loss", "bar": 1.0986,
                                                     "must_beat_reference": True,
                                                     "reference": e["confirmation_plan"]["reference"]}
    assert "PD, SA, BL1, FL1, ELC seasons 2024/25 + 2025/26" in e["test_set"] and "PER LEAGUE" in e["gate"]


def test_gate_command_refuses_unless_declared_and_unrun(monkeypatch):
    import cli
    for entry in (None, {**DECLARED, "status": "run", "run": {"run_at": "x"}}):
        monkeypatch.setattr(reg, "get", lambda eid, path=None, _e=entry: _e)
        r = CliRunner().invoke(cli.cli, ["soccer-expansion-gate", "--preflight"])
        assert r.exit_code == 2 and "REFUSED" in r.output and "read once" in r.output


def test_run_refuses_while_findings_are_open_and_on_missing_data(monkeypatch):
    assert sx.OPEN_FINDINGS and {f[:2] for f in sx.OPEN_FINDINGS} == {"F1", "F2", "F3", "F4", "F5"}
    with pytest.raises(sx.ExpansionRefused, match="open findings"):
        sx.run(-0.1, 0.0008)
    monkeypatch.setattr(sx, "OPEN_FINDINGS", ())
    scored = []
    monkeypatch.setattr("src.walters.soccer_backtest.run_soccer_backtest",
                        lambda *a, **k: scored.append(a) or results(5, True))
    monkeypatch.setattr(sx, "naive_for", lambda s, c: None if c == "ELC" else NAIVE)
    monkeypatch.setattr(sx, "finished_count", lambda s, c, se: 100)
    monkeypatch.setattr(sx, "scoreable_count", lambda s, c, se: 60)
    with pytest.raises(sx.ExpansionRefused, match="no stored 2023/24 for ELC"):
        sx.run(-0.1, 0.0008)
    monkeypatch.setattr(sx, "naive_for", lambda s, c: NAIVE)
    monkeypatch.setattr(sx, "scoreable_count", lambda s, c, se: 0 if (c, se) == ("SA", "2025/26") else 60)
    with pytest.raises(sx.ExpansionRefused, match="SA 2025/26 .100 finished, 0 scoreable"):
        sx.run(-0.1, 0.0008)
    assert scored == []                                         # refused BEFORE any league was scored


def test_a_league_that_misses_its_own_gate_is_dropped_and_the_verdict_names_the_survivors(monkeypatch):
    init_db()
    monkeypatch.setattr(sx, "OPEN_FINDINGS", ())
    monkeypatch.setattr(sx, "naive_for", lambda s, c: NAIVE)
    monkeypatch.setattr(sx, "finished_count", lambda s, c, se: 100)
    monkeypatch.setattr(sx, "scoreable_count", lambda s, c, se: 60)
    good = {"PD", "BL1"}
    monkeypatch.setattr("src.walters.soccer_backtest.run_soccer_backtest",
                        lambda code, season, *a, **k: results(60, code in good, seed=hash((code, season)) % 97,
                                                              start=1000 * sx.LEAGUES.index(code)
                                                              + (500 if season == "2025/26" else 0)))
    r = sx.run(-0.1, 0.0008)
    assert r["surviving"] == ["PD", "BL1"] and r["dropped"] == ["SA", "FL1", "ELC"]
    assert r["verdict"] == "PASS — surviving set PD, BL1"
    assert r["per_league"]["SA"]["verdict"].startswith("DROPPED") and len(r["scored_ids"]) == 5 * 120
    assert sx.overall({c: {"survives": False} for c in sx.LEAGUES})["verdict"] == "FAIL — no league survives"


def test_calibration_band_miss_drops_a_league_even_with_the_log_loss_margin():
    # 100 matches stated 0.70 on H that hit 80%: log-loss beats naive, the 70-80% band misses by 10pp
    res = [{"match_id": i, "p_home": 0.70, "p_draw": 0.15, "p_away": 0.15, "actual": "H" if i % 10 < 8 else "A"}
           for i in range(100)]
    g = sx.league_gate(res, NAIVE)
    assert g["crit_ll"] and not g["crit_bands"] and g["verdict"] == "DROPPED — calibration"


def test_market_side_is_reported_never_gated():
    res = results(3, True)
    closes = {0: {"HOME": 2.0, "DRAW": 3.5, "AWAY": 4.0}, 1: {"HOME": 1.5, "DRAW": 4.0, "AWAY": 6.0}}
    m = sx.market_side(res, closes)
    assert (m["n_priced"], m["n_unpriced"]) == (2, 1) and m["edge_cohort"]["min_edge_pp"] == 5.0
    assert m["edge_cohort"]["n"] >= 1
    assert sx.market_side(res, {}) is None
    g = sx.league_gate(res, NAIVE)
    assert "market" not in g                                    # attached by run(), outside the verdict


def test_soccer_backtest_refuses_these_leagues_while_unrun(monkeypatch):
    import cli
    monkeypatch.setattr(reg, "get", lambda eid, path=None: DECLARED if eid == sx.EID else None)
    r = CliRunner().invoke(cli.cli, ["soccer-backtest", "--competition", "BL1", "--season", "2024/25"])
    assert r.exit_code == 2 and "read once" in r.output
    assert sx.guards_backtest("PL") is None
    monkeypatch.setattr(reg, "get", lambda eid, path=None: {**DECLARED, "run": {"run_at": "x"}})
    assert sx.guards_backtest("BL1") is None


@pytest.fixture(scope="module")
def league():
    init_db()
    with session_scope() as s:
        c = s.execute(select(Competition).where(Competition.code == "FL1")).scalar_one_or_none()
        if c is None:
            c = Competition(sport=Sport.SOCCER, code="FL1", name="Ligue 1", area="France", type="LEAGUE")
            s.add(c)
            s.flush()
        t = [Team(sport=Sport.SOCCER, name=f"SX Club {i}") for i in range(6)]
        s.add_all(t)
        s.flush()
        rng = random.Random(7)
        start = datetime(2097, 8, 1)
        for i in range(48):
            h, a = rng.sample(range(6), 2)
            s.add(Match(sport=Sport.SOCCER, competition_id=c.id, season="2097/98", utc_date=start + timedelta(days=i),
                        status=MatchStatus.FINISHED, status_raw="FT", home_team_id=t[h].id, away_team_id=t[a].id,
                        home_score=rng.randint(0, 3), away_score=rng.randint(0, 3)))
        up = Match(sport=Sport.SOCCER, competition_id=c.id, season="2097/98", utc_date=start + timedelta(days=60, hours=5),
                   status=MatchStatus.SCHEDULED, home_team_id=t[0].id, away_team_id=t[1].id)
        s.add(up)
        s.flush()
        return {"up": up.id, "now": start + timedelta(days=60)}


def test_shadow_rows_carry_no_desk_call_and_write_no_prediction(league, monkeypatch, tmp_path):
    monkeypatch.setattr(sx, "CURRENT_SEASON", "2097/98")
    monkeypatch.setattr(reg, "get", lambda eid, path=None: DECLARED if eid == sx.EID else None)
    path, doc = sx.export_shadow(("soccer_vX", -0.1, 0.0008), now=league["now"], hours=24, out_dir=str(tmp_path))
    assert (doc["engine"], doc["contains_predictions"]) == ("model_shadow", False)
    (r,) = [x for x in doc["predictions"] if x["match_id"] == league["up"]]
    assert r["engine"] == "model_shadow" and r["competition"] == "FL1" and r["gate_verdict"] == "DECLARED — gate not run"
    p = r["prediction"]
    assert p["home_win_prob"] + p["draw_prob"] + p["away_win_prob"] == pytest.approx(1, abs=1e-3)
    assert "desk" not in r and "order" not in r
    assert dp.normalize(json.loads(open(path).read())) == []          # never a Desk input
    doc2 = json.loads(open(path).read())
    dp.annotate(doc2, now=league["now"])
    assert all("desk" not in x for x in doc2["predictions"])
    with session_scope() as s:
        assert s.execute(select(func.count(Prediction.id)).where(Prediction.match_id == league["up"])).scalar() == 0
    assert doc["counts"]["FL1"]["priced"] == 1 and doc["counts"]["PD"] in ({"not_stored": 1}, {"priced": 0})


def test_expansion_chains_are_data_only():
    from deploy.hosting import chains
    pre = chains.CHAINS["soccer-prematch"]["steps"]
    for c in sx.LEAGUES:
        args = ["--competition", c, "--season", "2026/27"]
        assert ["sync-matches", *args] in pre and ["sync-odds", *args] in pre
        assert ["sync-matches", *args] in chains.CHAINS["soccer-morning-after"]["steps"]
    for chain in ("soccer-prematch", "soccer-morning-after"):        # data only: no other verb names them
        for st in chains.CHAINS[chain]["steps"]:
            if any(c in st for c in sx.LEAGUES):
                assert st[0] in ("sync-matches", "sync-odds"), st


def test_every_backtest_path_is_refused_on_these_leagues_while_unrun(monkeypatch):
    """Codex on #326: the guard lives in the walk itself, so the rho / coefficient sweeps and the candidate
    harnesses cannot read the sealed test seasons either; only the gate passes sealed_read=True."""
    from src.walters import soccer_backtest as sb
    monkeypatch.setattr(reg, "get", lambda eid, path=None: DECLARED if eid == sx.EID else None)
    with pytest.raises(sx.ExpansionRefused, match="read once"):
        sb.run_soccer_backtest("BL1", "2024/25", dixon_coles_rho=-0.1)
    import cli
    for cmd in (["dixon-coles-sweep", "--competition", "BL1", "--season", "2024/25"],
                ["elo-coeff-sweep", "--competition", "BL1", "--season", "2024/25"]):
        r = CliRunner().invoke(cli.cli, cmd)
        assert r.exit_code != 0 and isinstance(r.exception, sx.ExpansionRefused), (cmd, r.output[-200:])
    init_db()
    assert sb.run_soccer_backtest("BL1", "2024/25", sealed_read=True) is None    # the gate's path: not refused


def test_scoreable_count_is_the_walks_own_predicate_without_reading_a_score(league):
    """Codex on #326: > min_prior finished rows does not mean anything scores (the walk needs both teams among the
    prior rows). The pre-scoring check uses the walk's predicate; here it agrees with the walk itself."""
    from src.walters.soccer_backtest import run_soccer_backtest
    with session_scope() as s:
        n = sx.scoreable_count(s, "FL1", "2097/98")
        assert n == len(run_soccer_backtest("FL1", "2097/98", sx.MIN_PRIOR, sealed_read=True) or []) == 8
    with session_scope() as s:                 # committed (throwaway test DB): the walk reads in its own session
        c = s.execute(select(Competition).where(Competition.code == "FL1")).scalar_one()
        t = [Team(sport=Sport.SOCCER, name=f"SX Late {i}") for i in range(3)]
        s.add_all(t)
        s.flush()
        start = datetime(2098, 8, 1)
        for i in range(41):                    # 40 rows among t0/t1, then one row with a club absent from all 40
            h, a = (t[0], t[1]) if i < 40 else (t[0], t[2])
            s.add(Match(sport=Sport.SOCCER, competition_id=c.id, season="2098/99", utc_date=start + timedelta(days=i),
                        status=MatchStatus.FINISHED, status_raw="FT", home_team_id=h.id, away_team_id=a.id,
                        home_score=1, away_score=0))
    with session_scope() as s:
        assert (sx.finished_count(s, "FL1", "2098/99"), sx.scoreable_count(s, "FL1", "2098/99")) == (41, 0)
        assert sx.scoreable_count(s, "FL1", "2098/99", min_prior=39) == 1       # the 40th row: both clubs seen
    assert run_soccer_backtest("FL1", "2098/99", sx.MIN_PRIOR, sealed_read=True) == []
    assert len(run_soccer_backtest("FL1", "2098/99", 39, sealed_read=True)) == 1
