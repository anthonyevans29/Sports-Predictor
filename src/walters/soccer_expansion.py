"""
SOCCER EXPANSION v1 — ONE registered experiment (ARCHITECT 2026-10-07, item 1; GATE-CLASS).
The ruling, verbatim, and the operational definitions: docs/specs/soccer-expansion-v1.md. Registry id
`soccer-expansion-v1` (docs/registry/experiments.json).

    soccer-expansion-gate --preflight   stream receipts only (matches per league-season, the 2023/24 naive
                                        frequencies, stages, closing-odds coverage); scores NOTHING
    soccer-expansion-gate               the ONE run: refused unless the registry holds the experiment declared and
                                        unrun AND the spec's open findings are ruled; per-league lines, the
                                        surviving set, the scored-ids sidecar (registry.record_run)
    export-soccer-expansion-shadow      the five leagues as a greyed SHADOW (engine model_shadow; no Desk call,
                                        no order line, no prediction row)
    soccer-expansion-shadow-grade       read-only: the shadow's top pick vs the three-way book close

- CANDIDATE: the PRODUCTION soccer model exactly as shipped. Its params (dixon_coles_rho, elo_goal_coeff) are
  resolved at run time from the production model version; no refit, no per-league tuning. The walk is the existing
  leakage-free harness, soccer_backtest.run_soccer_backtest, per league-season, at its default min_prior.
- GATE, PER LEAGUE: log-loss <= naive − 0.010 on the same matches (the intl-elo comparison, crit_ll) AND the
  intl-elo-v2 calibration bands (10pp bands, gated at n >= 100, ±5pp, three pairs per match:
  nhl_backtest.calibration_bands). RPS reported. Naive = that league's OWN H/D/A frequencies over its 2023/24
  season (frozen; never the test seasons).
- A league that misses its own gate is DROPPED. Verdict PASS iff at least one league survives; it names the set.
- Reported beside the gate, NEVER gated: the same matches against stored closing odds (bookmaker fdcuk_close,
  soccer-odds-history) where held: market log-loss and the >= +5pp positive-edge cohort.
- Nothing here touches PL: PL is not a league of this experiment, the shadow writes no prediction row, and
  nothing enters evaluate / improve / the results tally / the n=30 read.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from src.timeutil import utc_now_naive

EID = "soccer-expansion-v1"
LEAGUES = ("PD", "SA", "BL1", "FL1", "ELC")
TEST_SEASONS = ("2024/25", "2025/26")
NAIVE_SEASON = "2023/24"
CURRENT_SEASON = "2026/27"
LL_MARGIN = 0.010
MIN_PRIOR = 40                      # the harness default (soccer-backtest --min-prior; run_soccer_backtest)
EDGE_COHORT_PP = 5.0                # reported only: the positive-edge cohort (>= +5pp vs the close)
CLOSE_BOOKMAKER = "fdcuk_close"
ENGINE = "model_shadow"
FILE_PREFIX = "soccer_expansion_shadow_"
WINDOW_HOURS = 72
SHADOW_NOTE = ("SHADOW — soccer-expansion-v1 (PD, SA, BL1, FL1, ELC). Until CONFIRMED every one of these leagues "
               "is SHADOW: never a Desk call, never an order line, never a prediction row; nothing enters PL's "
               "evaluate / improve / results tally / n=30 read.")

# Points the ruling leaves undefined are FINDINGS for a ruling, listed in the spec (section 7). The one run
# REFUSES while any is open; a ruling closes them by editing this tuple and the spec in a reviewed PR.
OPEN_FINDINGS = (
    "F1 league without a stored 2023/24 season (naive undefined)",
    "F2 promoted-club priors in the walk-forward",
    "F3 relegation / promotion play-off rows inside a league-season",
    "F4 the tie: 'log-loss <= naive - 0.010 (tie rejects)' at exact equality",
)


class ExpansionRefused(RuntimeError):
    pass


# ------------------------------------------------------------------ pure --

def ll3(p: float) -> float:
    return -math.log(max(p, 1e-12))


def naive_from(outcomes) -> dict | None:
    """H/D/A frequencies from a 2023/24 outcome list ("H"/"D"/"A"). None when empty (finding F1)."""
    c = Counter(outcomes)
    n = sum(c.values())
    if not n:
        return None
    return {"H": c["H"] / n, "D": c["D"] / n, "A": c["A"] / n, "n": n}


def league_gate(results: list[dict], naive: dict) -> dict:
    """One league's gate over its scored test matches (soccer_backtest result rows). Pure."""
    from src.walters.evaluation import rps_1x2
    from src.walters.nhl_backtest import calibration_bands

    n = len(results)
    if not n:
        return {"n": 0, "verdict": "DROPPED — no scored matches", "survives": False}
    key = {"H": "p_home", "D": "p_draw", "A": "p_away"}
    ll_m = sum(ll3(r[key[r["actual"]]]) for r in results) / n
    ll_n = sum(ll3(naive[r["actual"]]) for r in results) / n
    rps_m = sum(rps_1x2(r["p_home"], r["p_draw"], r["p_away"], r["actual"]) for r in results) / n
    rps_n = sum(rps_1x2(naive["H"], naive["D"], naive["A"], r["actual"]) for r in results) / n
    pairs = [(r[key[o]], int(r["actual"] == o)) for r in results for o in "HDA"]
    bands = calibration_bands(pairs)
    crit_ll = (ll_n - ll_m) >= LL_MARGIN - 1e-12          # the intl-elo comparison, verbatim
    crit_bands = all(b["ok"] for b in bands if b["gated"])
    ok = crit_ll and crit_bands
    why = [w for w, good in (("log-loss margin", crit_ll), ("calibration", crit_bands)) if not good]
    return {"n": n, "ll_model": ll_m, "ll_naive": ll_n, "bar": ll_n - LL_MARGIN, "rps_model": rps_m,
            "rps_naive": rps_n, "bands": bands, "crit_ll": crit_ll, "crit_bands": crit_bands,
            "survives": ok, "verdict": "PASS" if ok else "DROPPED — " + ", ".join(why)}


