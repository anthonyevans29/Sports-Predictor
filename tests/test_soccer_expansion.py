"""soccer-expansion-v1 (ARCHITECT 2026-10-07, GATE-CLASS; declared, NOT run). Pins: the registry declaration and its
executable confirmation plan; the one-run command refuses unless declared and unrun, while the spec's findings are
open, and on a missing 2023/24 naive or test season (before any league is scored); the dropped-league rule and the
named surviving set; the market side-report is reported, never gated; soccer-backtest refuses these leagues while the
experiment is unrun; shadow rows are engine model_shadow, carry no desk call and write no prediction. The real
ledger is never touched (the registry is monkeypatched)."""
import json
import math
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


@pytest.fixture(autouse=True)
def _reservation(monkeypatch, tmp_path):
    """Every test reserves into a tmp path: the real docs/registry/ is never written."""
    monkeypatch.setattr(sx, "RESERVATION", str(tmp_path / "sx.started.json"))


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


def _prechecks_pass(monkeypatch):
    """Every pre-run check passes (the leagues are not stored in the test DB): placement, F1 baseline, counts."""
    monkeypatch.setattr(sx, "OPEN_FINDINGS", ())
    monkeypatch.setattr(sx, "unplaced", lambda s: [])
    monkeypatch.setattr(sx, "baseline_complete", lambda s, c: (True, "2023/24 complete"))
    monkeypatch.setattr(sx, "naive_for", lambda s, c: NAIVE)
    monkeypatch.setattr(sx, "finished_count", lambda s, c, se: 100)
    monkeypatch.setattr(sx, "scoreable_count", lambda s, c, se: 60)


def test_run_refuses_while_findings_are_open_and_on_missing_data(monkeypatch):
    # F1-F6 ruled (2026-10-07 / 2026-10-08); R1 (the registry operator correction) has no field to land in, so the
    # run still refuses until the architect directs it
    assert [f[:2] for f in sx.OPEN_FINDINGS] == ["R1"]
    with pytest.raises(sx.ExpansionRefused, match="open findings.*R1"):
        sx.run(-0.1, 0.0008)
    scored = []
    monkeypatch.setattr("src.walters.soccer_backtest.run_soccer_backtest",
                        lambda *a, **k: scored.append(a) or results(5, True))
    _prechecks_pass(monkeypatch)
    monkeypatch.setattr(sx, "unplaced", lambda s: ["SA 2024/25 'Weird Round' (2)"])
    with pytest.raises(sx.ExpansionRefused, match="cannot place.*Weird Round"):
        sx.run(-0.1, 0.0008)
    monkeypatch.setattr(sx, "unplaced", lambda s: [])
    monkeypatch.setattr(sx, "baseline_complete", lambda s, c: (False, "no regular-season row stored for 2023/24"))
    with pytest.raises(sx.ExpansionRefused, match="every league is dropped before the run.*nothing to test"):
        sx.run(-0.1, 0.0008)
    monkeypatch.setattr(sx, "baseline_complete", lambda s, c: (True, "complete"))
    monkeypatch.setattr(sx, "scoreable_count", lambda s, c, se: 0 if (c, se) == ("SA", "2025/26") else 60)
    with pytest.raises(sx.ExpansionRefused, match="SA 2025/26 .100 finished regular-season, 0 scoreable"):
        sx.run(-0.1, 0.0008)
    assert scored == []                                         # refused BEFORE any league was scored


