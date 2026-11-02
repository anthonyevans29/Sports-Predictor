"""
nfl-elo-v2: THE 2024-ONLY FIT FOR THE DECLARATION PROPOSAL (read-only). ARCHITECT 2026-11-02 10:35 ET, addendum 215
item 2 (in part, verbatim): "the candidate's one change is a calibration term fitted on the WARM-UP season only
(2024's own realized-vs-stated gap, never 2025's): the exact form Code proposes in the declaration PR from the 2024
walk (a probability shrink toward 0.5, or a smaller home advantage, one or the other, with its 2024-fitted value) — I
rule the form, the PR writes it before any 2025 figure is printed."

    nfl-v2-fit-warmup [--db COPY]
                        reads ONLY the 2024 NFL rows (the SQL selects season '2024'; a row of any other season the
                        query returns refuses the read), walks them predict-then-update with nfl_elo_v1's constants,
                        and prints, for EACH form, its 2024-fitted value with the method, and the 2024 bands (stated
                        vs realized) before and after the fitted term. It writes nothing, records nothing, and never
                        reads or prints a 2025 figure. --db reads a .backup copy through nfl-v2-gate's own --db
                        (outside data/, never created, mode=ro&immutable=1; addendum 219 item 6), so the fit's warm-up
                        fingerprint can be taken on the copy the run reads; without it, DATABASE_URL.

THE METHOD (ruled as built, addendum 219 item 2; the architect rules the form on 11-05):
    the 2024 walk   every 2024 non-preseason FINISHED NFL row with both scores, by kickoff then id (the gate's
                    warm-up, exactly), from default ratings (cold, as the gate's warm-up starts); each game priced
                    with the state before it, then updated (the predict-then-update walk of 215 item 2's "2024 walk";
                    the gate itself only updates on 2024). Ties count as home losses, as in the gate.
    shrink s        the s minimizing the mean log-loss of p' = 0.5 + s·(p − 0.5) over the 2024 walk's predictions
                    (price only: the walk's ratings are v1's whatever s is), searched on the grid s = 0.001 .. 1.500,
                    step 0.001 (a grid point where some p' leaves (0, 1) is skipped). The mean log-loss is convex in
                    s, so the grid minimum is the minimum to 0.001.
    home advantage  the h minimizing the mean log-loss of the 2024 walk re-run with home_advantage = h (price AND
                    update, the whole walk), on the grid h = 0.0 .. 120.0 Elo points, step 0.5.
    ties            the lowest mean log-loss; equal → the grid point nearest v1's value (s = 1, h = 48.0).
    the direction   a fitted s > 1 (an expansion, which nfl-v2-gate does not accept) or h >= 48.0 (not smaller) is
                    printed and flagged, never clamped: the architect reads it.
    the edge        a fitted value on a grid end is printed AT THE GRID EDGE (the true minimum may lie beyond).
    in-sample       both are fitted and scored on the same 2024 games: the "after" bands are in-sample by design
                    (2024's own realized-vs-stated gap); they say nothing about 2025.
"""
from __future__ import annotations

import math
from dataclasses import replace

from src.walters import nfl_backtest as nb
from src.walters import nfl_v2_gate as v2

SEASON = nb.WARMUP_SEASON          # "2024": the only season this module ever selects
S_GRID = [k / 1000 for k in range(1, 1501)]
H_GRID = [k / 2 for k in range(0, 241)]
EPS = 1e-12


class FitRefused(RuntimeError):
    pass


def load_warmup(report=None, session=None) -> list[nb.Game]:
    """The 2024 warm-up rows ONLY: the gate's stream query (nfl_backtest's selection) with season = '2024' in the
    SQL itself, so no row of another season is ever read; preseason excluded. A returned row of another season
    refuses (a guard, never expected). `session`: the --db copy's read-only session (nfl_backtest.read_session), else
    the app's."""
    from sqlalchemy import select

    from src.db.schema import Match, MatchStatus

    with nb.read_session(session) as s:
        games = list(s.execute(
            nb.nfl_scoped(select(Match)).where(
                Match.season == SEASON,
                Match.status == MatchStatus.FINISHED,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
            ).order_by(Match.utc_date, Match.id)
        ).scalars())
        games = [m for m in games if not nb.is_preseason(m.stage)]
        if report:
            report(nb.scope_line("nfl-v2-fit-warmup", games))
        rows = [nb.Game(m.id, m.utc_date, m.season, (m.stage or ""), m.home_team_id, m.away_team_id,
                        m.home_score, m.away_score) for m in games]
        if session is None:
            s.rollback()
    bad = sorted({r.season for r in rows if r.season != SEASON})
    if bad:
        raise FitRefused(f"the 2024 read returned rows of season(s) {bad}: refused, nothing printed")
    return rows


