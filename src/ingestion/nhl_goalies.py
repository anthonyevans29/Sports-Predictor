"""
NHL-GOALIE lane (a), architect 2026-09-30: the NHL API adapter.

Maps our NHL match rows to api-web.nhle.com game ids (date ± 12h + both team
names, via the shared refusal-on-ambiguity matcher) and ingests per-game
goalie appearances (starter flag, shots / saves / goals against, TOI) into
nhl_goalie_appearances, from 2023-24 through now.

LAW 1. This build environment cannot reach api-web.nhle.com (proxy 403), so
no response field name is assumed. It re-uses the discovery rules the
NHL-API-PROBE proved against the live API (#124: schedule, boxscore goalie
stats and starter flags all FEEDABLE):
  * games       = dicts with an integer "id" and a start-time key;
  * teams       = the game's sub-dicts under keys starting "home" / "away";
  * goalies     = lists under a key naming goalies, sided by a "home" / "away"
                  segment in their path;
  * starter     = a key naming starter/starting whose value is a boolean;
  * stats       = keys matched EXACTLY (case-insensitive): saves,
                  shotsAgainst, goalsAgainst, toi, decision, or the combined
                  "saveShotsAgainst" ("25/27").
Anything not found stays NULL and is counted; a game whose goalies cannot be
sided is REFUSED (counted, never guessed). The first run's receipt prints the
keys actually used — that is the law-1 receipt.

Writes: nhl_goalie_appearances only (upsert on game + goalie). Never deletes.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Callable

BASE = "https://api-web.nhle.com"
GOALIE = re.compile(r"goalie", re.I)
STARTER = re.compile(r"starter|starting", re.I)
START = re.compile(r"start.*time|gamedate|datetime", re.I)
GAMETYPE = re.compile(r"^gametype$", re.I)
KEEP_GAME_TYPES = {2, 3}          # regular season + playoffs; preseason (1) and exhibitions out
EXACT = {"saves": "saves", "shotsagainst": "shots_against", "goalsagainst": "goals_against",
         "toi": "toi", "decision": "decision", "saveshotsagainst": "save_shots"}

Fetch = Callable[[str], "tuple[int, dict | None]"]


def http_json(url: str, timeout: int = 20) -> tuple[int, dict | None]:
    req = urllib.request.Request(url, headers={"User-Agent": "sports-predictor/nhl-goalies",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, None


def walk(obj, path=""):
    """Yield (path, dict) for every dict in the tree."""
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


def _text(v) -> str | None:
    """A display string: plain str, or the API's localized {"default": ...}."""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        d = v.get("default")
        return d if isinstance(d, str) else None
    return None


def parse_time(v) -> datetime | None:
    """UTC-naive datetime from an ISO string ('...Z' allowed)."""
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def team_names(t: dict) -> list[str]:
    """Candidate full names for one side, most specific first: the API's
    full name if present, then place + common name. Accents stripped
    ("Montréal" -> "Montreal") so the shared normaliser can compare."""
    out = []
    full = _text(t.get("name")) or _text(t.get("fullName"))
    if full:
        out.append(full)
    place, common = _text(t.get("placeName")), _text(t.get("commonName"))
    if place and common:
        out.append(f"{place} {common}")
    return [strip_accents(n) for n in dict.fromkeys(out)]


def schedule_games(payload: dict | None) -> list[dict]:
    """Games found in a schedule payload: id, start (UTC naive), gameType,
    and both sides' name candidates + abbrev. De-duplicated by id."""
    out: dict[int, dict] = {}
    for _, d in walk(payload or {}):
        if not isinstance(d.get("id"), int) or not any(START.search(k) for k in d):
            continue
        sk = next((k for k in d if re.search(r"starttimeutc", k, re.I)), None) \
            or next(k for k in d if START.search(k))
        home = next((v for k, v in d.items() if k.lower().startswith("home") and isinstance(v, dict)), None)
        away = next((v for k, v in d.items() if k.lower().startswith("away") and isinstance(v, dict)), None)
        if home is None or away is None:
            continue
        gt_key = next((k for k in d if GAMETYPE.match(k)), None)
        out[d["id"]] = {"id": d["id"], "start": parse_time(d.get(sk)),
                        "game_type": d.get(gt_key) if gt_key else None,
                        "home_names": team_names(home), "away_names": team_names(away),
                        "home_abbrev": home.get("abbrev"), "away_abbrev": away.get("abbrev")}
    return list(out.values())