def overall(per_league: dict) -> dict:
    """PASS iff at least one league survives its own gate; the verdict names the surviving set. Pure."""
    surv = [c for c in LEAGUES if (per_league.get(c) or {}).get("survives")]
    return {"surviving": surv, "dropped": [c for c in LEAGUES if c not in surv],
            "verdict": ("PASS — surviving set " + ", ".join(surv)) if surv else "FAIL — no league survives"}


def market_side(results: list[dict], closes: dict[int, dict]) -> dict | None:
    """REPORTED, NEVER GATED: the same scored matches against de-vigged closing odds where held.
    closes: match_id -> {"HOME", "DRAW", "AWAY"} decimal prices. Pure."""
    key = {"H": ("p_home", "HOME"), "D": ("p_draw", "DRAW"), "A": ("p_away", "AWAY")}
    j = []
    for r in results:
        p = closes.get(r["match_id"])
        if not p or not {"HOME", "DRAW", "AWAY"} <= set(p):
            continue
        inv = {k: 1.0 / p[k] for k in ("HOME", "DRAW", "AWAY")}
        t = sum(inv.values())
        j.append((r, {k: v / t for k, v in inv.items()}))
    if not j:
        return None
    n = len(j)
    cohort = []
    for r, mk in j:
        rk, sel = max((key["H"], key["D"], key["A"]), key=lambda x: r[x[0]])
        edge = (r[rk] - mk[sel]) * 100
        if edge >= EDGE_COHORT_PP - 1e-9:
            cohort.append((edge, key[r["actual"]][1] == sel))
    return {"n_priced": n, "n_unpriced": len(results) - n,
            "ll_model": sum(ll3(r[key[r["actual"]][0]]) for r, _ in j) / n,
            "ll_market": sum(ll3(mk[key[r["actual"]][1]]) for r, mk in j) / n,
            "edge_cohort": {"min_edge_pp": EDGE_COHORT_PP, "n": len(cohort),
                            "hits": sum(1 for _, h in cohort if h),
                            "mean_edge_pp": (sum(e for e, _ in cohort) / len(cohort)) if cohort else None}}


# ------------------------------------------------------------ registry --

def declared_unrun():
    """The registry entry, refusing unless declared and unrun (the test seasons are read ONCE)."""
    from src.walters import registry as reg
    e = reg.get(EID)
    if e is None or e.get("status") != "declared" or e.get("run") is not None:
        raise ExpansionRefused(f"{EID} must be declared and unrun in the registry "
                               f"(status {e.get('status') if e else 'absent'}): the test seasons are read once")
    return e


