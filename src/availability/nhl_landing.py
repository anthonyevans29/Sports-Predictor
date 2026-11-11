"""
THE NHL LANDING FEED (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 3(b); 2026-11-05, addendum 258 item 2(2);
2026-11-11 11:40 ET, addendum 340; 11:55 ET, addendum 341 item 2; lane availability-record, #830; #835 item 2): the
availability record's second feed, source `nhl_api_landing`, and its watch.

THE RULING, 252 item 3(b), verbatim: "THE NHL LANDING READ (source `nhl_api_landing`): per game of the NHL day (the
probe's schedule read: GET /v1/schedule/<date>, game types 2 and 3), the landing page at the probe's offsets (T-120,
T-90, T-60, T-45, T-35, T-30, T-15, T-0) — each poll an observation with its poll_label — asserting projected_starter
per side from matchup.goalieComparison.<side>Team.leaders[0] (playerId, name beside it) EXACTLY as
scripts/nhl_leaders_order_receipt.py reads it, and the boxscore at T+20 asserting eventual_starter (the goalie with
toi above zero; two in net = two rows, flagged; none = an `empty` observation) — post hoc, kind-labelled, never a
pregame fact. The polls run under a watch on the host (an `availability-observe` timer every five minutes, the
cup-observe pattern), each poll stamped by our clock; a poll more than five minutes past its time is a `missed` row.
The receipt's reading of leaders[0]'s reliability STANDS as read on #105; this feed records what the page asserted and
when, which is a fact whatever the page's reliability, and it is the free NHL pregame record from the day it runs."

HOW IT READS (law 1: every name is the code's own; this build cannot reach api-web.nhle.com, so no field is assumed
beyond what the probe, the receipt and the ingest already read):
- THE SCHEDULE (addendum 340 item 4, verbatim in part: "at most hourly, kept per NHL day [...] It is support data, not
  an observation: it asserts nothing about who plays, so it writes no row in availability_observations; its payload is
  kept beside the others under logs/availability/nhl_api_landing/<date>/ with its sha256. A moved start recomputes the
  polls not yet written; a written poll is never touched. A failed schedule read invents nothing: no missed rows for
  games it could not know; one log line per tick and one notice per NHL day."): GET {BASE}/v1/schedule/<NHL day>,
  parsed by src.ingestion.nhl_goalies.schedule_games (the call and the parse nhl-goalie-sync and the timing probe make);
  the games of the NHL day [<day> 10:00Z, <day>+1 10:00Z) of game types 2 and 3 (the probe's day_games). The answer is
  kept as logs/availability/nhl_api_landing/<NHL day>/<YYYYmmddTHHMMSS>Z-<sha256, first 16 hex>-schedule.json only
  when its bytes differ from the newest kept for that day; a check stamp beside them
  (`schedule.checked`, "<instant> <sha256>") says when the day was last read, so a day read within SCHEDULE_TTL is
  not read again. A failed read uses the newest kept answer for that day if one exists (the games it already knew),
  else knows no game; the first failed read of an NHL day creates `schedule.notice` beside them and makes the tick's
  exit 1 (the unit's OnFailure pages it once), every later one prints its line and exits 0.
- THE WATCH'S WINDOW: the games whose scheduled start is within [now - LOOKBACK, now + AHEAD], read from the NHL days
  that window touches. AHEAD is T-120 (the first poll); LOOKBACK covers H0-3's buffer (no tick 04:00-05:59Z: a poll
  scheduled there is a `missed` row written by the first tick after it, addendum 340 item 3) and a T+20 read.
- THE POLLS, per game: POLLS (the probe's offsets and its T+20). A poll is WRITTEN once the store holds an observation
  of this source at its endpoint (the game's landing or boxscore URL, which carries the gameId) with its poll_label,
  whatever kickoff it was scheduled against: "a moved start recomputes the polls not yet written; a written poll is
  never touched" (340 item 4). A poll not written whose time (the schedule's start minus its offset) has passed is DUE:
  more than MISSED_AFTER past its time it is a `missed` row and no call (252 item 3(b): "a poll more than five minutes
  past its time is a `missed` row"); else it is asked once, stamped by our clock after the body has arrived, `late`
  when that is more than LATE_LIMIT after its time.
- THE LANDING (T-120 .. T-0): per side, leaders[0] read by the receipt's OWN `leader0` (scripts/nhl_leaders_order_
  receipt.py, loaded from its file, never copied): playerId and the name beside it. A side with no leaders[0] (no
  goalieComparison, no leaders list, an empty list, no integer playerId) asserts nothing and is counted with the
  receipt's reason; a landing with neither side is `empty`. Each assertion: kind projected_starter, player_id NULL
  (254 item 2(3): every NHL player unmapped, counted), source_player_id the playerId, player_name verbatim, the side's
  team (below), match_id (below), attrs {side, source_match_id: the gameId}, source_stamp NULL (252 item 1(b): "the
  NHL landing gives none").
- THE BOXSCORE (T+20): read by the ingest's OWN src.ingestion.nhl_goalies.boxscore_goalies (its sided goalie lists, its
  toi in seconds). Per side each goalie with toi above zero is an eventual_starter assertion (attrs: side,
  source_match_id, toi_seconds, two_in_net: True when the side had two or more above zero, toi_unread: the side's
  goalies whose toi the ingest could not read); none on either side is `empty`; a boxscore the ingest refuses (its
  goalie lists not sided one home + one away) is `failed` with the reason, its payload kept. eventual_starter is post
  hoc (record.POST_HOC_KINDS) and, slot per kind (addendum 258 item 2(3)), never closes a projected_starter.
- THE TEAM (ARCHITECT 2026-11-11 11:55 ET, addendum 341 item 2, verbatim in part: "the landing feed resolves team_id
  by THAT path, unchanged — a side maps only when its candidates resolve to exactly one of the NHL competition's
  teams; otherwise team_id NULL with source_team verbatim and the observation `partial`"): the side's candidate names
  are nhl_goalies.team_names() of the schedule's side (the API's full name, then placeName + commonName, then
  NAME_ALIASES, accents stripped), each through the shared normaliser (match_lookup.normalize_team_name) against the
  stored names of the teams of the NHL's matches (the rows find_match compares); in the matcher's own order a
  candidate that resolves to exactly one team maps the side, one that resolves to none or to more than one is passed
  over ("The matcher still refuses ambiguity at every candidate; an alias only adds a name to try"), and a side no
  candidate resolves stays unmapped. source_team is the schedule's abbrev for the side (the source's own text,
  stable across polls: the record's team identity), else its first candidate name.
- THE MATCH: the one match nhl_goalies' link holds for the gameId (nhl_goalie_appearances.match_id), else
  nhl_goalies.match_game AS IT STANDS (find_match: the NHL's rows within 12 h by both names, a SCHEDULED row included,
  CANCELLED and STALE_ORPHAN not, ambiguity refused; addendum 341 item 2), else NULL with attrs.source_match_id
  carrying the game. A team or the match left unmapped makes an asserting observation `partial` (254 item 2(7)).
- THE PAYLOAD: a 200's bytes kept under logs/availability/nhl_api_landing/<UTC date of the fetch>/<HHMMSS>Z-<sha256,
  first 16 hex>-<gameId>_<landing|boxscore>_<label>.json, created exclusively; never under data/, never mirrored.
- THE STORE: record.write_observation, the only writer: one observation per poll (its endpoint, match_id, kickoff_at
  = the schedule's start as this tick knew it, poll_label, scheduled_at, fetched_at, http_status, payload_sha256,
  payload_path, status, late, error) with its assertions, append-only. The poll's key, #835 item 2 (addendum 258 item
  2(2)): (source, endpoint, scheduled_at), a partial unique index and an insert guard (schema.py), so an unmapped poll
  written twice is one row and one "already", and a later mapped write of it is "already" too.
- THE LOCK (the cup-observe pattern, addendum 340 item 3): a tick plans mode=ro; with no poll due it calls nothing
  (the schedule read apart, at most hourly, item 4) and takes no lock; with a poll due it takes the chains' DB lock
  (sp_common.sync_lock) and plans again under it, so two overlapping ticks never ask one poll twice.

WHAT IT NEVER DOES (252 item 5): no model change, no Desk input, no row in any existing table, no provider call from a
closing run (the watch is its own unit), no backdating, no deletion, no payload under data/, no secret in an
endpoint (the NHL API takes no key). No name matching for players (254 item 2(3)); no alias or tla of its own (341).

    python cli.py availability-nhl-observe [--dry-run]
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.availability import record as rec
from src.ingestion import nhl_goalies as ng

SOURCE = "nhl_api_landing"
SPORT = "nhl"
BASE = ng.BASE                                         # https://api-web.nhle.com, the API nhl-goalie-sync reads
# THE POLLS (252 item 3(b): "the probe's offsets (T-120, T-90, T-60, T-45, T-35, T-30, T-15, T-0)" and "the boxscore
# at T+20"): (label, minutes before the scheduled start, endpoint). Equal to scripts/nhl_starter_timing_probe.py's
# OFFSETS and EVENTUAL and to the leaders receipt's PREGAME and EVENTUAL (tests pin it).
LANDING, BOXSCORE = "landing", "boxscore"
PREGAME = (("T-120", 120), ("T-90", 90), ("T-60", 60), ("T-45", 45), ("T-35", 35), ("T-30", 30), ("T-15", 15),
           ("T-0", 0))
EVENTUAL = ("T+20", -20)
POLLS = tuple((label, off, LANDING) for label, off in PREGAME) + ((EVENTUAL[0], EVENTUAL[1], BOXSCORE),)
DAY_CUT_UTC = 10                                       # the probe's NHL day: [date 10:00Z, date+1 10:00Z)
GAME_TYPES = frozenset(ng.KEEP_GAME_TYPES)             # 2 regular season, 3 playoffs (252 item 3(b))
MISSED_AFTER = timedelta(minutes=5)                    # 252 item 3(b): "more than five minutes past its time"
LATE_LIMIT = timedelta(minutes=5)                      # an answer stamped more than this after its time is `late`
AHEAD = timedelta(minutes=PREGAME[0][1])               # the first poll, T-120
LOOKBACK = timedelta(hours=6)                          # H0-3's 04:00-05:59Z gap and the T+20 read, with room
SCHEDULE_TTL = timedelta(hours=1)                      # 340 item 4: "at most hourly, kept per NHL day"
TIMEOUT = (10, 30)                                     # (connect, read) seconds
USER_AGENT = "sports-predictor availability-record (nhl landing)"
CHECKED, NOTICE = "schedule.checked", "schedule.notice"
POLL_GUARD = "trg_availability_observations_poll_guard"  # #835 item 2: the store's poll key must be migrated
POLL_KEY_INDEX = "uq_avail_obs_source_endpoint_scheduled"
REPO = Path(__file__).resolve().parents[2]
PAYLOAD_BASE = REPO                                    # the kept payloads' root (tests point it at a tmp dir)
RECEIPT_SCRIPT = REPO / "scripts" / "nhl_leaders_order_receipt.py"
SIDES = ("away", "home")                               # the receipt's order


class Refused(Exception):
    pass


# ---- the receipt's own reader ------------------------------------------------------------------------------------------

def _receipt():
    """scripts/nhl_leaders_order_receipt.py, loaded from its file (the kalshi_pool precedent): its `leader0` is THE
    reading 252 item 3(b) names ("EXACTLY as scripts/nhl_leaders_order_receipt.py reads it"); the script is unchanged."""
    name = "nhl_leaders_order_receipt"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, RECEIPT_SCRIPT)
    if spec is None or spec.loader is None:
        raise Refused(f"REFUSED: {RECEIPT_SCRIPT} is not loadable: the leaders reading is the receipt's own")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


def leader(landing, side: str) -> tuple[tuple[int, str | None] | None, str]:
    """((playerId, name), "") of the side's leaders[0], or (None, why it is missing): the receipt's leader0."""
    return _receipt().leader0(ng, landing, side)


# ---- times, urls -------------------------------------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def nhl_day(t: datetime) -> date:
    """The NHL day an instant falls in: [date 10:00Z, date+1 10:00Z) is `date` (the probe's DAY_CUT_UTC)."""
    return (t - timedelta(hours=DAY_CUT_UTC)).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    lo = datetime.combine(day, datetime.min.time()) + timedelta(hours=DAY_CUT_UTC)
    return lo, lo + timedelta(days=1)


def days_of(lo: datetime, hi: datetime) -> list[date]:
    """The NHL days the window [lo, hi] touches, in order."""
    out, d = [], nhl_day(lo)
    while d <= nhl_day(hi):
        out.append(d)
        d += timedelta(days=1)
    return out


def schedule_url(day: date) -> str:
    return f"{BASE}/v1/schedule/{day.isoformat()}"


def game_url(game_id: int, endpoint: str) -> str:
    return f"{BASE}/v1/gamecenter/{int(game_id)}/{endpoint}"


def _z(d: datetime | None) -> str:
    return d.isoformat(timespec="seconds") + "Z" if d else "—"


def _scrub(text) -> str:
    return rec.redact(str(text)) or ""


# ---- the HTTP read -----------------------------------------------------------------------------------------------------

@dataclass
class Answer:
    """One GET: its status, its bytes, and OUR stamp taken after the body arrived (or at the raise)."""
    url: str
    at: datetime
    status: int | None = None
    body: bytes | None = None
    error: str | None = None


def get(url: str, *, http_get=None, now_fn=None) -> Answer:
    """One GET, never raising for the call: a raise is an Answer with its error (redacted), a non-200 an Answer with
    its status and an error naming it. The stamp is taken after the body has been read in full (a 200's fetched_at
    is when we HAD the answer, the nflverse rule of Codex on #841, round 2)."""
    now_fn = now_fn or _now
    if http_get is None:
        import requests
        http_get = requests.get
    try:
        r = http_get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        code = int(r.status_code)
        body = r.content if code == 200 else None
    except Exception as e:  # noqa: BLE001 - a raised call is a row, never a stop (252 item 1(a))
        return Answer(url, now_fn(), error=_scrub(f"{type(e).__name__}: {e}")[:256])
    at = now_fn()
    if code != 200:
        return Answer(url, at, status=code, error=f"HTTP {code} from {url} (refused)")
    return Answer(url, at, status=code, body=body if isinstance(body, bytes) else bytes(body or b""))


def _json(body: bytes):
    try:
        return json.loads(body.decode("utf-8")), None
    except (UnicodeDecodeError, ValueError) as e:
        return None, f"the answer does not parse as JSON ({type(e).__name__})"


# ---- kept files --------------------------------------------------------------------------------------------------------

def _rel_dir(day: date) -> str:
    return "/".join((*rec.PAYLOAD_ROOT, SOURCE, day.isoformat()))


def _keep(rel_dir: str, name: str, body: bytes, sha: str) -> tuple[str, bool]:
    """(the relative path, created): the bytes at <rel_dir>/<name>, created EXCLUSIVELY (never over another file); a
    file already there holding exactly these bytes is reused (created False); other bytes there are Refused (the kept
    evidence is never overwritten). The writer's payload_path rule is checked before anything is made."""
    rel = f"{rel_dir}/{name}"
    why = rec.payload_path_refusal(rel, SOURCE)
    if why:
        raise Refused(f"REFUSED: {why}; nothing kept")
    final = PAYLOAD_BASE / rel
    final.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(final, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if hashlib.sha256(final.read_bytes()).hexdigest() == sha:
            return rel, False
        raise Refused(f"REFUSED: {final.name} already holds other bytes: the kept evidence is never overwritten") \
            from None
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(body)
    except BaseException:
        final.unlink(missing_ok=True)
        raise
    return rel, True


def _drop(rel: str | None) -> None:
    """Remove a payload THIS run created and no row names (a write the store answered "already"): never an orphan."""
    if rel:
        (PAYLOAD_BASE / rel).unlink(missing_ok=True)


# ---- the schedule (support data: no row) -------------------------------------------------------------------------------

@dataclass
class Schedule:
    day: date
    games: list = field(default_factory=list)           # nhl_goalies.schedule_games rows of the NHL day, types 2/3
    read: str = "kept"                                   # kept (fresh) | read (unchanged) | read (new) | failed | none
    path: str | None = None
    sha: str | None = None
    checked_at: datetime | None = None
    error: str | None = None
    notice: bool = False                                 # this tick's failure is the NHL day's first: the notice


def _side_text(t) -> str | None:
    """A side's own team text, VERBATIM (accents kept): its abbrev, else its full name, else placeName + commonName."""
    if not isinstance(t, dict):
        return None
    for v in (t.get("abbrev"), t.get("name"), t.get("fullName")):
        if ng._text(v):
            return ng._text(v)
    place, common = ng._text(t.get("placeName")), ng._text(t.get("commonName"))
    return f"{place} {common}" if place and common else None


def day_games(payload, day: date) -> list[dict]:
    """The schedule's games of the NHL day, types 2/3, in start order (the probe's day_games), each with
    `home_text` / `away_text`: the side's own team text verbatim (_side_text), the record's source_team."""
    lo, hi = day_bounds(day)
    out = [g for g in ng.schedule_games(payload) if g["start"] is not None and lo <= g["start"] < hi
           and g["game_type"] in GAME_TYPES]
    raw: dict = {}
    for _, d in ng.walk(payload or {}):                  # the dicts schedule_games read, by the game's id
        if isinstance(d.get("id"), int) and d["id"] not in raw:
            home = next((v for k, v in d.items() if k.lower().startswith("home") and isinstance(v, dict)), None)
            away = next((v for k, v in d.items() if k.lower().startswith("away") and isinstance(v, dict)), None)
            if home is not None and away is not None:
                raw[d["id"]] = (home, away)
    for g in out:
        home, away = raw.get(g["id"], (None, None))
        g["home_text"], g["away_text"] = _side_text(home), _side_text(away)
    return sorted(out, key=lambda g: (g["start"], g["id"]))


def _kept_schedules(day: date) -> list[Path]:
    d = PAYLOAD_BASE / _rel_dir(day)
    return sorted(d.glob("*Z-*-schedule.json")) if d.is_dir() else []


def _checked(day: date) -> tuple[datetime | None, str | None]:
    """(when the day was last read, the sha256 it answered or "failed"), from `schedule.checked`."""
    p = PAYLOAD_BASE / _rel_dir(day) / CHECKED
    try:
        at, sha = p.read_text(encoding="utf-8").split()
        return datetime.fromisoformat(at.rstrip("Z")), sha
    except (OSError, ValueError):
        return None, None


def _stamp_checked(day: date, at: datetime, sha: str) -> None:
    p = PAYLOAD_BASE / _rel_dir(day) / CHECKED
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(CHECKED + ".tmp")
    tmp.write_text(f"{_z(at)} {sha}\n", encoding="utf-8")
    os.replace(tmp, p)


def schedule(day: date, now: datetime, *, http_get=None, now_fn=None, keep: bool = True) -> Schedule:
    """The NHL day's games (the module docstring, THE SCHEDULE). `keep` False (a dry run) reads and keeps nothing."""
    kept = _kept_schedules(day)
    newest = kept[-1] if kept else None
    checked_at, checked_sha = _checked(day)
    sc = Schedule(day)
    known = None
    if newest is not None:
        sc.sha = hashlib.sha256(newest.read_bytes()).hexdigest()
        sc.path = newest.relative_to(PAYLOAD_BASE).as_posix()
        known, _ = _json(newest.read_bytes())
    # AT MOST HOURLY (340 item 4): a day read within the hour, answered or not, is not read again; the tick uses the
    # newest kept answer (the games it already knew), and a day whose last read failed says so on its line
    if checked_at is not None and now - checked_at < SCHEDULE_TTL and (checked_sha == "failed" or
                                                                       (known is not None and checked_sha == sc.sha)):
        sc.games, sc.checked_at = (day_games(known, day) if known is not None else []), checked_at
        if checked_sha == "failed":
            sc.read = f"last read FAILED at {_z(checked_at)}: the next read after {_z(checked_at + SCHEDULE_TTL)}"
        return sc
    a = get(schedule_url(day), http_get=http_get, now_fn=now_fn)
    payload, why = (_json(a.body) if a.error is None else (None, a.error))
    if payload is None:
        sc.read, sc.error = "failed", (why or "no answer")[:256]
        sc.games = day_games(known, day) if known is not None else []   # nothing invented (340 item 4)
        if keep:
            _stamp_checked(day, a.at, "failed")
            n = PAYLOAD_BASE / _rel_dir(day) / NOTICE
            n.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.close(os.open(n, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644))
                sc.notice = True
            except FileExistsError:
                pass
        return sc
    sha = hashlib.sha256(a.body).hexdigest()
    sc.games, sc.checked_at = day_games(payload, day), a.at
    if not keep:
        sc.read = "read (dry run: not kept)"
        return sc
    if sha == sc.sha:
        sc.read = "read (unchanged)"
    else:
        sc.path, _ = _keep(_rel_dir(day), f"{a.at:%Y%m%dT%H%M%S}Z-{sha[:16]}-schedule.json", a.body, sha)
        sc.sha, sc.read = sha, "read (new)"
    _stamp_checked(day, a.at, sha)
    return sc


# ---- the mapping (addendum 341 item 2) ---------------------------------------------------------------------------------

NHL_COMPETITION = "NHL"


def team_universe(s) -> dict:
    """{normalised name: {team ids}} over the NHL competition's teams: the teams of its stored matches (the host's 32,
    addendum 341 item 2, read from "the 2026 season's matches"; the rows find_match compares)."""
    from sqlalchemy import select, union

    from src.db.schema import Competition, Match, Sport, Team
    from src.ingestion.match_lookup import normalize_team_name
    nhl = select(Competition.id).where(Competition.sport == Sport.NHL, Competition.code == NHL_COMPETITION)
    mine = (Match.sport == Sport.NHL, Match.competition_id.in_(nhl))
    ids = union(select(Match.home_team_id.label("t")).where(*mine),
                select(Match.away_team_id.label("t")).where(*mine)).subquery()
    out: dict = {}
    for tid, name in s.execute(select(Team.id, Team.name).where(Team.id.in_(select(ids.c.t)))).all():
        n = normalize_team_name(name or "")
        if n:
            out.setdefault(n, set()).add(tid)
    return out


def resolve_team(universe: dict, candidates) -> int | None:
    """The team the side's candidates resolve to, or None (341 item 2, verbatim: "a side maps only when its candidates
    resolve to exactly one of the NHL competition's teams"): the union of the teams every candidate's normalised name
    names must be exactly one team; none, or two or more (a name held twice, an alias naming another row), is None."""
    from src.ingestion.match_lookup import normalize_team_name
    hit: set = set()
    for c in candidates or ():
        hit |= universe.get(normalize_team_name(c or ""), set())
    return next(iter(hit)) if len(hit) == 1 else None


def resolve_match(s, game: dict) -> int | None:
    """The link nhl_goalies holds for the gameId (exactly one match), else match_game as it stands, else None."""
    from sqlalchemy import select

    from src.db.schema import NHLGoalieAppearance as A
    linked = {m for (m,) in s.execute(select(A.match_id).where(A.nhl_game_id == int(game["id"]),
                                                                A.match_id.is_not(None)).distinct())}
    if len(linked) == 1:
        return next(iter(linked))
    if linked:
        return None                                       # two links for one game: refused, never chosen (law 4)
    m = ng.match_game(s, game)
    return m.id if m is not None else None


def source_team(game: dict, side: str) -> str | None:
    """The side's own team text, verbatim (day_games' `<side>_text`), or None: a side the schedule names no team for
    asserts nothing (law 4: never a made-up text), counted as missing."""
    return game.get(f"{side}_text")


# ---- reading one answer ------------------------------------------------------------------------------------------------

@dataclass
class Read:
    status: str
    assertions: list = field(default_factory=list)
    missing: dict = field(default_factory=dict)          # side -> why (a landing side with no leaders[0])
    two_in_net: list = field(default_factory=list)       # sides with two or more goalies above zero toi
    error: str | None = None                             # a `failed` read's reason, or an `empty` one's note


def read_landing(payload, game: dict, teams: dict, match_id: int | None) -> Read:
    r = Read("complete")
    for side in SIDES:
        got, why = leader(payload, side)
        if got is None:
            r.missing[side] = why
            continue
        pid, name = got
        if teams.get(side) is None and source_team(game, side) is None:
            r.missing[side] = "the schedule names no team for this side (nothing asserted: law 4)"
            continue
        r.assertions.append({"kind": "projected_starter", "player_id": None, "source_player_id": str(pid),
                             "player_name": name, "team_id": teams.get(side), "source_team": source_team(game, side),
                             "match_id": match_id,
                             "attrs": {"side": side, "source_match_id": str(game["id"])}})
    r.status = _status(r.assertions, match_id)
    return r


def read_boxscore(payload, game: dict, teams: dict, match_id: int | None) -> Read:
    rows, receipt = ng.boxscore_goalies(payload)
    if rows is None:
        lists = ", ".join(receipt.get("goalie_lists") or []) or "none"
        return Read("failed", error=f"the ingest refused the boxscore: goalie lists not sided one home + one away "
                                    f"(lists: {lists})"[:256])
    r = Read("complete")
    for side in SIDES:
        mine = [x for x in rows if x["side"] == side]
        on = [x for x in mine if x["toi_seconds"] is not None and x["toi_seconds"] > 0]
        unread = sum(x["toi_seconds"] is None for x in mine)
        if on and teams.get(side) is None and source_team(game, side) is None:
            r.missing[side] = "the schedule names no team for this side (nothing asserted: law 4)"
            continue
        if len(on) > 1:
            r.two_in_net.append(side)
        for x in on:
            r.assertions.append({"kind": "eventual_starter", "player_id": None,
                                 "source_player_id": str(x["goalie_id"]), "player_name": x["goalie_name"],
                                 "team_id": teams.get(side), "source_team": source_team(game, side),
                                 "match_id": match_id,
                                 "attrs": {"side": side, "source_match_id": str(game["id"]),
                                           "toi_seconds": x["toi_seconds"], "two_in_net": len(on) > 1,
                                           "toi_unread": unread}})
    r.status = _status(r.assertions, match_id)
    unread = sum(x["toi_seconds"] is None for x in rows)
    if r.status == "empty" and unread:                    # "none in net" only as far as the ingest could read it
        r.error = (f"no goalie above zero toi; {unread} goalie(s) whose toi the ingest could not read (law 4: not "
                   f"read as none in net)")
    return r


def _status(assertions: list, match_id: int | None) -> str:
    """252/254 item 2(7): `empty` with nothing to assert; `partial` when a team or the match is left unmapped."""
    if not assertions:
        return "empty"
    if match_id is None or any(a["team_id"] is None for a in assertions):
        return "partial"
    return "complete"


# ---- the tick ----------------------------------------------------------------------------------------------------------

@dataclass
class Poll:
    game: dict
    label: str
    offset: int
    endpoint: str
    scheduled_at: datetime
    missed: bool

    @property
    def url(self) -> str:
        return game_url(self.game["id"], self.endpoint)


@dataclass
class Tick:
    now: datetime
    dry_run: bool = False
    schedules: list = field(default_factory=list)
    games: int = 0
    due: list = field(default_factory=list)              # the Polls this tick plans
    remaining: int = 0                                   # polls of the window not yet due
    rows: list = field(default_factory=list)             # (Poll, status, line detail)
    already: int = 0
    exit_code: int = 0
    planned_at: datetime | None = None                   # the clock the due polls were planned on (under the lock)

    def lines(self) -> list[str]:
        out = [f"AVAILABILITY-NHL-OBSERVE · {_z(self.now)} · games in the window {self.games} · polls due "
               f"{len(self.due)} · not yet due {self.remaining}"
               + (" · DRY RUN: no landing or boxscore call, nothing written" if self.dry_run else
                  f" · written {len(self.rows)}")
               + (f" · already observed {self.already} (another run stored them first; skipped)"
                  if self.already else "")]
        for sc in self.schedules:
            out.append(f"  schedule {sc.day} · {sc.read} · {len(sc.games)} game(s) of types 2/3"
                       + (f" · sha256 {sc.sha[:16]}" if sc.sha else "")
                       + (f" · {sc.path}" if sc.path else "")
                       + (f" · ERROR (redacted): {sc.error}" if sc.error else "")
                       + (" · NOTICE: the NHL day's first failed schedule read (this tick exits 1)"
                          if sc.notice else ""))
        if self.dry_run:
            for p in self.due:
                out.append(f"  game {p.game['id']} {p.label} · scheduled {_z(p.scheduled_at)} · "
                           + ("would be MISSED (no call)" if p.missed else f"would ask {p.url}"))
        for p, _status, detail in self.rows:
            out.append(f"  game {p.game['id']} {p.label} · scheduled {_z(p.scheduled_at)} · {detail}")
        return out


def _window_games(schedules: list, now: datetime) -> list[dict]:
    lo, hi = now - LOOKBACK, now + AHEAD
    seen, out = set(), []
    for sc in schedules:
        for g in sc.games:
            if g["id"] not in seen and lo <= g["start"] <= hi:
                seen.add(g["id"])
                out.append(g)
    return sorted(out, key=lambda g: (g["start"], g["id"]))


def written_polls(s, games: list[dict]) -> set:
    """What the store holds for these games, as {(gameId, label)} and {(endpoint, scheduled_at)}: an observation of
    this source at the game's landing or boxscore URL with a poll label. A poll is WRITTEN when its label is held,
    whatever kickoff it was scheduled against (340 item 4: "a written poll is never touched"), or when its endpoint and
    scheduled time are held under another label (#835 item 2's key: "the scheduled poll time is the poll"; a start
    moved earlier can land a recomputed poll on one already asked)."""
    from sqlalchemy import select

    from src.db.schema import AvailabilityObservation as O
    by_url = {game_url(g["id"], ep): g["id"] for g in games for ep in (LANDING, BOXSCORE)}
    labels, times = set(), set()
    if not by_url:
        return labels | times
    for ep, label, sched in s.execute(select(O.endpoint, O.poll_label, O.scheduled_at).where(
            O.source == SOURCE, O.endpoint.in_(list(by_url)), O.poll_label.is_not(None))):
        labels.add((by_url[ep], label))
        if sched is not None:
            times.add((ep, sched))
    return labels | times


def plan(games: list[dict], written: set, now: datetime) -> tuple[list[Poll], int]:
    """The due polls (time passed, not written) and the count not yet due. `written` holds (gameId, label) and
    (endpoint, scheduled_at) pairs (written_polls)."""
    due, remaining = [], 0
    for g in games:
        for label, off, ep in POLLS:
            sched = g["start"] - timedelta(minutes=off)
            if (g["id"], label) in written or (game_url(g["id"], ep), sched) in written:
                continue
            if sched > now:
                remaining += 1
                continue
            due.append(Poll(g, label, off, ep, sched, missed=now - sched > MISSED_AFTER))
    due.sort(key=lambda p: (p.scheduled_at, p.game["id"], p.label))
    return due, remaining


def poll_key_migrated(s) -> bool:
    """True when the store holds #835 item 2's poll key (its index and its guard): a store migrated before it would
    let an unmapped poll be written twice, so the watch refuses to write until the migration has run again."""
    from sqlalchemy import text
    names = {r[0] for r in s.execute(text("SELECT name FROM sqlite_master WHERE name IN (:a, :b)"),
                                     {"a": POLL_GUARD, "b": POLL_KEY_INDEX})}
    return names == {POLL_GUARD, POLL_KEY_INDEX}


def _db_lock():
    """The chains' DB lock (#569), as cup_lineups_live._db_lock and nflverse._db_lock take it."""
    hosting = str(REPO / "deploy" / "hosting")
    if hosting not in sys.path:
        sys.path.insert(0, hosting)
    import sp_common
    return sp_common.sync_lock(on_wait=lambda p: print(f"… waiting for the DB lock {p} (a chain or closing run holds "
                                                       "it)", flush=True))


_UNMIGRATED = ("REFUSED: migrate_availability_record.py has not run on this store since #835 item 2's poll key "
               f"({POLL_KEY_INDEX}, {POLL_GUARD}): run it (a .backup first); nothing asked, nothing kept, nothing "
               "written. --dry-run reads without it.")


def _plan_ro(t: Tick, *, refuse_unmigrated: bool, at: datetime | None = None):
    """The window's games and their due polls at `at` (default the tick's start), read mode=ro. Refuses an unmigrated
    store when it will write."""
    from src.db.database import readonly_scope
    at = at or t.now
    games = _window_games(t.schedules, at)
    with readonly_scope() as s:
        ok = rec.migrated(s) and poll_key_migrated(s)
        if refuse_unmigrated and not ok:
            raise Refused(_UNMIGRATED)
        written = written_polls(s, games) if ok else set()
    t.games = len(games)
    t.due, t.remaining = plan(games, written, at)
    t.planned_at = at


def tick(now: datetime | None = None, *, dry_run: bool = False, http_get=None, now_fn=None) -> Tick:
    """ONE TICK of the watch (the module docstring). A missing DB file is refused before any session opens (law 5)."""
    now_fn = now_fn or _now
    now = now or now_fn()
    path = rec._db_file()
    if path is None or not path.is_file():
        raise Refused(f"REFUSED: no DB file at {path or 'a non-file database URL'}: the record never creates one "
                      "(law 5); nothing asked, nothing written")
    if not dry_run:                                      # refused BEFORE any call, kept file or notice
        from src.db.database import readonly_scope
        with readonly_scope() as s:
            if not (rec.migrated(s) and poll_key_migrated(s)):
                raise Refused(_UNMIGRATED)
    t = Tick(now=now, dry_run=dry_run)
    t.schedules = [schedule(d, now, http_get=http_get, now_fn=now_fn, keep=not dry_run)
                   for d in days_of(now - LOOKBACK, now + AHEAD)]
    if any(sc.notice for sc in t.schedules):
        t.exit_code = 1
    _plan_ro(t, refuse_unmigrated=not dry_run)
    if dry_run or not t.due:
        return t
    with _db_lock():
        # again under the lock, on the clock as it reads NOW: what another run wrote stands, and a poll that passed
        # its five minutes while the tick waited for the lock is `missed`, never asked late (252 item 3(b))
        _plan_ro(t, refuse_unmigrated=True, at=now_fn())
        if t.due:
            _execute(t, http_get=http_get, now_fn=now_fn)
    return t


def _execute(t: Tick, *, http_get, now_fn) -> None:
    from src.db.database import readonly_scope
    with readonly_scope() as s:
        universe = team_universe(s)
        maps = {}
        for g in {p.game["id"]: p.game for p in t.due}.values():
            maps[g["id"]] = ({side: resolve_team(universe, g.get(f"{side}_names")) for side in SIDES},
                             resolve_match(s, g))
        # ONE MATCH, ONE GAME (law 4): a match two gameIds resolve to, in this tick or already in the record, is
        # refused for both (NULL with attrs.source_match_id), never shared: Step B's key (source, match_id, kickoff,
        # label) would otherwise read the second game's poll as the first's, "already"
        claimed: dict = {}
        for gid, (_, mid) in maps.items():
            if mid is not None:
                claimed.setdefault(mid, set()).add(gid)
        for gid, (teams, mid) in list(maps.items()):
            if mid is not None and (len(claimed[mid]) > 1 or _claimed_elsewhere(s, mid, gid)):
                maps[gid] = (teams, None)
    for p in t.due:
        teams, match_id = maps[p.game["id"]]
        obs = {"sport": SPORT, "source": SOURCE, "endpoint": p.url, "match_id": match_id,
               "kickoff_at": p.game["start"], "poll_label": p.label, "scheduled_at": p.scheduled_at}
        if p.missed:
            _write(t, p, {**obs, "status": "missed"}, [], None,
                   f"MISSED: no call ({int(((t.planned_at or t.now) - p.scheduled_at).total_seconds() // 60)} min past "
                   f"its time)")
            continue
        why = rec.endpoint_refusal(p.url)
        if why:
            raise Refused(why)
        a = get(p.url, http_get=http_get, now_fn=now_fn)
        obs.update(fetched_at=a.at, http_status=a.status, late=a.at - p.scheduled_at > LATE_LIMIT)
        if a.error is not None:
            _write(t, p, {**obs, "status": "failed", "error": a.error}, [], None, f"FAILED: {a.error}")
            continue
        sha = hashlib.sha256(a.body).hexdigest()
        rel, created = _keep(_rel_dir(a.at.date()),
                             f"{a.at:%H%M%S}Z-{sha[:16]}-{int(p.game['id'])}_{p.endpoint}_{p.label}.json", a.body, sha)
        obs.update(payload_sha256=sha, payload_path=rel)
        payload, why = _json(a.body)
        if payload is None:
            _write(t, p, {**obs, "status": "failed", "error": why}, [], rel if created else None, f"FAILED: {why}")
            continue
        r = (read_landing if p.endpoint == LANDING else read_boxscore)(payload, p.game, teams, match_id)
        if r.status == "failed":
            _write(t, p, {**obs, "status": "failed", "error": r.error}, [], rel if created else None,
                   f"FAILED: {r.error}")
            continue
        detail = "; ".join(
            [f"{a_['attrs']['side']} {a_['source_player_id']}" + (f" ({a_['player_name']})" if a_['player_name']
                                                                  else "")
             + ("" if a_["team_id"] is not None else f" team {a_['source_team']} UNMAPPED")
             for a_ in r.assertions]
            + [f"{side} missing: {why_}" for side, why_ in r.missing.items()]
            + [f"{side} TWO IN NET" for side in r.two_in_net]
            + ([] if match_id is not None or not r.assertions else ["match UNMAPPED"]))
        if r.error:                                       # an `empty` boxscore's note (toi unread)
            obs["error"] = r.error[:256]
            detail = "; ".join(x for x in (detail, r.error) if x)
        _write(t, p, {**obs, "status": r.status}, r.assertions, rel if created else None,
               r.status.upper() + (" LATE" if obs["late"] else "") + (f": {detail}" if detail else ""))


def _claimed_elsewhere(s, match_id: int, game_id: int) -> bool:
    """True when the record holds an observation of this source mapped to `match_id` at ANOTHER game's endpoint."""
    from sqlalchemy import select

    from src.db.schema import AvailabilityObservation as O
    mine = (game_url(game_id, LANDING), game_url(game_id, BOXSCORE))
    return s.execute(select(O.id).where(O.source == SOURCE, O.match_id == match_id, O.endpoint.not_in(mine))
                     .limit(1)).first() is not None


def _write(t: Tick, p: Poll, obs: dict, assertions: list, created_rel: str | None, detail: str) -> None:
    """record.write_observation; "already" (a writer outside the lock stored this poll first) drops a payload this run
    created and counts it; a store refusal after a keep is written as a `failed` observation keeping the payload."""
    status = obs["status"]
    try:
        try:
            r = rec.write_observation(obs, assertions)
        except rec.Refused as e:
            if status in ("failed", "missed") or not obs.get("payload_path"):
                raise
            why = _scrub(e)[:256]
            status, detail = "failed", f"FAILED: {why}"
            r = rec.write_observation({**obs, "status": status, "error": why}, [])
    except BaseException:
        _drop(created_rel)                                # no row names it: never an orphan payload
        raise
    if r.already:
        t.already += 1
        _drop(created_rel)
        return
    t.rows.append((p, status, f"observation #{r.observation_id} · {detail}"))


__all__ = ["SOURCE", "BASE", "PREGAME", "EVENTUAL", "POLLS", "DAY_CUT_UTC", "GAME_TYPES", "MISSED_AFTER",
           "LATE_LIMIT", "AHEAD", "LOOKBACK", "SCHEDULE_TTL", "Refused", "leader", "nhl_day", "day_bounds", "days_of",
           "schedule_url", "game_url", "get", "schedule", "day_games", "team_universe", "resolve_team",
           "resolve_match", "read_landing", "read_boxscore", "written_polls", "plan", "poll_key_migrated", "tick",
           "Tick"]
