"""SOCCER-CANDIDATES lane (architect 2026-10-01; backtest-only, verdicts only):
(a) Dixon-Coles rho fitted on 2023/24 only, frozen; (b) S14 Stage-2 totals
adjustment (+1.17 goals on top pick < 0.45). Frozen constants, the fit
procedure, the walk extensions (off = byte-identical), the S14 criteria, and
both candidates end to end on a synthetic league; production untouched."""
import random
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, ModelVersion, Sport, Team
from src.walters import soccer_backtest as sb
from src.walters import soccer_candidates as sc

CODE = "SCAND"
SEASONS = ("2081/82", "2082/83", "2083/84")


def test_constants_frozen_a_priori():
    assert sc.GATE_COMPETITION == "PL" and sc.GATE_SEASONS == ("2023/24", "2024/25", "2025/26")
    assert sc.DC_FIT_SEASON == "2023/24" and sc.OOS_SEASONS == ("2024/25", "2025/26")
    assert (sc.DC_RHO_LO, sc.DC_RHO_HI, sc.DC_RHO_STEP) == (-0.300, 0.200, 0.001)
    assert sc.S14_UNCERTAIN_TOP_PICK == 0.45 and sc.S14_OFFSET_GOALS == 1.17
    assert sc.S14_CONFIDENT_TOL == 0.15 and sc.S14_TOTAL_LINE_GOALS == 3
    g = sc.rho_grid()
    assert g[0] == -0.3 and g[-1] == 0.2 and len(g) == 501 and 0.0 in g and -0.1 in g


def test_tau_and_fit_procedure():
    assert sc.tau(0, 0, 1.2, 1.0, -0.1) == pytest.approx(1 + 0.12)
    assert sc.tau(1, 0, 1.2, 1.0, -0.1) == pytest.approx(0.9)
    assert sc.tau(0, 1, 1.2, 1.0, -0.1) == pytest.approx(1 - 0.12)
    assert sc.tau(1, 1, 1.2, 1.0, -0.1) == pytest.approx(1.1)
    assert sc.tau(2, 1, 1.2, 1.0, -0.1) == 1.0
    row = lambda h, a: {"home_score": h, "away_score": a, "home_xg": 1.3, "away_xg": 1.1}
    # draw-heavy low scores -> negative rho; 1-0/0-1-heavy -> positive rho
    draws = [row(0, 0)] * 6 + [row(1, 1)] * 6 + [row(1, 0)] * 2 + [row(0, 1)] * 2 + [row(2, 1)] * 10
    assert sc.fit_rho(draws)["rho"] < 0
    singles = [row(1, 0)] * 8 + [row(0, 1)] * 8 + [row(0, 0)] + [row(1, 1)] + [row(3, 2)] * 10
    assert sc.fit_rho(singles)["rho"] > 0
    # no low scores at all: the likelihood is flat -> tie-break to the smallest |rho| = 0.0
    assert sc.fit_rho([row(2, 2), row(3, 1)])["rho"] == 0.0
    # infeasible points are skipped, never chosen
    assert sc.dc_loglik([row(1, 1)], 1.0) is None


def test_s14_criteria_hand_case():
    def r(mid, ph, pd, pa, hx, ax, hs, as_, po):
        return {"match_id": mid, "p_home": ph, "p_draw": pd, "p_away": pa, "home_xg": hx,
                "away_xg": ax, "home_score": hs, "away_score": as_, "p_over": po}
    base = [r(1, .40, .30, .30, 1.0, 1.0, 2, 2, .40),     # uncertain: residual +2.0
            r(2, .70, .20, .10, 2.0, 0.5, 2, 0, .55)]     # confident: residual -0.5
    cand = [r(1, .42, .26, .32, 1.5, 1.5, 2, 2, .60),     # uncertain: residual +1.0; over now right
            r(2, .70, .20, .10, 2.0, 0.5, 2, 0, .55)]
    s = sc.s14_criteria(base, cand)
    assert s["uncertain_residual"] == (2.0, 1.0) and s["confident_residual"] == (-0.5, -0.5)
    assert s["direction_hits"] == (0, 1)
    assert s["i_toward_zero"] and s["ii_direction_not_worse"] and s["iii_confident_within_tol"] and s["pass"]
    worse = [dict(cand[0], home_xg=0.5, away_xg=0.5), cand[1]]     # residual +3.0: away from zero
    assert not sc.s14_criteria(base, worse)["i_toward_zero"]


