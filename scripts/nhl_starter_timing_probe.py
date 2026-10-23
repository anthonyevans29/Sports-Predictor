"""
NHL STARTER TIMING PROBE (ARCHITECT 2026-10-23, addendum 157 item 2(b); lane nhl, #105) — read-only.

Verbatim: "(b) Starter information, a Step-A-style timing probe of the NHL API (api-web.nhle.com, the source we already
read): on three game days, which endpoint names each side's starting goalie and at what poll time (T-120, T-90, T-60,
T-45, T-30, T-15, puck drop), stamped by OUR poll time; plus whether any stored field reflects pre-game knowledge for
past games (expected: none; the boxscore starter is post hoc). The 2026-09-26 verdict stands for the hockey provider
(api-sports: no lineups). An external projected-starters source is a sourcing decision for the operator (terms,
ownership), not a probe."

  S   the schedule   one GET /v1/schedule/<date> (the call nhl_goalies.sync makes; parsed by its schedule_games): the
                     games whose scheduled start (startTimeUTC) falls in [<date> 10:00Z, <date>+1 10:00Z), the NHL
                     day in North America, of game type 2 or 3. The payload is a week; the other days are not polled.
  P   the polls      per game, at the scheduled start minus 120, 90, 60, 45, 30 and 15 minutes and at puck drop (the
                     scheduled start, "T-0"), in time order: GET /v1/gamecenter/<id>/<endpoint> for each endpoint of
                     ENDPOINTS (boxscore: the one nhl_goalies reads; landing and right-rail: the game's other pages on
                     the same API). Each request is stamped with OUR clock at its answer (UTC); the API's answers carry
                     no publication time for a starter. A poll more than 5 minutes past its time when its turn comes
                     (the probe started late, the laptop slept) is printed as missed and never counted under its label.
  R   the reading    per request: the HTTP status, the gameState the answer carries (a top-level "gameState" key, as
                     written), and per side every goalie the answer names: each dict under a path segment naming
                     "goalie" that carries an integer playerId (or id), sided by a "home"/"away" segment of its path
                     (nhl_goalies' sidedness rule). A side's STARTER is NAMED when exactly one goalie of that side
                     carries a key naming starter/starting whose value is True (nhl_goalies.STARTER, the flag the
                     boxscore ingest stores), or when the only goalie of that side sits under a path segment naming
                     starter/starting/probable/projected. Anything else is "listed, no starter named" or "none".
  Summary            per game and endpoint: the first poll at which both sides' starters were named, and the poll
                     before it answered without them; per endpoint, the games counted by that first poll; then the
                     requests made by status. The keys behind every naming are printed once (law 1).

--stored (no network): the stored fields, read-only. nhl_goalie_appearances (the stored starters): its rows per season
by the game id's first four digits, is_starter True / False / NULL, and how many rows were captured before their game's
start (captured_at < game_start): a row captured before the game is the only stored field that could reflect pre-game
knowledge. Opens the DB mode=ro (a copy that refuses it: the plain path with PRAGMA query_only = ON, #421); never
creates one.

It never stops on an error: a failed request is printed and counted. It writes nothing; --save DIR keeps every
answer whole (<game id>_<endpoint>_<label>.json; refused under data/).

Run:  python3 scripts/nhl_starter_timing_probe.py [--date YYYY-MM-DD] [--plan] [--save DIR]
      python3 scripts/nhl_starter_timing_probe.py --stored [--db PATH]
--date is the NHL day (default: today in UTC). --plan prints the games and their poll times after the one schedule
call and polls nothing. Start it before the first poll you want (T-120 of the day's first game); it exits after its
last poll (Ctrl-C prints the summary so far). Run on three game days; paste each whole output on #105.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OFFSETS = (120, 90, 60, 45, 30, 15, 0)        # minutes before the scheduled start; 0 = puck drop (the ruling's polls)
ENDPOINTS = ("boxscore", "landing", "right-rail")
LATE_LIMIT = timedelta(minutes=5)
NAP = 30.0
DAY_CUT_UTC = 10                               # the NHL day: [date 10:00Z, date+1 10:00Z)
GAME_TYPES = (2, 3)
GOALIE_SEG = re.compile(r"goalie", re.I)
STARTER_KEY = re.compile(r"starter|starting", re.I)
STARTER_SEG = re.compile(r"starter|starting|probable|projected", re.I)
MISSED = "missed"


def label(offset: int) -> str:
    return "T-0 (puck drop)" if offset == 0 else f"T-{offset}"


def day_games(payload, day: date) -> list[dict]:
    """The schedule's games of the NHL day, types 2/3, in start order (nhl_goalies.schedule_games parses)."""
    from src.ingestion.nhl_goalies import schedule_games
    lo = datetime.combine(day, datetime.min.time()) + timedelta(hours=DAY_CUT_UTC)
    hi = lo + timedelta(days=1)
    out = [g for g in schedule_games(payload) if g["start"] is not None and lo <= g["start"] < hi
           and (g["game_type"] in GAME_TYPES)]
    return sorted(out, key=lambda g: (g["start"], g["id"]))


