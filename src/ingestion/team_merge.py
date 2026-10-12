"""
ONE PROGRAM IS ONE TEAM ROW (ARCHITECT 2026-10-12, addendum 44 item 3; #426, #358), verbatim:

"One program is one team row. Where the provider holds one program under two team ids, the two rows are merged by a
reviewed command: a dry run by default, --apply only with a backup taken just before, as dedupe-matches has it. The
lower id keeps its row. Every reference to the other row is re-pointed to it, the other row's provider id is recorded
on it so that a listing carrying either id finds it, and the emptied row is deleted. Two rows are a candidate pair only
when their names are equal once unescaped and reduced to letters and digits without case, their sport is the same, no
stored game has the two playing each other, and no day holds a game of each. Anything else is listed and left.
Nothing is applied before I have read the dry run."

With it: the dry run counts the stored names that carry an HTML entity, by sport, and lists every candidate pair it
finds, not Hawai'i alone. A unique-table conflict, or a reference the command does not know, refuses the pair and says
which table.

- The references are read from the live database: every column whose foreign key names teams, and every column named
  team_id or *_team_id. The known ones are the schema's foreign keys to teams.id; any other that holds the other row's
  id refuses the pair. Team ids held inside JSON (model parameters) are not references this command can see.
- "No day holds a game of each": a stored kickoff's day read in UTC and in US Eastern; either reading sharing a day
  leaves the pair (the stricter reading: conservative unknowns).
- The other row's provider ids: a source the kept row lacks is set on it; a source it holds under another value joins
  "<source>_also" (a list), which service._find_team_by_source and the id comparisons read (source_ids()).
"""
from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
ALSO = "_also"
LIST_SUFFIXES = ("_prev", "_rekeys", ALSO)
ENTITY = re.compile(r"&(#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
_TEAM_COL = re.compile(r"^(.+_)?team_id$")


def canon(name: str | None) -> str:
    """Unescaped, reduced to letters and digits, without case: "Hawai&#x27;i" and "Hawai'i" are both "hawaii"."""
    return "".join(ch for ch in html.unescape(name or "").lower() if ch.isalnum())


def source_ids(ext: dict | None, source: str) -> set[str]:
    """Every provider id a team row answers to for `source`: its own and those recorded on it by a merge."""
    ext = ext or {}
    out = {str(ext[source])} if ext.get(source) is not None else set()
    return out | {str(x) for x in (ext.get(f"{source}{ALSO}") or [])}


def merged_ext(keep: dict | None, other: dict | None, other_id: int, at: str) -> dict:
    """The kept row's external_ids with the other row's provider ids recorded on it."""
    out = dict(keep or {})
    prior = list((other or {}).get("merged_from") or [])      # the other row's own earlier merges (Codex on #465)
    for k, v in (other or {}).items():
        if k == "merged_from":
            continue
        if k.endswith(LIST_SUFFIXES):
            cur = list(out.get(k) or [])
            out[k] = cur + [x for x in (v or []) if x not in cur]
        elif k not in out or out[k] is None:
            out[k] = v
        elif str(out[k]) != str(v):
            cur = list(out.get(f"{k}{ALSO}") or [])
            if str(v) not in {str(x) for x in cur}:
                cur.append(v)
            out[f"{k}{ALSO}"] = cur
    out["merged_from"] = list(out.get("merged_from") or []) + prior + [
        {"team_id": other_id, "external_ids": {k: v for k, v in (other or {}).items() if k != "merged_from"},
         "at": at}]
    return out


def _days(ts) -> set:
    if ts is None:
        return set()
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "").split(".")[0])
    u = ts.replace(tzinfo=UTC)
    return {("utc", u.date()), ("et", u.astimezone(ET).date())}


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def known_refs() -> set[tuple[str, str]]:
    """The schema's references to teams.id: (table, column)."""
    from src.db.schema import Base
    return {(t.name, c.name) for t in Base.metadata.sorted_tables for c in t.columns
            if any(fk.target_fullname == "teams.id" for fk in c.foreign_keys)}


