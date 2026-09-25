"""
NCAA Phase 0 probe (2026-09-25) — read-only reconnaissance, zero wiring.

The H-track pattern applied to college football: verify before code.
  1. Does the american-football plan carry NCAA?
  2. League id — verified by famous-program receipt (Alabama / Ohio
     State / Michigan in the team list), never trusted from memory.
  3. Season format + games-per-season scale (FBS-only vs FBS+FCS
     changes the sync's size class — measure, then decide).

Run:  python3 scripts/ncaa_phase0_probe.py
Writes nothing. Prints receipts.
"""
import os
import sys
import collections

import requests
from dotenv import load_dotenv

load_dotenv(".env")

KEY = (os.getenv("API_AMERICAN_FOOTBALL_KEY")
       or os.getenv("API_FOOTBALL_KEY") or "")
BASE = "https://v1.american-football.api-sports.io"
HDRS = {"x-apisports-key": KEY}


def get(path, **params):
    r = requests.get(f"{BASE}/{path}", headers=HDRS, params=params, timeout=20)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        print(f"  ✗ API errors on /{path}: {body['errors']}")
        sys.exit(1)
    return body.get("response") or []


def main():
    if not KEY:
        print("✗ No API key found. Stop.")
        sys.exit(1)

    print("Q1 — /leagues (full list; this API has no search param) …")
    leagues = [lg for lg in get("leagues")
               if "NCAA" in (((lg.get("league") or lg).get("name")) or "")]
    if not leagues:
        print("  ✗ No NCAA league found — plan or product gap. Stop.")
        sys.exit(1)
    for lg in leagues[:4]:
        l = lg.get("league") or lg
        seasons = [s.get("season") for s in (lg.get("seasons") or [])]
        print(f"  candidate: id={l.get('id')} name={l.get('name')!r} "
              f"seasons tail={seasons[-3:]}")

    ncaa_id = (leagues[0].get("league") or leagues[0]).get("id")
    seasons = (leagues[0].get("seasons") or [])
    season_val = seasons[-1].get("season") if seasons else 2026

    print(f"\nQ2 — famous-program receipt for id={ncaa_id}, season={season_val!r} …")
    teams = get("teams", league=ncaa_id, season=season_val)
    names = [(t.get("team") or t).get("name") or "" for t in teams]
    famous = [n for n in names if any(x in n for x in
              ("Alabama", "Ohio State", "Michigan", "Georgia", "Texas"))]
    print(f"  {len(names)} teams | famous check: {famous[:5] or 'NONE — stop'}")
    print(f"  sample: {names[:6]}")

    print(f"\nQ3 — games scale for season={season_val!r} …")
    games = get("games", league=ncaa_id, season=season_val)
    print(f"  {len(games)} games listed")
    weeks = collections.Counter(
        (g.get("game") or g).get("week") or (g.get("game") or g).get("stage")
        for g in games)
    print(f"  week/stage vocabulary (top 6): {weeks.most_common(6)}")
    shorts = collections.Counter(
        (((g.get("game") or g).get("status") or {}).get("short")) for g in games)
    print(f"  status vocabulary: {shorts.most_common(8)}")

    print("\n✓ Phase 0 receipts complete — paste back for the wiring go/no-go "
          "(NCAA enters DATA + MARKET-ONLY; its own model gate comes later).")


if __name__ == "__main__":
    main()
