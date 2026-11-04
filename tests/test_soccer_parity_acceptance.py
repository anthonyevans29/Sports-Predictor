"""THE SOCCER BACKTEST/PRODUCTION ACCEPTANCE SET: THREE TESTS (ARCHITECT 2026-11-04 11:50 ET, addendum 251 item 2;
addendum 249 item 1; addendum 248 item 2(a); addendum 230 item 1(e); the lane #789; #782's option A). Read-only
acceptance machinery, gate-class by what it guards: no model, constant or bar changes here. The harness is
tests/soccer_parity.py; the spec docs/specs/soccer-parity-acceptance.md. The walk's optional `context` keyword (the one
production-code change, default path byte-identical) is pinned by tests/test_soccer_backtest_default_golden.py.

251 item 2, the three tests (verbatim, abridged to the tests; the spec quotes the item whole): "(a) THE PARITY TEST,
with the context INJECTED: ... the test passes production's stored context to the walk and asserts production == the
walk, row for row, on the synthetic store. It PASSES on v22 (the shared path — Elo, estimate_strengths, Poisson,
Dixon-Coles — reproduces its gate) and fails the day a real divergence appears. No xfail. (b) THE CONTEXT-GAP PIN,
strict xfail on v22: the walk's effective context on a competition equals production's stored context for it. It turns
red (xpass) the day the two paths agree, which is the successor's obligation, and it carries the leak reason in its
docstring so nobody "fixes" it by reading the stored context into the walk. (c) THE NORMALISATION PIN, 249 item 1(b),
unchanged: strict xfail on v22 with its positive control."

WHAT THIS FILE HOLDS:
  (a) test_a_parity_production_equals_the_walk_with_production_s_context_injected, over soccer_parity.PREDICTORS, NO
      mark: v22 passes on all 23 rows at 0.
  (b) test_b_context_gap_the_walk_s_effective_context_is_production_s_stored_context, over PREDICTORS: v22 a STRICT
      xfail that only ContextGap satisfies; a successor takes no mark. Its positive control passes.
  (c) test_c_normalisation_average_teams_price_at_the_context_s_own_rates, over PREDICTORS: v22 a STRICT xfail that
      only NormalisationLean satisfies; its positive control (predict_match at the data's rates) passes.
  Beside them: the marks pinned (only v22, only (b) and (c), strict, the specific failure type); receipts (the store's
  shape, the gap's size on the default walk, 216's equations on the average row, 249's figures); the harness's units.
"""
from __future__ import annotations

import math

import pytest

import soccer_parity as P

CODE, SEASON = "PRQ", "2093/94"
W = 20 / 25                                  # n/(n+5) at n = 20 games per team (poisson.py's shrinkage)
G, B = 1.5, 1.2                              # the store's g and the data's home factor b
G0, B0 = 1.4, 1.15                           # the walk's default context: CompetitionScoringContext()'s
DATA_HOME, DATA_AWAY = 1.8, 1.2              # every team's home and away mean on the 60

#: v22's console on this store (2026-11-04, Python 3.12.3), the DEFAULT walk against production (the gap's size, a
#: receipt): the average row (match 61) and the worst row.
V22_AVERAGE_ROW_MAX_DP = 1.599069e-02
V22_WORST_ROW_MAX_DP = 2.886209e-02
V22_AVERAGE_PROD_PROBS = (0.419343, 0.274633, 0.306024)
V22_AVERAGE_WALK_PROBS = (0.411349, 0.266636, 0.322015)

#: Test (b)'s known gap: v22 only (addendum 251 item 2: v22 does not change; its recorded gate figure STANDS). A
#: successor never takes an entry here: v23's design PR states how its harness and its production path define g and b
#: identically.
KNOWN_CONTEXT_GAP = {
    P.V22.name: ("v22 on main: the gate's walk scores under the default context (1.4 / 1.15); production runs the "
                 "trained one; neither is as-of (addendum 251 item 2; Refs #789, #786). Never fixed by reading the "
                 "stored context into the walk (option 2, REJECTED by addendum 251 item 2)"),
}
#: Test (c)'s known lean: v22 only (addendum 216 item 1; 249 item 1(b)). v22 does not change.
KNOWN_NORMALISATION_LEAN = {
    P.V22.name: ("v22 on main: 216's lean, estimate_strengths deflates home goals by b and divides by the undeflated g "
                 "(addendum 249 item 1(b); Refs #786); v22 does not change"),
}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    P.fresh_store(tmp_path_factory.mktemp("soccer-parity") / "store.db", mp)
    ids = P.seed_v22_shape_store(CODE, SEASON)
    cache = {}

    def run(paths):
        if paths.name not in cache:
            cache[paths.name] = P.run_parity(paths, CODE, SEASON)
        return cache[paths.name]

    yield ids, run
    mp.undo()


