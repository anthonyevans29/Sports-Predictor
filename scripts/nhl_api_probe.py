"""
NHL-API-PROBE (architect lane, 2026-09-30) — read-only, zero wiring.

The question: can the NHL's own public API (api-web.nhle.com) feed what a
goalie-aware NHL candidate needs? That is the H2 reopening condition: an
EXTERNAL goalie/lineup source. api-sports' hockey product has no goalie data
(H2 probe NEGATIVE, 2026-09-26). The fallback source is MoneyPuck's
projected-starters CSV.

Law 1: this container cannot reach either host (proxy CONNECT 403). So no
field name below is assumed. Games, goalie lists, starter flags and goalie
stats are FOUND by searching the actual responses' key paths, and every
response's key paths are dumped into the receipt. Endpoint paths are
CANDIDATES: each is tried, and its HTTP answer is the receipt.

  N1 schedule       /v1/schedule/<date>: games with ids + start times
  N2 boxscore       /v1/gamecenter/<id>/boxscore on a finished game:
                    goalie lists, a starter flag, goalie stats (saves / shots)
  N3 roster         /v1/roster/<team>/current: a goalies list
  N4 pre-game       for every UPCOMING game in the next --hours: is a starter
                    already identified (boxscore / landing), and how many
                    minutes before puck drop? Run it several times on a game
                    day (T-6h, T-3h, T-90, T-30); --out appends each run as
                    JSON lines, so the lead time accumulates
  N5 history depth  a finished October game of 2023, 2024 and 2025: goalie
                    stats present?
  N6 host IP        run this same script ON THE HOST (python3 stdlib only):
                    N1's HTTP status there is the datacenter-IP receipt, and
                    the curl line printed at the end is the one-line
                    equivalent
  M1 MoneyPuck      candidate CSV URLs (--moneypuck-url overrides): HTTP
                    status, content type, the header row

VERDICT per need: FEEDABLE / NOT, from what was found. GREEN (starting goalie
feedable before puck drop + goalie game stats + depth 2023-2025) meets the
H2 reopening condition; a goalie-aware v5 would then go through the FROZEN
gate (the architect's call).

    python3 scripts/nhl_api_probe.py [--date YYYY-MM-DD] [--hours 24] [--out probe.jsonl]
                                     [--moneypuck-url URL ...]

Writes nothing unless --out is given (never under data/).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = "https://api-web.nhle.com"
MONEYPUCK_CANDIDATES = [
    # CANDIDATES (law 1): the probe reports what each one answers
    "https://moneypuck.com/moneypuck/tweets/goalies/goalies.csv",
    "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/goalies.csv",
    "https://moneypuck.com/goalies.htm",
]
GOALIE = re.compile(r"goalie", re.I)
STARTER = re.compile(r"starter|starting", re.I)
GSTATS = re.compile(r"save|shotsagainst|goalsagainst|savepct", re.I)
START = re.compile(r"start.*time|gamedate|datetime", re.I)
STATE = re.compile(r"gamestate|state", re.I)


def http_get(url: str, timeout: int = 20) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "sports-predictor-probe/1.0",
                                               "Accept": "application/json, text/csv, */*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "") if e.headers else "", b""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, f"ERROR {e}", b""


def key_paths(obj, prefix: str = "") -> list[str]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            out.append(p)
            out += key_paths(v, p)
    elif isinstance(obj, list) and obj:
        out += key_paths(obj[0], f"{prefix}[]")
    return out


def walk(obj, path=""):
    """Yield (path, dict) for every dict in the tree."""
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


def find_games(obj) -> list[dict]:
    """Game-like dicts: an integer id plus a start-time key (found, not assumed)."""
    games = []
    for p, d in walk(obj):
        if isinstance(d.get("id"), int) and any(START.search(k) for k in d):
            sk = next(k for k in d if START.search(k))
            st = next((k for k in d if STATE.search(k)), None)
            games.append({"id": d["id"], "start": d.get(sk), "start_key": sk,
                          "state": d.get(st) if st else None, "state_key": st, "path": p})
    return games


def goalie_read(obj) -> dict:
    """Goalie lists (a list under a key naming goalies), any starter flag set
    true inside them, and goalie stat keys present."""
    lists, starters, stat_keys = [], [], set()
    for p, d in walk(obj):
        for k, v in d.items():
            if GOALIE.search(k) and isinstance(v, list):
                lists.append(f"{p}.{k}" if p else k)
                for g in v:
                    if isinstance(g, dict):
                        stat_keys |= {kk for kk in g if GSTATS.search(kk)}
                        if any(STARTER.search(kk) and vv is True for kk, vv in g.items()):
                            starters.append({kk: g.get(kk) for kk in g
                                             if kk in ("playerId", "id", "name", "sweaterNumber")
                                             or STARTER.search(kk)})
            elif STARTER.search(k) and GOALIE.search(p) and v is True:
                starters.append({"path": f"{p}.{k}"})
    return {"goalie_lists": lists, "starter_flags_true": starters, "goalie_stat_keys": sorted(stat_keys)}


def parse_time(v) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def get_json(fetch, path: str) -> tuple[int, dict | None, str]:
    code, ctype, body = fetch(f"{BASE}{path}")
    try:
        return code, json.loads(body) if body else None, ctype
    except ValueError:
        return code, None, ctype


def run(fetch, today: date, now: datetime, hours: int = 24, moneypuck: list[str] | None = None) -> dict:
    rec: dict = {"probed_at": now.isoformat(), "base": BASE, "needs": {}}
    # N1 schedule: today and the next day (upcoming), and a week back (finished)
    sched, all_games = {}, []
    for d in (today - timedelta(days=7), today, today + timedelta(days=1)):
        code, doc, ctype = get_json(fetch, f"/v1/schedule/{d.isoformat()}")
        games = find_games(doc) if doc else []
        sched[d.isoformat()] = {"http": code, "content_type": ctype, "games_found": len(games),
                                "key_paths": key_paths(doc)[:60] if doc else []}
        all_games += games
    uniq = {g["id"]: g for g in all_games}
    rec["N1_schedule"] = sched
    rec["needs"]["schedule"] = bool(uniq)
    # N2 boxscore on a finished game (state read from the found state key)
    fin = [g for g in uniq.values() if str(g["state"] or "").upper() in ("OFF", "FINAL")]
    box = {"game": None}
    if fin:
        g = fin[-1]
        code, doc, _ = get_json(fetch, f"/v1/gamecenter/{g['id']}/boxscore")
        box = {"game": g["id"], "http": code, **(goalie_read(doc) if doc else {}),
               "key_paths": key_paths(doc)[:80] if doc else []}
    rec["N2_boxscore"] = box
    rec["needs"]["goalie_game_stats"] = bool(box.get("goalie_lists") and box.get("goalie_stat_keys"))
    rec["needs"]["starter_flag_postgame"] = bool(box.get("starter_flags_true"))
    # N3 roster: a team abbreviation found in the schedule response
    abbrev = None
    for d in (today, today - timedelta(days=7)):
        code, doc, _ = get_json(fetch, f"/v1/schedule/{d.isoformat()}")
        for _, dd in walk(doc or {}):
            if isinstance(dd.get("abbrev"), str):
                abbrev = dd["abbrev"]
                break
        if abbrev:
            break
    ros = {"team": abbrev}
    if abbrev:
        code, doc, _ = get_json(fetch, f"/v1/roster/{abbrev}/current")
        ros.update({"http": code, "goalie_keys": [k for k in (doc or {}) if GOALIE.search(k)],
                    "n_goalies": sum(len(v) for k, v in (doc or {}).items() if GOALIE.search(k) and isinstance(v, list))})
    rec["N3_roster"] = ros
    rec["needs"]["roster_goalies"] = bool(ros.get("n_goalies"))
    # N4 pre-game: every upcoming game inside --hours
    pre = []
    for g in uniq.values():
        t = parse_time(g["start"])
        if t is None or not (now <= t <= now + timedelta(hours=hours)):
            continue
        row = {"game": g["id"], "start": t.isoformat(), "minutes_to_puck_drop": round((t - now).total_seconds() / 60),
               "state": g["state"]}
        for ep in ("boxscore", "landing"):
            code, doc, _ = get_json(fetch, f"/v1/gamecenter/{g['id']}/{ep}")
            gr = goalie_read(doc) if doc else {}
            row[ep] = {"http": code, "goalie_lists": gr.get("goalie_lists", []),
                       "starter_identified": bool(gr.get("starter_flags_true")),
                       "starters": gr.get("starter_flags_true", [])}
        row["starter_identified"] = row["boxscore"]["starter_identified"] or row["landing"]["starter_identified"]
        pre.append(row)
    rec["N4_pregame"] = pre
    lead = [r["minutes_to_puck_drop"] for r in pre if r["starter_identified"]]
    rec["needs"]["starting_goalie_pregame"] = bool(lead)
    rec["N4_max_lead_minutes"] = max(lead) if lead else None
    # N5 history: the first finished game of an October week in 2023-2025
    hist = {}
    for yr in (2023, 2024, 2025):
        code, doc, _ = get_json(fetch, f"/v1/schedule/{yr}-10-20")
        gs = [g for g in (find_games(doc) if doc else []) if str(g["state"] or "").upper() in ("OFF", "FINAL")]
        h = {"schedule_http": code, "finished_found": len(gs)}
        if gs:
            c2, bd, _ = get_json(fetch, f"/v1/gamecenter/{gs[0]['id']}/boxscore")
            gr = goalie_read(bd) if bd else {}
            h.update({"game": gs[0]["id"], "boxscore_http": c2, "goalie_stat_keys": gr.get("goalie_stat_keys", []),
                      "starter_flag": bool(gr.get("starter_flags_true"))})
        hist[str(yr)] = h
    rec["N5_history"] = hist
    rec["needs"]["history_2023_2025"] = all(v.get("goalie_stat_keys") for v in hist.values())
    # M1 MoneyPuck fallback
    mp = []
    for url in moneypuck or MONEYPUCK_CANDIDATES:
        code, ctype, body = fetch(url)
        first = body.split(b"\n", 1)[0].decode("utf-8", "replace")[:300] if body else ""
        mp.append({"url": url, "http": code, "content_type": ctype, "header_or_first_line": first,
                   "looks_like_csv": "," in first and "<" not in first,
                   "goalie_columns": [c for c in first.split(",") if GOALIE.search(c) or STARTER.search(c)]})
    rec["M1_moneypuck"] = mp
    rec["needs"]["moneypuck_starters_csv"] = any(m["http"] == 200 and m["looks_like_csv"] and m["goalie_columns"]
                                                 for m in mp)
    n = rec["needs"]
    rec["verdict"] = {k: ("FEEDABLE" if v else "NOT") for k, v in n.items()}
    rec["h2_green"] = bool((n["starting_goalie_pregame"] or n["moneypuck_starters_csv"])
                           and n["goalie_game_stats"] and n["history_2023_2025"])
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NHL-API-PROBE: api-web.nhle.com goalie feed (read-only)")
    ap.add_argument("--date", default=None, help="the 'today' to probe (default: UTC today)")
    ap.add_argument("--hours", type=int, default=24, help="upcoming window for the pre-game read")
    ap.add_argument("--out", type=Path, default=None, help="append this run as one JSON line")
    ap.add_argument("--moneypuck-url", action="append", default=None)
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    today = date.fromisoformat(a.date) if a.date else now.date()
    r = run(http_get, today, now, a.hours, a.moneypuck_url)
    print(f"NHL-API-PROBE {r['probed_at']} · base {BASE}")
    for d, v in r["N1_schedule"].items():
        print(f"  N1 schedule {d}: HTTP {v['http']} · games found {v['games_found']} · {v['content_type']}")
    b = r["N2_boxscore"]
    print(f"  N2 boxscore game {b.get('game')}: HTTP {b.get('http')} · goalie lists {b.get('goalie_lists')} · "
          f"starter flags {len(b.get('starter_flags_true', []))} · goalie stat keys {b.get('goalie_stat_keys')}")
    ro = r["N3_roster"]
    print(f"  N3 roster {ro.get('team')}: HTTP {ro.get('http')} · goalie keys {ro.get('goalie_keys')} · "
          f"goalies {ro.get('n_goalies')}")
    for p in r["N4_pregame"]:
        print(f"  N4 pre-game game {p['game']} T-{p['minutes_to_puck_drop']}min state {p['state']}: starter "
              f"{'IDENTIFIED' if p['starter_identified'] else 'not yet'} · boxscore {p['boxscore']['http']} "
              f"{p['boxscore']['starters']} · landing {p['landing']['http']} {p['landing']['starters']}")
    print(f"  N4 max lead with a starter identified: {r['N4_max_lead_minutes']} min")
    for y, h in r["N5_history"].items():
        print(f"  N5 {y}: schedule HTTP {h['schedule_http']} · finished {h['finished_found']} · game {h.get('game')} "
              f"· goalie stat keys {h.get('goalie_stat_keys')} · starter flag {h.get('starter_flag')}")
    for m in r["M1_moneypuck"]:
        print(f"  M1 {m['url']}: HTTP {m['http']} · {m['content_type']} · goalie columns {m['goalie_columns']} · "
              f"first line {m['header_or_first_line'][:120]!r}")
    print("VERDICT:")
    for k, v in r["verdict"].items():
        print(f"  {v:8s} {k}")
    print(f"H2 REOPENING CONDITION: {'GREEN' if r['h2_green'] else 'NOT MET'} (starting goalie pre-game "
          "[NHL API or MoneyPuck] + goalie game stats + depth 2023-2025)")
    print(f"N6 HOST IP RECEIPT: run this script on the host, or: curl -sS -o /dev/null -w '%{{http_code}}\\n' "
          f"{BASE}/v1/schedule/{today.isoformat()}")
    if a.out:
        if "data" in a.out.resolve().parts:
            print("✗ refusing to write under data/ (law 5).")
            return 1
        with open(a.out, "a") as f:
            f.write(json.dumps(r, default=str) + "\n")
        print(f"✓ run appended to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
