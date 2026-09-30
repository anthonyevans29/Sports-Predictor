"""
NHL SHOT-QUALITY PROBE (architect lane, 2026-09-30) — read-only, zero wiring.

The restated NHL reopening condition: "shot-quality data (xG-class) entering
the stack — NEW LANE, read-only: probe api-web.nhle.com play-by-play for
shot events with location/type 2023-present, coverage vs our games, host IP
already 200. No v6 without it."

Law 1: this build environment cannot reach api-web.nhle.com, so no field
name is assumed. From /v1/gamecenter/<id>/play-by-play it FINDS:
  plays         the largest list of dicts under a key naming plays
  event type    a string-valued key naming a type (typeDescKey-like) in the
                plays; shot events = type values containing "shot" or "goal"
  location      numeric x / y keys (xCoord-like) in the play or its details
  shot type     a key naming a shot type
  shooter       a key naming the shooting / scoring player
  situation     a key naming the strength situation (e.g. situationCode)
and dumps the first response's key paths into the receipt.

NEEDS (verdict per need, FEEDABLE / NOT, over the sampled games):
  P1 shot events       >= 95% of sampled games carry shot events
  P2 location          >= 95% of shot events carry x AND y
  P3 shot type         >= 90% of shot events carry a shot type
  P4 shooter           >= 95% of shot events carry a shooter id
  P5 situation         >= 90% of shot events (or their plays) carry a strength situation
  P6 depth             P1 and P2 hold in EVERY sampled season (2023-24 .. now)
  P7 our games         with --from-db: the sample is drawn from OUR linked
                       games (nhl_goalie_appearances.match_id), so P1/P2 are
                       coverage vs our games; without it: schedule sample
  P8 host IP           run this same script ON THE HOST: the first call's HTTP
                       status is the datacenter-IP receipt
GREEN = P1-P4 + P6 FEEDABLE: shot-quality data can enter the stack (the
reopening condition); a v6 candidate would still go through the FROZEN gate.

    python3 scripts/nhl_pbp_probe.py [--per-season 20] [--seasons 2023 2024 2025]
                                     [--from-db] [--sleep 0.25] [--out pbp.jsonl]

Writes nothing unless --out is given (never under data/).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = "https://api-web.nhle.com"
PLAYS = re.compile(r"^plays?$", re.I)
TYPE = re.compile(r"typedesc|type.?key|eventtype|typecode", re.I)
SHOTISH = re.compile(r"shot|goal", re.I)
X = re.compile(r"^x(coord)?$", re.I)
Y = re.compile(r"^y(coord)?$", re.I)
SHOTTYPE = re.compile(r"shot.?type", re.I)
SHOOTER = re.compile(r"(shooting|scoring|shooter).*(player)?id$", re.I)
SITUATION = re.compile(r"situation", re.I)
# the season windows sampled (regular season, Oct .. Apr), keyed by the
# season's first year like the rest of the NHL code ("2024" = 2024-25)
SEASON_WINDOWS = {"2023": (date(2023, 10, 10), date(2024, 4, 18)),
                  "2024": (date(2024, 10, 8), date(2025, 4, 17)),
                  "2025": (date(2025, 10, 7), date(2026, 4, 16))}


def http_json(url: str, timeout: int = 20) -> tuple[int, dict | None]:
    req = urllib.request.Request(url, headers={"User-Agent": "sports-predictor-pbp-probe/1.0",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, None


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
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


def find_plays(payload) -> tuple[list[dict], str | None]:
    best, where = [], None
    for p, d in walk(payload or {}):
        for k, v in d.items():
            if PLAYS.match(k) and isinstance(v, list) and len(v) > len(best) \
                    and all(isinstance(x, dict) for x in v):
                best, where = v, (f"{p}.{k}" if p else k)
    return best, where


def _flat(play: dict) -> dict:
    """The play's own keys plus its nested dicts' keys (details etc.)."""
    out = dict(play)
    for v in play.values():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                out.setdefault(k2, v2)
    return out


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def read_game(payload) -> dict:
    """Per-game read: plays, shot events, and the share carrying each field."""
    plays, where = find_plays(payload)
    type_key = None
    for pl in plays:
        type_key = next((k for k, v in pl.items() if TYPE.search(k) and isinstance(v, str)), None)
        if type_key:
            break
    shots = [p for p in plays if type_key and SHOTISH.search(str(p.get(type_key, "")))]
    keys_used = Counter()
    have = Counter()
    for p in shots:
        f = _flat(p)
        xk = next((k for k in f if X.match(k) and _num(f[k])), None)
        yk = next((k for k in f if Y.match(k) and _num(f[k])), None)
        tk = next((k for k in f if SHOTTYPE.search(k) and f[k] not in (None, "")), None)
        sk = next((k for k in f if SHOOTER.search(k) and f[k] not in (None, "")), None)
        sit = next((k for k in f if SITUATION.search(k) and f[k] not in (None, "")), None)
        for name, k in (("x", xk), ("y", yk), ("shot_type", tk), ("shooter", sk), ("situation", sit)):
            if k:
                keys_used[f"{name}<-{k}"] += 1
        have["xy"] += bool(xk and yk)
        have["shot_type"] += bool(tk)
        have["shooter"] += bool(sk)
        have["situation"] += bool(sit)
    return {"plays": len(plays), "plays_at": where, "type_key": type_key,
            "shot_types": dict(Counter(str(p.get(type_key)) for p in shots)),
            "shots": len(shots), "have": dict(have), "keys_used": dict(keys_used)}


def schedule_sample(fetch, season: str, n: int, now: datetime, sleep: float) -> list[int]:
    """n finished regular-season game ids spread across the season window."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.ingestion.nhl_goalies import schedule_games

    lo, hi = SEASON_WINDOWS[season]
    hi = min(hi, (now - timedelta(days=1)).date())
    if hi < lo:
        return []
    days = max((hi - lo).days, 1)
    picks: list[int] = []
    for i in range(n):
        d = lo + timedelta(days=int(days * i / max(n, 1)))
        code, payload = fetch(f"{BASE}/v1/schedule/{d.isoformat()}")
        for g in schedule_games(payload):
            if g["game_type"] in (2, None) and g["start"] and g["start"] < now - timedelta(hours=6) \
                    and g["id"] not in picks:
                picks.append(g["id"])
                break
        if sleep:
            time.sleep(sleep)
    return picks