def live_refs(con) -> set[tuple[str, str]]:
    """Every column of the live database that may hold a team row's id: a foreign key naming teams, or a column
    named team_id / *_team_id."""
    out = set()
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                        "AND name NOT LIKE 'sqlite_%'")]
    for t in tables:
        if t == "teams":
            continue
        for fk in con.execute(f"PRAGMA foreign_key_list({_q(t)})"):
            if str(fk[2]).lower() == "teams":
                out.add((t, fk[3]))
        for col in con.execute(f"PRAGMA table_info({_q(t)})"):
            if _TEAM_COL.match(str(col[1]).lower()):
                out.add((t, col[1]))
    return out


def unique_keys(con, table: str) -> list[list[str]]:
    """The live table's unique column sets (unique indexes, the primary key when it is not the rowid alone)."""
    out = []
    for ix in con.execute(f"PRAGMA index_list({_q(table)})"):
        if ix[2]:                                             # unique
            out.append([r[2] for r in con.execute(f"PRAGMA index_info({_q(ix[1])})")])
    pk = [r[1] for r in sorted(con.execute(f"PRAGMA table_info({_q(table)})"), key=lambda r: r[5]) if r[5]]
    if len(pk) > 1 and pk not in out:
        out.append(pk)
    return out


def entity_names(con) -> dict:
    """Stored team names that carry an HTML entity, counted by sport, with the names."""
    by = defaultdict(list)
    for tid, sport, name in con.execute("SELECT id, sport, name FROM teams"):
        if ENTITY.search(name or ""):
            by[sport].append((tid, name))
    return dict(by)


def _games(con, tid: int) -> list:
    return [(r[0], r[1], r[2], r[3]) for r in con.execute(
        "SELECT id, utc_date, home_team_id, away_team_id FROM matches WHERE home_team_id = ? OR away_team_id = ?",
        (tid, tid))]


# Addendum 50 item 5(b): "Where the other row is a member of a competition and season of which the kept row is a
# member too, it is one membership: the other row's is dropped, not re-pointed, and the dry run counts it. Every other
# unique-table conflict refuses the pair, as ruled." competition_teams holds its three key columns and nothing else.
SAME_MEMBERSHIP = ("competition_teams", "team_id")


def _clash_where(t: str, col: str, key: list[str]) -> str:
    """A row x of the other team whose key, with the team swapped, is already the kept team's (y)."""
    others = [k for k in key if k != col]
    return " AND ".join(f"y.{_q(k)} IS x.{_q(k)}" for k in others) or "1"


def check_pair(con, keep: dict, other: dict, refs: set, known: set) -> tuple[str | None, dict]:
    """(why the pair is left, or None; what the merge would move). keep has the lower id. The moves hold, per
    reference, the rows re-pointed; a same membership dropped is counted under "dropped: <table>.<column>"."""
    a, b = keep["id"], other["id"]
    ga, gb = _games(con, a), _games(con, b)
    met = [g[0] for g in ga if b in (g[2], g[3])]
    if met:
        return f"a stored game has the two playing each other (match {', '.join(map(str, met[:5]))})", {}
    da = set().union(*[_days(g[1]) for g in ga]) if ga else set()
    db = set().union(*[_days(g[1]) for g in gb]) if gb else set()
    shared = sorted({str(d) for _, d in (da & db)})
    if shared:
        return f"a day holds a game of each ({', '.join(shared[:5])})", {}
    moves = {}
    for t, col in sorted(refs):
        n = con.execute(f"SELECT COUNT(*) FROM {_q(t)} WHERE {_q(col)} = ?", (b,)).fetchone()[0]
        if not n:
            continue
        if (t, col) not in known:
            return f"a reference the command does not know: {t}.{col} holds {n} row(s) of team {b}", {}
        dropped = 0
        for key in unique_keys(con, t):
            if col not in key:
                continue
            clash = con.execute(f"SELECT COUNT(*) FROM {_q(t)} x JOIN {_q(t)} y ON {_clash_where(t, col, key)} "
                                f"WHERE x.{_q(col)} = ? AND y.{_q(col)} = ?", (b, a)).fetchone()[0]
            if clash and (t, col) == SAME_MEMBERSHIP:
                dropped = max(dropped, clash)       # one membership: the other row's is dropped (addendum 50 5(b))
            elif clash:
                return (f"a unique-table conflict: {t} ({', '.join(key)}) holds {clash} row(s) of team {b} that would "
                        f"duplicate team {a}'s"), {}
        if n - dropped:
            moves[f"{t}.{col}"] = n - dropped
        if dropped:
            moves[f"dropped: {t}.{col}"] = dropped
    return None, moves


