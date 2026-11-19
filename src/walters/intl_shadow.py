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

import errno
import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

from src.timeutil import utc_now_naive
from src.walters.provenance import git_sha as _git_sha

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
           "exported_at": now.isoformat(),
           "git_sha": _git_sha(),  # addendum 249 item 2: the producing checkout (export.py's stamp)
           "window_hours": hours, "note": NOTE,
           "fit": r["fit"], "count": len(r["rows"]), "predictions": r["rows"]}
    with open(path, "w") as f:
        json.dump(doc, f, indent=2, default=str)
    return path, doc


def last_calls(export_dir: str = "exports") -> dict[int, dict]:
    """match_id -> the LAST shadow row written before its kickoff."""
    return calls_from_files(sorted(Path(export_dir).glob(f"{FILE_PREFIX}*.json")))


def calls_from_files(files, label=lambda f: f.name) -> dict[int, dict]:
    """last_calls over the given shadow files (in the order given; a tie on exported_at keeps the later file);
    `label(f)` names each row's source_file. The provenance receipt reads several export folders through it."""
    out: dict[int, dict] = {}
    for f in files:
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
                out[mid] = {**r, "exported_at": at, "source_file": label(f)}
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
    out = {"n": n, "hits": sum(1 for r in rows if r["hit"]),
           "ll_model": sum(r["ll_model"] for r in rows) / n if n else None,
           "ll_close": sum(r["ll_close"] for r in rows) / n if n and close else None}
    if close:      # ARCHITECT 2026-10-13 (addendum 63 item 3): the record against the close, on the same priced games
        from src.walters.vs_close import block
        out["vs_close"] = block([(r["p_model"], r["p_close"]) for r in rows])
    return out


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
                         "result": res, "hit": hit, "ll_model": ll_model, "ll_close": ll_close,
                         # addendum 63 item 3: the outcome's probability by the model and by the close
                         "p_model": model_p[side] if ll_model is not None else None,
                         "p_close": cl["fair"][side] if ll_close is not None else None})
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


# THE COPY (ARCHITECT 2026-11-11 18:20 ET, addendum 346 item 1, verbatim): "`--db PATH` on `intl-elo-confirm`, fenced by
# `mlb_pitchers_gate.check_db` (outside data/ by identity, never the configured DB, never created, refused beside a
# -wal, -shm or -journal file), the whole read on `mlb_pitchers_gate.readonly_session(copy)` (mode=ro + immutable=1;
# addendum 198 item 6(ii)), `confirmation_read` taking an optional session as `fit()` does, the copy's path and sha256
# printed. NOTHING ELSE CHANGES". Why (addendum 345 item 3, 346 item 5): since the 10-26 cutover the writer of record is
# the host, whose checkout is a tag and is never written, and the record writes the registry inside the checkout that
# runs it; the laptop reads the host's pulled .backup copy and the registry change lands in a PR.
COPY_SIDECARS = ("-wal", "-shm", "-journal")
# Every table the read touches (intl_elo.load, cohort, eligible_fixtures): probed on the copy before its sha line
# prints, so a copy without one is REFUSED (exit 2), never a traceback after the read began (Code's pre-push review).
COPY_TABLES = ("competitions", "matches", "match_neutral_derived", "intl_match_venue")


def check_copy(db) -> Path:
    """--db PATH: mlb_pitchers_gate.check_db itself, unchanged (an existing file, never created; never under the repo's
    data/ (or DATA_DIR) nor, from a worktree, the main checkout's data/, by resolved path, and never a hard link to a
    file directly under one; never the app's configured database); then refused when a -wal, -shm or -journal file sits
    beside it (immutable=1 would ignore it and read committed pages still in a WAL as missing; a fresh .backup copy has
    none); then each table the read touches (COPY_TABLES) probed through the same mode=ro + immutable=1 URI. A refusal
    reads nothing and writes nothing. The copy must not be replaced or written while the command runs: the CLI hashes it
    before and after the read and refuses on a difference."""
    import sqlite3

    from src.walters import mlb_pitchers_gate as mp
    try:
        path = mp.check_db(db)
        try:
            sides = copy_sidecars(path)
        except OSError as err:                     # #940 item 1: refused, never a traceback; never read as absent
            hint = "; take the copy under a shorter name" if err.errno == errno.ENAMETOOLONG else ""
            raise mp.GateRefused(f"--db {db}: a sidecar beside it cannot be checked ({err!r}){hint}") from None
        for name in sides:
            raise mp.GateRefused(f"--db {db} has a {name[len(path.name):]} sidecar ({name}): not a fresh .backup "
                                 "copy; immutable=1 would ignore it and read a stale store; take a fresh .backup copy")
        con = mp.open_ro(path)
        try:
            for t in COPY_TABLES:
                try:
                    con.execute(f"SELECT 1 FROM {t} LIMIT 1")
                except sqlite3.Error as e:
                    raise mp.GateRefused(f"--db {db}: the copy cannot be read for table {t} ({e})")
        finally:
            con.close()
    except mp.GateRefused as err:
        raise ShadowRefused(f"{err}; nothing read, nothing written")
    return path