def db_sample(n: int) -> dict[str, list[int]]:
    """n of OUR linked games per season (nhl_goalie_appearances.match_id)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, NHLGoalieAppearance

    by: dict[str, list[int]] = {}
    with session_scope() as s:
        rows = s.execute(select(NHLGoalieAppearance.nhl_game_id, Match.season)
                         .join(Match, NHLGoalieAppearance.match_id == Match.id).distinct()
                         .order_by(NHLGoalieAppearance.nhl_game_id)).all()
    for gid, season in rows:
        by.setdefault(str(season), []).append(gid)
    return {k: v[:: max(len(v) // n, 1)][:n] for k, v in by.items()}


def run(fetch, seasons: list[str], per_season: int, from_db: bool, now: datetime,
        sleep: float = 0.25) -> dict:
    first_status = None
    sample = db_sample(per_season) if from_db else {}
    rec = {"seasons": {}, "first_key_paths": [], "source": "our linked games" if from_db else "schedule"}
    for season in seasons:
        ids = sample.get(season, []) if from_db else schedule_sample(fetch, season, per_season, now, sleep)
        agg = Counter()
        types, keys = Counter(), Counter()
        for gid in ids:
            code, payload = fetch(f"{BASE}/v1/gamecenter/{gid}/play-by-play")
            if first_status is None:
                first_status = code
                rec["first_key_paths"] = key_paths(payload or {})[:60]
            if sleep:
                time.sleep(sleep)
            agg["games"] += 1
            agg[f"http_{code}"] += 1
            if not payload:
                continue
            r = read_game(payload)
            agg["games_with_shots"] += r["shots"] > 0
            agg["shots"] += r["shots"]
            for k, v in r["have"].items():
                agg[k] += v
            types.update(r["shot_types"])
            keys.update(r["keys_used"])
        rec["seasons"][season] = {"counts": dict(agg), "shot_types": dict(types),
                                  "keys_used": dict(keys.most_common(10))}
    rec["first_http"] = first_status
    rec["needs"] = verdict(rec)
    return rec


def _share(c: Counter | dict, k: str, of: str) -> float:
    return (c.get(k, 0) / c[of]) if c.get(of) else 0.0


def verdict(rec: dict) -> dict:
    seasons = rec["seasons"]
    tot = Counter()
    for s in seasons.values():
        tot.update(s["counts"])
    p1 = _share(tot, "games_with_shots", "games") >= 0.95
    p2 = _share(tot, "xy", "shots") >= 0.95
    per_season_ok = bool(seasons) and all(
        _share(s["counts"], "games_with_shots", "games") >= 0.95 and _share(s["counts"], "xy", "shots") >= 0.95
        for s in seasons.values())
    needs = {"P1 shot events": p1, "P2 location": p2,
             "P3 shot type": _share(tot, "shot_type", "shots") >= 0.90,
             "P4 shooter": _share(tot, "shooter", "shots") >= 0.95,
             "P5 situation": _share(tot, "situation", "shots") >= 0.90,
             "P6 depth": per_season_ok}
    needs["GREEN"] = all(needs[k] for k in ("P1 shot events", "P2 location", "P3 shot type",
                                              "P4 shooter", "P6 depth"))
    return needs


def main(argv=None, fetch=http_json, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seasons", nargs="+", default=list(SEASON_WINDOWS))
    ap.add_argument("--per-season", type=int, default=20)
    ap.add_argument("--from-db", action="store_true", help="sample OUR linked games (coverage vs our games)")
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--out", default=None, help="append the receipt as one JSON line (never under data/)")
    a = ap.parse_args(argv)
    if a.out and "data" in Path(a.out).resolve().parts:
        print("REFUSED: --out under data/ (the packaging law)")
        return 1
    unknown = [s for s in a.seasons if s not in SEASON_WINDOWS]
    if unknown:
        print(f"REFUSED: unknown season(s) {unknown}; known {list(SEASON_WINDOWS)}")
        return 2
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    rec = run(fetch, a.seasons, a.per_season, a.from_db, now, a.sleep)
    print(f"NHL SHOT-QUALITY PROBE · {now:%Y-%m-%d %H:%M} UTC · sample: {rec['source']} · "
          f"{a.per_season}/season · first HTTP {rec['first_http']} (on the host = the P8 IP receipt)")
    for season, s in rec["seasons"].items():
        c = s["counts"]
        print(f"  {season}: games {c.get('games', 0)} · with shot events {c.get('games_with_shots', 0)} · "
              f"shot events {c.get('shots', 0)} · x+y {_share(c, 'xy', 'shots') * 100:.1f}% · "
              f"shot type {_share(c, 'shot_type', 'shots') * 100:.1f}% · shooter "
              f"{_share(c, 'shooter', 'shots') * 100:.1f}% · situation {_share(c, 'situation', 'shots') * 100:.1f}%")
        print(f"    event types: {s['shot_types']}")
        print(f"    keys used: {s['keys_used']}")
    print("  first response key paths: " + ", ".join(rec["first_key_paths"][:30]))
    for k, v in rec["needs"].items():
        if k != "GREEN":
            print(f"  {k}: {'FEEDABLE' if v else 'NOT'}")
    print("REOPENING CONDITION (shot-quality data): " + ("GREEN — a v6 candidate may go to the frozen gate"
                                                        if rec["needs"]["GREEN"] else "NOT MET"))
    if a.out:
        with open(a.out, "a") as f:
            f.write(json.dumps({"at": now.isoformat(), **rec}, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
