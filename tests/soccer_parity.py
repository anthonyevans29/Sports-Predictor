"""THE SOCCER BACKTEST/PRODUCTION ACCEPTANCE HARNESS: THREE TESTS (ARCHITECT 2026-11-04 11:50 ET, addendum 251 item 2;
addendum 249 item 1; addendum 248 item 2(a); addendum 230 item 1(e); the lane #789, #782's option A). READ-ONLY
acceptance machinery: it changes no model and no constant. The one production-code change beside it is the walk's
optional `context` keyword (src/walters/soccer_backtest.py run_soccer_backtest), whose default path is byte-identical
(tests/test_soccer_backtest_default_golden.py). Not a test module: tests/test_soccer_parity_acceptance.py runs it, and a
soccer successor's tests import it (`import soccer_parity as P`, as tests/nfl_v2_world.py and tests/ledger_text.py are
imported) to run under it.

THE RULING, 251 item 2 (the three tests): "(a) THE PARITY TEST, with the context INJECTED: ... the test passes
production's stored context to the walk and asserts production == the walk, row for row, on the synthetic store. It
PASSES on v22 (the shared path — Elo, estimate_strengths, Poisson, Dixon-Coles — reproduces its gate) and fails the day
a real divergence appears. No xfail. (b) THE CONTEXT-GAP PIN, strict xfail on v22: the walk's effective context on a
competition equals production's stored context for it. ... (c) THE NORMALISATION PIN, 249 item 1(b), unchanged: strict
xfail on v22 with its positive control." (docs/specs/soccer-parity-acceptance.md quotes the item whole.)

WHAT IT COMPARES. One store, two paths, the same instant, the same match:
  * PRODUCTION (`SoccerPaths.production`): the predictor as the live chain runs it at the match's instant. For v22:
    src/walters/training.py `_train_fresh_soccer` (the real training: its per-competition g and b, its Elo) trained on
    the store as it stands at the instant, then `_generate_predictions_soccer(code, season, model_version=<that
    version>, only_match_id=<the match>)`, read back from the Prediction row it writes. The row also carries
    PRODUCTION'S STORED CONTEXT for the competition (`inputs["stored_context"]`, (g, b)), read from the ModelVersion's
    parameters exactly as the live path reads it (training.py:456-459, then training.py:514's
    `contexts.get(competition_code, CompetitionScoringContext())`).
  * THE WALK (`SoccerPaths.walk(code, season, context=None)`): the leakage-free replay. For v22:
    src/walters/soccer_backtest.py `run_soccer_backtest` exactly as `soccer-backtest`'s plain report calls it (cli.py
    soccer_backtest_cmd): min_prior 40 (the --min-prior default), dixon_coles_rho and elo_goal_coeff from the production
    row (cli._soccer_prod_poisson), detail=True for the xG. `context=None` is the gate's walk (the dataclass default,
    1.4 / 1.15, soccer_backtest.py); a context passed is the one every row of that walk is deflated and priced with.
  * THE INSTANT: the walk scores match M from the finished matches strictly before M's kickoff. Production prices what
    is SCHEDULED from what is FINISHED, and its training reads every FINISHED soccer match of every competition and
    season (training._load_finished_matches). `at_instant` puts the synthetic store where it stood at M's kickoff
    (EVERY soccer match kicking off at or after M's kickoff, whatever its competition or season, SCHEDULED, its score
    held aside), production trains and prices M, and the store is restored. The walks run on the restored store.

THE THREE TESTS (`run_parity` gathers what all three read; each has its own assertion and failure type):
  (a) THE PARITY TEST, the context INJECTED (`ParityRun.parity`, `assert_parity`, raises ParityFailure): for every row
      the default walk scores, the walk is run with production's stored context at that row's instant
      (`walk(code, season, context=<it>)`) and its row is compared with production's. CRITERION: for every row, max
      |p_prod − p_walk| over home/draw/away <= TOLERANCE (1e-12). No average: one row outside fails the report; a row
      missing from either path fails it; an empty report never passes. v22 PASSES (no xfail).
  (b) THE CONTEXT-GAP PIN (`ParityRun.context_gap`, `assert_no_context_gap`, raises ContextGap): for every row, the
      DEFAULT walk's effective context (the g and b its estimate_strengths deflated with and its predict_match priced
      with, recorded by the spy) equals production's stored context. v22 is a STRICT xfail (the walk's 1.4 / 1.15
      against training's g and b): it turns red the day the two paths agree, which is the successor's obligation. THE
      LEAK REASON (251 item 2, verbatim): "the stored context is fitted on the whole training pot — the same games the
      walk scores — so a walk that read it would leak the pot's own totals into every prior-only step". Never fix this
      by reading the stored context into the walk (option 2, REJECTED by addendum 251 item 2).
  (c) THE NORMALISATION PIN (`SoccerPaths.implied`, `normalisation`, `assert_self_consistent`, raises
      NormalisationLean): two average teams at equal Elo, fitted on a league of average teams at a known g and b,
      must price at the context's own rates: total 2g and home/away ratio b/(2−b). v22 is a STRICT xfail (216's lean:
      g(1+b)((3−b)/2)^2 and ratio b); the positive control (`DATA_RATE_CONTROL`, predict_match fed unit strengths at
      the data's rates) passes.

THE TOLERANCE, 1e-12: both paths end in the same deterministic `predict_match` in one process, so identical inputs give
identical floats; the only noise left is the last bits of a mean summed in another order (about 1e-16 on these
magnitudes). The default walk's difference from production on this store is of order 1e-2. 1e-12 sits about four
orders of magnitude above the summation noise and about ten below that difference. (The leagues' predict_as_of parity
tests use exact equality, not a tolerance.)

THE LOCATION: both paths are run with pass-through spies on the module's own `estimate_strengths` and `predict_match`
(the functions run unchanged; the spy records their arguments), so each row carries the inputs the code actually
resolved: the context the strengths were deflated and normalised with (g, b), the context the forecast priced with,
both Elo ratings, the history multiset, the weights/prior switches, the Poisson config and the match factors.
`differing_inputs` names every one that differs; the strengths are reported as derived.

THE STORE (`seed_v22_shape_store`), the v22 finding's shape (addendum 216 item 1): six teams of exactly equal record,
two double round robins (60 FINISHED matches, each team 10 at each venue); at each venue a team wins 2-1 four times and
loses 1-2 once (team h hosts team (h+1) % 6 in the 1-2), so EVERY team's home mean is 1.8 and away mean 1.2: g = 1.5,
the data's home factor b = 1.8 / 1.5 = 1.2 (inside training's [1.0, 1.30] clamp), the data's home/away ratio
1.5 = b/(2−b). Then three more fixtures, each 2-1. The first of the three (the average row, "average_row" in the
seed's ids) is priced from the 60 average-team matches alone, where 216's closed forms hold exactly. The poisson config
is v22's two stored values (rho −0.10, elo_goal_coeff 0.0008: tests/test_soccer_backtest_prod_params_138.py) on a
production row the real training inherits from. Synthetic stores only: `require_tmp_store` refuses a database outside
the system temp directory. (c) runs on its own synthetic league (`average_league`), not on this store: its g and b are
chosen (NORMALISATION_G, NORMALISATION_B) and its scores are the true means, floats a stored Match cannot hold.

HOW A SUCCESSOR RUNS UNDER IT: build a `SoccerPaths(name, production, walk, implied)`: production(code, season,
match_id) prices one SCHEDULED match at the store's current state and returns a PathRow whose inputs carry
"stored_context" (the (g, b) its production path reads for the competition); walk(code, season, context=None) returns
{match_id: PathRow} for every row it scores, a context passed being the one it deflates and prices every row with;
implied(g, b) returns the average-team forecast {"home", "away"} (equal Elo, any sample-size shrinkage undone) on
`average_league(g, b)`. Add it to PREDICTORS; the acceptance test parametrizes all three tests over PREDICTORS, and a
successor takes NO mark: v23's design PR (248 item 2(b)) states how its harness and its production path define g and b
identically, so (b) passes for it. `recording(module)` records the inputs of any path that calls a module-level
`estimate_strengths` / `predict_match`; a path that does not reports what it resolved in PathRow.inputs itself, under
the same keys where they apply. docs/specs/soccer-parity-acceptance.md.
"""
from __future__ import annotations

