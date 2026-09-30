"""S19 + S20 (architect 2026-09-30, Issues #83/#84; backtest-only).

S20: RPS for ordered H<D<A 3-way predictions, hand-computed values, reported
beside log-loss (never in an acceptance criterion).
S19: the time-decay candidate — frozen half-life, decay weights, the weighted
strengths fit (None path byte-identical), and the candidate path end to end on a
tiny synthetic DB: both arms report log-loss + RPS on the same matches, the
existing gate (delta >= 0.0050, ties reject) decides, production is untouched.
"""
import math
import random
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, ModelVersion, Sport, Team
from src.models.poisson import CompetitionScoringContext, estimate_strengths
from src.walters import soccer_backtest as sb
from src.walters.evaluation import rps_1x2, score_1x2

CODE = "S19T"
SEASONS = ("2091/92", "2092/93")


# ---------------------------------------------------------------- S20: RPS

@pytest.mark.parametrize("p,actual,expected", [
    ((1.0, 0.0, 0.0), "H", 0.0),                 # certain and right
    ((1.0, 0.0, 0.0), "A", 1.0),                 # certain HOME, AWAY happened: worst
    ((1.0, 0.0, 0.0), "D", 0.5),                 # (0-1)^2... cum (1,1) vs (0,1): 1/2
    ((0.0, 0.0, 1.0), "H", 1.0),
    ((1 / 3, 1 / 3, 1 / 3), "H", 5 / 18),        # ((1/3-1)^2 + (2/3-1)^2)/2
    ((1 / 3, 1 / 3, 1 / 3), "D", 1 / 9),         # ((1/3)^2 + (2/3-1)^2)/2
    ((1 / 3, 1 / 3, 1 / 3), "A", 5 / 18),        # ((1/3)^2 + (2/3)^2)/2
    ((0.5, 0.3, 0.2), "A", 0.445),               # (0.25 + 0.64)/2
    ((0.5, 0.3, 0.2), "H", 0.145),               # (0.25 + 0.04)/2
    ((0.5, 0.3, 0.2), "D", 0.145),               # (0.25 + 0.04)/2
])
def test_rps_hand_values(p, actual, expected):
    assert rps_1x2(*p, actual) == pytest.approx(expected, abs=1e-12)


def test_rps_is_ordinal_and_matches_stored_scorer():
    # ordinal: missing by one category costs less than missing by two
    assert rps_1x2(0.2, 0.7, 0.1, "H") < rps_1x2(0.1, 0.2, 0.7, "H")
    rnd = random.Random(3)
    for _ in range(200):
        a, b = rnd.random(), rnd.random()
        lo, hi = min(a, b), max(a, b)
        p = (lo, hi - lo, 1 - hi)
        for act in "HDA":
            assert rps_1x2(*p, act) == score_1x2(*p, act).rps  # same arithmetic
    with pytest.raises(ValueError):
        rps_1x2(0.4, 0.3, 0.3, "X")


def test_calibration_reports_rps_beside_log_loss():
    results = [{"match_id": 1, "p_home": 0.5, "p_draw": 0.3, "p_away": 0.2, "actual": "A"},
               {"match_id": 2, "p_home": 1 / 3, "p_draw": 1 / 3, "p_away": 1 / 3, "actual": "D"}]
    cal = sb.soccer_calibration(results)
    assert cal["rps"] == pytest.approx((0.445 + 1 / 9) / 2)
    assert cal["log_loss"] == pytest.approx((-math.log(0.2) - math.log(1 / 3)) / 2)


# ------------------------------------------------------ S19: decay weights

def test_half_life_frozen_single_value():
    assert sb.TIME_DECAY_HALF_LIFE_DAYS == 365.0
    assert sb.S19_GATE_COMPETITION == "PL"
    assert sb.S19_GATE_SEASONS == ("2023/24", "2024/25", "2025/26")


def test_decay_weights():
    hl = 365.0
    assert sb.time_decay_weight(0, hl) == 1.0
    assert sb.time_decay_weight(365, hl) == pytest.approx(0.5)
    assert sb.time_decay_weight(730, hl) == pytest.approx(0.25)
    assert sb.time_decay_weight(182.5, hl) == pytest.approx(2 ** -0.5)
    assert sb.time_decay_weight(-5, hl) == 1.0          # clamps, never > 1
    assert sb.time_decay_weight(100, hl) > sb.time_decay_weight(101, hl)
    with pytest.raises(ValueError):
        sb.time_decay_weight(1, 0)


def _mini():
    return [
        {"home_team_id": 1, "away_team_id": 2, "home_score": 3, "away_score": 0},
        {"home_team_id": 2, "away_team_id": 3, "home_score": 1, "away_score": 1},
        {"home_team_id": 3, "away_team_id": 1, "home_score": 0, "away_score": 2},
        {"home_team_id": 1, "away_team_id": 3, "home_score": 0, "away_score": 1},
    ]


