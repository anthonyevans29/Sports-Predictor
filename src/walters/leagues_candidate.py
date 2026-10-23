"""
THE FOUR LEAGUES' CANDIDATE PATH AND ITS PARITY RECEIPT (ARCHITECT 2026-10-23, addendum 158 item 2(a); lane leagues,
#322). Read-only.

Verbatim: "(a) PARITY RULING — what "the current constants, trained to 2025/26, frozen" means in code: the candidate per
league is the expansion gate's own walk as ruled (soccer_expansion: a cold start per league-season, F3 regular rounds
only, F5 same-kickoff batching, the production rho and Elo coefficient, nothing fitted), run prospectively on 2026/27:
the state at each fixture is the walk over that league's FINISHED 2026/27 games before it. The prospective prediction
path must BE that walk: a parity receipt per league (the shadow's probabilities for this season's finished games equal
the gate path's, row for row) comes with receipt 4(a) by 10-30. Every row keeps the candidate id, the code sha, the
input cutoff and the prediction stamp. The confirmation criterion is declared now: 60 more qualifying games at the same
bar, independently per league."

- predict_as_of: the PROSPECTIVE path for one fixture. The state is rebuilt from a cold start over the league-season's
  FINISHED rows with both scores and a kickoff STRICTLY before the fixture's (the gate's F5 predicate: a same-kickoff
  game never feeds another), regular rounds only (soccer_expansion.is_regular, F3), Elo updated game by game in kickoff
  order (soccer_backtest.update_after_match, EloConfig()), strengths estimated from those rows
  (soccer_backtest.estimate_strengths), then soccer_backtest.predict_match with the production rho and Elo
  coefficient. Unpriced, as the walk leaves a game unscored, when fewer than MIN_PRIOR rows precede it or a team has no
  strength. Nothing is fitted.
- gate_rows: the GATE path, soccer_backtest.run_soccer_backtest itself, as the expansion gate calls it (MIN_PRIOR,
  stage_filter=is_regular, batch_same_kickoff=True, the same rho and coefficient), on the 2026/27 season.
- parity: both paths on every finished 2026/27 game of the league: a row per game the gate scored, its three
  probabilities from each path and their largest absolute difference; games one path prices and the other does not
  are counted apart. Equal means a difference no larger than PARITY_TOL (floating-point summation order only).
- legacy_shadow: the probabilities the CURRENT shadow export (soccer_expansion.price_upcoming's arithmetic, read as of
  each game's kickoff: every stage, no same-kickoff batching, strengths from all finished games before it) would give
  the same games, against the gate path: reported as a finding, never used.
Every parity row carries the candidate id (CANDIDATE: the walk, prospective on 2026/27, until the declaration names
it), the code sha (git, short; None when git cannot say), the input cutoff (the game's kickoff: the latest input it
may read) and the prediction stamp (the receipt's own clock).
"""
from __future__ import annotations

import dataclasses
import subprocess
from datetime import datetime

from src.walters.soccer_expansion import CURRENT_SEASON, MIN_PRIOR, is_regular

CANDIDATE = "soccer-expansion-v1 walk, prospective on 2026/27 (undeclared: 158 item 2(c) declares it per league)"
PARITY_TOL = 1e-12


def code_sha() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def production_poisson():
    """(version, rho, elo_goal_coeff) of the production soccer model, as cli._soccer_prod_poisson resolves it; None
    when there is no production model (never faked)."""
    from src.db.database import session_scope
    from src.db.schema import Sport
    from src.models.poisson import PoissonConfig
    from src.walters.training import _resolve_model_version
    try:
        with session_scope() as s:
            mv = _resolve_model_version(s, None, Sport.SOCCER)
            pz = {**PoissonConfig().as_dict(), **((mv.parameters or {}).get("poisson") or {})}
            out = mv.version, float(pz["dixon_coles_rho"]), float(pz["elo_goal_coeff"])
            s.rollback()
            return out
    except Exception:  # noqa: BLE001 - no production model: None, labelled by the caller
        return None


