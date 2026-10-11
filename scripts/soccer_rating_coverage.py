"""
SOCCER RATING COVERAGE (ARCHITECT 2026-10-10, addendum 36 item 4), READ-ONLY: "scripts/soccer_rating_coverage.py
--competition CODE --season S. For each team of that competition and season: its id, its name, its rating in the
production model's league table or MISSING, and its team_to_league. Then the totals. The operator runs it on both
machines, and both consoles go on the Issue." (#410)

"Team of that competition and season" = every team id appearing as home or away in that competition's stored matches
of that season. The production model is the single model_versions row with sport soccer, family soccer_elo_poisson
and status production (training._current_production_version takes exactly one; more or none refuses, exit 2). Its
league table is parameters.elo.league.ratings (the legacy single-state shape, parameters.elo.ratings, is read the way
training.py reads it). Keys are team ids as JSON strings; MISSING means the id is not a key, which is when
EloState.get answers the starting rating. team_to_league is shown as stored, or "-" when the id is not in it.

Opens the DB read-only (mode=ro URI; a copy that refuses it falls back to a plain connect, SELECT only).

    python3 scripts/soccer_rating_coverage.py --competition PL --season 2026/27 [--db PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

FAMILY = "soccer_elo_poisson"


def db_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    url = os.getenv("DATABASE_URL")
    if not url:
        try:
            from dotenv import load_dotenv
            load_dotenv(".env")
            url = os.getenv("DATABASE_URL")
        except ImportError:
            pass
    url = url or "sqlite:///./data/sports.db"
    if not url.startswith("sqlite:///"):
        raise SystemExit(f"not a SQLite URL ({url.split(':')[0]}): the receipt is SQLite-only")
    return Path(url.replace("sqlite:///", ""))


def open_read(p: Path):
    if not p.exists():
        raise SystemExit(f"no database at {p}")
    try:
        con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
        con.execute("SELECT 1 FROM model_versions LIMIT 1")
        return con, "mode=ro URI"
    except sqlite3.OperationalError:
        con = sqlite3.connect(str(p), timeout=60)
        con.execute("SELECT 1 FROM model_versions LIMIT 1")
        return con, "plain connect (mode=ro refused), SELECT only"


class Refused(Exception):
    pass


def production(con) -> tuple[str, dict]:
    rows = con.execute("SELECT version, parameters FROM model_versions WHERE lower(sport) = 'soccer' "
                       "AND model_family = ? AND status = 'production'", (FAMILY,)).fetchall()
    if len(rows) != 1:
        raise Refused(f"REFUSED: {len(rows)} production {FAMILY} rows (exactly one is the production model)"
                      + (": " + ", ".join(r[0] for r in rows) if rows else ""))
    version, params = rows[0]
    params = json.loads(params) if isinstance(params, str) else (params or {})
    return version, params


def league_table(params: dict) -> dict:
    elo = params.get("elo") or {}
    raw = (elo.get("league") or {}) if ("league" in elo or "cup" in elo) else elo
    return {str(k): v for k, v in (raw.get("ratings") or {}).items()}


def coverage(con, competition: str, season: str) -> dict:
    comp = con.execute("SELECT id FROM competitions WHERE code = ?", (competition,)).fetchone()
    if comp is None:
        raise Refused(f"REFUSED: competition {competition} not in the DB")
    version, params = production(con)
    table = league_table(params)
    t2l = {str(k): v for k, v in (params.get("team_to_league") or {}).items()}
    # driven from the match-side ids, team names LEFT JOINed (Codex on #417): an id with no team row stays visible
    teams = con.execute(
        "SELECT ids.tid, COALESCE(t.name, '(no team row)') FROM ("
        " SELECT home_team_id AS tid FROM matches WHERE competition_id = ? AND season = ?"
        " UNION SELECT away_team_id FROM matches WHERE competition_id = ? AND season = ?) ids"
        " LEFT JOIN teams t ON t.id = ids.tid WHERE ids.tid IS NOT NULL ORDER BY t.name IS NULL, t.name, ids.tid",
        (comp[0], season, comp[0], season)).fetchall()
    rows = [{"id": tid, "name": name, "rating": table.get(str(tid)), "team_to_league": t2l.get(str(tid))}
            for tid, name in teams]
    rated = [r for r in rows if r["rating"] is not None]
    return {"competition": competition, "season": season, "model_version": version, "table_size": len(table),
            "rows": rows, "teams": len(rows), "in_table": len(rated), "missing": len(rows) - len(rated),
            "league_matches": sum(1 for r in rows if r["team_to_league"] == competition),
            "league_other": sum(1 for r in rows if r["team_to_league"] not in (None, competition)),
            "league_absent": sum(1 for r in rows if r["team_to_league"] is None)}


def report(c: dict, echo=print) -> None:
    echo(f"{c['competition']} {c['season']} · production {FAMILY} {c['model_version']} · league table "
         f"{c['table_size']} ids")
    echo(f"  {'id':>6}  {'name':<28} {'rating':>9}  team_to_league")
    for r in c["rows"]:
        rating = f"{r['rating']:.1f}" if isinstance(r["rating"], (int, float)) else (
            "MISSING" if r["rating"] is None else str(r["rating"]))
        echo(f"  {r['id']:>6}  {r['name'][:28]:<28} {rating:>9}  {r['team_to_league'] or '-'}")
    echo(f"TOTALS teams {c['teams']} · in the table {c['in_table']} · MISSING {c['missing']} · team_to_league "
         f"{c['competition']} {c['league_matches']} · other league {c['league_other']} · absent {c['league_absent']}")
    echo(f"SOCCER-RATING-COVERAGE {json.dumps({k: c[k] for k in ('competition', 'season', 'model_version', 'teams', 'in_table', 'missing', 'league_matches', 'league_other', 'league_absent')})}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 36 item 4: the production soccer model's rating coverage")
    ap.add_argument("--competition", required=True)
    ap.add_argument("--season", required=True)
    ap.add_argument("--db")
    a = ap.parse_args(argv)
    con, form = open_read(db_path(a.db))
    try:
        print(f"read-only open: {form}")
        report(coverage(con, a.competition, a.season))
    except Refused as e:
        print(str(e))
        return 2
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
