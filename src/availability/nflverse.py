"""
THE NFLVERSE DEPTH-CHART FEED (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 3(a); 259 item 2; lane
availability-record): the adapter and ingest of source `nflverse_depth_charts` into the availability record.

Item 3(a), verbatim in part: "nflverse DEPTH CHARTS (source `nflverse_depth_charts`): the release file for the season
(github.com/nflverse/nflverse-data, release tag depth_charts, the 2025+ format: dt, team, player_name, espn_id, gsis_id,
pos_grp_id, pos_grp, pos_id, pos_name, pos_abb, pos_slot, pos_rank — the dictionary as published; the 2023–2024 weekly
files are a DIFFERENT shape and are NOT ingested by this feed [...]). Each fetch is one observation; its NEW rows (dt
later than the newest source_stamp we hold for the source) become assertions of kind depth_rank (attrs: pos_grp,
pos_abb, pos_slot, pos_rank), one per player-slot; the fetch's payload sha256 is kept, and a fetch whose file is
byte-identical to the last is a `complete` observation with rows_asserted 0. [...] A QB1 from this feed is a DAILY RANK,
not a game-day confirmation (the report's own limit): kind depth_rank says so; nothing here writes projected_starter."

    python cli.py availability-nflverse [--season 2026] [--file PATH]

How it reads and writes (law 1: every column by its name, as 259 item 1 read the real files):
- THE FILE: csv.DictReader by column NAME. The header must be exactly COLUMNS (the twelve, each once; their order is
  not read), else the file is REFUSED with the reason, and the 2023–2024 weekly shape (season / week / club_code ...)
  is named as such. Every row's `dt` must be an ISO-8601 instant with Z or an offset, its `team` and one of
  player_name / gsis_id / espn_id non-empty, else the file is refused naming the line (never a guessed row).
- A ROW -> ONE ASSERTION of kind depth_rank: attrs pos_grp, pos_abb, pos_slot, pos_rank VERBATIM (strings, as the file
  holds them), dt_raw (the file's dt text), espn_id and gsis_id verbatim (both ids kept; the record's VOLATILE_ATTRS,
  identity not the fact); source_stamp = dt (UTC); source_player_id = espn_id, ONLY (ARCHITECT 2026-11-05 11:55 ET,
  addendum 262 item 5, #840). THE KEY IS ONE ID THAT DOES NOT MOVE: record.player_key keys facts and slots on
  source_player_id, so a key that switched ids when nflverse filled one in later would close the player's interval
  "slot asserted to someone else" (the same player) and open a new one: a false flip. espn_id because the chart is
  ESPN's (its own id); a gsis_id filled in later changes attrs only (VOLATILE_ATTRS), never the key (that fix stays:
  262 item 5, "correct even though the data has not produced the case yet"). 262 item 5 read the real files: blank
  espn_id 0 of 554,215 rows (2025) and 0 of 747,450 (2026); "RULED: keying on `espn_id` is right [...] the residual
  case has frequency zero and gets a GUARD, not a design: a row with a blank `espn_id` is counted and refused into the
  group's `partial` status, never keyed by name". So a row with a blank espn_id is NEVER asserted (never keyed on its
  gsis_id or its name): it is counted (the receipt's "rows with no espn_id" line), its (dt, team) group is partial (the
  rest of the group is asserted carrying attrs.rows_refused = the count, record.ROWS_REFUSED_ATTR, so derive() closes
  nothing for that team at that load and never takes it as a previous complete group). The OBSERVATION's status keeps
  254 item 2(7)'s meaning (`partial` = a team or match left unmapped): a refused row makes its group partial, not the
  observation. The record's writer refuses any snapshot-source row with no source_player_id (never keyed by name).
  player_id NULL (addendum 254 item 2(3): no player table maps an NFL id today;
  every player counted unmapped); player_name verbatim; source_team = team verbatim and team_id = OUR teams.id by the
  existing NFL team mapping: the NFL competition's teams (competition_teams, competition code NFL) whose `tla` (the
  api-american-football team `code`, stored by sync-teams) equals the file's team EXACTLY; none, or more than one, is
  UNMAPPED (team_id NULL, the text beside it), counted, and makes the observation `partial` (254 item 2(7)).
- ONLY NEW ROWS: a row is asserted only when its dt is later than the newest source_stamp the record holds for the
  source (any season's file: the watermark is the source's, 252 item 3(a)); the others are read and counted, never
  asserted twice. Both seasons' files are ingested alike (259 item 2(c)); every row recorded more than the cadence
  after its dt (record.SOURCE_CADENCE_HOURS, 24) reads BACKFILLED by the record's existing rule, and is counted here.
  BECAUSE THE WATERMARK IS THE SOURCE'S, the 2025 file is read BEFORE the first 2026 read (259 item 2(c): "2025 IS IN
  SCOPE"). A file that cannot add anything is never silent: a changed file whose newest dt is EARLIER than the
  watermark (the 2025 file after a 2026 read; an older or smaller file) is REFUSED, naming both instants (a --file: exit
  2, nothing written; a fetch: a `failed` observation, exit 1, paged); a changed file whose newest dt IS the watermark
  (nothing new) is `complete` with 0 rows and a "no new load" receipt line.
- NO LOAD FROM THE FUTURE: a row whose dt is later than our fetch's time plus FUTURE_SKEW (1 h of clock skew) refuses
  the file naming its line (a --file: exit 2, nothing written; a fetch: a `failed` observation, the file kept). One such
  stamp held would become the watermark for good (the record is append-only) and drop every real load after it as
  "older". 262 item 3: "the 1-hour future-skew tolerance stands [...] within the hour it is accepted and the skew is
  printed on the receipt -- clock drift is a fact, not a fault": a newest dt ahead of our fetch by up to the hour is
  asserted, and the receipt's "clock skew" line names it and by how much.
- THE PARTIAL-GROUP GUARD'S COUNT (259 item 2(b)): the receipt counts the new (dt, team) groups that hold fewer than
  half the rows of the team's previous complete group (record.guard_load, the rule derive() closes by), the previous
  complete groups read from the store's own loads first.
- THE FETCH (259 item 2(e)): GET RELEASE_URL for the season, redirects followed, explicit timeouts (TIMEOUT), If-None-
  Match with the ETag stored for the last kept payload of the same endpoint. The ETag is stored BESIDE THE PAYLOAD FILE
  (`<payload>.etag`): no column of availability_observations holds a validator (the endpoint, http_status,
  payload_sha256, payload_path and error columns each mean something else), and no column or table is added.
  A KEPT PAYLOAD IS TRUSTED ONLY WHEN IT IS THERE (ARCHITECT 2026-11-06, addendum 274 item 3(1)): "the sidecar is sent
  only when the kept file exists and its sha256 matches, else no If-None-Match and the next 200 restores it"
  (lost_refusal): a missing or altered kept file is no previous payload, so a byte-identical 200 is kept again (a new
  path) and a 304 is refused; the same holds for a --file byte-identical to a lost one. That kept-again copy is a
  RESTORE (Got.restored), recorded as the byte-identical answer is (complete, rows_asserted 0, nothing read: those
  bytes' facts are held), never as a new load, so the source's watermark never refuses it (an older season's file
  fetched after newer loads) and the restored copy is the previous payload, its ETag sent, from the next run on.
  - 304: a `complete` observation, rows_asserted 0, carrying the previous payload's sha256 and path;
  - 200: the body streamed to disk and hashed; byte-identical to the last kept payload: the copy removed, a `complete`
    observation with rows_asserted 0 carrying that payload's sha256 and path, and the answer's ETag, where it differs
    from the stored one, written beside that payload (the sidecar is not the record: no row changes), so the next
    unchanged day sends a validator the server matches; changed: kept under
    logs/availability/nflverse_depth_charts/<UTC date>/<HHMMSS>Z-<sha256, first 16 hex>-depth_charts_<season>.csv
    (never data/, never mirrored), created EXCLUSIVELY (O_EXCL: the same bytes there are reused, other bytes refused,
    never overwritten; Codex on #841, round 1), its ETag beside it, then read. A failed ETag sidecar write after the
    keep is a `failed` observation that NAMES the kept file and its sha256 (274 item 3(1): "a record that cannot be
    found again is no record");
  - a raised call, a broken stream, any other status, or a refused file (the parser's own errors among them: bytes
    that are not UTF-8, a CSV csv cannot read, an instant out of datetime's range in UTC, each Refused naming its class
    and line, 274 item 3(1): "a parser error after the keep must still write the FAILED observation"): a `failed`
    observation, the error redacted
    (record.redact, after every URL's query string is cut: a release asset redirects to a signed URL). EVERY refusal
    (a refused fetched file's, a store refusal's, one that ends the run) is scrubbed so BEFORE its 256-character cut,
    before it is printed or kept; the receipt prints the error as stored (a second scrub would regrow a placeholder
    the cut split) and scrubs the team texts it prints (Codex on #841, round 2). A 5xx or a 429
    is worded as requests words it ("503 Server Error", "429 Client Error: Too Many Requests"), so the chain's retry
    (sp_run's transient classes: connection errors, timeouts, HTTP 5xx and 429; two retries) treats it as it treats a
    connection error. Each attempt the chain makes is its own run and its own `failed` observation (a fetch that
    raised is a row, 252 item 1(a)): one chain run can write up to three.
  THE CLOCK (Codex on #841, round 2): a 200's fetched_at (every assertion's recorded_at) is our clock AFTER its body
  has fully streamed and, when changed, been kept; a 304's the answer's; a failure's the raise, or the headers'
  arrival (fetch()'s docstring).
  The endpoint string is the requested release URL (no secret is needed or sent), never the redirect's signed one.
- --file PATH: a local file (the operator's hand-carried release file; the tests) read the same way, endpoint
  "file:<its name>"; refused (exit 2, nothing written) when the header or a row is refused; kept under the payload
  directory (<HHMMSS>Z-<sha256, first 16 hex>-<its name>, exclusive) when its bytes differ from the last kept payload
  of that endpoint. ONE READ OF THE ORIGINAL (Codex on #841, round 1; 262 item 6: "copy once to a temporary file, then
  hash, parse and keep that same copy"): the file is copied ONCE to a private temporary file (tempfile.mkstemp, outside
  the checkout), and that copy is hashed, parsed and kept (copied into place from the copy, the copy's hash checked
  again on the way); the original is never read again, so a file changed while the run reads it cannot make the hash,
  the rows and the kept bytes disagree. The temporary copy is removed whatever the run's end. A file that cannot be
  read into its copy (unreadable, gone since is_file(), mkstemp or the copy failing) is refused, exit 2 (#853 F1).
- CHECKED BEFORE ANY FILE (Codex on #841, round 1): the endpoint by the writer's own rule (record.endpoint_refusal)
  before any call, copy or file, and the kept path (record.payload_path_refusal, the name's 255 bytes) before any
  directory or file is made: a refused name (a credential-like one, "api_token=secret.csv"; one too long to keep)
  leaves nothing on disk and no row. Every row to be asserted goes through the writer's own row checks
  (record.assertion_refusal: its widths among them, player_name 128 characters, source_team and source_player_id 64)
  BEFORE a --file is kept (on its temporary copy; refused: exit 2, nothing kept, nothing written) and, on a fetched
  file, before the write (refused: a `failed` observation keeping the payload's path, the refusal its error). A store
  refusal after a payload was kept leaves no orphan either: a --file's copy made by the run is removed (exit 2); a
  fetch is written as a `failed` observation keeping the path (Codex on #841, round 1).
- THE WRITE: one record.write_observation per run (one fetch, one observation, 252 item 3(a); a retried chain step
  is another run), under the chains' DB
  lock (sp_common.sync_lock, a no-op inside a chain), the store's state read mode=ro under the same lock. A missing DB
  file or an unmigrated store is refused before any call. No update or delete path (the record's triggers stand).
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.availability import record as rec

SOURCE = "nflverse_depth_charts"
KIND = "depth_rank"
# 259 item 1: "COLUMNS, both files, exactly the dictionary's twelve" (252 item 3(a): "the 2025+ format")
COLUMNS = ("dt", "team", "player_name", "espn_id", "gsis_id", "pos_grp_id", "pos_grp", "pos_id", "pos_name", "pos_abb",
           "pos_slot", "pos_rank")
ATTR_COLUMNS = ("pos_grp", "pos_abb", "pos_slot", "pos_rank")        # 252 item 3(a): "attrs: pos_grp, pos_abb, ..."
# columns that name the 2023-2024 weekly shape (nflverse's pre-2025 depth_charts dictionary), for the refusal's reason
WEEKLY_SHAPE_HINTS = ("season", "week", "club_code", "depth_team", "game_type", "formation", "depth_position")
FIRST_SEASON = 2025                                                    # 259 item 2(c): 2025 in scope; 2023-24 not
RELEASE_URL = "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_{season}.csv"
TIMEOUT = (10, 120)                       # (connect, read) seconds: explicit (259 item 2(e)); read is per chunk
CHUNK = 1 << 20
# the clock skew a load's dt may hold past our fetch's time before the file is refused (a future stamp would hold the
# source's watermark for good: the record is append-only)
FUTURE_SKEW = timedelta(hours=1)
USER_AGENT = "sports-predictor availability-record (nflverse depth charts; CC BY 4.0)"
NFL_COMPETITION = "NFL"
ATTRIBUTION = rec.SOURCES[SOURCE]
assert ATTRIBUTION == "Depth charts: nflverse (CC BY 4.0)"
# a URL's query string; never a whole "?[query removed]" a scrub left (so _scrub leaves its own output unchanged)
_QUERY = re.compile(r"(https?://[^\s?#'\"<>]+)\?(?!\[query removed\](?:[\s'\"<>]|$))[^\s'\"<>]*")

# where logs/availability/... lives: the checkout (the host's /opt/sports-predictor, the laptop's clone); the tests
# point it at their tmp directory
PAYLOAD_BASE = Path(__file__).resolve().parents[2]


class Refused(Exception):
    """Nothing written: the run refuses (exit 2)."""


def current_season(today: datetime | None = None) -> int:
    """The default --season: the calendar year from March on, else the year before. nflverse's season file turns over
    in March (259 item 1: the 2025 file's last load 2026-03-14T07:32:09Z, the 2026 file's first 2026-03-22)."""
    t = today or datetime.now(timezone.utc)
    return t.year if t.month >= 3 else t.year - 1


def release_url(season: int) -> str:
    return RELEASE_URL.format(season=int(season))


def season_refusal(season: int) -> str | None:
    if int(season) < FIRST_SEASON:
        return (f"REFUSED: season {season}: the 2023-2024 weekly depth-chart files are a DIFFERENT shape and are NOT "
                f"ingested by this feed (addendum 252 item 3(a); 259 item 2(c): 2025 and later only)")
    return None


# ---- the file ------------------------------------------------------------------------------------------------------

def header_refusal(fieldnames) -> str | None:
    """Why the header is not the 2025+ dictionary's twelve columns, or None (law 1: read by name, the set exact)."""
    got = list(fieldnames or [])
    if len(got) == len(COLUMNS) and set(got) == set(COLUMNS):
        return None
    missing = [c for c in COLUMNS if c not in got]
    extra = [c for c in got if c not in COLUMNS]
    dup = sorted({c for c in got if got.count(c) > 1})
    why = (f"the header is not the 2025+ depth_charts dictionary's twelve columns ({', '.join(COLUMNS)}): "
           f"missing {missing or 'none'}, unexpected {extra or 'none'}" + (f", repeated {dup}" if dup else ""))
    if any(c in got for c in WEEKLY_SHAPE_HINTS):     # said first: an observation's error keeps 256 characters
        why = ("this is the 2023-2024 weekly shape, which this feed does NOT ingest (addendum 252 item 3(a): \"a "
               "DIFFERENT shape [...] a second adapter later if a backtest wants them\"); " + why)
    return f"REFUSED: {why}"


