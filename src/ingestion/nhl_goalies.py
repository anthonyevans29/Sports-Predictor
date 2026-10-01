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


# NAME ALIASES (architect ruling 2026-10-01, NHL audit): the franchise
# renamed "Utah Hockey Club" -> "Utah Mammoth"; the shared normaliser cannot
# bridge the two ("utah hockey" vs "utah mammoth"), so the goalie mapping
# carries the alias both ways as extra CANDIDATE names. The matcher still
# refuses ambiguity at every candidate; an alias only adds a name to try.
# 2024 form (architect ruling 2026-10-01, re-audit): the 2024-25 schedule
# serves placeName "Utah" + commonName "Utah Hockey Club", so place + common
# builds the doubled token "Utah Utah Hockey Club"; it maps to the franchise
# (Utah Mammoth, plus Utah Hockey Club since aliases do not chain).
NAME_ALIASES = {
    "Utah Mammoth": ("Utah Hockey Club",),
    "Utah Hockey Club": ("Utah Mammoth",),
    "Utah Utah Hockey Club": ("Utah Mammoth", "Utah Hockey Club"),
}


def team_names(t: dict) -> list[str]:
    """Candidate full names for one side, most specific first: the API's
    full name if present, then place + common name, then ruled aliases.
    Accents stripped ("Montréal" -> "Montreal") so the shared normaliser can
    compare."""
    out = []
    full = _text(t.get("name")) or _text(t.get("fullName"))
    if full:
        out.append(full)
    place, common = _text(t.get("placeName")), _text(t.get("commonName"))
    if place and common:
        out.append(f"{place} {common}")
    names = [strip_accents(n) for n in dict.fromkeys(out)]
    for n in list(names):
        names += [a for a in NAME_ALIASES.get(n, ()) if a not in names]
    return names


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


def match_game(s, game: dict, tolerance_hours: int = 12):
    """Our Match for an API game, or None (no match / ambiguous: refused).
    The ± window is 12h unless the operator widens it after an audit
    (`nhl-goalie-sync --tolerance-hours`); ambiguity is refused at any width."""
    from src.db.schema import Sport
    from src.ingestion.match_lookup import find_match

    if game["start"] is None:
        return None
    for hn in game["home_names"]:
        for an in game["away_names"]:
            m = find_match(s, Sport.NHL, hn, an, game["start"], tolerance_hours=tolerance_hours)
            if m is not None:
                return m
    return None


