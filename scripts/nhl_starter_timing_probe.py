"""
NHL STARTER TIMING PROBE (ARCHITECT 2026-10-23, addendum 157 items 2(b) and 7; lane nhl, #105) — read-only.

Item 2(b), verbatim: "(b) Starter information, a Step-A-style timing probe of the NHL API (api-web.nhle.com, the source
we already read): on three game days, which endpoint names each side's starting goalie and at what poll time (T-120,
T-90, T-60, T-45, T-30, T-15, puck drop), stamped by OUR poll time; plus whether any stored field reflects pre-game
knowledge for past games (expected: none; the boxscore starter is post hoc). The 2026-09-26 verdict stands for the
hockey provider (api-sports: no lineups). An external projected-starters source is a sourcing decision for the operator
(terms, ownership), not a probe."

Item 7, verbatim: "THE TIMING RECEIPT'S SUCCESS CONDITION (157 item 2(b), sharpened). The probe reports the
DISTRIBUTION, not the earliest success: per game and poll, whether both sides had a unique team-linked goalie identity;
what the endpoint asserted and the poll time we first saw it; the share of games with usable information AT the
declared cutoff (T-35, the closing's); and the counts of missing, conflicting, withdrawn or changed names before puck
drop. The eventual starter is read only to check reliability, never to fill a gap in the pregame record. The legacy
scripts/nhl_api_probe.py green condition (a starter flag found, or the MoneyPuck fallback) does not apply."

  S   the schedule   one GET /v1/schedule/<date> (the call nhl_goalies.sync makes; parsed by its schedule_games): the
                     games whose scheduled start (startTimeUTC) falls in [<date> 10:00Z, <date>+1 10:00Z), the NHL
                     day in North America, of game type 2 or 3. The payload is a week; the other days are not polled.
  P   the polls      per game, at the scheduled start minus 120, 90, 60, 45, 35, 30 and 15 minutes and at puck drop
                     (the scheduled start, "T-0"), in time order: GET /v1/gamecenter/<id>/<endpoint> for each endpoint
                     of ENDPOINTS (boxscore: the page nhl_goalies reads; landing and right-rail: the game's other pages
                     on the same API). T-35 is the declared cutoff (item 7: "T-35, the closing's"), polled as its own
                     label beside the ruled ones. Each request is stamped with OUR clock at its answer (UTC); the
                     API's answers carry no publication time for a starter. A poll more than 5 minutes past its time
                     when its turn comes (the probe started late, the laptop slept) is printed as missed and never
                     counted under its label.
  E   the eventual   one more boxscore read per game at puck drop + 20 minutes ("T+20"), for its starter flags: the
      starter        eventual starter. Read only to check the pregame record's reliability (item 7); it never fills a
                     gap in it, and it is never counted in the pregame lines.
  R   the reading    per request and side, what the endpoint ASSERTED: "flag" (a goalie dict under a path segment
                     naming "goalie", sided by a "home"/"away" segment, carrying a key naming starter/starting whose
                     value is True: nhl_goalies.STARTER, the flag the boxscore ingest stores), "path" (the side's only
                     goalie, under a path segment naming starter/starting/probable/projected), "listed" (goalies named,
                     none asserted a starter: season leaders, a roster), or "none". A goalie is team-linked by its
                     path's home/away segment, the side nhl_goalies' boxscore ingest reads.
                     Per poll and side, across the endpoints: the IDENTITY is the set of goalie ids asserted as
                     starter (flag or path). UNIQUE: exactly one id; CONFLICTING: more than one (two endpoints, or one
                     endpoint flagging two); MISSING: none.
  Summary            per game: the poll at which each side's identity was first seen and which endpoint asserted it
                     (our poll time); USABLE AT THE CUTOFF: both sides unique at the last answered poll at or before
                     T-35; and the counts over the pregame polls before puck drop (T-120 .. T-15), per side: missing
                     (an answered poll with no identity), conflicting, withdrawn (an identity seen, then none at a later
                     answered poll), changed (a unique identity different from the side's previous one). Then, across
                     the day: the share of games usable at the cutoff, the first-seen polls by endpoint, the totals,
                     and the reliability check (the identity at the cutoff against the eventual starter: agrees /
                     differs / no identity at the cutoff / eventual starter unread). The requests made by status and
                     the keys behind every assertion close it (law 1).

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
call and polls nothing. Start it before the first poll you want (T-120 of the day's first game); it exits after the
day's last T+20 read (Ctrl-C prints the summary so far). Run on three game days; paste each whole output on #105.
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

OFFSETS = (120, 90, 60, 45, 35, 30, 15, 0)    # minutes before the scheduled start; 0 = puck drop; 35 = the cutoff
CUTOFF = 35                                    # item 7: "the declared cutoff (T-35, the closing's)"
EVENTUAL = -20                                 # puck drop + 20 minutes: the eventual starter (reliability only)
ENDPOINTS = ("boxscore", "landing", "right-rail")
LATE_LIMIT = timedelta(minutes=5)
NAP = 30.0
DAY_CUT_UTC = 10                               # the NHL day: [date 10:00Z, date+1 10:00Z)
GAME_TYPES = (2, 3)
GOALIE_SEG = re.compile(r"goalie", re.I)
STARTER_KEY = re.compile(r"starter|starting", re.I)
STARTER_SEG = re.compile(r"starter|starting|probable|projected", re.I)
SIDES = ("away", "home")


def label(offset: int) -> str:
    if offset == EVENTUAL:
        return "T+20 (eventual starter)"
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
    """(poll time UTC-naive, game, offset), in time order; the T+20 eventual read last per game."""
    return sorted(((g["start"] - timedelta(minutes=o), g, o) for g in games for o in (*OFFSETS, EVENTUAL)),
                  key=lambda t: (t[0], t[1]["id"], -t[2]))


def _segs(path: str) -> list[str]:
    return [s for s in re.split(r"[.\[\]]", path) if s and not s.isdigit()]


def asserted(payload) -> dict:
    """{side: {"kind": flag|path|listed|none, "ids": [asserted starter ids], "listed": n, "keys": {how}}}."""
    from src.ingestion.nhl_goalies import walk
    sides = {s: {"listed": {}, "flagged": {}, "under_seg": set()} for s in SIDES}
    for path, d in walk(payload or {}):
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
        sides[side]["listed"].setdefault(gid, path)
        fk = next((k for k in d if STARTER_KEY.search(k) and d[k] is True), None)
        if fk:
            sides[side]["flagged"][gid] = f"flag {fk}=True"
        if any(STARTER_SEG.search(s) for s in segs):
            sides[side]["under_seg"].add(gid)
    out = {}
    for side, s in sides.items():
        if s["flagged"]:
            out[side] = {"kind": "flag", "ids": sorted(s["flagged"]), "listed": len(s["listed"]),
                         "keys": set(s["flagged"].values())}
        elif len(s["under_seg"]) == 1 and len(s["listed"]) == 1:
            out[side] = {"kind": "path", "ids": sorted(s["under_seg"]), "listed": 1,
                         "keys": {"the side's only goalie under a starter/probable/projected path"}}
        else:
            out[side] = {"kind": "listed" if s["listed"] else "none", "ids": [], "listed": len(s["listed"]),
                         "keys": set()}
    return out


def read(fetch, game: dict, endpoint: str, clock) -> dict:
    from src.ingestion.nhl_goalies import BASE
    code, payload = fetch(f"{BASE}/v1/gamecenter/{game['id']}/{endpoint}")
    at = clock()
    return {"endpoint": endpoint, "status": code, "at": at, "payload": payload,
            "state": payload.get("gameState") if isinstance(payload, dict) else None,
            "sides": asserted(payload) if code == 200 else None}


def identity(reads: list[dict]) -> dict:
    """Per side, across one poll's answered reads: {"ids": the asserted starter ids, "by": {endpoint: kind}}."""
    out = {}
    for side in SIDES:
        ids, by = set(), {}
        for r in reads:
            if r["sides"] is None:
                continue
            a = r["sides"][side]
            by[r["endpoint"]] = a["kind"]
            ids |= set(a["ids"])
        out[side] = {"ids": sorted(ids), "by": by}
    return out


