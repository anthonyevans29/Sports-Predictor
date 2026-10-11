"""
HAWAI'I UNDER TWO PROVIDER TEAM IDS (ARCHITECT 2026-10-11, addendum 40 item 7, RECEIPT FIRST; #426), READ-ONLY:
"This morning's NCAA probe: three stored games (32536 Hawai'i at Wyoming, 32724 San José State at Hawai'i, 32744
Hawai'i at Arizona State) match a listing game by id while our Hawai'i carries team source id 901 and the listing's
carries 59. A read-only receipt: our teams named like Hawai'i with their ids, source ids and game counts, and what the
provider answers for team 59 and for team 901. [...] Nothing is built until I have read it."

1. OUR TEAMS: every team whose name contains "Hawai" (the HTML-escaped "Hawai&#x27;i" of #358 included): id, name as
   stored, sport, every external id, and its stored games (home + away) in total and by competition and season.
2. THE THREE GAMES (default 32536, 32724, 32744; --match to change): id, competition, season, kickoff, status, both
   teams (id, name, their api_american_football id) and the game's own external ids.
3. THE PROVIDER: GET /teams?id=<id> for each provider team id (default 59 and 901; --provider-team to change), every
   field of each answer verbatim. api-sports american-football (API_AMERICAN_FOOTBALL_KEY, else API_FOOTBALL_KEY;
   never printed). --no-provider skips it.

The database opens mode=ro (URI); a copy that refuses it: the plain path with PRAGMA query_only = ON, and the console
says which (#421's rule). It writes nothing.

    python3 scripts/ncaa_hawaii_receipt.py [--match 32536 --match 32724 ...] [--provider-team 59 ...] [--no-provider]
           [--db PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://v1.american-football.api-sports.io"     # src/adapters/api_american_football.py DIRECT_BASE
SOURCE = "api_american_football"
GAMES = (32536, 32724, 32744)
PROVIDER_TEAMS = (59, 901)


def _dotenv(name: str) -> str | None:
    v = os.getenv(name)
    if v:
        return v
    try:
        from dotenv import dotenv_values
        return dotenv_values(ROOT / ".env").get(name)
    except ImportError:
        return None


def db_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    url = _dotenv("DATABASE_URL") or "sqlite:///./data/sports.db"
    if not url.startswith("sqlite:///"):
        raise SystemExit(f"not a SQLite URL ({url.split(':')[0]}): the receipt is SQLite-only")
    return Path(url.replace("sqlite:///", ""))


def open_read(p: Path):
    if not p.exists():
        raise SystemExit(f"no database at {p}")
    try:
        con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
        con.execute("SELECT 1 FROM teams LIMIT 1")
        return con, "mode=ro URI"
    except sqlite3.OperationalError:
        con = sqlite3.connect(str(p), timeout=60)
        con.execute("PRAGMA query_only = ON")
        con.execute("SELECT 1 FROM teams LIMIT 1")
        return con, "plain path with PRAGMA query_only = ON (mode=ro refused)"


def _ext(v) -> dict:
    try:
        return (json.loads(v) if isinstance(v, str) else v) or {}
    except ValueError:
        return {"(unreadable)": v}


def our_teams(con) -> list[dict]:
    out = []
    for tid, name, sport, ext in con.execute(
            "SELECT id, name, sport, external_ids FROM teams WHERE name LIKE '%Hawai%' ORDER BY id").fetchall():
        games = con.execute(
            "SELECT COALESCE(c.code, '?'), m.season, COUNT(*) FROM matches m LEFT JOIN competitions c "
            "ON c.id = m.competition_id WHERE m.home_team_id = ? OR m.away_team_id = ? GROUP BY 1, 2 ORDER BY 1, 2",
            (tid, tid)).fetchall()
        out.append({"id": tid, "name": name, "sport": sport, "external_ids": _ext(ext),
                    "games": sum(n for _, _, n in games), "by_comp_season": [list(g) for g in games]})
    return out


def the_games(con, ids) -> list[dict]:
    out = []
    for mid in ids:
        r = con.execute(
            "SELECT m.id, COALESCE(c.code, '?'), m.season, m.utc_date, m.status, m.external_ids, "
            "h.id, h.name, h.external_ids, a.id, a.name, a.external_ids FROM matches m "
            "LEFT JOIN competitions c ON c.id = m.competition_id LEFT JOIN teams h ON h.id = m.home_team_id "
            "LEFT JOIN teams a ON a.id = m.away_team_id WHERE m.id = ?", (mid,)).fetchone()
        if r is None:
            out.append({"id": mid, "stored": False})
            continue
        out.append({"id": r[0], "stored": True, "competition": r[1], "season": r[2], "kickoff": r[3], "status": r[4],
                    "external_ids": _ext(r[5]),
                    "home": {"id": r[6], "name": r[7], "source_id": _ext(r[8]).get(SOURCE)},
                    "away": {"id": r[9], "name": r[10], "source_id": _ext(r[11]).get(SOURCE)}})
    return out


def get_json(path: str, params: dict, key: str, fetch=None) -> dict:
    if fetch is not None:
        return fetch(path, params)
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET", headers={"x-apisports-key": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def report(teams, games, provider: dict | None, echo=print) -> None:
    echo(f"OUR TEAMS named like Hawai'i: {len(teams)}")
    for t in teams:
        echo(f"  team {t['id']} · {t['name']!r} · sport {t['sport']} · external ids {json.dumps(t['external_ids'])}"
             f" · stored games {t['games']}")
        for comp, season, n in t["by_comp_season"]:
            echo(f"      {comp} {season}: {n}")
    echo(f"\nTHE GAMES: {len(games)}")
    for g in games:
        if not g["stored"]:
            echo(f"  match {g['id']}: not stored")
            continue
        echo(f"  match {g['id']} · {g['competition']} {g['season']} · {g['kickoff']} · {g['status']} · game external "
             f"ids {json.dumps(g['external_ids'])}")
        for side in ("away", "home"):
            s = g[side]
            echo(f"      {side}: team {s['id']} {s['name']!r} · {SOURCE} {s['source_id']}")
    if provider is None:
        echo("\nTHE PROVIDER: not asked (--no-provider)")
    else:
        echo("\nTHE PROVIDER: GET /teams?id=<id>, every field verbatim")
        for pid, ans in provider.items():
            resp = ans.get("response") or []
            echo(f"  provider team {pid}: results {ans.get('results', len(resp))}"
                 + (f" · errors {ans.get('errors')}" if ans.get("errors") else ""))
            for o in resp:
                echo("      " + json.dumps(o, sort_keys=True, default=str))
    names = sorted({t["name"] for t in teams})
    src = sorted({str(t["external_ids"].get(SOURCE)) for t in teams if t["external_ids"].get(SOURCE) is not None})
    echo("\nNCAA-HAWAII-RECEIPT " + json.dumps({"teams": len(teams), "names": names, "source_ids": src,
                                                "games_stored": sum(1 for g in games if g["stored"]),
                                                "provider_asked": sorted(provider) if provider else []},
                                               sort_keys=True))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 40 item 7: Hawai'i under two provider team ids")
    ap.add_argument("--match", type=int, action="append", help=f"a stored match id (default {GAMES})")
    ap.add_argument("--provider-team", type=int, action="append", help=f"a provider team id (default {PROVIDER_TEAMS})")
    ap.add_argument("--no-provider", action="store_true")
    ap.add_argument("--db")
    a = ap.parse_args(argv)
    con, form = open_read(db_path(a.db))
    try:
        print(f"read-only open: {form}")
        teams, games = our_teams(con), the_games(con, a.match or GAMES)
    finally:
        con.close()
    provider = None
    if not a.no_provider:
        key = _dotenv("API_AMERICAN_FOOTBALL_KEY") or _dotenv("API_FOOTBALL_KEY")
        if not key:
            print("REFUSED: no API_AMERICAN_FOOTBALL_KEY / API_FOOTBALL_KEY (or run with --no-provider)")
            return 2
        provider = {pid: get_json("teams", {"id": pid}, key) for pid in (a.provider_team or PROVIDER_TEAMS)}
    report(teams, games, provider)
    return 0


if __name__ == "__main__":
    sys.exit(main())