def plan(con) -> dict:
    """The dry run: every group of rows whose names are equal once unescaped and reduced, within a sport; a pair is a
    candidate or is listed and left with why. Reads only."""
    rows = [{"id": r[0], "sport": r[1], "name": r[2], "ext": _ext(r[3])}
            for r in con.execute("SELECT id, sport, name, external_ids FROM teams ORDER BY id")]
    groups = defaultdict(list)
    for r in rows:
        k = canon(r["name"])
        if k:
            groups[(r["sport"], k)].append(r)
    refs, known = live_refs(con), known_refs()
    out = {"entity_names": entity_names(con), "candidates": [], "left": [], "unknown_refs":
           sorted(f"{t}.{c}" for t, c in refs - known), "refs": sorted(f"{t}.{c}" for t, c in refs & known)}
    for (sport, key), grp in sorted(groups.items()):
        if len(grp) < 2:
            continue
        for r in grp:
            r["games"] = len(_games(con, r["id"]))
        if len(grp) > 2:
            out["left"].append({"sport": sport, "key": key, "rows": grp,
                                "why": f"{len(grp)} rows share the name: only a pair is merged"})
            continue
        keep, other = sorted(grp, key=lambda r: r["id"])
        why, moves = check_pair(con, keep, other, refs, known)
        entry = {"sport": sport, "key": key, "keep": keep, "other": other}
        if why:
            out["left"].append({**entry, "rows": grp, "why": why})
        else:
            out["candidates"].append({**entry, "moves": moves})
    return out


def pair_text(keep_id: int, other_id: int) -> str:
    """A pair in the form the dry run prints it and --apply takes it: <kept id>:<merged id>."""
    return f"{keep_id}:{other_id}"


def parse_pair(text: str) -> tuple[int, int]:
    a, sep, b = str(text).strip().partition(":")
    if not sep or not a.strip().isdigit() or not b.strip().isdigit():
        raise ValueError(f"{text!r} is not a pair <kept id>:<merged id> as the dry run prints it")
    return int(a), int(b)