def _state(ids: list) -> str:
    return "unique" if len(ids) == 1 else ("conflicting" if ids else "missing")


def poll_line(game: dict, off: int, reads: list[dict], ident: dict) -> str:
    stamps = " · ".join(f"{r['endpoint']} HTTP {r['status']} {r['at']:%H:%M:%S}Z" for r in reads)
    state = next((r["state"] for r in reads if r["state"] is not None), None)
    sides = []
    for side in SIDES:
        i = ident[side]
        asserted_by = ", ".join(f"{ep} {k}" for ep, k in i["by"].items())
        sides.append(f"{side} {_state(i['ids'])}" + (f" {i['ids']}" if i["ids"] else "") + f" ({asserted_by or 'unread'})")
    both = all(_state(ident[s]["ids"]) == "unique" for s in SIDES)
    return (f"  {game['id']} {label(off)} · {stamps} · gameState {state} · both unique {'yes' if both else 'no'} · "
            + " · ".join(sides))


def game_summary(game: dict, polls: dict, eventual: dict | None) -> dict:
    """polls: {offset: identity or None (missed/unanswered)}; eventual: the T+20 identity or None."""
    pre = [o for o in OFFSETS if o > 0]                  # before puck drop: T-120 .. T-15
    out = {"first": {}, "counts": {s: Counter() for s in SIDES}, "cutoff": None, "cutoff_label": None}
    for side in SIDES:
        last_seen, last_unique = None, None
        for o in sorted(pre, reverse=True):
            i = polls.get(o)
            if i is None:
                continue
            ids = i[side]["ids"]
            st = _state(ids)
            if ids and side not in out["first"]:
                out["first"][side] = (o, sorted(ep for ep, k in i[side]["by"].items() if k in ("flag", "path")), ids)
            if st == "missing":
                out["counts"][side]["missing"] += 1
                if last_seen:
                    out["counts"][side]["withdrawn"] += 1
                    last_seen = None
            else:
                last_seen = ids
                if st == "conflicting":
                    out["counts"][side]["conflicting"] += 1
                elif last_unique is not None and ids != last_unique:
                    out["counts"][side]["changed"] += 1
                if st == "unique":
                    last_unique = ids
    at = [o for o in OFFSETS if o >= CUTOFF and polls.get(o) is not None]
    if at:
        o = min(at)                                       # the last answered poll at or before the cutoff
        out["cutoff_label"] = label(o)
        out["cutoff"] = {s: polls[o][s]["ids"] for s in SIDES}
    usable = out["cutoff"] is not None and all(len(out["cutoff"][s]) == 1 for s in SIDES)
    out["usable"] = usable
    rel = {}
    for side in SIDES:
        ev = eventual[side]["ids"] if eventual else []
        cut = out["cutoff"][side] if out["cutoff"] else []
        rel[side] = ("eventual starter unread" if len(ev) != 1 else "no identity at the cutoff" if len(cut) != 1
                     else "agrees" if cut == ev else "differs")
    out["reliability"] = rel
    return out


