"""
NHL-xG v6 (#153 part 2; corrected manifest #210). EVERY constant below is
DECLARED in docs/specs/nhl-xg-v6.md and frozen BEFORE any run (law 3); the
run refuses unless the registry (#212) holds the "nhl-v6" declaration.

The ruling (2026-09-30, corrected 2026-10-01 by the external review):
  an xG model = logistic over distance, angle, situation class and a
  NULLABLE shot type, fitted ONLY on 2023-24 shots, frozen. The EVENT CODE is
  ELIGIBILITY + TARGET only (which plays are unblocked attempts; whether the
  attempt was a goal) — never a feature. Pre-committed rules for empty-net,
  blocked shots, orientation and missing coordinates. v6 = v1 Elo whose
  margin-of-victory input is the game's xG margin. No same-game leakage.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

# ---- eligibility + target (the ONLY use of the event code) ----------------
ELIGIBLE = frozenset({"shot-on-goal", "missed-shot", "goal"})   # unblocked attempts (Fenwick)
TARGET = frozenset({"goal"})
BLOCKED = frozenset({"blocked-shot"})                           # RULE B: excluded (coords = block site)

# ---- geometry ---------------------------------------------------------------
NET_X = 89.0          # goal line, feet from centre ice (NHL rink)

# ---- the fit ----------------------------------------------------------------
FIT_FROM = datetime(2023, 10, 1)        # 2023-24 regular season + playoffs
FIT_TO = datetime(2024, 10, 8)          # exclusive: the 2024 (train) opener, nhl_backtest.SEASON_STARTS
FIT_GAME_TYPES = frozenset({2, 3})
SHOT_TYPE_MIN = 100                      # a shot type is its own level with >= 100 fit events, else "other"
RIDGE = 1.0                              # L2 on the non-intercept coefficients (numerical stability only)
IRLS_ITERS = 50

# ---- v6 margin --------------------------------------------------------------
# v6 = v1 Elo (k 6.0, mov_base 2.2, regression 0.25, home advantage from the
# 2024 home rate) with ONE change: the margin inside ln(margin + 1) is the
# game's |xG_home - xG_away| (all situations, rules applied) instead of the
# goal margin. The win/loss result stays the game result. A game with no
# eligible event (coverage miss) uses its goal margin — counted.

# ---- rolling team xG (REPORTED, not a v6 input) ----------------------------
ROLL_HALF_LIFE_DAYS = 60.0
ROLL_PRIOR_GAMES = 10.0
GAME_MINUTES = 60.0        # per 60 = per game at regulation length; OT time is not stored, not adjusted


@dataclass
class Shot:
    """One stored nhl_shot_events row, the fields the rules read."""
    nhl_game_id: int
    match_id: int | None
    game_start: datetime
    game_type: int | None
    event_type: str
    period: int | None
    period_type: str | None
    side: str | None
    owner_side: str | None
    x: float | None
    y: float | None
    shot_type: str | None
    situation_code: str | None
    home_defending_side: str | None


@dataclass
class Prepared:
    """A shot after the rules: features + target, or the exclusion reason."""
    shot: Shot
    side: str | None = None
    distance: float | None = None
    angle: float | None = None
    situation: str | None = None
    goal: int = 0
    excluded: str | None = None


def _digits(code: str | None) -> tuple[int, int, int, int] | None:
    """situationCode 'ABCD': away goalie (1/0), away skaters, home skaters, home goalie."""
    if not code or len(code) != 4 or not code.isdigit():
        return None
    return int(code[0]), int(code[1]), int(code[2]), int(code[3])


def prepare(s: Shot) -> Prepared:
    """The PRE-COMMITTED rules, in order (the first that applies decides):
      R1 event code: blocked -> 'blocked'; not an unblocked attempt -> 'not_eligible'
      R2 shootout (period type SO, or period >= 5 in the regular season) -> 'shootout'
      R3 shooter side: roster side, else the play owner; neither -> 'no_side'
      R4 situation code missing/malformed -> 'no_situation'
      R5 empty net (the DEFENDING team's goalie digit 0) -> 'empty_net'
      R6 missing x or y -> 'missing_coords'
      R7 orientation: home attacks the net opposite home_defending_side
         (left -> x=+89, right -> x=-89); missing side -> 'no_orientation'
    Then distance (ft) and angle (deg, 0 = straight on) to the attacked net,
    and the situation class from the SHOOTER's view: EV / PP / SH."""
    p = Prepared(shot=s)
    et = (s.event_type or "").lower()
    if et in BLOCKED:
        p.excluded = "blocked"
        return p
    if et not in ELIGIBLE:
        p.excluded = "not_eligible"
        return p
    if (s.period_type or "").upper() == "SO" or (s.game_type == 2 and (s.period or 0) >= 5):
        p.excluded = "shootout"
        return p
    side = s.side or s.owner_side
    if side not in ("home", "away"):
        p.excluded = "no_side"
        return p
    d = _digits(s.situation_code)
    if d is None:
        p.excluded = "no_situation"
        return p
    away_g, away_sk, home_sk, home_g = d
    if (away_g if side == "home" else home_g) == 0:
        p.excluded = "empty_net"
        return p
    if s.x is None or s.y is None:
        p.excluded = "missing_coords"
        return p
    hds = (s.home_defending_side or "").lower()
    if hds not in ("left", "right"):
        p.excluded = "no_orientation"
        return p
    home_net = NET_X if hds == "left" else -NET_X
    net = home_net if side == "home" else -home_net
    dx, dy = abs(net - s.x), abs(s.y)
    p.side = side
    p.distance = math.hypot(dx, dy)
    p.angle = math.degrees(math.atan2(dy, dx)) if (dx or dy) else 0.0
    own, opp = (home_sk, away_sk) if side == "home" else (away_sk, home_sk)
    p.situation = "EV" if own == opp else ("PP" if own > opp else "SH")
    p.goal = 1 if et in TARGET else 0
    return p


@dataclass
class XGModel:
    """The frozen logistic model: coefficients + the shot-type levels."""
    names: list[str]
    coef: list[float]
    shot_levels: list[str]
    baseline_level: str
    # v6: True (a missing shot type is its own level, "na"). v7 (ARCHITECT
    # 2026-10-02, a correctness fix): False — "na" was a label leak (+3.02;
    # a missing shot type occurs on ~0.3% of goals), so an event without a
    # shot type takes the BASELINE level (all shot dummies 0).
    na_level: bool = True
    n_fit: int = 0
    goals_fit: int = 0
    fit_last_game: datetime | None = None
    exclusions: dict = field(default_factory=dict)

    def row(self, p: Prepared) -> list[float]:
        st = p.shot.shot_type
        if st is None:
            lvl = "na" if self.na_level else self.baseline_level
        else:
            lvl = st if st in self.shot_levels else "other"
        x = [1.0, p.distance, p.angle, 1.0 if p.situation == "PP" else 0.0, 1.0 if p.situation == "SH" else 0.0]
        x += [1.0 if lvl == L else 0.0 for L in self.shot_levels_all() if L != self.baseline_level]
        return x

    def shot_levels_all(self) -> list[str]:
        return list(self.shot_levels) + (["other", "na"] if self.na_level else ["other"])

    def xg(self, p: Prepared) -> float:
        z = sum(c * v for c, v in zip(self.coef, self.row(p)))
        return 1.0 / (1.0 + math.exp(-max(min(z, 40.0), -40.0)))


def fit(shots: list[Shot], na_level: bool = True) -> XGModel:
    """Fit on the 2023-24 window ONLY (FIT_FROM <= start < FIT_TO, game
    types 2/3). Shots outside the window are refused here, not filtered
    silently: the caller hands the window, the fit asserts it."""
    import numpy as np

    bad = [s for s in shots if not (FIT_FROM <= s.game_start < FIT_TO)]
    if bad:
        raise ValueError(f"fit window violated: {len(bad)} shot(s) outside 2023-24")
    prepared = [prepare(s) for s in shots if s.game_type in FIT_GAME_TYPES]
    excl = Counter(p.excluded for p in prepared if p.excluded)
    use = [p for p in prepared if not p.excluded]
    if not use:
        raise ValueError("no eligible 2023-24 shot after the rules")
    counts = Counter("na" if p.shot.shot_type is None else p.shot.shot_type for p in use)
    levels = sorted(k for k, n in counts.items() if k != "na" and n >= SHOT_TYPE_MIN)
    all_levels = levels + (["other", "na"] if na_level else ["other"])
    # v7: the baseline is chosen among the TYPED levels; untyped events then join it
    lvl_counts = Counter("na" if p.shot.shot_type is None else (p.shot.shot_type if p.shot.shot_type in levels
                                                                else "other") for p in use)
    baseline = max(all_levels, key=lambda L: (lvl_counts.get(L, 0), L))
    m = XGModel(names=["intercept", "distance", "angle", "PP", "SH"]
                + [f"shot:{L}" for L in all_levels if L != baseline],
                coef=[], shot_levels=levels, baseline_level=baseline, na_level=na_level)
    X = np.array([m.row(p) for p in use], dtype=float)
    y = np.array([p.goal for p in use], dtype=float)
    beta = np.zeros(X.shape[1])
    pen = np.full(X.shape[1], RIDGE)
    pen[0] = 0.0
    for _ in range(IRLS_ITERS):
        z = np.clip(X @ beta, -40, 40)
        mu = 1.0 / (1.0 + np.exp(-z))
        w = mu * (1 - mu)
        H = X.T @ (X * w[:, None]) + np.diag(pen)
        g = X.T @ (y - mu) - pen * beta
        step = np.linalg.solve(H, g)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-8:
            break
    m.coef = [float(b) for b in beta]
    m.n_fit, m.goals_fit = len(use), int(y.sum())
    m.fit_last_game = max(p.shot.game_start for p in use)
    m.exclusions = dict(excl)
    return m


def game_xg(model: XGModel, shots: list[Shot]) -> tuple[dict, Counter]:
    """match_id -> (xG_home, xG_away) over each LINKED game's shots, rules
    applied; plus the exclusion counts. Games with no eligible event are
    absent (v6 falls back to the goal margin for them)."""
    out: dict[int, list[float]] = {}
    excl = Counter()
    for s in shots:
        if s.match_id is None:
            continue
        p = prepare(s)
        if p.excluded:
            excl[p.excluded] += 1
            continue
        h_a = out.setdefault(s.match_id, [0.0, 0.0])
        h_a[0 if p.side == "home" else 1] += model.xg(p)
    return {k: (v[0], v[1]) for k, v in out.items()}, excl


def rolling_team_xg(games: list, xg_by_match: dict) -> dict[int, dict]:
    """REPORTED diagnostic (not a v6 input): each team's xG-for / -against per
    60 at the end of the stream, exponentially decayed (half-life 60 days)
    and shrunk toward the league mean with a 10-game prior."""
    events = []
    for g in games:
        xa = xg_by_match.get(getattr(g, "match_id", None))
        if xa is None:
            continue
        events.append((g.utc_date, g.home_id, xa[0], xa[1]))
        events.append((g.utc_date, g.away_id, xa[1], xa[0]))
    if not events:
        return {}
    end = max(e[0] for e in events)
    lam = math.log(2) / ROLL_HALF_LIFE_DAYS
    acc: dict[int, list[float]] = {}
    for t, team, f, a in events:
        w = math.exp(-lam * (end - t).total_seconds() / 86400.0)
        r = acc.setdefault(team, [0.0, 0.0, 0.0])
        r[0] += w * f
        r[1] += w * a
        r[2] += w
    league = sum(e[2] for e in events) / len(events)
    out = {}
    for team, (f, a, w) in acc.items():
        out[team] = {"xgf_per60": (f + ROLL_PRIOR_GAMES * league) / (w + ROLL_PRIOR_GAMES) * 60.0 / GAME_MINUTES,
                     "xga_per60": (a + ROLL_PRIOR_GAMES * league) / (w + ROLL_PRIOR_GAMES) * 60.0 / GAME_MINUTES,
                     "weight_games": w}
    return out


def load_shots():
    """Every stored shot event as a Shot (read-only)."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import NHLShotEvent

    with session_scope() as s:
        return [Shot(e.nhl_game_id, e.match_id, e.game_start, e.game_type, e.event_type, e.period,
                     e.period_type, e.side, e.owner_side, e.x, e.y, e.shot_type, e.situation_code,
                     e.home_defending_side)
                for e in s.execute(select(NHLShotEvent).order_by(NHLShotEvent.game_start)).scalars()]
