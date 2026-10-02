"""
NHL-xG lane (1) INGEST, architect 2026-09-30: "nhl_shot_events table (game,
team, shooter, x, y, event type, shot type nullable, situation, period/time)
from api-web play-by-play, 2023-24 to present, keyed to our matches via the
goalie-sync mapping; coverage receipt like goalie-coverage. Host-runnable."

Games come from the same schedule walk as nhl-goalie-sync (regular season +
playoffs, finished). Each game maps to OUR match through the goalie-sync
mapping first (nhl_goalie_appearances.match_id for the same nhl_game_id),
else through the same refusal-on-ambiguity matcher at the same tolerance;
every run also RELINKS stored shot rows whose game gained a goalie link
since (the path the unlinked-games audit fix takes: nhl-goalie-audit ->
nhl-goalie-sync --tolerance-hours N -> nhl-shot-sync).

LAW 1. Field names are DISCOVERED per payload with the probe's rules (the
probe ran GREEN on the host, 2026-09-30), never assumed:
  plays        the largest list of dicts under a key naming plays
  event type   the string-valued type key (typeDescKey-like); shot events
               are the plays whose type names a shot or a goal
  event id     an integer key named eventId (an event without one is skipped
               and counted — rows are keyed on it)
  period       an integer "period"/"number" key, top-level or in a nested
               dict naming the period; its period type likewise
  time         a "timeInPeriod"-like "mm:ss" key
  x / y        numeric xCoord / yCoord-like keys (play or details)
  shot type    a key naming a shot type — OPTIONAL by ruling
  shooter      shootingPlayerId / scoringPlayerId-like keys
  goalie       a goalieInNetId-like key
  situation    a key naming the situation (situationCode-like), stored raw
  owner team   an eventOwnerTeamId-like key -> owner_side
  teams        the payload's home*/away* dicts with an integer id
  roster       a list under a key naming roster whose dicts carry a player id
               and a team id -> the SHOOTER's side
The receipt prints the keys actually used and, per event type, how often the
shooter's roster side agrees with the owner side (law-1 receipt: the
blocked-shot owner convention is read, not assumed).

Writes: nhl_shot_events only (upsert on game + event id; a refetch never
blanks a stored value). Never deletes.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Callable

from src.ingestion.nhl_goalies import BASE, KEEP_GAME_TYPES, Fetch, http_json, match_game, schedule_games, walk

PLAYS = re.compile(r"^plays?$", re.I)
TYPE = re.compile(r"typedesc|type.?key|eventtype|typecode", re.I)
SHOTISH = re.compile(r"shot|goal", re.I)
EVENT_ID = re.compile(r"^event.?id$", re.I)
PERIOD_DICT = re.compile(r"period", re.I)
PERIOD_NUM = re.compile(r"^(period|number|periodnumber)$", re.I)
PERIOD_TYPE = re.compile(r"^period.?type$", re.I)
TIME_IN_PERIOD = re.compile(r"^time.?in.?period$", re.I)
X = re.compile(r"^x(coord)?$", re.I)
Y = re.compile(r"^y(coord)?$", re.I)
SHOTTYPE = re.compile(r"shot.?type", re.I)
SHOOTER_KEYS = (re.compile(r"^shooting.?player.?id$", re.I), re.compile(r"^scoring.?player.?id$", re.I),
                re.compile(r"^shooter.?(player)?.?id$", re.I))
GOALIE_IN_NET = re.compile(r"^goalie.*id$", re.I)
SITUATION = re.compile(r"situation", re.I)
OWNER = re.compile(r"owner.*team.*id$", re.I)
ZONE = re.compile(r"^zone.?code$", re.I)
DEFENDING = re.compile(r"defending.?side", re.I)
ROSTER = re.compile(r"roster", re.I)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _int(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _str(v) -> str | None:
    if isinstance(v, str) and v != "":
        return v
    if _int(v) is not None:
        return str(v)
    return None


def find_plays(payload) -> list[dict]:
    best: list[dict] = []
    for _, d in walk(payload or {}):
        for k, v in d.items():
            if PLAYS.match(k) and isinstance(v, list) and len(v) > len(best) \
                    and all(isinstance(x, dict) for x in v):
                best = v
    return best


def _flat(play: dict) -> dict:
    """The play's own keys plus its nested dicts' keys (details etc.);
    the play's own key wins a clash."""
    out = dict(play)
    for v in play.values():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                out.setdefault(k2, v2)
    return out


def _first(f: dict, rx, ok=lambda v: v not in (None, "")) -> tuple[str | None, object]:
    for k, v in f.items():
        if rx.search(k) and ok(v):
            return k, v
    return None, None


