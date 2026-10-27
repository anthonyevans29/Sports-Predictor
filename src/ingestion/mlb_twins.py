"""
MLB TWINS DEDUPE (#569 RULED, ARCHITECT 2026-10-21 12:46 ET, addendum 153 item 2), verbatim: "Then the dedupe, dry run
first, one PR, improve's holdout before/after in the body:
   (a) The kept row of a pair is the one with references (odds, snapshots, predictions, history, Kalshi legs); where
both have none, the lower id (the first stored); where both have some, REFUSED and listed for me. The kept row takes the
provider's current date, status and score (the make-up's), and the other row becomes STALE_ORPHAN with its references
re-pointed to the kept row (predictions and history included: a graded prediction never loses its game), as
dedupe-matches re-points the american-football family's. Nothing is deleted.
   (b) Class 1 (same-minute twins, 7) and class 4 (two FINISHED rows a day apart, 4): merge by (a); class 4 keeps the
earlier row, which holds the Kalshi settlements, and takes the later row's date.
   (c) Class 2 (a FINISHED game and a SCHEDULED copy, 5218 and 5308): the FINISHED row is kept; the SCHEDULED copy
becomes STALE_ORPHAN; its predictions and history re-point to the kept row as (a) says, and the record counts them as
predictions of a game already played at the time (never graded as calls; a line in the receipt). #638 is corrected by
that comment: they were never rainouts.
   (d) Class 3 (POSTPONED plus its make-up, 30): the POSTPONED row becomes STALE_ORPHAN; the make-up is the game. No
merge of fields is needed (the POSTPONED rows hold nothing); where one does, (a) applies.
   (e) Acceptance in the PR body before merge: the dry run's console on the laptop listing all 43 pairs with the kept id
and the reason, and improve's holdout line BEFORE/AFTER (the training set loses the double counts). Money-adjacent: my
read of both before the merge call."

The readings built here (each stated in the PR for the architect):
  * A GROUP: the MLB rows (every competition, as the statsapi upsert looks a gamePk up across the sport's rows, #650)
    that are not STALE_ORPHAN and carry one external_ids["mlb_stats_api"]. A group of three or more rows is REFUSED.
  * THE CLASS, from the two rows' stored state: both FINISHED with one score at one kickoff minute = 1; both FINISHED
    with one score at two kickoffs = 4; FINISHED and SCHEDULED = 2; POSTPONED and another status = 3. Two FINISHED rows
    with different scores, and any other pair of statuses, are REFUSED (no class of the ruling).
  * REFERENCES, the ruling's list: odds, odds_snapshots (Kalshi quotes included), predictions, prediction_history and
    kalshi_settled_markets (the Kalshi legs' settlements), counted per row.
  * THE KEPT ROW: class 1 by (a). Class 2 the FINISHED row (c), whatever either holds. Class 3 the make-up (d); a
    POSTPONED row holding references takes (a): it is kept when the make-up holds none, and takes the make-up's state;
    both holding some is REFUSED. Class 4 the earlier row (b), taking the later row's date; a later row holding
    references is REFUSED (b's keep and (a)'s keep would disagree), as is both holding some.
  * THE STATE the kept row takes, "the provider's current date, status and score": utc_date, status, status_raw,
    home_score, away_score and full_time_result from the current row (class 2: the FINISHED row; class 3: the make-up;
    class 4: the later row; class 1: the kept row itself, the two being one minute and one score). A NULL never blanks
    a stored value. Every change is printed.
  * RE-POINTING: every table referencing matches.id, read from the schema (match_dedupe._fk_tables; a table the live DB
    lacks is skipped and named). The references, pitcher_appearances and umpire_games (one row per source game, by
    their unique indexes) always move. Any other table moves only when the kept row holds no row of it: where both
    hold one (match_participants' starter, game_weather, match_stats' unique (match_id, team_id) ...), the retired
    row's own stays on it, counted and printed. Nothing is deleted.
  * THE RETIRED ROW: status STALE_ORPHAN; its mlb_stats_api id leaves the key (a sync looks the gamePk up by it and
    must find the kept row only) for mlb_stats_api_prev, with mlb_stats_api_merged_into (the kept id) and
    mlb_stats_api_deduped_at. The kept row records mlb_stats_api_merged_from. THE HOST (ARCHITECT 2026-10-27, addendum
    169 item 3(c): "both, laptop first (the MLB record), the host second under its lock"): the api-sports fallback
    looks a game up by external_ids["api_baseball"], so the retired row's api_baseball id moves the same way, to
    api_baseball_prev, and the kept row takes it when it holds none; the fallback never pairs a STALE_ORPHAN row
    (mlb_apisports.sync_matches).
  * CLASS 2's PREDICTIONS: each prediction re-pointed from the SCHEDULED copy carries factor_breakdown["dedupe_569"]
    ({from_match, into, computed_at, kickoff}); evaluate_finished never grades a prediction carrying it (training.py).
    The receipt line counts them and their history rows.
  * THE TRAINING SET: the FINISHED MLB rows per season before, and after (the retired FINISHED rows out).
  * --apply needs --backup PATH and --gamepks naming the groups (cli.py; as retire-orphans names its rows): the apply
    plans again in its own session under the chains' DB lock, and a named gamePk whose fresh plan is not a merge is
    REFUSED and left. A dry run rolls back.
"""
from __future__ import annotations