import random
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from unittest import mock

#: Per-row tolerance on each of p_home / p_draw / p_away (the module docstring says why 1e-12).
TOLERANCE = 1e-12

#: The walk's min_prior as soccer-backtest runs it (cli.py, `--min-prior` default 40).
WALK_MIN_PRIOR = 40

#: The inputs a row's location is read from, in the order the report names them.
LOCATION_KEYS = (
    "deflation_g", "deflation_b",        # the context estimate_strengths deflates home goals by and divides by
    "forecast_g", "forecast_b",          # the context predict_match prices with
    "home_elo", "away_elo",
    "history",                           # the multiset of prior results the strengths are fitted on
    "weighted", "strength_prior",        # estimate_strengths's weights / prior switches
    "rho", "elo_goal_coeff", "max_goals",
    "factor",                            # the (home, away) xG multipliers; None = (1.0, 1.0)
)
#: Reported beside the location, never as a location: they follow from history and the deflation context.
DERIVED_KEYS = ("home_attack", "home_defense", "away_attack", "away_defense")

#: The scoring-context inputs (#788's scoring-context row): where the DEFAULT walk differs from production on this
#: store (the context gap, test (b)). 216's lean is in how one path uses them (the deflation against the undeflated g)
#: and is common to both paths (test (c)).
CONTEXT_KEYS = ("deflation_g", "deflation_b", "forecast_g", "forecast_b")

