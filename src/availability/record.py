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
logs/availability/<source>/<YYYY-MM-DD>/ (so never under data/); a per-game fact without attrs.source_match_id from
a source in SOURCE_MATCH_IDS; an observation of a snapshot source (SNAPSHOT_SOURCES) that asserts a row and keeps no
payload_sha256 (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 1: the hash is the load's identity; the insert guard
trg_availability_assertions_snapshot_hash_guard refuses it around the writer too); an assertion of a snapshot source
with no source_player_id (262 item 5: never keyed by name); a missing DB
file (never created, law 5); a store migrate_availability_record.py has not migrated. The error text is redacted,
then cut to 256 characters. A poll the store already holds (the unique keys: source, match, stored kickoff, poll;
and, #835 item 2, source, endpoint, scheduled time) is counted "already", its row standing.
There is no update, delete or upsert function here, and the tables' triggers abort one from anywhere else.

THE MAPPING (item 1, law 4): a player or team the caller cannot map is written with player_id / team_id NULL and the
source's id and text beside it; the receipt counts the unmapped players, teams and per-game facts without a match.
Nothing here maps by name. The read keys a fact and a slot on the SOURCE'S OWN identifiers (its player id, else the
name verbatim; its team text; a per-game fact's attrs.source_match_id, which the writer requires from a source in
SOURCE_MATCH_IDS), ours only where the source gave none: our ids are joined for display, from the interval's LATEST
member that carries each id, and filter from it too, so a mapping that lands between two fetches, in either direction,
never splits one source fact into two and never hides it (Codex on #831, round 1).

THE READ. derive() turns assertions into intervals (item 1(b): "a fact holds from its observation to the next
observation of the same source that asserts the same (kind, player, team[, match]) differently, or that asserts the
slot to someone else"); as_of() is derive() over the assertions whose chosen clock is at or before the instant, keeping
the intervals still open; history() is every assertion, in time order, with the end of the interval it belongs to.
Both READ BOUNDED (Codex on #841, round 1; the section "the bounded read" below): the clock and the key in SQL, the
derivation partition by partition, the answer the full derivation's (pinned against load_rows + derive).
A LOAD of a snapshot source (SNAPSHOT_SOURCES: nflverse_depth_charts' depth_rank rows from a kept payload) also closes
every fact of each team it holds that it does not restate, a partial team group closing nothing (ARCHITECT 2026-11-05,
addendum 259 item 2(a)-(b); derive()); every such load carries its payload hash (the writer requires it, addendum 262
item 1), and a team group that lost a refused row (attrs.rows_refused, 262 item 5) is partial.
THE TWO CLOCKS (item 1, ruled): `recorded_at` is our knowledge, `source_stamp` the source's claim. Under the recorded
clock an assertion exists from its fetch, so a backfilled row never appears before it; under the source clock an
assertion with no source stamp is not read (counted, never filled from recorded_at). Every fact carries both stamps.
A fact reads BACKFILLED only while every member of its interval is backfilled: one fresh restatement puts it in the
live-era record, from that row's recorded_at (Fact.live_since). A --history line carries its own row's labels.
POST HOC (item 5) compares a per-game fact's recorded_at with its observation's stored kickoff (as stored at fetch
time), else with the kickoff our matches table stores for its match (a league-wide file stores none) AS STORED AT READ
TIME, not as of the instant, so a later re-date can change a past read's label; with neither, the fact reads "kickoff
unknown", never pregame (law 4).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from dataclasses import replace as _with   # private: the module exposes no name matching update/replace (test 6(a))
from datetime import date, datetime, timedelta, timezone
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Iterable, Iterator, Sequence
from urllib.parse import unquote, urlsplit

from src.db.schema import (APPEND_ONLY, AVAILABILITY_KINDS, AVAILABILITY_SNAPSHOT_SOURCES, AVAILABILITY_SOURCES,
                           AVAILABILITY_STATUSES, AVAILABILITY_TRIGGERS, Sport)

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
# THE BACKFILL CADENCE, in hours per source word (item 1: "recorded_at later than source_stamp by more than the feed's
# cadence"), frozen by addendum 259 item 2(d): "THE CADENCE CONSTANT: SOURCE_CADENCE_HOURS["nflverse_depth_charts"] =
# 24, frozen with the PR (254 item 2(2))". 254 item 2(2): "a frozen constant per source word (`SOURCE_CADENCE_HOURS`)
# [...] "backfill unknown", never "not backfilled", where no cadence is declared". A source with no entry has no ruled
# cadence: its stamped facts read "backfill unknown" (law 4). Read-only (a mapping proxy): a cadence moves only by a
# ruling and a PR, never at run time.
SOURCE_CADENCE_HOURS = MappingProxyType({"nflverse_depth_charts": 24})
# attrs keys a restatement may change without asserting the fact differently: the source's raw time text (its stamp
# is source_stamp, compared nowhere as a fact) and the source's player ids kept beside source_player_id (identity, not
# the fact: nflverse_depth_charts' espn_id and gsis_id, addendum 252 item 3(a))
# and ROWS_REFUSED_ATTR below (a count the adapter keeps on a load's team group, not the fact: addendum 262 item 5)
VOLATILE_ATTRS = ("dt_raw", "espn_id", "gsis_id", "rows_refused")
# THE SNAPSHOT SOURCES (ARCHITECT 2026-11-05 10:10 ET, addendum 259 item 2(a)-(b); 254 item 2(6)): a source whose
# every load (one source stamp in one observation) is the WHOLE chart of each team present in it. 259 item 1 read the
# real files: "EVERY LOAD IS A FULL 32-TEAM SNAPSHOT [...] A team's rows at one dt are its WHOLE chart, not its
# changes". The kind each one snapshots: only it closes by the rule (derive, below). No other source reads this way.
SNAPSHOT_SOURCES = MappingProxyType(dict(AVAILABILITY_SNAPSHOT_SOURCES))   # schema.py declares it (its insert guard)
# WHAT COUNTS AS A LOAD (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 1, verbatim in part): "for a SNAPSHOT source
# [...] the WRITER REQUIRES `payload_sha256` on every observation that asserts a row -- the hash is the load's identity
# (252 item 1(a)) and "has a hash" then means exactly "is a real load". An observation of a snapshot source with rows
# and no hash is REFUSED by the insert guard with its reason; `failed` and `missed` observations carry no payload and
# assert nothing, as before." The insert guard is the trigger schema.py names trg_availability_assertions_snapshot_
# hash_guard (a raw INSERT is refused with the reason); write_observation refuses the same before any session opens;
# snapshot_load's hash test stays, redundant by construction.
# THE REFUSED-ROW GUARD (addendum 262 item 5, #840): "a row with a blank `espn_id` is counted and refused into the
# group's `partial` status, never keyed by name". The adapter asserts the rest of that (dt, team) group with
# attrs[ROWS_REFUSED_ATTR] = the count of its rows refused; derive() reads such a team group of a load as partial (it
# closes nothing, and is never a previous complete group), as the partial guard reads a short one. "Never keyed by
# name" holds at the record too: the writer refuses an assertion of a snapshot source that carries no
# source_player_id (player_key would key it by its name), with its reason (_snapshot_id_refusal; assertion_refusal
# runs it, so the adapter's pre-check does). The writer refuses the observation; the adapter, which never passes such
# a row, is what counts it into its group's partial status.
ROWS_REFUSED_ATTR = "rows_refused"
assert ROWS_REFUSED_ATTR in VOLATILE_ATTRS
# 259 item 2(b): "a (dt, team) group with fewer than HALF the rows of that team's previous complete group is `partial`
# FOR THAT TEAM [...] The first group ever seen for a team is complete by definition."
PARTIAL_GROUP_FRACTION = 0.5
# THE SOURCE'S OWN GAME ID (Codex on #831, round 1): a per-game fact (GAME_KINDS) from a source listed here must carry
# attrs.source_match_id, the source's id for the game, so a fact first recorded before its game maps to our match_id
# and restated after is ONE fact (and its slot closes). nhl_api_landing: the NHL gameId (item 3(b): the landing and
# boxscore URLs' game id). nflverse_depth_charts asserts no per-game fact (item 3(a): depth_rank only). The paid feed's
# entry comes with its adapter's specification (item 3(c)). A source not listed keys its per-game facts on match_id.
SOURCE_MATCH_IDS = {"nhl_api_landing": "the NHL gameId"}

OBS_TABLE = "availability_observations"
ASR_TABLE = "availability_assertions"
TABLES = (OBS_TABLE, ASR_TABLE)
TRIGGERS = tuple(name for name, _, _ in AVAILABILITY_TRIGGERS)
MIGRATION_MARKER = "availability_record_migration"
WRITE_CHUNK = 5000                                   # assertions per INSERT batch (one transaction for them all)
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
# A NAME may carry percent escapes (#835 item 1; ARCHITECT 2026-11-05 09:40 ET, addendum 258 item 2(1): "`_PARAM` admits
# `%` escapes and classifies the decoded name"): "api%5Ftoken", "s%69g" and "%6Bey" are read as api_token, sig, key.
_PARAM = re.compile(r"(?<![\w%-])((?:[A-Za-z]|%[0-9A-Fa-f]{2})(?:[\w-]|%[0-9A-Fa-f]{2})*)([\"']?\s*[=:]\s*[\"']?)"
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
    """(name, value start, value end) for every credential-like name=value / name: value in the text. The name is
    classified percent-decoded (#835 item 1: "classifies the decoded name"); the span is the raw text's."""
    return [(m.group(1), m.end(2), m.end(2) + len(m.group(3))) for m in _PARAM.finditer(text)
            if _cred_name(unquote(m.group(1)))]


def _decoded(text: str) -> str:
    """The text percent-decoded until it no longer changes (at most three rounds: a doubly encoded name is read too)."""
    out = text
    for _ in range(3):
        nxt = unquote(out)
        if nxt == out:
            break
        out = nxt
    return out


def _redact_once(text: str) -> str:
    out = text
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


def redact(text: str | None) -> str | None:
    """The error text with every secret the environment holds, every URL's userinfo (user:password@), every
    credential-like value (a URL parameter, a header, a quoted dict or JSON key, with its auth scheme's token) and
    every bearer token replaced (the deploy's redact rule, deploy/hosting/sp_common.py, widened: addendum 252 item
    1(a), "error (redacted)"; the rows are append-only, so a secret that got through could never be removed).
    PERCENT-ENCODED (#835 item 1; ARCHITECT 2026-11-05 09:40 ET, addendum 258 item 2(1): "`redact` runs on the decoded
    string as well as the raw one"): the raw text is redacted first; then its percent-decoded form is redacted too, and
    where that finds something the raw reading did not (an encoded separator, "api_token%3D…", or an encoded value of a
    secret environment variable), the DECODED, redacted text is the one returned: a secret is never kept for the sake
    of the raw spelling."""
    if text is None:
        return None
    out = _redact_once(str(text))
    dec = _decoded(out)
    if dec != out:
        dec_r = _redact_once(dec)
        if dec_r != dec:
            return dec_r
    return out


def _endpoint_secret(endpoint: str) -> str | None:
    """Why the endpoint carries a secret, or None (item 5: "no secret in an endpoint string"): a secret environment
    value, credentials in the URL itself (user:password@ or a token as the user), or a credential-like parameter.
    PERCENT-ENCODED (#835 item 1; addendum 258 item 2(1): "`_endpoint_secret` checks the percent-decoded endpoint too
    (unquote) for credential names and for environment values"): every check runs on the raw endpoint and again on its
    decoded form, and the reason says which form carried it."""
    dec = _decoded(endpoint)
    for text, form in ((endpoint, ""), (dec, " (percent-decoded)")):
        if form and text == endpoint:
            break
        if any(v in text for v in _secret_values()):
            return f"it holds a value of a secret environment variable{form}"
        try:
            u = urlsplit(text)
            userinfo = u.username is not None or u.password is not None
        except ValueError:
            return f"it is not a URL the check can read{form} (refused, never guessed)"
        if userinfo or _USERINFO.search(text):
            return f"it carries credentials in the URL (userinfo before '@'){form}"
        spans = _cred_spans(text)
        if spans:
            return f"it holds a credential-like parameter ({unquote(spans[0][0])!r}){form}"
    return None


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


ENDPOINT_LIMIT = 512                                 # characters (the column's width)


def endpoint_refusal(ep) -> str | None:
    """Why the writer refuses this endpoint, or None: none given, longer than ENDPOINT_LIMIT, or carrying a secret
    (item 5). The writer's one check (_check_observation); an adapter runs it BEFORE it writes any file, so a refused
    endpoint leaves nothing on disk (Codex on #841, round 1)."""
    if not isinstance(ep, str) or not ep.strip():
        return "REFUSED: no endpoint (the URL or file name)"
    if len(ep) > ENDPOINT_LIMIT:
        return f"REFUSED: the endpoint is longer than {ENDPOINT_LIMIT} characters"
    why = _endpoint_secret(ep)
    if why:
        return f"REFUSED: the endpoint carries a secret: {why} (addendum 252 item 5); nothing written"
    return None


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
    why = endpoint_refusal(ep)
    if why:
        raise Refused(why)
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


def assertion_refusal(a, i, source: str | None = None) -> str | None:
    """Why the writer refuses this assertion, or None: the writer's own checks (_check_assertion: the columns, the
    vocabulary, the widths -- source_player_id and source_team 64 characters, player_name 128 -- a player and a team
    named, attrs as JSON) and, for a per-game fact from a source in SOURCE_MATCH_IDS, the source's game id. The same
    functions write_observation runs; an adapter runs it on every row it will assert BEFORE it keeps any file, so a row
    the writer would refuse leaves nothing on disk (Codex on #841, round 1). `i` names the row in the reason."""
    try:
        r = _check_assertion(a, i)
        if source in SOURCE_MATCH_IDS and r["kind"] in GAME_KINDS:
            _with_source_match_id(r["attrs"], i, source)
    except Refused as e:
        return str(e)
    return _snapshot_id_refusal(r, i, source)


def _snapshot_id_refusal(r: dict, i: int, source: str | None) -> str | None:
    """Why an assertion of a snapshot source is refused for want of the source's player id, or None (addendum 262 item
    5: a row with no id is "never keyed by name"; player_key keys a row with no source_player_id by its name)."""
    if source in SNAPSHOT_SOURCES and r["source_player_id"] is None:
        return (f"REFUSED: assertion {i} of the snapshot source {source} carries no source_player_id: a row is never "
                f"keyed by name (addendum 262 item 5); nothing written")
    return None


def _with_source_match_id(attrs: dict | None, i: int, source: str) -> dict:
    """attrs with source_match_id as text, or Refused: a per-game fact from a source in SOURCE_MATCH_IDS keeps the
    source's own game id (the stable identity across our match mapping)."""
    v = (attrs or {}).get("source_match_id")
    if isinstance(v, bool) or not isinstance(v, (str, int)) or not str(v).strip():
        raise Refused(f"REFUSED: assertion {i}: a per-game fact from {source} carries attrs.source_match_id "
                      f"({SOURCE_MATCH_IDS[source]}); none given, nothing written")
    if len(str(v)) > 64:
        raise Refused(f"REFUSED: assertion {i}: attrs.source_match_id is longer than 64 characters")
    return {**attrs, "source_match_id": str(v)}


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
    if rows and row["source"] in SNAPSHOT_SOURCES and row["payload_sha256"] is None:
        raise Refused(f"REFUSED: an observation of the snapshot source {row['source']} asserts {len(rows)} row(s) and "
                      f"keeps no payload_sha256: the hash is the load's identity, so a load without one is not a load "
                      f"(addendum 262 item 1; 252 item 1(a)); nothing written")
    for i, r in enumerate(rows, 1):
        why = _snapshot_id_refusal(r, i, row["source"])
        if why:
            raise Refused(why)
    if row["source"] in SOURCE_MATCH_IDS:
        for i, r in enumerate(rows, 1):
            if r["kind"] in GAME_KINDS:
                r["attrs"] = _with_source_match_id(r["attrs"], i, row["source"])
    path = _db_file()
    if path is None or not path.is_file():
        raise Refused(f"REFUSED: no DB file at {path or 'a non-file database URL'}: the record never creates one "
                      "(law 5)")
    from sqlalchemy import insert
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
            # one executemany INSERT, in chunks (a season file is ~750,000 rows: no ORM object per row), in the same
            # transaction: the insert triggers fire for every row as before (no backdating, recorded_at, sport)
            for i in range(0, len(rows), WRITE_CHUNK):
                s.execute(insert(AvailabilityAssertion),
                          [{**r, "observation_id": o.id, "sport": row["sport"], "recorded_at": row["fetched_at"]}
                           for r in rows[i:i + WRITE_CHUNK]])
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

@dataclass(frozen=True, slots=True)
class Row:
    """One assertion with the observation it came from. Slotted (no per-row __dict__): a read may hold a season's rows."""
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
    match_kickoff: datetime | None = None   # matches.utc_date for match_id, read in the same session (not a column)
    payload_sha256: str | None = None       # its observation's payload hash (a load of a kept file: snapshot_load)


@dataclass(eq=False)
class Interval:
    """A derived interval: the assertion that opened it, its latest restatement, and the group that closed it.
    `members` is every row it holds (the opening row and each restatement, in derivation order): derive() and history
    keep them. as_of keeps NO members (members None) but a Summary (summary): the labels' running values, so an open
    interval restated daily for a season holds two rows, not three hundred (Codex on #841, round 1; addendum 262 item
    4). Every label reads either one alike (interval_backfilled, live_since, mapped_now)."""
    first: Row
    last: Row
    start: datetime
    end: datetime | None = None
    closed_by: Row | None = None
    why_closed: str | None = None         # "asserted differently" | "slot asserted to someone else" |
    #                                       "not restated in its team's snapshot" (a snapshot source's load, 259 2(a))
    restated: int = 0
    members: list | None = field(default_factory=list)
    summary: Summary | None = None        # as_of's: the labels' running values in place of the members


class Summary:
    """What as_of's labels read of an interval's members, kept as each member is added (in derivation order, the
    order `members` holds them), so the members themselves need not be: for interval_backfilled, whether any member is
    fresh (backfilled False) and whether every member is backfilled (True); for live_since, the earliest recorded_at of
    a fresh member; for mapped_now, the latest player_id, team_id and match_id (with that member's match_kickoff) that
    a member carries. The same values the members give: the equivalence test compares the two on randomized histories.
    """
    __slots__ = ("any_fresh", "all_backfilled", "live", "player_id", "team_id", "match_id", "match_kickoff")

    def __init__(self, r: Row):
        self.any_fresh, self.all_backfilled, self.live = False, True, None
        self.player_id = self.team_id = self.match_id = self.match_kickoff = None
        self.add(r)

    def add(self, r: Row) -> None:
        m = backfilled(r)
        if m is False:
            self.any_fresh = True
            self.live = r.recorded_at if self.live is None or r.recorded_at < self.live else self.live
        if m is not True:
            self.all_backfilled = False
        if r.player_id is not None:
            self.player_id = r.player_id
        if r.team_id is not None:
            self.team_id = r.team_id
        if r.match_id is not None:
            self.match_id, self.match_kickoff = r.match_id, r.match_kickoff


READ_BATCH = 2000                                    # rows per cursor fetch on a bounded read (yield_per)


def _select(sport, kind: str | None = None):
    """The read's one SELECT: each assertion's columns, its observation's, and the kickoff our matches table stores for
    its match_id (a LEFT JOIN on matches.id, the primary key: None where the match is unmapped or not stored). Plain
    columns, no ORM object per row."""
    from sqlalchemy import select

    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    from src.db.schema import Match
    q = (select(A.id, A.observation_id, O.source, O.endpoint, O.poll_label, O.status, O.kickoff_at, A.sport, A.kind,
                A.player_id, A.source_player_id, A.player_name, A.team_id, A.source_team, A.match_id, A.attrs,
                A.source_stamp, A.recorded_at, Match.utc_date, O.payload_sha256)
         .join(O, O.id == A.observation_id).outerjoin(Match, Match.id == A.match_id)
         .where(A.sport == _sport(sport)))
    return q.where(A.kind == kind) if kind is not None else q


class _Rows:
    """Builds Row objects from the SELECT's tuples, sharing one object per equal value: per observation its columns
    (source, endpoint, poll label, status, kickoff, payload hash, recorded_at), per match its stored kickoff, and one
    object per equal text or stamp among the row's own columns and its attrs' keys and short text values (each row keeps
    its own attrs dict). The values are equal either way; only the memory differs."""

    def __init__(self):
        self.obs: dict = {}
        self.kickoff: dict = {}
        self.same: dict = {}

    def _one(self, v):
        if v is None or (isinstance(v, str) and len(v) > 64):
            return v
        return self.same.setdefault(v, v) if isinstance(v, (str, datetime)) else v

    def __call__(self, t) -> Row:
        (aid, oid, source, endpoint, poll, status, ko, sport, kind, pid, spid, name, tid, steam, mid, attrs, stamp,
         recorded, mko, sha) = t
        o = self.obs.get(oid)
        if o is None:
            o = self.obs[oid] = (source, endpoint, poll, status, ko, sha, recorded)
        if mid is not None and mid not in self.kickoff:
            self.kickoff[mid] = _naive_utc(mko, "matches.utc_date")
        one = self._one
        if type(attrs) is dict:
            attrs = {one(k): one(v) for k, v in attrs.items()}
        return Row(aid, oid, o[0], o[1], o[2], o[3], o[4], getattr(sport, "value", sport), one(kind), pid, one(spid),
                   one(name), tid, one(steam), mid, attrs, one(stamp), o[6] if recorded == o[6] else recorded,
                   self.kickoff.get(mid) if mid is not None else None, o[5])


def load_rows(s, sport, kind: str | None = None) -> list[Row]:
    """Every assertion of the sport (and kind), with its observation, and the kickoff our matches table stores for its
    match_id (Row.match_kickoff; None where the match is unmapped or not stored), in id order. Read only; the caller's
    session. THE FULL MATERIALISATION: as_of and history no longer call it (Codex on #841, round 1: they read bounded,
    partition by partition, _partitions); it stays the reference the equivalence tests compare them with."""
    from src.db.schema import AvailabilityAssertion as A
    build = _Rows()
    return [build(t) for t in _run(s, _select(sport, kind).order_by(A.id))]


def _run(s, q):
    """A read's SELECT on the session's connection (Core: no ORM loading layer per row)."""
    return s.connection().execute(q)


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


def match_key(r: Row) -> tuple | None:
    """The game's identity in the record: the source's own game id (attrs.source_match_id; the writer requires it from
    a source in SOURCE_MATCH_IDS), else our match_id, else None (a team-level fact, or a per-game fact of a source with
    no game id whose match is unmapped). The source's id never changes when our match maps (Codex on #831, round 1)."""
    v = (r.attrs or {}).get("source_match_id")
    if v is not None:
        return ("src", str(v))
    return ("id", r.match_id) if r.match_id is not None else None


def fact_key(r: Row) -> tuple:
    """Item 1(b): the same (kind, player, team[, match]), per source, on the source's own identifiers."""
    return (r.source, r.kind, player_key(r), team_key(r), match_key(r))


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
        mk = match_key(r)
        return (r.source, r.kind, mk, team_key(r)) if mk is not None else None
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
    return [(clock_of(g[0], clock), sorted(g, key=lambda r: r.id))
            for g in sorted(by.values(), key=lambda g: _group_order(g[0], clock))]


def _group_order(r: Row, clock: str) -> tuple:
    """The place of r's group (one observation, one source stamp) in the derivation: the chosen clock, then the other
    stamp, then the observation. Every row of a group has the same, and no two groups share one."""
    o = r.source_stamp if clock == "recorded" else r.recorded_at
    return (clock_of(r, clock), o is not None, o or datetime.min, r.observation_id)


def snapshot_load(g: Sequence[Row]) -> bool:
    """True when the group (one observation, one source stamp) is a LOAD of a snapshot source (SNAPSHOT_SOURCES): every
    row of that source and kind, from an observation that keeps its payload's hash (the adapter's: a fetched or a
    hand-carried release file, whose bytes are on disk). Since addendum 262 item 1 the writer refuses a snapshot
    source's rows without a hash, so the hash test is redundant by construction ("the right kind of redundancy"): it
    stays, so a store written before that rule never reads a hashless group as a load."""
    if not g:
        return False
    src = g[0].source
    kind = SNAPSHOT_SOURCES.get(src)
    return kind is not None and all(r.source == src and r.kind == kind and r.payload_sha256 is not None for r in g)


def partial_group(rows: int, previous_complete: int | None) -> bool:
    """259 item 2(b): a (dt, team) group is partial for its team when it holds fewer than HALF the rows of that team's
    previous complete group; the first group ever seen for a team (no previous complete group) is complete."""
    return previous_complete is not None and rows < previous_complete * PARTIAL_GROUP_FRACTION


def guard_load(team_rows: dict, last_complete: dict, refused: Iterable = ()) -> set:
    """The partial-group guard over one load: `team_rows` maps each team present to its row count, `last_complete`
    each team to the row count of its previous complete group (updated here for every complete group). Returns the
    teams whose group is partial (259 item 2(b)). `refused` names the teams whose group lost a row the adapter refused
    (attrs[ROWS_REFUSED_ATTR]; addendum 262 item 5): partial whatever their size, never a previous complete group. One
    rule for derive() and the adapter's receipt."""
    partial = set()
    refused = set(refused)
    for team, n in team_rows.items():
        if team in refused or partial_group(n, last_complete.get(team)):
            partial.add(team)
        else:
            last_complete[team] = n
    return partial


def derive(rows: Iterable[Row], clock: str = "recorded") -> list[Interval]:
    """THE DERIVED INTERVAL (item 1(b)). Each group of assertions made together restates, closes or opens:
    - an open interval whose fact the group asserts with the same attrs is RESTATED (it stays open);
    - an open interval whose fact (kind, player, team[, match]) the group asserts, but not with its attrs, is CLOSED
      ("asserted differently");
    - an open interval whose slot the group gives to another player, and which the group does not restate, is CLOSED
      ("slot asserted to someone else");
    - every assertion that restates nothing OPENS an interval at the group's clock.
    Facts of different sources never touch. Assertions made together never close each other (two goalies in net are
    two open intervals). Returns every interval in the order opened.
    THE SNAPSHOT CLOSURE (ARCHITECT 2026-11-05 10:10 ET, addendum 259 item 2(a)-(b); 254 item 2(6)), for a LOAD of a
    snapshot source only (snapshot_load: SNAPSHOT_SOURCES, nflverse_depth_charts' depth_rank rows from a kept payload):
    - "a load (one dt) is a full snapshot for EVERY team present in it; a team's facts not restated at that dt CLOSE at
      that observation" ("not restated in its team's snapshot", closed by the team's first row of the load), unless an
      earlier rule above closes it first, with that rule's reason;
    - "a team absent from a load [...] keeps its facts open" (nothing of it closes);
    - THE PARTIAL GUARD: a team whose group at the load holds fewer than HALF the rows of its previous complete group is
      partial: "its rows are asserted (a fact seen is a fact), it CLOSES NOTHING, the prior facts stay open" (no rule
      closes that team's intervals at that load); the first group ever seen for a team is complete. A team group that
      lost a row the adapter refused (a blank espn_id: its rows carry attrs[ROWS_REFUSED_ATTR], addendum 262 item 5) is
      partial the same way, whatever its size.
    "Close at that load" is the group's clock: under the source clock the load's dt; under the recorded clock the
    observation's recorded_at, the groups of one fetch read in dt order (_groups), so the facts a fetch holds at its
    recorded_at are its last load's (an earlier load's intervals open and close at the same recorded_at, and history
    still lists them). No other source and no row without a payload hash is read this way."""
    return _derive(rows, clock)


def _add(iv: Interval, r: Row) -> None:
    """r restates iv: its latest member, counted, and kept (members) or summarised (summary, as_of's)."""
    iv.last = r
    iv.restated += 1
    if iv.members is not None:
        iv.members.append(r)
    else:
        iv.summary.add(r)


def _derive(rows: Iterable[Row], clock: str, not_loads: frozenset = frozenset(),
            keep_members: bool = True) -> list[Interval]:
    """derive(), over `rows`; `not_loads` names the groups (observation id, source stamp) that are NOT a load although
    the rows given of them are all the snapshot kind: a partition's share of a group whose other rows (another kind)
    the partition does not hold (_mixed_groups). derive() passes none: it holds every row of each group.
    keep_members False (as_of's): each interval keeps a Summary in place of its members (Interval); the derivation's
    rules read first, last and the keys fixed at opening, never the members, so the intervals are the same."""
    out: list[Interval] = []
    open_: list[Interval] = []
    last_complete: dict = {}              # (source, team key) -> rows of that team's previous complete group
    key_of: dict = {}                     # id(interval) -> its (fact key, attrs signature): fixed when it opens
    for c, g in _groups(rows, clock):
        snap: dict = {}                   # team key -> its first row in this load (a snapshot load only)
        partial: set = set()
        snap_src = snap_kind = None
        if snapshot_load(g) and (g[0].observation_id, g[0].source_stamp) not in not_loads:
            counts: dict = {}
            refused: set = set()
            src = g[0].source
            for r in g:
                counts[team_key(r)] = counts.get(team_key(r), 0) + 1
                snap.setdefault(team_key(r), r)
                if (r.attrs or {}).get(ROWS_REFUSED_ATTR):
                    refused.add((src, team_key(r)))      # 262 item 5: a row of this group refused: the group is partial
            partial = {t for _, t in guard_load({(src, t): n for t, n in counts.items()}, last_complete, refused)}
            snap_src, snap_kind = src, SNAPSHOT_SOURCES[src]
        continuing: set = set()
        opened: dict = {}
        by_fact: dict = {}
        for iv in open_:                  # its key: every member's (a restatement has the opening row's key)
            by_fact.setdefault(key_of[id(iv)], []).append(iv)
        keyed = [((fact_key(r), _sig(r)), r) for r in g]
        for k, r in keyed:
            hit = by_fact.get(k)
            if hit:
                for iv in hit:
                    _add(iv, r)
                    continuing.add(id(iv))
                continue
            if k in opened:
                _add(opened[k], r)
                continue
            opened[k] = (Interval(first=r, last=r, start=c, members=[r]) if keep_members
                         else Interval(first=r, last=r, start=c, members=None, summary=Summary(r)))
            key_of[id(opened[k])] = k
        facts = {}
        slots: dict = {}
        for (fk, _), r in keyed:
            facts.setdefault(fk, r)
            sk = slot_key(r)
            if sk is not None:
                slots.setdefault(sk, {}).setdefault(player_key(r), r)
        still = []
        for iv in open_:
            if id(iv) in continuing:
                still.append(iv)
                continue
            fk, sk, pk = key_of[id(iv)][0], slot_key(iv.last), player_key(iv.last)
            mine = bool(snap) and iv.last.source == snap_src and iv.last.kind == snap_kind     # this load's source and kind
            if mine and team_key(iv.last) in partial:
                still.append(iv)          # 259 item 2(b): a partial team group closes nothing; the prior facts stay open
            elif fk in facts:
                iv.end, iv.closed_by, iv.why_closed = c, facts[fk], "asserted differently"
            elif sk in slots and set(slots[sk]) - {pk}:
                other = next(r for p, r in slots[sk].items() if p != pk)
                iv.end, iv.closed_by, iv.why_closed = c, other, "slot asserted to someone else"
            elif mine and team_key(iv.last) in snap:
                iv.end, iv.closed_by, iv.why_closed = c, snap[team_key(iv.last)], "not restated in its team's snapshot"
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
    post_hoc: bool | None                 # None: no kickoff stored anywhere (law 4: "kickoff unknown", never pregame)
    live_since: datetime | None = None    # the first fresh member's recorded_at; None while every member is backfilled


def backfilled(r: Row) -> bool | None:
    """Item 1: "recorded_at later than source_stamp by more than the feed's cadence". False where the source gives no
    stamp; None where the source has no ruled cadence."""
    if r.source_stamp is None:
        return False
    hours = SOURCE_CADENCE_HOURS.get(r.source)
    if hours is None:
        return None
    return r.recorded_at - r.source_stamp > timedelta(hours=hours)


def interval_backfilled(iv: Interval) -> bool | None:
    """The interval's label: False when any member is fresh (not backfilled), True when every member is backfilled,
    else None (no ruled cadence)."""
    if iv.members is None and iv.summary is not None:            # as_of's (Summary)
        sm = iv.summary
        return False if sm.any_fresh else True if sm.all_backfilled else None
    marks = [backfilled(r) for r in (iv.members or [iv.first])]
    if any(m is False for m in marks):
        return False
    return True if all(m is True for m in marks) else None


def live_since(iv: Interval) -> datetime | None:
    """The recorded_at of the first member that is not backfilled (our clock), or None."""
    if iv.members is None and iv.summary is not None:            # as_of's (Summary)
        return iv.summary.live
    fresh = [r.recorded_at for r in (iv.members or [iv.first]) if backfilled(r) is False]
    return min(fresh) if fresh else None


def mapped_now(iv: Interval) -> Row:
    """The interval's latest member, carrying the mapping the fact has now: each of our ids (player_id, team_id,
    match_id, with the match's stored kickoff) from the LATEST member that carries one, so neither direction of a
    mapping change hides the fact: unmapped then mapped is found by the new id, and mapped then restated unmapped (a
    "partial" fetch, item 6(c); a poll whose match did not map that time) is still found by the id it had (Codex on
    #831, round 1). The first member keeps the interval's start and its original stamps."""
    if iv.members is None and iv.summary is not None:            # as_of's (Summary): the same latest ids
        sm = iv.summary
        return _with(iv.last, player_id=sm.player_id, team_id=sm.team_id, match_id=sm.match_id,
                     match_kickoff=sm.match_kickoff)
    members = iv.members or [iv.first, iv.last]
    pid = next((r.player_id for r in reversed(members) if r.player_id is not None), None)
    tid = next((r.team_id for r in reversed(members) if r.team_id is not None), None)
    m = next((r for r in reversed(members) if r.match_id is not None), None)
    return _with(iv.last, player_id=pid, team_id=tid, match_id=m.match_id if m else None,
                   match_kickoff=m.match_kickoff if m else None)


def kickoff_of(r: Row, iv: Interval | None = None) -> datetime | None:
    """The kickoff a fact is compared to, in order (Codex on #831, round 1):
    1. its observation's stored kickoff (kickoff_at): the kickoff as stored at FETCH time, a per-game fetch;
    2. else the kickoff our matches table stores (utc_date) for the match the interval names now (mapped_now: the latest
       member that carries a match_id). A league-wide file stores no kickoff, and a fact recorded before its match
       mapped names it later. This is matches.utc_date AS STORED AT READ TIME, the current kickoff, not as of the
       instant: a match re-dated later can change a past as-of read's POST HOC label, where step 1 cannot;
    3. else the kickoff utc_date stores for the match the row itself names (no interval given);
    4. else None: "kickoff unknown", never read as pregame (law 4)."""
    if r.kickoff_at is not None:
        return r.kickoff_at
    if iv is not None:
        now = mapped_now(iv)
        if now.match_kickoff is not None:
            return now.match_kickoff
    return r.match_kickoff


def post_hoc(r: Row, iv: Interval | None = None) -> bool | None:
    """Item 5: "a fact recorded after its game is post hoc and labelled so"; eventual_starter always is (item 3(b)).
    None where no kickoff is stored anywhere (kickoff_of): "kickoff unknown", never read as pregame (law 4)."""
    if r.kind in POST_HOC_KINDS:
        return True
    ko = kickoff_of(r, iv)
    if ko is None:
        return None
    return r.recorded_at >= ko


def per_game(r: Row) -> bool:
    """A per-game fact: a per-game kind, or a row that names a game (ours or the source's)."""
    return r.kind in GAME_KINDS or match_key(r) is not None


def _team_matches(r: Row, team) -> bool:
    if team is None:
        return True
    t = str(team)
    return r.source_team == t or (t.isdigit() and r.team_id == int(t))


def _keep(iv: Interval, match_id, team) -> bool:
    """The --match-id / --team filter, read on the mapping the interval carries now (mapped_now: each id from the latest
    member that carries one; Codex on #831, round 1): a fact first recorded unmapped and restated after its team or
    match mapped is found by our id, and so is a mapped fact restated unmapped."""
    r = mapped_now(iv)
    return (match_id is None or r.match_id == match_id) and _team_matches(r, team)


def _instant(v) -> datetime:
    if not isinstance(v, datetime):
        raise Refused(f"REFUSED: the instant {v!r} is not a datetime")
    return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo is not None else v


# ---- the bounded read (Codex on #841, round 1) ------------------------------------------------------------------------
# as_of and history read only what their answer can depend on, and derive it partition by partition, so a read's memory
# follows one partition and its answer, not the record's whole history. Three bounds, none of which changes an answer:
# 1. THE CLOCK, in SQL: the chosen clock's column (recorded_at, or source_stamp, NULL excluded) before the day after the
#    instant's date: a SUPERSET of "at or before the instant" (the column's stored text begins with its ISO date, and
#    the writer stores every stamp in SQLAlchemy's one form), the exact cut (clock <= the instant) applied to each row in
#    Python, as before. A group (one observation, one source stamp) shares both clocks, so a cut never splits one.
#    Backfilled rows are cut by the chosen clock like any row: under the recorded clock a backfilled row is read from
#    its fetch, under the source clock from its stamp; BACKFILLED stays a label read over the interval, not a filter.
# 2. THE PARTITION: every rule of the derivation compares two rows of one source and kind only through fact_key (which
#    holds the team and the player), slot_key (the team for every kind but plays_for; the player for plays_for) and, for
#    a snapshot load, the team (its closure and its partial guard). So the intervals of a (source, kind, team) -- for
#    plays_for, a (source, kind, player) -- depend on that partition's rows alone and on one fact about each group: is
#    it a load (snapshot_load reads the whole group; _mixed_groups supplies the groups whose other rows are of another
#    kind). The SELECT is ordered by the partition's columns; each partition is derived as it completes and its closed
#    intervals dropped (as_of keeps the open ones).
# 3. THE KEY, in SQL: a --team or --match-id read loads only the partitions holding a row that names that team or match
#    (_key_filter). An interval the filter keeps (on mapped_now: the latest member's ids, the source's team text) has a
#    member that names it, so its partition is loaded, whole.
# 4. THE ANSWER (addendum 262 item 4): as_of keeps, per open interval, its first and last rows, its restated count and a
#    Summary (the labels' running values), never its members, so an unfiltered read holds one partition's rows and the
#    open facts, not every restatement of every fact in force. history keeps every member (its lines name them).
#    THE INDEX: ix_avail_asr_sport_recorded (sport, recorded_at) makes point 1 an index range under the recorded clock
#    (ix_avail_asr_sport_stamp under the source clock); migrate_availability_record.py creates it IF NOT EXISTS.
# The answers are put back in the full derivation's order (_group_order, then the row id). Equivalence with the full
# materialisation (load_rows + derive) on randomized histories, both clocks: tests/test_availability_record.py.

def _partition(r: Row) -> tuple:
    """The partition whose rows alone decide r's intervals (point 2 above)."""
    return (r.source, r.kind, player_key(r) if r.kind == "plays_for" else team_key(r))


def _clock_bound(clock: str, t: datetime):
    """Point 1: the chosen clock's column before the day after t's date (a superset of clock <= t; NULL excluded). On
    the last representable date (9999-12-31: no day after it) the bound is the column's NULL test alone, still a
    superset: the exact cut runs in Python either way, so the answer does not change (Codex on #841, round 1)."""
    from sqlalchemy import and_

    from src.db.schema import AvailabilityAssertion as A
    col = A.recorded_at if clock == "recorded" else A.source_stamp
    if t.date() == date.max:
        return col.is_not(None)
    return and_(col.is_not(None), col < datetime.combine(t.date() + timedelta(days=1), datetime.min.time()))


def _mixed_groups(s, sport, clock: str, t: datetime, kind: str | None) -> frozenset:
    """The groups (observation id, source stamp) read at t that are NOT a load although a partition's share of them is
    all the snapshot kind: a snapshot source's observation with a payload hash whose group, in this read, also holds a
    row of another kind. A read of one kind holds no such group. Usually none."""
    if kind is not None or not SNAPSHOT_SOURCES:
        return frozenset()
    from sqlalchemy import and_, or_, select

    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    q = (select(A.observation_id, A.source_stamp, A.recorded_at).join(O, O.id == A.observation_id)
         .where(A.sport == _sport(sport), O.payload_sha256.is_not(None), _clock_bound(clock, t),
                or_(*[and_(O.source == src, A.kind != k) for src, k in SNAPSHOT_SOURCES.items()])).distinct())
    out = set()
    for oid, stamp, recorded in _run(s, q):
        c = recorded if clock == "recorded" else stamp
        if c is not None and c <= t:
            out.add((oid, stamp))
    return frozenset(out)


KEY_FILTER_LIMIT = 5000                    # past this many partition keys, the read streams every partition instead


def _key_filter(s, sport, clock: str, t: datetime, kind: str | None, match_id, team):
    """Point 3: the WHERE clause that loads, whole, every partition holding a row that names the match (else the
    team), or None (no key: every partition). False when no row names it."""
    if match_id is None and team is None:
        return None
    from sqlalchemy import and_, false, or_, select

    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    if match_id is not None:
        names = A.match_id == match_id
    else:
        tt = str(team)
        names = or_(A.source_team == tt, A.team_id == int(tt)) if tt.isdigit() else A.source_team == tt
    q = (select(A.kind, A.source_team, A.team_id, A.source_player_id, A.player_name, A.player_id)
         .join(O, O.id == A.observation_id)
         .where(A.sport == _sport(sport), _clock_bound(clock, t), names).distinct())
    if kind is not None:
        q = q.where(A.kind == kind)
    teams_src, teams_id, p_src, p_name, p_id = set(), set(), set(), set(), set()
    for k, steam, tid, spid, name, pid in _run(s, q):
        if k == "plays_for":
            (p_src.add(spid) if spid is not None else p_name.add(name) if name is not None else p_id.add(pid))
        else:
            (teams_src.add(steam) if steam is not None else teams_id.add(tid))
    if sum(map(len, (teams_src, teams_id, p_src, p_name, p_id))) > KEY_FILTER_LIMIT:
        return None
    pf = A.kind == "plays_for"
    alts = []
    if teams_src:
        alts.append(and_(~pf, A.source_team.in_(sorted(teams_src))))
    if teams_id:
        alts.append(and_(~pf, A.source_team.is_(None), A.team_id.in_(sorted(teams_id))))
    if p_src:
        alts.append(and_(pf, A.source_player_id.in_(sorted(p_src))))
    if p_name:
        alts.append(and_(pf, A.source_player_id.is_(None), A.player_name.in_(sorted(p_name))))
    if p_id:
        alts.append(and_(pf, A.source_player_id.is_(None), A.player_name.is_(None), A.player_id.in_(sorted(p_id))))
    return or_(*alts) if alts else false()


def _partitions(s, sport, clock: str, t: datetime, kind: str | None = None, match_id=None, team=None):
    """The rows a read at t under the clock derives from (clock <= t), one partition (point 2) at a time, each whole.
    The SELECT is bounded by the clock (point 1) and the key (point 3) and ordered by the partition's columns, read in
    batches of READ_BATCH; a partition met twice would be a broken order, and is refused, never derived in halves."""
    from sqlalchemy import case, null

    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    where = _key_filter(s, sport, clock, t, kind, match_id, team)
    q = _select(sport, kind).where(_clock_bound(clock, t))
    if where is not None:
        q = q.where(where)
    pf = A.kind == "plays_for"
    q = q.order_by(O.source, A.kind, case((pf, A.source_player_id), else_=A.source_team),
                   case((pf, A.player_name), else_=null()), case((pf, A.player_id), else_=A.team_id), A.id)
    build = _Rows()
    cur, rows, seen = None, [], set()
    for tup in _run(s, q.execution_options(yield_per=READ_BATCH)):
        r = build(tup)
        c = clock_of(r, clock)
        if c is None or c > t:                    # the exact cut (point 1)
            continue
        p = _partition(r)
        if p != cur:
            if rows:
                yield rows
            if p in seen:
                raise RuntimeError(f"the read's order met partition {p!r} twice: refused, never derived in halves")
            seen.add(p)
            cur, rows = p, []
        rows.append(r)
    if rows:
        yield rows


def _checked(clock: str, kind: str | None, instant) -> datetime:
    if clock not in CLOCKS:
        raise Refused(f"REFUSED: clock {clock!r} is not one of {', '.join(CLOCKS)}")
    if kind is not None and kind not in KINDS:
        raise Refused(f"REFUSED: kind {kind!r} is not in the vocabulary ({', '.join(KINDS)})")
    return _instant(instant)


def as_of(s, sport, instant: datetime, clock: str = "recorded", match_id: int | None = None, team=None,
          kind: str | None = None) -> list[Fact]:
    """THE AS-OF QUERY (item 2): the facts in force at `instant` under `clock`: derive() over the assertions whose
    clock is at or before the instant, the intervals still open, in the order the derivation opened them. The match
    and team filters pick from the derivation of every partition that holds a row naming them, so a closure by another
    team's row (plays_for) is never lost. Read bounded (the section above): the answer is the full derivation's, its
    intervals carrying a Summary in place of their members (Interval; point 4 above): every label is the same."""
    t = _checked(clock, kind, instant)
    not_loads = _mixed_groups(s, sport, clock, t, kind)
    out = []
    for part in _partitions(s, sport, clock, t, kind, match_id, team):
        out.extend(iv for iv in _derive(part, clock, not_loads, keep_members=False)
                   if iv.end is None and _keep(iv, match_id, team))
    out.sort(key=lambda iv: (_group_order(iv.first, clock), iv.first.id))
    return [Fact(iv, interval_backfilled(iv), post_hoc(iv.first, iv), live_since(iv)) for iv in out]


def history(s, sport, instant: datetime, clock: str = "recorded", match_id: int | None = None, team=None,
            kind: str | None = None) -> list[tuple[Row, Interval]]:
    """--history (item 2): every assertion for the key with its clock at or before the instant, in time order, each
    with the interval it opened or restated (its derived end), so a flip shows. The same derive() as as_of; the key is
    read on each interval's latest member, so every row of a fact that mapped later is listed under our id. Read
    bounded, as as_of."""
    t = _checked(clock, kind, instant)
    not_loads = _mixed_groups(s, sport, clock, t, kind)
    out = []
    for part in _partitions(s, sport, clock, t, kind, match_id, team):
        member = {r.id: iv for iv in _derive(part, clock, not_loads) for r in iv.members}
        out.extend((r, member[r.id]) for r in part if _keep(member[r.id], match_id, team))
    out.sort(key=lambda x: (_group_order(x[0], clock), x[0].id))     # time order: the derivation's own
    return out


def walk(s, sport) -> Iterator[tuple[Row, Interval, Interval | None]]:
    """THE PROJECTION'S READ (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 4: "edges from the assertions carrying
    kind, recorded_at, source_stamp and the derived interval; rebuilt whole from SQLite"; 2026-11-11, addendum 347
    item 5): every assertion of the sport, each with the interval it opened or restated under the recorded clock and,
    where the row carries a source stamp, under the source clock (else None: the source clock does not read it). The
    same partitions and the same _derive as history (item 2: "there is no second path"), one partition at a time, so a
    walk holds one partition's rows, never the store's. A partition is (source, kind, team or player) under either
    clock, and its rows under the source clock are exactly its stamped rows, so one read serves both clocks. Pinned:
    for each clock, the walk's intervals equal history(s, sport, datetime.max, clock)'s, row by row
    (tests/test_availability_graph.py). Rows come in partition order, not time order."""
    t = _checked("recorded", None, datetime.max)
    not_loads = {c: _mixed_groups(s, sport, c, t, None) for c in CLOCKS}
    for part in _partitions(s, sport, "recorded", t):
        by_rec = {r.id: iv for iv in _derive(part, "recorded", not_loads["recorded"]) for r in iv.members}
        stamped = [r for r in part if r.source_stamp is not None]
        by_src = ({r.id: iv for iv in _derive(stamped, "source", not_loads["source"]) for r in iv.members}
                  if stamped else {})
        for r in part:
            yield r, by_rec[r.id], by_src.get(r.id)


def unread_under_source_clock(s, sport, kind: str | None = None) -> int:
    """How many assertions carry no source stamp (law 4: counted where the source clock does not read them). A COUNT in
    SQL over the same join load_rows reads."""
    from sqlalchemy import func, select

    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    q = (select(func.count()).select_from(A).join(O, O.id == A.observation_id)
         .where(A.sport == _sport(sport), A.source_stamp.is_(None)))
    if kind is not None:
        q = q.where(A.kind == kind)
    return int(_run(s, q).scalar() or 0)


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


def _labels(bf: bool | None, ph: bool | None, stamped: bool, game: bool = False) -> str:
    """The labels a fact line (as of) and a history line (per assertion) both carry, the same words."""
    labels = []
    if bf:
        labels.append("BACKFILLED (source-stamped backtests only; never the live-era record)")
    elif bf is None and stamped:
        labels.append("backfill unknown (no ruled cadence)")
    if ph:
        labels.append("POST HOC")
    elif ph is None and game:
        labels.append("kickoff unknown (post hoc undecidable; never read as pregame)")
    return "".join(f" · {x}" for x in labels)


def _match(r: Row) -> str:
    gid = (r.attrs or {}).get("source_match_id")
    if r.match_id is not None:
        return f" · match #{r.match_id}"
    return f" · match UNMAPPED (src {gid})" if gid is not None else ""


def fact_line(f: Fact) -> str:
    """A fact: its kind, attrs, stamps and observation from the row that opened it; its ids (ours, or UNMAPPED with
    the source's) from mapped_now, the mapping it carries now (Codex on #831, round 1)."""
    iv, r, now = f.interval, f.interval.first, mapped_now(f.interval)
    rest = (f" · restated {iv.restated}x, last {_obs(iv.last)} recorded_at {_z(iv.last.recorded_at)}"
            if iv.restated else "")
    live = (f" · live-era from {_z(f.live_since)} (first seen in backfilled history, restated fresh)"
            if f.live_since is not None and backfilled(r) else "")
    return (f"  {r.kind} · {_who(now)} · {_team(now)}{_match(now)} · "
            f"attrs {json.dumps(r.attrs or {}, sort_keys=True)} · recorded_at {_z(r.recorded_at)} · "
            f"source_stamp {_z(r.source_stamp)} · {_obs(r)}{rest}{live}"
            + _labels(f.backfilled, f.post_hoc, r.source_stamp is not None, per_game(now)))


def history_line(r: Row, iv: Interval) -> str:
    """One assertion, with the interval it opened or restated, and its own labels (the row's: a history line is one
    assertion, so BACKFILLED here is that row's, as recorded). Its ids print as recorded; where the interval maps them
    differently now (mapped_now), the line adds "mapped now" with those ids (Codex on #831, round 1)."""
    now = mapped_now(iv)
    mapped = (f" · mapped now: {_who(now)} · {_team(now)}{_match(now)}"
              if (now.player_id, now.team_id, now.match_id) != (r.player_id, r.team_id, r.match_id) else "")
    role = "opened" if iv.first.id == r.id else f"restated #{iv.first.id}"
    end = (f"ended {_z(iv.end)} ({iv.why_closed}, by assertion #{iv.closed_by.id})" if iv.end is not None
           else "open")
    return (f"  #{r.id} {r.kind} · {_who(r)} · {_team(r)}{_match(r)}{mapped}"
            + f" · attrs {json.dumps(r.attrs or {}, sort_keys=True)} · recorded_at {_z(r.recorded_at)} · "
              f"source_stamp {_z(r.source_stamp)} · {_obs(r)} · {role} · {end}"
            + _labels(backfilled(r), post_hoc(r, iv), r.source_stamp is not None, per_game(now)))


def attributions(sources: Iterable[str]) -> list[str]:
    """The attribution lines for the sources whose facts an output shows (item 3(a))."""
    return [SOURCES[x] for x in sorted(set(sources)) if SOURCES.get(x)]


__all__ = ["SOURCES", "STATUSES", "KINDS", "CLOCKS", "SOURCE_CADENCE_HOURS", "TABLES", "TRIGGERS", "MIGRATION_MARKER", "APPEND_ONLY",
           "Refused", "Receipt", "write_observation", "migrated", "redact", "payload_path_refusal", "endpoint_refusal",
           "assertion_refusal", "ENDPOINT_LIMIT", "ROWS_REFUSED_ATTR", "Row", "Interval",
           "Fact", "load_rows", "derive", "as_of", "history", "walk", "backfilled", "interval_backfilled", "live_since",
           "post_hoc", "kickoff_of", "mapped_now", "match_key", "SOURCE_MATCH_IDS", "attributions", "SNAPSHOT_SOURCES",
           "PARTIAL_GROUP_FRACTION", "snapshot_load", "partial_group", "guard_load"]