def test_a_league_that_misses_its_own_gate_is_dropped_and_the_verdict_names_the_survivors(monkeypatch):
    init_db()
    _prechecks_pass(monkeypatch)
    good = {"PD", "BL1"}
    seen_kw = []
    monkeypatch.setattr("src.walters.soccer_backtest.run_soccer_backtest",
                        lambda code, season, *a, **k: seen_kw.append(k) or results(
                            60, code in good, seed=hash((code, season)) % 97,
                            start=1000 * sx.LEAGUES.index(code) + (500 if season == "2025/26" else 0)))
    r = sx.run(-0.1, 0.0008)
    assert r["surviving"] == ["PD", "BL1"] and r["dropped"] == ["SA", "FL1", "ELC"]
    assert r["verdict"] == "PASS — surviving set PD, BL1" and r["dropped_before_run"] == {}
    assert r["per_league"]["SA"]["verdict"].startswith("DROPPED") and len(r["scored_ids"]) == 5 * 120
    assert sx.overall({c: {"survives": False} for c in sx.LEAGUES})["verdict"] == "FAIL — no league survives"
    # F3 + F5 (ruled): the gate walks regular-season rows only, same-kickoff fixtures batched
    assert all(k["stage_filter"] is sx.is_regular and k["batch_same_kickoff"] is True and k["sealed_read"]
               for k in seen_kw) and len(seen_kw) == 10


def test_f1_a_league_without_a_complete_baseline_is_dropped_before_the_run_never_read(monkeypatch):
    """ARCHITECT 2026-10-07 (addendum 3, F1): dropped from the candidate before the run, named with the reason; not a
    FAIL; no test-season read for it; the verdict names it apart from the gate's drops; the record carries it."""
    init_db()
    _prechecks_pass(monkeypatch)
    monkeypatch.setattr(sx, "baseline_complete", lambda s, c: (False, "2023/24 incomplete: 300 rows") if c == "ELC"
                        else (True, "complete"))
    read = []
    monkeypatch.setattr("src.walters.soccer_backtest.run_soccer_backtest",
                        lambda code, season, *a, **k: read.append(code) or results(
                            60, code == "PD", seed=3, start=1000 * sx.LEAGUES.index(code)
                            + (500 if season == "2025/26" else 0)))
    r = sx.run(-0.1, 0.0008)
    assert "ELC" not in read and "ELC" not in r["per_league"]
    assert r["dropped_before_run"] == {"ELC": "2023/24 incomplete: 300 rows"}
    assert r["surviving"] == ["PD"] and r["dropped"] == ["SA", "BL1", "FL1"]
    assert r["verdict"] == ("PASS — surviving set PD · dropped before the run (no complete stored 2023/24 baseline; "
                            "not gated): ELC (2023/24 incomplete: 300 rows)")
    saved = json.load(open(sx.reservation_path()))
    assert saved["dropped_before_run"] == {"ELC": "2023/24 incomplete: 300 rows"}
    v = sx.overall({}, {c: "x" for c in sx.LEAGUES if c != "SA"})
    assert v["verdict"].startswith("FAIL — no league survives · dropped before the run") and v["dropped"] == ["SA"]


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
                        home_score=rng.randint(0, 3), away_score=rng.randint(0, 3), stage=f"Regular Season - {i + 1}"))
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
        assert ["sync-kalshi-soccer", "--competition", c] in pre          # ARCHITECT 2026-10-07: capture only
    for chain in ("soccer-prematch", "soccer-morning-after"):        # data only: no other verb names them
        for st in chains.CHAINS[chain]["steps"]:
            if any(c in st for c in sx.LEAGUES):
                assert st[0] in ("sync-matches", "sync-odds", "sync-kalshi-soccer"), st
    # "A pinned series never makes a league live": no export / predict / window Kalshi line names them anywhere
    for name, chain in chains.CHAINS.items():
        for st in chain.get("steps") or []:
            if any(c in st for c in sx.LEAGUES):
                assert st[0] in ("sync-matches", "sync-odds", "sync-kalshi-soccer"), (name, st)
    assert not set(sx.LEAGUES) & set(chains.WINDOW_KALSHI)


