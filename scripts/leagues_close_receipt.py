"""
LEAGUES CLOSE RECEIPT (ARCHITECT 2026-10-23, addendum 155 item 4(a); addendum 156 item 1; roadmap lane leagues, #322)
— read-only.

155 item 4(a), verbatim: "(a) by 2026-10-30 (code): a read-only receipt per league of the 2026/27 games FINISHED with a
three-way close under addendum 150's rule, and the close's own log-loss on them — the bar's denominator; the same read
for the games still to come this season that already hold a capture."

156 item 1, verbatim in part: "Receipt 4(a) computes it per league: the kickoff date of the 60th 2026/27 fixture of that
league scheduled on or after 2026-11-06 (every game assumed to get a three-way close); the earliest of the four is the
step's date, the other three named in the step's text."

Per league (SA, BL1, FL1, ELC; the season as the DB stores it, "2026/27" by default), from paper.leagues_season:
  - the FINISHED games scored against addendum 150's three-way Kalshi close exactly as results-tally's close record
    scores a three-way competition (paper._score_three; the same line, paper.close_record_line, and the unpriced line
    by cause): n with a close and the close's log-loss on them, the bar's denominator;
  - the games still to come (not FINISHED, not cancelled / postponed / stale_orphan), read for the capture they hold
    now: a capture that forms a close by three_way_close's rule, or the cause it does not (UNPRICED), or none;
  - the projection: the season's stored fixtures (cancelled / postponed / stale_orphan left out) whose kickoff's UTC
    date is on or after the declaration date (2026-11-06), in kickoff order; the 60th's kickoff UTC date, every game
    assumed to get a three-way close. Fewer than 60 stored: no date, the count printed (law 4).
Then step (c)'s date as 156 item 1 rules it: the earliest of the four, the other three named.

The DB is the one DATABASE_URL names (else ./data/sports.db). A path with no file is refused before any import that
could open it: the receipt never creates a database. One session, rolled back; nothing written.

Run:  python3 scripts/leagues_close_receipt.py [--season 2026/27] [--declared 2026-11-06]
Paste the whole output on #322.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SEASON = "2026/27"
DECLARED = date(2026, 11, 6)                 # 155 item 4(b): the declaration; 156 item 1: "on or after 2026-11-06"


def db_file() -> Path:
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


def come_line(code: str, c: dict) -> str:
    from src.walters.paper import UNPRICED
    causes = " · ".join(f"{text.split(' {k}')[0]} {c[key]}" for key, text in UNPRICED if c[key])
    return (f"  - {code} · to come {c['n']} · a capture forming a close now {c['close']}"
            + (f" · no close: {causes}" if causes else ""))


def lines(res: dict, season: str, declared: date) -> list[str]:
    from src.walters.paper import WINDOW_GAMES, close_record_line
    L = [f"LEAGUES CLOSE RECEIPT (ARCHITECT 2026-10-23, addendum 155 item 4(a); 156 item 1; #322) · read-only · "
         f"season {season} · declaration {declared}"]
    dated = []
    for code, r in res.items():
        if not r["games"]:
            L.append(f"- {code} · no stored game of {season}; seasons stored: {', '.join(r['seasons_stored']) or 'none'}")
            continue
        L.append(f"{code} {season} · stored games {r['games']} (cancelled / postponed / stale_orphan {r['not_games']})")
        L.append(close_record_line(code, r["record"]))
        L.append(come_line(code, r["to_come"]))
        if r["projected"]:
            p = r["projected"]
            dated.append((p["date"], code))
            L.append(f"  - {code} · the {WINDOW_GAMES}th fixture on or after {declared}: kickoff {p['date']} (UTC date; "
                     f"match {p['match_id']}) · {r['from_declared']} stored on or after {declared}")
        else:
            L.append(f"  - {code} · the {WINDOW_GAMES}th fixture on or after {declared}: not stored (only "
                     f"{r['from_declared']} on or after it); no date")
    if dated:
        dated.sort()
        first = dated[0]
        rest = ", ".join(f"{c} {d}" for d, c in dated[1:])
        missing = [c for c in res if c not in {c for _, c in dated}]
        L.append(f"STEP (c) (156 item 1): due {first[0]} ({first[1]}, the earliest)" + (f"; the others: {rest}" if rest
                                                                                         else "")
                 + (f"; no date for {', '.join(missing)} (fewer than {WINDOW_GAMES} stored)" if missing else ""))
    else:
        L.append(f"STEP (c) (156 item 1): no date (no league stores {WINDOW_GAMES} fixtures on or after {declared})")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", default=SEASON, help="the season as the DB stores it (default 2026/27)")
    ap.add_argument("--declared", default=DECLARED.isoformat(), help="the declaration date (default 2026-11-06)")
    a = ap.parse_args(argv)
    f = db_file()
    if not f.is_file():
        raise SystemExit(f"no database at {f}: the receipt never creates one")
    declared = date.fromisoformat(a.declared)
    from src.walters.paper import LEAGUES, leagues_season
    for ln in lines(leagues_season(LEAGUES, a.season, declared), a.season, declared):
        print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
