"""
MATCH DEDUPE (ARCHITECT 2026-10-03, priority): "sync-matches NCAA (2026-10-03
07:51) created 1006 rows and the fixtures export now holds DUPLICATE games —
a scheduled row (old provider id?) and a finished row for the same fixture
... Receipt: how the two rows differ (ext ids, team ids, utc_date); fix the
matcher so a resync UPDATES; dedupe the 1006 with a receipt (never delete the
row the ledger or odds reference — merge into it)."

A DUPLICATE PAIR: two rows of one competition with the same home AND away team,
kickoffs within WINDOW_H, and DIFFERENT ids under the source. Clusters of three
or more, and pairs that only match home/away SWAPPED, are reported, never
merged.

MERGE (per pair): the KEEPER is the OLDER row (lower id) — the one the ledger,
odds, Kalshi snapshots and predictions were written against before the resync.
The newer row (the resync's) carries the provider's latest state:
  * status / status_raw / utc_date / matchday / stage / scores / result /
    venue copy from it, never blanking a value and never regressing a
    FINISHED keeper to non-finished;
  * the keeper takes its source id; the keeper's old id moves to
    "<source>_prev"; other ids it lacks are added;
  * every row in every table referencing matches.id is re-pointed to the
    keeper (discovered from the schema, not listed by hand); a table where
    match_id is unique and BOTH rows hold an entry refuses the pair (no child
    row is ever deleted);
  * then the newer row — now referenced by nothing — is deleted.
Dry-run by default; --apply needs a verified .backup (CLI).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

WINDOW_H = 12
FIELDS = ("status", "status_raw", "utc_date", "matchday", "stage", "home_score", "away_score",
          "home_score_ht", "away_score_ht", "home_score_90", "away_score_90", "full_time_result", "venue")


def _fk_tables():
    """(table, column, unique_with_match_id) for every column referencing matches.id."""
    from src.db.schema import Base

    out = []
    for t in Base.metadata.sorted_tables:
        for c in t.columns:
            if any(fk.target_fullname == "matches.id" for fk in c.foreign_keys):
                uniq = any(c.name in [x.name for x in con.columns] and len(con.columns) <= 2
                           for con in t.constraints
                           if con.__class__.__name__ in ("UniqueConstraint", "PrimaryKeyConstraint")
                           and [x.name for x in con.columns] != ["id"])
                out.append((t, c, uniq))
    return out


def find_pairs(s, competition_code: str, source: str):
    """(pairs, report): pairs = [(keeper, newer)]; report counts the rest."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match

    comp = s.execute(select(Competition).where(Competition.code == competition_code)).scalar_one_or_none()
    if comp is None:
        raise ValueError(f"competition {competition_code} not in DB")
    by_pair = defaultdict(list)
    for m in s.execute(select(Match).where(Match.competition_id == comp.id)).scalars():
        by_pair[(m.home_team_id, m.away_team_id)].append(m)
    win = timedelta(hours=WINDOW_H)
    pairs, rc, seen = [], Counter(), set()
    for (h, a), rows in by_pair.items():
        rows.sort(key=lambda m: (m.utc_date, m.id))
        for i, m in enumerate(rows):
            if m.id in seen:
                continue
            cluster = [x for x in rows if x.utc_date and m.utc_date and abs(x.utc_date - m.utc_date) <= win]
            if len(cluster) < 2:
                continue
            seen.update(x.id for x in cluster)
            ids = {(x.external_ids or {}).get(source) for x in cluster}
            if len(cluster) > 2:
                rc["refused_cluster_gt2"] += 1
                continue
            if None in ids or len(ids) < 2:
                rc["refused_same_or_missing_source_id"] += 1
                continue
            keeper, newer = sorted(cluster, key=lambda x: x.id)
            pairs.append((keeper, newer))
        for m in rows:                                   # swapped near-pairs: report only
            for x in by_pair.get((a, h), []):
                if h < a and x.utc_date and m.utc_date and abs(x.utc_date - m.utc_date) <= win:
                    rc["swapped_near_pairs_not_merged"] += 1
    return pairs, rc