def test_expansion_kalshi_series_are_pinned_as_ruled():
    """ARCHITECT 2026-10-07 (addendum 2, from the operator's kalshi-probe receipt): five pinned, three recorded
    and not wired. Pinned means resolved without discovery; never a sibling series."""
    from src.adapters.kalshi import KalshiAdapter
    a = KalshiAdapter.__new__(KalshiAdapter)
    a._get = lambda path, params=None: (_ for _ in ()).throw(AssertionError("no discovery for a pinned code"))
    pins = {"PD": "KXLALIGAGAME", "SA": "KXSERIEAGAME", "BL1": "KXBUNDESLIGAGAME", "FL1": "KXLIGUE1GAME",
            "ELC": "KXEFLCHAMPIONSHIPGAME"}
    for code, ticker in pins.items():
        assert a.resolve_soccer_series(code) == (ticker, "mapped")
    assert set(pins) == set(sx.LEAGUES)
    for code, ticker in {"EL1": "KXEFLL1GAME", "EFL": "KXEFLCUPGAME", "CZE": "KXCZEFLGAME"}.items():
        t, how = a.resolve_soccer_series(code)
        assert t is None and ticker in how and "recorded, not wired" in how


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
    # Codex on #326 (round 2): the generic `backtest` walk reads any competition's scores; sealed too
    from src.walters import backtest as gb
    with pytest.raises(sx.ExpansionRefused, match="read once"):
        gb.run_backtest(season="2024/25", competition_code="BL1")
    r = CliRunner().invoke(cli.cli, ["backtest", "--competition", "BL1", "--season", "2024/25"])
    assert r.exit_code == 2 and "REFUSED" in r.output and "read once" in r.output
    init_db()
    assert sb.run_soccer_backtest("BL1", "2024/25", sealed_read=True) is None    # the gate's path: not refused


def test_scoreable_count_is_the_walks_own_predicate_without_reading_a_score(league):
    """Codex on #326: > min_prior finished rows does not mean anything scores (the walk needs both teams among the
    prior rows). The pre-scoring check uses the walk's predicate; here it agrees with the walk itself."""
    from src.walters.soccer_backtest import run_soccer_backtest
    with session_scope() as s:
        n = sx.scoreable_count(s, "FL1", "2097/98")
        assert n == len(run_soccer_backtest("FL1", "2097/98", sx.MIN_PRIOR, sealed_read=True) or []) == 8
        assert n == len(run_soccer_backtest("FL1", "2097/98", sx.MIN_PRIOR, sealed_read=True, stage_filter=sx.is_regular,
                                            batch_same_kickoff=True))
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
                        home_score=1, away_score=0, stage="Regular Season - 1"))
    with session_scope() as s:
        assert (sx.finished_count(s, "FL1", "2098/99"), sx.scoreable_count(s, "FL1", "2098/99")) == (41, 0)
        assert sx.scoreable_count(s, "FL1", "2098/99", min_prior=39) == 1       # the 40th row: both clubs seen
    assert run_soccer_backtest("FL1", "2098/99", sx.MIN_PRIOR, sealed_read=True) == []
    assert len(run_soccer_backtest("FL1", "2098/99", 39, sealed_read=True)) == 1


def test_the_run_reserves_the_gate_before_the_first_read_and_fails_closed(monkeypatch):
    """Codex on #326: an interrupted, failed or concurrent run cannot read the sealed seasons a second time."""
    import os
    monkeypatch.setattr(reg, "get", lambda eid, path=None: DECLARED if eid == sx.EID else None)
    _prechecks_pass(monkeypatch)
    for patch in (("unplaced", lambda s: ["PD 2023/24 None (1)"]),                       # F3 unplaced label
                  ("baseline_complete", lambda s, c: (False, "competition not stored"))):  # F1: all five dropped
        with monkeypatch.context() as m:
            m.setattr(sx, *patch)
            with pytest.raises(sx.ExpansionRefused, match="cannot place|nothing to test"):
                sx.run(-0.1, 0.0008)
        assert not os.path.exists(sx.reservation_path())      # a pre-check refusal spends nothing

    def boom(*a, **k):
        raise KeyboardInterrupt                                # interrupted mid-read
    monkeypatch.setattr("src.walters.soccer_backtest.run_soccer_backtest", boom)
    with pytest.raises(KeyboardInterrupt):
        sx.run(-0.1, 0.0008, meta={"production_version": "v22"})
    saved = json.load(open(sx.reservation_path()))
    assert saved["id"] == sx.EID and saved["production_version"] == "v22" and saved["rho"] == -0.1
    for again in (lambda: sx.run(-0.1, 0.0008), sx.declared_unrun, sx.reserve):
        with pytest.raises(sx.ExpansionRefused, match="never|without an architect ruling"):
            again()


