"""
NFL v1 model + walk-forward backtest (phase 2, 2026-09-09).

THE GATE WAS WRITTEN FIRST — see BACKLOG "NFL PHASE 2 GATE". This module
implements exactly that protocol and prints a PASS/FAIL verdict against the
frozen numbers. Nothing here writes predictions; a pass earns a Week-2
dress rehearsal, nothing more.

Model: plain Elo with margin-of-victory multiplier (FiveThirtyEight-style),
self-contained on purpose (no dependency on the soccer Elo internals while
that module is under compression diagnosis). Win probability from rating
difference via the standard logistic. Preseason games are excluded from
both training and scoring — rotation noise (the EFL Trophy principle).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class NFLEloConfig:
    k_factor: float = 20.0
    home_advantage: float = 48.0      # Elo points ≈ ~2.5 pts spread
    season_regression: float = 0.25   # per-team, at ITS first game of a new season
    mov_base: float = 2.2             # margin multiplier: ln(|margin|+1) * base/(base + elo_gap*0.001)
    default_rating: float = 1500.0


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


def run_backtest(progress=None) -> dict:
    """Walk-forward per the frozen gate; returns verdict dict and prints it."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Sport

    def report(msg: str) -> None:
        if progress:
            progress(msg)

    cfg = NFLEloConfig()
    st = _State()

    with session_scope() as s:
        games = list(s.execute(
            select(Match).where(
                Match.sport == Sport.NFL,
                Match.status == MatchStatus.FINISHED,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
            ).order_by(Match.utc_date, Match.id)
        ).scalars())
        rows = [(m.home_team_id, m.away_team_id, m.season,
                 m.home_score, m.away_score,
                 (m.stage or "")) for m in games]

    rows = [r for r in rows if "pre" not in r[5].lower()]  # preseason excluded
    warmup = [r for r in rows if r[2] == "2024"]
    scored = [r for r in rows if r[2] == "2025"]
    report(f"stream: {len(rows)} games (preseason excluded) — warm-up {len(warmup)} (2024), scored {len(scored)} (2025)")

    # Baseline: constant home prob = warm-up realized home win rate (frozen).
    if not warmup or not scored:
        return {"ok": False, "reason": "insufficient seasons for protocol"}
    base_p = sum(1 for r in warmup if r[3] > r[4]) / len(warmup)
    report(f"baseline home prob (2024 realized): {base_p:.4f}")

    # Warm-up pass: update only.
    for h, a, season, hs, as_, _ in warmup:
        _update(cfg, st, h, a, season, hs, as_)

    # Scored pass: predict-then-update.
    eps = 1e-12
    ll_model = ll_base = 0.0
    bands: dict[int, list[tuple[float, int]]] = {}
    for h, a, season, hs, as_, _ in scored:
        p = _expected_home(cfg, st, h, a)
        y = 1 if hs > as_ else 0  # ties count as home loss for scoring; rare
        ll_model += -(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)))
        ll_base += -(y * math.log(base_p) + (1 - y) * math.log(1 - base_p))
        band = int(min(max(p, 0.0), 0.9999) * 10)
        bands.setdefault(band, []).append((p, y))
        _update(cfg, st, h, a, season, hs, as_)

    n = len(scored)
    ll_model /= n
    ll_base /= n
    crit1 = ll_model <= ll_base - 0.010
    report(f"log-loss: model {ll_model:.4f} vs baseline {ll_base:.4f} "
           f"(need <= {ll_base - 0.010:.4f}) -> {'PASS' if crit1 else 'FAIL'}")

    crit2 = True
    for band in sorted(bands):
        obs = bands[band]
        if len(obs) < 30:
            continue
        stated = sum(p for p, _ in obs) / len(obs)
        realized = sum(y for _, y in obs) / len(obs)
        gap = abs(realized - stated)
        ok = gap <= 0.07
        crit2 = crit2 and ok
        report(f"  band {band*10}-{band*10+10}%: n={len(obs)} stated {stated:.3f} "
               f"realized {realized:.3f} gap {gap*100:.1f}pp -> {'ok' if ok else 'FAIL'}")

    verdict = crit1 and crit2
    report(f"GATE VERDICT: {'PASS — Week-2 dress rehearsal earned' if verdict else 'FAIL — model does not ship'}")
    return {"ok": True, "pass": verdict, "ll_model": round(ll_model, 4),
            "ll_baseline": round(ll_base, 4), "scored_games": n}