def _elo_mult(inputs) -> float:
    return math.exp(inputs["elo_goal_coeff"] * (inputs["home_elo"] - inputs["away_elo"]) / 2)


def _neutral(row):
    """The path's λ with its own Elo multiplier divided out (home / m, away · m): what it prices two equal-Elo
    average teams at."""
    m = _elo_mult(row.inputs)
    return row.xg[0] / m, row.xg[1] * m


def _params(known: dict, raises):
    return [pytest.param(paths, id=paths.name.split(" ")[0],
                         marks=([pytest.mark.xfail(strict=True, raises=raises, reason=known[paths.name])]
                                if paths.name in known else []))
            for paths in P.PREDICTORS]


# ------------------------------------------------------------------ (a) --

@pytest.mark.parametrize("paths", _params({}, None))
def test_a_parity_production_equals_the_walk_with_production_s_context_injected(world, paths):
    """TEST (a), THE PARITY TEST, the context INJECTED (251 item 2(a)), NO xfail: for every row the default walk
    scores, production at the row's instant (the real training, the real pricing) against the walk run with the
    stored context production read at that instant: equal within 1e-12, row for row, every resolved input equal. It
    PASSES on v22: the shared path (Elo, estimate_strengths, Poisson, Dixon-Coles) reproduces its gate. It fails the
    day a real replay/live divergence appears."""
    ids, run = world
    r = run(paths)
    print("\n" + r.parity.table())
    print(f"INJECTED contexts: {len(set(r.injected.values()))} distinct over {len(r.injected)} rows; average row "
          f"{ids['average_row']}: g/b {'/'.join(f'{x:.6f}' for x in r.injected.get(ids['average_row'], ()))}")
    P.assert_parity(r.parity)
    assert all(row.differing == () for row in r.parity.rows)
    for row in r.parity.rows:                     # production priced with exactly the context it stored
        p = row.production.inputs
        assert (p["deflation_g"], p["deflation_b"]) == (p["forecast_g"], p["forecast_b"]) == p["stored_context"]
        assert (row.walk.inputs["forecast_g"], row.walk.inputs["forecast_b"]) == r.injected[row.match_id]


def test_a_v22_passes_on_every_row_at_zero(world):
    """v22's figures under (a): 23 rows (the walk's min_prior 40 on 63 finished), max |dp| 0.000e+00 on every row."""
    ids, run = world
    r = run(P.V22)
    assert len(r.parity.rows) == 23 and r.parity.passed
    worst = max(row.max_abs_diff for row in r.parity.rows)
    print(f"\nV22 (a): 23 rows, max |dp| {worst:.3e}")
    assert worst == 0.0


# ------------------------------------------------------------------ (b) --

@pytest.mark.parametrize("paths", _params(KNOWN_CONTEXT_GAP, P.ContextGap))
def test_b_context_gap_the_walk_s_effective_context_is_production_s_stored_context(world, paths):
    """TEST (b), THE CONTEXT-GAP PIN (251 item 2(b)): on every row the DEFAULT walk's effective context (the g and b
    its estimate_strengths deflated with and its predict_match priced with, recorded by the spy) equals production's
    stored context for the competition at that instant. A strict xfail on v22 (raises=ContextGap): it turns red (xpass)
    the day the two paths agree, which is the successor's obligation (v23's design PR, 248 item 2(b), defines g and b
    identically in its harness and its production path).

    THE LEAK REASON (addendum 251 item 2, verbatim): "the stored context is fitted on the whole training pot — the
    same games the walk scores — so a walk that read it would leak the pot's own totals into every prior-only step".
    never fix this by reading the stored context into the walk (option 2, REJECTED by addendum 251 item 2)."""
    _, run = world
    P.assert_no_context_gap(run(paths).context_gap)