def test_the_run_record_keeps_the_calibration_bands(monkeypatch):
    """Codex on #326: the band rows (the calibration half of each verdict) stay in the durable record."""
    import cli
    monkeypatch.setattr(reg, "get", lambda eid, path=None: DECLARED if eid == sx.EID else None)
    monkeypatch.setattr(cli, "_soccer_prod_poisson", lambda: ("v22", -0.1, 0.0008))
    g = sx.league_gate(results(300, True), NAIVE)
    g["market"] = None
    monkeypatch.setattr(sx, "run", lambda rho, coeff, progress=None, meta=None: {
        "per_league": {"PD": g}, "verdict": "x", "surviving": ["PD"], "dropped": [], "scored_ids": [1]})
    seen = {}
    monkeypatch.setattr(reg, "record_run", lambda eid, ids, result: seen.update(result) or {
        "run": {"n_scored": 1, "ids_sha256": "ab" * 32, "ids_file": "f"}})
    r = CliRunner().invoke(cli.cli, ["soccer-expansion-gate"])
    assert r.exit_code == 0, r.output
    bands = seen["per_league"]["PD"]["bands"]
    assert bands and {b["band"] for b in bands} == {b["band"] for b in g["bands"]}
    assert all({"n", "stated", "realized", "gated", "ok"} <= set(b) for b in bands)
    json.dumps(seen)                                           # the record stays JSON-serialisable


# ---------------------------------------------------------------- ARCHITECT 2026-10-07, addendum 3, item B (F1-F5) --

def test_f3_placement_is_pure_and_never_guesses():
    """Match.stage holds api-football's league.round verbatim ("Regular Season - 14"). Only that exact form is
    regular; play-off / relegation / promotion / final rounds are playoff; anything else (NULL included) is None."""
    assert sx.placement("Regular Season - 1") == sx.placement("Regular Season - 38") == "regular"
    for lab in ("Relegation Play-offs", "Promotion Play-offs - Semi-finals", "Semi-finals", "Final",
                "Relegation Round", "Play-offs", "Championship Round - 3"):
        assert sx.placement(lab) == "playoff", lab
    for lab in (None, "", "Regular Season", "Regular Season - 5 ", "regular season - 5", "Round of 16",
                "Group A", "1st Round"):
        assert sx.placement(lab) is None, lab
    assert sx.is_regular("Regular Season - 2") and not sx.is_regular("Final") and not sx.is_regular(None)


def test_f4_ties_reject_at_exact_equality(monkeypatch):
    """ARCHITECT 2026-10-07 (F4): PASS iff log-loss < naive - 0.010 on unrounded values; equality fails."""
    res = [{"match_id": 1, "p_home": 0.6, "p_draw": 0.2, "p_away": 0.2, "actual": "H"}]
    naive = {"H": 0.45, "D": 0.27, "A": 0.28, "n": 380}
    a = 1.05
    b = a - sx.LL_MARGIN                                   # the bar, computed exactly as league_gate computes it
    monkeypatch.setattr(sx, "ll3", lambda p: {0.6: b, 0.45: a}[p])
    g = sx.league_gate(res, naive)
    assert g["ll_model"] == g["bar"] == b and g["ll_naive"] == a
    assert (g["ll_naive"] - g["ll_model"]) >= sx.LL_MARGIN - 1e-12   # the old comparison would have passed it
    assert g["crit_ll"] is False and "log-loss margin" in g["verdict"]
    monkeypatch.setattr(sx, "ll3", lambda p: {0.6: math.nextafter(b, 0), 0.45: a}[p])
    assert sx.league_gate(res, naive)["crit_ll"] is True  # one ulp under the bar passes