def guards_backtest(competition_code: str) -> str | None:
    """soccer-backtest on a league of this experiment is refused while it is declared and unrun: an ad-hoc
    read would spend the test seasons outside the one run. None = allowed."""
    from src.walters import registry as reg
    if (competition_code or "").upper() not in LEAGUES:
        return None
    e = reg.get(EID)
    if e is not None and e.get("run") is None:
        return (f"{competition_code} is a {EID} league, declared and unrun: its test seasons are read once, by "
                "soccer-expansion-gate (docs/specs/soccer-expansion-v1.md)")
    return None


# ------------------------------------------------------------- the DB --

def _comp(s, code):
    from sqlalchemy import select
    from src.db.schema import Competition
    return s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()


def _outcome(m) -> str | None:
    if m.home_score is None or m.away_score is None:
        return None
    return "H" if m.home_score > m.away_score else "A" if m.home_score < m.away_score else "D"


def naive_for(s, code: str) -> dict | None:
    """That league's own 2023/24 H/D/A frequencies (finished, scored). None = not stored (finding F1)."""
    from sqlalchemy import select
    from src.db.schema import Match, MatchStatus
    c = _comp(s, code)
    if c is None:
        return None
    ms = s.execute(select(Match).where(Match.competition_id == c.id, Match.season == NAIVE_SEASON,
                                       Match.status == MatchStatus.FINISHED)).scalars()
    return naive_from([o for o in (_outcome(m) for m in ms) if o])


def finished_count(s, code: str, season: str) -> int:
    """Finished matches with both scores stored for a league-season (a count; no outcome is read)."""
    from sqlalchemy import func, select
    from src.db.schema import Match, MatchStatus
    c = _comp(s, code)
    if c is None:
        return 0
    return s.execute(select(func.count(Match.id)).where(
        Match.competition_id == c.id, Match.season == season, Match.status == MatchStatus.FINISHED,
        Match.home_score.isnot(None), Match.away_score.isnot(None))).scalar() or 0


def preflight(s) -> dict:
    """Stream receipts, scoring NOTHING: per league, stored matches per season and status, the stages present in
    the test seasons (finding F3), the 2023/24 naive frequencies, and closing-odds coverage on the test seasons.
    Counts only: no test-season OUTCOME is read."""
    from sqlalchemy import func, select
    from src.db.schema import Match, Odds
    out = {}
    for code in LEAGUES:
        c = _comp(s, code)
        if c is None:
            out[code] = {"stored": False}
            continue
        seasons = {}
        for season in (NAIVE_SEASON, *TEST_SEASONS, CURRENT_SEASON):
            rows = s.execute(select(Match.status, func.count()).where(
                Match.competition_id == c.id, Match.season == season).group_by(Match.status)).all()
            seasons[season] = {getattr(st, "value", str(st)): n for st, n in rows}
        stages = dict(s.execute(select(Match.stage, func.count()).where(
            Match.competition_id == c.id, Match.season.in_(TEST_SEASONS)).group_by(Match.stage)).all())
        test_ids = select(Match.id).where(Match.competition_id == c.id, Match.season.in_(TEST_SEASONS))
        closes = s.execute(select(func.count(func.distinct(Odds.match_id))).where(
            Odds.match_id.in_(test_ids), Odds.bookmaker == CLOSE_BOOKMAKER, Odds.market == "1X2")).scalar()
        out[code] = {"stored": True, "seasons": seasons, "stages": {str(k): v for k, v in stages.items()},
                     "naive": naive_for(s, code), "close_matches": closes}
    return out


def _closes(s, ids) -> dict[int, dict]:
    from sqlalchemy import select
    from src.db.schema import Odds
    out: dict[int, dict] = {}
    if not ids:
        return out
    for o in s.execute(select(Odds).where(Odds.match_id.in_(list(ids)), Odds.bookmaker == CLOSE_BOOKMAKER,
                                          Odds.market == "1X2")).scalars():
        out.setdefault(o.match_id, {})[o.selection] = o.price_decimal
    return out


