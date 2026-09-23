"""
NHL score-shape probe (2026-09-23) — diagnoses the 302-null-scores defect.

Fetches season 2024 raw games and prints the UNPARSED status/scores JSON
for (a) three games our parser handles, (b) three it fails on — the
side-by-side names the shape variant. Read-only.

Run:  python3 scripts/nhl_score_probe.py
"""
import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(".env")

KEY = (os.getenv("API_HOCKEY_KEY")
       or os.getenv("API_AMERICAN_FOOTBALL_KEY")
       or os.getenv("API_FOOTBALL_KEY") or "")


def parsed_score(block):
    """Mirror the adapter's current logic exactly."""
    if isinstance(block, dict):
        return block.get("total")
    return block


def main():
    r = requests.get("https://v1.hockey.api-sports.io/games",
                     headers={"x-apisports-key": KEY},
                     params={"league": 57, "season": 2024}, timeout=30)
    r.raise_for_status()
    games = r.json().get("response") or []
    ok, bad = [], []
    for g in games:
        game = g.get("game") or g
        scores = g.get("scores") or {}
        status = (game.get("status") or {})
        short = status.get("short") if isinstance(status, dict) else status
        hs = parsed_score(scores.get("home"))
        as_ = parsed_score(scores.get("away"))
        rec = {"id": game.get("id"), "short": short,
               "raw_status": status, "raw_scores": scores,
               "parsed": (hs, as_)}
        if short == "FT" and (hs is None or as_ is None):
            bad.append(rec)
        elif hs is not None and as_ is not None:
            ok.append(rec)
    print(f"{len(games)} games | parser-ok {len(ok)} | FT-with-null-parse {len(bad)}")
    print("\n== THREE THAT PARSE ==")
    for rec in ok[:3]:
        print(json.dumps({k: rec[k] for k in ("id", "short", "raw_scores", "parsed")},
                         default=str))
    print("\n== THREE THAT FAIL ==")
    for rec in bad[:3]:
        print(json.dumps({k: rec[k] for k in ("id", "short", "raw_status", "raw_scores", "parsed")},
                         default=str))
    if not bad:
        print("(no FT-null cases in this pull — paste anyway; the ok-shapes "
              "plus DB ids will guide the next step)")


if __name__ == "__main__":
    sys.exit(main())