@pytest.fixture(scope="module")
def world():
    init_db()
    rnd = random.Random(1401)
    with session_scope() as s:
        if s.execute(select(Competition).where(Competition.code == CODE)).scalar_one_or_none():
            return CODE
        comp = Competition(sport=Sport.SOCCER, code=CODE, name="candidates test league",
                           area="Testland", type="LEAGUE")
        teams = [Team(sport=Sport.SOCCER, name=f"SCAND club {i}") for i in range(8)]
        s.add(comp)
        s.add_all(teams)
        s.flush()
        ids = [t.id for t in teams]
        for si, season in enumerate(SEASONS):
            t0 = datetime(2081 + si, 8, 10, 15)
            for leg in range(2):
                for rd in range(7):
                    rot = ids[:1] + ids[1:][rd:] + ids[1:][:rd]
                    day = t0 + timedelta(days=18 * (leg * 7 + rd))
                    for i in range(4):
                        h, a = (rot[i], rot[7 - i]) if leg == 0 else (rot[7 - i], rot[i])
                        qh, qa = 1 + 0.3 * (ids.index(h) / 7 - 0.5), 1 + 0.3 * (ids.index(a) / 7 - 0.5)
                        hs = sum(1 for _ in range(10) if rnd.random() < 1.4 * qh / qa / 10)
                        as_ = sum(1 for _ in range(10) if rnd.random() < 1.1 * qa / qh / 10)
                        s.add(Match(sport=Sport.SOCCER, competition_id=comp.id, season=season,
                                    utc_date=day, status=MatchStatus.FINISHED,
                                    home_team_id=h, away_team_id=a, home_score=hs, away_score=as_))
    return CODE


KW = dict(min_prior=20, dixon_coles_rho=-0.10, elo_goal_coeff=0.0008)


def test_walk_extensions_off_are_byte_identical(world):
    base = sb.run_soccer_backtest(world, SEASONS[0], **KW)
    assert sb.run_soccer_backtest(world, SEASONS[0], detail=False, s14_uncertain_offset=None, **KW) == base
    det = sb.run_soccer_backtest(world, SEASONS[0], detail=True, **KW)
    assert [{k: d[k] for k in base[0]} for d in det] == base          # detail only ADDS keys
    assert {"home_xg", "away_xg", "p_over", "home_score", "away_score"} <= set(det[0])


def test_s14_offset_moves_only_uncertain_games(world):
    base = sb.run_soccer_backtest(world, SEASONS[0], detail=True, **KW)
    cand = sb.run_soccer_backtest(world, SEASONS[0], detail=True, s14_uncertain_offset=1.17, **KW)
    assert [b["match_id"] for b in base] == [c["match_id"] for c in cand]
    unc = [(b, c) for b, c in zip(base, cand) if max(b["p_home"], b["p_draw"], b["p_away"]) < 0.45]
    conf = [(b, c) for b, c in zip(base, cand) if max(b["p_home"], b["p_draw"], b["p_away"]) >= 0.45]
    assert unc and conf
    for b, c in conf:
        assert b == c
    for b, c in unc:
        assert (c["home_xg"] + c["away_xg"]) - (b["home_xg"] + b["away_xg"]) == pytest.approx(1.17, abs=1e-9)
        assert c["p_draw"] < b["p_draw"] and c["p_over"] > b["p_over"]


