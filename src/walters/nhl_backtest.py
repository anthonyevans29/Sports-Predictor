"""
NHL Phase 2 backtest harness (H-track, 2026-09-25) — cloned from the NFL
harness shape (src/walters/nfl_backtest.py).

THE GATE IS WRITTEN FIRST (architect, 2026-09-25 — see BACKLOG "NHL PHASE 2
GATE"). This module implements exactly that protocol and prints a verdict
against the frozen numbers. It writes NOTHING: no predictions, no model rows.
A PASS earns the NFL sequence (internal week, rehearsal + dry read, live
decision); promotion is the architect's ruling on the pasted verdict.

Protocol:
  * Stream: NHL competition, FINISHED, both scores present. FT/AOT/AP all
    count as decided games (the provider's totals include OT/SO).
  * Preseason EXCLUDED: any stage marker containing "pre", or a game dated
    before that season's regular-season opener (SEASON_STARTS, overridable).
  * Warm-up (train) = season "2024"; scored (test) = season "2025",
    predict-then-update (walk-forward).
  * Outcome: binary home win INCLUSIVE of OT/SO (moneyline convention).
    OT/SO weighting is an R-track hypothesis, not v1.
  * Baselines on the test season: constant 0.5, and the league home rate
    (realized in the TRAIN season, frozen before scoring).

Frozen acceptance:
  1. candidate test log-loss <= home-rate baseline - 0.010
  2. every 10pp probability band with n >= 100 calibrates within ±5pp
  3. final ratings all within 1200-1800 (outliers FAIL unless the architect
     names a reason)
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Protocol

TRAIN_SEASON = "2024"
TEST_SEASON = "2025"

# Regular-season opener per season (single-year int strings: "2024" = the
# 2024-25 season). Games dated before these are preseason. These are the
# North American openers; the 2024 Prague openers (Oct 4-5) overlapped the
# last preseason games, so the NA date is the conservative cut — it drops
# the two Prague games rather than admit preseason. ARCHITECT-RULE; the
# harness prints the boundary so the run itself verifies them.
SEASON_STARTS: dict[str, date] = {
    "2024": date(2024, 10, 8),
    "2025": date(2025, 10, 7),
}

LL_MARGIN = 0.010
BAND_MIN_N = 100
BAND_TOL = 0.05
RATING_MIN, RATING_MAX = 1200.0, 1800.0
EPS = 1e-12


@dataclass(frozen=True)
class Game:
    home_id: int
    away_id: int
    season: str
    utc_date: datetime
    home_score: int
    away_score: int
    stage: str = ""
    # Hours since each team's previous game start (attach_rest); None = no
    # earlier game in the loaded schedule. Used by candidate v2 only.
    home_rest_h: float | None = None
    away_rest_h: float | None = None

    @property
    def home_win(self) -> int:
        """Moneyline convention: OT/SO wins count (totals include them)."""
        return 1 if self.home_score > self.away_score else 0


class Predictor(Protocol):
    def predict(self, g: Game) -> float: ...
    def update(self, g: Game) -> None: ...
    def ratings(self) -> dict[int, float]: ...


# --------------------------------------------------------------------------
# Stream selection
# --------------------------------------------------------------------------


def preseason_reason(g: Game, season_starts: dict[str, date]) -> str | None:
    """Why a game is preseason ('stage' / 'date'), or None if it's in."""
    if "pre" in (g.stage or "").lower():
        return "stage"
    start = season_starts.get(g.season)
    if start is not None and g.utc_date.date() < start:
        return "date"
    return None


@dataclass
class Stream:
    train: list[Game] = field(default_factory=list)
    test: list[Game] = field(default_factory=list)
    excluded: Counter = field(default_factory=Counter)   # (season, reason) -> n
    ties: int = 0
    stages: dict[str, Counter] = field(default_factory=dict)
    boundary: dict[str, dict] = field(default_factory=dict)


def build_stream(games: list[Game], season_starts: dict[str, date] = SEASON_STARTS) -> Stream:
    st = Stream()
    for g in sorted(games, key=lambda x: x.utc_date):
        if g.season not in (TRAIN_SEASON, TEST_SEASON):
            continue
        st.stages.setdefault(g.season, Counter())[g.stage or "—"] += 1
        why = preseason_reason(g, season_starts)
        if why:
            st.excluded[(g.season, why)] += 1
            continue
        if g.home_score == g.away_score:   # impossible for a decided game
            st.ties += 1
            continue
        (st.train if g.season == TRAIN_SEASON else st.test).append(g)

    # Boundary receipt: last excluded-by-date day and first kept day, with counts.
    for season in (TRAIN_SEASON, TEST_SEASON):
        kept = Counter(g.utc_date.date() for g in (st.train if season == TRAIN_SEASON else st.test))
        dropped = Counter(g.utc_date.date() for g in games if g.season == season
                          and preseason_reason(g, season_starts) == "date")
        st.boundary[season] = {
            "start": season_starts.get(season),
            "last_dropped_days": sorted(dropped.items())[-3:],
            "first_kept_days": sorted(kept.items())[:3],
        }
    return st