def test_b_v22_s_gap_is_the_default_context_against_training_s_on_every_row_a_receipt(world):
    """What (b)'s xfail stands on, on v22 (a receipt, not an acceptance assertion): every row's default walk deflates
    and prices with 1.4 / 1.15 while production's stored context is training's g and b at the instant; on the average
    row that is the store's own 1.5 / 1.2."""
    ids, run = world
    r = run(P.V22)
    gap = r.context_gap
    print("\n" + gap.table())
    assert len(gap.rows) == 23 and len(gap.failing) == 23
    with pytest.raises(P.ContextGap):
        P.assert_no_context_gap(gap)
    for row in gap.rows:
        assert row.walk == (G0, B0, G0, B0)
        assert row.stored[0] != G0 and row.stored[1] != B0
    avg = next(row for row in gap.rows if row.match_id == ids["average_row"])
    assert avg.stored == pytest.approx((G, B), abs=1e-12)


def test_b_the_gap_s_size_on_the_default_walk_a_receipt(world):
    """THE GAP'S SIZE (a receipt for the finding Issue; the negative control that the row comparison can fail; not
    an acceptance assertion): the DEFAULT walk against production is outside 1e-12 on all 23 rows, located at the
    scoring context alone (deflation g/b, forecast g/b); Elo, history, switches, config and factors equal. With
    production's context injected the same rows are equal at 0 (test (a))."""
    ids, run = world
    r = run(P.V22).default_parity
    print("\n" + r.table())
    assert not r.passed and len(r.rows) == 23 and len(r.failing) == 23
    for row in r.rows:
        assert row.differing == P.CONTEXT_KEYS, (row.match_id, row.differing)
        p, w = row.production.inputs, row.walk.inputs
        assert (p["rho"], p["elo_goal_coeff"]) == (w["rho"], w["elo_goal_coeff"]) == (P.V22_RHO, P.V22_ELO_GOAL_COEFF)
        assert p["home_elo"] == w["home_elo"] and p["away_elo"] == w["away_elo"]       # bit-equal, not just close
        assert p["history"] == w["history"] and p["factor"] == w["factor"] == (1.0, 1.0)
        assert row.max_abs_diff > 1e-3
    worst = max(row.max_abs_diff for row in r.rows)
    avg = r.row(ids["average_row"])
    print(f"V22 default walk, average row {avg.match_id}: production H/D/A "
          f"{'/'.join(f'{x:.6f}' for x in avg.production.probs)}; walk H/D/A "
          f"{'/'.join(f'{x:.6f}' for x in avg.walk.probs)}; max |dp| {avg.max_abs_diff:.6e}; worst row {worst:.6e}")
    assert avg.max_abs_diff == pytest.approx(V22_AVERAGE_ROW_MAX_DP, abs=1e-8)
    assert worst == pytest.approx(V22_WORST_ROW_MAX_DP, abs=1e-8)
    assert avg.production.probs == pytest.approx(V22_AVERAGE_PROD_PROBS, abs=1e-6)
    assert avg.walk.probs == pytest.approx(V22_AVERAGE_WALK_PROBS, abs=1e-6)


def test_b_positive_control_a_path_whose_contexts_agree_passes_a_and_b(world):
    """(b)'s positive control: v22's own code with its stored context set to the walk's default. The default walk's
    effective context IS production's stored context on every row: (b) passes, and (a) with it."""
    _, run = world
    r = run(P.V22_WALK_CONTEXT_CONTROL)
    print("\n" + r.context_gap.table())
    P.assert_no_context_gap(r.context_gap)
    P.assert_parity(r.parity)
    assert len(r.context_gap.rows) == len(r.parity.rows) == 23
    assert set(r.injected.values()) == {(G0, B0)}


# ------------------------------------------------------------------ (c) --

