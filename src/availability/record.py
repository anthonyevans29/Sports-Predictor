"""
THE AVAILABILITY RECORD (ARCHITECT 2026-11-04 13:05 ET, addendum 252; lane availability-record): the one module that
writes the record and the one read path over it.

Item 1, verbatim in part: "a bitemporal, append-only store of what was knowable about who plays, stamped by our clock
[...] Two tables, both created by one migration, both written by ingest commands only, both read mode=ro by everything
else". Item 2: "The same function is the one a model term, the bulletin's teams section and the Cockpit will read;
there is no second path."

THE WRITER. write_observation(obs, assertions) is the only public writer: one observation row and its assertions in one
transaction, rows_asserted = len(assertions), every assertion's recorded_at = the observation's fetched_at (set here,
never by the caller). It refuses, before any session opens: a source, status or kind outside the vocabulary; a column
name it does not know (law 1); assertions on an observation that is not complete or partial; a missed row with a
fetched_at, or any other row without one; an endpoint that carries a secret; a payload_path outside
logs/availability/<source>/<YYYY-MM-DD>/ (so never under data/); a missing DB file (never created, law 5); a store
migrate_availability_record.py has not migrated. The error text is redacted, then cut to 256 characters. A poll the
store already holds (the unique key: source, match, stored kickoff, poll) is counted "already", its row standing.
There is no update, delete or upsert function here, and the tables' triggers abort one from anywhere else.

THE MAPPING (item 1, law 4): a player or team the caller cannot map is written with player_id / team_id NULL and the
source's id and text beside it; the receipt counts the unmapped players, teams and per-game facts without a match.
Nothing here maps by name. The read keys a fact and a slot on the SOURCE'S OWN identifiers (its player id, else the
name verbatim; its team text), ours only where the source gave none: our ids are joined for display, so a mapping that
lands between two fetches never splits one source fact into two.

THE READ. derive() turns assertions into intervals (item 1(b): "a fact holds from its observation to the next
observation of the same source that asserts the same (kind, player, team[, match]) differently, or that asserts the
slot to someone else"); as_of() is derive() over the assertions whose chosen clock is at or before the instant, keeping
the intervals still open; history() is every assertion, in time order, with the end of the interval it belongs to.
THE TWO CLOCKS (item 1, ruled): `recorded_at` is our knowledge, `source_stamp` the source's claim. Under the recorded
clock an assertion exists from its fetch, so a backfilled row never appears before it; under the source clock an
assertion with no source stamp is not read (counted, never filled from recorded_at). Every fact carries both stamps.
A fact reads BACKFILLED only while every member of its interval is backfilled: one fresh restatement puts it in the
live-era record, from that row's recorded_at (Fact.live_since). A --history line carries its own row's labels.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import Iterable, Sequence
from urllib.parse import urlsplit

from src.db.schema import (APPEND_ONLY, AVAILABILITY_KINDS, AVAILABILITY_SOURCES, AVAILABILITY_STATUSES,
                           AVAILABILITY_TRIGGERS, Sport)

# Each source word and the attribution any output that uses its facts prints (item 3(a): "the source word carries the
# attribution, and any output that uses the facts (a bulletin, a page) prints "Depth charts: nflverse (CC BY 4.0)"").
# The NHL API's and the paid feed's terms carry no attribution line in the ruling: None.
SOURCES = {
    "nflverse_depth_charts": "Depth charts: nflverse (CC BY 4.0)",
    "nhl_api_landing": None,
    "sportsdataio_goalies": None,
}
assert tuple(SOURCES) == AVAILABILITY_SOURCES
STATUSES = AVAILABILITY_STATUSES
KINDS = AVAILABILITY_KINDS
CLOCKS = ("recorded", "source")
ASSERTING = ("complete", "partial")                  # the statuses that carry facts
GAME_KINDS = ("projected_starter", "confirmed_starter", "eventual_starter", "inactive")   # per-game facts
STARTER_KINDS = ("projected_starter", "confirmed_starter", "eventual_starter")
POST_HOC_KINDS = ("eventual_starter",)               # item 3(b): "post hoc, kind-labelled, never a pregame fact"
# THE BACKFILL THRESHOLD, PROPOSED (item 1: "recorded_at later than source_stamp by more than the feed's cadence"):
# nflverse loads daily, so 24 hours. A source with no entry has no ruled cadence: its stamped facts read "backfill
# unknown", never "not backfilled" (law 4).
CADENCE = {"nflverse_depth_charts": timedelta(hours=24)}
# attrs keys a restatement may change without asserting the fact differently: the source's raw time text (its stamp
# is source_stamp, compared nowhere as a fact)
VOLATILE_ATTRS = ("dt_raw",)

OBS_TABLE = "availability_observations"
ASR_TABLE = "availability_assertions"
TABLES = (OBS_TABLE, ASR_TABLE)
TRIGGERS = tuple(name for name, _, _ in AVAILABILITY_TRIGGERS)
MIGRATION_MARKER = "availability_record_migration"
PAYLOAD_ROOT = ("logs", "availability")              # item 1(a): logs/availability/<source>/<date>/, never data/

OBS_FIELDS = ("sport", "source", "endpoint", "match_id", "kickoff_at", "poll_label", "scheduled_at", "fetched_at",
              "http_status", "payload_sha256", "payload_path", "status", "late", "error")
ASR_FIELDS = ("kind", "player_id", "source_player_id", "player_name", "team_id", "source_team", "match_id", "attrs",
              "source_stamp")
NOT_FROM_THE_CALLER = ("recorded_at", "observation_id", "sport", "id")

# the deploy's secret names (deploy/hosting/sp_common.py SECRET_ENV) and any variable named like a credential
_SECRET_ENV = ("API_FOOTBALL_KEY", "API_BASEBALL_KEY", "API_AMERICAN_FOOTBALL_KEY", "API_HOCKEY_KEY", "ODDS_API_KEY",
               "CFBD_API_KEY", "NTFY_TOPIC", "NTFY_CARD_TOPIC")
_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)$")
# A credential-like NAME: one of its words (split at '_', '-' and a camel-case hump) is a credential word, or ends in
# one. "api_token", "access_key", "client_secret", "apiKey", "X-Api-Key", "sig" are; "hockey", "monkey", "design" are
# not. The name is followed by '=' or ':' (a URL parameter, a header, a quoted dict or JSON key), and its VALUE is read
# in a lookahead, so a non-credential name never swallows the credential name after it ("Unauthorized: Authorization:
# Bearer …"); an auth scheme word (Bearer, Basic, Token, Digest) is redacted with its token.
_CRED_WORDS = frozenset({"key", "apikey", "accesskey", "token", "secret", "password", "passwd", "pwd", "auth",
                         "authorization", "bearer", "credential", "credentials", "sig", "signature", "jwt"})
_CRED_SUFFIXES = ("token", "secret", "password", "passwd", "apikey", "accesskey")
_PARAM = re.compile(r"(?<![\w-])([A-Za-z][\w-]*)([\"']?\s*[=:]\s*[\"']?)"
                    r"(?=((?:(?:bearer|basic|token|digest)\s+)?[^\s&\"',;}?#]+))", re.I)
_BEARER = re.compile(r"(?i)\b(bearer)\s+(?!\[REDACTED\])[^\s\"',;}]+")
_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/\s@?#]+@")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class Refused(Exception):
    """The record refuses: nothing was written (or, for a read, nothing was read)."""


# ---- secrets ----------------------------------------------------------------------------------------------------------

def _secret_values() -> list[str]:
    names = set(_SECRET_ENV) | {n for n in os.environ if _SECRET_NAME.search(n)}
    return [v for v in (os.environ.get(n) for n in sorted(names)) if v and len(v) >= 6]


def _cred_name(name: str) -> bool:
    words = [w.lower() for w in re.split(r"[_\-]+|(?<=[a-z])(?=[A-Z])", name) if w]
    return any(w in _CRED_WORDS or w.endswith(_CRED_SUFFIXES) for w in words)


def _cred_spans(text: str) -> list[tuple[str, int, int]]:
    """(name, value start, value end) for every credential-like name=value / name: value in the text."""
    return [(m.group(1), m.end(2), m.end(2) + len(m.group(3))) for m in _PARAM.finditer(text) if _cred_name(m.group(1))]


def redact(text: str | None) -> str | None:
    """The error text with every secret the environment holds, every URL's userinfo (user:password@), every
    credential-like value (a URL parameter, a header, a quoted dict or JSON key, with its auth scheme's token) and
    every bearer token replaced (the deploy's redact rule, deploy/hosting/sp_common.py, widened: addendum 252 item
    1(a), "error (redacted)"; the rows are append-only, so a secret that got through could never be removed)."""
    if text is None:
        return None
    out = str(text)
    for v in _secret_values():
        out = out.replace(v, "[REDACTED]")
    out = _USERINFO.sub(lambda m: m.group(1) + "[REDACTED]@", out)
    parts, pos = [], 0
    for _, a, b in sorted(_cred_spans(out), key=lambda x: x[1]):
        if b <= pos:
            continue
        parts += [out[pos:max(a, pos)], "[REDACTED]"]
        pos = b
    out = "".join(parts) + out[pos:]
    return _BEARER.sub(lambda m: m.group(1) + " [REDACTED]", out)


def _endpoint_secret(endpoint: str) -> str | None:
    """Why the endpoint carries a secret, or None (item 5: "no secret in an endpoint string"): a secret environment
    value, credentials in the URL itself (user:password@ or a token as the user), or a credential-like parameter."""
    if any(v in endpoint for v in _secret_values()):
        return "it holds a value of a secret environment variable"
    try:
        u = urlsplit(endpoint)
        userinfo = u.username is not None or u.password is not None
    except ValueError:
        return "it is not a URL the check can read (refused, never guessed)"
    if userinfo or _USERINFO.search(endpoint):
        return "it carries credentials in the URL (userinfo before '@')"
    spans = _cred_spans(endpoint)
    return f"it holds a credential-like parameter ({spans[0][0]!r})" if spans else None


# ---- validation (pure, before any DB) ---------------------------------------------------------------------------------

def _naive_utc(v, what: str) -> datetime | None:
    if v is None:
        return None
    if not isinstance(v, datetime):
        raise Refused(f"REFUSED: {what} {v!r} is not a datetime (UTC)")
    return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo is not None else v


def _int_or_none(v, what: str) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise Refused(f"REFUSED: {what} {v!r} is not an integer")
    return v


def _text_or_none(v, what: str, limit: int) -> str | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (str, int)):
        raise Refused(f"REFUSED: {what} {v!r} is neither text nor an id")
    s = str(v)
    if not s.strip():
        return None
    if len(s) > limit:
        raise Refused(f"REFUSED: {what} is longer than {limit} characters")
    return s


def _sport(v) -> Sport:
    if isinstance(v, Sport):
        return v
    try:
        return Sport(v)
    except ValueError:
        raise Refused(f"REFUSED: sport {v!r} is not one of {', '.join(s.value for s in Sport)}") from None


def payload_path_refusal(path: str, source: str) -> str | None:
    """Why `path` is not a payload path for `source`, or None. A payload path is relative, under
    logs/availability/<source>/<YYYY-MM-DD>/, with no '..' (item 1(a); item 5: "no payload under data/")."""
    s = str(path)
    p = PurePosixPath(s)
    if "\\" in s or p.is_absolute() or ".." in p.parts:
        return f"payload_path {s!r} is not a plain relative path"
    if "data" in p.parts:
        return f"payload_path {s!r} is under data/ (law 5; item 5: no payload under data/)"
    parts = p.parts
    if len(parts) < 5 or parts[:2] != PAYLOAD_ROOT or parts[2] != source:
        return f"payload_path {s!r} is not under {'/'.join(PAYLOAD_ROOT)}/{source}/<YYYY-MM-DD>/"
    try:
        date.fromisoformat(parts[3])
    except ValueError:
        return f"payload_path {s!r}: {parts[3]!r} is not a date (YYYY-MM-DD)"
    return None


def _check_observation(obs: dict) -> dict:
    if not isinstance(obs, dict):
        raise Refused("REFUSED: the observation is not a mapping")
    unknown = sorted(set(obs) - set(OBS_FIELDS))
    if unknown:
        raise Refused(f"REFUSED: the observation names {', '.join(unknown)}: not a column the writer sets "
                      f"({', '.join(OBS_FIELDS)}; rows_asserted is counted here)")
    row = {"sport": _sport(obs.get("sport"))}
    src = obs.get("source")
    if src not in SOURCES:
        raise Refused(f"REFUSED: source {src!r} is not in the vocabulary ({', '.join(SOURCES)}; addendum 252 item 3)")
    row["source"] = src
    status = obs.get("status")
    if status not in STATUSES:
        raise Refused(f"REFUSED: status {status!r} is not one of {', '.join(STATUSES)}")
    row["status"] = status
    ep = obs.get("endpoint")
    if not isinstance(ep, str) or not ep.strip():
        raise Refused("REFUSED: no endpoint (the URL or file name)")
    if len(ep) > 512:
        raise Refused("REFUSED: the endpoint is longer than 512 characters")
    why = _endpoint_secret(ep)
    if why:
        raise Refused(f"REFUSED: the endpoint carries a secret: {why} (addendum 252 item 5); nothing written")
    row["endpoint"] = ep
    row["match_id"] = _int_or_none(obs.get("match_id"), "match_id")
    row["http_status"] = _int_or_none(obs.get("http_status"), "http_status")
    for k in ("kickoff_at", "scheduled_at", "fetched_at"):
        row[k] = _naive_utc(obs.get(k), k)
    row["poll_label"] = _text_or_none(obs.get("poll_label"), "poll_label", 16)
    if row["poll_label"] is not None and row["scheduled_at"] is None:
        raise Refused("REFUSED: a polled observation (poll_label) has no scheduled_at")
    if status == "missed":
        if row["fetched_at"] is not None:
            raise Refused("REFUSED: a missed poll made no call: fetched_at must be empty")
        if row["scheduled_at"] is None:
            raise Refused("REFUSED: a missed poll has no scheduled_at")
        if any(obs.get(k) is not None for k in ("http_status", "payload_sha256", "payload_path")):
            raise Refused("REFUSED: a missed poll made no call: no http_status, payload or sha")
    elif row["fetched_at"] is None:
        raise Refused(f"REFUSED: a {status} observation has no fetched_at (our clock, UTC)")
    sha = obs.get("payload_sha256")
    if sha is not None and (not isinstance(sha, str) or not _SHA256.fullmatch(sha)):
        raise Refused(f"REFUSED: payload_sha256 {sha!r} is not 64 lower-case hex characters")
    row["payload_sha256"] = sha
    pp = obs.get("payload_path")
    if pp is not None:
        why = payload_path_refusal(pp, src)
        if why:
            raise Refused(f"REFUSED: {why}; nothing written")
    row["payload_path"] = str(pp) if pp is not None else None
    late = obs.get("late", False)
    if not isinstance(late, bool):
        raise Refused(f"REFUSED: late {late!r} is not a boolean")
    row["late"] = late
    err = obs.get("error")
    if status == "failed" and not (isinstance(err, str) and err.strip()):
        raise Refused("REFUSED: a failed observation keeps its error (the call raised: say what)")
    row["error"] = redact(err)[:256] if err is not None else None
    return row


def _check_assertion(a: dict, i: int) -> dict:
    if not isinstance(a, dict):
        raise Refused(f"REFUSED: assertion {i} is not a mapping")
    given = sorted(set(a) & set(NOT_FROM_THE_CALLER))
    if given:
        raise Refused(f"REFUSED: assertion {i} sets {', '.join(given)}: the writer sets these from the observation")
    unknown = sorted(set(a) - set(ASR_FIELDS))
    if unknown:
        raise Refused(f"REFUSED: assertion {i} names {', '.join(unknown)}: not a column ({', '.join(ASR_FIELDS)})")
    kind = a.get("kind")
    if kind not in KINDS:
        raise Refused(f"REFUSED: assertion {i}: kind {kind!r} is not in the vocabulary ({', '.join(KINDS)})")
    row = {"kind": kind,
           "player_id": _int_or_none(a.get("player_id"), f"assertion {i} player_id"),
           "source_player_id": _text_or_none(a.get("source_player_id"), f"assertion {i} source_player_id", 64),
           "player_name": _text_or_none(a.get("player_name"), f"assertion {i} player_name", 128),
           "team_id": _int_or_none(a.get("team_id"), f"assertion {i} team_id"),
           "source_team": _text_or_none(a.get("source_team"), f"assertion {i} source_team", 64),
           "match_id": _int_or_none(a.get("match_id"), f"assertion {i} match_id"),
           "source_stamp": _naive_utc(a.get("source_stamp"), f"assertion {i} source_stamp")}
    if row["player_id"] is None and row["source_player_id"] is None and row["player_name"] is None:
        raise Refused(f"REFUSED: assertion {i} names no player (ours, the source's id, or the name verbatim)")
    if row["team_id"] is None and row["source_team"] is None:
        raise Refused(f"REFUSED: assertion {i} names no team (ours, or the source's verbatim)")
    attrs = a.get("attrs")
    if attrs is not None:
        if not isinstance(attrs, dict):
            raise Refused(f"REFUSED: assertion {i}: attrs is not a mapping")
        try:
            json.dumps(attrs)
        except (TypeError, ValueError) as e:
            raise Refused(f"REFUSED: assertion {i}: attrs is not JSON ({e})") from None
    row["attrs"] = attrs
    return row


# ---- the store --------------------------------------------------------------------------------------------------------

def _db_file():
    """The SQLite file the app's sessions are bound to (as database.readonly_scope reads it), or None."""
    from pathlib import Path

    import src.db.database as db
    url = db.SessionLocal.kw["bind"].url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    raw = url.database[len("file:"):] if url.database.startswith("file:") else url.database
    return Path(raw.split("?", 1)[0]).resolve()


def migrated(rs) -> bool:
    """True only when migrate_availability_record.py ran: both tables AND the marker it alone writes."""
    from sqlalchemy import inspect, text
    try:
        ins = inspect(rs.get_bind())
        if not all(ins.has_table(t) for t in (*TABLES, MIGRATION_MARKER)):
            return False
        return bool(rs.execute(text(f"SELECT COUNT(*) FROM {MIGRATION_MARKER}")).scalar())
    except Exception:  # noqa: BLE001 - an unreadable marker is not a migration
        return False


@dataclass
class Receipt:
    """One write's receipt (law 2): what was written, and what the caller could not map (law 4: counted)."""
    source: str
    status: str
    observation_id: int | None = None
    written: bool = False
    already: bool = False                 # the store holds this poll already (the unique key): nothing written
    assertions: int = 0
    unmapped_players: int = 0
    unmapped_teams: int = 0
    unmapped_matches: int = 0             # per-game facts (GAME_KINDS) with no match of ours

    def line(self) -> str:
        if self.already:
            return f"· {self.source} {self.status}: already observed (the store's row stands); nothing written"
        return (f"+ {self.source} observation #{self.observation_id} {self.status}: {self.assertions} assertion(s); "
                f"unmapped: {self.unmapped_players} player(s), {self.unmapped_teams} team(s), "
                f"{self.unmapped_matches} per-game fact(s) with no match")


def write_observation(obs: dict, assertions: Sequence[dict] = ()) -> Receipt:
    """THE ONLY WRITER: one observation and its assertions, one transaction, append-only (see the module docstring)."""
    row = _check_observation(obs)
    rows = [_check_assertion(a, i) for i, a in enumerate(list(assertions or ()), 1)]
    if rows and row["status"] not in ASSERTING:
        raise Refused(f"REFUSED: a {row['status']} observation asserts nothing (only {' or '.join(ASSERTING)} "
                      f"observations carry facts); {len(rows)} assertion(s) given, nothing written")
    path = _db_file()
    if path is None or not path.is_file():
        raise Refused(f"REFUSED: no DB file at {path or 'a non-file database URL'}: the record never creates one "
                      "(law 5)")
    from sqlalchemy.exc import IntegrityError

    from src.db.database import session_scope
    from src.db.schema import AvailabilityAssertion, AvailabilityObservation
    rec = Receipt(source=row["source"], status=row["status"])
    try:
        with session_scope() as s:
            if not migrated(s):
                raise Refused("REFUSED: migrate_availability_record.py has not run (the tables and their marker); "
                              "nothing written")
            o = AvailabilityObservation(**row, rows_asserted=len(rows))
            s.add(o)
            s.flush()
            s.add_all([AvailabilityAssertion(**r, observation_id=o.id, sport=row["sport"],
                                             recorded_at=row["fetched_at"]) for r in rows])
            s.flush()
            rec.observation_id = o.id
    except IntegrityError as e:
        msg = str(getattr(e, "orig", e))
        if "this poll is already observed" in msg or msg.startswith(f"UNIQUE constraint failed: {OBS_TABLE}."):
            rec.already = True
            return rec
        raise Refused(f"REFUSED: the store refused the write ({msg}); nothing written") from None
    rec.written = True
    rec.assertions = len(rows)
    rec.unmapped_players = sum(r["player_id"] is None for r in rows)
    rec.unmapped_teams = sum(r["team_id"] is None for r in rows)
    rec.unmapped_matches = sum(r["kind"] in GAME_KINDS and r["match_id"] is None for r in rows)
    return rec


# ---- the read: one path ------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Row:
    """One assertion with the observation it came from."""
    id: int
    observation_id: int
    source: str
    endpoint: str
    poll_label: str | None
    obs_status: str
    kickoff_at: datetime | None
    sport: str
    kind: str
    player_id: int | None
    source_player_id: str | None
    player_name: str | None
    team_id: int | None
    source_team: str | None
    match_id: int | None
    attrs: dict | None
    source_stamp: datetime | None
    recorded_at: datetime


@dataclass(eq=False)
class Interval:
    """A derived interval: the assertion that opened it, its latest restatement, and the group that closed it."""
    first: Row
    last: Row
    start: datetime
    end: datetime | None = None
    closed_by: Row | None = None
    why_closed: str | None = None         # "asserted differently" | "slot asserted to someone else"
    restated: int = 0
    members: list = field(default_factory=list)


def load_rows(s, sport, kind: str | None = None) -> list[Row]:
    """Every assertion of the sport (and kind), with its observation. Read only; the caller's session."""
    from sqlalchemy import select

    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    q = (select(A, O).join(O, O.id == A.observation_id).where(A.sport == _sport(sport)))
    if kind is not None:
        q = q.where(A.kind == kind)
    out = []
    for a, o in s.execute(q.order_by(A.id)).all():
        out.append(Row(a.id, a.observation_id, o.source, o.endpoint, o.poll_label, o.status, o.kickoff_at,
                       getattr(a.sport, "value", a.sport), a.kind, a.player_id, a.source_player_id, a.player_name,
                       a.team_id, a.source_team, a.match_id, a.attrs, a.source_stamp, a.recorded_at))
    return out


def clock_of(r: Row, clock: str) -> datetime | None:
    if clock not in CLOCKS:
        raise Refused(f"REFUSED: clock {clock!r} is not one of {', '.join(CLOCKS)}")
    return r.recorded_at if clock == "recorded" else r.source_stamp


def player_key(r: Row) -> tuple:
    """The player's identity in the record: the SOURCE'S OWN id, else its name verbatim, and ours only where the
    source gave neither. Our ids are joined for display, never used for identity, so a mapping that lands between two
    fetches (an unmapped "partial" fetch, then a mapped one; or player-id mapping arriving for every NFL and NHL
    player) never splits one source fact into two; and a name is never matched to an id (law 4)."""
    if r.source_player_id is not None:
        return ("src", r.source_player_id)
    return ("name", r.player_name) if r.player_name is not None else ("id", r.player_id)


def team_key(r: Row) -> tuple:
    """The team's identity in the record: the source's text verbatim, and ours only where the source gave none (as
    player_key: a mapping never splits a fact or a slot)."""
    return ("src", r.source_team) if r.source_team is not None else ("id", r.team_id)


def fact_key(r: Row) -> tuple:
    """Item 1(b): the same (kind, player, team[, match]), per source, on the source's own identifiers."""
    return (r.source, r.kind, player_key(r), team_key(r), r.match_id)


def slot_key(r: Row) -> tuple | None:
    """The slot an assertion gives its player, or None where the kind has none: a depth chart's (team, group, slot,
    rank); a starter's (match, team); plays_for's player (one team at a time). inactive and injury_status have no slot
    (only the fact itself closes them)."""
    at = r.attrs or {}
    if r.kind == "depth_rank":
        if at.get("pos_slot") is None or at.get("pos_rank") is None:
            return None
        return (r.source, r.kind, team_key(r), at.get("pos_grp"), str(at["pos_slot"]), str(at["pos_rank"]))
    if r.kind in STARTER_KINDS:
        return (r.source, r.kind, r.match_id, team_key(r)) if r.match_id is not None else None
    if r.kind == "plays_for":
        return (r.source, r.kind, player_key(r))
    return None


def _sig(r: Row) -> str:
    return json.dumps({k: v for k, v in (r.attrs or {}).items() if k not in VOLATILE_ATTRS}, sort_keys=True,
                      default=str)


def _groups(rows: Iterable[Row], clock: str) -> list[tuple[datetime, list[Row]]]:
    """The assertions made together (one observation, one source stamp), ordered by the chosen clock, then the other
    stamp, then the observation. Under the source clock an assertion with no source stamp is not read."""
    by: dict = {}
    for r in rows:
        c = clock_of(r, clock)
        if c is None:
            continue
        by.setdefault((r.observation_id, r.source_stamp), []).append(r)
    other = (lambda r: r.source_stamp) if clock == "recorded" else (lambda r: r.recorded_at)

    def order(g):
        r = g[0]
        o = other(r)
        return (clock_of(r, clock), o is not None, o or datetime.min, r.observation_id)
    return [(clock_of(g[0], clock), sorted(g, key=lambda r: r.id)) for g in sorted(by.values(), key=order)]


def derive(rows: Iterable[Row], clock: str = "recorded") -> list[Interval]:
    """THE DERIVED INTERVAL (item 1(b)). Each group of assertions made together restates, closes or opens:
    - an open interval whose fact the group asserts with the same attrs is RESTATED (it stays open);
    - an open interval whose fact (kind, player, team[, match]) the group asserts, but not with its attrs, is CLOSED
      ("asserted differently");
    - an open interval whose slot the group gives to another player, and which the group does not restate, is CLOSED
      ("slot asserted to someone else");
    - every assertion that restates nothing OPENS an interval at the group's clock.
    Facts of different sources never touch. Assertions made together never close each other (two goalies in net are
    two open intervals). Returns every interval in the order opened."""
    out: list[Interval] = []
    open_: list[Interval] = []
    for c, g in _groups(rows, clock):
        continuing: set = set()
        opened: dict = {}
        by_fact: dict = {}
        for iv in open_:
            by_fact.setdefault((fact_key(iv.first), _sig(iv.first)), []).append(iv)
        for r in g:
            k = (fact_key(r), _sig(r))
            hit = by_fact.get(k)
            if hit:
                for iv in hit:
                    iv.last = r
                    iv.restated += 1
                    iv.members.append(r)
                    continuing.add(id(iv))
                continue
            if k in opened:
                opened[k].last = r
                opened[k].restated += 1
                opened[k].members.append(r)
                continue
            opened[k] = Interval(first=r, last=r, start=c, members=[r])
        facts = {}
        slots: dict = {}
        for r in g:
            facts.setdefault(fact_key(r), r)
            sk = slot_key(r)
            if sk is not None:
                slots.setdefault(sk, {}).setdefault(player_key(r), r)
        still = []
        for iv in open_:
            if id(iv) in continuing:
                still.append(iv)
                continue
            fk, sk = fact_key(iv.first), slot_key(iv.first)
            if fk in facts:
                iv.end, iv.closed_by, iv.why_closed = c, facts[fk], "asserted differently"
            elif sk in slots and set(slots[sk]) - {player_key(iv.first)}:
                other = next(r for p, r in slots[sk].items() if p != player_key(iv.first))
                iv.end, iv.closed_by, iv.why_closed = c, other, "slot asserted to someone else"
            else:
                still.append(iv)
        new = list(opened.values())
        out.extend(new)
        open_ = still + new
    return out


@dataclass
class Fact:
    """A fact in force at an instant: its interval, both stamps (via its rows), and its labels. backfilled is read
    over the interval's members (its opening row and every restatement up to the instant): True only when EVERY member
    is backfilled, False once one fresh, in-cadence row restates it (a QB1 who never changed opens on the first
    fetch's history rows and is restated fresh on every later fetch: he is in the live-era record). live_since is the
    recorded_at of the first member that is not backfilled: the earliest instant the fact is in the live-era record."""
    interval: Interval
    backfilled: bool | None               # None: the source has no ruled cadence (law 4: unknown, not "no")
    post_hoc: bool | None                 # None: no stored kickoff to compare (a league-wide file)
    live_since: datetime | None = None    # the first fresh member's recorded_at; None while every member is backfilled


def backfilled(r: Row) -> bool | None:
    """Item 1: "recorded_at later than source_stamp by more than the feed's cadence". False where the source gives no
    stamp; None where the source has no ruled cadence."""
    if r.source_stamp is None:
        return False
    cad = CADENCE.get(r.source)
    if cad is None:
        return None
    return r.recorded_at - r.source_stamp > cad


def interval_backfilled(iv: Interval) -> bool | None:
    """The interval's label: False when any member is fresh (not backfilled), True when every member is backfilled,
    else None (no ruled cadence)."""
    marks = [backfilled(r) for r in (iv.members or [iv.first])]
    if any(m is False for m in marks):
        return False
    return True if all(m is True for m in marks) else None


def live_since(iv: Interval) -> datetime | None:
    """The recorded_at of the first member that is not backfilled (our clock), or None."""
    fresh = [r.recorded_at for r in (iv.members or [iv.first]) if backfilled(r) is False]
    return min(fresh) if fresh else None


def post_hoc(r: Row) -> bool | None:
    """Item 5: "a fact recorded after its game is post hoc and labelled so"; eventual_starter always is (item 3(b))."""
    if r.kind in POST_HOC_KINDS:
        return True
    if r.kickoff_at is None:
        return None
    return r.recorded_at >= r.kickoff_at


def _team_matches(r: Row, team) -> bool:
    if team is None:
        return True
    t = str(team)
    return r.source_team == t or (t.isdigit() and r.team_id == int(t))


def _keep(r: Row, match_id, team) -> bool:
    return (match_id is None or r.match_id == match_id) and _team_matches(r, team)


def _instant(v) -> datetime:
    if not isinstance(v, datetime):
        raise Refused(f"REFUSED: the instant {v!r} is not a datetime")
    return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo is not None else v


def as_of(s, sport, instant: datetime, clock: str = "recorded", match_id: int | None = None, team=None,
          kind: str | None = None) -> list[Fact]:
    """THE AS-OF QUERY (item 2): the facts in force at `instant` under `clock`: derive() over the assertions whose
    clock is at or before the instant, the intervals still open. The derivation runs over the sport (and kind) whole;
    the match and team filters pick from its result, so a closure by another team's row (plays_for) is never lost."""
    if kind is not None and kind not in KINDS:
        raise Refused(f"REFUSED: kind {kind!r} is not in the vocabulary ({', '.join(KINDS)})")
    t = _instant(instant)
    rows = [r for r in load_rows(s, sport, kind) if (clock_of(r, clock) is not None and clock_of(r, clock) <= t)]
    return [Fact(iv, interval_backfilled(iv), post_hoc(iv.first), live_since(iv)) for iv in derive(rows, clock)
            if iv.end is None and _keep(iv.first, match_id, team)]


def history(s, sport, instant: datetime, clock: str = "recorded", match_id: int | None = None, team=None,
            kind: str | None = None) -> list[tuple[Row, Interval]]:
    """--history (item 2): every assertion for the key with its clock at or before the instant, in time order, each
    with the interval it opened or restated (its derived end), so a flip shows. The same derive() as as_of."""
    if kind is not None and kind not in KINDS:
        raise Refused(f"REFUSED: kind {kind!r} is not in the vocabulary ({', '.join(KINDS)})")
    t = _instant(instant)
    rows = [r for r in load_rows(s, sport, kind) if (clock_of(r, clock) is not None and clock_of(r, clock) <= t)]
    member = {r.id: iv for iv in derive(rows, clock) for r in iv.members}
    order = [r for _, g in _groups(rows, clock) for r in g]          # time order: the derivation's own
    return [(r, member[r.id]) for r in order if _keep(r, match_id, team)]


def unread_under_source_clock(s, sport, kind: str | None = None) -> int:
    """How many assertions carry no source stamp (law 4: counted where the source clock does not read them)."""
    return sum(r.source_stamp is None for r in load_rows(s, sport, kind))


# ---- printing (the cli's lines; the same objects a term reads) ----------------------------------------------------------

def _z(d: datetime | None) -> str:
    return d.isoformat(sep="T", timespec="seconds") + "Z" if d is not None else "—"


def _who(r: Row) -> str:
    if r.player_id is not None:
        return f"player #{r.player_id}" + (f" {r.player_name!r}" if r.player_name else "")
    ident = f"src {r.source_player_id}" if r.source_player_id else "no source id"
    return f"player UNMAPPED ({ident}, {r.player_name!r})"


def _team(r: Row) -> str:
    return f"team #{r.team_id}" if r.team_id is not None else f"team UNMAPPED ({r.source_team!r})"


def _obs(r: Row) -> str:
    poll = f" {r.poll_label}" if r.poll_label else ""
    return f"obs #{r.observation_id} {r.source}{poll} {r.obs_status} <{r.endpoint}>"


def _labels(bf: bool | None, ph: bool | None, stamped: bool) -> str:
    """The labels a fact line (as of) and a history line (per assertion) both carry, the same words."""
    labels = []
    if bf:
        labels.append("BACKFILLED (source-stamped backtests only; never the live-era record)")
    elif bf is None and stamped:
        labels.append("backfill unknown (no ruled cadence)")
    if ph:
        labels.append("POST HOC")
    return "".join(f" · {x}" for x in labels)


def fact_line(f: Fact) -> str:
    iv, r = f.interval, f.interval.first
    match = f" · match #{r.match_id}" if r.match_id is not None else ""
    rest = (f" · restated {iv.restated}x, last {_obs(iv.last)} recorded_at {_z(iv.last.recorded_at)}"
            if iv.restated else "")
    live = (f" · live-era from {_z(f.live_since)} (first seen in backfilled history, restated fresh)"
            if f.live_since is not None and backfilled(r) else "")
    return (f"  {r.kind} · {_who(r)} · {_team(r)}{match} · attrs {json.dumps(r.attrs or {}, sort_keys=True)} · "
            f"recorded_at {_z(r.recorded_at)} · source_stamp {_z(r.source_stamp)} · {_obs(r)}{rest}{live}"
            + _labels(f.backfilled, f.post_hoc, r.source_stamp is not None))


def history_line(r: Row, iv: Interval) -> str:
    """One assertion, with the interval it opened or restated, and its own labels (the row's: a history line is one
    assertion, so BACKFILLED here is that row's, as recorded)."""
    role = "opened" if iv.first.id == r.id else f"restated #{iv.first.id}"
    end = (f"ended {_z(iv.end)} ({iv.why_closed}, by assertion #{iv.closed_by.id})" if iv.end is not None
           else "open")
    return (f"  #{r.id} {r.kind} · {_who(r)} · {_team(r)}" + (f" · match #{r.match_id}" if r.match_id else "")
            + f" · attrs {json.dumps(r.attrs or {}, sort_keys=True)} · recorded_at {_z(r.recorded_at)} · "
              f"source_stamp {_z(r.source_stamp)} · {_obs(r)} · {role} · {end}"
            + _labels(backfilled(r), post_hoc(r), r.source_stamp is not None))


def attributions(sources: Iterable[str]) -> list[str]:
    """The attribution lines for the sources whose facts an output shows (item 3(a))."""
    return [SOURCES[x] for x in sorted(set(sources)) if SOURCES.get(x)]


__all__ = ["SOURCES", "STATUSES", "KINDS", "CLOCKS", "CADENCE", "TABLES", "TRIGGERS", "MIGRATION_MARKER", "APPEND_ONLY",
           "Refused", "Receipt", "write_observation", "migrated", "redact", "payload_path_refusal", "Row", "Interval",
           "Fact", "load_rows", "derive", "as_of", "history", "backfilled", "interval_backfilled", "live_since",
           "post_hoc", "attributions"]