def walk(rows, cfg: nb.NFLEloConfig | None = None) -> list[tuple[float, int]]:
    """Predict-then-update over `rows` from default ratings: [(the walk's home probability, home win 1/0)]."""
    cfg = cfg or nb.NFLEloConfig()
    st = nb._State()
    out = []
    for g in rows:
        out.append((nb._expected_home(cfg, st, g.home_id, g.away_id), 1 if g.home_score > g.away_score else 0))
        nb._update(cfg, st, g.home_id, g.away_id, g.season, g.home_score, g.away_score)
    return out


def mean_ll(pairs) -> float:
    return sum(-(y * math.log(max(p, EPS)) + (1 - y) * math.log(max(1 - p, EPS))) for p, y in pairs) / len(pairs)


def shrunk(pairs, s: float):
    return [(0.5 + s * (p - 0.5), y) for p, y in pairs]


def _argmin(cands, ref: float) -> tuple[float, float]:
    """(value, mean log-loss): the lowest log-loss; ties to the value nearest `ref`."""
    return min(cands, key=lambda c: (c[1], abs(c[0] - ref)))


def fit_shrink(pairs) -> dict:
    cands = []
    for s in S_GRID:
        q = shrunk(pairs, s)
        if all(0.0 < p < 1.0 for p, _ in q):
            cands.append((s, mean_ll(q)))
    s, ll = _argmin(cands, 1.0)
    return {"value": s, "ll": ll, "grid": (S_GRID[0], S_GRID[-1], 0.001),
            "at_edge": s in (S_GRID[0], S_GRID[-1]), "pairs": shrunk(pairs, s)}


def fit_home_advantage(rows) -> dict:
    base = nb.NFLEloConfig()
    cands = [(h, mean_ll(walk(rows, replace(base, home_advantage=h)))) for h in H_GRID]
    h, ll = _argmin(cands, base.home_advantage)
    return {"value": h, "ll": ll, "grid": (H_GRID[0], H_GRID[-1], 0.5),
            "at_edge": h in (H_GRID[0], H_GRID[-1]), "pairs": walk(rows, replace(base, home_advantage=h))}


def bands(pairs) -> list[dict]:
    """Every 10pp band of the stated probability (the gate's banding): n, stated, realized, gap, n >= 30."""
    by: dict[int, list] = {}
    for p, y in pairs:
        by.setdefault(int(min(max(p, 0.0), 0.9999) * 10), []).append((p, y))
    out = []
    for b in sorted(by):
        obs = by[b]
        st = sum(p for p, _ in obs) / len(obs)
        re_ = sum(y for _, y in obs) / len(obs)
        out.append({"band": b, "n": len(obs), "stated": st, "realized": re_, "gap": re_ - st,
                    "n30": len(obs) >= nb.BAND_MIN_N})
    return out


def fit(rows) -> dict:
    """Pure over the 2024 rows. Refuses a row of another season (the guard) and an empty season."""
    if any(r.season != SEASON for r in rows):
        raise FitRefused("a row of a season other than 2024 reached the fit: refused, nothing printed")
    if not rows:
        raise FitRefused("no 2024 warm-up row is stored: nothing to fit")
    v1 = walk(rows)
    rate = nb.baseline_rate(rows)
    return {"n": len(rows), "by_stage": v2._by(rows, lambda r: r.stage or "(none)"),
            "warmup_fingerprint": v2.warmup_fingerprint(rows)[0],
            "baseline_home_rate": rate, "ll_baseline": mean_ll([(rate, y) for _, y in v1]),
            "ll_v1": mean_ll(v1), "bands_v1": bands(v1),
            "shrink": fit_shrink(v1), "home_advantage": fit_home_advantage(rows)}


