"""
NFL v1 model + walk-forward backtest (phase 2, 2026-09-09).

THE GATE WAS WRITTEN FIRST — see BACKLOG "NFL PHASE 2 GATE". This module
implements exactly that protocol and prints a PASS/FAIL verdict against the
frozen numbers. Nothing here writes predictions. Live era (nfl_elo_v1
LIVE since Week 3, 2026-09-22): a re-run is a PROVENANCE / REGRESSION check —
PASS means the live model still clears the gate it was promoted on.

Model: plain Elo with margin-of-victory multiplier (FiveThirtyEight-style),
self-contained on purpose (no dependency on the soccer Elo internals while
that module is under compression diagnosis). Win probability from rating
difference via the standard logistic. Preseason games are excluded from
both training and scoring — rotation noise (the EFL Trophy principle).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import NamedTuple


@dataclass
class NFLEloConfig:
    k_factor: float = 20.0
    home_advantage: float = 48.0      # Elo points ≈ ~2.5 pts spread
    season_regression: float = 0.25   # per-team, at ITS first game of a new season
    mov_base: float = 2.2             # margin multiplier: ln(|margin|+1) * base/(base + elo_gap*0.001)
    default_rating: float = 1500.0


# ---------------------------------------------------------------------------
# Hard scope (2026-09-26, architect lane 6): NCAA football is stored under
# the same Sport.NFL family (Competition.code "NCAA"), so a sport-only filter
# lets college games into the NFL pot. Every NFL model path — ratings walk,
# backtest, prediction selection, grading — selects through nfl_scoped(),
# which pins Competition.code == "NFL" explicitly. scope_line() is the
# receipt each run prints so contamination stays visible forever.
# ---------------------------------------------------------------------------
NFL_COMPETITION_CODE = "NFL"
NFL_EXPECTED_TEAMS = 32


def nfl_scoped(stmt):
    """Restrict a select() over Match to the NFL competition only."""
    from src.db.schema import Competition, Match, Sport
    return (stmt.join(Competition, Competition.id == Match.competition_id)
            .where(Match.sport == Sport.NFL,
                   Competition.code == NFL_COMPETITION_CODE))


def scope_line(label: str, games, per_week: bool = False) -> str:
    """'scope[label]: teams=32, games=N, competitions={NFL}' from the rows
    actually selected; appends SCOPE ALERT when either set is off-model.

    per_week (the weekly prediction set, operator 2026-10-05): a week is not the
    whole league, because teams on bye do not play. Per week the expected count is
    32 − byes, i.e. teams = 2 × games with no team twice, never above 32. The
    multi-week streams (ratings, backtest) keep the full 32-team check."""
    teams: set[int] = set()
    comps: set[str] = set()
    for m in games:
        teams.update((m.home_team_id, m.away_team_id))
        comps.add(m.competition.code if m.competition else "?")
    line = (f"scope[{label}]: teams={len(teams)}, games={len(games)}, "
            f"competitions={{{', '.join(sorted(comps))}}}")
    bad = []
    if comps - {NFL_COMPETITION_CODE}:
        bad.append("competitions={NFL}")
    if per_week:
        weeks: dict = {}
        for m in games:
            weeks.setdefault(m.matchday, []).append(m)
        parts = []
        for wk in sorted(weeks, key=lambda w: (w is None, w)):
            gs = weeks[wk]
            seen = [t for m in gs for t in (m.home_team_id, m.away_team_id)]
            byes = NFL_EXPECTED_TEAMS - len(set(seen))
            parts.append(f"W{wk if wk is not None else '?'} {len(gs)}g, byes={byes}")
            if len(seen) != len(set(seen)) or len(set(seen)) > NFL_EXPECTED_TEAMS:
                bad.append(f"week {wk}: teams = 32 − byes, each team once "
                           f"(saw {len(set(seen))} teams in {len(gs)} games)")
        if parts:
            line += " · " + "; ".join(parts)
    elif games and len(teams) != NFL_EXPECTED_TEAMS:
        bad.append(f"teams={NFL_EXPECTED_TEAMS}")
    if bad:
        line += f"  ⚠ SCOPE ALERT (expected {'; '.join(bad)})"
    return line


@dataclass
class _State:
    ratings: dict[int, float] = field(default_factory=dict)
    last_season: dict[int, str] = field(default_factory=dict)


def _expected_home(cfg: NFLEloConfig, st: _State, home_id: int, away_id: int) -> float:
    rh = st.ratings.get(home_id, cfg.default_rating) + cfg.home_advantage
    ra = st.ratings.get(away_id, cfg.default_rating)
    return 1.0 / (1.0 + 10 ** ((ra - rh) / 400.0))


def _update(cfg: NFLEloConfig, st: _State, home_id: int, away_id: int,
            season: str, home_score: int, away_score: int) -> None:
    # Per-team season regression: a club regresses when ITS new season
    # starts — the stream-interleaving-immune semantics (soccer lesson).
    for tid in (home_id, away_id):
        prev = st.last_season.get(tid)
        if prev is not None and prev != season:
            r = st.ratings.get(tid, cfg.default_rating)
            st.ratings[tid] = r + cfg.season_regression * (cfg.default_rating - r)
        st.last_season[tid] = season

    exp_h = _expected_home(cfg, st, home_id, away_id)
    actual_h = 1.0 if home_score > away_score else (0.5 if home_score == away_score else 0.0)
    margin = abs(home_score - away_score)
    rh = st.ratings.get(home_id, cfg.default_rating)
    ra = st.ratings.get(away_id, cfg.default_rating)
    elo_gap = (rh + cfg.home_advantage - ra) if actual_h >= 0.5 else (ra - rh - cfg.home_advantage)
    mov = math.log(margin + 1.0) * (cfg.mov_base / (cfg.mov_base + max(elo_gap, 0.0) * 0.001))
    delta = cfg.k_factor * mov * (actual_h - exp_h)
    st.ratings[home_id] = rh + delta
    st.ratings[away_id] = ra - delta


def _apply_variant(p: float, cap: float | None, shrink: float | None) -> float:
    """R-track variants (2026-09-17): confidence cap and/or logit shrink,
    applied at SCORING time only — ratings and updates are untouched, so
    every variant walks the identical stream."""
    if shrink is not None:
        z = math.log(p / (1 - p)) * shrink
        p = 1 / (1 + math.exp(-z))
    if cap is not None:
        p = min(max(p, 1 - cap), cap)
    return p


class Game(NamedTuple):
    """One stream row as the frozen protocol reads it (the walk's fields, plus the id and kickoff that order it)."""
    match_id: int
    utc_date: object
    season: str
    stage: str
    home_id: int
    away_id: int
    home_score: int
    away_score: int


WARMUP_SEASON = "2024"     # the frozen gate: warm-up (update only)
SCORED_SEASON = "2025"     # the frozen gate: scored (predict, then update)
LL_MARGIN = 0.010          # criterion (1): model log-loss <= baseline - 0.010
BAND_MIN_N = 30            # criterion (2): every 10pp band with n >= 30 ...
BAND_MAX_GAP = 0.07        # ... within 7pp


def is_preseason(stage: str | None) -> bool:
    return "pre" in (stage or "").lower()


def load_stream(label: str = "nfl-backtest", report=None) -> list[Game]:
    """The frozen protocol's stream: every FINISHED NFL row (nfl_scoped) with both scores, by kickoff then id,
    preseason excluded. Reports the scope line. Shared by nfl-backtest and nfl-v2-gate (addendum 215 item 3)."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus

    with session_scope() as s:
        games = list(s.execute(
            nfl_scoped(select(Match)).where(
                Match.status == MatchStatus.FINISHED,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
            ).order_by(Match.utc_date, Match.id)
        ).scalars())
        games = [m for m in games if not is_preseason(m.stage)]
        if report:
            report(scope_line(label, games))
        return [Game(m.id, m.utc_date, m.season, (m.stage or ""), m.home_team_id, m.away_team_id,
                     m.home_score, m.away_score) for m in games]


def split(rows: list[Game]) -> tuple[list[Game], list[Game]]:
    """(warm-up, scored): the 2024 rows and the 2025 rows, in stream order; no other season is walked."""
    rows = [r for r in rows if not is_preseason(r.stage)]  # preseason excluded
    return ([r for r in rows if r.season == WARMUP_SEASON], [r for r in rows if r.season == SCORED_SEASON])


def baseline_rate(warmup: list[Game]) -> float:
    """Baseline: constant home prob = warm-up realized home win rate (frozen)."""
    return sum(1 for r in warmup if r.home_score > r.away_score) / len(warmup)


def walk_protocol(warmup: list[Game], scored: list[Game], cfg: NFLEloConfig | None = None, price=None,
                  report=None) -> dict:
    """THE FROZEN PHASE-2 PROTOCOL (2026-09-09), unchanged: baseline = the warm-up's realized home rate; warm-up
    update only; scored predict-then-update; (1) mean log-loss <= baseline - 0.010; (2) every 10pp band with n >= 30
    within 7pp. `cfg` is the Elo walk's config (v1's NFLEloConfig by default); `price` maps the walk's home
    probability to the stated one at SCORING time only (identity by default; ratings and updates untouched). Reports
    the baseline, log-loss and n >= 30 band lines exactly as nfl-backtest always printed them. Both lists non-empty.
    Returns every figure unrounded, the bands (all, each marked gated when n >= 30) and the scored ids."""
    def say(msg: str) -> None:
        if report:
            report(msg)

    cfg = cfg or NFLEloConfig()
    st = _State()
    base_p = baseline_rate(warmup)
    say(f"baseline home prob (2024 realized): {base_p:.4f}")

    # Warm-up pass: update only.
    for g in warmup:
        _update(cfg, st, g.home_id, g.away_id, g.season, g.home_score, g.away_score)

    # Scored pass: predict-then-update.
    eps = 1e-12
    ll_model = ll_base = 0.0
    bands: dict[int, list[tuple[float, int]]] = {}
    for g in scored:
        p = _expected_home(cfg, st, g.home_id, g.away_id)
        if price is not None:
            p = price(p)
        y = 1 if g.home_score > g.away_score else 0  # ties count as home loss for scoring; rare
        ll_model += -(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)))
        ll_base += -(y * math.log(base_p) + (1 - y) * math.log(1 - base_p))
        band = int(min(max(p, 0.0), 0.9999) * 10)
        bands.setdefault(band, []).append((p, y))
        _update(cfg, st, g.home_id, g.away_id, g.season, g.home_score, g.away_score)

    n = len(scored)
    ll_model /= n
    ll_base /= n
    crit1 = ll_model <= ll_base - LL_MARGIN
    say(f"log-loss: model {ll_model:.4f} vs baseline {ll_base:.4f} "
        f"(need <= {ll_base - LL_MARGIN:.4f}) -> {'PASS' if crit1 else 'FAIL'}")

    crit2 = True
    out_bands = []
    for band in sorted(bands):
        obs = bands[band]
        stated = sum(p for p, _ in obs) / len(obs)
        realized = sum(y for _, y in obs) / len(obs)
        gap = abs(realized - stated)
        gated = len(obs) >= BAND_MIN_N
        ok = gap <= BAND_MAX_GAP
        out_bands.append({"band": band, "n": len(obs), "stated": stated, "realized": realized, "gap": gap,
                          "gated": gated, "ok": ok if gated else None})
        if not gated:
            continue
        crit2 = crit2 and ok
        say(f"  band {band*10}-{band*10+10}%: n={len(obs)} stated {stated:.3f} "
            f"realized {realized:.3f} gap {gap*100:.1f}pp -> {'ok' if ok else 'FAIL'}")
    return {"baseline_home_rate": base_p, "ll_model": ll_model, "ll_baseline": ll_base,
            "bar": ll_base - LL_MARGIN, "crit_logloss": crit1, "crit_bands": crit2, "pass": crit1 and crit2,
            "bands": out_bands, "n_scored": n, "scored_ids": [g.match_id for g in scored]}


def run_backtest(progress=None, cap: float | None = None,
                 shrink: float | None = None) -> dict:
    """Walk-forward per the frozen gate; returns verdict dict and prints it."""
    def report(msg: str) -> None:
        if progress:
            progress(msg)

    rows = load_stream("nfl-backtest", report)
    warmup, scored = split(rows)
    report(f"stream: {len(rows)} games (preseason excluded) — warm-up {len(warmup)} (2024), scored {len(scored)} (2025)")

    if not warmup or not scored:
        return {"ok": False, "reason": "insufficient seasons for protocol"}
    w = walk_protocol(warmup, scored, NFLEloConfig(), lambda p: _apply_variant(p, cap, shrink), report)
    verdict = w["pass"]
    report(f"GATE VERDICT: {'PASS — provenance/regression check: the live model still clears its frozen gate' if verdict else 'FAIL — REGRESSION: the live model no longer clears its frozen gate; investigate before the next predict-nfl'}")
    return {"ok": True, "pass": verdict, "ll_model": round(w["ll_model"], 4),
            "ll_baseline": round(w["ll_baseline"], 4), "scored_games": w["n_scored"]}