def _season(code, season, rows, name):
    """Store a synthetic league-season in the throwaway test DB. rows: (hours_from_start, h, a, hs, as_, stage);
    hs None = a SCHEDULED row."""
    with session_scope() as s:
        c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
        if c is None:
            c = Competition(sport=Sport.SOCCER, code=code, name=code, area="x", type="LEAGUE")
            s.add(c)
            s.flush()
        n = 1 + max(max(r[1], r[2]) for r in rows)
        t = [Team(sport=Sport.SOCCER, name=f"{name} {i}") for i in range(n)]
        s.add_all(t)
        s.flush()
        start = datetime(2090, 8, 1)
        for off, h, a, hs, as_, stage in rows:
            done = hs is not None
            s.add(Match(sport=Sport.SOCCER, competition_id=c.id, season=season, utc_date=start + timedelta(hours=off),
                        status=MatchStatus.FINISHED if done else MatchStatus.SCHEDULED,
                        status_raw="FT" if done else None, home_team_id=t[h].id, away_team_id=t[a].id,
                        home_score=hs, away_score=as_, stage=stage))
        return [x.id for x in t]


def _ref_walk(code, season, min_prior, rho, coeff):
    """The pre-change harness walk (row by row), re-stated: the default path must reproduce it exactly."""
    import dataclasses
    from src.walters import soccer_backtest as sb
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == code)).scalar_one()
        ms = [m for m in s.execute(select(Match).where(Match.competition_id == comp.id, Match.season == season,
                                                       Match.status == MatchStatus.FINISHED)).scalars()
              if m.utc_date and m.home_score is not None and m.away_score is not None]
        ms.sort(key=lambda m: m.utc_date)
        ctx, elo = sb.CompetitionScoringContext(), sb.EloState(config=sb.EloConfig())
        cfg = dataclasses.replace(sb.PoissonConfig(), dixon_coles_rho=rho, elo_goal_coeff=coeff)
        out, prior = [], []
        for m in ms:
            if len(prior) >= min_prior:
                st = sb.estimate_strengths([{"home_team_id": p.home_team_id, "away_team_id": p.away_team_id,
                                             "home_score": p.home_score, "away_score": p.away_score} for p in prior],
                                           ctx, weights=None)
                hs, as_ = st.get(m.home_team_id), st.get(m.away_team_id)
                if hs and as_:
                    pr = sb.predict_match(home_elo=elo.get(m.home_team_id), away_elo=elo.get(m.away_team_id),
                                          home_strength=hs, away_strength=as_, context=ctx, config=cfg)
                    act = "H" if m.home_score > m.away_score else "A" if m.home_score < m.away_score else "D"
                    out.append({"match_id": m.id, "p_home": pr.p_home, "p_draw": pr.p_draw, "p_away": pr.p_away,
                                "actual": act})
            nh, na = sb.update_after_match(elo.get(m.home_team_id), elo.get(m.away_team_id), m.home_score,
                                           m.away_score, elo.config)
            elo.set(m.home_team_id, nh)
            elo.set(m.away_team_id, na)
            prior.append(m)
        return out


@pytest.fixture(scope="module")
def kickoffs():
    """BL1 "2090/91": 39 regular rows on distinct kickoffs (one relegation play-off row among them), then G1 = three
    rows sharing a kickoff that straddles min_prior (regular indices 39-41), 20 more distinct rows, then G2 = two
    rows sharing a kickoff with a shared club (0), and a final play-off row."""
    init_db()
    rng = random.Random(11)
    rows, hour = [], 0
    pairs = [(h, a) for h in range(6) for a in range(6) if h != a]
    for i in range(39):
        h, a = pairs[i % len(pairs)]
        rows.append((hour, h, a, rng.randint(0, 3), rng.randint(0, 3), f"Regular Season - {i // 3 + 1}"))
        hour += 24
        if i == 20:
            rows.append((hour, 2, 3, 2, 2, "Relegation Play-offs"))
            hour += 24
    for h, a in ((0, 1), (0, 2), (3, 4)):
        rows.append((hour, h, a, rng.randint(0, 3), rng.randint(0, 3), "Regular Season - 14"))
    hour += 24
    for i in range(20):
        h, a = rng.sample(range(6), 2)
        rows.append((hour, h, a, rng.randint(0, 3), rng.randint(0, 3), f"Regular Season - {15 + i}"))
        hour += 24
    rows.append((hour, 0, 5, 3, 0, "Regular Season - 35"))
    rows.append((hour, 1, 0, 0, 3, "Regular Season - 35"))
    rows.append((hour + 24, 4, 5, 1, 1, "Relegation Play-offs"))
    _season("BL1", "2090/91", rows, "SX KO")
    return {"code": "BL1", "season": "2090/91"}