@pytest.mark.parametrize("paths", _params(KNOWN_NORMALISATION_LEAN, P.NormalisationLean))
def test_c_normalisation_average_teams_price_at_the_context_s_own_rates(paths):
    """TEST (c), THE NORMALISATION PIN (249 item 1(b), unchanged by 251 item 2(c)): on a league of average teams at a
    known g and b, two average teams at equal Elo price at the context's own total 2g and home/away ratio b/(2−b),
    within 1e-9. A strict xfail on v22 (raises=NormalisationLean): 216's lean; it turns red the day the path no longer
    leans."""
    n = P.normalisation(paths.implied)
    print("\n" + P.normalisation_line(paths.name, n))
    P.assert_self_consistent(paths.name, n)


def test_c_positive_control_a_consistent_predictor_passes():
    """(c)'s positive control: the real predict_match fed unit strengths at the data's rates prices 2g and b/(2−b)."""
    n = P.normalisation(P.data_rate_implied)
    print("\n" + P.normalisation_line(P.DATA_RATE_CONTROL, n))
    P.assert_self_consistent(P.DATA_RATE_CONTROL, n)
    assert n["model_total"] == pytest.approx(2 * P.NORMALISATION_G, abs=1e-12)


def test_c_v22_s_figures_are_249_s_a_receipt():
    """What (c)'s xfail stands on, on v22 (a receipt): the chosen g and b reproduce 249 item 1(b)'s figures to their
    printed digits (model total 2.857 vs the context's 2.981, −4.14%; ratio 1.080 vs 1.173), through the REAL
    estimate_strengths and predict_match, equal to 216's closed forms g(1+b)((3−b)/2)^2 and b."""
    g, b = P.NORMALISATION_G, P.NORMALISATION_B
    raw = P.v22_implied(g, b)
    n = P.normalisation(P.v22_implied)
    print("\n" + P.normalisation_line(P.V22.name, n))
    as_run = raw["as_run_home"] + raw["as_run_away"]
    print(f"NORMALISATION v22 detail: league context g {raw['ctx'].avg_goals_per_team_per_match:.6f} b "
          f"{raw['ctx'].home_field_goal_boost:.6f}; rating (pre-shrinkage) {raw['rating']:.6f} = (3-b)/2 "
          f"{(3 - b) / 2:.6f}; as run (n = 38) rating {raw['as_run_rating']:.6f}, total {as_run:.6f} "
          f"({(as_run / (2 * g) - 1) * 100:+.2f}%)")
    assert raw["ctx"].avg_goals_per_team_per_match == pytest.approx(g, abs=1e-12)
    assert raw["ctx"].home_field_goal_boost == pytest.approx(b, abs=1e-12)
    assert raw["rating"] == pytest.approx((3 - b) / 2, abs=1e-12)
    assert n["model_total"] == pytest.approx(g * (1 + b) * ((3 - b) / 2) ** 2, abs=1e-12)
    assert n["model_ratio"] == pytest.approx(b, abs=1e-12)
    assert f"{n['model_total']:.3f}" == "2.857" and f"{n['context_total']:.3f}" == "2.981"
    assert f"{n['deficit'] * 100:.2f}" == "-4.14"
    assert f"{n['model_ratio']:.3f}" == "1.080" and f"{n['context_ratio']:.3f}" == "1.173"
    with pytest.raises(P.NormalisationLean):
        P.assert_self_consistent(P.V22.name, n)


# ---------------------------------------------------------------- marks --

def test_the_marks_only_v22_only_b_and_c_strict_on_their_own_failure_types():
    """(a) carries no mark for any predictor (251 item 2: an xfail over the whole parity test would blind it). (b) and
    (c) mark v22 only, strict (an XPASS is a CI failure), satisfied only by ContextGap / NormalisationLean (any other
    exception is red). A successor carries no mark."""
    assert P.PREDICTORS[0] is P.V22
    assert set(KNOWN_CONTEXT_GAP) == set(KNOWN_NORMALISATION_LEAN) == {P.V22.name}
    assert all(not p.marks for p in _params({}, None))
    for known, raises in ((KNOWN_CONTEXT_GAP, P.ContextGap), (KNOWN_NORMALISATION_LEAN, P.NormalisationLean)):
        params = {p.values[0].name: p.marks for p in _params(known, raises)}
        (mark,) = params[P.V22.name]
        assert mark.name == "xfail" and mark.kwargs["strict"] is True and mark.kwargs["raises"] is raises
        assert all(not marks for name, marks in params.items() if name != P.V22.name)
    for exc in (P.ParityFailure, P.ContextGap, P.NormalisationLean):
        assert issubclass(exc, AssertionError)
    assert len({P.ParityFailure, P.ContextGap, P.NormalisationLean}) == 3
    assert not issubclass(P.ContextGap, P.ParityFailure) and not issubclass(P.NormalisationLean, P.ParityFailure)
    assert "never fix this by reading the stored context into the walk (option 2, REJECTED by addendum 251 item 2)" \
        in test_b_context_gap_the_walk_s_effective_context_is_production_s_stored_context.__doc__
    assert ("the stored context is fitted on the whole training pot — the same games the walk scores — so a walk that "
            "read it would leak the pot's own totals into every prior-only step") in " ".join(
        test_b_context_gap_the_walk_s_effective_context_is_production_s_stored_context.__doc__.split())