def _season_rows(s, code: str, season: str):
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus
    c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
    if c is None:
        return []
    rows = [m for m in s.execute(select(Match).where(Match.competition_id == c.id, Match.season == season,
                                                     Match.status == MatchStatus.FINISHED)).scalars()
            if m.utc_date and m.home_score is not None and m.away_score is not None]
    rows.sort(key=lambda m: m.utc_date)
    return rows


def predict_as_of(rows, fixture, rho: float, coeff: float):
    """The prospective prediction for `fixture` from the finished regular-round rows strictly before its kickoff, or
    (None, why). `rows`: the league-season's finished rows (any order)."""
    from src.walters import soccer_backtest as sb
    prior = sorted((m for m in rows if is_regular(m.stage) and m.utc_date < fixture.utc_date and m.id != fixture.id),
                   key=lambda m: m.utc_date)
    if len(prior) < MIN_PRIOR:
        return None, "below_min_prior"
    elo = sb.EloState(config=sb.EloConfig())
    for m in prior:
        nh, na = sb.update_after_match(elo.get(m.home_team_id), elo.get(m.away_team_id), m.home_score, m.away_score,
                                       elo.config)
        elo.set(m.home_team_id, nh)
        elo.set(m.away_team_id, na)
    ctx = sb.CompetitionScoringContext()
    st = sb.estimate_strengths([{"home_team_id": p.home_team_id, "away_team_id": p.away_team_id,
                                 "home_score": p.home_score, "away_score": p.away_score} for p in prior], ctx)
    hs, as_ = st.get(fixture.home_team_id), st.get(fixture.away_team_id)
    if not (hs and as_):
        return None, "no_strength"
    cfg = dataclasses.replace(sb.PoissonConfig(), dixon_coles_rho=rho, elo_goal_coeff=coeff)
    return sb.predict_match(home_elo=elo.get(fixture.home_team_id), away_elo=elo.get(fixture.away_team_id),
                            home_strength=hs, away_strength=as_, context=ctx, config=cfg), None


def legacy_shadow(rows, fixture, rho: float, coeff: float):
    """soccer_expansion.price_upcoming's arithmetic for `fixture`, read as of its kickoff (every stage, no batching,
    Elo over every finished row before it, strengths from them all): the current shadow's number, for the finding."""
    from src.walters import soccer_backtest as sb
    done = sorted((m for m in rows if m.utc_date < fixture.utc_date and m.id != fixture.id), key=lambda m: m.utc_date)
    if len(done) < MIN_PRIOR:
        return None
    elo = sb.EloState(config=sb.EloConfig())
    for m in done:
        nh, na = sb.update_after_match(elo.get(m.home_team_id), elo.get(m.away_team_id), m.home_score, m.away_score,
                                       elo.config)
        elo.set(m.home_team_id, nh)
        elo.set(m.away_team_id, na)
    ctx = sb.CompetitionScoringContext()
    st = sb.estimate_strengths([{"home_team_id": p.home_team_id, "away_team_id": p.away_team_id,
                                 "home_score": p.home_score, "away_score": p.away_score} for p in done], ctx)
    hs, as_ = st.get(fixture.home_team_id), st.get(fixture.away_team_id)
    if not (hs and as_):
        return None
    cfg = dataclasses.replace(sb.PoissonConfig(), dixon_coles_rho=rho, elo_goal_coeff=coeff)
    return sb.predict_match(home_elo=elo.get(fixture.home_team_id), away_elo=elo.get(fixture.away_team_id),
                            home_strength=hs, away_strength=as_, context=ctx, config=cfg)


def gate_rows(code: str, season: str, rho: float, coeff: float) -> list[dict]:
    """The gate path: run_soccer_backtest exactly as soccer_expansion.run calls it, on `season`."""
    from src.walters.soccer_backtest import run_soccer_backtest
    from src.walters.soccer_expansion import BATCH_SAME_KICKOFF
    return run_soccer_backtest(code, season, MIN_PRIOR, dixon_coles_rho=rho, elo_goal_coeff=coeff,
                               stage_filter=is_regular, batch_same_kickoff=BATCH_SAME_KICKOFF) or []