def attach_rest(games: list[Game]) -> list[Game]:
    """Rest from the schedule already in the DB: hours between each team's
    consecutive game STARTS, over every loaded NHL game (preseason included —
    physical fatigue doesn't care whether the game counted). Hours, not UTC
    dates: a 7pm ET game then a 7pm PT game next day spans two UTC dates but
    is a true back-to-back."""
    from dataclasses import replace

    last: dict[int, datetime] = {}
    out = []
    for g in sorted(games, key=lambda x: (x.utc_date, x.home_id)):
        rest = {}
        for tid in (g.home_id, g.away_id):
            prev = last.get(tid)
            rest[tid] = None if prev is None else (g.utc_date - prev).total_seconds() / 3600.0
        out.append(replace(g, home_rest_h=rest[g.home_id], away_rest_h=rest[g.away_id]))
        last[g.home_id] = last[g.away_id] = g.utc_date
    return out


# --------------------------------------------------------------------------
# Scoring (pure)
# --------------------------------------------------------------------------


def beats_margin(ll_model: float, ll_home: float) -> bool:
    """Criterion 1: improvement over the home-rate baseline >= LL_MARGIN,
    inclusive. Compared as a difference with a float tolerance so an exact
    0.010 improvement isn't lost to rounding (0.690 - 0.010 = 0.67999...)."""
    return (ll_home - ll_model) >= LL_MARGIN - 1e-12


def _ll(p: float, y: int) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


@dataclass
class GateResult:
    n_train: int = 0
    n_test: int = 0
    home_rate: float = 0.0
    ll_const: float = 0.0
    ll_home: float = 0.0
    ll_model: float | None = None
    bands: list[dict] = field(default_factory=list)
    rating_min: float | None = None
    rating_max: float | None = None
    outliers: list[tuple[int, float]] = field(default_factory=list)
    crit_ll: bool = False
    crit_bands: bool = False
    crit_spread: bool = False
    verdict: str = ""


def baselines(stream: Stream) -> GateResult:
    """The two baselines on the test season. Home rate is the TRAIN season's
    realized home-win rate, frozen before any test game is scored."""
    r = GateResult(n_train=len(stream.train), n_test=len(stream.test))
    if not stream.train or not stream.test:
        r.verdict = "INVALID — protocol needs both seasons"
        return r
    r.home_rate = sum(g.home_win for g in stream.train) / len(stream.train)
    r.ll_const = sum(_ll(0.5, g.home_win) for g in stream.test) / len(stream.test)
    r.ll_home = sum(_ll(r.home_rate, g.home_win) for g in stream.test) / len(stream.test)
    return r


def calibration_bands(pairs: list[tuple[float, int]]) -> list[dict]:
    buckets: dict[int, list[tuple[float, int]]] = {}
    for p, y in pairs:
        buckets.setdefault(int(min(max(p, 0.0), 0.9999) * 10), []).append((p, y))
    out = []
    for b in sorted(buckets):
        obs = buckets[b]
        stated = sum(p for p, _ in obs) / len(obs)
        realized = sum(y for _, y in obs) / len(obs)
        gated = len(obs) >= BAND_MIN_N
        out.append({"band": b, "n": len(obs), "stated": stated, "realized": realized,
                    "gap": realized - stated, "gated": gated,
                    # inclusive ±5pp, float-safe: an exact 5.0pp gap passes on
                    # every Python (3.12's exact float sum() lands it at 0.0500...04)
                    "ok": (abs(realized - stated) <= BAND_TOL + 1e-12) if gated else None})
    return out