def run(rho: float, coeff: float, progress=None) -> dict:
    """The ONE run's computation (the CLI records it). Refuses while any spec finding is open, or a league's
    2023/24 naive is undefined."""
    if OPEN_FINDINGS:
        raise ExpansionRefused("open findings need a ruling before the run: " + "; ".join(OPEN_FINDINGS))
    from src.db.database import session_scope
    from src.walters.soccer_backtest import run_soccer_backtest

    with session_scope() as s:
        naives = {c: naive_for(s, c) for c in LEAGUES}
        empty = [f"{c} {se}" for c in LEAGUES for se in TEST_SEASONS if not finished_count(s, c, se)]
        s.rollback()
    if empty:                        # checked BEFORE any league is scored: a refusal never follows a read
        raise ExpansionRefused(f"no finished matches stored for {', '.join(empty)} (or the season string differs "
                               "from the stored one): run --preflight; missing data is never a silent DROP")
    missing = [c for c, v in naives.items() if v is None]
    if missing:
        raise ExpansionRefused(f"no stored {NAIVE_SEASON} for {', '.join(missing)}: naive undefined (finding F1)")
    per, scored = {}, []
    for code in LEAGUES:
        res = []
        for season in TEST_SEASONS:
            got = run_soccer_backtest(code, season, MIN_PRIOR, dixon_coles_rho=rho, elo_goal_coeff=coeff) or []
            if not got:              # law 4: missing data is never a silent DROP
                raise ExpansionRefused(f"{code} {season}: no scored matches (not stored, or season string differs "
                                       "from the stored one); run --preflight")
            res += got
        g = league_gate(res, naives[code])
        with session_scope() as s:
            g["market"] = market_side(res, _closes(s, [r["match_id"] for r in res]))
            s.rollback()
        g["naive_freq"] = naives[code]
        per[code] = g
        scored += [r["match_id"] for r in res]
        if progress:
            progress(code, g)
    return {"per_league": per, **overall(per), "scored_ids": scored}


# ------------------------------------------------------------- shadow --

def _status_label(e: dict | None, code: str) -> str:
    if e is None:
        return "NOT DECLARED"
    if not e.get("run"):
        return "DECLARED — gate not run"
    pl = ((e["run"].get("result") or {}).get("per_league") or {}).get(code) or {}
    v = (e.get("verdict") or {}).get("verdict")
    league = pl.get("verdict", "?")
    return f"{league} · verdict {v or 'pending'}" + (" · confirmation open" if e.get("status") == "confirming" else "")


def price_upcoming(code: str, now: datetime, hours: int, rho: float, coeff: float, season: str = CURRENT_SEASON):
    """The production model, walked over this season's finished matches before `now` (the harness's own walk),
    pricing the SCHEDULED matches in the window. Returns ([(match, pred)], counts)."""
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus
    from src.walters import soccer_backtest as sb

    out, cnt = [], Counter()
    with session_scope() as s:
        c = _comp(s, code)
        if c is None:
            return [], {"not_stored": 1}
        rows = list(s.execute(select(Match).where(Match.competition_id == c.id, Match.season == season)
                              .order_by(Match.utc_date, Match.id)).scalars())
        done = [m for m in rows if m.status == MatchStatus.FINISHED and m.utc_date and m.utc_date < now
                and m.home_score is not None and m.away_score is not None]
        due = [m for m in rows if m.status == MatchStatus.SCHEDULED and m.utc_date
               and now <= m.utc_date < now + timedelta(hours=hours)]
        import dataclasses
        ctx, elo = sb.CompetitionScoringContext(), sb.EloState(config=sb.EloConfig())
        cfg = dataclasses.replace(sb.PoissonConfig(), dixon_coles_rho=rho, elo_goal_coeff=coeff)
        for m in done:
            nh, na = sb.update_after_match(elo.get(m.home_team_id), elo.get(m.away_team_id),
                                           m.home_score, m.away_score, elo.config)
            elo.set(m.home_team_id, nh)
            elo.set(m.away_team_id, na)
        if len(done) < MIN_PRIOR:
            cnt["below_min_prior"] = len(due)
            due = []
        st = sb.estimate_strengths([{"home_team_id": p.home_team_id, "away_team_id": p.away_team_id,
                                     "home_score": p.home_score, "away_score": p.away_score} for p in done], ctx) \
            if due else {}
        for m in due:
            hs, as_ = st.get(m.home_team_id), st.get(m.away_team_id)
            if not (hs and as_):
                cnt["no_strength"] += 1
                continue
            out.append((m.id, sb.predict_match(home_elo=elo.get(m.home_team_id), away_elo=elo.get(m.away_team_id),
                                               home_strength=hs, away_strength=as_, context=ctx, config=cfg)))
        s.rollback()
    cnt["priced"] = len(out)
    return out, dict(cnt)


