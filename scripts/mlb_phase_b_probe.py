"""
MLB PHASE B PROBE (architect, 2026-09-29) — read-only, zero wiring.

Question: can api-sports BASEBALL feed what MLB predictions need beyond
schedule/results — starting PITCHERS, BULLPEN usage, UMPIRES? The first probe
ruled /games AMBER for predictions (no pitcher/umpire/bullpen fields). This
decides whether MLB predictions can ever run from the host (statsapi 406s
datacenter ASNs). Next-spring planning: the offseason is 5 weeks out.

Run on the LAPTOP (the key lives there):

    python3 scripts/mlb_phase_b_probe.py [--season 2026] [--out receipt.json]

What it does (law 1: the endpoint list is PROBED, never assumed; the adapter's
docs note lists Timezone/Seasons/Countries/Leagues/Teams/Standings/Games/Odds/
Bets/Bookmakers and no player endpoint):
  1. finds a recent FINISHED MLB game id (/games by date, up to 4 days back);
  2. dumps every key path of that /games item and flags any whose name smells
     of pitcher / bullpen / umpire / lineup / player data;
  3. calls each CANDIDATE path once, classifying it:
       EXISTS          a response came back (n items; its key paths are flagged too)
       NO-SUCH-ENDPOINT the API says the endpoint does not exist
       EXISTS-PARAMS   the API rejects our params (the endpoint is real)
       ERROR           HTTP / network / auth failure (reported, not interpreted)
  4. verdict per need (pitchers, bullpen, umpires): FEEDABLE (fields found on
     an existing endpoint) or NOT FROM API-SPORTS BASEBALL.

Cost: 1-4 /games date calls + one call per candidate (~10). Writes nothing
unless --out is given (never under data/).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

NEEDS = {
    "pitchers": re.compile(r"pitch|starter|probable", re.I),
    "bullpen": re.compile(r"bullpen|reliev|relief|save|hold|innings_?pitched|\bip\b", re.I),
    "umpires": re.compile(r"umpire|referee|official", re.I),
}
LINEUP = re.compile(r"lineup|player|roster|batter", re.I)


def candidates(game_id, season: int) -> list[tuple[str, dict]]:
    g = {"id": game_id}
    ls = {"league": 1, "season": season}
    return [
        ("timezone", {}),                         # control: a documented endpoint must EXIST
        ("players", ls), ("players/statistics", ls), ("players/squads", {"team": 1, "season": season}),
        ("games/statistics", g), ("games/statistics/players", g), ("games/statistics/teams", g),
        ("games/players", g), ("games/events", g), ("games/lineups", g),
        ("injuries", ls), ("umpires", {}),
    ]


def key_paths(obj, prefix: str = "") -> list[str]:
    """Every key path in a JSON value (lists collapse to [])."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            out.append(p)
            out += key_paths(v, p)
    elif isinstance(obj, list) and obj:
        out += key_paths(obj[0], f"{prefix}[]")
    return out


def flag(paths: list[str]) -> dict:
    return {need: sorted(p for p in paths if rx.search(p.split(".")[-1])) for need, rx in NEEDS.items()} | \
           {"lineup/player": sorted(p for p in paths if LINEUP.search(p.split(".")[-1]))}


def classify(fetch, path: str, params: dict) -> dict:
    """fetch(path, params) -> dict, raising on API/HTTP errors (the client's contract)."""
    try:
        data = fetch(path, params)
    except Exception as e:  # noqa: BLE001 — every failure is a receipt row
        msg = str(e)
        if re.search(r"endpoint", msg, re.I) and re.search(r"exist|not found|unknown", msg, re.I):
            return {"path": path, "status": "NO-SUCH-ENDPOINT", "detail": msg[:200]}
        if re.search(r"API error", msg):
            return {"path": path, "status": "EXISTS-PARAMS", "detail": msg[:200]}
        return {"path": path, "status": "ERROR", "detail": msg[:200]}
    resp = data.get("response")
    items = resp if isinstance(resp, list) else ([resp] if resp else [])
    paths = key_paths(items[0]) if items else []
    return {"path": path, "status": "EXISTS", "results": data.get("results", len(items)),
            "item_keys": sorted({p.split(".")[0] for p in paths}), "flags": flag(paths)}


def verdict(game_flags: dict, rows: list[dict]) -> dict:
    out = {}
    for need in NEEDS:
        where = ([f"/games: {', '.join(game_flags[need][:5])}"] if game_flags.get(need) else []) + \
                [f"/{r['path']}: {', '.join(r['flags'][need][:5])}" for r in rows
                 if r["status"] == "EXISTS" and r["flags"].get(need)]
        out[need] = {"feedable": bool(where), "where": where}
    return out


def find_finished_game(fetch, season: int, today: datetime) -> dict | None:
    for back in range(1, 5):
        d = (today - timedelta(days=back)).strftime("%Y-%m-%d")
        try:
            games = fetch("games", {"league": 1, "season": season, "date": d}).get("response") or []
        except Exception:  # noqa: BLE001
            continue
        for g in games:
            if ((g.get("status") or {}).get("short") or "").upper() in ("FT", "AOT"):
                return g
    return None


def run(fetch, season: int, today: datetime) -> dict:
    game = find_finished_game(fetch, season, today)
    game_paths = key_paths(game) if game else []
    game_flags = flag(game_paths) if game else {}
    rows = [classify(fetch, p, prm) for p, prm in candidates(game.get("id") if game else None, season)
            if game or "id" not in prm]
    return {"game_id": game.get("id") if game else None, "game_key_paths": game_paths,
            "game_flags": game_flags, "endpoints": rows, "verdict": verdict(game_flags, rows),
            "control_ok": any(r["path"] == "timezone" and r["status"] == "EXISTS" for r in rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MLB PHASE B: api-sports Baseball pitcher/bullpen/umpire feed probe")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from src.adapters.api_baseball import APIBaseballClient
    cl = APIBaseballClient.from_env()
    if cl is None:
        print("✗ No API-Baseball key (API_BASEBALL_KEY / API_FOOTBALL_KEY). Stop.")
        return 1
    r = run(lambda path, params: cl._get(path, params=params), a.season,
            datetime.now(timezone.utc).replace(tzinfo=None))
    print(f"PHASE B PROBE — season {a.season} · finished game used: {r['game_id']}")
    print(f"  /games item key paths ({len(r['game_key_paths'])}): {r['game_key_paths']}")
    print(f"  /games flags: {r['game_flags']}")
    for e in r["endpoints"]:
        tail = (f"results {e['results']} · keys {e['item_keys']} · flags "
                f"{ {k: v for k, v in e['flags'].items() if v} }" if e["status"] == "EXISTS" else e["detail"])
        print(f"  {e['status']:17s} /{e['path']:26s} {tail}")
    print(f"  control (/timezone EXISTS): {'✓' if r['control_ok'] else '✗ — results below are not trustworthy'}")
    print("VERDICT:")
    for need, v in r["verdict"].items():
        print(f"  {'✓ FEEDABLE' if v['feedable'] else '✗ NOT FROM API-SPORTS BASEBALL'}: {need}"
              + (f" — {'; '.join(v['where'])}" if v["where"] else ""))
    print(f"provider requests remaining: {cl.requests_remaining}")
    if a.out:
        if "data" in a.out.resolve().parts:
            print("✗ refusing to write under data/ (law 5).")
            return 1
        a.out.write_text(json.dumps(r, indent=1, default=str))
        print(f"✓ receipt written to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
