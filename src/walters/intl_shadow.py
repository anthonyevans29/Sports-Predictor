"""
UNL SHADOW ENGINE (ARCHITECT 2026-10-02): "intl-elo-v2 VERDICT — PASS under the
frozen gate (0.7889 vs bar 1.0424; gated bands ok; RPS 0.153 vs 0.237).
Ratified. ... CONFIRMATION WINDOW: 60 games after 2026-10-02 (UNL matchday 4
this weekend + November's WCQ_EU), scored by the plan; production allowed only
on CONFIRMED. UNTIL THEN: UNL gets a SHADOW ENGINE like NHL's —
export-unl-predictions writes intl-elo-v2 rows labelled "PASS — confirmation
0/60", greyed in the Cockpit, never feeding the Desk; nhl-style shadow-grade."

    export-unl-predictions  -> exports/unl_shadow_<YYYY-MM-DD_HHMM>.json
    unl-shadow-grade        -> live CLV (pick-vs-close), from the artifacts
    intl-elo-confirm        -> the plan's 60-game read (progress; --record)

- Rows: engine "model_shadow" (the Cockpit's shadow card: never `rows`, never
  a Desk call, never a venue input, never logged to the ledger), model_version
  "intl_elo_v2", gate_verdict "PASS — confirmation n/60" (n = confirmation
  games played so far). Three-way: home / draw / away.
- THE MODEL IS intl-elo-v2 EXACTLY AS RUN: its fitted c and K multipliers
  are READ from the registry run record (never refit here); neutral rule v3
  (intl_match_venue; unknown -> listed home +100); μ from the training
  stream; walk-forward over every finished stream game before now.
- Refuses until the registry holds intl-elo-v2 with its run record and a PASS
  verdict (status "confirming"): the shadow is the confirmation window's
  instrument, nothing earlier.
- The confirmation set is the declaration's: the first 60 senior COMPETITIVE
  national-team matches (every stream code but friendlies) that kick off
  after the verdict and are not in the test set, each priced
  predict-then-update; CONFIRMED iff log-loss <= ln 3 AND < naive − 0.010 on
  the same games (registry.record_confirmation computes it).
- COHORT (review on #248, 2026-10-02): the 60 are chosen from the stored
  FIXTURES, whatever their status, never from the scored stream, then FROZEN
  in the registry (intl-elo-confirm --freeze-cohort). A pending, postponed,
  cancelled or unscoreable cohort fixture leaves the read incomplete; it is
  never replaced by game 61. Until frozen the selection is labelled
  provisional and cannot be recorded.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from src.timeutil import utc_now_naive

ENGINE = "model_shadow"
MODEL_VERSION = "intl_elo_v2"
WINDOW_HOURS = 36
FILE_PREFIX = "unl_shadow_"
NOTE = ("SHADOW — CONFIRMATION WINDOW. intl_elo_v2 PASSED the frozen gate (0.7889 vs bar 1.0424; "
        "RPS 0.153 vs 0.237) and is in its 60-game confirmation window; production only on CONFIRMED. "
        "Never a call, never a venue input, never logged to the ledger. UNL runs MARKET-ONLY on the Desk.")


class ShadowRefused(RuntimeError):
    pass


def frozen():
    """(entry, c_mult, k_mult) from the registry; refuses unless intl-elo-v2 has
    its run record and a PASS verdict."""
    from src.walters import intl_elo as ie
    from src.walters import registry as reg

    e = reg.get(ie.EID_V2)
    if e is None or not e.get("run"):
        raise ShadowRefused(f"{ie.EID_V2} has no run record in docs/registry — splice it first")
    if (e.get("verdict") or {}).get("verdict") != "PASS":
        raise ShadowRefused(f"{ie.EID_V2} has no PASS verdict recorded — the shadow is the confirmation window's")
    r = e["run"]["result"]
    if "fit_c_mult" not in r or "fit_k_mult" not in r:
        raise ShadowRefused(f"{ie.EID_V2}'s run record lacks fit_c_mult / fit_k_mult")
    return e, float(r["fit_c_mult"]), float(r["fit_k_mult"])


def _verdict_at(e) -> datetime:
    return datetime.fromisoformat(e["verdict"]["at"].replace("Z", "+00:00")).replace(tzinfo=None)


def eligible_fixtures(s, e) -> list[dict]:
    """Every STORED fixture eligible for the confirmation set, WHATEVER ITS
    STATUS (scheduled, live, postponed, cancelled, finished with or without a
    usable score): competitive stream code, kickoff after the verdict, not in
    the test set; kickoff order. Result availability never enters."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match
    from src.walters import intl_elo as ie

    at = _verdict_at(e)
    comps = {c.id: c.code for c in s.execute(select(Competition).where(
        Competition.code.in_([c for c in ie.STREAM_CODES if c != ie.FRIENDLY]))).scalars()}
    if not comps:
        return []
    out = []
    for m in s.execute(select(Match).where(Match.competition_id.in_(list(comps)), Match.utc_date > at)
                       .order_by(Match.utc_date, Match.id)).scalars():
        g = ie.Game(m.id, comps[m.competition_id], m.season, m.utc_date, None, None, None, None, None)
        if ie.is_test(g):
            continue
        status = m.status.value if hasattr(m.status, "value") else str(m.status)
        out.append({"id": m.id, "kickoff": m.utc_date, "code": g.code, "status_raw": m.status_raw,
                    "status": status, "unscoreable": _unscoreable(m, status)})
    return out