#: Test (c)'s league: a g and b chosen so 216's closed forms reproduce 249 item 1(b)'s PL figures to their printed
#: digits (model total 2.857 vs the context's 2.981, -4.14%; ratio 1.080 vs 1.173). 251 item 2 prints PL's stored
#: context as "g ≈ 1.49, b ≈ 1.17"; 249's ratio pair puts b at 1.080 (b/(2−b) = 1.173), and this pin follows 249.
NORMALISATION_G, NORMALISATION_B = 1.4904, 1.0798
#: The average-team league (c) is fitted on: 20 teams, a double round robin (38 games a team).
AVERAGE_LEAGUE_TEAMS = 20


class ParityFailure(AssertionError):
    """Test (a)'s own failure: at least one row outside TOLERANCE (or missing, or no rows)."""


class ContextGap(AssertionError):
    """Test (b)'s own failure: on at least one row the default walk's effective context is not production's stored
    context for the competition (or a row is missing, or there are no rows)."""


class NormalisationLean(AssertionError):
    """Test (c)'s own failure: two average teams at equal Elo do not price at the context's own total 2g and
    home/away ratio b/(2−b)."""


class StoreRefused(RuntimeError):
    """The harness writes to its store (statuses at the instant, training's candidate rows, predictions): synthetic
    stores under the system temp directory only."""


# ------------------------------------------------------------------ rows --

@dataclass(frozen=True)
class PathRow:
    match_id: int
    probs: tuple                         # (p_home, p_draw, p_away)
    xg: tuple                            # (home_xg, away_xg)
    inputs: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class ParityRow:
    match_id: int
    production: PathRow | None
    walk: PathRow | None
    max_abs_diff: float | None           # over the three probabilities; None when a path has no row
    differing: tuple                     # LOCATION_KEYS that differ, or ("missing: <path>",)

    @property
    def ok(self) -> bool:
        return self.max_abs_diff is not None and self.max_abs_diff <= TOLERANCE


@dataclass(frozen=True)
class ParityReport:
    name: str
    rows: tuple

    @property
    def passed(self) -> bool:
        return bool(self.rows) and all(r.ok for r in self.rows)

    @property
    def failing(self) -> tuple:
        return tuple(r for r in self.rows if not r.ok)

    def row(self, match_id: int) -> ParityRow:
        return next(r for r in self.rows if r.match_id == match_id)

    def table(self) -> str:
        diffs = [r.max_abs_diff for r in self.rows if r.max_abs_diff is not None]
        out = [f"PARITY {self.name}: {len(self.rows)} rows, {len(self.failing)} outside {TOLERANCE:g} on H/D/A "
               f"(max |dp| {max(diffs) if diffs else float('nan'):.3e}) -> {'PASS' if self.passed else 'FAIL'}",
               f"{'match':>5}  {'production H/D/A':<26}  {'walk H/D/A':<26}  {'max|dp|':>9}  "
               f"{'prod xg':<15}  {'walk xg':<15}  differs at"]
        for r in self.rows:
            p, w = r.production, r.walk
            fp = "/".join(f"{x:.6f}" for x in p.probs) if p else "-"
            fw = "/".join(f"{x:.6f}" for x in w.probs) if w else "-"
            xp = "/".join(f"{x:.4f}" for x in p.xg) if p else "-"
            xw = "/".join(f"{x:.4f}" for x in w.xg) if w else "-"
            d = f"{r.max_abs_diff:.3e}" if r.max_abs_diff is not None else "-"
            out.append(f"{r.match_id:>5}  {fp:<26}  {fw:<26}  {d:>9}  {xp:<15}  {xw:<15}  "
                       f"{', '.join(r.differing) or 'none'}")
        return "\n".join(out)