def run_gate(stream: Stream, model: Predictor) -> GateResult:
    """Walk-forward: warm-up updates only; test predicts-then-updates."""
    r = baselines(stream)
    if r.verdict:
        return r
    for g in stream.train:
        model.update(g)
    pairs, ll = [], 0.0
    for g in stream.test:
        p = model.predict(g)
        pairs.append((p, g.home_win))
        ll += _ll(p, g.home_win)
        model.update(g)
    r.ll_model = ll / len(stream.test)
    r.bands = calibration_bands(pairs)

    ratings = model.ratings()
    if ratings:
        r.rating_min, r.rating_max = min(ratings.values()), max(ratings.values())
        r.outliers = sorted((t, v) for t, v in ratings.items()
                            if not RATING_MIN <= v <= RATING_MAX)

    r.crit_ll = beats_margin(r.ll_model, r.ll_home)
    r.crit_bands = all(b["ok"] for b in r.bands if b["gated"])
    r.crit_spread = not r.outliers
    if r.crit_ll and r.crit_bands and r.crit_spread:
        r.verdict = "PASS — earns the NFL sequence (internal week, rehearsal + dry read, live decision)"
    else:
        why = [n for n, ok in (("log-loss margin", r.crit_ll), ("calibration", r.crit_bands),
                               ("rating spread", r.crit_spread)) if not ok]
        r.verdict = "FAIL — " + ", ".join(why)
    return r


# --------------------------------------------------------------------------
# Candidate iteration (architect protocol 2026-09-25)
# --------------------------------------------------------------------------
#
# Parameters are tuned on 2024-INTERNAL sequential loss only (predict-then-
# update through the train season); 2025 is evaluated ONCE per candidate by
# run_gate. tune_v2 is handed the train games and nothing else.

# FROZEN before any run (logged in BACKLOG). Ordered simplest-first so an
# exact loss tie resolves to the simpler setting. season_regression is NOT
# tunable here: 2024 is the first season in the DB, so the train stream
# contains no season transition for it to act on — it stays at v1's 0.25.
V2_GRID: dict[str, tuple] = {
    "k_factor": (4.0, 6.0, 8.0, 10.0),
    "mov_base": (1.0, 2.2, 4.0),
    "home_advantage": (15.0, 25.0, 35.0, 45.0, 55.0),
    "b2b_penalty": (0.0, 15.0, 30.0, 45.0),
    "rest_per_day": (0.0, 5.0, 10.0),
}


def sequential_loss(games: list[Game], model: Predictor) -> float:
    """Mean log-loss of predict-then-update over `games` (one pass)."""
    total = 0.0
    for g in games:
        total += _ll(model.predict(g), g.home_win)
        model.update(g)
    return total / len(games)


def tune_v2(train: list[Game]) -> tuple[dict, list[tuple[float, dict]]]:
    """Grid search on 2024-internal sequential loss. Returns (best params,
    all (loss, params) rows sorted best-first)."""
    from itertools import product

    from src.models.nhl_elo import NHLEloConfigV2, NHLEloV2

    keys = list(V2_GRID)
    rows = []
    for values in product(*(V2_GRID[k] for k in keys)):
        params = dict(zip(keys, values))
        loss = sequential_loss(train, NHLEloV2(NHLEloConfigV2(**params)))
        rows.append((loss, params))
    rows.sort(key=lambda r: r[0])   # stable: grid order breaks exact ties
    return rows[0][1], rows


# --------------------------------------------------------------------------
# Candidate v3 (architect spec 2026-09-25, after v2's selection overfit)
# --------------------------------------------------------------------------
#
# v2 selected on the WHOLE 2024 sequence, which rewards sharpness with no
# counterweight (2024-internal improved, 2025 regressed, bands overconfident,
# 4/5 params at grid edges). v3 changes only the SELECTION:
#   * split 2024 chronologically: first VALIDATION_FIT_FRAC = fit (warm-up,
#     update only), remainder = validation;
#   * score each grid point by predict-then-update loss on the validation
#     games only (the same walk-forward protocol that scores 2025 — each
#     validation game is priced before its own result is seen);
#   * refit on ALL of 2024 at the chosen params (run_gate's warm-up), then
#     score 2025 once. Gate, model form and regression (0.25) unchanged.

VALIDATION_FIT_FRAC = 0.60

# FROZEN before any run. Every v2 value kept; options added only BELOW or
# BETWEEN them — nothing above the old maxima (the corners already testified).
# Ordered simplest-first so exact ties pick the simpler setting.
V3_GRID: dict[str, tuple] = {
    "k_factor": (2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0),
    "mov_base": (0.5, 1.0, 1.6, 2.2, 3.0, 4.0),
    "home_advantage": (15.0, 25.0, 35.0, 45.0, 55.0),
    "b2b_penalty": (0.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0),
    "rest_per_day": (0.0, 2.5, 5.0, 7.5, 10.0),
}


def validation_split(train: list[Game], frac: float = VALIDATION_FIT_FRAC
                     ) -> tuple[list[Game], list[Game]]:
    """Chronological split of the train season: (fit, validation)."""
    ordered = sorted(train, key=lambda g: g.utc_date)
    cut = int(len(ordered) * frac)
    return ordered[:cut], ordered[cut:]