def describe(keeper, newer, source: str) -> dict:
    """How the two rows differ (the receipt the ruling asks for)."""
    def row(m):
        return {"id": m.id, "ext": (m.external_ids or {}).get(source), "home": m.home_team_id,
                "away": m.away_team_id, "utc": m.utc_date.isoformat() if m.utc_date else None,
                "status": getattr(m.status, "value", m.status), "status_raw": m.status_raw,
                "score": f"{m.home_score}-{m.away_score}" if m.home_score is not None else None,
                "season": m.season}
    k, n = row(keeper), row(newer)
    return {"keeper": k, "newer": n, "differs": sorted(f for f in k if f != "id" and k[f] != n[f])}


def stamp_rekey(ext: dict, source: str, old, new, via: str) -> None:
    """Provenance for a re-key (ARCHITECT 2026-10-03: an apply that re-keyed 962
    rows printed "merged 0" — who re-keyed must be readable from the row):
    the old id joins "<source>_prev" and {"from","to","via","at"} joins
    "<source>_rekeys". via: "dedupe-merge" | "orphan-merge" | "orphan-relink" | "sync"."""
    from src.timeutil import utc_now_naive

    prev = list(ext.get(f"{source}_prev") or [])
    if old and old not in prev:
        prev.append(old)
    ext[f"{source}_prev"] = prev
    if old != new:
        log = list(ext.get(f"{source}_rekeys") or [])
        log.append({"from": old, "to": new, "via": via, "at": utc_now_naive().isoformat(timespec="seconds")})
        ext[f"{source}_rekeys"] = log


def merge(s, keeper, newer, source: str, take_state: bool = True, via: str = "dedupe-merge") -> dict:
    """Merge `newer` into `keeper` (see module doc). Returns {table: re-pointed} or
    {"refused": reason}. Caller owns the transaction. take_state=False (the
    orphan path, when the STALE row is the newer one): the keeper keeps its own
    state and id, the stale row's id joins its "<source>_prev"."""
    from sqlalchemy import func, select, update

    from src.db.schema import MatchStatus

    tables = _fk_tables()
    for t, c, uniq in tables:
        if uniq:
            both = [s.execute(select(func.count()).select_from(t).where(c == mid)).scalar()
                    for mid in (keeper.id, newer.id)]
            if all(both):
                return {"refused": f"{t.name}: both rows hold an entry ({both}) — nothing deleted"}
    finished = keeper.status == MatchStatus.FINISHED
    for f in (FIELDS if take_state else ()):
        v = getattr(newer, f)
        if v is None:
            continue
        if f == "status" and finished and v != MatchStatus.FINISHED:
            continue
        setattr(keeper, f, v)
    ext, new_ext = dict(keeper.external_ids or {}), dict(newer.external_ids or {})
    if take_state:
        stamp_rekey(ext, source, ext.get(source), new_ext.get(source), via)
        ext[source] = new_ext.get(source)
    else:                                   # keeper keeps its id; the stale id is history
        prev = list(ext.get(f"{source}_prev") or [])
        if new_ext.get(source) and new_ext.get(source) not in prev:
            prev.append(new_ext.get(source))
        ext[f"{source}_prev"] = prev
    for k, v in new_ext.items():
        ext.setdefault(k, v)
    moved = {}
    for t, c, _ in tables:
        n = s.execute(update(t).where(c == newer.id).values({c.name: keeper.id})).rowcount
        if n:
            moved[t.name] = n
    keeper.external_ids = ext
    s.flush()
    s.delete(newer)
    s.flush()
    return moved