def _instant(text: str) -> datetime | None:
    """The instant in naive UTC, or None (not an ISO-8601 instant with Z or an offset). An instant that leaves
    datetime's range when converted to UTC raises OverflowError: read_file refuses its line (addendum 274 item 3(1))."""
    s = (text or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        return None                                   # law 4: a time with no zone is not assumed UTC
    return d.astimezone(timezone.utc).replace(tzinfo=None)


@dataclass
class Parsed:
    rows: list = field(default_factory=list)          # (dt naive UTC, the row as read: name -> text)
    loads: list = field(default_factory=list)         # the distinct dt, ascending
    newest_line: int | None = None                    # the first line holding the newest dt (a refusal names it)


def read_file(path: Path) -> Parsed:
    """The file read by column name, every row checked; Refused (with the reason and line) on anything else. THE
    PARSER'S OWN ERRORS ARE REFUSALS (ARCHITECT 2026-11-06, addendum 274 item 3(1): "a parser error after the keep must
    still write the FAILED observation"): bytes that are not UTF-8 (UnicodeDecodeError), a CSV csv cannot read
    (csv.Error, e.g. a field past its limit) and an instant out of datetime's range in UTC (OverflowError) are Refused
    naming the class and the line, so a fetched file is a `failed` observation keeping its payload and a --file exits
    2 with nothing kept; the reason is scrubbed by its caller as every refusal is."""
    out = Parsed()
    seen = set()
    newest = None
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        try:
            why = header_refusal(reader.fieldnames)
            if why:
                raise Refused(why)
            for row in reader:
                line = reader.line_num
                if None in row or any(v is None for v in row.values()):
                    raise Refused(f"REFUSED: line {line} does not hold the twelve columns (a short or long row)")
                try:
                    dt = _instant(row["dt"])
                except OverflowError:
                    raise Refused(f"REFUSED: line {line}: dt {row['dt']!r} leaves the range a datetime holds in UTC "
                                  f"(OverflowError)") from None
                if dt is None:
                    raise Refused(f"REFUSED: line {line}: dt {row['dt']!r} is not an ISO-8601 instant with Z or an "
                                  f"offset")
                if not row["team"].strip():
                    raise Refused(f"REFUSED: line {line} names no team")
                if not (row["player_name"].strip() or row["gsis_id"].strip() or row["espn_id"].strip()):
                    raise Refused(f"REFUSED: line {line} names no player (player_name, gsis_id and espn_id all empty)")
                out.rows.append((dt, row))
                seen.add(dt)
                if newest is None or dt > newest:
                    newest, out.newest_line = dt, line
        except (UnicodeDecodeError, csv.Error) as e:
            kind = "csv.Error" if isinstance(e, csv.Error) else type(e).__name__
            raise Refused(f"REFUSED: the file cannot be read as UTF-8 CSV after line {reader.line_num} ({kind}: {e}); "
                          f"nothing asserted") from None
    out.loads = sorted(seen)
    return out


def future_refusal(parsed: Parsed, fetched_at: datetime) -> str | None:
    """Why the file holds a load from the future, or None: a dt later than our fetch's time plus FUTURE_SKEW. Such a
    stamp, once asserted, would be the source's watermark for good (append-only) and every real load after it would
    read "older"."""
    if not parsed.loads or parsed.loads[-1] <= fetched_at + FUTURE_SKEW:
        return None
    return (f"REFUSED: line {parsed.newest_line}: dt {parsed.loads[-1].isoformat(timespec='seconds')}Z is later than "
            f"our fetch ({fetched_at.isoformat(timespec='seconds')}Z) by more than "
            f"{int(FUTURE_SKEW.total_seconds() // 60)} min: a load from the future would hold the source's watermark "
            f"for good; nothing asserted")


def older_refusal(parsed: Parsed, wm: datetime | None) -> str | None:
    """Why the file cannot add anything, or None: every load EARLIER than the newest source_stamp the record holds for
    the source (the watermark is the source's, 252 item 3(a); so the 2025 file is read BEFORE the first 2026 read, 259
    item 2(c)). A file whose newest load IS the watermark is not refused (nothing new: complete, 0 rows)."""
    if wm is None or not parsed.loads or parsed.loads[-1] >= wm:
        return None
    return (f"REFUSED: every load is older than the source's watermark (newest dt "
            f"{parsed.loads[-1].isoformat(timespec='seconds')}Z < {wm.isoformat(timespec='seconds')}Z held): none "
            f"of its {len(parsed.rows)} rows can be asserted (252 item 3(a); 259 item 2(c): read the 2025 file "
            f"BEFORE the first 2026 read)")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


# ---- the store (read mode=ro) ----------------------------------------------------------------------------------------

def team_map(s) -> tuple[dict, set]:
    """{tla: team id} for the NFL competition's teams whose tla is held by exactly one of them, and the tlas held by
    more than one (ambiguous: unmapped, never a guess). The existing mapping: teams.tla, the api-american-football
    team code sync-teams stores (src/adapters/api_american_football.py list_teams)."""
    from sqlalchemy import select

    from src.db.schema import Competition, CompetitionTeam, Sport, Team
    got = s.execute(select(Team.id, Team.tla).join(CompetitionTeam, CompetitionTeam.team_id == Team.id)
                    .join(Competition, Competition.id == CompetitionTeam.competition_id)
                    .where(Competition.sport == Sport.NFL, Competition.code == NFL_COMPETITION,
                           Team.tla.is_not(None)).distinct()).all()
    ids: dict = {}
    for tid, tla in got:
        ids.setdefault(tla, set()).add(tid)
    return {k: next(iter(v)) for k, v in ids.items() if len(v) == 1}, {k for k, v in ids.items() if len(v) > 1}


def watermark(s) -> datetime | None:
    """The newest source_stamp the record holds for the source (252 item 3(a): "NEW rows (dt later than the newest
    source_stamp we hold for the source)")."""
    from sqlalchemy import func, select

    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    return s.execute(select(func.max(A.source_stamp)).join(O, O.id == A.observation_id)
                     .where(O.source == SOURCE)).scalar()


def stored_complete_groups(s) -> dict:
    """Each team's previous complete group size, from the store's own loads (the groups derive() reads as loads:
    observations that keep a payload hash), folded in dt order by record.guard_load; a group whose rows carry
    attrs.rows_refused (a row refused there, 262 item 5) is partial, never a previous complete group."""
    from sqlalchemy import func, select

    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    got = s.execute(select(A.observation_id, A.source_stamp, A.source_team, func.count(),
                           func.max(func.json_extract(A.attrs, f"$.{rec.ROWS_REFUSED_ATTR}")))
                    .join(O, O.id == A.observation_id)
                    .where(O.source == SOURCE, A.kind == KIND, O.payload_sha256.is_not(None))
                    .group_by(A.observation_id, A.source_stamp, A.source_team)
                    .order_by(A.source_stamp, A.observation_id)).all()
    last: dict = {}
    load_key, counts, refused = None, {}, set()
    for oid, stamp, team, n, k in got:
        if (oid, stamp) != load_key:
            if counts:
                rec.guard_load(counts, last, refused)
            load_key, counts, refused = (oid, stamp), {}, set()
        counts[(SOURCE, ("src", team))] = n
        if k:
            refused.add((SOURCE, ("src", team)))
    if counts:
        rec.guard_load(counts, last, refused)
    return last


def previous_observation(s, endpoint: str) -> tuple[str, str, str] | None:
    """(sha256, payload_path, status) of the newest complete, partial or empty observation of this endpoint that kept a
    payload: previous_payload's row, with its status, which an unchanged answer takes (#1003, ARCHITECT 2026-11-14,
    addendum 382 item 3: "AN UNCHANGED ANSWER TAKES THE STATUS OF THE PAYLOAD IT IS UNCHANGED FROM")."""
    from sqlalchemy import select

    from src.db.schema import AvailabilityObservation as O
    got = s.execute(select(O.payload_sha256, O.payload_path, O.status)
                    .where(O.source == SOURCE, O.endpoint == endpoint, O.status.in_((*rec.ASSERTING, "empty")),
                           O.payload_sha256.is_not(None), O.payload_path.is_not(None))
                    .order_by(O.id.desc()).limit(1)).first()
    return (got[0], got[1], got[2]) if got else None


def unchanged_status(prev_status: str | None) -> str:
    """The status of an unchanged answer (a 304, a byte-identical 200 or --file, a restore), verbatim from addendum 382
    item 3: "After a header-only payload a 304, a byte-identical 200 or a byte-identical --file is recorded `empty`,
    never `complete` with zero rows [...] After a complete or partial payload it stays `complete` with rows_asserted
    0". Nothing stored is rewritten; the rule holds from its merge."""
    return "empty" if prev_status == "empty" else "complete"


def previous_payload(s, endpoint: str) -> tuple[str, str] | None:
    """(sha256, payload_path) of the newest complete, partial or empty observation of this endpoint that kept a
    payload. An `empty` one (a header and no row) kept its payload too, so its ETag is the validator and a byte-
    identical answer is not kept again (#853 F2, ARCHITECT, addendum 381 item 3(iv)): before, each identical
    header-only file was downloaded and kept again as another `empty` row, or the older non-empty ETag was sent.
    record.ASSERTING is unchanged: an `empty` observation still asserts nothing. previous_observation's row."""
    got = previous_observation(s, endpoint)
    return got[:2] if got else None


def lost_refusal(prev: tuple[str, str]) -> str | None:
    """Why the previous kept payload cannot be trusted, or None (ARCHITECT 2026-11-06, addendum 274 item 3(1): "a kept
    payload that has gone missing is NOT trusted through its surviving ETag — the sidecar is sent only when the kept
    file exists and its sha256 matches, else no If-None-Match and the next 200 restores it"): its file missing,
    unreadable, or holding bytes that are not the recorded sha256's. An untrusted payload is no previous payload: no
    ETag is sent, a 304 is refused as one with no stored payload, and a byte-identical answer is KEPT (a new path),
    never recorded under the lost one."""
    p = PAYLOAD_BASE / prev[1]
    try:
        if not p.is_file():
            return "missing"
        got = sha256_file(p)
    except OSError as e:
        return f"unreadable ({type(e).__name__})"
    return None if got == prev[0] else f"altered (sha256 {got[:16]}, not {prev[0][:16]})"


def stored_etag(payload_path: str | None) -> str | None:
    if not payload_path:
        return None
    p = PAYLOAD_BASE / (payload_path + ".etag")
    try:
        v = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return v or None


# ---- the fetch ---------------------------------------------------------------------------------------------------------

def _payload_dir(now: datetime) -> tuple[str, Path]:
    rel = "/".join((*rec.PAYLOAD_ROOT, SOURCE, now.date().isoformat()))
    return rel, PAYLOAD_BASE / rel


def _scrub(text: str) -> str:
    """Every URL's query string cut (a release asset redirects to a signed URL), then the record's redact."""
    return rec.redact(_QUERY.sub(lambda m: m.group(1) + "?[query removed]", str(text)))


@dataclass
class Got:
    """What one fetch (or one --file read) produced."""
    endpoint: str
    fetched_at: datetime
    http_status: int | None = None
    sha256: str | None = None
    payload_path: str | None = None       # relative (logs/availability/...)
    changed: bool = False                 # a new payload, kept and to be read
    error: str | None = None              # the call raised / the status was refused (failed)
    etag: str = "none"                    # the ETag line: sent/not sent, the answer
    created: bool = False                 # this run created the kept file (not an earlier run's same bytes, reused)
    # 274 item 3(1), "the next 200 restores it": the recorded payload's own bytes kept again because its kept file was
    # lost; recorded as the byte-identical answer is (complete, nothing read or asserted: those bytes' facts are held),
    # so no watermark check refuses it and the restored copy is the previous payload from then on
    restored: bool = False


NAME_MAX = 255                            # bytes in one file name (Linux's NAME_MAX): a longer kept name is refused


def _kept(now: datetime, name: str, sha: str) -> tuple[str, Path]:
    """The kept payload's (relative path, absolute path): logs/availability/<source>/<UTC date>/<HHMMSS>Z-<the payload's
    sha256, first 16 hex>-<name>, so two different payloads kept in one second never share a path (Codex on #841, round
    1). Checked BEFORE any directory or file is made: the writer's payload_path rule and the file-name length; a refusal
    leaves nothing on disk. Creates nothing."""
    rel_dir, abs_dir = _payload_dir(now)
    final = f"{now:%H%M%S}Z-{sha[:16]}-{name}"
    rel = f"{rel_dir}/{final}"
    why = rec.payload_path_refusal(rel, SOURCE)
    if why:
        raise Refused(f"REFUSED: {why}; nothing kept, nothing written")
    if len(final.encode("utf-8")) > NAME_MAX:
        raise Refused(f"REFUSED: the kept payload's file name would be {len(final.encode('utf-8'))} bytes, longer than "
                      f"{NAME_MAX}; nothing kept, nothing written")
    return rel, abs_dir / final


def _remove_empty_payload_dirs(final: Path) -> None:
    """The kept file's date and source folders, each only when it is left empty (a refused keep leaves no folder)."""
    for d in (final.parent, final.parent.parent):
        try:
            d.rmdir()
        except OSError:
            break


def _retain(src: Path, final: Path, sha: str) -> bool:
    """The payload's bytes at `final`, created EXCLUSIVELY (O_EXCL: never over another file). True when written; False
    when `final` already holds exactly these bytes (its sha256 is the payload's: reused, not written again); Refused
    when it holds other bytes (the evidence there is never overwritten). The bytes are hashed as they are copied: a
    copy whose bytes are not `sha` is removed and refused (262 item 6: the kept bytes are the hashed bytes). A failed
    copy removes its partial file."""
    final.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(final, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if sha256_file(final) == sha:
            return False
        raise Refused(f"REFUSED: {final.name} already holds other bytes (sha256 {sha256_file(final)[:16]}, not "
                      f"{sha[:16]}): the kept evidence is never overwritten; nothing written") from None
    h = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            for b in iter(lambda: inp.read(CHUNK), b""):
                h.update(b)
                out.write(b)
        if h.hexdigest() != sha:
            raise Refused(f"REFUSED: the bytes copied to {final.name} are not the hashed payload (sha256 "
                          f"{h.hexdigest()[:16]}, not {sha[:16]}): nothing kept, nothing written")
    except BaseException:
        final.unlink(missing_ok=True)
        raise
    return True


def status_error(code: int) -> str:
    """A non-200, non-304 answer's error, worded as requests words an HTTPError for 5xx and 429 ("503 Server Error",
    "429 Client Error: Too Many Requests"), so sp_run's retry reads them in its transient class (connection errors,
    timeouts, HTTP 5xx and 429) like a connection error; any other status is never retried."""
    if 500 <= code <= 599:
        why = f"{code} Server Error"
    elif code == 429:
        why = "429 Client Error: Too Many Requests"
    elif 400 <= code <= 499:
        why = f"{code} Client Error"
    else:
        why = "unexpected status"
    return f"HTTP {code} from the release asset (refused): {why}"


def _refresh_etag(payload_path: str, stored: str | None, new: str | None) -> str:
    """A byte-identical 200 whose ETag differs from the stored one: the new ETag written beside the kept payload (the
    sidecar is not the record; no row changes), so the next unchanged day sends a validator the server matches (259
    item 2(e): "the daily cost is one small request on an unchanged day"). Returns the receipt's ETag-line suffix."""
    if not new or new == stored:
        return ""
    try:
        (PAYLOAD_BASE / (payload_path + ".etag")).write_text(str(new) + "\n", encoding="utf-8")
    except OSError as e:
        return f"; its new ETag NOT stored ({type(e).__name__}): the next call sends the old one"
    return "; its new ETag stored beside the kept payload"


def fetch(season: int, prev: tuple[str, str] | None, *, http_get, now_fn) -> Got:
    """One conditional GET of the season's release asset (the module docstring). Never raises for the call: a raised
    call is a Got with error (a failed observation).

    THE OBSERVATION'S CLOCK (Codex on #841, round 2): a 200's fetched_at (the record's recorded_at for every assertion
    it carries) is our clock AFTER its body is fully streamed and, when it changed, retained at its kept path: never
    the headers' arrival, so no fact is recorded as known before its bytes were on disk. A 304 carries no body: its
    clock is the answer's arrival. A failure keeps its own rule: a raised call is our clock when it raised; a refused
    status, a broken stream, or a failure keeping the file is our clock when the answer's headers arrived (the
    attempt's time; a failed observation asserts nothing). The kept file is named by the headers' arrival (the
    download's start: <UTC date>/<HHMMSS>Z), taken before the body is read."""
    url = release_url(season)
    lost = lost_refusal(prev) if prev else None
    lost_prev = prev if lost else None
    if lost:
        prev = None                     # 274 item 3(1): never trusted through its surviving ETag; the next 200 kept
    etag = stored_etag(prev[1]) if prev else None
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    sent = ("ETag sent" if etag else f"the last kept payload {lost}: its ETag not sent (unconditional GET)" if lost
            else "no ETag stored (unconditional GET)")
    part = None
    try:
        resp = http_get(url, headers=headers, timeout=TIMEOUT, stream=True, allow_redirects=True)
    except Exception as e:  # noqa: BLE001 - a raised call is a failed observation, its error kept (redacted)
        return Got(url, now_fn(), error=_scrub(f"{type(e).__name__}: {e}")[:256], etag=f"{sent}; the call raised")
    answered = now_fn()                 # the headers' arrival: a 304's, a refused status's and a failure's clock
    try:
        code = int(resp.status_code)
        if code == 304:
            if not prev:
                return Got(url, answered, 304, error="HTTP 304 with no stored payload to carry (refused)",
                           etag=f"{sent}; 304")
            return Got(url, answered, 304, prev[0], prev[1], etag=f"{sent}; 304 not modified")
        if code != 200:
            return Got(url, answered, code, error=status_error(code), etag=f"{sent}; HTTP {code}")
        abs_dir = _payload_dir(answered)[1]
        abs_dir.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{answered:%H%M%S}Z-depth_charts_{int(season)}.", suffix=".csv.part",
                                    dir=abs_dir)          # a name of its own: two runs never share a partial file
        part = Path(name)
        h = hashlib.sha256()
        with os.fdopen(fd, "wb") as f:
            for b in resp.iter_content(chunk_size=CHUNK):
                if b:
                    h.update(b)
                    f.write(b)
        sha = h.hexdigest()
        new_etag = (resp.headers or {}).get("ETag")
        if prev and sha == prev[0]:
            part.unlink()
            part = None
            done = now_fn()                               # the body fully streamed and hashed: this fetch's clock
            return Got(url, done, 200, prev[0], prev[1],
                       etag=f"{sent}; 200 byte-identical (not kept again)" + _refresh_etag(prev[1], etag, new_etag))
        rel, final = _kept(answered, f"depth_charts_{int(season)}.csv", sha)
        _retain(part, final, sha)                         # exclusive: another payload's file is never overwritten
        done = now_fn()                                   # streamed AND retained: this fetch's clock (round 2)
        if new_etag:
            try:
                (final.parent / (final.name + ".etag")).write_text(str(new_etag) + "\n", encoding="utf-8")
            except OSError as e:
                # 274 item 3(1): "a failed ETag sidecar write after the keep writes a failed observation that NAMES the
                # kept file and its sha256 (a record that cannot be found again is no record)"
                return Got(url, done, 200, sha, rel, changed=True,
                           error=_scrub(f"REFUSED: the ETag sidecar write failed after the payload was kept "
                                        f"({type(e).__name__}: {e}); the kept file is this row's payload_path and "
                                        f"payload_sha256; nothing asserted")[:256],
                           etag=f"{sent}; 200 changed; its ETag NOT stored ({type(e).__name__})")
        if lost_prev and sha == lost_prev[0]:
            # 274 item 3(1): "the next 200 restores it": the recorded bytes, kept again, recorded as a byte-identical
            # answer (complete, nothing asserted); never refused as a new load older than the watermark
            return Got(url, done, 200, sha, rel, changed=True, restored=True,
                       etag=f"{sent}; 200 byte-identical to the lost payload: kept again (restored)"
                       + ("" if new_etag else " (the answer carried no ETag)"))
        return Got(url, done, 200, sha, rel, changed=True,
                   etag=f"{sent}; 200 changed" + ("" if new_etag else " (the answer carried no ETag)"))
    except Exception as e:  # noqa: BLE001 - a broken stream is a failed observation
        return Got(url, answered, getattr(resp, "status_code", None),
                   error=_scrub(f"{type(e).__name__}: {e}")[:256], etag=f"{sent}; the read broke")
    finally:
        if part is not None:
            try:
                part.unlink()
            except OSError:
                pass
        close = getattr(resp, "close", None)
        if close:
            close()


def file_endpoint(path: Path) -> str:
    return f"file:{path.name}"


def snapshot_copy(path: Path) -> tuple[Path, str]:
    """262 item 6: the --file's ONE read. Its bytes copied once to a private temporary file (tempfile.mkstemp, outside
    the checkout: nothing under logs/ until the keep), and that copy hashed. Returns (the copy, its sha256); the caller
    parses and keeps the same copy and removes it whatever happens. A failed copy removes its partial file."""
    fd, name = tempfile.mkstemp(prefix=".nflverse-file-", suffix=".csv")
    copy = Path(name)
    try:
        with os.fdopen(fd, "wb") as out, open(path, "rb") as inp:
            shutil.copyfileobj(inp, out, CHUNK)
        return copy, sha256_file(copy)
    except BaseException:
        copy.unlink(missing_ok=True)
        raise


def from_file(copy: Path, name: str, sha: str, prev: tuple[str, str] | None, now: datetime) -> Got:
    """A hand-carried file, by its one temporary copy (snapshot_copy: `copy` and its `sha`; `name` the original's
    file name): kept under the payload directory, FROM THAT COPY, when its bytes differ from the last kept one (262 item
    6: never a second read of the original). The endpoint and the kept path are checked (the writer's endpoint rule,
    the payload path rule, the name's length) BEFORE anything is kept: a refusal leaves no file (Codex on #841, round
    1)."""
    ep = f"file:{name}"
    why = rec.endpoint_refusal(ep)
    if why:
        raise Refused(why)
    lost = lost_refusal(prev) if prev else None
    restoring = bool(lost) and sha == prev[0]
    if lost:
        prev = None                       # 274 item 3(1), the same reading: a lost kept payload is restored, not named
    if prev and sha == prev[0]:
        return Got(ep, now, None, prev[0], prev[1], etag="n/a (--file); byte-identical to the last kept payload")
    rel, final = _kept(now, name, sha)
    try:
        created = _retain(copy, final, sha)
    except OSError as e:
        # #1003 (ARCHITECT, addendum 382 item 2): the keep's own I/O (the payload directory, the kept file's exclusive
        # create, the copy, the copy's source) failing is a refusal (exit 2), never a traceback (exit 1 is a failed
        # observation's code). _retain has removed its partial file; the folders it made and left empty go too, so a
        # refusal leaves nothing on disk. Named by the error's type and strerror, never str(e), which names a path.
        _remove_empty_payload_dirs(final)
        raise Refused(f"REFUSED: --file {name!r} could not be kept ({type(e).__name__}: "
                      f"{e.strerror or 'no error text'}); nothing kept, nothing written") from None
    return Got(ep, now, None, sha, rel, changed=True, created=created, restored=restoring,
               etag="n/a (--file)" + (f"; the last kept payload {lost}: kept again"
                                      + (" (restored: byte-identical to it)" if restoring else "") if lost else ""))


# ---- the ingest -------------------------------------------------------------------------------------------------------

@dataclass
class Ingest:
    """The run's receipt (law 2)."""
    got: Got
    status: str = "complete"
    observation_id: int | None = None
    rows_read: int = 0
    loads: int = 0
    new_loads: int = 0
    new_rows: int = 0
    rows_asserted: int = 0
    old_rows: int = 0                     # at or before the watermark: read, not asserted again
    watermark: datetime | None = None
    partial_groups: list = field(default_factory=list)     # (dt, team, rows, previous complete rows)
    unmapped_teams: dict = field(default_factory=dict)     # team text -> rows
    ambiguous_teams: set = field(default_factory=set)
    unmapped_players: int = 0
    backfilled: int = 0
    refused: str | None = None            # a fetched file the adapter refused (a failed observation)
    # 262 item 5 (#840): rows with a blank espn_id, never asserted (never keyed by gsis_id or name), and their groups
    no_espn_rows: int = 0
    no_espn_groups: list = field(default_factory=list)     # (dt, team, rows refused, rows asserted)
    newest_load: datetime | None = None   # the file's newest dt (262 item 3: its skew past our fetch is printed)

    def lines(self) -> list[str]:
        g = self.got
        t = _scrub                        # a team's text is the payload's: scrubbed where the receipt prints it
        z = (lambda d: d.isoformat(timespec="seconds") + "Z" if d else "none held")
        out = [f"AVAILABILITY-NFLVERSE · observation #{self.observation_id} · {self.status} · <{g.endpoint}> · "
               f"fetched_at {z(g.fetched_at)}" + (f" · HTTP {g.http_status}" if g.http_status is not None else "")]
        if g.error:
            # printed AS STORED: every producer scrubs before its 256-character cut (fetch()'s raises, run()'s
            # refusals; the 304 and status errors are constant text), and a second scrub here would regrow a cut
            # placeholder ("?[query rem") and print other text than the row holds (round 2)
            out.append(f"  error (redacted): {g.error}")
        out.append(f"  rows read {self.rows_read} · loads {self.loads} (new {self.new_loads}) · new rows "
                   f"{self.new_rows} · rows asserted {self.rows_asserted} · older rows not asserted again "
                   f"{self.old_rows} (watermark: newest source_stamp held {z(self.watermark)})")
        out.append(f"  partial team groups: {len(self.partial_groups) + len(self.no_espn_groups)}, closing nothing"
                   + "".join(f"\n    {z(dt)} {t(team)}: {n} row(s) < half of {prev}" for dt, team, n, prev
                             in self.partial_groups)
                   + "".join(f"\n    {z(dt)} {t(team)}: {k} row(s) with no espn_id refused ({n} asserted)"
                             for dt, team, k, n in self.no_espn_groups))
        out.append(f"  rows with no espn_id: {self.no_espn_rows}, refused, never keyed by gsis_id or name (addendum "
                   f"262 item 5); their team groups partial: {len(self.no_espn_groups)}")
        um = ", ".join(f"{t(k)} ({n} row(s))" for k, n in sorted(self.unmapped_teams.items())) or "none"
        out.append(f"  unmapped teams: {len(self.unmapped_teams)} ({um})"
                   + (f"; ambiguous tla (more than one NFL team): "
                      f"{', '.join(t(k) for k in sorted(self.ambiguous_teams))}" if self.ambiguous_teams else "")
                   + f" · unmapped players: {self.unmapped_players} row(s) (no NFL player table: addendum 254 item "
                     f"2(3))")
        out.append(f"  backfilled rows (recorded more than {rec.SOURCE_CADENCE_HOURS[SOURCE]} h after their dt): "
                   f"{self.backfilled}")
        if self.newest_load is not None and g.fetched_at is not None and self.newest_load > g.fetched_at:
            ahead = int((self.newest_load - g.fetched_at).total_seconds())
            out.append(f"  clock skew: the newest load (dt {z(self.newest_load)}) is {ahead} s ahead of our fetch "
                       f"({z(g.fetched_at)}), within the {int(FUTURE_SKEW.total_seconds() // 60)} min tolerance: "
                       f"accepted (addendum 262 item 3: clock drift is a fact, not a fault)")
        # no load newer than the watermark (not "no new row": a new load whose rows were all refused, 262 item 5, is
        # counted in new_loads and is not "nothing new")
        if g.changed and self.rows_read and not self.new_loads and not self.refused:
            out.append(f"  no new load: the file's newest dt is the watermark ({z(self.watermark)}); nothing to "
                       f"assert")
        out.append(f"  payload sha256 {g.sha256[:16] if g.sha256 else 'none'}"
                   + (f" · {g.payload_path}" if g.payload_path else "") + f" · ETag: {g.etag}")
        out.append(ATTRIBUTION)
        return out


def writer_refusal(rows: list[dict]) -> str | None:
    """Why the writer would refuse these assertions, or None: record.assertion_refusal (the writer's own checks, its
    widths among them: player_name 128 characters, source_team and source_player_id 64) on every row, numbered as the
    writer numbers them. Run BEFORE a --file is kept (a refusal: exit 2, nothing kept, nothing written) and, on a
    fetched file, before the write (a refusal: a failed observation that keeps the payload's path) (Codex on #841,
    round 1)."""
    for i, a in enumerate(rows, 1):
        why = rec.assertion_refusal(a, i, SOURCE)
        if why:
            return why
    return None


def _assertions(parsed: Parsed, wm: datetime | None, tmap: dict, ambiguous: set, fetched: datetime,
                last_complete: dict, ing: Ingest) -> list[dict]:
    out = []
    by_load: dict = {}
    no_espn: dict = {}                    # (dt, team) -> rows refused there (262 item 5)
    cad = timedelta(hours=rec.SOURCE_CADENCE_HOURS[SOURCE])
    for dt, row in parsed.rows:
        if wm is not None and dt <= wm:
            ing.old_rows += 1
            continue
        team = row["team"]
        espn = row["espn_id"] if row["espn_id"].strip() else None
        if espn is None:
            # 262 item 5: "a row with a blank `espn_id` is counted and refused into the group's `partial` status, never
            # keyed by name": never asserted, never keyed by gsis_id or the name; its (dt, team) group is partial
            no_espn[(dt, team)] = no_espn.get((dt, team), 0) + 1
            continue
        tid = tmap.get(team) if team not in ambiguous else None
        if tid is None:
            ing.unmapped_teams[team] = ing.unmapped_teams.get(team, 0) + 1
            if team in ambiguous:
                ing.ambiguous_teams.add(team)
        attrs = {**{c: row[c] for c in ATTR_COLUMNS},
                 "dt_raw": row["dt"], "espn_id": row["espn_id"], "gsis_id": row["gsis_id"]}
        # ONE id that does not move: the chart's own (espn_id), ONLY (262 item 5); a gsis_id filled in later changes
        # attrs only (VOLATILE_ATTRS), never the key (record.player_key), so it never reads as a flip (the docstring)
        out.append({"kind": KIND, "player_id": None, "source_player_id": espn,
                    "player_name": row["player_name"] or None, "team_id": tid, "source_team": team,
                    "match_id": None, "attrs": attrs, "source_stamp": dt})
        by_load.setdefault(dt, {}).setdefault(team, 0)
        by_load[dt][team] += 1
        if fetched - dt > cad:
            ing.backfilled += 1
    for a in out:                         # the rest of a group that lost a row: partial, and says how many
        k = no_espn.get((a["source_stamp"], a["source_team"]))
        if k:
            a["attrs"][rec.ROWS_REFUSED_ATTR] = k
    ing.no_espn_rows = sum(no_espn.values())
    ing.new_loads = len(set(by_load) | {dt for dt, _ in no_espn})
    for dt in sorted(by_load):
        counts = {(SOURCE, ("src", t)): n for t, n in by_load[dt].items()}
        refused = {(SOURCE, ("src", t)) for d, t in no_espn if d == dt}
        prev = dict(last_complete)
        for key in rec.guard_load(counts, last_complete, refused):
            if key not in refused:
                ing.partial_groups.append((dt, key[1][1], counts[key], prev[key]))
    ing.no_espn_groups = sorted((dt, t, k, by_load.get(dt, {}).get(t, 0)) for (dt, t), k in no_espn.items())
    ing.partial_groups.sort(key=lambda x: (x[0], x[1]))
    ing.new_rows = len(out)
    ing.unmapped_players = len(out)
    return out


def _db_lock():
    """The chains' DB lock (#569), as cup_lineups_live._db_lock takes it: a no-op inside a chain step."""
    import sys
    hosting = str(Path(__file__).resolve().parents[2] / "deploy" / "hosting")
    if hosting not in sys.path:
        sys.path.insert(0, hosting)
    import sp_common
    return sp_common.sync_lock(on_wait=lambda p: print(f"… waiting for the DB lock {p} (a chain or closing run holds "
                                                       "it)", flush=True))


def _after_a_refused_write(got: Got, e: Exception, *, hand_carried: bool) -> None:
    """The writer refused a write AFTER a payload was kept (every check the writer runs on the rows is run before the
    keep: what is left is the store's own refusal). Never an orphan payload (Codex on #841, round 1): a --file's copy
    made by this run is removed and the refusal stands (exit 2, nothing copied, nothing written); a fetched file's
    payload stays as evidence and returns here, so the caller writes the fetch as a `failed` observation that keeps
    its path, the refusal its error. A write that kept nothing is re-raised as it was."""
    if not (got.changed and got.payload_path):
        raise e
    if hand_carried:
        if got.created:
            final = PAYLOAD_BASE / got.payload_path
            final.unlink(missing_ok=True)
            for d in (final.parent, final.parent.parent):    # the date and source directories, only when left empty
                try:
                    d.rmdir()
                except OSError:
                    break
        raise e


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run(season: int | None = None, file: str | None = None, *, http_get=None, now_fn=_now) -> Ingest:
    """THE INGEST (the module docstring): one observation, its new rows, its receipt. Refused (nothing written, no
    call) on a missing DB file, an unmigrated store, a season before 2025, or a --file that is not the 2025+ shape,
    holds a load from the future, or holds only loads older than the source's watermark. A --file is read ONCE, into
    a temporary copy that is hashed, parsed and kept (262 item 6), and removed whatever the run's end. EVERY REFUSAL IS
    SCRUBBED (Codex on #841, round 2): one that ends the run (exit 2: a --file's refused row can quote its text) is
    re-raised scrubbed as an observation's error is (_scrub: every URL's query cut, then record.redact), before the
    command prints it."""
    try:
        return _run_args(season, file, http_get=http_get, now_fn=now_fn)
    except (Refused, rec.Refused) as e:
        raise type(e)(_scrub(str(e))) from None


def _run_args(season, file, *, http_get, now_fn) -> Ingest:
    """run() itself: its argument checks, then _run."""
    season = current_season() if season is None else int(season)
    why = season_refusal(season)
    if why and file is None:
        raise Refused(why)
    path = rec._db_file()
    if path is None or not path.is_file():
        raise Refused(f"REFUSED: no DB file at {path or 'a non-file database URL'}: the record never creates one "
                      "(law 5)")
    src_file = None
    if file is not None:
        src_file = Path(file)
        if not src_file.is_file():
            raise Refused(f"REFUSED: --file {file!r} is not a file")
    endpoint = file_endpoint(src_file) if src_file is not None else release_url(season)
    why = rec.endpoint_refusal(endpoint)            # the writer's rule, before any call, copy or file (Codex #841 r1)
    if why:
        raise Refused(why)
    if src_file is None:
        return _run(season, None, endpoint, http_get=http_get, now_fn=now_fn)
    try:
        copy, sha = snapshot_copy(src_file)         # 262 item 6: the original's one read
    except OSError as e:
        # #853 F1 (ARCHITECT, addendum 381 item 3(iv)): the original unreadable or gone since is_file(), or its copy
        # failing (mkstemp, a full disk), is a refusal (exit 2), never a traceback (exit 1 is a failed observation's
        # code). Named by the error's type and strerror, never str(e), which names the temporary path; snapshot_copy
        # has removed its partial copy. run() scrubs the text.
        raise Refused(f"REFUSED: --file {src_file.name!r} could not be read into its temporary copy "
                      f"({type(e).__name__}: {e.strerror or 'no error text'}); nothing copied, nothing written") from None
    try:
        return _run(season, (src_file.name, copy, sha), endpoint, http_get=http_get, now_fn=now_fn)
    finally:
        copy.unlink(missing_ok=True)


def _run(season: int, local, endpoint: str, *, http_get, now_fn) -> Ingest:
    """run() past its argument checks; `local` is a --file's (name, temporary copy, its sha256), else None."""
    from src.db.database import readonly_scope
    if local is not None:
        parsed_local = read_file(local[1])          # the copy: refused before anything is kept or written
    with _db_lock():
        with readonly_scope() as s:
            if not rec.migrated(s):
                raise Refused("REFUSED: migrate_availability_record.py has not run (the tables and their marker); "
                              "nothing fetched, nothing written")
            prev_obs = previous_observation(s, endpoint)
            prev = prev_obs[:2] if prev_obs else None
            wm = watermark(s)
            tmap, ambiguous = team_map(s)
            last_complete = stored_complete_groups(s)
        pre = None
        if local is not None:
            now = now_fn()
            why = future_refusal(parsed_local, now) or older_refusal(parsed_local, wm)
            if why:
                raise Refused(why)                  # an operator's file: nothing copied, nothing written (exit 2)
            # every row it would assert, through the writer's own checks, BEFORE anything is kept (Codex #841 r1)
            pre = Ingest(got=Got(endpoint, now), watermark=wm)
            pre_rows = _assertions(parsed_local, wm, tmap, ambiguous, now, last_complete, pre)
            why = writer_refusal(pre_rows)
            if why:
                raise Refused(f"{why}; nothing copied, nothing written")
            got = from_file(local[1], local[0], local[2], prev, now)
        else:
            if http_get is None:
                import requests
                http_get = requests.get
            got = fetch(season, prev, http_get=http_get, now_fn=now_fn)
        ing = Ingest(got=got, watermark=wm)
        rows: list = []
        if not got.error and (not got.changed or got.restored):
            ing.status = unchanged_status(prev_obs[2] if prev_obs else None)    # #1003, 382 item 3
        if got.error:
            ing.status = "failed"
        elif got.changed and not got.restored:   # a restore is recorded as a byte-identical answer (274 item 3(1))
            try:
                if pre is not None:                 # the --file: its copy read and checked above, before the keep
                    parsed, ing, rows = parsed_local, pre, pre_rows
                    ing.got = got
                else:
                    parsed = read_file(PAYLOAD_BASE / got.payload_path)
                    why = future_refusal(parsed, got.fetched_at) or older_refusal(parsed, wm)
                    if why:
                        raise Refused(why)          # a fetched file: a failed observation, the file kept (evidence)
                    rows = _assertions(parsed, wm, tmap, ambiguous, got.fetched_at, last_complete, ing)
                    why = writer_refusal(rows)
                    if why:
                        raise Refused(why)          # the writer's own rule: the same failed observation, file kept
            except Refused as e:
                why = _scrub(str(e))                # a refusal can quote the payload: scrubbed before the cut, before
                ing = Ingest(got=got, watermark=wm, status="failed", refused=why)    # it is printed or kept (round 2)
                got.error = why[:256]
                parsed, rows = None, []
            if parsed is not None:
                ing.rows_read, ing.loads = len(parsed.rows), len(parsed.loads)
                ing.newest_load = parsed.loads[-1] if parsed.loads else None
                # 254 item 2(7): `partial` = a team or match left unmapped. A row refused (no espn_id, 262 item 5)
                # makes its GROUP partial (attrs.rows_refused), never the observation: the ruled meaning stands
                ing.status = "empty" if not parsed.rows else "partial" if ing.unmapped_teams else "complete"
        obs = {"sport": "nfl", "source": SOURCE, "endpoint": got.endpoint, "fetched_at": got.fetched_at,
               "http_status": got.http_status, "payload_sha256": got.sha256, "payload_path": got.payload_path,
               "status": ing.status, "error": got.error}
        try:
            r = rec.write_observation(obs, rows if ing.status in rec.ASSERTING else [])
        except rec.Refused as e:
            _after_a_refused_write(got, e, hand_carried=local is not None)       # raises unless a fetch kept a file
            why = _scrub(str(e))                    # the same scrub, before the cut (Codex on #841, round 2)
            ing = Ingest(got=got, watermark=wm, status="failed", refused=why)
            got.error = why[:256]
            r = rec.write_observation({**obs, "status": "failed", "error": got.error}, [])
    ing.observation_id = r.observation_id
    ing.rows_asserted = r.assertions
    return ing


__all__ = ["SOURCE", "KIND", "COLUMNS", "ATTR_COLUMNS", "FIRST_SEASON", "RELEASE_URL", "TIMEOUT", "ATTRIBUTION",
           "Refused", "Parsed", "Got", "Ingest", "current_season", "release_url", "season_refusal", "header_refusal",
           "read_file", "future_refusal", "older_refusal", "status_error", "FUTURE_SKEW", "team_map", "watermark",
           "stored_complete_groups", "previous_payload", "previous_observation",
           "unchanged_status", "lost_refusal", "stored_etag", "fetch", "snapshot_copy",
           "from_file", "writer_refusal", "run"]
