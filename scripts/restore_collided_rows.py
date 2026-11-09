"""
THE RESTORE of the two provider-id collisions (ARCHITECT 2026-11-09, addendum 310 item 4; #902). Verbatim:

"a small read-then-write script Code ships in the fix PR (`scripts/restore_collided_rows.py --from <10-09 copy> --ids
36454,36753 --dry-run|--apply`): it reads the two rows' full content from the 10-09 copy (opened mode=ro +
immutable=1), refuses unless the live rows read exactly the 2026 state of item 1 (Utah v Cincinnati 2026-10-31 /
Alabama v LSU 2026-11-07, provider ids 18216/18240), then in ONE transaction: creates two NEW 2026 rows with the
LISTING's orientation (Cincinnati home / Utah away, 25-49; LSU home / Alabama away, 13-31; provider ids 18216/18240,
season 2026, status FINISHED, full_time_result by the new orientation), moves every odds_snapshots / odds / match_stats
row of 36454 and 36753 to the new ids, and rewrites 36454 and 36753 to their 10-09 content (season 2025, the 2025
kickoff, 45-14 and 20-9, provider ids kept, `provider_orientation` removed); prints before and after, every id.
`--dry-run` prints the plan and writes nothing; `--apply` is my block's word."

    python scripts/restore_collided_rows.py --db data/sports_predictor.db --from <10-09 .backup> \\
        --ids 36454,36753 --dry-run           # prints the plan; opens --db read-only (mode=ro); writes nothing
    python scripts/restore_collided_rows.py --db ... --from ... --ids 36454,36753 --apply   # the architect's block

Exactly one of --dry-run / --apply (else exit 2, nothing written). Exit 0 = planned (dry run) or applied; exit 2 =
refused, nothing written. The live DB is opened read-write only on --apply (one transaction, BEGIN IMMEDIATE, every
check read again inside it); --from always mode=ro&immutable=1 (a copy nobody writes).

THE PINNED STATES (item 1, the operator's read of the 10-09 and 11-09 copies): EXPECTED below, per row id. The live
row must read the 2026 game (season, kickoff, provider id, the team names through the teams table, status FINISHED and
the 2026 score by team, written into the stored orientation by the chain of #884); the --from row must read the 2025
row (the SAME row id, the SAME provider id, season, kickoff, FINISHED and the 2025 score). Everything WRITTEN is read
from the two copies: the new row is the live row with home/away (and every score pair) swapped into the listing's
orientation; the old row is the --from row, column for column.

WHAT MOVES, WHAT STAYS, WHAT REFUSES (law 4; enumerated from the live file's declared foreign keys to matches.id and
src/db/schema.py's, every table printed):
  * odds_snapshots / odds / match_stats (item 4): every row on the old id moves to the new id. A row the 10-09 copy
    already held on that id was the 2025 game's: REFUSED (the ruling moves "every" row and does not say where a 2025
    row goes). match_stats is by team_id: moved as is.
  * odds and odds_snapshots store their sides as HOME / AWAY (src/db/schema.py: `selection` "HOME","AWAY",...), not by
    team. A Kalshi snapshot (source "kalshi") was placed by the matcher on the STORED home team's name
    (src/ingestion/kalshi_match.py: side = "HOME" if yes == home_name; kalshi_history the same), so on the new row,
    whose home is the stored away team, its HOME and AWAY swap. A book row (any other source) with a HOME / AWAY side
    was written in the provider's orientation before #885 (addendum 295 item 5) and in the stored orientation after,
    and the row does not record which: REFUSED, never guessed. A side that names no team (DRAW, OVER, UNDER) moves
    as is.
  * every other table referencing the old id: rows identical in the 10-09 copy are the 2025 game's and stay with the
    restored row; a row added or changed since (or one the copy has and the live file lost) is REFUSED, named: the
    ruling does not say where it goes.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

SOURCE = "api_american_football"
ORIENTATION_KEY = "provider_orientation"          # src.ingestion.score_orientation.PROVIDER_ORIENTATION_KEY
COMPETITION = "NCAA"
MOVE_TABLES = ("odds_snapshots", "odds", "match_stats")          # item 4, verbatim
SIDED = ("HOME", "AWAY")
SWAP = {"HOME": "AWAY", "AWAY": "HOME"}
KALSHI = "kalshi"
SCORE_PAIRS = (("home_score", "away_score"), ("home_score_ht", "away_score_ht"), ("home_score_90", "away_score_90"))

# Item 1, the facts (stored orientation: the row's home team first). `live`: the 2026 game as the row reads today (its
# score by team, the chain's write); `from`: the row on 2026-10-09; `new`: the listing's orientation of the 2026 game.
EXPECTED = {
    36454: {"provider_id": "18216", "home": "Utah", "away": "Cincinnati",
            "live": {"season": "2026", "kickoff": datetime(2026, 10, 31, 19, 45), "score": (49, 25)},
            "from": {"season": "2025", "kickoff": datetime(2025, 11, 2, 2, 15), "score": (45, 14)},
            "new": {"home": "Cincinnati", "away": "Utah", "score": (25, 49)}},
    36753: {"provider_id": "18240", "home": "Alabama", "away": "LSU",
            "live": {"season": "2026", "kickoff": datetime(2026, 11, 7, 20, 30), "score": (31, 13)},
            "from": {"season": "2025", "kickoff": datetime(2025, 11, 9, 0, 30), "score": (20, 9)},
            "new": {"home": "LSU", "away": "Alabama", "score": (13, 31)}},
}


class Refused(Exception):
    """A check failed: exit 2, nothing written."""


def _uri(p: Path, query: str) -> str:
    return Path(p).resolve().as_uri() + "?" + query


def open_from(p: Path) -> sqlite3.Connection:
    if not Path(p).is_file():
        raise Refused(f"--from {p}: no such file")
    con = sqlite3.connect(_uri(p, "mode=ro&immutable=1"), uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    return con


def open_live(p: Path, apply: bool) -> sqlite3.Connection:
    if not Path(p).is_file():
        raise Refused(f"--db {p}: no such file")
    if apply:
        con = sqlite3.connect(str(Path(p).resolve()), timeout=60, isolation_level=None)
        con.execute("PRAGMA foreign_keys = ON")
    else:
        con = sqlite3.connect(_uri(p, "mode=ro"), uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    return con


def _dt(v) -> datetime | None:
    if v is None:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        return None


def _ext(v) -> dict:
    if v is None:
        return {}
    try:
        out = json.loads(v) if isinstance(v, (str, bytes)) else dict(v)
    except ValueError:
        return {}
    return out if isinstance(out, dict) else {}


def _columns(con, table) -> list[str]:
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def match_refs(con) -> list[tuple[str, str]]:
    """[(table, column)] for every column referencing matches.id: the live file's declared foreign keys (law 1) and
    src/db/schema.py's (a migration-built table may not declare one), for the tables the file holds."""
    out = set()
    have = _tables(con)
    for t in sorted(have):
        for fk in con.execute(f'PRAGMA foreign_key_list("{t}")'):
            if fk[2] == "matches" and (fk[4] in (None, "id")):
                out.add((t, fk[3]))
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from src.db.schema import Base
        for t in Base.metadata.sorted_tables:
            if t.name not in have:
                continue
            for c in t.columns:
                if any(fk.target_fullname == "matches.id" for fk in c.foreign_keys):
                    out.add((t.name, c.name))
    except Exception as e:  # noqa: BLE001 — the file's own FKs stand; the miss is printed (law 2)
        print(f"  (schema.py not read: {type(e).__name__}: {e}; the file's declared foreign keys only)")
    return sorted(out)