def test_f5_default_walk_is_byte_identical_to_the_pre_change_walk(kickoffs):
    from src.walters.soccer_backtest import run_soccer_backtest
    code, se = kickoffs["code"], kickoffs["season"]
    got = run_soccer_backtest(code, se, sx.MIN_PRIOR, dixon_coles_rho=-0.1, elo_goal_coeff=0.0008, sealed_read=True)
    assert got and got == _ref_walk(code, se, sx.MIN_PRIOR, -0.1, 0.0008)
    explicit = run_soccer_backtest(code, se, sx.MIN_PRIOR, dixon_coles_rho=-0.1, elo_goal_coeff=0.0008,
                                   sealed_read=True, stage_filter=None, batch_same_kickoff=False)
    assert explicit == got
    batched = run_soccer_backtest(code, se, sx.MIN_PRIOR, dixon_coles_rho=-0.1, elo_goal_coeff=0.0008,
                                  sealed_read=True, batch_same_kickoff=True)
    assert batched != got                                   # the fixture exercises the difference


def test_f5_batched_rows_share_one_pre_state(kickoffs, monkeypatch):
    """Two same-kickoff rows with a shared club see the same Elo for it and the same prior; row-by-row they do not.
    Play-off rows (F3) are never scored under the gate's stage filter."""
    from src.walters import soccer_backtest as sb
    code, se = kickoffs["code"], kickoffs["season"]

    def capture(batch):
        calls, sizes = [], []
        real_p, real_s = sb.predict_match, sb.estimate_strengths
        with monkeypatch.context() as m:
            m.setattr(sb, "predict_match", lambda **k: calls.append((k["home_elo"], k["away_elo"])) or real_p(**k))
            m.setattr(sb, "estimate_strengths", lambda inp, ctx, weights=None: sizes.append(len(inp))
                      or real_s(inp, ctx, weights=weights))
            res = sb.run_soccer_backtest(code, se, sx.MIN_PRIOR, sealed_read=True, stage_filter=sx.is_regular,
                                         batch_same_kickoff=batch)
        return res, calls, sizes
    res, calls, sizes = capture(True)
    (h1, _), (_, a2) = calls[-2], calls[-1]                 # G2: club 0 at home, then away, same kickoff
    assert h1 == a2 and sizes[-1] == sizes[-2]
    res0, calls0, sizes0 = capture(False)
    assert calls0[-2][0] != calls0[-1][1] and sizes0[-1] == sizes0[-2] + 1
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == code)).scalar_one()
        play = set(s.execute(select(Match.id).where(Match.competition_id == comp.id, Match.season == se,
                                                    Match.stage == "Relegation Play-offs")).scalars())
    assert len(play) == 2 and not play & {r["match_id"] for r in res + res0}       # F3: never scored


def test_scoreable_count_agrees_with_the_walk_in_both_modes(kickoffs):
    from src.walters.soccer_backtest import run_soccer_backtest
    code, se = kickoffs["code"], kickoffs["season"]
    counts = {}
    with session_scope() as s:
        assert sx.finished_count(s, code, se) == 64            # the two play-off rows excluded (F3)
        for batch in (False, True):
            n = sx.scoreable_count(s, code, se, batch_same_kickoff=batch)
            walk = run_soccer_backtest(code, se, sx.MIN_PRIOR, sealed_read=True, stage_filter=sx.is_regular,
                                       batch_same_kickoff=batch)
            assert n == len(walk), batch
            counts[batch] = n
        assert sx.scoreable_count(s, code, se) == counts[True]     # the gate's default is batched
    assert counts[False] == counts[True] + 2                    # G1 straddles min_prior: only row-by-row scores 2