def _differs(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is not b
        return abs(float(a) - float(b)) > TOLERANCE
    if isinstance(a, tuple) and isinstance(b, tuple) and len(a) == len(b) and all(
            isinstance(x, (int, float)) for x in a + b):
        return any(_differs(float(x), float(y)) for x, y in zip(a, b))
    return a != b


def differing_inputs(prod: dict, walk: dict) -> tuple:
    """Every LOCATION_KEY whose value differs between the two paths' resolved inputs (floats within TOLERANCE are
    equal). A key one path did not report is a difference: never assumed equal."""
    return tuple(k for k in LOCATION_KEYS if (k in prod) != (k in walk) or _differs(prod.get(k), walk.get(k)))


def compare(name: str, production: dict, walk: dict, targets) -> ParityReport:
    """Row for row, in `targets` order: the max |dp| over H/D/A and the inputs that differ."""
    rows = []
    for mid in targets:
        p, w = production.get(mid), walk.get(mid)
        if p is None or w is None:
            rows.append(ParityRow(mid, p, w, None, ("missing: " + ("production" if p is None else "walk"),)))
            continue
        d = max(abs(a - b) for a, b in zip(p.probs, w.probs))
        rows.append(ParityRow(mid, p, w, d, differing_inputs(p.inputs, w.inputs)))
    return ParityReport(name, tuple(rows))


def assert_parity(report: ParityReport) -> None:
    """TEST (a)'S ASSERTION: every row inside TOLERANCE. Raises ParityFailure (with the table) otherwise."""
    if not report.passed:
        raise ParityFailure("production != the backtest walk, row for row\n" + report.table())


# ------------------------------------------------------- the context gap --

@dataclass(frozen=True)
class GapRow:
    match_id: int
    stored: tuple | None                 # production's stored (g, b) for the competition at the row's instant
    walk: tuple | None                   # the default walk's effective (deflation g, b, forecast g, b) on the row

    @property
    def ok(self) -> bool:
        if self.stored is None or self.walk is None:
            return False
        return not any(_differs(float(x), float(y)) for x, y in zip(self.walk, self.stored + self.stored))


@dataclass(frozen=True)
class GapReport:
    name: str
    rows: tuple

    @property
    def passed(self) -> bool:
        return bool(self.rows) and all(r.ok for r in self.rows)

    @property
    def failing(self) -> tuple:
        return tuple(r for r in self.rows if not r.ok)

    def table(self) -> str:
        out = [f"CONTEXT GAP {self.name}: {len(self.rows)} rows, {len(self.failing)} where the default walk's context "
               f"is not production's stored context -> {'PASS' if self.passed else 'FAIL'}",
               f"{'match':>5}  {'production stored g/b':<24}  {'walk deflation g/b, forecast g/b':<40}"]
        for r in self.rows:
            fs = "/".join(f"{x:.6f}" for x in r.stored) if r.stored else "-"
            fw = "/".join(f"{x:.6f}" for x in r.walk) if r.walk else "-"
            out.append(f"{r.match_id:>5}  {fs:<24}  {fw:<40}")
        return "\n".join(out)


def context_gap(name: str, production: dict, default_walk: dict, targets) -> GapReport:
    rows = []
    for mid in targets:
        p, w = production.get(mid), default_walk.get(mid)
        stored = tuple(p.inputs["stored_context"]) if p is not None and "stored_context" in p.inputs else None
        eff = tuple(w.inputs[k] for k in CONTEXT_KEYS) if w is not None and all(
            k in w.inputs for k in CONTEXT_KEYS) else None
        rows.append(GapRow(mid, stored, eff))
    return GapReport(name, tuple(rows))


def assert_no_context_gap(report: GapReport) -> None:
    """TEST (b)'S ASSERTION: on every row the default walk deflates and prices with production's stored context.
    Raises ContextGap (with the table) otherwise."""
    if not report.passed:
        raise ContextGap("the walk's effective context != production's stored context\n" + report.table())


# ----------------------------------------------------- the normalisation --

def average_league(g: float, b: float, n_teams: int = AVERAGE_LEAGUE_TEAMS) -> list:
    """Test (c)'s synthetic league of AVERAGE teams: every fixture of a double round robin, scored at the true means
    (home g·b, away g·(2−b)), as the match dicts the live caller hands estimate_strengths (training.py:515-524)."""
    return [{"home_team_id": h, "away_team_id": a, "home_score": g * b, "away_score": g * (2 - b)}
            for h in range(n_teams) for a in range(n_teams) if h != a]


def league_context(matches):
    """training.py:196-214's expressions (inline in _train_fresh_soccer, no pure helper without a DB) on a league of
    match dicts: g = total / (2 × matches), b = home mean / g clamped to [1.0, 1.30]."""
    from src.models.poisson import CompetitionScoringContext
    total = sum(m["home_score"] + m["away_score"] for m in matches)
    home = sum(m["home_score"] for m in matches)
    avg = total / (2 * len(matches))
    return CompetitionScoringContext(avg_goals_per_team_per_match=avg,
                                     home_field_goal_boost=max(1.0, min(1.30, (home / len(matches)) / avg)))


def normalisation(implied, g: float = NORMALISATION_G, b: float = NORMALISATION_B) -> dict:
    """The predictor's implied average-team figures against the context's own: the model's total and home/away ratio
    (implied(g, b)) beside 2g and b/(2−b)."""
    out = implied(g, b)
    home, away = float(out["home"]), float(out["away"])
    return {"g": g, "b": b, "model_total": home + away, "context_total": 2 * g,
            "deficit": (home + away) / (2 * g) - 1, "model_ratio": home / away, "context_ratio": b / (2 - b),
            "home": home, "away": away}


def normalisation_line(name: str, n: dict) -> str:
    return (f"NORMALISATION {name}: g {n['g']:.4f} b {n['b']:.4f}; average-team total {n['model_total']:.3f} vs the "
            f"context's {n['context_total']:.3f} ({n['deficit'] * 100:+.2f}%); home/away ratio {n['model_ratio']:.3f} "
            f"vs the context's {n['context_ratio']:.3f}")


def assert_self_consistent(name: str, n: dict) -> None:
    """TEST (c)'S ASSERTION: the implied total equals 2g and the implied ratio b/(2−b), within 1e-9. Raises
    NormalisationLean otherwise."""
    if abs(n["model_total"] - n["context_total"]) > 1e-9 or abs(n["model_ratio"] - n["context_ratio"]) > 1e-9:
        raise NormalisationLean("average teams do not price at the context's own rates\n" + normalisation_line(name, n))


# --------------------------------------------------------------- the spy --

@contextmanager
def recording(module):
    """Pass-through spies on `module.estimate_strengths` and `module.predict_match`: each runs the real function with
    the arguments it was given and returns its result unchanged; the spy only records. Yields the event list."""
    events: list = []
    real_es, real_pm = module.estimate_strengths, module.predict_match

    def es(matches, context, prior=None, weights=None):
        out = real_es(matches, context, prior=prior, weights=weights)
        events.append(("strengths", {
            "deflation_g": float(context.avg_goals_per_team_per_match),
            "deflation_b": float(context.home_field_goal_boost),
            "history": tuple(sorted((m["home_team_id"], m["away_team_id"], m["home_score"], m["away_score"])
                                    for m in matches)),
            "weighted": weights is not None, "strength_prior": prior is not None}))
        return out

    def pm(home_elo, away_elo, home_strength, away_strength, context, config=None, factor_adjustment=None):
        out = real_pm(home_elo, away_elo, home_strength, away_strength, context, config, factor_adjustment)
        cfg = config if config is not None else module.PoissonConfig()
        fa = factor_adjustment
        events.append(("predict", {
            "forecast_g": float(context.avg_goals_per_team_per_match),
            "forecast_b": float(context.home_field_goal_boost),
            "home_elo": float(home_elo), "away_elo": float(away_elo),
            "rho": float(cfg.dixon_coles_rho), "elo_goal_coeff": float(cfg.elo_goal_coeff),
            "max_goals": int(cfg.max_goals),
            "factor": (1.0, 1.0) if fa is None else (float(fa.home_xg_multiplier), float(fa.away_xg_multiplier)),
            "home_attack": float(home_strength.attack), "home_defense": float(home_strength.defense),
            "away_attack": float(away_strength.attack), "away_defense": float(away_strength.defense)}, out))
        return out

    with mock.patch.object(module, "estimate_strengths", es), mock.patch.object(module, "predict_match", pm):
        yield events


def paired(events) -> list:
    """Each predict_match call with the strengths fit it priced from (the latest estimate_strengths call before it):
    [(inputs, MatchPrediction)]."""
    out, last = [], None
    for ev in events:
        if ev[0] == "strengths":
            last = ev[1]
        else:
            if last is None:
                raise AssertionError("a predict_match call with no estimate_strengths call before it")
            out.append(({**last, **ev[1]}, ev[2]))
    return out


# ------------------------------------------------------------- the store --

def require_tmp_store(database: str | None = None) -> None:
    """Refuse any store whose SQLite file is not under the system temp directory (data/ is never touched)."""
    if database is None:
        import src.db.database as db
        database = db._engine.url.database
    if not database:
        raise StoreRefused("the bound store has no SQLite file")
    p, tmp = Path(database).resolve(), Path(tempfile.gettempdir()).resolve()
    if tmp not in p.parents or "data" in p.relative_to(tmp).parts:
        raise StoreRefused(f"synthetic stores under {tmp} only, not {p}")


def fresh_store(path, monkeypatch):
    """Bind src.db.database to a fresh SQLite file at `path` (tmp only) and create the tables (tests/nfl_v2_world.py's
    fresh(), the same binding)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    require_tmp_store(str(path))
    import src.db.database as db
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    return db


N_TEAMS = 6
DOUBLE_ROUND_ROBINS = 2
START = datetime(2093, 8, 1, 15, 0)
STEP = timedelta(hours=12)
#: The three fixtures after the 60; each is played 2-1 (score()). The first is the average row.
TARGETS = ((0, 2), (3, 5), (1, 4))
#: v22's stored poisson values (tests/test_soccer_backtest_prod_params_138.py: rho −0.10, elo_goal_coeff 0.0008).
V22_RHO, V22_ELO_GOAL_COEFF = -0.10, 0.0008
PRODUCTION_ROW = "v22-shape"


def score(h: int, a: int) -> tuple:
    """Team h hosts team (h + 1) % N_TEAMS in its one 1-2; every other home game is 2-1."""
    return (1, 2) if a == (h + 1) % N_TEAMS else (2, 1)


def seed_v22_shape_store(code: str, season: str) -> dict:
    """The v22 finding's shape (module docstring). Returns the ids: teams, the 60, the targets, AVERAGE_ROW."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, ModelVersion, Sport, Team
    from src.models.poisson import PoissonConfig

    require_tmp_store()
    rng = random.Random(248)
    fixtures = []
    for _ in range(DOUBLE_ROUND_ROBINS):
        block = [(h, a) for h in range(N_TEAMS) for a in range(N_TEAMS) if h != a]
        rng.shuffle(block)
        fixtures += block
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code=code, name="Parity League", area="X", type="LEAGUE")
        s.add(comp)
        teams = [Team(sport=Sport.SOCCER, name=f"Parity {i}") for i in range(N_TEAMS)]
        s.add_all(teams)
        s.flush()
        tid = [t.id for t in teams]
        rows = []
        for i, (h, a) in enumerate(fixtures + list(TARGETS)):
            hs, as_ = score(h, a)
            m = Match(sport=Sport.SOCCER, competition_id=comp.id, season=season, utc_date=START + i * STEP,
                      status=MatchStatus.FINISHED, home_team_id=tid[h], away_team_id=tid[a],
                      home_score=hs, away_score=as_)
            s.add(m)
            rows.append(m)
        s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version=PRODUCTION_ROW,
                           status="production",
                           parameters={"elo": {"league": {}, "cup": {}}, "contexts": {}, "team_to_league": {},
                                       "poisson": {**PoissonConfig().as_dict(), "dixon_coles_rho": V22_RHO,
                                                   "elo_goal_coeff": V22_ELO_GOAL_COEFF}}))
        s.flush()
        ids = [m.id for m in rows]
    n = len(fixtures)
    return {"teams": tid, "average_matches": ids[:n], "targets": ids[n:], "average_row": ids[n]}


