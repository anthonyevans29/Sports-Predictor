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

253 item 2(a) (ARCHITECT 2026-11-04 13:20 ET, verbatim): "THE PARITY TEST'S SCOPE IS DECLARED, in its docstring, its
name and the PR body: "same inputs, shared path" — production and the walk given the SAME context, the SAME Elo state,
the SAME history and NO factor inputs produce the SAME probabilities, row for row. It pins the shared computation (Elo
update, estimate_strengths, Poisson, Dixon-Coles) and nothing else; it passes on v22 and fails on a real divergence in
that path. Nobody may read it as "production equals the walk"; the pins below say where it does not."

WHAT THIS FILE HOLDS: ONE passing parity test and FIVE strict xfails on v22 (253 item 2(c): "parity where parity is
claimed, a named pin for each place it is not"):
  (a) test_a_same_inputs_shared_path_production_equals_the_walk_with_one_context_one_elo_one_history_no_factors, over
      soccer_parity.PREDICTORS, NO mark: v22 passes on all 23 rows at 0, on (a)'s store (no prior season, no factor
      rows, unique kickoffs: the scope's precondition).
  (b) test_b_context_gap_the_walk_s_effective_context_is_production_s_stored_context, over PREDICTORS: v22 a STRICT
      xfail that only ContextGap satisfies; a successor takes no mark. Its positive control passes.
  (c) test_c_normalisation_average_teams_price_at_the_context_s_own_rates, over PREDICTORS: v22 a STRICT xfail that
      only NormalisationLean satisfies; its positive control (predict_match at the data's rates) passes.
  THE THREE LOCATED PINS (253 item 2(b)), over PREDICTORS, each on its OWN seeded store and under (a)'s comparison,
  v22 a STRICT xfail that only its own gap satisfies (any other failure is red):
      test_pin_prior_season_elo_..., EloStateGap (#788's "Elo state" row);
      test_pin_match_factors_..., FactorGap (#788's "match factors" row);
      test_pin_simultaneous_kickoffs_..., KickoffBatchingGap (a NEW ROW on #788, 253 item 2(b)); its positive control
      (the walk batched by kickoff) passes.
  Beside them: the marks pinned (only v22, only the five pins, strict, each its own failure type); receipts (the
  store's shape, (a)'s precondition, the gap's size on the default walk, 216's equations on the average row, 249's
  figures, each pin's figures); the harness's units.
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
#: The three located pins' known gaps (addendum 253 item 2(b)): v22 only. A successor takes no entry: v23's design PR
#: shows each row identical BY CONSTRUCTION (253 item 2(d)).
KNOWN_ELO_STATE_GAP = {
    P.V22.name: ("v22 on main: production trains Elo on every finished soccer match with per-team season regression; "
                 "the walk starts each competition-season at a fresh EloState (#788 Elo state; addendum 253 item 2(b))"),
}
KNOWN_FACTOR_GAP = {
    P.V22.name: ("v22 on main: production composes injury x lineup x XI into factor_adjustment; the walk passes none "
                 "(#788 match factors; addendum 253 item 2(b))"),
}
KNOWN_KICKOFF_BATCHING_GAP = {
    P.V22.name: ("v22 on main: production's instant hides every match at or after the target kickoff; the walk with "
                 "batch_same_kickoff=False updates between same-kickoff rows (a new row on #788; addendum 253 item "
                 "2(b))"),
}
#: The prior-season Elo pin's earlier season of the same competition (before SEASON).
PRIOR_SEASON = "2092/93"
#: The located pins' figures on v22 (2026-11-04, Python 3.12.3; receipts, each pin's docstring prints them).
PIN_ELO_MAX_DP = 3.481158e-02             # 23 of 23 rows, at home_elo / away_elo
PIN_FACTOR_MAX_DP = 3.486242e-02          # 7 of 23 rows, at the factor (the target's, injury x lineup)


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


def _variant(tmp_path_factory, name, seed, controls=()):
    """A located pin's OWN store (never (a)'s): seed_v22_shape_store, then `seed(ids)`; every predictor's run (and the
    controls') is computed here and the binding undone before any test reads them, so the module's other stores stay
    bound as they were. Returns (ids, what the seed returned, {paths.name: ParityRun})."""
    mp = pytest.MonkeyPatch()
    try:
        P.fresh_store(tmp_path_factory.mktemp(name) / "store.db", mp)
        ids = P.seed_v22_shape_store(CODE, SEASON)
        seeded = seed(ids)
        runs = {paths.name: P.run_parity(paths, CODE, SEASON) for paths in P.PREDICTORS + tuple(controls)}
        from sqlalchemy import select
        from src.db.database import session_scope
        from src.db.schema import Injury, Match
        with session_scope() as s:                       # what the receipts read, read while the store is bound
            ms = s.execute(select(Match.id, Match.utc_date, Match.home_team_id, Match.away_team_id)).all()
            ids = {**ids, "kickoffs": {m[0]: m[1] for m in ms}, "sides": {m[0]: (m[2], m[3]) for m in ms},
                   "injury_refreshed_at": [i.refreshed_at for i in s.execute(select(Injury)).scalars()]}
    finally:
        mp.undo()
    return ids, seeded, runs


@pytest.fixture(scope="module")
def elo_world(tmp_path_factory):
    """THE PRIOR-SEASON ELO PIN's store: (a)'s store plus a prior season of the same competition (seed_prior_season)."""
    return _variant(tmp_path_factory, "parity-prior-season",
                    lambda ids: P.seed_prior_season(CODE, PRIOR_SEASON, ids["teams"]))


@pytest.fixture(scope="module")
def factor_world(tmp_path_factory):
    """THE MATCH FACTORS PIN's store: (a)'s store plus an injury row and confirmed lineups for team 1, the home side of
    the third target (seed_match_factors)."""
    return _variant(tmp_path_factory, "parity-factors",
                    lambda ids: P.seed_match_factors(ids["targets"][2], ids["teams"]))


@pytest.fixture(scope="module")
def kickoff_world(tmp_path_factory):
    """THE SIMULTANEOUS KICKOFFS PIN's store: (a)'s store with the third target moved onto the second's kickoff
    (share_kickoff; disjoint teams); its positive control's run (the walk batched by kickoff) beside it."""
    def seed(ids):
        P.share_kickoff(ids["targets"][2], ids["targets"][1])
        return (ids["targets"][1], ids["targets"][2])
    return _variant(tmp_path_factory, "parity-kickoffs", seed, controls=(P.V22_BATCHED_WALK_CONTROL,))


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
def test_a_same_inputs_shared_path_production_equals_the_walk_with_one_context_one_elo_one_history_no_factors(world,
                                                                                                             paths):
    """TEST (a), THE PARITY TEST, its scope DECLARED (addendum 253 item 2(a)): "same inputs, shared path" — production
    and the walk given the SAME context, the SAME Elo state, the SAME history and NO factor inputs produce the SAME
    probabilities, row for row.

    It pins the shared computation (Elo update, estimate_strengths, Poisson, Dixon-Coles) and nothing else; it passes
    on v22 and fails on a real divergence in that path. Nobody may read it as "production equals the walk"; the five
    pins say where it does not: (b) the context, (c) the normalisation, and the three located pins of 253 item 2(b)
    (prior-season Elo, match factors, simultaneous kickoffs).

    HOW (251 item 2(a), NO xfail): for every row the default walk scores, production at the row's instant (the real
    training, the real pricing) against the walk run with the stored context production read at that instant (the
    SAME context, injected): equal within 1e-12, row for row, AND every resolved input equal
    (`assert_same_inputs_parity`; a differing Elo, history or factor fails it, located).

    THE SCOPE'S PRECONDITION, the store it runs on (seed_v22_shape_store, kept exactly as it is): ONE season (no prior
    season, so the Elo state is the same), NO injury or lineup rows (no factor inputs) and UNIQUE kickoffs (the same
    history); test_a_the_store_meets_the_scope_s_precondition checks it. The pins seed each of those on their own
    stores."""
    ids, run = world
    r = run(paths)
    print("\n" + r.parity.table())
    print(f"INJECTED contexts: {len(set(r.injected.values()))} distinct over {len(r.injected)} rows; average row "
          f"{ids['average_row']}: g/b {'/'.join(f'{x:.6f}' for x in r.injected.get(ids['average_row'], ()))}")
    P.assert_same_inputs_parity(r.parity)
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


def test_a_the_store_meets_the_scope_s_precondition(world):
    """(a)'s scope's precondition on its store (253 item 2(a)): one season of the competition (no prior season), no
    injury or lineup rows (no factor inputs), every kickoff unique (no simultaneous kickoffs), so the report's
    same-kickoff set is empty."""
    from sqlalchemy import func, select
    from src.db.database import session_scope
    from src.db.schema import Injury, Lineup, Match
    ids, run = world
    with session_scope() as s:
        seasons = set(s.execute(select(Match.season)).scalars())
        kicks = list(s.execute(select(Match.utc_date)).scalars())
        n_inj = s.execute(select(func.count()).select_from(Injury)).scalar_one()
        n_lu = s.execute(select(func.count()).select_from(Lineup)).scalar_one()
    assert seasons == {SEASON} and len(kicks) == 63 and len(set(kicks)) == 63
    assert n_inj == n_lu == 0
    assert run(P.V22).parity.same_kickoff == frozenset()


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


# ------------------------------------------------- the three located pins --
# ARCHITECT 2026-11-04 13:20 ET, addendum 253 item 2(b): "THREE MORE STRICT-XFAIL PINS, one per finding, each SEEDED so
# the gap shows, each red (xpass) the day its gap closes, each carrying in its docstring the probe's figures (rows
# affected, the size of the gap, the cause by file and line) and the #788 row it pins". Each runs (a)'s comparison
# (assert_same_inputs_parity) on its own store; v22's strict xfail accepts its own gap only.

def _pin_figures(report):
    failing = [r for r in report.rows if not r.ok or r.differing]
    dps = [r.max_abs_diff for r in report.rows if r.max_abs_diff is not None]
    where = sorted(set().union(*(r.differing for r in failing))) if failing else []
    return failing, max(dps) if dps else None, where


def _print_pin(label, report):
    """Prints a pin's table and its one-line figures; never raises on them. With no row carrying a numeric max |dp|
    (every row malformed), the figure prints as "-": a crash here would hide the ParityFailure the pin then raises
    (Codex on #828: the same bug class as ParityReport.table()'s)."""
    failing, worst, where = _pin_figures(report)
    print("\n" + report.table())
    print(f"PIN {label}: {len(failing)} of {len(report.rows)} rows differ; outside 1e-12 on H/D/A "
          f"{len(report.failing)}; max |dp| {'-' if worst is None else f'{worst:.3e}'}; differs at "
          f"{', '.join(where) or 'none'}; located "
          f"{getattr(P.located_gap(report), '__name__', 'none (passes)')}")


@pytest.mark.parametrize("paths", _params(KNOWN_ELO_STATE_GAP, P.EloStateGap))
def test_pin_prior_season_elo_production_equals_the_walk_on_a_two_season_store(elo_world, paths):
    """THE PRIOR-SEASON ELO PIN (addendum 253 item 2(b); #788's "Elo state" row), (a)'s comparison on a store with
    TWO seasons: (a)'s store plus a prior season of the same competition (PRIOR_SEASON, 60 FINISHED, the lower-numbered
    team winning every one 2-1: an Elo ladder; soccer_parity.seed_prior_season). A STRICT xfail on v22 that only
    EloStateGap satisfies; it turns red (xpass) the day production and the walk carry the same Elo state across the
    season boundary.

    THE FIGURES (v22, this store, Python 3.12.3): 23 of 23 rows differ, all 23 outside 1e-12; max |dp| 3.481e-02;
    located at home_elo and away_elo alone (history, factor and the injected context equal). The #828 probe's case A
    (a prior season of its own seeding) measured 23 / 23 at 4.685e-02, located at the same two inputs; the size
    follows the seeded ladder, the rows and the location do not.

    THE CAUSE, both paths:
      * production: src/walters/training.py:152 `_load_finished_matches` (every FINISHED soccer match, every season and
        competition), :177 the Elo stream's season key `<code>:<season>`, :182 `train_elo(...)`, which regresses each
        team toward the mean when its own season changes (src/models/elo.py:199-201, `regress_team` at :136): the
        regressed prior-season Elo is carried into season two;
      * the walk: src/walters/soccer_backtest.py:194-195 (`Match.season == season`: one season only) and :212
        (`EloState(config=EloConfig())`: every team at a fresh 1500): season two starts fresh.
    """
    _, _, runs = elo_world
    r = runs[paths.name]
    _print_pin("prior-season Elo " + paths.name, r.parity)
    P.assert_same_inputs_parity(r.parity)


@pytest.mark.parametrize("paths", _params(KNOWN_FACTOR_GAP, P.FactorGap))
def test_pin_match_factors_production_equals_the_walk_with_an_injury_and_a_lineup_row(factor_world, paths):
    """THE MATCH FACTORS PIN (addendum 253 item 2(b); #788's "match factors" row), (a)'s comparison on a store with an
    injury row and a lineup row for a target fixture: (a)'s store plus, for team 1 (the home side of the third target),
    one Injury row (an Attacker, fixture_source_id None) and confirmed XIs (three earlier XIs of eleven regulars; the
    target's XI drops one regular) (soccer_parity.seed_match_factors). A STRICT xfail on v22 that only FactorGap
    satisfies; it turns red (xpass) the day both paths price the same factor inputs.

    SYNTHETIC ROWS (addendum 253 item 2(b), verbatim): "Synthetic rows in the synthetic store are allowed — 216 item 4's
    "historical injuries are never manufactured" governs a real backtest's inputs, not a test's fixtures, and the
    docstring says so."

    THE FIGURES (v22, this store, Python 3.12.3): 7 of 23 rows differ (every scored row team 1 plays), all 7 outside
    1e-12; max |dp| 3.486e-02 (the target); located at the factor alone (Elo, history and context equal). On the target
    the factor is injury x lineup, 0.94 x 0.97 = 0.9118 on team 1's side; on team 1's other six rows the injury alone
    (0.94 on its side), all six priced before the injury row's own refreshed_at. Seeded one at a time on this
    store they reproduce the #828 probe exactly: the injury alone (case B1) 7 / 23 at 2.403e-02, the lineup alone
    (case B2) 1 / 23 at 1.173e-02.

    THE CAUSE, both paths:
      * production: src/walters/training.py:569 reads EVERY Injury row (no as-of filter: the row reaches team 1's rows
        priced before its own refreshed_at), :578-586 the lineup kinds, :596-600 the starters per match, :606-627 the
        recent-XI frequency (ordered by refreshed_at, not as-of), :795 `injury_adjustment`, :799 `lineup_adjustment`,
        :858 `inj_factor.combine(lu_factor).combine(xi_factor)`, :867 `factor_adjustment=factor`;
      * the walk: src/walters/soccer_backtest.py:259-264 calls `predict_match` with no factor_adjustment: it
        reconstructs none.
    """
    _, _, runs = factor_world
    r = runs[paths.name]
    _print_pin("match factors " + paths.name, r.parity)
    P.assert_same_inputs_parity(r.parity)


@pytest.mark.parametrize("paths", _params(KNOWN_KICKOFF_BATCHING_GAP, P.KickoffBatchingGap))
def test_pin_simultaneous_kickoffs_production_equals_the_walk_on_a_shared_kickoff(kickoff_world, paths):
    """THE SIMULTANEOUS KICKOFFS PIN (addendum 253 item 2(b); a NEW ROW on #788 per addendum 253 item 2(b)), (a)'s
    comparison on a store where a pair of fixtures shares a kickoff after min_prior: (a)'s store with the third target
    (teams 1 v 4) moved onto the second's kickoff (teams 3 v 5; disjoint teams, a real calendar's shape;
    soccer_parity.share_kickoff), the walk at its default batch_same_kickoff=False, as the gate runs it. A STRICT
    xfail on v22 that only KickoffBatchingGap satisfies; it turns red (xpass) the day both paths price a shared
    kickoff from the same state. Its positive control (the walk batched by kickoff) passes.

    THE FIGURES (v22, this store, Python 3.12.3): 1 of 23 rows differs (the second row of the pair), 0 outside 1e-12;
    max |dp| 0.000e+00; located at the history on that row (the walk's prior holds the first row of the pair,
    production's does not). The probabilities stay equal because the teams are disjoint and the context is injected;
    the differing-input half of (a)'s comparison fails, and that is the gap. The probe's case C1 measured the same:
    0 rows outside 1e-12, |dp| 0, history on row 63.

    THE CAUSE, both paths:
      * production: tests/soccer_parity.py:716, `at_instant`'s `Match.utc_date >= kick`, hides every match at or after
        the target kickoff, the instant production's training reads (src/walters/training.py:152 reads what is
        FINISHED): both rows of the pair are priced from the same state;
      * the walk: src/walters/soccer_backtest.py:228-236 (batch_same_kickoff False: one row per group) and :294-302
        (Elo and the prior updated after each group): the first row of the pair is in the second's prior. The
        harness's v22_walk passes no batch_same_kickoff (tests/soccer_parity.py:882, as soccer-backtest's plain report
        calls the walk).
    """
    _, _, runs = kickoff_world
    r = runs[paths.name]
    _print_pin("simultaneous kickoffs " + paths.name, r.parity)
    P.assert_same_inputs_parity(r.parity)


def test_pin_prior_season_elo_v22_s_figures_a_receipt(elo_world):
    """What the prior-season Elo pin's xfail stands on, on v22 (a receipt): located at the Elo ratings alone."""
    _, prior, runs = elo_world
    r = runs[P.V22.name].parity
    failing, worst, where = _pin_figures(r)
    _print_pin("prior-season Elo receipt", r)
    assert len(prior) == 60 and len(r.rows) == 23
    assert P.located_gap(r) is P.EloStateGap
    with pytest.raises(P.EloStateGap):
        P.assert_same_inputs_parity(r)
    assert len(failing) == len(r.failing) == 23
    assert set(where) == P.ELO_KEYS
    for row in r.rows:
        p, w = row.production.inputs, row.walk.inputs
        assert p["history"] == w["history"] and p["factor"] == w["factor"] == (1.0, 1.0)
        assert (p["forecast_g"], p["forecast_b"]) == (w["forecast_g"], w["forecast_b"])
    first = r.rows[0]
    print(f"ELO RECEIPT: max |dp| {worst:.6e}; first row {first.match_id}: production Elo "
          f"{first.production.inputs['home_elo']:.3f}/{first.production.inputs['away_elo']:.3f}, the walk's "
          f"{first.walk.inputs['home_elo']:.3f}/{first.walk.inputs['away_elo']:.3f}")
    assert worst == pytest.approx(PIN_ELO_MAX_DP, abs=1e-8)


def test_pin_match_factors_v22_s_figures_a_receipt(factor_world):
    """What the match factors pin's xfail stands on, on v22 (a receipt): located at the factor alone, on every scored
    row team 1 plays and no other; the XIs' own matches are never scored; the target carries injury x lineup, the other
    six the injury alone, every one of them priced before the injury row's refreshed_at (production's read is not
    as-of)."""
    ids, seeded, runs = factor_world
    r = runs[P.V22.name].parity
    failing, worst, where = _pin_figures(r)
    _print_pin("match factors receipt", r)
    assert P.located_gap(r) is P.FactorGap
    with pytest.raises(P.FactorGap):
        P.assert_same_inputs_parity(r)
    assert where == ["factor"] and not set(seeded["xi_matches"]) & {row.match_id for row in r.rows}
    team = ids["teams"][P.FACTOR_TEAM]
    assert {row.match_id for row in failing} == {row.match_id for row in r.rows if team in ids["sides"][row.match_id]}
    assert len(failing) == len(r.failing) == 7
    for row in failing:
        p, w = row.production.inputs, row.walk.inputs
        assert w["factor"] == (1.0, 1.0) and p["home_elo"] == w["home_elo"] and p["history"] == w["history"]
    target = r.row(seeded["target"])
    assert target.production.inputs["factor"] == pytest.approx((0.94 * 0.97, 1.0), abs=1e-12)
    others = [row for row in failing if row.match_id != target.match_id]
    (refreshed,) = ids["injury_refreshed_at"]
    for row in others:
        home, _ = ids["sides"][row.match_id]
        assert row.production.inputs["factor"] == ((0.94, 1.0) if home == team else (1.0, 0.94))
        assert ids["kickoffs"][row.match_id] < refreshed
    print(f"FACTOR RECEIPT: {len(failing)} rows; max |dp| {worst:.6e}; target {target.match_id} factor "
          f"{target.production.inputs['factor']} |dp| {target.max_abs_diff:.6e}; {len(others)} other rows at 0.94, "
          f"all before the injury's refreshed_at {refreshed}")
    assert worst == target.max_abs_diff == pytest.approx(PIN_FACTOR_MAX_DP, abs=1e-8)


def test_pin_simultaneous_kickoffs_v22_s_figures_a_receipt(kickoff_world):
    """What the simultaneous kickoffs pin's xfail stands on, on v22 (a receipt): the second row of the pair differs at
    the history alone with |dp| 0; the pair is the report's only same-kickoff rows."""
    ids, pair, runs = kickoff_world
    r = runs[P.V22.name].parity
    failing, worst, where = _pin_figures(r)
    _print_pin("simultaneous kickoffs receipt", r)
    assert r.same_kickoff == frozenset(pair) and len(r.rows) == 23
    assert P.located_gap(r) is P.KickoffBatchingGap
    with pytest.raises(P.KickoffBatchingGap):
        P.assert_same_inputs_parity(r)
    assert [row.match_id for row in failing] == [pair[1]] and where == ["history"]
    assert r.passed and worst == 0.0                     # the probabilities equal; the inputs do not
    from collections import Counter
    row = r.row(pair[1])
    extra = Counter(row.walk.inputs["history"]) - Counter(row.production.inputs["history"])
    assert not Counter(row.production.inputs["history"]) - Counter(row.walk.inputs["history"])
    (only,) = extra.elements()                           # the walk holds exactly one more result: the pair's first
    sides = ids["sides"][pair[0]]
    assert only[:2] == sides and not set(sides) & set(ids["sides"][pair[1]])   # disjoint teams
    assert ids["kickoffs"][pair[0]] == ids["kickoffs"][pair[1]]
    print(f"KICKOFF RECEIPT: row {pair[1]}'s walk history holds {only} (row {pair[0]}, same kickoff "
          f"{ids['kickoffs'][pair[0]]}); production's does not; |dp| {row.max_abs_diff:.3e}")


#: The causes the three pins cite by file:line (their docstrings), each with text the cited line holds.
PIN_CITATIONS = (
    ("src/walters/training.py", 152, "finished = _load_finished_matches(s, sport)"),
    ("src/walters/training.py", 177, 'season=f"{m.competition.code}:{m.season}"'),
    ("src/walters/training.py", 182, "elo_state_league = train_elo(_to_train(league_matches))"),
    ("src/models/elo.py", 136, "def regress_team("),
    ("src/models/elo.py", 201, "regress_team(state, tid)"),
    ("src/walters/soccer_backtest.py", 195, "q = q.where(Match.season == season)"),
    ("src/walters/soccer_backtest.py", 212, "elo = EloState(config=EloConfig())"),
    ("src/walters/training.py", 569, "for inj in s.execute(select(Injury)).scalars():"),
    ("src/walters/training.py", 579, "select(Lineup.match_id, Lineup.team_id, Lineup.kind).distinct()"),
    ("src/walters/training.py", 597, "select(Lineup).where(Lineup.is_starter == True"),
    ("src/walters/training.py", 606, "for team_id in upcoming_team_ids:"),
    ("src/walters/training.py", 614, ".order_by(Lineup.refreshed_at.desc())"),
    ("src/walters/training.py", 795, "inj_factor = injury_adjustment("),
    ("src/walters/training.py", 799, "lu_factor = lineup_adjustment("),
    ("src/walters/training.py", 858, "factor = inj_factor.combine(lu_factor).combine(xi_factor)"),
    ("src/walters/training.py", 867, "factor_adjustment=factor,"),
    ("src/walters/soccer_backtest.py", 259, "pred = predict_match("),
    ("src/walters/soccer_backtest.py", 264, ")"),
    ("src/walters/soccer_backtest.py", 228, "if batch_same_kickoff:"),
    ("src/walters/soccer_backtest.py", 236, "groups = [[m] for m in matches]"),
    ("src/walters/soccer_backtest.py", 295, "# --- AFTER predicting, update Elo + add to prior"),
    ("src/walters/soccer_backtest.py", 302, "prior.append(m)"),
    ("tests/soccer_parity.py", 716, "Match.utc_date >= kick"),
    ("tests/soccer_parity.py", 882, "results = sb.run_soccer_backtest(code, season, WALK_MIN_PRIOR"),
)


def test_the_pins_cite_the_lines_that_hold_their_causes():
    """Every file:line the three located pins cite holds the code it names (read-before-edit: a moved line fails here,
    and the pin's docstring is corrected with it)."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    docs = " ".join(" ".join(t.__doc__.split()) for t, _, _ in PINS[2:])
    spans = [(int(a), int(b or a)) for a, b in re.findall(r":(\d+)(?:-(\d+))?", docs)]
    for path, line, text in PIN_CITATIONS:
        held = (root / path).read_text().splitlines()[line - 1]
        assert text in held, (path, line, held)
        assert any(a <= line <= b for a, b in spans), (path, line)      # a cited line, or inside a cited range


def test_pin_simultaneous_kickoffs_positive_control_the_walk_batched_by_kickoff_passes(kickoff_world):
    """The simultaneous kickoffs pin's positive control: on the same store, v22's production against the walk with
    batch_same_kickoff=True (soccer_backtest.py:228-234, every fixture sharing a kickoff predicted from the same state)
    passes (a)'s comparison on every row. The pin is the batching, nothing else."""
    _, pair, runs = kickoff_world
    r = runs[P.V22_BATCHED_WALK_CONTROL.name].parity
    _print_pin("simultaneous kickoffs control", r)
    assert len(r.rows) == 23 and r.same_kickoff == frozenset(pair)
    P.assert_same_inputs_parity(r)


# ---------------------------------------------------------------- marks --

#: The five pins (253 item 2(c): "ONE passing parity test and FIVE strict xfails"): (test, its known table, the one
#: failure type its strict xfail on v22 accepts).
PINS = (
    (test_b_context_gap_the_walk_s_effective_context_is_production_s_stored_context, KNOWN_CONTEXT_GAP, P.ContextGap),
    (test_c_normalisation_average_teams_price_at_the_context_s_own_rates, KNOWN_NORMALISATION_LEAN,
     P.NormalisationLean),
    (test_pin_prior_season_elo_production_equals_the_walk_on_a_two_season_store, KNOWN_ELO_STATE_GAP, P.EloStateGap),
    (test_pin_match_factors_production_equals_the_walk_with_an_injury_and_a_lineup_row, KNOWN_FACTOR_GAP, P.FactorGap),
    (test_pin_simultaneous_kickoffs_production_equals_the_walk_on_a_shared_kickoff, KNOWN_KICKOFF_BATCHING_GAP,
     P.KickoffBatchingGap),
)


def test_the_marks_only_v22_only_the_five_pins_strict_on_their_own_failure_types():
    """(a) carries no mark for any predictor (251 item 2: an xfail over the whole parity test would blind it). The five
    pins ((b), (c) and the three located pins of 253 item 2(b)) mark v22 only, strict (an XPASS is a CI failure), each
    satisfied only by its own failure type: no pin's type is another's, or a subclass of another's, so any other
    failure is red. A successor carries no mark."""
    assert P.PREDICTORS[0] is P.V22
    assert all(set(known) == {P.V22.name} for _, known, _ in PINS)
    assert all(not p.marks for p in _params({}, None))
    for test, known, raises in PINS:
        params = {p.values[0].name: p.marks for p in _params(known, raises)}
        (mark,) = params[P.V22.name]
        assert mark.name == "xfail" and mark.kwargs["strict"] is True and mark.kwargs["raises"] is raises
        assert all(not marks for name, marks in params.items() if name != P.V22.name)
        (decorated,) = [m for m in test.pytestmark if m.name == "parametrize"]
        assert [p.marks for p in decorated.args[1]] == [p.marks for p in _params(known, raises)], test.__name__
    types = [raises for _, _, raises in PINS]
    assert len(set(types)) == 5
    for a in types:
        assert issubclass(a, AssertionError)
        for b in types:
            assert a is b or not issubclass(a, b), (a, b)
    for gap in (P.EloStateGap, P.FactorGap, P.KickoffBatchingGap):     # (a)'s failures, located; ParityFailure is not
        assert issubclass(gap, P.ParityFailure) and not issubclass(P.ParityFailure, gap)
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


def test_harness_units_the_located_gaps_each_pin_accepts_its_own_failure_only():
    """(a)'s comparison (assert_same_inputs_parity) raises a located gap ONLY when every failing row is located at that
    gap's inputs alone; anything else is plain ParityFailure, which no pin's strict xfail accepts (addendum 253 item
    2(b): each pin its own failure type)."""
    good = (0.5, 0.3, 0.2)

    def report(prod_inputs, walk_inputs, same=frozenset(), probs=good, n=1):
        prod = {i: _row(i, good, **prod_inputs) for i in range(1, n + 1)}
        walk = {i: _row(i, probs, **walk_inputs) for i in range(1, n + 1)}
        return P.compare("t", prod, walk, list(range(1, n + 1)), same)

    hist = ((1, 2, 2, 1),)
    cases = (
        (report({}, {}), None),
        (report({"home_elo": 1510.0}, {}, probs=(0.49, 0.3, 0.21)), P.EloStateGap),
        (report({"home_elo": 1510.0, "away_elo": 1490.0}, {}), P.EloStateGap),
        (report({"factor": (0.94, 1.0)}, {}, probs=(0.48, 0.3, 0.22)), P.FactorGap),
        (report({}, {"history": hist}, same=frozenset({1})), P.KickoffBatchingGap),
        (report({}, {"history": hist}), P.ParityFailure),                       # its own kickoff: not this pin
        (report({}, {"history": hist}, same=frozenset({1}), n=2), P.ParityFailure),  # row 2 not shared
        (report({"home_elo": 1510.0, "factor": (0.94, 1.0)}, {}), P.ParityFailure),  # two gaps at once
        (report({"home_elo": 1510.0}, {"history": hist}, same=frozenset({1})), P.ParityFailure),
        (report({"deflation_g": 1.4}, {}), P.ParityFailure),                    # the context: (b)'s, not a pin here
        (report({}, {}, probs=(0.5 + 1e-9, 0.3, 0.2 - 1e-9)), P.ParityFailure),  # outside 1e-12, no input differs
        (P.compare("t", {1: _row(1, good)}, {}, [1]), P.ParityFailure),         # missing
        (P.compare("t", {}, {}, []), P.ParityFailure),                          # no rows
    )
    for i, (r, expected) in enumerate(cases):
        assert P.located_gap(r) is expected, (i, P.located_gap(r), expected)
        if expected is None:
            P.assert_same_inputs_parity(r)
            continue
        with pytest.raises(AssertionError) as caught:
            P.assert_same_inputs_parity(r)
        assert type(caught.value) is expected, (i, type(caught.value))
        for gap in (P.EloStateGap, P.FactorGap, P.KickoffBatchingGap):         # only its own pin's xfail takes it
            assert isinstance(caught.value, gap) is (gap is expected), (i, gap)


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


def test_harness_units_a_malformed_probability_vector_fails_its_row():
    """Codex on #828, round 1: compare() zips the two vectors, so a short or long vector (or a NaN leg, which max()
    skips past) once passed at a difference of 0. Exactly three finite legs on both paths, or the row fails, named.
    Review on round 1: the table that names the row must not crash on the vector it names (a None vector or a
    non-numeric leg once raised TypeError / ValueError out of report.table(), hiding the ParityFailure): a vector is
    formatted leg by leg only when every leg is a finite number, else printed as its repr."""
    import re
    nan, inf, good = float("nan"), float("inf"), (0.5, 0.3, 0.2)
    for prod, walk, why in (((0.5, 0.3), good, "production has 2 legs, not 3"),
                            (good, (0.5, 0.3), "walk has 2 legs, not 3"),
                            ((0.5, 0.3), (0.5, 0.3), "production has 2 legs, not 3"),
                            ((0.5, 0.3, 0.2, 0.0), good, "production has 4 legs, not 3"),
                            ((), good, "production has 0 legs, not 3"),
                            ((0.5, nan, 0.2), good, "production has a non-finite leg"),
                            (good, (0.5, 0.3, inf), "walk has a non-finite leg"),
                            (None, good, "production has not a vector (NoneType)"),
                            (good, None, "walk has not a vector (NoneType)"),
                            ((0.5, "0.3", 0.2), good, "production has a non-numeric leg"),
                            (good, (0.5, None, 0.2), "walk has a non-numeric leg")):
        report = P.compare("t", {7: _row(7, prod)}, {7: _row(7, walk)}, [7])
        assert not report.passed, (prod, walk)
        assert report.rows[0].max_abs_diff is None and any(why in d for d in report.rows[0].differing), (prod, walk)
        table = report.table()                                   # never raises on the vector it names
        if why.endswith(("(NoneType)", "a non-numeric leg", "a non-finite leg")):
            assert repr(prod if why.startswith("production") else walk) in table, (prod, walk)
        with pytest.raises(P.ParityFailure, match=re.escape(why)):
            P.assert_parity(report)
        with pytest.raises(P.ParityFailure, match=re.escape(why)):
            P.assert_same_inputs_parity(report)
        assert P.located_gap(report) is P.ParityFailure          # a malformed row is never a located gap
    assert P.compare("t", {7: _row(7, list(good))}, {7: _row(7, good)}, [7]).passed   # three finite legs, any sequence


def test_harness_units_a_pin_s_print_never_hides_the_parity_failure_on_an_all_malformed_report(capsys):
    """Codex on #828: _print_pin once formatted max |dp| with :.3e before the pin asserted anything; on a report with
    no numeric max |dp| (every row malformed) that raised TypeError and hid the located ParityFailure. It prints "-"
    and the pin's comparison then raises the ParityFailure, named."""
    good = (0.5, 0.3, 0.2)
    report = P.compare("t", {7: _row(7, (0.5, 0.3)), 8: _row(8, None)}, {7: _row(7, good), 8: _row(8, good)}, [7, 8])
    assert _pin_figures(report)[1] is None
    _print_pin("all-malformed", report)                          # never raises
    assert "max |dp| -;" in capsys.readouterr().out
    with pytest.raises(P.ParityFailure, match="production has 2 legs, not 3") as caught:
        P.assert_same_inputs_parity(report)
    assert type(caught.value) is P.ParityFailure                 # not a located gap any pin's xfail accepts


def test_harness_units_a_non_finite_normalisation_is_a_hard_failure_not_the_known_lean():
    """Codex on #828, round 1: NaN compares false, so a NaN figure once passed (c); an infinity raised
    NormalisationLean, which v22's strict xfail (raises=NormalisationLean) would swallow. A non-finite figure raises
    NonFiniteNormalisation, which is not a NormalisationLean: pytest's xfail fails any exception that is not an
    instance of its `raises`, so a NaN from v22 or from a successor is red."""
    nan, inf = float("nan"), float("inf")
    for home, away in ((nan, 1.2), (1.8, nan), (inf, 1.2), (1.8, inf), (nan, nan)):
        n = P.normalisation(lambda g, b, h=home, a=away: {"home": h, "away": a}, 1.5, 1.2)
        with pytest.raises(AssertionError) as caught:
            P.assert_self_consistent("t", n)
        assert type(caught.value).__name__ == "NonFiniteNormalisation", (home, away, type(caught.value))
        assert not isinstance(caught.value, P.NormalisationLean)
    (mark,) = [p.marks for p in _params(KNOWN_NORMALISATION_LEAN, P.NormalisationLean)
               if p.values[0].name == P.V22.name][0]
    assert not issubclass(P.NonFiniteNormalisation, mark.kwargs["raises"])
    assert issubclass(P.NonFiniteNormalisation, AssertionError)


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