def test_weighted_strengths_none_path_unchanged_and_unit_weights_identical():
    ctx = CompetitionScoringContext(avg_goals_per_team_per_match=1.2, home_field_goal_boost=1.1)
    base = estimate_strengths(_mini(), ctx)
    ones = estimate_strengths(_mini(), ctx, weights=[1.0] * 4)
    assert {k: (v.attack, v.defense) for k, v in base.items()} == \
        {k: (v.attack, v.defense) for k, v in ones.items()}   # exact, not approx
    # hand check team 1, unweighted: gf = [3/1.1, 2, 0/1.1], n=3, w=3/8
    gf = (3 / 1.1 + 2 + 0) / 3 / 1.2
    assert base[1].attack == pytest.approx(3 / 8 * gf + 5 / 8)


def test_weighted_strengths_downweight_old_matches():
    ctx = CompetitionScoringContext(avg_goals_per_team_per_match=1.2, home_field_goal_boost=1.1)
    w = [0.25, 0.5, 0.75, 1.0]                       # match 0 oldest
    got = estimate_strengths(_mini(), ctx, weights=w)
    # team 1 goals-for: m0 3/1.1 (w .25), m2 2 (w .75), m3 0 (w 1.0); n stays 3
    mean = (0.25 * 3 / 1.1 + 0.75 * 2 + 1.0 * 0) / 2.0
    assert got[1].attack == pytest.approx(3 / 8 * (mean / 1.2) + 5 / 8)
    with pytest.raises(ValueError):
        estimate_strengths(_mini(), ctx, weights=[1.0])


# ---------------------------------------------------- gate rule (verbatim)

def test_gate_rule_ties_reject():
    assert sb.candidate_gate_verdict(1.0000, 0.9950, 0.005)[0] == "PASS"   # delta == bar
    assert sb.candidate_gate_verdict(1.0000, 0.9951, 0.005)[0] == "REJECT"
    assert sb.candidate_gate_verdict(1.0000, 1.0000, 0.005)[0] == "REJECT"  # a tie
    assert sb.candidate_gate_verdict(1.0000, 1.0100, 0.005)[0] == "REJECT"


def test_compare_refuses_different_match_sets():
    a = [{"match_id": 1, "p_home": .5, "p_draw": .3, "p_away": .2, "actual": "H"}]
    b = [{"match_id": 2, "p_home": .5, "p_draw": .3, "p_away": .2, "actual": "H"}]
    assert sb.compare_candidate(a, b, 0.005)["verdict"] == "INVALID"
    assert sb.compare_candidate([], [], 0.005)["verdict"] == "INVALID"
    thin = [{"match_id": i, "p_home": .5, "p_draw": .3, "p_away": .2, "actual": "H"}
            for i in range(29)]                     # improve's floor is 30
    assert sb.compare_candidate(thin, thin, 0.005)["verdict"] == "INVALID"
    assert sb.compare_candidate(thin + [dict(thin[0], match_id=99)],
                                thin + [dict(thin[0], match_id=99)],
                                0.005)["verdict"] == "REJECT"   # n=30, a tie


# ------------------------------------------- end to end, synthetic world

@pytest.fixture(scope="module")
def world():
    """Eight clubs, two seasons, double round robin with strengths that DRIFT
    through each season (so recency carries information)."""
    init_db()
    rnd = random.Random(19)
    with session_scope() as s:
        if s.execute(select(Competition).where(Competition.code == CODE)).scalar_one_or_none():
            return CODE
        comp = Competition(sport=Sport.SOCCER, code=CODE, name="S19 test league",
                           area="Testland", type="LEAGUE")
        teams = [Team(sport=Sport.SOCCER, name=f"S19 club {i}") for i in range(8)]
        s.add(comp)
        s.add_all(teams)
        s.flush()
        ids = [t.id for t in teams]
        for si, season in enumerate(SEASONS):
            t0 = datetime(2091 + si, 8, 10, 15)
            rounds = []
            for leg in range(2):
                for rd in range(7):
                    pairs = []
                    rot = ids[:1] + ids[1:][rd:] + ids[1:][:rd]
                    for i in range(4):
                        h, a = rot[i], rot[7 - i]
                        pairs.append((h, a) if leg == 0 else (a, h))
                    rounds.append(pairs)
            for rn, pairs in enumerate(rounds):
                day = t0 + timedelta(days=18 * rn)
                frac = rn / len(rounds)
                for h, a in pairs:
                    # club quality drifts linearly across the season
                    qh = 1.0 + 0.5 * (ids.index(h) / 7 - 0.5) * (1 - 2 * frac)
                    qa = 1.0 + 0.5 * (ids.index(a) / 7 - 0.5) * (1 - 2 * frac)
                    lam_h, lam_a = 1.5 * qh / qa, 1.1 * qa / qh
                    hs = sum(1 for _ in range(10) if rnd.random() < lam_h / 10)
                    as_ = sum(1 for _ in range(10) if rnd.random() < lam_a / 10)
                    s.add(Match(sport=Sport.SOCCER, competition_id=comp.id, season=season,
                                utc_date=day, status=MatchStatus.FINISHED,
                                home_team_id=h, away_team_id=a,
                                home_score=hs, away_score=as_))
    return CODE