def _unscoreable(m, status: str) -> bool:
    """Can this fixture NEVER be scored (ARCHITECT 2026-10-02: "unscoreable is
    the criterion, not the status label")? Cancelled (CANC / ABD), or finished
    under a non-FT code (AWD / WO, or AET / PEN) without a 90-minute score —
    the stream's own rule (ie.load) can never admit it. A FT row still waiting
    for its score is data lag, not unscoreable: it stays pending."""
    if status == "cancelled":
        return True
    if status != "finished":
        return False
    if m.home_score_90 is not None and m.away_score_90 is not None:
        return False
    return (m.status_raw or "").upper() != "FT"


def substitutions_due(e, s) -> list[dict]:
    """ARCHITECT 2026-10-02 (2): every UNSCOREABLE cohort fixture (cancelled
    CANC / ABD; finished AWD / WO, or AET / PEN without a 90-minute score) is
    released and replaced by the next eligible fixture AFTER the cohort (61st,
    62nd …): kickoff order, after every fixture that is or was in the cohort,
    never unscoreable itself, never one already used. The reason is the raw
    provider code. POSTPONED / scheduled / live fixtures are never released.
    Read-only: the registry write is intl-elo-confirm --substitute."""
    c = e.get("confirmation_cohort")
    if not c:
        return []
    co = cohort(e, s)
    elig = eligible_fixtures(s, e)
    by_id = {f["id"]: f for f in elig}
    ever = set(co["ids"]) | {int(x["released"]) for x in c.get("substitutions") or []}
    last = max(((by_id[i]["kickoff"], i) for i in ever if i in by_id), default=None)
    pool = [f for f in elig if f["id"] not in ever and not f["unscoreable"]
            and (last is None or (f["kickoff"], f["id"]) > last)]
    out = []
    for i in co["ids"]:
        f = by_id.get(i)
        if f is None or not f["unscoreable"]:
            continue
        reason = (f["status_raw"] or f["status"]).upper()            # the raw provider code
        out.append({"released": f, "replacement": pool.pop(0) if pool else None, "reason": reason})
    return out


def cohort(e, s) -> dict:
    """The confirmation cohort: the FROZEN ids from the registry when frozen;
    otherwise the provisional first n eligible fixtures (possibly fewer than n
    while the schedule is short). Never depends on results."""
    from src.walters import registry as reg

    n = e["confirmation_plan"]["n_games"]
    elig = eligible_fixtures(s, e)
    try:
        frozen_ids = reg.frozen_cohort(e)
    except reg.RegistryError as err:
        raise ShadowRefused(str(err))
    if frozen_ids is not None:
        return {"state": "frozen", "ids": frozen_ids, "n_games": n, "eligible_stored": len(elig)}
    return {"state": "provisional", "ids": [f["id"] for f in elig[:n]], "n_games": n,
            "eligible_stored": len(elig), "fixtures": elig[:n]}


def _labelled(cohort_ids, games) -> set[int]:
    """Cohort fixtures with a scoreable label (finished, 90-minute score: the
    stream's own rule, ie.load)."""
    have = {g.id for g in games}
    return {i for i in cohort_ids if i in have}