def apply(con, at: str, pairs: list[tuple[int, int]]) -> dict:
    """Addendum 50 item 5(a): "--apply takes the pairs it merges, each by its two ids as the dry run printed them,
    and merges those and no other. A named pair that is not a candidate when the apply reads the database is refused
    with its reason. --apply without a pair is refused." Per named pair: re-point, record the provider ids, delete the
    emptied row; one transaction per pair, re-checked inside it; a pair that fails its check is left, never forced."""
    if not pairs:
        raise ValueError("--apply without a pair is refused: name each pair the dry run printed (--pair KEPT:MERGED)")
    res = {"merged": [], "refused": []}
    refs, known = live_refs(con), known_refs()
    p = plan(con)
    cands = {(c["keep"]["id"], c["other"]["id"]): c for c in p["candidates"]}
    left = {}
    for x in p["left"]:
        for r in x["rows"]:
            left.setdefault(r["id"], x["why"])
    todo = []
    for a_id, b_id in pairs:
        if (a_id, b_id) in cands:
            todo.append(cands[(a_id, b_id)])
        elif (b_id, a_id) in cands:
            res["refused"].append({"keep": a_id, "other": b_id, "why": f"not as the dry run prints it: the pair is "
                                   f"{pair_text(b_id, a_id)} (the lower id keeps its row)"})
        else:
            why = left.get(a_id) if left.get(a_id) == left.get(b_id) and a_id in left else None
            res["refused"].append({"keep": a_id, "other": b_id, "why": "not a candidate pair when the apply read the "
                                   "database" + (f": {why}" if why else " (names, sport or the rows themselves differ)")})
    for c in todo:
        keep, other = c["keep"], c["other"]
        try:
            con.execute("BEGIN IMMEDIATE")
            # re-read both rows under the write lock: an ingest between the plan and the lock must not be overwritten
            # with the plan's copy (Codex on #465)
            cur = {r[0]: r for r in con.execute("SELECT id, name, external_ids FROM teams WHERE id IN (?, ?)",
                                                 (keep["id"], other["id"]))}
            if set(cur) != {keep["id"], other["id"]} or tm_key(cur[keep["id"]][1]) != tm_key(cur[other["id"]][1]):
                con.execute("ROLLBACK")
                res["refused"].append({"keep": keep["id"], "other": other["id"],
                                       "why": "a row changed or left between the plan and the lock"})
                continue
            keep = {**keep, "ext": _ext(cur[keep["id"]][2])}
            other = {**other, "ext": _ext(cur[other["id"]][2])}
            why, moves = check_pair(con, keep, other, refs, known)
            if why:
                con.execute("ROLLBACK")
                res["refused"].append({"keep": keep["id"], "other": other["id"], "why": why})
                continue
            for tc in [k for k in moves if k.startswith("dropped: ")]:       # one membership (addendum 50 5(b))
                t, col = tc[len("dropped: "):].split(".", 1)
                for key in unique_keys(con, t):
                    if col in key:
                        con.execute(f"DELETE FROM {_q(t)} AS x WHERE x.{_q(col)} = ? AND EXISTS (SELECT 1 FROM "
                                    f"{_q(t)} y WHERE y.{_q(col)} = ? AND {_clash_where(t, col, key)})",
                                    (other["id"], keep["id"]))
            for tc in [k for k in moves if not k.startswith("dropped: ")]:
                t, col = tc.split(".", 1)
                con.execute(f"UPDATE {_q(t)} SET {_q(col)} = ? WHERE {_q(col)} = ?", (keep["id"], other["id"]))
            ext = merged_ext(keep["ext"], other["ext"], other["id"], at)
            con.execute("UPDATE teams SET external_ids = ? WHERE id = ?", (json.dumps(ext), keep["id"]))
            left = {f"{t}.{col}": con.execute(f"SELECT COUNT(*) FROM {_q(t)} WHERE {_q(col)} = ?",
                                              (other["id"],)).fetchone()[0] for t, col in refs}
            if any(left.values()):
                con.execute("ROLLBACK")
                res["refused"].append({"keep": keep["id"], "other": other["id"],
                                       "why": f"rows still name team {other['id']} after re-pointing: "
                                              f"{ {k: v for k, v in left.items() if v} }"})
                continue
            con.execute("DELETE FROM teams WHERE id = ?", (other["id"],))
            con.execute("COMMIT")
            res["merged"].append({"keep": keep["id"], "other": other["id"], "moves": moves, "external_ids": ext})
        except Exception as e:  # noqa: BLE001 - the pair is left and the reason receipted
            try:
                con.execute("ROLLBACK")
            except Exception:  # noqa: BLE001
                pass
            res["refused"].append({"keep": keep["id"], "other": other["id"], "why": f"{type(e).__name__}: {e}"[:300]})
    return res


def tm_key(name) -> str:
    return canon(name)


def _ext(raw) -> dict:
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def counts(con) -> Counter:
    return Counter({"teams": con.execute("SELECT COUNT(*) FROM teams").fetchone()[0]})
