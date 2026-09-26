"""
H2 probe (2026-09-26) — read-only reconnaissance, zero wiring.

The NHL model track is SUSPENDED at the schedule-only floor (~0.691 vs the
0.6866 bar); goaltending is the missing signal class, and this probe is the
reopening condition's first receipt. Question: does the hockey provider
(v1.hockey.api-sports.io) expose STARTING GOALIES / LINEUPS — which
endpoints, which fields, how far back, and before puck drop?

Endpoint names below are CANDIDATES, not facts (law 1): each is tried and
the provider's own answer (rows, errors, field paths) is the receipt. The
probe never stops on an error — a missing endpoint is a finding.

  Q0  /status          plan + requests remaining (the probe uses ~25)
  Q1  sample games     one recent FINISHED and one upcoming NHL game
  Q2  candidates       per endpoint x game: rows, errors, field paths, and
                       every path/value that smells of goaltending
  Q3  history depth    endpoints that answered: earliest finished game of
                       2025 / 2024 / 2023
  Q4  pre-game         does the UPCOMING game already carry a starter?

Run:  python3 scripts/h2_goalie_probe.py
Writes nothing. Prints receipts — paste the whole output to the architect.
"""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(".env")

KEY = (os.getenv("API_HOCKEY_KEY") or os.getenv("API_AMERICAN_FOOTBALL_KEY")
       or os.getenv("API_FOOTBALL_KEY") or "")
BASE = "https://v1.hockey.api-sports.io"
NHL_LEAGUE_ID = 57          # certified (Phase 0, 2026-09-23)
HDRS = {"x-apisports-key": KEY}

# (path, param-builder) — candidates only; the provider decides.
CANDIDATES = [
    ("games/events", lambda g, t: {"game": g}),
    ("games/players", lambda g, t: {"game": g}),
    ("games/lineups", lambda g, t: {"game": g}),
    ("games/statistics", lambda g, t: {"game": g}),
    ("games/players/statistics", lambda g, t: {"game": g}),
    ("players", lambda g, t: {"team": t, "season": 2025}),
    ("injuries", lambda g, t: {"team": t}),
]
GOALIE_HINTS = ("goal", "goalie", "goaltender", "netminder", "keeper", "starter",
                "lineup", "save")


def get(path, **params):
    """(status_code, api_errors, response_list). Never raises, never exits."""
    try:
        r = requests.get(f"{BASE}/{path}", headers=HDRS, params=params, timeout=20)
    except requests.RequestException as e:
        return None, {"request": str(e)}, []
    try:
        body = r.json()
    except ValueError:
        return r.status_code, {"body": r.text[:120]}, []
    errs = body.get("errors") or {}
    resp = body.get("response")
    if isinstance(resp, dict):
        resp = [resp]
    return r.status_code, errs, resp or []


def field_paths(obj, prefix="", depth=0, out=None, max_depth=4):
    """Flattened key paths of one item (lists: first element, marked [])."""
    out = out if out is not None else []
    if depth > max_depth:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            out.append(p)
            field_paths(v, p, depth + 1, out, max_depth)
    elif isinstance(obj, list) and obj:
        field_paths(obj[0], f"{prefix}[]", depth + 1, out, max_depth)
    return out


def goalie_hits(obj, prefix=""):
    """Every (path, value) whose KEY or string VALUE mentions goaltending."""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            if any(h in str(k).lower() for h in GOALIE_HINTS):
                hits.append((p, v if not isinstance(v, (dict, list)) else type(v).__name__))
            hits += goalie_hits(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:40]):
            hits += goalie_hits(v, f"{prefix}[{i}]")
    elif isinstance(obj, str) and any(h in obj.lower() for h in GOALIE_HINTS):
        hits.append((prefix, obj))
    return hits


