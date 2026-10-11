"""
NFL INJURED-PLAYER POSITION PROBE (ARCHITECT 2026-10-11, addendum 40 item 4, PROBE FIRST; #432, finding #424),
READ-ONLY: "a read-only script that takes the injured players whose position did not resolve in the stored lists and
asks the provider for each by its player id. Does it answer a position? The operator runs it and the console goes on
the Issue. Nothing is built on it until I have read it."

Law 1, from the code: our injuries rows store no provider player id (src/db/schema.py Injury: team_id, player_name,
player_position, reason, type, fixture_source_id, source, refreshed_at). So for each team with an unresolved name the
probe reads the provider's own /injuries answer for that team (the feed the sync reads; player = id/name/image) and
takes the player id from it by EXACT name. A stored name the feed no longer lists has no id: it is listed, never
guessed. Then, per id, GET /players?id=<id> and print what the provider answers: every field of each player object
(position and group verbatim), or that it answered nothing.

- The stored side opens the database mode=ro (URI); a copy that refuses it: the plain path with PRAGMA query_only =
  ON, and the console says which (#421's rule). It writes nothing.
- The provider side: GET only, api-sports american-football (API_AMERICAN_FOOTBALL_KEY, else API_FOOTBALL_KEY, from
  the environment or .env; the key is never printed). One /injuries call per team and one /players call per id; the
  count of calls is printed. `--team` narrows to teams whose name contains the text; `--limit` caps the ids asked.
- `--out FILE` appends one JSON line per player (the stored row, the feed's player object, the /players answer).

    python3 scripts/nfl_injury_position_probe.py [--team Baltimore] [--limit 40] [--out probe.jsonl] [--db PATH]
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
SOURCE = "api_american_football"                         # the adapter's source_name (teams.external_ids key)


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
        raise SystemExit(f"not a SQLite URL ({url.split(':')[0]}): the probe is SQLite-only")
    return Path(url.replace("sqlite:///", ""))


def open_read(p: Path):
    """(connection, form): mode=ro first; a copy that refuses it: the plain path with query_only set (#421)."""
    if not p.exists():
        raise SystemExit(f"no database at {p}")
    try:
        con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
        con.execute("SELECT 1 FROM injuries LIMIT 1")
        return con, "mode=ro URI"
    except sqlite3.OperationalError:
        con = sqlite3.connect(str(p), timeout=60)
        con.execute("PRAGMA query_only = ON")
        con.execute("SELECT 1 FROM injuries LIMIT 1")
        return con, "plain path with PRAGMA query_only = ON (mode=ro refused)"


def unresolved(con, team_filter: str | None = None, competition: str = "NFL") -> list[dict]:
    """The stored injured players of NFL teams (teams in a stored match of `competition`) whose position is empty."""
    rows = con.execute(
        "SELECT i.id, i.team_id, t.name, t.external_ids, i.player_name, i.refreshed_at FROM injuries i "
        "JOIN teams t ON t.id = i.team_id "
        "WHERE (i.player_position IS NULL OR TRIM(i.player_position) = '') AND i.team_id IN ("
        " SELECT m.home_team_id FROM matches m JOIN competitions c ON c.id = m.competition_id WHERE c.code = ?"
        " UNION SELECT m.away_team_id FROM matches m JOIN competitions c ON c.id = m.competition_id"
        " WHERE c.code = ?) ORDER BY t.name, i.player_name", (competition, competition)).fetchall()
    out = []
    for iid, tid, tname, ext, pname, at in rows:
        if team_filter and team_filter.lower() not in (tname or "").lower():
            continue
        try:
            ext = json.loads(ext) if isinstance(ext, str) else (ext or {})
        except ValueError:
            ext = {}
        out.append({"injury_id": iid, "team_id": tid, "team": tname, "team_source_id": (ext or {}).get(SOURCE),
                    "player_name": pname, "refreshed_at": at})
    return out


def out_refusal(out: str, db: Path) -> str | None:
    """--out never touches storage (Codex on #436): not under data/, not the database, not one of its -wal / -shm /
    -journal sidecars, and not a hard link or symlink to any of them (compared by resolved path and file identity)."""
    tgt = Path(out).resolve()
    data = (ROOT / "data").resolve()
    if tgt == data or data in tgt.parents:
        return f"REFUSED: --out {out} is under data/ (law 5)"
    dbs = [Path(str(db.resolve()) + x) for x in ("", "-wal", "-shm", "-journal")]

    def same(a, b) -> bool:
        try:
            return os.path.samefile(a, b)
        except OSError:
            return False
    if tgt in dbs or (tgt.exists() and any(x.exists() and same(tgt, x) for x in dbs)):
        return f"REFUSED: --out {out} is the database (or its sidecar) {db}: the probe is read-only"
    return None


def provider_errors(ans: dict):
    """The api-sports envelope's own errors (an HTTP-200 answer can carry them): a failed read, never evidence."""
    errs = (ans or {}).get("errors")
    return errs if errs and (errs if isinstance(errs, list) else list(errs.values())) else None


def get_json(path: str, params: dict, key: str, fetch=None) -> dict:
    """GET only. `fetch(path, params) -> dict` is injectable (tests)."""
    if fetch is not None:
        return fetch(path, params)
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET", headers={"x-apisports-key": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def probe(items: list[dict], key: str, limit: int | None = None, fetch=None, echo=print) -> dict:
    by_team: dict = {}
    for x in items:
        by_team.setdefault((x["team_id"], x["team"], x["team_source_id"]), []).append(x)
    calls, asked, results = 0, 0, []
    for (tid, tname, sid), xs in by_team.items():
        echo(f"\n{tname} (team {tid}, provider team {sid or 'NONE'}): {len(xs)} stored name(s) with no position")
        if not sid:
            for x in xs:
                results.append({**x, "verdict": "no provider team id"})
                echo(f"  {x['player_name']}: no provider team id on our team row: not asked")
            continue
        feed = get_json("injuries", {"team": sid}, key, fetch)
        calls += 1
        ferr = provider_errors(feed)
        if ferr:                          # Codex on #436: a provider error is a failed read, not "not in the feed"
            echo(f"  /injuries answered errors {ferr}: a failed read; no name of this team is judged")
            for x in xs:
                results.append({**x, "verdict": "provider error (/injuries)", "errors": ferr})
            continue
        ids: dict = {}
        for it in feed.get("response") or []:
            pl = it.get("player") or {}
            if pl.get("name"):
                ids.setdefault(pl["name"].strip(), pl)
        for x in xs:
            pl = ids.get(x["player_name"])
            if pl is None or pl.get("id") is None:
                results.append({**x, "verdict": "not in the feed now (no id)"})
                echo(f"  {x['player_name']}: the feed does not list this name now: no player id, not asked")
                continue
            if limit is not None and asked >= limit:
                results.append({**x, "feed_player": pl, "verdict": "not asked (--limit)"})
                echo(f"  {x['player_name']} (player id {pl['id']}): not asked (--limit {limit})")
                continue
            ans = get_json("players", {"id": pl["id"]}, key, fetch)
            calls += 1
            asked += 1
            resp = ans.get("response") or []
            objs = [r.get("player") if isinstance(r.get("player"), dict) else r for r in resp]
            pos = [(o.get("position"), o.get("group")) for o in objs]
            verdict = ("provider error (/players)" if provider_errors(ans) else
                       "answers a position" if any(p for p, _ in pos) else
                       "answers a group only" if any(g for _, g in pos) else
                       "answers no position" if objs else "answers nothing")
            results.append({**x, "feed_player": pl, "players_answer": ans, "verdict": verdict})
            echo(f"  {x['player_name']} (player id {pl['id']}): {verdict} · results {ans.get('results', len(resp))}"
                 + (f" · errors {ans.get('errors')}" if ans.get("errors") else ""))
            for o in objs:
                echo("      " + json.dumps(o, sort_keys=True, default=str))          # every field, never cut
    counts: dict = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {"names": len(items), "teams": len(by_team), "calls": calls, "verdicts": counts, "results": results}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 40 item 4: does the provider answer a position by player id?")
    ap.add_argument("--team", help="only teams whose name contains this text")
    ap.add_argument("--limit", type=int, default=None, help="ask at most this many player ids")
    ap.add_argument("--out", help="append one JSON line per player here")
    ap.add_argument("--db")
    a = ap.parse_args(argv)
    dbp = db_path(a.db)
    if a.out and (why := out_refusal(a.out, dbp)):
        print(why)
        return 2
    con, form = open_read(dbp)
    try:
        items = unresolved(con, a.team)
    finally:
        con.close()
    print(f"read-only open: {form} · stored NFL injured players with no position: {len(items)}")
    key = _dotenv("API_AMERICAN_FOOTBALL_KEY") or _dotenv("API_FOOTBALL_KEY")
    if not key:
        print("REFUSED: no API_AMERICAN_FOOTBALL_KEY / API_FOOTBALL_KEY in the environment or .env")
        return 2
    res = probe(items, key, a.limit)
    if a.out:
        with open(a.out, "a", encoding="utf-8") as f:
            for r in res["results"]:
                f.write(json.dumps(r, default=str) + "\n")
    print("\nNFL-POSITION-PROBE " + json.dumps({k: res[k] for k in ("names", "teams", "calls", "verdicts")},
                                                sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
