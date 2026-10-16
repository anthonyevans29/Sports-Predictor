"""
ncaa-elo-v2 D1: THE FIT OF THE LOGISTIC SCALE s. GATE-CLASS (the fit freezes a model parameter). ARCHITECT 2026-10-16,
addendum 81 item 2, D1 (verbatim): "Candidate: NCAAEloV1's structure and constants (k_factor 24, home_advantage 55,
mov_base 2.2, season_regression 0.25, default_rating 1500, neutral rule no_home_advantage_at_neutral) with ONE fitted
parameter: the logistic scale s in P(home) = 1 / (1 + 10^(-(dr + ha) / s)), fitted by maximum likelihood on the 2024
and 2025 regular-season games of the stream (D2) and then frozen; v1 is s = 400. Code's PR prints the fitted s, the
fit's log-likelihood curve at s = 300..500 by 25, and the slope b that the fitted s gives on 2025 (a read of the
training set, reported, not a gate). Nothing else is fitted."

THE PROCEDURE, declared here before any fit is run (docs/specs/ncaa-elo-v2.md, "The fit of s"):
  * The model: the shared D1 wrapper with s (ncaa_backtest.NeutralRuleElo(scale=s) over ncaa_elo.NCAAEloV2): s
    replaces 400 in the stated P(home) and nowhere else. PRICE ONLY (ARCHITECT 2026-10-16, addendum 86 item 3, Q1,
    verbatim): "s enters the stated probability and nothing else; the update keeps v1's expected score at /400, so
    the ratings walk exactly as NCAAEloV1's do and v1r's ratings are v2's ratings."
  * The games: the D2 stream's 2024 and 2025 games (training_games), in stream order: every one is walked (predict,
    then update; postseason and a game without a season_type are walked); the likelihood is over the games whose
    season_type is exactly 'regular'. No 2026 game is walked or read: the command loads the labels of 2024 and 2025
    only (ncaa_backtest.load_v1r_games(seasons), Codex on #553), and fit() refuses any game outside 2024 and 2025.
    fit() also refuses unless EACH of 2024 and 2025 has a 'regular' game in the likelihood (Codex on #553): D1 fits on
    both seasons, never on one.
  * The likelihood of s: the sum of log P(result) over those games, each priced before its own update by a fresh
    model walking from the first 2024 game (a cold start: v1r's stream starts in 2024); p clipped as
    ncaa_backtest._ll clips it (1e-12).
  * The search: s on the grid BRACKET[0]..BRACKET[1] by GRID_STEP; the best grid value (an exact tie goes to the value
    nearer 400); then a golden-section search for the maximum within one grid step either side of it (inside the
    bracket) until the interval is narrower than TOL; the fitted s is the best of the points evaluated. A best grid
    value on an end of the bracket is printed ON THE BRACKET EDGE: the bracket is not widened after the fact; the
    architect rules.
  * Frozen: the fitted s exactly as printed (Python's repr, which round-trips), written into the registry entry
    (ncaa-elo-v2, logistic_scale.s) by the declaration PR with the training fingerprint the fit read.

Read-only: reads the stored 2024 and 2025 games and the registry; writes nothing; reads no 2026 label or score.
"""
from __future__ import annotations

import math

from src.walters import ncaa_backtest as nb
from src.walters import ncaa_v1r_gate as vg

BRACKET = (100.0, 1000.0)
GRID_STEP = 5.0
TOL = 1e-6
CURVE = tuple(300.0 + 25.0 * i for i in range(9))      # D1: "s = 300..500 by 25"
V1_SCALE = 400.0
REPRODUCE_TOL = 1e-9
_PHI = (math.sqrt(5.0) - 1.0) / 2.0


class FitRefused(RuntimeError):
    """A precondition of the fit is not met: printed with its reason, exit 2; nothing read past it."""