# ------------------------------------------------------------- receipts --

def test_the_store_is_the_finding_s_shape(world):
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import Match
    ids, _ = world
    with session_scope() as s:
        ms = list(s.execute(select(Match).where(Match.id.in_(ids["average_matches"]))).scalars())
    assert len(ms) == 60
    for t in ids["teams"]:
        home = [m.home_score for m in ms if m.home_team_id == t]
        away = [m.away_score for m in ms if m.away_team_id == t]
        assert len(home) == len(away) == 10
        assert sum(home) / 10 == pytest.approx(DATA_HOME, abs=1e-12)
        assert sum(away) / 10 == pytest.approx(DATA_AWAY, abs=1e-12)
    goals = sum(m.home_score + m.away_score for m in ms)
    assert goals / (2 * len(ms)) == pytest.approx(G, abs=1e-12)
    assert (sum(m.home_score for m in ms) / len(ms)) / G == pytest.approx(B, abs=1e-12)
    assert DATA_HOME / DATA_AWAY == pytest.approx(B / (2 - B), abs=1e-12)        # the data's ratio is b/(2−b)
    assert len(ids["targets"]) == 3 and ids["average_row"] == ids["targets"][0]


def test_the_average_row_carries_216_s_equations(world):
    """A RECEIPT (216's lean through the real code, on the store): on the average row (60 average-team matches, equal
    records) production is 216 item 1's equations at the stored 1.5 / 1.2, through the real training and the real
    pricing; the injected walk is the same row to the bit; the default walk is the same equations at 1.4 / 1.15."""
    ids, run = world
    r = run(P.V22)
    row = r.default_parity.row(ids["average_row"])
    inj = r.parity.row(ids["average_row"])
    p, w = row.production.inputs, row.walk.inputs
    assert p["deflation_g"] == pytest.approx(G, abs=1e-12) and p["deflation_b"] == pytest.approx(B, abs=1e-12)
    assert inj.walk.probs == row.production.probs and inj.walk.xg == row.production.xg
    r_pre = (3 - B) / 2
    for k in P.DERIVED_KEYS:
        assert p[k] == pytest.approx(W * r_pre + (1 - W), abs=1e-12)
    r0_pre = G * (B / B0 + 2 - B) / (2 * G0)
    for k in P.DERIVED_KEYS:
        assert w[k] == pytest.approx(W * r0_pre + (1 - W), abs=1e-12)
    rp, rw = W * r_pre + (1 - W), W * r0_pre + (1 - W)
    m = _elo_mult(p)
    assert _elo_mult(w) == m
    assert row.production.xg[0] == pytest.approx(G * B * rp * rp * m, abs=1e-12)
    assert row.production.xg[1] == pytest.approx(G * rp * rp / m, abs=1e-12)
    assert row.walk.xg[0] == pytest.approx(G0 * B0 * rw * rw * m, abs=1e-12)
    assert row.walk.xg[1] == pytest.approx(G0 * rw * rw / m, abs=1e-12)
    ph, pa = _neutral(row.production)
    pre_total = G * (1 + B) * r_pre ** 2
    assert round(pre_total, 3) == 2.673 and round((pre_total / (2 * G) - 1) * 100, 1) == -10.9
    assert ph + pa == pytest.approx(G * (1 + B) * rp * rp, abs=1e-12)
    assert ph / pa == pytest.approx(B, abs=1e-12)
    print(f"\nRECEIPT 216 on the average row: production g {p['deflation_g']:.6f} b {p['deflation_b']:.6f}, rating "
          f"{rp:.6f} (pre-shrinkage {r_pre:.6f} = (3-b)/2), equal-Elo total {ph + pa:.6f} (pre-shrinkage "
          f"g(1+b)((3-b)/2)^2 = {pre_total:.6f}), ratio {ph / pa:.6f} vs the data's "
          f"{DATA_HOME / DATA_AWAY:.6f} = b/(2-b); the injected walk equal to the bit")