from collections import Counter, defaultdict

SOURCE = "mlb_stats_api"
PREV = f"{SOURCE}_prev"
MERGED_INTO = f"{SOURCE}_merged_into"
MERGED_FROM = f"{SOURCE}_merged_from"
DEDUPED_AT = f"{SOURCE}_deduped_at"
MARK = "dedupe_569"                 # factor_breakdown key: a prediction of a game already played, never graded
REFERENCES = ("odds", "odds_snapshots", "predictions", "prediction_history", "kalshi_settled_markets")
ALWAYS_MOVE = REFERENCES + ("pitcher_appearances", "umpire_games")
OTHER_IDS = ("api_baseball",)      # the host's api-sports fallback id (mlb_apisports.SOURCE): moves with the gamePk
STATE = ("utc_date", "status", "status_raw", "home_score", "away_score", "full_time_result")


def _sid(m) -> str | None:
    v = (m.external_ids or {}).get(SOURCE)
    return str(v) if v is not None and str(v).strip() else None


def _st(m) -> str:
    return m.status.name if m.status is not None else "NULL"


def _minute(m):
    return m.utc_date.replace(second=0, microsecond=0) if m.utc_date else None


def _val(v):
    if hasattr(v, "isoformat"):
        return v.isoformat(timespec="minutes")
    return getattr(v, "name", v)


def groups(s) -> dict:
    """{gamePk: [rows]} for every gamePk two or more live MLB rows hold, rows by id."""
    from sqlalchemy import select

    from src.db.schema import Match, MatchStatus, Sport

    held = defaultdict(list)
    for m in s.execute(select(Match).where(Match.sport == Sport.MLB, Match.status != MatchStatus.STALE_ORPHAN)
                       .order_by(Match.id)).scalars():
        if _sid(m):
            held[_sid(m)].append(m)
    return {pk: rows for pk, rows in sorted(held.items()) if len(rows) > 1}


def references(s, tables, mid: int) -> dict:
    from sqlalchemy import func, select
    return {t.name: n for t, c, _ in tables if t.name in REFERENCES
            for n in [s.execute(select(func.count()).select_from(t).where(c == mid)).scalar()] if n}


def classify(a, b) -> tuple[int | None, str]:
    st = {_st(a), _st(b)}
    if st == {"FINISHED"}:
        if (a.home_score, a.away_score) != (b.home_score, b.away_score):
            return None, (f"two FINISHED rows with different scores ({a.home_score}-{a.away_score}, "
                          f"{b.home_score}-{b.away_score}): no class of the ruling")
        return (1, "same-minute twins") if _minute(a) == _minute(b) else (4, "two FINISHED rows, two kickoffs")
    if st == {"FINISHED", "SCHEDULED"}:
        return 2, "a FINISHED game and a SCHEDULED copy"
    if "POSTPONED" in st and len(st) == 2:
        return 3, "a POSTPONED row and its make-up"
    return None, f"statuses {' and '.join(sorted(st)) if len(st) == 2 else _st(a) + ' twice'}: no class of the ruling"