def plan(games: list[dict]) -> list[tuple[datetime, dict, int]]:
    """(poll time UTC-naive, game, offset), in time order."""
    return sorted(((g["start"] - timedelta(minutes=o), g, o) for g in games for o in OFFSETS),
                  key=lambda t: (t[0], t[1]["id"], -t[2]))


def _segs(path: str) -> list[str]:
    return [s for s in re.split(r"[.\[\]]", path) if s and not s.isdigit()]


def _walk(obj, path=""):
    from src.ingestion.nhl_goalies import walk
    yield from walk(obj, path)


def goalies_named(payload) -> dict:
    """{side: {"listed": {id: [paths]}, "flagged": {id: key}, "under_starter_seg": {id}}} and the sides' starters."""
    sides = {s: {"listed": {}, "flagged": {}, "under_starter_seg": set()} for s in ("home", "away")}
    for path, d in _walk(payload or {}):
        segs = _segs(path)
        if not any(GOALIE_SEG.search(s) for s in segs):
            continue
        gid = d.get("playerId") if isinstance(d.get("playerId"), int) else d.get("id")
        if not isinstance(gid, int) or isinstance(gid, bool):
            continue
        low = [s.lower() for s in segs]
        side = ("home" if any(s.startswith("home") for s in low) else
                "away" if any(s.startswith("away") for s in low) else None)
        if side is None:
            continue
        sides[side]["listed"].setdefault(gid, []).append(path)
        fk = next((k for k in d if STARTER_KEY.search(k) and d[k] is True), None)
        if fk:
            sides[side]["flagged"][gid] = fk
        if any(STARTER_SEG.search(s) for s in segs):
            sides[side]["under_starter_seg"].add(gid)
    for s in sides.values():
        if len(s["flagged"]) == 1:
            s["starter"], s["how"] = next(iter(s["flagged"])), f"flag {next(iter(s['flagged'].values()))}=True"
        elif len(s["under_starter_seg"]) == 1 and len(s["listed"]) == 1:
            s["starter"], s["how"] = next(iter(s["under_starter_seg"])), "the only goalie under a starter path"
        else:
            s["starter"], s["how"] = None, ("listed, no starter named" if s["listed"] else "none")
    return sides


def read(fetch, game: dict, endpoint: str, clock) -> dict:
    from src.ingestion.nhl_goalies import BASE
    code, payload = fetch(f"{BASE}/v1/gamecenter/{game['id']}/{endpoint}")
    at = clock()
    sides = goalies_named(payload) if code == 200 else None
    return {"endpoint": endpoint, "status": code, "at": at, "payload": payload,
            "state": payload.get("gameState") if isinstance(payload, dict) else None, "sides": sides,
            "both": bool(sides and sides["home"]["starter"] and sides["away"]["starter"])}