def fit(now: datetime, s=None):
    """(model, games, receipt): intl-elo-v2 walked over every finished stream
    game before `now` (rule v3)."""
    from src.walters import intl_elo as ie

    e, c_mult, k_mult = frozen()
    if s is None:
        from src.db.database import session_scope
        with session_scope() as s2:
            games, c = ie.load(s2, rule="v3")
            co = cohort(e, s2)
            s2.rollback()
    else:
        games, c = ie.load(s, rule="v3")
        co = cohort(e, s)
    train = [g for g in games if ie.TRAIN_FROM <= g.kickoff < ie.TRAIN_TO]
    if not train:
        raise ShadowRefused("no training-stream games stored: run intl-sync first")
    mu = sum(g.hg + g.ag for g in train) / (2 * len(train))
    m = ie.IntlElo(mu=mu, c_mult=c_mult, k_mult=k_mult)
    used = 0
    for g in games:
        if g.kickoff < now:
            m.update(g)
            used += 1
    done = _labelled(co["ids"], [g for g in games if g.kickoff < now])
    return m, games, {"games_used": used, "mu": round(mu, 4), "c_mult": c_mult, "k_mult": k_mult,
                      "confirmation_played": len(done), "confirmation_n": e["confirmation_plan"]["n_games"],
                      "cohort_state": co["state"],
                      **{k: v for k, v in c.items()}}


def gate_label(rc: dict) -> str:
    return f"PASS — confirmation {min(rc['confirmation_played'], rc['confirmation_n'])}/{rc['confirmation_n']}"


def build_rows(now: datetime | None = None, hours: int = WINDOW_HOURS) -> dict:
    from collections import Counter

    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, IntlMatchVenue, Match, MatchStatus
    from src.walters import intl_elo as ie
    from src.walters.export import _fixture_row

    now = now or utc_now_naive()
    with session_scope() as s:
        model, _, rc = fit(now, s)
        label = gate_label(rc)
        codes = [c for c in ie.STREAM_CODES if c != ie.FRIENDLY]
        comps = {c.id: c.code for c in s.execute(select(Competition).where(Competition.code.in_(codes))).scalars()}
        rows = []
        q = (select(Match).where(Match.competition_id.in_(list(comps)), Match.status == MatchStatus.SCHEDULED,
                                 Match.utc_date >= now, Match.utc_date < now + timedelta(hours=hours))
             .order_by(Match.utc_date, Match.id))
        for m in s.execute(q).scalars():
            v = s.get(IntlMatchVenue, m.id)
            neutral = v.neutral_v3 if v else None
            g = ie.Game(m.id, comps[m.competition_id], m.season, m.utc_date, m.home_team_id, m.away_team_id,
                        0, 0, neutral)
            ph, pd, pa = model.probs(g)
            top = max((("home_win", ph), ("draw", pd), ("away_win", pa)), key=lambda x: x[1])
            row = _fixture_row(s, m, comps[m.competition_id], Counter(), Counter())
            row.update({
                "engine": ENGINE, "model_version": MODEL_VERSION, "gate_verdict": label,
                "prediction": {"home_win_prob": round(ph, 4), "draw_prob": round(pd, 4),
                               "away_win_prob": round(pa, 4), "top_pick": top[0],
                               "top_pick_prob": round(top[1], 4),
                               "elo_home": round(model.r(m.home_team_id), 1),
                               "elo_away": round(model.r(m.away_team_id), 1),
                               "home_adv_applied": ie.home_term(g),
                               "neutral_v3": neutral},
            })
            rows.append(row)
        s.rollback()
    return {"rows": rows, "fit": rc, "label": label, "now": now}


def export(now: datetime | None = None, hours: int = WINDOW_HOURS, out_dir: str = "exports") -> tuple[str, dict]:
    r = build_rows(now, hours)
    now = r["now"]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(out_dir) / f"{FILE_PREFIX}{now.strftime('%Y-%m-%d_%H%M')}.json")
    doc = {"sport": "unl", "engine": ENGINE, "model_version": MODEL_VERSION, "gate_verdict": r["label"],
           "contains_predictions": False,   # nothing here is a live prediction (doctrine)
           "exported_at": now.isoformat(), "window_hours": hours, "note": NOTE,
           "fit": r["fit"], "count": len(r["rows"]), "predictions": r["rows"]}
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
                out[mid] = {**r, "exported_at": at, "source_file": f.name}
    return out


PICK = {"home_win": "HOME", "draw": "DRAW", "away_win": "AWAY"}
OUTCOME_SIDE = {"H": "HOME", "D": "DRAW", "A": "AWAY"}
# ARCHITECT 2026-10-07 item 4 (d): the split by |model − close| in pp, read on
# the TOP-PICK side (the grade's own `div`; CONFIRMED, ARCHITECT 2026-10-07
# addendum 3, item C: "the gap is measured on the top-pick side"). Lower bounds inclusive:
# 4 -> 4-10, 10 -> 10-15, 15 -> >=15.
DIV_BUCKETS = (("<4", 0.0, 4.0), ("4-10", 4.0, 10.0), ("10-15", 10.0, 15.0), (">=15", 15.0, None))