def copy_sidecars(path: Path) -> list[str]:
    """The -wal, -shm and -journal files beside the copy, by name (none for a fresh .backup copy). Read before the read
    (check_copy) and again after it (the CLI): a sidecar that appears during the read can hold committed pages the
    immutable open ignored, so the main file's unchanged sha256 alone would not show the copy changed (Codex P2, #938).
    Probed with os.stat: only "no such file" (FileNotFoundError, NotADirectoryError) reads as absent; any other OSError
    is raised to the caller, never read as absent (law 4, #940 item 1). One case: a copy name of 248 to 255 bytes makes
    "<name>-journal" longer than the filesystem allows (ENAMETOOLONG), which os.stat raises on every Python and
    Path.exists() stopped raising in 3.14. Each caller words its own refusal: check_copy before the read ("nothing
    read, nothing written"), the CLI after it ("nothing recorded")."""
    out = []
    for sfx in COPY_SIDECARS:
        side = path.with_name(path.name + sfx)
        try:
            os.stat(side)
        except (FileNotFoundError, NotADirectoryError):
            continue
        out.append(side.name)
    return out


def copy_sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(games, want, train, mu: float, c_mult: float, k_mult: float) -> dict:
    """One line of the read: predict-then-update over the whole stream, the cohort scored; the naive rates estimated
    on THIS line's training games by THIS line's flags (ARCHITECT 2026-11-19, addendum 429 item 1(a), (A))."""
    from src.walters import intl_elo as ie

    base = ie.naive(train)
    m = ie.IntlElo(mu=mu, c_mult=c_mult, k_mult=k_mult)
    ll_m = ll_n = 0.0
    scored, first, probs = [], None, {}
    for g in games:
        if g.id in want:
            q = base["neutral"] if g.neutral is True else base["home"]
            p = m.probs(g)
            ll_m += ie.ll3(p, g.outcome)
            ll_n += ie.ll3(q, g.outcome)
            scored.append(g.id)
            probs[g.id] = p
            first = first or g.kickoff
        m.update(g)
    return {"ll_m": ll_m, "ll_n": ll_n, "scored": scored, "first": first, "probs": probs, "base": base}


def naive_rates(base: dict) -> dict:
    """The naive baseline's rates as estimated on the training stream (intl_elo.naive), printed beside each line."""
    h, d, a = base["home"]
    return {"home": [round(h, 4), round(d, 4), round(a, 4)], "neutral_draw": round(base["neutral"][1], 4),
            "n_train_nonneutral": base["n_train_nonneutral"], "n_train_neutral": base["n_train_neutral"]}


def _line_summary(w: dict, n_games: int, bar: float) -> dict:
    from src.walters import intl_elo as ie
    n = len(w["scored"])
    out = {"n": n, "n_games": n_games, "bar": bar, "naive_rates": naive_rates(w["base"])}
    if n:
        out.update({"log_loss": w["ll_m"] / n, "naive_log_loss": w["ll_n"] / n,
                    "reference_log_loss": w["ll_n"] / n - ie.LL_MARGIN})
    return out