def validation_loss(fit: list[Game], val: list[Game], model: Predictor) -> float:
    """Warm up on `fit` (update only), then walk-forward loss on `val`."""
    for g in fit:
        model.update(g)
    return sequential_loss(val, model)


def tune_v3(train: list[Game], grid: dict[str, tuple] | None = None
            ) -> tuple[dict, list[tuple[float, dict]], tuple[list[Game], list[Game]]]:
    """Select params by walk-forward validation INSIDE the train season.
    Returns (best params, all (validation loss, params) rows best-first,
    (fit, validation) split)."""
    from itertools import product

    from src.models.nhl_elo import NHLEloConfigV2, NHLEloV2

    grid = grid or V3_GRID
    fit, val = validation_split(train)
    keys = list(grid)
    rows = []
    for values in product(*(grid[k] for k in keys)):
        params = dict(zip(keys, values))
        rows.append((validation_loss(fit, val, NHLEloV2(NHLEloConfigV2(**params))), params))
    rows.sort(key=lambda r: r[0])   # stable: grid order breaks exact ties
    return rows[0][1], rows, (fit, val)


# --------------------------------------------------------------------------
# DB loading + report
# --------------------------------------------------------------------------


def load_games() -> list[Game]:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport

    with session_scope() as s:
        rows = s.execute(
            select(Match)
            .join(Competition, Match.competition_id == Competition.id)
            .where(
                Match.sport == Sport.NHL,
                Competition.code == "NHL",           # 4 Nations etc. stay out
                Match.status == MatchStatus.FINISHED,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
            ).order_by(Match.utc_date, Match.id)
        ).scalars().all()
        return [Game(m.home_team_id, m.away_team_id, m.season, m.utc_date,
                     m.home_score, m.away_score, m.stage or "") for m in rows]


def report(stream: Stream, r: GateResult, out: Callable[[str], None] = print,
           model_name: str | None = None, extra: list[str] | None = None) -> None:
    out(f"NHL Phase 2 gate · train {TRAIN_SEASON} · test {TEST_SEASON}")
    for season in (TRAIN_SEASON, TEST_SEASON):
        ex = {why: n for (s_, why), n in stream.excluded.items() if s_ == season}
        b = stream.boundary.get(season, {})
        out(f"  {season}: kept {len(stream.train if season == TRAIN_SEASON else stream.test)}"
            f" · preseason excluded by stage {ex.get('stage', 0)}, by date {ex.get('date', 0)}"
            f" (opener {b.get('start')})")
        days = lambda xs: ", ".join(f"{d.isoformat()}×{n}" for d, n in xs or []) or "—"
        out(f"    UTC days: last dropped [{days(b.get('last_dropped_days'))}] · "
            f"first kept [{days(b.get('first_kept_days'))}]")
        out(f"    stage values: {dict(stream.stages.get(season, {}))}")
    if stream.ties:
        out(f"  ⚠ {stream.ties} tied finals skipped (a decided game can't tie — data defect)")
    if r.verdict.startswith("INVALID"):
        out(f"VERDICT: {r.verdict}")
        return
    out(f"BASELINES (test season, n={r.n_test})")
    out(f"  constant 0.5          log-loss {r.ll_const:.4f}")
    out(f"  league home rate      log-loss {r.ll_home:.4f}  (p_home = {r.home_rate:.4f}, "
        f"realized in {TRAIN_SEASON})")
    if r.ll_model is None:
        out("  (baselines only — no candidate model scored)")
        return
    for line in extra or []:          # e.g. candidate tuning receipts
        out(line)
    out(f"CANDIDATE {model_name or ''}")
    out(f"  1) log-loss {r.ll_model:.4f} vs need <= {r.ll_home - LL_MARGIN:.4f} "
        f"-> {'PASS' if r.crit_ll else 'FAIL'}")
    out(f"  2) calibration (10pp bands; gated when n >= {BAND_MIN_N}, tolerance ±{BAND_TOL*100:.0f}pp)")
    for b in r.bands:
        tag = ("ok" if b["ok"] else "FAIL") if b["gated"] else "(n < 100, not gated)"
        out(f"     {b['band']*10:>2}-{b['band']*10+10}%: n={b['n']:<4} stated {b['stated']:.3f} "
            f"realized {b['realized']:.3f} gap {b['gap']*100:+.1f}pp {tag}")
    out(f"  3) final ratings {r.rating_min:.0f}-{r.rating_max:.0f} (bound {RATING_MIN:.0f}-{RATING_MAX:.0f})"
        + (f" OUTLIERS {r.outliers}" if r.outliers else "") + f" -> {'PASS' if r.crit_spread else 'FAIL'}")
    out(f"GATE VERDICT: {r.verdict}")