def decide(cls: int, a, b, refs: dict) -> dict:
    """{kept, other, current, why} or {refused}: the kept row, the retired row and the row whose state the kept takes."""
    has = {m.id: bool(refs[m.id]) for m in (a, b)}
    both = has[a.id] and has[b.id]
    if cls == 2:
        kept, other = (a, b) if _st(a) == "FINISHED" else (b, a)
        return {"kept": kept, "other": other, "current": kept, "why": "(c) class 2: the FINISHED row is kept"}
    if cls == 3:
        post, make = (a, b) if _st(a) == "POSTPONED" else (b, a)
        if both:
            return {"refused": "(d) with (a): both rows hold references"}
        if has[post.id]:
            return {"kept": post, "other": make, "current": make,
                    "why": "(d) with (a): the POSTPONED row holds references, the make-up none; it takes the make-up's "
                           "date, status and score"}
        return {"kept": make, "other": post, "current": make, "why": "(d) class 3: the make-up is the game"}
    if cls == 4:
        early, late = sorted((a, b), key=lambda m: (m.utc_date, m.id))
        if both:
            return {"refused": "(a): both rows hold references"}
        if has[late.id]:
            return {"refused": "(b) keeps the earlier row, but the later row holds the references ((a) would keep it)"}
        return {"kept": early, "other": late, "current": late,
                "why": "(b) class 4: the earlier row is kept" + (" (it holds the references)" if has[early.id] else
                                                                 " (neither holds references)")
                       + " and takes the later row's date"}
    if both:
        return {"refused": "(a): both rows hold references"}
    if has[b.id]:
        return {"kept": b, "other": a, "current": b, "why": "(a) class 1: the row holding the references"}
    return {"kept": a, "other": b, "current": a,
            "why": "(a) class 1: " + ("the row holding the references" if has[a.id] else
                                      "neither holds references, the lower id (the first stored)")}


def describe(m, refs) -> dict:
    return {"id": m.id, "status": _st(m), "utc": _val(m.utc_date), "score": (f"{m.home_score}-{m.away_score}"
            if m.home_score is not None else None), "season": m.season, "stage": m.stage, "refs": refs or {}}


def state_changes(kept, current) -> dict:
    if current is kept:
        return {}
    return {f: (_val(getattr(kept, f)), _val(getattr(current, f))) for f in STATE
            if getattr(current, f) is not None and getattr(current, f) != getattr(kept, f)}


def moves(s, tables, kept, other) -> tuple[dict, dict]:
    """({table: rows re-pointed}, {table: rows left on the retired row}) as the module doc says."""
    from sqlalchemy import func, select
    move, left = {}, {}
    for t, c, _ in tables:
        n = s.execute(select(func.count()).select_from(t).where(c == other.id)).scalar()
        if not n:
            continue
        if t.name in ALWAYS_MOVE or not s.execute(select(func.count()).select_from(t).where(c == kept.id)).scalar():
            move[t.name] = n
        else:
            left[t.name] = n
    return move, left


def plan(s) -> dict:
    from sqlalchemy import select

    from src.db.schema import Prediction, PredictionHistory
    from src.ingestion import match_dedupe as md

    tables = md._fk_tables(s)
    out = {"groups": [], "refused": [], "skipped_absent": sorted(md.SKIPPED_ABSENT)}
    for pk, rows in groups(s).items():
        refs = {m.id: references(s, tables, m.id) for m in rows}
        g = {"gamepk": pk, "rows": [describe(m, refs[m.id]) for m in rows]}
        if len(rows) > 2:
            out["refused"].append({**g, "why": f"{len(rows)} rows hold one gamePk: a pair only"})
            continue
        cls, what = classify(*rows)
        if cls is None:
            out["refused"].append({**g, "why": what})
            continue
        d = decide(cls, *rows, refs)
        if "refused" in d:
            out["refused"].append({**g, "class": cls, "what": what, "why": d["refused"]})
            continue
        kept, other = d["kept"], d["other"]
        move, left = moves(s, tables, kept, other)
        g.update({"class": cls, "what": what, "kept": kept.id, "other": other.id, "why": d["why"],
                  "takes": state_changes(kept, d["current"]), "moves": move, "left": left})
        if cls == 2:
            preds = s.execute(select(Prediction.computed_at).where(Prediction.match_id == other.id)).scalars().all()
            hist = s.execute(select(PredictionHistory.id).where(PredictionHistory.match_id == other.id)).scalars().all()
            g["played_before"] = {"predictions": len(preds), "history": len(hist),
                                  "after_kickoff": sum(1 for p in preds if p and kept.utc_date and p >= kept.utc_date),
                                  "kickoff": _val(kept.utc_date)}
        out["groups"].append(g)
    finished = finished_by_season(s)
    retired = Counter(r["season"] for g in out["groups"] for r in g["rows"]
                      if r["id"] == g["other"] and r["status"] == "FINISHED")
    out["finished"] = {season: (n, n - retired[season]) for season, n in sorted(finished.items())}
    return out