def _team(con, tid) -> str | None:
    r = con.execute("SELECT name FROM teams WHERE id = ?", (tid,)).fetchone()
    return None if r is None else r[0]


def _row(con, mid) -> dict | None:
    r = con.execute("SELECT * FROM matches WHERE id = ?", (mid,)).fetchone()
    return None if r is None else dict(r)


def _comp_code(con, cid) -> str | None:
    r = con.execute("SELECT code FROM competitions WHERE id = ?", (cid,)).fetchone()
    return None if r is None else r[0]


def describe(con, m: dict) -> str:
    return (f"season {m.get('season')} · {m.get('utc_date')} · {m.get('status')} · "
            f"{_team(con, m.get('home_team_id'))} {m.get('home_score')} v {_team(con, m.get('away_team_id'))} "
            f"{m.get('away_score')} · ftr {m.get('full_time_result')} · {SOURCE} {_ext(m.get('external_ids')).get(SOURCE)}"
            f" · external_ids {m.get('external_ids')}")


def check_state(con, m: dict | None, mid: int, exp: dict, which: str) -> list[str]:
    """The refusals for one row against its pinned state (`which` "live" or "from"); [] = it reads exactly that."""
    if m is None:
        return [f"{which} row {mid} does not exist"]
    want = exp[which]
    bad = []
    if _comp_code(con, m.get("competition_id")) != COMPETITION:
        bad.append(f"competition {_comp_code(con, m.get('competition_id'))!r}, not {COMPETITION}")
    if str(m.get("season")) != want["season"]:
        bad.append(f"season {m.get('season')!r}, not {want['season']!r}")
    if _dt(m.get("utc_date")) != want["kickoff"]:
        bad.append(f"kickoff {m.get('utc_date')!r}, not {want['kickoff']:%Y-%m-%d %H:%M}Z")
    if str(_ext(m.get("external_ids")).get(SOURCE)) != exp["provider_id"]:
        bad.append(f"{SOURCE} {_ext(m.get('external_ids')).get(SOURCE)!r}, not {exp['provider_id']}")
    names = (_team(con, m.get("home_team_id")), _team(con, m.get("away_team_id")))
    if names != (exp["home"], exp["away"]):
        bad.append(f"teams {names[0]!r} v {names[1]!r}, not {exp['home']} v {exp['away']}")
    if m.get("status") != "FINISHED":
        bad.append(f"status {m.get('status')!r}, not FINISHED")
    if (m.get("home_score"), m.get("away_score")) != want["score"]:
        bad.append(f"score {m.get('home_score')}-{m.get('away_score')}, not {want['score'][0]}-{want['score'][1]}")
    return [f"{which} row {mid}: {b}" for b in bad]