@pytest.fixture
def gate_on_world(world, monkeypatch):
    monkeypatch.setattr(sc, "GATE_COMPETITION", world)
    monkeypatch.setattr(sc, "GATE_SEASONS", SEASONS)
    monkeypatch.setattr(sc, "DC_FIT_SEASON", SEASONS[0])
    monkeypatch.setattr(sc, "OOS_SEASONS", SEASONS[1:])
    return world


def test_dixon_coles_candidate_end_to_end(gate_on_world):
    r = sc.run_dixon_coles_candidate(prod_rho=-0.10, elo_goal_coeff=0.0008, min_prior=20)
    assert r["fit"]["rho"] is not None and sc.DC_RHO_LO <= r["fit"]["rho"] <= sc.DC_RHO_HI
    p = r["pooled"]
    assert p["verdict"] in ("PASS", "REJECT") and p["n"] == 3 * 36
    assert p["verdict"] == ("PASS" if p["delta"] >= 0.005 else "REJECT")
    assert r["oos_pooled"]["n"] == 2 * 36 and "_arms" not in r


def test_s14_candidate_end_to_end(gate_on_world):
    r = sc.run_s14_candidate(prod_rho=-0.10, elo_goal_coeff=0.0008, min_prior=20)
    p, s = r["pooled"], r["s14"]
    assert p["verdict"] in ("PASS", "REJECT") and s["n"] == 3 * 36
    assert s["iii_confident_within_tol"] and s["confident_residual"][0] == s["confident_residual"][1]
    assert r["verdict"] == ("PASS" if p["verdict"] == "PASS" and s["pass"] else "REJECT")


def test_missing_season_is_invalid(gate_on_world, monkeypatch):
    monkeypatch.setattr(sc, "GATE_SEASONS", (SEASONS[0], "1900/01"))
    assert sc.run_s14_candidate(prod_rho=-0.1, elo_goal_coeff=0.0008, min_prior=20)["verdict"] == "INVALID"
    assert sc.run_dixon_coles_candidate(prod_rho=-0.1, elo_goal_coeff=0.0008,
                                        min_prior=20)["pooled"]["verdict"] == "INVALID"


def _mv():
    with session_scope() as s:
        return sorted((m.sport.value, m.version, m.status, str(m.parameters))
                      for m in s.execute(select(ModelVersion)).scalars())


def test_cli_both_candidates_and_refusals(gate_on_world, monkeypatch):
    import cli
    monkeypatch.setattr(cli, "_soccer_prod_poisson", lambda: ("v22", -0.10, 0.0008))
    before = _mv()
    for cand, tag in (("dixon-coles-fit", "DC-FIT-GATE:"), ("s14-totals", "S14-STAGE2-GATE:")):
        out = CliRunner().invoke(cli.cli, ["soccer-backtest", "--competition", gate_on_world,
                                           "--min-prior", "20", "--candidate", cand])
        assert out.exit_code == 0, out.output
        gate = [ln for ln in out.output.splitlines() if ln.startswith(tag)]
        assert len(gate) == 1 and (" PASS " in gate[0] or " REJECT " in gate[0]), out.output
        assert "ties reject" in out.output
    assert "fitted rho =" in CliRunner().invoke(cli.cli, ["soccer-backtest", "--competition", gate_on_world,
                                                         "--min-prior", "20", "--candidate",
                                                         "dixon-coles-fit"]).output
    out = CliRunner().invoke(cli.cli, ["soccer-backtest", "--competition", gate_on_world, "--season",
                                       SEASONS[0], "--candidate", "s14-totals"])
    assert "S14-STAGE2-GATE: REFUSED" in out.output
    monkeypatch.setattr(cli, "_soccer_prod_poisson", lambda: None)
    out = CliRunner().invoke(cli.cli, ["soccer-backtest", "--competition", gate_on_world,
                                       "--candidate", "dixon-coles-fit"])
    assert "DC-FIT-GATE: INVALID" in out.output
    assert _mv() == before                                   # production untouched