def _round_robin(t):
    return [(24 * k, h, a, (h + k) % 3, a % 2, f"Regular Season - {k + 1}")
            for k, (h, a) in enumerate((h, a) for h in range(t) for a in range(t) if h != a)]


def test_f1_complete_stored_season_and_f3_census(monkeypatch):
    """F1's operational definition and F3's census on stored rows; naive_for reads regular-season rows only."""
    init_db()
    monkeypatch.setattr(sx, "NAIVE_SEASON", "2091/92")
    rr = _round_robin(4)
    _season("FL1", "2091/92", rr + [(500, 0, 1, 0, 3, "Relegation Play-offs")], "SX RR")
    with session_scope() as s:
        ok, why = sx.baseline_complete(s, "FL1")
        assert ok and "12 regular-season rows, 4 clubs" in why
        assert sx.naive_for(s, "FL1")["n"] == 12                 # the play-off row is not in the baseline
        census = sx.stage_census(s, "FL1", "2091/92")
        assert ("Relegation Play-offs", 1, "playoff") in census and all(pl for _, _, pl in census)
    _season("FL1", "2092/93", rr[:-1], "SX RR short")            # one fixture never stored
    _season("FL1", "2093/94", rr[:-1] + [(900, 3, 2, None, None, rr[-1][5])], "SX RR open")   # one not finished
    for season, frag in (("2092/93", "11 regular-season rows, 4 clubs (a double round-robin is 12)"),
                         ("2093/94", "1 not finished"), ("2094/95", "no regular-season row stored")):
        monkeypatch.setattr(sx, "NAIVE_SEASON", season)
        with session_scope() as s:
            ok, why = sx.baseline_complete(s, "FL1")
            assert not ok and frag in why, why
    with session_scope() as s:
        assert sx.baseline_complete(s, "XX9") == (False, "competition not stored")


def test_the_run_end_to_end_on_stored_rows(monkeypatch):
    """F1 + F3 + F5 through run() on synthetic seasons: an unplaced label refuses before the reservation; a league
    with an incomplete baseline is dropped before the run and never read; leagues not stored are dropped too."""
    import os
    import src.walters.soccer_backtest as sb
    init_db()
    monkeypatch.setattr(sx, "OPEN_FINDINGS", ())
    monkeypatch.setattr(sx, "NAIVE_SEASON", "2095/96")
    monkeypatch.setattr(sx, "TEST_SEASONS", ("2096/97", "2097/98x"))
    rr = _round_robin(4)
    _season("SA", "2095/96", rr, "SX E2E SA")                      # complete baseline
    _season("PD", "2095/96", rr[:-2], "SX E2E PD")                 # incomplete: dropped before the run
    rng = random.Random(5)
    for se in sx.TEST_SEASONS:
        rows = [(24 * k, *rng.sample(range(4), 2), rng.randint(0, 3), rng.randint(0, 3), f"Regular Season - {k + 1}")
                for k in range(60)]
        rows.append((24 * 61, 0, 1, 1, 0, "Promotion Play-offs - Final"))
        _season("SA", se, rows, f"SX E2E SA {se}")
        _season("PD", se, rows, f"SX E2E PD {se}")
    _season("SA", "2096/97", [(24 * 70, 0, 1, None, None, "Matchday Special")], "SX E2E odd")
    read = []
    real = sb.run_soccer_backtest
    monkeypatch.setattr(sb, "run_soccer_backtest", lambda code, *a, **k: read.append(code) or real(code, *a, **k))
    with pytest.raises(sx.ExpansionRefused, match="cannot place.*SA 2096/97 'Matchday Special'"):
        sx.run(-0.1, 0.0008)
    assert read == [] and not os.path.exists(sx.reservation_path())
    with session_scope() as s:                                     # the odd row becomes a stale orphan: not a fixture
        comp = s.execute(select(Competition).where(Competition.code == "SA")).scalar_one()
        m = s.execute(select(Match).where(Match.competition_id == comp.id,
                                          Match.stage == "Matchday Special")).scalar_one()
        m.status = MatchStatus.STALE_ORPHAN
    r = sx.run(-0.1, 0.0008)
    assert set(read) == {"SA"} and list(r["per_league"]) == ["SA"]
    assert set(r["dropped_before_run"]) == {"PD", "BL1", "FL1", "ELC"}
    assert "incomplete" in r["dropped_before_run"]["PD"]
    assert "dropped before the run" in r["verdict"] and "PD (2095/96 incomplete" in r["verdict"]
    with session_scope() as s:
        po = set(s.execute(select(Match.id).where(Match.stage == "Promotion Play-offs - Final")).scalars())
        assert sum(sx.scoreable_count(s, "SA", se) for se in sx.TEST_SEASONS) == r["per_league"]["SA"]["n"]
    assert po and not po & set(r["scored_ids"])