def _ftr(h, a) -> str | None:
    if h is None or a is None:
        return None
    return "HOME" if h > a else "AWAY" if a > h else "DRAW"


def new_row(live: dict) -> dict:
    """The live row in the LISTING's orientation: home/away and every score pair swapped, full_time_result by the new
    orientation, status FINISHED, provider_orientation removed; every other column as the live row (id assigned)."""
    out = {k: v for k, v in live.items() if k != "id"}
    out["home_team_id"], out["away_team_id"] = live["away_team_id"], live["home_team_id"]
    for h, a in SCORE_PAIRS:
        if h in live and a in live:
            out[h], out[a] = live[a], live[h]
    out["full_time_result"] = _ftr(out.get("home_score"), out.get("away_score"))
    out["status"] = "FINISHED"
    ext = _ext(live.get("external_ids"))
    ext.pop(ORIENTATION_KEY, None)
    out["external_ids"] = json.dumps(ext)
    return out


def restored_row(frm: dict, live_cols: list[str]) -> dict:
    """The --from row, column for column (the live file's columns; a column the copy lacks is refused upstream unless
    the live value is NULL), external_ids with provider_orientation removed (the copy's text kept when it has none)."""
    out = {k: frm[k] for k in live_cols if k in frm and k != "id"}
    ext = _ext(frm.get("external_ids"))
    if ORIENTATION_KEY in ext:
        ext.pop(ORIENTATION_KEY)
        out["external_ids"] = json.dumps(ext)
    return out


def _rows_on(con, table, col, mid) -> list[dict]:
    return [dict(r) for r in con.execute(f'SELECT * FROM "{table}" WHERE "{col}" = ?', (mid,))]


def _content(r: dict, col: str, cols: list[str]) -> tuple:
    return tuple((k, r.get(k)) for k in cols if k != col)


def plan_refs(live, frm, refs, mid) -> tuple[list, list, list]:
    """(moves, stays, refusals) for every table referencing `mid`. moves: (table, col, rowid, {col: new values}) with
    the selection swap where one applies; stays: (table, n); refusals: lines."""
    moves, stays, bad = [], [], []
    from_tables = _tables(frm)
    for t, col in refs:
        cols = _columns(live, t)
        lrows = [dict(r) for r in live.execute(f'SELECT rowid AS "__rowid__", * FROM "{t}" WHERE "{col}" = ?', (mid,))]
        frows = _rows_on(frm, t, col, mid) if t in from_tables and col in _columns(frm, t) else []
        fcols = [c for c in cols if t in from_tables and c in _columns(frm, t)]
        fset = [_content(r, col, fcols) for r in frows]
        if t in MOVE_TABLES:
            if frows:
                bad.append(f"{t}: the 10-09 copy holds {len(frows)} row(s) on {mid} (the 2025 game's); item 4 moves "
                           f"every row to the new id and does not say where a 2025 row goes — not guessed")
                continue
            for r in lrows:
                upd = {col: "<new>"}
                sel, src = r.get("selection"), r.get("source")
                if t in ("odds", "odds_snapshots") and sel in SIDED:
                    if t == "odds_snapshots" and src == KALSHI:
                        upd["selection"] = SWAP[sel]
                    else:
                        bad.append(f"{t} row {r['__rowid__']} (source {src!r}, market {r.get('market')!r}, "
                                   f"selection {sel!r}, captured_at {r.get('captured_at')}): a book side stored as "
                                   f"HOME/AWAY in an orientation the row does not record (before #885 the provider's, "
                                   f"after it the stored) — not guessed")
                        continue
                moves.append((t, col, r["__rowid__"], upd, r))
        else:
            live_c = [_content(r, col, fcols) for r in lrows]
            changed = [r for r, c in zip(lrows, live_c) if c not in fset]
            lost = [r for r, c in zip(frows, fset) if c not in live_c]
            if changed or lost:
                bad.append(f"{t}: {len(changed)} row(s) on {mid} added or changed since the 10-09 copy, {len(lost)} "
                           f"row(s) of the copy gone; the ruling does not say where they go — not guessed")
            elif lrows:
                stays.append((t, len(lrows)))
    return moves, stays, bad