def test_candidate_scores_same_matches_both_metrics(world):
    kw = dict(min_prior=20, dixon_coles_rho=-0.10, elo_goal_coeff=0.0008)
    base = sb.run_soccer_backtest(world, SEASONS[0], **kw)
    cand = sb.run_soccer_backtest(world, SEASONS[0], decay_half_life_days=365.0, **kw)
    assert base and cand and len(base) == 56 - 20
    assert [r["match_id"] for r in base] == [r["match_id"] for r in cand]
    assert any(abs(b["p_home"] - c["p_home"]) > 1e-9 for b, c in zip(base, cand))
    # no-decay default is deterministic = the baseline walk, unchanged
    assert sb.run_soccer_backtest(world, SEASONS[0], **kw) == base

    r = sb.run_time_decay_comparison(world, SEASONS, min_prior=20,
                                     dixon_coles_rho=-0.10, elo_goal_coeff=0.0008)
    p = r["pooled"]
    assert p["verdict"] in ("PASS", "REJECT") and p["n"] == 2 * 36
    for k in ("prod_log_loss", "cand_log_loss", "prod_rps", "cand_rps"):
        assert 0 < p[k] < 2
    assert p["min_delta"] == 0.005
    assert p["verdict"] == ("PASS" if p["prod_log_loss"] - p["cand_log_loss"] >= 0.005
                            else "REJECT")
    assert [x["season"] for x in r["per_season"]] == list(SEASONS)


def test_missing_season_is_invalid_never_partial_pass(world):
    r = sb.run_time_decay_comparison(world, (SEASONS[0], "1900/01"), min_prior=20,
                                     dixon_coles_rho=-0.10, elo_goal_coeff=0.0008)
    assert r["pooled"]["verdict"] == "INVALID" and r["missing"] == ["1900/01"]


def _mv_snapshot():
    with session_scope() as s:
        return sorted((mv.sport.value, mv.version, mv.status, str(mv.parameters))
                      for mv in s.execute(select(ModelVersion)).scalars())


def test_cli_gate_mode_end_to_end_production_untouched(world, monkeypatch):
    import cli
    monkeypatch.setattr(sb, "S19_GATE_COMPETITION", world)
    monkeypatch.setattr(sb, "S19_GATE_SEASONS", SEASONS)
    monkeypatch.setattr(cli, "_soccer_prod_poisson", lambda: ("v22", -0.10, 0.0008))
    before = _mv_snapshot()
    out = CliRunner().invoke(cli.cli, ["soccer-backtest", "--competition", world,
                                       "--min-prior", "20", "--candidate", "time-decay"])
    assert out.exit_code == 0, out.output
    assert "POOLED" in out.output and "RPS" in out.output
    assert "not an acceptance criterion" in out.output
    gate = [ln for ln in out.output.splitlines() if ln.startswith("S19-GATE:")]
    assert len(gate) == 1 and (" PASS " in gate[0] or " REJECT " in gate[0])
    assert "production v22" in gate[0] and "bar >= 0.0050" in gate[0]
    assert _mv_snapshot() == before                  # nothing written


def test_cli_informational_mode_has_no_verdict(world, monkeypatch):
    import cli
    monkeypatch.setattr(cli, "_soccer_prod_poisson", lambda: ("v22", -0.10, 0.0008))
    out = CliRunner().invoke(cli.cli, ["soccer-backtest", "--competition", world,
                                       "--season", SEASONS[1], "--min-prior", "20",
                                       "--candidate", "time-decay"])
    assert out.exit_code == 0, out.output
    assert "S19-INFORMATIONAL" in out.output and "S19-GATE:" not in out.output


def test_cli_no_production_is_invalid(world, monkeypatch):
    import cli
    monkeypatch.setattr(cli, "_soccer_prod_poisson", lambda: None)
    out = CliRunner().invoke(cli.cli, ["soccer-backtest", "--candidate", "time-decay"])
    assert "S19-GATE: INVALID" in out.output


def test_prod_poisson_reads_stored_config(monkeypatch):
    import cli
    import src.walters.training as tr

    class _MV:
        version = "v22"
        parameters = {"poisson": {"dixon_coles_rho": -0.10, "elo_goal_coeff": 0.0008}}
    monkeypatch.setattr(tr, "_resolve_model_version", lambda s, v, sport: _MV())
    assert cli._soccer_prod_poisson() == ("v22", -0.10, 0.0008)


def test_plain_backtest_prints_rps_beside_log_loss(world, monkeypatch):
    import cli
    out = CliRunner().invoke(cli.cli, ["soccer-backtest", "--competition", world,
                                       "--season", SEASONS[0], "--min-prior", "20",
                                       "--rho", "-0.1"])
    assert out.exit_code == 0, out.output
    assert "multiclass log-loss" in out.output and "RPS (H<D<A ordered)" in out.output


def test_production_paths_do_not_decay():
    import inspect
    import src.walters.training as tr
    for fn in (tr._train_fresh_soccer, tr._generate_predictions_soccer):
        src = inspect.getsource(fn)
        assert "weights=" not in src and "decay" not in src.lower()