def test_preflight_prints_every_label_with_its_placement_and_the_baseline(monkeypatch):
    """F1 + F3: the preflight receipt the architect confirms placement from; it scores nothing."""
    import cli
    init_db()
    monkeypatch.setattr(reg, "get", lambda eid, path=None: DECLARED if eid == sx.EID else None)
    _season("ELC", "2024/25", [(0, 0, 1, 1, 0, "Regular Season - 1"), (24, 1, 0, 0, 0, "Semi-finals"),
                               (48, 0, 1, None, None, None)], "SX PF")
    r = CliRunner().invoke(cli.cli, ["soccer-expansion-gate", "--preflight"])
    assert r.exit_code == 0, r.output
    assert "stages 2024/25: 'Regular Season - 1' 1 → regular; 'Semi-finals' 1 → playoff; None 1 → UNPLACED" in r.output
    assert "UNPLACED label(s), the run refuses: ELC 2024/25 None" in r.output
    assert "ELC: " in r.output and "DROPPED BEFORE THE RUN" in r.output
    assert "open findings (the run refuses until ruled): R1" in r.output and "nothing scored" in r.output


def test_shadow_leagues_never_get_a_venue_call():
    """Codex on #326: the pinned series are captured, and the 24h window card spans every competition, so the venue
    engine must never call these leagues (window card and any fixtures file) until CONFIRMED."""
    from datetime import timezone
    from deploy.hosting import chains
    assert dp.SHADOW_VENUE_COMPS == set(sx.LEAGUES) == set(chains.KALSHI_CAPTURE_ONLY)
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    now_ms = now.timestamp() * 1000
    ko = (now + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S")
    row = {"home_team": "A", "away_team": "B", "utc_date": ko, "status": "scheduled", "engine": "market_only",
           "competition": "PD", "market": {"bookmaker_count": 8, "fair_prob": {"HOME": .60, "DRAW": .22, "AWAY": .18},
                                            "captured_at": (now - timedelta(minutes=20)).isoformat()},
           "kalshi": {"status": "two_sided", "prob": {"HOME": .45, "DRAW": .30, "AWAY": .25}}}
    v = dp.window_venue(row, now_ms)
    assert v["eligible"] is False and "shadow league (PD" in v["reason"]
    pl = dp.window_venue({**row, "competition": "PL"}, now_ms)          # a live league with the same gap: unchanged
    assert "shadow league" not in pl["reason"]
    fx = {"competition_code": "SA", "fixtures": [{**row, "competition": "SA"}]}
    dp.annotate(fx, now=now)
    d = fx["fixtures"][0]["desk"]
    assert d["call"] == "PASS" and d["order"] is None and "shadow league (SA" in d["reason"]


def test_f6_a_league_with_no_gated_band_is_dropped_never_passed_on_log_loss_alone():
    """F6 (ARCHITECT 2026-10-08): no calibration band at >= 100 observations FAILS the bands criterion."""
    few = results(20, True)                                      # 60 pairs: no band can reach 100
    g = sx.league_gate(few, NAIVE)
    assert not any(b["gated"] for b in g["bands"])
    assert g["crit_bands"] is False and g["survives"] is False
    assert "no gated band" in g["verdict"] and g["verdict"].startswith("DROPPED")