def run(db: Path, frm_path: Path, ids: list[int], apply: bool, out=print, _fail_at: str | None = None) -> int:
    out(f"restore_collided_rows (ARCHITECT 2026-11-09, addendum 310 item 4; #902): {'APPLY' if apply else 'DRY RUN'}"
        f" · --db {db} ({'read-write, ONE transaction' if apply else 'read-only, mode=ro'}) · --from {frm_path} "
        f"(mode=ro&immutable=1) · ids {', '.join(str(i) for i in ids)}")
    if Path(db).resolve() == Path(frm_path).resolve():
        raise Refused("--db and --from are the same file")
    unknown = [i for i in ids if i not in EXPECTED]
    if unknown:
        raise Refused(f"ids {unknown} have no pinned state in item 1 (EXPECTED: {sorted(EXPECTED)})")
    frm = open_from(frm_path)
    live = open_live(db, apply)
    try:
        if apply:
            live.execute("BEGIN IMMEDIATE")
        try:
            rc = _run(live, frm, ids, apply, out, _fail_at)
        except BaseException:
            if apply and live.in_transaction:
                live.execute("ROLLBACK")
                out("ROLLED BACK: nothing written")
            raise
        if apply:
            live.execute("COMMIT")
            out("COMMITTED")
        return rc
    finally:
        live.close()
        frm.close()