def read_on_copy(db, fn, echo=print):
    """fn(session) on a .backup copy under addendum 346's fence, as intl-elo-confirm --db reads it: check_copy (outside
    data/, never the configured DB, never created, no sidecar, every COPY_TABLES table readable), the sha256 printed
    before the read and checked after it, the sidecars checked after it (#940: only those two checks are the copy's),
    the whole read on mlb_pitchers_gate.readonly_session (mode=ro + immutable=1). ShadowRefused on any of them."""
    from sqlalchemy.exc import DBAPIError

    from src.walters import mlb_pitchers_gate as mp
    copy = check_copy(db)
    try:
        sha_before = copy_sha256(copy)
    except OSError as err:
        raise ShadowRefused(f"--db {copy}: the copy could not be hashed ({err!r}); nothing read, nothing written")
    echo(f"--db {copy} · sha256 {sha_before} · a .backup copy, opened {mp.COPY_URI_QUERY.lstrip('?')} (the app's "
         "database is not read)")
    try:
        with mp.readonly_session(copy) as s:
            out = fn(s)
            try:
                sha_after = copy_sha256(copy)
                sides_after = copy_sidecars(copy)
            except OSError as err:
                raise ShadowRefused(f"--db {copy}: the copy could not be re-read after the read ({err!r})") from None
    except DBAPIError as err:
        raise ShadowRefused(f"--db {copy}: the copy could not be read ({err.orig!r})") from None
    if sides_after:
        raise ShadowRefused(f"--db {copy} changed during the read: {', '.join(sides_after)} appeared beside it, which "
                            "immutable=1 ignores; the receipt is not tied to the copy")
    if sha_after != sha_before:
        raise ShadowRefused(f"--db {copy} changed during the read (sha256 {sha_before[:16]}… before, {sha_after[:16]}… "
                            "after): the receipt is not tied to the printed copy")
    return out


def confirmation_read(now: datetime | None = None, s=None) -> dict:
    """The plan's read so far: the first-60 set priced predict-then-update
    (walk-forward over the whole stream), model log-loss vs naive − 0.010.
    `s`: a session to read through (intl-elo-confirm --db: the copy's mode=ro + immutable=1 session, addendum 346); None
    reads the app's database, as before.

    THE READ BOTH WAYS (ARCHITECT 2026-10-23, addendum 160 item 3: "The read [...] is reported BOTH ways (stored flags;
    corrected flags); the verdict is taken on the corrected inputs; the frozen method is untouched"; 161 item 2:
    "'Stored' = the provider's flags as derived before any override (provider_flag); 'corrected' = the flags after
    intl-venue-override --apply re-derives them [...] the verdict and --record stand on the corrected flags"; 429 item
    1(a): "Each line uses its own flags throughout, the naive rates included"). The keys of the read as before are the
    CORRECTED line (neutral_v3 as stored), which --record takes. While the override table holds an entry, `both` adds
    the stored-flags line, from the same load in the same session (provider_flag of each row's stored venue and home
    countries), each line whole with its naive rates, and how many cohort fixtures the two price differently with the
    largest single difference in a probability (427 item 3(d)). `derive_mismatch`: the rows whose neutral_v3 differs
    from intl_venues.derive() (the override not applied on this store, or lapsed): --record refuses while any is listed
    (429 item 1(d)). With an empty table, the read is today's."""
    from dataclasses import replace

    from sqlalchemy import select

    from src.db.schema import IntlMatchVenue
    from src.ingestion import intl_venues as iv
    from src.walters import intl_elo as ie

    now = now or utc_now_naive()
    e, c_mult, k_mult = frozen()

    def read(s):
        games, _ = ie.load(s, rule="v3")
        co = cohort(e, s)
        elig = eligible_fixtures(s, e)
        venue = {v.match_id: (v.venue_id, v.venue_country, v.home_country, v.neutral_v3)
                 for v in s.execute(select(IntlMatchVenue)).scalars()}
        return games, co, elig, venue

    if s is None:
        from src.db.database import session_scope
        with session_scope() as s2:
            games, co, elig, venue = read(s2)
            s2.rollback()
    else:
        games, co, elig, venue = read(s)
    status = {f["id"]: f["status"] for f in elig}
    unscoreable = {f["id"]: f["unscoreable"] for f in elig}
    train = [g for g in games if ie.TRAIN_FROM <= g.kickoff < ie.TRAIN_TO]
    if not train:
        raise ShadowRefused("no training-stream games stored: run intl-sync first")
    mu = sum(g.hg + g.ag for g in train) / (2 * len(train))
    games = [g for g in games if g.kickoff < now]
    want = _labelled(co["ids"], games)
    w = _walk(games, want, train, mu, c_mult, k_mult)
    ll_m, ll_n, scored, first = w["ll_m"], w["ll_n"], w["scored"], w["first"]
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
    out["derive_mismatch"] = sorted(mid for mid, (vid, vc, hc, flag) in venue.items()
                                    if iv.derive(vid, vc, hc)[0] != flag)
    if iv.VENUE_COUNTRY_OVERRIDES:
        pf = {mid: iv.provider_flag(vc, hc) for mid, (vid, vc, hc, flag) in venue.items()}

        def provider(gs):
            return [replace(g, neutral=pf[g.id]) if g.id in pf else g for g in gs]

        w2 = _walk(provider(games), want, provider(train), mu, c_mult, k_mult)
        diffs = sorted(((max(abs(a - b) for a, b in zip(w["probs"][i], w2["probs"][i])), i) for i in w["probs"]),
                       key=lambda t: (-t[0], t[1]))
        moved = [(d, i) for d, i in diffs if d > 1e-12]
        out["both"] = {"corrected": _line_summary(w, plan["n_games"], plan["bar"]),
                       "stored": _line_summary(w2, plan["n_games"], plan["bar"]),
                       "priced_differently": len(moved), "priced_of": len(diffs),
                       "max_diff": moved[0] if moved else (0.0, None)}
    return out