def walk(train, scale: float, spec: vg.Spec = vg.V2) -> dict:
    """One walk of the training games at logistic scale `scale`: predict, then update, every game in order; the
    'regular' games' log-likelihood and their (p, y) pairs by season. Refuses any game outside the training seasons
    (no 2026 game is read). Pure."""
    bad = sorted({g.season for g in train if g.season not in spec.warmup})
    if bad:
        raise FitRefused(f"the fit reads {', '.join(spec.warmup)} only; given games of {', '.join(bad)}")
    m = nb.NeutralRuleElo(scale=scale)
    ll, n, pairs = 0.0, 0, {}
    for g in train:
        if g.season_type == vg.REGULAR:
            p = m.predict(g)
            ll -= nb._ll(p, g.home_win)
            n += 1
            pairs.setdefault(g.season, []).append((p, g.home_win))
        m.update(g)
    return {"s": scale, "ll": ll, "n": n, "pairs": pairs}


def check_training(train, spec: vg.Spec = vg.V2) -> dict[str, int]:
    """Refuses (FitRefused) a game outside the training seasons, and a training season with no 'regular' game: the
    likelihood is over BOTH seasons' 'regular' games (D1), so a season contributing none is refused, never fitted on
    the other alone (Codex on #553). Returns the 'regular' count per training season. Pure."""
    bad = sorted({g.season for g in train if g.season not in spec.warmup})
    if bad:
        raise FitRefused(f"the fit reads {', '.join(spec.warmup)} only; given games of {', '.join(bad)}")
    n = {s_: sum(1 for g in train if g.season == s_ and g.season_type == vg.REGULAR) for s_ in spec.warmup}
    empty = [s_ for s_, k in n.items() if k == 0]
    if empty:
        raise FitRefused(f"no '{vg.REGULAR}' game of {', '.join(empty)} in the training stream: D1 fits s on the "
                         f"{' and '.join(spec.warmup)} '{vg.REGULAR}' games, so nothing is fitted on fewer seasons")
    return n


def grid() -> list[float]:
    k = int(round((BRACKET[1] - BRACKET[0]) / GRID_STEP))
    return [BRACKET[0] + GRID_STEP * i for i in range(k + 1)]


def fit(train, spec: vg.Spec = vg.V2) -> dict:
    """The declared search (module docstring). Returns the fitted s, its log-likelihood, the grid's best value, the
    bracket-edge flag, the number of walks, and the 'regular' count. Refuses as check_training does, before any walk.
    Pure (but walks the training games ~220 times)."""
    check_training(train, spec)
    lls = {}

    def f(s_):
        if s_ not in lls:
            lls[s_] = walk(train, s_, spec)["ll"]
        return lls[s_]

    g_vals = grid()
    for s_ in g_vals:
        f(s_)
    best_ll = max(lls[s_] for s_ in g_vals)
    g_best = min((s_ for s_ in g_vals if lls[s_] == best_ll), key=lambda s_: (abs(s_ - V1_SCALE), s_))
    edge = g_best in (BRACKET[0], BRACKET[1])
    lo, hi = max(BRACKET[0], g_best - GRID_STEP), min(BRACKET[1], g_best + GRID_STEP)
    c, d = hi - _PHI * (hi - lo), lo + _PHI * (hi - lo)
    while hi - lo >= TOL:
        if f(c) >= f(d):
            hi, d = d, c
            c = hi - _PHI * (hi - lo)
        else:
            lo, c = c, d
            d = lo + _PHI * (hi - lo)
    s_hat = max(lls, key=lambda s_: (lls[s_], -abs(s_ - V1_SCALE)))
    return {"s": s_hat, "ll": lls[s_hat], "grid_best": g_best, "grid_best_ll": best_ll, "on_bracket_edge": edge,
            "walks": len(lls), "n": sum(1 for g in train if g.season_type == vg.REGULAR)}