def poll_line(game: dict, off: int, r: dict) -> str:
    head = f"  {game['id']} {label(off)} · {r['endpoint']} · HTTP {r['status']} · polled {r['at']:%H:%M:%S}Z"
    if r["sides"] is None:
        return head + " · not read"
    parts = []
    for side in ("away", "home"):
        s = r["sides"][side]
        if s["starter"]:
            parts.append(f"{side} starter {s['starter']} ({s['how']})")
        else:
            parts.append(f"{side} {s['how']}" + (f" ({len(s['listed'])} listed)" if s["listed"] else ""))
    return head + f" · gameState {r['state']} · " + " · ".join(parts)


def summarize(games: list[dict], log: list[tuple[dict, int, dict | None]]) -> list[str]:
    """The first poll per game and endpoint at which both starters were named."""
    L = ["SUMMARY · per game and endpoint, the first poll naming both starters (the poll before it answered without)"]
    by_ep: dict[str, Counter] = {ep: Counter() for ep in ENDPOINTS}
    keys: set = set()
    for g in games:
        for ep in ENDPOINTS:
            rows = [(off, r) for gg, off, r in log if gg["id"] == g["id"] and (r is None or r["endpoint"] == ep)]
            first, before = None, None
            for off, r in sorted(rows, key=lambda t: -t[0]):
                if r is None:
                    continue
                if r["both"]:
                    first = off
                    keys |= {r["sides"][s]["how"] for s in ("home", "away")}
                    break
                if r["status"] == 200:
                    before = off
            missed = sum(1 for _, r in rows if r is None) // max(1, len(ENDPOINTS))
            res = (f"first at {label(first)}" + (f" (answered without at {label(before)})" if before is not None
                                                  else " (no earlier poll answered without)")
                   if first is not None else "never named")
            by_ep[ep][label(first) if first is not None else "never named"] += 1
            L.append(f"  {g['id']} {'/'.join(g['away_names'][:1])} @ {'/'.join(g['home_names'][:1])} · {ep}: {res}"
                     + (f" · {missed} poll(s) missed" if missed else ""))
    for ep in ENDPOINTS:
        L.append(f"  {ep}: " + " · ".join(f"{k} {v}" for k, v in sorted(by_ep[ep].items())))
    L.append("  keys behind each naming: " + (" · ".join(sorted(keys)) or "none"))
    return L


def run(day: date, fetch, now, sleep, save: Path | None = None, plan_only: bool = False, out=print) -> int:
    from src.ingestion.nhl_goalies import BASE
    code, payload = fetch(f"{BASE}/v1/schedule/{day.isoformat()}")
    games = day_games(payload, day)
    out(f"NHL STARTER TIMING PROBE (ARCHITECT 2026-10-23, addendum 157 item 2(b); #105) · read-only · day {day} · "
        f"schedule HTTP {code} · {len(games)} game(s) of types 2/3 starting in [{day} {DAY_CUT_UTC:02d}:00Z, +1 day)")
    for g in games:
        out(f"  game {g['id']} type {g['game_type']} · {'/'.join(g['away_names'][:1])} @ "
            f"{'/'.join(g['home_names'][:1])} · scheduled {g['start']:%Y-%m-%d %H:%M}Z")
    tasks = plan(games)
    if plan_only or not tasks:
        for t, g, o in tasks:
            out(f"  plan {t:%H:%M}Z · {g['id']} {label(o)} · {', '.join(ENDPOINTS)}")
        return 0
    calls: Counter = Counter()
    log: list = []
    try:
        for t, g, o in tasks:
            while now() < t:
                sleep(min(NAP, max(0.0, (t - now()).total_seconds())))
            if now() - t > LATE_LIMIT:
                out(f"  {g['id']} {label(o)} · MISSED (its turn came at {now():%H:%M:%S}Z, {t:%H:%M}Z + 5 min)")
                log += [(g, o, None)] * len(ENDPOINTS)
                continue
            for ep in ENDPOINTS:
                r = read(fetch, g, ep, now)
                calls[f"{ep} HTTP {r['status']}"] += 1
                out(poll_line(g, o, r))
                if save is not None and r["payload"] is not None:
                    (save / f"{g['id']}_{ep}_{label(o).split()[0]}.json").write_text(json.dumps(r["payload"]))
                r["payload"] = None
                log.append((g, o, r))
    except KeyboardInterrupt:
        out("  interrupted: the summary so far")
    for ln in summarize(games, log):
        out(ln)
    out("  requests: schedule 1 · " + " · ".join(f"{k} {v}" for k, v in sorted(calls.items())))
    return 0