@contextmanager
def at_instant(code: str, season: str, match_id: int):
    """The store as it stood at `match_id`'s kickoff: it and EVERY soccer match kicking off at or after it, whatever
    its competition or season, SCHEDULED with no score (production's training reads every finished soccer match, so a
    later season or another competition would otherwise leak); restored on exit."""
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport

    require_tmp_store()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == code)).scalar_one()
        target = s.get(Match, match_id)
        if target.competition_id != comp.id or target.season != season:
            raise AssertionError(f"match {match_id} is not in {code} {season}")
        kick = target.utc_date
        held = []
        for m in s.execute(select(Match).where(Match.sport == Sport.SOCCER, Match.utc_date >= kick)).scalars():
            held.append((m.id, m.status, m.home_score, m.away_score))
            m.status, m.home_score, m.away_score = MatchStatus.SCHEDULED, None, None
    try:
        yield
    finally:
        with session_scope() as s:
            for mid, status, hs, as_ in held:
                m = s.get(Match, mid)
                m.status, m.home_score, m.away_score = status, hs, as_


def kickoff_order(match_ids) -> list:
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:
        kick = dict(s.execute(select(Match.id, Match.utc_date).where(Match.id.in_(list(match_ids)))).all())
    return sorted(match_ids, key=lambda i: (kick[i], i))