def run(competition_code: str, source: str = "api_american_football", apply: bool = False,
        sample: int = 8) -> dict:
    from src.db.database import session_scope

    out = {"competition": competition_code, "source": source, "applied": apply}
    with session_scope() as s:
        out["before"] = state(s, competition_code, source)
        pairs, rc = find_pairs(s, competition_code, source)
        out["pairs"] = len(pairs)
        out["report"] = dict(rc)
        out["differs"] = dict(Counter(f for k, n in pairs for f in describe(k, n, source)["differs"]))
        out["sample"] = [describe(k, n, source) for k, n in pairs[:sample]]
        moved, refused, merged = Counter(), [], 0
        if apply:
            for k, n in pairs:
                r = merge(s, k, n, source)
                if "refused" in r:
                    refused.append({"keeper": k.id, "newer": n.id, "why": r["refused"]})
                    continue
                merged += 1
                moved.update(r)
        else:
            s.rollback()
        out.update(merged=merged, refused=refused, repointed=dict(moved))
        s.flush()
        out["after"] = state(s, competition_code, source)
    return out


def state(s, competition_code: str, source: str) -> dict:
    """The competition's re-key state — what a summary must report besides this
    run's merges (ARCHITECT 2026-10-03: "merged 0" on a table 962 rows of which
    were already re-keyed in place). rekeys_by_via counts the provenance log."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus

    comp = s.execute(select(Competition).where(Competition.code == competition_code)).scalar_one_or_none()
    if comp is None:
        raise ValueError(f"competition {competition_code} not in DB")
    rows = list(s.execute(select(Match).where(Match.competition_id == comp.id)).scalars())
    via = Counter(r.get("via") for m in rows for r in ((m.external_ids or {}).get(f"{source}_rekeys") or []))
    return {"rows": len(rows),
            "carry_prev": sum(1 for m in rows if (m.external_ids or {}).get(f"{source}_prev")),
            "stale_orphans": sum(1 for m in rows if m.status == MatchStatus.STALE_ORPHAN),
            "rekeys_by_via": dict(via)}


# ---------------------------------------------------------------------------
# ORPHANS (ARCHITECT 2026-10-03): "13 window duplicates where the kickoff moved
# >12h (twin test too tight for provider time corrections: widen to same
# home+away within 48h when one row is stale-scheduled and the other has a live
# id), and 142 stale SCHEDULED rows >6h past kickoff with no result — orphans
# under retired ids ... Add `dedupe-matches --orphans` dry-run/apply: resolve
# each stale row's sid at the provider; NOT FOUND + a live twin → merge; NOT
# FOUND + no twin → mark status=stale_orphan (never delete). Receipt first.
# Georgia@Alabama must resolve to its live id before next Saturday."
#
# Candidates: SCHEDULED rows with no score and a source id that are either
# STALE (kickoff more than STALE_H past) or have a TWIN (same home AND away,
# kickoffs within TWIN_H, a different source id). Each candidate's id is
# resolved at the provider (GET /games?id=):
#   * found               -> live: untouched ("resync" when stale — the next
#                            sync-matches brings the result);
#   * lookup error        -> UNRESOLVED: untouched (never read as absent);
#   * NOT FOUND + exactly one twin whose id IS found -> MERGE (keeper = the older
#     row; when the stale row is the keeper it takes the twin's id and state,
#     else the twin keeps its own and the stale id joins its _prev);
#   * NOT FOUND, no twin  -> the provider's games on the row's date ±2 days are
#     searched for the same home AND away team: exactly one, its id held by no
#     row -> RELINK (re-key in place, provider state applied); held by a row
#     outside the twin window, two games, or only home/away swapped -> REFUSED
#     (reported); none -> STALE_ORPHAN (never deleted).
# Dry-run by default; --apply needs a verified .backup (CLI).
STALE_H = 6
TWIN_H = 48
SEARCH_DAYS = 2


def _team_sids(s, source: str, team_ids) -> dict:
    from sqlalchemy import select

    from src.db.schema import Team

    return {t.id: (t.external_ids or {}).get(source)
            for t in s.execute(select(Team).where(Team.id.in_(set(team_ids)))).scalars()}


def _check_allows_orphan(s) -> str | None:
    """SQLite DDL guard: a table created with a CHECK on the status column that
    predates STALE_ORPHAN would reject the mark — refuse it cleanly instead."""
    from sqlalchemy import text

    if s.get_bind().dialect.name != "sqlite":
        return None
    ddl = s.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='matches'")).scalar() or ""
    if "CHECK" in ddl.upper() and "SCHEDULED" in ddl and "STALE_ORPHAN" not in ddl:
        return "the matches table carries a status CHECK constraint without STALE_ORPHAN"
    return None


def orphans(competition_code: str, adapter, source: str = "api_american_football", apply: bool = False,
            now=None, pace=None) -> dict:
    """Plan (and with apply, perform) the orphan actions. Returns the receipt."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus
    from src.ingestion.service import IngestionService
    from src.timeutil import utc_now_naive

    now = now or utc_now_naive()
    pace = pace or (lambda: None)
    cache: dict = {}

    def resolve(sid):
        if sid not in cache:
            pace()
            try:
                exists, nm = adapter.get_game(str(sid), competition_code)
                cache[sid] = ("found", nm) if exists else ("absent", None)
            except Exception as e:  # noqa: BLE001 — UNRESOLVED, never absent
                cache[sid] = ("error", f"{type(e).__name__}: {str(e)[:120]}")
        return cache[sid]

    day_cache: dict = {}

    def games_on(day: str):
        if day not in day_cache:
            pace()
            try:
                day_cache[day] = adapter.list_matches(competition_code, date_from=day, date_to=day)
            except Exception as e:  # noqa: BLE001
                day_cache[day] = e
        return day_cache[day]

    out = {"competition": competition_code, "source": source, "applied": apply, "now": now.isoformat()}
    with session_scope() as s:
        out["before"] = state(s, competition_code, source)
        comp = s.execute(select(Competition).where(Competition.code == competition_code)).scalar_one()
        rows = list(s.execute(select(Match).where(Match.competition_id == comp.id)).scalars())
        sid_of = lambda m: (m.external_ids or {}).get(source)  # noqa: E731
        holder = {}
        for m in rows:
            if sid_of(m):
                holder.setdefault(str(sid_of(m)), []).append(m)
        by_pair = defaultdict(list)
        for m in rows:
            if m.status not in (MatchStatus.CANCELLED, MatchStatus.STALE_ORPHAN):
                by_pair[(m.home_team_id, m.away_team_id)].append(m)

        def unplayed(m):
            return m.status == MatchStatus.SCHEDULED and m.home_score is None and m.away_score is None

        def twins(m):
            return [x for x in by_pair[(m.home_team_id, m.away_team_id)]
                    if x.id != m.id and x.utc_date and m.utc_date and sid_of(x) and sid_of(x) != sid_of(m)
                    and abs(x.utc_date - m.utc_date) <= timedelta(hours=TWIN_H)]

        stale_cut = now - timedelta(hours=STALE_H)
        cands = sorted((m for m in rows if unplayed(m) and sid_of(m) and m.utc_date
                        and (m.utc_date < stale_cut or twins(m))), key=lambda m: m.id)
        tsid = _team_sids(s, source, [t for m in cands for t in (m.home_team_id, m.away_team_id)])
        plan, done, claimed = [], set(), set()          # claimed: live ids a relink already takes
        for m in cands:
            if m.id in done:
                continue
            st, info = resolve(sid_of(m))
            base = {"id": m.id, "sid": sid_of(m), "utc": m.utc_date.isoformat(), "home": m.home_team_id,
                    "away": m.away_team_id, "stale": m.utc_date < stale_cut}
            if st == "error":
                plan.append({**base, "action": "unresolved", "why": info})
                continue
            if st == "found":
                plan.append({**base, "action": "live_resync" if base["stale"] else "live"})
                continue
            live_twins = [x for x in twins(m) if x.id not in done and resolve(sid_of(x))[0] == "found"]
            if len(live_twins) > 1:
                plan.append({**base, "action": "refused", "why": f"{len(live_twins)} live twins "
                             f"{[x.id for x in live_twins]} (ambiguous)"})
                continue
            if live_twins:
                t = live_twins[0]
                done.update((m.id, t.id))
                plan.append({**base, "action": "merge", "twin": t.id, "twin_sid": sid_of(t),
                             "keeper": min(m.id, t.id), "_rows": (m, t)})
                continue
            hs, as_ = tsid.get(m.home_team_id), tsid.get(m.away_team_id)
            found, swapped, err = [], [], None
            for d in range(-SEARCH_DAYS, SEARCH_DAYS + 1):
                g = games_on((m.utc_date + timedelta(days=d)).strftime("%Y-%m-%d"))
                if isinstance(g, Exception):
                    err = f"{type(g).__name__}: {str(g)[:120]}"
                    continue
                for nm in g:
                    if nm.home_team_source_id == hs and nm.away_team_source_id == as_:
                        found.append(nm)
                    elif nm.home_team_source_id == as_ and nm.away_team_source_id == hs:
                        swapped.append(nm)
            found = list({nm.source_id: nm for nm in found}.values())
            if err and not found:
                plan.append({**base, "action": "unresolved", "why": f"provider search: {err}"})
            elif len(found) > 1:
                plan.append({**base, "action": "refused", "why": f"{len(found)} provider games for the pair "
                             f"within ±{SEARCH_DAYS}d {[n.source_id for n in found]}"})
            elif found:
                nm = found[0]
                held = [x.id for x in holder.get(str(nm.source_id), []) if x.id != m.id]
                if str(nm.source_id) in claimed:
                    plan.append({**base, "action": "refused", "live_sid": nm.source_id,
                                 "why": f"live id {nm.source_id} already taken by another relink in this run"})
                elif held:
                    plan.append({**base, "action": "refused", "live_sid": nm.source_id,
                                 "why": f"live id {nm.source_id} held by row(s) {held} outside the "
                                        f"{TWIN_H}h twin window — review"})
                else:
                    done.add(m.id)
                    claimed.add(str(nm.source_id))
                    plan.append({**base, "action": "relink", "live_sid": nm.source_id,
                                 "live_utc": nm.utc_date.isoformat(), "_nm": nm, "_row": m})
            elif swapped:
                plan.append({**base, "action": "refused", "why": f"provider holds the pair home/away SWAPPED "
                             f"{[n.source_id for n in swapped]}"})
            else:
                done.add(m.id)
                plan.append({**base, "action": "orphan", "_row": m})
        out["counts"] = dict(Counter(p["action"] for p in plan))
        out["provider_lookups"] = {"games_by_id": len(cache), "dates_searched": len(day_cache)}
        applied, refused = Counter(), []
        if apply:
            guard = _check_allows_orphan(s)
            for p in plan:
                if p["action"] == "merge":
                    m, t = p["_rows"]
                    keeper, newer = (m, t) if m.id < t.id else (t, m)
                    r = merge(s, keeper, newer, source, take_state=(keeper is m), via="orphan-merge")
                    if "refused" in r:
                        refused.append({"id": p["id"], "why": r["refused"]})
                    else:
                        applied["merge"] += 1
                elif p["action"] == "relink":
                    m, nm = p["_row"], p["_nm"]
                    ext = dict(m.external_ids or {})
                    stamp_rekey(ext, source, sid_of(m), str(nm.source_id), "orphan-relink")
                    ext[source] = str(nm.source_id)
                    m.external_ids = ext
                    IngestionService._apply_match_updates(m, nm)
                    applied["relink"] += 1
                elif p["action"] == "orphan":
                    if guard:
                        refused.append({"id": p["id"], "why": f"orphan mark refused: {guard}"})
                        continue
                    m = p["_row"]
                    ext = dict(m.external_ids or {})
                    ext[f"{source}_orphaned_at"] = now.isoformat(timespec="seconds")
                    m.external_ids = ext
                    m.status = MatchStatus.STALE_ORPHAN
                    applied["orphan"] += 1
            s.flush()
        else:
            s.rollback()
        out["applied_counts"] = dict(applied)
        out["refused_at_apply"] = refused
        out["plan"] = [{k: v for k, v in p.items() if not k.startswith("_")} for p in plan]
        out["after"] = state(s, competition_code, source) if apply else out["before"]
    return out