def finished_by_season(s) -> Counter:
    """The FINISHED MLB rows per season: the rows the training set reads."""
    from sqlalchemy import select

    from src.db.schema import Match, MatchStatus, Sport
    return Counter(m.season for m in s.execute(select(Match).where(
        Match.sport == Sport.MLB, Match.status == MatchStatus.FINISHED)).scalars())


def merge(s, tables, g: dict, at: str) -> dict:
    """Apply one planned group (see the module doc). The caller owns the transaction."""
    from sqlalchemy import select, update

    from src.db.schema import Match, MatchStatus, Prediction

    kept, other = s.get(Match, g["kept"]), s.get(Match, g["other"])
    current = other if g["takes"] else kept
    for f in g["takes"]:
        setattr(kept, f, getattr(current, f))
    marked = []
    if g["class"] == 2:
        for p in s.execute(select(Prediction).where(Prediction.match_id == other.id)).scalars():
            p.factor_breakdown = {**(p.factor_breakdown or {}), MARK: {
                "from_match": other.id, "into": kept.id, "computed_at": _val(p.computed_at),
                "kickoff": _val(kept.utc_date),
                "why": "a prediction of a game already played at the time: never graded as a call (#569 (c))"}}
            marked.append(p.id)
    s.flush()
    moved = {}
    for t, c, _ in tables:
        if t.name in g["moves"]:
            moved[t.name] = s.execute(update(t).where(c == other.id).values({c.name: kept.id})).rowcount
    ext_o, ext_k = dict(other.external_ids or {}), dict(kept.external_ids or {})
    pk = ext_o.pop(SOURCE, None)
    ext_o[PREV] = sorted({*(ext_o.get(PREV) or []), str(pk)})
    ext_o[MERGED_INTO], ext_o[DEDUPED_AT] = kept.id, at
    ext_k[MERGED_FROM] = sorted({*(ext_k.get(MERGED_FROM) or []), other.id})
    for key in OTHER_IDS:                          # the host's fallback looks a game up by its own id (addendum 169 3(c))
        v = ext_o.pop(key, None)
        if v is not None:
            ext_o[f"{key}_prev"] = sorted({*(ext_o.get(f"{key}_prev") or []), str(v)})
            ext_k.setdefault(key, v)
    other.external_ids, kept.external_ids = ext_o, ext_k
    other.status = MatchStatus.STALE_ORPHAN
    s.flush()
    return {"gamepk": g["gamepk"], "kept": kept.id, "other": other.id, "moved": moved, "marked": marked}


def run(apply: bool = False, named=None) -> dict:
    """The plan; with apply, the named groups merged (a named gamePk the fresh plan does not merge is refused)."""
    from contextlib import nullcontext

    from src.db.database import session_scope
    from src.ingestion import match_dedupe as md
    from src.timeutil import utc_now_naive

    md.SKIPPED_ABSENT.clear()
    if apply:
        from src.ingestion.service import _db_lock
        lock = _db_lock()
    else:
        lock = nullcontext()
    with lock, session_scope() as s:
        r = plan(s)
        r["applied"], r["merged"], r["refused_at_apply"] = apply, [], []
        if not apply:
            s.rollback()
            return r
        why = md._check_allows_orphan(s)
        if why:
            raise ValueError(f"REFUSED: {why}; nothing was written")
        planned = {g["gamepk"]: g for g in r["groups"]}
        refused = {x["gamepk"]: x["why"] for x in r["refused"]}
        tables = md._fk_tables(s)
        at = utc_now_naive().isoformat(timespec="seconds")
        for pk in dict.fromkeys(named):             # a gamePk named twice is merged once (Codex on #704)
            if pk not in planned:
                r["refused_at_apply"].append({"gamepk": pk, "why": refused.get(pk, "no live MLB rows share it")})
                continue
            r["merged"].append(merge(s, tables, planned[pk], at))
        s.flush()
        after = finished_by_season(s)                # the state the apply leaves, not the plan's (Codex on #704)
        r["finished_applied"] = {season: (n, after[season]) for season, (n, _) in r["finished"].items()}
    return r