def summary_lines(games: list[dict], res: dict) -> list[str]:
    L = ["SUMMARY (item 7: the distribution, not the earliest success)"]
    usable = 0
    first_by = Counter()
    totals = Counter()
    rel = Counter()
    for g in games:
        s = res[g["id"]]
        usable += s["usable"]
        parts = []
        for side in SIDES:
            f = s["first"].get(side)
            parts.append(f"{side} first seen " + (f"{label(f[0])} by {', '.join(f[1]) or 'none'} {f[2]}" if f
                                                  else "never before puck drop"))
            if f:
                for ep in f[1]:
                    first_by[(ep, label(f[0]))] += 1
            totals.update(s["counts"][side])
            rel[s["reliability"][side]] += 1
        cnt = " · ".join(f"{side} " + (", ".join(f"{k} {v}" for k, v in sorted(s["counts"][side].items())) or "none")
                         for side in SIDES)
        L.append(f"  {g['id']} {'/'.join(g['away_names'][:1])} @ {'/'.join(g['home_names'][:1])} · "
                 + " · ".join(parts)
                 + f" · at the cutoff ({s['cutoff_label'] or 'no answered poll at or before T-35'}): "
                 + ("USABLE" if s["usable"] else "not usable") + f" · before puck drop: {cnt}"
                 + " · reliability: " + ", ".join(f"{side} {s['reliability'][side]}" for side in SIDES))
    n = len(games)
    L.append(f"  usable at the cutoff (T-35): {usable} of {n} games" + (f" ({usable / n:.0%})" if n else ""))
    L.append("  first seen, by endpoint and poll (a side counts once per asserting endpoint): "
             + (" · ".join(f"{ep} {lab} {v}" for (ep, lab), v in sorted(first_by.items())) or "none"))
    L.append("  before puck drop, side-polls: " + " · ".join(f"{k} {totals.get(k, 0)}"
                                                         for k in ("missing", "conflicting", "withdrawn", "changed")))
    L.append("  reliability (the identity at the cutoff against the eventual starter; never fills a gap), sides: "
             + (" · ".join(f"{k} {v}" for k, v in sorted(rel.items())) or "none"))
    return L