# ------------------------------------------------------------- the paths --

@dataclass(frozen=True)
class SoccerPaths:
    name: str
    production: Callable                 # (code, season, match_id) -> PathRow (inputs["stored_context"] = (g, b))
    walk: Callable                       # (code, season, context=None) -> {match_id: PathRow}
    implied: Callable                    # (g, b) -> {"home", "away"}: two average teams at equal Elo, test (c)


@dataclass(frozen=True)
class ParityRun:
    """What the three tests read for one predictor: (a) `parity`, the walk with production's stored context
    injected, row for row; (b) `context_gap`, the default walk's effective context against production's stored one;
    and the default walk's own comparison with production (`default_parity`, a receipt of the gap's size)."""
    name: str
    parity: ParityReport
    context_gap: GapReport
    default_parity: ParityReport
    injected: dict                       # {match_id: the context (g, b) injected into that row's walk}


def run_parity(paths: SoccerPaths, code: str, season: str, targets=None) -> ParityRun:
    """The default walk once on the store; production at each row's instant; then, for each row, the walk run with
    the stored context production read at that instant (each distinct context walked once), compared row for row.
    Every row the default walk scores unless `targets` names a subset."""
    from src.models.poisson import CompetitionScoringContext

    require_tmp_store()
    default_rows = paths.walk(code, season)
    order = kickoff_order(list(default_rows) if targets is None else list(targets))
    production = {}
    for mid in order:
        with at_instant(code, season, mid):
            row = paths.production(code, season, mid)
        if row is not None:
            production[mid] = row
    walks, injected, injected_rows = {}, {}, {}
    for mid in order:
        p = production.get(mid)
        if p is None or "stored_context" not in p.inputs:
            continue
        g, b = (float(x) for x in p.inputs["stored_context"])
        if (g, b) not in walks:
            walks[(g, b)] = paths.walk(code, season, context=CompetitionScoringContext(
                avg_goals_per_team_per_match=g, home_field_goal_boost=b))
        injected[mid] = (g, b)
        if mid in walks[(g, b)]:
            injected_rows[mid] = walks[(g, b)][mid]
    return ParityRun(paths.name,
                     compare(paths.name, production, injected_rows, order),
                     context_gap(paths.name, production, default_rows, order),
                     compare(paths.name + " [default walk]", production, default_rows, order),
                     injected)