def lines(r: dict) -> list[str]:
    import json

    def row(x):
        return (f"match {x['id']} {x['status']} {x['utc']} score {x['score']} season {x['season']} stage {x['stage']} "
                f"references {json.dumps(x['refs'], sort_keys=True) if x['refs'] else 'none'}")
    by = Counter(g["class"] for g in r["groups"])
    L = [f"DEDUPE-MLB-TWINS (#569, addendum 153 item 2) · {'APPLY' if r['applied'] else 'DRY RUN (nothing written)'} · "
         f"gamePks held by two or more live MLB rows {len(r['groups']) + len(r['refused'])} · planned "
         f"{len(r['groups'])} (" + " · ".join(f"class {k} {by[k]}" for k in sorted(by)) + f") · refused "
         f"{len(r['refused'])}"]
    if r["skipped_absent"]:
        L.append(f"  reference tables absent from the live DB, skipped (they hold no references): "
                 f"{', '.join(r['skipped_absent'])}")
    for g in sorted(r["groups"], key=lambda g: (g["class"], g["gamepk"])):
        L.append(f"  [class {g['class']}] gamePk {g['gamepk']} ({g['what']}): KEEPS {g['kept']}, RETIRES {g['other']} "
                 f"to STALE_ORPHAN · {g['why']}")
        for x in g["rows"]:
            L.append(f"      {row(x)}")
        L.append("      the kept row takes: " + (", ".join(f"{f} {a} -> {b}" for f, (a, b) in g["takes"].items())
                                                 or "nothing (its own state is the provider's)"))
        L.append("      re-points: " + (", ".join(f"{t} {n}" for t, n in sorted(g["moves"].items())) or "nothing")
                 + " · left on the retired row (the kept row holds its own): "
                 + (", ".join(f"{t} {n}" for t, n in sorted(g["left"].items())) or "nothing"))
        if "played_before" in g:
            p = g["played_before"]
            L.append(f"      (c) predictions of a game already played at the time: {p['predictions']} prediction(s) "
                     f"({p['after_kickoff']} computed at or after the kept row's kickoff {p['kickoff']}) and "
                     f"{p['history']} history row(s), re-pointed; each prediction marked {MARK}, never graded as a "
                     "call")
    for x in r["refused"]:
        L.append(f"  [REFUSED] gamePk {x['gamepk']}" + (f" (class {x['class']}, {x['what']})" if "class" in x else "")
                 + f": {x['why']} · listed for the architect, nothing written")
        for y in x["rows"]:
            L.append(f"      {row(y)}")
    pb = [g["played_before"] for g in r["groups"] if "played_before" in g]
    L.append(f"  (c) the record: {sum(p['predictions'] for p in pb)} prediction(s) and {sum(p['history'] for p in pb)} "
             f"history row(s) of a game already played at the time, never graded as calls")
    L.append("  the training set's FINISHED MLB rows per season, before -> after: "
             + (" · ".join(f"{k} {a} -> {b}" for k, (a, b) in r["finished"].items()) or "none"))
    if r["groups"]:
        L.append("  to apply, after the architect's read: --apply --backup PATH --gamepks "
                 + ",".join(g["gamepk"] for g in r["groups"]))
    if r["applied"]:
        for m in r["merged"]:
            L.append(f"  MERGED gamePk {m['gamepk']}: kept {m['kept']}, {m['other']} STALE_ORPHAN · re-pointed "
                     + (", ".join(f"{t} {n}" for t, n in sorted(m["moved"].items())) or "nothing")
                     + (f" · predictions marked {MARK}: {', '.join(map(str, m['marked']))}" if m["marked"] else ""))
        for x in r["refused_at_apply"]:
            L.append(f"  REFUSED gamePk {x['gamepk']}: {x['why']} (named, not merged)")
        L.append(f"  merged {len(r['merged'])} · refused {len(r['refused_at_apply'])}")
        L.append("  the training set's FINISHED MLB rows per season after this apply (read back): "
                 + (" · ".join(f"{k} {a} -> {b}" for k, (a, b) in r["finished_applied"].items()) or "none"))
    return L