def _line_text(x: dict) -> str:
    nr = x["naive_rates"]
    rates = (f"naive rates: home H/D/A {nr['home'][0]:.4f}/{nr['home'][1]:.4f}/{nr['home'][2]:.4f} over "
             f"{nr['n_train_nonneutral']} train games, neutral draw {nr['neutral_draw']:.4f} over {nr['n_train_neutral']}")
    head = f"{x['n']}/{x['n_games']} labelled"
    if not x["n"]:
        return f"{head} · {rates}"
    return (f"{head} · log-loss {x['log_loss']:.4f} · naive {x['naive_log_loss']:.4f} · reference (naive − 0.010) "
            f"{x['reference_log_loss']:.4f} · bar {x['bar']:.4f} · {rates}")


def both_ways_lines(r: dict) -> list[str]:
    """intl-elo-confirm's lines after "so far": the read both ways while the override table holds an entry (160 item 3;
    161 item 2; 429 item 1(a): "The read prints each line whole: log-loss, naive, reference (naive − 0.010), the bar,
    and its naive rates"; 427 item 3(d)), and the rows the override has not been applied to (429 item 1(d)'s guard).
    Nothing when the table is empty and every row agrees with the derivation: the console is today's."""
    L = []
    b = r.get("both")
    if b:
        L.append("  BOTH WAYS (ARCHITECT 2026-10-23, addendum 160 item 3; 161 item 2; 429 item 1(a)): each line on its "
                 "own flags throughout, its naive rates included; the verdict and --record stand on the corrected flags")
        L.append("    corrected flags (neutral_v3 as stored, after intl-venue-override --apply): "
                 + _line_text(b["corrected"]))
        L.append("    stored flags (the provider's venue country alone, no override): " + _line_text(b["stored"]))
        d, mid = b["max_diff"]
        L.append(f"    cohort fixtures priced differently by the two: {b['priced_differently']} of {b['priced_of']} · "
                 "largest single difference in a probability: "
                 + (f"{d:.4f} (fixture {mid})" if mid is not None else "none"))
    mm = r.get("derive_mismatch") or []
    if mm:
        L.append(f"  NOT APPLIED: {len(mm)} row(s) whose neutral_v3 differs from intl-venue-override's derivation (the "
                 "override not applied on this store, or lapsed): " + ", ".join(map(str, mm[:12]))
                 + (" …" if len(mm) > 12 else "") + " — --record refuses until intl-venue-override --apply has run")
    return L


def results_section(days: int, export_dir: str = "exports", graded: dict | None = None) -> str:
    """RESULTS.md: the UNL shadow's live CLV in its own section (NHL-style),
    never a record line beside the live sports. `graded`: grade()'s own result for these days and export_dir, when the
    caller already holds it (results-tally's JSON, addendum 289 item 3); None: graded here, as before."""
    r = graded if graded is not None else grade(days=days, export_dir=export_dir)
    head = f"## UNL — SHADOW, CONFIRMATION WINDOW ({MODEL_VERSION} · PASS, production only on CONFIRMED)\n\n"
    if not r["graded"]:
        return head + (f"Live model-close divergence and the record against the close. No graded shadow calls in window "
                       f"({r['calls_on_file']} calls on file).\n")
    from src.walters.vs_close import line
    return head + (f"- Live model-close divergence and the record against the close; not a record of calls. Graded "
                   f"calls: {r['graded']}\n"
                   "- Mean pick-vs-close: "
                   + (f"{r['mean_clv_pp']:+.2f}pp (n={r['priced']} priced)" if r["mean_clv_pp"] is not None
                      else f"— (no stored close; {r['unpriced']} unpriced)") + "\n"
                   # ARCHITECT 2026-10-13 (addendum 63 item 3): "the INTL and NHL grades" carry the record against
                   # the close, on the same priced games with a result
                   + f"- {line(r['same_priced']['vs_close'])}\n")