def _set_context(version: str, code: str, context) -> None:
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import ModelVersion
    with session_scope() as s:
        mv = s.execute(select(ModelVersion).where(ModelVersion.version == version)).scalar_one()
        params = dict(mv.parameters or {})
        params["contexts"] = {**(params.get("contexts") or {}), code: context.as_dict()}
        mv.parameters = params


def stored_context(version: str, code: str):
    """Production's stored context for `code`, read from the ModelVersion's parameters exactly as the live path reads
    it: training.py:456-459 builds {code: CompetitionScoringContext(**v)} from parameters["contexts"], and
    training.py:514 takes `contexts.get(competition_code, CompetitionScoringContext())`."""
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import ModelVersion
    from src.models.poisson import CompetitionScoringContext
    with session_scope() as s:
        params = s.execute(select(ModelVersion).where(ModelVersion.version == version)).scalar_one().parameters or {}
    contexts_raw = params.get("contexts", {})
    contexts = {k: CompetitionScoringContext(**v) for k, v in contexts_raw.items()}
    return contexts.get(code, CompetitionScoringContext())


def v22_production(code: str, season: str, match_id: int, context_override=None) -> PathRow | None:
    """v22's live path at the instant: the real training, then the real pricing of the one match, read back from the
    Prediction row it writes, with the stored context it read. `context_override` (the positive control only)
    replaces the trained context before pricing; None = v22 exactly as trained."""
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import Prediction
    from src.walters import training as tr

    with recording(tr) as events:
        version = tr._train_fresh_soccer(notes="soccer_parity harness: v22's path at the instant").version
        if context_override is not None:
            _set_context(version, code, context_override)
        n = tr._generate_predictions_soccer(code, season, model_version=version, only_match_id=match_id)
    calls = paired(events)
    if n == 0:
        return None
    if n != 1 or len(calls) != 1:
        raise AssertionError(f"one row and one forecast expected, got {n} rows and {len(calls)} forecasts")
    inputs, pred = calls[0]
    ctx = stored_context(version, code)
    stored = (float(ctx.avg_goals_per_team_per_match), float(ctx.home_field_goal_boost))
    with session_scope() as s:
        p = s.execute(select(Prediction).where(Prediction.match_id == match_id)).scalar_one()
        row = PathRow(match_id, (p.home_win_prob, p.draw_prob, p.away_win_prob),
                      (p.expected_home_score, p.expected_away_score),
                      {**inputs, "version": version, "stored_context": stored})
    if row.probs != (pred.p_home, pred.p_draw, pred.p_away) or row.xg != (pred.home_xg, pred.away_xg):
        raise AssertionError("the stored Prediction row is not the forecast the spy recorded")
    return row