def curve(train, spec: vg.Spec = vg.V2) -> list[dict]:
    """D1: the log-likelihood at s = 300..500 by 25 (and the mean log-loss it implies)."""
    out = []
    for s_ in CURVE:
        w = walk(train, s_, spec)
        out.append({"s": s_, "ll": w["ll"], "n": w["n"], "mean_log_loss": -w["ll"] / w["n"] if w["n"] else None})
    return out


def slope_on(train, scale: float, season: str, spec: vg.Spec = vg.V2) -> dict:
    """D1: "the slope b that the fitted s gives on 2025": D5 (3)'s fit (ncaa_backtest.logistic_slope) over the
    'regular' games of `season` as the walk at `scale` priced them. Reported, never a gate."""
    pairs = walk(train, scale, spec)["pairs"].get(season, [])
    a, b = nb.logistic_slope(pairs) if pairs else (None, None)
    return {"season": season, "n": len(pairs), "a": a, "b": b}


def compute(v, entry: dict | None, v1r_entry: dict | None, spec: vg.Spec = vg.V2, later: int | None = None) -> dict:
    """The fit's printout over a loaded D2 stream: the training games (2024 and 2025 only), the fit, the curve, the
    slope on 2025 at the fitted s, and two checks against v1r's recorded run (its stream fingerprint, and b at
    s = 400 on 2025). `later`: the later-season games kicking off before the last 2025 game, as run() counts them
    from the store without reading a score (its stream holds 2024 and 2025 only); None = counted from `v` (a stream
    that holds later seasons). Pure."""
    train = vg.training_games(v.games, spec)
    tfp, tn = vg.training_fingerprint(v.games, spec)
    ft = fit(train, spec)
    last = spec.warmup[-1]
    res = (v1r_entry or {}).get("run") or {}
    res = res.get("result") or {}
    v1r_fp = vg.stream_fingerprint(v.games, vg.V1R)[0]
    at400 = slope_on(train, V1_SCALE, last, spec)
    frozen, _why = vg.scale_state(spec, entry)
    return {"training_games": tn, "training_fingerprint": tfp,
            "by_season": {s_: sum(1 for g in train if g.season == s_) for s_ in spec.warmup},
            "regular_by_season": {s_: sum(1 for g in train if g.season == s_ and g.season_type == vg.REGULAR)
                                  for s_ in spec.warmup},
            "later_walked_before": (later if later is not None else
                                    sum(1 for g in vg.walked(v.games, vg.V1R.gate) if g.season not in spec.warmup)),
            "fit": ft, "curve": curve(train, spec), "slope": slope_on(train, ft["s"], last, spec),
            "at_400": at400, "v1r_recorded_b": res.get("slope_b"),
            "v1r_recorded_fingerprint": res.get("stream_fingerprint"), "v1r_fingerprint_today": v1r_fp,
            "frozen": frozen}