def _game_ids(rows, finished):
    out = []
    for g in rows:
        game = g.get("game") or g
        short = ((game.get("status") or {}).get("short") or "")
        done = short in ("FT", "AOT", "AP", "ASO")
        if done == finished:
            home = ((g.get("teams") or {}).get("home") or {}).get("id")
            ts = ((game.get("date") or {}).get("timestamp") or 0)
            out.append((ts, game.get("id"), home, short))
    return sorted(out)


def probe_endpoint(path, params):
    code, errs, rows = get(path, **params)
    hits = goalie_hits(rows)
    return {"code": code, "errors": errs, "rows": len(rows),
            "paths": field_paths(rows[0]) if rows else [], "hits": hits}


def show(label, res):
    print(f"  {label}: HTTP {res['code']} · rows {res['rows']}"
          + (f" · API errors {res['errors']}" if res["errors"] else ""))
    if res["paths"]:
        print(f"    fields: {', '.join(res['paths'][:40])}"
              + (" …" if len(res["paths"]) > 40 else ""))
    for p, v in res["hits"][:12]:
        print(f"    goalie-hint  {p} = {v!r}"[:160])
    if res["rows"] and not res["hits"]:
        print("    (no goaltending hint in this payload)")


def main():
    if not KEY:
        print("✗ No API key found (API_HOCKEY_KEY / API_AMERICAN_FOOTBALL_KEY / API_FOOTBALL_KEY). Stop.")
        return 1

    print("Q0 — /status")
    code, errs, st = get("status")
    acct = st[0] if st else {}
    print(f"  HTTP {code} · subscription {acct.get('subscription')} · requests {acct.get('requests')}"
          + (f" · errors {errs}" if errs else ""))

    print("\nQ1 — sample NHL games")
    _, e25, g25 = get("games", league=NHL_LEAGUE_ID, season=2025)
    _, e26, g26 = get("games", league=NHL_LEAGUE_ID, season=2026)
    fin = _game_ids(g25, finished=True)
    upc = _game_ids(g26, finished=False)
    if not fin:
        print(f"  ✗ no finished 2025 game found (errors {e25}). Stop.")
        return 1
    latest_fin = fin[-1]
    next_upc = upc[0] if upc else None
    print(f"  finished: game {latest_fin[1]} (status {latest_fin[3]}, home team {latest_fin[2]})")
    print(f"  upcoming: " + (f"game {next_upc[1]} (home team {next_upc[2]})" if next_upc
                             else f"none listed for 2026 (errors {e26})"))

    print("\nQ2 — candidate endpoints on the FINISHED game")
    answered = []
    for path, build in CANDIDATES:
        res = probe_endpoint(path, build(latest_fin[1], latest_fin[2]))
        show(f"/{path}", res)
        if res["rows"] and not res["errors"]:
            answered.append((path, build))

    print("\nQ3 — historical depth (earliest finished game per season) for endpoints that answered")
    if not answered:
        print("  (no candidate endpoint returned rows — nothing to date)")
    for season in (2025, 2024, 2023):
        _, errs, rows = get("games", league=NHL_LEAGUE_ID, season=season)
        f = _game_ids(rows, finished=True)
        if not f:
            print(f"  {season}: no finished games listed (errors {errs})")
            continue
        first = f[0]
        for path, build in answered:
            res = probe_endpoint(path, build(first[1], first[2]))
            print(f"  {season} game {first[1]}  /{path}: rows {res['rows']} · goalie-hints "
                  f"{len(res['hits'])}" + (f" · errors {res['errors']}" if res["errors"] else ""))

    print("\nQ4 — pre-game: the UPCOMING game on the endpoints that answered")
    if not next_upc:
        print("  (no upcoming game to test)")
    for path, build in answered:
        res = probe_endpoint(path, build(next_upc[1], next_upc[2])) if next_upc else None
        if res:
            print(f"  /{path}: rows {res['rows']} · goalie-hints {len(res['hits'])}"
                  + (f" · errors {res['errors']}" if res["errors"] else ""))

    print("\n✓ H2 probe complete — paste this whole output to the architect. Nothing was written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