def v22_walk(code: str, season: str, context=None) -> dict:
    """v22's replay: run_soccer_backtest as soccer-backtest's plain report calls it; `context` None = that call
    exactly (the gate's walk, the dataclass default context), else the context every row is deflated and priced
    with."""
    import cli
    from src.walters import soccer_backtest as sb

    prod = cli._soccer_prod_poisson()
    rho = prod[1] if prod else 0.0
    coeff = prod[2] if prod else None
    kw = {} if context is None else {"context": context}
    with recording(sb) as events:
        results = sb.run_soccer_backtest(code, season, WALK_MIN_PRIOR, dixon_coles_rho=rho, elo_goal_coeff=coeff,
                                         detail=True, **kw) or []
    calls = paired(events)
    if len(calls) != len(results):
        raise AssertionError(f"{len(results)} walk rows and {len(calls)} forecasts")
    out = {}
    for r, (inputs, pred) in zip(results, calls):
        row = PathRow(r["match_id"], (r["p_home"], r["p_draw"], r["p_away"]), (r["home_xg"], r["away_xg"]), inputs)
        if row.probs != (pred.p_home, pred.p_draw, pred.p_away):
            raise AssertionError("a walk row is not the forecast the spy recorded")
        out[r["match_id"]] = row
    return out


def v22_implied(g: float, b: float) -> dict:
    """v22's average-team forecast (test (c)): the REAL estimate_strengths (training's own import) on
    average_league(g, b) with the context training's expressions give it, the n/(n+5) shrinkage undone exactly
    (poisson.py: w = n/(n+5) toward 1.0; raw = (out − (1 − w)) / w, n = 38 here), then the REAL predict_match at equal
    Elo with no factors. Also returns the as-run (shrunk) forecast for the receipt."""
    from src.models.poisson import PoissonConfig, TeamStrength
    from src.walters import training as tr

    matches = average_league(g, b)
    ctx = league_context(matches)
    st = tr.estimate_strengths(matches, ctx)
    n = 2 * (AVERAGE_LEAGUE_TEAMS - 1)
    w = n / (n + 5)
    first = st[0]
    if any(abs(x.attack - first.attack) > 1e-12 or abs(x.defense - first.defense) > 1e-12 for x in st.values()):
        raise AssertionError("the average-team league fitted unequal teams")
    pre = TeamStrength(attack=(first.attack - (1 - w)) / w, defense=(first.defense - (1 - w)) / w)
    p = tr.predict_match(1500.0, 1500.0, pre, pre, ctx, PoissonConfig())
    shrunk = tr.predict_match(1500.0, 1500.0, first, first, ctx, PoissonConfig())
    return {"home": p.home_xg, "away": p.away_xg, "rating": pre.attack, "ctx": ctx,
            "as_run_home": shrunk.home_xg, "as_run_away": shrunk.away_xg, "as_run_rating": first.attack}


#: main's v22: production as trained, the walk as the gate runs it.
V22 = SoccerPaths("v22 (main): production vs soccer-backtest", v22_production, v22_walk, v22_implied)


def _v22_production_walk_context(code, season, match_id):
    from src.models.poisson import CompetitionScoringContext
    return v22_production(code, season, match_id, context_override=CompetitionScoringContext())


#: THE POSITIVE CONTROL for (a) and (b) (not a predictor): v22's own code with the trained context replaced by the
#: walk's default (the dataclass default, soccer_backtest.py), so the default walk's context IS production's stored
#: one on this store: (b) passes for it, and (a) with it.
V22_WALK_CONTEXT_CONTROL = SoccerPaths("control: v22 production priced with the walk's context",
                                       _v22_production_walk_context, v22_walk, v22_implied)


def data_rate_implied(g: float, b: float) -> dict:
    """THE POSITIVE CONTROL for (c) (not a predictor): the real predict_match fed unit strengths at the data's rates
    (home g·b; away g·(2−b) through the away factor multiplier), equal Elo: consistent by construction."""
    from types import SimpleNamespace
    from src.models.poisson import CompetitionScoringContext, PoissonConfig, TeamStrength, predict_match
    ctx = CompetitionScoringContext(avg_goals_per_team_per_match=g, home_field_goal_boost=b)
    unit = TeamStrength(attack=1.0, defense=1.0)
    p = predict_match(1500.0, 1500.0, unit, unit, ctx, PoissonConfig(),
                      factor_adjustment=SimpleNamespace(home_xg_multiplier=1.0, away_xg_multiplier=2 - b))
    return {"home": p.home_xg, "away": p.away_xg}


DATA_RATE_CONTROL = "control: predict_match fed unit strengths at the data's rates"

#: The soccer predictors the acceptance tests run. A successor appends its own SoccerPaths here.
PREDICTORS = (V22,)
