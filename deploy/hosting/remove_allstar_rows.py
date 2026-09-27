#!/usr/bin/env python3
"""HOST-ONLY, one-time: remove the Pro Bowl / all-star rows the host ingested
before #43's adapter exclusion (architect ruling 2026-09-27: targeted delete
AUTHORIZED because the host DB is a REHEARSAL database, replaced wholesale at
cutover. This is not destruction of truth. The laptop never had these rows
and is never touched.)

    python deploy/hosting/remove_allstar_rows.py            # dry-run: print what would go
    python deploy/hosting/remove_allstar_rows.py --apply    # backup, delete, print post-counts

- Targets NFL-family teams that the adapter's own exhibition rule
  (api_american_football._non_competitive: AFC/NFC sides, "pro bowl" /
  "all-star" markers) classifies as all-star. There is one definition in the
  codebase.
- Cascades through the DECLARED foreign-key graph (PRAGMA foreign_key_list):
  the teams' games, and those games' odds, snapshots, predictions ->
  outcomes, and so on. Children are deleted before parents. Every row is
  printed.
- Refuses unless the host marker (/etc/sports-predictor/host.env, or
  SP_HOST_ENV) exists, so it cannot run on the laptop.
- --apply first takes a `precleanup` .backup (integrity-checked, sha256),
  holds the DB lock, and runs in ONE transaction. It prints pre and post
  counts per NFL season and NFL team counts (expected: -1 game per season
  that had a Pro Bowl, teams 34 -> 32). Receipted (kind "cleanup").
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402

sys.path.insert(0, str(c.REPO))


def children_of(con) -> dict:
    """parent_table -> [(child_table, fk_column)] from the declared FKs (law 1)."""
    out: dict = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' "
                            "AND name NOT LIKE 'sqlite_%'"):
        for fk in con.execute(f'PRAGMA foreign_key_list("{t}")'):
            out.setdefault(fk[2], []).append((t, fk[3]))
    return out


def has_id(con, table) -> bool:
    return any(r[1] == "id" for r in con.execute(f'PRAGMA table_info("{table}")'))


def cascade(con, kids, table, ids, order, seen) -> None:
    """Post-order: children's rows are appended before the parent rows."""
    for child, col in kids.get(table, []):
        q = ",".join("?" * len(ids))
        rows = con.execute(f'SELECT rowid{", id" if has_id(con, child) else ""} FROM "{child}" '
                           f'WHERE "{col}" IN ({q})', list(ids)).fetchall()
        rowids = {r[0] for r in rows} - seen.setdefault(child, set())
        if not rowids:
            continue
        seen[child] |= rowids
        if has_id(con, child):
            cascade(con, kids, child, sorted({r[1] for r in rows if r[0] in rowids}), order, seen)
        order.append((child, sorted(rowids)))


def nfl_counts(con) -> dict:
    games = {f"{r[0]} {r[1]}": r[2] for r in con.execute(
        "SELECT c.code, m.season, COUNT(*) FROM matches m JOIN competitions c "
        "ON c.id = m.competition_id WHERE c.sport = 'NFL' GROUP BY c.code, m.season "
        "ORDER BY 1, 2")}
    teams = {r[0]: r[1] for r in con.execute(
        "SELECT c.code, COUNT(DISTINCT ct.team_id) FROM competition_teams ct JOIN competitions c "
        "ON c.id = ct.competition_id WHERE c.sport = 'NFL' GROUP BY c.code")}
    return {"games": games, "teams": teams}


def allstar_teams(con) -> list[tuple]:
    from src.adapters.api_american_football import _non_competitive
    return [(tid, name, why) for tid, name in con.execute(
        "SELECT id, name FROM teams WHERE sport = 'NFL' ORDER BY id")
        if (why := _non_competitive(team_names=(name,)))]


def plan(con) -> tuple[list, list]:
    teams = allstar_teams(con)
    if not teams:
        return teams, []
    ids = [t[0] for t in teams]
    order: list = []
    cascade(con, children_of(con), "teams", ids, order, {})
    team_rows = [r[0] for r in con.execute(
        f"SELECT rowid FROM teams WHERE id IN ({','.join('?' * len(ids))})", ids)]
    order.append(("teams", sorted(team_rows)))  # parents last
    return teams, order


def show(con, order) -> None:
    for table, rowids in order:
        print(f"  {table}: {len(rowids)} row(s)")
        cols = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')][:8]
        for rid in rowids[:50]:
            row = con.execute(f'SELECT {", ".join(chr(34) + x + chr(34) for x in cols)} '
                              f'FROM "{table}" WHERE rowid = ?', (rid,)).fetchone()
            print(f"    {dict(zip(cols, row))}")
        if len(rowids) > 50:
            print(f"    … {len(rowids) - 50} more")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="backup, then delete (default: dry-run)")
    a = ap.parse_args(argv)
    if not c.HOST_ENV.exists():
        print(f"✗ REFUSED: host marker {c.HOST_ENV} not found — this script runs on the HOST "
              f"rehearsal DB only; the laptop never had these rows.")
        return 2
    c.load_host_env()
    db = c.db_path()
    import sp_backup
    with c.db_lock():
        con = sqlite3.connect(db)
        try:
            pre = nfl_counts(con)
            teams, order = plan(con)
            print(f"all-star teams: {[(t[0], t[1]) for t in teams] or 'none'}")
            for t in teams:
                print(f"  team id={t[0]} {t[1]!r}: {t[2]}")
            show(con, order)
            print(f"pre-counts:  games {pre['games']}  teams {pre['teams']}")
            if not a.apply or not order:
                print("dry-run: nothing deleted" if order else "nothing to remove")
                c.append_receipt({"kind": "cleanup", "exit": 0, "applied": False,
                                  "planned": {t: len(r) for t, r in order}})
                return 0
            bk = sp_backup.run_backup("precleanup", lock=False)
            if bk["exit"] != 0:
                print(f"✗ pre-cleanup backup failed ({bk.get('error')}); nothing deleted.")
                return 1
            print(f"✓ backup {bk['file']} integrity={bk['integrity']} sha256={bk['sha256'][:16]}")
            with con:  # one transaction: all or nothing
                for table, rowids in order:
                    for i in range(0, len(rowids), 500):
                        chunk = rowids[i:i + 500]
                        con.execute(f'DELETE FROM "{table}" WHERE rowid IN '
                                    f'({",".join("?" * len(chunk))})', chunk)
            post = nfl_counts(con)
        finally:
            con.close()
    print(f"post-counts: games {post['games']}  teams {post['teams']}")
    c.append_receipt({"kind": "cleanup", "exit": 0, "applied": True, "backup": bk["file"],
                      "backup_sha256": bk["sha256"], "teams": [(t[0], t[1]) for t in teams],
                      "deleted": {t: len(r) for t, r in order},
                      "pre": pre, "post": post})
    return 0


if __name__ == "__main__":
    sys.exit(main())