def _toi_seconds(v) -> int | None:
    m = re.fullmatch(r"(\d+):(\d{2})", str(v or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _int(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def goalie_rows(g: dict) -> dict:
    """One goalie dict -> our columns (NULL where not found), plus the keys used."""
    keys = {k.lower(): k for k in g}
    used = {}
    row = {"goalie_id": _int(g.get("playerId")) or _int(g.get("id")),
           "goalie_name": _text(g.get("name")) or " ".join(filter(None, (_text(g.get("firstName")),
                                                                      _text(g.get("lastName"))))) or None,
           "is_starter": None, "shots_against": None, "saves": None, "goals_against": None,
           "toi_seconds": None, "decision": None}
    sk = next((k for k in g if STARTER.search(k) and isinstance(g[k], bool)), None)
    if sk:
        row["is_starter"], used["starter"] = g[sk], sk
    for low, col in EXACT.items():
        if low not in keys:
            continue
        k = keys[low]
        used[col] = k
        v = g[k]
        if col == "toi":
            row["toi_seconds"] = _toi_seconds(v)
        elif col == "decision":
            row["decision"] = v if isinstance(v, str) else None
        elif col == "save_shots":
            m = re.fullmatch(r"(\d+)/(\d+)", str(v or ""))
            if m and row["saves"] is None and row["shots_against"] is None:
                row["saves"], row["shots_against"] = int(m.group(1)), int(m.group(2))
        else:
            row[col] = _int(v)
    if row["goals_against"] is None and row["saves"] is not None and row["shots_against"] is not None:
        row["goals_against"] = row["shots_against"] - row["saves"]
    return {"row": row, "used": used}


def boxscore_goalies(payload: dict | None) -> tuple[list[dict] | None, dict]:
    """(rows with side, receipt). None when the goalie lists cannot be sided
    as exactly one home list + one away list (the game is REFUSED)."""
    lists = []
    for p, d in walk(payload or {}):
        for k, v in d.items():
            if GOALIE.search(k) and isinstance(v, list) and all(isinstance(x, dict) for x in v):
                path = f"{p}.{k}" if p else k
                segs = [s.lower() for s in re.split(r"[.\[\]]", path) if s]
                side = ("home" if any(s.startswith("home") for s in segs)
                        else "away" if any(s.startswith("away") for s in segs) else None)
                lists.append((path, side, v))
    sided = {s: [(p, v) for p, s_, v in lists if s_ == s] for s in ("home", "away")}
    receipt = {"goalie_lists": [p for p, _, _ in lists], "keys_used": {}}
    if len(sided["home"]) != 1 or len(sided["away"]) != 1:
        return None, receipt
    rows = []
    for side in ("home", "away"):
        for g in sided[side][0][1]:
            r = goalie_rows(g)
            receipt["keys_used"].update(r["used"])
            if r["row"]["goalie_id"] is None:
                continue
            rows.append({**r["row"], "side": side})
    return rows, receipt


def match_game(s, game: dict):
    """Our Match for an API game, or None (no match / ambiguous: refused)."""
    from src.db.schema import Sport
    from src.ingestion.match_lookup import find_match

    if game["start"] is None:
        return None
    for hn in game["home_names"]:
        for an in game["away_names"]:
            m = find_match(s, Sport.NHL, hn, an, game["start"], tolerance_hours=12)
            if m is not None:
                return m
    return None


def sync(start: date, end: date, fetch: Fetch = http_json, sleep: float = 0.25,
         refresh: bool = False, dry_run: bool = False, now: datetime | None = None,
         progress: Callable[[str], None] | None = None) -> dict:
    """Walk the schedule week by week from `start` to `end`, map each kept
    game to our match, fetch finished games' boxscores and upsert goalie
    rows. Returns the receipt."""
    from sqlalchemy import func, select

    from src.db.database import session_scope
    from src.db.schema import NHLGoalieAppearance
    from src.timeutil import utc_now_naive

    now = now or utc_now_naive()
    say = progress or (lambda _m: None)
    rc = Counter()
    keys_used: dict = {}
    refused: list[dict] = []
    unmatched_names: Counter = Counter()
    seen: dict[int, dict] = {}
    d = start
    while d <= end:
        code, payload = fetch(f"{BASE}/v1/schedule/{d.isoformat()}")
        rc["schedule_calls"] += 1
        rc[f"schedule_http_{code}"] += 1
        for g in schedule_games(payload):
            if g["start"] is None or not (start <= g["start"].date() <= end + timedelta(days=1)):
                continue
            seen.setdefault(g["id"], g)
        d += timedelta(days=7)
        if sleep:
            time.sleep(sleep)
    games = sorted(seen.values(), key=lambda g: g["start"])
    rc["games_found"] = len(games)
    with session_scope() as s:
        have = {gid for (gid,) in s.execute(
            select(NHLGoalieAppearance.nhl_game_id).where(NHLGoalieAppearance.is_starter.is_(True))
            .group_by(NHLGoalieAppearance.nhl_game_id)
            .having(func.count() >= 2))}
    for g in games:
        gt = g["game_type"]
        if gt is not None and gt not in KEEP_GAME_TYPES:
            rc[f"skipped_game_type_{gt}"] += 1
            continue
        if gt is None:
            rc["game_type_missing_kept"] += 1
        if g["start"] > now - timedelta(hours=6):
            rc["skipped_not_finished"] += 1
            continue
        with session_scope() as s:
            m = match_game(s, g)
            match_id = m.id if m is not None else None
        rc["mapped_to_our_match" if match_id else "not_in_our_db"] += 1
        if match_id is None:
            unmatched_names[f"{'/'.join(g['away_names'])} @ {'/'.join(g['home_names'])}"] += 1
        if g["id"] in have and not refresh:
            rc["skipped_already_complete"] += 1
            if match_id:
                _link(g["id"], match_id, dry_run)
            continue
        code, payload = fetch(f"{BASE}/v1/gamecenter/{g['id']}/boxscore")
        rc["boxscore_calls"] += 1
        rc[f"boxscore_http_{code}"] += 1
        if sleep:
            time.sleep(sleep)
        rows, receipt = boxscore_goalies(payload)
        keys_used.update(receipt["keys_used"])
        if rows is None:
            rc["refused_unsided"] += 1
            refused.append({"game": g["id"], "goalie_lists": receipt["goalie_lists"]})
            continue
        starters = Counter(r["side"] for r in rows if r["is_starter"] is True)
        rc["both_starters" if starters.get("home") == 1 and starters.get("away") == 1 else "starter_incomplete"] += 1
        if not dry_run:
            _upsert(g, match_id, rows)
        rc["rows_written" if not dry_run else "rows_would_write"] += len(rows)
        say(f"  {g['start']:%Y-%m-%d} game {g['id']}: {len(rows)} goalies"
            + (f" -> match {match_id}" if match_id else " (not in our DB)"))
    return {"counts": dict(rc), "keys_used": keys_used, "refused": refused[:20],
            "unmatched_sample": unmatched_names.most_common(15)}


def _link(nhl_game_id: int, match_id: int, dry_run: bool) -> None:
    from sqlalchemy import update

    from src.db.database import session_scope
    from src.db.schema import NHLGoalieAppearance

    if dry_run:
        return
    with session_scope() as s:
        s.execute(update(NHLGoalieAppearance).where(NHLGoalieAppearance.nhl_game_id == nhl_game_id,
                                                    NHLGoalieAppearance.match_id.is_(None))
                  .values(match_id=match_id))


def _upsert(g: dict, match_id: int | None, rows: list[dict]) -> None:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import NHLGoalieAppearance
    from src.timeutil import utc_now_naive

    with session_scope() as s:
        for r in rows:
            cur = s.execute(select(NHLGoalieAppearance).where(
                NHLGoalieAppearance.nhl_game_id == g["id"],
                NHLGoalieAppearance.goalie_id == r["goalie_id"])).scalar_one_or_none()
            vals = dict(match_id=match_id, game_start=g["start"], game_type=g["game_type"],
                        side=r["side"], team_abbrev=g[f"{r['side']}_abbrev"],
                        goalie_name=r["goalie_name"], is_starter=r["is_starter"],
                        shots_against=r["shots_against"], saves=r["saves"],
                        goals_against=r["goals_against"], toi_seconds=r["toi_seconds"],
                        decision=r["decision"], captured_at=utc_now_naive())
            if cur is None:
                s.add(NHLGoalieAppearance(nhl_game_id=g["id"], goalie_id=r["goalie_id"], **vals))
            else:
                for k, v in vals.items():
                    if v is not None:          # a refetch never blanks a stored value
                        setattr(cur, k, v)


def coverage() -> dict:
    """Receipt (lane (a)): of OUR finished NHL games (competition NHL), how
    many have both starters identified in nhl_goalie_appearances — by season."""
    from sqlalchemy import func, select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, NHLGoalieAppearance, Sport

    with session_scope() as s:
        ours = s.execute(select(Match.id, Match.season).join(Competition, Match.competition_id == Competition.id)
                         .where(Match.sport == Sport.NHL, Competition.code == "NHL",
                                Match.status == MatchStatus.FINISHED)).all()
        starters = Counter()
        for mid, side in s.execute(select(NHLGoalieAppearance.match_id, NHLGoalieAppearance.side)
                                   .where(NHLGoalieAppearance.match_id.is_not(None),
                                          NHLGoalieAppearance.is_starter.is_(True))):
            starters[(mid, side)] += 1
        linked = {mid for (mid,) in s.execute(select(NHLGoalieAppearance.match_id)
                                              .where(NHLGoalieAppearance.match_id.is_not(None)).distinct())}
        total_rows = s.execute(select(func.count(NHLGoalieAppearance.id))).scalar()
    by = {}
    for mid, season in ours:
        b = by.setdefault(season, Counter())
        b["finished"] += 1
        b["linked"] += mid in linked
        b["both_starters"] += starters[(mid, "home")] == 1 and starters[(mid, "away")] == 1
    return {"by_season": {k: dict(v) for k, v in sorted(by.items())}, "rows": total_rows}