def _mmss(v) -> int | None:
    m = re.fullmatch(r"(\d+):(\d{2})", str(v or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def game_teams(payload) -> dict[int, dict]:
    """team id -> {side, abbrev} from the payload's top-level home*/away* dicts."""
    out: dict[int, dict] = {}
    for k, v in (payload or {}).items():
        if not isinstance(v, dict) or _int(v.get("id")) is None:
            continue
        side = "home" if k.lower().startswith("home") else "away" if k.lower().startswith("away") else None
        if side:
            out[v["id"]] = {"side": side, "abbrev": v.get("abbrev") if isinstance(v.get("abbrev"), str) else None}
    return out if {t["side"] for t in out.values()} == {"home", "away"} and len(out) == 2 else {}


def roster_teams(payload) -> dict[int, int]:
    """player id -> team id from roster lists (dicts carrying both ids)."""
    out: dict[int, int] = {}
    for _, d in walk(payload or {}):
        for k, v in d.items():
            if ROSTER.search(k) and isinstance(v, list):
                for r in v:
                    if isinstance(r, dict):
                        pid, tid = _int(r.get("playerId")), _int(r.get("teamId"))
                        if pid is not None and tid is not None:
                            out[pid] = tid
    return out


def _period(play: dict) -> tuple[int | None, str | None, list[str]]:
    used = []
    num = next((_int(v) for k, v in play.items() if PERIOD_NUM.match(k) and _int(v) is not None), None)
    ptype = next((v for k, v in play.items() if PERIOD_TYPE.match(k) and isinstance(v, str)), None)
    if num is not None:
        used.append("period<-(play)")
    for k, v in play.items():
        if isinstance(v, dict) and PERIOD_DICT.search(k):
            if num is None:
                num = next((_int(x) for k2, x in v.items() if PERIOD_NUM.match(k2) and _int(x) is not None), None)
                if num is not None:
                    used.append(f"period<-{k}")
            if ptype is None:
                ptype = next((x for k2, x in v.items() if PERIOD_TYPE.match(k2) and isinstance(x, str)), None)
    return num, ptype, used


def read_events(payload) -> tuple[list[dict] | None, dict]:
    """(event rows, receipt). None when the payload has no plays or no type
    key (the game is REFUSED — counted, never guessed)."""
    plays = find_plays(payload)
    rec = {"keys_used": Counter(), "skipped_no_event_id": 0, "teams_found": False, "roster_players": 0}
    type_key = None
    for pl in plays:
        type_key = next((k for k, v in pl.items() if TYPE.search(k) and isinstance(v, str)), None)
        if type_key:
            break
    if not plays or type_key is None:
        return None, rec
    teams = game_teams(payload)
    roster = roster_teams(payload)
    rec["teams_found"], rec["roster_players"] = bool(teams), len(roster)
    rows = []
    for p in plays:
        et = p.get(type_key)
        if not isinstance(et, str) or not SHOTISH.search(et):
            continue
        f = _flat(p)
        ek, eid = _first(f, EVENT_ID, lambda v: _int(v) is not None)
        if ek is None:
            rec["skipped_no_event_id"] += 1
            continue
        period, ptype, pused = _period(p)
        xk, x = _first(f, X, _num)
        yk, y = _first(f, Y, _num)
        tk, st = _first(f, SHOTTYPE, lambda v: isinstance(v, str) and v != "")
        shooter, sk = None, None
        for rx in SHOOTER_KEYS:
            sk, shooter = _first(f, rx, lambda v: _int(v) is not None)
            if sk:
                break
        gk, gid = _first(f, GOALIE_IN_NET, lambda v: _int(v) is not None)
        sitk, sit = _first(f, SITUATION, lambda v: _str(v) is not None)
        ok_, owner = _first(f, OWNER, lambda v: _int(v) is not None)
        tik, tip = _first(f, TIME_IN_PERIOD)
        zk, zone = _first(f, ZONE, lambda v: isinstance(v, str) and v != "")
        dk, dside = _first(f, DEFENDING, lambda v: isinstance(v, str) and v != "")
        owner_side = teams.get(owner, {}).get("side") if owner is not None else None
        shooter_team = roster.get(shooter) if shooter is not None else None
        side = teams.get(shooter_team, {}).get("side") if shooter_team is not None else None
        for name, k in (("event_id", ek), ("type", type_key), ("x", xk), ("y", yk), ("shot_type", tk),
                        ("shooter", sk), ("goalie", gk), ("situation", sitk), ("owner", ok_),
                        ("time", tik), ("zone", zk), ("defending", dk)):
            if k:
                rec["keys_used"][f"{name}<-{k}"] += 1
        for u in pused:
            rec["keys_used"][u] += 1
        rows.append({"event_id": eid, "event_type": et, "period": period, "period_type": ptype,
                     "time_in_period_s": _mmss(tip), "shot_type": st, "side": side, "owner_side": owner_side,
                     "team_abbrev": teams.get(shooter_team, {}).get("abbrev") if shooter_team is not None else None,
                     "shooter_id": shooter, "goalie_id": gid, "x": float(x) if x is not None else None,
                     "y": float(y) if y is not None else None, "zone_code": zone,
                     "home_defending_side": dside, "situation_code": _str(sit)})
    return rows, rec


def goalie_links(s) -> dict[int, int | None]:
    """nhl_game_id -> our match id from the goalie-sync mapping; a game whose
    goalie rows disagree on the match maps to None (refused)."""
    from sqlalchemy import select

    from src.db.schema import NHLGoalieAppearance

    out: dict[int, set] = {}
    for gid, mid in s.execute(select(NHLGoalieAppearance.nhl_game_id, NHLGoalieAppearance.match_id)
                              .where(NHLGoalieAppearance.match_id.is_not(None)).distinct()):
        out.setdefault(gid, set()).add(mid)
    return {g: (next(iter(m)) if len(m) == 1 else None) for g, m in out.items()}


def sync(start: date, end: date, fetch: Fetch = http_json, sleep: float = 0.25,
         refresh: bool = False, dry_run: bool = False, now: datetime | None = None,
         tolerance_hours: int = 12,
         progress: Callable[[str], None] | None = None) -> dict:
    """Walk the schedule, map each kept finished game to our match (goalie
    link first, else the matcher), fetch play-by-play for games without
    stored events, upsert shot events, then relink. Returns the receipt."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import NHLShotEvent
    from src.timeutil import utc_now_naive

    now = now or utc_now_naive()
    say = progress or (lambda _m: None)
    rc, types, keys = Counter(), Counter(), Counter()
    agree: dict[str, Counter] = {}
    refused: list[int] = []
    seen: dict[int, dict] = {}
    d = start
    while d <= end:
        code, payload = fetch(f"{BASE}/v1/schedule/{d.isoformat()}")
        rc["schedule_calls"] += 1
        rc[f"schedule_http_{code}"] += 1
        for g in schedule_games(payload):
            if g["start"] is not None and start <= g["start"].date() <= end + timedelta(days=1):
                seen.setdefault(g["id"], g)
        d += timedelta(days=7)
        if sleep:
            time.sleep(sleep)
    games = sorted(seen.values(), key=lambda g: g["start"])
    rc["games_found"] = len(games)
    with session_scope() as s:
        have = {gid for (gid,) in s.execute(select(NHLShotEvent.nhl_game_id).distinct())}
        links = goalie_links(s)
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
        if g["id"] in links:
            match_id = links[g["id"]]
            rc["mapped_via_goalie_link" if match_id else "refused_goalie_link_conflict"] += 1
        else:
            with session_scope() as s:
                m = match_game(s, g, tolerance_hours)
                match_id = m.id if m is not None else None
            rc["mapped_via_matcher" if match_id else "not_in_our_db"] += 1
        if g["id"] in have and not refresh:
            rc["skipped_already_stored"] += 1
            continue
        code, payload = fetch(f"{BASE}/v1/gamecenter/{g['id']}/play-by-play")
        rc["pbp_calls"] += 1
        rc[f"pbp_http_{code}"] += 1
        if sleep:
            time.sleep(sleep)
        rows, rec = read_events(payload)
        keys.update(rec["keys_used"])
        rc["events_skipped_no_event_id"] += rec["skipped_no_event_id"]
        if rows is None:
            rc["refused_no_plays"] += 1
            refused.append(g["id"])
            continue
        if not rec["teams_found"]:
            rc["games_teams_not_found"] += 1
        if not rows:
            rc["games_zero_shot_events"] += 1
        for r in rows:
            types[r["event_type"]] += 1
            if r["side"] and r["owner_side"]:
                agree.setdefault(r["event_type"], Counter())["agree" if r["side"] == r["owner_side"]
                                                             else "disagree"] += 1
        if not dry_run:
            _upsert(g, match_id, rows)
        rc["events_written" if not dry_run else "events_would_write"] += len(rows)
        say(f"  {g['start']:%Y-%m-%d} game {g['id']}: {len(rows)} shot events"
            + (f" -> match {match_id}" if match_id else " (not in our DB)"))
    rc["relinked_events"] = 0 if dry_run else relink(tolerance_hours=None)
    return {"counts": dict(rc), "event_types": dict(types), "keys_used": dict(keys.most_common(24)),
            "side_vs_owner": {k: dict(v) for k, v in sorted(agree.items())}, "refused": refused[:20]}


def relink(tolerance_hours: int | None = None) -> int:
    """Link stored shot rows with no match to the goalie-sync mapping of
    their game (DB-only). Returns rows linked."""
    from sqlalchemy import select, update

    from src.db.database import session_scope
    from src.db.schema import NHLShotEvent

    n = 0
    with session_scope() as s:
        links = goalie_links(s)
        todo = {gid for (gid,) in s.execute(select(NHLShotEvent.nhl_game_id)
                                            .where(NHLShotEvent.match_id.is_(None)).distinct())}
        for gid in todo:
            mid = links.get(gid)
            if mid:
                n += s.execute(update(NHLShotEvent).where(NHLShotEvent.nhl_game_id == gid,
                                                          NHLShotEvent.match_id.is_(None))
                               .values(match_id=mid)).rowcount or 0
    return n


def _upsert(g: dict, match_id: int | None, rows: list[dict]) -> None:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import NHLShotEvent
    from src.timeutil import utc_now_naive

    with session_scope() as s:
        cur = {e.event_id: e for e in s.execute(select(NHLShotEvent).where(
            NHLShotEvent.nhl_game_id == g["id"])).scalars()}
        for r in rows:
            vals = dict(match_id=match_id, game_start=g["start"], game_type=g["game_type"],
                        captured_at=utc_now_naive(), **{k: v for k, v in r.items() if k != "event_id"})
            e = cur.get(r["event_id"])
            if e is None:
                e = NHLShotEvent(nhl_game_id=g["id"], event_id=r["event_id"], **vals)
                s.add(e)
                cur[r["event_id"]] = e
            else:
                for k, v in vals.items():
                    if v is not None:          # a refetch never blanks a stored value
                        setattr(e, k, v)


FIELDS = ("x", "y", "shot_type", "shooter_id", "situation_code", "side", "owner_side", "period",
          "time_in_period_s", "goalie_id")

# The probe's FEEDABLE thresholds (scripts/nhl_pbp_probe.py P1-P6, declared
# 2026-09-30 before any run; denominators: P1/P6 the v6 GATE stream's games —
# ruled 2026-10-02; all finished games are reported beside it, not judged —
# P2-P5 ALL stored shot events). The ingest receipt reports against the SAME bars.
FEEDABLE = {"games_with_events": 95.0, "xy": 95.0, "shot_type": 90.0, "shooter_id": 95.0,
            "situation_code": 90.0}


def gate_stream_ids() -> dict[str, set[int]]:
    """The v6 GATE stream's games by season: nhl_backtest's own load_games +
    build_stream (train 2024, test 2025, preseason cut), so the receipt's gate
    denominator is the gate's, never a re-derivation."""
    from src.walters.nhl_backtest import TEST_SEASON, TRAIN_SEASON, build_stream, load_games

    st = build_stream(load_games())
    return {TRAIN_SEASON: {g.match_id for g in st.train if g.match_id is not None},
            TEST_SEASON: {g.match_id for g in st.test if g.match_id is not None}}


def feedable_lines(cov: dict) -> list[str]:
    """P1-P6 against the frozen bars, over the stored rows (the coverage
    receipt's verdict lines). Shot type is OPTIONAL by ruling (absent on
    blocked shots by nature): P3 is reported over all events and, for
    reading, over the non-blocked ones."""
    tot = Counter()
    for et, c in cov["by_type"].items():
        for k in ("n", "xy", "shot_type", "shooter_id", "situation_code"):
            tot[k] += c.get(k, 0)
        if "block" not in et.lower():
            tot["n_unblocked"] += c.get("n", 0)
            tot["shot_type_unblocked"] += c.get("shot_type", 0)
    pct = lambda a, b: (tot[a] / tot[b] * 100) if tot[b] else 0.0
    # ARCHITECT 2026-10-02 (shot-sync receipt): "the coverage receipt reports
    # both denominators (all finished; gate stream) and the thresholds apply to
    # the gate stream." All-finished includes PRESEASON games the gate excludes
    # by construction; it is reported, never judged.
    fin = sum(b.get("finished", 0) for b in cov["by_season"].values())
    withs = sum(b.get("with_shots", 0) for b in cov["by_season"].values())
    gate = cov.get("gate_stream") or {}
    gfin = sum(b["games"] for b in gate.values())
    gwith = sum(b["with_shots"] for b in gate.values())
    p1 = gwith / gfin * 100 if gfin else 0.0
    rows = [("P1 shot events (games, GATE stream)", p1, FEEDABLE["games_with_events"]),
            ("P2 location x+y", pct("xy", "n"), FEEDABLE["xy"]),
            ("P3 shot type (all events)", pct("shot_type", "n"), FEEDABLE["shot_type"]),
            ("P4 shooter", pct("shooter_id", "n"), FEEDABLE["shooter_id"]),
            ("P5 situation", pct("situation_code", "n"), FEEDABLE["situation_code"])]
    out = [f"{k}: {v:.1f}% [{'FEEDABLE' if v >= bar else 'NOT'} >= {bar:g}%]" for k, v, bar in rows]
    out.insert(1, f"P1 read, ALL finished (preseason included; not judged): {withs}/{fin} = "
                  f"{(withs / fin * 100) if fin else 0.0:.1f}%")
    out.append(f"P3 read: shot type on non-blocked events {pct('shot_type_unblocked', 'n_unblocked'):.1f}% "
               "(optional by ruling; blocked shots carry none by nature)")
    p6 = [season for season, b in gate.items()
          if not b["games"] or b["with_shots"] / b["games"] * 100 < FEEDABLE["games_with_events"]]
    out.append("P6 depth (P1 in every GATE-stream season: "
               + ", ".join(f"{k} {b['with_shots']}/{b['games']}" for k, b in sorted(gate.items())) + "): "
               + ("FEEDABLE" if gate and not p6 else "NOT — " + (", ".join(p6) or "no gate stream")))
    return out


def coverage() -> dict:
    """Receipt (lane (1)): of OUR finished NHL games (competition NHL), how
    many carry shot events — by season — plus field completeness by event
    type, the side/owner agreement, and stored games with no link."""
    from sqlalchemy import func, select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, NHLGoalieAppearance, NHLShotEvent, Sport

    with session_scope() as s:
        ours = s.execute(select(Match.id, Match.season).join(Competition, Match.competition_id == Competition.id)
                         .where(Match.sport == Sport.NHL, Competition.code == "NHL",
                                Match.status == MatchStatus.FINISHED)).all()
        per_match = dict(s.execute(select(NHLShotEvent.match_id, func.count(NHLShotEvent.id))
                                   .where(NHLShotEvent.match_id.is_not(None))
                                   .group_by(NHLShotEvent.match_id)).all())
        goalie_linked = {m for (m,) in s.execute(select(NHLGoalieAppearance.match_id)
                                                 .where(NHLGoalieAppearance.match_id.is_not(None)).distinct())}
        cols = [getattr(NHLShotEvent, f) for f in FIELDS]
        by_type: dict[str, Counter] = {}
        for row in s.execute(select(NHLShotEvent.event_type, *cols)):
            c = by_type.setdefault(row[0], Counter())
            c["n"] += 1
            for f, v in zip(FIELDS, row[1:]):
                c[f] += v is not None
            c["xy"] += row[1 + FIELDS.index("x")] is not None and row[1 + FIELDS.index("y")] is not None
            side, owner = row[1 + FIELDS.index("side")], row[1 + FIELDS.index("owner_side")]
            if side and owner:
                c["side_agrees_owner" if side == owner else "side_disagrees_owner"] += 1
        unlinked = dict(s.execute(select(NHLShotEvent.game_type, func.count(func.distinct(NHLShotEvent.nhl_game_id)))
                                  .where(NHLShotEvent.match_id.is_(None))
                                  .group_by(NHLShotEvent.game_type)).all())
        games = s.execute(select(func.count(func.distinct(NHLShotEvent.nhl_game_id)))).scalar()
        total = s.execute(select(func.count(NHLShotEvent.id))).scalar()
    by = {}
    for mid, season in ours:
        b = by.setdefault(season, Counter())
        b["finished"] += 1
        b["with_shots"] += mid in per_match
        b["events"] += per_match.get(mid, 0)
        b["goalie_linked_no_shots"] += mid in goalie_linked and mid not in per_match
    gate = {season: {"games": len(ids), "with_shots": sum(1 for m in ids if m in per_match)}
            for season, ids in sorted(gate_stream_ids().items())}
    return {"by_season": {k: dict(v) for k, v in sorted(by.items())}, "gate_stream": gate,
            "by_type": {k: dict(v) for k, v in sorted(by_type.items())},
            "unlinked_games_by_game_type": {str(k): v for k, v in sorted(unlinked.items(), key=str)},
            "games": games, "rows": total}