def parity(code: str, rho: float, coeff: float, season: str = CURRENT_SEASON, now: datetime | None = None) -> dict:
    """The parity receipt for one league (the module docstring). Read-only: one session, rolled back."""
    from src.db.database import session_scope
    from src.timeutil import utc_now_naive
    now = now or utc_now_naive()
    sha = code_sha()
    gate = {r["match_id"]: r for r in gate_rows(code, season, rho, coeff)}
    out = {"code": code, "season": season, "gate_scored": len(gate), "rows": [], "max_diff": 0.0, "unequal": 0,
           "shadow_only": [], "gate_only": [], "legacy_max_diff": 0.0, "legacy_unequal": 0, "legacy_unpriced": 0}
    with session_scope() as s:
        rows = _season_rows(s, code, season)
        regular = [m for m in rows if is_regular(m.stage)]
        for m in regular:
            pred, why = predict_as_of(rows, m, rho, coeff)
            g = gate.get(m.id)
            if pred is None and g is None:
                continue
            if g is None:
                out["shadow_only"].append(m.id)
                continue
            if pred is None:
                out["gate_only"].append((m.id, why))
                continue
            diff = max(abs(pred.p_home - g["p_home"]), abs(pred.p_draw - g["p_draw"]), abs(pred.p_away - g["p_away"]))
            out["max_diff"] = max(out["max_diff"], diff)
            out["unequal"] += diff > PARITY_TOL
            leg = legacy_shadow(rows, m, rho, coeff)
            if leg is None:
                out["legacy_unpriced"] += 1
            else:
                ld = max(abs(leg.p_home - g["p_home"]), abs(leg.p_draw - g["p_draw"]), abs(leg.p_away - g["p_away"]))
                out["legacy_max_diff"] = max(out["legacy_max_diff"], ld)
                out["legacy_unequal"] += ld > PARITY_TOL
            out["rows"].append({"match_id": m.id, "candidate": CANDIDATE, "code_sha": sha, "input_cutoff": m.utc_date,
                                "prediction_stamp": now, "shadow": (pred.p_home, pred.p_draw, pred.p_away),
                                "gate": (g["p_home"], g["p_draw"], g["p_away"]), "diff": diff})
        out["finished_regular"] = len(regular)
        out["not_regular"] = len(rows) - len(regular)
        s.rollback()
    return out


def parity_lines(p: dict, rows: bool = True) -> list[str]:
    head = (f"{p['code']} {p['season']} · PARITY (158 item 2(a)) · finished regular-round {p['finished_regular']} "
            f"(other stages {p['not_regular']}, never walked) · gate scored {p['gate_scored']} · compared "
            f"{len(p['rows'])} · unequal {p['unequal']} (max |diff| {p['max_diff']:.3g}; equal within {PARITY_TOL:g}) · "
            f"priced by the shadow only {len(p['shadow_only'])} · by the gate only {len(p['gate_only'])}")
    L = [head, f"  - the current shadow export's arithmetic (price_upcoming, as of each kickoff) on the same games: "
               f"unequal {p['legacy_unequal']} of {len(p['rows']) - p['legacy_unpriced']} priced (max |diff| "
               f"{p['legacy_max_diff']:.3g}); unpriced {p['legacy_unpriced']} (a finding: it is not the gate's walk)"]
    if rows:
        for r in p["rows"]:
            L.append(f"  - match {r['match_id']} · cutoff {r['input_cutoff']:%Y-%m-%d %H:%M}Z · shadow "
                     + "/".join(f"{x:.4f}" for x in r["shadow"]) + " · gate " + "/".join(f"{x:.4f}" for x in r["gate"])
                     + f" · |diff| {r['diff']:.2g}")
        if p["rows"]:
            r0 = p["rows"][0]
            L.append(f"  - every row: candidate {r0['candidate']!r} · code sha {r0['code_sha'] or 'unknown'} · "
                     f"prediction stamp {r0['prediction_stamp']:%Y-%m-%d %H:%M:%S}Z")
    return L
