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
  strength. Nothing is fitted. THE ONE PREDICATE (ARCHITECT 2026-10-30 11:00 ET, addendum 181 item 2: "La Liga's ONE
  predicate governs the whole path"): the priors pass through soccer_backtest._confirmation_rows
  (soccer_expansion.unscoreable): a game finished under AWD or WO is neither scored nor walked, a non-FT row with a
  stored 90-minute score is walked on it, a no-raw-code row is walked as stored (C1).
- gate_rows: the GATE path, soccer_backtest.run_soccer_backtest itself, as the expansion gate calls it (MIN_PRIOR,
  stage_filter=is_regular, batch_same_kickoff=True, the same rho and coefficient), on the 2026/27 season, as the
  confirmation walk with that predicate (confirmation_scoring=True; 181 item 2: "158 item 2(a)'s "the gate's walk" is
  the confirmation walk with that predicate, not the raw walk"), so the parity holds by construction.
- parity: both paths on every finished 2026/27 game of the league the predicate scores (an unscoreable one is
  priced by neither): a row per game the gate scored, its three
  probabilities from each path and their largest absolute difference; games one path prices and the other does not
  are counted apart. Equal means a difference no larger than PARITY_TOL (floating-point summation order only).
  REFUSED (ExpansionRefused, before any game is walked) when the league-season stores a stage / round label the code
  cannot place (soccer_expansion.placement None, NULL or empty included), read by the gate's own census
  (soccer_expansion.stage_census, STALE_ORPHAN excluded): the gate's run refuses on such a label (F3, never guessed),
  so the parity read does too, and a game is never silently left out of both paths (Codex on #663).
- legacy_shadow: the probabilities the RETIRED shadow arithmetic (soccer_expansion.price_upcoming's, deleted by the
  export switch, 164 item 3; read as of each game's kickoff: every stage, no same-kickoff batching, strengths from all
  finished games before it) would give the same games, against the gate path: reported as a finding, never used.
- THE SHADOW SIDE of the parity is the export's own function, soccer_expansion.shadow_entry (prospective=False: a
  finished game is priced as of its kickoff), which calls predict_as_of; the receipt so proves the export path
  (ARCHITECT 2026-10-24, addendum 164 item 3: "the prospective predictions for SA/BL1/FL1/ELC — and for PD (159 item
  6(a)) — are produced by leagues_candidate.predict_as_of from the declaration on, bound to the run record's frozen
  parameters, never by price_upcoming").
Every parity row carries the candidate id (CANDIDATE: the walk, prospective on 2026/27, until the declaration names
it), the code sha (git, short; None when git cannot say), the input cutoff (the game's kickoff: the latest input it
may read) and the prediction stamp (the receipt's own clock).
"""
from __future__ import annotations

import dataclasses
from datetime import datetime

from src.walters.soccer_expansion import CURRENT_SEASON, MIN_PRIOR, ExpansionRefused, is_regular, stage_census

CANDIDATE = "soccer-expansion-v1 walk, prospective on 2026/27 (undeclared: 158 item 2(c) declares it per league)"
PARITY_TOL = 1e-12


def code_sha() -> str | None:
    """The producing checkout's short sha: provenance.git_sha() (anchored to the repo, not the process's working
    directory; SP_GIT_SHA overrides; None when git cannot say), the `git_sha` every export carries and compare_exports
    masks."""
    from src.walters.provenance import git_sha
    return git_sha()


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


def priors(rows, fixture) -> list:
    """The rows predict_as_of walks for `fixture`, in kickoff order: the finished regular-round rows strictly before
    its kickoff (F5), itself excluded, through the one predicate (soccer_backtest._confirmation_rows; addendum 181 item
    2). Pure; the selection predict_as_of makes, lifted out so the shadow export records what it read."""
    from src.walters import soccer_backtest as sb
    return sorted(sb._confirmation_rows(m for m in rows if is_regular(m.stage) and m.utc_date < fixture.utc_date
                                        and m.id != fixture.id),
                  key=lambda m: m.utc_date)


def predict_as_of(rows, fixture, rho: float, coeff: float):
    """The prospective prediction for `fixture` from the finished regular-round rows strictly before its kickoff, or
    (None, why). `rows`: the league-season's finished rows (any order). The priors pass through the one predicate
    (soccer_backtest._confirmation_rows; addendum 181 item 2): AWD / WO released, a non-FT row on its 90' score."""
    from src.walters import soccer_backtest as sb
    prior = priors(rows, fixture)
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
    """The retired soccer_expansion.price_upcoming's arithmetic for `fixture` (deleted by the export switch, 164 item
    3), read as of its kickoff (every stage, no batching, Elo over every finished row before it, strengths from them
    all): the old shadow's number, kept for the finding."""
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


def gate_rows(code: str, season: str, rho: float, coeff: float, through: datetime | None = None) -> list[dict]:
    """The gate path: run_soccer_backtest as soccer_expansion.run calls it, on `season`, as the confirmation walk with
    the one predicate (confirmation_scoring=True, addendum 181 item 2); cut at `through` when the leagues' window
    fence is up (addendum 178 R8; 181 item 1(b): no game after the cut is walked)."""
    from src.walters.soccer_backtest import run_soccer_backtest
    from src.walters.soccer_expansion import BATCH_SAME_KICKOFF
    return run_soccer_backtest(code, season, MIN_PRIOR, dixon_coles_rho=rho, elo_goal_coeff=coeff,
                               stage_filter=is_regular, batch_same_kickoff=BATCH_SAME_KICKOFF,
                               confirmation_scoring=True, through=through) or []


def unplaced_labels(s, code: str, season: str) -> list[str]:
    """F3 for one league-season: every stored label placement() cannot place, with its count, by the gate's own census
    (soccer_expansion.stage_census, as soccer_expansion.unplaced reads it for the gate's seasons)."""
    return [f"{code} {season} {lab!r} ({n})" for lab, n, pl in stage_census(s, code, season) if pl is None]


def parity(code: str, rho: float, coeff: float, season: str = CURRENT_SEASON, now: datetime | None = None) -> dict:
    """The parity receipt for one league (the module docstring). Read-only: one session, rolled back.
    THE WINDOW FENCE (ARCHITECT 2026-10-30, addendum 178 R8; addendum 181 item 1(b)): while the league's verdict is
    not recorded (leagues_window.fence_cutoff), both paths read only the 2026/27 games kicking off at or before the
    cut (its declared_at; PRE_DECLARATION_CUT while no entry exists); the finished regular-round games after it are
    counted (`fenced`), never walked or compared. PL, PD and every other competition: unchanged."""
    from src.walters.soccer_expansion import shadow_entry, unscoreable
    from src.db.database import session_scope
    from src.timeutil import utc_now_naive
    from src.walters.leagues_window import fence_cutoff
    now = now or utc_now_naive()
    cut = fence_cutoff(code, season)
    with session_scope() as s:
        bad = unplaced_labels(s, code, season)
        s.rollback()
    if bad:                          # F3, as the gate's run refuses: never guessed, never silently left out
        raise ExpansionRefused("stage / round labels the code cannot place (F3; the gate's run refuses on them, so "
                               "the parity read does; never guessed): " + "; ".join(bad))
    sha = code_sha()
    gate = {r["match_id"]: r for r in gate_rows(code, season, rho, coeff, through=cut)}
    out = {"code": code, "season": season, "gate_scored": len(gate), "rows": [], "max_diff": 0.0, "unequal": 0,
           "shadow_only": [], "gate_only": [], "legacy_max_diff": 0.0, "legacy_unequal": 0, "legacy_unpriced": 0,
           "fenced": 0}
    with session_scope() as s:
        rows = _season_rows(s, code, season)
        if cut is not None:          # R8: the window's games are the cohort reader's alone
            out["fenced"] = sum(1 for m in rows if m.utc_date > cut and is_regular(m.stage))
            rows = [m for m in rows if m.utc_date <= cut]
        regular = [m for m in rows if is_regular(m.stage)]
        out["released"] = sum(1 for m in regular if unscoreable(m))     # 181 item 2: neither path prices them
        for m in regular:
            if unscoreable(m):
                continue
            pred, why = shadow_entry(rows, m, {"rho": rho, "elo_goal_coeff": coeff}, None, prospective=False)
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
            f"priced by the shadow only {len(p['shadow_only'])} · by the gate only {len(p['gate_only'])}"
            + (f" · released {p['released']} (the one predicate: AWD / WO, or a non-FT code with no 90-minute score; "
               "neither path walks or prices them, addendum 181 item 2)" if p.get("released") else "")
            + (f" · fenced {p['fenced']} (finished after the cut: the cohort reader's alone, addendum 178 R8; "
               "addendum 181 item 1(b))" if p.get("fenced") else ""))
    L = [head, f"  - the retired shadow arithmetic (price_upcoming's, as of each kickoff) on the same games: "
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