# ---------------------------------------------------------------- units --

def _row(mid, probs, **inputs):
    base = {k: 0.0 for k in P.LOCATION_KEYS}
    base.update(history=(), weighted=False, strength_prior=False, max_goals=10, factor=(1.0, 1.0))
    base.update(inputs)
    return P.PathRow(mid, probs, (1.0, 1.0), base)


def test_harness_units_tolerance_missing_rows_and_the_location():
    a = _row(1, (0.5, 0.3, 0.2))
    assert P.compare("t", {1: a}, {1: _row(1, (0.5 + 1e-13, 0.3, 0.2 - 1e-13))}, [1]).passed
    off = P.compare("t", {1: a}, {1: _row(1, (0.5 + 1e-9, 0.3, 0.2 - 1e-9))}, [1])
    assert not off.passed and off.rows[0].differing == ()       # outputs differ, no recorded input does
    miss = P.compare("t", {1: a, 2: a}, {1: a}, [1, 2])
    assert not miss.passed and miss.rows[1].differing == ("missing: walk",)
    assert not P.compare("t", {}, {}, []).passed                # an empty report never passes
    elo = P.compare("t", {1: _row(1, (0.5, 0.3, 0.2), home_elo=1510.0)}, {1: _row(1, (0.6, 0.2, 0.2))}, [1])
    assert elo.rows[0].differing == ("home_elo",)
    absent = dict(a.inputs)
    del absent["history"]
    assert "history" in P.differing_inputs(a.inputs, absent)    # an unreported input is a difference
    with pytest.raises(P.ParityFailure):
        P.assert_parity(off)


def test_harness_units_the_context_gap():
    ctx = dict(deflation_g=1.5, deflation_b=1.2, forecast_g=1.5, forecast_b=1.2)
    prod = _row(1, (0.5, 0.3, 0.2), stored_context=(1.5, 1.2))
    assert P.context_gap("t", {1: prod}, {1: _row(1, (0.5, 0.3, 0.2), **ctx)}, [1]).passed
    for k in P.CONTEXT_KEYS:                                     # any one of the four off -> a gap
        off = P.context_gap("t", {1: prod}, {1: _row(1, (0.5, 0.3, 0.2), **{**ctx, k: ctx[k] + 1e-9})}, [1])
        assert not off.passed
        with pytest.raises(P.ContextGap):
            P.assert_no_context_gap(off)
    assert P.context_gap("t", {1: prod}, {1: _row(1, (0.5, 0.3, 0.2), **{**ctx, "forecast_b": 1.2 + 1e-13})},
                         [1]).passed                             # within the tolerance
    assert not P.context_gap("t", {1: _row(1, (0.5, 0.3, 0.2))}, {1: _row(1, (0.5, 0.3, 0.2), **ctx)}, [1]).passed
    assert not P.context_gap("t", {1: prod}, {}, [1]).passed     # a missing row is a gap
    assert not P.context_gap("t", {}, {}, []).passed             # an empty report never passes


def test_harness_units_the_normalisation():
    ok = P.normalisation(lambda g, b: {"home": g * b, "away": g * (2 - b)}, 1.5, 1.2)
    P.assert_self_consistent("t", ok)
    for home, away in ((1.5 * 1.2 + 1e-8, 1.5 * 0.8), (1.5 * 1.2, 1.5 * 0.8 - 1e-8)):
        with pytest.raises(P.NormalisationLean):
            P.assert_self_consistent("t", P.normalisation(lambda g, b, h=home, a=away: {"home": h, "away": a},
                                                          1.5, 1.2))
    league = P.average_league(1.5, 1.2)
    assert len(league) == 380
    ctx = P.league_context(league)
    assert (ctx.avg_goals_per_team_per_match, ctx.home_field_goal_boost) == pytest.approx((1.5, 1.2), abs=1e-12)