def _run(live, frm, ids, apply, out, _fail_at) -> int:
    refs = match_refs(live)
    out(f"tables referencing matches.id (the live file's foreign keys and src/db/schema.py's): "
        f"{', '.join(f'{t}.{c}' for t, c in refs) or 'none'}")
    live_cols = _columns(live, "matches")
    from_cols = set(_columns(frm, "matches"))
    bad, rows = [], {}
    for mid in ids:
        exp = EXPECTED[mid]
        lm, fm = _row(live, mid), _row(frm, mid)
        out(f"BEFORE {mid} live: {describe(live, lm) if lm else 'absent'}")
        out(f"BEFORE {mid} from: {describe(frm, fm) if fm else 'absent'}")
        bad += check_state(live, lm, mid, exp, "live") + check_state(frm, fm, mid, exp, "from")
        if lm and fm:
            for k in ("home_team_id", "away_team_id"):
                if _team(live, fm[k]) != _team(frm, fm[k]):
                    bad.append(f"from row {mid}: {k} {fm[k]} reads {_team(frm, fm[k])!r} in the copy and "
                               f"{_team(live, fm[k])!r} in the live file")
            for k in live_cols:
                if k not in from_cols and lm.get(k) is not None:
                    bad.append(f"from row {mid}: column {k} is not in the 10-09 copy and the live row holds "
                               f"{lm.get(k)!r}")
        rows[mid] = (lm, fm)
    moves, stays = {}, {}
    for mid in ids:
        mv, st, rf = plan_refs(live, frm, refs, mid)
        moves[mid], stays[mid] = mv, st
        bad += [f"row {mid}: {x}" for x in rf]
    if bad:
        for b in bad:
            out(f"REFUSED: {b}")
        raise Refused(f"{len(bad)} check(s) failed; nothing written")
    created = {}
    for mid in ids:
        lm, fm = rows[mid]
        exp = EXPECTED[mid]
        nr = new_row(lm)
        if (nr["home_score"], nr["away_score"]) != exp["new"]["score"] or \
                (_team(live, nr["home_team_id"]), _team(live, nr["away_team_id"])) != (exp["new"]["home"],
                                                                                       exp["new"]["away"]):
            raise Refused(f"row {mid}: the new row would read {_team(live, nr['home_team_id'])} "
                          f"{nr['home_score']} v {_team(live, nr['away_team_id'])} {nr['away_score']}, not item 4's "
                          f"{exp['new']['home']} {exp['new']['score'][0]} v {exp['new']['away']} "
                          f"{exp['new']['score'][1]}")
        out(f"PLAN {mid} -> NEW 2026 row (the listing's orientation): {describe(live, nr)}")
        rr = restored_row(fm, live_cols)
        out(f"PLAN {mid} -> its 10-09 content: {describe(frm, rr)}")
        by_table: dict = {}
        for t, col, rowid, upd, r in moves[mid]:
            k = by_table.setdefault(t, {"rows": 0, "swapped": 0})
            k["rows"] += 1
            k["swapped"] += "selection" in upd
        for t in MOVE_TABLES:
            k = by_table.get(t, {"rows": 0, "swapped": 0})
            out(f"PLAN {mid} MOVE {t}: {k['rows']} row(s) to the new id"
                + (f" ({k['swapped']} Kalshi HOME/AWAY swapped to the new orientation)" if t == "odds_snapshots" else ""))
        for t, n in stays[mid]:
            out(f"PLAN {mid} STAY {t}: {n} row(s), identical in the 10-09 copy (the 2025 game's), kept on {mid}")
        if not apply:
            continue
        cols = list(nr)
        cur = live.execute(f'INSERT INTO matches ({", ".join(chr(34) + c + chr(34) for c in cols)}) '
                           f'VALUES ({", ".join("?" * len(cols))})', [nr[c] for c in cols])
        new_id = cur.lastrowid
        created[mid] = new_id
        out(f"CREATED {new_id} for {mid}")
        if _fail_at == "after_create":
            raise RuntimeError("injected failure (test): after the create")
        for t, col, rowid, upd, _r in moves[mid]:
            sets = {**upd, col: new_id}
            live.execute(f'UPDATE "{t}" SET {", ".join(f"{chr(34)}{k}{chr(34)} = ?" for k in sets)} WHERE rowid = ?',
                         [*sets.values(), rowid])
        if _fail_at == "after_moves":
            raise RuntimeError("injected failure (test): after the moves")
        live.execute(f'UPDATE matches SET {", ".join(f"{chr(34)}{k}{chr(34)} = ?" for k in rr)} WHERE id = ?',
                     [*rr.values(), mid])
    if not apply:
        out("DRY RUN: nothing written")
        return 0
    for mid in ids:
        new_id = created[mid]
        out(f"AFTER {mid}: {describe(live, _row(live, mid))}")
        out(f"AFTER {new_id} (new, for {mid}): {describe(live, _row(live, new_id))}")
        for t in MOVE_TABLES:
            if t in _tables(live):
                col = next(c for tt, c in refs if tt == t) if any(tt == t for tt, _ in refs) else "match_id"
                n_old = live.execute(f'SELECT COUNT(*) FROM "{t}" WHERE "{col}" = ?', (mid,)).fetchone()[0]
                n_new = live.execute(f'SELECT COUNT(*) FROM "{t}" WHERE "{col}" = ?', (new_id,)).fetchone()[0]
                out(f"AFTER {t}: {n_old} row(s) on {mid} · {n_new} row(s) on {new_id}")
        lm = _row(live, mid)
        exp = EXPECTED[mid]
        if check_state(live, lm, mid, exp, "from") or check_state(live, _row(live, new_id), new_id, {
                **exp, "home": exp["new"]["home"], "away": exp["new"]["away"],
                "from": {**exp["live"], "score": exp["new"]["score"]}}, "from"):
            raise Refused(f"row {mid}: the written state does not read as planned; rolled back")
    if _fail_at == "before_commit":
        raise RuntimeError("injected failure (test): before the commit")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--db", required=True, type=Path, help="the live DB (read-write only on --apply)")
    ap.add_argument("--from", dest="frm", required=True, type=Path,
                    help="the 2026-10-09 .backup copy (opened mode=ro&immutable=1)")
    ap.add_argument("--ids", required=True, help="the row ids, comma-separated (item 4: 36454,36753)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="print the plan; write nothing")
    mode.add_argument("--apply", action="store_true", help="write it, in ONE transaction (the architect's block)")
    a = ap.parse_args(argv)
    try:
        ids = [int(x) for x in a.ids.split(",") if x.strip()]
    except ValueError:
        print(f"REFUSED: --ids {a.ids!r} is not a list of row ids; nothing written")
        return 2
    if not ids or len(set(ids)) != len(ids):
        print(f"REFUSED: --ids {a.ids!r} names no id, or one twice; nothing written")
        return 2
    try:
        return run(a.db, a.frm, ids, a.apply)
    except Refused as e:
        print(f"REFUSED: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