def div_bucket(div_pp: float) -> str:
    """The |model − close| bucket of a divergence in pp (sign dropped). Rounded
    to 9 decimals first so float noise (0.55 − 0.51 = 0.04000000000000004)
    never moves a game across a boundary."""
    x = round(abs(div_pp), 9)
    for name, lo, hi in DIV_BUCKETS:
        if x >= lo and (hi is None or x < hi):
            return name
    raise ValueError(div_pp)


def result_90(m) -> str | None:
    """The realized three-way outcome under the stream's own rule (intl_elo.load):
    the 90-minute score; else the score of a FT row; else None (no result: an
    AET/PEN row without a 90-minute score is never scored, law 4)."""
    if m.home_score_90 is not None and m.away_score_90 is not None:
        hg, ag = m.home_score_90, m.away_score_90
    elif (m.status_raw or "").upper() == "FT" and m.home_score is not None and m.away_score is not None:
        hg, ag = m.home_score, m.away_score
    else:
        return None
    return "H" if hg > ag else ("A" if hg < ag else "D")


def _ll(p) -> float | None:
    return None if p is None else -math.log(max(float(p), 1e-12))


def _agg(rows: list[dict], close: bool = True) -> dict:
    n = len(rows)
    return {"n": n, "hits": sum(1 for r in rows if r["hit"]),
            "ll_model": sum(r["ll_model"] for r in rows) / n if n else None,
            "ll_close": sum(r["ll_close"] for r in rows) / n if n and close else None}