def lines(c: dict, spec: vg.Spec = vg.V2) -> list[str]:
    ft, sl, a4 = c["fit"], c["slope"], c["at_400"]
    seasons = " and ".join(spec.warmup)
    L = [f"{spec.title} · THE FIT OF s (D1: maximum likelihood on the {seasons} '{vg.REGULAR}' games of the stream, "
         f"then frozen; v1 is s = 400) · reads {seasons} only: no {spec.gate.test} game is walked or read",
         f"  training stream: {c['training_games']} games walked ("
         + ", ".join(f"{s_} {n}" for s_, n in c["by_season"].items()) + ") · in the likelihood: "
         + ", ".join(f"{s_} {n}" for s_, n in c["regular_by_season"].items()) + f" '{vg.REGULAR}' games · "
         f"training fingerprint {c['training_fingerprint']}",
         f"  search (declared before any fit): s on {BRACKET[0]:g}..{BRACKET[1]:g} by {GRID_STEP:g}, then golden-section "
         f"within one step of the best grid value to {TOL:g}; {ft['walks']} walks · best grid value "
         f"{ft['grid_best']:g} (log-likelihood {ft['grid_best_ll']:.6f})"
         + (" · ON THE BRACKET EDGE: the bracket is not widened after the fact; the architect rules"
            if ft["on_bracket_edge"] else ""),
         f"  CURVE (D1: s = 300..500 by 25; log-likelihood over the {ft['n']} '{vg.REGULAR}' games, and the mean "
         "log-loss it implies):"]
    for p in c["curve"]:
        L.append(f"    s {p['s']:>5.0f} · log-likelihood {p['ll']:.6f} · mean log-loss "
                 + (f"{p['mean_log_loss']:.6f}" if p["mean_log_loss"] is not None else "—"))
    L.append(f"  FITTED s = {ft['s']!r} · log-likelihood {ft['ll']:.6f} · mean log-loss "
             + (f"{-ft['ll'] / ft['n']:.6f}" if ft["n"] else "—"))
    L.append(f"  slope b on {sl['season']} at the fitted s: "
             + (f"{sl['b']:.6f} (intercept a {sl['a']:.6f})" if sl["b"] is not None else "— (did not converge)")
             + f" over {sl['n']} '{vg.REGULAR}' games — a read of the training set, reported, not a gate (D1)")
    rb = c["v1r_recorded_b"]
    same_b = rb is not None and a4["b"] is not None and abs(a4["b"] - rb) <= REPRODUCE_TOL
    same_fp = c["v1r_recorded_fingerprint"] is not None and c["v1r_recorded_fingerprint"] == c["v1r_fingerprint_today"]
    L.append(f"  CHECK against v1r's recorded run: at s = 400, b on {a4['season']} "
             + (f"{a4['b']:.6f}" if a4["b"] is not None else "—")
             + f" vs recorded {rb!r} -> {'REPRODUCED' if same_b else 'NOT REPRODUCED'} · v1r's stream fingerprint "
             f"today {c['v1r_fingerprint_today']} vs recorded {c['v1r_recorded_fingerprint']} -> "
             + ("SAME" if same_fp else "CHANGED"))
    L.append(f"  later-season games kicking off before the last {spec.warmup[-1]} game: {c['later_walked_before']} "
             f"(v1r's walk updated on any such game; this fit reads {seasons} only; 0 expected, and both checks "
             "above assume it)")
    L.append("  frozen in the registry entry: " + (repr(c["frozen"]) if c["frozen"] is not None else
                                                  "not yet — the declaration PR freezes the FITTED s above"))
    L.append(f"FIT ONLY: nothing scored on {spec.gate.test}, nothing reserved, nothing recorded, nothing written.")
    return L


def run(spec: vg.Spec = vg.V2) -> dict:
    """The command's read: the declared entry (any status), the training seasons covered (L2 + L3), one read of the
    2024 and 2025 labels only (no other season's label or score is loaded, Codex on #553) and the count of later-
    season games before the last 2025 game (kickoffs and stamps only), then compute(). Refuses (FitRefused) an
    unscaled declaration, an absent entry, a training season not covered, or one without a 'regular' game."""
    from src.walters import registry as reg

    if not spec.scaled:
        raise FitRefused(f"{spec.eid} fits nothing (its constants are a priori): only a scaled declaration has an s")
    e = reg.get(spec.eid, reg.LEDGER)
    if e is None:
        raise FitRefused(f"{spec.eid} is not declared in docs/registry: the fit follows the declaration")
    try:
        vg.require_coverage(vg.coverage(spec.warmup), spec.warmup, "the fit of s")
    except vg.GateRefused as err:
        raise FitRefused(str(err))
    v = nb.load_v1r_streams((spec.warmup,), nb.load_v1r_games(spec.warmup))[0]
    last = [g.utc_date for g in v.games if g.season == vg.V1R.gate.test]
    later_seasons = [s_ for s_ in vg.V1R.seasons if s_ not in spec.warmup]          # v1r's stream's later season: 2026
    later = nb.count_current_labels_before(last[-1], later_seasons) if last else 0
    return compute(v, e, reg.get(vg.EID, reg.LEDGER), spec, later=later)