def stored(db: Path, out=print) -> int:
    if not db.is_file():
        raise SystemExit(f"no database at {db}: the probe never creates one")
    try:
        con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        con.execute("SELECT 1 FROM nhl_goalie_appearances LIMIT 1")
        form = "mode=ro URI"
    except sqlite3.OperationalError:
        con = sqlite3.connect(str(db), timeout=60)
        con.execute("PRAGMA query_only = ON")
        con.execute("SELECT 1 FROM nhl_goalie_appearances LIMIT 1")
        form = "plain path with PRAGMA query_only = ON (mode=ro refused)"
    tally: dict = {}
    for gid, start, cap, st in con.execute("SELECT nhl_game_id, game_start, captured_at, is_starter "
                                           "FROM nhl_goalie_appearances"):
        season = gid // 1_000_000 if isinstance(gid, int) and gid >= 1_000_000_000 else None
        t = tally.setdefault(season, Counter())
        t["rows"] += 1
        t[{1: "starter True", 0: "starter False", None: "starter NULL"}.get(st, "starter NULL")] += 1
        try:
            before = datetime.fromisoformat(str(cap)) < datetime.fromisoformat(str(start))
        except ValueError:
            t["capture or start unreadable"] += 1
            continue
        t["captured before the game's start" if before else "captured at or after the start"] += 1
    con.close()
    out(f"NHL STARTER TIMING PROBE --stored · nhl_goalie_appearances, read-only ({form}) · the stored starters")
    for season in sorted(tally, key=lambda s: (s is None, s)):
        t = tally[season]
        name = f"{season}-{(season + 1) % 100:02d}" if season else "game id not ten digits"
        out(f"  {name}: rows {t['rows']} · " + " · ".join(f"{k} {v}" for k, v in sorted(t.items()) if k != "rows"))
    pre = sum(t["captured before the game's start"] for t in tally.values())
    out(f"  stored fields reflecting pre-game knowledge: {pre} row(s) captured before their game's start "
        f"(of {sum(t['rows'] for t in tally.values())}); the boxscore starter flag is read after the game (post hoc)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", help="the NHL day, YYYY-MM-DD (default: today in UTC)")
    ap.add_argument("--plan", action="store_true", help="print the games and poll times; poll nothing")
    ap.add_argument("--save", help="keep every answer whole in DIR (never under data/)")
    ap.add_argument("--stored", action="store_true", help="the stored fields only (no network)")
    ap.add_argument("--db", help="SQLite file for --stored (default: DATABASE_URL, else ./data/sports.db)")
    a = ap.parse_args(argv)
    if a.stored:
        here = Path(__file__).resolve().parent
        sys.path.insert(0, str(here))
        from nhl_gsax_feasibility import db_path
        return stored(db_path(a.db))
    day = date.fromisoformat(a.date) if a.date else datetime.now(timezone.utc).date()
    save = None
    if a.save:
        save = Path(a.save).resolve()
        if "data" in save.parts:
            raise SystemExit(f"--save {a.save}: refused, never under data/")
        save.mkdir(parents=True, exist_ok=True)
    from src.ingestion.nhl_goalies import http_json
    return run(day, http_json, lambda: datetime.now(timezone.utc).replace(tzinfo=None), time.sleep, save, a.plan)


if __name__ == "__main__":
    sys.exit(main())