def grade(days: int = 30, export_dir: str = "exports", now: datetime | None = None, progress=None) -> dict:
    """Live CLV: the shadow's top pick vs the three-way book close (#207
    contract), from the last call before kickoff.

    ARCHITECT 2026-10-07 item 4 (d) adds, per graded row: the result (the
    stream's 90-minute rule), the hit (top pick == result), the model's
    three-way log-loss of the realized outcome, and the book close's on the
    same row when the close is priced; the aggregate model vs close log-loss
    over the SAME priced games only (a close, a result and a model probability
    on the row; n priced / unpriced / without a result stated); and the split
    by |model − close| on the top-pick side: <4, 4-10, 10-15, >=15pp.
    Read-only; not a record (the confirmation read is intl-elo-confirm)."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Odds
    from src.walters.close import close_1x2, outcomes_for, priced

    now = now or utc_now_naive()
    calls = last_calls(export_dir)
    clvs, lines, rows = [], [], []
    graded = unpriced = 0
    with session_scope() as s:
        for mid, c in sorted(calls.items(), key=lambda kv: kv[1].get("utc_date") or ""):
            m = s.get(Match, mid)
            if m is None or m.status != MatchStatus.FINISHED or m.utc_date < now - timedelta(days=days):
                continue
            graded += 1
            pr = c["prediction"]
            sel = PICK[pr["top_pick"]]
            odds = list(s.execute(select(Odds).where(Odds.match_id == m.id, Odds.market == "1X2")).scalars())
            cl = close_1x2(odds, m.utc_date, outcomes_for(m.sport))
            clv = None
            if priced(cl):
                clv = pr["top_pick_prob"] - cl["fair"][sel]
                clvs.append(clv)
            else:
                unpriced += 1
            res = result_90(m)
            side = OUTCOME_SIDE.get(res)
            model_p = {"HOME": pr.get("home_win_prob"), "DRAW": pr.get("draw_prob"), "AWAY": pr.get("away_win_prob")}
            hit = None if side is None else sel == side
            ll_model = _ll(model_p[side]) if side is not None else None
            ll_close = _ll(cl["fair"][side]) if side is not None and clv is not None else None
            rows.append({"match_id": m.id, "pick": sel, "pick_prob": pr["top_pick_prob"],
                         "close_pick": cl["fair"][sel] if clv is not None else None,
                         "div_pp": clv * 100 if clv is not None else None,
                         "bucket": div_bucket(clv * 100) if clv is not None else None,
                         "result": res, "hit": hit, "ll_model": ll_model, "ll_close": ll_close})
            line = (f"  {m.away_team.name[:14]:14} @ {m.home_team.name[:15]:15} pick {sel} "
                    f"{pr['top_pick_prob']:.3f} close={'%.3f' % cl['fair'][sel] if clv is not None else '  — '} "
                    f"div={'%+.1fpp' % (clv * 100) if clv is not None else '—'}"
                    f" · result {res or '—'} hit {'—' if hit is None else ('Y' if hit else 'N')}"
                    f" · LL model {'—' if ll_model is None else '%.3f' % ll_model}"
                    f" close {'—' if ll_close is None else '%.3f' % ll_close}")
            lines.append(line)
            if progress:
                progress(line)
    same = [r for r in rows if r["ll_close"] is not None and r["ll_model"] is not None]
    scored = [r for r in rows if r["ll_model"] is not None]
    return {"graded": graded, "priced": len(clvs), "unpriced": unpriced,
            "mean_clv_pp": round(sum(clvs) / len(clvs) * 100, 2) if clvs else None,
            "calls_on_file": len(calls), "lines": lines,
            # ARCHITECT 2026-10-07 item 4 (d)
            "rows": rows, "no_result": sum(1 for r in rows if r["result"] is None),
            "all_scored": _agg(scored, close=False),        # every row with a result (priced or not): model side only
            "same_priced": _agg(same),           # model vs close on the SAME priced games
            "priced_no_result": sum(1 for r in rows if r["div_pp"] is not None and r["result"] is None),
            "buckets": {name: _agg([r for r in same if r["bucket"] == name]) for name, _, _ in DIV_BUCKETS}}


def confirmation_read(now: datetime | None = None) -> dict:
    """The plan's read so far: the first-60 set priced predict-then-update
    (walk-forward over the whole stream), model log-loss vs naive − 0.010."""
    from src.db.database import session_scope
    from src.walters import intl_elo as ie

    now = now or utc_now_naive()
    e, c_mult, k_mult = frozen()
    with session_scope() as s:
        games, _ = ie.load(s, rule="v3")
        co = cohort(e, s)
        elig = eligible_fixtures(s, e)
        status = {f["id"]: f["status"] for f in elig}
        unscoreable = {f["id"]: f["unscoreable"] for f in elig}
        s.rollback()
    train = [g for g in games if ie.TRAIN_FROM <= g.kickoff < ie.TRAIN_TO]
    if not train:
        raise ShadowRefused("no training-stream games stored: run intl-sync first")
    mu = sum(g.hg + g.ag for g in train) / (2 * len(train))
    base = ie.naive(train)
    games = [g for g in games if g.kickoff < now]
    want = _labelled(co["ids"], games)
    m = ie.IntlElo(mu=mu, c_mult=c_mult, k_mult=k_mult)
    ll_m = ll_n = 0.0
    scored, first = [], None
    for g in games:
        if g.id in want:
            q = base["neutral"] if g.neutral is True else base["home"]
            ll_m += ie.ll3(m.probs(g), g.outcome)
            ll_n += ie.ll3(q, g.outcome)
            scored.append(g.id)
            first = first or g.kickoff
        m.update(g)
    n = len(scored)
    plan = e["confirmation_plan"]
    pending = sorted(set(co["ids"]) - set(scored))
    out = {"n": n, "n_games": plan["n_games"], "bar": plan["bar"], "scored_ids": scored,
           "first_game_at": first.strftime("%Y-%m-%dT%H:%M:%SZ") if first else None,
           "cohort_state": co["state"], "cohort_size": len(co["ids"]), "eligible_stored": co["eligible_stored"],
           "pending": [{"id": i, "status": status.get(i, "not stored")} for i in pending],
           "release_due": sum(1 for i in pending if unscoreable.get(i) and co["state"] == "frozen"),
           # recordable only as the WHOLE frozen cohort, every fixture labelled
           "complete": co["state"] == "frozen" and not pending and n == plan["n_games"]}
    if n:
        out.update({"log_loss": ll_m / n, "naive_log_loss": ll_n / n,
                    "reference_log_loss": ll_n / n - ie.LL_MARGIN})
    return out


def results_section(days: int, export_dir: str = "exports") -> str:
    """RESULTS.md: the UNL shadow's live CLV in its own section (NHL-style),
    never a record line beside the live sports."""
    r = grade(days=days, export_dir=export_dir)
    head = f"## UNL — SHADOW, CONFIRMATION WINDOW ({MODEL_VERSION} · PASS, production only on CONFIRMED)\n\n"
    if not r["graded"]:
        return head + f"Live model-close divergence only. No graded shadow calls in window ({r['calls_on_file']} calls on file).\n"
    return head + (f"- Live model-close divergence only; not a record. Graded calls: {r['graded']}\n"
                   "- Mean pick-vs-close: "
                   + (f"{r['mean_clv_pp']:+.2f}pp (n={r['priced']} priced)" if r["mean_clv_pp"] is not None
                      else f"— (no stored close; {r['unpriced']} unpriced)") + "\n")
