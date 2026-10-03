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


def merge(s, keeper, newer, source: str) -> dict:
    """Merge `newer` into `keeper` (see module doc). Returns {table: re-pointed} or
    {"refused": reason}. Caller owns the transaction."""
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
    for f in FIELDS:
        v = getattr(newer, f)
        if v is None:
            continue
        if f == "status" and finished and v != MatchStatus.FINISHED:
            continue
        setattr(keeper, f, v)
    ext, new_ext = dict(keeper.external_ids or {}), dict(newer.external_ids or {})
    old = ext.get(source)
    prev = list(ext.get(f"{source}_prev") or [])
    if old and old not in prev:
        prev.append(old)
    ext[f"{source}_prev"] = prev
    ext[source] = new_ext.get(source)
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
    return out