def _band_lines(bs) -> list[str]:
    return [f"      {b['band'] * 10:>2}-{b['band'] * 10 + 10}%: n {b['n']:>3} · stated {b['stated']:.3f} · realized "
            f"{b['realized']:.3f} · realized − stated {b['gap'] * 100:+.1f}pp" + ("" if b["n30"] else " (n < 30)")
            for b in bs]


def fit_lines(r: dict, scope: str | None = None) -> list[str]:
    cfg = nb.NFLEloConfig()
    L = [f"NFL-ELO-V2 · THE 2024 FIT (read-only; 2024 rows only, no 2025 row is selected; {v2.RULING})"]
    if scope:
        L.append(f"  {scope}")
    L.append(f"  2024 walk: {r['n']} games (non-preseason FINISHED NFL, both scores; by stage "
             + ", ".join(f"{k} {n}" for k, n in r["by_stage"].items())
             + f") · predict-then-update from default ratings with nfl_elo_v1's constants (k {cfg.k_factor}, home "
             f"advantage {cfg.home_advantage}, season regression {cfg.season_regression}, mov base {cfg.mov_base}, "
             f"default {cfg.default_rating})")
    L.append(f"  warm-up fingerprint {r['warmup_fingerprint']} (the 2024 rows the fit read; the gate's --preflight "
             "compares it with the one the entry records)")
    L.append(f"  2024 in-sample: v1 mean log-loss {r['ll_v1']:.6f} · the constant 2024 home rate "
             f"{r['baseline_home_rate']:.6f}: log-loss {r['ll_baseline']:.6f}")
    L.append("  v1's 2024 bands (stated vs realized):")
    L += _band_lines(r["bands_v1"])
    s, h = r["shrink"], r["home_advantage"]
    L.append(f"  FORM shrink: s = {s['value']:.3f} · method: the s minimizing the 2024 walk's mean log-loss of "
             f"p' = 0.5 + s·(p − 0.5) (price only), grid {s['grid'][0]}..{s['grid'][1]} step {s['grid'][2]}, ties to "
             f"the nearest 1 · 2024 mean log-loss {s['ll']:.6f} (v1 {r['ll_v1']:.6f})"
             + (" · AT THE GRID EDGE" if s["at_edge"] else "")
             + (" · s > 1 is an EXPANSION away from 0.5, not a shrink: the gate accepts 0 < s < 1 and refuses this "
                "value (the architect reads this line)" if s["value"] > 1 else "")
             + (" · s = 1 is nfl_elo_v1 unchanged, no shrink: the gate accepts 0 < s < 1 and refuses this value (the "
                "architect reads this line)" if s["value"] == 1 else ""))
    L += _band_lines(bands(s["pairs"]))
    L.append(f"  FORM home advantage: h = {h['value']:.1f} Elo points (v1 {cfg.home_advantage}) · method: the h "
             f"minimizing the mean log-loss of the 2024 walk re-run with home_advantage = h (price and update), grid "
             f"{h['grid'][0]}..{h['grid'][1]} step {h['grid'][2]}, ties to the nearest {cfg.home_advantage} · 2024 "
             f"mean log-loss {h['ll']:.6f} (v1 {r['ll_v1']:.6f})" + (" · AT THE GRID EDGE" if h["at_edge"] else "")
             + (f" · h >= v1's {cfg.home_advantage}: not a smaller home advantage: the gate accepts 0 <= h < "
                f"{cfg.home_advantage} and refuses this value (the architect reads this line)"
                if h["value"] >= cfg.home_advantage else ""))
    L += _band_lines(bands(h["pairs"]))
    L.append("  in-sample on 2024 by design (215 item 2: \"2024's own realized-vs-stated gap, never 2025's\"); no "
             "2025 figure is read or printed. The architect rules the form; the declaration writes it.")
    L.append("FIT only: nothing written, nothing reserved, nothing recorded.")
    return L


def fit_read(db=None) -> list[str]:
    """The fit's one read: the 2024 rows from the --db copy when given (nfl_v2_gate.check_db / db_session, the gate's
    own --db, addendum 219 item 6), else DATABASE_URL; then fit(). A --db refusal is a FitRefused."""
    try:
        path = v2.check_db(db) if db is not None else None
    except v2.GateRefused as e:
        raise FitRefused(str(e))
    scope: list[str] = []
    with v2.db_session(path) as s:
        rows = load_warmup(scope.append, session=s)
    return fit_lines(fit(rows), v2._scope(scope, path))