def sync(start: date, end: date, fetch: Fetch = http_json, sleep: float = 0.25,
         refresh: bool = False, dry_run: bool = False, now: datetime | None = None,
         tolerance_hours: int = 12,
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
            m = match_game(s, g, tolerance_hours)
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


# --------------------------------------------------------------------------
# Unlinked-games AUDIT (architect 2026-09-30): "audit the ~290 unlinked
# regular-season games (UTC-boundary suspects) so coverage nears 100%".
# Read-only: re-walks the schedule, reads our matches + the stored links,
# writes nothing. It classifies each unlinked game by CAUSE and counts what a
# wider window would link uniquely, so the fix is chosen from the receipt.
# --------------------------------------------------------------------------

AUDIT_WINDOW_H = 48
WHAT_IF_TOLERANCES = (18, 24, 36, 48)


def _norm(name: str) -> str:
    from src.ingestion.match_lookup import normalize_team_name
    return normalize_team_name(strip_accents(name or ""))


def _our_nhl_matches(s) -> list[dict]:
    """Our finished NHL (competition NHL) matches with normalized names."""
    from sqlalchemy import select
    from sqlalchemy.orm import aliased

    from src.db.schema import Competition, Match, MatchStatus, Sport, Team

    H, A = aliased(Team), aliased(Team)
    rows = s.execute(select(Match.id, Match.utc_date, Match.season, Match.stage, H.name, A.name)
                     .join(Competition, Match.competition_id == Competition.id)
                     .join(H, Match.home_team_id == H.id).join(A, Match.away_team_id == A.id)
                     .where(Match.sport == Sport.NHL, Competition.code == "NHL",
                            Match.status == MatchStatus.FINISHED)).all()
    return [{"id": i, "t": t, "season": se, "stage": st or "", "home": h, "away": a,
             "hn": _norm(h), "an": _norm(a)} for i, t, se, st, h, a in rows]


def classify(game: dict, ours: list[dict], linked_ids: set[int]) -> dict:
    """Why an API game has no link to our match. Pure (testable)."""
    hs, as_ = {_norm(n) for n in game["home_names"]}, {_norm(n) for n in game["away_names"]}
    near = [(abs((o["t"] - game["start"]).total_seconds()) / 3600.0, o) for o in ours
            if o["t"] is not None and abs((o["t"] - game["start"]).total_seconds()) <= AUDIT_WINDOW_H * 3600]
    same = [(dh, o) for dh, o in near if o["hn"] in hs and o["an"] in as_]
    swapped = [(dh, o) for dh, o in near if o["hn"] in as_ and o["an"] in hs]
    out = {"cause": None, "offset_h": None, "match_id": None, "detail": ""}
    within12 = [x for x in same if x[0] <= 12]
    if len(within12) > 1:
        out.update(cause="ambiguous_within_12h", detail=f"{len(within12)} of our matches")
    elif within12:
        dh, o = within12[0]
        out.update(cause="unlinked_within_12h", offset_h=round(dh, 1), match_id=o["id"],
                   detail="matchable now: never synced, or its boxscore was refused")
    elif same:
        dh, o = min(same, key=lambda x: x[0])
        out.update(cause="utc_boundary" if len(same) == 1 else "ambiguous_beyond_12h",
                   offset_h=round(dh, 1), match_id=o["id"],
                   detail=f"ours {o['t']:%Y-%m-%d %H:%M} vs API {game['start']:%Y-%m-%d %H:%M} UTC"
                          + ("" if o["id"] not in linked_ids else " (our match already linked elsewhere)"))
    elif swapped:
        dh, o = min(swapped, key=lambda x: x[0])
        out.update(cause="home_away_swapped", offset_h=round(dh, 1), match_id=o["id"],
                   detail=f"ours {o['away']} @ {o['home']}")
    else:
        one = [o for dh, o in near if dh <= 12 and ({o["hn"], o["an"]} & (hs | as_))]
        if one:
            o = one[0]
            out.update(cause="name_mismatch",
                       detail=f"API {'/'.join(game['away_names'])} @ {'/'.join(game['home_names'])} vs ours "
                              f"{o['away']} @ {o['home']}")
        else:
            out.update(cause="not_in_our_db")
    return out


# OUR-SIDE LISTING (architect ruling 2026-10-01): "List the ~200 remaining
# unlinked OUR games for 2024/2025 by date with the nearest API game and its
# delta — cause unknown, name it." For each of OUR finished, unlinked matches
# the nearest API game (any gameType, ±LIST_WINDOW_D days) is found in order of
# preference — the same pair, the pair swapped, one shared team — and the
# cause is NAMED from what was found (a label from evidence, never a guess):
#   api_preseason          the same pair, but the API calls it gameType 1 (not ingested)
#   api_game_not_synced    the same pair within 12h, API game never linked
#   utc_offset_beyond_12h  the same pair, |delta| > 12h (a widened window links it)
#   linked_to_other_match  the same pair's API game is linked to a DIFFERENT match of ours
#   home_away_swapped      only the swapped pair exists
#   one_team_only          nearest API game shares one team (a name mismatch?)
#   no_api_game            nothing within the window (postponed / phantom in our DB?)
LIST_WINDOW_D = 7


def list_unlinked_ours(api_games: list[dict], ours: list[dict], links: dict[int, int],
                       seasons: set[str] | None) -> list[dict]:
    """Pure: our unlinked matches with the nearest API game and a named cause."""
    linked_ids = set(links.values())
    rows = []
    for o in sorted(ours, key=lambda x: x["t"] or datetime.min):
        if o["id"] in linked_ids or o["t"] is None or (seasons and str(o["season"]) not in seasons):
            continue
        best = {}
        for g in api_games:
            if g["start"] is None:
                continue
            dh = (g["start"] - o["t"]).total_seconds() / 3600.0
            if abs(dh) > LIST_WINDOW_D * 24:
                continue
            hs, as_ = {_norm(n) for n in g["home_names"]}, {_norm(n) for n in g["away_names"]}
            kind = ("same" if o["hn"] in hs and o["an"] in as_ else
                    "swapped" if o["hn"] in as_ and o["an"] in hs else
                    "one" if {o["hn"], o["an"]} & (hs | as_) else None)
            if kind and (kind not in best or abs(dh) < abs(best[kind][0])):
                best[kind] = (dh, g)
        if "same" in best:
            dh, g = best["same"]
            other = links.get(g["id"])
            cause = ("api_preseason" if g["game_type"] == 1 else
                     "linked_to_other_match" if other is not None and other != o["id"] else
                     "utc_offset_beyond_12h" if abs(dh) > 12 else "api_game_not_synced")
        elif "swapped" in best:
            dh, g = best["swapped"]
            cause = "home_away_swapped"
        elif "one" in best:
            dh, g = best["one"]
            cause = "one_team_only"
        else:
            dh, g, cause = None, None, "no_api_game"
        rows.append({"match_id": o["id"], "season": o["season"], "t": o["t"],
                     "ours": f"{o['away']} @ {o['home']}", "cause": cause,
                     "delta_h": round(dh, 1) if dh is not None else None,
                     "api": (None if g is None else
                             f"game {g['id']} type {g['game_type']} {g['start']:%Y-%m-%d %H:%M} "
                             f"{'/'.join(g['away_names'])} @ {'/'.join(g['home_names'])}"),
                     "api_linked_to": links.get(g["id"]) if g is not None else None})
    return rows


def audit(start: date, end: date, fetch: Fetch = http_json, sleep: float = 0.25,
          now: datetime | None = None, list_seasons: set[str] | None = None) -> dict:
    """Receipt: API-side and our-side unlinked games by cause, the offset
    distribution, and how many a wider window would link uniquely."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import NHLGoalieAppearance
    from src.timeutil import utc_now_naive

    now = now or utc_now_naive()
    seen: dict[int, dict] = {}
    d, calls = start, 0
    while d <= end:
        code, payload = fetch(f"{BASE}/v1/schedule/{d.isoformat()}")
        calls += 1
        for g in schedule_games(payload):
            if g["start"] and start <= g["start"].date() <= end + timedelta(days=1):
                seen.setdefault(g["id"], g)
        d += timedelta(days=7)
        if sleep:
            time.sleep(sleep)
    with session_scope() as s:
        ours = _our_nhl_matches(s)
        links = dict(s.execute(select(NHLGoalieAppearance.nhl_game_id, NHLGoalieAppearance.match_id)
                               .where(NHLGoalieAppearance.match_id.is_not(None)).distinct()).all())
    linked_ids = set(links.values())
    api = [g for g in seen.values() if (g["game_type"] in KEEP_GAME_TYPES or g["game_type"] is None)
           and g["start"] is not None and g["start"] <= now - timedelta(hours=6)]
    causes, by_type, offsets, samples = Counter(), Counter(), Counter(), {}
    what_if = Counter()
    for g in api:
        if g["id"] in links:
            continue
        c = classify(g, ours, linked_ids)
        causes[c["cause"]] += 1
        by_type[(c["cause"], g["game_type"])] += 1
        if c["offset_h"] is not None and c["cause"] in ("utc_boundary", "ambiguous_beyond_12h"):
            offsets[int(c["offset_h"])] += 1
        if c["cause"] == "utc_boundary" and c["match_id"] not in linked_ids:
            for t in WHAT_IF_TOLERANCES:
                if c["offset_h"] <= t:
                    what_if[t] += 1
        samples.setdefault(c["cause"], []).append(
            f"{g['start']:%Y-%m-%d %H:%M} game {g['id']} {'/'.join(g['away_names'])} @ "
            f"{'/'.join(g['home_names'])}" + (f" · {c['detail']}" if c["detail"] else ""))
    # our side: finished matches with no link, by season
    listing = (list_unlinked_ours(list(seen.values()), ours, links, list_seasons)
               if list_seasons is not None else None)
    our_unlinked = [o for o in ours if o["id"] not in linked_ids]
    our_by_season = Counter(o["season"] for o in our_unlinked)
    our_total = Counter(o["season"] for o in ours)
    return {"schedule_calls": calls, "api_games": len(api), "api_linked": sum(1 for g in api if g["id"] in links),
            "api_unlinked_by_cause": dict(causes),
            "api_unlinked_by_cause_type": {f"{k[0]}|gameType {k[1]}": v for k, v in sorted(by_type.items(), key=str)},
            "offset_hours": dict(sorted(offsets.items())), "would_link_uniquely": dict(sorted(what_if.items())),
            "ours_unlinked_by_season": dict(sorted(our_by_season.items())),
            "ours_total_by_season": dict(sorted(our_total.items())),
            "samples": samples, "ours_listing": listing}
