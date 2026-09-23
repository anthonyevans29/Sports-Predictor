"""
NHL Phase 0 probe (2026-09-23) — read-only reconnaissance, zero wiring.

Answers the three questions Phase 1's build depends on, per H-track
doctrine (famous-club receipt or stop; season-string semantics verified
BEFORE any sync — the WC lesson):

  1. Does this plan's key reach the hockey product?
  2. What is the NHL's league id?  (verified by Maple Leafs / Bruins in
     the team list, never trusted from memory)
  3. What season-string format does the API use for 2026-27?

Run:  python3 scripts/nhl_phase0_probe.py
Writes nothing. Prints receipts.
"""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(".env")

KEY = (os.getenv("API_HOCKEY_KEY")
       or os.getenv("API_AMERICAN_FOOTBALL_KEY")
       or os.getenv("API_FOOTBALL_KEY") or "")
BASE = "https://v1.hockey.api-sports.io"
HDRS = {"x-apisports-key": KEY}


def get(path, **params):
    r = requests.get(f"{BASE}/{path}", headers=HDRS, params=params, timeout=15)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        print(f"  ✗ API errors on /{path}: {body['errors']}")
        sys.exit(1)
    return body.get("response") or []


def main():
    if not KEY:
        print("✗ No API key found (API_HOCKEY_KEY / fallbacks). Stop.")
        sys.exit(1)

    print("Q1 — plan coverage: requesting /leagues …")
    leagues = get("leagues", search="NHL")
    if not leagues:
        print("  ✗ No NHL in /leagues — plan may not cover hockey. Stop.")
        sys.exit(1)
    for lg in leagues[:3]:
        l = lg.get("league") or lg
        print(f"  candidate: id={l.get('id')} name={l.get('name')!r} "
              f"country={(lg.get('country') or {}).get('name')}")
        seasons = lg.get("seasons") or []
        if seasons:
            latest = seasons[-1]
            print(f"    seasons tail: {[s.get('season') for s in seasons[-3:]]}"
                  f"  (format receipt — single-year int vs cross-year)")

    nhl_id = (leagues[0].get("league") or leagues[0]).get("id")
    print(f"\nQ2 — famous-club receipt for id={nhl_id}: requesting /teams …")
    # try the latest listed season for the id
    seasons = (leagues[0].get("seasons") or [])
    season_val = seasons[-1].get("season") if seasons else 2026
    teams = get("teams", league=nhl_id, season=season_val)
    names = [(t.get("team") or t).get("name") for t in teams]
    print(f"  {len(names)} teams for season={season_val!r}")
    famous = [n for n in names if n and ("Maple Leafs" in n or "Bruins" in n
                                          or "Rangers" in n or "Canadiens" in n)]
    print(f"  famous-club check: {famous or 'NONE — WRONG LEAGUE, stop'}")
    print(f"  sample: {names[:6]}")

    print(f"\nQ3 — games shape: requesting a few games for season={season_val!r} …")
    games = get("games", league=nhl_id, season=season_val)
    print(f"  {len(games)} games listed")
    for g in games[:3]:
        print(f"    {g.get('date')} {((g.get('teams') or {}).get('away') or {}).get('name')} @ "
              f"{((g.get('teams') or {}).get('home') or {}).get('name')} "
              f"status={((g.get('status') or {}).get('short'))}")
    pre = [g for g in games if (g.get('status') or {}).get('short') in ('PRE', 'NS')]
    print(f"  (scheduled/preseason-ish in listing: {len(pre)})")

    print("\n✓ Phase 0 receipts complete — paste this output back for the "
          "Phase 1 go/no-go read.")


if __name__ == "__main__":
    main()