def run(day: date, fetch, now, sleep, save: Path | None = None, plan_only: bool = False, out=print) -> int:
    from src.ingestion.nhl_goalies import BASE
    code, payload = fetch(f"{BASE}/v1/schedule/{day.isoformat()}")
    games = day_games(payload, day)
    out(f"NHL STARTER TIMING PROBE (ARCHITECT 2026-10-23, addendum 157 items 2(b) and 7; #105) · read-only · day {day} · "
        f"schedule HTTP {code} · {len(games)} game(s) of types 2/3 starting in [{day} {DAY_CUT_UTC:02d}:00Z, +1 day) · "
        f"cutoff T-{CUTOFF}")
    for g in games:
        out(f"  game {g['id']} type {g['game_type']} · {'/'.join(g['away_names'][:1])} @ "
            f"{'/'.join(g['home_names'][:1])} · scheduled {g['start']:%Y-%m-%d %H:%M}Z")
    tasks = plan(games)
    if plan_only or not tasks:
        for t, g, o in tasks:
            eps = "boxscore" if o == EVENTUAL else ", ".join(ENDPOINTS)
            out(f"  plan {t:%H:%M}Z · {g['id']} {label(o)} · {eps}")
        return 0
    calls: Counter = Counter()
    keys: set = set()
    polls: dict = {g["id"]: {} for g in games}
    eventual: dict = {}
    try:
        for t, g, o in tasks:
            while now() < t:
                sleep(min(NAP, max(0.0, (t - now()).total_seconds())))
            if now() - t > LATE_LIMIT:
                out(f"  {g['id']} {label(o)} · MISSED (its turn came at {now():%H:%M:%S}Z, {t:%H:%M}Z + 5 min)")
                continue
            reads = [read(fetch, g, ep, now) for ep in (("boxscore",) if o == EVENTUAL else ENDPOINTS)]
            for r in reads:
                calls[f"{r['endpoint']} HTTP {r['status']}"] += 1
                if r["sides"]:
                    for a in r["sides"].values():
                        keys |= a["keys"]
                if save is not None and r["payload"] is not None:
                    (save / f"{g['id']}_{r['endpoint']}_{label(o).split()[0]}.json").write_text(json.dumps(r["payload"]))
                r["payload"] = None
            ident = identity(reads) if any(r["sides"] is not None for r in reads) else None
            if o == EVENTUAL:
                eventual[g["id"]] = ident
                if ident:
                    out(f"  {g['id']} {label(o)} · reliability only: "
                        + " · ".join(f"{s} {ident[s]['ids'] or 'none'}" for s in SIDES))
                continue
            polls[g["id"]][o] = ident
            if ident is None:
                out(f"  {g['id']} {label(o)} · " + " · ".join(f"{r['endpoint']} HTTP {r['status']}" for r in reads)
                    + " · not answered")
            else:
                out(poll_line(g, o, reads, ident))
    except KeyboardInterrupt:
        out("  interrupted: the summary so far")
    res = {g["id"]: game_summary(g, polls[g["id"]], eventual.get(g["id"])) for g in games}
    for ln in summary_lines(games, res):
        out(ln)
    out("  requests: schedule 1 · " + " · ".join(f"{k} {v}" for k, v in sorted(calls.items())))
    out("  keys behind each assertion: " + (" · ".join(sorted(keys)) or "none"))
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
        sys.path.insert(0, str(Path(__file__).resolve().parent))
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