def shadow_row(fixture_row: dict, pred, model_version: str, label: str, code: str) -> dict:
    """A greyed shadow row. Pure. No desk, no order, never a prediction."""
    probs = {"home_win": pred.p_home, "draw": pred.p_draw, "away_win": pred.p_away}
    top = max(probs.items(), key=lambda kv: kv[1])
    return {**fixture_row, "competition": code, "engine": ENGINE, "model_version": model_version,
            "gate_verdict": label,
            "prediction": {"home_win_prob": round(pred.p_home, 4), "draw_prob": round(pred.p_draw, 4),
                           "away_win_prob": round(pred.p_away, 4), "top_pick": top[0],
                           "top_pick_prob": round(top[1], 4)}}


def export_shadow(prod: tuple, now: datetime | None = None, hours: int = WINDOW_HOURS,
                  out_dir: str = "exports") -> tuple[str, dict]:
    """prod = (version, rho, coeff) of the PRODUCTION soccer model (resolved by the caller, never faked)."""
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import registry as reg
    from src.walters.export import _fixture_row

    version, rho, coeff = prod
    now = now or utc_now_naive()
    e = reg.get(EID)
    rows, counts = [], {}
    for code in LEAGUES:
        priced, counts[code] = price_upcoming(code, now, hours, rho, coeff, season=CURRENT_SEASON)
        with session_scope() as s:
            for mid, pred in priced:
                fx = _fixture_row(s, s.get(Match, mid), code, Counter(), Counter())
                rows.append(shadow_row(fx, pred, version, _status_label(e, code), code))
            s.rollback()
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(out_dir) / f"{FILE_PREFIX}{now.strftime('%Y-%m-%d_%H%M')}.json")
    doc = {"sport": "soccer", "engine": ENGINE, "experiment": EID, "model_version": version,
           "gate_verdict": e and e.get("status") or "not declared", "contains_predictions": False,
           "exported_at": now.isoformat(), "window_hours": hours, "note": SHADOW_NOTE, "counts": counts,
           "count": len(rows), "predictions": rows}
    with open(path, "w") as f:
        json.dump(doc, f, indent=2, default=str)
    return path, doc


def last_calls(export_dir: str = "exports") -> dict[int, dict]:
    """match_id -> the LAST shadow row written before its kickoff."""
    out: dict[int, dict] = {}
    for f in sorted(Path(export_dir).glob(f"{FILE_PREFIX}*.json")):
        try:
            doc = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if doc.get("engine") != ENGINE:
            continue
        at = doc.get("exported_at") or ""
        for r in doc.get("predictions") or []:
            mid, ko = r.get("match_id"), r.get("utc_date") or ""
            if mid is None or not at or at >= ko:
                continue
            if mid not in out or at >= out[mid]["exported_at"]:
                out[mid] = {**r, "exported_at": at}
    return out


PICK = {"home_win": "HOME", "draw": "DRAW", "away_win": "AWAY"}


def shadow_grade(days: int = 30, export_dir: str = "exports", now: datetime | None = None) -> dict:
    """READ-ONLY: the shadow's top pick vs the three-way book close (#207 contract), per league."""
    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Odds
    from src.walters.close import close_1x2, outcomes_for, priced
    from sqlalchemy import select

    now = now or utc_now_naive()
    per: dict[str, dict] = {}
    lines = []
    with session_scope() as s:
        for mid, c in sorted(last_calls(export_dir).items(), key=lambda kv: kv[1].get("utc_date") or ""):
            m = s.get(Match, mid)
            if m is None or m.status != MatchStatus.FINISHED or m.utc_date < now - timedelta(days=days):
                continue
            code = c.get("competition") or "?"
            d = per.setdefault(code, {"graded": 0, "priced": 0, "clv": []})
            d["graded"] += 1
            sel = PICK[c["prediction"]["top_pick"]]
            cl = close_1x2(list(s.execute(select(Odds).where(Odds.match_id == m.id, Odds.market == "1X2"))
                                .scalars()), m.utc_date, outcomes_for(m.sport))
            clv = None
            if priced(cl):
                clv = c["prediction"]["top_pick_prob"] - cl["fair"][sel]
                d["priced"] += 1
                d["clv"].append(clv)
            lines.append(f"  {code:4} {m.away_team.name[:14]:14} @ {m.home_team.name[:15]:15} pick {sel} "
                         f"{c['prediction']['top_pick_prob']:.3f} div="
                         + ("%+.1fpp" % (clv * 100) if clv is not None else "—"))
        s.rollback()
    for d in per.values():
        v = d.pop("clv")
        d["mean_clv_pp"] = round(sum(v) / len(v) * 100, 2) if v else None
    return {"per_league": per, "lines": lines}
