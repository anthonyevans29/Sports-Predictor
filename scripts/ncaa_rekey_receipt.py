"""
NCAA re-key receipt (ARCHITECT 2026-10-03, after `dedupe-matches --apply`
found 0 pairs on a table that showed 962 at 07:51): READ-ONLY.

"Confirm from the DB receipt (ext ids on the 32612/47549-class pairs now)
and record it; if 1,006 orphan rows remain under the old ids, say so ...
Georgia@Alabama still "no odds yet" at 16:48Z with no 429s — provider-side?
check the game id resolves."

Prints, for one competition (default NCAA, source api_american_football):
  1. rows, rows re-keyed in place (carrying "<source>_prev"), source-id
     leading digits (old 22xxx vs new 23xxx/24xxx classes);
  2. the natural-key clusters (same home AND away, kickoffs within 12h) by
     the same rules as match_dedupe.find_pairs: mergeable pairs (different
     ids), SAME-id pairs, missing-id pairs, clusters of 3+ — so a 0 from the
     dedupe is explained, not assumed;
  3. rows with no twin by id class and status (the orphan count: an old-class
     row that is SCHEDULED with its kickoff in the past is stale);
  4. the export window (now .. +days): rows vs distinct natural keys — two
     rows per game means duplicates are still in the window;
  5. --ids: each row's ext ids, _prev, status, kickoff, odds / snapshot rows;
  6. --game "Georgia@Alabama": every row of that pairing in the window, the
     same fields; with --resolve, each row's source id is looked up at the
     provider (GET /games?id=, GET /odds?game=; never prints the key).

    python scripts/ncaa_rekey_receipt.py --ids 32612 47549 --game "Georgia@Alabama" [--resolve]
    python scripts/ncaa_rekey_receipt.py --audit-merges      # PR #270 review: provenance audit of merges

--audit-merges: every row carrying "<source>_prev" (re-keyed in place, by a sync,
a dedupe merge or an orphan merge) with any OTHER same-pair row still within 48h
of it — a competing twin the merge did not weigh. Rows whose "<source>_rekeys"
log names the provenance are labelled with it. A zero reads "no current nearby
rows found" and nothing more (#270 review 2026-10-04): it sees only the CURRENT
table, so a merge that moved the keeper's kickoff can leave a twin outside 48h
of the new kickoff that was inside 48h of the old one.

--reconstruct-merges --backup PRE.db [--plan FILE] [--expect N] (#270 review
2026-10-04): every orphan merge in the provenance log, rebuilt against the
retained PRE-APPLY backup (opened read-only): the original connected twin group
(same pair, kickoffs within 48h, different ids), the keeper's and the merged
row's pre ids / sids / kickoffs, the keeper's post kickoff (a shift is named),
every reference move (per table referencing matches: pre counts on both rows vs
post on the keeper), and any same-pair row near the PRE or the POST kickoff
outside the group. --plan cross-checks the pasted `dedupe-matches --orphans`
apply output ([merge] lines). Anything the backup or the log cannot show reads
UNKNOWN (law 4). --expect N states the reported cohort size; the receipt says
whether it accounts for all N.

Opens the DB read-only (mode=ro URI); writes nothing anywhere.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "deploy" / "hosting"))
import sp_common as c  # noqa: E402

WINDOW_H = 12
BASE = "https://v1.american-football.api-sports.io"


def _dt(v):
    if v is None:
        return None
    return datetime.fromisoformat(str(v).replace("Z", "")).replace(tzinfo=None)


def _sid_class(sid) -> str:
    s = str(sid or "")
    return f"{s[:2]}xxx" if s.isdigit() and len(s) >= 4 else ("none" if not s else "other")


def load(con, comp_code: str, source: str):
    cur = con.execute("SELECT id FROM competitions WHERE code = ?", (comp_code,))
    row = cur.fetchone()
    if row is None:
        raise SystemExit(f"competition {comp_code} not in DB")
    names = dict(con.execute("SELECT id, name FROM teams"))
    odds = Counter(dict(con.execute("SELECT match_id, COUNT(*) FROM odds GROUP BY match_id")))
    snaps = Counter(dict(con.execute("SELECT match_id, COUNT(*) FROM odds_snapshots GROUP BY match_id")))
    rows = []
    for mid, h, a, utc, st, st_raw, hs, as_, ext in con.execute(
            "SELECT id, home_team_id, away_team_id, utc_date, status, status_raw, home_score, away_score, "
            "external_ids FROM matches WHERE competition_id = ?", (row[0],)):
        e = json.loads(ext) if isinstance(ext, str) and ext else (ext or {})
        rows.append({"id": mid, "home": h, "away": a, "home_name": names.get(h), "away_name": names.get(a),
                     "utc": _dt(utc), "status": st, "status_raw": st_raw,
                     "score": None if hs is None else f"{hs}-{as_}", "sid": e.get(source),
                     "prev": e.get(f"{source}_prev") or [], "rekeys": e.get(f"{source}_rekeys") or [],
                     "odds": odds.get(mid, 0), "snaps": snaps.get(mid, 0)})
    return rows


def clusters(rows):
    """The match_dedupe.find_pairs grouping, reported in full."""
    by_pair = defaultdict(list)
    for r in rows:
        by_pair[(r["home"], r["away"])].append(r)
    win, seen, out = timedelta(hours=WINDOW_H), set(), []
    for prs in by_pair.values():
        prs.sort(key=lambda r: (r["utc"] or datetime.min, r["id"]))
        for r in prs:
            if r["id"] in seen or r["utc"] is None:
                continue
            cl = [x for x in prs if x["utc"] and abs(x["utc"] - r["utc"]) <= win]
            if len(cl) < 2:
                continue
            seen.update(x["id"] for x in cl)
            ids = [x["sid"] for x in cl]
            kind = ("cluster_3plus" if len(cl) > 2 else "missing_id" if None in ids
                    else "same_id" if len(set(ids)) < 2 else "mergeable")
            out.append((kind, sorted(cl, key=lambda x: x["id"])))
    return out, seen


def show(r) -> str:
    return (f"id {r['id']} · {r['away_name']} @ {r['home_name']} · {r['utc']} · {r['status']}/{r['status_raw']}"
            f" · score {r['score']} · sid {r['sid']} · prev {r['prev']} · odds {r['odds']} · snapshots {r['snaps']}")


def resolve(sid) -> str:
    """GET-only provider lookup for one game id (the key is never printed)."""
    import requests

    key = os.environ.get("API_AMERICAN_FOOTBALL_KEY") or os.environ.get("API_FOOTBALL_KEY") \
        or c._dotenv().get("API_AMERICAN_FOOTBALL_KEY") or c._dotenv().get("API_FOOTBALL_KEY")
    if not key:
        return "provider: no API key in env/.env — not looked up"
    h = {"x-apisports-key": key}
    out = []
    for path, params in (("games", {"id": sid}), ("odds", {"game": sid})):
        try:
            r = requests.get(f"{BASE}/{path}", headers=h, params=params, timeout=20)
            body = r.json()
        except Exception as e:  # noqa: BLE001 — a receipt, never a crash
            out.append(f"/{path}: {type(e).__name__}")
            continue
        resp, err = body.get("response") or [], body.get("errors")
        if path == "games":
            g = resp[0] if resp else None
            out.append(f"/games?id={sid}: HTTP {r.status_code} · " + (
                f"resolves: {g['teams']['away']['name']} @ {g['teams']['home']['name']} · "
                f"{g['game']['date']['date']} {g['game']['date'].get('time')} · {g['game']['status']['short']}"
                if g else f"NOT FOUND (results {body.get('results')}, errors {err or 'none'})"))
        else:
            books = len(resp[0].get("bookmakers") or []) if resp else 0
            out.append(f"/odds?game={sid}: HTTP {r.status_code} · results {body.get('results')} · "
                       f"bookmakers {books} · errors {err or 'none'}")
    return " | ".join(redact_all(out))


def redact_all(lines):
    return [c.redact(x) for x in lines]


TWIN_H = 48                                            # match_dedupe.TWIN_H (the orphan twin window)


def open_read(p: Path):
    """Read-only open; a macOS .backup that refuses mode=ro (the 2026-10-03 hotfix) falls back to a plain
    connect that this script only ever SELECTs on. Returns (con, form)."""
    try:
        con = c.ro_connect(p)
        con.execute("SELECT 1 FROM matches LIMIT 1")
        return con, "mode=ro URI"
    except sqlite3.OperationalError:
        con = sqlite3.connect(str(p), timeout=60)
        con.execute("SELECT 1 FROM matches LIMIT 1")
        return con, "plain connect (mode=ro refused), SELECT only"


def ref_counts(con, ids) -> dict:
    """{table: {match_id: rows}} for every table with a column referencing matches.id."""
    out = {}
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for t in tables:
        for fk in con.execute(f'PRAGMA foreign_key_list("{t}")'):
            if fk[2] == "matches" and fk[4] == "id":
                col = fk[3]
                q = f'SELECT "{col}", COUNT(*) FROM "{t}" WHERE "{col}" IN ({",".join("?" * len(ids))}) GROUP BY "{col}"'
                out[f"{t}.{col}"] = dict(con.execute(q, list(ids))) if ids else {}
    return out


def twin_group(rows_of_pair, start) -> list:
    """The connected component of `start` in the twin graph (kickoffs within TWIN_H, different ids)."""
    seen, todo = {start["id"]}, [start]
    while todo:
        r = todo.pop()
        for x in rows_of_pair:
            if x["id"] in seen or not (x["utc"] and r["utc"] and x["sid"] and r["sid"]):
                continue
            if x["sid"] != r["sid"] and abs(x["utc"] - r["utc"]) <= timedelta(hours=TWIN_H):
                seen.add(x["id"])
                todo.append(x)
    return sorted((x for x in rows_of_pair if x["id"] in seen), key=lambda x: x["id"])


def parse_plan(path) -> dict:
    """{keeper id: (merged row id, twin sid)} from pasted `[merge] id X sid Y ... {'twin': T, ...}` lines."""
    import ast
    import re
    out = {}
    for ln in Path(path).read_text(errors="replace").splitlines():
        m = re.search(r"\[merge\] id (\d+) sid (\S+) .*?(\{.*\})\s*$", ln)
        if not m:
            continue
        try:
            kw = ast.literal_eval(m.group(3))
        except (ValueError, SyntaxError):
            continue
        rid, twin = int(m.group(1)), kw.get("twin")
        keeper = kw.get("keeper", min(rid, twin) if twin else rid)
        other = twin if keeper == rid else rid
        out[keeper] = (other, m.group(2))
    return out


def reconstruct(cur_path: Path, pre_path: Path, comp: str, source: str, plan_path, expect) -> int:
    pre_con, form = open_read(pre_path)
    cur_con, _ = open_read(cur_path)
    pre, cur = load(pre_con, comp, source), load(cur_con, comp, source)
    pre_by, cur_by = {r["id"]: r for r in pre}, {r["id"]: r for r in cur}
    pre_pair = defaultdict(list)
    for r in pre:
        if r["status"] not in ("CANCELLED", "STALE_ORPHAN"):
            pre_pair[(r["home"], r["away"])].append(r)
    cur_pair = defaultdict(list)
    for r in cur:
        cur_pair[(r["home"], r["away"])].append(r)
    merges = [(r, e) for r in cur for e in (r["rekeys"] or []) if e.get("via") == "orphan-merge"]
    plan = parse_plan(plan_path) if plan_path else None
    print(f"8. MERGE COHORT RECONSTRUCTION · pre-apply backup {pre_path.name} ({form}) · "
          f"orphan merges in the provenance log: {len(merges)}"
          + (f" · reported {expect}" if expect is not None else ""))
    unlogged = [r for r in cur if r["prev"] and not r["rekeys"]]
    if unlogged:
        print(f"   re-keyed rows with NO provenance log (pre-log; merge provenance UNKNOWN): {len(unlogged)}")
    flags = Counter()
    keeper_ids = []
    for k, e in merges:
        kp = pre_by.get(k["id"])
        keeper_ids.append(k["id"])
        print(f"   merge → keeper id {k['id']} · {k['away_name']} @ {k['home_name']} · log {e.get('from')} → "
              f"{e.get('to')} at {e.get('at') or 'UNKNOWN'}")
        if kp is None:
            print("      keeper NOT in the pre-apply backup — pre state UNKNOWN")
            flags["keeper absent from backup"] += 1
            continue
        sids = {str(e.get("from")), str(e.get("to"))}
        gone = [x for x in pre_pair[(kp["home"], kp["away"])] if x["id"] not in cur_by and x["id"] != kp["id"]]
        merged = [x for x in gone if str(x["sid"]) in sids] or None
        group = twin_group(pre_pair[(kp["home"], kp["away"])], kp)
        print(f"      pre group ({len(group)} row(s)): "
              + "; ".join(f"id {x['id']} sid {x['sid']} {x['utc']} {x['status']}"
                          f"{'' if x['id'] in cur_by else ' (gone)'}" for x in group))
        if merged is None:
            print("      merged row: UNKNOWN (no gone same-pair row carries the logged ids)")
            flags["merged row UNKNOWN"] += 1
            mrow = None
        else:
            mrow = merged[0]
            if len(merged) > 1:
                print(f"      merged row AMBIGUOUS: {[x['id'] for x in merged]}")
                flags["merged row ambiguous"] += 1
            print(f"      merged row id {mrow['id']} sid {mrow['sid']} pre kickoff {mrow['utc']}")
        if len(group) != 2 or (mrow and mrow["id"] not in [x["id"] for x in group]):
            print("      ⚠ the pre group is not exactly {keeper, merged row}")
            flags["group not a clean pair"] += 1
        shift = (k["utc"] - kp["utc"]) if (k["utc"] and kp["utc"]) else None
        print(f"      keeper kickoff pre {kp['utc']} → post {k['utc']}"
              + (f" · SHIFTED {shift}" if shift else "" if shift is not None else " · UNKNOWN"))
        if shift:
            flags["keeper kickoff shifted"] += 1
        ids = [k["id"]] + ([mrow["id"]] if mrow else [])
        pre_refs, post_refs = ref_counts(pre_con, ids), ref_counts(cur_con, ids)
        moves = []
        for t in sorted(set(pre_refs) | set(post_refs)):
            pk, pm = pre_refs.get(t, {}).get(k["id"], 0), (pre_refs.get(t, {}).get(mrow["id"], 0) if mrow else None)
            qk, qm = post_refs.get(t, {}).get(k["id"], 0), (post_refs.get(t, {}).get(mrow["id"], 0) if mrow else None)
            if pk or pm or qk or qm:
                ok = mrow is not None and qm == 0 and qk == pk + pm
                moves.append(f"{t}: keeper {pk}→{qk}, merged {pm if pm is not None else 'UNKNOWN'}→"
                             f"{qm if qm is not None else 'UNKNOWN'}{'' if ok else ' ⚠'}")
                if not ok:
                    flags["reference move not accounted"] += 1
        print("      references: " + ("; ".join(moves) or "none on either row"))
        near = {}
        for when, label in ((kp["utc"], "pre"), (k["utc"], "post")):
            if not when:
                continue
            for src, rows_ in (("backup", pre_pair[(kp["home"], kp["away"])]), ("now", cur_pair[(kp["home"], kp["away"])])):
                for x in rows_:
                    if x["id"] in ids or not x["utc"] or abs(x["utc"] - when) > timedelta(hours=TWIN_H):
                        continue
                    near.setdefault((x["id"], src), (x, set()))[1].add(label)
        for (xid, src), (x, labels) in sorted(near.items()):
            print(f"      ⚠ same-pair row near the {'/'.join(sorted(labels))} kickoff ({src}): id {xid} sid {x['sid']} "
                  f"{x['utc']} {x['status']}")
            flags["same-pair row near pre/post kickoff"] += 1
    if plan is not None:
        missing = sorted(set(plan) - set(keeper_ids))
        extra = sorted(set(keeper_ids) - set(plan))
        print(f"   plan cross-check ({len(plan)} [merge] line(s) parsed): in the plan but not in the log {missing or 'none'}"
              f" · in the log but not in the pasted plan {extra or 'none'}"
              + (" (the console prints --sample merge lines; '… N more' are not in the paste)" if extra else ""))
        if missing:
            flags["plan merge not in the log"] += len(missing)
    accounted = len(merges) if expect is None else f"{len(merges)}/{expect}"
    verdict = "ACCOUNTED" if (expect is None or len(merges) == expect) and not flags else "REVIEW"
    print(f"   RECONSTRUCTION: merges {accounted} · flags {dict(flags) or 'none'} · {verdict}")
    pre_con.close()
    cur_con.close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--competition", default="NCAA")
    ap.add_argument("--source", default="api_american_football")
    ap.add_argument("--ids", nargs="*", type=int, default=[])
    ap.add_argument("--game", default=None, help='"Away@Home" (substring match on team names)')
    ap.add_argument("--days", type=int, default=7, help="export window length from now (UTC)")
    ap.add_argument("--resolve", action="store_true", help="look --game rows' ids up at the provider (GET)")
    ap.add_argument("--audit-merges", action="store_true", help="re-keyed rows with a same-pair row within 48h")
    ap.add_argument("--reconstruct-merges", action="store_true",
                    help="rebuild every orphan merge against the pre-apply --backup (read-only)")
    ap.add_argument("--backup", default=None, help="the retained PRE-APPLY .backup file (read-only)")
    ap.add_argument("--plan", default=None, help="the pasted dedupe-matches --orphans --apply output (optional)")
    ap.add_argument("--expect", type=int, default=None, help="the reported merge count (e.g. 30)")
    ap.add_argument("--db", default=None, help=argparse.SUPPRESS)        # tests
    ap.add_argument("--now", default=None, help=argparse.SUPPRESS)       # tests
    a = ap.parse_args(argv)
    p = Path(a.db) if a.db else c.db_path()
    now = _dt(a.now) if a.now else datetime.now(timezone.utc).replace(tzinfo=None)
    con = c.ro_connect(p)
    rows = load(con, a.competition, a.source)
    con.close()
    print(f"NCAA RE-KEY RECEIPT · {a.competition} ({a.source}) · db {p} (read-only) · now {now:%Y-%m-%dT%H:%MZ}")
    rek = [r for r in rows if r["prev"]]
    print(f"1. rows {len(rows)} · re-keyed in place (carry {a.source}_prev) {len(rek)} · source-id classes "
          f"{dict(sorted(Counter(_sid_class(r['sid']) for r in rows).items()))}")
    cl, in_cluster = clusters(rows)
    kinds = Counter(k for k, _ in cl)
    print(f"2. natural-key clusters (same home+away, kickoffs ≤{WINDOW_H}h): {sum(kinds.values())} · "
          f"mergeable (different ids) {kinds['mergeable']} · SAME id {kinds['same_id']} · "
          f"missing id {kinds['missing_id']} · 3+ rows {kinds['cluster_3plus']}")
    print(f"   id-class pattern per cluster: "
          f"{dict(Counter((k, tuple(_sid_class(x['sid']) for x in xs)) for k, xs in cl).most_common(8))}")
    for k in ("mergeable", "same_id", "missing_id", "cluster_3plus"):
        for _, xs in [z for z in cl if z[0] == k][:2]:
            print(f"   e.g. [{k}]")
            for x in xs:
                print(f"      {show(x)}")
    lone = [r for r in rows if r["id"] not in in_cluster]
    stale = [r for r in lone if r["status"] == "SCHEDULED" and r["utc"] and r["utc"] < now - timedelta(hours=6)]
    print(f"3. rows with no twin: {len(lone)} by id class/status "
          f"{dict(Counter((_sid_class(r['sid']), r['status']) for r in lone).most_common(10))}")
    print(f"   of which SCHEDULED with kickoff >6h past (stale; orphan candidates): {len(stale)} "
          f"by id class {dict(Counter(_sid_class(r['sid']) for r in stale))}")
    win = [r for r in rows if r["utc"] and now <= r["utc"] <= now + timedelta(days=a.days)]
    keys = {(r["home"], r["away"], r["utc"].date()) for r in win}
    print(f"4. export window {now:%Y-%m-%d} .. +{a.days}d: rows {len(win)} · distinct games (home, away, date) "
          f"{len(keys)} · rows with odds {sum(1 for r in win if r['odds'])} · "
          f"{'DUPLICATES IN WINDOW' if len(win) > len(keys) else 'one row per game'}")
    if a.ids:
        print("5. rows by id:")
        by_id = {r["id"]: r for r in rows}
        for i in a.ids:
            print(f"   {show(by_id[i]) if i in by_id else f'id {i}: not in {a.competition}'}")
    if a.audit_merges:
        rk = [r for r in rows if r["prev"]]
        by_pair = {}
        for r in rows:
            by_pair.setdefault((r["home"], r["away"]), []).append(r)
        hits = []
        for r in rk:
            near = [x for x in by_pair[(r["home"], r["away"])] if x["id"] != r["id"] and x["utc"] and r["utc"]
                    and abs(x["utc"] - r["utc"]) <= timedelta(hours=48)]
            if near:
                hits.append((r, near))
        via = Counter(v.get("via") for r in rk for v in (r.get("rekeys") or []))
        print(f"7. merge provenance audit: {len(rk)} re-keyed row(s) · provenance log {dict(via) or '{} (pre-log)'} · "
              f"with another same-pair row within 48h: {len(hits)} "
              f"({'no current nearby rows found' if not hits else 'REVIEW these'})")
        if not hits:
            print("   (current table only: it cannot see a pre-merge kickoff — --reconstruct-merges --backup "
                  "checks the cohort against the pre-apply backup)")
        for r, near in hits:
            print(f"   {show(r)}")
            for x in near:
                print(f"      near: {show(x)}")
    if a.reconstruct_merges:
        if not a.backup:
            print("8. --reconstruct-merges needs --backup PRE.db (the retained pre-apply backup) — REFUSED")
            return 2
        return reconstruct(p, Path(a.backup), a.competition, a.source, a.plan, a.expect)
    if a.game:
        away, _, home = a.game.partition("@")
        hits = [r for r in rows if r["utc"] and abs(r["utc"] - now) <= timedelta(days=a.days)
                and away.strip().lower() in (r["away_name"] or "").lower()
                and home.strip().lower() in (r["home_name"] or "").lower()]
        print(f"6. {a.game}: {len(hits)} row(s) within ±{a.days}d")
        for r in hits:
            print(f"   {show(r)}")
            if a.resolve and r["sid"]:
                print(f"      {resolve(r['sid'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