def test_harness_refuses_a_store_outside_the_temp_directory():
    with pytest.raises(P.StoreRefused):
        P.require_tmp_store("/home/user/Sports-Predictor/data/sports.db")
    with pytest.raises(P.StoreRefused):
        P.require_tmp_store("")


def test_at_instant_holds_aside_every_later_soccer_match_whatever_its_competition_or_season(tmp_path, monkeypatch):
    """Production's training reads every FINISHED soccer match of every competition and season, so the instant must
    hold aside every soccer match at or after the kickoff, not only the competition-season's. Finished rows after the
    average row's kickoff, in a later season of the same competition and in another competition, change nothing in
    what production resolved at that instant (context, stored context, Elo, history, probabilities), and the store is
    restored."""
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport

    P.fresh_store(tmp_path / "instant.db", monkeypatch)
    ids = P.seed_v22_shape_store(CODE, SEASON)
    mid = ids["average_row"]
    with P.at_instant(CODE, SEASON, mid):
        before = P.v22_production(CODE, SEASON, mid)
    t = ids["teams"]
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == CODE)).scalar_one()
        other = Competition(sport=Sport.SOCCER, code="PRX", name="Parity Other", area="X", type="LEAGUE")
        s.add(other)
        s.flush()
        last = max(m.utc_date for m in s.execute(select(Match).where(Match.competition_id == comp.id)).scalars())
        later = [Match(sport=Sport.SOCCER, competition_id=comp.id, season="2094/95", utc_date=last + P.timedelta(days=300),
                       status=MatchStatus.FINISHED, home_team_id=t[0], away_team_id=t[1], home_score=7, away_score=0),
                 Match(sport=Sport.SOCCER, competition_id=other.id, season=SEASON, utc_date=last + P.timedelta(days=1),
                       status=MatchStatus.FINISHED, home_team_id=t[0], away_team_id=t[2], home_score=6, away_score=0)]
        s.add_all(later)
        s.flush()
        later_ids = [m.id for m in later]
    with P.at_instant(CODE, SEASON, mid):
        with session_scope() as s:
            assert all(s.get(Match, i).status == MatchStatus.SCHEDULED for i in later_ids)
        after = P.v22_production(CODE, SEASON, mid)
    for k in P.LOCATION_KEYS + P.DERIVED_KEYS + ("stored_context",):
        assert after.inputs[k] == before.inputs[k], k
    assert (after.inputs["deflation_g"], after.inputs["deflation_b"]) == (G, B) == after.inputs["stored_context"]
    assert not any(h in (7, 6) for (_, _, h, _) in after.inputs["history"])
    assert after.probs == before.probs and after.xg == before.xg
    with session_scope() as s:
        assert [(s.get(Match, i).status, s.get(Match, i).home_score) for i in later_ids] == [
            (MatchStatus.FINISHED, 7), (MatchStatus.FINISHED, 6)]
    with pytest.raises(AssertionError, match="is not in"):
        with P.at_instant("PRX", SEASON, mid):
            pass


def test_stored_context_reads_as_the_live_path_reads_it(world):
    """stored_context is training.py:456-459 + :514: a code with a stored context gets it; a code with none falls back
    to CompetitionScoringContext() (1.4 / 1.15), as the live path does."""
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import ModelVersion
    from src.models.poisson import CompetitionScoringContext
    with session_scope() as s:
        version = s.execute(select(ModelVersion.version).where(ModelVersion.version == P.PRODUCTION_ROW)).scalar_one()
    assert P.stored_context(version, "NOPE") == CompetitionScoringContext()
    with P.at_instant(CODE, SEASON, world[0]["average_row"]):
        row = P.v22_production(CODE, SEASON, world[0]["average_row"])
    assert P.stored_context(row.inputs["version"], CODE) == CompetitionScoringContext(
        avg_goals_per_team_per_match=row.inputs["stored_context"][0],
        home_field_goal_boost=row.inputs["stored_context"][1])
